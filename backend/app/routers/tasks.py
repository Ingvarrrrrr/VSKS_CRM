import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_, func, and_, exists
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.task import Task, TaskStatus, TaskPriority, TaskAssignee
from app.models.task_decline import TaskConsentDecline
from app.models.task_comment import TaskComment
from app.models.task_change import TaskChange, TaskFieldSeen
from app.models.user import User
from app.schemas.schemas import (
    TaskCreate, TaskUpdate, TaskOut, TaskAssigneeOut,
    TaskCommentCreate, TaskCommentOut, ReviewCompleteRequest, DismissFieldRequest,
)
from app.auth.jwt import get_current_user, get_org_filter
from typing import List, Optional
from datetime import date, datetime, timezone, timedelta
from app.chat_manager import manager as chat_manager
from app.models.chat_room import ChatRoom, ChatParticipant
from app.models.chat_message import ChatMessage

logger = logging.getLogger(__name__)


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

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


# ── helpers ──────────────────────────────────────────────────────────────────

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
        res = await db.execute(select(User).where(User.id.in_(user_ids)))
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
        res2 = await db.execute(select(User).where(User.id.in_(assignee_user_ids)))
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


async def _set_assignees(task_id: int, assignee_ids: List[int], db: AsyncSession):
    """Replace all assignees for a task."""
    await db.execute(
        __import__("sqlalchemy").delete(TaskAssignee).where(TaskAssignee.task_id == task_id)
    )
    for uid in assignee_ids:
        db.add(TaskAssignee(task_id=task_id, user_id=uid))


# ── CRUD ─────────────────────────────────────────────────────────────────────

@router.get("/", response_model=List[TaskOut])
async def list_tasks(
    status: Optional[str] = None,
    assigned_to_me: bool = False,
    created_by_me: bool = False,
    category: Optional[str] = None,
    department: Optional[str] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(Task)

    org_ids = get_org_filter(current_user)
    if org_ids is not None:
        q = q.where(Task.org_id.in_(org_ids))

    if status:
        q = q.where(Task.status == status)
    if assigned_to_me:
        me_subq = select(TaskAssignee.task_id).where(TaskAssignee.user_id == current_user.id).scalar_subquery()
        q = q.where(Task.id.in_(me_subq))
    if created_by_me:
        q = q.where(Task.created_by_id == current_user.id)
    if category:
        q = q.where(Task.category == category)
    if department:
        dept_users = select(User.id).where(User.department == department).scalar_subquery()
        assignee_tasks = select(TaskAssignee.task_id).where(TaskAssignee.user_id.in_(dept_users)).scalar_subquery()
        q = q.where(Task.id.in_(assignee_tasks))
    if search:
        search_filters = [
            Task.title.ilike(f"%{search}%"),
            Task.description.ilike(f"%{search}%"),
        ]
        # Search by task_number if numeric
        if search.isdigit():
            search_filters.append(Task.task_number == int(search))
        q = q.where(or_(*search_filters))

    q = q.order_by(Task.due_date.asc().nullslast(), Task.created_at.desc())
    tasks = (await db.execute(q)).scalars().all()
    return await _enrich_tasks(tasks, db)


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

    for org in orgs:
        task_q = select(func.count(Task.id)).where(
            Task.org_id == org.id,
            or_(
                Task.created_by_id == user_id,
                Task.id.in_(select(TaskAssignee.task_id).where(TaskAssignee.user_id == user_id)),
                Task.id.in_(select(TaskComment.task_id).where(TaskComment.user_id == user_id).distinct()),
            )
        )
        task_count = (await db.execute(task_q)).scalar() or 0

        purchase_q = select(func.count(Purchase.id)).join(
            Subsidy, Purchase.subsidy_id == Subsidy.id
        ).where(Subsidy.org_id == org.id)
        purchase_count = (await db.execute(purchase_q)).scalar() or 0

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
    import asyncio

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

    from app.models.task_decline import TaskConsentDecline
    q_declines = select(TaskConsentDecline).where(
        TaskConsentDecline.creator_id == current_user.id,
        TaskConsentDecline.acknowledged == False,  # noqa: E712
    )

    q_categories = select(Task.category).where(Task.category.isnot(None)).distinct()
    q_departments = select(User.department).where(User.department.isnot(None), User.department != "").distinct()

    # Execute all queries
    [r_my, r_pending, r_declines, r_cats, r_depts] = await asyncio.gather(
        db.execute(q_my),
        db.execute(q_pending),
        db.execute(q_declines),
        db.execute(q_categories),
        db.execute(q_departments),
    )

    my_tasks_rows = r_my.scalars().all()
    pending_rows = r_pending.scalars().all()
    declines_rows = r_declines.scalars().all()
    categories = sorted([r[0] for r in r_cats.all()])
    departments = sorted([r[0] for r in r_depts.all()])

    # Enrich tasks
    [my_tasks_out, pending_out] = await asyncio.gather(
        _enrich_tasks(my_tasks_rows, db, current_user_id=current_user.id),
        _enrich_tasks(pending_rows, db, current_user_id=current_user.id),
    )

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


@router.get("/my", response_model=List[TaskOut])
async def my_tasks(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Задачи назначенные мне (через task_assignees) или созданные мной. Исключает задачи, требующие моего согласия."""
    # IDs задач где я исполнитель И согласие дано (consent_pending=False)
    accepted_ids = select(TaskAssignee.task_id).where(
        TaskAssignee.user_id == current_user.id,
        TaskAssignee.consent_pending == False,  # noqa: E712
    ).scalar_subquery()
    q = select(Task).where(
        or_(
            Task.id.in_(accepted_ids),
            Task.created_by_id == current_user.id,
        ),
        Task.status != TaskStatus.cancelled,
    ).order_by(Task.due_date.asc().nullslast(), Task.created_at.desc())

    tasks = (await db.execute(q)).scalars().all()
    return await _enrich_tasks(tasks, db, current_user_id=current_user.id)


@router.get("/pending-consent", response_model=List[TaskOut])
async def pending_consent_tasks(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Задачи, назначенные мне, но ожидающие моего согласия."""
    pending_ids = select(TaskAssignee.task_id).where(
        TaskAssignee.user_id == current_user.id,
        TaskAssignee.consent_pending == True,  # noqa: E712
    ).scalar_subquery()
    q = select(Task).where(Task.id.in_(pending_ids)).order_by(Task.created_at.desc())
    tasks = (await db.execute(q)).scalars().all()
    return await _enrich_tasks(tasks, db, current_user_id=current_user.id)


@router.post("/{task_id}/consent", response_model=TaskOut)
async def respond_task_consent(
    task_id: int,
    accept: bool = Query(..., description="true=принять, false=отклонить"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Принять или отклонить задачу, ожидающую согласия."""
    import sqlalchemy
    assignee_row = (await db.execute(
        select(TaskAssignee).where(
            TaskAssignee.task_id == task_id,
            TaskAssignee.user_id == current_user.id,
            TaskAssignee.consent_pending == True,  # noqa: E712
        )
    )).scalar_one_or_none()
    if not assignee_row:
        raise HTTPException(404, "Задача не найдена или согласие не требуется")

    if accept:
        assignee_row.consent_pending = False
        # Уведомить постановщика о принятии
        db_task_obj = await db.get(Task, task_id)
        if db_task_obj:
            db.add(TaskConsentDecline(
                task_id=task_id,
                declined_user_id=current_user.id,
                creator_id=db_task_obj.created_by_id,
                is_accepted=True,
            ))
            try:
                from app.notifications import notify_user
                creator = await db.get(User, db_task_obj.created_by_id)
                accepter_name = current_user.full_name or current_user.username
                if creator:
                    await notify_user(
                        creator,
                        f"✅ <b>{accepter_name}</b> принял задачу:\n<b>{db_task_obj.title}</b>"
                    )
            except Exception:
                pass

            # D-18: Create chat room on consent acceptance + WS notification to assignee
            try:
                task_title = db_task_obj.title or f"Задача #{task_id}"
                creator_id = db_task_obj.created_by_id
                task_org_id = current_user.org_id or 1
                room_id = await _create_task_chat_room(
                    db, creator_id, current_user.id, task_org_id,
                    f"Задача: {task_title}",
                )
                await db.commit()
                await chat_manager.send_to_user(current_user.id, {
                    "type": "system_notification",
                    "subtype": "task_assigned",
                    "task_id": task_id,
                    "room_id": room_id,
                    "message": f"[СИСТЕМА] Вам назначена задача: «{task_title}»",
                    "link": "/my-tasks",
                })
            except Exception as exc:
                logger.error("Chat room/WS error on task consent accept (task_id=%s): %s", task_id, exc)

        await db.commit()
        db_task = await db.get(Task, task_id)
        result = await _enrich_tasks([db_task], db, current_user_id=current_user.id)
        return result[0]
    else:
        # Отклонено: убрать пользователя из исполнителей
        await db.execute(
            sqlalchemy.delete(TaskAssignee).where(
                TaskAssignee.task_id == task_id,
                TaskAssignee.user_id == current_user.id,
            )
        )
        # Создать запись об отклонении для постановщика
        db_task_obj = await db.get(Task, task_id)
        if db_task_obj:
            db.add(TaskConsentDecline(
                task_id=task_id,
                declined_user_id=current_user.id,
                creator_id=db_task_obj.created_by_id,
            ))
            # Уведомить постановщика
            try:
                from app.notifications import notify_user
                from app.models.user import User as UserModel
                creator = await db.get(UserModel, db_task_obj.created_by_id)
                decliner_name = current_user.full_name or current_user.username
                if creator:
                    await notify_user(creator,
                        f"❌ <b>{decliner_name}</b> отклонил назначение на задачу:\n"
                        f"<b>{db_task_obj.title}</b>\n"
                        f"Зайдите в CRM → Задачи для подтверждения."
                    )
            except Exception:
                pass
        await db.commit()
        db_task = await db.get(Task, task_id)
        result = await _enrich_tasks([db_task], db, current_user_id=current_user.id)
        return result[0]


@router.get("/consent-declines")
async def list_consent_declines(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Непрочитанные уведомления об отклонённых назначениях (для постановщика)."""
    result = await db.execute(
        select(TaskConsentDecline).where(
            TaskConsentDecline.creator_id == current_user.id,
            TaskConsentDecline.acknowledged == False,  # noqa: E712
        )
    )
    declines = result.scalars().all()
    out = []
    for d in declines:
        task = d.task
        decliner = d.declined_user
        out.append({
            "id": d.id,
            "task_id": d.task_id,
            "task_title": task.title if task else "—",
            "declined_by_name": (decliner.full_name or decliner.username) if decliner else "—",
            "is_accepted": d.is_accepted,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        })
    return out


@router.post("/consent-declines/{decline_id}/acknowledge")
async def acknowledge_decline(
    decline_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Подтвердить получение уведомления об отклонении."""
    row = await db.get(TaskConsentDecline, decline_id)
    if not row or row.creator_id != current_user.id:
        raise HTTPException(404, "Уведомление не найдено")
    row.acknowledged = True
    await db.commit()
    return {"ok": True}


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
    from datetime import timedelta
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

    from sqlalchemy import literal_column
    # New purchases assigned to me or where I'm member
    new_purchases_q = select(func.count(Purchase.id)).where(
        or_(
            Purchase.assigned_user_id == current_user.id,
            Purchase.id.in_(my_member_pids),
        ),
    )
    # We don't have created_at on purchases, use id-based heuristic
    # Instead, count purchases with status changes
    # Simpler: count tasks/purchases with recent activity

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

    return {
        "new_tasks": new_tasks,
        "task_changes": task_changes,
        "new_purchases": new_purchases,
        "purchase_changes": purchase_changes,
        "chat_unread": chat_unread,
    }


@router.get("/categories", response_model=List[str])
async def list_categories(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(Task.category).where(Task.category.isnot(None)).distinct()
    result = await db.execute(q)
    return sorted([r[0] for r in result.all()])


@router.get("/departments", response_model=List[str])
async def list_departments(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(User.department).where(User.department.isnot(None), User.department != "").distinct()
    org_ids = get_org_filter(current_user)
    if org_ids is not None:
        q = q.where(User.org_id.in_(org_ids))
    result = await db.execute(q)
    return sorted([r[0] for r in result.all()])


@router.post("/", response_model=TaskOut)
async def create_task(
    task: TaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.auth.jwt import get_single_org_id, MANAGER_ROLES as _MR
    from app.models.user_hierarchy import UserHierarchy

    if task.due_date:
        today = date.today()
        due_d = task.due_date.date() if isinstance(task.due_date, datetime) else task.due_date
        if due_d < today:
            raise HTTPException(422, "Срок исполнения не может быть раньше текущей даты")

    org_id = get_single_org_id(current_user)
    # Consent is determined purely by hierarchy, not by role
    can_assign_others = False

    # Determine effective assignee IDs
    assignee_ids = task.assignee_ids or []
    if not assignee_ids:
        assignee_ids = [current_user.id]

    # Validate subtask due_date <= parent due_date
    if task.parent_task_id and task.due_date:
        parent_task = await db.get(Task, task.parent_task_id)
        if parent_task and parent_task.due_date:
            parent_due = parent_task.due_date.date() if hasattr(parent_task.due_date, 'date') else parent_task.due_date
            task_due = task.due_date.date() if hasattr(task.due_date, 'date') else task.due_date
            if task_due > parent_due:
                raise HTTPException(422, "Срок подзадачи не может быть позже срока родительской задачи")

    # For subtask delegation: verify current user is assignee of parent
    if task.parent_task_id and not can_assign_others:
        non_self = [uid for uid in assignee_ids if uid != current_user.id]
        if non_self:
            parent_assignee_ids = [a.user_id for a in (await db.execute(
                select(TaskAssignee).where(TaskAssignee.task_id == task.parent_task_id)
            )).scalars().all()]
            if current_user.id not in parent_assignee_ids:
                raise HTTPException(403, "Делегирование доступно только исполнителю родительской задачи")

    # Determine which assignees need consent (no hierarchy authority)
    # Managers/admins never need consent; assigning to self never needs consent
    # ManagerOrganization: if user manages an org, all members of that org don't need consent
    consent_needed: set[int] = set()
    if not can_assign_others:
        non_self = [uid for uid in assignee_ids if uid != current_user.id]
        if non_self:
            # Load hierarchy: current user's subordinates
            hier_res = await db.execute(
                select(UserHierarchy.subordinate_id).where(
                    UserHierarchy.manager_id == current_user.id
                )
            )
            subordinate_ids = {r[0] for r in hier_res.all()}

            # Load orgs managed by current user
            from app.models.manager_organization import ManagerOrganization
            mo_res = await db.execute(
                select(ManagerOrganization.org_id).where(
                    ManagerOrganization.manager_user_id == current_user.id
                )
            )
            managed_org_ids = {r[0] for r in mo_res.all()}

            # Load depts managed by current user
            from app.models.manager_department import ManagerDepartment
            from app.models.department import DepartmentMember
            md_res = await db.execute(
                select(ManagerDepartment.dept_id).where(
                    ManagerDepartment.manager_user_id == current_user.id
                )
            )
            managed_dept_ids = {r[0] for r in md_res.all()}
            # Get all user IDs in managed depts
            managed_dept_user_ids: set[int] = set()
            if managed_dept_ids:
                dm_res = await db.execute(
                    select(DepartmentMember.user_id).where(DepartmentMember.department_id.in_(managed_dept_ids))
                )
                managed_dept_user_ids = {r[0] for r in dm_res.all()}

            # Load org_id for each assignee
            assignee_org_map = {}
            if managed_org_ids:
                assignee_users = (await db.execute(
                    select(User.id, User.org_id).where(User.id.in_(non_self))
                )).all()
                assignee_org_map = {r[0]: r[1] for r in assignee_users}

            for uid in non_self:
                if uid in subordinate_ids:
                    continue  # direct subordinate
                if assignee_org_map.get(uid) in managed_org_ids:
                    continue  # manages their org
                if uid in managed_dept_user_ids:
                    continue  # manages their dept
                consent_needed.add(uid)

    db_task = Task(
        title=task.title,
        description=task.description,
        priority=task.priority,
        due_date=task.due_date,
        assigned_user_id=assignee_ids[0] if assignee_ids else current_user.id,
        created_by_id=current_user.id,
        org_id=org_id,
        category=task.category,
        parent_task_id=task.parent_task_id,
        purchase_id=task.purchase_id,
        import_to_parent=task.import_to_parent,
    )
    # Auto-assign task_number
    max_num = (await db.execute(select(func.coalesce(func.max(Task.task_number), 0)))).scalar()
    db_task.task_number = max_num + 1

    db.add(db_task)
    await db.flush()  # get db_task.id

    for uid in assignee_ids:
        db.add(TaskAssignee(
            task_id=db_task.id,
            user_id=uid,
            consent_pending=(uid in consent_needed),
        ))

    await db.commit()
    await db.refresh(db_task)

    # Send notifications to assignees
    try:
        from app.notifications import notify_task_assigned, notify_consent_required
        from app.models.user import User as UserModel
        assigner_name = current_user.full_name or current_user.username
        for uid in assignee_ids:
            if uid == current_user.id:
                continue
            assignee_user = await db.get(UserModel, uid)
            if assignee_user:
                if uid in consent_needed:
                    await notify_consent_required(db_task, assignee_user, assigner_name)
                else:
                    await notify_task_assigned(db_task, assignee_user, assigner_name)
    except Exception as exc:
        logger.error("Notification error on task create (task_id=%s): %s", db_task.id, exc, exc_info=True)

    # D-17/D-18: Create chat rooms + send WS system_notification for each assignee
    task_title = db_task.title or f"Задача #{db_task.id}"
    task_org_id = org_id or current_user.org_id or 1
    for uid in assignee_ids:
        if uid == current_user.id:
            continue
        try:
            room_id = await _create_task_chat_room(
                db, current_user.id, uid, task_org_id,
                f"Задача: {task_title}",
            )
            await db.commit()
            subtype = "consent_request" if uid in consent_needed else "task_assigned"
            msg_text = (
                f"[СИСТЕМА] Запрос на назначение на задачу: «{task_title}»"
                if uid in consent_needed
                else f"[СИСТЕМА] Вам назначена задача: «{task_title}»"
            )
            await chat_manager.send_to_user(uid, {
                "type": "system_notification",
                "subtype": subtype,
                "task_id": db_task.id,
                "room_id": room_id,
                "message": msg_text,
                "link": "/my-tasks",
            })
        except Exception as exc:
            logger.error("Chat room/WS error on task assign (task_id=%s, uid=%s): %s", db_task.id, uid, exc)

    result = await _enrich_tasks([db_task], db, current_user_id=current_user.id)
    return result[0]


@router.patch("/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: int,
    task: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_task = await db.get(Task, task_id)
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Check if current user is an assignee
    assignee_check = (await db.execute(
        select(TaskAssignee).where(
            TaskAssignee.task_id == task_id,
            TaskAssignee.user_id == current_user.id,
        )
    )).scalar_one_or_none()
    is_assignee = assignee_check is not None

    from app.routers.departments import can_edit_task_of_user
    if current_user.id != db_task.created_by_id and not is_assignee:
        if not await can_edit_task_of_user(current_user, db_task.created_by_id, db):
            raise HTTPException(403, "Недостаточно прав для редактирования этой задачи")

    update_data = task.dict(exclude_unset=True)

    # Assignee cannot change protected fields
    PROTECTED_FIELDS = {"title", "description", "priority", "due_date", "assignee_ids"}
    is_creator = current_user.id == db_task.created_by_id
    if not is_creator and current_user.role not in ("superadmin", "account_owner", "admin"):
        blocked = PROTECTED_FIELDS & set(update_data.keys())
        if blocked:
            raise HTTPException(403, f"Исполнитель не может изменять: {', '.join(blocked)}")

    if "due_date" in update_data and update_data["due_date"]:
        due_val = update_data["due_date"]
        created_d = db_task.created_at.date() if db_task.created_at else date.today()
        due_d = due_val.date() if isinstance(due_val, datetime) else due_val
        if due_d < created_d:
            raise HTTPException(422, "Срок исполнения не может быть раньше даты создания задачи")

    # Handle assignee_ids separately
    new_assignee_ids = update_data.pop("assignee_ids", None)

    # Snapshot old values BEFORE changes (for change tracking)
    TRACKED_FIELDS = {"status", "priority", "due_date", "description", "title"}
    old_values = {f: getattr(db_task, f, None) for f in TRACKED_FIELDS}
    old_assignee_ids: set | None = None
    if new_assignee_ids is not None:
        old_assignee_ids = {
            a.user_id for a in (await db.execute(
                select(TaskAssignee).where(TaskAssignee.task_id == task_id)
            )).scalars().all()
        }

    # Assignee cannot move status backwards
    STATUS_ORDER = {"todo": 0, "in_progress": 1, "review": 2, "done": 3}
    old_status_str = db_task.status.value if hasattr(db_task.status, 'value') else str(db_task.status)
    if "status" in update_data and not is_creator and current_user.role not in ("superadmin", "account_owner", "admin"):
        new_status = update_data["status"]
        new_status_str = new_status.value if hasattr(new_status, 'value') else str(new_status)
        if STATUS_ORDER.get(new_status_str, 0) < STATUS_ORDER.get(old_status_str, 0):
            raise HTTPException(403, "Исполнитель не может переводить задачу назад по статусу")

    # If non-creator moves task to "done" → intercept to "review" (creator must confirm)
    req_status = update_data.get("status")
    req_status_str = req_status.value if hasattr(req_status, 'value') else str(req_status) if req_status else None
    if req_status_str == "done" and not is_creator and current_user.role not in ("superadmin", "account_owner", "admin"):
        update_data["status"] = TaskStatus.review
        req_status_str = "review"

    new_status_str = update_data.get("status")
    if new_status_str and hasattr(new_status_str, 'value'):
        new_status_str = new_status_str.value

    for key, value in update_data.items():
        setattr(db_task, key, value)

    consent_needed_update: set[int] = set()
    newly_added_ids: set[int] = set()

    if new_assignee_ids is not None:
        import sqlalchemy
        from app.auth.jwt import MANAGER_ROLES as _MR
        from app.models.user_hierarchy import UserHierarchy as _UH

        # Consent determined purely by hierarchy, not role
        can_assign_others = False
        newly_added_ids = set(new_assignee_ids) - (old_assignee_ids or set())
        if not can_assign_others and newly_added_ids:
            non_self = [uid for uid in newly_added_ids if uid != current_user.id]
            if non_self:
                hier_res = await db.execute(
                    select(_UH.subordinate_id).where(_UH.manager_id == current_user.id)
                )
                subordinate_ids = {r[0] for r in hier_res.all()}
                # Check ManagerOrganization
                from app.models.manager_organization import ManagerOrganization as _MO
                mo_res = await db.execute(
                    select(_MO.org_id).where(_MO.manager_user_id == current_user.id)
                )
                managed_org_ids = {r[0] for r in mo_res.all()}
                assignee_org_map = {}
                if managed_org_ids:
                    au_res = (await db.execute(select(User.id, User.org_id).where(User.id.in_(non_self)))).all()
                    assignee_org_map = {r[0]: r[1] for r in au_res}
                for uid in non_self:
                    if uid in subordinate_ids:
                        continue
                    if assignee_org_map.get(uid) in managed_org_ids:
                        continue
                    consent_needed_update.add(uid)

        await db.execute(
            sqlalchemy.delete(TaskAssignee).where(TaskAssignee.task_id == task_id)
        )
        for uid in new_assignee_ids:
            db.add(TaskAssignee(
                task_id=task_id,
                user_id=uid,
                consent_pending=(uid in consent_needed_update),
            ))
        if new_assignee_ids:
            db_task.assigned_user_id = new_assignee_ids[0]

    await db.commit()
    await db.refresh(db_task)

    # Record field changes for unseen tracking
    try:
        actor_name = current_user.full_name or current_user.username
        changes_to_add = []
        for f in TRACKED_FIELDS:
            if f in update_data:
                old_v = old_values.get(f)
                new_v = update_data.get(f)
                old_s = old_v.value if hasattr(old_v, 'value') else str(old_v) if old_v is not None else ''
                new_s = new_v.value if hasattr(new_v, 'value') else str(new_v) if new_v is not None else ''
                if old_s != new_s:
                    changes_to_add.append(TaskChange(
                        task_id=task_id, field_name=f,
                        changed_by_id=current_user.id, changed_by_name=actor_name,
                    ))
        if old_assignee_ids is not None:
            new_set = set(new_assignee_ids or [])
            if old_assignee_ids != new_set:
                changes_to_add.append(TaskChange(
                    task_id=task_id, field_name="assignees",
                    changed_by_id=current_user.id, changed_by_name=actor_name,
                ))
        if changes_to_add:
            for ch in changes_to_add:
                db.add(ch)
            await db.commit()
    except Exception as exc:
        logger.warning("task change tracking failed: %s", exc)

    # Notify newly added / removed assignees
    if newly_added_ids or (old_assignee_ids is not None and new_assignee_ids is not None):
        removed_ids = (old_assignee_ids or set()) - set(new_assignee_ids or []) if new_assignee_ids is not None else set()
        try:
            from app.notifications import notify_task_assigned, notify_consent_required, notify_user
            assigner_name = current_user.full_name or current_user.username
            # Added
            for uid in newly_added_ids:
                if uid == current_user.id:
                    continue
                assignee_user = await db.get(User, uid)
                if assignee_user:
                    if uid in consent_needed_update:
                        await notify_consent_required(db_task, assignee_user, assigner_name)
                    else:
                        await notify_task_assigned(db_task, assignee_user, assigner_name)
            # Removed
            for uid in removed_ids:
                if uid == current_user.id:
                    continue
                removed_user = await db.get(User, uid)
                if removed_user:
                    from app.notifications import _esc, _task_keyboard
                    msg = (
                        f"🚫 <b>Вас удалили из задачи</b>\n\n"
                        f"📌 <b>{_esc(db_task.title)}</b>\n"
                        f"👤 <i>{_esc(assigner_name)}</i>"
                    )
                    await notify_user(removed_user, msg)
        except Exception as exc:
            logger.error("Notification error on assignee update (task_id=%s): %s", task_id, exc, exc_info=True)

    # Notify all assignees about status change
    if new_status_str and new_status_str != old_status_str:
        try:
            from app.notifications import notify_task_status_changed
            from sqlalchemy.orm import selectinload as _sload
            task_r = await db.execute(
                select(Task).options(_sload(Task.assignees).selectinload(TaskAssignee.user)).where(Task.id == task_id)
            )
            task_full = task_r.scalar_one_or_none()
            if task_full:
                await notify_task_status_changed(
                    task_full, current_user.full_name or current_user.username,
                    new_status_str, current_user.id,
                )
        except Exception:
            pass
        # Notify creator if task sent for review
        if new_status_str == "review":
            try:
                creator = await db.get(User, db_task.created_by_id)
                if creator and creator.id != current_user.id:
                    from app.notifications import notify_user
                    actor = current_user.full_name or current_user.username
                    msg = f"✅ «{actor}» отметил задачу «{db_task.title}» как выполненную. Подтвердите или верните в работу."
                    await notify_user(creator, msg, task_id=db_task.id)
            except Exception:
                pass

    result = await _enrich_tasks([db_task], db)
    return result[0]


@router.post("/{task_id}/review-complete", response_model=TaskOut)
async def review_complete(
    task_id: int,
    body: ReviewCompleteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Создатель подтверждает (confirm=true→done) или отклоняет (confirm=false→in_progress) выполнение задачи."""
    db_task = await db.get(Task, task_id)
    if not db_task:
        raise HTTPException(404, "Задача не найдена")
    if db_task.created_by_id != current_user.id:
        raise HTTPException(403, "Только создатель задачи может подтвердить выполнение")
    if db_task.status not in (TaskStatus.review, "review"):
        raise HTTPException(400, "Задача не находится в статусе проверки")

    old_status = db_task.status.value if hasattr(db_task.status, 'value') else str(db_task.status)
    db_task.status = TaskStatus.done if body.confirm else TaskStatus.in_progress
    new_status = db_task.status.value
    await db.commit()
    await db.refresh(db_task)

    # Notify assignees about the decision
    try:
        from app.notifications import notify_task_status_changed
        from sqlalchemy.orm import selectinload as _sload
        task_r = await db.execute(
            select(Task).options(_sload(Task.assignees).selectinload(TaskAssignee.user)).where(Task.id == task_id)
        )
        task_full = task_r.scalar_one_or_none()
        if task_full:
            await notify_task_status_changed(
                task_full, current_user.full_name or current_user.username,
                new_status, current_user.id,
            )
    except Exception:
        pass

    result = await _enrich_tasks([db_task], db)
    return result[0]


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    t = await db.get(Task, task_id)
    if not t:
        raise HTTPException(404, "Задача не найдена")
    result = await _enrich_tasks([t], db)
    return result[0]


@router.get("/{task_id}/subtasks", response_model=List[TaskOut])
async def list_subtasks(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tasks = (await db.execute(
        select(Task).where(Task.parent_task_id == task_id)
        .order_by(Task.due_date.asc().nullslast(), Task.created_at.asc())
    )).scalars().all()
    return await _enrich_tasks(tasks, db)


@router.delete("/{task_id}")
async def delete_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_task = await db.get(Task, task_id)
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")
    await db.delete(db_task)
    await db.commit()
    return {"ok": True}


# ── Comments ─────────────────────────────────────────────────────────────────

@router.get("/{task_id}/comments", response_model=List[TaskCommentOut])
async def list_comments(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(404, "Задача не найдена")
    result = await db.execute(
        select(TaskComment)
        .where(TaskComment.task_id == task_id)
        .order_by(TaskComment.created_at.asc())
    )
    return result.scalars().all()


@router.post("/{task_id}/comments", response_model=TaskCommentOut)
async def add_comment(
    task_id: int,
    body: TaskCommentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(404, "Задача не найдена")
    if not body.text.strip():
        raise HTTPException(422, "Комментарий не может быть пустым")
    comment = TaskComment(
        task_id=task_id,
        user_id=current_user.id,
        user_name=current_user.full_name or current_user.username,
        text=body.text.strip(),
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)

    # Notify: mentioned users (@username) or all assignees
    try:
        import re as _re
        from app.notifications import notify_task_comment
        from sqlalchemy.orm import selectinload as _sload

        # Reload task with assignees
        task_r = await db.execute(
            select(Task).options(_sload(Task.assignees).selectinload(TaskAssignee.user)).where(Task.id == task_id)
        )
        task_full = task_r.scalar_one_or_none()

        # Find @mentions (match usernames or full names)
        mentions = _re.findall(r'@(\S+)', body.text)
        mentioned_users = []
        if mentions:
            all_users_r = await db.execute(select(User))
            all_users = all_users_r.scalars().all()
            for u in all_users:
                for m in mentions:
                    if (u.username and m.lower() == u.username.lower()) or \
                       (u.full_name and m.lower() in u.full_name.lower()):
                        if u.id != current_user.id:
                            mentioned_users.append(u)

        if task_full:
            await notify_task_comment(
                task_full,
                current_user.full_name or current_user.username,
                body.text.strip(),
                mentioned_users=mentioned_users if mentioned_users else None,
            )
    except Exception:
        pass

    return comment


@router.delete("/{task_id}/comments/{comment_id}")
async def delete_comment(
    task_id: int,
    comment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    comment = await db.get(TaskComment, comment_id)
    if not comment or comment.task_id != task_id:
        raise HTTPException(404, "Комментарий не найден")
    from app.auth.jwt import ADMIN_ROLES
    if comment.user_id != current_user.id and current_user.role not in ADMIN_ROLES:
        raise HTTPException(403, "Вы можете удалять только свои комментарии")
    await db.delete(comment)
    await db.commit()
    return {"ok": True}


# ── Department report ────────────────────────────────────────────────────────

@router.get("/report/by-department")
async def department_report(
    department: Optional[str] = None,
    weeks: int = Query(1, ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_ids = get_org_filter(current_user)

    user_q = select(User.id, User.full_name, User.username, User.department)
    if org_ids is not None:
        user_q = user_q.where(User.org_id.in_(org_ids))
    if department:
        user_q = user_q.where(User.department == department)
    else:
        user_q = user_q.where(User.department.isnot(None), User.department != "")
    user_rows = (await db.execute(user_q)).all()
    user_ids = [r.id for r in user_rows]
    user_names = {r.id: r.full_name or r.username for r in user_rows}
    user_depts = {r.id: r.department for r in user_rows}

    if not user_ids:
        return {"departments": [], "summary": {}}

    # Get tasks where any of these users is an assignee
    since = datetime.now(timezone.utc) - timedelta(weeks=weeks)
    assignee_task_ids = select(TaskAssignee.task_id).where(TaskAssignee.user_id.in_(user_ids)).scalar_subquery()
    tasks = (await db.execute(select(Task).where(Task.id.in_(assignee_task_ids)))).scalars().all()

    # Load assignees for dept report
    all_task_ids = [t.id for t in tasks]
    assignee_rows = (await db.execute(
        select(TaskAssignee).where(TaskAssignee.task_id.in_(all_task_ids))
    )).scalars().all()
    task_first_assignee = {}
    for a in assignee_rows:
        if a.task_id not in task_first_assignee and a.user_id in user_ids:
            task_first_assignee[a.task_id] = a.user_id

    departments: dict = {}
    for t in tasks:
        assignee_uid = task_first_assignee.get(t.id)
        dept = user_depts.get(assignee_uid, "Без отдела") if assignee_uid else "Без отдела"
        if dept not in departments:
            departments[dept] = {"done": [], "in_progress": [], "todo": [], "overdue": []}

        st = t.status.value if isinstance(t.status, TaskStatus) else t.status
        entry = {
            "id": t.id, "title": t.title,
            "priority": t.priority.value if isinstance(t.priority, TaskPriority) else t.priority,
            "due_date": t.due_date.isoformat() if t.due_date else None,
            "assigned_user": user_names.get(assignee_uid),
            "status": st,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        }

        if st == "done" and t.updated_at and t.updated_at >= since:
            departments[dept]["done"].append(entry)
        elif st == "in_progress":
            departments[dept]["in_progress"].append(entry)
            if t.due_date and t.due_date.date() < date.today():
                departments[dept]["overdue"].append(entry)
        elif st == "todo":
            departments[dept]["todo"].append(entry)

    result = []
    for dept_name, groups in sorted(departments.items()):
        result.append({
            "department": dept_name,
            "done_count": len(groups["done"]),
            "in_progress_count": len(groups["in_progress"]),
            "todo_count": len(groups["todo"]),
            "overdue_count": len(groups["overdue"]),
            "done": groups["done"], "in_progress": groups["in_progress"],
            "todo": groups["todo"], "overdue": groups["overdue"],
        })

    summary = {
        "total_done": sum(len(d["done"]) for d in departments.values()),
        "total_in_progress": sum(len(d["in_progress"]) for d in departments.values()),
        "total_todo": sum(len(d["todo"]) for d in departments.values()),
        "total_overdue": sum(len(d["overdue"]) for d in departments.values()),
        "period_weeks": weeks,
    }

    return {"departments": result, "summary": summary}


# ── Broadcast (рассылка) ─────────────────────────────────────────────────────

@router.post("/{task_id}/broadcast")
async def broadcast_from_task(
    task_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send a message from task context to selected scope: department / org / all.
    Requires admin+ role. 'all' scope requires superadmin."""
    from app.models.organization import Organization
    from app.models.department import Department, DepartmentMember
    from app.notifications import notify_user, _task_url

    BROADCAST_ROLES = ("superadmin", "org_admin", "admin", "manager")
    if current_user.role not in BROADCAST_ROLES:
        raise HTTPException(403, "Рассылка доступна только администраторам и менеджерам")

    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(404, "Задача не найдена")

    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(422, "Текст сообщения обязателен")

    scope = body.get("scope", "")  # "department", "organization", "all"
    scope_id = body.get("scope_id")  # department_id or org_id

    # Build user query
    q = select(User).where(User.id != current_user.id)

    if scope == "department" and scope_id:
        member_uids = select(DepartmentMember.user_id).where(DepartmentMember.department_id == int(scope_id))
        q = q.where(User.id.in_(member_uids))
    elif scope == "organization" and scope_id:
        q = q.where(User.org_id == int(scope_id))
    elif scope == "all":
        # org_admin/admin — only their org tree; superadmin — everyone
        org_ids = get_org_filter(current_user)
        if org_ids is not None:
            q = q.where(User.org_id.in_(org_ids))
    else:
        raise HTTPException(422, "Укажите scope: department, organization или all")

    users = (await db.execute(q)).scalars().all()

    # Build notification
    from app.notifications import _esc
    sender_name = current_user.full_name or current_user.username
    msg = (
        f"📢 <b>Рассылка</b>\n\n"
        f"📌 <b>{_esc(task.title)}</b>\n"
        f"👤 <i>{_esc(sender_name)}</i>:\n"
        f"{_esc(text)}"
    )

    sent = 0
    for u in users:
        tg = getattr(u, "telegram_id", None)
        mx = getattr(u, "max_chat_id", None)
        if tg or mx:
            await notify_user(u, msg, task_id=task.id,
                               button_url=_task_url(task.id), button_label="Перейти к задаче")
            sent += 1

    # Also save as comment
    from app.models.task_comment import TaskComment
    scope_label = {"department": "отделу", "organization": "организации", "all": "всем"}.get(scope, scope)
    db.add(TaskComment(
        task_id=task_id,
        user_id=current_user.id,
        user_name=sender_name,
        text=f"[Рассылка {scope_label}] {text}",
    ))
    await db.commit()

    return {"ok": True, "sent": sent, "total_users": len(users)}


# ── Dismiss field change ──────────────────────────────────────────────────────

@router.post("/{task_id}/dismiss-field")
async def dismiss_field(
    task_id: int,
    body: DismissFieldRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark a specific changed field as seen (dismiss its highlight) for current user."""
    existing = (await db.execute(
        select(TaskFieldSeen).where(
            TaskFieldSeen.user_id == current_user.id,
            TaskFieldSeen.task_id == task_id,
            TaskFieldSeen.field_name == body.field_name,
        )
    )).scalar_one_or_none()

    if existing:
        existing.dismissed_at = func.now()
    else:
        db.add(TaskFieldSeen(
            user_id=current_user.id,
            task_id=task_id,
            field_name=body.field_name,
        ))

    await db.commit()
    return {"ok": True}


@router.get("/broadcast/scopes")
async def broadcast_scopes(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get available broadcast scopes: departments and organizations."""
    from app.models.organization import Organization
    from app.models.department import Department

    orgs = []
    depts = []

    org_ids = get_org_filter(current_user)
    if org_ids is None:
        # superadmin — all orgs
        res = await db.execute(select(Organization).where(Organization.is_active == True))
        orgs = [{"id": o.id, "name": o.name} for o in res.scalars().all()]
        dept_q = select(Department)
    else:
        res = await db.execute(select(Organization).where(Organization.id.in_(org_ids)))
        orgs = [{"id": o.id, "name": o.name} for o in res.scalars().all()]
        dept_q = select(Department).where(Department.org_id.in_(org_ids))

    res2 = await db.execute(dept_q.order_by(Department.name))
    depts = [{"id": d.id, "name": d.name, "org_id": d.org_id} for d in res2.scalars().all()]

    return {"organizations": orgs, "departments": depts}
