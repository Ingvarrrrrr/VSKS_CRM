"""Аудит безопасности 2026-10-20: GET /api/diag/version был полностью
публичным (без Depends) — отдавал git sha + счётчики из БД кому угодно без
входа. Не используется ни фронтом, ни autodeploy — весь раздел /api/diag
только для суперадмина (routers/diag.py)."""
import pytest

from app.auth.jwt import create_access_token


@pytest.mark.asyncio
async def test_diag_version_rejects_anonymous(client):
    resp = await client.get("/api/diag/version")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_diag_rejects_employee(client, make_user):
    """Весь /api/diag — только суперадмин: advance-overview отдавал закупки
    всех аккаунтов любому вошедшему."""
    user = await make_user(role="employee")
    token = create_access_token({"sub": user.username, "org_id": user.org_id})
    h = {"Authorization": f"Bearer {token}"}
    assert (await client.get("/api/diag/version", headers=h)).status_code == 403
    assert (await client.get("/api/diag/advance-overview", headers=h)).status_code == 403


@pytest.mark.asyncio
async def test_diag_version_allows_superadmin(client, make_user):
    user = await make_user(role="superadmin")
    token = create_access_token({"sub": user.username, "org_id": user.org_id})
    resp = await client.get(
        "/api/diag/version", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert "git_sha" in resp.json()
