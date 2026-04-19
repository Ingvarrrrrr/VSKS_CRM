# Phase 15: Reusable Purchase Items Editor — Context

**Gathered:** 2026-04-19
**Status:** Ready for planning
**Source:** Inline capture from discussion (user confirmed variant A — proper refactor)

<domain>
## Phase Boundary

**Deliver:** a single Vue 3 component `<PurchaseItemsEditor />` that encapsulates the complete "position editor" experience — shared by `CreateOrderView.vue` ("Новый заказ") and `WishesView.vue` ("Заявка"), so both forms have the same catalogue-backed autocomplete, photo tooltips, full product card with upload, Excel drag-and-drop import, smart AI import, and FileDropZone.

**Do NOT deliver:** backend changes to `products`, `purchase_items`, or `wish_items` tables; changes to how `final_unit_price` / `feo_planned_item_id` are stored (these columns are Purchase-only and exposed via props).

**Success test:** open "Заявку" → add position → typing a name shows autocomplete from products with photo tooltip (same as in "Новом заказе"); click "+ Товар полная карточка" → can upload photo → saved product appears in the row with mini-thumb; click "Импорт из Excel" → 2-step dialog with drag-and-drop column mapping works identically to the one in CreateOrderView.

</domain>

<decisions>
## Implementation Decisions

### Component shape
- **Name:** `PurchaseItemsEditor` (component file: `frontend/src/components/PurchaseItemsEditor.vue`)
- **Parent API (props):**
  - `modelValue: Item[]` — v-model binding of items array
  - `itemShape: 'purchase' | 'wish'` — selects column set. `purchase` includes `final_unit_price`, `final_total`, `feo_planned_item_id`; `wish` omits those columns and keeps 7 columns (№ / Наименование / Тип / Кол-во / Ед.изм / Цена / Сумма)
  - `allowedItemTypes: string[]` — default `['товар', 'услуга', 'работа']`
  - `defaultItemType: string` — e.g. `'товар'`
  - `defaultUnit: string` — e.g. `'шт'`
  - `defaultCountry: string` — default `'Россия'`
  - `supportsExcelImport: boolean` — default `true`
  - `supportsSmartImport: boolean` — default `true`
  - `supportsFullProductDialog: boolean` — default `true`
  - `supportsPhotoUpload: boolean` — default `true`
  - `readonly: boolean` — default `false`
- **Emits:** `update:modelValue` (v-model), `item-added`, `item-removed`, `product-created` (fires after creating new product via full dialog)
- **Slots (optional):** `#toolbar-actions` for parent-specific buttons (e.g. "Копировать НМЦК"), `#row-extra` to append per-row cells (for `final_unit_price` / FEO link on Purchase side)

### Item type — shared interface
```ts
interface EditorItem {
  product_id: number | null
  item_name: string
  item_type: string                  // 'товар' | 'услуга' | 'работа'
  quantity: number | null
  unit: string
  unit_price: number | null
  total_price: number | null
  country_origin: string
  // Purchase-only (ignored when itemShape === 'wish'):
  final_unit_price?: number | null
  final_total?: number | null
  feo_planned_item_id?: number | null
  // UI-local state (stripped on save by parent):
  _selectedProduct?: Product | null
  _photo_url?: string
  _description?: string
}
```
The component emits this shape. Parents (`CreateOrderView`, `WishesView`) strip `_*` helper fields before PUT/POST, exactly as CreateOrderView already does at line 4669.

### Feature parity with CreateOrderView (locked — must appear in extracted component)
1. **Autocomplete in "Наименование"** — queries `/api/products/?search=` with debounce; shows photo thumb + price + description in dropdown items
2. **Photo tooltip** — hover the row's photo thumb → 200×200 preview (CreateOrderView:341-347)
3. **Quick-add row** — clicking "Добавить позицию" inserts empty row (CreateOrderView:4407)
4. **Full product card dialog** — "+ Создать товар полная карточка" opens dialog with: name, type (товар/услуга), category, price, description, **photo via v-file-input with live preview + upload**, photo_link fallback (CreateOrderView:1923-2197, supported API: POST `/api/products/{id}/photo`)
5. **Excel import (2-step)** — FileDropZone for .xlsx upload → backend preview `/api/purchase-items/import/excel/preview` → drag-and-drop column mapping with dragMapping (CreateOrderView:2163-2310, 4440-4770)
6. **Smart AI import** — one-shot call that auto-maps columns and returns items (CreateOrderView:4772-4883)
7. **Row delete** with confirm (undo not required)
8. **Auto-calc** — `unit_price × quantity → total_price` on change (CreateOrderView:calcItemTotal)
9. **Combobox unit** with presets (`шт, компл, усл, м, кг, л, м²`)
10. **Combobox country** — default persistent hint "По умолчанию — Россия"

### Callsite changes
- **`CreateOrderView.vue`**: replace inline items table (lines ~326-418), itemsImportDialog block (lines ~2163-2310), fullProductDialog block (lines ~1823-2030), and supporting script blocks (`items` ref, `addItem`, `calcItemTotal`, `itemsImportFile`, `dragMapping`, `fullProductForm`, `onFullPhotoFileChange`, `importProducts`, `parseItemsFromFile`, `applyItemsImport`, `smartImportItems`) with `<PurchaseItemsEditor v-model="items" item-shape="purchase" ... >`. ~2000 lines of inline logic move into the component.
- **`WishesView.vue`**: replace Section 2 "Позиции" (lines 326-399) with `<PurchaseItemsEditor v-model="wishForm.items" item-shape="wish" :supports-excel-import="true" ... >`.
- **Keep** Purchase-only columns (`final_unit_price`, `final_total`, FEO link) in CreateOrderView by conditioning on `itemShape === 'purchase'` inside the component (NOT via a slot — simpler to test).

### API surfaces — consumed, not changed
- `GET /api/products/?search=...` — autocomplete source
- `POST /api/products/` — create new product from full dialog
- `POST /api/products/{id}/photo` — upload product photo
- `POST /api/purchase-items/import/excel/preview` — read headers + sample rows (reused for wish import too — backend endpoint is catalogue-agnostic, writes happen on the parent Save)
- `POST /api/purchase-items/import/excel/smart` — one-shot AI mapping

### `OrderProductsTable.vue` (existing 285-line unused component)
- **Decision:** audit first, then **delete** if it's a skeleton or an earlier aborted attempt. Planner must include a single task "Audit OrderProductsTable.vue — delete or repurpose". It is NOT used as the starter; the authoritative source is `CreateOrderView.vue`'s inline block.

### Testing
- **Playwright E2E** — extend `e2e/` with a new spec `18-purchase-items-editor.spec.ts`: mount in both CreateOrderView and WishesView; verify autocomplete, photo tooltip, add/delete row, Excel import with drag-mapping.
- **No unit tests** — project has no Vue unit test infra; keep parity with existing conventions.

### Data model note (NOT to change in this phase)
`WishItem` lacks `final_unit_price` / `final_total` / `feo_planned_item_id`. The component does NOT render those columns when `itemShape='wish'`. If we later want them in Заявки, that's a separate backend phase.

### Out of scope (defer)
- Backend additions to `wish_items` table
- Auto-sync edits to `products` catalogue (happens via full product dialog only, as today)
- Undo/Redo on items editor (tracked separately in 04_TODO.md)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Source to extract from
- `frontend/src/views/CreateOrderView.vue` — authoritative source of the position editor behaviour. Relevant regions:
  - `326-418` — inline items `<v-table>` with autocomplete, row edit, delete
  - `1823-2030` — full product card dialog (photo upload, description, prices)
  - `2163-2310` — Excel import dialog with 2-step flow + drag-and-drop column mapping
  - `4407-4960` — script: `addItem`, `calcItemTotal`, `itemsImportFile`, `dragMapping`, `onDragStart/onDropToTarget/onDropToUnresolved`, `parseItemsFromFile`, `applyItemsImport`, `smartImportItems`, `onProductSelected`, `fullProductPhoto*`
  - `5441` — `.map(({ _selectedProduct, _photo_url, _description, ...rest }))` — strip helpers before save

### Target to wire into
- `frontend/src/views/WishesView.vue` — Section 2 "Позиции" at lines 326-399 to be replaced by `<PurchaseItemsEditor item-shape="wish" />`

### Existing unused component to evaluate
- `frontend/src/components/OrderProductsTable.vue` (285 lines) — audit task, likely delete

### Models (for interface shape — do NOT modify)
- `backend/app/models/purchase_item.py` — PurchaseItem columns (13 fields incl. final_*, feo_planned_item_id)
- `backend/app/models/wish_item.py` — WishItem columns (8 fields, no final_*/feo)

### API routers (unchanged, consumed)
- `backend/app/routers/products.py` — GET/POST products, POST /{id}/photo
- `backend/app/routers/purchases.py` — POST purchase, PUT /{id} with items
- `backend/app/routers/wishes.py` — POST/PUT wishes with items (lines 115, 154)
- `backend/app/routers/feo_planned_items.py` — read-only reference for FEO linkage

### Testing infrastructure
- `playwright.config.ts` + `e2e/helpers.ts` (login, waitForOverlays, collectApiErrors)

### Project guidelines
- `CLAUDE.md` — project rules
- Global `~/.claude/CLAUDE.md` — balanced profile (Opus plans, Sonnet executes)

</canonical_refs>

<specifics>
## Specific Ideas

### Informal requirements (to be mapped to plan `requirements` field)
- **ITEMS-EDITOR-01** — Create `PurchaseItemsEditor.vue` with props API (itemShape, allowedItemTypes, defaults, supports*, readonly)
- **ITEMS-EDITOR-02** — Inline table with autocomplete, photo tooltip, auto-calc, row delete
- **ITEMS-EDITOR-03** — "Full product card" dialog with v-file-input photo upload + POST `/api/products/{id}/photo`
- **ITEMS-EDITOR-04** — Excel import 2-step dialog with drag-and-drop column mapping
- **ITEMS-EDITOR-05** — Smart AI import one-shot path
- **ITEMS-EDITOR-06** — Wire into CreateOrderView.vue, preserve Purchase-specific columns (`final_unit_price`, `final_total`, FEO link)
- **ITEMS-EDITOR-07** — Wire into WishesView.vue Section 2 "Позиции"
- **ITEMS-EDITOR-08** — Audit & decision on OrderProductsTable.vue (delete or repurpose); add Playwright spec `18-purchase-items-editor.spec.ts` asserting both parents have parity

### Parallelisation
- Plan A (extract component) and Plan C (audit OrderProductsTable) can run in Wave 1 in parallel
- Plan B (wire into CreateOrderView) and Plan D (wire into WishesView) depend on Plan A → Wave 2, in parallel with each other
- Plan E (E2E spec) depends on B+D → Wave 3

### Risk
- CreateOrderView.vue is **6222 lines**; regression risk is real. Every plan MUST preserve existing behaviour for Purchase-side (item-level totals roll up to `total_nmck`, `planned_total_price`, budget check). Plan B must include a manual smoke: create a purchase with 3 items from catalogue + 1 new full-card product + 1 Excel-imported row → save → reopen → verify all 5 items intact.
- Vuetify autocomplete reactive reset: existing CreateOrderView has quirks (items[idx]._photo_url = undefined on clear, line 4956). Preserve that.

</specifics>

<deferred>
## Deferred Ideas

- Migrating `wish_items` schema to add `final_unit_price` / `final_total` / `feo_planned_item_id` — out of scope (requires discussion on Wish lifecycle)
- Unit tests for the component — no existing Vue unit test infra; covered by Playwright E2E
- Undo/Redo on items editor — tracked in 04_TODO.md under "Автосохранение + Undo/Redo"
- Drag-reorder rows within the items table — not requested by user
- Support for a third callsite (e.g. ContractsView line-items) — not in scope; if needed later, the component is already decoupled

</deferred>

---

*Phase: 15-reusable-purchase-items-editor*
*Context gathered: 2026-04-19 via inline capture from user discussion*
