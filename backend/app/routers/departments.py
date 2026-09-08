"""CRUD-ядро отделов: список/дерево/создание/правка/удаление отдела +
проверка права редактировать задачу другого пользователя
(``can_edit_task_of_user``, внешний потребитель — ``app/routers/tasks.py``
и тест ``backend/tests/test_can_edit_task_of_user.py``, путь импорта не
менялся).

РАЗРЕЗАНО (Правило №5, сессия 2026-09-08) из монолитного departments.py
(1068 строк) на:
  - app/routers/departments_members.py — участники отдела: GET/POST
    /{dept_id}/members, PATCH/DELETE /{dept_id}/members/{user_id}.
  - app/routers/departments_delegates.py — делегирование права редактировать
    задачи: GET/POST /delegates, DELETE /delegates/{delegate_id}.
  - app/routers/departments_import.py — импорт дерева отделов из Excel:
    GET /import/template, POST /import/excel.

Схемы (DepartmentCreate/Update/Out, MemberAdd/Out, DelegateAdd/Out) и
``_enrich_dept`` остаются здесь — соседние роутеры импортируют схемы отсюда
(однонаправленно, без цикла). Все под-роутеры используют тот же префикс
``/api/departments`` — коллизий путь+метод с catch-all `/{dept_id}` (только
PATCH/DELETE) нет ни у одного статического пути соседей, порядок регистрации
в app/routes.py сохраняет исходный визуальный порядок блоков этого файла
(CRUD → участники → делегаты → импорт).

Должность сотрудника (Правило №6) — единственный писатель services/user_position.py;
этот файл и соседи только читают через resolve_user_position (создание строки
membership с position=... напрямую — установленный паттерн, см. докстринг
set_user_position: создание membership не входит в его ответственность).
"""
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import (
    get_current_user, get_org_filter, get_single_org_id,
    ADMIN_ROLES,
)
from app.auth.permissions import require_tab
from app.database import get_db
from app.models.department import Department, TaskEditDelegate
from app.models.organization import Organization
from app.models.user import User
from app.models.user_organization import UserOrganization
from app.services.user_position import resolve_user_position

router = APIRouter(prefix="/api/departments", tags=["departments"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class DepartmentCreate(BaseModel):
    name: str
    subsidy_id: Optional[int] = None
    head_user_id: Optional[int] = None
    deputy_head_user_id: Optional[int] = None
    curator_user_id: Optional[int] = None
    parent_id: Optional[int] = None
    org_id: Optional[int] = None  # Override org assignment (superadmin only)

class DepartmentUpdate(BaseModel):
    name: Optional[str] = None
    head_user_id: Optional[int] = None
    deputy_head_user_id: Optional[int] = None
    curator_user_id: Optional[int] = None
    parent_id: Optional[int] = None
    subsidy_id: Optional[int] = None

class DepartmentOut(BaseModel):
    id: int
    name: str
    org_id: int
    subsidy_id: Optional[int] = None
    head_user_id: Optional[int] = None
    head_user_name: Optional[str] = None
    deputy_head_user_id: Optional[int] = None
    curator_user_id: Optional[int] = None
    parent_id: Optional[int] = None
    member_count: int = 0
    class Config:
        from_attributes = True

class MemberAdd(BaseModel):
    user_id: int
    position: Optional[str] = None
    dept_assigned_at: Optional[date] = None  # дата назначения в отдел; по умолчанию — сегодня

class MemberOut(BaseModel):
    id: int
    department_id: int
    user_id: int
    user_name: Optional[str] = None
    user_role: Optional[str] = None
    position: Optional[str] = None
    dept_assigned_at: Optional[date] = None
    position_assigned_at: Optional[date] = None
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
        select(func.count(UserOrganization.id)).where(UserOrganization.dept_id == d.id)
    )
    member_count = count_res.scalar() or 0
    return DepartmentOut(
        id=d.id, name=d.name, org_id=d.org_id, subsidy_id=d.subsidy_id,
        head_user_id=d.head_user_id, head_user_name=head_name,
        deputy_head_user_id=d.deputy_head_user_id, curator_user_id=d.curator_user_id,
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
    org_id: Optional[int] = Query(None),
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
    if org_id is not None:
        q = q.where(Department.org_id == org_id)
    depts = (await db.execute(q)).scalars().all()

    dept_ids = [d.id for d in depts]
    # Load all members from user_organizations.dept_id (single source of truth)
    uo_dept_rows = []
    if dept_ids:
        uo_dept_rows = (await db.execute(
            select(UserOrganization).where(
                UserOrganization.dept_id.in_(dept_ids),
            )
        )).scalars().all()

    # Load user names + positions
    user_ids = {uo.user_id for uo in uo_dept_rows}
    for d in depts:
        if d.head_user_id:
            user_ids.add(d.head_user_id)
    users_map = {}
    users_obj_map: dict[int, User] = {}
    if user_ids:
        for u in (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all():  # superadmin-bypass-ok: lookup by pre-computed IDs for enrichment
            users_obj_map[u.id] = u
            # position здесь legacy-фон только для head_user_name-карточки (без
            # membership-контекста); фактическая должность члена резолвится ниже
            # через resolve_user_position с конкретной UO-строкой этого отдела.
            users_map[u.id] = {"id": u.id, "name": u.full_name or u.username, "role": u.role, "position": u.position}

    # Load org names
    all_org_ids = {d.org_id for d in depts if d.org_id}
    orgs_map: dict = {}
    if all_org_ids:
        for o in (await db.execute(select(Organization).where(Organization.id.in_(all_org_ids)))).scalars().all():
            orgs_map[o.id] = o.name

    # Build tree
    by_id = {}
    for d in depts:
        head_u = users_map.get(d.head_user_id, {})
        by_id[d.id] = {
            "id": d.id, "name": d.name, "org_id": d.org_id,
            "org_name": orgs_map.get(d.org_id),
            "subsidy_id": d.subsidy_id, "parent_id": d.parent_id,
            "head_user_id": d.head_user_id,
            "head_user_name": head_u.get("name"),
            "members": [],
            "children": [],
        }

    # Build members list from user_organizations (single source of truth)
    added_pairs: set = set()

    for uo in uo_dept_rows:
        if uo.dept_id not in by_id:
            continue
        if (uo.dept_id, uo.user_id) in added_pairs:
            continue
        u = users_map.get(uo.user_id, {})
        entry = {
            "member_id": uo.id, "user_id": uo.user_id,
            "name": u.get("name", "?"), "role": u.get("role"),
            "position": resolve_user_position(
                users_obj_map.get(uo.user_id), org_id=uo.org_id, memberships=[uo]
            ),
        }
        by_id[uo.dept_id]["members"].append(entry)
        added_pairs.add((uo.dept_id, uo.user_id))

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
    current_user: User = Depends(require_tab('staff')),
):
    # Superadmin can assign to any org via body.org_id; others use their org
    if data.org_id and current_user.role in ('superadmin', 'account_owner'):
        org_id = data.org_id
    else:
        org_id = get_single_org_id(current_user) or current_user.org_id
    # 27.4-02: НЕ применяем .title() — он ломает аббревиатуры («отдел МТО» → «Отдел Мто»).
    # Сохраняем регистр как ввёл пользователь.
    norm_name = data.name.strip() if data.name else data.name
    dept = Department(
        name=norm_name, org_id=org_id,
        subsidy_id=data.subsidy_id, head_user_id=data.head_user_id,
        deputy_head_user_id=data.deputy_head_user_id, curator_user_id=data.curator_user_id,
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
    current_user: User = Depends(require_tab('staff')),
):
    dept = await db.get(Department, dept_id)
    if not dept:
        raise HTTPException(404, "Отдел не найден")
    old_name = dept.name
    old_head = dept.head_user_id
    old_deputy = dept.deputy_head_user_id
    update = data.dict(exclude_unset=True)
    if "name" in update and update["name"]:
        update["name"] = update["name"].strip()
    for k, v in update.items():
        setattr(dept, k, v)
    await db.commit()
    await db.refresh(dept)
    # If name changed, sync users.department for all members
    if "name" in update and dept.name != old_name:
        member_ids_q = select(UserOrganization.user_id).where(UserOrganization.dept_id == dept_id)
        await db.execute(
            sa_update(User).where(User.id.in_(member_ids_q)).values(department=dept.name)
        )
        await db.commit()
    # If head changed, sync hierarchy
    if dept.head_user_id and dept.head_user_id != old_head:
        from app.routers.users import _sync_head_hierarchy
        await _sync_head_hierarchy(dept, db)
        await db.commit()
    # Двусторонняя синхронизация: head/deputy отдела → должность в членстве
    if dept.head_user_id != old_head or dept.deputy_head_user_id != old_deputy:
        from app.services.dept_role_sync import sync_position_from_head
        await sync_position_from_head(db, dept, old_head, old_deputy)
        await db.commit()
    return await _enrich_dept(dept, db)


@router.delete("/{dept_id}")
async def delete_department(
    dept_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab('staff')),
):
    dept = await db.get(Department, dept_id)
    if not dept:
        raise HTTPException(404, "Отдел не найден")
    # Check for members
    member_count = (await db.execute(
        select(func.count()).select_from(UserOrganization).where(UserOrganization.dept_id == dept_id)
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
            UserOrganization, UserOrganization.dept_id == Department.id
        ).where(
            Department.head_user_id == editor.id,
            UserOrganization.user_id == task_owner_id,
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
            UserOrganization, UserOrganization.dept_id == ManagerDepartment.dept_id
        ).where(
            ManagerDepartment.manager_user_id == editor.id,
            UserOrganization.user_id == task_owner_id,
        )
    )
    if md_check.first():
        return True
    # ManagerOrganization: editor manages entire org that task_owner belongs to?
    # UserOrganization уже импортирован на уровне модуля (строка 21) — локальный
    # импорт здесь раньше делал имя ЛОКАЛЬНЫМ для всей функции (правило области
    # видимости Python: имя, которому есть присваивание/import где-либо в теле
    # функции, локально везде в функции), из-за чего использование
    # `UserOrganization` в head_check ВЫШЕ по коду (строка ~732, до этого
    # импорта) падало с UnboundLocalError на КАЖДОМ вызове can_edit_task_of_user
    # (ruff F823). Затронутый путь — tasks.py:337, редактирование чужой задачи
    # не-админом/не-владельцем.
    from app.models.manager_organization import ManagerOrganization
    task_owner = await db.get(User, task_owner_id)
    if task_owner:
        mo_check = await db.execute(
            select(ManagerOrganization.id).where(
                ManagerOrganization.manager_user_id == editor.id,
                ManagerOrganization.org_id == task_owner.org_id,
            )
        )
        if mo_check.first():
            return True
        # Also check extra org memberships
        mo_extra = await db.execute(
            select(ManagerOrganization.id).join(
                UserOrganization, UserOrganization.org_id == ManagerOrganization.org_id
            ).where(
                ManagerOrganization.manager_user_id == editor.id,
                UserOrganization.user_id == task_owner_id,
            )
        )
        if mo_extra.first():
            return True
    return False
