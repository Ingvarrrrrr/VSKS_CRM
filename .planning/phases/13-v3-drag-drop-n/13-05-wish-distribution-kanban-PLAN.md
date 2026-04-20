---
phase: 13-v3-drag-drop-n
plan: 05
type: execute
wave: 3
depends_on:
  - 02
  - 04
files_modified:
  - frontend/package.json
  - frontend/src/components/WishDistributionKanban.vue
  - frontend/src/components/WishDistributionCard.vue
  - frontend/src/views/WishesView.vue
autonomous: true
requirements:
  - D-01
  - D-02
  - D-04
  - D-05
  - D-08
must_haves:
  truths:
    - "Opening a wish renders an N+1 column kanban — one column per distinct product.category plus 'Не определено'"
    - "Dragging a card from column A to column B persists target_column_key via PATCH and visually moves instantly"
    - "Each column header shows: category name, item count badge, sum of total_price as НМЦК"
    - "Wish total NMCK (sum across columns) is visible at board top"
    - "Clicking 'Одобрить (создать N закупок)' calls POST /approve-distribution and on success switches the view to an approved banner with links to the created purchases"
    - "After approval, all drag-drop is disabled and the kanban becomes read-only"
    - "PurchaseItemsEditor in WishesView renders with item-shape='purchase' (D-08) — full column set (country, photo, description, НМЦК) matching CreateOrderView"
    - "DnD persistence (save → reload → card stays in new column) verified by E2E Scenario 2 in 13-07 (no local automated reload test in this plan)"
  artifacts:
    - path: "frontend/package.json"
      provides: "vuedraggable-next dependency (Vue 3 compatible fork of vuedraggable)"
      contains: "vuedraggable"
    - path: "frontend/src/components/WishDistributionKanban.vue"
      provides: "Kanban board container with columns, DnD orchestration, approve button"
      contains: "defineProps<{ wish: Wish, items: WishItem[], readonly: boolean }>()"
    - path: "frontend/src/components/WishDistributionCard.vue"
      provides: "Single item card (photo, name, qty, price) used inside draggable column"
      contains: "defineProps<{ item: WishItem }>()"
    - path: "frontend/src/views/WishesView.vue"
      provides: "Conditional rendering: when wish has items AND status in (draft/submitted) → show kanban view instead of plain form"
      contains: "WishDistributionKanban"
  key_links:
    - from: "WishDistributionKanban.vue @end event on draggable"
      to: "PATCH /api/wishes/{wid}/items/{iid} with {target_column_key}"
      via: "apiFetch('wishes/{wid}/items/{iid}', { method: 'PATCH', body: JSON.stringify({target_column_key: newKey}) })"
      pattern: "PATCH.*items.*target_column_key"
    - from: "Одобрить button"
      to: "POST /api/wishes/{wid}/approve-distribution"
      via: "apiFetch('/wishes/{wid}/approve-distribution', { method: 'POST' })"
      pattern: "approve-distribution"
    - from: "After approval"
      to: "N purchase detail pages"
      via: "response.purchase_ids.map(id => router link `/orders/${id}/edit`)"
      pattern: "/orders/.*edit"
---

<objective>
Build the flagship kanban UI inside WishesView. Implements CONTEXT D-01 (kanban columns = future purchases), D-02 (always-present «Не определено» column), D-04 (DnD only within same wish), D-05 (approve button), D-08 (flip PurchaseItemsEditor prop `item-shape="wish"` → `"purchase"` in WishesView.vue line 334 — confirmed via grep that current value is `"wish"`, must become `"purchase"` for full columns set: country, photo, description, НМЦК).

Purpose: This is the user-facing deliverable — the moment «заявка» becomes a real tool. Everything else in Phase 13 feeds into this screen.

Output:
- `vuedraggable@next` installed (Vue 3 compatible fork; native HTML5 DnD as fallback is harder to polish — vuedraggable-next is ~10KB and battle-tested)
- Two new components + wire into existing WishesView
- No regression to existing wish form — kanban is a conditional alternate view triggered by items count > 0
</objective>

<execution_context>
@C:/Users/1/Desktop/Cursor/VSKS_CRM/.claude/get-shit-done/workflows/execute-plan.md
@C:/Users/1/Desktop/Cursor/VSKS_CRM/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/13-v3-drag-drop-n/CONTEXT.md
@.planning/phases/13-v3-drag-drop-n/13-02-wish-distribution-approve-PLAN.md
@.planning/phases/13-v3-drag-drop-n/13-04-advanced-product-selector-category-required-PLAN.md

<interfaces>
From Plan 13-02 (backend API):
- PATCH /api/wishes/{wid}/items/{iid} body `{target_column_key: string | null}` → `{id, target_column_key}`
- POST /api/wishes/{wid}/approve-distribution → `{wish_id, purchase_ids: [int, int, ...], count, status: "approved"}`
- GET /api/wishes/{wid} already returns WishOut with items[]; each item gets new `target_column_key` field

From frontend/src/views/WishesView.vue line 332:
```vue
<PurchaseItemsEditor
  v-model="wishForm.items"
  ...
```
(existing — keep as-is for draft mode where user adds items)

From frontend/src/views/CreateOrderView.vue line 2471: `apiFetch` is used everywhere for API — import from `@/api/client` or wherever WishesView does.

WishItem TypeScript shape (inferred from schema + Plan 13-02):
```typescript
interface WishItem {
  id: number
  product_id: number | null
  item_name: string
  item_type: string
  quantity: number
  unit: string
  unit_price: number
  total_price: number
  country_origin: string
  target_column_key: string | null
  // client-only resolution helpers (not persisted):
  _resolved_key?: string  // computed from target_column_key OR product.category OR "__uncategorized__"
  _product_category?: string  // joined from /api/products/{id} when product_id present
}
```

vuedraggable-next API (for reference during implementation):
```vue
<draggable v-model="columnItems" :group="{ name: 'wish-items' }" item-key="id" @end="onDragEnd">
  <template #item="{ element }">
    <WishDistributionCard :item="element" />
  </template>
</draggable>
```
The `:group` name must be IDENTICAL across all columns within one wish (so cards can move between them) and NOT shared with any other wish's board (scoping to single wish per D-04). Since each wish renders its own Kanban instance, default single-component scoping is sufficient — but explicitly use `group: 'wish-{wid}'` to be safe.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1: Install vuedraggable-next dependency</name>
  <read_first>
    - frontend/package.json (current deps, lines 11-27)
    - .planning/phases/13-v3-drag-drop-n/CONTEXT.md (D-01)
  </read_first>
  <action>
    Run in frontend/:
    ```bash
    cd frontend && npm install vuedraggable@next
    ```

    This installs `vuedraggable@^4.x` (Vue 3 compatible). Verify `package.json` now has:
    ```json
    "vuedraggable": "^4.1.0"
    ```
    (version may differ — just confirm entry exists).

    Run `npm install` again to update `package-lock.json` if not already updated.
  </action>
  <verify>
    <automated>cd frontend && grep -q "vuedraggable" package.json && test -d node_modules/vuedraggable && echo "OK: vuedraggable installed"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "vuedraggable" frontend/package.json`
    - `test -d frontend/node_modules/vuedraggable`
    - `cd frontend && npm run build` passes (sanity — no import break yet because we haven't used it)
  </acceptance_criteria>
  <done>
    Dependency installed and ready to import.
  </done>
</task>

<task type="auto" tdd="false">
  <name>Task 2: Create WishDistributionCard.vue + WishDistributionKanban.vue components</name>
  <read_first>
    - frontend/src/components/PurchaseItemsEditor.vue (how items are displayed — rows 170-260 show card-like structure with photo, name, qty, price; model structure for `EditorItem`)
    - frontend/src/views/WishesView.vue lines 655-770 (wishForm.items structure, apiFetch usage pattern, showSnack usage)
    - Plan 13-02 PLAN.md (API contract — exact request/response shapes for PATCH/approve-distribution)
    - .planning/phases/13-v3-drag-drop-n/CONTEXT.md (D-01, D-02, D-04, D-05)
  </read_first>
  <action>
    === File 1: frontend/src/components/WishDistributionCard.vue ===

    ```vue
    <template>
      <div class="wish-card" :class="{ 'readonly': readonly }">
        <div class="wish-card-photo">
          <img v-if="item._photo_url" :src="item._photo_url" alt="" />
          <v-icon v-else color="grey-lighten-1" size="32">mdi-package-variant</v-icon>
        </div>
        <div class="wish-card-body">
          <div class="wish-card-name" :title="item.item_name">{{ item.item_name }}</div>
          <div class="wish-card-meta">
            <span class="wish-card-qty">{{ item.quantity }} {{ item.unit || 'шт' }}</span>
            <span class="wish-card-price">{{ formatMoney(item.total_price) }}</span>
          </div>
          <v-chip v-if="item._product_category" size="x-small" color="info" variant="tonal" class="mt-1">
            {{ item._product_category }}
          </v-chip>
        </div>
      </div>
    </template>

    <script setup lang="ts">
    interface WishItem {
      id: number
      item_name: string
      quantity: number
      unit: string
      total_price: number
      target_column_key: string | null
      _photo_url?: string
      _product_category?: string
    }
    defineProps<{
      item: WishItem
      readonly?: boolean
    }>()
    function formatMoney(v: number | null | undefined): string {
      if (v == null) return '0 ₽'
      return new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 }).format(v)
    }
    </script>

    <style scoped>
    .wish-card {
      display: flex; gap: 8px; padding: 8px 10px;
      background: rgb(var(--v-theme-surface));
      border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
      border-radius: 6px;
      cursor: grab;
      transition: box-shadow 0.15s, transform 0.15s;
    }
    .wish-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.12); transform: translateY(-1px); }
    .wish-card.readonly { cursor: default; opacity: 0.85; }
    .wish-card.readonly:hover { box-shadow: none; transform: none; }
    .wish-card-photo { width: 48px; height: 48px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; background: rgba(var(--v-theme-surface-variant), 0.3); border-radius: 4px; }
    .wish-card-photo img { max-width: 100%; max-height: 100%; object-fit: contain; }
    .wish-card-body { flex: 1; min-width: 0; }
    .wish-card-name { font-weight: 500; font-size: 0.875rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .wish-card-meta { display: flex; justify-content: space-between; font-size: 0.75rem; color: rgba(var(--v-theme-on-surface), 0.7); margin-top: 2px; }
    .wish-card-price { font-weight: 600; }
    </style>
    ```

    === File 2: frontend/src/components/WishDistributionKanban.vue ===

    ```vue
    <template>
      <div class="wish-kanban-wrap">
        <!-- Header: totals -->
        <div class="wish-kanban-header">
          <div class="text-h6">Распределение позиций по закупкам</div>
          <div class="wish-kanban-totals">
            <span>Всего позиций: <strong>{{ items.length }}</strong></span>
            <span>Сумма заявки: <strong>{{ formatMoney(totalSum) }}</strong></span>
            <span>Колонок: <strong>{{ columns.length }}</strong></span>
          </div>
          <div class="wish-kanban-actions">
            <v-btn v-if="!readonly" color="success" size="large" prepend-icon="mdi-check-all"
              :loading="approving" :disabled="columns.length === 0"
              @click="onApprove">
              Одобрить (создать {{ columns.length }} закупок)
            </v-btn>
          </div>
        </div>

        <!-- Approved banner -->
        <v-alert v-if="readonly && approvedPurchaseIds.length"
          type="success" variant="tonal" class="mb-3" icon="mdi-check-circle">
          Заявка одобрена. Создано закупок: <strong>{{ approvedPurchaseIds.length }}</strong>.
          <span class="ml-2">
            <router-link v-for="pid in approvedPurchaseIds" :key="pid" :to="`/orders/${pid}/edit`" class="mr-2">
              Закупка #{{ pid }}
            </router-link>
          </span>
        </v-alert>

        <!-- Columns -->
        <div class="wish-kanban-cols">
          <div v-for="col in columns" :key="col.key" class="wish-kanban-col">
            <div class="wish-kanban-col-header" :class="{ 'is-uncat': col.key === '__uncategorized__' }">
              <div class="wish-kanban-col-title">{{ col.label }}</div>
              <div class="wish-kanban-col-meta">
                <v-chip size="x-small" color="primary" variant="flat">{{ col.items.length }}</v-chip>
                <span class="wish-kanban-col-sum">{{ formatMoney(col.sum) }}</span>
              </div>
            </div>
            <draggable
              :model-value="col.items"
              :group="`wish-${wish.id}`"
              item-key="id"
              :disabled="readonly"
              class="wish-kanban-col-body"
              @change="(e: any) => onDragChange(col.key, e)">
              <template #item="{ element }">
                <WishDistributionCard :item="element" :readonly="readonly" />
              </template>
            </draggable>
          </div>
        </div>
      </div>
    </template>

    <script setup lang="ts">
    import { computed, ref } from 'vue'
    import draggable from 'vuedraggable'
    import WishDistributionCard from './WishDistributionCard.vue'
    import { apiFetch } from '@/api/client'  // executor: adjust import path to match WishesView's apiFetch import

    interface Wish { id: number; status: string; title: string }
    interface WishItem {
      id: number; product_id: number | null; item_name: string; quantity: number; unit: string
      unit_price: number; total_price: number; target_column_key: string | null
      _product_category?: string; _photo_url?: string
    }
    const props = defineProps<{
      wish: Wish
      items: WishItem[]
      readonly: boolean
      approvedPurchaseIds?: number[]
    }>()
    const emit = defineEmits<{
      (e: 'approved', payload: { purchase_ids: number[]; count: number }): void
      (e: 'items-updated', items: WishItem[]): void
      (e: 'error', msg: string): void
    }>()

    const approving = ref(false)

    // Resolve column key: override wins; else product.category; else __uncategorized__
    function resolveKey(it: WishItem): string {
      if (it.target_column_key) return it.target_column_key
      if (it._product_category) return it._product_category
      return '__uncategorized__'
    }

    const columns = computed(() => {
      const groups = new Map<string, WishItem[]>()
      // Always ensure __uncategorized__ exists (D-02: «Не определено» column always first)
      groups.set('__uncategorized__', [])
      for (const it of props.items) {
        const k = resolveKey(it)
        if (!groups.has(k)) groups.set(k, [])
        groups.get(k)!.push(it)
      }
      // Drop __uncategorized__ if empty (per CONTEXT D-02 re-read: always FIRST if present; show even when empty for drop target)
      // Per CONTEXT D-02: "Колонка «Не определено» (всегда первая)" — keep visible even if empty so users can drag into it
      const out: Array<{ key: string; label: string; items: WishItem[]; sum: number }> = []
      // First: uncategorized
      out.push({
        key: '__uncategorized__',
        label: 'Не определено',
        items: groups.get('__uncategorized__') || [],
        sum: (groups.get('__uncategorized__') || []).reduce((s, i) => s + (Number(i.total_price) || 0), 0),
      })
      // Then: other groups sorted alphabetically by key
      for (const [k, arr] of [...groups.entries()].filter(([k]) => k !== '__uncategorized__').sort((a, b) => a[0].localeCompare(b[0], 'ru'))) {
        out.push({ key: k, label: k, items: arr, sum: arr.reduce((s, i) => s + (Number(i.total_price) || 0), 0) })
      }
      return out
    })

    const totalSum = computed(() => props.items.reduce((s, i) => s + (Number(i.total_price) || 0), 0))

    function formatMoney(v: number): string {
      return new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 }).format(v || 0)
    }

    // vuedraggable @change emits { added: { newIndex, element }, removed: { oldIndex, element }, moved: {...} }
    async function onDragChange(targetKey: string, evt: any) {
      const added = evt.added
      if (!added?.element) return  // only process the drop side
      const item: WishItem = added.element
      const newKey = targetKey === '__uncategorized__' ? null : targetKey
      try {
        await apiFetch(`/wishes/${props.wish.id}/items/${item.id}`, {
          method: 'PATCH',
          body: JSON.stringify({ target_column_key: newKey }),
        })
        // Optimistic: mutate the local item
        item.target_column_key = newKey
        const updatedList = props.items.map(i => i.id === item.id ? { ...i, target_column_key: newKey } : i)
        emit('items-updated', updatedList)
      } catch (e: any) {
        emit('error', `Не удалось сохранить распределение: ${e?.message || e}`)
      }
    }

    async function onApprove() {
      if (!confirm(`Создать ${columns.value.length} закупок и одобрить заявку? Откат будет невозможен через UI.`)) return
      approving.value = true
      try {
        const resp = await apiFetch<{ purchase_ids: number[]; count: number; status: string }>(
          `/wishes/${props.wish.id}/approve-distribution`,
          { method: 'POST' },
        )
        emit('approved', { purchase_ids: resp.purchase_ids, count: resp.count })
      } catch (e: any) {
        emit('error', `Не удалось одобрить: ${e?.message || e}`)
      } finally {
        approving.value = false
      }
    }
    </script>

    <style scoped>
    .wish-kanban-wrap { padding: 8px 0; }
    .wish-kanban-header { display: flex; flex-wrap: wrap; align-items: center; gap: 16px; margin-bottom: 12px; }
    .wish-kanban-totals { display: flex; gap: 16px; font-size: 0.875rem; color: rgba(var(--v-theme-on-surface), 0.75); }
    .wish-kanban-actions { margin-left: auto; }
    .wish-kanban-cols { display: flex; gap: 12px; overflow-x: auto; padding-bottom: 8px; min-height: 400px; }
    .wish-kanban-col {
      flex: 0 0 280px;
      background: rgba(var(--v-theme-surface-variant), 0.4);
      border-radius: 8px;
      display: flex; flex-direction: column;
      max-height: calc(100vh - 300px);
    }
    .wish-kanban-col-header {
      padding: 10px 12px; border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
      border-radius: 8px 8px 0 0; background: rgb(var(--v-theme-surface));
    }
    .wish-kanban-col-header.is-uncat { background: rgba(var(--v-theme-warning), 0.08); border-left: 3px solid rgb(var(--v-theme-warning)); }
    .wish-kanban-col-title { font-weight: 600; font-size: 0.95rem; }
    .wish-kanban-col-meta { display: flex; justify-content: space-between; align-items: center; margin-top: 4px; font-size: 0.8rem; }
    .wish-kanban-col-sum { font-weight: 500; color: rgba(var(--v-theme-on-surface), 0.75); }
    .wish-kanban-col-body { flex: 1; overflow-y: auto; padding: 8px; display: flex; flex-direction: column; gap: 6px; min-height: 100px; }
    </style>
    ```

    Notes for executor:
    - The `apiFetch` import path MUST match the path used in WishesView.vue — grep that file for `import.*apiFetch` to find the exact module.
    - The `_product_category` field on items is populated by WishesView (Task 3) by joining products → wish_items client-side; the kanban itself doesn't fetch.
    - All comments/user-facing text in Russian (matches project convention).
  </action>
  <verify>
    <automated>cd frontend && npm run build 2>&1 | grep -iE "^error|build failed" | head -10; test -f src/components/WishDistributionKanban.vue && test -f src/components/WishDistributionCard.vue && echo "OK"</automated>
  </verify>
  <acceptance_criteria>
    - Files `frontend/src/components/WishDistributionKanban.vue` and `WishDistributionCard.vue` exist
    - `grep -q "vuedraggable" frontend/src/components/WishDistributionKanban.vue`
    - `grep -q "approve-distribution" frontend/src/components/WishDistributionKanban.vue`
    - `grep -q "target_column_key" frontend/src/components/WishDistributionKanban.vue`
    - `grep -q "Не определено" frontend/src/components/WishDistributionKanban.vue`
    - `npm run build` in frontend/ exits 0
  </acceptance_criteria>
  <done>
    Two components created and build cleanly. DnD bound to PATCH endpoint. Approve bound to approve-distribution endpoint. Uncategorized column always rendered first.
  </done>
</task>

<task type="auto" tdd="false">
  <name>Task 3: Wire kanban into WishesView + enrich items with product.category</name>
  <read_first>
    - frontend/src/views/WishesView.vue (full file, 935 lines — find the wish dialog, especially lines 243-400 where PurchaseItemsEditor lives)
    - frontend/src/views/WishesView.vue lines 655-770 (wishForm, loadWishes, openEditDialog)
    - frontend/src/views/WishesView.vue lines 780-830 (saveWish — to understand the draft→submitted flow)
    - frontend/src/components/WishDistributionKanban.vue (Task 2 output)
    - backend/app/routers/products.py (GET /api/products — to understand list endpoint for joining categories)
  </read_first>
  <action>
    === Step 0 (D-08): Flip item-shape on PurchaseItemsEditor ===
    In `frontend/src/views/WishesView.vue` line 334 (confirmed by grep 2026-04-20: current value is `item-shape="wish"`), change:
    ```vue
    <PurchaseItemsEditor
      v-model="wishForm.items"
      ...
      item-shape="wish"     <!-- BEFORE -->
    ```
    to:
    ```vue
    <PurchaseItemsEditor
      v-model="wishForm.items"
      ...
      item-shape="purchase" <!-- AFTER — D-08: full column set (country, photo, description, НМЦК) -->
    ```
    Acceptance: `grep -n 'item-shape="purchase"' frontend/src/views/WishesView.vue` must return a match. `grep -q 'item-shape="wish"' frontend/src/views/WishesView.vue` must NOT match.

    === Step 1: Add products lookup for category enrichment ===
    In WishesView.vue `<script setup>`, add:
    ```typescript
    import WishDistributionKanban from '@/components/WishDistributionKanban.vue'

    const productsById = ref<Map<number, { category: string; photo_url: string | null }>>(new Map())

    async function loadProductsForWish(wishItems: any[]) {
      const ids = [...new Set(wishItems.map(i => i.product_id).filter(Boolean) as number[])]
      if (!ids.length) return
      try {
        // W9 (revision 1): Prefer id-filter if /api/products/?ids=1,2,3 exists (grep backend router).
        // If not supported: fall back to limit=10000 — known inefficiency when product catalog > 5K rows;
        // optimize in follow-up phase if the catalog grows.
        const all = await apiFetch<any[]>('/products/?limit=10000')
        productsById.value = new Map(all.map((p: any) => [p.id, { category: p.category, photo_url: p.photo_url }]))
      } catch {}
    }

    function enrichItems(items: any[]): any[] {
      return items.map(i => {
        const p = i.product_id ? productsById.value.get(i.product_id) : undefined
        return {
          ...i,
          _product_category: p?.category,
          _photo_url: p?.photo_url || null,
        }
      })
    }
    ```

    === Step 2: Track approved state per wish ===
    Add reactive state:
    ```typescript
    const wishForKanban = ref<any | null>(null)  // the wish being viewed in kanban mode
    const approvedIds = ref<number[]>([])  // set after approve response
    const kanbanItems = ref<any[]>([])
    ```

    === Step 3: Open-in-kanban handler ===
    Adjust `openEditDialog` (line 779): detect when wish has items and is not draft-empty → open kanban mode instead of pure form.
    ```typescript
    async function openEditDialog(wish: Wish) {
      editingWishId.value = wish.id
      resetForm()
      wishForm.value.subsidy_id = wish.subsidy_id ?? null
      wishForm.value.feo_category_id = wish.feo_category_id ?? null
      wishForm.value.assigned_to = wish.assigned_to ?? null
      wishForm.value.justification = wish.justification || ''
      wishForm.value.priority = wish.priority || 'medium'
      wishForm.value.desired_date = wish.desired_date || ''
      wishForm.value.items = (wish as any).items || []

      // Phase 13: load products for kanban categories, open kanban mode if wish has items
      await loadProductsForWish(wishForm.value.items)
      wishForm.value.items = enrichItems(wishForm.value.items)
      wishForKanban.value = wish
      kanbanItems.value = wishForm.value.items

      wishDialog.value = true
    }
    ```

    === Step 4: Template — add kanban below PurchaseItemsEditor ===
    After line 332-357 (where PurchaseItemsEditor lives), add a separator and the kanban. The kanban should render ONLY when `kanbanItems.length > 0`. It runs in parallel with the editor — editor lets user add/edit items, kanban lets user distribute them.

    ```vue
    <v-col v-if="wishForKanban && kanbanItems.length > 0" cols="12">
      <v-divider class="my-4" />
      <WishDistributionKanban
        :wish="wishForKanban"
        :items="kanbanItems"
        :readonly="wishForKanban.status === 'approved' || wishForKanban.status === 'rejected' || wishForKanban.status === 'converted'"
        :approved-purchase-ids="approvedIds"
        @items-updated="kanbanItems = $event"
        @approved="onWishApproved"
        @error="msg => showSnack(msg, 'error')"
      />
    </v-col>
    ```

    === Step 5: onWishApproved handler ===
    ```typescript
    async function onWishApproved(payload: { purchase_ids: number[]; count: number }) {
      approvedIds.value = payload.purchase_ids
      showSnack(`Заявка одобрена. Создано ${payload.count} закупок.`, 'success')
      // Update the wish status in the local view without forcing a close
      if (wishForKanban.value) {
        wishForKanban.value = { ...wishForKanban.value, status: 'approved' }
      }
      await loadWishes()
    }
    ```

    === Step 6: Reset state on dialog close ===
    In whichever close handler exists (probably `wishDialog = false` watcher or explicit close button), reset:
    ```typescript
    wishForKanban.value = null
    kanbanItems.value = []
    approvedIds.value = []
    ```
  </action>
  <verify>
    <automated>cd frontend && npm run build 2>&1 | grep -iE "^error|build failed" | head -20; grep -q "WishDistributionKanban" src/views/WishesView.vue && echo "OK"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "import WishDistributionKanban" frontend/src/views/WishesView.vue`
    - `grep -q "WishDistributionKanban" frontend/src/views/WishesView.vue` (used in template)
    - `grep -q "enrichItems\|_product_category" frontend/src/views/WishesView.vue`
    - `grep -q "onWishApproved\|approved-purchase-ids" frontend/src/views/WishesView.vue`
    - `grep -qE "status === .approved." frontend/src/views/WishesView.vue` (readonly gate)
    - **D-08 (revision 1):** `grep -n 'item-shape="purchase"' frontend/src/views/WishesView.vue` MUST match
    - **D-08 (revision 1):** `grep -q 'item-shape="wish"' frontend/src/views/WishesView.vue` MUST NOT match (old value removed)
    - `npm run build` green
  </acceptance_criteria>
  <done>
    Opening a wish with items renders kanban below the items editor. DnD triggers PATCH. Approve triggers POST /approve-distribution and transitions UI to read-only banner with purchase links.
  </done>
</task>

</tasks>

<verification>
- `npm run build` green
- Manually (optional dev check): open existing wish with items → see kanban below items editor, 1+ columns, cards draggable between, "Одобрить" button visible
- Click Одобрить → dialog confirm → success alert → read-only banner with purchase links
</verification>

<success_criteria>
1. vuedraggable installed and imported
2. WishDistributionKanban + WishDistributionCard components exist and build cleanly
3. Kanban renders N+1 columns (distinct categories + «Не определено»)
4. DnD persists via PATCH /items/{iid} (instant visual update)
5. Column headers show count badge + sum
6. Одобрить button calls approve-distribution, triggers UI switch to read-only
7. After approval: wish read-only, banner with purchase links visible
8. No regression in existing wish form / PurchaseItemsEditor flows
</success_criteria>

<output>
After completion, create `.planning/phases/13-v3-drag-drop-n/13-05-SUMMARY.md`
</output>
