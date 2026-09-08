"""Делегирование права редактировать чужие задачи (вынесено из
departments.py, Правило №5, сессия 2026-09-08 — см. докстринг
departments.py). Проверка самого права — ``can_edit_task_of_user`` осталась
в ядре ``app/routers/departments.py`` (внешний потребитель tasks.py
импортирует её оттуда, путь не менялся).

Регистрируется на том же префиксе ``/api/departments`` рядом с ядром;
``/delegates`` и ``/delegates/{delegate_id}`` не пересекаются по
путь+метод с catch-all ``/{dept_id}`` (тот несёт только PATCH/DELETE),
порядок регистрации относительно ядра значения не имеет.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user, get_org_filter, get_single_org_id
from app.auth.permissions import require_tab
from app.database import get_db
from app.models.department import TaskEditDelegate
from app.models.user import User
from app.routers.departments import DelegateAdd, DelegateOut

router = APIRouter(prefix="/api/departments", tags=["departments"])


# ── Task Edit Delegates ──────────────────────────────────────────────────────

@router.get("/delegates", response_model=List[DelegateOut])
async def list_delegates(
    target_user_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(TaskEditDelegate)
    org_ids = get_org_filter(current_user)
    if org_ids is not None:
        q = q.where(TaskEditDelegate.org_id.in_(org_ids))
    if target_user_id is not None:
        q = q.where(TaskEditDelegate.target_user_id == target_user_id)
    rows = (await db.execute(q)).scalars().all()
    user_ids = set()
    for r in rows:
        user_ids.add(r.target_user_id)
        user_ids.add(r.delegate_user_id)
    users_map = {}
    if user_ids:
        for u in (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all():  # superadmin-bypass-ok: lookup by pre-computed IDs for delegate enrichment
            users_map[u.id] = u.full_name or u.username
    return [
        DelegateOut(
            id=r.id,
            target_user_id=r.target_user_id,
            target_user_name=users_map.get(r.target_user_id),
            delegate_user_id=r.delegate_user_id,
            delegate_user_name=users_map.get(r.delegate_user_id),
        )
        for r in rows
    ]


@router.post("/delegates", response_model=DelegateOut)
async def add_delegate(
    data: DelegateAdd,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab('staff')),
):
    org_id = get_single_org_id(current_user) or current_user.org_id
    existing = (await db.execute(
        select(TaskEditDelegate).where(
            TaskEditDelegate.target_user_id == data.target_user_id,
            TaskEditDelegate.delegate_user_id == data.delegate_user_id,
        )
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "Такое делегирование уже существует")
    d = TaskEditDelegate(
        target_user_id=data.target_user_id,
        delegate_user_id=data.delegate_user_id,
        org_id=org_id,
    )
    db.add(d)
    await db.commit()
    await db.refresh(d)
    users_map = {}
    for uid in (data.target_user_id, data.delegate_user_id):
        u = await db.get(User, uid)
        if u:
            users_map[uid] = u.full_name or u.username
    return DelegateOut(
        id=d.id,
        target_user_id=d.target_user_id,
        target_user_name=users_map.get(d.target_user_id),
        delegate_user_id=d.delegate_user_id,
        delegate_user_name=users_map.get(d.delegate_user_id),
    )


@router.delete("/delegates/{delegate_id}")
async def remove_delegate(
    delegate_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab('staff')),
):
    d = await db.get(TaskEditDelegate, delegate_id)
    if not d:
        raise HTTPException(404, "Делегирование не найдено")
    await db.delete(d)
    await db.commit()
    return {"ok": True}
