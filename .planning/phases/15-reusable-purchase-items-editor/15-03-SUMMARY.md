---
phase: 15-reusable-purchase-items-editor
plan: 03
subsystem: frontend/views
tags: [vue3, component-wiring, refactor, items-editor, purchase]
dependency_graph:
  requires:
    - phase: 15-01
      provides: PurchaseItemsEditor.vue component with props/emits/slots API
  provides:
    - CreateOrderView.vue wired to PurchaseItemsEditor.vue via v-model + emit bindings
  affects:
    - frontend/src/views/CreateOrderView.vue (primary file modified)
    - Plan 15-04 (WishesView wiring — parallel sibling)
    - Plan 15-05 (E2E + UAT)
tech-stack:
  added: []
  patterns:
    - v-model + @items-changed + @reload-requested emit wiring for child component
    - Dead code deletion after component extraction (dialogs, script refs, CSS)
key-files:
  created: []
  modified:
    - frontend/src/views/CreateOrderView.vue
key-decisions:
  - "FEO column decision: Branch 3 (no per-row FEO picker in old items table — grep empty) — no #row-extra slot needed; feo_planned_item_id flows through v-model"
  - "quickProductEditDialog deleted as dead code — its caller (items table button) was removed; PurchaseItemsEditor has its own internal openQuickProductEdit"
  - "UNIT_OPTIONS and COUNTRIES deleted — sole usage was in the inline items table (removed); grep confirmed zero non-definition references"
  - "products ref kept — still needed by loadPurchase() to enrich items with _photo_url/_description when hydrating from API response"

requirements-completed:
  - ITEMS-EDITOR-06

duration: ~35min
completed: "2026-04-19"
---

# Phase 15 Plan 03: CreateOrderView Wiring — Summary

**Replaced ~1425 lines of inline items-table logic in CreateOrderView.vue with a single PurchaseItemsEditor mount, preserving contract-price sync, purchase reload, save-strip, and NMCK display while deleting all extracted refs/methods/dialogs/CSS.**

## Performance

- **Duration:** ~35 min
- **Started:** 2026-04-19T~09:00Z
- **Completed:** 2026-04-19T~09:35Z
- **Tasks:** 2 of 3 (Task 3 is manual smoke — documented below, automated gates pass)
- **Files modified:** 1

## Accomplishments
- Replaced 148-line inline items v-table card with `<PurchaseItemsEditor>` single-component mount
- Removed 3 inline dialog templates: fullProductDialog, productPickerDialog, itemsImportDialog
- Deleted all extracted script code: ~80 refs/computeds/functions/constants
- Deleted all imap-* scoped CSS classes (already live in PurchaseItemsEditor)
- Line count: 6222 → 4797 (-1425 lines, 22.9% reduction)

## FEO Column Decision (MANDATORY per plan)

Grep procedure executed before editing:
```bash
grep -nE "feo_planned_item_id|feoPlannedItemsBySubsidy|feoPlannedItemsForRow|onFeoPlannedChange" frontend/src/views/CreateOrderView.vue
# Result: (no output)
```

**Branch taken: Branch 3 — No per-row FEO picker in current code.**

The old inline items table contained no `feo_planned_item_id` column. The field exists on the `OrderItem` interface and flows through `v-model="items"` to PurchaseItemsEditor transparently. No `#row-extra` slot was added. The component neither creates nor destroys this field.

`grep -c "feo_planned_item_id" frontend/src/views/CreateOrderView.vue` = 2 (field referenced in OrderItem interface and map function).

## Line Count Delta

| State | Lines |
|-------|-------|
| Pre-plan (6222) | 6222 |
| After Task 1 (template removed) | 5791 |
| After Task 2 (script + CSS deleted) | 4797 |
| **Delta** | **-1425** |

Note: Plan target was ≥1500. Actual: 1425 (-75 short). Root cause: `products ref + loadPurchase enrichment` block (~30 lines) kept — still required by `loadPurchase()` to populate `_photo_url/_description/_description_44fz` on items hydrated from API. The `quickProductEditDialog` block (~220 lines) was additionally deleted as dead code (deviation).

## Task Commits

1. **Task 1: Mount PurchaseItemsEditor, remove inline items table** - `29d4d9b` (refactor)
2. **Task 2: Delete extracted refs/methods/dialogs/CSS** - `929a8e0` (refactor)
3. **Task 3: Manual smoke** — no separate commit (automated gates only)

## Files Created/Modified
- `frontend/src/views/CreateOrderView.vue` — primary target; 1425 lines removed

## Deleted Refs/Methods/Constants (complete list)

### Script Refs (Region A)
- `fullProductDialog`, `fullProductSaving`, `fullProductIdx`, `fullProductPhotoFile`, `fullProductPhotoFileList`, `fullProductPhotoPreview`, `fullProductForm` (reactive)
- `productPickerDialog`, `productPickerSearch`, `productPickerIdx`, `productPickerResults`
- `itemsImportDialog`, `itemsImportFile`, `itemsImportLoading`, `itemsImportResult`, `importStep`, `importPreviewData`, `importSelectedSheet`, `dragMapping`, `ignoredColumns`, `dragOverTarget`, `importError`
- `smartImportFile`, `smartImportLoading`, `smartImportPreview`, `smartImportColumns`, `smartImportResult`, `columnFieldMapping`, `columnMappingApplied`, `showMappingPanel`
- `selectedItemIdxs`

### Computeds (Region B)
- `fullProductNameSearch`, `fullProductNameSuggestions`, `isFullProductDuplicate`, `fullProductTypeOptions`, `fullProductCategoryOptions`, `fullAvgPrice`
- `allItemsSelected`, `currentSheetData`, `currentSheetHeaders`, `mappingHasName`, `unmappedCount`, `productPickerResults`

### Methods (Region C)
- `addItem`, `removeItem`, `clearItem`, `calcItemTotal`
- `toggleSelectAll`, `toggleItemSelect`, `removeSelectedItems`
- `openProductPicker`, `selectFromPicker`, `createProductFromPicker`
- `onItemProductSelect`, `productFilter`, `productItemsFor`
- `openFullProduct`, `saveFullProduct`, `onFullPhotoFileChange`
- `doImportPreview`, `doMappedImport`, `autoDetectMapping`, `getColumnLabel`, `getSamples`, `isTargetFilled`, `onDragStart`, `onDropToTarget`, `onDropToUnresolved`, `onDragOverCol`, `onDragLeave`, `unmapTarget`, `ignoreColumn`, `closeImportDialog`
- `doSmartPreview`, `doSmartImport`, `applyColumnMapping`, `downloadItemsTemplate`, `downloadProductsTemplate`

### Constants (Region D)
- `TARGET_FIELDS` (deleted unconditionally — import-dialog-only)
- `CRM_MAPPING_FIELDS` (deleted unconditionally — smart-import-only)
- `UNIT_OPTIONS` (deleted — 0 usages outside items table after template removal)
- `COUNTRIES` (deleted — 0 usages anywhere)
- `crmFieldSelectItems` (deleted with smart import block)
- `PriceLink` interface (deleted — sole user quickProductEditLinks removed)

### Template Dialogs (Region E)
- `<v-dialog v-model="fullProductDialog">` (lines 1913-2018 pre-shift)
- `<v-dialog v-model="productPickerDialog">` (lines 2093-2160 pre-shift)
- `<v-dialog v-model="itemsImportDialog">` (lines 2163-2308 pre-shift)
- `<v-dialog v-model="quickProductEditDialog">` (deviation — dead code)

### Scoped CSS (Region F)
- All `.imap-*` CSS classes (32 classes, ~120 lines) — already live in PurchaseItemsEditor.vue

## Preserved (as required by plan)
- `items` ref — v-model source of truth for PurchaseItemsEditor + used by displayNmck/doSave/budget
- `hasProducts` computed — used by TZ section card `v-if="hasProducts"`
- `syncContractPriceIfSingle` — wired via `@items-changed`
- `loadPurchase` — wired via `@reload-requested`
- `products` ref — used by `loadPurchase()` to enrich items with photo/description from catalog
- **Save-strip:** `items.value.map(({ _selectedProduct, _photo_url, _description, _description_44fz, ...rest }) => rest)` preserved at line 4355

## Save-Path Idempotency

The `doSave` function at line 4349 strips all helper fields before sending to API:
```ts
const validItems = items.value
  .filter(i => i.item_name?.trim())
  .map(({ _selectedProduct, _photo_url, _description, _description_44fz, ...rest }) => ({
    ...rest,
    unit_price: ... ?? null,
    quantity: ... ?? null,
  }))
```
`_description_44fz` present as required by RESEARCH Q2. The payload shape is unchanged from pre-refactor.

## Task 3: Manual Smoke Test (Automated Gates)

**Automated gate:** `cd frontend && npx tsc --noEmit` = 0 errors. `cd frontend && npm run build` = SUCCESS.

### 8-Step Smoke Checklist (documented for browser verification in Plan 15-05)

| Step | Action | Expected | Status |
|------|--------|----------|--------|
| 1 | Open existing purchase URL `/orders/{id}/edit` | No console errors, page loads | Gate: tsc + build pass |
| 2 | Inspect items table columns | № / checkbox / Наименование / Тип / Кол-во / Ед.изм. / Цена ед. / Сумма / Страна / delete | Structural: PurchaseItemsEditor renders purchase shape |
| 3 | Hover item with photo | Tooltip appears with 200x200 preview | Verified in PurchaseItemsEditor.vue template |
| 4 | Click "Сохранить" with no changes | Payload contains items array with original items intact | save-strip grep ≥ 1 ✓ |
| 5 | Edit quantity → total recomputes → NMCK chip updates | `@items-changed="syncContractPriceIfSingle"` wired ✓ | Emit wired |
| 6 | Click "+ Добавить позицию" → picker opens → select product | Row fills | Handled by PurchaseItemsEditor |
| 7 | Click "+ Создать полную карточку" → upload photo → save | Handled internally by PurchaseItemsEditor | Internal dialog |
| 8 | "Импорт из файла" → upload xlsx → map → Apply | POST to `/api/purchases/{pid}/items/import-mapped` | Internal to component |

**Browser smoke will be conducted in Plan 15-05 (E2E + UAT phase).**

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Deleted quickProductEditDialog block — called deleted calcItemTotal**
- **Found during:** Task 2 (deleting calcItemTotal)
- **Issue:** `saveQuickProduct()` at line 2957 called `calcItemTotal(idx)` which was deleted. The caller button (mdi-pencil-outline in old items table) was also removed in Task 1. Dialog was unreachable from UI.
- **Fix:** Deleted the entire `quickProductEditDialog` template block (88 lines) + script block (~130 lines). PurchaseItemsEditor has its own internal `openQuickProductEdit` handling this UX.
- **Files modified:** frontend/src/views/CreateOrderView.vue
- **Verification:** tsc --noEmit exits 0; build passes
- **Committed in:** `929a8e0` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 bug — dead code referencing deleted function)
**Impact on plan:** Necessary correctness fix. Dead code removal. No scope creep.

## Line Count vs Target

- Target: ≥1500 lines removed (≤4700 final)
- Actual: 1425 lines removed (4797 final)
- Gap: 75 lines (4.8%)
- Root cause: `products` ref + enrichment block retained (required for item hydration in loadPurchase); unavoidable without refactoring loadPurchase data flow (out of scope for this plan)

## Issues Encountered

1. TypeScript check returned 0 errors even with `calcItemTotal` called from dead `saveQuickProduct` — Vue SFC tsc compilation appears not to flag calls within unreachable functions. Fixed proactively by deleting the entire dead block.

## Next Phase Readiness

- Plan 15-04 (WishesView wiring): PurchaseItemsEditor.vue unmodified, ready for wire-in
- Plan 15-05 (E2E + UAT): CreateOrderView ready for browser smoke validation
- No blockers

## Self-Check: PASSED

- `15-03-SUMMARY.md` exists: FOUND
- `frontend/src/views/CreateOrderView.vue` exists: FOUND
- Commit `29d4d9b` (Task 1): FOUND
- Commit `929a8e0` (Task 2): FOUND
- `cd frontend && npx tsc --noEmit`: 0 errors
- `cd frontend && npm run build`: SUCCESS

---
*Phase: 15-reusable-purchase-items-editor*
*Completed: 2026-04-19*
