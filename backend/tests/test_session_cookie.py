"""Перенос JWT из localStorage в httpOnly-cookie `gala_session` (2026-10-13).

Один профильный файл (Правило — объём тестов по объёму правки):
- /api/auth/login ставит HttpOnly cookie, access_token больше не в теле;
- запрос с cookie без заголовка Authorization проходит (app/auth/jwt.py);
- "Bearer null" + валидная cookie — тоже проходит (мусорный заголовок
  закешированного старого фронта не должен перекрывать cookie);
- POST с cookie и ЧУЖИМ Origin -> 403 (CSRF, app/auth/csrf_protection.py),
  со СВОИМ Origin -> ок;
- POST с валидным Bearer и БЕЗ Origin -> ок (API-клиенты/тесты не затронуты);
- POST /api/auth/logout снимает cookie;
- POST /api/auth/session-from-token ставит cookie по старому Bearer-токену;
- смена пароля (token_version bump) инвалидирует cookie-сессию так же, как
  Bearer-сессию (test_login_protection.py уже проверяет Bearer-ветку).
"""
from datetime import datetime, timedelta

import jwt as pyjwt
import pytest

from app.auth.jwt import create_access_token
from app.auth.session_cookie import SESSION_COOKIE_NAME
from app.config import settings


def _decode(token: str) -> dict:
    return pyjwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


@pytest.fixture(autouse=True)
def _reset_ip_rate_limiter():
    from app.auth import rate_limit
    rate_limit._attempts.clear()
    yield
    rate_limit._attempts.clear()


@pytest.fixture
async def confirmed_user(test_user, db_session):
    test_user.is_email_confirmed = True
    test_user.email = f"{test_user.username}@example.com"
    await db_session.commit()
    await db_session.refresh(test_user)
    return test_user


# ---------------------------------------------------------------------------
# login sets cookie, not body
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_login_sets_httponly_cookie_no_access_token_in_body(client, confirmed_user):
    resp = await client.post("/api/auth/login", json={
        "username": confirmed_user.username, "password": "testpass123",
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("access_token") is None

    set_cookie = resp.headers.get_list("set-cookie") if hasattr(resp.headers, "get_list") else [resp.headers.get("set-cookie", "")]
    joined = ";".join(set_cookie) if isinstance(set_cookie, list) else str(set_cookie)
    assert SESSION_COOKIE_NAME in joined
    assert "httponly" in joined.lower()

    token = resp.cookies.get(SESSION_COOKIE_NAME)
    assert token
    payload = _decode(token)
    assert payload["sub"] == confirmed_user.username


# ---------------------------------------------------------------------------
# cookie-only auth
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_request_with_cookie_only_no_header_passes(client, confirmed_user):
    login_resp = await client.post("/api/auth/login", json={
        "username": confirmed_user.username, "password": "testpass123",
    })
    assert login_resp.status_code == 200

    # client хранит cookie jar — следующий запрос шлёт её сам, без заголовка.
    me = await client.get("/api/auth/me")
    assert me.status_code == 200, me.text
    assert me.json()["username"] == confirmed_user.username


@pytest.mark.asyncio
async def test_bearer_null_with_cookie_falls_back_to_cookie(client, confirmed_user):
    login_resp = await client.post("/api/auth/login", json={
        "username": confirmed_user.username, "password": "testpass123",
    })
    assert login_resp.status_code == 200

    me = await client.get("/api/auth/me", headers={"Authorization": "Bearer null"})
    assert me.status_code == 200, me.text
    assert me.json()["username"] == confirmed_user.username


@pytest.mark.asyncio
async def test_no_cookie_no_header_401(client):
    me = await client.get("/api/auth/me")
    assert me.status_code == 401


# ---------------------------------------------------------------------------
# CSRF
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_post_with_cookie_and_foreign_origin_403(client, confirmed_user):
    login_resp = await client.post("/api/auth/login", json={
        "username": confirmed_user.username, "password": "testpass123",
    })
    assert login_resp.status_code == 200

    resp = await client.post(
        "/api/legal/consent",
        json={"kind": "pd", "accepted": True},
        headers={"Origin": "http://evil.example"},
    )
    assert resp.status_code == 403, resp.text
    assert "источник" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_post_with_cookie_and_own_origin_ok(client, confirmed_user):
    login_resp = await client.post("/api/auth/login", json={
        "username": confirmed_user.username, "password": "testpass123",
    })
    assert login_resp.status_code == 200

    resp = await client.post(
        "/api/legal/consent",
        json={"kind": "pd", "accepted": True},
        headers={"Origin": "http://test"},
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_post_with_bearer_no_origin_ok(client, confirmed_user):
    """API-клиенты/тесты — Authorization: Bearer валидного JWT без cookie —
    не должны требовать Origin вовсе (не cookie-аутентифицированы)."""
    token = create_access_token({"sub": confirmed_user.username, "org_id": confirmed_user.org_id})
    resp = await client.post(
        "/api/legal/consent",
        json={"kind": "pd", "accepted": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text


# ---------------------------------------------------------------------------
# logout / session-from-token
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_logout_clears_cookie(client, confirmed_user):
    login_resp = await client.post("/api/auth/login", json={
        "username": confirmed_user.username, "password": "testpass123",
    })
    assert login_resp.status_code == 200

    logout_resp = await client.post("/api/auth/logout", headers={"Origin": "http://test"})
    assert logout_resp.status_code == 200, logout_resp.text

    me = await client.get("/api/auth/me")
    assert me.status_code == 401


@pytest.mark.asyncio
async def test_logout_without_auth_still_200(client):
    resp = await client.post("/api/auth/logout")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_session_from_token_sets_cookie(client, confirmed_user):
    old_token = create_access_token({"sub": confirmed_user.username, "org_id": confirmed_user.org_id})

    resp = await client.post(
        "/api/auth/session-from-token",
        headers={"Authorization": f"Bearer {old_token}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is True

    me = await client.get("/api/auth/me")
    assert me.status_code == 200, me.text
    assert me.json()["username"] == confirmed_user.username


@pytest.mark.asyncio
async def test_session_from_token_rejects_garbage(client):
    for bad in ("null", "undefined", "", "not-a-jwt"):
        resp = await client.post(
            "/api/auth/session-from-token",
            headers={"Authorization": f"Bearer {bad}"} if bad else {},
        )
        assert resp.status_code == 401, f"{bad!r} -> {resp.status_code}"


# ---------------------------------------------------------------------------
# token_version invalidates cookie session too
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_password_change_invalidates_cookie_session(client, confirmed_user, db_session):
    login_resp = await client.post("/api/auth/login", json={
        "username": confirmed_user.username, "password": "testpass123",
    })
    assert login_resp.status_code == 200

    me = await client.get("/api/auth/me")
    assert me.status_code == 200

    confirmed_user.password_reset_token = "test-reset-token-cookie"
    confirmed_user.password_reset_expires = datetime.utcnow() + timedelta(hours=1)
    await db_session.commit()

    reset_resp = await client.post("/api/auth/reset-password", json={
        "token": "test-reset-token-cookie",
        "password": "BrandNewPass9",
    }, headers={"Origin": "http://test"})
    assert reset_resp.status_code == 200, reset_resp.text
    db_session.expire_all()

    # Старая cookie (tv=0) всё ещё лежит в client — теперь должна отклоняться.
    me_after = await client.get("/api/auth/me")
    assert me_after.status_code == 401
