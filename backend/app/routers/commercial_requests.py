import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.jwt import get_current_user, require_role, MANAGER_ROLES, ALL_ROLES, get_org_filter
from app.auth.permissions import require_tab
from app.auth.visibility import get_visible_subsidy_ids
from app.database import get_db
from app.models.commercial_request import (
    CommercialRequest, CommercialRequestRecipient, CommercialRequestOffer,
)
from app.models.contractor import Contractor
from app.models.product import Product
from app.models.purchase import Purchase
from app.schemas.schemas import (
    CommercialRequestCreate,
    CommercialRequestUpdate,
    CommercialRequestOut,
    CommercialRequestRecipientOut,
    CommercialRequestStatusUpdate,
    CommercialRequestRecipientStatusUpdate,
    FreeRecipient,
    CommercialRequestOfferIn,
    CommercialRequestOfferOut,
)
from app.services.price_actualization import actualize_product_price
from datetime import date as _date

router = APIRouter(prefix="/api/commercial-requests", tags=["commercial_requests"])


@router.post("/", response_model=CommercialRequestOut)
async def create_commercial_request(
    data: CommercialRequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab('commercial_requests')),
):
    purchase = (await db.execute(select(Purchase).where(Purchase.id == data.purchase_id))).scalar_one_or_none()
    if not purchase:
        raise HTTPException(404, "Закупка не найдена")

    contractors = []
    if data.recipient_ids:
        contractors = (
            await db.execute(select(Contractor).where(Contractor.id.in_(data.recipient_ids)))
        ).scalars().all()

    req = CommercialRequest(
        purchase_id=data.purchase_id,
        subject=data.subject,
        intro_text=data.intro_text,
        delivery_date=data.delivery_date,
        status="prepared",
        created_by=getattr(current_user, "id", None),
    )
    db.add(req)
    await db.flush()

    for c in contractors:
        db.add(CommercialRequestRecipient(
            request_id=req.id,
            contractor_id=c.id,
            contractor_name=c.name,
            email=c.email,
            status="prepared",
        ))

    for fr in (data.free_recipients or []):
        db.add(CommercialRequestRecipient(
            request_id=req.id,
            contractor_id=None,
            contractor_name=fr.name or fr.email,
            email=fr.email,
            status="prepared",
        ))

    await db.commit()

    created = (await db.execute(
        select(CommercialRequest)
        .options(selectinload(CommercialRequest.recipients))
        .where(CommercialRequest.id == req.id)
    )).scalar_one()
    return _to_out(created)


@router.get("/", response_model=List[CommercialRequestOut])
async def list_commercial_requests(
    purchase_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    q = (select(CommercialRequest)
         .options(selectinload(CommercialRequest.recipients))
         .order_by(CommercialRequest.id.desc()))
    if purchase_id is not None:
        q = q.where(CommercialRequest.purchase_id == purchase_id)
    # Двухуровневая видимость по вкладке «Запросы КП».
    vis = await get_visible_subsidy_ids(current_user, db, "commercial_requests")
    if vis is not None:
        q = q.where(CommercialRequest.purchase_id.in_(
            select(Purchase.id).where(Purchase.subsidy_id.in_(vis))
        ))
    rows = (await db.execute(q)).scalars().all()
    return [_to_out(r) for r in rows]


@router.put("/{request_id}", response_model=CommercialRequestOut)
async def update_commercial_request(
    request_id: int,
    data: CommercialRequestUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab('commercial_requests')),
):
    """Обновить тему, текст, срок КП запроса."""
    req = (await db.execute(
        select(CommercialRequest)
        .options(selectinload(CommercialRequest.recipients))
        .where(CommercialRequest.id == request_id)
    )).scalar_one_or_none()
    if not req:
        raise HTTPException(404, "Запрос КП не найден")
    req.subject = data.subject
    req.intro_text = data.intro_text
    req.delivery_date = data.delivery_date
    await db.commit()
    await db.refresh(req)
    return _to_out(req)


@router.patch("/{request_id}/status", response_model=CommercialRequestOut)
async def update_commercial_request_status(
    request_id: int,
    data: CommercialRequestStatusUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab('commercial_requests')),
):
    req = (await db.execute(
        select(CommercialRequest)
        .options(selectinload(CommercialRequest.recipients))
        .where(CommercialRequest.id == request_id)
    )).scalar_one_or_none()
    if not req:
        raise HTTPException(404, "Запрос КП не найден")
    req.status = data.status
    await db.commit()
    await db.refresh(req)
    return _to_out(req)


@router.patch("/recipients/{recipient_id}/status", response_model=CommercialRequestOut)
async def update_recipient_status(
    recipient_id: int,
    data: CommercialRequestRecipientStatusUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab('commercial_requests')),
):
    recipient = (await db.execute(
        select(CommercialRequestRecipient).where(CommercialRequestRecipient.id == recipient_id)
    )).scalar_one_or_none()
    if not recipient:
        raise HTTPException(404, "Получатель запроса КП не найден")
    recipient.status = data.status
    await db.commit()

    req = (await db.execute(
        select(CommercialRequest)
        .options(selectinload(CommercialRequest.recipients))
        .where(CommercialRequest.id == recipient.request_id)
    )).scalar_one()
    return _to_out(req)


class KpSendRequest(BaseModel):
    recipients: List[FreeRecipient]  # name + email
    subject: str
    body: str


@router.post("/send")
async def send_kp_emails(
    data: KpSendRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab('commercial_requests')),
):
    """Отправить КП напрямую через SMTP (настройки из БД)."""
    from app.routers.settings import get_setting

    host = await get_setting(db, "smtp_host") or ""
    port = int(await get_setting(db, "smtp_port") or 587)
    user = await get_setting(db, "smtp_user") or ""
    password = await get_setting(db, "smtp_password") or ""
    frm_addr = await get_setting(db, "smtp_from") or user
    frm_name = await get_setting(db, "smtp_from_name") or ""
    ssl = (await get_setting(db, "smtp_ssl") or "false") == "true"

    if not host or not user:
        raise HTTPException(400, "SMTP не настроен. Перейдите в Настройки → Email.")

    valid = [r for r in data.recipients if r.email and r.email.strip()]
    if not valid:
        raise HTTPException(400, "Нет получателей с email")

    from_header = f"{frm_name} <{frm_addr}>" if frm_name else frm_addr

    logger.info("KP send: %d recipients via %s:%s (ssl=%s)", len(valid), host, port, ssl)

    sent, failed = 0, []
    try:
        if ssl:
            server = smtplib.SMTP_SSL(host, port, timeout=15)
        else:
            server = smtplib.SMTP(host, port, timeout=15)
            server.starttls()
        server.login(user, password)

        for r in valid:
            try:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = data.subject
                msg["From"] = from_header
                msg["To"] = r.email.strip()
                msg.attach(MIMEText(data.body, "plain", "utf-8"))
                server.sendmail(frm_addr, r.email.strip(), msg.as_string())
                sent += 1
                logger.info("KP email sent → %s", r.email.strip())
            except Exception as e:
                logger.warning("KP email failed → %s: %s", r.email, e)
                failed.append({"email": r.email, "error": str(e)})

        server.quit()
    except smtplib.SMTPAuthenticationError:
        logger.error("SMTP auth error for user=%s", user)
        raise HTTPException(400, "Ошибка авторизации SMTP. Проверьте логин и пароль.")
    except Exception as e:
        logger.error("SMTP connect error: %s", e)
        raise HTTPException(400, f"Ошибка подключения к SMTP: {str(e)}")

    return {"sent": sent, "failed": failed}


# ── Offers (владелец, 2026-08-29): цены, полученные от получателей запроса КП ──

def _offer_to_out(o: CommercialRequestOffer) -> CommercialRequestOfferOut:
    return CommercialRequestOfferOut(
        id=o.id,
        request_id=o.request_id,
        recipient_id=o.recipient_id,
        product_id=o.product_id,
        item_name=o.item_name,
        unit=o.unit,
        unit_price=o.unit_price,
        is_accepted=o.is_accepted,
        note=o.note,
        created_at=o.created_at,
    )


@router.get("/{request_id}/offers", response_model=List[CommercialRequestOfferOut])
async def list_offers(
    request_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    req = await db.get(CommercialRequest, request_id)
    if not req:
        raise HTTPException(404, "Запрос КП не найден")
    rows = (await db.execute(
        select(CommercialRequestOffer)
        .where(CommercialRequestOffer.request_id == request_id)
        .order_by(CommercialRequestOffer.id)
    )).scalars().all()
    return [_offer_to_out(o) for o in rows]


@router.put("/{request_id}/offers", response_model=List[CommercialRequestOfferOut])
async def replace_offers(
    request_id: int,
    offers: List[CommercialRequestOfferIn],
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab('commercial_requests')),
):
    """Заменить набор предложений (позиции × получатели) запроса КП.

    Строки с `id`, отсутствующим в новом наборе, удаляются (diff-sync — как и
    другие списки в проекте); строки с `id` обновляются на месте; строки без
    `id` создаются заново.
    """
    req = await db.get(CommercialRequest, request_id)
    if not req:
        raise HTTPException(404, "Запрос КП не найден")

    existing_rows = (await db.execute(
        select(CommercialRequestOffer).where(CommercialRequestOffer.request_id == request_id)
    )).scalars().all()
    existing_by_id = {o.id: o for o in existing_rows}

    kept_ids: set = set()
    result_rows: List[CommercialRequestOffer] = []
    for item in offers:
        if item.id is not None and item.id in existing_by_id:
            o = existing_by_id[item.id]
            o.recipient_id = item.recipient_id
            o.product_id = item.product_id
            o.item_name = item.item_name
            o.unit = item.unit
            o.unit_price = item.unit_price
            o.note = item.note
            kept_ids.add(o.id)
            result_rows.append(o)
        else:
            o = CommercialRequestOffer(
                request_id=request_id,
                recipient_id=item.recipient_id,
                product_id=item.product_id,
                item_name=item.item_name,
                unit=item.unit,
                unit_price=item.unit_price,
                note=item.note,
            )
            db.add(o)
            result_rows.append(o)

    for o in existing_rows:
        if o.id not in kept_ids:
            await db.delete(o)

    await db.commit()
    for o in result_rows:
        await db.refresh(o)
    return [_offer_to_out(o) for o in result_rows]


@router.post("/{request_id}/offers/{offer_id}/accept", response_model=CommercialRequestOfferOut)
async def accept_offer(
    request_id: int,
    offer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab('commercial_requests')),
):
    """Принять предложение — снимает флаг с остальных предложений на тот же
    товар в этом запросе КП и актуализирует цену товара в каталоге
    (source='kp'), см. app/services/price_actualization.py."""
    offer = (await db.execute(
        select(CommercialRequestOffer).where(
            CommercialRequestOffer.id == offer_id,
            CommercialRequestOffer.request_id == request_id,
        )
    )).scalar_one_or_none()
    if not offer:
        raise HTTPException(404, "Предложение не найдено")
    if offer.product_id is None:
        raise HTTPException(400, {
            "code": "offer_not_linked_to_product",
            "message": "Предложение не привязано к товару каталога — сначала сопоставьте позицию с товаром",
        })
    if offer.unit_price is None:
        raise HTTPException(400, {
            "code": "offer_missing_price",
            "message": "У предложения не заполнена цена",
        })

    product = await db.get(Product, offer.product_id)
    if not product:
        raise HTTPException(404, "Товар каталога не найден")

    # Снять принятие с остальных предложений на тот же товар в этом запросе
    siblings = (await db.execute(
        select(CommercialRequestOffer).where(
            CommercialRequestOffer.request_id == request_id,
            CommercialRequestOffer.product_id == offer.product_id,
            CommercialRequestOffer.id != offer.id,
        )
    )).scalars().all()
    for s in siblings:
        s.is_accepted = False
    offer.is_accepted = True

    contractor_id = None
    if offer.recipient_id:
        recipient = await db.get(CommercialRequestRecipient, offer.recipient_id)
        if recipient:
            contractor_id = recipient.contractor_id

    await actualize_product_price(
        db, product,
        price=offer.unit_price,
        source="kp",
        source_ref=f"Запрос КП №{request_id}",
        contractor_id=contractor_id,
        collected_at=_date.today(),
        user=current_user,
    )

    await db.commit()
    await db.refresh(offer)
    return _offer_to_out(offer)


def _to_out(r: CommercialRequest) -> CommercialRequestOut:
    return CommercialRequestOut(
        id=r.id,
        purchase_id=r.purchase_id,
        subject=r.subject,
        intro_text=r.intro_text,
        delivery_date=r.delivery_date,
        status=r.status,
        created_by=r.created_by,
        created_at=r.created_at.isoformat() if r.created_at else None,
        recipients=[
            CommercialRequestRecipientOut(
                id=x.id,
                contractor_id=x.contractor_id,
                contractor_name=x.contractor_name,
                email=x.email,
                status=x.status,
            )
            for x in (r.recipients or [])
        ],
    )
