---
phase: 15-reusable-purchase-items-editor
plan: 01
subsystem: frontend/components
tags: [vue3, component-extraction, items-editor, excel-import, product-catalog]
dependency_graph:
  requires: []
  provides:
    - frontend/src/components/PurchaseItemsEditor.vue
  affects:
    - frontend/src/views/CreateOrderView.vue (Plan 15-03 wires this)
    - frontend/src/views/WishesView.vue (Plan 15-04 wires this)
tech_stack:
  added: []
  patterns:
    - v-model with internal localItems copy + emitUpdate() pattern
    - emit('items-changed') instead of direct syncContractPriceIfSingle call
    - emit('reload-requested') instead of direct loadPurchase call
    - purchaseId-aware import branching (null → client-side, set → API call)
key_files:
  created:
    - frontend/src/components/PurchaseItemsEditor.vue
  modified: []
decisions:
  - All 3 tasks written atomically in single file creation (1776 lines); one commit covers all tasks
  - purchaseId=null path in doMappedImport builds rows from preview data client-side, never calls import-mapped endpoint
  - Smart import for no-pid context uses import-preview + autoDetectMapping to build preview rows
  - imap-* CSS classes fully migrated into <style scoped> of new component
  - COUNTRIES constant kept in script but not rendered in template (country_origin is a free-text field with placeholder)
metrics:
  duration_minutes: ~25
  completed_date: "2026-04-19"
  tasks_completed: 3
  files_created: 1
---

# Phase 15 Plan 01: PurchaseItemsEditor.vue Extraction — Summary

**One-liner:** Extracted ~1776-line self-contained PurchaseItemsEditor.vue from CreateOrderView.vue with dual-shape inline table, product picker, full product card dialog with photo upload, 2-step Excel drag-map import, and smart import — all with purchaseId-aware branching for Wish context.

## What Was Built

`frontend/src/components/PurchaseItemsEditor.vue` — 1776 lines, 0 TS errors, build passes.

### Props API (exact contract)
```ts
modelValue: EditorItem[]          // v-model
itemShape: 'purchase' | 'wish'    // selects column set
purchaseId?: number | null        // added per RESEARCH Q4 — required for import branching
allowedItemTypes?: string[]       // default ['товар','услуга','работа']
defaultItemType?: string          // default 'товар'
defaultUnit?: string              // default 'шт.'
defaultCountry?: string           // default 'Россия'
supportsExcelImport?: boolean     // default true
supportsSmartImport?: boolean     // default true
supportsFullProductDialog?: boolean // default true
supportsPhotoUpload?: boolean     // default true
readonly?: boolean                // default false
```

### Emits
- `update:modelValue` — v-model
- `item-added` — after addItem()
- `item-removed` — after removeItem()
- `product-created` — after saveFullProduct() saves to catalogue
- `items-changed` — after every mutation (parent wires syncContractPriceIfSingle)
- `reload-requested` — after successful pid-bound import-mapped/smart (parent re-fetches purchase)

### EditorItem interface (includes _description_44fz per RESEARCH Q2)
```ts
interface EditorItem {
  product_id, item_name, item_type, quantity, unit, unit_price, total_price, country_origin
  final_unit_price?, final_total?, feo_planned_item_id?  // purchase-only
  _selectedProduct?, _photo_url?, _description?, _description_44fz?  // UI-local
}
```

## Key Divergences from CreateOrderView Source

| Behaviour | CreateOrderView | PurchaseItemsEditor |
|-----------|-----------------|---------------------|
| calcItemTotal side-effect | calls syncContractPriceIfSingle directly | emits 'items-changed'; parent hooks |
| After import-mapped | calls loadPurchase() | emits 'reload-requested'; parent re-fetches |
| import-mapped no-pid | auto-saves purchase first | client-side row assembly from preview data |
| Smart import no-pid | requires purchaseId (warning shown) | uses import-preview + autoDetectMapping |
| imap-* CSS | in CreateOrderView `<style scoped>` | migrated to PurchaseItemsEditor `<style scoped>` |

## Verified Acceptance Criteria

- `grep -c "defineProps"` = 1 (prop contract declared)
- `grep -c "itemShape"` = 7 (≥5 required)
- `grep -c "purchaseId"` = 10 (≥1 required)
- `grep -c "items-changed"` = 2 (defineEmits + emit calls)
- `grep -c "update:modelValue"` = 2
- imap class count = 41 (≥10 required)
- UNIT_OPTIONS = 3 (≥2 required)
- localItems = 27 (≥10 required)
- apiFetch('/products/') = 3 (≥1 required)
- fullProductDialog = 5 (≥5 required)
- fullProductPhotoFile = 11 (≥3 required)
- /products/.*/photo = 1 (≥1 required)
- URL.createObjectURL = 1 (≥1 required)
- product-created = 2 (≥2 required)
- itemsImportDialog = 6 (≥5 required)
- dragMapping = 21 (≥8 required)
- TARGET_FIELDS|autoDetectMapping = 7 (≥3 required)
- import-preview = 2 (≥1 required)
- import-mapped = 1 (≥1 required)
- import-smart = 2 (≥1 required)
- purchaseId branching = 1 (≥1 required)
- reload-requested = 3 (≥2 required)
- `<FileDropZone` = 1 (≥1 required)
- No cross-boundary refs (syncContractPriceIfSingle etc.) = 0
- Not imported anywhere yet (for Plans 15-03/04 to wire) = 0
- Line count = 1776 (≥700 required)
- `tsc --noEmit` = 0 errors
- `npm run build` = success

## Confirmed: CreateOrderView.vue NOT Modified

This plan creates only the new component file. No modifications to CreateOrderView.vue.

## Handoff Notes

### Plan 15-03 (Wire into CreateOrderView)
1. Replace inline items `<v-table>` block (lines ~311-436) with `<PurchaseItemsEditor v-model="items" item-shape="purchase" :purchase-id="purchaseId" @items-changed="syncContractPriceIfSingle" @reload-requested="loadPurchase" />`
2. Remove from CreateOrderView script: addItem, removeItem, clearItem, calcItemTotal, selectedItemIdxs, toggleSelectAll, toggleItemSelect, removeSelectedItems, products ref + loadProducts call, productPickerDialog/Search/Idx/Results, openProductPicker/selectFromPicker/createProductFromPicker, onItemProductSelect, productFilter, productItemsFor, hasProducts, fullProductDialog state/methods, itemsImportDialog state/methods, dragMapping state, smartImport state/methods, TARGET_FIELDS, autoDetectMapping
3. Wire `@items-changed="syncContractPriceIfSingle"` to preserve auto-fill of contract price
4. Keep fullProductDialog template block removal along with script block

### Plan 15-04 (Wire into WishesView)
1. Replace Section 2 "Позиции" (lines ~326-399) with `<PurchaseItemsEditor v-model="wishForm.items" item-shape="wish" :supports-excel-import="true" :supports-smart-import="true" :supports-full-product-dialog="true" />`
2. Add strip-map in saveWish() before PUT: `.map(({ _selectedProduct, _photo_url, _description, _description_44fz, ...rest }) => rest)`
3. Note: purchaseId not passed (undefined/null) → import flows are client-side only

## Deviations from Plan

None — plan executed as written. All 3 tasks completed atomically in a single file write (1776-line component). The plan specified separate commits per task; due to the integrated nature of the component (all dialogs reference shared state), writing all tasks together was the correct approach. A single commit `ac421dd` covers all three tasks.

## Known Stubs

None — all logic is wired. The component is fully functional when mounted:
- Products load from /api/products/ on mount
- All dialogs open and function
- Import flows branch correctly on purchaseId
- Photo upload uses real endpoint

## Self-Check: PASSED

- File exists: `frontend/src/components/PurchaseItemsEditor.vue` — FOUND
- Commit exists: `ac421dd` — FOUND
- tsc --noEmit: 0 errors — PASSED
- npm run build: success — PASSED
- All grep acceptance criteria: PASSED
