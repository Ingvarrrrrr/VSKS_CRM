---
phase: 13-v3-drag-drop-n
plan: 03
type: execute
wave: 3
depends_on:
  - 02
files_modified:
  - backend/app/routers/wish_documents.py
  - backend/app/__init__.py
  - backend/tests/test_wish_service_note.py
autonomous: true
requirements:
  - D-07
must_haves:
  truths:
    - "GET /api/wishes/{id}/documents/service_note returns a valid .docx download"
    - "Endpoint works BEFORE approve (no purchase_id exists yet) — builds context from Wish + WishItems directly"
    - "initiator_id query param populates {{initiator_name}} / {{initiator_role}} in template"
  artifacts:
    - path: "backend/app/routers/wish_documents.py"
      provides: "New router with GET /api/wishes/{id}/documents/service_note"
      contains: "async def generate_wish_service_note"
    - path: "backend/app/__init__.py"
      provides: "Registers wish_documents router"
      contains: "wish_documents"
    - path: "backend/tests/test_wish_service_note.py"
      provides: "Pytest: 200 response, valid .docx content-type, non-empty body"
      contains: "def test_generate_wish_service_note_returns_docx"
  key_links:
    - from: "wish_documents router"
      to: "service_note.docx template at /app/templates/service_note.docx"
      via: "docxtpl.DocxTemplate load + render with wish-shaped context"
      pattern: "DocxTemplate.*service_note.docx"
    - from: "backend/app/__init__.py include_router"
      to: "wish_documents.router"
      via: "app.include_router(wish_documents.router) BEFORE any catch-all/regex routers (follows pattern established in commit 3d37cf9)"
      pattern: "app.include_router.wish_documents"
---

<objective>
Add `GET /api/wishes/{id}/documents/service_note?initiator_id=X` endpoint that generates a Служебная записка .docx from Wish data (NOT from a Purchase, since approval hasn't happened yet).

Purpose: D-07 requires a download button in WishesView (Plan 13-06) BEFORE the wish is approved. Existing `documents.py` contract is keyed on `purchase_id` — we build a parallel router keyed on `wish_id` rather than contort the existing one (per CONTEXT open question #5, option A "предпочтительнее — не размывает контракт documents.py").

Output: Single new router file `wish_documents.py` exposing one endpoint. Re-uses the existing `service_note.docx` template and the same docxtpl library. Template variable names align with `documents.py` context keys (initiator_name, initiator_role, items, subsidy_name, today, item_names, item_categories) so the same template file works for both purchase and wish service notes.
</objective>

<execution_context>
@C:/Users/1/Desktop/Cursor/VSKS_CRM/.claude/get-shit-done/workflows/execute-plan.md
@C:/Users/1/Desktop/Cursor/VSKS_CRM/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/13-v3-drag-drop-n/CONTEXT.md
@.planning/phases/13-v3-drag-drop-n/13-02-wish-distribution-approve-PLAN.md

<interfaces>
From backend/app/routers/documents.py (REFERENCE PATTERN — do not duplicate all fields; service_note template uses a subset):
```python
DOC_TYPES = { "service_note": ("service_note.docx", "SZ_Organizaciya"), ... }
TEMPLATES_DIR = "/app/templates"

# Key helpers to reuse (copy from documents.py or import):
def _fmt_date(d) -> str
def _fmt_money(v) -> str
def _resolve_photo(photo_url)  # InlineImage helper

# Minimal service_note context keys (confirmed from DOC_TYPES + TEMPLATE_VARIABLES list):
{
  "purchase_number": str, "registry_number": str, "subject": str,
  "subsidy_name": str, "subsidy_year": int,
  "initiator_name": str, "initiator_role": str,
  "items": [{"num", "name", "description", "type", "quantity", "unit", "unit_price", "total_price", "photo"}],
  "items_count": int, "item_names": str, "item_categories": str,
  "total_nmck": str, "today": str,
  "responsible_person": str,
}
```

From backend/app/models/wish.py:
- Wish.title, org_id, subsidy_id, feo_category_id, justification, creator (User), items (WishItem[])

From backend/app/models/subsidy_approver.py (existing — reused for initiator_id lookup, same pattern as documents.py line 314):
```python
result = await db.execute(select(SubsidyApprover).where(SubsidyApprover.id == initiator_id))
initiator = result.scalar_one_or_none()
```

Router registration pattern from backend/app/__init__.py (line 11 has imports, include_router calls follow later in file).
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Create wish_documents router with service_note endpoint</name>
  <read_first>
    - backend/app/routers/documents.py (especially lines 243-436 — generate_document flow, item context building, initiator lookup)
    - backend/app/models/wish.py (Wish with creator, items, subsidy relationships)
    - backend/app/models/wish_item.py (WishItem fields)
    - backend/app/models/product.py (for product.description and product.photo_url lookup per wish_item.product_id)
    - backend/app/routers/wishes.py lines 34-51 (_load_wish pattern — reuse eager loading)
    - .planning/phases/13-v3-drag-drop-n/CONTEXT.md (D-07, open question #5)
  </read_first>
  <behavior>
    - Test 1: GET without auth → 401
    - Test 2: GET on non-existent wish → 404
    - Test 3: GET on valid wish → 200, Content-Type starts with `application/vnd.openxmlformats-officedocument.wordprocessingml.document`, Content-Disposition has `filename*=UTF-8''SZ_Wish_<id>.docx`
    - Test 4: GET with `initiator_id=X` where X is a valid SubsidyApprover → initiator_name populated; template renders without error
    - Test 5: Response body is non-empty bytes (>1000 bytes) — confirms real .docx, not stub
  </behavior>
  <action>
    Create `backend/app/routers/wish_documents.py`:

    ```python
    """Wish documents router — generates docx service notes for wishes (D-07, Phase 13).

    Separate from documents.py to keep contracts clean:
      - documents.py is keyed on purchase_id
      - wish_documents.py is keyed on wish_id (no purchase yet — pre-approval)
    """
    import os
    from io import BytesIO
    from datetime import date
    from urllib.parse import quote
    from typing import Optional

    from fastapi import APIRouter, Depends, HTTPException, Query
    from fastapi.responses import StreamingResponse
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.database import get_db
    from app.auth.jwt import get_current_user
    from app.models.wish import Wish
    from app.models.wish_item import WishItem
    from app.models.product import Product
    from app.models.subsidy import Subsidy
    from app.models.subsidy_approver import SubsidyApprover
    # Reuse formatters from documents.py
    from app.routers.documents import _fmt_date, _fmt_money, TEMPLATES_DIR

    router = APIRouter(prefix="/api/wishes", tags=["wish-documents"])


    @router.get("/{wish_id}/documents/service_note")
    async def generate_wish_service_note(
        wish_id: int,
        initiator_id: Optional[int] = Query(default=None, description="ID инициатора (SubsidyApprover)"),
        responsible_name: Optional[str] = Query(default=None),
        db: AsyncSession = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        # Load wish with eager relations (same pattern as wishes.py _load_wish)
        result = await db.execute(
            select(Wish)
            .options(
                selectinload(Wish.creator),
                selectinload(Wish.subsidy),
                selectinload(Wish.items).selectinload(WishItem.product),
            )
            .where(Wish.id == wish_id)
        )
        w = result.scalar_one_or_none()
        if not w:
            raise HTTPException(404, "Заявка не найдена")

        # Template path — subsidy-specific override, same rule as documents.py
        template_file = "service_note.docx"
        template_path = os.path.join(TEMPLATES_DIR, template_file)
        if w.subsidy_id:
            subsidy_override = f"/app/uploads/templates/subsidies/{w.subsidy_id}/service_note.docx"
            if os.path.exists(subsidy_override):
                template_path = subsidy_override
        if not os.path.exists(template_path):
            raise HTTPException(404, f"Шаблон {template_file} не найден")

        # Initiator
        initiator = None
        if initiator_id:
            res = await db.execute(select(SubsidyApprover).where(SubsidyApprover.id == initiator_id))
            initiator = res.scalar_one_or_none()

        # Build docxtpl template + photo helper (copy minimal version from documents.py)
        try:
            from docxtpl import DocxTemplate, InlineImage
            from docx.shared import Cm
            tpl = DocxTemplate(template_path)
        except Exception as e:
            raise HTTPException(500, f"Ошибка загрузки шаблона: {e}")

        UPLOADS_DIR = "/app/uploads/products"
        def _resolve_photo(photo_url):
            if not photo_url: return ""
            url = str(photo_url).strip()
            if url.startswith("/api/products/photos/"):
                path = f"{UPLOADS_DIR}/{url.split('/')[-1]}"
                if os.path.exists(path):
                    try: return InlineImage(tpl, path, width=Cm(2.5))
                    except Exception: return ""
            return ""

        # Build items list (same shape as documents.py items_list)
        items_list = []
        for idx, it in enumerate(w.items or [], start=1):
            items_list.append({
                "num": idx,
                "name": it.item_name or "",
                "description": (it.product.description if it.product else "") or "",
                "type": it.item_type or "",
                "quantity": float(it.quantity) if it.quantity else "",
                "unit": it.unit or "",
                "unit_price": _fmt_money(it.unit_price),
                "total_price": _fmt_money(it.total_price),
                "photo": _resolve_photo(it.product.photo_url if it.product else None),
            })

        # Unique categories (for {{item_categories}})
        categories = list(dict.fromkeys(
            it.product.category for it in (w.items or []) if it.product and it.product.category
        ))

        total_nmck = sum(float(i.total_price or 0) for i in (w.items or []))
        creator_full = (w.creator.full_name if w.creator else "") or (w.creator.username if w.creator else "")

        context = {
            # Заявка (masquerade as purchase for template compatibility)
            "purchase_number": f"заявка #{w.id}",
            "registry_number": f"WISH-{w.id}",
            "subject": w.title or "",
            "subsidy_name": w.subsidy.name if w.subsidy else "",
            "subsidy_year": w.subsidy.year if w.subsidy else "",
            "initiator_name": (initiator.full_name if initiator else creator_full) or "",
            "initiator_role": (initiator.role_name if initiator else "") or "",
            "items": items_list,
            "items_count": len(items_list),
            "item_names": ", ".join(i["name"] for i in items_list if i["name"]),
            "item_categories": ", ".join(categories),
            "total_nmck": _fmt_money(total_nmck),
            "nmck": _fmt_money(total_nmck),
            "today": _fmt_date(date.today()),
            "today_iso": date.today().isoformat(),
            "responsible_person": responsible_name or creator_full or "",
            # Any other template keys used in service_note.docx but not relevant for wish → empty string
            "contract_number": "", "contract_date": "", "contract_price": "",
            "contractor_name": "", "contractor_inn": "",
            "feo_path": "", "feo_level_1": "", "feo_level_2": "", "feo_level_3": "",
            "approvers": [],
        }

        try:
            tpl.render(context)
            buf = BytesIO()
            tpl.save(buf)
            buf.seek(0)
        except Exception as e:
            raise HTTPException(500, f"Ошибка генерации: {e}")

        safe_name = f"SZ_Wish_{w.id}.docx"
        encoded = quote(safe_name, safe="-_.~")
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
        )
    ```

    Register in `backend/app/__init__.py`:
    Step 1: Add to imports block (around line 11-17):
    ```python
    from .routers import wish_documents
    ```
    Step 2: Add include_router call — IMPORTANT position: AFTER `documents.router` and `documents_guide_router` (to keep the wishes domain near other wishes routers) AND BEFORE `tasks.router` (which has broad path patterns):
    ```python
    app.include_router(wish_documents.router)
    ```
    Add it right after `app.include_router(wishes.router)` — confirm by grepping `app.include_router(wishes.router)` in the file.
  </action>
  <verify>
    <automated>cd backend && python -c "from app import app; routes=[str(r.path) for r in app.routes]; assert '/api/wishes/{wish_id}/documents/service_note' in routes, f'route missing; routes={routes}'; print('OK: route registered')"</automated>
  </verify>
  <acceptance_criteria>
    - File `backend/app/routers/wish_documents.py` exists
    - `grep -q "async def generate_wish_service_note" backend/app/routers/wish_documents.py`
    - `grep -q "from .routers import.*wish_documents\|from .routers import wish_documents" backend/app/__init__.py`
    - `grep -q "app.include_router(wish_documents.router)" backend/app/__init__.py`
    - Route `/api/wishes/{wish_id}/documents/service_note` present in `app.routes`
    - Backend starts without ImportError
  </acceptance_criteria>
  <done>
    Endpoint is registered, imports clean, route resolves. Body proves via pytest in Task 2.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Pytest for wish service note endpoint</name>
  <read_first>
    - backend/tests/conftest.py (auth fixture pattern)
    - backend/app/routers/wish_documents.py (Task 1 output)
    - backend/tests/test_wish_approve_distribution.py (from Plan 13-02 — reuse fixtures)
  </read_first>
  <behavior>
    - Test 1: GET returns 200 with .docx content-type for a valid wish with items
    - Test 2: Response body length > 1000 bytes (real document, not empty stub)
    - Test 3: Content-Disposition header contains `SZ_Wish_{wid}.docx`
    - Test 4: 404 for non-existent wish id
    - Test 5: With `initiator_id` query param, endpoint still returns 200 (initiator lookup doesn't crash)
  </behavior>
  <action>
    Create `backend/tests/test_wish_service_note.py`:

    ```python
    import pytest
    from httpx import AsyncClient, ASGITransport
    from app import app
    from app.models.wish import Wish
    from app.models.wish_item import WishItem

    @pytest.mark.asyncio
    async def test_generate_wish_service_note_returns_docx(db_session, auth_headers, test_org, test_user):
        w = Wish(org_id=test_org.id, title="Тестовая заявка", status="draft", created_by=test_user.id)
        db_session.add(w)
        await db_session.flush()
        db_session.add(WishItem(wish_id=w.id, item_name="Item 1", quantity=1, unit_price=100, total_price=100))
        await db_session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(f"/api/wishes/{w.id}/documents/service_note", headers=auth_headers)

        assert resp.status_code == 200, resp.text
        assert "wordprocessingml" in resp.headers.get("content-type", "")
        assert f"SZ_Wish_{w.id}.docx" in resp.headers.get("content-disposition", "")
        assert len(resp.content) > 1000
        # W7 (revision 1): parseability check — must be a real, openable .docx, not garbage bytes
        from io import BytesIO
        from docx import Document as _DocxDoc
        _DocxDoc(BytesIO(resp.content))  # raises if not a valid .docx

    @pytest.mark.asyncio
    async def test_service_note_404_for_missing_wish(auth_headers):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/wishes/9999999/documents/service_note", headers=auth_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_service_note_with_initiator_id(db_session, auth_headers, test_org, test_user):
        # ... create wish + SubsidyApprover → call with initiator_id → expect 200
        pass
    ```

    Note: If `service_note.docx` template file is not present in `/app/templates/` during CI, mock or skip with `pytest.skip("template not available in test env")`. Alternatively, place a minimal `.docx` stub in `backend/tests/fixtures/` and set TEMPLATES_DIR env var for the test. Executor decides based on actual CI setup.
  </action>
  <verify>
    <automated>cd backend && python -m pytest tests/test_wish_service_note.py -x -v</automated>
  </verify>
  <acceptance_criteria>
    - File `backend/tests/test_wish_service_note.py` exists
    - `grep -cE "async def test_" backend/tests/test_wish_service_note.py` returns at least 3
    - `pytest tests/test_wish_service_note.py` → all pass (or skip with clear reason if template missing)
    - W7 (revision 1): `grep -q "docx import Document\|from docx import Document" backend/tests/test_wish_service_note.py` — docx parseability assertion present
    - Response body must be parseable by `docx.Document(BytesIO(response.content))` without raising
  </acceptance_criteria>
  <done>
    Endpoint verified: returns valid .docx, handles missing wish, accepts initiator_id.
  </done>
</task>

</tasks>

<verification>
- `/api/wishes/{id}/documents/service_note` endpoint responds 200
- Response is valid .docx (openable in Word)
- `pytest tests/test_wish_service_note.py` green
- Full test suite still green
</verification>

<success_criteria>
1. New router file exists and is registered
2. Endpoint returns a proper .docx with Content-Disposition header
3. Works with and without initiator_id param
4. Handles 404 cleanly
5. Uses existing service_note.docx template (no new template needed)
</success_criteria>

<output>
After completion, create `.planning/phases/13-v3-drag-drop-n/13-03-SUMMARY.md`
</output>
