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


async def _get_effective(user: User, db: AsyncSession, org_id: Optional[int]) -> set:
    """Return effective key set (tabs + actions, undifferentiated).

    Boolean-flip: base = {key for RP where role_name=user.role and granted=True};
    then for each override row: granted=True -> add; granted=False -> discard.
    """
    # Step 1: base from role matrix
    rp_rows = await db.execute(
        select(RolePermission).where(
            RolePermission.role_name == user.role,
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
