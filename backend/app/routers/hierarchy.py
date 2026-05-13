"""
Hierarchy graph management.

Endpoints:
  GET    /api/hierarchy/graph         — full graph for canvas
  POST   /api/hierarchy/edges         — create edge (user_user | user_dept | user_org)
  DELETE /api/hierarchy/edges/{id}    — remove edge
  GET    /api/users/{uid}/task-authority — who this user can assign tasks to and who can assign to them
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user, require_role, get_org_filter, ADMIN_ROLES
from app.auth.permissions import require_tab, ensure_user_org_access, remove_user_org_access
from app.database import get_db
from app.models.department import Department, DepartmentMember
from app.models.manager_department import ManagerDepartment
from app.models.manager_organization import ManagerOrganization
from app.models.organization import Organization
from app.models.user import User
from app.models.user_hierarchy import UserHierarchy
from app.models.user_organization import UserOrganization

router = APIRouter(tags=["hierarchy"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class EdgeCreate(BaseModel):
    type: str  # "user_user" | "user_dept" | "user_org"
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
    extra_org_ids: List[int] = []
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


class UserOrgEdgeOut(BaseModel):
    id: int
    manager_user_id: int
    org_id: int


class GraphOut(BaseModel):
    orgs: List[OrgOut]
    departments: List[DeptGraphOut]
    users: List[UserGraphOut]
    user_user_edges: List[UserUserEdgeOut]
    user_dept_edges: List[UserDeptEdgeOut]
    user_org_edges: List[UserOrgEdgeOut]


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
    # Also include dept memberships from user_organizations.dept_id (mirror with department_members)
    if dept_ids:
        uo_dept_rows = (await db.execute(
            select(UserOrganization).where(
                UserOrganization.dept_id.in_(dept_ids),
            )
        )).scalars().all()
        for r in uo_dept_rows:
            if r.dept_id in members_map and r.user_id not in members_map[r.dept_id]:
                members_map[r.dept_id].append(r.user_id)
            if r.position and r.user_id not in user_position_map:
                user_position_map[r.user_id] = r.position

    # Also ensure dept head is always in member_ids
    for d in depts:
        if d.head_user_id and d.head_user_id not in members_map.get(d.id, []):
            members_map[d.id].append(d.head_user_id)

    # Load users
    q_users = select(User)
    if org_ids is not None:
        q_users = q_users.where(User.org_id.in_(org_ids))
    # D-09: hide superadmin from non-superadmin callers
    if current_user.role != "superadmin":
        q_users = q_users.where(User.role != "superadmin")
    users = (await db.execute(q_users)).scalars().all()

    # Load extra org memberships (user_organizations) with salary
    user_ids = {u.id for u in users}
    extra_orgs_map: dict[int, list[int]] = {}
    user_org_details: dict[int, list[dict]] = {}  # user_id -> [{org_id, org_name, position, salary, pct}]
    org_name_map = {o.id: o.name for o in orgs}
    if user_ids:
        uo_rows = (await db.execute(
            select(UserOrganization).where(UserOrganization.user_id.in_(user_ids))
        )).scalars().all()
        dept_name_map = {d.id: d.name for d in depts}
        for r in uo_rows:
            extra_orgs_map.setdefault(r.user_id, []).append(r.org_id)
            user_org_details.setdefault(r.user_id, []).append({
                "org": org_name_map.get(r.org_id, f"#{r.org_id}"),
                "dept": dept_name_map.get(r.dept_id, "") if r.dept_id else "",
                "pos": r.position or "",
                "salary": float(r.salary_amount) if r.salary_amount else None,
                "pct": r.employment_percent,
            })

    # Load user-user edges (only within our org)
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

    # Load user-org edges
    uo_edges = []
    if user_ids and org_id_set:
        mo_rows = (await db.execute(
            select(ManagerOrganization).where(
                ManagerOrganization.manager_user_id.in_(user_ids),
                ManagerOrganization.org_id.in_(org_id_set),
            )
        )).scalars().all()
        uo_edges = [{"id": r.id, "manager_user_id": r.manager_user_id, "org_id": r.org_id} for r in mo_rows]

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
                "extra_org_ids": extra_orgs_map.get(u.id, []),
                "avatar": getattr(u, "avatar", None),
                "position": user_position_map.get(u.id) or getattr(u, "position", None),
                "user_orgs": (
                    [{"org": org_name_map.get(u.org_id, ""), "dept": "", "pos": u.position or "", "salary": None, "pct": None}]
                    if u.org_id and not any(d.get("org") == org_name_map.get(u.org_id) for d in user_org_details.get(u.id, []))
                    else []
                ) + user_org_details.get(u.id, []),
            }
            for u in users
        ],
        "user_user_edges": uu_edges,
        "user_dept_edges": ud_edges,
        "user_org_edges": uo_edges,
    }


# ── Edge CRUD ─────────────────────────────────────────────────────────────────

@router.post("/api/hierarchy/edges", response_model=EdgeOut)
async def create_edge(
    body: EdgeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab('staff')),
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

    elif body.type == "user_org":
        org = await db.get(Organization, body.target_id)
        if not org:
            raise HTTPException(404, "Организация не найдена")
        existing = (await db.execute(
            select(ManagerOrganization).where(
                ManagerOrganization.manager_user_id == body.source_id,
                ManagerOrganization.org_id == body.target_id,
            )
        )).scalar_one_or_none()
        if existing:
            return {"id": existing.id, "type": "user_org"}
        row = ManagerOrganization(manager_user_id=body.source_id, org_id=body.target_id)
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return {"id": row.id, "type": "user_org"}

    elif body.type == "user_extra_org":
        # Multi-org membership
        org = await db.get(Organization, body.target_id)
        if not org:
            raise HTTPException(404, "Организация не найдена")
        existing = (await db.execute(
            select(UserOrganization).where(
                UserOrganization.user_id == body.source_id,
                UserOrganization.org_id == body.target_id,
            )
        )).scalar_one_or_none()
        if existing:
            return {"id": existing.id, "type": "user_extra_org"}
        row = UserOrganization(user_id=body.source_id, org_id=body.target_id)
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return {"id": row.id, "type": "user_extra_org"}

    else:
        raise HTTPException(400, f"Неизвестный тип связи: {body.type}")


@router.delete("/api/hierarchy/edges/{edge_id}", response_model=OkOut)
async def delete_edge(
    edge_id: int,
    type: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab('staff')),
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

    elif type == "user_org":
        row = await db.get(ManagerOrganization, edge_id)
        if not row:
            raise HTTPException(404, "Связь не найдена")
        await db.delete(row)
        await db.commit()
        return {"ok": True}

    elif type == "user_extra_org":
        row = await db.get(UserOrganization, edge_id)
        if not row:
            raise HTTPException(404, "Связь не найдена")
        await db.delete(row)
        await db.commit()
        return {"ok": True}

    else:
        raise HTTPException(400, f"Неизвестный тип связи: {type}")


# ── Multi-org membership CRUD ──────────────────────────────────────────────────

@router.get("/api/users/{uid}/organizations")
async def get_user_organizations(
    uid: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all organizations a user belongs to (primary + extra)."""
    user = await db.get(User, uid)
    if not user:
        raise HTTPException(404, "Пользователь не найден")

    rows = (await db.execute(
        select(UserOrganization, Organization).join(
            Organization, Organization.id == UserOrganization.org_id
        ).where(UserOrganization.user_id == uid)
    )).all()

    primary = None
    if user.org_id:
        org = await db.get(Organization, user.org_id)
        if org:
            primary = {"id": org.id, "name": org.name, "primary": True}

    extra = [
        {"id": org.id, "name": org.name, "primary": False, "membership_id": uo.id,
         "position": uo.position}
        for uo, org in rows if org.id != user.org_id
    ]

    return {"primary": primary, "extra": extra}


class OrgMembershipBody(BaseModel):
    position: Optional[str] = None
    salary_amount: Optional[float] = None
    employment_percent: Optional[int] = None


@router.post("/api/users/{uid}/organizations/{org_id}")
async def add_user_to_organization(
    uid: int,
    org_id: int,
    body: OrgMembershipBody = OrgMembershipBody(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab('staff')),
):
    """Add user to an extra organization (or update position if already a member)."""
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Организация не найдена")
    existing = (await db.execute(
        select(UserOrganization).where(
            UserOrganization.user_id == uid,
            UserOrganization.org_id == org_id,
        )
    )).scalar_one_or_none()
    if existing:
        if body.position is not None:
            existing.position = body.position
            await db.commit()
        # Phase 17.1-05: mirror to user_org_access (role defaults to user.role)
        u = await db.get(User, uid)
        await ensure_user_org_access(uid, org_id, u.role if u else None, db)
        await db.commit()
        return {"id": existing.id, "ok": True}
    row = UserOrganization(user_id=uid, org_id=org_id, position=body.position)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    # Phase 17.1-05: mirror to user_org_access (role defaults to user.role)
    u = await db.get(User, uid)
    await ensure_user_org_access(uid, org_id, u.role if u else None, db)
    await db.commit()
    return {"id": row.id, "ok": True}


@router.patch("/api/users/{uid}/organizations/{org_id}")
async def update_user_org_position(
    uid: int,
    org_id: int,
    body: OrgMembershipBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab('staff')),
):
    """Update user's position in a specific extra organization."""
    # Use UPDATE ... WHERE to avoid MultipleResultsFound when user has several
    # dept rows for the same org (multi-dept case, e.g. Цыганов in org_id=1).
    values: dict = {}
    if body.position is not None:
        values["position"] = body.position
    if body.salary_amount is not None:
        values["salary_amount"] = body.salary_amount
    if body.employment_percent is not None:
        values["employment_percent"] = body.employment_percent

    if values:
        result = await db.execute(
            sa_update(UserOrganization)
            .where(
                UserOrganization.user_id == uid,
                UserOrganization.org_id == org_id,
            )
            .values(**values)
        )
        if result.rowcount == 0:
            # No existing rows — auto-create for primary org
            user = await db.get(User, uid)
            if user and user.org_id == org_id:
                db.add(UserOrganization(user_id=uid, org_id=org_id, **values))
            else:
                raise HTTPException(404, "Членство не найдено")
    await db.commit()
    return {"ok": True}


@router.get("/api/users/{uid}/salary")
async def get_user_salary(
    uid: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get salary info for a user across all orgs. Restricted to superadmin, org_admin, chief accountant."""
    # Access check: superadmin sees all; org_admin/accountant sees own org members
    can_view = current_user.role in ("superadmin", "account_owner")
    if not can_view and current_user.role in ("org_admin", "admin"):
        can_view = True  # org admins can see their org members' salary
    if not can_view:
        # Check if current user is chief accountant (by position)
        pos = (current_user.position or "").lower()
        if "бухгалтер" in pos and "главн" in pos:
            can_view = True
    if not can_view:
        raise HTTPException(403, "Недостаточно прав для просмотра оклада")

    rows = (await db.execute(
        select(UserOrganization).where(UserOrganization.user_id == uid)
    )).scalars().all()
    # Load dept names for dept_ids
    dept_ids = [r.dept_id for r in rows if r.dept_id]
    dept_names = {}
    if dept_ids:
        from app.models.department import Department as _D
        d_rows = (await db.execute(select(_D).where(_D.id.in_(dept_ids)))).scalars().all()
        dept_names = {d.id: d.name for d in d_rows}

    result = [
        {
            "id": r.id,
            "dept_id": r.dept_id,
            "org_id": r.org_id,
            "org_name": r.organization.name if r.organization else "",
            "dept_name": dept_names.get(r.dept_id, "") if r.dept_id else "",
            "position": r.position,
            "salary_amount": float(r.salary_amount) if r.salary_amount else None,
            "employment_percent": r.employment_percent,
        }
        for r in rows
    ]
    # Include primary org only if no records exist for it
    user = await db.get(User, uid)
    if user and user.org_id and not any(r["org_id"] == user.org_id for r in result):
        from app.models.organization import Organization
        org = await db.get(Organization, user.org_id)
        result.insert(0, {
            "id": None,
            "dept_id": None,
            "org_id": user.org_id,
            "org_name": org.name if org else "",
            "position": user.position or "",
            "salary_amount": None,
            "employment_percent": None,
        })
    return result


@router.delete("/api/users/{uid}/organizations/{org_id}")
async def remove_user_from_organization(
    uid: int,
    org_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab('staff')),
):
    """Remove user from an organization (extra or primary)."""
    user = await db.get(User, uid)
    is_primary = user and user.org_id == org_id

    row = (await db.execute(
        select(UserOrganization).where(
            UserOrganization.user_id == uid,
            UserOrganization.org_id == org_id,
        )
    )).scalar_one_or_none()

    if not row and not is_primary:
        raise HTTPException(404, "Членство не найдено")
    if row:
        await db.delete(row)
    if is_primary:
        user.org_id = None
    await db.commit()
    # Phase 17.1-05: remove uoa only for extra orgs; primary uoa is managed via
    # user.org_id changes in users.update_user to avoid accidental revocation.
    if not is_primary:
        await remove_user_org_access(uid, org_id, db)
        await db.commit()
    return {"ok": True}


@router.delete("/api/users/{uid}/org-memberships/{row_id}")
async def remove_user_org_membership_row(
    uid: int,
    row_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab('staff')),
):
    """Удалить конкретную строку user_organizations (адресуется по PK).
    Mirror: если у строки задан dept_id — удалить и DepartmentMember(dept_id,user_id),
    если у user'а в этом dept'е больше нет других строк user_organizations.
    """
    row = await db.get(UserOrganization, row_id)
    if not row or row.user_id != uid:
        raise HTTPException(404, "Запись не найдена")

    dept_id = row.dept_id
    org_id = row.org_id
    await db.delete(row)
    await db.flush()

    # Mirror в department_members: удалить если в user_organizations не осталось этого юзера в этом dept'е
    if dept_id is not None:
        from app.models.department import DepartmentMember
        remaining = (await db.execute(
            select(UserOrganization).where(
                UserOrganization.user_id == uid,
                UserOrganization.dept_id == dept_id,
            )
        )).scalar_one_or_none()
        if remaining is None:
            dm = (await db.execute(
                select(DepartmentMember).where(
                    DepartmentMember.user_id == uid,
                    DepartmentMember.department_id == dept_id,
                )
            )).scalar_one_or_none()
            if dm:
                await db.delete(dm)

    # Если у юзера больше нет привязок к этой org — снять primary org_id
    user = await db.get(User, uid)
    if user and user.org_id == org_id:
        any_left = (await db.execute(
            select(UserOrganization).where(
                UserOrganization.user_id == uid,
                UserOrganization.org_id == org_id,
            )
        )).scalar_one_or_none()
        if any_left is None:
            user.org_id = None

    await db.commit()
    return {"ok": True}


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
                   + all users in orgs where user is ManagerOrganization
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

    # Organization manager: get all users in those orgs
    mo_rows = (await db.execute(
        select(ManagerOrganization).where(ManagerOrganization.manager_user_id == uid)
    )).scalars().all()
    if mo_rows:
        mo_org_ids = [r.org_id for r in mo_rows]
        # D-09: task authority endpoint, hide superadmin from non-superadmin callers
        _org_user_q = select(User).where(User.org_id.in_(mo_org_ids))
        if current_user.role != "superadmin":
            _org_user_q = _org_user_q.where(User.role != "superadmin")
        org_users = (await db.execute(_org_user_q)).scalars().all()
        for u in org_users:
            if u.id != uid:
                sub_ids.add(u.id)
        # Also users with extra membership in those orgs
        extra_members = (await db.execute(
            select(UserOrganization).where(UserOrganization.org_id.in_(mo_org_ids))
        )).scalars().all()
        for r in extra_members:
            if r.user_id != uid:
                sub_ids.add(r.user_id)

    can_assign_to = []
    if sub_ids:
        users = (await db.execute(select(User).where(User.id.in_(sub_ids)))).scalars().all()  # superadmin-bypass-ok: lookup by pre-computed IDs from hierarchy
        can_assign_to = [{"id": u.id, "full_name": u.full_name, "username": u.username, "role": u.role} for u in users]

    # Who can assign tasks to uid (uid is their subordinate)
    mgr_rows = (await db.execute(
        select(UserHierarchy).where(UserHierarchy.subordinate_id == uid)
    )).scalars().all()
    mgr_ids = {r.manager_id for r in mgr_rows}

    can_receive_from = []
    if mgr_ids:
        mgrs = (await db.execute(select(User).where(User.id.in_(mgr_ids)))).scalars().all()  # superadmin-bypass-ok: lookup by pre-computed manager IDs
        can_receive_from = [{"id": u.id, "full_name": u.full_name, "username": u.username, "role": u.role} for u in mgrs]

    return {
        "can_assign_to": can_assign_to,
        "can_receive_from": can_receive_from,
    }
