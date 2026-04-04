# Phase 6: Analytics + Budget History — Research

**Researched:** 2026-04-03
**Domain:** FastAPI audit-log model + async write hook + paginated REST + Vue 3 timeline dialog
**Confidence:** HIGH (all findings sourced from direct codebase inspection)

---

## Summary

Phase 6 requires three deliverables: (1) a `BudgetHistory` SQLAlchemy model + DB table, (2) write hooks in two places in the existing backend (purchases `update_purchase` and subsidies `update_subsidy`), (3) a `GET /api/subsidies/{id}/history` paginated endpoint, and (4) a budget history timeline dialog in `SubsidiesView.vue`.

The `budget_history` table is mentioned in HANDOFF.md as "ready in DB" but it is an orphaned, empty table — there is no SQLAlchemy model anywhere, no router, no write path, and zero frontend references. Everything must be built from scratch. The pattern for creating new tables in this project is: define a SQLAlchemy model class, import it in `backend/app/models/__init__.py`, then run `python /app/init_db.py` (which calls `Base.metadata.create_all`) or `python /app/check_schema.py --apply` inside the container.

The standard pagination pattern in this codebase (confirmed in `contractors.py`) uses `offset: int = Query(0, ge=0)` + `limit: int = Query(50, ge=1, le=200)` query parameters and returns `{"items": [...], "total": N}`. The frontend uses `apiFetch<T>(path, options)` for all API calls. Dialogs in SubsidiesView follow the established pattern: `v-dialog v-model="showXxxDialog"` with state declared via `ref(false)` and a trigger button in the subsidy card action row.

**Primary recommendation:** Create `BudgetHistory` model → register it → run `create_all` → add write helpers in purchases + subsidies → add paginated endpoint in subsidies router → add `BudgetHistoryDialog.vue` component → wire into SubsidiesView.

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| BUDGET-07 | Every change to a subsidy's `limit` (`budget` field) or a purchase's `planned_total_price` must write a record to `budget_history` with `changed_at`, `changed_by`, `old_value`, `new_value`, `reason` | Write hook must be inserted before `await db.commit()` in `update_purchase` (purchases.py line 773) and `update_subsidy` (subsidies.py line 181) |
| BUDGET-08 | `GET /api/subsidies/{id}/history` returns paginated records from `budget_history` | New route added to `subsidies.py`; response shape `{"items": [...], "total": N}` matching codebase pagination convention |
| BUDGET-09 | Subsidy detail view includes a timeline/modal showing budget history | New `BudgetHistoryDialog.vue` component + trigger button in the subsidy card in SubsidiesView.vue |
</phase_requirements>

---

## Standard Stack

### Core (already in project — no new installs needed)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy async | already installed | ORM model for `budget_history` table | entire backend uses it |
| FastAPI | already installed | paginated endpoint | entire backend uses it |
| Vue 3 + Vuetify 3 | already installed | timeline dialog UI | entire frontend uses it |
| `apiFetch` (`frontend/src/api.ts`) | project utility | HTTP calls from Vue | used everywhere in SubsidiesView |

### No new packages required.

---

## Architecture Patterns

### Recommended Project Structure for New Files
```
backend/app/models/budget_history.py       # new SQLAlchemy model
backend/app/models/__init__.py             # add import (required for create_all + check_schema)
backend/app/routers/subsidies.py           # add GET /{id}/history endpoint (append to file)
backend/app/routers/purchases.py           # add write hook inside update_purchase
backend/app/schemas/schemas.py             # add BudgetHistoryOut schema
backend/app/__init__.py                    # no change needed (subsidies router already registered)
frontend/src/components/BudgetHistoryDialog.vue   # new standalone dialog component
frontend/src/views/SubsidiesView.vue       # wire in dialog: button + component + state
```

### Pattern 1: SQLAlchemy Audit-Log Model

Modelled directly on `PurchaseEvent` and `TaskChange` which are the two existing audit tables in this codebase:

```python
# backend/app/models/budget_history.py
from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from app.database import Base

class BudgetHistory(Base):
    __tablename__ = "budget_history"

    id = Column(Integer, primary_key=True)
    subsidy_id = Column(Integer, ForeignKey("subsidies.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    purchase_id = Column(Integer, ForeignKey("purchases.id", ondelete="SET NULL"),
                         nullable=True, index=True)
    entity_type = Column(String(20), nullable=False)   # "subsidy" | "purchase"
    old_value = Column(Numeric(15, 2), nullable=True)
    new_value = Column(Numeric(15, 2), nullable=True)
    changed_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    changed_by_name = Column(String(200), nullable=True)   # denormalised for history readability
    reason = Column(Text, nullable=True)
    changed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
```

Key design decisions:
- `purchase_id` is nullable — subsidy limit changes have no purchase
- `entity_type` discriminates the two write paths ("subsidy" vs "purchase")
- `changed_by_name` is denormalised (same pattern as `TaskChange.changed_by_name`) so history is readable even after user deletion
- `old_value` / `new_value` use `Numeric(15,2)` matching `planned_total_price` column type in `Purchase` and `budget` (Float in Subsidy model but Numeric is safer for money)
- `reason` is nullable Text — requirement says "reason" field should exist; will be NULL for programmatic changes unless passed explicitly

### Pattern 2: Model Registration

After creating the model file, two places must be updated:

```python
# backend/app/models/__init__.py  — append at bottom
from app.models.budget_history import BudgetHistory
```

This is mandatory: `check_schema.py` and `init_db.py` both do `import app.models` to populate `Base.metadata`. Without this import, the table is never created by `create_all` and never checked by `check_schema`.

### Pattern 3: Write Hook in update_purchase

Insert immediately before `await db.commit()` at line 773 of `purchases.py`:

```python
# Inside update_purchase(), AFTER setattr loop, BEFORE await db.commit()
old_planned = float(old_planned_total_price or 0)   # captured before setattr loop
new_planned = float(p.planned_total_price or 0)
if old_planned != new_planned and p.subsidy_id:
    from app.models.budget_history import BudgetHistory
    db.add(BudgetHistory(
        subsidy_id=p.subsidy_id,
        purchase_id=p.id,
        entity_type="purchase",
        old_value=old_planned,
        new_value=new_planned,
        changed_by_id=current_user.id,
        changed_by_name=current_user.full_name or current_user.username,
        reason=None,
    ))
```

**Critical detail:** `old_planned_total_price` must be captured from the DB object BEFORE the `setattr` loop at line 720. The pattern: `old_planned_total_price = p.planned_total_price` immediately after line 683 (`result.scalar_one_or_none()`).

**Watch out for the frozen-total logic:** Lines 700-711 show that `p.planned_total_price` is NOT updated when `is_contracted` is True. The write hook must check the final value of `p.planned_total_price`, not `data.planned_total_price`.

### Pattern 4: Write Hook in update_subsidy

Insert immediately before `await db.commit()` in `update_subsidy` (subsidies.py, after line 181):

```python
# Inside update_subsidy(), AFTER setattr loop, BEFORE await db.commit()
old_budget_val = old_budget   # captured before setattr loop
new_budget_val = db_subsidy.budget
if old_budget_val != new_budget_val:
    from app.models.budget_history import BudgetHistory
    db.add(BudgetHistory(
        subsidy_id=subsidy_id,
        purchase_id=None,
        entity_type="subsidy",
        old_value=old_budget_val,
        new_value=new_budget_val,
        changed_by_id=current_user.id,
        changed_by_name=current_user.full_name or current_user.username,
        reason=None,
    ))
```

Capture `old_budget = db_subsidy.budget` after the SELECT at line 173, before the `setattr` loop at line 176.

### Pattern 5: Paginated History Endpoint

Follows exactly the pattern from `contractors.py` lines 380-415:

```python
# Append to backend/app/routers/subsidies.py
from app.models.budget_history import BudgetHistory as BudgetHistoryModel

@router.get("/{subsidy_id}/history")
async def get_budget_history(
    subsidy_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from sqlalchemy import func as safunc
    base_q = select(BudgetHistoryModel).where(
        BudgetHistoryModel.subsidy_id == subsidy_id
    ).order_by(BudgetHistoryModel.changed_at.desc())

    total = (await db.execute(
        select(safunc.count()).select_from(base_q.subquery())
    )).scalar() or 0

    rows = (await db.execute(base_q.offset(offset).limit(limit))).scalars().all()

    return {
        "total": total,
        "items": [
            {
                "id": r.id,
                "entity_type": r.entity_type,
                "purchase_id": r.purchase_id,
                "old_value": float(r.old_value) if r.old_value is not None else None,
                "new_value": float(r.new_value) if r.new_value is not None else None,
                "changed_by_name": r.changed_by_name,
                "reason": r.reason,
                "changed_at": r.changed_at.isoformat() if r.changed_at else None,
            }
            for r in rows
        ],
    }
```

### Pattern 6: Vue Timeline Dialog Component

Follows the pattern of `BudgetDrillDownDialog.vue` (already in `frontend/src/components/`):
- `v-dialog` wrapping, `v-model="dialog"` prop
- `defineExpose({ open })` pattern or emit approach
- `apiFetch` for data loading
- `watch` on open state to trigger load

Minimal structure for `BudgetHistoryDialog.vue`:
```vue
<template>
  <v-dialog v-model="dialog" max-width="800" scrollable>
    <v-card>
      <v-card-title>История бюджета: {{ subsidyName }}</v-card-title>
      <v-card-text>
        <v-timeline density="compact" side="end">
          <v-timeline-item
            v-for="item in items" :key="item.id"
            :dot-color="item.entity_type === 'subsidy' ? 'orange' : 'blue'"
            size="small"
          >
            <div class="text-caption text-medium-emphasis">{{ formatDate(item.changed_at) }} — {{ item.changed_by_name }}</div>
            <div>{{ entityLabel(item) }}: {{ fmt(item.old_value) }} → {{ fmt(item.new_value) }}</div>
            <div v-if="item.reason" class="text-caption">{{ item.reason }}</div>
          </v-timeline-item>
        </v-timeline>
        <!-- pagination controls -->
      </v-card-text>
    </v-card>
  </v-dialog>
</template>
```

Vuetify 3 `v-timeline` is available (Vuetify 3.x ships it). Use `density="compact"` and `side="end"` for a right-aligned compact layout that fits the existing UI style.

### Pattern 7: Wire into SubsidiesView

Add in the subsidy card actions row (near line 60-62 in the template, next to other icon buttons):
```vue
<v-btn icon="mdi-history" size="x-small" variant="text" color="blue-grey"
       title="История бюджета" @click.stop="openHistoryDialog(s)" />
```

Add dialog at end of template (after existing dialogs, before closing `</template>`):
```vue
<BudgetHistoryDialog ref="historyDialogRef" />
```

Add state in `<script setup>`:
```typescript
import BudgetHistoryDialog from '@/components/BudgetHistoryDialog.vue'
const historyDialogRef = ref<InstanceType<typeof BudgetHistoryDialog> | null>(null)
function openHistoryDialog(s: SubsidyRow) {
  historyDialogRef.value?.open(s.id, s.name)
}
```

### Anti-Patterns to Avoid

- **Writing history AFTER commit:** If `db.add(BudgetHistory(...))` is placed after `await db.commit()`, it will be a separate transaction. Place it BEFORE `await db.commit()` so the history row and the value change are atomic.
- **Using `data.planned_total_price` in hook:** The request body value may differ from what is actually saved (frozen logic for contracted status). Always read `p.planned_total_price` after all assignments.
- **Global import at module top:** The `BudgetHistory` import in `purchases.py` should be local (inside the function) to avoid circular imports — follow the same pattern as the existing `from app.models.purchase import Purchase` local imports in `subsidies.py`.
- **Not registering model in `__init__.py`:** `check_schema.py` will not detect or create the table. This is the single most common deployment gap.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Timeline UI | Custom CSS list | Vuetify `v-timeline` | Ships with Vuetify 3; density/side props handle layout |
| Pagination | Custom offset math | `q.offset(offset).limit(limit)` | Already the codebase pattern; SQLAlchemy does it natively |
| Date formatting in Vue | Custom format fn | `new Date(s).toLocaleString('ru-RU')` | One-liner; no lib needed for display-only formatting |
| DB table creation | Manual `CREATE TABLE` SQL | SQLAlchemy model + `create_all` | The project toolchain (`init_db.py`, `check_schema.py`) handles it |

---

## Common Pitfalls

### Pitfall 1: `budget_history` table already exists with different columns
**What goes wrong:** The DB table was created manually (or from an old init) with different column names than the new model. `check_schema.py --apply` adds missing columns but cannot rename or drop existing ones.
**Why it happens:** HANDOFF.md says the table is "ready in DB" but no model was ever committed; the real schema is unknown.
**How to avoid:** Before deploying the model, connect to the running DB container and run `\d budget_history` to inspect actual columns. If column names differ from the model, either rename in the model to match, or drop and recreate (table is empty per HANDOFF.md).
**Warning signs:** `check_schema.py --apply` reports 0 missing columns but the model has columns the DB doesn't — meaning existing columns were already misnamed.

### Pitfall 2: `old_value` captured after `setattr` loop overwrites it
**What goes wrong:** `old_planned_total_price = p.planned_total_price` is placed after the `setattr` loop, capturing the NEW value instead of the old.
**How to avoid:** Capture old values immediately after fetching the DB object (`result.scalar_one_or_none()`), before any mutation. Same for `old_budget` in subsidies.

### Pitfall 3: History written for no-change saves
**What goes wrong:** Every PUT to a purchase writes a history row even when `planned_total_price` didn't change, polluting the history table.
**How to avoid:** Guard with `if old_planned != new_planned` (use numeric comparison, not string).

### Pitfall 4: Subsidy `budget` vs `calculated_budget` confusion
**What goes wrong:** `subsidies.py` uses TWO budget fields — `budget` (the user-set limit) and `calculated_budget` (computed from FEO tree). BUDGET-07 says "change to a subsidy's limit" — this means `budget`, not `calculated_budget`. `calculated_budget` is auto-derived and should not trigger history writes.
**How to avoid:** Only compare `db_subsidy.budget` (before/after), not `calculated_budget`.

### Pitfall 5: Model not in `__init__.py` causes silent table-not-created
**What goes wrong:** `BudgetHistory` model file exists but is not imported in `backend/app/models/__init__.py`. `Base.metadata.create_all` silently skips it. No error is thrown; the table just doesn't exist. First write attempt fails with `relation "budget_history" does not exist`.
**How to avoid:** Always add the import to `__init__.py` immediately after creating the model file.

### Pitfall 6: `v-timeline` not rendered if history is empty
**What goes wrong:** Component shows nothing (no message) when the subsidy has no history entries yet, making it look broken.
**How to avoid:** Add explicit empty state: `<div v-if="items.length === 0">Изменений ещё не было</div>`.

---

## Code Examples

### Existing Pagination Pattern (contractors.py lines 384-415)
```python
offset: int = Query(0, ge=0),
limit: int = Query(50, ge=1, le=200),
# ...
count_q = select(safunc.count()).select_from(q.subquery())
total = (await db.execute(count_q)).scalar() or 0
contractors = (await db.execute(q.offset(offset).limit(limit))).scalars().all()
# returns list directly (no wrapper object — but for history, use {"total": N, "items": [...]})
```

### Existing Model Pattern: DateTime with server_default (purchase_event.py)
```python
created_at = Column(DateTime(timezone=True), server_default=func.now())
```

### Existing Dialog Pattern in SubsidiesView (line 920)
```vue
<v-dialog v-model="showApproversDialog" max-width="700" scrollable>
  ...
</v-dialog>
```
State: `const showApproversDialog = ref(false)`

### Existing apiFetch Call Pattern (SubsidiesView line 2302)
```typescript
const res = await apiFetch<any>('/subsidies/', { method: 'POST', body })
```

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| Manual SQL migrations (Alembic) | `check_schema.py --apply` + `create_all` | New tables: add model + import in `__init__.py`, run `init_db.py` |
| n8n middleware | Direct API calls | No n8n dependency for this phase |

---

## Open Questions

1. **What columns does the existing `budget_history` DB table actually have?**
   - What we know: HANDOFF.md says it exists; no SQLAlchemy model was ever created.
   - What's unclear: Column names in the live DB may differ from what we define in the model.
   - Recommendation: Task Wave 0 should connect to DB and run `\d budget_history`. If columns match requirements, adapt model to match. If table is empty and columns are wrong, drop and recreate.

2. **Should `reason` be capturable from the UI?**
   - What we know: BUDGET-07 says record "reason" field; no UI requirement specifies a reason input.
   - What's unclear: Whether admins need to enter a reason when changing subsidy limit, or if it's always NULL.
   - Recommendation: Store NULL for programmatic changes. The field is there for future use. No UI reason-input needed for Phase 6.

3. **Does `create_purchase` also need a write hook?**
   - What we know: BUDGET-07 says "every change to... a purchase's planned_total_price". Creating a new purchase sets `planned_total_price` for the first time (old_value = NULL or 0).
   - Recommendation: Yes, hook into `create_purchase` as well with `old_value=None`, `new_value=new_planned`. Keep it consistent so history shows creation events too.

---

## Sources

### Primary (HIGH confidence — direct codebase inspection)
- `backend/app/routers/purchases.py` — `update_purchase` function, budget check pattern, `planned_total_price` mutation logic
- `backend/app/routers/subsidies.py` — `update_subsidy` function, budget field update pattern
- `backend/app/routers/contractors.py` lines 380-415 — canonical pagination pattern in codebase
- `backend/app/models/purchase_event.py` — audit log model pattern (`DateTime + func.now`, JSONB data)
- `backend/app/models/task_change.py` — audit log with `changed_by_name` denormalisation
- `backend/app/models/__init__.py` — model registration mechanism
- `backend/check_schema.py` — confirms: only ALTER TABLE for new columns; new tables need `create_all`
- `backend/init_db.py` — confirms: `Base.metadata.create_all` creates new tables
- `backend/app/__init__.py` — subsidies router already registered; no new router registration needed
- `backend/app/auth/jwt.py` — `ADMIN_ROLES`, `MANAGER_ROLES` constants; `get_current_user` dep pattern
- `frontend/src/views/SubsidiesView.vue` — dialog registration pattern, `apiFetch` usage, state refs
- `frontend/src/components/BudgetDrillDownDialog.vue` — component structure pattern
- `HANDOFF.md` line 407 — confirms `budget_history` table exists in DB but is empty

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all patterns sourced directly from production code
- Architecture: HIGH — hooks placed at exact line numbers from code inspection
- Pitfalls: HIGH — derived from actual code logic (frozen-total, dual-budget, missing __init__)

**Research date:** 2026-04-03
**Valid until:** 2026-05-03 (stable stack, no fast-moving dependencies)
