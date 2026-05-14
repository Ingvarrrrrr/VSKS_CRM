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
from app.models.department import Department, DepartmentMember
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
                select(DepartmentMember.user_id).where(
                    DepartmentMember.department_id.in_(headed_dept_ids)
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
                select(DepartmentMember.user_id).where(
                    DepartmentMember.department_id.in_(managed_dept_ids)
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

    # Phase 26-AA: «поглощение» — если в подчинённых есть SaaS-юзер, наследуем
    # SaaS-видимость (None = без фильтра). Бизнес-правило: «ты ставишь задачи
    # superadmin'у → ты видишь то же что и он».
    if visible - {user.id}:
        saas_check = await db.execute(
            select(User.id).where(
                User.id.in_(visible - {user.id}),
                User.role.in_(_SAAS_ROLES),
            )
        )
        if saas_check.first() is not None:
            return None  # bypass фильтра — наследовал SaaS

    return visible


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

    if doc_type == "purchase":
        return _build_purchase_clause(user, visible_uids, view_all_orgs)
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


def _build_purchase_clause(user: User, visible_uids: Optional[set[int]], view_all_orgs: set[int]):
    """Build or_() clause for Purchase."""
    clauses = []

    # Rule 3: view_all_in_org — match via subsidy FK (Purchase has no direct org_id)
    if view_all_orgs:
        clauses.append(
            Purchase.subsidy_id.in_(
                select(Subsidy.id).where(Subsidy.org_id.in_(view_all_orgs))
            )
        )

    # Rules 0,1,2,4: responsible column
    if visible_uids is not None:
        clauses.append(Purchase.assigned_user_id.in_(visible_uids))

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
