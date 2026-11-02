/**
 * Форматирование результата сводной (pivot) — единый источник для
 * PivotBuilderView.vue (превью при конструировании) и PivotResultTable.vue
 * (превью builder'а + запуск сохранённой сводной в ReportRunView.vue).
 * ПРАВИЛО №6: формулы/подписи считаются здесь один раз, остальные места
 * только читают.
 */

export interface PivotCalcColSpec {
  type: 'share' | 'cumulative' | 'delta'
  measure?: string
  actual?: string
  plan?: string
}

export const aggOptions = [
  { value: 'sum', title: 'Сумма' },
  { value: 'avg', title: 'Среднее' },
  { value: 'count', title: 'Количество' },
  { value: 'count_distinct', title: 'Уникальных' },
  { value: 'min', title: 'Минимум' },
  { value: 'max', title: 'Максимум' },
] as const

export function aggTitle(agg: string): string {
  return aggOptions.find((a) => a.value === agg)?.title || agg
}

/** Человеческая подпись меры: "Плановая сумма (сумма)". */
export function measureLabel(fieldLabel: string, agg: string): string {
  return `${fieldLabel} (${aggTitle(agg).toLowerCase()})`
}

export function fmtNumber(v: any): string {
  if (v === null || v === undefined || v === '') return ''
  const n = Number(v)
  if (isNaN(n)) return String(v)
  return n.toLocaleString('ru-RU', { maximumFractionDigits: 2 })
}

export function fmtCalc(row: any, cc: PivotCalcColSpec): string {
  if (cc.type === 'share') {
    const v = row[`share_${cc.measure}`]
    if (v === undefined) return ''
    return (Number(v) * 100).toFixed(1) + '%'
  }
  if (cc.type === 'cumulative') return fmtNumber(row[`cumulative_${cc.measure}`])
  if (cc.type === 'delta') return fmtNumber(row[`delta_${cc.actual}_vs_${cc.plan}`])
  return ''
}

export function calcLabel(cc: PivotCalcColSpec): string {
  if (cc.type === 'share') return `% от итога: ${cc.measure}`
  if (cc.type === 'cumulative') return `Нараст.: ${cc.measure}`
  if (cc.type === 'delta') return `Δ: ${cc.actual} vs ${cc.plan}`
  return ''
}
