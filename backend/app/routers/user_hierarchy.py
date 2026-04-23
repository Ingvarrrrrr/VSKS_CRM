"""
User hierarchy management.

Endpoints:
  GET    /api/users/{uid}/subordinates     — list all direct subordinates
  GET    /api/users/{uid}/subordinates/all — recursive (all levels)
  POST   /api/users/{uid}/subordinates     — add subordinate
  DELETE /api/users/{uid}/subordinates/{sid} — remove

Hierarchy-aware purchases filter:
  GET /api/purchases/?managed_by={uid} returns purchases where
  creator or any member is in uid's recursive subordinates (+ uid itself).
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from app.auth.jwt import get_current_user, require_role
from app.auth.permissions import require_tab
from app.database import get_db
from app.models.user import User
from app.models.user_hierarchy import UserHierarchy

router = APIRouter(prefix="/api/users", tags=["user-hierarchy"])


class SubordinateOut(BaseModel):
    id: int
    username: str
    full_name: str | None = None
    role: str


class AddSubordinateBody(BaseModel):
    subordinate_id: int


async def get_all_subordinate_ids(manager_id: int, db: AsyncSession) -> list[int]:
    """Recursive CTE to get all subordinate user IDs at any depth."""
    result = await db.execute(
        text("""
        WITH RECURSIVE hier AS (
            SELECT subordinate_id FROM user_hierarchy WHERE manager_id = :mid
            UNION ALL
            SELECT uh.subordinate_id FROM user_hierarchy uh
            INNER JOIN hier ON uh.manager_id = hier.subordinate_id
        )
        SELECT subordinate_id FROM hier
        """),
        {"mid": manager_id},
    )
    return [row[0] for row in result.fetchall()]


@router.get("/{uid}/subordinates", response_model=List[SubordinateOut])
async def list_subordinates(
    uid: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    rows = (await db.execute(
        select(UserHierarchy).where(UserHierarchy.manager_id == uid)
    )).scalars().all()
    return [SubordinateOut(
        id=r.subordinate.id,
        username=r.subordinate.username,
        full_name=r.subordinate.full_name,
        role=r.subordinate.role,
    ) for r in rows]


@router.get("/{uid}/subordinates/all", response_model=List[SubordinateOut])
async def list_all_subordinates(
    uid: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    ids = await get_all_subordinate_ids(uid, db)
    if not ids:
        return []
    users = (await db.execute(select(User).where(User.id.in_(ids)))).scalars().all()
    return [SubordinateOut(id=u.id, username=u.username, full_name=u.full_name, role=u.role) for u in users]


@router.post("/{uid}/subordinates", response_model=SubordinateOut)
async def add_subordinate(
    uid: int,
    body: AddSubordinateBody,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab('staff')),
):
    if uid == body.subordinate_id:
        raise HTTPException(400, "Пользователь не может быть подчинённым самого себя")
    # prevent cycles: check if uid is already subordinate of body.subordinate_id
    ids = await get_all_subordinate_ids(body.subordinate_id, db)
    if uid in ids:
        raise HTTPException(400, "Создаст цикл в иерархии")

    manager = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    subordinate = (await db.execute(select(User).where(User.id == body.subordinate_id))).scalar_one_or_none()
    if not manager or not subordinate:
        raise HTTPException(404, "Пользователь не найден")

    existing = (await db.execute(
        select(UserHierarchy).where(
            UserHierarchy.manager_id == uid,
            UserHierarchy.subordinate_id == body.subordinate_id,
        )
    )).scalar_one_or_none()
    if not existing:
        db.add(UserHierarchy(manager_id=uid, subordinate_id=body.subordinate_id))
        await db.commit()
    return SubordinateOut(id=subordinate.id, username=subordinate.username,
                          full_name=subordinate.full_name, role=subordinate.role)


@router.delete("/{uid}/subordinates/{sid}", status_code=204)
async def remove_subordinate(
    uid: int,
    sid: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab('staff')),
):
    h = (await db.execute(
        select(UserHierarchy).where(
            UserHierarchy.manager_id == uid,
            UserHierarchy.subordinate_id == sid,
        )
    )).scalar_one_or_none()
    if h:
        await db.delete(h)
        await db.commit()
