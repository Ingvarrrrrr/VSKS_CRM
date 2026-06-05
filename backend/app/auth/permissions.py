"""Phase 17: effective permission resolution + Depends factories.

Boolean-flip model (D-02): effective = overrides.get(key, role_permissions[role][key])
Superadmin bypass (D-05.3): always True, no DB queries.
Per-org (D-08): FK via user_org_access.id.
"""
from typing import Optional
from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.user import User
from app.models.user_org_access import UserOrgAccess
from app.models.permission import RolePermission, UserOrgPermissionOverride
from app.auth.jwt import get_current_user


async def ensure_user_org_access(
    user_id: int, org_id: int, role: Optional[str], db: AsyncSession
) -> int:
    """Idempotent UPSERT into user_org_access.

    Returns the uoa.id. If row exists, updates role only if new role is provided
    and differs from existing. Creates row with given role if missing.
    Caller is responsible for committing the session.
    """
    existing = (await db.execute(
        select(UserOrgAccess).where(
            UserOrgAccess.user_id == user_id,
            UserOrgAccess.org_id == org_id,
        )
    )).scalar_one_or_none()
    if existing:
        if role is not None and existing.role != role:
            existing.role = role
        return existing.id
    new = UserOrgAccess(user_id=user_id, org_id=org_id, role=role)
    db.add(new)
    await db.flush()
    return new.id


async def remove_user_org_access(
    user_id: int, org_id: int, db: AsyncSession
) -> None:
    """Idempotent DELETE from user_org_access.

    Cascades to user_org_permission_overrides via FK ON DELETE CASCADE.
    Caller is responsible for committing the session.
    """
    existing = (await db.execute(
        select(UserOrgAccess).where(
            UserOrgAccess.user_id == user_id,
            UserOrgAccess.org_id == org_id,
        )
    )).scalar_one_or_none()
    if existing:
        await db.delete(existing)


_ROLE_PRIORITY = {
    "superadmin": 6,
    "account_owner": 5,
    "admin": 4,
    "org_admin": 3,
    "manager": 2,
    "employee": 1,
}


async def _get_effective_simple(user: User, db: AsyncSession, org_id: Optional[int]) -> set:
    """Return effective key set for a single user WITHOUT hierarchy inheritance.

    Role resolution: if user_org_access.role is set for (user_id, org_id) it takes
    precedence over user.role; otherwise fallback to user.role.
    Per-org fallback (N-10): if user has no contour role (NULL) or no UOA for the
    active org, also scan ALL user_org_access rows and pick the highest-priority role.
    This ensures users managed via per-org role assignment (e.g. org_admin in ВСКС)
    receive correct tab/action permissions even when their contour user.role is NULL.
    Boolean-flip: base = {key for RP where role_name=effective_role and granted=True};
    then for each override row: granted=True -> add; granted=False -> discard.

    NOTE: Does NOT call get_visible_user_ids — safe to call from _get_effective loop.
    """
    # Step 0: resolve effective role (per-org override takes precedence)
    effective_role = user.role
    if org_id:
        uoa = (await db.execute(
            select(UserOrgAccess).where(
                UserOrgAccess.user_id == user.id,
                UserOrgAccess.org_id == org_id,
            )
        )).scalar_one_or_none()
        if uoa and uoa.role:
            effective_role = uoa.role

    # Step 0b: elevate to best per-org role if it outranks the contour role.
    # Модель: вкладки/действия — по max-роли (глоб. ИЛИ лучшая per-org).
    # Данные при этом скоупятся отдельно через get_org_filter в эндпоинтах.
    all_uoa_rows = (await db.execute(
        select(UserOrgAccess.role).where(
            UserOrgAccess.user_id == user.id,
            UserOrgAccess.role.isnot(None),
        )
    )).scalars().all()
    if all_uoa_rows:
        best_per_org = max(all_uoa_rows, key=lambda r: _ROLE_PRIORITY.get(r, 0))
        if _ROLE_PRIORITY.get(best_per_org, 0) > _ROLE_PRIORITY.get(effective_role, 0):
            effective_role = best_per_org

    # Step 1: base from role matrix with resolved role
    rp_rows = await db.execute(
        select(RolePermission).where(
            RolePermission.role_name == effective_role,
            RolePermission.granted == True,  # noqa: E712
        )
    )
    effective: set = {r.key for r in rp_rows.scalars()}

    # Step 2: apply per-org overrides
    if org_id:
        ov_rows = await db.execute(
            select(UserOrgPermissionOverride).join(
                UserOrgAccess,
                UserOrgPermissionOverride.user_org_access_id == UserOrgAccess.id,
            ).where(
                UserOrgAccess.user_id == user.id,
                UserOrgAccess.org_id == org_id,
            )
        )
        for ov in ov_rows.scalars():
            if ov.granted:
                effective.add(ov.key)
            else:
                effective.discard(ov.key)

    return effective


async def _get_effective(user: User, db: AsyncSession, org_id: Optional[int]) -> set:
    """Return effective key set (tabs + actions, undifferentiated) — "поглощение".

    Phase 28-Ext (5736ba3) / Phase 26-AA (revert после фидбека пользователя):
    "Иерархия > роли" — пользователь наследует UNION прав ВСЕХ подчинённых через
    UserHierarchy. То есть если ты ставишь задачи admin'у — ты получаешь его tabs.
    Если ставишь задачи superadmin'у — получаешь SaaS-уровень.

    Бизнес-семантика: «он наследует все умения тех, кому ставит задачи».
    Pluton-стиль владения: руководитель видит то же что и подчинённый.

    Лессон: Phase 26-P (7da566a) убирал UNION чтобы ограничить UI Лягину,
    но это слом business model — иерархия должна давать поглощение.

    Если в visible_uids есть SaaS-юзер (superadmin/account_owner) — добавляем
    также все ключи (через role matrix этого SaaS-уровня).
    """
    effective = await _get_effective_simple(user, db, org_id)

    from app.auth.visibility import get_visible_user_ids
    visible = await get_visible_user_ids(user, db)
    if visible is None:
        # User сам SaaS — _get_effective_simple уже даёт ему максимум
        return effective
    for sub_uid in visible - {user.id}:
        sub_user = await db.get(User, sub_uid)
        if sub_user:
            effective |= await _get_effective_simple(sub_user, db, org_id)
    return effective


# Phase 26-AA: оставлен alias для обратной совместимости (visibility.py использовал)
_get_effective_with_inheritance = _get_effective


async def get_effective_tabs(
    user: User, db: AsyncSession, org_id: Optional[int] = None
) -> set:
    """Alias kept for readability - same resolution for tabs and actions."""
    return await _get_effective(user, db, org_id)


async def get_effective_actions(
    user: User, db: AsyncSession, org_id: Optional[int] = None
) -> set:
    return await _get_effective(user, db, org_id)


def _active_org(user: User) -> Optional[int]:
    return getattr(user, "_active_org_id", None) or user.org_id


def require_tab(tab_key: str):
    """FastAPI Depends factory. 403 if tab_key not in effective; bypass superadmin."""
    async def checker(
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ):
        if user.role == "superadmin":
            return user
        effective = await _get_effective(user, db, _active_org(user))
        if tab_key not in effective:
            raise HTTPException(status_code=403, detail="Доступ запрещён")
        return user

    return checker


def require_action(action_key: str):
    """FastAPI Depends factory. 403 if action_key not in effective; bypass superadmin."""
    async def checker(
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ):
        if user.role == "superadmin":
            return user
        effective = await _get_effective(user, db, _active_org(user))
        if action_key not in effective:
            raise HTTPException(status_code=403, detail="Действие запрещено")
        return user

    return checker


async def can_manage_purchase(user, purchase, db) -> bool:
    """27.4-09: True если user имеет право управлять данной закупкой.

    Правила:
    - superadmin → всегда
    - admin/account_owner → если purchase видим (через build_visibility_clause)
    - Любой user → если он автор авансового отчёта (purchase_method='advance' AND reimbursement_user_id == user.id)
    - manager → если purchase видим И user имеет tab 'purchases'
    - employee → только свои авансовые отчёты (см. выше)
    """
    if not purchase:
        return False
    if user.role == 'superadmin':
        return True
    # Owner авансового — всегда
    if (getattr(purchase, 'purchase_method', None) == 'advance'
            and getattr(purchase, 'reimbursement_user_id', None) == user.id):
        return True
    # Manager+ с tab 'purchases'
    effective = await _get_effective(user, db, _active_org(user))
    if 'purchases' in effective and user.role in ('admin', 'manager', 'account_owner'):
        return True
    return False
