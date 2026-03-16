from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_, func, case, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.task import Task, TaskStatus, TaskPriority
from app.models.task_comment import TaskComment
from app.models.user import User
from app.schemas.schemas import (
    TaskCreate, TaskUpdate, TaskOut,
    TaskCommentCreate, TaskCommentOut,
)
from app.auth.jwt import get_current_user, get_org_filter
from typing import List, Optional
from datetime import date, datetime, timezone, timedelta

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


# ── helpers ──────────────────────────────────────────────────────────────────

async def _enrich_tasks(tasks: list, db: AsyncSession) -> List[TaskOut]:
    """Build TaskOut list with user names and last comment preview."""
    if not tasks:
        return []

    task_ids = [t.id for t in tasks]

    # User names
    user_ids = set()
    for t in tasks:
        if t.assigned_user_id:
            user_ids.add(t.assigned_user_id)
        user_ids.add(t.created_by_id)
    users_map = {}
    if user_ids:
        res = await db.execute(select(User).where(User.id.in_(user_ids)))
        for u in res.scalars().all():
            users_map[u.id] = u.full_name or u.username

    # Comment counts
    count_q = (
        select(TaskComment.task_id, func.count(TaskComment.id).label("cnt"))
        .where(TaskComment.task_id.in_(task_ids))
        .group_by(TaskComment.task_id)
    )
    count_rows = (await db.execute(count_q)).all()
    count_map = {r.task_id: r.cnt for r in count_rows}

    # Last comment per task (using lateral / window)
    from sqlalchemy import text
    last_comments_map = {}
    if task_ids:
        # Simple approach: get latest comment per task
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
        last_q = select(subq).where(subq.c.rn == 1)
        for row in (await db.execute(last_q)).all():
            last_comments_map[row.task_id] = {
                "text": row.text[:100] if row.text else None,
                "user": row.user_name,
                "at": row.created_at,
            }

    out = []
    for t in tasks:
        lc = last_comments_map.get(t.id, {})
        out.append(TaskOut(
            id=t.id, title=t.title, description=t.description,
            status=t.status.value if isinstance(t.status, TaskStatus) else t.status,
            priority=t.priority.value if isinstance(t.priority, TaskPriority) else t.priority,
            due_date=t.due_date,
            assigned_user_id=t.assigned_user_id,
            assigned_user_name=users_map.get(t.assigned_user_id),
            created_by_id=t.created_by_id,
            created_by_name=users_map.get(t.created_by_id),
            org_id=t.org_id, category=t.category,
            created_at=t.created_at, updated_at=t.updated_at,
            last_comment=lc.get("text"),
            last_comment_user=lc.get("user"),
            last_comment_at=lc.get("at"),
            comment_count=count_map.get(t.id, 0),
        ))
    return out


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
        q = q.where(Task.assigned_user_id == current_user.id)
    if created_by_me:
        q = q.where(Task.created_by_id == current_user.id)
    if category:
        q = q.where(Task.category == category)
    if department:
        # Filter tasks assigned to users in a specific department
        dept_users = select(User.id).where(User.department == department).scalar_subquery()
        q = q.where(Task.assigned_user_id.in_(dept_users))
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
    """Задачи назначенные мне или созданные мной."""
    q = select(Task).where(
        or_(
            Task.assigned_user_id == current_user.id,
            Task.created_by_id == current_user.id,
        ),
        Task.status.notin_([TaskStatus.done, TaskStatus.cancelled]),
    ).order_by(Task.due_date.asc().nullslast(), Task.created_at.desc())

    tasks = (await db.execute(q)).scalars().all()
    return await _enrich_tasks(tasks, db)


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
    """Список всех отделов в организации."""
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
    from app.auth.jwt import get_single_org_id

    # Validate due_date >= today
    if task.due_date:
        today = date.today()
        due_d = task.due_date.date() if isinstance(task.due_date, datetime) else task.due_date
        if due_d < today:
            raise HTTPException(422, "Срок исполнения не может быть раньше текущей даты")

    org_id = get_single_org_id(current_user)

    # Только manager и выше может назначать задачи другим; employee — только себе
    from app.auth.jwt import MANAGER_ROLES as _MR
    effective_assignee = (
        task.assigned_user_id if current_user.role in _MR else current_user.id
    )

    db_task = Task(
        title=task.title,
        description=task.description,
        priority=task.priority,
        due_date=task.due_date,
        assigned_user_id=effective_assignee,
        created_by_id=current_user.id,
        org_id=org_id,
        category=task.category,
    )
    db.add(db_task)
    await db.commit()
    await db.refresh(db_task)

    result = await _enrich_tasks([db_task], db)
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

    # Permission check: owner, admin, department head, or delegate
    from app.routers.departments import can_edit_task_of_user
    target_id = db_task.assigned_user_id or db_task.created_by_id
    if current_user.id != db_task.created_by_id and current_user.id != db_task.assigned_user_id:
        if not await can_edit_task_of_user(current_user, target_id, db):
            raise HTTPException(403, "Недостаточно прав для редактирования этой задачи")

    update_data = task.dict(exclude_unset=True)

    # Validate due_date >= created_at date
    if "due_date" in update_data and update_data["due_date"]:
        due_val = update_data["due_date"]
        created_d = db_task.created_at.date() if db_task.created_at else date.today()
        due_d = due_val.date() if isinstance(due_val, datetime) else due_val
        if due_d < created_d:
            raise HTTPException(422, "Срок исполнения не может быть раньше даты создания задачи")

    for key, value in update_data.items():
        setattr(db_task, key, value)

    await db.commit()
    await db.refresh(db_task)

    result = await _enrich_tasks([db_task], db)
    return result[0]


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
    # Only author or admin can delete
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
    """
    Отчёт по отделу: выполненные задачи за N недель, в работе, планируются.
    Если department не указан — по всем отделам.
    """
    org_ids = get_org_filter(current_user)

    # Get users in department(s)
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

    # Fetch tasks assigned to these users
    since = datetime.now(timezone.utc) - timedelta(weeks=weeks)
    tasks_q = select(Task).where(Task.assigned_user_id.in_(user_ids))
    tasks = (await db.execute(tasks_q)).scalars().all()

    # Group by department
    departments: dict = {}
    for t in tasks:
        dept = user_depts.get(t.assigned_user_id, "Без отдела")
        if dept not in departments:
            departments[dept] = {"done": [], "in_progress": [], "todo": [], "overdue": []}

        st = t.status.value if isinstance(t.status, TaskStatus) else t.status
        entry = {
            "id": t.id,
            "title": t.title,
            "priority": t.priority.value if isinstance(t.priority, TaskPriority) else t.priority,
            "due_date": t.due_date.isoformat() if t.due_date else None,
            "assigned_user": user_names.get(t.assigned_user_id),
            "status": st,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        }

        if st == "done" and t.updated_at and t.updated_at >= since:
            departments[dept]["done"].append(entry)
        elif st == "in_progress":
            departments[dept]["in_progress"].append(entry)
            # Check overdue
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
            "done": groups["done"],
            "in_progress": groups["in_progress"],
            "todo": groups["todo"],
            "overdue": groups["overdue"],
        })

    summary = {
        "total_done": sum(len(d["done"]) for d in departments.values()),
        "total_in_progress": sum(len(d["in_progress"]) for d in departments.values()),
        "total_todo": sum(len(d["todo"]) for d in departments.values()),
        "total_overdue": sum(len(d["overdue"]) for d in departments.values()),
        "period_weeks": weeks,
    }

    return {"departments": result, "summary": summary}
