"""
task_delegation.py — Task consent/delegation endpoints + _set_assignees helper.

Extracted from tasks.py per refactor Plan 16-10 (D-12).

Endpoints
---------
GET  /api/tasks/pending-consent                     — tasks awaiting current user's consent
POST /api/tasks/{task_id}/consent                   — accept or decline a consent request
GET  /api/tasks/consent-declines                    — unread decline notifications for creator
POST /api/tasks/consent-declines/{decline_id}/acknowledge — mark notification as read

Helpers (importable)
--------------------
_set_assignees   — replaces all assignees for a task (used by tasks.py CRUD create/update)

Downstream consumers
--------------------
- app.routers.tasks   (CRUD create/update import _set_assignees back)
- backend/app/__init__.py  (include_router)
"""
import logging
import sqlalchemy
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.database import get_db
from app.models.task import Task, TaskAssignee
from app.models.task_decline import TaskConsentDecline
from app.models.user import User
from app.auth.jwt import get_current_user
from app.routers.task_visibility import _enrich_tasks, _create_task_chat_room
from app.chat_manager import manager as chat_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["task-delegation"])


# ── Helper ────────────────────────────────────────────────────────────────────

async def _set_assignees(task_id: int, assignee_ids: List[int], db: AsyncSession):
    """Replace all assignees for a task."""
    await db.execute(
        sqlalchemy.delete(TaskAssignee).where(TaskAssignee.task_id == task_id)
    )
    for uid in assignee_ids:
        db.add(TaskAssignee(task_id=task_id, user_id=uid))


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/pending-consent", response_model=List)
async def pending_consent_tasks(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Задачи, назначенные мне, но ожидающие моего согласия.

    Returns the list of tasks where the current user is an assignee with
    consent_pending=True.  Used by the MyTasksView badge and the consent
    modal in the frontend.

    Response shape: List[TaskOut] (same as GET /api/tasks/).
    """
    pending_ids = select(TaskAssignee.task_id).where(
        TaskAssignee.user_id == current_user.id,
        TaskAssignee.consent_pending == True,  # noqa: E712
    ).scalar_subquery()
    q = select(Task).where(Task.id.in_(pending_ids)).order_by(Task.created_at.desc())
    tasks = (await db.execute(q)).scalars().all()
    return await _enrich_tasks(tasks, db, current_user_id=current_user.id)


@router.post("/{task_id}/consent")
async def respond_task_consent(
    task_id: int,
    accept: bool = Query(..., description="true=принять, false=отклонить"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Принять или отклонить задачу, ожидающую согласия.

    accept=true:
      - Clears consent_pending flag on the TaskAssignee row.
      - Records an is_accepted=True TaskConsentDecline for the creator.
      - Sends a Telegram notification to the task creator.
      - Creates (or reuses) a task chat room (D-18) and sends a WS
        system_notification to the accepting user.

    accept=false:
      - Removes the TaskAssignee row entirely.
      - Records a TaskConsentDecline for the creator so they can see who
        declined and re-assign if needed.
      - Sends a Telegram notification to the task creator.

    Returns TaskOut for the task (same shape as GET /api/tasks/{id}).
    Raises 404 if the task or pending consent row is not found.
    """
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
    """Непрочитанные уведомления об отклонённых назначениях (для постановщика).

    Returns all unacknowledged TaskConsentDecline rows where creator_id matches
    the current user.  Each entry includes both accepted and declined consent
    responses so the creator can track who confirmed and who declined.

    Response shape: list of dicts with keys:
      id, task_id, task_title, declined_by_name, is_accepted, created_at.
    """
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
    """Подтвердить получение уведомления об отклонении.

    Sets acknowledged=True on the TaskConsentDecline row.  Only the task
    creator (row.creator_id) may acknowledge their own notifications.

    Returns {"ok": True} on success.
    Raises 404 if the decline row is not found or belongs to another user.
    """
    row = await db.get(TaskConsentDecline, decline_id)
    if not row or row.creator_id != current_user.id:
        raise HTTPException(404, "Уведомление не найдено")
    row.acknowledged = True
    await db.commit()
    return {"ok": True}
