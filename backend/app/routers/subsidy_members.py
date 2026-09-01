"""Subsidy members router — совместная работа над черновой субсидией (план C1/C2).

«Так же подключать к этой субсидии других людей для совместной работы (как с
заявкой)» — калька wish_members, но БЕЗ consent-флоу: субсидия ещё не «рабочая»
(это смета), приглашение участника не требует его подтверждения.

Endpoints:
  GET    /api/subsidies/{sid}/members            — list participants
  POST   /api/subsidies/{sid}/members             — add participant
  DELETE /api/subsidies/{sid}/members/{user_id}   — remove participant

Добавляет/удаляет участников автор субсидии или тот, у кого выдано право
subsidy.edit в орге этой субсидии.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.jwt import get_current_user, get_org_filter
from app.auth.permissions import has_org_key
from app.models.user import User
from app.models.subsidy import Subsidy
from app.models.subsidy_member import SubsidyMember

logger = logging.getLogger(__name__)

# NOTE: prefix matches subsidies.router so FastAPI resolves all /api/subsidies/* paths together.
router = APIRouter(prefix="/api/subsidies", tags=["subsidy-members"])


def _member_dict(m: SubsidyMember) -> dict:
    return {
        "id": m.id,
        "subsidy_id": m.subsidy_id,
        "user_id": m.user_id,
        "added_by_id": m.added_by_id,
        "username": (m.user.username if m.user else None),
        "full_name": (m.user.full_name if m.user else None),
        "added_by_name": (
            (m.added_by.full_name or m.added_by.username) if m.added_by else None
        ),
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


async def _get_subsidy_or_403(sid: int, current_user: User, db: AsyncSession) -> Subsidy:
    subsidy = await db.get(Subsidy, sid)
    if subsidy is None:
        raise HTTPException(404, "Субсидия не найдена")
    org_ids = get_org_filter(current_user)
    if org_ids is not None and subsidy.org_id not in org_ids:
        raise HTTPException(403, "Нет доступа к этой субсидии")
    return subsidy


async def _can_manage_subsidy_members(subsidy: Subsidy, current_user: User, db: AsyncSession) -> bool:
    """Добавляет/удаляет участников автор субсидии или тот, у кого subsidy.edit
    в орге этой субсидии (владелец: «CRUD участников ... добавляет автор или
    тот, у кого subsidy.edit»)."""
    if current_user.role in ("superadmin", "account_owner"):
        return True
    if subsidy.created_by is not None and subsidy.created_by == current_user.id:
        return True
    return await has_org_key(current_user, db, subsidy.org_id, "subsidy.edit", subsidy_id=subsidy.id)


# ---------------------------------------------------------------------------
# GET /api/subsidies/{sid}/members
# ---------------------------------------------------------------------------

@router.get("/{sid}/members")
async def list_subsidy_members(
    sid: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_subsidy_or_403(sid, current_user, db)
    result = await db.execute(
        select(SubsidyMember).where(SubsidyMember.subsidy_id == sid)
    )
    return [_member_dict(m) for m in result.scalars().all()]


# ---------------------------------------------------------------------------
# POST /api/subsidies/{sid}/members
# ---------------------------------------------------------------------------

@router.post("/{sid}/members", status_code=201)
async def add_subsidy_member(
    sid: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    subsidy = await _get_subsidy_or_403(sid, current_user, db)
    if not await _can_manage_subsidy_members(subsidy, current_user, db):
        raise HTTPException(
            403,
            "Добавлять участников субсидии может автор или сотрудник с правом «Редактирование субсидий»",
        )

    user_id = int(body.get("user_id", 0))
    if not user_id:
        raise HTTPException(422, "user_id обязателен")

    target_user = await db.get(User, user_id)
    if target_user is None:
        raise HTTPException(404, "Пользователь не найден")

    existing = await db.execute(
        select(SubsidyMember).where(
            SubsidyMember.subsidy_id == sid,
            SubsidyMember.user_id == user_id,
        )
    )
    m = existing.scalar_one_or_none()
    if m is None:
        m = SubsidyMember(subsidy_id=sid, user_id=user_id, added_by_id=current_user.id)
        db.add(m)
        await db.flush()

    await db.commit()
    await db.refresh(m)
    return _member_dict(m)


# ---------------------------------------------------------------------------
# DELETE /api/subsidies/{sid}/members/{user_id}
# ---------------------------------------------------------------------------

@router.delete("/{sid}/members/{user_id}")
async def remove_subsidy_member(
    sid: int,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    subsidy = await _get_subsidy_or_403(sid, current_user, db)
    if not await _can_manage_subsidy_members(subsidy, current_user, db):
        raise HTTPException(
            403,
            "Удалять участников субсидии может автор или сотрудник с правом «Редактирование субсидий»",
        )

    result = await db.execute(
        select(SubsidyMember).where(
            SubsidyMember.subsidy_id == sid,
            SubsidyMember.user_id == user_id,
        )
    )
    m = result.scalar_one_or_none()
    if m:
        await db.delete(m)
        await db.commit()
    return {"ok": True}
