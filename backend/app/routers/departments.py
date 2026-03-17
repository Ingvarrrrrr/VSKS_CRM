from io import BytesIO
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import (
    get_current_user, require_role, get_org_filter, get_single_org_id,
    ADMIN_ROLES, MANAGER_ROLES,
)
from app.database import get_db
from app.models.department import Department, DepartmentMember, TaskEditDelegate
from app.models.user import User

router = APIRouter(prefix="/api/departments", tags=["departments"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class DepartmentCreate(BaseModel):
    name: str
    subsidy_id: Optional[int] = None
    head_user_id: Optional[int] = None
    parent_id: Optional[int] = None

class DepartmentUpdate(BaseModel):
    name: Optional[str] = None
    head_user_id: Optional[int] = None
    parent_id: Optional[int] = None
    subsidy_id: Optional[int] = None

class DepartmentOut(BaseModel):
    id: int
    name: str
    org_id: int
    subsidy_id: Optional[int] = None
    head_user_id: Optional[int] = None
    head_user_name: Optional[str] = None
    parent_id: Optional[int] = None
    member_count: int = 0
    class Config:
        from_attributes = True

class MemberAdd(BaseModel):
    user_id: int
    position: Optional[str] = None

class MemberOut(BaseModel):
    id: int
    department_id: int
    user_id: int
    user_name: Optional[str] = None
    user_role: Optional[str] = None
    position: Optional[str] = None
    class Config:
        from_attributes = True

class DelegateAdd(BaseModel):
    target_user_id: int
    delegate_user_id: int

class DelegateOut(BaseModel):
    id: int
    target_user_id: int
    target_user_name: Optional[str] = None
    delegate_user_id: int
    delegate_user_name: Optional[str] = None
    class Config:
        from_attributes = True


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _enrich_dept(d: Department, db: AsyncSession) -> DepartmentOut:
    head_name = None
    if d.head_user_id:
        u = await db.get(User, d.head_user_id)
        head_name = (u.full_name or u.username) if u else None
    count_res = await db.execute(
        select(func.count(DepartmentMember.id)).where(DepartmentMember.department_id == d.id)
    )
    member_count = count_res.scalar() or 0
    return DepartmentOut(
        id=d.id, name=d.name, org_id=d.org_id, subsidy_id=d.subsidy_id,
        head_user_id=d.head_user_id, head_user_name=head_name,
        parent_id=d.parent_id, member_count=member_count,
    )


# ── CRUD Departments ─────────────────────────────────────────────────────────

@router.get("/", response_model=List[DepartmentOut])
async def list_departments(
    subsidy_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(Department).order_by(Department.name)
    org_ids = get_org_filter(current_user)
    if org_ids is not None:
        q = q.where(Department.org_id.in_(org_ids))
    if subsidy_id is not None:
        q = q.where(Department.subsidy_id == subsidy_id)
    depts = (await db.execute(q)).scalars().all()
    return [await _enrich_dept(d, db) for d in depts]


@router.get("/tree")
async def department_tree(
    subsidy_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Дерево отделов с вложенными сотрудниками."""
    q = select(Department).order_by(Department.name)
    org_ids = get_org_filter(current_user)
    if org_ids is not None:
        q = q.where(Department.org_id.in_(org_ids))
    if subsidy_id is not None:
        q = q.where(Department.subsidy_id == subsidy_id)
    depts = (await db.execute(q)).scalars().all()

    dept_ids = [d.id for d in depts]
    # Load all members
    members = []
    if dept_ids:
        members = (await db.execute(
            select(DepartmentMember).where(DepartmentMember.department_id.in_(dept_ids))
        )).scalars().all()

    # Load user names
    user_ids = {m.user_id for m in members}
    for d in depts:
        if d.head_user_id:
            user_ids.add(d.head_user_id)
    users_map = {}
    if user_ids:
        for u in (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all():
            users_map[u.id] = {"id": u.id, "name": u.full_name or u.username, "role": u.role}

    # Build tree
    by_id = {}
    for d in depts:
        head_u = users_map.get(d.head_user_id, {})
        by_id[d.id] = {
            "id": d.id, "name": d.name, "org_id": d.org_id,
            "subsidy_id": d.subsidy_id, "parent_id": d.parent_id,
            "head_user_id": d.head_user_id,
            "head_user_name": head_u.get("name"),
            "members": [],
            "children": [],
        }

    for m in members:
        u = users_map.get(m.user_id, {})
        entry = {
            "member_id": m.id, "user_id": m.user_id,
            "name": u.get("name", "?"), "role": u.get("role"),
            "position": m.position,
        }
        if m.department_id in by_id:
            by_id[m.department_id]["members"].append(entry)

    roots = []
    for d in depts:
        node = by_id[d.id]
        if d.parent_id and d.parent_id in by_id:
            by_id[d.parent_id]["children"].append(node)
        else:
            roots.append(node)
    return roots


@router.post("/", response_model=DepartmentOut)
async def create_department(
    data: DepartmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*ADMIN_ROLES)),
):
    org_id = get_single_org_id(current_user) or current_user.org_id
    norm_name = data.name.strip().title() if data.name else data.name
    dept = Department(
        name=norm_name, org_id=org_id,
        subsidy_id=data.subsidy_id, head_user_id=data.head_user_id,
        parent_id=data.parent_id,
    )
    db.add(dept)
    await db.commit()
    await db.refresh(dept)
    return await _enrich_dept(dept, db)


@router.patch("/{dept_id}", response_model=DepartmentOut)
async def update_department(
    dept_id: int,
    data: DepartmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*ADMIN_ROLES)),
):
    dept = await db.get(Department, dept_id)
    if not dept:
        raise HTTPException(404, "Отдел не найден")
    old_head = dept.head_user_id
    update = data.dict(exclude_unset=True)
    if "name" in update and update["name"]:
        update["name"] = update["name"].strip().title()
    for k, v in update.items():
        setattr(dept, k, v)
    await db.commit()
    await db.refresh(dept)
    # If head changed, sync hierarchy
    if dept.head_user_id and dept.head_user_id != old_head:
        from app.routers.users import _sync_head_hierarchy
        await _sync_head_hierarchy(dept, db)
        await db.commit()
    return await _enrich_dept(dept, db)


@router.delete("/{dept_id}")
async def delete_department(
    dept_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*ADMIN_ROLES)),
):
    dept = await db.get(Department, dept_id)
    if not dept:
        raise HTTPException(404, "Отдел не найден")
    # Check for members
    member_count = (await db.execute(
        select(func.count()).select_from(DepartmentMember).where(DepartmentMember.department_id == dept_id)
    )).scalar() or 0
    if member_count > 0:
        raise HTTPException(400, f"Нельзя удалить отдел с сотрудниками ({member_count} чел.). Сначала уберите всех сотрудников из отдела.")
    # Check for child departments
    child_count = (await db.execute(
        select(func.count()).select_from(Department).where(Department.parent_id == dept_id)
    )).scalar() or 0
    if child_count > 0:
        raise HTTPException(400, f"Нельзя удалить отдел с дочерними отделами ({child_count} шт.). Сначала удалите или переместите дочерние отделы.")
    await db.delete(dept)
    await db.commit()
    return {"ok": True}


# ── Members ──────────────────────────────────────────────────────────────────

@router.get("/{dept_id}/members", response_model=List[MemberOut])
async def list_members(
    dept_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    members = (await db.execute(
        select(DepartmentMember).where(DepartmentMember.department_id == dept_id)
    )).scalars().all()
    user_ids = {m.user_id for m in members}
    users_map = {}
    if user_ids:
        for u in (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all():
            users_map[u.id] = u
    out = []
    for m in members:
        u = users_map.get(m.user_id)
        out.append(MemberOut(
            id=m.id, department_id=m.department_id, user_id=m.user_id,
            user_name=(u.full_name or u.username) if u else None,
            user_role=u.role if u else None,
            position=m.position,
        ))
    return out


@router.post("/{dept_id}/members", response_model=MemberOut)
async def add_member(
    dept_id: int,
    data: MemberAdd,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*ADMIN_ROLES)),
):
    dept = await db.get(Department, dept_id)
    if not dept:
        raise HTTPException(404, "Отдел не найден")
    existing = (await db.execute(
        select(DepartmentMember).where(
            DepartmentMember.department_id == dept_id,
            DepartmentMember.user_id == data.user_id,
        )
    )).scalar_one_or_none()
    if existing:
        existing.position = data.position
        await db.commit()
        await db.refresh(existing)
        m = existing
    else:
        m = DepartmentMember(department_id=dept_id, user_id=data.user_id, position=data.position)
        db.add(m)
        await db.commit()
        await db.refresh(m)
    # Also update user.department string
    user = await db.get(User, data.user_id)
    if user:
        user.department = dept.name
        await db.commit()
    u = await db.get(User, m.user_id)
    return MemberOut(
        id=m.id, department_id=m.department_id, user_id=m.user_id,
        user_name=(u.full_name or u.username) if u else None,
        user_role=u.role if u else None,
        position=m.position,
    )


@router.patch("/{dept_id}/members/{user_id}")
async def update_member(
    dept_id: int,
    user_id: int,
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*ADMIN_ROLES)),
):
    m = (await db.execute(
        select(DepartmentMember).where(
            DepartmentMember.department_id == dept_id,
            DepartmentMember.user_id == user_id,
        )
    )).scalar_one_or_none()
    if not m:
        raise HTTPException(404, "Сотрудник не найден в отделе")
    if "position" in data:
        m.position = data["position"]
    await db.commit()
    return {"ok": True}


@router.delete("/{dept_id}/members/{user_id}")
async def remove_member(
    dept_id: int,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*ADMIN_ROLES)),
):
    m = (await db.execute(
        select(DepartmentMember).where(
            DepartmentMember.department_id == dept_id,
            DepartmentMember.user_id == user_id,
        )
    )).scalar_one_or_none()
    if not m:
        raise HTTPException(404, "Сотрудник не найден в отделе")
    # Check for active purchases assigned to this user
    from app.models.purchase import Purchase
    active_count = (await db.execute(
        select(func.count()).select_from(Purchase).where(
            Purchase.assigned_user_id == user_id,
            Purchase.status.notin_(['paid', 'cancelled']),
        )
    )).scalar() or 0
    if active_count > 0:
        raise HTTPException(400, f"У сотрудника {active_count} активных задач (закупок). Сначала перераспределите задачи.")
    await db.delete(m)
    await db.commit()
    return {"ok": True}


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
        for u in (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all():
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
    current_user: User = Depends(require_role(*ADMIN_ROLES)),
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
    current_user: User = Depends(require_role(*ADMIN_ROLES)),
):
    d = await db.get(TaskEditDelegate, delegate_id)
    if not d:
        raise HTTPException(404, "Делегирование не найдено")
    await db.delete(d)
    await db.commit()
    return {"ok": True}


# ── Permission check helper ──────────────────────────────────────────────────

async def can_edit_task_of_user(
    editor: User, task_owner_id: int, db: AsyncSession
) -> bool:
    """Check if editor can edit tasks of task_owner_id."""
    # Admin can edit anything
    if editor.role in ADMIN_ROLES:
        return True
    # Own task
    if editor.id == task_owner_id:
        return True
    # Department head?
    head_check = await db.execute(
        select(Department.id).join(
            DepartmentMember, DepartmentMember.department_id == Department.id
        ).where(
            Department.head_user_id == editor.id,
            DepartmentMember.user_id == task_owner_id,
        )
    )
    if head_check.first():
        return True
    # Custom delegate?
    delegate_check = await db.execute(
        select(TaskEditDelegate.id).where(
            TaskEditDelegate.target_user_id == task_owner_id,
            TaskEditDelegate.delegate_user_id == editor.id,
        )
    )
    if delegate_check.first():
        return True
    # ManagerDepartment: editor is manager of a dept containing task_owner?
    from app.models.manager_department import ManagerDepartment
    md_check = await db.execute(
        select(ManagerDepartment.id).join(
            DepartmentMember, DepartmentMember.department_id == ManagerDepartment.dept_id
        ).where(
            ManagerDepartment.manager_user_id == editor.id,
            DepartmentMember.user_id == task_owner_id,
        )
    )
    if md_check.first():
        return True
    return False


# ── Excel import ─────────────────────────────────────────────────────────────

@router.get("/import/template")
async def dept_import_template(_=Depends(require_role(*ADMIN_ROLES))):
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
    except ImportError:
        raise HTTPException(500, "openpyxl не установлен")

    wb = Workbook()
    ws = wb.active
    ws.title = "Отделы и сотрудники"

    headers = ["Отдел", "Родительский отдел", "ФИО сотрудника", "Должность", "Начальник (да/нет)", "Субсидия"]
    hdr_fill = PatternFill("solid", fgColor="1E40AF")
    hdr_font = Font(bold=True, color="FFFFFF")
    for ci, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=ci, value=h)
        cell.font = hdr_font
        cell.fill = hdr_fill
        cell.alignment = Alignment(horizontal="center")

    examples = [
        ["Отдел закупок", "", "Иванов Иван", "Начальник отдела", "да", ""],
        ["Отдел закупок", "", "Петров Пётр", "Менеджер", "нет", ""],
        ["Склад", "", "Сидоров Сидор", "Кладовщик", "да", ""],
        ["ИТ-отдел", "", "Козлов Андрей", "Разработчик", "нет", ""],
        ["Сектор мониторинга", "Отдел закупок", "Фёдорова Мария", "Аналитик", "да", "ФАДМ_2026"],
    ]
    for ri, row in enumerate(examples, 2):
        for ci, val in enumerate(row, 1):
            ws.cell(row=ri, column=ci, value=val)

    for ci, w in enumerate([30, 25, 30, 25, 18, 20], 1):
        ws.column_dimensions[ws.cell(row=1, column=ci).column_letter].width = w

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=departments_template.xlsx"},
    )


@router.post("/import/excel")
async def import_departments_excel(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*ADMIN_ROLES)),
):
    """Import department tree from Excel."""
    if not (file.filename or '').lower().endswith(('.xlsx', '.xls')):
        raise HTTPException(400, "Только .xlsx / .xls файлы")

    try:
        from openpyxl import load_workbook
    except ImportError:
        raise HTTPException(500, "openpyxl не установлен")

    content = await file.read()
    wb = load_workbook(BytesIO(content), read_only=True, data_only=True)
    ws = wb.active

    org_id = get_single_org_id(current_user) or current_user.org_id

    # Load existing users by full_name for matching
    users_res = await db.execute(select(User).where(User.org_id == org_id))
    users_by_name = {}
    for u in users_res.scalars().all():
        if u.full_name:
            users_by_name[u.full_name.strip().lower()] = u

    # Load existing subsidies for matching
    from app.models.subsidy import Subsidy
    subs_res = await db.execute(select(Subsidy))
    subs_by_name = {s.name.strip().lower(): s for s in subs_res.scalars().all() if s.name}

    # Parse header
    header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
    if not header_row:
        raise HTTPException(400, "Файл пустой")

    def _norm(v):
        return str(v).strip().lower() if v else ''

    col = {}
    for i, h in enumerate(header_row):
        hs = _norm(h)
        if any(x in hs for x in ('отдел', 'department', 'подразделен')):
            col.setdefault('dept', i)
        if any(x in hs for x in ('родител', 'parent')):
            col.setdefault('parent', i)
        if any(x in hs for x in ('фио', 'сотрудник', 'имя', 'full_name')):
            col.setdefault('name', i)
        if any(x in hs for x in ('должност', 'position', 'позиц')):
            col.setdefault('position', i)
        if any(x in hs for x in ('начальник', 'head', 'руковод')):
            col.setdefault('head', i)
        if any(x in hs for x in ('субсид', 'subsidy')):
            col.setdefault('subsidy', i)

    if 'dept' not in col:
        raise HTTPException(400, "Не найдена колонка «Отдел»")

    def _cell(row, field):
        idx = col.get(field)
        if idx is None or idx >= len(row):
            return None
        v = row[idx]
        return str(v).strip() if v else None

    # First pass: collect departments
    dept_cache = {}  # name -> Department
    created_depts = 0
    created_members = 0
    errors = []

    rows = list(ws.iter_rows(min_row=2, values_only=True))

    # Create departments first
    for ri, row in enumerate(rows, 2):
        dept_name = _cell(row, 'dept')
        if not dept_name:
            continue
        key = dept_name.lower()
        if key not in dept_cache:
            subsidy_name = _cell(row, 'subsidy')
            subsidy_id = None
            if subsidy_name:
                sub = subs_by_name.get(subsidy_name.lower())
                if sub:
                    subsidy_id = sub.id

            # Check if already exists in DB
            existing = (await db.execute(
                select(Department).where(Department.org_id == org_id, func.lower(Department.name) == key)
            )).scalar_one_or_none()
            if existing:
                dept_cache[key] = existing
            else:
                dept = Department(name=dept_name.strip().title(), org_id=org_id, subsidy_id=subsidy_id)
                db.add(dept)
                await db.flush()
                dept_cache[key] = dept
                created_depts += 1

    # Set parent_id for departments
    for ri, row in enumerate(rows, 2):
        dept_name = _cell(row, 'dept')
        parent_name = _cell(row, 'parent')
        if dept_name and parent_name:
            dept = dept_cache.get(dept_name.lower())
            parent = dept_cache.get(parent_name.lower())
            if dept and parent and dept.id != parent.id:
                dept.parent_id = parent.id

    # Second pass: add members
    for ri, row in enumerate(rows, 2):
        dept_name = _cell(row, 'dept')
        user_name = _cell(row, 'name')
        if not dept_name or not user_name:
            continue

        dept = dept_cache.get(dept_name.lower())
        if not dept:
            errors.append({"row": ri, "error": f"Отдел «{dept_name}» не найден"})
            continue

        user = users_by_name.get(user_name.lower())
        if not user:
            errors.append({"row": ri, "error": f"Сотрудник «{user_name}» не найден в системе"})
            continue

        position = _cell(row, 'position')
        is_head = _cell(row, 'head')
        is_head_bool = is_head and is_head.lower() in ('да', 'yes', '1', 'true', 'head', 'начальник')

        # Add member
        existing_m = (await db.execute(
            select(DepartmentMember).where(
                DepartmentMember.department_id == dept.id,
                DepartmentMember.user_id == user.id,
            )
        )).scalar_one_or_none()
        if not existing_m:
            db.add(DepartmentMember(department_id=dept.id, user_id=user.id, position=position))
            created_members += 1
        elif position:
            existing_m.position = position

        if is_head_bool:
            dept.head_user_id = user.id

        # Update user.department
        user.department = dept.name

    await db.commit()
    return {
        "created_departments": created_depts,
        "created_members": created_members,
        "errors": errors,
    }
