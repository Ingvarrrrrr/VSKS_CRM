"""
task_reports.py — Reporting endpoints for tasks.

Contains GET /api/tasks/report/by-department endpoint extracted from tasks.py
per refactor Plan 16-11 (D-09 finalization — slim tasks.py to ≤500 lines).

Uses prefix /api/tasks to keep the same URL path.
Registered in backend/app/__init__.py alongside other task_* sub-routers.
"""
import logging
from datetime import date, datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.task import Task, TaskStatus, TaskPriority, TaskAssignee
from app.models.user import User
from app.auth.jwt import get_current_user, get_org_filter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["task-reports"])


# ── Department report ─────────────────────────────────────────────────────────

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
