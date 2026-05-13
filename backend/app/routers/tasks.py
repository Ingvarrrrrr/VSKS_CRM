import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.task import Task, TaskStatus, TaskPriority, TaskAssignee
from app.models.task_comment import TaskComment
from app.models.task_change import TaskChange
from app.models.user import User
from app.schemas.schemas import (
    TaskCreate, TaskUpdate, TaskOut, TaskAssigneeOut,
    ReviewCompleteRequest,
)
from app.auth.jwt import get_current_user, get_org_filter
from typing import List, Optional
from datetime import date, datetime
from app.chat_manager import manager as chat_manager
from app.models.chat_room import ChatRoom, ChatParticipant
from app.models.chat_message import ChatMessage
from app.auth.visibility import build_visibility_clause

logger = logging.getLogger(__name__)

from app.routers.task_visibility import _get_visible_user_ids, _enrich_tasks, _create_task_chat_room
from app.routers.task_delegation import _set_assignees  # noqa: F401 — used by create/update

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


# ── CRUD ─────────────────────────────────────────────────────────────────────

@router.get("/", response_model=List[TaskOut])
async def list_tasks(
    status: Optional[str] = None,
    assigned_to_me: bool = False,
    created_by_me: bool = False,
    category: Optional[str] = None,
    department: Optional[str] = None,
    search: Optional[str] = None,
    org_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(Task)

    org_ids = get_org_filter(current_user)
    if org_id is not None:
        q = q.where(Task.org_id == org_id)
    elif org_ids is not None:
        q = q.where(Task.org_id.in_(org_ids))

    # Phase 28 Bundle 2B: unified visibility helper replaces inline logic.
    clause = await build_visibility_clause(current_user, db, 'task')
    if clause is not None:
        q = q.where(clause)

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

# department_report moved to task_reports.py (Plan 16-11)

