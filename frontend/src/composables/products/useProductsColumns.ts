// useProductsColumns.ts — конфигуратор столбцов таблицы товаров.
// Дословный перенос из ProductsView.vue.
import { ref, computed } from 'vue'

// All available columns — порядок по умолчанию
export const ALL_COLUMNS = [
  { title: '',          key: 'photo',              width: 56,  sortable: false, fixed: true },
  { title: 'Наименование', key: 'name',            minWidth: 240, fixed: true },
  { title: 'Тип',       key: 'product_type',       width: 140 },
  { title: 'Категория', key: 'category',           minWidth: 140 },
  { title: 'Цена',      key: 'price',              width: 130, align: 'end' as const },
  { title: 'Цена по договору', key: 'contract_price', width: 180, align: 'end' as const },
  { title: 'Актуальность цены', key: 'price_freshness', width: 200 },
  { title: 'Страна',    key: 'country_origin',     width: 120 },
  { title: 'Статус',    key: 'is_active',          width: 110 },
  { title: 'Действия',  key: 'actions',            width: 100, sortable: false },
  { title: 'ТЗ проверено',     key: 'tz_verified_at',      width: 160, sortable: false },
  { title: 'ТЗ 44-ФЗ',        key: 'tz_44fz_verified_at', width: 150, sortable: false },
]

function loadColOrder(): string[] {
  try {
    const saved = localStorage.getItem('products_col_order')
    if (saved) {
      const arr = JSON.parse(saved) as string[]
      const allKeys = ALL_COLUMNS.map(c => c.key)
      // merge: saved + any new columns not yet in saved
      const merged = arr.filter(k => allKeys.includes(k))
      allKeys.forEach(k => { if (!merged.includes(k)) merged.push(k) })
      return merged
    }
  } catch {}
  return ALL_COLUMNS.map(c => c.key)
}

export function useProductsColumns() {
  const colOrder = ref<string[]>(loadColOrder())

  const headers = computed(() => {
    const map = Object.fromEntries(ALL_COLUMNS.map(c => [c.key, c]))
    return colOrder.value.map(k => map[k]).filter(Boolean)
  })

  function saveColOrder() {
    localStorage.setItem('products_col_order', JSON.stringify(colOrder.value))
  }

  // Column configurator dialog
  const colConfigDialog = ref(false)
  const dragSrcIdx = ref<number | null>(null)

  function onDragStart(idx: number) { dragSrcIdx.value = idx }
  function onDragOver(e: DragEvent, idx: number) {
    e.preventDefault()
    if (dragSrcIdx.value === null || dragSrcIdx.value === idx) return
    const newOrder = [...colOrder.value]
    const [moved] = newOrder.splice(dragSrcIdx.value, 1)
    newOrder.splice(idx, 0, moved)
    colOrder.value = newOrder
    dragSrcIdx.value = idx
  }
  function onDragEnd() { dragSrcIdx.value = null; saveColOrder() }
  function moveCol(idx: number, dir: -1 | 1) {
    const to = idx + dir
    if (to < 0 || to >= colOrder.value.length) return
    const newOrder = [...colOrder.value]
    ;[newOrder[idx], newOrder[to]] = [newOrder[to], newOrder[idx]]
    colOrder.value = newOrder
    saveColOrder()
  }
  function resetColOrder() {
    colOrder.value = ALL_COLUMNS.map(c => c.key)
    saveColOrder()
  }

  return {
    colOrder, headers, colConfigDialog, dragSrcIdx,
    onDragStart, onDragOver, onDragEnd, moveCol, resetColOrder,
  }
}
