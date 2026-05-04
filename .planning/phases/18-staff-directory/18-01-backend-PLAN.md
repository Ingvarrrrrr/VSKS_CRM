---
phase: 18
plan: 18-01
title: Backend — User.work_phone + /api/staff-directory + tab_key seed
wave: 1
depends_on: []
autonomous: true
files_modified:
  - backend/app/models/user.py
  - backend/app/schemas/schemas.py
  - backend/app/routers/staff_directory.py  # NEW
  - backend/app/__init__.py
  - backend/alembic/versions/staff_directory_seed.sql  # NEW (idempotent)
requirements: []
---

# 18-01: Backend — Staff Directory API

<objective>
Поддержать backend Phase 18:
1. Добавить колонку `User.work_phone` (стационарный телефон, String(30) nullable).
2. Расширить Pydantic schemas (`UserOut`, `UserCreate`, `UserUpdate`) полем `work_phone`.
3. Создать роутер `staff_directory.py` с одним endpoint `GET /api/staff-directory`, возвращающим список сотрудников видимых current_user через `get_org_filter`, с фильтрацией superadmin и `exclude_from_directory`.
4. Зарегистрировать роутер в `backend/app/__init__.py`.
5. Seed нового permission tab `staff_directory` (доступен всем 5 ролям по умолчанию) — idempotent SQL миграция, поскольку alembic chain сломан (паттерн из Phase 17.1 perm_seed_hotfix).
</objective>

<must_haves>
- `User.work_phone` колонка существует в БД (через `Base.metadata.create_all` после старта backend)
- `UserOut.work_phone: Optional[str]` присутствует и сериализуется
- `GET /api/staff-directory` отдаёт `200 OK` с массивом объектов `{id, full_name, position, department, phone, work_phone, email, photo_url, org_name, org_id}`
- Фильтр по `get_org_filter(current_user)` — пользователь видит только свои организации
- Superadmin записи видны **только** другим superadmin'ам (D-09 carry-forward)
- Записи с `exclude_from_directory=true` НЕ возвращаются никому
- Tab `staff_directory` появился в `permission_tabs` + есть `role_permissions` строки для 5 ролей с `is_allowed=true` (или эквивалент по схеме Phase 17)
- `require_tab('staff_directory')` декоратор работает на endpoint
</must_haves>

<tasks>

<task id="18-01-01" title="Добавить колонку User.work_phone">
<read_first>
- backend/app/models/user.py — прочитать структуру модели (где `phone`, `exclude_from_directory`)
</read_first>

<action>
В `backend/app/models/user.py` после строки с `phone = Column(String(30), nullable=True)` добавить:

```python
work_phone = Column(String(30), nullable=True)  # Стационарный/рабочий телефон (Phase 18)
```

Если есть `exclude_from_directory` (он уже добавлен коммитом `38ac526`) — `work_phone` идёт рядом с `phone`, до `exclude_from_directory`.

**SQLAlchemy `Base.metadata.create_all` создаст колонку при старте backend** — alembic не нужен.
</action>

<acceptance_criteria>
- `grep -n "work_phone = Column" backend/app/models/user.py` возвращает 1 совпадение
- Файл синтаксически валиден Python (`python -c "import ast; ast.parse(open('backend/app/models/user.py').read())"`)
</acceptance_criteria>
</task>

<task id="18-01-02" title="Расширить Pydantic schemas">
<read_first>
- backend/app/schemas/schemas.py — найти `UserCreate`, `UserUpdate`, `UserOut` (или соответствующие имена). Прочитать как уже добавлено `exclude_from_directory` полем.
</read_first>

<action>
В `backend/app/schemas/schemas.py` для каждой из схем `UserCreate`, `UserUpdate`, `UserOut` добавить поле:

```python
work_phone: Optional[str] = None
```

Расположить рядом с `phone: Optional[str]` (если `phone` уже есть в схеме). Если в `UserOut` `phone` обязательное — `work_phone` сделать `Optional[str] = None`.
</action>

<acceptance_criteria>
- `grep -c "work_phone" backend/app/schemas/schemas.py` ≥ 3 (UserCreate, UserUpdate, UserOut)
- Файл синтаксически валиден Python
</acceptance_criteria>
</task>

<task id="18-01-03" title="Создать роутер staff_directory.py">
<read_first>
- backend/app/routers/users.py — паттерн endpoint'а GET с `Depends(get_current_user)` + `get_org_filter` + `require_tab`
- backend/app/auth/jwt.py — сигнатура `get_org_filter(user) -> Optional[List[int]]`
- backend/app/auth/permissions.py — `require_tab` декоратор
- backend/app/models/user.py — поля User (после правки 18-01-01)
- backend/app/models/user_org_access.py (если существует) ИЛИ backend/app/models/user_organization.py — модель multi-org membership
</read_first>

<action>
Создать новый файл `backend/app/routers/staff_directory.py`:

```python
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.organization import Organization
from app.auth.jwt import get_current_user, get_org_filter
from app.auth.permissions import require_tab

router = APIRouter(prefix="/api/staff-directory", tags=["staff-directory"])


@router.get("/", dependencies=[Depends(require_tab("staff_directory"))])
async def list_directory(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Read-only список сотрудников видимых current_user через org_filter.
    
    Скрыто: superadmin (если current_user не superadmin) + exclude_from_directory=true.
    """
    org_ids = get_org_filter(current_user)
    
    # Базовый запрос
    q = select(User).where(
        User.is_active == True,
        User.exclude_from_directory == False,
    )
    
    # Фильтр по организациям — User.org_id ИЛИ через user_organizations join
    if org_ids is not None:
        # Импорт лениво, чтобы избежать circular
        try:
            from app.models.user_org_access import UserOrgAccess
            q = q.outerjoin(UserOrgAccess, UserOrgAccess.user_id == User.id).where(
                or_(
                    User.org_id.in_(org_ids),
                    UserOrgAccess.org_id.in_(org_ids),
                )
            )
        except ImportError:
            # Fallback на простой User.org_id
            q = q.where(User.org_id.in_(org_ids))
    
    # D-09: superadmin виден только другим superadmin
    if current_user.role != "superadmin":
        q = q.where(User.role != "superadmin")
    
    q = q.distinct()
    result = await db.execute(q)
    users = result.scalars().all()
    
    # Подгрузить org names
    org_id_to_name = {}
    if users:
        org_ids_in_use = {u.org_id for u in users if u.org_id}
        if org_ids_in_use:
            org_q = select(Organization.id, Organization.name).where(
                Organization.id.in_(org_ids_in_use)
            )
            org_rows = await db.execute(org_q)
            org_id_to_name = {r[0]: r[1] for r in org_rows.all()}
    
    out = []
    for u in users:
        out.append({
            "id": u.id,
            "full_name": u.full_name or u.username,
            "position": u.position,
            "department": u.department,
            "phone": u.phone,
            "work_phone": u.work_phone,
            "email": u.email,
            "photo_url": u.profile_photo,  # base64 data URL или None
            "org_id": u.org_id,
            "org_name": org_id_to_name.get(u.org_id) if u.org_id else None,
        })
    
    # Сортировка: ФИО алфавит
    out.sort(key=lambda r: (r.get("full_name") or "").lower())
    return out
```
</action>

<acceptance_criteria>
- Файл `backend/app/routers/staff_directory.py` существует
- `grep -n "/api/staff-directory" backend/app/routers/staff_directory.py` возвращает совпадение в `prefix`
- `grep -n "exclude_from_directory == False" backend/app/routers/staff_directory.py` возвращает 1+ совпадение
- `grep -n "role != .superadmin" backend/app/routers/staff_directory.py` возвращает 1+ совпадение
- `grep -n "require_tab(.staff_directory.)" backend/app/routers/staff_directory.py` возвращает 1+ совпадение
</acceptance_criteria>
</task>

<task id="18-01-04" title="Зарегистрировать роутер в __init__.py">
<read_first>
- backend/app/__init__.py — посмотреть строки с `app.include_router(...)` и `from .routers import (...)`
</read_first>

<action>
В `backend/app/__init__.py`:

1. В блок `from .routers import (...)` добавить `staff_directory` в список (рядом с `subsidy_approvers`, `responsible_persons` или в логичном месте).

2. После строки `app.include_router(users.router)` (или близко к users) добавить:

```python
app.include_router(staff_directory.router)
```
</action>

<acceptance_criteria>
- `grep -n "staff_directory" backend/app/__init__.py` возвращает ≥2 совпадения (import + include_router)
- Файл синтаксически валиден Python
</acceptance_criteria>
</task>

<task id="18-01-05" title="SQL seed для permission tab staff_directory">
<read_first>
- backend/alembic/versions/perm_seed_hotfix.sql — паттерн idempotent SQL для seed permission tab/role_permissions (если файл существует)
- backend/app/models/permission.py ИЛИ permission_tab.py — структура таблиц `permission_tabs`, `role_permissions`
</read_first>

<action>
Создать `backend/alembic/versions/staff_directory_seed.sql` (idempotent):

```sql
-- Phase 18: seed permission tab 'staff_directory' + grant for all 5 roles
-- Idempotent: можно запускать многократно

-- 1. Tab
INSERT INTO permission_tabs (tab_key, label, sort_order)
VALUES ('staff_directory', 'Справочник сотрудников', 100)
ON CONFLICT (tab_key) DO NOTHING;

-- 2. Role permissions (allowed для всех 5 ролей: superadmin, admin, org_admin, manager, employee)
INSERT INTO role_permissions (role_name, key, is_allowed)
SELECT r.role_name, 'staff_directory', TRUE
FROM (VALUES ('superadmin'), ('admin'), ('org_admin'), ('manager'), ('employee')) AS r(role_name)
ON CONFLICT (role_name, key) DO UPDATE SET is_allowed = TRUE;
```

**ВАЖНО:** проверь точные имена колонок таблиц `permission_tabs` и `role_permissions` через чтение модели или существующих миграций (например `permission_seed_hotfix.sql`). Если schema отличается — адаптируй SQL под реальные колонки. Например:
- если `permission_tabs.label` называется иначе (`title` / `name`) — использовать правильное имя
- если в `role_permissions` нет колонки `is_allowed` (а есть просто наличие записи = allowed) — использовать правильную форму

Файл должен быть применён вручную на проде (через `docker exec psql -f`) — alembic chain сломан. В commit message указать инструкцию для пользователя.

Также: добавить **fallback INSERT в Python startup** в `backend/app/__init__.py` — если SQL не применён, при старте backend записи появятся:

В `lifespan` функции (где сейчас `_deadline_reminder_loop`) ДО `yield`:

```python
# Phase 18: idempotent seed для tab 'staff_directory'
try:
    from .models.permission_tab import PermissionTab  # имя модели может отличаться — найти через grep
    from sqlalchemy import select as _select
    async with async_session() as db:
        existing = await db.execute(_select(PermissionTab).where(PermissionTab.tab_key == 'staff_directory'))
        if not existing.scalar_one_or_none():
            db.add(PermissionTab(tab_key='staff_directory', label='Справочник сотрудников'))
            await db.commit()
except Exception as e:
    import logging
    logging.getLogger(__name__).warning(f"staff_directory tab seed failed (non-fatal): {e}")
```

**Если модель называется иначе** — найти через `grep -n "class.*PermissionTab\|class.*permission_tabs" backend/app/models/`.
</action>

<acceptance_criteria>
- Файл `backend/alembic/versions/staff_directory_seed.sql` существует
- `grep -n "staff_directory" backend/alembic/versions/staff_directory_seed.sql` возвращает ≥2 совпадения
- (Опционально, не блокер) В `backend/app/__init__.py` есть fallback Python seed для startup
</acceptance_criteria>
</task>

</tasks>

<verification>
После execute этой плана:
- `curl -s -o /dev/null -w "%{http_code}" http://85.239.53.155/api/staff-directory/` после autodeploy → ожидаем 401 (без токена) или 200 (с токеном)
- На проде применить SQL: `docker cp backend/alembic/versions/staff_directory_seed.sql vsks-crm-db-1:/tmp/ && docker exec vsks-crm-db-1 psql -U vsks -d vsks_crm -f /tmp/staff_directory_seed.sql`
- В UI: после логина админ → `/admin/roles` → должна появиться колонка `staff_directory` с allowed=true для всех 5 ролей.
</verification>
