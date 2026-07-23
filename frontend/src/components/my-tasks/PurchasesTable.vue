<template>
  <v-card variant="outlined">
    <v-table density="compact" hover>
      <thead>
        <tr>
          <th>Статус</th>
          <th>Название</th>
          <th>Контрагент</th>
          <th class="text-right">Сумма</th>
          <th>Срок</th>
          <th>Комментарий</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="task in purchases"
          :key="task.id"
          style="cursor:pointer"
          @click="$emit('open-purchase', task.id)"
        >
          <td>
            <div class="d-flex align-center ga-1 flex-wrap">
              <v-chip :color="statusColor(task.status)" size="x-small" variant="flat">
                {{ purchaseStatusLabel(task) }}
              </v-chip>
              <v-chip v-if="task.substatus" size="x-small" variant="outlined" color="teal">
                {{ SUBSTATUS_LABEL[task.substatus] || task.substatus }}
              </v-chip>
            </div>
          </td>
          <td class="font-weight-medium">{{ task.subject || `Закупка #${task.purchase_number || task.id}` }}</td>
          <td class="text-body-2">{{ task.contractor_name || '—' }}</td>
          <td class="text-right text-body-2">{{ formatMoney(task.contract_price || task.planned_total_price) }}</td>
          <td>
            <v-chip v-if="task.execution_term" :color="deadlineColor(task.execution_term)" size="x-small" variant="tonal">
              {{ formatDate(task.execution_term) }}
            </v-chip>
            <span v-else class="text-medium-emphasis">—</span>
          </td>
          <td class="text-body-2 text-truncate" style="max-width:200px">{{ task.task_comment || '' }}</td>
        </tr>
        <tr v-if="purchases.length === 0">
          <td colspan="6" class="text-center text-medium-emphasis pa-4">Нет задач</td>
        </tr>
      </tbody>
    </v-table>
  </v-card>
</template>

<script setup lang="ts">
/**
 * PurchasesTable — list view (v-table) for the Purchases tab in MyTasksView (D-17).
 * Pure presentation: all data comes via props, all mutations are emitted back to parent.
 * Pure presentation — no API calls, no router, no store access.
 */

export interface Purchase {
  id: number
  purchase_number?: string | null
  subject?: string | null
  status: string
  substatus?: string | null
  contractor_name?: string | null
  contract_price?: number | null
  planned_total_price?: number | null
  execution_term?: string | null
  task_comment?: string | null
  delivery_date?: string | null
  is_monthly_payment?: boolean
  unseen_changes_count?: number
  purchase_contract_type?: string | null
  subsidy_id?: number | null
  subsidy_name?: string | null
  kanban_status?: string | null
}

interface Props {
  /** Filtered list of purchases to display */
  purchases: Purchase[]
  /** Currently selected org id — reserved for future filtering */
  selectedOrgId: number | null
  /** Loading state — used by parent to show skeleton/spinner above table */
  loading: boolean
}

defineProps<Props>()

defineEmits<{
  /** User clicked a purchase row — parent navigates to /orders/:id/edit */
  (e: 'open-purchase', purchaseId: number): void
}>()

// ── Status/substatus labels ──────────────────────────────────────────────────
const STATUS_LABELS: Record<string, string> = {
  wishes: 'Желания',
  plan_schedule: 'План-график',
  work_in_progress: 'Ведётся работа',
  contracted: 'Договор',
  delivered: 'Поставлено',
  paid: 'Оплачено',
}

const FRAMEWORK_TYPES = new Set(['framework_cumulative', 'framework_with_amount'])

function purchaseStatusLabel(task: Purchase): string {
  if (task.status === 'contracted' && FRAMEWORK_TYPES.has(task.purchase_contract_type || '')) return 'Заказ'
  return STATUS_LABELS[task.status] || task.status
}

const SUBSTATUS_LABEL: Record<string, string> = {
  tz_forming: 'Формирование ТЗ',
  kp_collecting: 'Сбор КП',
  on_platform: 'На площадке',
  contractor_negotiations: 'Переговоры с подрядчиком',
  contract_signing: 'Договор на подписании',
}

// ── Color helpers ────────────────────────────────────────────────────────────
function statusColor(s: string): string {
  const map: Record<string, string> = {
    wishes: 'amber',
    plan_schedule: 'orange',
    work_in_progress: 'teal',
    contracted: 'indigo',
    delivered: 'deep-purple',
    paid: 'success',
  }
  return map[s] || 'grey'
}

function deadlineColor(d: string): string {
  const diff = (new Date(d).getTime() - Date.now()) / 86400000
  if (diff < 0) return 'error'
  if (diff <= 7) return 'warning'
  return 'success'
}

// ── Format helpers ───────────────────────────────────────────────────────────
function formatDate(d: string): string {
  if (!d) return ''
  const [y, m, day] = d.split('-')
  return `${day}.${m}.${y}`
}

function formatMoney(v?: number | null): string {
  if (!v) return '0 ₽'
  if (v >= 1_000_000) return (v / 1_000_000).toFixed(1) + ' млн ₽'
  if (v >= 1_000) return (v / 1_000).toFixed(0) + ' тыс ₽'
  return v.toLocaleString('ru-RU') + ' ₽'
}
</script>

<style scoped>
/* Ensure rows show pointer cursor for click affordance */
:deep(tbody tr) {
  cursor: pointer;
}

/* Tighten dense row height */
:deep(.v-table tbody tr > td) {
  padding-top: 6px;
  padding-bottom: 6px;
  vertical-align: middle;
}

/* Highlight rows on hover with a subtle background */
:deep(tbody tr:hover td) {
  background: rgba(var(--v-theme-primary), 0.04);
}

/* Cap the subject column width */
:deep(.v-table th:nth-child(2)),
:deep(.v-table td:nth-child(2)) {
  min-width: 200px;
  max-width: 360px;
}

/* Amount column: right-aligned */
:deep(.v-table td:nth-child(4)) {
  white-space: nowrap;
}

/* Comment column: truncate overflow */
:deep(.v-table td:last-child) {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Responsive: allow horizontal scroll on narrow screens */
:deep(.v-table__wrapper) {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

/* Ensure header row sticks during horizontal scroll */
:deep(thead th) {
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--crm-surface, #fff);
  white-space: nowrap;
}

/* No-data message centering */
:deep(tbody tr td[colspan]) {
  text-align: center;
  padding: 32px 16px;
  color: rgba(0, 0, 0, 0.45);
}

/* Status chip consistent min-width */
:deep(.v-chip--size-x-small) {
  min-width: 64px;
  justify-content: center;
}

/* Highlight rows on hover with primary tint */
:deep(tbody tr:hover) {
  background: rgba(var(--v-theme-primary), 0.03);
}

/* Money column: always right-aligned with fixed spacing */
:deep(.v-table td:nth-child(4)) {
  font-variant-numeric: tabular-nums;
  font-weight: 500;
}

/* Deadline chip sizing */
:deep(.v-table .v-chip--size-x-small) {
  min-width: 80px;
  justify-content: center;
}

/* Empty state: center message */
:deep(tbody td[colspan="6"]) {
  padding: 32px 16px !important;
  text-align: center;
  color: rgba(0, 0, 0, 0.45);
}

/* Substatus chip: teal outlined shrinks on small screens */
:deep(.v-chip[class*='teal']) {
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Contractor column: don't wrap short names */
:deep(.v-table td:nth-child(3)) {
  white-space: nowrap;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Row with unseen changes — subtle left accent */
:deep(tbody tr[data-unseen='true'] td:first-child) {
  border-left: 3px solid rgb(var(--v-theme-warning));
}
</style>
