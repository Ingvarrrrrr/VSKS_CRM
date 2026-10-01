"""Общий источник «кто вообще может иметь такое-то org/subsidy action-право» —
пул кандидатов + фильтр app.auth.permissions.has_org_key.

Раньше жил только внутри app/routers/plan_excess.py как
_authorized_plan_excess_approvers, зашитый под единственный ключ
'plan_excess.decide'. Вынесено сюда (ПРАВИЛО №6 — один источник истины для
«кто может X»), чтобы верхний согласующий заявки (app/routers/wish_approvals.py,
право 'subsidy.edit') считался ТЕМ ЖЕ способом, а не вторым отдельным расчётом.
plan_excess.py теперь тоже вызывает эту функцию (см. её докстринг там).
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import has_org_key, _ROLE_PRIORITY
from app.auth.visibility import compute_account_contour_org_ids
from app.models.user import User
from app.models.user_organization import UserOrganization
from app.models.user_org_access import UserOrgAccess
from app.models.user_subsidy_access import UserSubsidyAccess
from app.models.organization import Organization

_ACCOUNT_LEVEL_ROLES = ("admin", "account_owner")


async def list_users_with_org_key(
    db: AsyncSession,
    org_id: int,
    action_key: str,
    subsidy_id: int | None = None,
    exclude_user_id: int | None = None,
) -> list[User]:
    """Пользователи, у которых эффективно есть action-право action_key в
    организации org_id (усиленное персональным грантом на subsidy_id, если он
    задан) — та же проверка, что применяется в гейте на запись (has_org_key),
    не второй расчёт.

    Кандидаты собираются из источников (кто ВООБЩЕ может иметь право):
    членство в организации (UserOrganization), явная орг-роль (UserOrgAccess),
    персональный грант на субсидию (UserSubsidyAccess, если subsidy_id задан)
    и владелец организации (Organization.owner_user_id) — has_org_key
    пропускает account_owner/superadmin без проверки членства, поэтому
    владелец организации не всегда состоит в ней участником (см. баг
    «АНО ЦЕНТРПОИСК», 2026-09-02, зафиксирован в test_plan_excess_approvers.py).

    Сознательно НЕ добавляет: всех account_owner огулом (раскрыло бы владельцев
    ЧУЖИХ SaaS-аккаунтов как кандидатов в чужой организации) и superadmin
    (техническая роль поддержки, не сотрудник клиента).

    Дочерние орги (созданные из контрагента субсидии, org_dedup.py) имеют
    root_org_id на корневую, но owner_user_id=NULL — владелец записан только
    у корневой орги. Поэтому владельца и admin/account_owner аккаунта ищем не
    только по org_id, а по всему контуру аккаунта
    (app.auth.visibility.compute_account_contour_org_ids — тот же канонический
    расчёт, что в jwt.get_current_user), иначе владелец/админ дочерней
    организации не попадает в кандидаты (баг Цыганов/Маркадеева, 2026-10-01).
    """
    candidate_ids: set[int] = set()
    stmts = [
        select(UserOrganization.user_id).where(UserOrganization.org_id == org_id),
        select(UserOrgAccess.user_id).where(UserOrgAccess.org_id == org_id),
        select(User.id).where(User.org_id == org_id),
    ]
    if subsidy_id is not None:
        stmts.append(
            select(UserSubsidyAccess.user_id).where(UserSubsidyAccess.subsidy_id == subsidy_id)
        )
    for stmt in stmts:
        candidate_ids.update((await db.execute(stmt)).scalars().all())

    owner_id = (await db.execute(
        select(Organization.owner_user_id).where(Organization.id == org_id)
    )).scalar_one_or_none()
    if owner_id is not None:
        candidate_ids.add(owner_id)

    contour_org_ids = await compute_account_contour_org_ids(db, org_id)
    if contour_org_ids:
        owner_ids_in_contour = (await db.execute(
            select(Organization.owner_user_id).where(
                Organization.id.in_(contour_org_ids),
                Organization.owner_user_id.isnot(None),
            )
        )).scalars().all()
        candidate_ids.update(owner_ids_in_contour)

        account_level_ids = (await db.execute(
            select(User.id).where(
                User.org_id.in_(contour_org_ids),
                User.role.in_(_ACCOUNT_LEVEL_ROLES),
            )
        )).scalars().all()
        candidate_ids.update(account_level_ids)

        account_level_uoa_ids = (await db.execute(
            select(UserOrgAccess.user_id).where(
                UserOrgAccess.org_id.in_(contour_org_ids),
                UserOrgAccess.role.in_(_ACCOUNT_LEVEL_ROLES),
            )
        )).scalars().all()
        candidate_ids.update(account_level_uoa_ids)

    if exclude_user_id is not None:
        candidate_ids.discard(exclude_user_id)
    if not candidate_ids:
        return []

    users = (await db.execute(select(User).where(User.id.in_(candidate_ids)))).scalars().all()
    authorized: list[User] = []
    for u in users:
        if await has_org_key(u, db, org_id, action_key, subsidy_id=subsidy_id):
            authorized.append(u)

    def _sort_key(u: User):
        prio = _ROLE_PRIORITY.get(u.role or "", 0)
        name = (u.full_name or u.username or "").lower()
        return (-prio, name)

    authorized.sort(key=_sort_key)
    return authorized
