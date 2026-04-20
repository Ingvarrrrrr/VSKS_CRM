---
phase: 13-v3-drag-drop-n
plan: 02
type: execute
wave: 2
depends_on:
  - "01"
files_modified:
  - backend/app/models/wish_item.py
  - backend/alembic/versions/o2p3q4r5s6t7_add_wish_item_target_column_key.py
  - backend/app/schemas/wishes.py
  - backend/app/routers/wishes.py
  - backend/tests/test_wish_approve_distribution.py
autonomous: true
requirements:
  - D-04
  - D-05
  - D-06
must_haves:
  truths:
    - "PATCH /api/wishes/{id}/items/{item_id} with {target_column_key} persists the move"
    - "POST /api/wishes/{id}/approve-distribution creates N purchases (one per column) atomically"
    - "On approve, wish.status becomes 'approved' and the wish becomes immutable (PUT returns 409)"
    - "Approve failure rolls back: zero purchases created, wish status unchanged"
  artifacts:
    - path: "backend/app/models/wish_item.py"
      provides: "WishItem.target_column_key column (VARCHAR(200) nullable)"
      contains: "target_column_key = Column"
    - path: "backend/alembic/versions/o2p3q4r5s6t7_add_wish_item_target_column_key.py"
      provides: "Alembic migration adding the column"
      contains: "op.add_column"
    - path: "backend/app/routers/wishes.py"
      provides: "PATCH /items/{item_id} endpoint + POST /approve-distribution endpoint"
      contains: "async def approve_distribution"
    - path: "backend/tests/test_wish_approve_distribution.py"
      provides: "Pytest for atomic transaction + rollback on failure"
      contains: "def test_approve_distribution_creates_n_purchases"
  key_links:
    - from: "WishItem.target_column_key"
      to: "product.category (fallback when null)"
      via: "read-time resolution in _resolve_column_key(item)"
      pattern: "target_column_key.*or.*product.category"
    - from: "approve-distribution endpoint"
      to: "Purchase table (status='wishes')"
      via: "INSERT N rows inside single db transaction, then wish.status='approved'"
      pattern: "status=.wishes."
    - from: "approve-distribution endpoint"
      to: "_create_assignment_chat_room"
      via: "import from app.routers.purchase_members (existing helper)"
      pattern: "from app.routers.purchase_members import _create_assignment_chat_room"
---

<objective>
Add backend machinery for drag-drop persistence and all-or-nothing approval. Implements CONTEXT D-04 (DnD scope — by structural constraint only: endpoint scoped by wish_id), D-05 (approve all-or-nothing), D-06 (N purchases in status='wishes').

Purpose: Plans 13-05 (kanban UI) and 13-07 (E2E) depend on these endpoints. No purchase-status migration needed — `status='wishes'` already exists (Purchase model default, line 26 in purchase.py).

**Wave note (revision 1):** This plan is **Wave 2**, dependent on **13-01**. The migration `o2p3q4r5s6t7_add_wish_item_target_column_key.py` chains `down_revision='n1o2p3q4r5s6'` (13-01's output). Running 13-01 and 13-02 in parallel on the same wave would create an Alembic chain race (missing revision). Wave-2 placement guarantees 13-01's revision exists before 13-02 applies.

Output:
- New column `wish_items.target_column_key VARCHAR(200) NULL`
- PATCH `/api/wishes/{wish_id}/items/{item_id}` accepts `{target_column_key: str|null}`
- POST `/api/wishes/{wish_id}/approve-distribution` → creates N purchases, returns `{wish_id, purchase_ids: [...], count: N, status: "approved"}`
- Server-side atomic transaction with pytest proving rollback on induced failure
</objective>

<execution_context>
@C:/Users/1/Desktop/Cursor/VSKS_CRM/.claude/get-shit-done/workflows/execute-plan.md
@C:/Users/1/Desktop/Cursor/VSKS_CRM/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/13-v3-drag-drop-n/CONTEXT.md
@.planning/phases/13-v3-drag-drop-n/13-01-product-category-not-null-PLAN.md

<interfaces>
From backend/app/models/wish_item.py (current — to extend):
```python
class WishItem(Base):
    __tablename__ = "wish_items"
    id = Column(Integer, primary_key=True, index=True)
    wish_id = Column(Integer, ForeignKey("wishes.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    item_name = Column(Text, nullable=False)
    item_type = Column(String(20), default="товар")
    quantity = Column(Numeric(15, 4), default=1)
    unit = Column(String(50), default="шт")
    unit_price = Column(Numeric(15, 2), default=0)
    total_price = Column(Numeric(15, 2), default=0)
    country_origin = Column(String(100), default="Россия")
    wish = relationship("Wish", back_populates="items")
```

From backend/app/models/purchase.py (target — create rows with these fields):
```python
class Purchase(Base):
    status = Column(String(30), default="wishes")  # already supports 'wishes' — no new migration needed
    subsidy_id, feo_category_id, subject, item_name, planned_quantity, planned_total_price, total_nmck, assigned_user_id
    items = relationship("PurchaseItem", ...)  # PurchaseItem must be cloned from WishItem
```

From backend/app/models/purchase_item.py (need to check structure — confirm columns match WishItem): item_name, item_type, quantity, unit, unit_price, total_price, product_id, country_origin, purchase_id.

From backend/app/routers/purchase_members.py line 36:
```python
async def _create_assignment_chat_room(
    db: AsyncSession,
    assignor_id: int,
    assignee_id: int,
    org_id: int,
    room_name: str,
) -> int:
```

From backend/app/routers/wishes.py (current endpoint shape, line 17):
```python
router = APIRouter(prefix="/api/wishes", tags=["wishes"])
```

RBAC constants from app/auth/jwt.py:
- `ALL_ROLES`, `MANAGER_ROLES`, `ADMIN_ROLES`
- Per CONTEXT: only users who can currently approve a wish (ADMIN_ROLES based on `convert_wish` pattern at line 252) may call `approve-distribution`. Use `require_role(*ADMIN_ROLES)`.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add WishItem.target_column_key column + migration + schema update</name>
  <read_first>
    - backend/app/models/wish_item.py (existing model, 20 lines)
    - backend/app/schemas/wishes.py (WishItemOut — add target_column_key: Optional[str])
    - backend/alembic/versions/n1o2p3q4r5s6_product_category_not_null.py (predecessor revision id — MUST exist on branch since 13-01 is in Wave 1 and this plan is Wave 2)
  </read_first>
  <behavior>
    - Test 1: Column `target_column_key` exists after upgrade, type VARCHAR(200), nullable=True.
    - Test 2: `WishItemOut` schema returns `target_column_key` field (null for existing items).
    - Test 3: Downgrade drops the column cleanly.
  </behavior>
  <action>
    Step 1: Add column to `backend/app/models/wish_item.py` after `country_origin` line:
    ```python
    target_column_key = Column(String(200), nullable=True)  # Phase 13 D-04: kanban column override; falls back to product.category when null
    ```

    Step 2: Create `backend/alembic/versions/o2p3q4r5s6t7_add_wish_item_target_column_key.py`:
    ```python
    """add wish_items.target_column_key

    Revision ID: o2p3q4r5s6t7
    Revises: n1o2p3q4r5s6
    Create Date: 2026-04-20
    """
    from alembic import op
    import sqlalchemy as sa

    revision = 'o2p3q4r5s6t7'
    down_revision = 'n1o2p3q4r5s6'  # 13-01 migration — guaranteed present (Wave 2 runs after Wave 1)
    branch_labels = None
    depends_on = None

    def upgrade() -> None:
        op.add_column('wish_items',
            sa.Column('target_column_key', sa.String(length=200), nullable=True))

    def downgrade() -> None:
        op.drop_column('wish_items', 'target_column_key')
    ```

    REVISION-1 NOTE: Previous draft warned about chain race when this plan was Wave 1. That concern is now resolved — this plan is Wave 2, 13-01's revision `n1o2p3q4r5s6` is guaranteed to be applied before this migration runs. Do NOT fall back to `h1i2j3k4l5m6`.

    Step 3: In `backend/app/schemas/wishes.py` `WishItemOut`, add:
    ```python
    target_column_key: Optional[str] = None
    ```
    Also in `WishItemIn` / WishCreate items payload shape (currently `Optional[list]`) — document in docstring that items may carry `target_column_key`.
  </action>
  <verify>
    <automated>cd backend && alembic upgrade head && python -c "from sqlalchemy import create_engine, inspect; import os; e=create_engine(os.environ['DATABASE_URL'].replace('+asyncpg','+psycopg2')); i=inspect(e); cols={c['name']: c for c in i.get_columns('wish_items')}; assert 'target_column_key' in cols and cols['target_column_key']['nullable'] is True; print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "target_column_key = Column" backend/app/models/wish_item.py`
    - File `backend/alembic/versions/o2p3q4r5s6t7_add_wish_item_target_column_key.py` exists
    - `grep -q "down_revision = 'n1o2p3q4r5s6'" backend/alembic/versions/o2p3q4r5s6t7_add_wish_item_target_column_key.py`
    - `grep -q "target_column_key: Optional\[str\]" backend/app/schemas/wishes.py`
    - `alembic upgrade head` succeeds with no error
    - `psql` inspection: `\\d wish_items` shows `target_column_key character varying(200)` (not NOT NULL)
  </acceptance_criteria>
  <done>
    Column exists, migration reversible, schema exposes field, no tests regress.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: PATCH /items/{item_id} + POST /approve-distribution endpoints with atomic transaction</name>
  <read_first>
    - backend/app/routers/wishes.py (existing endpoints, 304 lines — add to same file)
    - backend/app/routers/purchase_members.py line 36-71 (reuse `_create_assignment_chat_room`)
    - backend/app/models/purchase.py line 6-109 (Purchase fields — clone into new purchases)
    - backend/app/models/purchase_item.py (PurchaseItem fields — clone from WishItem)
    - backend/app/models/wish.py line 22 ("status" column values: draft/submitted/approved/rejected/converted)
    - backend/app/auth/jwt.py (ADMIN_ROLES export)
  </read_first>
  <behavior>
    - Test 1: `PATCH /api/wishes/{wid}/items/{iid}` with `{target_column_key: "Электроника"}` returns 200 and persists the value.
    - Test 2: `PATCH` with `target_column_key: null` clears the override.
    - Test 3: `PATCH` against a wish with `status='approved'` returns 409 Conflict (read-only).
    - Test 4: `POST /api/wishes/{wid}/approve-distribution` with items spanning 3 distinct keys creates exactly 3 purchases, each with correct items, all `status='wishes'`, and sets wish.status='approved'.
    - Test 5: `POST /approve-distribution` on a wish where a forced failure occurs mid-transaction rolls back — 0 purchases remain, wish still 'submitted'. (Induce failure via monkeypatch — see Task 3 for exact mechanism.)
    - Test 6: Second call to `/approve-distribution` on already-approved wish returns 400 with message "Заявка уже одобрена".
  </behavior>
  <action>
    In `backend/app/routers/wishes.py`, add TWO new endpoints after existing ones:

    ```python
    from app.schemas.wishes import WishItemPatch  # new — create below
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    from app.routers.purchase_members import _create_assignment_chat_room

    @router.patch("/{wish_id}/items/{item_id}")
    async def patch_wish_item(
        wish_id: int,
        item_id: int,
        body: WishItemPatch,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        """D-04: Drag-drop target update. Scoped to wish — cannot move items between wishes."""
        wish = await _load_wish(wish_id, db)
        if wish.status not in ("draft", "submitted"):
            raise HTTPException(409, "Заявка уже одобрена — редактирование запрещено")
        # Find item BELONGING TO THIS WISH
        item = next((i for i in wish.items if i.id == item_id), None)
        if item is None:
            raise HTTPException(404, "Позиция не найдена в данной заявке")
        # body.target_column_key may be None (clear) or string
        item.target_column_key = body.target_column_key
        await db.commit()
        await db.refresh(item)
        return {"id": item.id, "target_column_key": item.target_column_key}


    @router.post("/{wish_id}/approve-distribution")
    async def approve_distribution(
        wish_id: int,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_role(*ADMIN_ROLES)),
    ):
        """D-05/D-06: Atomic all-or-nothing approve. Creates N purchases (status='wishes'),
        one per non-empty target_column_key group, items distributed accordingly,
        wish.status='approved'. Rolls back entirely on any failure."""
        wish = await _load_wish(wish_id, db)
        if wish.status == "approved":
            raise HTTPException(400, "Заявка уже одобрена")
        if wish.status not in ("draft", "submitted"):
            raise HTTPException(400, f"Нельзя одобрить заявку в статусе {wish.status}")
        if not wish.items:
            raise HTTPException(400, "Заявка пустая — нечего одобрять")

        # Group items by resolved column key
        def resolve_key(it):
            if it.target_column_key:
                return it.target_column_key
            if it.product_id and it.product and it.product.category:
                return it.product.category
            return "__uncategorized__"

        # Preload products for resolution
        from sqlalchemy.orm import selectinload
        from app.models.product import Product
        res = await db.execute(
            select(WishItem).options(selectinload(WishItem.product)).where(WishItem.wish_id == wish_id)
        )
        items_full = res.scalars().all()

        groups: dict[str, list] = {}
        for it in items_full:
            groups.setdefault(resolve_key(it), []).append(it)

        if not groups:
            raise HTTPException(400, "Нет позиций для распределения")

        created_purchase_ids: list[int] = []
        # Begin atomic transaction — SQLAlchemy async session is already in a transaction
        try:
            for column_key, items_in_col in groups.items():
                total_nmck = sum(float(i.total_price or 0) for i in items_in_col)
                display_key = "Не определено" if column_key == "__uncategorized__" else column_key
                p = Purchase(
                    subsidy_id=wish.subsidy_id,
                    feo_category_id=wish.feo_category_id,
                    item_name=wish.title or f"Заявка #{wish.id}",
                    subject=f"{wish.title or 'Заявка'} — {display_key}",
                    planned_total_price=total_nmck,
                    total_nmck=total_nmck,
                    nmck=total_nmck,
                    status="wishes",
                    assigned_user_id=wish.assigned_to,
                    service_note_text=wish.justification,
                    service_note_by=wish.created_by,
                )
                db.add(p)
                await db.flush()  # get p.id
                created_purchase_ids.append(p.id)

                for wi in items_in_col:
                    pi = PurchaseItem(
                        purchase_id=p.id,
                        product_id=wi.product_id,
                        item_name=wi.item_name,
                        item_type=wi.item_type,
                        quantity=wi.quantity,
                        unit=wi.unit,
                        unit_price=wi.unit_price,
                        total_price=wi.total_price,
                        country_origin=wi.country_origin,
                    )
                    db.add(pi)
                await db.flush()

                # Create chat room per purchase if assignee differs from current user
                if wish.assigned_to and wish.assigned_to != current_user.id:
                    await _create_assignment_chat_room(
                        db, current_user.id, wish.assigned_to,
                        current_user.org_id or wish.org_id,
                        f"Закупка: {p.subject}",
                    )

            wish.status = "approved"
            wish.approved_by = current_user.id
            await db.commit()
        except Exception as e:
            await db.rollback()
            raise HTTPException(500, f"Ошибка при создании закупок — откат: {e}")

        return {
            "wish_id": wish.id,
            "purchase_ids": created_purchase_ids,
            "count": len(created_purchase_ids),
            "status": "approved",
        }
    ```

    Also add to `backend/app/schemas/wishes.py`:
    ```python
    class WishItemPatch(BaseModel):
        target_column_key: Optional[str] = None
    ```

    Note PurchaseItem field names — executor MUST verify against `backend/app/models/purchase_item.py`. If a field (e.g., `country_origin`) is missing on PurchaseItem, omit it from the clone.
  </action>
  <verify>
    <automated>cd backend && python -m pytest tests/test_wish_approve_distribution.py -x -v</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "async def approve_distribution" backend/app/routers/wishes.py`
    - `grep -q "async def patch_wish_item" backend/app/routers/wishes.py`
    - `grep -q "from app.routers.purchase_members import _create_assignment_chat_room" backend/app/routers/wishes.py`
    - `grep -q "class WishItemPatch" backend/app/schemas/wishes.py`
    - `grep -q "status=.wishes." backend/app/routers/wishes.py` (purchases created as 'wishes')
    - `grep -q "wish.status = .approved." backend/app/routers/wishes.py`
    - `grep -q "await db.rollback" backend/app/routers/wishes.py` (explicit rollback exists)
  </acceptance_criteria>
  <done>
    Both endpoints exist, pytest suite proves atomicity (rollback on failure), RBAC enforced, existing wish tests still pass.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Pytest suite for atomic approve-distribution + PATCH scope enforcement — FULL test bodies</name>
  <read_first>
    - backend/tests/ (existing patterns — look for test_wishes_*.py or similar)
    - backend/tests/conftest.py (auth fixtures, DB setup)
    - backend/app/routers/wishes.py (Task 2 result)
    - backend/app/models/wish.py, wish_item.py, purchase.py, purchase_item.py (field references)
  </read_first>
  <behavior>
    - Setup: Create a wish with 4 items — 2 with `product.category='Электроника'`, 1 with `product.category='Мебель'`, and 1 uncategorized (no product).
    - Test 1 (happy path): `POST /approve-distribution` → 200, returns `{count: 3}` (3 groups: Электроника, Мебель, __uncategorized__). After approve, `SELECT COUNT(*) FROM purchases WHERE id IN (...)` = 3, all `status='wishes'`, `wish.status='approved'`.
    - Test 2 (double approve 400): Second call returns 400 with message containing "уже одобрена".
    - Test 3 (PATCH blocked on approved 409): `PATCH /items/{iid}` on approved wish returns 409.
    - Test 4 (PATCH cross-wish 404): `PATCH /items/{iid}` where item belongs to a different wish returns 404 (enforces D-04 scope).
    - Test 5 (rollback on induced failure): monkeypatch `Purchase.__init__` to raise RuntimeError on the SECOND instantiation. Assert HTTP 500, assert zero new purchases for this wish in DB, assert wish.status still 'submitted'.
  </behavior>
  <action>
    Create `backend/tests/test_wish_approve_distribution.py`. REVISION-1: All test bodies are FULLY SPECIFIED below — no `pass` stubs. Executor implements these verbatim (only adjust fixture names if project conftest differs).

    Use the in-process `ASGITransport` pattern per Phase 16 STATE note (line 68).

    ```python
    import pytest
    from httpx import AsyncClient, ASGITransport
    from sqlalchemy import select, func
    from app import app
    from app.models.wish import Wish
    from app.models.wish_item import WishItem
    from app.models.purchase import Purchase
    from app.models.product import Product


    async def _seed_wish_with_mixed_items(db_session, test_org, test_user):
        """Create a wish with 4 items spanning 3 resolved column keys: Электроника, Мебель, __uncategorized__."""
        p_elec = Product(name="Laptop", category="Электроника", org_id=test_org.id)
        p_furn = Product(name="Chair", category="Мебель", org_id=test_org.id)
        db_session.add_all([p_elec, p_furn])
        await db_session.flush()

        w = Wish(org_id=test_org.id, title="Офис-комплект", status="submitted", created_by=test_user.id)
        db_session.add(w)
        await db_session.flush()

        db_session.add_all([
            WishItem(wish_id=w.id, product_id=p_elec.id, item_name="Laptop",
                     quantity=1, unit_price=50000, total_price=50000),
            WishItem(wish_id=w.id, product_id=p_elec.id, item_name="Mouse",
                     quantity=2, unit_price=1000, total_price=2000),
            WishItem(wish_id=w.id, product_id=p_furn.id, item_name="Chair",
                     quantity=3, unit_price=5000, total_price=15000),
            WishItem(wish_id=w.id, item_name="Прочее канцтовары",
                     quantity=1, unit_price=100, total_price=100),  # no product_id → uncategorized
        ])
        await db_session.commit()
        return w


    @pytest.mark.asyncio
    async def test_approve_distribution_creates_n_purchases(db_session, admin_headers, test_org, test_user):
        w = await _seed_wish_with_mixed_items(db_session, test_org, test_user)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(f"/api/wishes/{w.id}/approve-distribution", headers=admin_headers)

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["count"] == 3, f"expected 3 groups, got {body}"
        assert body["status"] == "approved"
        assert len(body["purchase_ids"]) == 3

        # Verify DB state: 3 purchases with status='wishes'
        purchases = (await db_session.execute(
            select(Purchase).where(Purchase.id.in_(body["purchase_ids"]))
        )).scalars().all()
        assert len(purchases) == 3
        assert all(p.status == "wishes" for p in purchases)

        # Verify wish is now approved
        await db_session.refresh(w)
        assert w.status == "approved"


    @pytest.mark.asyncio
    async def test_double_approve_returns_400(db_session, admin_headers, test_org, test_user):
        w = await _seed_wish_with_mixed_items(db_session, test_org, test_user)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            first = await c.post(f"/api/wishes/{w.id}/approve-distribution", headers=admin_headers)
            assert first.status_code == 200

            second = await c.post(f"/api/wishes/{w.id}/approve-distribution", headers=admin_headers)

        assert second.status_code == 400
        assert "уже одобрена" in second.json().get("detail", "").lower() or \
               "approved" in second.json().get("detail", "").lower()


    @pytest.mark.asyncio
    async def test_patch_item_blocked_when_approved(db_session, auth_headers, admin_headers, test_org, test_user):
        """D-05: wish becomes read-only after approve. PATCH /items/{iid} returns 409."""
        w = await _seed_wish_with_mixed_items(db_session, test_org, test_user)

        # Approve the wish
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            approve_resp = await c.post(f"/api/wishes/{w.id}/approve-distribution", headers=admin_headers)
            assert approve_resp.status_code == 200

            # Pick any item from the wish
            items = (await db_session.execute(
                select(WishItem).where(WishItem.wish_id == w.id)
            )).scalars().all()
            assert items, "fixture items missing"
            target_item = items[0]

            patch_resp = await c.patch(
                f"/api/wishes/{w.id}/items/{target_item.id}",
                json={"target_column_key": "Новая категория"},
                headers=auth_headers,
            )

        assert patch_resp.status_code == 409, patch_resp.text
        detail = patch_resp.json().get("detail", "")
        assert "одобрена" in detail.lower() or "редактирование" in detail.lower()


    @pytest.mark.asyncio
    async def test_patch_item_wrong_wish_returns_404(db_session, auth_headers, test_org, test_user):
        """D-04: cannot PATCH an item that belongs to a different wish."""
        # Wish A with its own item
        wa = Wish(org_id=test_org.id, title="Заявка A", status="submitted", created_by=test_user.id)
        db_session.add(wa)
        await db_session.flush()
        item_a = WishItem(wish_id=wa.id, item_name="Item A",
                          quantity=1, unit_price=10, total_price=10)
        db_session.add(item_a)

        # Wish B (different wish, used only for path param)
        wb = Wish(org_id=test_org.id, title="Заявка B", status="submitted", created_by=test_user.id)
        db_session.add(wb)
        await db_session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            # Attempt: PATCH via wish B's path but item A's id
            resp = await c.patch(
                f"/api/wishes/{wb.id}/items/{item_a.id}",
                json={"target_column_key": "X"},
                headers=auth_headers,
            )

        assert resp.status_code == 404, resp.text
        assert "не найдена" in resp.json().get("detail", "").lower() or \
               "not found" in resp.json().get("detail", "").lower()


    @pytest.mark.asyncio
    async def test_approve_distribution_rollback_on_failure(
        db_session, admin_headers, test_org, test_user, monkeypatch
    ):
        """D-05 atomicity: if ANY purchase creation fails mid-transaction, ALL purchases
        are rolled back and wish.status remains unchanged."""
        w = await _seed_wish_with_mixed_items(db_session, test_org, test_user)

        # Count existing purchases for this wish's subsidy BEFORE the call (should be 0 new ones after rollback)
        before_count = await db_session.scalar(
            select(func.count()).select_from(Purchase).where(
                Purchase.subsidy_id == w.subsidy_id
            )
        ) or 0

        # Induce failure: patch Purchase.__init__ to raise on the SECOND invocation
        import app.models.purchase as purchase_module
        original_init = purchase_module.Purchase.__init__
        call_count = {"n": 0}

        def faulty_init(self, *args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise RuntimeError("Induced failure for rollback test (2nd purchase)")
            original_init(self, *args, **kwargs)

        monkeypatch.setattr(purchase_module.Purchase, "__init__", faulty_init)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(f"/api/wishes/{w.id}/approve-distribution", headers=admin_headers)

        # Endpoint wraps the exception → HTTP 500 with "откат" in detail
        assert resp.status_code == 500, resp.text
        assert "откат" in resp.json().get("detail", "").lower() or \
               "rollback" in resp.json().get("detail", "").lower() or \
               "induced failure" in resp.json().get("detail", "").lower()

        # Critical assertions: zero new purchases, wish status unchanged
        await db_session.rollback()  # clear any stale session state
        after_count = await db_session.scalar(
            select(func.count()).select_from(Purchase).where(
                Purchase.subsidy_id == w.subsidy_id
            )
        ) or 0
        assert after_count == before_count, (
            f"Rollback failed: {after_count - before_count} purchases leaked into DB. "
            f"Transaction was NOT atomic."
        )

        await db_session.refresh(w)
        assert w.status == "submitted", (
            f"Wish status changed to {w.status!r} despite rollback — atomicity broken."
        )
    ```

    Fixtures (`db_session`, `auth_headers`, `admin_headers`, `test_org`, `test_user`) must exist in `backend/tests/conftest.py`. If any are missing, extend conftest.py minimally — do NOT rewrite it. `admin_headers` should return a JWT for a user with a role in ADMIN_ROLES; `auth_headers` is a regular authenticated user.
  </action>
  <verify>
    <automated>cd backend && python -m pytest tests/test_wish_approve_distribution.py -x -v</automated>
  </verify>
  <acceptance_criteria>
    - File `backend/tests/test_wish_approve_distribution.py` exists
    - `grep -cE "async def test_" backend/tests/test_wish_approve_distribution.py` returns exactly 5
    - NO `pass` or `...` as the sole body of any test function: `grep -A1 "async def test_" backend/tests/test_wish_approve_distribution.py | grep -E "^\s*(pass|\.\.\.)\s*$"` returns nothing
    - `grep -q "monkeypatch.setattr.*Purchase" backend/tests/test_wish_approve_distribution.py` (rollback test uses real monkeypatch)
    - `grep -q "assert after_count == before_count" backend/tests/test_wish_approve_distribution.py` (rollback assertion is real)
    - `grep -q "assert w.status == .submitted." backend/tests/test_wish_approve_distribution.py` (wish-status assertion is real)
    - `pytest tests/test_wish_approve_distribution.py` → 5 passed
    - Full backend pytest suite green (no regressions)
  </acceptance_criteria>
  <done>
    All 5 tests pass with REAL assertion bodies (no stubs). Atomic transaction verified: induced failure produces HTTP 500, zero purchases created, wish status unchanged. DnD scope (D-04) enforced at endpoint level (404 on cross-wish item access). Read-only gate (D-05) enforced (409 on approved wish).
  </done>
</task>

</tasks>

<verification>
- Migration `o2p3q4r5s6t7` applied (chains after 13-01's `n1o2p3q4r5s6`)
- Endpoints respond per contract (manual curl with JWT)
- `pytest tests/test_wish_approve_distribution.py` → 5 passed
- `pytest backend/tests/` full suite — no regressions
</verification>

<success_criteria>
1. `wish_items.target_column_key` column exists, nullable
2. PATCH endpoint persists target_column_key, scoped to wish
3. POST /approve-distribution creates N purchases atomically, with status='wishes'
4. Rollback verified by induced-failure test (real monkeypatch, real DB assertion)
5. RBAC: only ADMIN_ROLES can approve
6. Wish becomes read-only (status='approved') after successful approval
</success_criteria>

<output>
After completion, create `.planning/phases/13-v3-drag-drop-n/13-02-SUMMARY.md`
</output>
