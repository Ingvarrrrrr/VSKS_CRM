"""Списки пользователей для пикеров исполнителей/инициаторов: кому можно
поставить задачу без согласования, все сотрудники «моих» организаций, все
видимые для делегирования служебной записки.

ПЕРЕНЕСЕНО (не изменено) из app/routers/users.py при разрезании монолитного
роутера (Правило №5, сессия 2026-09-08). Тот же префикс /api/users. Все три
пути здесь — ровно один сегмент (/assignable-ids, /in-my-orgs, /i-can-act-for),
поэтому ОБЯЗАНЫ регистрироваться в app/routes.py ДО users.router — иначе
Starlette матчит их на литерал маршрута GET /{user_id} раньше, чем на эти,
и FastAPI падает 422 при попытке привести "assignable-ids" и т.п. к int.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.auth.jwt import get_current_user
from app.schemas.schemas import UserOut
from typing import List

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/assignable-ids")
async def assignable_user_ids(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """ID пользователей, которым текущий может ставить задачи БЕЗ согласия.

    Нужен фронту, чтобы в пикере участников заявки/задачи показать пометку
    «требуется согласование» у тех, кто не в подчинении. all=true → SaaS-роль,
    согласование не нужно ни для кого.
    """
    from app.services.consent import compute_assignable_user_ids
    assignable = await compute_assignable_user_ids(current_user, db)
    if assignable is None:
        return {"all": True, "ids": []}
    return {"all": False, "ids": sorted(assignable)}


@router.get("/in-my-orgs", response_model=List[UserOut])
async def list_users_in_my_orgs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Возвращает пользователей из всех организаций текущего юзера для autocomplete
    «Исполнитель» в MyTasksView (без hierarchy-фильтра).
    Для не-подчинённых назначаемых create_task выставит consent_needed=true.

    Источники org_id (объединение):
      1. user_organizations.user_id == current_user.id
      2. users.org_id (primary org — legacy для юзеров без user_organizations row)
      3. user_org_access.user_id == current_user.id (per-org role/permissions)
    Если ни одного орг не нашлось — возвращаем всех (fallback, ранний бутстрап).
    Суперадмины скрыты от не-суперадминов (бизнес-правило: суперадмин невидим).
    """
    from app.models.user_organization import UserOrganization
    own_orgs: set[int] = set()

    # 1. user_organizations
    res = await db.execute(
        select(UserOrganization.org_id).where(UserOrganization.user_id == current_user.id)
    )
    own_orgs.update(r[0] for r in res.all() if r[0])

    # 2. primary org_id
    if current_user.org_id:
        own_orgs.add(current_user.org_id)

    # 3. user_org_access
    try:
        from app.models.user_org_access import UserOrgAccess
        res = await db.execute(
            select(UserOrgAccess.org_id).where(UserOrgAccess.user_id == current_user.id)
        )
        own_orgs.update(r[0] for r in res.all() if r[0])
    except Exception:
        pass

    if own_orgs:
        # Все user_id из этих орг (через любой источник)
        user_ids: set[int] = set()
        res = await db.execute(
            select(UserOrganization.user_id).where(UserOrganization.org_id.in_(own_orgs)).distinct()
        )
        user_ids.update(r[0] for r in res.all() if r[0])
        res = await db.execute(
            select(User.id).where(User.org_id.in_(own_orgs))
        )
        user_ids.update(r[0] for r in res.all() if r[0])
        # Сам current_user всегда включён
        user_ids.add(current_user.id)
        if user_ids:
            q = select(User).where(User.id.in_(user_ids)).order_by(User.full_name)
            if current_user.role != "superadmin":
                q = q.where(User.role != "superadmin")
            res = await db.execute(q)
            return res.scalars().all()

    # Fallback: ни одной орг не нашлось — вернуть всех (ранний бутстрап / data-issue)
    q_fallback = select(User).order_by(User.full_name)
    if current_user.role != "superadmin":
        q_fallback = q_fallback.where(User.role != "superadmin")
    res = await db.execute(q_fallback)
    return res.scalars().all()


@router.get("/i-can-act-for", response_model=List[UserOut])
async def list_users_i_can_act_for(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Возвращает себя + всех видимых через _get_visible_user_ids (подчинённые
    по иерархии + начальник отдела/орг). Используется для picker'а инициатора
    служебной записки: за другого человека делать СЗ может только тот, кому
    он подчинён. См. бизнес-правило в documents.py:generate_document."""
    from app.routers.task_visibility import _get_visible_user_ids
    visible = await _get_visible_user_ids(current_user, db)
    if visible is None:
        # SaaS-wide — отдаём всех; суперадмины скрыты от не-суперадминов
        q_all = select(User).order_by(User.full_name)
        if current_user.role != "superadmin":
            q_all = q_all.where(User.role != "superadmin")
        res = await db.execute(q_all)
        return res.scalars().all()
    # Самого себя гарантированно включаем
    visible = set(visible)
    visible.add(current_user.id)
    if not visible:
        return [current_user]
    q_vis = select(User).where(User.id.in_(visible)).order_by(User.full_name)
    if current_user.role != "superadmin":
        q_vis = q_vis.where(User.role != "superadmin")
    res = await db.execute(q_vis)
    return res.scalars().all()
