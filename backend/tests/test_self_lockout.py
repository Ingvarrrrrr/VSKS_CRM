"""Phase 17 Plan 05: admin cannot revoke own 'admin.roles' or 'staff' tab."""
import pytest


@pytest.mark.asyncio
async def test_admin_cannot_revoke_own_admin_roles(client, admin_headers, test_admin_user):
    """PUT /api/permissions/roles/org_admin with admin.roles granted=False → 403."""
    r = await client.put(
        "/api/permissions/roles/org_admin",
        headers=admin_headers,
        json=[{"key": "admin.roles", "granted": False}],
    )
    assert r.status_code == 403
    # 2026-09-15: текст отказа обновлён (слово «суперадмин» убрано из сообщений,
    # см. app/routers/permissions.py ~:104-:109) — теперь это общее «Недостаточно
    # прав: ...», а не отдельная self-lockout формулировка. Код 403 и сценарий
    # (админ не может снять admin.roles у своей же роли) не изменились.
    assert (
        "Нельзя" in r.text
        or "lockout" in r.text.lower()
        or "Самоблок" in r.text
        or "Недостаточно прав" in r.text
    )

@pytest.mark.asyncio
async def test_admin_cannot_revoke_own_staff_tab(client, admin_headers, test_admin_user):
    r = await client.put(
        "/api/permissions/roles/org_admin",
        headers=admin_headers,
        json=[{"key": "staff", "granted": False}],
    )
    assert r.status_code == 403

@pytest.mark.asyncio
async def test_admin_can_revoke_other_role_staff(client, admin_headers):
    """admin CAN revoke manager's staff tab (not self-lockout)."""
    r = await client.put(
        "/api/permissions/roles/manager",
        headers=admin_headers,
        json=[{"key": "staff", "granted": False}],
    )
    assert r.status_code in (200, 204)
