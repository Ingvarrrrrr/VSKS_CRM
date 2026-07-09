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
from sqlalchemy import select, update as sa_update, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user, require_role, get_org_filter, ADMIN_ROLES
from app.auth.permissions import require_tab, ensure_user_org_access, remove_user_org_access
from app.database import get_db
from app.models.department import Department
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
    inn: Optional[str] = None
    color: Optional[str] = None  # Phase 30: hex цвет орг для иерархии
    contractor_id: Optional[int] = None  # привязка к контрагенту (единая карточка)


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
    photo_url: Optional[str] = None  # Phase 30: фото профиля для аватара
    user_orgs: List[dict] = []  # массив с детализацией по орг (org/dept/pos/salary/pct)


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


class DeptDeptEdgeOut(BaseModel):
    parent_id: int
    dept_id: int


class GraphOut(BaseModel):
    orgs: List[OrgOut]
    departments: List[DeptGraphOut]
    users: List[UserGraphOut]
    user_user_edges: List[UserUserEdgeOut]
    user_dept_edges: List[UserDeptEdgeOut]
    user_org_edges: List[UserOrgEdgeOut]
    dept_dept_edges: List[DeptDeptEdgeOut] = []


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
    # Hierarchy canvas is the org-management surface: SaaS roles see ALL orgs
    # regardless of the transient active-org focus selection (otherwise a
    # newly-created org card never shows up). Fixes "created org not appearing".
    if current_user.role in ('superadmin', 'account_owner'):
        org_ids = None

    # Load orgs
    q_orgs = select(Organization)
    if org_ids is not None:
        q_orgs = q_orgs.where(Organization.id.in_(org_ids))
    orgs = (await db.execute(q_orgs)).scalars().all()
    org_id_set = {o.id for o in orgs}

    # Rule: any org linked to a subsidy is "in the contour" → ensure its card
    # appears even if it's outside the dept-based org filter.
    # Только для SaaS-ролей: org_admin видит только свои орги, subsidy-expansion
    # давала ему чужие карточки.
    if current_user.role in ('superadmin', 'account_owner'):
        from app.models.subsidy import Subsidy
        subsidy_org_rows = (await db.execute(
            select(Subsidy.org_id).where(Subsidy.org_id.isnot(None)).distinct()
        )).all()
        extra_org_ids = {r[0] for r in subsidy_org_rows if r[0] is not None} - org_id_set
        if extra_org_ids:
            extra_orgs = (await db.execute(
                select(Organization).where(Organization.id.in_(extra_org_ids))
            )).scalars().all()
            orgs = list(orgs) + list(extra_orgs)
            org_id_set = org_id_set | {o.id for o in extra_orgs}

    # Load departments
    q_depts = select(Department)
    if org_ids is not None:
        q_depts = q_depts.where(Department.org_id.in_(org_ids))
    depts = (await db.execute(q_depts)).scalars().all()
    dept_ids = [d.id for d in depts]

    # Load dept members from user_organizations (single source of truth)
    members_map: dict[int, list[int]] = {d.id: [] for d in depts}
    user_position_map: dict[int, str] = {}  # user_id -> position from UserOrganization
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
    # Phase 30.6 fix: cross-org membership — пользователь может числиться primary
    # в одной орг (User.org_id), но быть членом отдела в другой (через
    # user_organizations.dept_id). Без этого fix'а counter
    # «1 чел.» в отделе показывал, а карточка не рендерилась.
    extra_user_ids: set[int] = set()
    for ids in members_map.values():
        extra_user_ids.update(ids)
    q_users = select(User)
    if org_ids is not None:
        if extra_user_ids:
            q_users = q_users.where(or_(
                User.org_id.in_(org_ids),
                User.id.in_(extra_user_ids),
            ))
        else:
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

    # Dept→dept edges (вышестоящее подразделение) — только когда оба конца видимы
    dept_id_set = set(dept_ids)
    dd_edges = [
        {"parent_id": d.parent_id, "dept_id": d.id}
        for d in depts
        if d.parent_id and d.parent_id in dept_id_set
    ]

    # Dedup org-узлов по ИНН: одна организация (один ИНН) = один узел, даже если
    # на неё ссылаются несколько субсидий/контрагентов. Представителя выбираем по
    # приоритету: есть отделы > есть contractor_id > меньший id. Орг без ИНН не трогаем.
    dept_org_ids = {d.org_id for d in depts}
    by_inn: dict[str, object] = {}
    deduped_orgs = []
    for o in orgs:
        _inn = (getattr(o, "inn", None) or "").strip()
        if not _inn:
            deduped_orgs.append(o)
            continue
        prev = by_inn.get(_inn)
        if prev is None:
            by_inn[_inn] = o
            deduped_orgs.append(o)
            continue
        def _rank(x):
            return (1 if x.id in dept_org_ids else 0, 1 if getattr(x, "contractor_id", None) else 0, -x.id)
        if _rank(o) > _rank(prev):
            deduped_orgs[deduped_orgs.index(prev)] = o
            by_inn[_inn] = o

    return {
        "orgs": [{"id": o.id, "name": o.name, "inn": getattr(o, "inn", None), "color": getattr(o, "color", None), "contractor_id": getattr(o, "contractor_id", None)} for o in deduped_orgs],
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
                # Phase 30: фото профиля для аватара в иерархии (если загружено)
                "photo_url": getattr(u, "profile_photo", None),
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
        "dept_dept_edges": dd_edges,
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
        # Стрелка человек→отдел = куратор подразделения (заполняет явное поле,
        # которое читает цепочка согласования).
        dept.curator_user_id = body.source_id
        existing = (await db.execute(
            select(ManagerDepartment).where(
                ManagerDepartment.manager_user_id == body.source_id,
                ManagerDepartment.dept_id == body.target_id,
            )
        )).scalar_one_or_none()
        if existing:
            await db.commit()
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

    elif body.type == "dept_dept":
        # Стрелка отдел→отдел: источник — вышестоящее подразделение цели.
        if body.source_id == body.target_id:
            raise HTTPException(400, "Отдел не может быть вышестоящим для самого себя")
        src = await db.get(Department, body.source_id)
        tgt = await db.get(Department, body.target_id)
        if not src or not tgt:
            raise HTTPException(404, "Отдел не найден")
        # Защита от цикла: source не должен быть потомком target.
        cur, depth = src, 0
        while cur is not None and cur.parent_id and depth < 30:
            if cur.parent_id == body.target_id:
                raise HTTPException(400, "Создаст цикл в дереве подразделений")
            cur = await db.get(Department, cur.parent_id)
            depth += 1
        tgt.parent_id = body.source_id
        await db.commit()
        return {"id": tgt.id, "type": "dept_dept"}

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
        dept = await db.get(Department, row.dept_id)
        if dept is not None and dept.curator_user_id == row.manager_user_id:
            dept.curator_user_id = None
        await db.delete(row)
        await db.commit()
        return {"ok": True}

    elif type == "dept_dept":
        # edge_id = id целевого отдела; снять вышестоящее подразделение.
        tgt = await db.get(Department, edge_id)
        if not tgt:
            raise HTTPException(404, "Связь не найдена")
        tgt.parent_id = None
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
            "hired_at": r.hired_at.isoformat() if r.hired_at else None,
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
            "hired_at": None,
        })
    return result


@router.delete("/api/users/{uid}/organizations/{org_id}")
async def remove_user_from_organization(
    uid: int,
    org_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab('staff')),
):
    """Remove user from an organization (extra or primary).
    7c: Cascade — удаляет ВСЕ строки user_organizations с этим org_id.
    """
    user = await db.get(User, uid)
    is_primary = user and user.org_id == org_id

    # 7c: Load ALL rows for this user+org (may be multiple due to multi-dept)
    all_rows = (await db.execute(
        select(UserOrganization).where(
            UserOrganization.user_id == uid,
            UserOrganization.org_id == org_id,
        )
    )).scalars().all()

    if not all_rows and not is_primary:
        raise HTTPException(404, "Членство не найдено")

    # Delete all user_organizations rows for this org
    for row in all_rows:
        await db.delete(row)
    await db.flush()

    if is_primary:
        user.org_id = None
    await db.commit()
    # Phase 17.1-05: remove uoa only for extra orgs; primary uoa is managed via
    # user.org_id changes in users.update_user to avoid accidental revocation.
    if not is_primary:
        await remove_user_org_access(uid, org_id, db)
        await db.commit()
    return {"ok": True}


@router.patch("/api/users/{uid}/org-memberships/{row_id}")
async def patch_user_org_membership_row(
    uid: int,
    row_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab('staff')),
):
    """Обновить поля конкретной строки user_organizations (position, salary_amount, employment_percent)."""
    row = await db.get(UserOrganization, row_id)
    if not row or row.user_id != uid:
        raise HTTPException(404, "Запись не найдена")
    if "position" in body:
        row.position = body["position"] or None
    if "salary_amount" in body:
        row.salary_amount = body["salary_amount"]
    if "employment_percent" in body:
        row.employment_percent = body["employment_percent"]
    if "hired_at" in body:
        from datetime import datetime
        v = body["hired_at"]
        row.hired_at = datetime.fromisoformat(v) if v else None
    await db.commit()
    # Должность в членстве → head/deputy отдела (двусторонняя синхронизация)
    if "position" in body and row.dept_id:
        from app.models.department import Department
        from app.services.dept_role_sync import sync_head_from_position
        dept = await db.get(Department, row.dept_id)
        if dept is not None:
            await sync_head_from_position(db, dept, uid, row.position)
            await db.commit()
    return {"ok": True}


@router.delete("/api/users/{uid}/org-memberships/{row_id}")
async def remove_user_org_membership_row(
    uid: int,
    row_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab('staff')),
):
    """Удалить конкретную строку user_organizations (адресуется по PK)."""
    row = await db.get(UserOrganization, row_id)
    if not row or row.user_id != uid:
        raise HTTPException(404, "Запись не найдена")

    org_id = row.org_id
    await db.delete(row)
    await db.flush()

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
            select(UserOrganization).where(UserOrganization.dept_id.in_(dept_ids))
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
