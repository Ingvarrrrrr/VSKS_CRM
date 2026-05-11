import { ref, reactive } from 'vue'

export interface PivotDimension { key: string; label: string }
export interface PivotMeasure { key: string; field: string; label: string; agg: 'sum' | 'avg' | 'count' | 'count_distinct' | 'min' | 'max' }
export interface PivotCalcCol { type: 'share' | 'cumulative' | 'delta'; measure?: string; actual?: string; plan?: string }
export interface PivotState {
  rows: PivotDimension[]
  cols: PivotDimension[]
  measures: PivotMeasure[]
  filters: Record<string, any>
  calc_columns: PivotCalcCol[]
  compare_subsidy_ids: number[]
}

export function usePivotConfig() {
  const state = reactive<PivotState>({
    rows: [],
    cols: [],
    measures: [],
    filters: {},
    calc_columns: [],
    compare_subsidy_ids: [],
  })
  const dirty = ref(false)

  function addRow(field: { key: string; label: string }) {
    if (state.rows.find((r) => r.key === field.key)) return
    state.rows.push({ key: field.key, label: field.label })
    dirty.value = true
  }
  function addCol(field: { key: string; label: string }) {
    if (state.cols.find((c) => c.key === field.key)) return
    state.cols.push({ key: field.key, label: field.label })
    dirty.value = true
  }
  function addMeasure(field: { key: string; label: string; agg_default?: string }, agg?: string) {
    const finalAgg = (agg || field.agg_default || 'sum') as PivotMeasure['agg']
    const mkey = `${finalAgg}_${field.key}`
    if (state.measures.find((m) => m.key === mkey)) return
    state.measures.push({ key: mkey, field: field.key, label: field.label, agg: finalAgg })
    dirty.value = true
  }
  function removeRow(idx: number) { state.rows.splice(idx, 1); dirty.value = true }
  function removeCol(idx: number) { state.cols.splice(idx, 1); dirty.value = true }
  function removeMeasure(idx: number) { state.measures.splice(idx, 1); dirty.value = true }
  function setFilter(key: string, value: any) {
    if (value === null || value === undefined || (Array.isArray(value) && !value.length)) delete state.filters[key]
    else state.filters[key] = value
    dirty.value = true
  }
  function addCalcColumn(spec: PivotCalcCol) { state.calc_columns.push(spec); dirty.value = true }
  function removeCalcColumn(idx: number) { state.calc_columns.splice(idx, 1); dirty.value = true }

  function buildQuery() {
    return {
      kind: 'pivot' as const,
      rows: state.rows.map((r) => r.key),
      cols: state.cols.map((c) => c.key),
      measures: state.measures.map((m) => ({ field: m.field, agg: m.agg })),
      filters: { ...state.filters },
      calc_columns: state.calc_columns,
    }
  }

  function loadFromConfig(config: any) {
    state.rows = (config.rows || []).map((k: string) => ({ key: k, label: k }))
    state.cols = (config.cols || []).map((k: string) => ({ key: k, label: k }))
    state.measures = (config.measures || []).map((m: any) => ({
      key: `${m.agg}_${m.field}`,
      field: m.field,
      label: m.field,
      agg: m.agg,
    }))
    state.filters = { ...(config.filters || {}) }
    state.calc_columns = config.calc_columns || []
    state.compare_subsidy_ids = config.compare_subsidy_ids || []
    dirty.value = false
  }

  function clear() {
    state.rows = []
    state.cols = []
    state.measures = []
    state.filters = {}
    state.calc_columns = []
    state.compare_subsidy_ids = []
    dirty.value = false
  }

  return {
    state,
    dirty,
    addRow, addCol, addMeasure,
    removeRow, removeCol, removeMeasure,
    setFilter,
    addCalcColumn, removeCalcColumn,
    buildQuery, loadFromConfig, clear,
  }
}
