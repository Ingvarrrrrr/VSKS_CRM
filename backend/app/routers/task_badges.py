"""
task_badges.py — Badge counts, org-summary, and init bootstrap endpoints.

Extracted from tasks.py per refactor Plan 16-09 (D-11).

Endpoints
---------
GET /api/tasks/badges       — sidebar badge counts (new tasks, changes, chat unread)
GET /api/tasks/org-summary  — per-org counters (task, purchase, unseen-change counts)
GET /api/tasks/init         — MyTasksView bootstrap: tasks + pending + declines + meta
"""
import logging
import asyncio
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, or_, exists
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from datetime import datetime, timezone, timedelta

from app.database import get_db
from app.models.task import Task, TaskStatus, TaskAssignee
from app.models.task_comment import TaskComment
from app.models.task_change import TaskChange, TaskFieldSeen
from app.models.task_decline import TaskConsentDecline
from app.models.user import User
from app.models.chat_room import ChatRoom, ChatParticipant
from app.auth.jwt import get_current_user, get_org_filter
from app.routers.task_visibility import _get_visible_user_ids, _enrich_tasks

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["task-badges"])


@router.get("/org-summary")
async def org_summary(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Per-organization summary: task count, purchase count, unseen changes count."""
    from app.models.organization import Organization
    from app.models.purchase import Purchase
    from app.models.subsidy import Subsidy

    user_id = current_user.id
    org_ids = get_org_filter(current_user)

    if org_ids is None:
        orgs_result = await db.execute(select(Organization).where(Organization.is_active == True))
    else:
        orgs_result = await db.execute(select(Organization).where(Organization.id.in_(org_ids)))
    orgs = orgs_result.scalars().all()

    result = []
    total_tasks = 0
    total_purchases = 0
    total_unseen = 0

    # Compute visibility once, reuse across all orgs
    visible_ids = await _get_visible_user_ids(current_user, db)

    for org in orgs:
        if visible_ids is None:
            # SaaS-level (superadmin / account_owner): count all tasks in org (exclude done/cancelled)
            task_q = select(func.count(Task.id)).where(
                Task.org_id == org.id,
                Task.status.notin_(['done', 'cancelled']),
            )
        else:
            # Everyone else: tasks where someone in my hierarchy tree is creator/assignee,
            # OR tasks I personally participate in (commented OR chat-room participant).
            task_q = select(func.count(Task.id)).where(
                Task.org_id == org.id,
                Task.status.notin_(['done', 'cancelled']),
                or_(
                    Task.created_by_id.in_(visible_ids),
                    Task.id.in_(select(TaskAssignee.task_id).where(TaskAssignee.user_id.in_(visible_ids))),
                    Task.id.in_(select(TaskComment.task_id).where(TaskComment.user_id == user_id)),
                    Task.id.in_(
                        select(ChatRoom.entity_id)
                        .join(ChatParticipant, ChatParticipant.room_id == ChatRoom.id)
                        .where(
                            ChatParticipant.user_id == user_id,
                            ChatRoom.entity_type == 'task',
                            ChatRoom.entity_id.isnot(None),
                        )
                    ),
                )
            )
        task_count = (await db.execute(task_q)).scalar() or 0

        # Purchase count — respects hierarchy-based visibility.
        from app.models.purchase_event import PurchaseMember
        purchase_base = select(func.count(Purchase.id)).join(
            Subsidy, Purchase.subsidy_id == Subsidy.id
        ).where(Subsidy.org_id == org.id, Purchase.status != 'paid')

        if visible_ids is not None:
            # Purchase visibility:
            #   - assigned_user_id in hierarchy, OR
            #   - I'm a PurchaseMember (invited to the discussion), OR
            #   - I'm a chat-room participant for a room linked to the purchase
            # Previously included `Purchase.assigned_user_id IS NULL`, which leaked
            # every unassigned purchase (~379 in VSKS) into the count for any
            # non-SaaS role — observed as "381 total" in the All-Orgs card for
            # Lyubarets. Dropped.
            member_pids = select(PurchaseMember.purchase_id).where(PurchaseMember.user_id.in_(visible_ids))
            chat_pids = (
                select(ChatRoom.entity_id)
                .join(ChatParticipant, ChatParticipant.room_id == ChatRoom.id)
                .where(
                    ChatParticipant.user_id == user_id,
                    ChatRoom.entity_type == 'purchase',
                    ChatRoom.entity_id.isnot(None),
                )
            )
            purchase_base = purchase_base.where(
                or_(
                    Purchase.assigned_user_id.in_(visible_ids),
                    Purchase.id.in_(member_pids),
                    Purchase.id.in_(chat_pids),
                )
            )
        purchase_count = (await db.execute(purchase_base)).scalar() or 0

        unseen_q = select(func.count(func.distinct(TaskChange.task_id))).join(
            Task, TaskChange.task_id == Task.id
        ).where(
            Task.org_id == org.id,
            TaskChange.changed_by_id != user_id,
            ~exists(
                select(TaskFieldSeen.id).where(
                    TaskFieldSeen.task_id == TaskChange.task_id,
                    TaskFieldSeen.user_id == user_id,
                    TaskFieldSeen.field_name == TaskChange.field_name,
                    TaskFieldSeen.dismissed_at >= TaskChange.changed_at,
                )
            )
        )
        unseen_count = (await db.execute(unseen_q)).scalar() or 0

        result.append({
            "org_id": org.id, "org_name": org.name,
            "task_count": task_count, "purchase_count": purchase_count,
            "unseen_count": unseen_count,
        })
        total_tasks += task_count
        total_purchases += purchase_count
        total_unseen += unseen_count

    result.insert(0, {
        "org_id": None, "org_name": "Все организации",
        "task_count": total_tasks, "purchase_count": total_purchases,
        "unseen_count": total_unseen,
    })
    return result


@router.get("/init")
async def tasks_init(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Single endpoint returning all data needed for MyTasksView initial load."""
    # Run all queries concurrently inside the server
    accepted_ids = select(TaskAssignee.task_id).where(
        TaskAssignee.user_id == current_user.id,
        TaskAssignee.consent_pending == False,  # noqa: E712
    ).scalar_subquery()
    pending_ids = select(TaskAssignee.task_id).where(
        TaskAssignee.user_id == current_user.id,
        TaskAssignee.consent_pending == True,  # noqa: E712
    ).scalar_subquery()

    q_my = select(Task).where(
        or_(Task.id.in_(accepted_ids), Task.created_by_id == current_user.id),
        Task.status != TaskStatus.cancelled,
    ).order_by(Task.due_date.asc().nullslast(), Task.created_at.desc())

    q_pending = select(Task).where(Task.id.in_(pending_ids)).order_by(Task.created_at.desc())

    q_declines = select(TaskConsentDecline).where(
        TaskConsentDecline.creator_id == current_user.id,
        TaskConsentDecline.acknowledged == False,  # noqa: E712
    )

    q_categories = select(Task.category).where(Task.category.isnot(None)).distinct()
    q_departments = select(User.department).where(User.department.isnot(None), User.department != "").distinct()

    # Execute all queries sequentially — AsyncSession is NOT concurrent-safe;
    # asyncio.gather on shared session causes asyncpg "another operation in progress" → 502.
    r_my = await db.execute(q_my)
    r_pending = await db.execute(q_pending)
    r_declines = await db.execute(q_declines)
    r_cats = await db.execute(q_categories)
    r_depts = await db.execute(q_departments)

    my_tasks_rows = r_my.scalars().all()
    pending_rows = r_pending.scalars().all()
    declines_rows = r_declines.scalars().all()
    categories = sorted([r[0] for r in r_cats.all()])
    departments = sorted([r[0] for r in r_depts.all()])

    # Enrich tasks sequentially — same shared session constraint.
    my_tasks_out = await _enrich_tasks(my_tasks_rows, db, current_user_id=current_user.id)
    pending_out = await _enrich_tasks(pending_rows, db, current_user_id=current_user.id)

    # Format declines
    declines_out = []
    for d in declines_rows:
        task = d.task
        decliner = d.declined_user
        declines_out.append({
            "id": d.id,
            "task_id": d.task_id,
            "task_title": task.title if task else "—",
            "declined_by_name": (decliner.full_name or decliner.username) if decliner else "—",
            "is_accepted": d.is_accepted,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        })

    return {
        "my_tasks": [t.model_dump() for t in my_tasks_out],
        "pending_consent": [t.model_dump() for t in pending_out],
        "consent_declines": declines_out,
        "categories": categories,
        "departments": departments,
    }


@router.get("/badges")
async def get_badges(
    org_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get badge counts for sidebar: new tasks, task changes, new purchases, purchase changes."""
    from app.models.purchase import Purchase
    from app.models.purchase_event import PurchaseMember

    # Last seen timestamps from query param or default to 24h ago
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    # New tasks assigned to me in last 24h
    my_task_ids = select(TaskAssignee.task_id).where(
        TaskAssignee.user_id == current_user.id,
    ).scalar_subquery()

    new_tasks_q = select(func.count(Task.id)).where(
        Task.id.in_(my_task_ids),
        Task.created_at > cutoff,
    )
    if org_id is not None:
        new_tasks_q = new_tasks_q.where(Task.org_id == org_id)
    new_tasks = (await db.execute(new_tasks_q)).scalar() or 0

    # Task status changes in last 24h (tasks I'm involved in)
    task_changes_q = select(func.count(Task.id)).where(
        Task.id.in_(my_task_ids),
        Task.updated_at > cutoff,
        Task.created_at < cutoff,  # exclude newly created
    )
    if org_id is not None:
        task_changes_q = task_changes_q.where(Task.org_id == org_id)
    task_changes = (await db.execute(task_changes_q)).scalar() or 0

    # Purchases: I'm assigned or member
    my_member_pids = select(PurchaseMember.purchase_id).where(
        PurchaseMember.user_id == current_user.id
    ).scalar_subquery()

    new_purchases = 0  # No created_at on Purchase model
    purchase_changes = 0

    # Use purchase_events for changes
    try:
        from app.models.purchase_event import PurchaseEvent
        purchase_changes = (await db.execute(
            select(func.count(PurchaseEvent.id)).where(
                PurchaseEvent.created_at > cutoff,
                or_(
                    PurchaseEvent.purchase_id.in_(
                        select(Purchase.id).where(Purchase.assigned_user_id == current_user.id)
                    ),
                    PurchaseEvent.purchase_id.in_(my_member_pids),
                ),
            )
        )).scalar() or 0
    except Exception:
        pass

    # Chat unread count
    chat_unread = 0
    try:
        from app.models.chat_message import ChatMessage, MessageRead
        from app.models.chat_room import ChatParticipant as CP
        chat_unread_q = (
            select(func.count(func.distinct(CP.room_id)))
            .join(ChatMessage, ChatMessage.room_id == CP.room_id)
            .outerjoin(
                MessageRead,
                (MessageRead.room_id == CP.room_id) & (MessageRead.user_id == CP.user_id),
            )
            .where(
                CP.user_id == current_user.id,
                or_(
                    MessageRead.last_read_message_id.is_(None),
                    ChatMessage.id > MessageRead.last_read_message_id,
                ),
                ChatMessage.sender_id != current_user.id,
            )
        )
        chat_unread = (await db.execute(chat_unread_q)).scalar() or 0
    except Exception:
        pass

    # Wishes: заявки, ждущие моего согласования (актуальная очередь) + недавно
    # добавленные меня в участники (транзиентный «новый» индикатор за 24ч).
    wishes_approval = 0
    wishes_new = 0
    try:
        from app.models.wish import Wish
        from app.models.wish_member import WishMember
        from app.models.wish_approval import WishApproval

        # 1) submitted-заявки, где я назначенный согласующий ИЛИ мой шаг цепочки pending
        my_pending_appr_wids = select(WishApproval.wish_id).where(
            WishApproval.user_id == current_user.id,
            WishApproval.status == "pending",
        ).scalar_subquery()
        wishes_approval_q = select(func.count(func.distinct(Wish.id))).where(
            Wish.status == "submitted",
            or_(
                Wish.assigned_to == current_user.id,
                Wish.id.in_(my_pending_appr_wids),
            ),
        )
        if org_id is not None:
            wishes_approval_q = wishes_approval_q.where(Wish.org_id == org_id)
        wishes_approval = (await db.execute(wishes_approval_q)).scalar() or 0

        # 2) меня добавили участником за последние 24ч (не самим собой)
        wishes_new_q = (
            select(func.count(func.distinct(WishMember.wish_id)))
            .select_from(WishMember)
            .join(Wish, Wish.id == WishMember.wish_id)
            .where(
                WishMember.user_id == current_user.id,
                WishMember.added_by_id != current_user.id,
                WishMember.created_at > cutoff,
            )
        )
        if org_id is not None:
            wishes_new_q = wishes_new_q.where(Wish.org_id == org_id)
        wishes_new = (await db.execute(wishes_new_q)).scalar() or 0
    except Exception:
        pass

    return {
        "new_tasks": new_tasks,
        "task_changes": task_changes,
        "new_purchases": new_purchases,
        "purchase_changes": purchase_changes,
        "chat_unread": chat_unread,
        "wishes_approval": wishes_approval,
        "wishes_new": wishes_new,
    }
