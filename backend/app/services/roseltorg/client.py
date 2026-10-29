"""Оркестрация создания черновика процедуры на Росэлторг.Бизнес.

Разрезано из publications_roseltorg_client.py (ПРАВИЛО №5): этот файл только
последовательность вызовов API (new → PUT → notice-lot → items → documents),
авторизация — auth.py, позиции — items.py, единицы — okei.py.

НЕ публикует автоматически (владелец): результат — черновик (status='draft',
external_id=noticeId). Публикацию делает отдельный шаг — publish_roseltorg_draft
(вызывается роутом POST /api/publications/{pub_id}/publish-draft).
"""
import logging
from datetime import datetime, timezone, date

from sqlalchemy import select

from app.database import async_session
from app.models.platform_publication import PlatformPublication
from app.services.publications_status import (
    _set_pub_success,
    _set_pub_error,
    _set_pub_attachments_result,
)
from app.services.publications_fabrikant_client import _get_platform_creds

from .auth import (
    ROSELTORG_TOKEN,
    ROSELTORG_BASE_URL,
    ROSELTORG_TEMPLATE_IDS,
    get_roseltorg_jwt,
    rb_call,
    rb_call_multipart,
    rb_ok,
    rb_error_text,
    RoseltorgAuthError,
)
from .items import load_purchase_item_rows, build_roseltorg_item_payloads
from .lot_requirements import resolve_roseltorg_region, build_lot_payment

logger = logging.getLogger(__name__)

# Кабинет площадки — используется как ссылка черновика, когда точный адрес
# страницы черновика неизвестен (владелец, живая проверка 28.10.2026, черновик
# 303879): точного URL страницы черновика нет в документации/ответах API.
ROSELTORG_CABINET_URL = "https://business.roseltorg.ru/"


def _iso_day(dt_str: str | None) -> tuple[str, str] | None:
    """ISO-datetime или ISO-date из формы → (date-часть 00:00:00, тот же
    день с временем из dt_str, либо тоже 00:00:00 если времени не было).
    Формат площадки — ISO БЕЗ часового пояса (проверено живьём)."""
    if not dt_str:
        return None
    try:
        # datetime-local фронта шлёт "YYYY-MM-DDTHH:MM" — без секунд/TZ
        dt = datetime.fromisoformat(dt_str)
    except ValueError:
        return None
    day = dt.date()
    date_part = f"{day.isoformat()}T00:00:00"
    time_part = dt.strftime("%Y-%m-%dT%H:%M:%S")
    return date_part, time_part


def _build_order_stages(payload: dict) -> list[dict]:
    """Массив этапов Order для PUT /notices/{id} (владелец, живая проверка):
    AcceptanceApplicationsDateBegin/.../SummingUp. Begin — ВСЕГДА сегодня
    (проверка площадки: дата начала приёма ≤ текущей) — proposal_start из
    payload для Begin НЕ используется. End/SummingUp — только если заданы
    в payload, иначе этапы не шлём (площадка даёт заполнить в кабинете)."""
    today = date.today()
    today_iso = f"{today.isoformat()}T00:00:00"
    stages = [
        {"type": "AcceptanceApplicationsDateBegin", "date": today_iso, "time": today_iso},
    ]
    end_pair = _iso_day(payload.get("proposal_end"))
    if end_pair:
        stages.append({"type": "AcceptanceApplicationsDateEnd", "date": end_pair[0], "time": end_pair[1]})
    summing_pair = _iso_day(payload.get("summing_up_date"))
    if summing_pair:
        stages.append({"type": "SummingUp", "date": summing_pair[0], "time": summing_pair[1]})
    return stages


async def _resolve_roseltorg_token(user_id: int | None) -> str:
    """Токен из личной учётки пользователя (platform='roseltorg', приоритет),
    иначе запасной ROSELTORG_TOKEN из окружения (ПРАВИЛО №6: тот же
    _get_platform_creds, что у Фабриканта — не второй механизм хранения).

    Токен хранится в зашифрованном поле пароля UserPlatformCredential
    (login у roseltorg может быть пустой строкой — у площадки нет понятия
    логина для интеграционного токена).
    """
    if user_id is not None:
        try:
            async with async_session() as cred_db:
                creds = await _get_platform_creds(cred_db, user_id, "roseltorg")
            if creds:
                _login, token = creds
                if token:
                    return token
        except Exception:
            pass
    return ROSELTORG_TOKEN


async def _attach_roseltorg_documents(jwt: str, notice_id: int, purchase_id: int) -> list[dict]:
    """Рендерит пакет Росэлторга (5 документов Фабриканта + xlsx позиций) и
    прикрепляет каждый файл к черновику. Сбой файлов НЕ роняет публикацию —
    только пишется в attachments_result (как у Фабриканта)."""
    from app.routers.documents import render_fabrikant_package_files
    from app.services.documents.roseltorg_package import render_roseltorg_package_files

    results: list[dict] = []
    async with async_session() as db:
        fab_rendered, fab_errors = await render_fabrikant_package_files(db, purchase_id)
        ros_rendered, ros_errors = await render_roseltorg_package_files(db, purchase_id)

    for err in fab_errors + ros_errors:
        file_label = err.split(":")[0] if ":" in err else "unknown"
        results.append({"file": file_label, "ok": False, "error": err[:300]})

    all_files = [(name, data) for (name, _title, data) in fab_rendered] + list(ros_rendered)

    base = ROSELTORG_BASE_URL
    for file_name, file_data in all_files:
        try:
            resp, status = await rb_call_multipart(
                jwt, f"{base}/notices/{notice_id}/documents", file_name, file_data,
            )
            if rb_ok(resp, status):
                results.append({"file": file_name, "ok": True})
            else:
                results.append({"file": file_name, "ok": False, "error": rb_error_text(resp)})
        except Exception as exc:
            results.append({"file": file_name, "ok": False, "error": str(exc)[:300]})

    return results


async def _call_roseltorg(
    pub_id: int,
    payload: dict,
    user_id: int | None = None,
    attach_documents: bool = False,
):
    """Создаёт черновик процедуры на Росэлторг.Бизнес из payload закупки.

    payload — результат _build_publish_payload (publications_payload.py),
    дополненный роутером полями procedure_type/proposal_start/proposal_end/
    okpd2_code (тот же PublishRequest, что у Фабриканта — ПРАВИЛО №6, поля
    не переизобретаются под вторую площадку).
    """
    token = await _resolve_roseltorg_token(user_id)
    if not token:
        await _set_pub_error(
            pub_id,
            "Не задан токен Росэлторг.Бизнес — укажите его в профиле "
            "(Учётные данные площадок → Росэлторг.Бизнес) или ROSELTORG_TOKEN в окружении сервера.",
        )
        return

    # ОКПД2 НЕ обязателен (живая проверка владельцем на черновике 303879,
    # уточнение 28.10.2026): позиция с okpd2Code="" создаётся успешно — отказ
    # «код … не найден» был только когда ключа не было вовсе в теле, не из-за
    # пустого значения. Ключ всегда шлётся пустой строкой — build_roseltorg_item_payloads.
    try:
        jwt = await get_roseltorg_jwt(token)
    except RoseltorgAuthError as e:
        await _set_pub_error(pub_id, f"Ошибка авторизации Росэлторг: {str(e)[:250]}")
        return
    except Exception as e:
        await _set_pub_error(pub_id, f"Ошибка авторизации Росэлторг: {str(e)[:250]}")
        return

    base = ROSELTORG_BASE_URL
    procedure_type = payload.get("procedure_type") or "request_quotations"
    template_id = ROSELTORG_TEMPLATE_IDS.get(procedure_type, ROSELTORG_TEMPLATE_IDS["request_quotations"])
    subject = payload.get("subject") or f"Закупка {payload.get('registry_number', '')}"
    nmck = payload.get("nmck", 0)
    purchase_id = int(payload.get("purchase_id") or 0)

    try:
        # Шаг 1: создаём черновик процедуры по выбранному шаблону
        result, status = await rb_call(jwt, f"{base}/notices/{template_id}/new")
        notice_id = (result.get("data") or {}).get("noticeId")
        if not rb_ok(result, status) or not notice_id:
            await _set_pub_error(pub_id, f"Росэлторг создание процедуры: {rb_error_text(result)}")
            return

        # Сохраняем noticeId сразу — виден в карточке публикации даже если
        # дальше произойдёт сбой (ссылка на черновик уже существует).
        async with async_session() as db:
            res = await db.execute(select(PlatformPublication).where(PlatformPublication.id == pub_id))
            pub = res.scalar_one_or_none()
            if pub:
                pub.external_id = str(notice_id)
                await db.commit()

        # Шаг 2: название процедуры и этапы приёма предложений. Обёртка
        # {"data": {...}} ОБЯЗАТЕЛЬНА (живая проверка: без неё success:true,
        # но ничего не сохраняется). mainCustomerInn НЕ шлём — это поле
        # означает «процедура для другой компании», заказчик (ВСКС)
        # подставляется площадкой сам из учётки токена.
        put_body: dict = {
            "data": {
                "ProcedureMainInfo": {"name": subject},
                "Order": _build_order_stages(payload),
            }
        }
        put_result, put_status = await rb_call(jwt, f"{base}/notices/{notice_id}", put_body, method="PUT")
        if not rb_ok(put_result, put_status):
            logger.warning(
                "Roseltorg PUT /notices/%s: %s (не блокирует создание лота)",
                notice_id, rb_error_text(put_result),
            )

        # Шаг 3: лот — НМЦК/валюта/адрес и регион доставки/срок поставки из
        # _build_publish_payload (ПРАВИЛО №6, не собираем заново). Обёртка
        # {"data": {...}} и currency="643" (код ОКВ рубля) — живая проверка:
        # с "RUB" площадка отвечает success:false "Currency not found.".
        no_nmcd = bool(payload.get("no_nmcd"))
        lot_data_body: dict = {
            "name": subject,
            "currency": "643",
        }
        if not no_nmcd:
            # «Без НМЦД» (то же поле, что у Фабриканта, ПРАВИЛО №6): живая
            # проверка площадки — лот БЕЗ ключа initialSum создаётся штатно
            # (initialSum=0, methodToSpecifyLotPrice="initial"; 37 из 57
            # опубликованных лотов на площадке именно такие) — ключ не шлём
            # вовсе, не "0" (не допустимое значение-пустышка).
            lot_data_body["initialSum"] = str(nmck)
        if payload.get("delivery_address"):
            lot_data_body["DeliveryDetails"] = payload["delivery_address"]
        if payload.get("execution_term"):
            lot_data_body["DeliveryTerm"] = payload["execution_term"]

        # lot.region — населённый пункт доставки из справочника площадки
        # (разработчик проверил живьём 29.10.2026): без него — «Регионы доставки:
        # Место поставки должно быть заполнено». Preflight в publications.py
        # уже отверг отправку без совпадения — сюда доходит только найденный
        # (но сбой здесь не должен ронять уже созданный черновик, см. except ниже).
        region_match = resolve_roseltorg_region(payload)
        if region_match:
            lot_data_body["region"] = [region_match]

        # lot.payment — условия оплаты (формат проверен разработчиком живьём
        # 29.10.2026): PUT принимает
        # любое значение, ошибка всплывает только на publish — поэтому
        # preflight в publications.py проверяет согласованность ДО черновика,
        # здесь просто собираем тело из того же источника (ПРАВИЛО №6).
        lot_data_body["payment"] = build_lot_payment(
            payload.get("payment_terms_type"),
            payload.get("payment_postpone_days"),
            payload.get("payment_postpone_day_type"),
            payload.get("payment_other_terms"),
        )

        lot_result, lot_status = await rb_call(
            jwt, f"{base}/notices/{notice_id}/notice-lot", {"data": lot_data_body},
        )
        if not rb_ok(lot_result, lot_status):
            await _set_pub_error(pub_id, f"Росэлторг создание лота: {rb_error_text(lot_result)}")
            return
        lot_data = lot_result.get("data") or {}
        notice_lot_id = lot_data.get("noticeLotId") or lot_data.get("id")

        # Шаг 4: позиции лота — из того же источника, что и xlsx «Позиции по лоту»
        attach_errors: list[str] = []
        if notice_lot_id and purchase_id:
            async with async_session() as db:
                try:
                    _purchase, raw_rows = await load_purchase_item_rows(db, purchase_id)
                except Exception as e:
                    raw_rows = []
                    attach_errors.append(f"Позиции закупки: {type(e).__name__}: {e}")

            items_payloads = build_roseltorg_item_payloads(
                raw_rows,
                okpd2_code=payload.get("okpd2_code"),
                okpd2_name=payload.get("okpd2_name"),
                no_nmcd=no_nmcd,
            )
            for item_data in items_payloads:
                item_result, item_status = await rb_call(
                    jwt, f"{base}/notice/lot/{notice_lot_id}/items", {"data": item_data},
                )
                if not rb_ok(item_result, item_status):
                    attach_errors.append(f"Позиция «{item_data.get('name')}»: {rb_error_text(item_result)}")

        # Шаг 5: документы пакета Росэлторг — сбой не роняет публикацию
        attachments_results: list[dict] = [{"file": "позиция", "ok": False, "error": e} for e in attach_errors]
        if attach_documents and purchase_id:
            try:
                doc_results = await _attach_roseltorg_documents(jwt, notice_id, purchase_id)
                attachments_results.extend(doc_results)
            except Exception as exc:
                attachments_results.append({"file": "пакет документов", "ok": False, "error": str(exc)[:300]})

        if attachments_results:
            await _set_pub_attachments_result(pub_id, attachments_results)

        # Результат — ЧЕРНОВИК (владелец: не публиковать автоматически).
        # Ссылка — кабинет площадки (точный адрес страницы черновика
        # неизвестен, см. ROSELTORG_CABINET_URL); номер подтянется через
        # refresh_roseltorg_status (procedureRegistrationNumber).
        await _set_pub_success(
            pub_id,
            external_id=str(notice_id),
            external_url=ROSELTORG_CABINET_URL,
            status="draft",
            platform_number=None,
            platform_state="noticeDraft",
        )
    except Exception as e:
        logger.exception("Roseltorg _call_roseltorg error pub=%s", pub_id)
        await _set_pub_error(pub_id, f"Ошибка Росэлторг: {str(e)[:250]}")


async def publish_roseltorg_draft(pub_id: int, user_id: int | None = None) -> dict:
    """Публикует ранее созданный черновик (POST /notices/{id}/publish).

    Возвращает {"ok": bool, "detail": str} — роутер сам решает, как ответить
    клиенту (это НЕ фоновая задача, пользователь ждёт результат синхронно).
    """
    async with async_session() as db:
        res = await db.execute(select(PlatformPublication).where(PlatformPublication.id == pub_id))
        pub = res.scalar_one_or_none()
    if not pub:
        return {"ok": False, "detail": "Публикация не найдена"}
    if pub.platform != "roseltorg_rb":
        return {"ok": False, "detail": "Публикация черновика поддерживается только для Росэлторг.Бизнес"}
    if pub.status != "draft" or not pub.external_id:
        return {"ok": False, "detail": "У публикации нет черновика для размещения"}

    token = await _resolve_roseltorg_token(user_id)
    if not token:
        return {"ok": False, "detail": "Не задан токен Росэлторг.Бизнес"}

    try:
        jwt = await get_roseltorg_jwt(token)
    except Exception as e:
        return {"ok": False, "detail": f"Ошибка авторизации Росэлторг: {str(e)[:250]}"}

    base = ROSELTORG_BASE_URL
    result, status = await rb_call(jwt, f"{base}/notices/{pub.external_id}/publish")
    if not rb_ok(result, status):
        err = rb_error_text(result)
        await _set_pub_error(pub_id, f"Росэлторг публикация: {err}")
        return {"ok": False, "detail": err}

    await _set_pub_success(
        pub_id,
        external_id=pub.external_id,
        external_url=pub.external_url,
        status="published",
        platform_number=pub.platform_number,
        platform_state="published",
    )
    return {"ok": True, "detail": "Процедура размещена"}


async def refresh_roseltorg_status(pub_id: int, user_id: int | None = None) -> dict:
    """GET /notices/{id}/status → обновляет platform_state/platform_number/status.

    Возвращает {"ok": bool, "detail": str}."""
    async with async_session() as db:
        res = await db.execute(select(PlatformPublication).where(PlatformPublication.id == pub_id))
        pub = res.scalar_one_or_none()
    if not pub or not pub.external_id:
        return {"ok": False, "detail": "У публикации нет идентификатора процедуры на площадке"}

    token = await _resolve_roseltorg_token(user_id)
    if not token:
        return {"ok": False, "detail": "Не задан токен Росэлторг.Бизнес"}

    try:
        jwt = await get_roseltorg_jwt(token)
    except Exception as e:
        return {"ok": False, "detail": f"Ошибка авторизации Росэлторг: {str(e)[:250]}"}

    base = ROSELTORG_BASE_URL
    result, status = await rb_call(jwt, f"{base}/notices/{pub.external_id}/status", method="GET")
    if not rb_ok(result, status):
        return {"ok": False, "detail": rb_error_text(result)}

    data = result.get("data") or {}
    notice_state = data.get("noticeState") or ""
    last_errors = data.get("lastError") or []
    new_status = "published" if notice_state not in ("", "noticeDraft") else "draft"

    async with async_session() as db:
        res = await db.execute(select(PlatformPublication).where(PlatformPublication.id == pub_id))
        pub = res.scalar_one_or_none()
        if pub:
            pub.platform_state = notice_state
            pub.platform_number = data.get("procedureRegistrationNumber") or pub.platform_number
            pub.status = new_status
            if new_status == "published" and not pub.published_at:
                pub.published_at = datetime.now(timezone.utc)
            pub.updated_at = datetime.now(timezone.utc)
            await db.commit()

    detail = f"Статус: {notice_state or 'неизвестен'}"
    if last_errors:
        detail += "; ошибки площадки: " + "; ".join(str(e) for e in last_errors)
    return {"ok": True, "detail": detail}
