"""Phase 17 Plan 03: /users/me?org_id returns effective tabs+actions."""
import pytest


@pytest.mark.asyncio
async def test_me_returns_permissions_object(client, admin_headers, test_admin_user):
    r = await client.get(f"/api/users/me?org_id={test_admin_user.org_id}", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert 'permissions' in body
    assert 'tabs' in body['permissions']
    assert 'actions' in body['permissions']

@pytest.mark.asyncio
async def test_me_admin_sees_staff_tab(client, admin_headers, test_admin_user):
    r = await client.get(f"/api/users/me?org_id={test_admin_user.org_id}", headers=admin_headers)
    assert 'staff' in r.json()['permissions']['tabs']

@pytest.mark.asyncio
async def test_me_employee_no_staff_tab(client, auth_headers, test_user):
    r = await client.get(f"/api/users/me?org_id={test_user.org_id}", headers=auth_headers)
    assert 'staff' not in r.json()['permissions']['tabs']

@pytest.mark.asyncio
async def test_me_override_flips_bit(client, auth_headers, test_user, user_org_access, make_override):
    """Grant 'staff' to employee via override → /users/me reflects it."""
    await make_override(user_org_access.id, 'staff', True)
    r = await client.get(f"/api/users/me?org_id={test_user.org_id}", headers=auth_headers)
    assert 'staff' in r.json()['permissions']['tabs']


# --- routers/users_platform_credentials.py::_assert_platform_access ---------
# Раньше три эндпоинта (GET/PUT/DELETE platform-credentials) дублировали
# инлайн-проверку "сам пользователь ИЛИ вкладка staff"; перевели на общий
# хелпер _assert_platform_access — узел ниже проверяет, что 403 для чужого
# пользователя без доступа к staff сохранился дословно (Правило №6).

@pytest.mark.asyncio
async def test_platform_credentials_403_for_other_user_without_staff_tab(
    client, auth_headers, test_user, make_user
):
    """test_user (employee, без staff — см. test_me_employee_no_staff_tab)
    не может смотреть platform-credentials ДРУГОГО пользователя."""
    other = await make_user(role="employee", org_id=test_user.org_id)
    r = await client.get(f"/api/users/{other.id}/platform-credentials", headers=auth_headers)
    assert r.status_code == 403
    # Глобальный обработчик исключений оборачивает HTTPException.detail в
    # {"message": ...} (см. app/__init__.py), не {"detail": ...} — сверяем
    # текст (дословно как в _assert_platform_access) в этом поле.
    body = r.json()
    assert "Просмотр" in body["message"]
    assert "«Персонал»" in body["message"]


@pytest.mark.asyncio
async def test_platform_credentials_self_access_allowed(client, auth_headers, test_user):
    """Сам себе — доступ всегда разрешён, независимо от вкладки staff."""
    r = await client.get(f"/api/users/{test_user.id}/platform-credentials", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []
