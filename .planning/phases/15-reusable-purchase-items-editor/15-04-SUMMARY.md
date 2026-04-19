---
phase: 15-reusable-purchase-items-editor
plan: 04
subsystem: ui
tags: [vue3, wishes, purchase-items-editor, excel-import, product-catalog]

# Dependency graph
requires:
  - phase: 15-01
    provides: PurchaseItemsEditor.vue component with wish-shape branch, purchaseId-aware import
provides:
  - WishesView.vue Section 2 wired with PurchaseItemsEditor in wish mode
  - saveWish helper-field stripper (no _selectedProduct/_photo_url/_description/_description_44fz in POST/PUT body)
affects:
  - backend/app/routers/wishes.py (items body now clean — no UI-local keys)
  - Plan 15-05 (E2E automation + UAT gate tests WishesView with new editor)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - PurchaseItemsEditor mounted with item-shape=wish and :purchase-id=null for client-side Excel apply path
    - Helper-field stripper pattern in saveWish (same as CreateOrderView after Plan 15-03)

key-files:
  created: []
  modified:
    - frontend/src/views/WishesView.vue

key-decisions:
  - ":readonly=false used because dialog only opens for draft wishes — status check unnecessary"
  - "wishForm.items typed as any[] to accept EditorItem fields (product_id, _selectedProduct, etc.)"
  - "totalNmck computed retained in WishesView (reads total_price from EditorItem, compatible)"

patterns-established:
  - "All wish item saves must strip helper fields via .map(({ _selectedProduct, _photo_url, _description, _description_44fz, ...rest }) => rest)"

requirements-completed:
  - ITEMS-EDITOR-07

# Metrics
duration: 15min
completed: 2026-04-19
---

# Phase 15 Plan 04: WishesView PurchaseItemsEditor Wiring — Summary

**WishesView Section 2 "Позиции" replaced with PurchaseItemsEditor (wish-shape, purchase-id=null) giving Заявка full parity with Новый заказ: product autocomplete, photo tooltip, full product card dialog, client-side Excel import, smart import.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-04-19T12:30:00Z
- **Completed:** 2026-04-19T12:45:00Z
- **Tasks:** 2 auto + 1 checkpoint:manual
- **Files modified:** 1

## Accomplishments

- Replaced 100+ lines of simple v-table (raw text fields, no autocomplete, no photo) in WishesView with single `<PurchaseItemsEditor>` mount
- Removed local `addItem`, `removeItem`, `calcItemTotal` methods — all owned by component now
- Patched `saveWish` to strip UI-local helper fields before POST/PUT — prevents backend schema rejection

## Line Delta

WishesView.vue: 1035 lines → 935 lines (**-100 lines net**, within plan estimate of 40-100)

## Task Commits

1. **Task 1: Mount PurchaseItemsEditor in WishesView.vue Section 2** - `f1c5273` (feat)
2. **Task 2: Patch saveWish to strip UI-local helper fields** - `f407d24` (fix)

## Files Created/Modified

- `frontend/src/views/WishesView.vue` — Section 2 replaced, addItem/removeItem/calcItemTotal deleted, import added, saveWish patched

## WishesView-Specific Wiring Notes

### readonly derivation
The `:readonly="false"` binding is correct: the edit dialog (`wishDialog`) only opens when `wish.status === 'draft'` (see template line 101: `v-if="wish.status === 'draft'"`). There is no need to derive readonly from `wishForm.status` — the form only appears for editable wishes. If the dialog is ever extended to open approved/converted wishes in read-only mode, add a `wishFormReadonly` ref and pass it here.

### wishForm.items typing
Changed from `WishItem[]` to `any[]` to accept `EditorItem` shape (which adds `product_id`, `_selectedProduct`, `_photo_url`, `_description`, `_description_44fz`). The local `WishItem` interface remains for list-view rendering but is no longer used in `wishForm`.

### totalNmck compatibility
The existing `totalNmck` computed (`wishForm.value.items.reduce((sum, i) => sum + (i.total_price || 0), 0)`) remains unchanged — `EditorItem` carries `total_price` just like the old `WishItem`, so the computed works without modification.

### Helper-field stripper location
Applied in the shared `payload` construction block that feeds both PUT and POST paths. Single point of truth — both save paths are covered.

## Decisions Made

- `:readonly="false"` — dialog only opens for drafts, no dynamic readonly needed
- `wishForm.items` typed `any[]` — EditorItem is a superset of WishItem, TypeScript satisfied
- `totalNmck` computed retained — reads `total_price` which EditorItem has

## Deviations from Plan

None — plan executed exactly as written. The `:readonly` binding was simplified from `wishForm.status === 'approved' || ...` to `false` because `wishForm` has no `status` field (deviation avoided a TSC error that would have blocked Task 1).

**Deviation (minor):** `:readonly="false"` instead of `wishForm.status` check
- **Found during:** Task 1
- **Issue:** `wishForm` ref has no `status` field — accessing `wishForm.status` returns `undefined`, TypeScript would warn; more importantly, the edit dialog is guarded at call-site (`v-if="wish.status === 'draft'"`), making the runtime check redundant
- **Fix:** Used `:readonly="false"` — semantically equivalent since dialog only opens for drafts
- **Files modified:** `frontend/src/views/WishesView.vue`
- **Rule:** Rule 1 (auto-fix — prevents potential TS error and incorrect behavior)

## Verification Results

### tsc --noEmit (after Task 1)
```
(no output — 0 errors)
```

### tsc --noEmit (after Task 2)
```
(no output — 0 errors)
```

### npm run build (after Task 2)
```
✓ built in 17.26s
PWA v1.2.0 — generateSW — 33 entries precached
```

### Acceptance Criteria

| Criterion | Result |
|-----------|--------|
| `grep -c "<PurchaseItemsEditor" WishesView.vue` ≥ 1 | 1 |
| `grep -c 'item-shape="wish"' WishesView.vue` ≥ 1 | 1 |
| `grep -c ':purchase-id="null"' WishesView.vue` ≥ 1 | 1 |
| `grep -c "import PurchaseItemsEditor" WishesView.vue` ≥ 1 | 1 |
| `grep -n 'v-model="item.item_name"' WishesView.vue` = 0 | 0 |
| `grep -c "function addItem\|function calcItemTotal" WishesView.vue` = 0 | 0 |
| `grep -cE "wishForm\\.value\\.items\\.map.*_selectedProduct" WishesView.vue` ≥ 1 | 1 |
| `grep -c "_description_44fz" WishesView.vue` ≥ 1 | 1 |
| `grep -c "_photo_url" WishesView.vue` ≥ 1 | 1 |
| tsc --noEmit exits 0 | PASS |
| npm run build exits 0 | PASS |

## Task 3: Manual Smoke Test (checkpoint:manual)

Task 3 is a `checkpoint:manual` task. The automated gate (tsc + build) has passed. The 14 manual smoke steps are documented below for the tester:

### 14-Step Smoke Checklist

| Step | Action | Expected | Status |
|------|--------|----------|--------|
| 1 | Navigate to «Заявки» → «Создать заявку» | Dialog opens, Section 2 shows PurchaseItemsEditor toolbar (not a plain table) | PENDING |
| 2 | Pick a subsidy + FEO 3-level | Subsidy and FEO selects cascade correctly | PENDING |
| 3 | Click «Добавить позицию» button in the editor toolbar | Product picker dialog opens (not a raw text field) | PENDING |
| 4 | Type a product name in the picker search | Catalogue suggestions appear with photo thumb + unit_price | PENDING |
| 5 | Select a catalogue item | Row fills: name, type, unit_price, country_origin="Россия". Photo thumb visible in row | PENDING |
| 6 | Hover the photo thumb | 200×200 preview tooltip appears | PENDING |
| 7 | Click «Создать полную карточку» in the picker | Full product dialog opens with all fields | PENDING |
| 8 | Fill name, category, price, upload a photo → Save | Product saved; row populates with new product and photo thumb | PENDING |
| 9 | Confirm new product row has photo thumb | Photo thumb renders in the items table | PENDING |
| 10 | Click «Импорт из файла» → upload 3-row .xlsx | Step 1 (file drop) → Step 2 (column mapper) appears | PENDING |
| 11 | Map columns → click «Применить»; **check Network tab** | 3 rows appear. **No call to `/api/purchases/.../items/import-mapped`** (purchase-id=null → client-side apply) | PENDING |
| 12 | Click «Сохранить» | POST /api/wishes/ fires with all items | PENDING |
| 13 | **Inspect Network tab POST body** `items` array | Each item has ONLY: product_id, item_name, item_type, quantity, unit, unit_price, total_price, country_origin (and optional id). **No** `_selectedProduct`, `_photo_url`, `_description` keys | PENDING |
| 14 | Reload wish from list (click edit) | All items persist with photos, prices, quantities | PENDING |

### Network Payload Sample (Step 13 — expected shape after stripper)

```json
{
  "items": [
    {
      "product_id": 42,
      "item_name": "Ноутбук Dell XPS 13",
      "item_type": "товар",
      "quantity": 2,
      "unit": "шт.",
      "unit_price": 120000,
      "total_price": 240000,
      "country_origin": "Россия"
    }
  ]
}
```

Fields that must NOT appear: `_selectedProduct`, `_photo_url`, `_description`, `_description_44fz`, `final_unit_price`, `final_total`, `feo_planned_item_id`

## Issues Encountered

None — both auto tasks completed cleanly on first attempt.

## Known Stubs

None — PurchaseItemsEditor is fully wired. All interactions (product picker, photo upload, Excel import, smart import) use real API endpoints. The `purchase-id=null` path uses client-side row assembly from import-preview data (not a stub — this is the correct behavior per 15-01 design).

## Next Phase Readiness

- Plan 15-05 (E2E automation + UAT gate) can now cover WishesView with the full editor
- Заявка ↔ Новый заказ parity is complete on position editing

---
*Phase: 15-reusable-purchase-items-editor*
*Completed: 2026-04-19*
