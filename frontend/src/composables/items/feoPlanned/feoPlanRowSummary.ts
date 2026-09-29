// feoPlanRowSummary — единственное место, собирающее подписи «план · выбрано ·
// остаток · не хватает N» плановой позиции (FeoPlanResidualSummary.vue) из уже
// готовых чисел consumed/residual/shortfall (Правило №6, второй расчёт текста
// не заводим). Вынесено из useFeoPlannedRows.ts::rowDisplayProps (владелец,
// 30.09.2026: «в подходящих не видно, сколько запланировано и сколько
// выбрано») — та же формула используется ТЕПЕРЬ и FeoPlannedMatchSuggestions.vue
// (карточка кандидата подсказки), не только FeoPlannedItemRow.vue (строка списка).
//
// consumed/residual/shortfall — уже посчитанные вызывающим кодом (у
// useFeoPlannedRows.ts они учитывают pendingByPlannedItem/«уже выбрано в этой
// форме», у FeoPlannedMatchSuggestions.vue — нет такого контекста, там просто
// row.consumed/row.residual) — эта функция сама числа не считает, только
// форматирует их в готовый набор подписей.
import { formatPlanResidual, type PlanResidualDisplay } from '@/utils/numberFormat'
import { formatMoney } from '@/utils/formatMoney'
import type { FeoPlanPosition } from '@/composables/useFeoPlannedResiduals'

export interface FeoPlanRowSummaryDisplay {
  qtyLabel: string
  plannedLabel: string
  consumedLabel: string
  residualDisplay: PlanResidualDisplay
  shortfallLabel: string | null
}

export function feoPlanRowQtyLabel(row: Pick<FeoPlanPosition, 'planned_quantity' | 'unit'>): string {
  const qty = row.planned_quantity != null ? row.planned_quantity.toLocaleString('ru-RU') : '—'
  return `${qty} ${row.unit || ''}`.trim()
}

/**
 * @param row плановая позиция (нужны planned_quantity/unit/planned_amount)
 * @param consumed уже посчитанное «выбрано» (₽)
 * @param residual уже посчитанный остаток (₽) — тот же знак, что и
 *   FeoPlanPosition.residual (может быть отрицательным — превышение)
 * @param shortfall остаток МИНУС сумма новой позиции (тот же знак, что и
 *   useFeoPlannedRows.ts::shortfall) — null, если сумма новой позиции неизвестна
 *   (тогда «не хватает» не показываем вовсе, а не считаем нулём).
 */
export function feoPlanRowSummary(
  row: Pick<FeoPlanPosition, 'planned_quantity' | 'unit' | 'planned_amount'>,
  consumed: number,
  residual: number,
  shortfall: number | null,
): FeoPlanRowSummaryDisplay {
  return {
    qtyLabel: feoPlanRowQtyLabel(row),
    plannedLabel: formatMoney(row.planned_amount),
    consumedLabel: formatMoney(consumed),
    residualDisplay: formatPlanResidual(residual),
    shortfallLabel: shortfall != null && shortfall < 0 ? formatMoney(Math.abs(shortfall)) : null,
  }
}
