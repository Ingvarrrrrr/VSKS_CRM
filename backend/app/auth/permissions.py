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


async def _get_effective(user: User, db: AsyncSession, org_id: Optional[int]) -> set:
    """Return effective key set (tabs + actions, undifferentiated).

    Role resolution: if user_org_access.role is set for (user_id, org_id) it takes
    precedence over user.role; otherwise fallback to user.role.
    Boolean-flip: base = {key for RP where role_name=effective_role and granted=True};
    then for each override row: granted=True -> add; granted=False -> discard.
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
