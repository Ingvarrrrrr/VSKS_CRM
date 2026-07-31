import asyncio
import base64
import json
import logging
import os
import re
import ssl
import urllib.request
import urllib.error
import uuid

logger = logging.getLogger(__name__)
import httpx
from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, async_session
from app.models.platform_publication import PlatformPublication
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.contractor import Contractor
from app.models.subsidy import Subsidy
from app.models.organization import Organization
from app.schemas.schemas import PublishRequest, PublicationOut, PublicationStatusUpdate
from app.services.ru_regions import get_region_info
from app.auth.jwt import get_current_user
from app.auth.permissions import require_action

router = APIRouter(prefix="/api/publications", tags=["publications"])

ROSELTORG_TOKEN = os.getenv("ROSELTORG_TOKEN", "")
ROSELTORG_URL = "https://business.roseltorg.ru/api/v1/lots"

FABRIKANT_LOGIN = os.getenv("FABRIKANT_LOGIN", "")
FABRIKANT_PASSWORD = os.getenv("FABRIKANT_PASSWORD", "")
FABRIKANT_URL = "https://api.fabrikant.ru/multi-integration/common/commercial_trade"


def _make_ssl_ctx() -> ssl.SSLContext:
    """SSL context compatible with Росэлторг / Фабрикант (TLS 1.2, specific cipher)."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        ctx.set_ciphers("ECDHE-RSA-AES256-GCM-SHA384:ECDHE-RSA-AES128-GCM-SHA256:DEFAULT@SECLEVEL=1")
    except ssl.SSLError:
        pass
    return ctx

PLATFORM_LABELS = {
    "fabrikant":    "Фабрикант",
    "roseltorg_rb": "Росэлторг.Бизнес",
}

SUPPORTED_PLATFORMS = set(PLATFORM_LABELS.keys())

# SOAPAction per operation (tns = binding namespace)
_FABRIKANT_SOAP_ACTION = {
    "zp":               "tns:purchaseNoticeZPCommercial",
    "reduction":        "tns:purchaseNoticeReductionCommercial",
    "price_monitoring": "tns:purchaseNoticePriceMonitoringCommercial",
}
_FABRIKANT_SOAP_ACTION_CHECK     = "tns:checkRequest"
_FABRIKANT_SOAP_ACTION_GET_INFO  = "tns:getProcedureInfo"

NS_PI = "http://api.fabrikant.ru/multi-integration/common/commercial_trade/procedureInfo"


# ── helpers ─────────────────────────────────────────────────────────────────

async def _set_pub_success(
    pub_id: int,
    external_id: str = None,
    external_url: str = None,
    status: str = "published",
    platform_number: str = None,
    platform_state: str = None,
):
    async with async_session() as db:
        res = await db.execute(select(PlatformPublication).where(PlatformPublication.id == pub_id))
        pub = res.scalar_one_or_none()
        if pub:
            pub.status = status
            pub.external_id = external_id
            pub.external_url = external_url
            pub.platform_number = platform_number
            pub.platform_state = platform_state
            if status == "published":
                pub.published_at = datetime.now(timezone.utc)
            pub.updated_at = datetime.now(timezone.utc)
            await db.commit()


async def _set_pub_platform_number(pub_id: int, number: str):
    """Проставляет platform_number ДО рендера/прикрепления документов, чтобы
    печатная форма извещения показывала номер площадки, а не наш internal
    requestId (external_id). _set_pub_success ниже по потоку перезапишет тем
    же либо уточнённым номером."""
    async with async_session() as db:
        res = await db.execute(select(PlatformPublication).where(PlatformPublication.id == pub_id))
        pub = res.scalar_one_or_none()
        if pub:
            pub.platform_number = number
            pub.updated_at = datetime.now(timezone.utc)
            await db.commit()


async def _set_pub_error(pub_id: int, error_text: str):
    async with async_session() as db:
        res = await db.execute(select(PlatformPublication).where(PlatformPublication.id == pub_id))
        pub = res.scalar_one_or_none()
        if pub:
            pub.status = "error"
            pub.error_text = error_text[:500]
            pub.updated_at = datetime.now(timezone.utc)
            await db.commit()


async def _set_pub_attachments_result(pub_id: int, results: list):
    """Сохраняет результат прикрепления документов в PlatformPublication.attachments_result."""
    async with async_session() as db:
        res = await db.execute(select(PlatformPublication).where(PlatformPublication.id == pub_id))
        pub = res.scalar_one_or_none()
        if pub:
            pub.attachments_result = json.dumps(results, ensure_ascii=False)
            pub.updated_at = datetime.now(timezone.utc)
            await db.commit()


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


# ── Фабрикант SOAP: addFileToPurchaseNotice ───────────────────────────────────

NS_UF = "http://api.fabrikant.ru/multi-integration/common/commercial_trade/uploadFile"
NS_T_TYPES = "http://api.fabrikant.ru/multi-integration/common/commercial_trade/types"
FABRIKANT_SOAP_ACTION_ADD_FILE = "tns:addFileToPurchaseNotice"


def _build_add_file_soap_xml(
    purchase_id_str: str,
    file_id: str,
    file_name: str,
    title: str,
    file_bytes_b64: str,
) -> str:
    """Строит SOAP Envelope для операции addFileToPurchaseNotice."""
    def esc(s: str) -> str:
        return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    packet_guid = str(uuid.uuid4())
    create_dt = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+03:00")

    item_guid = str(uuid.uuid4())

    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
        "<soap:Body>"
        f'<uf:addFileToPurchaseNotice xmlns:uf="{NS_UF}" xmlns:t="{NS_T_TYPES}">'
        "<t:header>"
        f"<t:guid>{esc(packet_guid)}</t:guid>"
        f"<t:createDateTime>{create_dt}</t:createDateTime>"
        "</t:header>"
        f"<uf:body><uf:item><t:guid>{esc(item_guid)}</t:guid><uf:addFileToPurchaseNoticeData>"
        f"<uf:purchaseId>{esc(purchase_id_str)}</uf:purchaseId>"
        f"<uf:fileId>{esc(file_id)}</uf:fileId>"
        f"<uf:fileName>{esc(file_name)}</uf:fileName>"
        f"<uf:title>{esc(title)}</uf:title>"
        f"<uf:fileBytes>{file_bytes_b64}</uf:fileBytes>"
        "</uf:addFileToPurchaseNoticeData></uf:item></uf:body>"
        "</uf:addFileToPurchaseNotice>"
        "</soap:Body></soap:Envelope>"
    )


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


async def _build_publish_payload(purchase_id: int, db: AsyncSession) -> dict:
    res = await db.execute(select(Purchase).where(Purchase.id == purchase_id))
    p = res.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Закупка не найдена")

    items_res = await db.execute(select(PurchaseItem).where(PurchaseItem.purchase_id == purchase_id))
    items = items_res.scalars().all()

    contractor = None
    if p.contractor_id:
        c_res = await db.execute(select(Contractor).where(Contractor.id == p.contractor_id))
        contractor = c_res.scalar_one_or_none()

    subsidy = None
    if p.subsidy_id:
        s_res = await db.execute(select(Subsidy).where(Subsidy.id == p.subsidy_id))
        subsidy = s_res.scalar_one_or_none()

    org_inn = None
    org_address = None
    org_region = None
    _sub_org = None
    if subsidy and subsidy.org_id:
        org_res = await db.execute(
            select(Organization)
            .where(Organization.id == subsidy.org_id)
            .options(selectinload(Organization.contractor))
        )
        _sub_org = org_res.scalar_one_or_none()
        if _sub_org:
            org_inn = _sub_org.inn or (_sub_org.contractor.inn if _sub_org.contractor else None)
            # Адрес по merge-паттерну: org.address, при пустом — адрес привязанного контрагента
            org_address = (_sub_org.address or "").strip() or (
                (_sub_org.contractor.address or "").strip() if _sub_org.contractor else ""
            ) or None
            org_region = (_sub_org.region or "").strip() or None

    # Субъект РФ доставки: сначала явное поле delivery_region, фолбэк — регион организации субсидии.
    # p.region — «Регион проведения мероприятия» (ДРУГОЕ поле, НЕ трогаем для места поставки).
    delivery_region_value = (p.delivery_region or "").strip() or (org_region or "")
    region_info = get_region_info(delivery_region_value) if delivery_region_value else None

    # Полный адрес доставки: собираем из структурных частей, фолбэк — свободные поля.
    def _build_delivery_address() -> str | None:
        parts = []
        if (p.delivery_postcode or "").strip():
            parts.append(p.delivery_postcode.strip())
        if delivery_region_value:
            parts.append(delivery_region_value)
        if (p.delivery_city or "").strip():
            parts.append(p.delivery_city.strip())
        if (p.delivery_street or "").strip():
            parts.append(p.delivery_street.strip())
        if (p.delivery_house or "").strip():
            parts.append("д. " + p.delivery_house.strip())
        if (p.delivery_building or "").strip():
            parts.append("к. " + p.delivery_building.strip())
        if parts:
            return ", ".join(parts)
        # Фолбэк: свободная строка → место доставки/услуг → адрес организации субсидии
        return (
            (p.delivery_address or "").strip()
            or (p.delivery_location or "").strip()
            or org_address
            or None
        )

    delivery_address = _build_delivery_address()

    return {
        "purchase_id":       p.id,
        "registry_number":   p.registry_number,
        "subject":           p.subject,
        "nmck":              float(p.total_nmck or p.nmck or p.planned_total_price or 0) or sum(
            float(i.total_price or 0) or (float(i.unit_price or 0) * float(i.quantity or 0))
            for i in items
        ),
        "purchase_method":   p.purchase_method,
        "contract_type":     p.purchase_contract_type,
        "execution_term":    str(p.execution_term) if p.execution_term else None,
        "delivery_address":  delivery_address or None,
        "region":            p.region or None,
        # deliveryPlaceType: state (фед. округ) / region (субъект) / regionOkato (11 цифр)
        "delivery_state":    region_info["district"] if region_info else None,
        "delivery_region":   delivery_region_value if region_info else None,
        "delivery_okato":    region_info["okato"] if region_info else None,
        "org_inn":           org_inn,
        "contractor": {
            "name": contractor.name if contractor else None,
            "inn":  contractor.inn  if contractor else None,
        } if contractor else None,
        "items": [
            {
                "item_name":   i.item_name,
                "quantity":    float(i.quantity or 0),
                "unit":        i.unit,
                "unit_price":  float(i.unit_price or 0),
                "total_price": float(i.total_price or 0),
            }
            for i in items
        ],
    }


# ── Росэлторг ────────────────────────────────────────────────────────────────

ROSELTORG_AUTH_URL = "https://lk.roseltorg.ru/api/app/api/auth-integration/v1/auth"
ROSELTORG_BASE_URL = "https://business.roseltorg.ru/integration/v1"

ROSELTORG_TEMPLATE_IDS = {
    "request_quotations": 8,
    "request_proposals":  9,
    "competition":        10,
    "auction":            11,
}


async def _get_roseltorg_jwt() -> str:
    """Обменивает интеграционный токен на JWT (двухшаговая авторизация по документации v2.0)."""
    body = json.dumps({
        "grant_type": "integration",
        "token": ROSELTORG_TOKEN,
        "platform": "b2b",
        "client": "b2b",
    }).encode("utf-8")
    req = urllib.request.Request(
        ROSELTORG_AUTH_URL,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "VSKS-CRM/1.0"},
    )
    loop = asyncio.get_event_loop()
    resp = await loop.run_in_executor(
        None, lambda: urllib.request.urlopen(req, timeout=30, context=_make_ssl_ctx())
    )
    data = json.loads(resp.read().decode("utf-8"))
    return data["access_token"]


async def _rb_call(jwt: str, url: str, body: dict = None, method: str = "POST"):
    """Выполняет запрос к Росэлторг.Бизнес API с JWT."""
    data = json.dumps(body).encode("utf-8") if body is not None else b"{}"
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization": f"Bearer {jwt}",
            "Content-Type": "application/json",
            "User-Agent": "VSKS-CRM/1.0",
        },
    )
    loop = asyncio.get_event_loop()
    try:
        resp = await loop.run_in_executor(
            None, lambda: urllib.request.urlopen(req, timeout=30, context=_make_ssl_ctx())
        )
        return json.loads(resp.read().decode("utf-8")), resp.status
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", errors="replace")
        return {"_error": text, "_code": e.code}, e.code


async def _call_roseltorg(pub_id: int, payload: dict):
    if not ROSELTORG_TOKEN:
        await _set_pub_error(pub_id, "Не задан ROSELTORG_TOKEN в окружении сервера")
        return

    # Шаг 1: получаем JWT
    try:
        jwt = await _get_roseltorg_jwt()
    except Exception as e:
        await _set_pub_error(pub_id, f"Ошибка авторизации Росэлторг: {str(e)[:200]}")
        return

    procedure_type = payload.get("procedure_type", "request_quotations")
    template_id = ROSELTORG_TEMPLATE_IDS.get(procedure_type, 8)
    subject = payload.get("subject") or f"Закупка {payload.get('registry_number', '')}"
    nmck = payload.get("nmck", 0)
    base = ROSELTORG_BASE_URL

    try:
        # Шаг 2: создаём черновик процедуры
        result, status = await _rb_call(jwt, f"{base}/notices/{template_id}/new")
        if status not in (200, 201) or not result.get("data", {}).get("noticeId"):
            await _set_pub_error(pub_id, f"Росэлторг создание процедуры {status}: {str(result)[:250]}")
            return
        notice_id = result["data"]["noticeId"]

        # Шаг 3: задаём название процедуры
        await _rb_call(jwt, f"{base}/notices/{notice_id}",
            body={"data": {"ProcedureMainInfo": {"name": subject}}}, method="PUT")

        # Шаг 4: создаём лот
        lot_body = {"name": subject, "initialSum": str(nmck), "currency": "RUB"}
        lot_result, lot_status = await _rb_call(jwt, f"{base}/notices/{notice_id}/notice-lot", lot_body)
        if lot_status not in (200, 201):
            await _set_pub_error(pub_id, f"Росэлторг создание лота {lot_status}: {str(lot_result)[:250]}")
            return
        notice_lot_id = (lot_result.get("data") or {}).get("noticeLotId") or (lot_result.get("data") or {}).get("id")

        # Шаг 5: добавляем позиции лота
        if notice_lot_id:
            for idx, item in enumerate(payload.get("items", []), 1):
                if not item.get("item_name"):
                    continue
                item_body = {"data": {
                    "name": item["item_name"],
                    "quantity": str(item.get("quantity", 1)),
                    "unit": item.get("unit", "Штука"),
                    "okeiId": "796",
                    "ordinalNumber": idx,
                }}
                if item.get("unit_price"):
                    item_body["data"]["commodityItemPrice"] = str(item["unit_price"])
                await _rb_call(jwt, f"{base}/notice/lot/{notice_lot_id}/items", item_body)

        # Шаг 6: публикуем
        pub_result, pub_status = await _rb_call(jwt, f"{base}/notices/{notice_id}/publish")
        if pub_status in (200, 201):
            procedure_id = (pub_result.get("data") or {}).get("procedureId") or notice_id
            await _set_pub_success(
                pub_id,
                external_id=str(procedure_id),
                external_url=f"https://business.roseltorg.ru/procedures/{procedure_id}",
            )
        else:
            await _set_pub_error(pub_id, f"Росэлторг публикация {pub_status}: {str(pub_result)[:300]}")
    except Exception as e:
        await _set_pub_error(pub_id, f"Ошибка Росэлторг: {str(e)[:200]}")


# ── Фабрикант SOAP ───────────────────────────────────────────────────────────

def _build_soap_xml(payload: dict) -> str:
    """Собирает SOAP-конверт для Фабрикант.

    Тип процедуры задаётся payload["procedure_type"]:
      "zp"              — Запрос предложений (purchaseNoticeZPCommercial)   [default]
      "reduction"       — Редукцион (purchaseNoticeReductionCommercial)
      "price_monitoring"— Мониторинг цен (purchaseNoticePriceMonitoringCommercial)

    Элементы строятся строго по sequence из WSDL. Никаких вымышленных элементов.
    """
    procedure_type = payload.get("procedure_type") or "zp"
    if procedure_type not in ("zp", "reduction", "price_monitoring"):
        raise HTTPException(422, f"Неверный тип процедуры Фабрикант: {procedure_type!r}. Допустимо: zp, reduction, price_monitoring")

    def esc(s):
        return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    purchase_id = esc(payload.get("registry_number") or str(payload.get("purchase_id", "")))
    subject = esc(payload.get("subject") or f"Закупка {purchase_id}")
    nmck = payload.get("nmck", 0)

    now = datetime.now()

    def fdt(d):
        return d.strftime("%Y-%m-%dT%H:%M:%S+03:00")

    def _parse_dt(s):
        try:
            return datetime.fromisoformat(str(s))
        except Exception:
            return None

    if payload.get("proposal_start"):
        start = fdt(_parse_dt(payload["proposal_start"]) or (now + timedelta(hours=1)))
    else:
        start = fdt(now + timedelta(hours=1))

    if payload.get("proposal_end"):
        end_dt = _parse_dt(payload["proposal_end"]) or (now + timedelta(days=7))
    else:
        end_dt = now + timedelta(days=7)
        if payload.get("execution_term"):
            try:
                end_dt = datetime.fromisoformat(str(payload["execution_term"]))
            except Exception:
                pass
    end = fdt(end_dt)

    if payload.get("summing_up_date"):
        summing = fdt(_parse_dt(payload["summing_up_date"]) or (end_dt + timedelta(days=2)))
    else:
        summing = fdt(end_dt + timedelta(days=2))

    NS_PNC = "http://api.fabrikant.ru/multi-integration/common/commercial_trade/purchaseNotice"
    NS_T   = "http://api.fabrikant.ru/multi-integration/common/commercial_trade/types"

    # ── Билдер deliveryPlace (deliveryPlaceType, WSDL): state? → region? → regionOkato? → adress ──
    def _delivery_place_xml(default_addr: str = "") -> str:
        """Порядок элементов строго по sequence WSDL. Каждый опциональный элемент —
        только при наличии значения; adress обязателен (без адреса блок не строим)."""
        addr = payload.get("delivery_address") or default_addr
        if not addr:
            return ""
        xml = "<pnc:deliveryPlace>"
        if payload.get("delivery_state"):
            xml += f"<pnc:state>{esc(payload['delivery_state'])}</pnc:state>"
        if payload.get("delivery_region"):
            xml += f"<pnc:region>{esc(payload['delivery_region'])}</pnc:region>"
        if payload.get("delivery_okato"):
            xml += f"<pnc:regionOkato>{esc(payload['delivery_okato'])}</pnc:regionOkato>"
        xml += f"<pnc:adress>{esc(addr)}</pnc:adress></pnc:deliveryPlace>"
        return xml

    # ── Вспомогательный билдер: initialSumInfo с необязательным pricingMethod перед ним ──
    def _initial_sum_xml(nmck_val: float) -> str:
        """XSD-схема Фабриканта (WSDL проверен 2026-07-28):
        - initialSumInfo — minOccurs=0, элемент необязателен.
        - Если явно запрошено «без НМЦД» (payload["no_nmcd"]) — не слать элемент вовсе.
        - Иначе: есть НМЦД → шлём его; нет НМЦД → откат на сумму позиций;
          нет ни того ни другого → не слать элемент (возвращаем "").
        - pricingMethod=withoutNDSType добавляется перед initialSumInfo
          когда НМЦД отсутствует, но есть сумма позиций.
        """
        if payload.get("no_nmcd"):
            # Пользователь явно потребовал публикацию без НМЦД — элемент не слать
            return ""
        nmck_f = float(nmck_val or 0)
        if nmck_f >= 0.01:
            return (
                f"<pnc:initialSumInfo><pnc:initialSum>{nmck_f:.2f}</pnc:initialSum>"
                f"<pnc:ndsType>without_nds</pnc:ndsType></pnc:initialSumInfo>"
            )
        items_total = sum(
            float(i.get("total_price", 0)) or (float(i.get("unit_price", 0)) * float(i.get("quantity", 1)))
            for i in payload.get("items", [])
            if i.get("item_name")
        )
        items_total = round(items_total, 2)
        if items_total >= 0.01:
            return (
                "<pnc:pricingMethod>withoutNDSType</pnc:pricingMethod>"
                f"<pnc:initialSumInfo><pnc:initialSum>{items_total:.2f}</pnc:initialSum>"
                f"<pnc:ndsType>without_nds</pnc:ndsType></pnc:initialSumInfo>"
            )
        # Neither НМЦД nor item prices — omit the element entirely (minOccurs=0)
        return ""

    # ── Вывод ОКВЭД2 из кода ОКПД2 ──
    def _okved2_from_okpd2(okpd2_code_raw: str) -> str:
        """Возвращает код ОКВЭД2, взяв первые два сегмента ОКПД2. Пример: 29.20.23 → 29.20."""
        parts = okpd2_code_raw.split(".")
        if len(parts) >= 2:
            derived = parts[0] + "." + parts[1]
        else:
            derived = okpd2_code_raw
        return derived

    # ── Билдер lotItems для ЗП (lotItemType) ──
    def _build_lot_items_zp() -> str:
        items_xml = ""
        for idx, item in enumerate(payload.get("items", []), 1):
            if not item.get("item_name"):
                continue
            qty = item.get("quantity", 1)
            up = float(item.get("unit_price", 0))
            tp = float(item.get("total_price", 0)) or (up * qty)
            unit_name = esc(item.get("unit", "шт") or "шт")
            okpd2_code_raw = item.get("okpd2_code") or payload.get("okpd2_code") or ""
            okpd2_code = esc(okpd2_code_raw)
            okpd2_name = esc(item.get("okpd2_name") or item.get("item_name", "Товар")[:100])
            _derived_okved2 = _okved2_from_okpd2(okpd2_code_raw) if okpd2_code_raw else "G"
            okved2_code = esc(item.get("okved2_code") or _derived_okved2)
            okved2_name = esc(item.get("okved2_name") or item.get("okpd2_name") or item.get("item_name", "Товар")[:100])
            # positionPrice(total) before positionPricePerUnit per lotItemType sequence
            # При no_nmcd цены позиций не передаём (minOccurs=0 в lotItemType)
            if up > 0 and not payload.get("no_nmcd"):
                price_xml = (
                    f"<pnc:positionPrice><pnc:price>{tp}</pnc:price><pnc:ndsType>without_nds</pnc:ndsType></pnc:positionPrice>"
                    f"<pnc:positionPricePerUnit><pnc:price>{up}</pnc:price><pnc:ndsType>without_nds</pnc:ndsType></pnc:positionPricePerUnit>"
                )
            else:
                price_xml = ""
            items_xml += (
                f"<pnc:lotItem>"
                f"<pnc:ordinalNumber>{idx}</pnc:ordinalNumber>"
                f"<pnc:positionName>{esc(item['item_name'])}</pnc:positionName>"
                f"<pnc:okpd2><t:code>{okpd2_code}</t:code><t:name>{okpd2_name}</t:name></pnc:okpd2>"
                f"<pnc:okved2><t:code>{okved2_code}</t:code><t:name>{okved2_name}</t:name></pnc:okved2>"
                f"<pnc:okei><t:code>796</t:code><t:name>{unit_name}</t:name></pnc:okei>"
                f"<pnc:qty>{qty}</pnc:qty>"
                f"{price_xml}"
                f"</pnc:lotItem>"
            )
        return f"<pnc:lotItems>{items_xml}</pnc:lotItems>" if items_xml else ""

    # ── Билдер lotItems для Редукциона (lotItemReductionType) ──
    def _build_lot_items_reduction() -> str:
        items_xml = ""
        for idx, item in enumerate(payload.get("items", []), 1):
            if not item.get("item_name"):
                continue
            qty = item.get("quantity", 1)
            unit_name = esc(item.get("unit", "шт") or "шт")
            okpd2_code_raw = item.get("okpd2_code") or payload.get("okpd2_code") or ""
            okpd2_code = esc(okpd2_code_raw)
            okpd2_name = esc(item.get("okpd2_name") or item.get("item_name", "Товар")[:100])
            _derived_okved2 = _okved2_from_okpd2(okpd2_code_raw) if okpd2_code_raw else "G"
            okved2_code = esc(item.get("okved2_code") or _derived_okved2)
            okved2_name = esc(item.get("okved2_name") or item.get("okpd2_name") or item.get("item_name", "Товар")[:100])
            # lotItemReductionType sequence: ordinalNumber? okpd2? okved2? okei? qty? additionalInfo?
            items_xml += (
                f"<pnc:lotItem>"
                f"<pnc:ordinalNumber>{idx}</pnc:ordinalNumber>"
                f"<pnc:okpd2><t:code>{okpd2_code}</t:code><t:name>{okpd2_name}</t:name></pnc:okpd2>"
                f"<pnc:okved2><t:code>{okved2_code}</t:code><t:name>{okved2_name}</t:name></pnc:okved2>"
                f"<pnc:okei><t:code>796</t:code><t:name>{unit_name}</t:name></pnc:okei>"
                f"<pnc:qty>{qty}</pnc:qty>"
                f"</pnc:lotItem>"
            )
        return f"<pnc:lotItems>{items_xml}</pnc:lotItems>" if items_xml else ""

    soap_header = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
        "<soap:Body>"
    )
    soap_footer = "</soap:Body></soap:Envelope>"

    # ═══════════════════════════════════════════════════════════════════════════
    # ЗП — Запрос предложений (purchaseNoticeZPCommercial)
    # BaseDataType: purchaseId → purchaseCategoryCustom → name → placer? → customer? → notDishonest?
    # lotType sequence: lotId → subject → currency → pricingMethod? → initialSumInfo → deliveryPlace? →
    #   [applicationSupplyNeeded+applicationSupplySumm]? → applicationSupplyExtra? → lotItems →
    #   proposalStartDateTime → proposalEndDateTime → proposalDeterminationDateTime →
    #   summingUpDateTime → lotFramework → lotAllowParticipantsExceedPricesByPositions? → criteria?
    # ═══════════════════════════════════════════════════════════════════════════
    if procedure_type == "zp":
        if payload.get("determination_date"):
            determ = fdt(_parse_dt(payload["determination_date"]) or (end_dt + timedelta(days=1)))
        else:
            determ = fdt(end_dt + timedelta(days=1))

        lot_items = _build_lot_items_zp()
        initial_sum_xml = _initial_sum_xml(nmck)
        delivery_place = _delivery_place_xml(default_addr="Москва")

        body = (
            f'<pnc:purchaseNoticeZPCommercial xmlns:pnc="{NS_PNC}" xmlns:t="{NS_T}">'
            "<pnc:body><pnc:item><pnc:purchaseNoticeZPCommercialData>"
            f"<pnc:purchaseId>{purchase_id}</pnc:purchaseId>"
            "<pnc:purchaseCategoryCustom>Запрос предложений</pnc:purchaseCategoryCustom>"
            f"<pnc:name>{subject}</pnc:name>"
            f"<pnc:placer><t:inn>{esc(payload.get('org_inn') or '')}</t:inn></pnc:placer>"
            f"<pnc:customer><t:inn>{esc(payload.get('org_inn') or '')}</t:inn></pnc:customer>"
            "<pnc:notDishonest>false</pnc:notDishonest>"
            "<pnc:lots><pnc:lot>"
            f"<pnc:lotId>{purchase_id}</pnc:lotId>"
            f"<pnc:subject>{subject}</pnc:subject>"
            "<pnc:currency><t:code>RUB</t:code></pnc:currency>"
            f"{initial_sum_xml}"
            f"{delivery_place}"
            "<pnc:applicationSupplyNeeded>false</pnc:applicationSupplyNeeded>"
            f"{lot_items}"
            f"<pnc:proposalStartDateTime>{start}</pnc:proposalStartDateTime>"
            f"<pnc:proposalEndDateTime>{end}</pnc:proposalEndDateTime>"
            f"<pnc:proposalDeterminationDateTime>{determ}</pnc:proposalDeterminationDateTime>"
            f"<pnc:summingUpDateTime>{summing}</pnc:summingUpDateTime>"
            "<pnc:lotFramework>false</pnc:lotFramework>"
            "</pnc:lot></pnc:lots>"
            "</pnc:purchaseNoticeZPCommercialData></pnc:item></pnc:body>"
            "</pnc:purchaseNoticeZPCommercial>"
        )
        return soap_header + body + soap_footer

    # ═══════════════════════════════════════════════════════════════════════════
    # Редукцион (purchaseNoticeReductionCommercial)
    # BaseDataType: purchaseId → name → placer? → customer? → notDishonest?
    #   (БЕЗ purchaseCategoryCustom!)
    # lotReductionType sequence: lotId → subject → currency → pricingMethod? → initialSumInfo →
    #   deliveryPlace(ОБЯЗАТЕЛЕН!) → [applicationSupplyNeeded+...]? → applicationSupplyExtra? →
    #   lotItems → proposalStartDateTime → proposalEndDateTime → auctionDateStart →
    #   summingUpDateTime → auctionNewBetLimitFrom → auctionNewBetLimitTo →
    #   contractExecutionTerms? → deliveryTerm? → lotPaymentConditions? →
    #   refusalToPurchase? → preferenceInformation? → comment? → lotFramework
    # ═══════════════════════════════════════════════════════════════════════════
    if procedure_type == "reduction":
        missing = []
        if not payload.get("delivery_address"):
            missing.append("место поставки")
        if not payload.get("auction_date_start"):
            missing.append("дата начала редукциона")
        if payload.get("auction_bet_limit_from") is None:
            missing.append("граница ставки от")
        if payload.get("auction_bet_limit_to") is None:
            missing.append("граница ставки до")
        if missing:
            raise HTTPException(422, f"Для редукциона обязательны: {', '.join(missing)}")

        auction_start = fdt(_parse_dt(payload["auction_date_start"]) or (end_dt + timedelta(days=1)))
        bet_from = float(payload["auction_bet_limit_from"])
        bet_to = float(payload["auction_bet_limit_to"])
        delivery_place = _delivery_place_xml()  # delivery_address гарантирован проверкой выше
        lot_items = _build_lot_items_reduction()
        initial_sum_xml = _initial_sum_xml(nmck)

        body = (
            f'<pnc:purchaseNoticeReductionCommercial xmlns:pnc="{NS_PNC}" xmlns:t="{NS_T}">'
            "<pnc:body><pnc:item><pnc:purchaseNoticeReductionCommercialData>"
            f"<pnc:purchaseId>{purchase_id}</pnc:purchaseId>"
            f"<pnc:name>{subject}</pnc:name>"
            f"<pnc:placer><t:inn>{esc(payload.get('org_inn') or '')}</t:inn></pnc:placer>"
            f"<pnc:customer><t:inn>{esc(payload.get('org_inn') or '')}</t:inn></pnc:customer>"
            "<pnc:notDishonest>false</pnc:notDishonest>"
            "<pnc:lots><pnc:lot>"
            f"<pnc:lotId>{purchase_id}</pnc:lotId>"
            f"<pnc:subject>{subject}</pnc:subject>"
            "<pnc:currency><t:code>RUB</t:code></pnc:currency>"
            f"{initial_sum_xml}"
            f"{delivery_place}"
            "<pnc:applicationSupplyNeeded>false</pnc:applicationSupplyNeeded>"
            f"{lot_items}"
            f"<pnc:proposalStartDateTime>{start}</pnc:proposalStartDateTime>"
            f"<pnc:proposalEndDateTime>{end}</pnc:proposalEndDateTime>"
            f"<pnc:auctionDateStart>{auction_start}</pnc:auctionDateStart>"
            f"<pnc:summingUpDateTime>{summing}</pnc:summingUpDateTime>"
            f"<pnc:auctionNewBetLimitFrom>{bet_from:.2f}</pnc:auctionNewBetLimitFrom>"
            f"<pnc:auctionNewBetLimitTo>{bet_to:.2f}</pnc:auctionNewBetLimitTo>"
            "<pnc:lotFramework>false</pnc:lotFramework>"
            "</pnc:lot></pnc:lots>"
            "</pnc:purchaseNoticeReductionCommercialData></pnc:item></pnc:body>"
            "</pnc:purchaseNoticeReductionCommercial>"
        )
        return soap_header + body + soap_footer

    # ═══════════════════════════════════════════════════════════════════════════
    # Мониторинг цен (purchaseNoticePriceMonitoringCommercial)
    # BaseDataType: purchaseId → name → placer? → customer?
    #   (без notDishonest, без purchaseCategoryCustom)
    # PriceMonitoringLotType sequence: lotId → subject → currency →
    #   [okei+qty]?(0..1) → okpd2(1..N, ОБЯЗАТЕЛЕН) → deliveryPlace? →
    #   proposalStartDateTime → proposalEndDateTime
    #   (НЕТ initialSumInfo, НЕТ lotItems, НЕТ цен)
    # ═══════════════════════════════════════════════════════════════════════════
    # procedure_type == "price_monitoring"
    okpd2_code = (payload.get("okpd2_code") or "").strip()
    if not okpd2_code:
        raise HTTPException(422, "Для мониторинга цен обязателен ОКПД2")

    # okei+qty — опционально, берём из первой позиции если есть
    okei_qty_xml = ""
    first_item = next((i for i in payload.get("items", []) if i.get("item_name")), None)
    if first_item:
        qty = first_item.get("quantity", 1)
        unit_name = esc(first_item.get("unit", "шт") or "шт")
        okei_qty_xml = (
            f"<pnc:okei><t:code>796</t:code><t:name>{unit_name}</t:name></pnc:okei>"
            f"<pnc:qty>{qty}</pnc:qty>"
        )

    okpd2_name = esc(payload.get("okpd2_name") or okpd2_code)

    body = (
        f'<pnc:purchaseNoticePriceMonitoringCommercial xmlns:pnc="{NS_PNC}" xmlns:t="{NS_T}">'
        "<pnc:body><pnc:item><pnc:purchaseNoticePriceMonitoringCommercialData>"
        f"<pnc:purchaseId>{purchase_id}</pnc:purchaseId>"
        f"<pnc:name>{subject}</pnc:name>"
        f"<pnc:placer><t:inn>{esc(payload.get('org_inn') or '')}</t:inn></pnc:placer>"
        f"<pnc:customer><t:inn>{esc(payload.get('org_inn') or '')}</t:inn></pnc:customer>"
        "<pnc:lots><pnc:lot>"
        f"<pnc:lotId>{purchase_id}</pnc:lotId>"
        f"<pnc:subject>{subject}</pnc:subject>"
        "<pnc:currency><t:code>RUB</t:code></pnc:currency>"
        f"{okei_qty_xml}"
        f"<pnc:okpd2><t:code>{esc(okpd2_code)}</t:code><t:name>{okpd2_name}</t:name></pnc:okpd2>"
        # deliveryPlace опционален (minOccurs=0) — добавляем только при наличии адреса
        f"{_delivery_place_xml()}"
        f"<pnc:proposalStartDateTime>{start}</pnc:proposalStartDateTime>"
        f"<pnc:proposalEndDateTime>{end}</pnc:proposalEndDateTime>"
        "</pnc:lot></pnc:lots>"
        "</pnc:purchaseNoticePriceMonitoringCommercialData></pnc:item></pnc:body>"
        "</pnc:purchaseNoticePriceMonitoringCommercial>"
    )
    return soap_header + body + soap_footer


FABRIKANT_CHECK_URL = "https://api.fabrikant.ru/multi-integration/common/commercial_trade/checkRequest"
NS_CR = "http://api.fabrikant.ru/multi-integration/common/commercial_trade/checkRequest"


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

    payload = await _build_publish_payload(purchase_id, db)

    if body.no_nmcd:
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
        background_tasks.add_task(_call_roseltorg, pub.id, payload)

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

    if pub.platform != "fabrikant":
        raise HTTPException(400, f"Обновление статуса поддерживается только для Фабриканта, а не для {pub.platform}")

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


@router.patch("/{pub_id}/status", response_model=PublicationOut)
async def update_publication_status(
    pub_id: int,
    body: PublicationStatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Обновляет статус публикации (используется для ручного сброса и обратной совместимости)."""
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
