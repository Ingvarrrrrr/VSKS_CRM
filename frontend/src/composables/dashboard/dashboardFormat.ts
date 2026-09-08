// Чистые форматтеры/хелперы дашборда без загрузки данных.
// Перенесено без изменений из DashboardView.vue при разбиении на модули.
import { toAmount } from '@/types/purchaseAmounts'
import { STATUS_LABELS, STATUS_COLORS } from './dashboardStatusMaps'

export function pct(part: number, total: number): number {
  if (!total) return 0
  return Math.round((part / total) * 100)
}

export function progressColor(p: number): string {
  if (p >= 90) return 'error'
  if (p >= 70) return 'warning'
  return 'primary'
}

export function formatCurrency(v: number): string {
  return (v || 0).toLocaleString('ru-RU', { maximumFractionDigits: 0 }) + ' ₽'
}

export function formatCurrencyShort(v: number): string {
  if (!v) return '0 ₽'
  if (Math.abs(v) >= 1_000_000_000) return (v / 1_000_000_000).toFixed(1) + ' млрд ₽'
  if (Math.abs(v) >= 1_000_000) return (v / 1_000_000).toFixed(1) + ' млн ₽'
  if (Math.abs(v) >= 1_000) return (v / 1_000).toFixed(0) + ' тыс ₽'
  return v.toLocaleString('ru-RU') + ' ₽'
}

export function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n) + '…' : s
}

// ПРАВИЛО №6 (2026-09-05/06): «сумма закупки» больше не считается на фронте —
// единый источник backend/app/services/purchase_amounts.py (см. amounts.effective,
// bulk-загружено на GET /api/purchases/, откуда приходит allPurchases). 0-фолбэк
// для закупок, где вся цепочка формулы пуста, — тот же дефолт, что был у
// pickPositive() раньше (возвращаемое число используется напрямую в суммах/
// формате без null-проверок ниже по коду дашборда).
// QA (2026-09-06): amounts.effective приходит с бэкенда JSON-строкой (Decimal),
// не числом — toAmount() обязателен, иначе суммирование в reduce-ах конкатенирует
// строки вместо сложения (0 + "10000.00" = "010000.00") — источник NaN в виджетах
// и drill-диалоге.
export function purchaseEffectivePrice(p: any): number {
  return toAmount(p.amounts?.effective) ?? 0
}

export function statusLabel(s: string): string {
  return STATUS_LABELS[s] || s
}

// Раньше statusColor()/statusColorHex() дублировали свою урезанную карту (без wishes/plan_schedule/
// ordered — те молча падали на серый), теперь оба берут цвет из общего STATUS_COLORS.
export function statusColor(s: string): string {
  return STATUS_COLORS[s] || '#94A3B8'
}

export function statusColorHex(s: string): string {
  return STATUS_COLORS[s] || '#94A3B8'
}
