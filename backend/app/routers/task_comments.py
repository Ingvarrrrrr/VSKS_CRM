"""
task_comments.py — Comments, broadcast, and dismiss-field endpoints for tasks.

Extracted from tasks.py per refactor Plan 16-08 (D-13).

Endpoints
---------
GET  /{task_id}/comments                — list comments for a task
POST /{task_id}/comments                — add comment (with @mention notifications)
DELETE /{task_id}/comments/{comment_id} — delete comment
POST /{task_id}/broadcast               — send broadcast message from task context
POST /{task_id}/dismiss-field           — mark a changed field as seen for current user
GET  /broadcast/scopes                  — list available broadcast scopes (orgs + depts)

Design decisions
----------------
- D-13: comments/broadcast/dismiss-field cluster extracted to own module.
- Imports from task_visibility (no circular deps — task_visibility has no router).
- auth.jwt.ADMIN_ROLES used for comment deletion permission check.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.database import get_db
from app.models.task import Task, TaskAssignee
from app.models.task_comment import TaskComment
from app.models.task_change import TaskFieldSeen
from app.models.user import User
from app.schemas.schemas import (
    TaskCommentCreate, TaskCommentOut, DismissFieldRequest,
)
from app.auth.jwt import get_current_user, get_org_filter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["task-comments"])


# ── Comments ──────────────────────────────────────────────────────────────────

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
            all_users_r = await db.execute(select(User))  # superadmin-bypass-ok: @mention lookup for notifications, not a user-list endpoint
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


# ── Broadcast (рассылка) ──────────────────────────────────────────────────────

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
    q = select(User).where(User.id != current_user.id)  # superadmin-bypass-ok: broadcast notifications, not a user-list endpoint returned to client

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
    from app.models.task_comment import TaskComment as _TC
    scope_label = {"department": "отделу", "organization": "организации", "all": "всем"}.get(scope, scope)
    db.add(_TC(
        task_id=task_id,
        user_id=current_user.id,
        user_name=sender_name,
        text=f"[Рассылка {scope_label}] {text}",
    ))
    await db.commit()

    return {"ok": True, "sent": sent, "total_users": len(users)}


# ── Dismiss field change ───────────────────────────────────────────────────────

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


# ── Broadcast scopes ──────────────────────────────────────────────────────────

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
