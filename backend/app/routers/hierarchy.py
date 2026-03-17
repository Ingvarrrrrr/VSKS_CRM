"""
Hierarchy graph management.

Endpoints:
  GET    /api/hierarchy/graph         — full graph for canvas
  POST   /api/hierarchy/edges         — create edge (user_user | user_dept)
  DELETE /api/hierarchy/edges/{id}    — remove edge
  GET    /api/users/{uid}/task-authority — who this user can assign tasks to and who can assign to them
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user, require_role, get_org_filter, ADMIN_ROLES
from app.database import get_db
from app.models.department import Department, DepartmentMember
from app.models.manager_department import ManagerDepartment
from app.models.organization import Organization
from app.models.user import User
from app.models.user_hierarchy import UserHierarchy

router = APIRouter(tags=["hierarchy"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class EdgeCreate(BaseModel):
    type: str  # "user_user" | "user_dept"
    source_id: int
    target_id: int


class EdgeOut(BaseModel):
    id: int
    type: str


class OkOut(BaseModel):
    ok: bool


class OrgOut(BaseModel):
    id: int
    name: str


class DeptGraphOut(BaseModel):
    id: int
    name: str
    org_id: int
    head_user_id: Optional[int]
    member_ids: List[int]


class UserGraphOut(BaseModel):
    id: int
    full_name: Optional[str]
    username: str
    role: str
    org_id: Optional[int]
    avatar: Optional[str]
    position: Optional[str] = None


class UserUserEdgeOut(BaseModel):
    id: int
    manager_id: int
    subordinate_id: int


class UserDeptEdgeOut(BaseModel):
    id: int
    manager_user_id: int
    dept_id: int


class GraphOut(BaseModel):
    orgs: List[OrgOut]
    departments: List[DeptGraphOut]
    users: List[UserGraphOut]
    user_user_edges: List[UserUserEdgeOut]
    user_dept_edges: List[UserDeptEdgeOut]


class TaskAuthorityUserOut(BaseModel):
    id: int
    full_name: Optional[str]
    username: str
    role: str


class TaskAuthorityOut(BaseModel):
    can_assign_to: List[TaskAuthorityUserOut]
    can_receive_from: List[TaskAuthorityUserOut]


# ── Graph endpoint ─────────────────────────────────────────────────────────────

@router.get("/api/hierarchy/graph", response_model=GraphOut)
async def get_hierarchy_graph(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_ids = get_org_filter(current_user)

    # Load orgs
    q_orgs = select(Organization)
    if org_ids is not None:
        q_orgs = q_orgs.where(Organization.id.in_(org_ids))
    orgs = (await db.execute(q_orgs)).scalars().all()
    org_id_set = {o.id for o in orgs}

    # Load departments
    q_depts = select(Department)
    if org_ids is not None:
        q_depts = q_depts.where(Department.org_id.in_(org_ids))
    depts = (await db.execute(q_depts)).scalars().all()
    dept_ids = [d.id for d in depts]

    # Load dept members
    members_map: dict[int, list[int]] = {d.id: [] for d in depts}
    user_position_map: dict[int, str] = {}  # user_id -> position from DepartmentMember
    if dept_ids:
        members = (await db.execute(
            select(DepartmentMember).where(DepartmentMember.department_id.in_(dept_ids))
        )).scalars().all()
        for m in members:
            if m.department_id in members_map:
                members_map[m.department_id].append(m.user_id)
            if m.position:
                user_position_map[m.user_id] = m.position
    # Also ensure dept head is always in member_ids
    for d in depts:
        if d.head_user_id and d.head_user_id not in members_map.get(d.id, []):
            members_map[d.id].append(d.head_user_id)

    # Load users
    q_users = select(User)
    if org_ids is not None:
        q_users = q_users.where(User.org_id.in_(org_ids))
    users = (await db.execute(q_users)).scalars().all()

    # Load user-user edges (only within our org)
    user_ids = {u.id for u in users}
    uu_edges = []
    if user_ids:
        rows = (await db.execute(
            select(UserHierarchy).where(
                UserHierarchy.manager_id.in_(user_ids),
                UserHierarchy.subordinate_id.in_(user_ids),
            )
        )).scalars().all()
        uu_edges = [{"id": r.id, "manager_id": r.manager_id, "subordinate_id": r.subordinate_id} for r in rows]

    # Load user-dept edges
    ud_edges = []
    if user_ids and dept_ids:
        ud_rows = (await db.execute(
            select(ManagerDepartment).where(
                ManagerDepartment.manager_user_id.in_(user_ids),
                ManagerDepartment.dept_id.in_(dept_ids),
            )
        )).scalars().all()
        ud_edges = [{"id": r.id, "manager_user_id": r.manager_user_id, "dept_id": r.dept_id} for r in ud_rows]

    return {
        "orgs": [{"id": o.id, "name": o.name} for o in orgs],
        "departments": [
            {
                "id": d.id, "name": d.name, "org_id": d.org_id,
                "head_user_id": d.head_user_id,
                "member_ids": members_map.get(d.id, []),
            }
            for d in depts
        ],
        "users": [
            {
                "id": u.id,
                "full_name": u.full_name,
                "username": u.username,
                "role": u.role,
                "org_id": u.org_id,
                "avatar": getattr(u, "avatar", None),
                "position": user_position_map.get(u.id) or getattr(u, "position", None),
            }
            for u in users
        ],
        "user_user_edges": uu_edges,
        "user_dept_edges": ud_edges,
    }


# ── Edge CRUD ─────────────────────────────────────────────────────────────────

@router.post("/api/hierarchy/edges", response_model=EdgeOut)
async def create_edge(
    body: EdgeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*ADMIN_ROLES)),
):
    if body.type == "user_user":
        # Prevent self-loop
        if body.source_id == body.target_id:
            raise HTTPException(400, "Пользователь не может быть подчинённым самого себя")
        # Prevent cycles: check if source is already subordinate of target
        from app.routers.user_hierarchy import get_all_subordinate_ids
        existing_subs = await get_all_subordinate_ids(body.target_id, db)
        if body.source_id in existing_subs:
            raise HTTPException(400, "Создаст цикл в иерархии")

        existing = (await db.execute(
            select(UserHierarchy).where(
                UserHierarchy.manager_id == body.source_id,
                UserHierarchy.subordinate_id == body.target_id,
            )
        )).scalar_one_or_none()
        if existing:
            return {"id": existing.id, "type": "user_user"}
        row = UserHierarchy(manager_id=body.source_id, subordinate_id=body.target_id)
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return {"id": row.id, "type": "user_user"}

    elif body.type == "user_dept":
        # Get org_id from dept
        dept = await db.get(Department, body.target_id)
        if not dept:
            raise HTTPException(404, "Отдел не найден")
        existing = (await db.execute(
            select(ManagerDepartment).where(
                ManagerDepartment.manager_user_id == body.source_id,
                ManagerDepartment.dept_id == body.target_id,
            )
        )).scalar_one_or_none()
        if existing:
            return {"id": existing.id, "type": "user_dept"}
        row = ManagerDepartment(
            manager_user_id=body.source_id,
            dept_id=body.target_id,
            org_id=dept.org_id,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return {"id": row.id, "type": "user_dept"}

    else:
        raise HTTPException(400, f"Неизвестный тип связи: {body.type}")


@router.delete("/api/hierarchy/edges/{edge_id}", response_model=OkOut)
async def delete_edge(
    edge_id: int,
    type: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*ADMIN_ROLES)),
):
    if type == "user_user":
        row = await db.get(UserHierarchy, edge_id)
        if not row:
            raise HTTPException(404, "Связь не найдена")
        await db.delete(row)
        await db.commit()
        return {"ok": True}

    elif type == "user_dept":
        row = await db.get(ManagerDepartment, edge_id)
        if not row:
            raise HTTPException(404, "Связь не найдена")
        await db.delete(row)
        await db.commit()
        return {"ok": True}

    else:
        raise HTTPException(400, f"Неизвестный тип связи: {type}")


# ── Task authority ─────────────────────────────────────────────────────────────

@router.get("/api/users/{uid}/task-authority", response_model=TaskAuthorityOut)
async def get_task_authority(
    uid: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    can_assign_to: direct subordinates from UserHierarchy
                   + all members of departments where user is ManagerDepartment
    can_receive_from: users who have uid as subordinate in UserHierarchy
    """
    # Direct subordinates
    uu_subs = (await db.execute(
        select(UserHierarchy).where(UserHierarchy.manager_id == uid)
    )).scalars().all()
    sub_ids = {r.subordinate_id for r in uu_subs}

    # Department manager: get all members of those depts
    ud_rows = (await db.execute(
        select(ManagerDepartment).where(ManagerDepartment.manager_user_id == uid)
    )).scalars().all()
    if ud_rows:
        dept_ids = [r.dept_id for r in ud_rows]
        dept_members = (await db.execute(
            select(DepartmentMember).where(DepartmentMember.department_id.in_(dept_ids))
        )).scalars().all()
        for m in dept_members:
            if m.user_id != uid:
                sub_ids.add(m.user_id)

    can_assign_to = []
    if sub_ids:
        users = (await db.execute(select(User).where(User.id.in_(sub_ids)))).scalars().all()
        can_assign_to = [{"id": u.id, "full_name": u.full_name, "username": u.username, "role": u.role} for u in users]

    # Who can assign tasks to uid (uid is their subordinate)
    mgr_rows = (await db.execute(
        select(UserHierarchy).where(UserHierarchy.subordinate_id == uid)
    )).scalars().all()
    mgr_ids = {r.manager_id for r in mgr_rows}

    can_receive_from = []
    if mgr_ids:
        mgrs = (await db.execute(select(User).where(User.id.in_(mgr_ids)))).scalars().all()
        can_receive_from = [{"id": u.id, "full_name": u.full_name, "username": u.username, "role": u.role} for u in mgrs]

    return {
        "can_assign_to": can_assign_to,
        "can_receive_from": can_receive_from,
    }
