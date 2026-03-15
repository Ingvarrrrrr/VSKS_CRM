from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
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
    CommercialRequestOut,
    CommercialRequestRecipientOut,
    CommercialRequestStatusUpdate,
    CommercialRequestRecipientStatusUpdate,
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
