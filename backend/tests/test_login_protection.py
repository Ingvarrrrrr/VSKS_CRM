"""Защита входа от подбора пароля — три механизма в одном файле:

1. Блокировка учётной записи (app/auth/account_lockout.py): 10 неверных
   паролей подряд -> аккаунт заблокирован на 15 мин, 11-я попытка 429 даже с
   верным паролем; по истечении блокировки верный пароль пускает и сбрасывает
   счётчик.
2. Политика пароля (app/services/password_policy.py): короткий/частый пароль
   отклоняется при регистрации и сбросе.
3. token_version (app/auth/token_version.py): смена пароля аннулирует ранее
   выданные токены (claim "tv"); токен без claim (tv=0) продолжает работать,
   пока пароль не менялся; switch-org сохраняет tv в новом токене.
4. forgot-password: не чаще 1 письма/20 мин на аккаунт.

Изоляция от IP-лимитера (app/auth/rate_limit.py, тоже MAX_ATTEMPTS=10/60с на
тот же /api/auth/login) — см. test_login_rate_limit.py: httpx.ASGITransport
подставляет один IP для всех запросов `client`, лимитер module-level и иначе
протекал бы между тестами/механизмами. Чистим его автоюзом в этом файле тоже.
"""
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest
import pytest_asyncio

from app.auth import rate_limit
from app.auth.account_lockout import MAX_ATTEMPTS as LOCKOUT_MAX_ATTEMPTS
from app.auth.jwt import create_access_token
from app.config import settings


@pytest.fixture(autouse=True)
def _reset_ip_rate_limiter():
    rate_limit._attempts.clear()
    yield
    rate_limit._attempts.clear()


@pytest_asyncio.fixture
async def confirmed_user(test_user, db_session):
    """test_user (conftest.py) defaults is_email_confirmed=False -> login 403s
    before ever reaching lockout logic. Give it an email too (lockout warning
    + forgot-password need one)."""
    test_user.is_email_confirmed = True
    test_user.email = f"{test_user.username}@example.com"
    await db_session.commit()
    await db_session.refresh(test_user)
    return test_user


def _decode(token: str) -> dict:
    return pyjwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


# ---------------------------------------------------------------------------
# 1. Account lockout
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tenth_failure_locks_account_eleventh_blocked_even_with_right_password(
    client, confirmed_user, monkeypatch, db_session,
):
    sent = []

    async def _fake_send(email):
        sent.append(email)

    monkeypatch.setattr("app.auth.account_lockout.send_account_locked_email", _fake_send)

    # Captured up front: accessing ORM attributes after expire_all() below
    # would trigger an implicit (sync) lazy-load outside of greenlet context
    # and blow up — see record_failed_password()'s raw-SQL note below.
    username = confirmed_user.username
    email = confirmed_user.email

    for i in range(LOCKOUT_MAX_ATTEMPTS):
        r = await client.post(
            "/api/auth/login",
            json={"username": username, "password": "wrong-password"},
        )
        assert r.status_code == 401, f"attempt {i + 1} unexpected: {r.text}"

    # Clear the (unrelated, already covered by test_login_rate_limit.py)
    # per-IP limiter so the 11th request's 429 can only come from the
    # per-ACCOUNT lock this test is actually about — both limiters use
    # MAX_ATTEMPTS=10 and httpx.ASGITransport reuses one IP for everything,
    # so without this the IP limiter would also have tripped by now.
    rate_limit._attempts.clear()
    # record_failed_password() writes locked_until via raw SQL (not the
    # ORM-tracked `confirmed_user`/`user` object) — the `client` fixture
    # shares ONE db_session/identity-map across every request in this test
    # (unlike production, where each request gets its own fresh session), so
    # the login handler's own re-query of the User row would otherwise still
    # see a stale (pre-lock) `locked_until` from the identity map.
    db_session.expire_all()

    # 11th attempt, even with the CORRECT password, must be blocked.
    r = await client.post(
        "/api/auth/login",
        json={"username": username, "password": "testpass123"},
    )
    assert r.status_code == 429, r.text
    assert "заблокирован" in r.json()["detail"]
    assert sent == [email], "lockout warning email must be sent exactly once, to the account owner"


@pytest.mark.asyncio
async def test_lock_expires_then_correct_password_resets_counter(client, confirmed_user, db_session):
    # Пропускаем реальное ожидание 15 минут — напрямую выставляем локаут в
    # прошлом (как будто он уже истёк), проверяя только поведение ПОСЛЕ
    # истечения, не сам таймер.
    confirmed_user.locked_until = datetime.now(timezone.utc) - timedelta(minutes=1)
    confirmed_user.failed_login_count = 0
    confirmed_user.failed_login_first_at = None
    await db_session.commit()

    r = await client.post(
        "/api/auth/login",
        json={"username": confirmed_user.username, "password": "testpass123"},
    )
    assert r.status_code == 200, r.text

    await db_session.refresh(confirmed_user)
    assert confirmed_user.locked_until is None
    assert confirmed_user.failed_login_count == 0
    assert confirmed_user.failed_login_first_at is None


# ---------------------------------------------------------------------------
# 2. Password policy
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_register_rejects_short_password(client):
    import uuid
    resp = await client.post("/api/register", json={
        "org_name": f"TestOrg-{uuid.uuid4().hex[:8]}",
        "password": "abc123",  # < 8 chars
        "email": f"short-{uuid.uuid4().hex[:8]}@example.com",
        "consent_accepted": True,
        "consent_version": "privacy:1.0+consent:1.0",
    })
    assert resp.status_code == 422, resp.text
    assert "8 символов" in resp.json()["message"]


@pytest.mark.asyncio
async def test_register_rejects_common_password(client):
    import uuid
    resp = await client.post("/api/register", json={
        "org_name": f"TestOrg-{uuid.uuid4().hex[:8]}",
        "password": "qwerty123",  # common, 9 chars
        "email": f"common-{uuid.uuid4().hex[:8]}@example.com",
        "consent_accepted": True,
        "consent_version": "privacy:1.0+consent:1.0",
    })
    assert resp.status_code == 422, resp.text
    assert "распространён" in resp.json()["message"]


@pytest.mark.asyncio
async def test_reset_password_rejects_short_password(client, confirmed_user, db_session):
    confirmed_user.password_reset_token = "test-reset-token-short"
    confirmed_user.password_reset_expires = datetime.utcnow() + timedelta(hours=1)
    await db_session.commit()

    resp = await client.post("/api/auth/reset-password", json={
        "token": "test-reset-token-short",
        "password": "short1",
    })
    assert resp.status_code == 422, resp.text


# ---------------------------------------------------------------------------
# 3. token_version
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_old_token_rejected_new_token_works_after_reset(client, confirmed_user, db_session):
    old_token = create_access_token({"sub": confirmed_user.username, "org_id": confirmed_user.org_id, "tv": 0})

    confirmed_user.password_reset_token = "test-reset-token-tv"
    confirmed_user.password_reset_expires = datetime.utcnow() + timedelta(hours=1)
    await db_session.commit()

    resp = await client.post("/api/auth/reset-password", json={
        "token": "test-reset-token-tv",
        "password": "BrandNewPass9",
    })
    assert resp.status_code == 200, resp.text
    # bump_token_version() writes via raw SQL (not the ORM-tracked `user`
    # object) — force the shared test session to re-read token_version from
    # the DB on next access instead of serving a stale cached attribute.
    db_session.expire_all()

    # Old token (tv=0) must now be rejected — token_version bumped to 1.
    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {old_token}"})
    assert r.status_code == 401, r.text

    # New login with the new password issues a token that works.
    r = await client.post("/api/auth/login", json={
        "username": confirmed_user.username, "password": "BrandNewPass9",
    })
    assert r.status_code == 200, r.text
    new_token = r.json()["access_token"]
    assert _decode(new_token)["tv"] == 1

    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {new_token}"})
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_token_without_tv_claim_works_when_token_version_zero(client, confirmed_user):
    """Токены, выпущенные ДО этой задачи, не несут claim "tv" — должны
    продолжать работать, пока пароль не менялся (token_version=0)."""
    token = create_access_token({"sub": confirmed_user.username, "org_id": confirmed_user.org_id})
    assert "tv" not in _decode(token)

    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_switch_org_preserves_token_version(client, confirmed_user, test_org, db_session):
    from app.models.organization import Organization
    from app.models.user_org_access import UserOrgAccess

    org2 = Organization(name="SwitchTargetOrg")
    db_session.add(org2)
    await db_session.flush()
    db_session.add(UserOrgAccess(user_id=confirmed_user.id, org_id=org2.id, role=confirmed_user.role))

    # Simulate a prior password change: token_version bumped to 1.
    confirmed_user.token_version = 1
    await db_session.commit()

    token = create_access_token({
        "sub": confirmed_user.username, "org_id": confirmed_user.org_id, "tv": 1,
    })

    r = await client.post(
        "/api/auth/switch-org",
        json={"org_id": org2.id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    new_token = r.json()["access_token"]
    assert _decode(new_token)["tv"] == 1

    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {new_token}"})
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# 4. forgot-password: 1 письмо / 20 мин на аккаунт
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_forgot_password_does_not_resend_within_20_minutes(client, confirmed_user, monkeypatch):
    sent = []

    async def _fake_send(email, token):
        sent.append((email, token))

    monkeypatch.setattr("app.routers.auth.send_password_reset_email", _fake_send)

    r1 = await client.post("/api/auth/forgot-password", json={"email": confirmed_user.email})
    assert r1.status_code == 200
    r2 = await client.post("/api/auth/forgot-password", json={"email": confirmed_user.email})
    assert r2.status_code == 200

    assert len(sent) == 1, "second forgot-password within 20 min must not send a second email"
