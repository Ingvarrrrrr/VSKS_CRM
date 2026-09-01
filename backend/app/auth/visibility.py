"""Phase 28, Step 1: Cross-entity visibility layer.

Implements unified document visibility rules for purchases, contracts,
tasks, and wishes. Not wired to any endpoint yet (Step 4-6 will do that).

Design
------
- get_visible_user_ids  — frontier-loop (fix-point, ≤5 iter) over UserHierarchy
                          + dept heads + managed orgs + UOA org_admin/manager.
                          Returns None for SaaS roles (superadmin / account_owner).
- get_view_all_org_ids  — set of org_ids where user has 'documents.view_all_in_org'
                          effective action. Safe before migration: missing key → empty set.
- build_visibility_clause — main entry point. Returns or_() SQLAlchemy clause or None.

Public API (3 async functions):
  get_visible_user_ids(user, db) -> Optional[set[int]]
  get_view_all_org_ids(user, db) -> set[int]
  build_visibility_clause(user, db, doc_type: str) -> clause | None

doc_type ∈ {'purchase', 'contract', 'task', 'wish'}.
"""
import logging
from typing import Optional

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.purchase import Purchase
from app.models.contract import Contract
from app.models.task import Task, TaskAssignee
from app.models.task_comment import TaskComment
from app.models.wish import Wish
from app.models.purchase_event import PurchaseMember
from app.models.chat_room import ChatRoom, ChatParticipant
from app.models.subsidy import Subsidy
from app.models.department import Department
from app.models.user_organization import UserOrganization
from app.models.manager_department import ManagerDepartment
from app.models.manager_organization import ManagerOrganization
from app.models.user_org_access import UserOrgAccess

logger = logging.getLogger(__name__)

# SaaS-level roles that bypass all user-level filters
_SAAS_ROLES = frozenset({"superadmin", "account_owner"})

# Maximum iterations for the frontier fix-point loop
_MAX_FRONTIER_ITER = 5


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def get_visible_user_ids(user: User, db: AsyncSession) -> Optional[set[int]]:
    """Возвращает set user_id'ов чьи документы видит current_user, или None для SaaS.

    Реализует правила 1, 2, 4 из плана через frontier-loop с фикс-точкой
    (≤5 итераций). На каждой итерации добавляет subordinates (UserHierarchy),
    members отделов где frontier-юзеры head_user_id, и членов orgs где
    они managed/UOA org_admin/manager. Останавливается когда frontier пуст.

    SaaS-роли ('superadmin', 'account_owner') — return None (без фильтра).
    """
    if user.role in _SAAS_ROLES:
        return None

    from app.routers.user_hierarchy import get_all_subordinate_ids

    visible: set[int] = {user.id}
    frontier: set[int] = {user.id}

    for _iter in range(_MAX_FRONTIER_ITER):
        if not frontier:
            break

        new_ids: set[int] = set()

        # Rule 1: recursive subordinates via UserHierarchy (CTE per frontier member)
        for uid in frontier:
            sub_ids = await get_all_subordinate_ids(uid, db)
            new_ids.update(sub_ids)

        # Rule 2a: department head — include all members of headed depts
        headed_dept_res = await db.execute(
            select(Department.id).where(Department.head_user_id.in_(frontier))
        )
        headed_dept_ids = [r[0] for r in headed_dept_res.all()]
        if headed_dept_ids:
            dm_res = await db.execute(
                select(UserOrganization.user_id).where(
                    UserOrganization.dept_id.in_(headed_dept_ids)
                )
            )
            new_ids.update(r[0] for r in dm_res.all())

        # Rule 2b: managed departments (ManagerDepartment explicit assignment)
        md_res = await db.execute(
            select(ManagerDepartment.dept_id).where(
                ManagerDepartment.manager_user_id.in_(frontier)
            )
        )
        managed_dept_ids = [r[0] for r in md_res.all()]
        if managed_dept_ids:
            dm2_res = await db.execute(
                select(UserOrganization.user_id).where(
                    UserOrganization.dept_id.in_(managed_dept_ids)
                )
            )
            new_ids.update(r[0] for r in dm2_res.all())

        # Rule 4a: managed organizations (ManagerOrganization table)
        mo_res = await db.execute(
            select(ManagerOrganization.org_id).where(
                ManagerOrganization.manager_user_id.in_(frontier)
            )
        )
        managed_org_ids = [r[0] for r in mo_res.all()]
        if managed_org_ids:
            org_user_q = select(User.id).where(User.org_id.in_(managed_org_ids))
            # D-09: hide superadmin from non-superadmin callers
            if user.role != "superadmin":
                org_user_q = org_user_q.where(User.role != "superadmin")
            org_users = await db.execute(org_user_q)
            new_ids.update(r[0] for r in org_users.all())

        # Rule 4b: per-org role org_admin/manager via UserOrgAccess
        uoa_res = await db.execute(
            select(UserOrgAccess.org_id).where(
                UserOrgAccess.user_id.in_(frontier),
                UserOrgAccess.role.in_(["org_admin", "manager"]),
            )
        )
        uoa_org_ids = [r[0] for r in uoa_res.all()]
        if uoa_org_ids:
            uoa_members_res = await db.execute(
                select(User.id).where(
                    User.org_id.in_(uoa_org_ids),
                    User.role != "superadmin",
                )
            )
            new_ids.update(r[0] for r in uoa_members_res.all())

        # Compute what is genuinely new to avoid infinite loops
        frontier = new_ids - visible
        visible.update(new_ids)

    if not visible or visible == {user.id}:
        logger.warning(
            "get_visible_user_ids: user %s (role=%s) resolved to only self — "
            "no hierarchy/dept/org assignments found",
            user.id,
            user.role,
        )

    # Phase 26-AA: «поглощение» — если в подчинённых есть account_owner, наследуем
    # SaaS-видимость (None = без фильтра). Бизнес-правило: «ты ставишь задачи
    # account_owner'у → ты видишь то же что и он».
    # superadmin намеренно исключён из этой проверки: он невидим для не-суперадминов,
    # поэтому подчинённый-суперадмин не должен давать вызывающему SaaS-видимость.
    if visible - {user.id}:
        saas_check = await db.execute(
            select(User.id).where(
                User.id.in_(visible - {user.id}),
                User.role == "account_owner",
            )
        )
        if saas_check.first() is not None:
            return None  # bypass фильтра — наследовал SaaS от account_owner

    return visible


async def compute_account_contour_org_ids(db: AsyncSession, org_id: Optional[int]) -> set[int]:
    """КАНОНИЧЕСКИЙ расчёт контура аккаунта: root_org_id-дерево ∪ owner_user_id-связь.

    Единственная реализация алгоритма — используется и в jwt.get_current_user
    (кэш _contour_org_ids на логине, а также all_orgs_access), и здесь как
    fallback. НЕ путать с billing._contour_org_ids: там контур ПЛАТЕЛЬЩИКА
    (для расчёта тарифа) — namеренно та же owner_user_id-связь, но БЕЗ
    root_org_id-дерева (одному владельцу могут принадлежать несколько
    независимых корневых орг, каждая — свой биллинг-юнит).

    root_org_id-дерево одно даёт неполный контур там, где часть организаций
    аккаунта заведена суперадмином как «standalone» (root_org_id NULL) — так
    исторически появились орг-«сироты» вроде региональных отделений, которые
    структурно относятся к тому же аккаунту, но синтаксически являются
    отдельными «корнями». owner_user_id — второй независимый сигнал
    принадлежности (self-service дочерняя орг от account_owner). Объединяем
    оба через fix-point обход (≤5 итераций, граф маленький): для каждой орг
    во frontier добавляем и root-дерево, и owner_user_id-сиблингов, пока не
    перестанут появляться новые id.
    """
    if not org_id:
        return set()
    from app.models.organization import Organization

    contour: set[int] = set()
    frontier: set[int] = {int(org_id)}

    for _ in range(5):
        if not frontier:
            break
        new_ids: set[int] = set()
        for oid in frontier:
            org = await db.get(Organization, oid)
            if not org:
                continue
            root_id = int(org.root_org_id or org.id)
            new_ids.add(root_id)
            tree_ids = (await db.execute(
                select(Organization.id).where(Organization.root_org_id == root_id)
            )).scalars().all()
            new_ids.update(int(x) for x in tree_ids)
            if org.owner_user_id:
                owner_ids = (await db.execute(
                    select(Organization.id).where(Organization.owner_user_id == org.owner_user_id)
                )).scalars().all()
                new_ids.update(int(x) for x in owner_ids)
        frontier = new_ids - contour
        contour.update(new_ids)

    contour.add(int(org_id))
    return contour


async def get_all_orgs_access_org_ids(
    user: User,
    db: AsyncSession,
    *,
    uoa_org_ids: Optional[set[int]] = None,
    managed_org_ids: Optional[set[int]] = None,
) -> set[int]:
    """Множество org_id, доступных пользователю через users.all_orgs_access.

    Единственная реализация: вызывается и в jwt.get_current_user (кэш
    _all_orgs_access_org_ids на логине — передаёт уже посчитанные
    uoa_org_ids/managed_org_ids, чтобы не дублировать запросы), и в
    permissions.py при массовом применении override сразу на все орг охвата
    (Владелец 2026-09-01, п.4: «должна быть настройка прав по всем
    организациям сразу»). Без флага или для SaaS-ролей — пустое множество.

    anchor-орги (org_id, откуда считаем контур): primary org_id ∪ UOA-орги
    ∪ управляемые орг — те же якоря, что и membership/полномочия пользователя
    (иначе флаг бесполезен для UOA-only сотрудника без users.org_id, Модель A).
    """
    if not getattr(user, 'all_orgs_access', False) or user.role in ('superadmin', 'account_owner'):
        return set()

    if uoa_org_ids is None:
        from app.models.user_org_access import UserOrgAccess
        uoa_rows = (await db.execute(
            select(UserOrgAccess.org_id).where(UserOrgAccess.user_id == user.id)
        )).scalars().all()
        uoa_org_ids = {int(x) for x in uoa_rows if x}
    if managed_org_ids is None:
        from app.models.manager_organization import ManagerOrganization
        mo_rows = (await db.execute(
            select(ManagerOrganization.org_id).where(
                ManagerOrganization.manager_user_id == user.id
            )
        )).scalars().all()
        managed_org_ids = {int(x) for x in mo_rows if x}

    anchor_org_ids: set[int] = set(uoa_org_ids) | set(managed_org_ids)
    if user.org_id:
        anchor_org_ids.add(int(user.org_id))

    all_ids: set[int] = set()
    for anchor in anchor_org_ids:
        all_ids |= await compute_account_contour_org_ids(db, anchor)
    return all_ids


async def get_account_contour_org_ids(user: User, db: AsyncSession) -> set[int]:
    """Орги аккаунта пользователя: корневая орга его primary-орги + все дочерние.

    Wave 3: глобальная роль (user.role) действует на весь аккаунт, поэтому
    контурные орги входят в кандидаты org-scoped гейтинга (эффективная роль в
    каждой = UOA-роль этой орги или глобальная). Использует кэш из
    get_current_user (_contour_org_ids), иначе считает по Organization."""
    cached = getattr(user, "_contour_org_ids", None)
    if cached is not None:
        return {int(x) for x in cached}
    return await compute_account_contour_org_ids(db, user.org_id)


async def get_managed_org_ids(user: User, db: AsyncSession) -> set[int]:
    """Орги, которыми пользователь руководит (ManagerOrganization).

    Принцип: «командуешь оргой → видишь всё, что в ней происходит» (данные,
    персонал, вкладки, субсидии). Подчинённость задаётся управлением, а не деревом
    орг (root_org_id/контур), поэтому орга вне контура аккаунта тоже сюда попадает.
    Использует кэш _managed_org_ids из get_current_user, иначе считает по БД."""
    if user.role in _SAAS_ROLES:
        return set()
    cached = getattr(user, "_managed_org_ids", None)
    if cached is not None:
        return {int(x) for x in cached}
    return {int(x) for x in (await db.execute(
        select(ManagerOrganization.org_id).where(
            ManagerOrganization.manager_user_id == user.id
        )
    )).scalars().all() if x}


async def get_view_all_org_ids(user: User, db: AsyncSession) -> set[int]:
    """set[org_id] где у user есть effective action 'documents.view_all_in_org'.

    Для каждой org из get_org_filter(user) вызывает _get_effective(user, db, org_id)
    и проверяет вхождение 'documents.view_all_in_org' в результат. SaaS-роли
    возвращают пустой set (им clause is None и так не нужен).

    Должно корректно работать ДО применения SQL миграции которая добавит
    action — в этом случае возвращает пустой set (нет такого ключа в эффективных).
    """
    # SaaS roles bypass via None clause — no need to compute org set
    if user.role in _SAAS_ROLES:
        return set()

    from app.auth.jwt import get_org_filter
    from app.auth.permissions import _get_effective_with_inheritance

    ACTION_KEY = "documents.view_all_in_org"

    org_ids = get_org_filter(user)
    if not org_ids:
        return set()

    result: set[int] = set()
    for org_id in org_ids:
        # Phase 26-W: для visibility данных нужен UNION с правами подчинённых.
        # Иначе руководитель не получает action 'documents.view_all_in_org'
        # которая есть у его org_admin-подчинённого → не видит данные org.
        effective = await _get_effective_with_inheritance(user, db, org_id)
        if ACTION_KEY in effective:
            result.add(org_id)

    return result


async def get_role_scoped_org_ids(
    user: User, db: AsyncSession, min_role: str
) -> Optional[list[int]]:
    """Орг, где эффективная роль пользователя >= min_role (по _ROLE_PRIORITY).

    Per-org эффективная роль = user_org_access.role при реальном членстве
    (user_organizations ∪ primary), иначе контурная user.role. Это та же логика,
    что Step 0 в _get_effective_simple, но возвращает множество орг по порогу роли.

    Семантика возврата:
      - None  → фильтр не накладывается (SaaS: superadmin/account_owner видят всё).
      - [..]  → Model.org_id.in_(list).
      - []    → ни одной подходящей орг → данные пусты (.in_([])).
                ВАЖНО: вызывающий эндпоинт НЕ должен схлопывать [] в «всё» —
                различать None и [] через `if org_ids is not None`.

    Используется для орг-админ/менеджер-эксклюзивных вкладок: данные показываем
    только из орг, где роль пользователя соответствует порогу вкладки. Так
    employee, повышенный до org_admin в одной орг, не видит в орг-админ-вкладке
    данные орг, где он рядовой сотрудник.
    """
    if user.role in _SAAS_ROLES:
        return None

    from app.auth.permissions import _ROLE_PRIORITY
    from app.models.user_organization import UserOrganization

    threshold = _ROLE_PRIORITY.get(min_role, 0)

    member: set[int] = {int(x) for x in (await db.execute(
        select(UserOrganization.org_id).where(UserOrganization.user_id == user.id)
    )).scalars().all() if x}
    if user.org_id:
        member.add(int(user.org_id))

    uoa_rows = (await db.execute(
        select(UserOrgAccess.org_id, UserOrgAccess.role).where(
            UserOrgAccess.user_id == user.id,
            UserOrgAccess.role.isnot(None),
        )
    )).all()
    uoa_role_map = {int(oid): r for (oid, r) in uoa_rows if oid is not None}

    # Кандидаты = членство (user_organizations ∪ primary) ∪ орг из user_org_access
    # ∪ контур аккаунта (Wave 3: глобальная роль действует на весь аккаунт).
    # UOA даёт доступ к орг даже без строки в user_organizations (как get_org_filter),
    # поэтому такие орг тоже учитываем — иначе org_admin-через-UOA орг теряются.
    candidates = member | set(uoa_role_map.keys()) | await get_account_contour_org_ids(user, db)
    candidates |= await get_managed_org_ids(user, db)

    result: list[int] = []
    for org_id in candidates:
        role = uoa_role_map.get(org_id) or user.role
        if _ROLE_PRIORITY.get(role, 0) >= threshold:
            result.append(org_id)
    return result


async def get_tab_scoped_org_ids(
    user: User, db: AsyncSession, tab_key: str
) -> Optional[list[int]]:
    """Орги, где у пользователя эффективный таб tab_key включён (True).

    Семантика возврата (ВАЖНО для caller'а — различать None и []):
      - None  → SaaS-роль (superadmin/account_owner): фильтр не накладывать.
      - [..]  → список org_id где таб разрешён → использовать .in_(list).
      - []    → ни одной орги с разрешённым табом → данных быть не должно (.in_([])).

    Кандидаты-орги: membership (user_organizations ∪ primary) ∪ user_org_access,
    как в get_visible_subsidy_ids. Для каждой орги вызывает _get_effective_simple
    и проверяет наличие tab_key в эффективных правах.
    """
    if user.role in _SAAS_ROLES:
        return None

    from app.auth.permissions import _get_effective_simple

    # Кандидаты-орги: те же источники, что в get_visible_subsidy_ids
    # (членство ∪ primary ∪ UOA ∪ контур аккаунта).
    org_ids: set[int] = {int(x) for x in (await db.execute(
        select(UserOrganization.org_id).where(UserOrganization.user_id == user.id)
    )).scalars().all() if x}
    if user.org_id:
        org_ids.add(int(user.org_id))
    org_ids |= {int(x) for x in (await db.execute(
        select(UserOrgAccess.org_id).where(UserOrgAccess.user_id == user.id)
    )).scalars().all() if x}
    org_ids |= await get_account_contour_org_ids(user, db)
    org_ids |= await get_managed_org_ids(user, db)

    result: list[int] = []
    for oid in org_ids:
        eff = await _get_effective_simple(user, db, oid, include_subsidy_grants=False)
        if tab_key in eff:
            result.append(oid)
    return result


async def get_visible_subsidy_ids(
    user: User, db: AsyncSession, tab_key: str = "subsidies"
) -> Optional[set[int]]:
    """Двухуровневая видимость субсидий по вкладке tab_key.

    Орг-уровень: ключ tab_key в эффективных правах юзера для орг X
    (роль + орг-overrides) → по умолчанию видны ВСЕ субсидии орг X.
    Пер-субсидийный override (get_subsidy_effective) перебивает орг-дефолт для
    конкретной субсидии: tab_key∈eff → показать, иначе → скрыть (даже если
    орг-дефолт ON). Субсидии чужих орг видны только при индивидуальном грант-ON.

    tab_key="subsidies" → видимость на странице «Субсидии».
    tab_key="dashboard" → данные субсидии на Дашборде: пер-субсидийная галочка
    «Дашборд» превалирует над орг-дефолтом (напр. ВСКС dashboard=OFF на уровне орг,
    но грант на ДНР с dashboard=ON → ДНР показывается на дашборде).

    None → SaaS (superadmin/account_owner): фильтр не накладывать, видит всё.
    """
    from app.auth.permissions import _get_effective_simple, get_subsidy_effective
    from app.models.subsidy import Subsidy
    from app.models.user_organization import UserOrganization
    from app.models.user_subsidy_access import UserSubsidyAccess

    if user.role in _SAAS_ROLES:
        return None

    # Кандидаты-орг: членство (user_organizations ∪ primary) ∪ user_org_access
    # ∪ контур аккаунта (Wave 3: глобальная роль действует на весь аккаунт —
    # без этого сотрудники корня теряют субсидии, перепривязанные к дочерним оргам).
    org_ids: set[int] = {int(x) for x in (await db.execute(
        select(UserOrganization.org_id).where(UserOrganization.user_id == user.id)
    )).scalars().all() if x}
    if user.org_id:
        org_ids.add(int(user.org_id))
    org_ids |= {int(x) for x in (await db.execute(
        select(UserOrgAccess.org_id).where(UserOrgAccess.user_id == user.id)
    )).scalars().all() if x}
    org_ids |= await get_account_contour_org_ids(user, db)
    # Руководимые орги: видимость субсидий наследуется по управлению, даже если
    # орг вне контура аккаунта. Гейт по эффективной вкладке ниже отсекает лишнее.
    org_ids |= await get_managed_org_ids(user, db)

    visible: set[int] = set()
    # Орг-дефолт: орг с эффективным ключом tab_key → все её субсидии.
    # include_subsidy_grants=False: орг-дефолт = чисто орг-уровень (роль+орг-override);
    # пер-субсидийные гранты учитываются отдельно ниже, иначе грант tab_key по
    # одной субсидии ошибочно открыл бы ВСЕ субсидии орг.
    for oid in org_ids:
        eff = await _get_effective_simple(user, db, oid, include_subsidy_grants=False)
        if tab_key in eff:
            sub_ids = (await db.execute(
                select(Subsidy.id).where(Subsidy.org_id == oid)
            )).scalars().all()
            visible.update(int(s) for s in sub_ids)

    # Пер-субсидийный override перебивает орг-дефолт.
    grant_subs = (await db.execute(
        select(UserSubsidyAccess.subsidy_id).where(UserSubsidyAccess.user_id == user.id)
    )).scalars().all()
    for sid in grant_subs:
        if sid is None:
            continue
        eff = await get_subsidy_effective(user.id, int(sid), db)
        if eff is None:
            continue
        if tab_key in eff:
            visible.add(int(sid))
        else:
            visible.discard(int(sid))

    return visible


async def build_visibility_clause(user: User, db: AsyncSession, doc_type: str):
    """Возвращает SQLAlchemy or_() clause или None.

    None означает «фильтр не нужен» (SaaS-роль).
    Иначе or_() из:
      - Model.org_id.in_(view_all_orgs)  # правило 3
      - Model.<responsible_col>.in_(visible_uids)  # правила 0,1,2,4
      - Model.id.in_(<participation subqueries>)  # правило 5

    doc_type ∈ {'purchase','contract','task','wish'}.

    Конфиг (захардкодить в _DOC_VISIBILITY_CONFIG):
      purchase:
        Model = Purchase
        responsible_col = Purchase.assigned_user_id
        org_id_path = Purchase.subsidy.has(Subsidy.org_id.in_(view_all_orgs))  # ИЛИ через subquery
            — но Purchase напрямую org_id НЕ имеет. Используй subquery:
            Purchase.subsidy_id.in_(select(Subsidy.id).where(Subsidy.org_id.in_(view_all_orgs)))
        participation:
          - Purchase.id.in_(select(PurchaseMember.purchase_id).where(PurchaseMember.user_id == user.id))
          - Purchase.id.in_(
              select(ChatRoom.entity_id)
              .join(ChatParticipant, ChatParticipant.room_id == ChatRoom.id)
              .where(ChatParticipant.user_id == user.id, ChatRoom.entity_type == 'purchase')
            )
          - Purchase.id.in_(
              select(Task.purchase_id)
              .join(TaskAssignee, TaskAssignee.task_id == Task.id)
              .where(TaskAssignee.user_id == user.id, Task.purchase_id.isnot(None))
            )
      task:
        Model = Task
        responsible_col = Task.created_by_id
        org_id check: Task.org_id.in_(view_all_orgs)
        participation:
          - Task.id.in_(select(TaskAssignee.task_id).where(TaskAssignee.user_id == user.id))
          - Task.id.in_(select(ChatRoom.entity_id).join(ChatParticipant ...).where(... entity_type='task'))
          - Task.id.in_(select(TaskComment.task_id).where(TaskComment.user_id == user.id))
      wish:
        Model = Wish
        responsible_col = Wish.created_by
        org_id check: Wish.org_id.in_(view_all_orgs)
        дополнительно: Wish.assigned_to.in_(visible_uids) — assignee тоже видит
        participation: (нет чата у wishes)
      contract:
        Model = Contract
        НЕТ responsible_col — Contract не имеет user-поля
        org_id check: Contract.subsidy_id.in_(select(Subsidy.id).where(Subsidy.org_id.in_(view_all_orgs)))
        видимость через purchases:
          Contract.id.in_(select(Purchase.contract_id).where(
              <тот же or_() что для purchase, но без org_id-ветки>
          ))
        — то есть юзер видит договор если видит хотя бы одну закупку этого договора.
        Если view_all_orgs не пуст — добавить и org_id ветку.
    """
    # SaaS roles — no filter
    if user.role in _SAAS_ROLES:
        return None

    # Gather building blocks
    visible_uids = await get_visible_user_ids(user, db)
    view_all_orgs = await get_view_all_org_ids(user, db)

    # #8: per-user subsidy grant расширяет видимость — пользователь видит ВСЕ
    # закупки субсидии, к которой ему явно выдан доступ (user_subsidy_access),
    # даже если её орг вне его контура. Additive к правилам 0-5.
    granted_subsidy_ids: set[int] = set()
    if doc_type in ("purchase", "contract"):
        from app.models.user_subsidy_access import UserSubsidyAccess
        granted_subsidy_ids = {int(x) for x in (await db.execute(
            select(UserSubsidyAccess.subsidy_id).where(UserSubsidyAccess.user_id == user.id)
        )).scalars().all() if x}

    if doc_type == "purchase":
        return _build_purchase_clause(user, visible_uids, view_all_orgs, granted_subsidy_ids)
    elif doc_type == "task":
        return _build_task_clause(user, visible_uids, view_all_orgs)
    elif doc_type == "wish":
        return _build_wish_clause(user, visible_uids, view_all_orgs)
    elif doc_type == "contract":
        return _build_contract_clause(user, visible_uids, view_all_orgs)
    else:
        raise ValueError(f"build_visibility_clause: unknown doc_type={doc_type!r}")


# ---------------------------------------------------------------------------
# Internal clause builders (synchronous — all DB work done above)
# ---------------------------------------------------------------------------

def _purchase_participation_clauses(user_id: int):
    """Return list of participation clauses for purchase (no org_id branch)."""
    return [
        # PurchaseMember — explicitly added to purchase
        Purchase.id.in_(
            select(PurchaseMember.purchase_id).where(PurchaseMember.user_id == user_id)
        ),
        # Chat participant in purchase-linked chat room
        Purchase.id.in_(
            select(ChatRoom.entity_id)
            .join(ChatParticipant, ChatParticipant.room_id == ChatRoom.id)
            .where(
                ChatParticipant.user_id == user_id,
                ChatRoom.entity_type == "purchase",
            )
        ),
        # Assigned to a task linked to this purchase
        Purchase.id.in_(
            select(Task.purchase_id)
            .join(TaskAssignee, TaskAssignee.task_id == Task.id)
            .where(
                TaskAssignee.user_id == user_id,
                Task.purchase_id.isnot(None),
            )
        ),
    ]


def _build_purchase_clause(user: User, visible_uids: Optional[set[int]], view_all_orgs: set[int], granted_subsidy_ids: Optional[set[int]] = None):
    """Build or_() clause for Purchase."""
    clauses = []

    # Rule 3: view_all_in_org — match via subsidy FK (Purchase has no direct org_id)
    if view_all_orgs:
        clauses.append(
            Purchase.subsidy_id.in_(
                select(Subsidy.id).where(Subsidy.org_id.in_(view_all_orgs))
            )
        )

    # #8: явный grant субсидии → видны все её закупки
    if granted_subsidy_ids:
        clauses.append(Purchase.subsidy_id.in_(granted_subsidy_ids))

    # Rules 0,1,2,4: responsible column
    if visible_uids is not None:
        clauses.append(Purchase.assigned_user_id.in_(visible_uids))
        # 27.4-05: для авансовых отчётов responsible = reimbursement_user_id
        # (кому возмещение). Без этого employee не видит свои собственные
        # авансовые отчёты в /advance-reports, т.к. assigned_user_id обычно NULL.
        clauses.append(Purchase.reimbursement_user_id.in_(visible_uids))

    # Rule 5: participation
    clauses.extend(_purchase_participation_clauses(user.id))

    return or_(*clauses)


def _build_task_clause(user: User, visible_uids: Optional[set[int]], view_all_orgs: set[int]):
    """Build or_() clause for Task."""
    clauses = []

    # Rule 3: view_all_in_org
    if view_all_orgs:
        clauses.append(Task.org_id.in_(view_all_orgs))

    # Rules 0,1,2,4: creator is responsible for task visibility
    if visible_uids is not None:
        clauses.append(Task.created_by_id.in_(visible_uids))

    # Rule 5: participation

    # Assigned as task assignee
    clauses.append(
        Task.id.in_(
            select(TaskAssignee.task_id).where(TaskAssignee.user_id == user.id)
        )
    )

    # Chat participant in task-linked chat room
    clauses.append(
        Task.id.in_(
            select(ChatRoom.entity_id)
            .join(ChatParticipant, ChatParticipant.room_id == ChatRoom.id)
            .where(
                ChatParticipant.user_id == user.id,
                ChatRoom.entity_type == "task",
            )
        )
    )

    # Left a comment on the task
    clauses.append(
        Task.id.in_(
            select(TaskComment.task_id).where(TaskComment.user_id == user.id)
        )
    )

    return or_(*clauses)


def _build_wish_clause(user: User, visible_uids: Optional[set[int]], view_all_orgs: set[int]):
    """Build or_() clause for Wish."""
    clauses = []

    # Rule 3: view_all_in_org
    if view_all_orgs:
        clauses.append(Wish.org_id.in_(view_all_orgs))

    # Rules 0,1,2,4: creator
    if visible_uids is not None:
        clauses.append(Wish.created_by.in_(visible_uids))
        # Assignee also sees the wish
        clauses.append(Wish.assigned_to.in_(visible_uids))

    # Self-visibility: always see wishes you're assigned to or created
    # (redundant when visible_uids includes self, but safe to add explicitly)
    clauses.append(Wish.created_by == user.id)
    clauses.append(Wish.assigned_to == user.id)

    return or_(*clauses)


def _build_contract_clause(user: User, visible_uids: Optional[set[int]], view_all_orgs: set[int]):
    """Build or_() clause for Contract.

    Contract has no responsible_col. Visibility is derived from purchase visibility:
    user sees a contract if they see at least one purchase of that contract.
    """
    clauses = []

    # Rule 3: view_all_in_org via subsidy FK (same pattern as Purchase)
    if view_all_orgs:
        clauses.append(
            Contract.subsidy_id.in_(
                select(Subsidy.id).where(Subsidy.org_id.in_(view_all_orgs))
            )
        )

    # Visibility via purchases: user sees contract if they can see any linked purchase.
    # Build the same purchase-level clauses (minus org_id branch which is handled above).
    purchase_clauses = []

    if visible_uids is not None:
        purchase_clauses.append(Purchase.assigned_user_id.in_(visible_uids))
        # 27.4-05: для авансовых — reimbursement_user_id (см. _build_purchase_clause)
        purchase_clauses.append(Purchase.reimbursement_user_id.in_(visible_uids))

    purchase_clauses.extend(_purchase_participation_clauses(user.id))

    if purchase_clauses:
        clauses.append(
            Contract.id.in_(
                select(Purchase.contract_id).where(
                    Purchase.contract_id.isnot(None),
                    or_(*purchase_clauses),
                )
            )
        )

    return or_(*clauses)
