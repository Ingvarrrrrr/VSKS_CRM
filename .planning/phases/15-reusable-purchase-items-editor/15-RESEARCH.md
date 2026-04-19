# Phase 15: Reusable Purchase Items Editor — Research

**Researched:** 2026-04-19
**Domain:** Vue 3 component extraction / refactor — inline items editor from CreateOrderView.vue into PurchaseItemsEditor.vue
**Confidence:** HIGH (all findings sourced from actual files in the codebase)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Component shape:**
- Name: `PurchaseItemsEditor` (file: `frontend/src/components/PurchaseItemsEditor.vue`)
- Props: `modelValue: Item[]`, `itemShape: 'purchase' | 'wish'`, `allowedItemTypes: string[]`, `defaultItemType`, `defaultUnit`, `defaultCountry`, `supportsExcelImport: boolean`, `supportsSmartImport: boolean`, `supportsFullProductDialog: boolean`, `supportsPhotoUpload: boolean`, `readonly: boolean`
- Emits: `update:modelValue`, `item-added`, `item-removed`, `product-created`
- Slots (optional): `#toolbar-actions`, `#row-extra`

**Item interface (EditorItem)** — exactly as in CONTEXT.md. UI-only fields `_selectedProduct`, `_photo_url`, `_description` are stripped by parent before save.

**Callsite changes:**
- CreateOrderView: replace lines 326–418 (table), 1913–2018 (fullProductDialog), 2163–2308 (itemsImportDialog), and script blocks addItem/calcItemTotal/import/product-selection/photo (~lines 4404–4960). Keep Purchase-only columns (final_unit_price, final_total, FEO) inside component via `itemShape === 'purchase'` conditionals (NOT slots).
- WishesView: replace Section 2 lines 326–399 with `<PurchaseItemsEditor v-model="wishForm.items" item-shape="wish" ...>`

**API surfaces (consumed, not changed):**
- `GET /api/products/?search=...`
- `POST /api/products/`
- `POST /api/products/{id}/photo`
- `POST /api/purchases/items/import-preview` (catalogue-agnostic, no pid required)
- `POST /api/purchases/{pid}/items/import-mapped` (pid-bound — see critical issue below)
- `POST /api/purchases/{pid}/items/import-smart` (pid-bound)

**OrderProductsTable.vue:** audit first, then delete; NOT used as starter.

**Testing:** Playwright E2E only (`e2e/18-purchase-items-editor.spec.ts`). No unit tests.

**Deferred (out of scope):**
- Backend additions to wish_items table
- Auto-sync edits to products catalogue (only via full product dialog)
- Undo/Redo on items editor
- Drag-reorder rows
- Third callsite (ContractsView)

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ITEMS-EDITOR-01 | Create `PurchaseItemsEditor.vue` with full props API (itemShape, allowedItemTypes, defaults, supports*, readonly) | Props interface fully defined; all signals confirmed in CreateOrderView code |
| ITEMS-EDITOR-02 | Inline table with autocomplete (product picker dialog), photo tooltip, auto-calc, row delete | Lines 326–418 (template), 4404–4960 (script). Product search is client-side filter over `products.value`. Photo tooltip at lines 341–348 |
| ITEMS-EDITOR-03 | Full product card dialog with v-file-input photo upload + POST `/api/products/{id}/photo` | Lines 1913–2018 (dialog), 4120–4211 (script). Endpoint confirmed at `products.py:794` |
| ITEMS-EDITOR-04 | Excel import 2-step dialog with drag-and-drop column mapping | Lines 2163–2308 (dialog), 4438–4755 (script). Preview endpoint at `purchases.py:2032` (no pid). Final apply at `purchases.py:2181` (requires pid — CRITICAL BLOCKER) |
| ITEMS-EDITOR-05 | Smart AI import one-shot path | Lines 4771–4856 (script). Endpoint at `purchases.py:2398`. Requires pid. Uses markitdown + column-detection (no LLM). For wish context: client-only preview path is available |
| ITEMS-EDITOR-06 | Wire into CreateOrderView.vue, preserve Purchase-only columns | ~2000 lines to remove, replace with single component tag. syncContractPriceIfSingle callback needed (see Q1 below) |
| ITEMS-EDITOR-07 | Wire into WishesView.vue Section 2 "Позиции" | Lines 326–399 (template), addItem/removeItem/calcItemTotal/totalNmck at ~lines 753–772 (script). wishForm.items serialization must be verified |
| ITEMS-EDITOR-08 | Audit OrderProductsTable.vue; add Playwright spec `18-purchase-items-editor.spec.ts` | OrderProductsTable: dead code, only imported in `.backup.vue`. Delete confirmed |

</phase_requirements>

---

## Summary

Phase 15 extracts roughly 2 000 lines of inline "position editor" logic from `CreateOrderView.vue` (6 222 lines) into a standalone `PurchaseItemsEditor.vue` component and wires it into both `CreateOrderView.vue` and `WishesView.vue`. The extraction is a pure frontend refactor — no backend changes are needed and no DB schema changes are in scope.

**The most important technical discovery is the Excel import endpoint split.** The preview step (`POST /api/purchases/items/import-preview`) is purchase-agnostic and can be reused directly. The apply step (`POST /api/purchases/{pid}/items/import-mapped`) and smart import (`POST /api/purchases/{pid}/items/import-smart`) are purchase-ID-bound. For the Wish context, the component cannot call these endpoints directly. The recommended resolution (from CONTEXT.md) is that `doMappedImport` in the component parses rows client-side from the already-received preview data and emits them via `update:modelValue`; the parent (WishesView) never calls `import-mapped` — instead the items land in `wishForm.items` and are persisted on `PUT /api/wishes/{id}`. For the Purchase context, the existing auto-save-then-import flow from CreateOrderView is preserved unchanged.

Product search is **entirely client-side** — `products.value` is loaded once on mount via `GET /api/products/` (no pagination, no debounce), and `productItemsFor()` / `productFilter()` do in-memory substring matching. This is fast for the current catalogue but means the component receives a `products` array that must be loaded by the component itself (or passed as a prop). The CONTEXT.md decision to load products inside the component is correct.

**Primary recommendation:** Extract exactly the regions listed in CONTEXT.md, pass `purchaseId` as an optional prop to PurchaseItemsEditor, and branch import behavior in `doMappedImport` / `doSmartImport`: if `purchaseId` is provided, call the purchase-bound endpoints (Purchase context); otherwise, skip the API call and directly `emit('update:modelValue', parsedRows)` (Wish context and any other callsite without a pre-existing DB record).

---

## Q1 — Reactive State to Extract vs Keep in Parent

**Move to PurchaseItemsEditor (child owns):**

| Ref/Computed/Method | Line | Reason |
|---------------------|------|--------|
| `items` ref | 2977 | v-model target — emitted upward; internal copy synced from `modelValue` prop |
| `selectedItemIdxs`, `allItemsSelected`, `toggleSelectAll`, `toggleItemSelect`, `removeSelectedItems` | 4417–4436 | Row-selection UI state, fully internal |
| `addItem`, `removeItem`, `clearItem` | 4404–4958 | Item CRUD |
| `calcItemTotal` | 4858 | Must call parent's `syncContractPriceIfSingle` via emit (see below) |
| `products` ref | 2993 | Loaded by child (`GET /api/products/` on mount) |
| `itemsImportDialog`, `itemsImportFile`, `itemsImportLoading`, `itemsImportResult` | 4439–4442 | Import dialog state |
| `importStep`, `importPreviewData`, `importSelectedSheet` | 4443–4445 | Import step state |
| `dragMapping`, `ignoredColumns`, `dragOverTarget`, `importError` | 4447–4450 | Drag-map state |
| `TARGET_FIELDS`, `autoDetectMapping`, drag functions | 4452–4519 | Import helpers |
| `smartImportFile`, `smartImportLoading`, `smartImportPreview`, `smartImportColumns`, `smartImportResult` | 4522–4526 | Smart import state |
| `columnFieldMapping`, `columnMappingApplied`, `showMappingPanel`, `CRM_MAPPING_FIELDS` | 4529–4545 | Column re-mapping state |
| `doImportPreview`, `doMappedImport`, `doSmartPreview`, `doSmartImport` | 4619–4856 | Import async functions |
| `fullProductDialog`, `fullProductSaving`, `fullProductIdx`, `fullProductPhotoFile`, `fullProductPhotoFileList`, `fullProductPhotoPreview`, `fullProductForm` | 4120–4130 | Full product dialog state |
| `fullProductNameSearch`, `fullProductNameSuggestions`, `isFullProductDuplicate`, `fullProductTypeOptions`, `fullProductCategoryOptions`, `fullAvgPrice` | 4132–4161 | Full product dialog computed |
| `onFullPhotoFileChange`, `openFullProduct`, `saveFullProduct` | 4164–4211 | Full product dialog methods |
| `productPickerDialog`, `productPickerSearch`, `productPickerIdx`, `productPickerResults` | 4929–4933 | Product picker dialog |
| `openProductPicker`, `selectFromPicker`, `createProductFromPicker` | 4935–4950 | Product picker handlers |
| `onItemProductSelect`, `productFilter`, `productItemsFor` | 4869–4925 | Product selection handlers |
| `hasProducts` computed | 4960 | Used only by child's toolbar (button visibility) |

**Must stay in CreateOrderView parent (cross-cutting):**

| State | Line | Why it stays |
|-------|------|--------------|
| `totalNmck` computed | 4214 | Feeds `displayNmck` → `planned_total_price` in save payload and budget indicator |
| `syncContractPriceIfSingle` | 4255 | Reads `isSinglePurchase`, `contractPriceMode` — parent-only state |
| `form.item_type` | 2914 | Controls `defaultType` for new items (pass as prop or prop default) |
| `form.description_mode` | 2959 | Used by `activeDescription()` — pass as prop to child or expose separately |
| `purchaseId` | 2788 | Required by import-mapped/import-smart endpoints |

**Cross-cutting concern — `calcItemTotal` side-effect:**
At line 4866, `calcItemTotal` calls `nextTick(() => syncContractPriceIfSingle())`. This crosses the component boundary. Solution: emit `'items-changed'` after any calc, and parent subscribes `@items-changed="syncContractPriceIfSingle"`. Alternatively, parent uses `@update:modelValue` watch to re-run `syncContractPriceIfSingle`.

---

## Q2 — Dependencies and Imports

| Dependency | Used in editor block | Destination |
|------------|---------------------|-------------|
| `apiFetch` from `@/api` | saveFullProduct, loadProducts | Move to child |
| `FileDropZone` component | itemsImportDialog (line 2190), addContractorDialog (line 2035) | Move to child (import dialog only); stay in CreateOrderView for contractor |
| `UNIT_OPTIONS` const | Line 2859 | Move to child (define as internal constant) |
| `COUNTRIES` const | Line 2858 | Move to child |
| `TARGET_FIELDS` const | Line 4452 | Move to child |
| `nextTick` from vue | calcItemTotal | Move to child |
| `ref`, `computed`, `reactive`, `watch` from vue | Throughout | Standard — move to child |
| `PurchaseEventFeed`, `ApprovalPanel`, `ChatEmbed` components | NOT in editor block | Stay in CreateOrderView |
| `useOrgConfig` composable | Line 2818 — `isSectionVisible` | Stays in CreateOrderView (not editor logic) |
| `useRoute`, `useRouter` | Routes/navigation | Stay in CreateOrderView; child gets `purchaseId` as prop |
| `localStorage.getItem('auth_token')` | Raw fetch calls in doImportPreview/doMappedImport | Move pattern to child; use `apiFetch` where possible, fall back to raw fetch for multipart |
| Product type interface | Lines 2864+ | Move to child's types; re-export or duplicate in parent |
| `showSnack` helper | All feedback toasts in editor | Must be available in child — define own snackbar state in child, or accept a `notify` prop/emit. Simplest: child has its own `v-snackbar` |

---

## Q3 — Product Search API

**Method:** Entirely client-side. No search query to the backend.

1. On mount, `loadRefs()` fetches `GET /api/products/` (line 4987) — returns the full product list, no `search` parameter.
2. `productItemsFor(search?)` (line 4917) does synchronous in-memory filter over `products.value` by name/description/type.
3. `productFilter()` (line 4908) is a Vuetify `custom-filter` prop — same logic, called by `v-combobox`/`v-autocomplete` internally.
4. The product picker dialog uses `productPickerResults = computed(() => productItemsFor(productPickerSearch.value))` (line 4933) — a computed ref.

**No debounce needed.** No `?search=` API call. No server-side pagination.

**Photos:** Products have two fields:
- `photo_url`: local path like `/api/products/photos/product_42.jpg` (uploaded via `POST /api/products/{id}/photo`)
- `photo_link`: external URL fallback

In `onItemProductSelect` (line 4891): `item._photo_url = val.photo_url || val.photo_link || undefined`

The component stores the resolved URL in `item._photo_url` and renders a tooltip `<img>` from it (lines 341–348).

---

## Q4 — Excel Import Endpoints: Critical Architectural Discovery

**CONTEXT.md stated:** `POST /api/purchase-items/import/excel/preview` — this path does NOT exist.

**Actual endpoints in `purchases.py`:**

| Step | Endpoint | Auth Required | Purchase ID? | Notes |
|------|----------|--------------|-------------|-------|
| Preview (file → headers+sample) | `POST /api/purchases/items/import-preview` | Yes (get_current_user) | No | Returns `{sheets: [{name, headers, sample, total_rows, header_row_offset}]}`. Catalogue-agnostic. |
| Apply (mapped columns → create PurchaseItems) | `POST /api/purchases/{pid}/items/import-mapped` | Yes | Yes — required | Creates PurchaseItem rows in DB under purchase pid |
| Smart import | `POST /api/purchases/{pid}/items/import-smart` | Yes | Yes — required | Uses markitdown + column detection. `confirm=false` returns preview. `confirm=true` creates rows |

**The import-mapped and import-smart endpoints write to `purchase_items` table and require a real purchase ID. They cannot be called for WishItem creation.**

**Resolution for Wish context (recommended approach):**

The `doMappedImport` function in the component should branch:

```ts
if (props.purchaseId) {
  // Purchase path — call /api/purchases/{pid}/items/import-mapped as today
} else {
  // Wish path (and any context without pid) — build items array from preview data
  // using dragMapping, emit update:modelValue with new items
  // No API call. Parent persists on save.
}
```

For smart import in Wish context: use `confirm=false` preview-only (no `confirm=true`), then add parsed rows to `modelValue`. The client-side path already exists in `doSmartImport` for `columnMappingApplied.value === true` (lines 4808–4828) — this pattern works without a purchase ID.

**The component needs a `purchaseId` optional prop** (`purchaseId?: number | null`). Pass from CreateOrderView. WishesView passes nothing (undefined/null). This is additive to the locked props API; CONTEXT.md does not forbid it.

---

## Q5 — Smart AI Import

**Location:** `purchases.py:2398` — `POST /{pid}/items/import-smart`

**Technology:** NOT an LLM call. Uses `markitdown` (document → markdown text) + internal Python column detection (`parse_markdown_tables`, `pick_best_table`, `detect_columns` from `app.utils.document_to_markdown`). No OpenAI / Anthropic API call. Pure heuristic column matching.

**Two-step flow in frontend:**
1. `doSmartPreview` (`confirm=false`) — returns `{preview: [], columns_found: []}` 
2. `doSmartImport` (`confirm=true`) — creates rows in DB; OR if `columnMappingApplied.value`, skips API and directly pushes rows to `items.value` (lines 4808–4828)

**For Wish context:** Only `confirm=false` (preview) + client-side push to items array. Skip `confirm=true`. This is already supported by the existing code path.

---

## Q6 — Photo Upload Flow

**Endpoint:** `POST /api/products/{product_id}/photo` (products.py:794)

**Request:** `multipart/form-data` with field `file` (UploadFile). Allowed MIME: `image/jpeg, image/jpg, image/png, image/webp, image/gif`.

**Storage:** `/app/uploads/products/product_{id}{ext}` (inside container). Path is a bind-mount or volume.

**Response:** Returns full `ProductOut` object with updated `photo_url` set to `/api/products/photos/{filename}`.

**Product model has both fields:**
- `photo_url` — local upload path (e.g. `/api/products/photos/product_42.jpg`)
- `photo_link` — external URL fallback

**Priority in `onItemProductSelect`:** `val.photo_url || val.photo_link || undefined` (line 4891).

**No auth check** in the upload endpoint (no `Depends(get_current_user)`) — the endpoint at line 794 only depends on `db`.

---

## Q7 — OrderProductsTable.vue — Decision: DELETE

**Status:** Pure dead code.

**Evidence:**
- Only imported in `CreateOrderView.backup.vue` (line 254) — a backup file, not in the actual router or production build.
- Not imported anywhere in active `.vue` files (`grep` confirmed: zero results in `frontend/src/views/` or active components).
- The component uses a different data shape (`OrderProduct { product: Product; quantity; price }`) — incompatible with the `EditorItem` interface used in CreateOrderView.
- It is an earlier, abandoned implementation that predates the inline items table.

**Recommendation:** Delete `OrderProductsTable.vue` in Plan A (Wave 1) as a cleanup task. Planner should include: audit (read file), confirm no active imports, delete file.

---

## Q8 — Dead Code Components Audit

| Component | Active Imports Found | Decision |
|-----------|---------------------|----------|
| `OrderProductsTable.vue` | Only in `.backup.vue` | DELETE |
| `AdvancedProductSelector.vue` | Not confirmed imported in active views | Likely DELETE (uses old `.sync` modifier syntax for Vue 2 — `search-input.sync` at line 8; incompatible with Vue 3) |
| `SimpleProductSelector.vue` | Only in `.backup.vue` (line 253) | DELETE |
| `CreateOrderView.backup.vue` | Not in router | DELETE after Phase 15 |

None of these can serve as a starter for `PurchaseItemsEditor`. The authoritative source is the inline block in `CreateOrderView.vue`.

---

## Q9 — Unit Presets and Country List

**UNIT_OPTIONS** (line 2859 in CreateOrderView.vue):
```ts
const UNIT_OPTIONS = ['шт.', 'усл.', 'компл.', 'уп.', 'м.', 'кг.', 'л.', 'п.м.', 'кв.м.', 'час.', 'мес.', 'год']
```
Note: CreateOrderView uses trailing dots (шт., усл.) but WishesView.vue inline uses no dots (['шт', 'компл', 'усл', 'м', 'кг', 'л', 'м²']). The new component should use the CreateOrderView version (canonical) — trailing dot variants. CONTEXT.md specifies `'шт, компл, усл, м, кг, л, м²'` — planner must decide which to use; recommend CreateOrderView version with dots.

**COUNTRIES** (line 2858 in CreateOrderView.vue):
```ts
const COUNTRIES = ['Российская Федерация', 'Беларусь', 'Казахстан', 'Китай', 'Германия', 'США', 'Япония', 'Турция', 'Индия']
```
Default is `'Россия'` (prop `defaultCountry`). The country field in CreateOrderView is a `v-text-field` with `placeholder="Россия"` — not a select. Keep as free-text field with hint.

Both are inline constants — move to child as module-level constants.

---

## Q10 — Vuetify Caveats Confirmed in Code

**Quirk 1 — clearItem must set `_photo_url = undefined` explicitly (not `null`):**
```ts
// line 4952–4957
items.value[idx]._photo_url = undefined
items.value[idx]._description = undefined
```
Vuetify v-autocomplete's `@click:clear` handler fires before the model updates. Setting to `undefined` (not `null`) avoids stale photo tooltip rendering on next render.

**Quirk 2 — onItemProductSelect receives string when user types free text:**
At line 4879: `typeof val === 'string'` — Vuetify combobox returns the raw string if user types without selecting. Must handle both `string` and `Product` types (lines 4876–4903).

**Quirk 3 — v-autocomplete with `return-object` and `no-filter`:**
The product picker uses `productFilter` as custom-filter (line 4908) with a stable `products.value` ref. The CONTEXT.md note says: "Vuetify search-reset bug — items never change while typing → no Vuetify search-reset bug." The new component must replicate this: pass the full `products.value` as `:items` and provide `custom-filter`.

**Quirk 4 — v-file-input binding:**
`fullProductPhotoFileList` is `ref<File[]>([])` (not `File | null`). `@update:model-value` receives `File[]`. The handler `onFullPhotoFileChange(files: File[])` takes the first element (line 4165). Preserve this pattern in the new component.

**Quirk 5 — `items` ref mutated directly in `removeSelectedItems`:**
```ts
items.value = items.value.filter(...)  // line 4433
```
This reassigns the ref, which triggers `v-for` re-render. When using v-model, emit must happen after any direct mutation.

---

## Q11 — FileDropZone Usage Patterns

**Confirmed API from `FileDropZone.vue`:**
- Props: `modelValue?: File | null`, `accept?: string`, `multiple?: boolean`, `hint?: string`
- Emits: `update:modelValue` (single file), `files` (array, both single and multiple)
- When `multiple: false` (default): drops emit `update:modelValue` with `files[0]`
- When `multiple: true`: drops emit `files` with all files, does NOT emit `update:modelValue`
- Has `#default` scoped slot with `{ file, dragging, clear, open }`
- Exposes `openPicker()` and `clear()` via `defineExpose`

**Three usages in CreateOrderView.vue:**
1. Line 2035 (`addContractorDialog`) — stays in CreateOrderView, not part of the editor
2. Line 2190 (`itemsImportDialog` Step 1) — moves to PurchaseItemsEditor
3. No third usage in editor (the smart import section uses `v-file-input` directly, not FileDropZone)

For the import dialog in PurchaseItemsEditor, usage is identical to current: `<FileDropZone v-model="itemsImportFile" accept=".xlsx,.xls,.pdf,.docx,.doc" hint="..." />` — single file, no `multiple`.

---

## Q12 — Parent Save-Time Item Serialization

**CreateOrderView (line 5441):**
```ts
const validItems = items.value
  .filter(i => i.item_name?.trim())
  .map(({ _selectedProduct, _photo_url, _description, _description_44fz, ...rest }) => ({
    ...rest,
    unit_price: (rest.unit_price !== '' && rest.unit_price != null) ? rest.unit_price : null,
    quantity: (rest.quantity !== '' && rest.quantity != null) ? rest.quantity : null,
  }))
```

**WishesView — current save at saveWish():** No stripping of `_*` fields exists today because WishesView has no `_selectedProduct` / `_photo_url` fields at all. After Phase 15, WishesView will receive `EditorItem[]` from the component which includes `_*` fields. The `saveWish` function must add the same strip-map before sending to `PUT /api/wishes/{id}`:
```ts
const validItems = wishForm.value.items
  .filter(i => i.item_name?.trim())
  .map(({ _selectedProduct, _photo_url, _description, ...rest }) => rest)
```
This is a required addition in the WishesView wiring plan (ITEMS-EDITOR-07).

The `WishItem` model does NOT have `final_unit_price`, `final_total`, `feo_planned_item_id` columns — the strip must also drop those (they will be `undefined` when `itemShape='wish'`, so spread+rest is sufficient).

---

## Q13 — Risk Analysis (Top 5)

**Risk 1: `syncContractPriceIfSingle` cross-boundary call (HIGH)**
`calcItemTotal` calls `nextTick(() => syncContractPriceIfSingle())` at line 4866. After extraction, this function lives in CreateOrderView and is not accessible from the child. If not addressed, changing item prices will NOT update `contract_price` auto-field.
Mitigation: emit `'items-changed'` from child after any `calcItemTotal` call; parent's `@items-changed` handler calls `syncContractPriceIfSingle()`.

**Risk 2: `items.value` reference after import-mapped side-effects (HIGH)**
`doMappedImport` calls `loadPurchase()` after successful import (line 4745), which overwrites `items.value` from the DB. After extraction, `loadPurchase` is a parent function. The component must emit a `'reload-requested'` event (or parent can watch `itemsImportResult`) so parent re-fetches the purchase and passes updated `modelValue` down.

**Risk 3: Draft auto-save touching `items.value` (MEDIUM)**
CreateOrderView has a `clearDraft` / draft save mechanism. After extraction, draft serialization must include the current `modelValue` of PurchaseItemsEditor. Search for `clearDraft` / `draftSaved` usages — these read `items.value` directly. After extraction, draft must read from the prop not an internal ref.

**Risk 4: `removeSelectedItems` calls `doSave(false)` when `isEdit.value` (line 4435)**
This couples bulk-delete to the parent's save function. After extraction, bulk-delete inside the child must emit `'items-changed'` and the parent conditionally auto-saves. If missed, deleting selected rows in edit mode will not auto-save.

**Risk 5: Template scoped CSS in CreateOrderView's `<style>` block affecting import dialog (MEDIUM)**
The `imap-grid`, `imap-col`, `imap-card` CSS classes used by the drag-drop column mapper are defined in CreateOrderView's `<style scoped>`. When the import dialog moves to PurchaseItemsEditor, those styles must move with it. Missing styles will cause the column mapper to render as unstyled blocks.

---

## Q14 — Testing Strategy

**Existing specs relevant to this phase:**
- `e2e/05-orders.spec.ts` — tests create-order form loads, filters, export button. Does NOT test items table, autocomplete, or import.
- `e2e/08-products.spec.ts` — tests products list page. Does not test the inline editor.
- No existing spec touches WishesView items.

**New spec:** `e2e/18-purchase-items-editor.spec.ts`

**Pattern to follow** (from helpers.ts):
```ts
import { test, expect, Page } from '@playwright/test'
import { login, clickButton, collectApiErrors, waitForOverlays } from './helpers'

test.describe('PurchaseItemsEditor — CreateOrderView', () => {
  // beforeAll: login, navigate to /create-order
  // tests: ...
})
test.describe('PurchaseItemsEditor — WishesView', () => {
  // beforeAll: login, navigate to /wishes, open create dialog
  // tests: ...
})
```

**Key test cases per ITEMS-EDITOR-01..08:**

| Requirement | Test | Approach |
|-------------|------|----------|
| ITEMS-EDITOR-02 | Autocomplete shows products | Navigate to /create-order, click item name field, verify product picker dialog opens |
| ITEMS-EDITOR-02 | Photo tooltip visible | Add product with photo, hover thumbnail, assert tooltip img visible |
| ITEMS-EDITOR-02 | Auto-calc | Fill qty=3 price=100, assert total=300 |
| ITEMS-EDITOR-02 | Row delete | Add item, click delete icon, assert row count decrements |
| ITEMS-EDITOR-03 | Full product dialog opens | Click "Добавить товар в каталог", verify dialog visible |
| ITEMS-EDITOR-04 | Excel import dialog | Click "Импорт из файла", verify Step 1 shows FileDropZone |
| ITEMS-EDITOR-06 | CreateOrderView still saves | Create purchase with 2 items, save, reload, assert both items present |
| ITEMS-EDITOR-07 | WishesView items parity | Open Wishes, create wish, add position, verify autocomplete available |
| ITEMS-EDITOR-08 | No regression on existing purchase | Load existing purchase `/orders/{id}/edit`, verify items load |

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead |
|---------|-------------|-------------|
| File drag-and-drop | Custom event handlers on div | `FileDropZone.vue` — already exists, tested |
| Product search | Server-side search endpoint | Client-side filter over pre-loaded `products.value` (pattern already proven) |
| Photo preview | Custom FileReader logic | `URL.createObjectURL(file)` — already used at line 4167 |
| Excel column auto-detection | Custom regex | `autoDetectMapping()` function — move it wholesale |
| Vuetify overlay dismiss | Custom scrim handler | `waitForOverlays` from `e2e/helpers.ts` in tests |

---

## Architecture Patterns

### Component File Structure
```
frontend/src/components/
├── PurchaseItemsEditor.vue    # new — ~800 lines (template 300, script 500)
├── FileDropZone.vue           # existing — imported by PurchaseItemsEditor
├── OrderProductsTable.vue     # DELETE in Plan A
└── AdvancedProductSelector.vue # DELETE (dead code)
```

### v-model Pattern (Vue 3 Composition API)
```typescript
// PurchaseItemsEditor.vue
const props = defineProps<{
  modelValue: EditorItem[]
  itemShape: 'purchase' | 'wish'
  purchaseId?: number | null        // needed for import-mapped/import-smart
  allowedItemTypes?: string[]
  defaultItemType?: string
  defaultUnit?: string
  defaultCountry?: string
  supportsExcelImport?: boolean
  supportsSmartImport?: boolean
  supportsFullProductDialog?: boolean
  supportsPhotoUpload?: boolean
  readonly?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [items: EditorItem[]]
  'item-added': [item: EditorItem]
  'item-removed': [idx: number]
  'product-created': [product: Product]
  'items-changed': []           // parent calls syncContractPriceIfSingle
}>()

// Internal copy — never mutate props directly
const localItems = ref<EditorItem[]>([...props.modelValue])

watch(() => props.modelValue, (v) => { localItems.value = [...v] }, { deep: true })

function emitUpdate() {
  emit('update:modelValue', localItems.value)
  emit('items-changed')
}
```

### Anti-Patterns to Avoid
- **Mutating `props.modelValue` directly** — Vuetify inputs may appear to work but will cause reactivity issues; always use `localItems` copy.
- **Calling `loadPurchase()` from inside child** — child should emit `'reload-requested'`; parent owns the purchase fetch lifecycle.
- **Putting `syncContractPriceIfSingle` logic in child** — it reads `isSinglePurchase`, `contractPriceMode`, `displayNmck` which are all Purchase-specific. Child only emits.

---

## Validation Architecture

> `workflow.nyquist_validation` — not explicitly set to false in `.planning/config.json`, so validation section is REQUIRED.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | Playwright (no unit tests in project) |
| Config file | `playwright.config.ts` |
| Quick run command | `npx playwright test e2e/18-purchase-items-editor.spec.ts` |
| Full suite command | `npx playwright test` |

### Phase Requirements → Validation Map

| Req ID | Behavior | Test Type | Automated Command / Check | File |
|--------|----------|-----------|--------------------------|------|
| ITEMS-EDITOR-01 | PurchaseItemsEditor.vue exists, props typed correctly | Build check | `cd frontend && npx tsc --noEmit` | `src/components/PurchaseItemsEditor.vue` |
| ITEMS-EDITOR-01 | Component renders in both parents without console errors | Smoke E2E | `npx playwright test e2e/18-purchase-items-editor.spec.ts -g "renders"` | Wave 0 |
| ITEMS-EDITOR-02 | Autocomplete/picker shows products from catalogue | E2E | `npx playwright test e2e/18-purchase-items-editor.spec.ts -g "autocomplete"` | Wave 0 |
| ITEMS-EDITOR-02 | Photo tooltip visible on hover | E2E | `npx playwright test e2e/18-purchase-items-editor.spec.ts -g "photo tooltip"` | Wave 0 |
| ITEMS-EDITOR-02 | qty*price auto-calc | E2E | `npx playwright test e2e/18-purchase-items-editor.spec.ts -g "auto-calc"` | Wave 0 |
| ITEMS-EDITOR-02 | Row delete | E2E | `npx playwright test e2e/18-purchase-items-editor.spec.ts -g "row delete"` | Wave 0 |
| ITEMS-EDITOR-03 | Full product dialog opens, photo upload field visible | E2E | `npx playwright test e2e/18-purchase-items-editor.spec.ts -g "full product dialog"` | Wave 0 |
| ITEMS-EDITOR-04 | Excel import dialog Step 1 (FileDropZone) visible | E2E | `npx playwright test e2e/18-purchase-items-editor.spec.ts -g "excel import step 1"` | Wave 0 |
| ITEMS-EDITOR-04 | Step 2 column mapping UI renders after file upload | E2E (manual-only for file input) | Manual smoke: upload test.xlsx, verify column cards | Manual |
| ITEMS-EDITOR-05 | Smart import dialog accessible | E2E | `npx playwright test e2e/18-purchase-items-editor.spec.ts -g "smart import"` | Wave 0 |
| ITEMS-EDITOR-06 | CreateOrderView saves purchase with items, reloads correctly | E2E | `npx playwright test e2e/05-orders.spec.ts` (existing, no regression) | Existing |
| ITEMS-EDITOR-06 | syncContractPriceIfSingle fires after item price change | Manual smoke | Edit item price, verify "Цена договора" field updates | Manual |
| ITEMS-EDITOR-06 | `final_unit_price`, `final_total` columns visible in purchase context | E2E grep | `grep -n "final_unit_price" frontend/src/components/PurchaseItemsEditor.vue` | Grep |
| ITEMS-EDITOR-07 | WishesView creates wish with items, persists on save | E2E | `npx playwright test e2e/18-purchase-items-editor.spec.ts -g "WishesView items"` | Wave 0 |
| ITEMS-EDITOR-07 | WishesView strips _* fields before PUT | Grep | `grep -n "_selectedProduct\|_photo_url" frontend/src/views/WishesView.vue` (should not appear in saveWish payload) | Grep |
| ITEMS-EDITOR-08 | OrderProductsTable.vue deleted | Grep | `ls frontend/src/components/OrderProductsTable.vue` (should fail) | Grep/FS |
| ITEMS-EDITOR-08 | No TS import errors after deletion | Build | `cd frontend && npm run build` | Build |

### Sampling Rate
- **Per task commit:** `cd frontend && npx tsc --noEmit`
- **Per wave merge:** `npx playwright test e2e/18-purchase-items-editor.spec.ts`
- **Phase gate:** Full suite `npx playwright test` green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `e2e/18-purchase-items-editor.spec.ts` — must be created in Wave 1 or Wave 3 (Plan E)
- [ ] No framework install needed — Playwright already configured

---

## Common Pitfalls

### Pitfall 1: Import-mapped endpoint requires purchase ID
**What goes wrong:** Component calls `POST /api/purchases/{pid}/items/import-mapped` with `pid=null` → 404 or 422.
**Why it happens:** Developer assumes the import endpoint is catalogue-agnostic like preview; it is not.
**How to avoid:** Branch on `props.purchaseId` in `doMappedImport`. For null pid, compute items client-side from dragMapping + preview rows and emit `update:modelValue`.
**Warning signs:** 404 response in browser network tab when trying import in WishesView.

### Pitfall 2: Missing imap-* CSS classes in new component
**What goes wrong:** Column mapper Step 2 renders as unstyled divs without column borders/backgrounds.
**Why it happens:** Styles are in CreateOrderView's `<style scoped>` block.
**How to avoid:** Copy imap-* CSS to PurchaseItemsEditor's `<style scoped>`.
**Warning signs:** Column mapping UI appears as flat text list without card/column layout.

### Pitfall 3: `syncContractPriceIfSingle` not called after item price change
**What goes wrong:** Auto-fill of "Цена договора" field stops working in CreateOrderView after extraction.
**Why it happens:** `calcItemTotal` originally called `syncContractPriceIfSingle` directly; after extraction the child cannot call a parent function.
**How to avoid:** Add `emit('items-changed')` to child's `emitUpdate()`. Parent: `<PurchaseItemsEditor @items-changed="syncContractPriceIfSingle" />`.
**Warning signs:** Price contract field no longer auto-updates after editing item unit_price or quantity.

### Pitfall 4: WishesView saveWish sends _* fields to backend
**What goes wrong:** `PUT /api/wishes/{id}` receives payload with `_selectedProduct` (a full Product object) causing validation error or silently ignored fields.
**Why it happens:** WishesView today has no `_*` fields; after Phase 15 `wishForm.items` will contain EditorItem shape.
**How to avoid:** In WishesView `saveWish`, add strip-map before constructing PUT payload.
**Warning signs:** Backend returns 422 validation error; or Wish saves but items have wrong types.

### Pitfall 5: `loadPurchase()` called from inside child
**What goes wrong:** After import-mapped succeeds, child calls `loadPurchase()` (parent function) — TypeScript error or runtime crash.
**Why it happens:** The original `doMappedImport` calls `await loadPurchase()` on success (line 4745).
**How to avoid:** Replace with `emit('reload-requested')`. Parent handles the reload. Or: child emits imported items directly (the DB reload path is only needed for Purchase context, where the parent can watch the emit).

---

## State of the Art

| Old Approach | Current Approach | Note |
|--------------|------------------|------|
| Single-item purchase form | Multi-item inline table with autocomplete | Phase 1 migration path at lines 5269–5282 in loadPurchase |
| External AdvancedProductSelector/SimpleProductSelector (Vuetify 2 patterns) | Inline product picker dialog with custom-filter | Dead code confirmed |
| OrderProductsTable.vue as planned sub-component | Never used; inline table is the real implementation | Backup file only |

---

## Environment Availability

Step 2.6: SKIPPED — Phase is pure frontend refactor. No external tools, services, or CLIs beyond the existing project stack (Node, Vite, Playwright) are required. All confirmed already functional.

---

## Open Questions

1. **`purchaseId` prop — not in CONTEXT.md locked props list**
   - What we know: Import-mapped and smart-import need pid; CONTEXT.md does not include it in the props list
   - What's unclear: Does adding `purchaseId?: number | null` violate any decision?
   - Recommendation: Add as optional prop; it is a technical necessity and doesn't change the external API semantics. CONTEXT.md says "API surfaces — consumed, not changed" which is still true; the prop is just the mechanism to pass pid to the component.

2. **`_description_44fz` field — not in CONTEXT.md EditorItem interface**
   - What we know: CreateOrderView uses `_description_44fz` at lines 4878, 4893, 5441. It's stripped at save.
   - What's unclear: Should it appear in the shared EditorItem interface?
   - Recommendation: Include it in the interface as optional `_description_44fz?: string`. It's needed for TZ mode toggling in Purchase context (`activeDescription()` function at line 2970). In Wish context it will always be `undefined`.

3. **WishesView `addItem` default values mismatch**
   - What we know: WishesView `addItem()` defaults `country_origin: 'Россия'` (line 761) but CONTEXT.md `defaultCountry` prop defaults to `'Россия'`. Both agree.
   - Recommendation: No conflict. Use prop default `'Россия'` in component.

---

## Sources

### Primary (HIGH confidence — sourced from actual files)
- `frontend/src/views/CreateOrderView.vue` lines 292–436, 1913–2018, 2163–2308, 2775–2884, 2977–2999, 4120–4960, 5409–5488
- `frontend/src/views/WishesView.vue` lines 326–399, 573–772
- `frontend/src/components/FileDropZone.vue`
- `frontend/src/components/OrderProductsTable.vue`
- `backend/app/routers/purchases.py` lines 2029–2550 (import endpoints)
- `backend/app/routers/products.py` lines 56–85, 794–815 (list + photo upload)
- `backend/app/models/purchase_item.py`
- `backend/app/models/wish_item.py`
- `e2e/helpers.ts`, `e2e/05-orders.spec.ts`

### Secondary (MEDIUM confidence)
- `frontend/src/components/AdvancedProductSelector.vue` — partially read; dead code conclusion based on import grep result

---

## Metadata

**Confidence breakdown:**
- State to extract: HIGH — read directly from source files with line references
- Import endpoints: HIGH — verified in purchases.py router; CONTEXT.md path `/api/purchase-items/import/excel/preview` was wrong, actual path confirmed
- Architecture decisions: HIGH — all derived from actual code, not assumption
- Pitfalls: HIGH — all five are directly observed in the code, not hypothetical

**Research date:** 2026-04-19
**Valid until:** 60 days (stable codebase, no external API dependency)

---

## RESEARCH COMPLETE

**Phase:** 15 - Reusable Purchase Items Editor
**Confidence:** HIGH

### Key Findings

1. **Excel import endpoint mismatch with CONTEXT.md** — The actual preview endpoint is `POST /api/purchases/items/import-preview` (no pid); the apply endpoint `POST /api/purchases/{pid}/items/import-mapped` requires a purchase ID. For Wish context, the component must use client-side-only row assembly from preview data and emit upward. A `purchaseId?: number | null` prop is technically required and must be added to the locked props.

2. **Product search is entirely client-side** — `GET /api/products/` fetches all products once on mount; in-memory filter drives both the product picker dialog and the combobox custom-filter. No debounce, no server search endpoint.

3. **Smart import is heuristic, not LLM** — Uses markitdown + Python column detection. Can run in Wish context using `confirm=false` preview-only + client-side push.

4. **`syncContractPriceIfSingle` boundary crossing** — Must be handled via `emit('items-changed')` from child; parent wires `@items-changed="syncContractPriceIfSingle"`.

5. **OrderProductsTable.vue confirmed dead code** — Only imported in `.backup.vue`. Delete it.

### Files Created
`C:/Users/1/Desktop/Cursor/VSKS_CRM/.planning/phases/15-reusable-purchase-items-editor/15-RESEARCH.md`

### Confidence Assessment
| Area | Level | Reason |
|------|-------|--------|
| State to extract (Q1) | HIGH | Line-by-line audit of CreateOrderView.vue script block |
| API endpoints (Q4/Q5/Q6) | HIGH | Read actual router implementations |
| Architecture patterns | HIGH | Derived from existing proven patterns in codebase |
| Pitfalls | HIGH | Each observed in actual code |
| Testing | HIGH | Existing helpers.ts and spec patterns confirmed |

### Open Questions
1. `purchaseId` prop addition — technically required, not in CONTEXT.md locked list (LOW risk — additive)
2. `_description_44fz` field in EditorItem interface — needed for TZ mode in Purchase context

### Ready for Planning
Research complete. Planner can now create PLAN.md files.
