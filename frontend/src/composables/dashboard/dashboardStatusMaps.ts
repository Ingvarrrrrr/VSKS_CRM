// Единый источник цвета/подписи статуса закупки для дашборда:
// frontend/src/constants/purchaseStatus.ts (Правило №6 — один источник истины).
// 'planned'/'in_progress' — легаси-алиасы (см. backend PLAN_STATUSES / status="planned" для
// дочерних закупок после разделения); резолвятся в тот же цвет, что канонический статус.
// Перенесено без изменений из DashboardView.vue при разбиении на модули.
import { PURCHASE_STATUS_ORDER, purchaseStatusLabel, purchaseStatusColor } from '@/constants/purchaseStatus'

export const STATUS_LABELS: Record<string, string> = {
  ...Object.fromEntries(PURCHASE_STATUS_ORDER.map(s => [s, purchaseStatusLabel(s)])),
  planned: 'Планируется',
  in_progress: purchaseStatusLabel('work_in_progress'),
}

export const STATUS_COLORS: Record<string, string> = {
  ...Object.fromEntries(PURCHASE_STATUS_ORDER.map(s => [s, purchaseStatusColor(s)])),
  planned: purchaseStatusColor('plan_schedule'),
  in_progress: purchaseStatusColor('work_in_progress'),
}
