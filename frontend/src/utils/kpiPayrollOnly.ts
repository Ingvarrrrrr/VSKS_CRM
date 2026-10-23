// kpiPayrollOnly.ts — выбор ОДНОГО числа «Только ФОТ» для KPI-карточек
// (переключатель «Всё / Только закупки / Только ФОТ», владелец, план
// payroll_view, 23.10.2026). ЕДИНСТВЕННОЕ место, которое решает «как достать
// payroll-долю из уже готовой разбивки» — не считает НИЧЕГО заново (ПРАВИЛО
// №6): входные объекты (committed_by_kind/paid_declared_by_kind/
// redistributable_by_kind/widget[stage][`${stage}_payroll`]/budget_payroll/
// planned_payroll) уже посчитаны бэкендом (app/services/payroll_visibility.py,
// app/services/dashboard_type_split.py) — здесь только читаем готовое поле.
//
// «Только закупки» (payroll_view=exclude) СЮДА не заходит вовсе — бэкенд уже
// возвращает числа без ФОТ целиком (scrub_payroll_from_dashboard_charts с
// force_hide_all=True, тот же механизм, что скрывает ФОТ от пользователя без
// права «Видеть ФОТ»), фронту достаточно передать ?payroll_view=exclude и
// показать уже пришедшие суммы как обычно.
//
// Карточка, для которой бэкенд НЕ даёт payroll-долю отдельным полем
// (Экономия по закупкам, Остаток субсидии — см. docstring
// scrub_payroll_from_dashboard_charts «НЕ скрабится»), обязана показать «нет
// данных» — вызывающий код передаёт `undefined`/`null`, функции ниже честно
// возвращают null, а не 0 (0 выглядел бы как «ФОТ точно нет», хотя мы просто
// не умеем его посчитать для этой карточки).

export interface ByKindAmounts {
  payroll?: number | null
  [k: string]: number | null | undefined
}

/** committed_by_kind / planned_not_committed_by_kind / redistributable_by_kind /
 * paid_declared_by_kind / paid_confirmed_by_kind / delivered_unpaid_declared_by_kind —
 * ВСЕГДА присутствуют в ответе /dashboard/charts независимо от ?type_split
 * (см. app/services/payroll_visibility.py::_BY_KIND_PAIRS). */
export function payrollOnlyFromByKind(byKind: ByKindAmounts | null | undefined): number | null {
  if (!byKind) return null
  const v = byKind.payroll
  return typeof v === 'number' ? v : null
}

/** widget[stage] / effectiveWidgets[stage] (работа/заказано/договоры/
 * поставлено/оплачено и т.п.) — поле `${stage}_payroll` появляется ТОЛЬКО
 * когда бэкенд считал разбивку по видам (?type_split=true либо
 * ?payroll_view=only, который форсирует её же, см. dashboard_charts.py). */
export function payrollOnlyFromStageBucket(bucket: Record<string, any> | null | undefined, stage: string): number | null {
  if (!bucket) return null
  const v = bucket[`${stage}_payroll`]
  return typeof v === 'number' ? v : null
}

/** «Бюджет (ФЭО)»/«Запланировано» по типу — budget_payroll/planned_payroll
 * прямо на строке субсидии (тоже требуют type_split/only). */
export function payrollOnlyFromRow(row: { budget_payroll?: number | null; planned_payroll?: number | null } | null | undefined, field: 'budget_payroll' | 'planned_payroll'): number | null {
  if (!row) return null
  const v = row[field]
  return typeof v === 'number' ? v : null
}

/** «Свободно» = budget_payroll − planned_payroll, та же формула, что и для
 * «целиком»/по товарам-услугам (SubsidyKpiCards.vue::splitRowsFor('free')),
 * просто для корзины payroll — не вторая формула, то же вычитание. */
export function payrollOnlyFree(row: { budget_payroll?: number | null; planned_payroll?: number | null } | null | undefined): number | null {
  const b = payrollOnlyFromRow(row, 'budget_payroll')
  const p = payrollOnlyFromRow(row, 'planned_payroll')
  if (b == null || p == null) return null
  return b - p
}
