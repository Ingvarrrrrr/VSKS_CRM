"""test_db_error_handler.py — app/errors_db.py: БД-ошибки мусорного ввода
ОБЯЗАНЫ отдавать 4xx, не 500 (находка С4 поведенческого тестирования,
tests/behavior/REPORT.md). Через настоящий HTTP-запрос (fixture `client`),
не вызовом классификатора напрямую — handler регистрируется на уровне
FastAPI app (app/main.py), важно проверить весь путь: роут → asyncpg/
SQLAlchemy ошибка → app/errors_db.py → JSONResponse."""
import pytest

from app.errors_db import _classify


async def test_int32_overflow_path_param_returns_422(client, superadmin_headers):
    """GET /api/vehicle-fines/{id} с id > 2^31 падал в asyncpg OverflowError
    ('value out of int32 range') → голый 500 (см. .schemathesis crash
    DELETE_api_departments_*). Теперь — честный 422."""
    resp = await client.get("/api/vehicle-fines/19578353087", headers=superadmin_headers)
    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert body["code"] == "INVALID_PARAM_VALUE"
    assert "correlation_id" in body


async def test_fk_violation_on_create_returns_422(client, superadmin_headers):
    """POST /api/vehicle-fines/ с несуществующим vehicle_id падал в
    asyncpg.ForeignKeyViolationError → 500. Теперь — 422 FK_NOT_FOUND."""
    resp = await client.post(
        "/api/vehicle-fines/",
        headers=superadmin_headers,
        json={
            "vehicle_id": 999999999,
            "issued_at": "2026-01-01T00:00:00Z",
            "amount": "100.00",
            "violation_type": "test",
        },
    )
    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert body["code"] == "FK_NOT_FOUND"


async def test_chat_search_negative_limit_returns_422(client, superadmin_headers):
    """GET /api/chat/search?limit=-5 — Query(20, le=50) без ge=1 раньше
    долетал до SQL LIMIT -5 → 500. Теперь Query(..., ge=1, le=50) → честный
    422 от pydantic (RequestValidationError, не затрагивает errors_db.py,
    но это тот же репорт С4 — фиксируем регрессию рядом)."""
    resp = await client.get("/api/chat/search?q=aa&limit=-5", headers=superadmin_headers)
    assert resp.status_code == 422, resp.text


class _FakeOrig:
    def __init__(self, text):
        self._text = text

    def __str__(self):
        return self._text


class _FakeDBAPIError(Exception):
    def __init__(self, orig_text):
        self.orig = _FakeOrig(orig_text)


def test_classify_foreign_key_violation():
    exc = _FakeDBAPIError(
        'insert or update on table "vehicle_fines" violates foreign key constraint '
        '"vehicle_fines_vehicle_id_fkey"\nDETAIL:  Key (vehicle_id)=(999999999) is not '
        'present in table "vehicles".'
    )
    status_code, code, message = _classify(exc)
    assert status_code == 422
    assert code == "FK_NOT_FOUND"


def test_classify_int32_overflow():
    exc = _FakeDBAPIError(
        "<class 'asyncpg.exceptions.DataError'>: invalid input for query argument $1: "
        "19578353087 (value out of int32 range)"
    )
    status_code, code, message = _classify(exc)
    assert status_code == 422
    assert code == "INVALID_PARAM_VALUE"


def test_classify_numeric_value_out_of_range():
    exc = _FakeDBAPIError(
        "<class 'asyncpg.exceptions.NumericValueOutOfRangeError'>: numeric field overflow"
    )
    status_code, code, message = _classify(exc)
    assert status_code == 422
    assert code == "NUMBER_TOO_LARGE"


def test_classify_invalid_text_representation():
    exc = _FakeDBAPIError(
        "<class 'asyncpg.exceptions.InvalidTextRepresentationError'>: invalid input syntax "
        "for type integer: \"abc\""
    )
    status_code, code, message = _classify(exc)
    assert status_code == 422
    assert code == "INVALID_PARAM_VALUE"


def test_classify_unique_violation_without_local_handling():
    exc = _FakeDBAPIError(
        'duplicate key value violates unique constraint "some_unique_idx"'
    )
    status_code, code, message = _classify(exc)
    assert status_code == 409
    assert code == "ALREADY_EXISTS"


def test_classify_unknown_returns_none():
    exc = _FakeDBAPIError("some completely unrelated database error")
    assert _classify(exc) is None


def test_classify_negative_limit_or_offset():
    exc = _FakeDBAPIError(
        "<class 'asyncpg.exceptions.InvalidRowCountInLimitClauseError'>: LIMIT must not be negative"
    )
    status_code, code, message = _classify(exc)
    assert status_code == 422
    assert code == "INVALID_PARAM_VALUE"

    exc2 = _FakeDBAPIError(
        "<class 'asyncpg.exceptions.InvalidRowCountInResultOffsetClauseError'>: OFFSET must not be negative"
    )
    status_code2, code2, _ = _classify(exc2)
    assert status_code2 == 422
    assert code2 == "INVALID_PARAM_VALUE"


def test_classify_string_too_long():
    exc = _FakeDBAPIError(
        "<class 'asyncpg.exceptions.StringDataRightTruncationError'>: value too long for type "
        "character varying(9)"
    )
    status_code, code, message = _classify(exc)
    assert status_code == 422
    assert code == "INVALID_PARAM_VALUE"


def test_classify_bare_overflow_error_without_db():
    """vehicles_dashboard_fines.py: timedelta(days=huge) падает ДО похода в
    БД — голый builtin OverflowError, у него нет .orig (не DBAPIError)."""
    exc = OverflowError("days=1204829003; must have magnitude <= 999999999")
    status_code, code, message = _classify(exc)
    assert status_code == 422
    assert code == "INVALID_PARAM_VALUE"


def test_classify_bare_overflow_error_different_message():
    """Та же fines-summary, но ДРУГОЙ текст той же OverflowError (period_days
    настолько огромен, что int сам не влезает в C int до timedelta-проверки
    магнитуды) — классификация по isinstance, не по тексту сообщения."""
    exc = OverflowError("Python int too large to convert to C int")
    status_code, code, message = _classify(exc)
    assert status_code == 422
    assert code == "INVALID_PARAM_VALUE"


async def test_negative_limit_returns_422(client, superadmin_headers):
    """GET /api/legal/requests?limit=-467629 падал в asyncpg.
    InvalidRowCountInLimitClauseError ('LIMIT must not be negative') → 500.
    Теперь — 422 через errors_db.py (роутер сам ge=1 не проверяет)."""
    resp = await client.get(
        "/api/legal/requests?offset=0&limit=-467629", headers=superadmin_headers,
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == "INVALID_PARAM_VALUE"


async def test_period_days_overflow_returns_422(client, superadmin_headers):
    """GET /api/vehicles-dashboard/fines-by-filial?period_days=<huge> падал в
    голый OverflowError (timedelta) → 500. Теперь — 422."""
    resp = await client.get(
        "/api/vehicles-dashboard/fines-by-filial?period_days=1204829003",
        headers=superadmin_headers,
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == "INVALID_PARAM_VALUE"


async def test_period_days_extreme_overflow_returns_422(client, superadmin_headers):
    """fines-summary с ЕЩЁ большим period_days — другое сообщение той же
    OverflowError ('Python int too large to convert to C int'), найдено при
    проверке фикса выше (классификация по isinstance это покрывает)."""
    resp = await client.get(
        "/api/vehicles-dashboard/fines-summary"
        "?period_days=2098273457431341806007615488",
        headers=superadmin_headers,
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == "INVALID_PARAM_VALUE"
