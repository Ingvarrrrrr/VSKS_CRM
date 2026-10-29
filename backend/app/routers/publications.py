import base64
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db, async_session
from app.models.platform_publication import PlatformPublication
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.schemas.schemas import PublishRequest, PublicationOut, PublicationStatusUpdate
from app.auth.jwt import get_current_user
from app.auth.permissions import require_action
from app.services.publications_payload import _build_publish_payload
from app.services.tz_items import tz_required, items_without_tz
from app.services.publications_fabrikant_client import (
    FABRIKANT_LOGIN,
    FABRIKANT_PASSWORD,
    _call_fabrikant,
    _get_platform_creds,
    _fabrikant_procedure_state,
)
from app.services.publications_roseltorg_client import _call_roseltorg
from app.services.roseltorg.client import publish_roseltorg_draft, refresh_roseltorg_status
from app.auth.object_visibility import ensure_purchase_visible

router = APIRouter(prefix="/api/publications", tags=["publications"])

PLATFORM_LABELS = {
    "fabrikant":    "Фабрикант",
    "roseltorg_rb": "Росэлторг.Бизнес",
}

SUPPORTED_PLATFORMS = set(PLATFORM_LABELS.keys())


# ── endpoints ────────────────────────────────────────────────────────────────

@router.get("/purchases/{purchase_id}", response_model=List[PublicationOut])
async def get_publications(
    purchase_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    res = await db.execute(
        select(PlatformPublication)
        .where(PlatformPublication.purchase_id == purchase_id)
        .order_by(PlatformPublication.created_at.desc())
    )
    return res.scalars().all()


@router.post("/purchases/{purchase_id}", response_model=PublicationOut)
async def publish_purchase(
    purchase_id: int,
    body: PublishRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_action('publication.create')),
):
    if body.platform not in SUPPORTED_PLATFORMS:
        raise HTTPException(400, f"Неизвестная площадка: {body.platform}")

    existing_pub = (await db.execute(
        select(PlatformPublication).where(
            PlatformPublication.purchase_id == purchase_id,
            PlatformPublication.platform == body.platform,
            PlatformPublication.status.in_(["pending", "publishing", "draft", "published"]),
        )
    )).scalar_one_or_none()
    if existing_pub:
        platform_label = PLATFORM_LABELS.get(body.platform, body.platform)
        if existing_pub.status == "draft":
            proc_ref = f" №{existing_pub.platform_number}" if existing_pub.platform_number else ""
            raise HTTPException(
                409,
                f"На {platform_label} уже создан черновик процедуры{proc_ref}. "
                "Разместите его в личном кабинете площадки. "
                "Если статус изменился — нажмите «Обновить статус» в карточке публикации."
            )
        raise HTTPException(409, f"Закупка уже опубликована или публикуется на {platform_label}")

    # ПРАВИЛО №8 п.1 (задача владельца 30.10.2026): «без ТЗ не давать
    # выставлять закупку на площадки» — без действующего ТЗ хотя бы одной
    # позиции отправка на ЛЮБУЮ площадку (Фабрикант, Росэлторг.Бизнес)
    # запрещена. Единый источник — tz_required/items_without_tz
    # (app/services/tz_items.py, ПРАВИЛО №6 — тот же гейт, что у склейки
    # дублей ТЗ в документах, вторая формула здесь не пишется). Проверяем ДО
    # создания PlatformPublication, чтобы вернуть русский 422 сразу, а не
    # дожидаться ошибки площадки (ПРАВИЛО №8 п.6 — валидный HTTP, не 500).
    purchase_for_tz = (await db.execute(
        select(Purchase)
        .options(selectinload(Purchase.items).selectinload(PurchaseItem.product))
        .where(Purchase.id == purchase_id)
    )).scalar_one_or_none()
    if not purchase_for_tz:
        raise HTTPException(404, "Закупка не найдена")
    if tz_required(purchase_for_tz):
        missing_tz_items = items_without_tz(purchase_for_tz.items)
        if missing_tz_items:
            names = ", ".join(f"«{it.item_name}»" for it in missing_tz_items)
            raise HTTPException(422, detail={
                "code": "TZ_MISSING",
                "message": (
                    f"Нет ТЗ у позиций: {names} — заполните характеристики "
                    "или отметьте «ТЗ не требуется»"
                ),
                "item_ids": [it.id for it in missing_tz_items],
            })

    payload = await _build_publish_payload(purchase_id, db)

    # «Без НМЦД» — ЕДИНСТВЕННОЕ хранимое состояние purchase.fabrikant_no_nmcd
    # (ПРАВИЛО №6, владелец 28.10.2026): то же поле читает скачивание ZIP-пакета
    # без отправки (app/routers/documents.py::download_fabrikant_package).
    # body.no_nmcd пришло явно (не None) → это новый выбор пользователя в
    # диалоге отправки — сохраняем его на закупку. Не пришло → берём текущее
    # значение закупки (диалог отправки должен помнить прошлый выбор, а не
    # сбрасывать его на эвристику при каждом открытии).
    purchase_for_nmcd = await db.get(Purchase, purchase_id)
    if purchase_for_nmcd is None:
        raise HTTPException(404, "Закупка не найдена")
    if body.no_nmcd is not None and bool(body.no_nmcd) != bool(purchase_for_nmcd.fabrikant_no_nmcd):
        purchase_for_nmcd.fabrikant_no_nmcd = bool(body.no_nmcd)
        await db.commit()
    effective_no_nmcd = bool(purchase_for_nmcd.fabrikant_no_nmcd)

    if effective_no_nmcd:
        payload["nmck"] = 0
        payload["no_nmcd"] = True

    if body.procedure_type:
        payload["procedure_type"] = body.procedure_type
    if body.proposal_start:
        payload["proposal_start"] = body.proposal_start
    if body.proposal_end:
        payload["proposal_end"] = body.proposal_end
    if body.determination_date:
        payload["determination_date"] = body.determination_date
    if body.summing_up_date:
        payload["summing_up_date"] = body.summing_up_date
    if body.okpd2_code:
        payload["okpd2_code"] = body.okpd2_code.strip()
        if body.platform == "roseltorg_rb":
            from app.models.okpd2_code import Okpd2Code
            okpd2_row = await db.get(Okpd2Code, payload["okpd2_code"])
            if okpd2_row:
                payload["okpd2_name"] = okpd2_row.name
    if body.auction_date_start:
        payload["auction_date_start"] = body.auction_date_start
    if body.auction_bet_limit_from is not None:
        payload["auction_bet_limit_from"] = body.auction_bet_limit_from
    if body.auction_bet_limit_to is not None:
        payload["auction_bet_limit_to"] = body.auction_bet_limit_to

    # ── Предварительная валидация для Фабриканта ──────────────────────────────
    # Проверяем ЗДЕСЬ (до записи в БД и фонового вызова), чтобы вернуть русский
    # 422 сразу, а не дожидаться бизнес-ошибки от ЭТП.
    if body.platform == "fabrikant":
        proc = payload.get("procedure_type") or "zp"
        if proc != "price_monitoring":
            preflight_errors: list[str] = []
            if not payload.get("delivery_state") and not payload.get("delivery_okato"):
                preflight_errors.append("Укажите субъект РФ (для места поставки)")
            if not payload.get("delivery_address"):
                preflight_errors.append("Укажите адрес доставки")
            if preflight_errors:
                raise HTTPException(422, "; ".join(preflight_errors))

    # Росэлторг.Бизнес: ОКПД2 НЕ обязателен (владелец, уточнение 28.10.2026,
    # живая проверка на черновике 303879) — позиция с okpd2Code="" создаётся
    # успешно, площадка не требует код.
    #
    # Но регион доставки / условия оплаты / единицы измерения позиций —
    # ОБЯЗАТЕЛЬНЫ (разработчик проверил живьём на площадке 29.10.2026, 13
    # размещённых процедур ДНР): PUT принимает что угодно, ошибка всплывает
    # только на publish. Решение владельца по итогам проверки: «Условия
    # оплаты» — поле обязательное именно при отправке на площадку (сохранить
    # закупку без него можно), единица измерения позиции — только из списка.
    # Проверяем здесь (ПРАВИЛО №8: preflight ДО создания черновика, русский
    # 422 сразу), используя ТЕ ЖЕ расчёты, что и сам client.py (ПРАВИЛО №6 —
    # resolve_roseltorg_region/build_lot_payment/find_items_with_unknown_unit,
    # не второй расчёт).
    if body.platform == "roseltorg_rb":
        from app.services.roseltorg.lot_requirements import resolve_roseltorg_region
        from app.services.roseltorg.items import load_purchase_item_rows, find_items_with_unknown_unit

        rb_errors: list[str] = []
        if not resolve_roseltorg_region(payload):
            city = payload.get("delivery_city_raw") or "—"
            rb_errors.append(
                f"Не найден населённый пункт доставки в справочнике Росэлторга: «{city}»"
                + (f", {payload['delivery_region_raw']}" if payload.get("delivery_region_raw") else "")
            )

        terms_type = payload.get("payment_terms_type") or "postpayment"
        if terms_type == "postponement" and not payload.get("payment_postpone_days"):
            rb_errors.append("Укажите количество дней отсрочки платежа (Условия оплаты)")
        if terms_type == "other" and not (payload.get("payment_other_terms") or "").strip():
            rb_errors.append("Укажите текст условий оплаты «Иное» (Условия оплаты)")

        _rb_purchase, _rb_rows = await load_purchase_item_rows(db, purchase_id)
        bad_units = find_items_with_unknown_unit(_rb_rows)
        if bad_units:
            rb_errors.append(
                "Единица измерения не из справочника ОКЕИ у позиций: " + "; ".join(bad_units)
            )
        if rb_errors:
            raise HTTPException(422, "; ".join(rb_errors))

    pub = PlatformPublication(
        purchase_id=purchase_id,
        platform=body.platform,
        status="publishing",
    )
    db.add(pub)
    await db.commit()
    await db.refresh(pub)

    if body.platform == "fabrikant":
        background_tasks.add_task(
            _call_fabrikant, pub.id, payload, current_user.id,
            body.attach_documents,
        )
    elif body.platform == "roseltorg_rb":
        background_tasks.add_task(
            _call_roseltorg, pub.id, payload, current_user.id,
            body.attach_documents,
        )

    return pub


@router.post("/{pub_id}/refresh", response_model=PublicationOut)
async def refresh_publication_status(
    pub_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Запрашивает актуальное состояние процедуры на площадке и обновляет запись публикации.

    Поддерживается только Фабрикант (getProcedureInfo — синхронная операция).
    """
    res = await db.execute(select(PlatformPublication).where(PlatformPublication.id == pub_id))
    pub = res.scalar_one_or_none()
    if not pub:
        raise HTTPException(404, "Публикация не найдена")

    if pub.platform == "roseltorg_rb":
        result = await refresh_roseltorg_status(pub_id, current_user.id)
        if not result["ok"]:
            raise HTTPException(502, result["detail"])
        await db.refresh(pub)
        return pub

    if pub.platform != "fabrikant":
        raise HTTPException(400, f"Обновление статуса поддерживается только для Фабриканта и Росэлторг.Бизнес, а не для {pub.platform}")

    # Получаем credentials текущего пользователя (или env-fallback)
    login = FABRIKANT_LOGIN
    password = FABRIKANT_PASSWORD
    try:
        async with async_session() as cred_db:
            result = await _get_platform_creds(cred_db, current_user.id, "fabrikant")
        if result:
            login, password = result
    except Exception:
        pass

    if not login or not password:
        raise HTTPException(503, "Не заданы учётные данные Фабриканта")

    auth = base64.b64encode(f"{login}:{password}".encode()).decode()

    # Загружаем закупку, чтобы получить правильный идентификатор процедуры на площадке.
    # external_id хранит requestId SOAP-запроса, а getProcedureInfo принимает purchaseId/lotId —
    # то есть registry_number закупки или её числовой id (как при публикации).
    purchase_res = await db.execute(select(Purchase).where(Purchase.id == pub.purchase_id))
    purchase = purchase_res.scalar_one_or_none()
    if not purchase:
        raise HTTPException(404, f"Закупка #{pub.purchase_id} для публикации {pub_id} не найдена")

    lookup_id = (purchase.registry_number or "").strip() or str(purchase.id)
    if not lookup_id:
        raise HTTPException(
            400,
            "Процедура ещё не создана на площадке (нет идентификатора закупки) — обновлять нечего",
        )

    pi = await _fabrikant_procedure_state(lookup_id, auth)

    if pi is None:
        raise HTTPException(502, "Не удалось получить состояние процедуры от Фабриканта")

    state_str = pi.get("state") or ""
    new_status = "draft" if "черновик" in state_str.lower() else "published"
    new_url = pi.get("procedure_url") or pub.external_url

    pub.platform_state  = state_str
    pub.platform_number = pi.get("procedure_number") or pub.platform_number
    pub.external_url    = new_url
    pub.status          = new_status
    if new_status == "published" and not pub.published_at:
        pub.published_at = datetime.now(timezone.utc)
    pub.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(pub)
    return pub


@router.post("/{pub_id}/publish-draft", response_model=PublicationOut)
async def publish_draft(
    pub_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_action('publication.create')),
):
    """Размещает ранее созданный черновик процедуры (сейчас — только Росэлторг.Бизнес,
    POST /notices/{id}/publish). Фабрикант такого отдельного шага не требует —
    площадка публикует процедуру сама в рамках SOAP-вызова размещения.

    ПРАВИЛО №8: та же видимая закупка + то же право publication.create, что
    при создании публикации; ошибки площадки — текстом в detail 4xx, не 500.
    """
    res = await db.execute(select(PlatformPublication).where(PlatformPublication.id == pub_id))
    pub = res.scalar_one_or_none()
    if not pub:
        raise HTTPException(404, "Публикация не найдена")

    await ensure_purchase_visible(current_user, pub.purchase_id, db)

    if pub.platform != "roseltorg_rb":
        raise HTTPException(400, f"Размещение черновика поддерживается только для Росэлторг.Бизнес, а не для {pub.platform}")

    result = await publish_roseltorg_draft(pub_id, current_user.id)
    if not result["ok"]:
        raise HTTPException(422, result["detail"])

    await db.refresh(pub)
    return pub


@router.patch("/{pub_id}/status", response_model=PublicationOut)
async def update_publication_status(
    pub_id: int,
    body: PublicationStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Обновляет статус публикации (используется для ручного сброса и обратной совместимости).
    Аудит безопасности 2026-09-29: требуем вход, как у соседнего refresh_publication_status."""
    res = await db.execute(select(PlatformPublication).where(PlatformPublication.id == pub_id))
    pub = res.scalar_one_or_none()
    if not pub:
        raise HTTPException(404, "Публикация не найдена")

    pub.status = body.status
    if body.external_id:
        pub.external_id = body.external_id
    if body.external_url:
        pub.external_url = body.external_url
    if body.error_text:
        pub.error_text = body.error_text
    if body.status == "published":
        pub.published_at = datetime.now(timezone.utc)
    pub.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(pub)
    return pub
