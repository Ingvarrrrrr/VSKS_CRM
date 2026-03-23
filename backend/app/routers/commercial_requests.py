import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.jwt import get_current_user, require_role, MANAGER_ROLES, get_org_filter
from app.database import get_db
from app.models.commercial_request import CommercialRequest, CommercialRequestRecipient
from app.models.contractor import Contractor
from app.models.purchase import Purchase
from app.schemas.schemas import (
    CommercialRequestCreate,
    CommercialRequestUpdate,
    CommercialRequestOut,
    CommercialRequestRecipientOut,
    CommercialRequestStatusUpdate,
    CommercialRequestRecipientStatusUpdate,
    FreeRecipient,
)

router = APIRouter(prefix="/api/commercial-requests", tags=["commercial_requests"])


@router.post("/", response_model=CommercialRequestOut)
async def create_commercial_request(
    data: CommercialRequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(*MANAGER_ROLES)),
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
    from app.models.subsidy import Subsidy
    q = (select(CommercialRequest)
         .options(selectinload(CommercialRequest.recipients))
         .order_by(CommercialRequest.id.desc()))
    if purchase_id is not None:
        q = q.where(CommercialRequest.purchase_id == purchase_id)
    org_ids = get_org_filter(current_user)
    if org_ids is not None:
        q = q.join(Purchase, CommercialRequest.purchase_id == Purchase.id).join(Subsidy, Purchase.subsidy_id == Subsidy.id).where(Subsidy.org_id.in_(org_ids))
    rows = (await db.execute(q)).scalars().all()
    return [_to_out(r) for r in rows]


@router.put("/{request_id}", response_model=CommercialRequestOut)
async def update_commercial_request(
    request_id: int,
    data: CommercialRequestUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(*MANAGER_ROLES)),
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
    _=Depends(require_role(*MANAGER_ROLES)),
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
    _=Depends(require_role(*MANAGER_ROLES)),
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
    _=Depends(require_role(*MANAGER_ROLES)),
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

    sent, failed = 0, []
    try:
        if ssl:
            server = smtplib.SMTP_SSL(host, port)
        else:
            server = smtplib.SMTP(host, port)
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
            except Exception as e:
                failed.append({"email": r.email, "error": str(e)})

        server.quit()
    except smtplib.SMTPAuthenticationError:
        raise HTTPException(400, "Ошибка авторизации SMTP. Проверьте логин и пароль.")
    except Exception as e:
        raise HTTPException(400, f"Ошибка подключения к SMTP: {str(e)}")

    return {"sent": sent, "failed": failed}


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
