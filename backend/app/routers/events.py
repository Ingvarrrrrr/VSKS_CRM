import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user, get_org_filter
from app.auth.permissions import has_org_key
from app.database import get_db
from app.models.event import Event
from app.models.subsidy import Subsidy
from app.models.wish import Wish
from app.models.purchase import Purchase
from app.schemas.schemas import EventCreate, EventOut

router = APIRouter(prefix="/api/events", tags=["events"])


def normalize_event_name(name: Optional[str]) -> str:
    """Нормализация имени мероприятия для сравнения на дубли: trim, схлопывание
    внутренних пробелов, casefold, ё→е. Единственная точка ввода мероприятий —
    карточка субсидии (требование владельца, 2026-08-19): «разночтения в
    названиях, иначе я потом никогда ничего не посчитаю» — поэтому сравнение
    должно игнорировать регистр/пробелы/ё-е, а не требовать байт-в-байт совпадение."""
    if not name:
        return ""
    s = name.strip().casefold().replace("ё", "е")
    s = re.sub(r"\s+", " ", s)
    return s


async def _get_subsidy_for_events(
    sid: int, db: AsyncSession, current_user, edit: bool = False
) -> Subsidy:
    """Гейт по субсидии-владельцу мероприятия (по образцу
    subsidy_approvers._get_subsidy_or_404). Единственная точка ввода
    мероприятий — карточка субсидии; право добавлять/менять = право
    редактировать субсидию (subsidy.edit), а не отдельная админ-вкладка."""
    result = await db.execute(select(Subsidy).where(Subsidy.id == sid))
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(404, "Субсидия не найдена")
    if edit:
        if not await has_org_key(current_user, db, s.org_id, 'subsidy.edit', subsidy_id=sid):
            raise HTTPException(
                403,
                "Добавлять и править мероприятия может только тот, у кого есть право "
                "редактирования этой субсидии",
            )
    else:
        org_ids = get_org_filter(current_user)
        if org_ids is not None and s.org_id not in org_ids:
            raise HTTPException(403, "Нет доступа к этой субсидии")
    return s


async def _find_duplicate_event(
    db: AsyncSession, subsidy_id: int, name: str, exclude_id: Optional[int] = None
) -> Optional[Event]:
    norm = normalize_event_name(name)
    if not norm:
        return None
    q = select(Event).where(Event.subsidy_id == subsidy_id)
    if exclude_id is not None:
        q = q.where(Event.id != exclude_id)
    rows = (await db.execute(q)).scalars().all()
    for ev in rows:
        if normalize_event_name(ev.name) == norm:
            return ev
    return None


@router.get("/", response_model=List[EventOut])
async def list_events(
    subsidy_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Фильтр по орге СУБСИДИИ, а не Event.org_id: исторически часть мероприятий
    # заведена с org_id пользователя-создателя, отличным от org_id субсидии —
    # такие мероприятия не должны пропадать из списков (см. миграцию i0j1k2l3m4n5).
    q = (
        select(Event)
        .join(Subsidy, Subsidy.id == Event.subsidy_id)
        .order_by(Event.id)
    )
    if subsidy_id is not None:
        q = q.where(Event.subsidy_id == subsidy_id)
    org_ids = get_org_filter(current_user)
    if org_ids is not None:
        q = q.where(Subsidy.org_id.in_(org_ids))
    rows = (await db.execute(q)).scalars().all()
    return rows


@router.post("/", response_model=EventOut)
async def create_event(
    data: EventCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    subsidy = await _get_subsidy_for_events(data.subsidy_id, db, current_user, edit=True)

    dup = await _find_duplicate_event(db, data.subsidy_id, data.name)
    if dup:
        raise HTTPException(
            409,
            f"В субсидии уже есть мероприятие «{dup.name}» (id {dup.id}) — "
            "выберите его, а не создавайте копию",
        )

    ev = Event(
        subsidy_id=data.subsidy_id,
        name=data.name,
        is_active=data.is_active,
        org_id=subsidy.org_id,
        region=data.region,
        date_from=data.date_from,
        date_to=data.date_to,
        order_decree=data.order_decree,
        planned_indicators=data.planned_indicators,
        actual_indicators=data.actual_indicators,
        media_link_1=data.media_link_1,
        media_link_2=data.media_link_2,
        media_link_3=data.media_link_3,
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
    current_user=Depends(get_current_user),
):
    ev = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
    if not ev:
        raise HTTPException(404, "Мероприятие не найдено")

    await _get_subsidy_for_events(ev.subsidy_id, db, current_user, edit=True)

    if data.subsidy_id != ev.subsidy_id:
        raise HTTPException(409, "Мероприятие нельзя перенести в другую субсидию")

    dup = await _find_duplicate_event(db, ev.subsidy_id, data.name, exclude_id=ev.id)
    if dup:
        raise HTTPException(
            409,
            f"В субсидии уже есть мероприятие «{dup.name}» (id {dup.id}) — "
            "выберите его, а не создавайте копию",
        )

    ev.name = data.name
    ev.is_active = data.is_active
    ev.region = data.region
    ev.date_from = data.date_from
    ev.date_to = data.date_to
    ev.order_decree = data.order_decree
    ev.planned_indicators = data.planned_indicators
    ev.actual_indicators = data.actual_indicators
    ev.media_link_1 = data.media_link_1
    ev.media_link_2 = data.media_link_2
    ev.media_link_3 = data.media_link_3
    await db.commit()
    await db.refresh(ev)
    return ev


@router.delete("/{event_id}")
async def delete_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    ev = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
    if not ev:
        raise HTTPException(404, "Мероприятие не найдено")

    await _get_subsidy_for_events(ev.subsidy_id, db, current_user, edit=True)

    wishes_count = (
        await db.execute(select(func.count()).select_from(Wish).where(Wish.event_id == event_id))
    ).scalar() or 0
    purchases_count = (
        await db.execute(select(func.count()).select_from(Purchase).where(Purchase.event_id == event_id))
    ).scalar() or 0
    if wishes_count or purchases_count:
        raise HTTPException(
            409,
            f"Мероприятие используется: заявок {wishes_count}, закупок {purchases_count}. "
            "Снимите галочку «активно» вместо удаления",
        )

    await db.delete(ev)
    await db.commit()
    return {"ok": True}
