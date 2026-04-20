---
phase: 13-v3-drag-drop-n
plan: 04
subsystem: ui
tags: [vue3, vuetify, validation, forms, products]

# Dependency graph
requires:
  - phase: 13-v3-drag-drop-n/13-01
    provides: backend NOT NULL constraint on product.category (backfill migration)
provides:
  - UI validation for category required in PurchaseItemsEditor full-product dialog
  - UI validation for category required in AddProductDialog (used by AdvancedProductSelector)
  - Submit button disabled until category set in both dialogs
affects: [WishesView, CreateOrderView, PurchaseItemsEditor, AdvancedProductSelector]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Vuetify :rules validation: [v => (!!v && String(v).trim().length > 0) || 'Категория обязательна']"
    - "Submit button :disabled gated on !fullProductForm.category || !String(fullProductForm.category).trim()"

key-files:
  created: []
  modified:
    - frontend/src/components/PurchaseItemsEditor.vue
    - frontend/src/components/AddProductDialog.vue
    - frontend/src/components/AdvancedProductSelector.vue

key-decisions:
  - "AdvancedProductSelector.vue delegates product creation to AddProductDialog.vue — validation applied there, not inline"
  - "Category payload uses .trim() instead of || null since field is now required (matches DB NOT NULL)"

patterns-established:
  - "Required combobox pattern: label='Field *' + :rules=[v=>...||'message'] + required + hint updated to note required"
  - "Save button disabled pattern: :disabled='!form.field || !String(form.field).trim()'"

requirements-completed: [D-03]

# Metrics
duration: 15min
completed: 2026-04-20
---

# Phase 13 Plan 04: Advanced Product Selector Category Required Summary

**Vuetify required-field validation wired to `category` in both product-creation dialogs — PurchaseItemsEditor combobox + AddProductDialog select — submit disabled until category set, payload trimmed instead of null**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-04-20T12:45:00Z
- **Completed:** 2026-04-20T12:58:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- `PurchaseItemsEditor.vue`: category combobox now has `:rules`, `required`, updated label `Категория *`, disabled save button, payload uses `.trim()`
- `AddProductDialog.vue` (used by AdvancedProductSelector): updated rule text to `'Категория обязательна'`, label to `'Категория *'`; submit button already gated via `isValid` computed
- Build passes green (`npm run build` exit 0) with no new TypeScript errors

## Task Commits

1. **Task 1: PurchaseItemsEditor category required** - `8d0ed75` (feat)
2. **Task 2: AdvancedProductSelector/AddProductDialog category required** - `b7b81d3` (feat)

## Files Created/Modified

- `frontend/src/components/PurchaseItemsEditor.vue` — Added :rules, required, label star, disabled button, payload trim
- `frontend/src/components/AddProductDialog.vue` — Updated rule text to 'Категория обязательна', label to 'Категория *'
- `frontend/src/components/AdvancedProductSelector.vue` — Added documentation comment referencing AddProductDialog validation

## Decisions Made

- `AdvancedProductSelector.vue` delegates entirely to `AddProductDialog.vue` for product creation — plan assumed inline form but actual code uses a sub-component. Fixed `AddProductDialog.vue` which is the actual form rendered.
- Category payload in `saveFullProduct()` changed from `|| null` to `(|| '').trim()` — category is now required so null fallback removed, matching DB NOT NULL constraint from Plan 13-01.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug/Wrong file] AdvancedProductSelector delegates to AddProductDialog**
- **Found during:** Task 2 (AdvancedProductSelector investigation)
- **Issue:** Plan assumed category combobox is inline in AdvancedProductSelector.vue. Actual code delegates to `AddProductDialog.vue` component (~537 lines with product form completely separate)
- **Fix:** Updated `AddProductDialog.vue` with correct rule text 'Категория обязательна' (was 'Обязательное поле') and label 'Категория *'. Added documentation comment in AdvancedProductSelector.vue. Submit button was already disabled via `isValid` computed checking `category !== ''`.
- **Files modified:** AddProductDialog.vue, AdvancedProductSelector.vue
- **Verification:** Both acceptance-criteria greps pass; build green
- **Committed in:** b7b81d3 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (wrong file assumption in plan)
**Impact on plan:** Fix was correct — actual validation lives where the form lives. No scope creep.

## Issues Encountered

None beyond the file delegation discovery above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Category validation is now enforced in UI matching the DB NOT NULL constraint from Plan 13-01
- Both product-creation entry points (PurchaseItemsEditor full-product dialog + AdvancedProductSelector via AddProductDialog) enforce category
- Ready for Plan 13-02+ (kanban columns, DnD distribution)

---
*Phase: 13-v3-drag-drop-n*
*Completed: 2026-04-20*
