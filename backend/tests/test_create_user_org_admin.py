"""Задача владельца (2026-10-16): в списке ролей при создании сотрудника
(«Добавить сотрудника», «+» в Иерархии, «Создать и добавить в отдел», импорт
из Excel) не было «Администратор организации» — роль ВНУТРИ ОДНОЙ организации
(UserOrgAccess.role), не глобальная (см. docstring split_new_user_role /
assert_new_user_role_allowed в app/auth/permissions.py).

Кейсы:
  (а) account_owner создаёт через POST /api/users/ с role='org_admin' →
      User.role == 'employee', UserOrgAccess(org) .role == 'org_admin'.
  (б) manager с role='org_admin' → 403 (ранг автора в орге < org_admin).
  (в) org_admin создаёт account_owner → 403 (assert_role_assignable).
  (г) org_admin создаёт org_admin в своей орге → разрешено (без исключения).
  (д) импорт: строка с ролью «Администратор организации» → UOA org_admin;
      строка с ролью «superadmin» → ошибка в errors (не падает весь импорт).
"""
import io
import uuid

import pytest
from openpyxl import Workbook
from fastapi import UploadFile, HTTPException
from sqlalchemy import select

from app.auth.permissions import (
    split_new_user_role,
    assert_new_user_role_allowed,
    assert_all_orgs_access_assignable,
)
from app.models.user_org_access import UserOrgAccess


def _mk_xlsx_upload(headers, rows) -> UploadFile:
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    return UploadFile(file=bio, filename=f"import-{uuid.uuid4().hex[:6]}.xlsx")


def test_split_new_user_role_org_admin():
    assert split_new_user_role("org_admin") == ("employee", "org_admin")
    assert split_new_user_role("manager") == ("manager", "manager")
    assert split_new_user_role("account_owner") == ("account_owner", "account_owner")


# ---------------------------------------------------------------------------
# (а) account_owner создаёт org_admin — сквозной HTTP через create_user
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_account_owner_creates_org_admin_via_http(client, db_session, test_org, make_user):
    from app.auth.jwt import create_access_token

    owner = await make_user(role="account_owner", org_id=test_org.id)
    token = create_access_token({"sub": owner.username, "org_id": owner.org_id})
    headers = {"Authorization": f"Bearer {token}"}

    email = f"orgadmin_{uuid.uuid4().hex[:8]}@example.com"
    resp = await client.post(
        "/api/users/",
        json={
            "email": email,
            "password": "Password123!",
            "last_name": "Орг",
            "first_name": "Админов",
            "role": "org_admin",
            "org_id": test_org.id,
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["role"] == "employee"

    uoa = (await db_session.execute(
        select(UserOrgAccess).where(
            UserOrgAccess.user_id == body["id"],
            UserOrgAccess.org_id == test_org.id,
        )
    )).scalar_one_or_none()
    assert uoa is not None
    assert uoa.role == "org_admin"


# ---------------------------------------------------------------------------
# (б) manager не может назначить org_admin (ранг < org_admin)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_manager_cannot_assign_org_admin(db_session, test_org, make_user):
    manager = await make_user(role="manager", org_id=test_org.id)
    with pytest.raises(HTTPException) as exc_info:
        await assert_new_user_role_allowed(manager, "org_admin", test_org.id, db_session)
    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# (в) org_admin не может назначить account_owner
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_org_admin_cannot_assign_account_owner(db_session, test_org, make_user):
    admin = await make_user(role="org_admin", org_id=test_org.id)
    with pytest.raises(HTTPException) as exc_info:
        await assert_new_user_role_allowed(admin, "account_owner", test_org.id, db_session)
    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# (г) org_admin МОЖЕТ назначить org_admin в своей же орге
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_org_admin_can_assign_org_admin_in_own_org(db_session, test_org, make_user):
    admin = await make_user(role="org_admin", org_id=test_org.id)
    # Не должно поднять исключение.
    await assert_new_user_role_allowed(admin, "org_admin", test_org.id, db_session)


# ---------------------------------------------------------------------------
# Аудит безопасности 2026-10-20 (дыра: эскалация при создании пользователя):
# раньше ранговая проверка в assert_new_user_role_allowed стояла ТОЛЬКО для
# role='org_admin' — менеджер (ранг 2) с правом user.manage мог создать
# 'admin' (ранг 4) без единой проверки. Дополнено общей ранговой проверкой
# для ЛЮБОЙ назначаемой роли (actor_rank >= target_rank).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_manager_cannot_assign_admin(db_session, test_org, make_user):
    manager = await make_user(role="manager", org_id=test_org.id)
    with pytest.raises(HTTPException) as exc_info:
        await assert_new_user_role_allowed(manager, "admin", test_org.id, db_session)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_org_admin_cannot_assign_admin(db_session, test_org, make_user):
    admin = await make_user(role="org_admin", org_id=test_org.id)
    with pytest.raises(HTTPException) as exc_info:
        await assert_new_user_role_allowed(admin, "admin", test_org.id, db_session)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_account_owner_can_assign_admin_via_http(client, test_org, make_user):
    from app.auth.jwt import create_access_token

    owner = await make_user(role="account_owner", org_id=test_org.id)
    token = create_access_token({"sub": owner.username, "org_id": owner.org_id})
    headers = {"Authorization": f"Bearer {token}"}

    email = f"admin_{uuid.uuid4().hex[:8]}@example.com"
    resp = await client.post(
        "/api/users/",
        json={
            "email": email,
            "password": "Password123!",
            "last_name": "Админ",
            "first_name": "Админович",
            "role": "admin",
            "org_id": test_org.id,
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["role"] == "admin"


# ---------------------------------------------------------------------------
# Аудит безопасности 2026-10-20 (дыра: all_orgs_access=True из тела запроса
# без проверки) — assert_all_orgs_access_assignable ограничивает флаг до
# superadmin/account_owner, единая точка для create_user и update_user.
# ---------------------------------------------------------------------------

def test_manager_cannot_set_all_orgs_access_direct():
    class _FakeUser:
        role = "manager"
    with pytest.raises(HTTPException) as exc_info:
        assert_all_orgs_access_assignable(_FakeUser())
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_manager_cannot_set_all_orgs_access_via_http(client, test_org, make_user):
    from app.auth.jwt import create_access_token

    manager = await make_user(role="manager", org_id=test_org.id)
    token = create_access_token({"sub": manager.username, "org_id": manager.org_id})
    headers = {"Authorization": f"Bearer {token}"}

    email = f"escal_{uuid.uuid4().hex[:8]}@example.com"
    resp = await client.post(
        "/api/users/",
        json={
            "email": email,
            "password": "Password123!",
            "last_name": "Тест",
            "first_name": "Тестович",
            "role": "employee",
            "org_id": test_org.id,
            "all_orgs_access": True,
        },
        headers=headers,
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_account_owner_can_set_all_orgs_access_via_http(client, test_org, make_user):
    from app.auth.jwt import create_access_token

    owner = await make_user(role="account_owner", org_id=test_org.id)
    token = create_access_token({"sub": owner.username, "org_id": owner.org_id})
    headers = {"Authorization": f"Bearer {token}"}

    email = f"allorgs_{uuid.uuid4().hex[:8]}@example.com"
    resp = await client.post(
        "/api/users/",
        json={
            "email": email,
            "password": "Password123!",
            "last_name": "Тест",
            "first_name": "Тестович",
            "role": "employee",
            "org_id": test_org.id,
            "all_orgs_access": True,
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# (д) импорт: русское название роли → org_admin; superadmin → ошибка в строке
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_import_excel_org_admin_role_and_superadmin_rejected(db_session, test_org, make_user):
    from app.routers.users_import import import_users_excel

    owner = await make_user(role="account_owner", org_id=test_org.id)

    email_admin = f"import_admin_{uuid.uuid4().hex[:8]}@example.com"
    email_bad = f"import_bad_{uuid.uuid4().hex[:8]}@example.com"
    headers = ["ФИО", "Email", "Логин", "Пароль", "Роль", "Город"]
    rows = [
        ["Импортов Админ Админович", email_admin, f"importadmin_{uuid.uuid4().hex[:6]}",
         "Password123!", "Администратор организации", "Москва"],
        ["Импортов Супер Суперович", email_bad, f"importsuper_{uuid.uuid4().hex[:6]}",
         "Password123!", "superadmin", "Москва"],
    ]
    upload = _mk_xlsx_upload(headers, rows)

    result = await import_users_excel(file=upload, db=db_session, current_user=owner)

    assert result["created"] == 1, result
    assert len(result["errors"]) == 1, result
    assert "superadmin" in result["errors"][0]["error"] or "Супер" in result["errors"][0]["error"]

    from app.models.user import User
    created = (await db_session.execute(
        select(User).where(User.email == email_admin)
    )).scalar_one_or_none()
    assert created is not None
    assert created.role == "employee"

    uoa = (await db_session.execute(
        select(UserOrgAccess).where(
            UserOrgAccess.user_id == created.id,
            UserOrgAccess.org_id == test_org.id,
        )
    )).scalar_one_or_none()
    assert uoa is not None
    assert uoa.role == "org_admin"

    not_created = (await db_session.execute(
        select(User).where(User.email == email_bad)
    )).scalar_one_or_none()
    assert not_created is None
