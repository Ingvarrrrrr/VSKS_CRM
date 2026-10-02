// ИСПРАВЛЕНО 02.10.2026 (план «Деньги субсидии», шаг 3 — база экономии
// переведена на плановую позицию FeoPlannedItem, см. backend/app/services/
// purchase_economy.py docstring): один текст подписи «экономия не посчитана
// для N позиций: ...» — переиспользуется SubsidyMoneyCards.vue,
// EconomyByMethodTable.vue и PurchaseFinanceSection.vue (ПРАВИЛО №6, не
// плодить копии форматирования). Показывает только ненулевые причины.
export interface EconomyUnmeasuredByReason {
  unlinked: number
  no_plan_price: number
  monthly: number
  no_fact: number
}

const REASON_LABELS: Record<keyof EconomyUnmeasuredByReason, string> = {
  unlinked: 'не привязаны к плановой позиции',
  no_plan_price: 'у плановой позиции нет количества',
  monthly: 'ежемесячные',
  no_fact: 'нет суммы договора',
}

/** total — суммарное число неизмеренных позиций (economy_no_planned_price_items/
 * no_planned_price_items); by_reason — разбивка (может быть null/undefined,
 * если вызывающий код ещё не передал её — тогда показываем только total). */
export function formatEconomyUnmeasuredText(
  total: number | null | undefined,
  byReason?: EconomyUnmeasuredByReason | null,
): string {
  const n = total ?? 0
  if (n <= 0) return ''
  if (!byReason) return `экономия не посчитана для ${n} позиций`
  const parts = (Object.keys(REASON_LABELS) as (keyof EconomyUnmeasuredByReason)[])
    .filter((key) => (byReason[key] || 0) > 0)
    .map((key) => `${REASON_LABELS[key]} — ${byReason[key]}`)
  if (!parts.length) return `экономия не посчитана для ${n} позиций`
  return `экономия не посчитана для ${n} позиций: ${parts.join(', ')}`
}
