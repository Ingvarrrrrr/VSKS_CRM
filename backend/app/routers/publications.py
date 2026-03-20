import asyncio
import base64
import json
import os
import re
import ssl
import urllib.request
import urllib.error
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
from app.schemas.schemas import PublishRequest, PublicationOut, PublicationStatusUpdate
from app.auth.jwt import get_current_user

router = APIRouter(prefix="/api/publications", tags=["publications"])

ROSELTORG_TOKEN = os.getenv("ROSELTORG_TOKEN", "")
ROSELTORG_URL = "https://business.roseltorg.ru/api/v1/lots"

FABRIKANT_LOGIN = os.getenv("FABRIKANT_LOGIN", "")
FABRIKANT_PASSWORD = os.getenv("FABRIKANT_PASSWORD", "")
FABRIKANT_URL = "https://api.fabrikant.ru/multiintegration/common/commercial_trade"


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

    return {
        "purchase_id":     p.id,
        "registry_number": p.registry_number,
        "subject":         p.subject,
        "nmck":            float(p.total_nmck or p.planned_total_price or 0),
        "purchase_method": p.purchase_method,
        "contract_type":   p.purchase_contract_type,
        "execution_term":  str(p.execution_term) if p.execution_term else None,
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

ROSELTORG_TEMPLATE_IDS = {
    "request_quotations": "1",
    "request_proposals":  "2",
    "competition":        "3",
    "auction":            "4",
}


async def _get_roseltorg_jwt() -> str:
    """Обменивает интеграционный токен на JWT для API вызовов (двухшаговая авторизация)."""
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


async def _call_roseltorg(pub_id: int, payload: dict):
    if not ROSELTORG_TOKEN:
        await _set_pub_error(pub_id, "Не задан ROSELTORG_TOKEN в окружении сервера")
        return

    # Шаг 1: получаем JWT
    try:
        jwt_token = await _get_roseltorg_jwt()
    except Exception as e:
        await _set_pub_error(pub_id, f"Ошибка авторизации Росэлторг: {str(e)[:200]}")
        return

    procedure_type = payload.get("procedure_type", "request_quotations")
    template_id = ROSELTORG_TEMPLATE_IDS.get(procedure_type, "1")

    body = {
        "templateId": template_id,
        "lotName": payload.get("subject") or f"Закупка {payload.get('registry_number', '')}",
        "currency": "RUB",
        "initialSum": payload.get("nmck", 0),
        "positions": [
            {
                "name":     i["item_name"],
                "quantity": i["quantity"],
                "unit":     i.get("unit", "шт"),
                "price":    i.get("unit_price", 0),
            }
            for i in payload.get("items", []) if i.get("item_name")
        ],
    }

    # Шаг 2: вызов API с JWT
    try:
        req_data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            ROSELTORG_URL,
            data=req_data,
            method="POST",
            headers={
                "authorization": jwt_token,
                "Content-Type": "application/json",
                "User-Agent": "VSKS-CRM/1.0",
            },
        )
        loop = asyncio.get_event_loop()
        try:
            resp = await loop.run_in_executor(
                None, lambda: urllib.request.urlopen(req, timeout=30, context=_make_ssl_ctx())
            )
            resp_body = resp.read().decode("utf-8")
            status_code = resp.status
        except urllib.error.HTTPError as e:
            resp_body = e.read().decode("utf-8", errors="replace")
            status_code = e.code

        if status_code in (200, 201):
            data = json.loads(resp_body)
            lot_id = data.get("id") or data.get("lotId") or data.get("noticeId") or data.get("lot_id")
            await _set_pub_success(
                pub_id,
                external_id=str(lot_id) if lot_id else None,
                external_url=f"https://business.roseltorg.ru/lot/{lot_id}" if lot_id else None,
            )
        else:
            await _set_pub_error(pub_id, f"Росэлторг API {status_code}: {resp_body[:300]}")
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

    start = fdt(now + timedelta(hours=1))
    end_dt = now + timedelta(days=7)
    if payload.get("execution_term"):
        try:
            end_dt = datetime.fromisoformat(str(payload["execution_term"]))
        except Exception:
            pass
    end = fdt(end_dt)
    determ = fdt(end_dt + timedelta(days=1))
    summing = fdt(end_dt + timedelta(days=2))

    items_xml = ""
    for idx, item in enumerate(payload.get("items", []), 1):
        if not item.get("item_name"):
            continue
        qty = item.get("quantity", 1)
        up = float(item.get("unit_price", 0))
        tp = float(item.get("total_price", 0)) or (up * qty)
        price_xml = (
            f"<positionPricePerUnit><price>{up}</price><ndsType>not_payer_nds</ndsType></positionPricePerUnit>"
            f"<positionPrice><price>{tp}</price><ndsType>not_payer_nds</ndsType></positionPrice>"
        ) if up > 0 else ""
        unit = esc(item.get("unit", "шт"))
        items_xml += (
            f"<lotItem><ordinalNumber>{idx}</ordinalNumber>"
            f"<positionName>{esc(item['item_name'])}</positionName>"
            f"<okei><code>796</code><name>{unit}</name></okei>"
            f"<qty>{qty}</qty>{price_xml}</lotItem>"
        )

    lot_items = f"<lotItems>{items_xml}</lotItems>" if items_xml else ""

    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
        "<soap:Body>"
        '<purchaseNoticeZPCommercial xmlns="http://commercial_trade.multiintegration.common.api.fabrikant.ru/">'
        "<body><item><purchaseNoticeZPCommercialData>"
        f"<purchaseId>{purchase_id}</purchaseId>"
        "<purchaseCategoryCustom>Запрос предложений</purchaseCategoryCustom>"
        f"<name>{subject}</name>"
        "<notDishonest>false</notDishonest>"
        "<lots><lot>"
        f"<lotId>{purchase_id}</lotId>"
        f"<subject>{subject}</subject>"
        "<currency><code>RUB</code></currency>"
        f"<initialSumInfo><initialSum>{nmck}</initialSum><ndsType>not_payer_nds</ndsType></initialSumInfo>"
        "<deliveryPlace><state>Москва</state><address>Москва</address></deliveryPlace>"
        "<applicationSupplyNeeded>false</applicationSupplyNeeded>"
        f"{lot_items}"
        f"<proposalStartDateTime>{start}</proposalStartDateTime>"
        f"<proposalEndDateTime>{end}</proposalEndDateTime>"
        f"<proposalDeterminationDateTime>{determ}</proposalDeterminationDateTime>"
        f"<summingUpDateTime>{summing}</summingUpDateTime>"
        "<lotFramework>false</lotFramework>"
        "</lot></lots>"
        "</purchaseNoticeZPCommercialData></item></body>"
        "</purchaseNoticeZPCommercial>"
        "</soap:Body></soap:Envelope>"
    )


async def _call_fabrikant(pub_id: int, payload: dict):
    if not FABRIKANT_LOGIN or not FABRIKANT_PASSWORD:
        await _set_pub_error(pub_id, "Не заданы FABRIKANT_LOGIN / FABRIKANT_PASSWORD в окружении")
        return

    auth = base64.b64encode(f"{FABRIKANT_LOGIN}:{FABRIKANT_PASSWORD}".encode()).decode()
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

        m = re.search(r"<requestId>([^<]+)</requestId>", resp_text)
        if m:
            req_id = m.group(1)
            await _set_pub_success(
                pub_id,
                external_id=req_id,
                external_url=f"https://www.fabrikant.ru/trades/commercial/?id={req_id}",
            )
        else:
            fault = re.search(r"<faultstring[^>]*>([^<]+)</faultstring>", resp_text)
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
    _=Depends(get_current_user),
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

    if body.procedure_type:
        payload["procedure_type"] = body.procedure_type

    pub = PlatformPublication(
        purchase_id=purchase_id,
        platform=body.platform,
        status="publishing",
    )
    db.add(pub)
    await db.commit()
    await db.refresh(pub)

    if body.platform == "fabrikant":
        background_tasks.add_task(_call_fabrikant, pub.id, payload)
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
