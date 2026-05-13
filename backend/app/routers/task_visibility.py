"""
task_visibility.py — Helper-only module (no router, no endpoints).

Contains visibility, enrichment, and chat-room helpers extracted from
tasks.py per refactor Plan 16-07 (D-10 + D-21).

Design decisions
----------------
- D-10: visibility logic lives in its own module so task_badges.py,
  task_delegation.py, task_comments.py, and tasks.py can all import
  without circular imports.
- D-21: helper stays in the originating module; others import from here.
- No router instance — this module is never passed to include_router().
- NOT registered in backend/app/__init__.py.

Public API
----------
_get_visible_user_ids   coroutine  — returns set of user IDs current_user may see (or None for SaaS-wide)
_enrich_tasks           coroutine  — builds TaskOut list with user names, assignees, comment previews
_create_task_chat_room  coroutine  — creates or finds a ChatRoom for a task assignment

Downstream consumers (import from this module)
-----------------------------------------------
- app.routers.tasks   (list / CRUD endpoints)
- app.routers.purchases  (Plan 16-11 will update cross-file import)
"""
import logging
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from app.models.task import Task, TaskStatus, TaskPriority, TaskAssignee
from app.models.task_comment import TaskComment
from app.models.task_change import TaskChange, TaskFieldSeen
from app.models.user import User
from app.models.chat_room import ChatRoom, ChatParticipant
from app.models.chat_message import ChatMessage
from app.schemas.schemas import TaskOut, TaskAssigneeOut

logger = logging.getLogger(__name__)


async def _get_visible_user_ids(current_user, db) -> Optional[set]:
    """
    Returns the set of user IDs whose tasks/purchases current_user may see.
    Returning None means "no user-level filter, scope purely by org_id".

    Visibility rule (business, not title):
      - superadmin / account_owner  → SaaS-wide or tenant-wide → None (no user filter)
      - everyone else (admin, org_admin, manager, employee) → by hierarchy:
          {self} ∪ recursive subordinates ∪ managed-department members
                ∪ managed-organization members
        — employees and admins without subordinates end up with just {self}.

    Being 'admin' or 'org_admin' grants system privileges (settings, delete,
    export, publish) but does NOT widen visibility. Only the SaaS-level
    roles see everything by virtue of being the platform itself.
    """
    if current_user.role in ('superadmin', 'account_owner'):
        return None  # SaaS-level — no user-level filter

    from app.models.manager_department import ManagerDepartment
    from app.models.manager_organization import ManagerOrganization
    from app.models.department import Department, DepartmentMember
    from app.routers.user_hierarchy import get_all_subordinate_ids

    visible = {current_user.id}

    # Direct + recursive subordinates (everyone can have reports, incl. admins)
    sub_ids = await get_all_subordinate_ids(current_user.id, db)
    visible.update(sub_ids)

    # Department head: if current_user is head of a dept (Department.head_user_id),
    # include all members of that dept and its sub-depts.
    headed_dept_res = await db.execute(
        select(Department.id).where(Department.head_user_id == current_user.id)
    )
    headed_dept_ids = [r[0] for r in headed_dept_res.all()]
    if headed_dept_ids:
        head_dm_res = await db.execute(
            select(DepartmentMember.user_id).where(DepartmentMember.department_id.in_(headed_dept_ids))
        )
        visible.update(r[0] for r in head_dm_res.all())

    # Managed departments (ManagerDepartment table — explicit assignment)
    md_res = await db.execute(
        select(ManagerDepartment.dept_id).where(ManagerDepartment.manager_user_id == current_user.id)
    )
    managed_dept_ids = [r[0] for r in md_res.all()]
    if managed_dept_ids:
        dm_res = await db.execute(
            select(DepartmentMember.user_id).where(DepartmentMember.department_id.in_(managed_dept_ids))
        )
        visible.update(r[0] for r in dm_res.all())

    # Managed organizations
    mo_res = await db.execute(
        select(ManagerOrganization.org_id).where(ManagerOrganization.manager_user_id == current_user.id)
    )
    managed_org_ids = [r[0] for r in mo_res.all()]
    if managed_org_ids:
        # D-09: hide superadmin from non-superadmin callers
        org_user_q = select(User.id).where(User.org_id.in_(managed_org_ids))
        if current_user.role != "superadmin":
            org_user_q = org_user_q.where(User.role != "superadmin")
        org_users = await db.execute(org_user_q)
        visible.update(r[0] for r in org_users.all())

    # Per-org role: user_org_access.role IN ('org_admin','manager') → see all members of that org
    from app.models.user_org_access import UserOrgAccess
    uoa_orgs_res = await db.execute(
        select(UserOrgAccess.org_id).where(
            UserOrgAccess.user_id == current_user.id,
            UserOrgAccess.role.in_(['org_admin', 'manager']),
        )
    )
    uoa_org_ids = [r[0] for r in uoa_orgs_res.all()]
    if uoa_org_ids:
        uoa_members_res = await db.execute(
            select(User.id).where(
                User.org_id.in_(uoa_org_ids),
                User.role != 'superadmin',
            )
        )
        visible.update(r[0] for r in uoa_members_res.all())

    return visible


async def _create_task_chat_room(
    db: AsyncSession,
    assignor_id: int,
    assignee_id: int,
    org_id: int,
    room_name: str,
) -> int:
    """Create or find a ChatRoom for this task assignment. Returns room_id."""
    existing_q = select(ChatRoom.id).where(ChatRoom.name == room_name, ChatRoom.org_id == org_id)
    existing = await db.execute(existing_q)
    room_id = existing.scalar_one_or_none()
    if room_id:
        return room_id

    room = ChatRoom(name=room_name, is_group=False, org_id=org_id, created_by=assignor_id)
    db.add(room)
    await db.flush()
    db.add(ChatParticipant(room_id=room.id, user_id=assignor_id))
    db.add(ChatParticipant(room_id=room.id, user_id=assignee_id))
    sys_msg = ChatMessage(
        room_id=room.id,
        sender_id=assignor_id,
        content=f"[СИСТЕМА] Чат создан для обсуждения: {room_name}",
    )
    db.add(sys_msg)
    await db.flush()
    return room.id


async def _enrich_tasks(tasks: list, db: AsyncSession, current_user_id: int = 0) -> List[TaskOut]:
    """Build TaskOut list with user names, assignees and last comment preview."""
    if not tasks:
        return []

    task_ids = [t.id for t in tasks]

    # Collect all user IDs needed
    user_ids = set()
    for t in tasks:
        user_ids.add(t.created_by_id)
    users_map = {}
    if user_ids:
        res = await db.execute(select(User).where(User.id.in_(user_ids)))  # superadmin-bypass-ok: lookup by ID for enrichment, not a user-list endpoint
        for u in res.scalars().all():
            users_map[u.id] = u.full_name or u.username

    # Load all assignees for these tasks
    assignee_rows = (await db.execute(
        select(TaskAssignee).where(TaskAssignee.task_id.in_(task_ids))
    )).scalars().all()
    # group by task_id
    assignees_map: dict[int, list] = {}
    assignee_user_ids = set()
    for a in assignee_rows:
        assignees_map.setdefault(a.task_id, []).append(a)
        assignee_user_ids.add(a.user_id)
    # load assignee user names
    if assignee_user_ids:
        res2 = await db.execute(select(User).where(User.id.in_(assignee_user_ids)))  # superadmin-bypass-ok: lookup by ID for enrichment, not a user-list endpoint
        for u in res2.scalars().all():
            users_map[u.id] = u.full_name or u.username

    # Comment counts
    count_q = (
        select(TaskComment.task_id, func.count(TaskComment.id).label("cnt"))
        .where(TaskComment.task_id.in_(task_ids))
        .group_by(TaskComment.task_id)
    )
    count_map = {r.task_id: r.cnt for r in (await db.execute(count_q)).all()}

    # Subtask counts
    subtask_q = (
        select(Task.parent_task_id, func.count(Task.id).label("cnt"))
        .where(Task.parent_task_id.in_(task_ids))
        .group_by(Task.parent_task_id)
    )
    subtask_map = {r.parent_task_id: r.cnt for r in (await db.execute(subtask_q)).all()}

    # Last comment per task
    last_comments_map: dict = {}
    if task_ids:
        subq = (
            select(
                TaskComment.task_id,
                TaskComment.text,
                TaskComment.user_name,
                TaskComment.created_at,
                func.row_number().over(
                    partition_by=TaskComment.task_id,
                    order_by=TaskComment.created_at.desc()
                ).label("rn")
            )
            .where(TaskComment.task_id.in_(task_ids))
            .subquery()
        )
        for row in (await db.execute(select(subq).where(subq.c.rn == 1))).all():
            last_comments_map[row.task_id] = {
                "text": row.text[:100] if row.text else None,
                "user": row.user_name,
                "at": row.created_at,
            }

    # Load linked purchases for tasks that have purchase_id
    purchase_ids = {t.purchase_id for t in tasks if t.purchase_id}
    purchase_map: dict = {}
    if purchase_ids:
        from app.models.purchase import Purchase
        pq = await db.execute(select(Purchase).where(Purchase.id.in_(purchase_ids)))
        for p in pq.scalars().all():
            purchase_map[p.id] = p

    # Load unseen field changes for current user
    # changes_map: task_id → {field_name: latest_changed_at}
    changes_map: dict[int, dict] = {}
    # seen_map: (task_id, field_name) → dismissed_at
    seen_map: dict[tuple, object] = {}
    if current_user_id and task_ids:
        try:
            change_rows = (await db.execute(
                select(TaskChange).where(
                    TaskChange.task_id.in_(task_ids),
                    or_(TaskChange.changed_by_id != current_user_id,
                        TaskChange.changed_by_id.is_(None)),
                ).order_by(TaskChange.changed_at.asc())
            )).scalars().all()
            for c in change_rows:
                # Keep latest per (task_id, field_name)
                task_fields = changes_map.setdefault(c.task_id, {})
                task_fields[c.field_name] = c.changed_at

            seen_rows = (await db.execute(
                select(TaskFieldSeen).where(
                    TaskFieldSeen.user_id == current_user_id,
                    TaskFieldSeen.task_id.in_(task_ids),
                )
            )).scalars().all()
            for s in seen_rows:
                seen_map[(s.task_id, s.field_name)] = s.dismissed_at
        except Exception as exc:
            logger.warning("unseen changes query failed: %s", exc)

    out = []
    for t in tasks:
        lc = last_comments_map.get(t.id, {})
        task_assignees = assignees_map.get(t.id, [])
        assignees_out = [
            TaskAssigneeOut(
                user_id=a.user_id,
                user_name=users_map.get(a.user_id),
                consent_pending=bool(getattr(a, 'consent_pending', False)),
            ) for a in task_assignees
        ]
        # backward compat: first assignee as assigned_user_id
        first_a = task_assignees[0] if task_assignees else None
        needs_my_consent = any(
            a.user_id == current_user_id and getattr(a, 'consent_pending', False)
            for a in task_assignees
        )
        linked_purchase = purchase_map.get(t.purchase_id) if t.purchase_id else None

        # Compute unseen fields for this task
        unseen_fields: list = []
        task_changes = changes_map.get(t.id, {})
        for fname, fat in task_changes.items():
            dismissed_at = seen_map.get((t.id, fname))
            if dismissed_at is None or fat > dismissed_at:
                unseen_fields.append(fname)

        out.append(TaskOut(
            id=t.id, task_number=t.task_number, title=t.title, description=t.description,
            status=t.status.value if isinstance(t.status, TaskStatus) else t.status,
            priority=t.priority.value if isinstance(t.priority, TaskPriority) else t.priority,
            due_date=t.due_date,
            assignees=assignees_out,
            assigned_user_id=first_a.user_id if first_a else None,
            assigned_user_name=users_map.get(first_a.user_id) if first_a else None,
            created_by_id=t.created_by_id,
            created_by_name=users_map.get(t.created_by_id),
            org_id=t.org_id, category=t.category,
            parent_task_id=t.parent_task_id,
            purchase_id=t.purchase_id,
            purchase_subject=linked_purchase.subject if linked_purchase else None,
            purchase_number=linked_purchase.purchase_number if linked_purchase else None,
            purchase_status=linked_purchase.status if linked_purchase else None,
            import_to_parent=t.import_to_parent,
            subtask_count=subtask_map.get(t.id, 0),
            created_at=t.created_at, updated_at=t.updated_at,
            last_comment=lc.get("text"),
            last_comment_user=lc.get("user"),
            last_comment_at=lc.get("at"),
            comment_count=count_map.get(t.id, 0),
            needs_my_consent=needs_my_consent,
            unseen_changes_count=len(unseen_fields),
            unseen_fields=unseen_fields,
        ))
    return out
