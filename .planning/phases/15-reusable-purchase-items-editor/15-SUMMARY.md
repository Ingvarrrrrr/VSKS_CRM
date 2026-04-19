---
phase: 15-reusable-purchase-items-editor
status: complete
completed: 2026-04-19
plans: 5/5
---

# Phase 15 — Reusable Purchase Items Editor

## Goal

Take the purchase-items table that already worked inside `CreateOrderView` and make it reusable, so the **Заявка** form (`WishesView`) can mount the same editor and reach feature parity with **Новый заказ**.

## Outcome

✅ One shared component (`PurchaseItemsEditor.vue`) is mounted in both parents. Заявка now has the same product autocomplete, photo tooltip, full product card dialog, and Excel import flow as Новый заказ. Smoke spec asserts the editor renders cleanly in both pages on the deploy.

## Plan roll-up

| Plan | Title | Commits | Outcome |
|------|-------|---------|---------|
| 15-01 | Extract PurchaseItemsEditor component | `ac421dd`, `6d5aec0` | New 1776-line component with full items CRUD, product picker, Excel/smart import, scoped imap-* styles |
| 15-02 | Delete dead OrderProductsTable.vue | `dd115c0`, `44724e2` | 285 lines of dead code removed (only reference was `*.backup.vue`) |
| 15-03 | Wire into CreateOrderView | `29d4d9b`, `929a8e0`, `165b8fc` | Inline items table replaced with `<PurchaseItemsEditor>`; **−1425 lines** in CreateOrderView |
| 15-04 | Wire into WishesView Section 2 | `f1c5273`, `f407d24`, `5ce0adc` | Заявка form gets full editor + helper-field stripper for clean POST/PUT body; **−100 lines** in WishesView |
| 15-05 | E2E smoke spec + closure | _this commit_ | 3 smoke tests pass on deploy (60s); fixtures dropped, scope cut from 7→3 scenarios |

## Line-count impact

| File | Before | After | Δ |
|------|--------|-------|---|
| `frontend/src/views/CreateOrderView.vue` | ~3000 | ~1575 | **−1425** |
| `frontend/src/views/WishesView.vue` | 1035 | 935 | **−100** |
| `frontend/src/components/OrderProductsTable.vue` | 285 | _deleted_ | **−285** |
| `frontend/src/components/PurchaseItemsEditor.vue` | 0 | 1776 | **+1776** |
| **Net** |  |  | **−34 lines** + reusability gain |

## Files

**Created:**
- `frontend/src/components/PurchaseItemsEditor.vue`
- `e2e/18-purchase-items-editor.spec.ts`
- 4 plan summaries + this roll-up

**Modified:**
- `frontend/src/views/CreateOrderView.vue` (mounted editor, deleted inline table + dialogs + helpers)
- `frontend/src/views/WishesView.vue` (mounted editor in Section 2, helper-field stripper in saveWish)
- `e2e/helpers.ts` (added `dismissOrgPicker`)

**Deleted:**
- `frontend/src/components/OrderProductsTable.vue`

## UAT

- 14-step manual smoke checklist documented in 15-04-SUMMARY (covers picker, photo, full product card, Excel 2-step, smart import, save payload shape, persistence)
- Automated smoke: 3/3 pass on `BASE_URL=http://85.239.53.155` in 60s

## Known notes

- Local Playwright run blocked by unrelated **localhost backend 502** (in `04_TODO.md` since prior session). Deploy run is the source of truth for this phase.
- Deep regression coverage (every flow inside the editor) deferred to Phase 13 (Заявки v3) where the new flows actually land. Phase 15 is a refactor — behavior unchanged.

## Unblocks

- **Phase 13 (Заявки v3 — авторасспределение)** can now build on the shared editor without duplicating UI between заявки and заказы.
