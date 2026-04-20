---
phase: 13-v3-drag-drop-n
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - backend/alembic/versions/n1o2p3q4r5s6_product_category_not_null.py
  - backend/tests/test_product_category_required.py
autonomous: true
requirements:
  - D-03
must_haves:
  truths:
    - "Existing products with NULL category get backfilled to 'Прочее' before NOT NULL constraint applies"
    - "POST /api/products/ without category returns 422 validation error"
    - "Existing tests pass unchanged"
  artifacts:
    - path: "backend/alembic/versions/n1o2p3q4r5s6_product_category_not_null.py"
      provides: "Alembic migration: backfill NULL→'Прочее' then ALTER COLUMN products.category SET NOT NULL"
      contains: "def upgrade"
    - path: "backend/tests/test_product_category_required.py"
      provides: "Pytest case verifying 422 when creating product without category"
      contains: "def test_create_product_without_category_returns_422"
  key_links:
    - from: "alembic migration"
      to: "products.category column"
      via: "UPDATE products SET category='Прочее' WHERE category IS NULL; ALTER COLUMN ... SET NOT NULL"
      pattern: "ALTER COLUMN.*category.*SET NOT NULL"
    - from: "Product model"
      to: "DB schema"
      via: "nullable=False on category Column"
      pattern: "nullable=False"
---

<objective>
Flip `products.category` from nullable to NOT NULL with a safe backfill of 'Прочее' for existing NULL rows. Implements CONTEXT D-03 (backend half). Frontend validation lands in Plan 13-04 (wave 1 parallel).

Purpose: Guarantees every new wish item resolves to a known kanban column in Plan 13-05 — the kanban relies on `product.category` as column-identity. Avoid the "Не определено" column swelling in practice.

Output: One Alembic migration, one pytest spec, one model update (`backend/app/models/product.py` line 16 `nullable=True` → `nullable=False`).
</objective>

<execution_context>
@C:/Users/1/Desktop/Cursor/VSKS_CRM/.claude/get-shit-done/workflows/execute-plan.md
@C:/Users/1/Desktop/Cursor/VSKS_CRM/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/ROADMAP.md
@.planning/phases/13-v3-drag-drop-n/CONTEXT.md

<interfaces>
From backend/app/models/product.py (current):
```python
class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(Text, nullable=False)
    category = Column(String(200), nullable=True)  # ← CHANGE TO nullable=False
    ...
```

Latest Alembic revision head (from `backend/alembic/versions/`):
- `h1i2j3k4l5m6_add_wish_items_and_wish_fields.py` (from Phase 13-v2, h1i2j3k4l5m6)

Migration chain pattern (confirm in any existing versions file):
```python
revision = 'n1o2p3q4r5s6'
down_revision = 'h1i2j3k4l5m6'
branch_labels = None
depends_on = None
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Create Alembic migration with backfill + NOT NULL constraint</name>
  <read_first>
    - backend/app/models/product.py (line 16 — current `category` column definition)
    - backend/alembic/versions/h1i2j3k4l5m6_add_wish_items_and_wish_fields.py (follow style for revision/down_revision)
    - backend/alembic/versions/g8h9i0j1k2l3_add_wish_fields_category_priority_date_link.py (another style reference)
    - .planning/phases/13-v3-drag-drop-n/CONTEXT.md (D-03)
  </read_first>
  <behavior>
    - Test 1: Running `alembic upgrade head` on a DB with rows where `products.category IS NULL` must leave zero NULLs AND set the column to NOT NULL.
    - Test 2: After upgrade, inserting a product with category=NULL fails at the DB level (IntegrityError).
    - Test 3: `alembic downgrade -1` restores nullable=True without data loss (category values remain as-is, including 'Прочее' backfills).
  </behavior>
  <action>
    Create `backend/alembic/versions/n1o2p3q4r5s6_product_category_not_null.py`.

    Exact revision metadata:
    ```python
    """product category NOT NULL with backfill

    Revision ID: n1o2p3q4r5s6
    Revises: h1i2j3k4l5m6
    Create Date: 2026-04-20
    """
    from alembic import op
    import sqlalchemy as sa

    revision = 'n1o2p3q4r5s6'
    down_revision = 'h1i2j3k4l5m6'
    branch_labels = None
    depends_on = None
    ```

    upgrade() body:
    ```python
    def upgrade() -> None:
        # Step 1: backfill NULL rows with 'Прочее' (per CONTEXT D-03)
        op.execute("UPDATE products SET category = 'Прочее' WHERE category IS NULL")
        # Step 2: flip constraint
        op.alter_column(
            'products', 'category',
            existing_type=sa.String(length=200),
            nullable=False,
        )
    ```

    downgrade() body:
    ```python
    def downgrade() -> None:
        op.alter_column(
            'products', 'category',
            existing_type=sa.String(length=200),
            nullable=True,
        )
        # Do NOT revert 'Прочее' backfill — cannot distinguish original NULLs from user-entered 'Прочее'
    ```

    Also update `backend/app/models/product.py` line 16: change `category = Column(String(200), nullable=True)` to `category = Column(String(200), nullable=False, default='Прочее')` (per D-03 — default covers edge case of ORM-level inserts without explicit category; DB-level NOT NULL is the source of truth).
  </action>
  <verify>
    <automated>cd backend && alembic upgrade head && python -c "from sqlalchemy import create_engine, inspect; import os; e=create_engine(os.environ['DATABASE_URL'].replace('+asyncpg','+psycopg2')); i=inspect(e); cols=[c for c in i.get_columns('products') if c['name']=='category']; assert cols and cols[0]['nullable'] is False, f'category still nullable: {cols}'; print('OK: products.category is NOT NULL')"</automated>
  </verify>
  <acceptance_criteria>
    - File `backend/alembic/versions/n1o2p3q4r5s6_product_category_not_null.py` exists
    - `grep -q "down_revision = 'h1i2j3k4l5m6'" backend/alembic/versions/n1o2p3q4r5s6_product_category_not_null.py`
    - `grep -q "UPDATE products SET category = 'Прочее'" backend/alembic/versions/n1o2p3q4r5s6_product_category_not_null.py`
    - `grep -q "nullable=False" backend/alembic/versions/n1o2p3q4r5s6_product_category_not_null.py`
    - `grep -q "category = Column(String(200), nullable=False" backend/app/models/product.py`
    - After `alembic upgrade head`: `psql $DATABASE_URL -c "SELECT COUNT(*) FROM products WHERE category IS NULL"` returns 0
  </acceptance_criteria>
  <done>
    Migration file exists, runs cleanly up/down, `products.category` is NOT NULL in DB, all existing tests still pass.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Backend validation test — POST /api/products/ without category returns 422</name>
  <read_first>
    - backend/app/routers/products.py (find POST endpoint + request schema for create-product)
    - backend/app/schemas/schemas.py (find ProductCreate pydantic model — make `category: str` required, not Optional)
    - backend/tests/ (find existing conftest.py pattern for auth fixtures — e.g., test_*.py files)
  </read_first>
  <behavior>
    - Test 1: `POST /api/products/` with body missing `category` → HTTP 422, response JSON contains `{"detail": [...{"loc": ["body", "category"], ...}]}`.
    - Test 2: `POST /api/products/` with `category: ""` (empty string) → HTTP 422 (category must be non-empty string).
    - Test 3: `POST /api/products/` with `category: "Электроника"` → HTTP 201 with product body.
  </behavior>
  <action>
    Step 1: In `backend/app/schemas/schemas.py`, locate `ProductCreate` (or `ProductIn`/`ProductBase`). Change `category` field from `Optional[str] = None` to `category: str = Field(..., min_length=1)`.

    Step 2: Create `backend/tests/test_product_category_required.py`:
    ```python
    import pytest
    from httpx import AsyncClient, ASGITransport
    from app import app

    @pytest.mark.asyncio
    async def test_create_product_without_category_returns_422(auth_headers):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/api/products/",
                json={"name": "Test product", "item_kind": "товар"},
                headers=auth_headers,
            )
            assert resp.status_code == 422, resp.text
            body = resp.json()
            assert any(err["loc"][-1] == "category" for err in body["detail"])

    @pytest.mark.asyncio
    async def test_create_product_with_empty_category_returns_422(auth_headers):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/api/products/",
                json={"name": "Test", "category": "", "item_kind": "товар"},
                headers=auth_headers,
            )
            assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_product_with_category_returns_201(auth_headers):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/api/products/",
                json={"name": "Test", "category": "Электроника", "item_kind": "товар"},
                headers=auth_headers,
            )
            assert resp.status_code in (200, 201), resp.text
    ```

    Use the existing `auth_headers` fixture pattern from any `test_*.py` in `backend/tests/`. If no fixture exists, create a minimal one in `backend/tests/conftest.py` that returns a JWT for a test superadmin.
  </action>
  <verify>
    <automated>cd backend && python -m pytest tests/test_product_category_required.py -x -v</automated>
  </verify>
  <acceptance_criteria>
    - File `backend/tests/test_product_category_required.py` exists
    - `grep -q "category: str" backend/app/schemas/schemas.py` (ProductCreate)
    - `grep -q "test_create_product_without_category_returns_422" backend/tests/test_product_category_required.py`
    - `pytest tests/test_product_category_required.py` → 3 passed
    - No other test in `backend/tests/` regresses (full suite still green)
  </acceptance_criteria>
  <done>
    Schema requires category; pytest suite validates 422 for missing/empty and 201 for valid; no regressions in other tests.
  </done>
</task>

</tasks>

<verification>
- `alembic upgrade head` succeeds
- `SELECT COUNT(*) FROM products WHERE category IS NULL` returns 0
- `pytest backend/tests/test_product_category_required.py` passes 3/3
- `pytest backend/tests/` (full suite) — no regressions
- `grep nullable=False backend/app/models/product.py` finds category line
</verification>

<success_criteria>
1. DB schema: `products.category VARCHAR(200) NOT NULL`
2. Existing products all have a non-NULL category ('Прочее' for previously NULL ones)
3. API rejects product creation without category with HTTP 422
4. Migration is reversible (downgrade works)
5. No other tests regress
</success_criteria>

<output>
After completion, create `.planning/phases/13-v3-drag-drop-n/13-01-SUMMARY.md`
</output>
