// useProductsColumns.ts — конфигуратор столбцов таблицы товаров.
// Дословный перенос из ProductsView.vue.
import { ref, computed } from 'vue'

// All available columns — порядок по умолчанию
export const ALL_COLUMNS = [
  { title: '',          key: 'photo',              width: 56,  sortable: false, fixed: true },
  // width (не только minWidth) обязателен для КАЖДОЙ колонки: v-data-table
  // рендерит таблицу с table-layout:fixed (fixed-header), а в этом режиме
  // браузер по спецификации CSS2 игнорирует min-width/max-width ячеек —
  // колонка без явного width коллапсирует к 0, текст идёт по одной букве
  // столбиком (воспроизведено 14.10 даже с чистым localStorage, до «Ед.
  // изм.» это било 'name', теперь так же ловит и 'category').
  { title: 'Наименование', key: 'name',            width: 240, minWidth: 240, fixed: true },
  { title: 'Тип',       key: 'product_type',       width: 140 },
  { title: 'Категория', key: 'category',           width: 140, minWidth: 140 },
  // Ед. изм. (владелец, 14.10) — formatUnitWithPack показывает упаковку:
  // «упак. (10 шт.)» (см. ProductsTable.vue, utils/units.ts). Сортировка на
  // сервере по этой колонке не предусмотрена (не входит в SORTABLE_COLUMNS
  // app/services/product_search.py) — sortable:false, как и у остальных
  // колонок ниже без прямого соответствия серверному полю сортировки.
  { title: 'Ед. изм.',  key: 'unit',               width: 130, sortable: false },
  { title: 'Цена',      key: 'price',              width: 130, align: 'end' as const },
  // Средняя цена за 60 дней (решение владельца 2026-09-16, п.3) — avg_price/
  // avg_price_basis/avg_price_stale уже приходят в ProductOut, второго запроса
  // на строку не делаем (Правило №6). Считается не колонкой БД — сортировать
  // на сервере нечем, sortable:false (владелец, 26.10 — серверная пагинация).
  { title: 'Средняя',   key: 'avg_price',          width: 150, align: 'end' as const, sortable: false },
  { title: 'Цена по договору', key: 'contract_price', width: 180, align: 'end' as const, sortable: false },
  { title: 'Актуальность цены', key: 'price_freshness', width: 200, sortable: false },
  { title: 'Страна',    key: 'country_origin',     width: 120, sortable: false },
  { title: 'Статус',    key: 'is_active',          width: 110, sortable: false },
  { title: 'Действия',  key: 'actions',            width: 100, sortable: false },
  { title: 'ТЗ проверено',     key: 'tz_verified_at',      width: 160, sortable: false },
  { title: 'ТЗ 44-ФЗ',        key: 'tz_44fz_verified_at', width: 150, sortable: false },
]

// v-resizable-columns (frontend/src/directives/resizable-columns.ts) хранит
// ширины колонок в localStorage как массив ПО ИНДЕКСУ th (ключ 'vrc_products'),
// а не по key. Когда появляется новая колонка (напр. «Ед. изм.», владелец,
// 14.10) и порядок колонок у пользователя мигрирует (ниже), индексы всех
// колонок ПОСЛЕ точки вставки сдвигаются — а сохранённые ширины остаются на
// старых позициях: th «Тип» получает ширину бывшего соседа и т.п. (это и дало
// текст столбиком на приёмке). Директиву трогать нельзя (вне зоны этой
// задачи), поэтому переносим ширины по key здесь же, до того как директива
// их восстановит. Первая позиция th — чекбокс выбора строки (show-select),
// в colOrder не участвует, поэтому offset = 1.
const VRC_WIDTHS_KEY = 'vrc_products'
const VRC_CHECKBOX_OFFSET = 1

function migrateColumnWidths(oldOrder: string[], newOrder: string[]) {
  try {
    const saved = localStorage.getItem(VRC_WIDTHS_KEY)
    if (!saved) return
    const widths: number[] = JSON.parse(saved)
    if (widths.length !== oldOrder.length + VRC_CHECKBOX_OFFSET) return // чужая/непонятная структура — не трогаем
    const widthByKey: Record<string, number> = {}
    oldOrder.forEach((key, i) => { widthByKey[key] = widths[i + VRC_CHECKBOX_OFFSET] })
    const migrated = [
      widths[0],
      ...newOrder.map(key => widthByKey[key] ?? 0), // 0 → directive игнорирует и берёт width/minWidth колонки
    ]
    localStorage.setItem(VRC_WIDTHS_KEY, JSON.stringify(migrated))
  } catch {}
}

// Пользователь мог подвинуть ширину колонки (vrc_products сохранился), ни
// разу не перетащив порядок (products_col_order ещё не создан) — миграция
// выше тогда не сработает, потому что у неё нет old-order для сопоставления.
// Последняя защита: если длина сохранённого массива ширин не совпадает с
// текущим числом колонок — массив относится к другой раскладке (старой, до
// новой колонки), доверять индексам нельзя. Безопаснее стереть, чем сдвигать
// (директива тогда возьмёт width/minWidth из ALL_COLUMNS).
function dropStaleWidthsIfMismatched(order: string[]) {
  try {
    const saved = localStorage.getItem(VRC_WIDTHS_KEY)
    if (!saved) return
    const widths: number[] = JSON.parse(saved)
    if (widths.length !== order.length + VRC_CHECKBOX_OFFSET) {
      localStorage.removeItem(VRC_WIDTHS_KEY)
    }
  } catch {}
}

function loadColOrder(): string[] {
  try {
    const saved = localStorage.getItem('products_col_order')
    if (saved) {
      const arr = JSON.parse(saved) as string[]
      const allKeys = ALL_COLUMNS.map(c => c.key)
      // merge: saved + any new columns not yet in saved
      const oldRendered = arr.filter(k => allKeys.includes(k))
      const merged = [...oldRendered]
      allKeys.forEach(k => { if (!merged.includes(k)) merged.push(k) })
      if (merged.length !== oldRendered.length) {
        migrateColumnWidths(oldRendered, merged)
      }
      dropStaleWidthsIfMismatched(merged)
      return merged
    }
  } catch {}
  const defaultOrder = ALL_COLUMNS.map(c => c.key)
  dropStaleWidthsIfMismatched(defaultOrder)
  return defaultOrder
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
