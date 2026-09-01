"""Phase 17: effective permission resolution + Depends factories.

Boolean-flip model (D-02): effective = overrides.get(key, role_permissions[role][key])
Superadmin bypass (D-05.3): always True, no DB queries.
Per-org (D-08): FK via user_org_access.id.
Per-subsidy (D-09): FK via user_subsidy_access.id.
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


# B4 (2026-09-01): экшен-ключи, которые ОПАСНО вливать из пер-субсидийного
# гранта (user_subsidy_access) в ГЛОБАЛЬНЫЙ набор прав пользователя. Грант на
# ОДНУ субсидию не должен превращаться во власть над write-действиями во ВСЕХ
# организациях — раньше именно так и было: _subsidy_grant_keys() возвращал
# ключ, а _has_key_in_any_org()/require_action() пропускали пользователя
# в любой орге, где этот ключ вообще существовал в матрице.
# Точечная проверка "есть грант ИМЕННО на эту субсидию" остаётся рабочей —
# см. has_org_key(..., subsidy_id=...) и get_subsidy_effective(), они читают
# грант напрямую и НЕ используют эту константу.
# ВАЖНО: здесь только action-ключи (глаголы: .edit/.manage/.delete/.register).
# Ключи-ВКЛАДКИ (feo_categories, subsidies, wishes, purchases, ...) сюда
# добавлять НЕЛЬЗЯ — вкладка это ВИДИМОСТЬ, грант на субсидию обязан
# по-прежнему открывать пользователю нужные разделы меню и данные,
# иначе мы отбираем чтение вместо того, чтобы резать запись.
SUBSIDY_GRANT_NON_GLOBAL = {
    "feo_category.edit",
    "subsidy.edit",
    "user.manage",
    "contract.delete",
    "payment.register",
}


_ROLE_PRIORITY = {
    "superadmin": 6,
    "account_owner": 5,
    "admin": 4,
    "org_admin": 3,
    "manager": 2,
    "employee": 1,
}


async def _get_effective_simple(user: User, db: AsyncSession, org_id: Optional[int], include_subsidy_grants: bool = True) -> set:
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
    # Модель A: UOA-роль — самодостаточный источник полномочий по орг, членство
    # (user_organizations) НЕ требуется. Полномочия ≠ трудоустройство.

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

    # Step 0b (N-10 fallback ONLY): если у пользователя вовсе нет глобальной
    # роли (user.role NULL) и нет UOA для этой орги — берём лучшую per-org роль.
    # Cross-org elevation при НАЛИЧИИ глобальной роли убран (Wave 3): орг-роль
    # даёт власть только в своей орге; в чужих оргах действует глобальная роль.
    # Гейты вкладок/действий компенсируют это перебором орг (см. require_tab).
    if not effective_role:
        _uoa_role_rows = (await db.execute(
            select(UserOrgAccess.org_id, UserOrgAccess.role).where(
                UserOrgAccess.user_id == user.id,
                UserOrgAccess.role.isnot(None),
            )
        )).all()
        all_uoa_rows = [r for (oid, r) in _uoa_role_rows if oid]
        if all_uoa_rows:
            effective_role = max(all_uoa_rows, key=lambda r: _ROLE_PRIORITY.get(r, 0))

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

    # Step 2b: union per-subsidy grant keys (поглощение по выданным субсидиям).
    # Применяется ДО потолка employee, чтобы admin.* из гранта тоже срезался.
    # include_subsidy_grants=False — для ОРГ-УРОВНЕВОГО гейтинга данных по вкладке
    # (get_tab_scoped_org_ids / org-default субсидий): субсидия-грант даёт доступ к
    # ДАННЫМ субсидии, а не к данным всей орг по вкладке, и не должен перекрывать
    # орг-override (revoke вкладки для орг). Per-субсидийный scope считается отдельно.
    if include_subsidy_grants:
        # B4: вычитаем SUBSIDY_GRANT_NON_GLOBAL — не даём точечному гранту на
        # ОДНУ субсидию превращаться в ГЛОБАЛЬНОЕ право (все орги). Точечная
        # проверка по subsidy_id (has_org_key) эту константу не трогает.
        effective |= (await _subsidy_grant_keys(user.id, db)) - SUBSIDY_GRANT_NON_GLOBAL

    # Жёсткий потолок: genuine employee (роль не повышена членским UOA) НЕ может
    # получить орг-админ вкладки admin.* (billing/roles/settings) даже через
    # персональные галки «Доступ». Требование: сотрудник = строго свой scope.
    if effective_role == 'employee':
        effective = {k for k in effective if not k.startswith('admin.')}

    return effective


async def _subsidy_grant_keys(user_id: int, db: AsyncSession) -> set:
    """UNION эффективных ключей по всем субсидия-грантам пользователя.
    Для каждого user_subsidy_access: base = role matrix грантовой роли,
    затем применяются user_subsidy_permission_overrides (grant→add, revoke→discard)."""
    from app.models.user_subsidy_access import UserSubsidyAccess, UserSubsidyPermissionOverride
    grants = (await db.execute(
        select(UserSubsidyAccess.id, UserSubsidyAccess.role).where(
            UserSubsidyAccess.user_id == user_id
        )
    )).all()
    if not grants:
        return set()
    keys: set = set()
    for (usa_id, grole) in grants:
        rp = (await db.execute(
            select(RolePermission.key).where(
                RolePermission.role_name == (grole or "employee"),
                RolePermission.granted == True,  # noqa: E712
            )
        )).scalars().all()
        eff = set(rp)
        ov = (await db.execute(
            select(UserSubsidyPermissionOverride.key, UserSubsidyPermissionOverride.granted).where(
                UserSubsidyPermissionOverride.user_subsidy_access_id == usa_id
            )
        )).all()
        for (k, g) in ov:
            if g:
                eff.add(k)
            else:
                eff.discard(k)
        keys |= eff
    return keys


async def get_subsidy_effective(user_id: int, subsidy_id: int, db: AsyncSession) -> Optional[set]:
    """Эффективный набор ключей (листы+действия) для одной субсидии-гранта.
    None если у пользователя нет гранта на эту субсидию."""
    from app.models.user_subsidy_access import UserSubsidyAccess, UserSubsidyPermissionOverride
    grant = (await db.execute(
        select(UserSubsidyAccess).where(
            UserSubsidyAccess.user_id == user_id,
            UserSubsidyAccess.subsidy_id == subsidy_id,
        )
    )).scalar_one_or_none()
    if grant is None:
        return None
    rp = (await db.execute(
        select(RolePermission.key).where(
            RolePermission.role_name == (grant.role or "employee"),
            RolePermission.granted == True,  # noqa: E712
        )
    )).scalars().all()
    eff = set(rp)
    ov = (await db.execute(
        select(UserSubsidyPermissionOverride.key, UserSubsidyPermissionOverride.granted).where(
            UserSubsidyPermissionOverride.user_subsidy_access_id == grant.id
        )
    )).all()
    for (k, g) in ov:
        if g:
            eff.add(k)
        else:
            eff.discard(k)
    return eff


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


async def _has_key_in_any_org(user: User, db: AsyncSession, key: str) -> bool:
    """Гейт-проверка: ключ есть в эффективных правах хотя бы одной доступной орги
    (активная + все UOA-орги). Пер-орг роль без cross-org elevation (Wave 3) —
    поэтому гейт перебирает орги, а данные скоупятся per-org в эндпоинтах."""
    candidates: list = []
    active = _active_org(user)
    if active:
        candidates.append(active)
    for oid in (getattr(user, "_uoa_org_ids", None) or []):
        if oid not in candidates:
            candidates.append(oid)
    if not candidates:
        candidates = [None]
    for oid in candidates:
        if key in await _get_effective(user, db, oid):
            return True
    return False


async def has_org_key(
    user: User, db: AsyncSession, org_id: Optional[int], key: str,
    subsidy_id: Optional[int] = None,
) -> bool:
    """Орг-осознанная проверка права для КОНКРЕТНОЙ орги операции (Wave 3).

    Орг-роль даёт власть только в своей орге: ключ должен быть эффективен именно
    для org_id (UOA-роль этой орги или глобальная роль + орг-overrides).

    Решение 2026-07-06: write-права НЕ наследуются по иерархии «ставлю задачи»
    (в отличие от видимости/вкладок в _get_effective) — иерархическое поглощение
    даёт только read. Менять можно лишь там, где есть собственная роль или
    персональный грант на конкретную субсидию (subsidy_id)."""
    if user.role in ("superadmin", "account_owner"):
        return True
    if key in await _get_effective_simple(user, db, org_id, include_subsidy_grants=False):
        return True
    if subsidy_id is not None:
        sub_eff = await get_subsidy_effective(user.id, subsidy_id, db)
        if sub_eff and key in sub_eff:
            return True
    return False


def require_tab(tab_key: str):
    """FastAPI Depends factory. 403 if tab_key not in effective; bypass superadmin."""
    async def checker(
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ):
        if user.role == "superadmin":
            return user
        if not await _has_key_in_any_org(user, db, tab_key):
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
        if not await _has_key_in_any_org(user, db, action_key):
            raise HTTPException(status_code=403, detail="Действие запрещено")
        return user

    return checker


async def can_manage_purchase(user, purchase, db) -> bool:
    """27.4-09: True если user имеет право управлять данной закупкой.

    Правила:
    - superadmin → всегда
    - Любой user → если он автор авансового отчёта (purchase_method='advance' AND reimbursement_user_id == user.id)
    - admin/org_admin/manager/account_owner → если tab 'purchases' есть хоть в одной орге (any-org, как у bulk-delete)
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
    # Manager+ с tab 'purchases' — any-org, как в require_tab('purchases') у bulk-delete.
    # Иначе per-row удаление давало 403, когда активная орга не совпадает
    # с оргой, где у пользователя есть 'purchases' (bulk при этом работал).
    if user.role in ('admin', 'org_admin', 'manager', 'account_owner'):
        if await _has_key_in_any_org(user, db, 'purchases'):
            return True
    return False
