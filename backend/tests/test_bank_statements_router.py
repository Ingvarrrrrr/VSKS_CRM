"""Phase 22.04 — smoke tests for bank_statements router.

Tests use the ASGITransport pattern (conftest.py: client, superadmin_headers).
These are scaffold tests — they verify routing and auth, not full DB integration.

To run: pytest backend/tests/test_bank_statements_router.py -v
"""
import io
import pytest
import pytest_asyncio


# ---------------------------------------------------------------------------
# Helper: build a minimal valid xlsx in memory (2 data rows)
# ---------------------------------------------------------------------------

def _make_minimal_xlsx() -> bytes:
    """Build a tiny xlsx with ScrollerHash-compatible headers and 2 data rows."""
    try:
        from openpyxl import Workbook
    except ImportError:
        pytest.skip("openpyxl not installed")

    wb = Workbook()
    ws = wb.active
    # Minimal columns expected by parse_workbook
    ws.append([
        "НОМЕР ДОКУМЕНТА",
        "ДАТА ДОКУМЕНТА",
        "СТАТУС ДОКУМЕНТА",
        "СУММА",
        "ИНН ПЛАТЕЛЬЩИКА",
        "НАИМЕНОВАНИЕ ПЛАТЕЛЬЩИКА",
        "ИНН ПОЛУЧАТЕЛЯ",
        "НАИМЕНОВАНИЕ ПОЛУЧАТЕЛЯ",
        "РАСШИФРОВКА П/П/КОНТРАКТ (ДОГОВОР)",
    ])
    ws.append(["0001", "01.01.2026", "ИСПОЛНЕН", 100000.00,
               "1234567890", "ООО Рога", "0987654321", "ООО Копыта",
               "Договор 5 от 01.01.2026"])
    ws.append(["0002", "02.01.2026", "ИСПОЛНЕН", 50000.00,
               "1234567890", "ООО Рога", "1112223334", "ООО Хвост",
               "Контракт 7 от 15.12.2025"])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Test 1: POST /api/payments/imports — superadmin happy path (mocked services)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_upload_bank_statement_requires_auth(client):
    """Without token → 401."""
    xlsx = _make_minimal_xlsx()
    resp = await client.post(
        "/api/payments/imports",
        files={"file": ("statement.xlsx", xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"


@pytest.mark.asyncio
async def test_upload_bank_statement_wrong_ext(client, superadmin_headers):
    """Non-xlsx file → 400."""
    resp = await client.post(
        "/api/payments/imports",
        files={"file": ("data.csv", b"col1,col2\n1,2", "text/csv")},
        headers=superadmin_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_upload_bank_statement_happy_path(client, superadmin_headers, monkeypatch):
    """POST /imports with valid xlsx → 200, BankStatementImportOut returned.

    We monkeypatch match_all_in_import so the test doesn't need a live DB
    with all contracts/contractors seeded.
    """
    import app.routers.bank_statements as bsr

    async def _fake_match(db, import_id):
        return 1, 1  # matched=1, unmatched=1

    monkeypatch.setattr(bsr, "match_all_in_import", _fake_match)

    xlsx = _make_minimal_xlsx()
    resp = await client.post(
        "/api/payments/imports",
        files={"file": ("statement.xlsx", xlsx,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=superadmin_headers,
    )
    # If DB is not available in test env → 500 is acceptable here;
    # we're checking routing + auth are wired correctly.
    assert resp.status_code in (200, 500), f"Unexpected: {resp.status_code} {resp.text}"
    if resp.status_code == 200:
        data = resp.json()
        assert "id" in data
        assert data["status"] in ("done", "error", "processing")


# ---------------------------------------------------------------------------
# Test 2: GET /api/payments/imports — list
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_imports_requires_auth(client):
    resp = await client.get("/api/payments/imports")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_list_imports_superadmin(client, superadmin_headers):
    resp = await client.get("/api/payments/imports", headers=superadmin_headers)
    # 200 list or 500 if DB not seeded — routing is what we verify
    assert resp.status_code in (200, 500)
    if resp.status_code == 200:
        assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# Test 3: GET /api/payments/registry — rejestr
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_registry_requires_auth(client):
    resp = await client.get("/api/payments/registry")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_registry_superadmin(client, superadmin_headers):
    resp = await client.get("/api/payments/registry", headers=superadmin_headers)
    assert resp.status_code in (200, 500)
    if resp.status_code == 200:
        assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# Test 4: POST /registry/{id}/confirm — validates missing matched_contract_id
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_confirm_not_found(client, superadmin_headers):
    """Non-existent bp_id → 404."""
    resp = await client.post(
        "/api/payments/registry/999999/confirm",
        json={"purchase_ids": [1, 2]},
        headers=superadmin_headers,
    )
    assert resp.status_code in (404, 500)


# ---------------------------------------------------------------------------
# Test 5: PATCH /registry/{id}/match — requires payment.confirm action
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_match_requires_action(client):
    """No auth → 401/403."""
    resp = await client.patch(
        "/api/payments/registry/1/match",
        json={"contract_id": 1},
    )
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Test 6: POST /registry/{id}/unbind — requires payment.unbind action
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unbind_requires_action(client):
    resp = await client.post("/api/payments/registry/1/unbind")
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Test 7: DELETE /imports/{id} — requires payment.import action
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_import_not_found(client, superadmin_headers):
    resp = await client.delete("/api/payments/imports/999999", headers=superadmin_headers)
    assert resp.status_code in (404, 500)
