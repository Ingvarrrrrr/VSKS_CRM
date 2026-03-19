from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.task import Task, TaskStatus, TaskPriority, TaskAssignee
from app.models.task_decline import TaskConsentDecline
from app.models.task_comment import TaskComment
from app.models.user import User
from app.schemas.schemas import (
    TaskCreate, TaskUpdate, TaskOut, TaskAssigneeOut,
    TaskCommentCreate, TaskCommentOut,
)
from app.auth.jwt import get_current_user, get_org_filter
from typing import List, Optional
from datetime import date, datetime, timezone, timedelta

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
        out.append(TaskOut(
            id=t.id, title=t.title, description=t.description,
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
            import_to_parent=t.import_to_parent,
            subtask_count=subtask_map.get(t.id, 0),
            created_at=t.created_at, updated_at=t.updated_at,
            last_comment=lc.get("text"),
            last_comment_user=lc.get("user"),
            last_comment_at=lc.get("at"),
            comment_count=count_map.get(t.id, 0),
            needs_my_consent=needs_my_consent,
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
        q = q.where(or_(
            Task.title.ilike(f"%{search}%"),
            Task.description.ilike(f"%{search}%"),
        ))

    q = q.order_by(Task.due_date.asc().nullslast(), Task.created_at.desc())
    tasks = (await db.execute(q)).scalars().all()
    return await _enrich_tasks(tasks, db)


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
        Task.status.notin_([TaskStatus.done, TaskStatus.cancelled]),
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
    can_assign_others = current_user.role in _MR

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
            for uid in non_self:
                if uid not in subordinate_ids:
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
        import_to_parent=task.import_to_parent,
    )
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
    except Exception:
        pass  # notifications are best-effort

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
    if not is_creator and current_user.role not in ("superadmin", "org_admin", "admin"):
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

    # Assignee cannot move status backwards
    STATUS_ORDER = {"todo": 0, "in_progress": 1, "done": 2}
    if "status" in update_data and not is_creator and current_user.role not in ("superadmin", "org_admin", "admin"):
        new_status = update_data["status"]
        new_status_str = new_status.value if hasattr(new_status, 'value') else str(new_status)
        old_status_str = db_task.status.value if hasattr(db_task.status, 'value') else str(db_task.status)
        if STATUS_ORDER.get(new_status_str, 0) < STATUS_ORDER.get(old_status_str, 0):
            raise HTTPException(403, "Исполнитель не может переводить задачу назад по статусу")

    for key, value in update_data.items():
        setattr(db_task, key, value)

    if new_assignee_ids is not None:
        import sqlalchemy
        await db.execute(
            sqlalchemy.delete(TaskAssignee).where(TaskAssignee.task_id == task_id)
        )
        for uid in new_assignee_ids:
            db.add(TaskAssignee(task_id=task_id, user_id=uid))
        if new_assignee_ids:
            db_task.assigned_user_id = new_assignee_ids[0]

    await db.commit()
    await db.refresh(db_task)

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
