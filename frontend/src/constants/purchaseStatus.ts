/**
 * Единый словарь статусов закупки (жизненный цикл: Желания → План закупок →
 * Ведётся работа → Договор → Заказано → Поставлено → Оплачено).
 *
 * Лейблы синхронизированы с тем, что реально видит пользователь сейчас:
 * frontend/src/views/OrdersView.vue (STATUS_LABEL) и
 * frontend/src/views/SubsidiesView.vue (PURCHASE_STATUS_LABELS).
 * Не дублировать label/color по view — импортировать отсюда.
 */

export type PurchaseStatus =
  | 'wishes' | 'plan_schedule' | 'work_in_progress'
  | 'contracted' | 'ordered' | 'delivered' | 'paid'

export interface PurchaseStatusMeta { label: string; color: string; icon: string; order: number }

export const PURCHASE_STATUS_META: Record<string, PurchaseStatusMeta> = {
  wishes:           { label: 'Желания',        color: '#6B7280', icon: 'mdi-hand-heart-outline', order: 0 },
  plan_schedule:    { label: 'План закупок',    color: '#F59E0B', icon: 'mdi-calendar-clock',     order: 1 },
  work_in_progress: { label: 'Ведётся работа', color: '#14B8A6', icon: 'mdi-progress-wrench',    order: 2 },
  contracted:       { label: 'Договор',        color: '#6366F1', icon: 'mdi-file-sign',          order: 3 },
  ordered:          { label: 'Заказано',       color: '#0EA5E9', icon: 'mdi-cart-check',         order: 4 },
  delivered:        { label: 'Поставлено',     color: '#8B5CF6', icon: 'mdi-truck-check',         order: 5 },
  paid:             { label: 'Оплачено',       color: '#22C55E', icon: 'mdi-cash-check',         order: 6 },
}

export const PURCHASE_STATUS_ORDER: string[] = Object.keys(PURCHASE_STATUS_META).sort(
  (a, b) => PURCHASE_STATUS_META[a].order - PURCHASE_STATUS_META[b].order
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
