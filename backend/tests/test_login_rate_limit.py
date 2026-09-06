"""In-memory login rate limiter (backend/app/auth/rate_limit.py).

10 неудачных попыток за 60с на IP -> 11-я 429; успешный логин сбрасывает
счётчик того же IP.

Изоляция: `_attempts` в rate_limit.py — module-level dict, живёт в памяти
процесса весь pytest-run (не привязан к db_session/транзакции теста).
httpx.ASGITransport по умолчанию подставляет один и тот же client IP
('127.0.0.1', 123) для всех запросов через фикстуру `client` — значит без
явного сброса состояние утекало бы МЕЖДУ тестами этого файла. autouse-
фикстура ниже чистит счётчик до и после каждого теста; scope — только этот
файл, остальные тесты проекта login не дёргают (см. grep перед написанием
теста), так что глобальный conftest.py трогать не нужно.
"""
import pytest
import pytest_asyncio

from app.auth import rate_limit
from app.auth.rate_limit import MAX_ATTEMPTS


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    rate_limit._attempts.clear()
    yield
    rate_limit._attempts.clear()


@pytest_asyncio.fixture
async def confirmed_user(test_user, db_session):
    """test_user (conftest.py) defaults is_email_confirmed=False — /api/auth/login
    would 403 on that before ever reaching the rate limiter. Confirm it here
    rather than touching the shared conftest.py fixture (out of this task's
    scope)."""
    test_user.is_email_confirmed = True
    await db_session.commit()
    await db_session.refresh(test_user)
    return test_user


@pytest.mark.asyncio
async def test_eleventh_failed_attempt_is_rate_limited(client, confirmed_user):
    for _ in range(MAX_ATTEMPTS):
        r = await client.post(
            "/api/auth/login",
            json={"username": confirmed_user.username, "password": "wrong-password"},
        )
        assert r.status_code == 401

    r = await client.post(
        "/api/auth/login",
        json={"username": confirmed_user.username, "password": "wrong-password"},
    )
    assert r.status_code == 429
    assert r.json()["detail"] == "Слишком много попыток входа. Повторите через минуту."
    assert "Retry-After" in r.headers

    # Even the correct password is blocked while the IP is rate-limited.
    r = await client.post(
        "/api/auth/login",
        json={"username": confirmed_user.username, "password": "testpass123"},
    )
    assert r.status_code == 429


@pytest.mark.asyncio
async def test_successful_login_resets_counter(client, confirmed_user):
    for _ in range(MAX_ATTEMPTS - 1):
        r = await client.post(
            "/api/auth/login",
            json={"username": confirmed_user.username, "password": "wrong-password"},
        )
        assert r.status_code == 401

    # One attempt left before the limit — a successful login here must
    # reset the counter rather than merely "use up" the last slot.
    r = await client.post(
        "/api/auth/login",
        json={"username": confirmed_user.username, "password": "testpass123"},
    )
    assert r.status_code == 200

    # Fresh budget of MAX_ATTEMPTS failures should be available again.
    for _ in range(MAX_ATTEMPTS):
        r = await client.post(
            "/api/auth/login",
            json={"username": confirmed_user.username, "password": "wrong-password"},
        )
        assert r.status_code == 401

    r = await client.post(
        "/api/auth/login",
        json={"username": confirmed_user.username, "password": "wrong-password"},
    )
    assert r.status_code == 429
