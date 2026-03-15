from typing import List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from datetime import datetime

from app.auth.jwt import get_current_user, require_role
from app.database import get_db
from app.models.purchase import Purchase
from app.models.purchase_event import PurchaseMember, PurchaseEvent
from app.models.user import User

router = APIRouter(prefix="/api/purchases", tags=["purchase-events"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class MemberOut(BaseModel):
    id: int
    purchase_id: int
    user_id: int
    role: str
    username: str
    full_name: Optional[str] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class EventOut(BaseModel):
    id: int
    purchase_id: int
    user_id: Optional[int] = None
    username: Optional[str] = None
    full_name: Optional[str] = None
    event_type: str
    data: Optional[Any] = None
    created_at: str

    class Config:
        from_attributes = True


class AddMemberBody(BaseModel):
    user_id: int
    role: str = "viewer"


class AddEventBody(BaseModel):
    event_type: str
    data: Optional[Any] = None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _member_out(m: PurchaseMember) -> MemberOut:
    return MemberOut(
        id=m.id,
        purchase_id=m.purchase_id,
        user_id=m.user_id,
        role=m.role,
        username=m.user.username if m.user else str(m.user_id),
        full_name=m.user.full_name if m.user else None,
        created_at=m.created_at.isoformat() if m.created_at else None,
    )


def _event_out(e: PurchaseEvent) -> EventOut:
    return EventOut(
        id=e.id,
        purchase_id=e.purchase_id,
        user_id=e.user_id,
        username=e.user.username if e.user else None,
        full_name=e.user.full_name if e.user else None,
        event_type=e.event_type,
        data=e.data,
        created_at=e.created_at.isoformat() if e.created_at else "",
    )


# ── Members ──────────────────────────────────────────────────────────────────

@router.get("/{pid}/members", response_model=List[MemberOut])
async def list_members(
    pid: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    rows = (await db.execute(
        select(PurchaseMember).where(PurchaseMember.purchase_id == pid)
    )).scalars().all()
    return [_member_out(m) for m in rows]


@router.post("/{pid}/members", response_model=MemberOut)
async def add_member(
    pid: int,
    body: AddMemberBody,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin", "manager")),
):
    purchase = (await db.execute(select(Purchase).where(Purchase.id == pid))).scalar_one_or_none()
    if not purchase:
        raise HTTPException(404, "Закупка не найдена")
    user = (await db.execute(select(User).where(User.id == body.user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Пользователь не найден")

    existing = (await db.execute(
        select(PurchaseMember).where(
            PurchaseMember.purchase_id == pid,
            PurchaseMember.user_id == body.user_id,
        )
    )).scalar_one_or_none()
    if existing:
        existing.role = body.role
    else:
        existing = PurchaseMember(purchase_id=pid, user_id=body.user_id, role=body.role)
        db.add(existing)
    await db.commit()
    await db.refresh(existing)
    m = (await db.execute(
        select(PurchaseMember).where(PurchaseMember.id == existing.id)
    )).scalar_one()
    return _member_out(m)


@router.delete("/{pid}/members/{uid}", status_code=204)
async def remove_member(
    pid: int,
    uid: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin", "manager")),
):
    m = (await db.execute(
        select(PurchaseMember).where(
            PurchaseMember.purchase_id == pid,
            PurchaseMember.user_id == uid,
        )
    )).scalar_one_or_none()
    if m:
        await db.delete(m)
        await db.commit()


# ── Events ───────────────────────────────────────────────────────────────────

@router.get("/{pid}/events", response_model=List[EventOut])
async def list_events(
    pid: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    rows = (await db.execute(
        select(PurchaseEvent)
        .where(PurchaseEvent.purchase_id == pid)
        .order_by(PurchaseEvent.id.desc())
    )).scalars().all()
    return [_event_out(e) for e in rows]


@router.post("/{pid}/events", response_model=EventOut)
async def add_event(
    pid: int,
    body: AddEventBody,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    purchase = (await db.execute(select(Purchase).where(Purchase.id == pid))).scalar_one_or_none()
    if not purchase:
        raise HTTPException(404, "Закупка не найдена")
    event = PurchaseEvent(
        purchase_id=pid,
        user_id=getattr(current_user, "id", None),
        event_type=body.event_type,
        data=body.data,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    e = (await db.execute(select(PurchaseEvent).where(PurchaseEvent.id == event.id))).scalar_one()
    return _event_out(e)
