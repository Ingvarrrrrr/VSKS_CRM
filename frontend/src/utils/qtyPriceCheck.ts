// Применение выбора пользователя к расхождению «кол-во × цена ≠ сумма» на
// клиенте — зеркало backend/app/services/qty_price_check.py:resolve_qty_price_choice
// (Правило №6: тот же смысл выбора recalc_sum/recalc_price/keep). Нужен на
// фронте отдельно, т.к. в потоке «wish / новая закупка» позиции копятся в
// localItems на клиенте ДО сохранения — сервер про них ещё не знает, значит
// выбор пользователя применяется прямо здесь, а не только на бэке (см.
// useItemsImport.ts, ветку import-mapped-nopid / import-smart-nopid).
//
// Сумма при recalc_sum считается через lineTotal() из utils/itemAmounts.ts —
// единственный источник quantity × unit_price на фронте (Правило №6), не
// повторный Math.round по месту.
import { lineTotal } from '@/utils/itemAmounts'

export type SumMismatchChoice = 'recalc_sum' | 'recalc_price' | 'keep'

export interface SumMismatchWarning {
  kind: string
  row: number
  name: string
  message: string
  file_total: number
  calc_total: number
}

export function applySumMismatchChoice(
  item: { quantity?: number | null; unit_price?: number | null; total_price?: number | null },
  choice: SumMismatchChoice | undefined,
) {
  if (!choice || choice === 'keep') return
  const qty = item.quantity
  if (choice === 'recalc_sum' && qty != null && item.unit_price != null) {
    item.total_price = lineTotal(qty, item.unit_price)
  } else if (choice === 'recalc_price' && qty && item.total_price != null) {
    item.unit_price = Math.round((item.total_price / qty) * 100) / 100
  }
}
