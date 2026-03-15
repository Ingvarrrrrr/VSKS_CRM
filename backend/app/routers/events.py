from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user, ADMIN_ROLES, require_role, get_single_org_id, get_org_filter
from app.database import get_db
from app.models.event import Event
from app.schemas.schemas import EventCreate, EventOut

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("/", response_model=List[EventOut])
async def list_events(
    subsidy_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    q = select(Event).order_by(Event.id)
    if subsidy_id is not None:
        q = q.where(Event.subsidy_id == subsidy_id)
    org_ids = get_org_filter(current_user)
    if org_ids is not None:
        q = q.where(Event.org_id.in_(org_ids))
    rows = (await db.execute(q)).scalars().all()
    return rows


@router.post("/", response_model=EventOut)
async def create_event(
    data: EventCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(*ADMIN_ROLES)),
):
    ev = Event(
        subsidy_id=data.subsidy_id,
        name=data.name,
        is_active=data.is_active,
        org_id=get_single_org_id(current_user) or current_user.org_id,
    )
    db.add(ev)
    await db.commit()
    await db.refresh(ev)
    return ev


@router.put("/{event_id}", response_model=EventOut)
async def update_event(
    event_id: int,
    data: EventCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(*ADMIN_ROLES)),
):
    ev = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
    if not ev:
        raise HTTPException(404, "Мероприятие не найдено")
    ev.subsidy_id = data.subsidy_id
    ev.name = data.name
    ev.is_active = data.is_active
    await db.commit()
    await db.refresh(ev)
    return ev


@router.delete("/{event_id}")
async def delete_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(*ADMIN_ROLES)),
):
    ev = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
    if not ev:
        raise HTTPException(404, "Мероприятие не найдено")
    await db.delete(ev)
    await db.commit()
    return {"ok": True}
