// useContractsColumns.ts — конфигурация колонок таблицы (useColumnConfig),
// локальная сортировка/фильтры ColumnHeaderMenu. Дословный перенос из
// ContractsView.vue.
import { computed, ref } from 'vue'
import { useColumnConfig, type ColumnDef } from '@/composables/useColumnConfig'

export function useContractsColumns(isAdmin: boolean) {
  const allColumns: ColumnDef[] = [
    // core — видимые по умолчанию
    // (_rownum добавляется отдельно через tableHeaders computed — всегда первая колонка,
    //  не зависит от useColumnConfig localStorage state)
    { title: '', key: 'data-table-expand', width: 40, sortable: false, group: 'core' },
    // Phase 26-MMM: actions — обычная колонка через useColumnConfig (двигается/скрывается).
    // Раньше была hardcoded в tableHeaders.computed → нельзя было переместить.
    ...(isAdmin ? [{ title: 'Действия', key: 'actions', width: 80, sortable: false, group: 'core' as const }] : []),
    { title: '№ документа', key: 'number', group: 'core' },
    { title: 'Дата', key: 'date', width: 110, group: 'core' },
    { title: 'Тип', key: 'contract_type', width: 170, group: 'core' },
    { title: 'Способ', key: 'purchase_method', width: 130, group: 'core' },
    { title: 'Контрагент', key: 'contractor_name', width: 220, group: 'core' },
    { title: 'Субсидия', key: 'subsidy_name', group: 'core' },
    { title: 'Предельная сумма', key: 'max_amount', align: 'end', width: 140, group: 'core' },
    { title: 'Заказано', key: 'total_ordered', align: 'end', width: 120, group: 'core' },
    { title: 'Поставлено', key: 'total_delivered', align: 'end', width: 120, group: 'core' },
    { title: 'Оплачено', key: 'total_paid', align: 'end', width: 120, group: 'core' },
    { title: 'Ост. (заказ)', key: 'remaining_ordered', align: 'end', width: 130, group: 'core' },
    { title: 'Не поставлено', key: 'remaining_delivered', align: 'end', width: 140, group: 'core' },
    { title: 'Не оплачено', key: 'remaining_paid', align: 'end', width: 130, group: 'core' },
    { title: 'Предмет договора', key: 'subject', group: 'core' },
    { title: 'Тип позиции', key: 'item_type', width: 90, group: 'core' },
    { title: 'Срок', key: 'end_date', width: 110, group: 'core' },
    // all — дополнительные поля из ContractOut / Contract модели
    { title: 'Дата начала', key: 'start_date', width: 130, group: 'all' },
    { title: 'Статус', key: 'status', width: 120, group: 'all' },
    { title: 'Примечания', key: 'notes', group: 'all' },
    { title: 'ИНН контрагента', key: 'contractor_inn', width: 160, group: 'all' },
    { title: 'ID контрагента', key: 'contractor_id', width: 140, group: 'all' },
    { title: 'ID субсидии', key: 'subsidy_id', width: 120, group: 'all' },
    { title: 'Плановый ежемесячный', key: 'planned_monthly', width: 190, align: 'end', group: 'all' },
    { title: 'Всего оплат', key: 'total_payment', width: 140, align: 'end', group: 'all' },
    { title: 'Остаток (legacy)', key: 'remaining', width: 150, align: 'end', group: 'all' },
    { title: 'Доп. субсидии', key: 'extra_subsidies', width: 160, group: 'all' },
  ]

  const groups = [
    { key: 'core', label: 'Основные' },
    { key: 'all', label: 'Все возможные' },
  ]

  const {
    state: colState, visibleHeaders, toggleVisible, setPosition, setWidth, reset: resetColumns,
    setFilter: cfgSetFilter, clearAllFilters: cfgClearAllFilters, activeFilterCount: cfgActiveFilterCount,
  } = useColumnConfig('contracts', allColumns)

  // _rownum — всегда первая колонка, не зависит от useColumnConfig состояния
  const tableHeaders = computed(() => {
    // Phase 26-MMM: actions теперь часть allColumns → проходит через useColumnConfig.
    // Здесь только _rownum (sequential row #) — спец-колонка, не настраивается.
    return [
      { title: '№ п/п', key: '_rownum', width: 60, sortable: false },
      ...visibleHeaders.value,
    ]
  })
  const showColumnPicker = ref(false)

  // ── Column header filters & sort ──────────────────────────────────────────
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
    const filters = colState.value.filters
    for (const [k, f] of Object.entries(filters)) {
      const v = row?.[k] ?? null
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
    allColumns, groups,
    colState, toggleVisible, setPosition, setWidth, resetColumns, cfgSetFilter, cfgClearAllFilters, cfgActiveFilterCount,
    tableHeaders, showColumnPicker,
    localSort, getSortBy, applySort, uniqValues, matchesColumnFilters,
  }
}
