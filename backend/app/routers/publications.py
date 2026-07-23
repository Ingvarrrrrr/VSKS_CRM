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
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, async_session
from app.models.platform_publication import PlatformPublication
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.contractor import Contractor
from app.models.subsidy import Subsidy
from app.models.organization import Organization
from app.schemas.schemas import PublishRequest, PublicationOut, PublicationStatusUpdate
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


# ── helpers ─────────────────────────────────────────────────────────────────

async def _set_pub_success(pub_id: int, external_id: str = None, external_url: str = None):
    async with async_session() as db:
        res = await db.execute(select(PlatformPublication).where(PlatformPublication.id == pub_id))
        pub = res.scalar_one_or_none()
        if pub:
            pub.status = "published"
            pub.external_id = external_id
            pub.external_url = external_url
            pub.published_at = datetime.now(timezone.utc)
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

    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
        "<soap:Body>"
        f'<uf:addFileToPurchaseNotice xmlns:uf="{NS_UF}">'
        "<uf:header>"
        f"<uf:guid>{esc(packet_guid)}</uf:guid>"
        f"<uf:createDateTime>{create_dt}</uf:createDateTime>"
        "</uf:header>"
        "<uf:body><uf:item><uf:addFileToPurchaseNoticeData>"
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
    if subsidy and subsidy.org_id:
        org = await db.get(Organization, subsidy.org_id)
        org_inn = org.inn if org else None

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
        "delivery_address":  p.delivery_address or None,
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

    if payload.get("determination_date"):
        determ = fdt(_parse_dt(payload["determination_date"]) or (end_dt + timedelta(days=1)))
    else:
        determ = fdt(end_dt + timedelta(days=1))

    if payload.get("summing_up_date"):
        summing = fdt(_parse_dt(payload["summing_up_date"]) or (end_dt + timedelta(days=2)))
    else:
        summing = fdt(end_dt + timedelta(days=2))

    NS_PNC = "http://api.fabrikant.ru/multi-integration/common/commercial_trade/purchaseNotice"
    NS_T   = "http://api.fabrikant.ru/multi-integration/common/commercial_trade/types"

    items_xml = ""
    for idx, item in enumerate(payload.get("items", []), 1):
        if not item.get("item_name"):
            continue
        qty = item.get("quantity", 1)
        up = float(item.get("unit_price", 0))
        tp = float(item.get("total_price", 0)) or (up * qty)
        unit_name = esc(item.get("unit", "шт") or "шт")
        # okpd2/okved2 codes from item or defaults (both required by Fabrikant schema)
        okpd2_code = esc(item.get("okpd2_code") or payload.get("okpd2_code") or "")
        okpd2_name = esc(item.get("okpd2_name") or item.get("item_name", "Товар")[:100])
        okved2_code = esc(item.get("okved2_code") or "G")
        okved2_name = esc(item.get("okved2_name") or "Торговля оптовая и розничная")
        # positionPrice (total) comes before positionPricePerUnit per schema
        if up > 0:
            price_xml = (
                f"<pnc:positionPrice><pnc:price>{tp}</pnc:price><pnc:ndsType>without_nds</pnc:ndsType></pnc:positionPrice>"
                f"<pnc:positionPricePerUnit><pnc:price>{up}</pnc:price><pnc:ndsType>without_nds</pnc:ndsType></pnc:positionPricePerUnit>"
            )
        else:
            # Без НМЦД — цена не указана
            price_xml = "<pnc:noNmcd>true</pnc:noNmcd>"
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

    lot_items = f"<pnc:lotItems>{items_xml}</pnc:lotItems>" if items_xml else ""
    initial_sum_xml = (
        f"<pnc:initialSumInfo><pnc:initialSum>{nmck}</pnc:initialSum><pnc:ndsType>without_nds</pnc:ndsType></pnc:initialSumInfo>"
        if float(nmck or 0) > 0
        else "<pnc:noNmcd>true</pnc:noNmcd>"
    )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
        "<soap:Body>"
        f'<pnc:purchaseNoticeZPCommercial xmlns:pnc="{NS_PNC}" xmlns:t="{NS_T}">'
        "<pnc:body><pnc:item><pnc:purchaseNoticeZPCommercialData>"
        f"<pnc:purchaseId>{purchase_id}</pnc:purchaseId>"
        "<pnc:purchaseCategoryCustom>Запрос предложений</pnc:purchaseCategoryCustom>"
        f"<pnc:name>{subject}</pnc:name>"
        f"<pnc:customer><t:inn>{esc(payload.get('org_inn') or '')}</t:inn></pnc:customer>"
        "<pnc:notDishonest>false</pnc:notDishonest>"
        "<pnc:lots><pnc:lot>"
        f"<pnc:lotId>{purchase_id}</pnc:lotId>"
        f"<pnc:subject>{subject}</pnc:subject>"
        "<pnc:currency><t:code>RUB</t:code></pnc:currency>"
        f"{initial_sum_xml}"
        f"<pnc:deliveryPlace><pnc:adress>{esc(payload.get('delivery_address') or 'Москва')}</pnc:adress></pnc:deliveryPlace>"
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
        "</soap:Body></soap:Envelope>"
    )


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
                "SOAPAction": '""',
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

        url_m = re.search(r"<[^:>\s]*:?procedureUrl[^>]*>([^<]+)<", resp_text)

        if url_m:
            proc_url = url_m.group(1).strip()
            await _set_pub_success(pub_id, external_id=request_id, external_url=proc_url)
            # Прикрепляем документы ПОСЛЕ успешной публикации
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
                    # Сбой прикрепления не должен ронять статус публикации
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

    items = [i for i in payload.get("items", []) if i.get("item_name")]
    if not items:
        await _set_pub_error(pub_id, "В закупке нет позиций. Добавьте хотя бы одну позицию перед публикацией.")
        return

    org_inn = (payload.get("org_inn") or "").strip()
    if not org_inn:
        await _set_pub_error(
            pub_id,
            "Не заполнен ИНН организации. Откройте раздел Организации → кнопка редактирования → укажите ИНН."
        )
        return

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

    try:
        req = urllib.request.Request(
            FABRIKANT_URL,
            data=soap_xml.encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "Authorization": f"Basic {auth}",
                "SOAPAction": '""',
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

    existing = await db.execute(
        select(PlatformPublication).where(
            PlatformPublication.purchase_id == purchase_id,
            PlatformPublication.platform == body.platform,
            PlatformPublication.status.in_(["pending", "publishing", "published"]),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"Закупка уже опубликована или публикуется на {PLATFORM_LABELS.get(body.platform)}")

    payload = await _build_publish_payload(purchase_id, db)

    if body.no_nmcd:
        payload["nmck"] = 0

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
