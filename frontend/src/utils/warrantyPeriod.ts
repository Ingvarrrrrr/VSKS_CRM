// Срок гарантии договора: число + единица (дни/месяцы/годы) — жалоба владельца
// (п.10, 2026-09-17): «Срок гарантии может быть в днях, в месяцах, в годах».
// Склонение здесь — ТОЛЬКО превью для формы (что уйдёт в документ, склоняет
// backend/app/services/documents/contract_terms.py::warranty_period_text —
// единственный источник для самого документа, ПРАВИЛО №6). Эта функция и её
// backend-двойник обязаны давать одинаковый текст на одинаковых входных данных.

export type WarrantyUnit = 'days' | 'months' | 'years'

export const WARRANTY_UNIT_OPTIONS: Array<{ title: string; value: WarrantyUnit }> = [
  { title: 'дней', value: 'days' },
  { title: 'месяцев', value: 'months' },
  { title: 'лет', value: 'years' },
]

const UNIT_WORDS: Record<WarrantyUnit, [string, string, string]> = {
  days: ['день', 'дня', 'дней'],
  months: ['месяц', 'месяца', 'месяцев'],
  years: ['год', 'года', 'лет'],
}

function ruPlural(n: number, [one, few, many]: [string, string, string]): string {
  const nAbs = Math.abs(Math.trunc(n))
  const lastTwo = nAbs % 100
  const lastOne = nAbs % 10
  if (lastTwo >= 11 && lastTwo <= 14) return many
  if (lastOne === 1) return one
  if (lastOne >= 2 && lastOne <= 4) return few
  return many
}

/** «1 год» / «2 года» / «5 лет» / «12 месяцев» / «30 дней». unit=null/undefined → 'days' (старые закупки). */
export function warrantyPeriodText(value: number | null | undefined, unit: string | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return ''
  const key: WarrantyUnit = (unit === 'months' || unit === 'years') ? unit : 'days'
  return `${value} ${ruPlural(value, UNIT_WORDS[key])}`
}
