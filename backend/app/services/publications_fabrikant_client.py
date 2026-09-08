"""Сетевые вызовы Фабриканта: getProcedureInfo, addFileToPurchaseNotice, покупка, поллинг (волна резки publications.py)."""
import asyncio
import base64
import logging
import os
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.platform_publication import PlatformPublication
from app.services.publications_status import (
    _make_ssl_ctx,
    _set_pub_success,
    _set_pub_error,
    _set_pub_platform_number,
    _set_pub_attachments_result,
)
from app.services.publications_fabrikant_soap import (
    FABRIKANT_URL,
    FABRIKANT_CHECK_URL,
    NS_PI,
    NS_CR,
    FABRIKANT_SOAP_ACTION_ADD_FILE,
    _FABRIKANT_SOAP_ACTION,
    _FABRIKANT_SOAP_ACTION_CHECK,
    _FABRIKANT_SOAP_ACTION_GET_INFO,
    _build_soap_xml,
    _build_add_file_soap_xml,
)

logger = logging.getLogger(__name__)

FABRIKANT_LOGIN = os.getenv("FABRIKANT_LOGIN", "")
FABRIKANT_PASSWORD = os.getenv("FABRIKANT_PASSWORD", "")


async def _fabrikant_procedure_state(purchase_id_str: str, auth: str) -> dict | None:
    """Синхронный вызов getProcedureInfo — возвращает словарь с состоянием процедуры.

    Возвращает None при любой ошибке (наружу исключения не пробрасываем).
    """
    soap_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
        "<soap:Body>"
        f'<pi:getProcedureInfo xmlns:pi="{NS_PI}">'
        "<pi:body><pi:item><pi:getProcedureInfoData>"
        f"<pi:purchaseId>{purchase_id_str}</pi:purchaseId>"
        f"<pi:lotId>{purchase_id_str}</pi:lotId>"
        "</pi:getProcedureInfoData></pi:item></pi:body>"
        "</pi:getProcedureInfo>"
        "</soap:Body></soap:Envelope>"
    )
    try:
        req = urllib.request.Request(
            FABRIKANT_URL,
            data=soap_xml.encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "Authorization": f"Basic {auth}",
                "SOAPAction": _FABRIKANT_SOAP_ACTION_GET_INFO,
                "User-Agent": "VSKS-CRM/1.0",
            },
        )
        loop = asyncio.get_event_loop()
        try:
            resp = await loop.run_in_executor(
                None, lambda: urllib.request.urlopen(req, timeout=30, context=_make_ssl_ctx())
            )
            resp_text = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            resp_text = e.read().decode("utf-8", errors="replace")

        logger.info("Fabrikant getProcedureInfo (purchaseId=%s): %.600s", purchase_id_str, resp_text)

        # Парсим локальными именами тегов, namespace-префикс произвольный
        state_m   = re.search(r"<[^:>\s]*:?state[^>]*>([^<]+)<", resp_text)
        lot_st_m  = re.search(r"<[^:>\s]*:?status[^>]*>([^<]+)<", resp_text)
        num_m     = re.search(r"<[^:>\s]*:?procedureNumber[^>]*>([^<]+)<", resp_text)
        # procedureUrl НЕ должен матчить draftProcedureUrl — негативный lookahead как в поллинге
        url_m     = re.search(r"<(?:[^:>\s]*:)?procedureUrl(?![A-Za-z])[^>]*>([^<]+)<", resp_text)

        if not state_m:
            logger.warning("getProcedureInfo: не удалось извлечь state из ответа")
            return None

        return {
            "state":            state_m.group(1).strip(),
            "lot_status":       lot_st_m.group(1).strip() if lot_st_m else None,
            "procedure_number": num_m.group(1).strip() if num_m else None,
            "procedure_url":    url_m.group(1).strip() if url_m else None,
        }

    except Exception as exc:
        logger.warning("Fabrikant getProcedureInfo error (purchaseId=%s): %s", purchase_id_str, exc)
        return None


async def _attach_documents_to_notice(
    pub_id: int,
    purchase_id_str: str,
    purchase_db_id: int,
    auth: str,
):
    """Рендерит 5 документов и прикрепляет каждый к извещению Фабрикант.

    Частичный сбой прикрепления НЕ меняет статус публикации — только
    записывает детали в attachments_result.
    """
    # Импорт внутри функции чтобы избежать циклического импорта
    from app.routers.documents import render_fabrikant_package_files

    async with async_session() as db:
        rendered, render_errors = await render_fabrikant_package_files(db, purchase_db_id)

    results = []

    # Render errors — сразу фиксируем как failed
    for err_msg in render_errors:
        # extract file name from error message prefix "filename.docx: ..."
        file_label = err_msg.split(":")[0] if ":" in err_msg else "unknown"
        results.append({"file": file_label, "ok": False, "error": err_msg[:300]})

    loop = asyncio.get_event_loop()

    for n, (ascii_name, ru_title, file_data) in enumerate(rendered, start=1):
        file_id = f"{purchase_id_str}-doc-{n}"
        file_bytes_b64 = base64.b64encode(file_data).decode("ascii")

        soap_xml = _build_add_file_soap_xml(
            purchase_id_str=purchase_id_str,
            file_id=file_id,
            file_name=ascii_name,
            title=ru_title[:255],
            file_bytes_b64=file_bytes_b64,
        )

        try:
            req = urllib.request.Request(
                FABRIKANT_URL,
                data=soap_xml.encode("utf-8"),
                method="POST",
                headers={
                    "Content-Type": "text/xml; charset=utf-8",
                    "Authorization": f"Basic {auth}",
                    "SOAPAction": FABRIKANT_SOAP_ACTION_ADD_FILE,
                    "User-Agent": "VSKS-CRM/1.0",
                },
            )
            try:
                resp = await loop.run_in_executor(
                    None, lambda: urllib.request.urlopen(req, timeout=30, context=_make_ssl_ctx())
                )
                resp_text = resp.read().decode("utf-8")
                resp_status = resp.status
            except urllib.error.HTTPError as e:
                resp_text = e.read().decode("utf-8", errors="replace")
                resp_status = e.code

            logger.info(
                "Fabrikant addFileToPurchaseNotice file=%s pub=%d: HTTP %s %.400s",
                ascii_name, pub_id, resp_status, resp_text,
            )

            # Ответ операции — messageAccepted (асинхронный), ошибка — Fault / <error>
            fault_m = re.search(r"<[^:>\s]*:?faultstring[^>]*>([^<]+)<", resp_text)
            err_m = re.search(r"<[^:>\s]*:?error\b[^>]*>([^<]{3,})<", resp_text)
            if fault_m:
                results.append({"file": ascii_name, "ok": False, "error": fault_m.group(1).strip()[:300]})
            elif err_m:
                results.append({"file": ascii_name, "ok": False, "error": err_m.group(1).strip()[:300]})
            elif resp_status not in (200, 202):
                results.append({"file": ascii_name, "ok": False, "error": f"HTTP {resp_status}: {resp_text[:200]}"})
            else:
                results.append({"file": ascii_name, "ok": True})

        except Exception as exc:
            results.append({"file": ascii_name, "ok": False, "error": str(exc)[:300]})
            logger.warning("Fabrikant addFile error for %s pub=%d: %s", ascii_name, pub_id, exc)

    await _set_pub_attachments_result(pub_id, results)
    ok_count = sum(1 for r in results if r.get("ok"))
    logger.info("Fabrikant attach documents: pub=%d total=%d ok=%d", pub_id, len(results), ok_count)



async def _poll_fabrikant_result(
    pub_id: int,
    request_id: str,
    auth: str,
    attempts: int = 0,
    attach_documents: bool = False,
    purchase_id_str: str = "",
    purchase_db_id: int = 0,
):
    """Poll checkRequest every 30s until responseIsReady, then update publication."""
    MAX_ATTEMPTS = 20  # 10 minutes max

    soap_check = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
        "<soap:Body>"
        f'<cr:checkRequest xmlns:cr="{NS_CR}">'
        f"<cr:requestId>{request_id}</cr:requestId>"
        "</cr:checkRequest>"
        "</soap:Body></soap:Envelope>"
    )

    try:
        req = urllib.request.Request(
            FABRIKANT_CHECK_URL,
            data=soap_check.encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "Authorization": f"Basic {auth}",
                "SOAPAction": _FABRIKANT_SOAP_ACTION_CHECK,
                "User-Agent": "VSKS-CRM/1.0",
            },
        )
        loop = asyncio.get_event_loop()
        try:
            resp = await loop.run_in_executor(
                None, lambda: urllib.request.urlopen(req, timeout=30, context=_make_ssl_ctx())
            )
            resp_text = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            resp_text = e.read().decode("utf-8", errors="replace")

        logger.info("Fabrikant checkRequest (pub=%d attempt=%d): %.800s", pub_id, attempts, resp_text)

        # Check responseIsReady flag
        ready_m = re.search(r"<[^:>\s]*:?responseIsReady[^>]*>([^<]+)<", resp_text)
        is_ready = ready_m and ready_m.group(1).strip() in ("1", "true", "True")

        if not is_ready:
            if attempts < MAX_ATTEMPTS:
                await asyncio.sleep(30)
                await _poll_fabrikant_result(
                    pub_id, request_id, auth, attempts + 1,
                    attach_documents=attach_documents,
                    purchase_id_str=purchase_id_str,
                    purchase_db_id=purchase_db_id,
                )
            else:
                await _set_pub_error(pub_id, f"Фабрикант: таймаут ожидания результата (requestId={request_id})")
            return

        # Ready — check for error (match <message> or <ns1:message> with non-trivial content)
        err_m = re.search(r"<[^:>\s]*:?message\b[^>]*>([^<]{5,})<", resp_text)

        # Извлекаем номер процедуры из ответа создания извещения
        num_m      = re.search(r"<[^:>\s]*:?procedureNumber[^>]*>([^<]+)<", resp_text)
        # draftProcedureUrl — рабочая ссылка на черновик (procedureUrl даёт 403 до размещения)
        draft_m    = re.search(r"<[^:>\s]*:?draftProcedureUrl[^>]*>([^<]+)<", resp_text)
        # procedureUrl НЕ должен матчить draftProcedureUrl — используем негативный lookahead
        url_m      = re.search(r"<(?:[^:>\s]*:)?procedureUrl(?![A-Za-z])[^>]*>([^<]+)<", resp_text)

        if url_m or draft_m:
            # При наличии черновика используем его URL — он открывается сразу без авторизации
            effective_url = (draft_m.group(1).strip() if draft_m else url_m.group(1).strip())
            proc_number   = num_m.group(1).strip() if num_m else None

            # Сохраняем номер процедуры ДО рендера документов — печатная форма
            # (notice_number) читает platform_number из БД внутри _attach_documents_to_notice,
            # иначе там был бы виден ещё не проставленный номер (fallback на external_id)
            if proc_number:
                try:
                    await _set_pub_platform_number(pub_id, proc_number)
                except Exception as _pne:
                    logger.warning("Fabrikant _set_pub_platform_number failed pub=%d: %s", pub_id, _pne)

            # Прикрепляем документы ДО определения финального статуса, т.к. площадка
            # может не позволить размещение извещения без документов
            if attach_documents and purchase_db_id:
                try:
                    await _attach_documents_to_notice(
                        pub_id=pub_id,
                        purchase_id_str=purchase_id_str or request_id,
                        purchase_db_id=purchase_db_id,
                        auth=auth,
                    )
                except Exception as _ae:
                    logger.error("Fabrikant attach_documents failed pub=%d: %s", pub_id, _ae)

            # Проверяем фактическое состояние процедуры на площадке
            lookup_id = purchase_id_str or request_id
            pi = await _fabrikant_procedure_state(lookup_id, auth)

            if pi is not None:
                state_str = pi.get("state") or ""
                # Площадка вернула «Черновик» — фиксируем draft, иначе published
                final_status = "draft" if "черновик" in state_str.lower() else "published"
                final_state  = state_str
                # Номер и URL приоритетно берём из getProcedureInfo (актуальнее)
                if pi.get("procedure_number"):
                    proc_number = pi["procedure_number"]
                if pi.get("procedure_url"):
                    effective_url = pi["procedure_url"]
            else:
                # getProcedureInfo не ответил — состояние неизвестно, но по API
                # процедура может быть только черновиком (публикация в WSDL отсутствует)
                final_status = "draft"
                final_state  = None

            await _set_pub_success(
                pub_id,
                external_id=request_id,
                external_url=effective_url,
                status=final_status,
                platform_number=proc_number,
                platform_state=final_state,
            )
        elif err_m:
            await _set_pub_error(pub_id, f"Фабрикант: {err_m.group(1).strip()[:400]}")
        else:
            await _set_pub_error(pub_id, f"Фабрикант: не удалось разобрать ответ checkRequest: {resp_text[:300]}")

    except Exception as e:
        if attempts < MAX_ATTEMPTS:
            await asyncio.sleep(30)
            await _poll_fabrikant_result(
                pub_id, request_id, auth, attempts + 1,
                attach_documents=attach_documents,
                purchase_id_str=purchase_id_str,
                purchase_db_id=purchase_db_id,
            )
        else:
            await _set_pub_error(pub_id, f"Фабрикант: ошибка опроса результата: {str(e)[:200]}")



async def _get_platform_creds(db: AsyncSession, user_id: int, platform: str):
    """Возвращает (login, plain_password) из per-user кредов площадки, или None если нет записи."""
    from app.models.user_platform_credential import UserPlatformCredential
    from app.services.cred_crypto import decrypt_password
    row = (await db.execute(
        select(UserPlatformCredential).where(
            UserPlatformCredential.user_id == user_id,
            UserPlatformCredential.platform == platform,
        )
    )).scalar_one_or_none()
    if row is None:
        return None
    try:
        plain = decrypt_password(row.encrypted_password)
    except Exception:
        return None
    return row.login, plain


async def _call_fabrikant(pub_id: int, payload: dict, user_id: int | None = None, attach_documents: bool = False):
    # Определяем логин/пароль: per-user креды из БД (приоритет) или env
    login = FABRIKANT_LOGIN
    password = FABRIKANT_PASSWORD
    if user_id is not None:
        try:
            async with async_session() as _cred_db:
                result = await _get_platform_creds(_cred_db, user_id, "fabrikant")
            if result:
                login, password = result
        except Exception:
            pass  # fallback to env creds

    if not login or not password:
        await _set_pub_error(pub_id, "Не заданы FABRIKANT_LOGIN / FABRIKANT_PASSWORD в окружении")
        return

    nmck = float(payload.get("nmck") or 0)
    proc_type = payload.get("procedure_type") or "zp"

    items = [i for i in payload.get("items", []) if i.get("item_name")]
    # Мониторинг цен не требует позиций (lotItems отсутствует в схеме)
    if proc_type != "price_monitoring" and not items:
        await _set_pub_error(pub_id, "В закупке нет позиций. Добавьте хотя бы одну позицию перед публикацией.")
        return

    org_inn = (payload.get("org_inn") or "").strip()
    if not org_inn:
        await _set_pub_error(
            pub_id,
            "Не заполнен ИНН организации. Откройте раздел Организации → кнопка редактирования → укажите ИНН."
        )
        return

    # ОКПД2 на уровне позиций проверяем только для ЗП и Редукциона;
    # для Мониторинга цен ОКПД2 задаётся на уровне лота (проверяется в _build_soap_xml)
    if proc_type != "price_monitoring":
        purchase_okpd = (payload.get("okpd2_code") or "").strip()
        missing_okpd = [i.get("item_name", "?") for i in items if not (i.get("okpd2_code") or purchase_okpd)]
        if missing_okpd:
            await _set_pub_error(
                pub_id,
                f"Не заполнен код ОКПД2 у позиций: {', '.join(missing_okpd[:3])}. "
                "Укажите код ОКПД2 в диалоге публикации."
            )
            return

    auth = base64.b64encode(f"{login}:{password}".encode()).decode()
    soap_xml = _build_soap_xml(payload)
    soap_action = _FABRIKANT_SOAP_ACTION.get(proc_type, _FABRIKANT_SOAP_ACTION["zp"])

    try:
        req = urllib.request.Request(
            FABRIKANT_URL,
            data=soap_xml.encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "Authorization": f"Basic {auth}",
                "SOAPAction": soap_action,
                "User-Agent": "VSKS-CRM/1.0",
            },
        )
        loop = asyncio.get_event_loop()
        try:
            resp = await loop.run_in_executor(
                None, lambda: urllib.request.urlopen(req, timeout=30, context=_make_ssl_ctx())
            )
            resp_text = resp.read().decode("utf-8")
            status_code = resp.status
        except urllib.error.HTTPError as e:
            resp_text = e.read().decode("utf-8", errors="replace")
            status_code = e.code

        logger.info("Fabrikant SOAP response (pub=%d): %.500s", pub_id, resp_text)

        m = re.search(r"<[^:>\s]*:?requestId>([^<]+)<", resp_text)
        if m:
            req_id = m.group(1).strip()
            # Save requestId immediately, then poll checkRequest for real procedureUrl
            async with async_session() as db:
                res = await db.execute(select(PlatformPublication).where(PlatformPublication.id == pub_id))
                pub = res.scalar_one_or_none()
                if pub:
                    pub.external_id = req_id
                    pub.updated_at = datetime.now(timezone.utc)
                    await db.commit()
            purchase_id_str = str(payload.get("registry_number") or payload.get("purchase_id", ""))
            await _poll_fabrikant_result(
                pub_id, req_id, auth,
                attach_documents=attach_documents,
                purchase_id_str=purchase_id_str,
                purchase_db_id=int(payload.get("purchase_id", 0)),
            )
        else:
            fault = re.search(r"<[^:>\s]*:?faultstring[^>]*>([^<]+)<", resp_text)
            err = fault.group(1) if fault else f"HTTP {status_code}: {resp_text[:200]}"
            await _set_pub_error(pub_id, f"Фабрикант SOAP: {err}")
    except Exception as e:
        await _set_pub_error(pub_id, f"Ошибка соединения с Фабрикант: {str(e)[:200]}")

