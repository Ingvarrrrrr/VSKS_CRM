"""Tests for Phase 13 Plan 03: wish service note endpoint (D-07).

Covers:
  - 200 response with valid .docx content-type for a wish with items
  - Response body > 1000 bytes (real document, not stub)
  - Content-Disposition contains SZ_Wish_{id}.docx
  - docx.Document(BytesIO(content)) parseability — confirms valid .docx structure
  - 404 for non-existent wish id
  - 200 with initiator_id query param (SubsidyApprover lookup doesn't crash)
  - 401 without auth (get_current_user dependency)

All test bodies are fully specified — no pass/... stubs.
"""
import pytest
import pytest_asyncio
from io import BytesIO
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app import app
from app.models.wish import Wish
from app.models.wish_item import WishItem


# ---------------------------------------------------------------------------
# Helper: check whether service_note.docx template is present in the container
# ---------------------------------------------------------------------------

def _template_exists() -> bool:
    """Return True if service_note.docx is available at the expected path."""
    import os
    return os.path.exists("/app/templates/service_note.docx")


_SKIP_NO_TEMPLATE = pytest.mark.skipif(
    not _template_exists(),
    reason="service_note.docx not available in test environment — template-dependent tests skipped",
)


# ---------------------------------------------------------------------------
# Test 1: Happy path — GET returns 200 with valid .docx content
# ---------------------------------------------------------------------------

@_SKIP_NO_TEMPLATE
@pytest.mark.asyncio
async def test_generate_wish_service_note_returns_docx(db_session, auth_headers, test_org, test_user):
    """GET /api/wishes/{id}/documents/service_note returns a parseable .docx (D-07)."""
    # Arrange: wish with one item
    w = Wish(
        org_id=test_org.id,
        title="Тестовая заявка для СЗ",
        status="draft",
        created_by=test_user.id,
    )
    db_session.add(w)
    await db_session.flush()
    db_session.add(WishItem(
        wish_id=w.id,
        item_name="Ноутбук тестовый",
        quantity=2,
        unit="шт",
        unit_price=50000,
        total_price=100000,
    ))
    await db_session.commit()
    await db_session.refresh(w)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(
            f"/api/wishes/{w.id}/documents/service_note",
            headers=auth_headers,
        )

    # Status + content-type
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    ct = resp.headers.get("content-type", "")
    assert "wordprocessingml" in ct, f"Expected .docx content-type, got: {ct!r}"

    # Content-Disposition
    cd = resp.headers.get("content-disposition", "")
    assert f"SZ_Wish_{w.id}.docx" in cd, f"Expected SZ_Wish_{w.id}.docx in Content-Disposition, got: {cd!r}"

    # Non-trivial body size — real .docx, not empty stub
    assert len(resp.content) > 1000, (
        f"Response body too small ({len(resp.content)} bytes) — likely not a real .docx"
    )

    # W7 (revision 1): parseability check — must be a valid, openable .docx
    from docx import Document as _DocxDoc
    _DocxDoc(BytesIO(resp.content))  # raises zipfile.BadZipFile or similar if invalid


# ---------------------------------------------------------------------------
# Test 2: 404 for non-existent wish
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_service_note_404_for_missing_wish(auth_headers):
    """GET on a non-existent wish_id returns 404."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(
            "/api/wishes/9999999/documents/service_note",
            headers=auth_headers,
        )
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
    detail = resp.json().get("detail", "") or resp.json().get("message", "")
    assert (
        "не найдена" in detail.lower() or "not found" in detail.lower()
    ), f"Expected 'не найдена' in detail, got: {detail!r}"


# ---------------------------------------------------------------------------
# Test 3: With initiator_id — endpoint doesn't crash even if approver not found
# ---------------------------------------------------------------------------

@_SKIP_NO_TEMPLATE
@pytest.mark.asyncio
async def test_service_note_with_initiator_id(db_session, auth_headers, test_org, test_user):
    """GET with initiator_id=9999999 (non-existent approver) still returns 200.

    Endpoint gracefully falls back to creator name when initiator not found.
    """
    w = Wish(
        org_id=test_org.id,
        title="Заявка с инициатором",
        status="submitted",
        created_by=test_user.id,
    )
    db_session.add(w)
    await db_session.flush()
    db_session.add(WishItem(
        wish_id=w.id,
        item_name="Мышь беспроводная",
        quantity=5,
        unit="шт",
        unit_price=1500,
        total_price=7500,
    ))
    await db_session.commit()
    await db_session.refresh(w)

    # Non-existent initiator_id — should not crash, fallback to creator name
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(
            f"/api/wishes/{w.id}/documents/service_note?initiator_id=9999999",
            headers=auth_headers,
        )

    assert resp.status_code == 200, f"Expected 200 with unknown initiator_id, got {resp.status_code}: {resp.text}"
    ct = resp.headers.get("content-type", "")
    assert "wordprocessingml" in ct, f"Expected .docx content-type, got: {ct!r}"
    assert len(resp.content) > 1000, (
        f"Response body too small ({len(resp.content)} bytes) — likely not a real .docx"
    )

    # Parseability check
    from docx import Document as _DocxDoc
    _DocxDoc(BytesIO(resp.content))  # must not raise


# ---------------------------------------------------------------------------
# Test 4: Wish with NO items — endpoint returns 200 with empty items list
# ---------------------------------------------------------------------------

@_SKIP_NO_TEMPLATE
@pytest.mark.asyncio
async def test_service_note_wish_with_no_items(db_session, auth_headers, test_org, test_user):
    """GET on a wish with zero items returns 200 (empty items list is valid)."""
    w = Wish(
        org_id=test_org.id,
        title="Пустая заявка",
        status="draft",
        created_by=test_user.id,
    )
    db_session.add(w)
    await db_session.commit()
    await db_session.refresh(w)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(
            f"/api/wishes/{w.id}/documents/service_note",
            headers=auth_headers,
        )

    assert resp.status_code == 200, f"Expected 200 for empty wish, got {resp.status_code}: {resp.text}"
    assert len(resp.content) > 1000, "Expected non-trivial .docx even with empty items"

    from docx import Document as _DocxDoc
    _DocxDoc(BytesIO(resp.content))


# ---------------------------------------------------------------------------
# Test 5: No auth → 401
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_service_note_requires_auth():
    """GET without Authorization header returns 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/wishes/1/documents/service_note")
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"
