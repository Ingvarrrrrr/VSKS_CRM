"""Phase 17 Plan 05: Admin CRUD for role permissions matrix + per-user overrides.

D-03: GET/PUT matrix endpoints for AdminRolesView.vue
D-05.2: Self-lockout protection on admin.roles + staff keys
D-08: Per-org overrides via user_org_access_id FK
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.user_org_access import UserOrgAccess
from app.models.permission import (
    PermissionTab, PermissionAction, RolePermission, UserOrgPermissionOverride,
)
from app.auth.jwt import get_current_user
from app.auth.permissions import require_tab
from app.schemas.schemas import (
    PermissionTabOut, PermissionActionOut, RoleMatrixRow,
    PermissionUpdate, OverrideOut, RoleUpdate,
)

router = APIRouter(prefix="/api/permissions", tags=["permissions"])

ROLES = ("superadmin", "account_owner", "admin", "org_admin", "manager", "employee")
SELF_LOCKOUT_PROTECTED_KEYS = {"admin.roles", "staff"}


@router.get("/tabs", response_model=List[PermissionTabOut])
async def list_tabs(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_tab("admin.roles")),
):
    res = await db.execute(select(PermissionTab).order_by(PermissionTab.tab_key))
    return res.scalars().all()


@router.get("/actions", response_model=List[PermissionActionOut])
async def list_actions(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_tab("admin.roles")),
):
    res = await db.execute(select(PermissionAction).order_by(PermissionAction.action_key))
    return res.scalars().all()


@router.get("/roles", response_model=List[RoleMatrixRow])
async def get_matrix(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_tab("admin.roles")),
):
    """Return the full matrix as one row per role with granted tab_keys/action_keys."""
    tab_keys = {r for r, in (await db.execute(select(PermissionTab.tab_key))).all()}
    action_keys = {r for r, in (await db.execute(select(PermissionAction.action_key))).all()}

    rows = []
    for role in ROLES:
        if role == "superadmin":
            continue  # D-09: superadmin не отображается в матрице
        res = await db.execute(
            select(RolePermission).where(
                RolePermission.role_name == role,
                RolePermission.granted == True,  # noqa: E712
            )
        )
        granted = {r.key for r in res.scalars()}
        rows.append(RoleMatrixRow(
            role_name=role,
            tabs=sorted(granted & tab_keys),
            actions=sorted(granted & action_keys),
        ))
    return rows


@router.put("/roles/{role_name}")
async def update_role_matrix(
    role_name: str,
    updates: List[PermissionUpdate],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("admin.roles")),
):
    if role_name not in ROLES or role_name == "superadmin":
        raise HTTPException(400, "Недопустимая роль")

    # D-05.2 self-lockout protection
    if role_name == current_user.role:
        for upd in updates:
            if upd.key in SELF_LOCKOUT_PROTECTED_KEYS and not upd.granted:
                raise HTTPException(
                    403,
                    f"Нельзя снять доступ к '{upd.key}' у своей роли (самоблокировка)",
                )

    # Upsert each (role_name, key) row
    for upd in updates:
        res = await db.execute(
            select(RolePermission).where(
                RolePermission.role_name == role_name,
                RolePermission.key == upd.key,
            )
        )
        existing = res.scalar_one_or_none()
        if existing:
            existing.granted = upd.granted
        else:
            db.add(RolePermission(role_name=role_name, key=upd.key, granted=upd.granted))
    await db.commit()
    return {"status": "ok", "updated": len(updates)}


@router.get("/users/{user_id}/overrides", response_model=List[OverrideOut])
async def list_overrides(
    user_id: int,
    org_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_tab("staff")),
):
    uoa = await db.execute(
        select(UserOrgAccess).where(
            UserOrgAccess.user_id == user_id,
            UserOrgAccess.org_id == org_id,
        )
    )
    uoa_obj = uoa.scalar_one_or_none()
    if uoa_obj is None:
        return []
    res = await db.execute(
        select(UserOrgPermissionOverride).where(
            UserOrgPermissionOverride.user_org_access_id == uoa_obj.id
        )
    )
    return res.scalars().all()


@router.put("/users/{user_id}/overrides")
async def update_overrides(
    user_id: int,
    updates: List[PermissionUpdate],
    org_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("staff")),
):
    # D-05.2 self-lockout on own user
    if user_id == current_user.id:
        for upd in updates:
            if upd.key in SELF_LOCKOUT_PROTECTED_KEYS and not upd.granted:
                raise HTTPException(
                    403,
                    f"Нельзя снять доступ к '{upd.key}' у себя (самоблокировка)",
                )

    uoa = await db.execute(
        select(UserOrgAccess).where(
            UserOrgAccess.user_id == user_id,
            UserOrgAccess.org_id == org_id,
        )
    )
    uoa_obj = uoa.scalar_one_or_none()
    if uoa_obj is None:
        raise HTTPException(404, "Пользователь не привязан к организации")

    for upd in updates:
        res = await db.execute(
            select(UserOrgPermissionOverride).where(
                UserOrgPermissionOverride.user_org_access_id == uoa_obj.id,
                UserOrgPermissionOverride.key == upd.key,
            )
        )
        existing = res.scalar_one_or_none()
        if existing:
            existing.granted = upd.granted
        else:
            db.add(UserOrgPermissionOverride(
                user_org_access_id=uoa_obj.id,
                key=upd.key,
                granted=upd.granted,
            ))
    await db.commit()
    return {"status": "ok", "updated": len(updates)}


@router.get("/users/{user_id}/org-roles")
async def get_user_org_roles(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_tab("staff")),
):
    """Return per-org role (uoa.role) for each org the user is attached to."""
    rows = (await db.execute(
        select(UserOrgAccess).where(UserOrgAccess.user_id == user_id)
    )).scalars().all()
    return [{"org_id": r.org_id, "role": r.role} for r in rows]


@router.patch("/users/{user_id}/role")
async def update_user_org_role(
    user_id: int,
    body: RoleUpdate,
    org_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("staff")),
):
    """Change user_org_access.role for a single (user, org) pair.

    D-09: superadmin is never assignable via API.
    D-05.2: self-lockout — cannot demote self to a role lacking admin.roles/staff.
    """
    # D-09: only the 5 visible roles are allowed (no superadmin)
    if body.role not in ("account_owner", "admin", "org_admin", "manager", "employee"):
        raise HTTPException(400, "Недопустимая роль")

    # D-05.2: self-lockout — cannot demote self below admin-level in own org
    if user_id == current_user.id:
        res = await db.execute(
            select(RolePermission.key).where(
                RolePermission.role_name == body.role,
                RolePermission.granted == True,  # noqa: E712
            )
        )
        new_role_keys = {r for r, in res.all()}
        if "admin.roles" not in new_role_keys or "staff" not in new_role_keys:
            raise HTTPException(
                403,
                "Нельзя понизить себе роль в этой организации (самоблокировка)",
            )

    uoa = (await db.execute(
        select(UserOrgAccess).where(
            UserOrgAccess.user_id == user_id,
            UserOrgAccess.org_id == org_id,
        )
    )).scalar_one_or_none()
    if uoa is None:
        raise HTTPException(404, "Пользователь не привязан к организации")

    uoa.role = body.role
    await db.commit()
    return {"status": "ok", "role": body.role}


@router.delete("/users/{user_id}/overrides/{key}")
async def delete_override(
    user_id: int,
    key: str,
    org_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_tab("staff")),
):
    """Remove an override — effective reverts to role-default."""
    uoa = await db.execute(
        select(UserOrgAccess).where(
            UserOrgAccess.user_id == user_id,
            UserOrgAccess.org_id == org_id,
        )
    )
    uoa_obj = uoa.scalar_one_or_none()
    if uoa_obj is None:
        raise HTTPException(404, "Пользователь не привязан к организации")
    await db.execute(
        delete(UserOrgPermissionOverride).where(
            UserOrgPermissionOverride.user_org_access_id == uoa_obj.id,
            UserOrgPermissionOverride.key == key,
        )
    )
    await db.commit()
    return {"status": "ok"}
