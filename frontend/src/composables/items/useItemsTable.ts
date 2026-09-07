// useItemsTable — row identity (_uid, id="item-row-*" is stamped by the table
// presentational components, this owns the uid VALUE), the localItems array
// itself (single source of truth, mirrored to/from props.modelValue), CRUD
// (add/remove/clear/confirm-match) and row selection. Extracted from
// PurchaseItemsEditor.vue (monolith refactor, часть 2).
import { ref, computed, watch, type Ref } from 'vue'

// EditorItem is structurally identical to the parent's; kept loose here (same
// convention as ItemsTableFlat.vue) since the parent owns the real shape and
// this composable only reads/writes the fields it sets below.
type EditorItem = any

export interface UseItemsTableDeps {
  props: {
    modelValue: EditorItem[]
    defaultItemType?: string
    defaultUnit?: string
    defaultCountry?: string
    itemShape: 'purchase' | 'wish'
    defaultFeoPlannedItemId?: number | null
    feoPerItem?: boolean
    defaultFeoCategoryId?: number | null
  }
  emit: {
    (event: 'update:modelValue', items: EditorItem[]): void
    (event: 'items-changed'): void
    (event: 'item-added', item: EditorItem): void
    (event: 'item-removed', idx: number): void
  }
}

export function useItemsTable(deps: UseItemsTableDeps) {
  const { props, emit } = deps

  // BUG #3: stable, monotonically-increasing row identity. Used as :key so that
  // rows keep insertion order and do NOT re-order/re-render when item_name changes
  // (e.g. via inline catalog matching).
  let _uidCounter = 0
  function nextUid(): string {
    _uidCounter += 1
    return `it-${Date.now().toString(36)}-${_uidCounter}`
  }
  function ensureUid<T extends { _uid?: string | number }>(item: T): T {
    if (item._uid == null) item._uid = nextUid()
    return item
  }

  // BUG #3: assign stable _uid to every incoming item missing one (in-place so the
  // parent's objects keep identity), preserving insertion order.
  function normalizeItems(items: EditorItem[]): EditorItem[] {
    return items.map(it => ensureUid(it))
  }
  const localItems: Ref<EditorItem[]> = ref(normalizeItems([...props.modelValue]))

  // Perf: self-emit guard breaks the emit→parent-writeback→watch-rebuild echo loop.
  // Shallow watch (no deep) — we only need to react when the parent SWAPS the array
  // reference (load/reset). Local nested-field edits mutate localItems[idx] objects
  // directly and call emitUpdate() explicitly, so deep traversal is unnecessary.
  let _selfEmit = false
  watch(
    () => props.modelValue,
    (v) => {
      // Skip rebuild when the incoming value is the array we just emitted.
      if (_selfEmit) { _selfEmit = false; return }
      localItems.value = normalizeItems([...v])
    }
  )

  function emitUpdate() {
    _selfEmit = true
    emit('update:modelValue', [...localItems.value])
    emit('items-changed')
  }

  // ── Items CRUD ────────────────────────────────────────────────────────────────

  function addItem(atStart = false) {
    const newItem: EditorItem = {
      _uid: nextUid(),
      product_id: null,
      item_name: '',
      item_type: props.defaultItemType,
      quantity: null,
      unit: props.defaultUnit,
      unit_price: null,
      total_price: null,
      country_origin: props.defaultCountry,
      _selectedProduct: null,
      _photo_url: undefined,
      _description: undefined,
      _description_44fz: undefined,
    }
    if (props.itemShape === 'purchase') {
      newItem.final_unit_price = null
      newItem.final_total = null
      // F-PLAN: новая строка сразу наследует шапочную плановую позицию, если задана
      newItem.feo_planned_item_id = props.defaultFeoPlannedItemId ?? null
      newItem.over_plan = false
      // ISSUE-3 PART A: inherit header-selected deepest FEO level by default
      if (props.feoPerItem && newItem.feo_category_id == null && props.defaultFeoCategoryId != null) {
        newItem.feo_category_id = props.defaultFeoCategoryId
      }
    }
    if (atStart) {
      // Кнопка в шапке: новая строка сверху, чтобы была видна без прокрутки длинного списка
      localItems.value.unshift(newItem)
      selectedItemIdxs.value = selectedItemIdxs.value.map(i => i + 1)
    } else {
      localItems.value.push(newItem)
    }
    emit('item-added', newItem)
    emitUpdate()
  }

  function removeItem(idx: number) {
    localItems.value.splice(idx, 1)
    selectedItemIdxs.value = selectedItemIdxs.value
      .filter(i => i !== idx)
      .map(i => (i > idx ? i - 1 : i))
    emit('item-removed', idx)
    emitUpdate()
  }

  function clearItem(idx: number) {
    localItems.value[idx].item_name = ''
    localItems.value[idx].product_id = null
    localItems.value[idx]._selectedProduct = null
    localItems.value[idx]._photo_url = undefined
    localItems.value[idx]._description = undefined
    localItems.value[idx]._description_44fz = undefined
    localItems.value[idx]._price_meta = null
    emitUpdate()
  }

  function confirmMatch(idx: number) {
    const item = localItems.value[idx]
    if (item) {
      item.match_confirmed = true
      emitUpdate()
    }
  }

  // ── Selection ────────────────────────────────────────────────────────────────

  const selectedItemIdxs = ref<number[]>([])
  const allItemsSelected = computed(() =>
    localItems.value.length > 0 && selectedItemIdxs.value.length === localItems.value.length
  )

  function toggleSelectAll(val: boolean | null) {
    selectedItemIdxs.value = val ? localItems.value.map((_, i) => i) : []
  }

  function toggleItemSelect(idx: number, val: boolean | null) {
    if (val) {
      if (!selectedItemIdxs.value.includes(idx)) selectedItemIdxs.value.push(idx)
    } else {
      selectedItemIdxs.value = selectedItemIdxs.value.filter(i => i !== idx)
    }
  }

  function removeSelectedItems() {
    const toRemove = new Set(selectedItemIdxs.value)
    localItems.value = localItems.value.filter((_, i) => !toRemove.has(i))
    selectedItemIdxs.value = []
    emitUpdate()
  }

  return {
    nextUid, ensureUid, normalizeItems, localItems, emitUpdate,
    addItem, removeItem, clearItem, confirmMatch,
    selectedItemIdxs, allItemsSelected, toggleSelectAll, toggleItemSelect, removeSelectedItems,
  }
}
