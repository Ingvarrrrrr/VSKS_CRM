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
from app.models.user_subsidy_access import UserSubsidyAccess, UserSubsidyPermissionOverride
from app.models.subsidy import Subsidy
from app.models.user_organization import UserOrganization
from app.models.permission import (
    PermissionTab, PermissionAction, RolePermission, UserOrgPermissionOverride,
)
from app.auth.jwt import get_current_user
from app.auth.permissions import (
    require_tab, ensure_user_org_access,
    assert_can_manage_user_access, get_user_rank, ROLE_LABELS_RU, _ROLE_PRIORITY,
)
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

    # Владелец 2026-09-02: эскалация через матрицу — org_admin мог сам себе
    # (или роли выше) добавить допуск, правя дефолты роли, а не только свои
    # персональные overrides. Правило то же: править дефолты роли можно
    # только СТРОГО ниже своей — своя роль и роли выше недоступны никому,
    # кроме superadmin.
    if current_user.role != "superadmin":
        actor_rank = await get_user_rank(current_user, db, None)
        target_rank = _ROLE_PRIORITY.get(role_name, 0)
        if actor_rank <= target_rank:
            role_label = ROLE_LABELS_RU.get(role_name, role_name)
            raise HTTPException(
                403,
                f"Недостаточно прав: менять набор допусков по умолчанию для роли "
                f"«{role_label}» может только хозяин аккаунта (владелец) или "
                "суперадмин — эта роль равна вашей или выше.",
            )

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


async def _apply_overrides_for_org(
    user_id: int, org_id: int, updates: List[PermissionUpdate], db: AsyncSession
) -> None:
    """Upsert overrides for one (user, org) pair. Self-heals UOA from membership
    if missing (superadmin's own contour org, added via all_orgs_access fan-out,
    might not have a membership row — in that case ensure_user_org_access creates
    the UOA directly, no user_organizations required, Модель A)."""
    uoa = await db.execute(
        select(UserOrgAccess).where(
            UserOrgAccess.user_id == user_id,
            UserOrgAccess.org_id == org_id,
        )
    )
    uoa_obj = uoa.scalar_one_or_none()
    if uoa_obj is None:
        user_obj = await db.get(User, user_id)
        role = user_obj.role if user_obj else None
        uoa_id = await ensure_user_org_access(user_id, org_id, role, db)
        uoa_obj = await db.get(UserOrgAccess, uoa_id)

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


@router.put("/users/{user_id}/overrides")
async def update_overrides(
    user_id: int,
    updates: List[PermissionUpdate],
    org_id: int = Query(...),
    apply_to_all: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("staff")),
):
    # Владелец 2026-09-02: эскалация — правил и запрещал себе допуски кто угодно
    # со вкладкой staff. Никто не правит свои допуски; настраивать чужие можно
    # только строго сверху вниз по лестнице ролей.
    await assert_can_manage_user_access(current_user, user_id, db, org_id)

    # D-05.2 self-lockout on own user (легаси-проверка более узкого случая —
    # теперь недостижима для не-superadmin: строка выше уже блокирует ЛЮБУЮ
    # правку собственных допуски. Оставлена как есть по требованию не ломать.)
    if user_id == current_user.id:
        for upd in updates:
            if upd.key in SELF_LOCKOUT_PROTECTED_KEYS and not upd.granted:
                raise HTTPException(
                    403,
                    f"Нельзя снять доступ к '{upd.key}' у себя (самоблокировка)",
                )

    # Явную org_id (текущий выбор в UI) сначала self-heal'им через членство,
    # как раньше: org_id из селектора обязан быть реальной оргой пользователя,
    # а не просто любой оргой контура — иначе опечатка в query param молча
    # создала бы UOA в чужой для юзера орге.
    uoa = await db.execute(
        select(UserOrgAccess).where(
            UserOrgAccess.user_id == user_id,
            UserOrgAccess.org_id == org_id,
        )
    )
    if uoa.scalar_one_or_none() is None:
        membership = (await db.execute(
            select(UserOrganization).where(
                UserOrganization.user_id == user_id,
                UserOrganization.org_id == org_id,
            )
        )).scalar_one_or_none()
        if membership is None:
            raise HTTPException(
                404,
                f"Пользователь не состоит в организации id={org_id} — "
                "сначала добавьте его в организацию",
            )

    await _apply_overrides_for_org(user_id, org_id, updates, db)

    # Владелец 2026-09-01, п.4, ЗАТЕМ уточнено владельцем 2026-09-02:
    # изначально («должна быть настройка прав по всем организациям сразу,
    # если есть доступ ко всем организациям») это било веером по всем
    # организациям охвата ЦЕЛЕВОГО пользователя автоматически, всегда, как
    # только у него включён all_orgs_access. Владелец уточнил 2026-09-02:
    # «нужно чтобы при доступе ко всем организациям были разные настройки
    # именно для всех организаций» — то есть автоматический веер делал
    # именно то, что запрещал сам запрос: разные организации настроить
    # по-разному было невозможно. Это НЕ отмена требования от 1 сентября,
    # а явное включение — массовое применение остаётся доступным, но по
    # запросу (apply_to_all=true), а не как побочный эффект наличия
    # all_orgs_access у пользователя. По умолчанию правка задевает только
    # org_id из селектора, даже если у пользователя включён охват.
    # Роль при этом не трогаем (fan-out идёт только по overrides).
    applied_org_ids = [org_id]
    if apply_to_all:
        target_user = await db.get(User, user_id)
        if target_user is not None and getattr(target_user, 'all_orgs_access', False):
            from app.auth.visibility import get_all_orgs_access_org_ids
            scope_org_ids = await get_all_orgs_access_org_ids(target_user, db)
            for oid in scope_org_ids:
                if oid == org_id:
                    continue
                await _apply_overrides_for_org(user_id, oid, updates, db)
                applied_org_ids.append(oid)

    await db.commit()
    return {"status": "ok", "updated": len(updates), "applied_org_ids": applied_org_ids}


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

    # Владелец 2026-09-02, п.3: главный путь эскалации — org_admin назначал
    # СЕБЕ (или кому угодно) роль account_owner через этот эндпоинт. Роль
    # «Хозяин аккаунта» вправе выдавать только superadmin или действующий
    # account_owner.
    if body.role == "account_owner" and current_user.role not in ("superadmin", "account_owner"):
        raise HTTPException(
            403,
            "Роль «Хозяин аккаунта» может назначить только суперадмин или "
            "действующий хозяин аккаунта.",
        )

    # Владелец 2026-09-02, п.1-2: никто не правит свою роль (в обе стороны —
    # раньше блокировалось только понижение), настраивать чужую роль можно
    # только строго сверху вниз по лестнице ролей.
    await assert_can_manage_user_access(current_user, user_id, db, org_id)

    # D-05.2: self-lockout — cannot demote self below admin-level in own org
    # (легаси-проверка более узкого случая — теперь недостижима для
    # не-superadmin: строка выше уже блокирует ЛЮБУЮ правку своей роли.
    # Оставлена как есть по требованию не ломать существующую защиту.)
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

    # Модель A: ensure_user_org_access идемпотентно создаёт/обновляет UOA-роль —
    # самодостаточный источник полномочий. Членство (user_organizations) НЕ требуется
    # и НЕ создаётся: полномочия ≠ трудоустройство. Нет 404 «сначала добавьте
    # в организацию» — org_admin назначается сразу, видимость даёт сама UOA-роль.
    await ensure_user_org_access(user_id, org_id, body.role, db)
    await db.commit()
    return {"status": "ok", "role": body.role}


@router.delete("/users/{user_id}/overrides/{key}")
async def delete_override(
    user_id: int,
    key: str,
    org_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("staff")),
):
    """Remove an override — effective reverts to role-default."""
    await assert_can_manage_user_access(current_user, user_id, db, org_id)
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


# --- Per-user subsidy access ---

@router.get("/users/{user_id}/subsidy-access")
async def get_user_subsidy_access(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_tab("staff")),
):
    rows = (await db.execute(
        select(UserSubsidyAccess.subsidy_id, UserSubsidyAccess.role, Subsidy.name)
        .join(Subsidy, Subsidy.id == UserSubsidyAccess.subsidy_id)
        .where(UserSubsidyAccess.user_id == user_id)
    )).all()
    return [{"subsidy_id": sid, "role": role, "subsidy_name": name} for (sid, role, name) in rows]


@router.put("/users/{user_id}/subsidy-access")
async def upsert_user_subsidy_access(
    user_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("staff")),
):
    await assert_can_manage_user_access(current_user, user_id, db, None)
    subsidy_id = body.get("subsidy_id")
    role = body.get("role") or "employee"
    if not subsidy_id:
        raise HTTPException(400, "subsidy_id обязателен")
    if role not in ("org_admin", "manager", "employee"):
        raise HTTPException(400, f"Недопустимая роль: {role}")
    existing = (await db.execute(
        select(UserSubsidyAccess).where(
            UserSubsidyAccess.user_id == user_id,
            UserSubsidyAccess.subsidy_id == subsidy_id,
        )
    )).scalar_one_or_none()
    if existing:
        existing.role = role
    else:
        db.add(UserSubsidyAccess(user_id=user_id, subsidy_id=subsidy_id, role=role))
    await db.commit()
    return {"status": "ok"}


@router.delete("/users/{user_id}/subsidy-access/{subsidy_id}")
async def delete_user_subsidy_access(
    user_id: int,
    subsidy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("staff")),
):
    await assert_can_manage_user_access(current_user, user_id, db, None)
    row = (await db.execute(
        select(UserSubsidyAccess).where(
            UserSubsidyAccess.user_id == user_id,
            UserSubsidyAccess.subsidy_id == subsidy_id,
        )
    )).scalar_one_or_none()
    if row:
        await db.delete(row)
        await db.commit()
    return {"status": "ok"}


# --- Per-subsidy permission overrides (зеркало орг-оверрайдов) ---

@router.get("/users/{user_id}/subsidy-access/{subsidy_id}/overrides", response_model=List[OverrideOut])
async def list_subsidy_overrides(
    user_id: int,
    subsidy_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_tab("staff")),
):
    grant = (await db.execute(
        select(UserSubsidyAccess).where(
            UserSubsidyAccess.user_id == user_id,
            UserSubsidyAccess.subsidy_id == subsidy_id,
        )
    )).scalar_one_or_none()
    if grant is None:
        return []
    rows = (await db.execute(
        select(UserSubsidyPermissionOverride).where(
            UserSubsidyPermissionOverride.user_subsidy_access_id == grant.id
        )
    )).scalars().all()
    return rows


@router.put("/users/{user_id}/subsidy-access/{subsidy_id}/overrides")
async def update_subsidy_overrides(
    user_id: int,
    subsidy_id: int,
    updates: List[PermissionUpdate],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("staff")),
):
    await assert_can_manage_user_access(current_user, user_id, db, None)
    grant = (await db.execute(
        select(UserSubsidyAccess).where(
            UserSubsidyAccess.user_id == user_id,
            UserSubsidyAccess.subsidy_id == subsidy_id,
        )
    )).scalar_one_or_none()
    if grant is None:
        raise HTTPException(404, "Сначала выдайте пользователю доступ к этой субсидии")
    for upd in updates:
        existing = (await db.execute(
            select(UserSubsidyPermissionOverride).where(
                UserSubsidyPermissionOverride.user_subsidy_access_id == grant.id,
                UserSubsidyPermissionOverride.key == upd.key,
            )
        )).scalar_one_or_none()
        if existing:
            existing.granted = upd.granted
        else:
            db.add(UserSubsidyPermissionOverride(
                user_subsidy_access_id=grant.id,
                key=upd.key,
                granted=upd.granted,
            ))
    await db.commit()
    return {"status": "ok", "updated": len(updates)}


@router.delete("/users/{user_id}/subsidy-access/{subsidy_id}/overrides/{key}")
async def delete_subsidy_override(
    user_id: int,
    subsidy_id: int,
    key: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("staff")),
):
    await assert_can_manage_user_access(current_user, user_id, db, None)
    grant = (await db.execute(
        select(UserSubsidyAccess).where(
            UserSubsidyAccess.user_id == user_id,
            UserSubsidyAccess.subsidy_id == subsidy_id,
        )
    )).scalar_one_or_none()
    if grant is None:
        raise HTTPException(404, "Грант не найден")
    await db.execute(
        delete(UserSubsidyPermissionOverride).where(
            UserSubsidyPermissionOverride.user_subsidy_access_id == grant.id,
            UserSubsidyPermissionOverride.key == key,
        )
    )
    await db.commit()
    return {"status": "ok"}


