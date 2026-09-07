/**
 * Единый словарь статусов закупки (жизненный цикл: Желания → План закупок →
 * Ведётся работа → Договор → Заказано → Поставлено → Оплачено).
 *
 * ПРАВИЛО №6 (2026-09-07): подписи (label) статусов/подстатусов/способов
 * закупки/оснований/типов договора генерируются из бэкенда
 * (backend/app/services/dictionaries.py, GET /api/dictionaries/purchase) в
 * frontend/src/data/dictionaries.json скриптом
 * backend/scripts/export_dictionaries.py — НЕ редактировать label здесь и
 * НЕ заводить второй словарь в другом файле/view; при расхождении менять
 * бэкенд-источник и перегенерировать JSON (`python
 * backend/scripts/export_dictionaries.py`), см. `--check` в CI.
 *
 * Цвета/иконки статусов на бэкенде не заводятся (это чисто фронтовая
 * вёрстка) — они остаются здесь, отдельной картой поверх backend-label.
 */
import dictionaries from '@/data/dictionaries.json'

export type PurchaseStatus =
  | 'wishes' | 'plan_schedule' | 'work_in_progress'
  | 'contracted' | 'ordered' | 'delivered' | 'paid'

export interface PurchaseStatusMeta { label: string; color: string; icon: string; order: number }

const STATUS_VISUAL: Record<string, { color: string; icon: string }> = {
  wishes:           { color: '#6B7280', icon: 'mdi-hand-heart-outline' },
  plan_schedule:    { color: '#F59E0B', icon: 'mdi-calendar-clock' },
  work_in_progress: { color: '#14B8A6', icon: 'mdi-progress-wrench' },
  contracted:       { color: '#6366F1', icon: 'mdi-file-sign' },
  ordered:          { color: '#0EA5E9', icon: 'mdi-cart-check' },
  delivered:        { color: '#8B5CF6', icon: 'mdi-truck-check' },
  paid:             { color: '#22C55E', icon: 'mdi-cash-check' },
}

export const PURCHASE_STATUS_META: Record<string, PurchaseStatusMeta> = Object.fromEntries(
  (dictionaries.statuses as { key: string; label: string }[]).map((s, order) => [
    s.key,
    {
      label: s.label,
      color: STATUS_VISUAL[s.key]?.color ?? '#94A3B8',
      icon: STATUS_VISUAL[s.key]?.icon ?? 'mdi-help-circle-outline',
      order,
    },
  ])
)

export const PURCHASE_STATUS_ORDER: string[] = Object.keys(PURCHASE_STATUS_META).sort(
  (a, b) => (PURCHASE_STATUS_META[a]?.order ?? 99) - (PURCHASE_STATUS_META[b]?.order ?? 99)
)

export function purchaseStatusLabel(s?: string | null): string {
  if (!s) return ''
  return PURCHASE_STATUS_META[s]?.label ?? s
}

export function purchaseStatusIcon(s?: string | null): string {
  if (!s) return 'mdi-help-circle-outline'
  return PURCHASE_STATUS_META[s]?.icon ?? 'mdi-help-circle-outline'
}

export function purchaseStatusColor(s?: string | null): string {
  if (!s) return '#94A3B8'
  return PURCHASE_STATUS_META[s]?.color ?? '#94A3B8'
}

export function purchaseStatusOrder(s?: string | null): number {
  if (!s) return 99
  return PURCHASE_STATUS_META[s]?.order ?? 99
}

// ── Подстатус закупки (tz_forming/kp_collecting/on_platform/...) ────────────
const SUBSTATUS_LABELS: Record<string, string> = Object.fromEntries(
  (dictionaries.substatuses as { key: string; label: string }[]).map(s => [s.key, s.label])
)

export function purchaseSubstatusLabel(s?: string | null): string {
  if (!s) return ''
  return SUBSTATUS_LABELS[s] ?? s
}

// ── Способ закупки / основание / тип договора ───────────────────────────────
const PURCHASE_METHOD_LABELS: Record<string, string> = Object.fromEntries(
  (dictionaries.purchase_methods as { key: string; label: string }[]).map(s => [s.key, s.label])
)
const PURCHASE_BASIS_LABELS: Record<string, string> = Object.fromEntries(
  (dictionaries.purchase_bases as { key: string; label: string }[]).map(s => [s.key, s.label])
)
const CONTRACT_TYPE_LABELS: Record<string, string> = Object.fromEntries(
  (dictionaries.contract_types as { key: string; label: string }[]).map(s => [s.key, s.label])
)

export function purchaseMethodLabel(m?: string | null): string {
  if (!m) return ''
  return PURCHASE_METHOD_LABELS[m] ?? m
}

export function purchaseBasisLabel(b?: string | null): string {
  if (!b) return ''
  return PURCHASE_BASIS_LABELS[b] ?? b
}

export function contractTypeLabel(t?: string | null): string {
  if (!t) return ''
  return CONTRACT_TYPE_LABELS[t] ?? t
}
