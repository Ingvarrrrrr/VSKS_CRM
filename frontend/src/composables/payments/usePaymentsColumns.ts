// usePaymentsColumns.ts — конфигурация колонок таблицы (useColumnConfig),
// локальная сортировка/фильтры ColumnHeaderMenu, master-список raw-колонок.
// Дословный перенос из PaymentRegistryView.vue.
import { computed, ref, watch } from 'vue'
import { apiFetch } from '@/api'
import { useColumnConfig, type ColumnDef } from '@/composables/useColumnConfig'
import { SCROLLERHASH_MASTER_KEYS } from '@/constants/scrollerhash_columns'
import { coreColumnDefs } from './paymentsTypes'

export function usePaymentsColumns(options: { importId: { value: number | null } }) {
  const { importId } = options

  const showColumnPicker = ref(false)
  const rawColumns = ref<{ key: string; count: number }[]>([])
  const masterFilter = ref('')
  const masterListLength = SCROLLERHASH_MASTER_KEYS.length

  const filteredMaster = computed(() => {
    const q = masterFilter.value.trim().toLowerCase()
    return q
      ? SCROLLERHASH_MASTER_KEYS.filter(k => k.toLowerCase().includes(q))
      : SCROLLERHASH_MASTER_KEYS
  })

  async function loadRawColumns() {
    try {
      const importIdFilter = importId.value
      const url = importIdFilter
        ? `/payments/registry/raw-columns?import_id=${importIdFilter}`
        : '/payments/registry/raw-columns'
      rawColumns.value = await apiFetch<{ key: string; count: number }[]>(url)
    } catch {
      rawColumns.value = []
    }
  }

  watch(showColumnPicker, (open) => {
    if (open) loadRawColumns()
  })

  // allColumnsRef: core + file (raw_* from API) + all (master list), merged reactively
  const allColumnsRef = computed<ColumnDef[]>(() => {
    const fileColumns: ColumnDef[] = rawColumns.value.map(rc => ({
      key: `raw_${rc.key}`,
      title: rc.key,
      group: 'file',
      width: 160,
      sortable: false,
    }))
    const allMasterColumns: ColumnDef[] = SCROLLERHASH_MASTER_KEYS.map(k => ({
      key: `raw_${k}`,
      title: k,
      group: 'all',
      width: 160,
      sortable: false,
    }))
    // Deduplicate: file columns override all-master entries with same key
    const fileKeys = new Set(fileColumns.map(c => c.key))
    const dedupedMaster = allMasterColumns.filter(c => !fileKeys.has(c.key))
    return [...coreColumnDefs, ...fileColumns, ...dedupedMaster]
  })

  const {
    state: colConfigState,
    visibleHeaders: visibleColumnHeaders,
    toggleVisible,
    setPosition,
    setWidth: setColWidth,
    reset: resetColumns,
    migrateFrom,
    setFilter,
    clearAllFilters,
    activeFilterCount,
  } = useColumnConfig('payment_registry', allColumnsRef)

  const activeHeaders = computed(() =>
    visibleColumnHeaders.value.map(col => {
      // raw_* колонки — данные из raw_json
      if (col.key.startsWith('raw_')) {
        const rawKey = col.key.slice(4)
        const w = colConfigState.value.widths[col.key] ?? col.width ?? 160
        return {
          title: col.title,
          key: col.key,
          value: (item: any) => item.raw_json?.[rawKey] ?? '—',
          sortable: false,
          width: w ? `${w}px` : undefined,
        }
      }
      const w = colConfigState.value.widths[col.key] ?? col.width
      return {
        title: col.title,
        key: col.key,
        sortable: col.sortable,
        width: w ? `${w}px` : undefined,
      }
    })
  )

  // _rownum — всегда первая колонка, не зависит от useColumnConfig состояния
  const tableHeaders = computed(() => [
    { title: '№ п/п', key: '_rownum', width: 60, sortable: false },
    ...activeHeaders.value,
  ])

  // ── ColumnHeaderMenu helpers ─────────────────────────────────────────────
  const localSort = ref<{ key: string; order: 'asc' | 'desc' } | null>(null)
  function getSortBy(k: string): 'asc' | 'desc' | null {
    return localSort.value?.key === k ? localSort.value.order : null
  }
  function applySort(k: string, dir: 'asc' | 'desc' | null) {
    localSort.value = dir ? { key: k, order: dir } : null
  }

  function uniqValues(rows: any[], key: string): (string | number | null)[] {
    const set = new Set<any>()
    rows.forEach(r => set.add(r?.[key] ?? null))
    return [...set].sort((a, b) => String(a ?? '').localeCompare(String(b ?? '')))
  }

  function matchesColumnFilters(row: any): boolean {
    const filters = colConfigState.value.filters
    for (const [k, f] of Object.entries(filters)) {
      // matched — derived from matched_contract_id
      let v: any
      if (k === 'matched') {
        v = Boolean(row?.matched_contract_id)
      } else if (k.startsWith('raw_')) {
        v = row?.raw_json?.[k.slice(4)] ?? null
      } else {
        v = row?.[k] ?? null
      }
      if (f.type === 'text') {
        if (!f.q) continue
        if (!String(v ?? '').toLowerCase().includes(f.q.toLowerCase())) return false
      } else if (f.type === 'enum') {
        if (!f.values || f.values.length === 0) continue
        if (!f.values.includes(v)) return false
      } else if (f.type === 'number') {
        const n = typeof v === 'number' ? v : parseFloat(v)
        if (f.min != null && !(n >= f.min)) return false
        if (f.max != null && !(n <= f.max)) return false
      } else if (f.type === 'date') {
        if (!v) { if (f.from || f.to) return false; continue }
        const d = String(v).slice(0, 10)
        if (f.from && d < f.from) return false
        if (f.to && d > f.to) return false
      } else if (f.type === 'boolean') {
        if (f.value == null) continue
        if (Boolean(v) !== f.value) return false
      }
    }
    return true
  }

  return {
    coreColumnDefs,
    showColumnPicker,
    rawColumns,
    masterFilter,
    masterListLength,
    filteredMaster,
    loadRawColumns,
    allColumnsRef,
    colConfigState,
    visibleColumnHeaders,
    toggleVisible,
    setPosition,
    setColWidth,
    resetColumns,
    migrateFrom,
    setFilter,
    clearAllFilters,
    activeFilterCount,
    tableHeaders,
    localSort,
    getSortBy,
    applySort,
    uniqValues,
    matchesColumnFilters,
  }
}
