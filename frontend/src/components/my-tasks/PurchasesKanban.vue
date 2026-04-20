<template>
  <div>
    <!-- Subsidy filter -->
    <div v-if="subsidyItems.length > 2" class="d-flex align-center mb-3 ga-2">
      <v-select
        v-model="kanbanSubsidyFilter"
        :items="subsidyItems"
        item-title="title"
        item-value="value"
        density="compact"
        variant="outlined"
        hide-details
        style="max-width:280px"
        prepend-inner-icon="mdi-filter-outline"
        label="Субсидия"
        clearable
      />
    </div>

    <!-- Kanban board -->
    <div class="kanban-board">
      <div
        v-for="col in visibleColumns"
        :key="col.status"
        class="kanban-column"
        @dragover.prevent
        @drop="onDrop($event, col.status)"
      >
        <div class="kanban-column-header" :style="{ borderTopColor: col.color }">
          <span class="kanban-column-title">{{ col.label }}</span>
          <v-chip size="x-small" :color="col.color" variant="tonal">{{ tasksByStatus(col.status).length }}</v-chip>
        </div>
        <div class="kanban-column-body">
          <div
            v-for="task in tasksByStatus(col.status)"
            :key="task.id"
            class="kanban-card"
            draggable="true"
            @dragstart="onDragStart($event, task)"
            @click="$emit('open-purchase', task.id)"
          >
            <div class="kanban-card-header">
              <span class="kanban-card-title">{{ task.subject || `Закупка #${task.purchase_number || task.id}` }}</span>
            </div>
            <div v-if="task.contractor_name" class="kanban-card-meta">
              <v-icon icon="mdi-domain" size="12" class="mr-1" />{{ task.contractor_name }}
            </div>
            <div v-if="task.substatus" class="kanban-card-meta">
              <v-chip size="x-small" variant="outlined" color="teal">
                {{ SUBSTATUS_LABEL[task.substatus] || task.substatus }}
              </v-chip>
            </div>
            <div class="kanban-card-footer">
              <span class="kanban-card-amount">{{ formatMoney(task.contract_price || task.planned_total_price) }}</span>
              <v-chip
                v-if="task.execution_term"
                :color="deadlineColor(task.execution_term)"
                size="x-small"
                variant="tonal"
              >{{ formatDate(task.execution_term) }}</v-chip>
              <v-icon v-if="task.is_monthly_payment" size="14" color="blue" title="Ежемесячный платёж" class="ml-1">mdi-calendar-sync</v-icon>
            </div>
            <!-- Missing fields indicators -->
            <div v-if="!task.contractor_name || !task.execution_term || !(task.contract_price || task.planned_total_price)" class="d-flex flex-wrap ga-1 mt-1">
              <v-chip v-if="!task.contractor_name" size="x-small" color="error" variant="tonal" prepend-icon="mdi-domain-off" title="Не выбран контрагент">Контрагент</v-chip>
              <v-chip v-if="!task.execution_term" size="x-small" color="warning" variant="tonal" prepend-icon="mdi-calendar-alert" title="Не указан срок исполнения">Срок</v-chip>
              <v-chip v-if="!(task.contract_price || task.planned_total_price)" size="x-small" color="warning" variant="tonal" prepend-icon="mdi-currency-rub" title="Не указана сумма">Сумма</v-chip>
            </div>
            <!-- Unseen changes -->
            <div v-if="task.unseen_changes_count" class="d-flex align-center mt-1">
              <v-chip size="x-small" variant="flat" color="warning" :title="`${task.unseen_changes_count} новых изменений`">
                <v-icon icon="mdi-bell-ring" size="10" class="mr-1" />{{ task.unseen_changes_count }}
              </v-chip>
            </div>
            <div v-if="task.delivery_date && task.status === 'contracted'" class="kanban-card-meta">
              <v-icon icon="mdi-truck-delivery" size="12" class="mr-1" />Доставка: {{ formatDate(task.delivery_date) }}
            </div>
            <div v-if="task.task_comment" class="kanban-card-comment">
              <v-icon icon="mdi-comment-text-outline" size="12" class="mr-1" />
              <span>{{ task.task_comment.length > 100 ? task.task_comment.slice(0, 100) + '…' : task.task_comment }}</span>
            </div>
          </div>
          <div v-if="tasksByStatus(col.status).length === 0" class="kanban-empty">
            Нет задач
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * PurchasesKanban — kanban column view for the Purchases tab in MyTasksView (D-17).
 * Pure presentation: all data via props, mutations emitted back to parent.
 * Drag-drop updates kanban_status via 'update-kanban-status' emit.
 * Pure presentation — no API calls, no router, no store access.
 */
import { ref, computed } from 'vue'

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
  delivery_date?: string | null
  task_comment?: string | null
  is_monthly_payment?: boolean
  unseen_changes_count?: number
  purchase_contract_type?: string | null
  subsidy_id?: number | null
  subsidy_name?: string | null
  kanban_status?: string | null
}

interface KanbanColumn {
  status: string
  label: string
  color: string
}

interface Props {
  /** Active (non-paid) purchases for the kanban board */
  purchases: Purchase[]
  /** Archive (paid) purchases — shown when showArchive is true */
  archivePurchases: Purchase[]
  /** Currently selected org id — reserved for future filtering */
  selectedOrgId: number | null
  /** Whether to show the paid/archive column */
  showArchive: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  /** User clicked a purchase card — parent navigates to /orders/:id/edit */
  (e: 'open-purchase', purchaseId: number): void
  /** User dragged a card to a new column — parent should PATCH kanban-status */
  (e: 'update-kanban-status', purchaseId: number, newStatus: string): void
}>()

// ── Kanban columns definition ────────────────────────────────────────────────
const COLUMNS: KanbanColumn[] = [
  { status: 'wishes', label: 'Желания сотрудников', color: '#F59E0B' },
  { status: 'plan_schedule', label: 'План-график', color: '#FB923C' },
  { status: 'confirmed', label: 'Подтверждено', color: '#3B82F6' },
  { status: 'work_in_progress', label: 'Ведётся работа', color: '#14B8A6' },
  { status: 'contracted', label: 'Договор', color: '#6366F1' },
  { status: 'delivered', label: 'Поставлено', color: '#8B5CF6' },
]
const ARCHIVE_COLUMN: KanbanColumn = { status: 'paid', label: 'Оплачено (архив)', color: '#22C55E' }

const visibleColumns = computed<KanbanColumn[]>(() =>
  props.showArchive ? [...COLUMNS, ARCHIVE_COLUMN] : COLUMNS
)

// ── Substatus labels ─────────────────────────────────────────────────────────
const SUBSTATUS_LABEL: Record<string, string> = {
  tz_forming: 'Формируется ТЗ',
  kp_collecting: 'Сбор КП',
  on_platform: 'На площадке',
}

// ── Subsidy filter (local UI state) ─────────────────────────────────────────
const kanbanSubsidyFilter = ref<number | null>(null)

const subsidyItems = computed(() => {
  const all = [...props.purchases, ...props.archivePurchases]
  const seen = new Map<number, string>()
  for (const t of all) {
    if (t.subsidy_id && !seen.has(t.subsidy_id)) {
      seen.set(t.subsidy_id, t.subsidy_name || `Субсидия #${t.subsidy_id}`)
    }
  }
  return [
    { title: 'Все субсидии', value: null },
    ...Array.from(seen.entries()).map(([v, title]) => ({ title, value: v })),
  ]
})

// ── Tasks by status (with subsidy filter) ───────────────────────────────────
function tasksByStatus(status: string): Purchase[] {
  const base = status === 'paid'
    ? props.archivePurchases
    : props.purchases.filter(t => t.status === status)
  if (kanbanSubsidyFilter.value === null) return base
  return base.filter(t => t.subsidy_id === kanbanSubsidyFilter.value)
}

// ── Drag & Drop ──────────────────────────────────────────────────────────────
let draggedTask: Purchase | null = null

function onDragStart(e: DragEvent, task: Purchase) {
  draggedTask = task
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', String(task.id))
  }
}

function onDrop(e: DragEvent, targetStatus: string) {
  e.preventDefault()
  if (!draggedTask || draggedTask.status === targetStatus) return
  const task = draggedTask
  draggedTask = null
  emit('update-kanban-status', task.id, targetStatus)
}

// ── Utility helpers ──────────────────────────────────────────────────────────
function deadlineColor(d: string): string {
  const diff = (new Date(d).getTime() - Date.now()) / 86400000
  if (diff < 0) return 'error'
  if (diff <= 7) return 'warning'
  return 'success'
}

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
.kanban-board {
  display: flex;
  gap: 12px;
  overflow-x: auto;
  padding-bottom: 12px;
  min-height: 400px;
}

.kanban-column {
  min-width: 240px;
  max-width: 280px;
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--crm-surface-alt);
  border-radius: 12px;
  border: 1px solid var(--crm-border);
}

.kanban-column-header {
  padding: 12px 14px;
  border-top: 3px solid;
  border-radius: 12px 12px 0 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--crm-surface);
}

.kanban-column-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--crm-text-secondary);
}

.kanban-column-body {
  flex: 1;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 100px;
}

.kanban-card {
  background: var(--crm-surface);
  border-radius: 8px;
  padding: 12px;
  border: 1px solid var(--crm-border);
  cursor: grab;
  transition: box-shadow 0.15s, transform 0.1s, background 0.3s, border-color 0.3s;
}
.kanban-card:hover {
  box-shadow: 0 2px 8px var(--crm-shadow-hover);
  transform: translateY(-1px);
}
.kanban-card:active {
  cursor: grabbing;
  opacity: 0.8;
}

.kanban-card-header {
  margin-bottom: 6px;
}

.kanban-card-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--crm-text);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.kanban-card-meta {
  font-size: 11px;
  color: var(--crm-text-muted);
  margin-bottom: 6px;
  display: flex;
  align-items: center;
}

.kanban-card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.kanban-card-amount {
  font-size: 12px;
  font-weight: 600;
  color: var(--crm-text-secondary);
}

.kanban-card-comment {
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px dashed var(--crm-border);
  font-size: 11px;
  color: var(--crm-text-muted);
  display: flex;
  align-items: flex-start;
}

.kanban-empty {
  text-align: center;
  color: var(--crm-text-faint);
  font-size: 12px;
  padding: 20px 8px;
}
</style>
