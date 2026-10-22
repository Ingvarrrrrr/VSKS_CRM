// Форматирование значений ленты истории ФЭО (FeoItemHistory.vue/
// FeoImportRunsPanel.vue) — задача владельца 22.10.2026: денежные поля
// показывались сырым Decimal-текстом с бэкенда («1710.0000000000002»/
// «1710.00»), а не «1 710,00 ₽», как везде в дереве ФЭО. ЕДИНАЯ функция
// (ПРАВИЛО №6 — один показатель, один источник форматирования), читающая ТУ
// ЖЕ formatCurrency, что и дерево/карточки (composables/subsidies/format.ts) —
// второй копии форматирования денег здесь не заводим.
//
// old_value/new_value приходят с бэкенда уже СТРОКОЙ (app/services/
// feo_history*.py сериализует Decimal через str()) — эта функция ТОЛЬКО
// форматирует готовое значение для отображения, саму историю не пересчитывает.
import { formatCurrency } from '@/composables/subsidies/format'

// Денежные поля — те же суммы, что formatCurrency показывает везде в дереве
// ФЭО (budget/плановая сумма/цена за единицу/ежемесячный платёж). Список
// синхронизирован с FEO_HISTORY_FIELD_LABELS (feoHistoryFieldLabels.ts) —
// при добавлении нового денежного поля туда добавить и сюда.
const MONEY_FIELDS = new Set([
  'amount', 'unit_price', 'budget', 'feo_amount', 'feo_unit_price',
  'manual_plan_amount', 'planned_amount', 'monthly_amount',
])

// Количественные поля — число, без «₽», до 4 знаков после запятой, без
// хвостовых нулей (0.3330000000000001 → 0.333, 2.0 → 2).
const QUANTITY_FIELDS = new Set([
  'quantity', 'feo_quantity', 'planned_quantity', 'months_count',
])

function trimTrailingZeros(n: number): string {
  // toFixed(4) гарантирует, что плавающая точка (0.3330000000000001) не
  // просочится дальше 4 знаков, parseFloat убирает хвостовые нули/точку.
  return String(parseFloat(n.toFixed(4)))
}

export function formatFeoHistoryValue(field: string, raw: string | null | undefined): string {
  if (raw == null || raw === '') return '—'
  if (MONEY_FIELDS.has(field)) {
    const n = Number(raw)
    return Number.isFinite(n) ? formatCurrency(n) : raw
  }
  if (QUANTITY_FIELDS.has(field)) {
    const n = Number(raw)
    return Number.isFinite(n) ? trimTrailingZeros(n) : raw
  }
  return raw
}
