<template>
  <v-data-table
      :headers="taskListHeaders"
      :items="tasks"
      density="compact"
      hover
      items-per-page="25"
      :items-per-page-options="[25,50,100]"
      @click:row="(_e: any, { item }: any) => linkPurchaseId ? $emit('link-purchase', item.id) : $emit('open-task', item)"
    >
      <template #item.task_number="{ item }">
        <span class="text-caption font-weight-medium">{{ item.task_number || '—' }}</span>
      </template>
      <template #item.priority="{ item }">
        <v-chip :color="PRIORITY_COLOR[item.priority]||'grey'" size="x-small" variant="flat">{{ PRIORITY_LABEL[item.priority] }}</v-chip>
      </template>
      <template #item.status="{ item }">
        <v-chip :color="item.status==='done'?'success':item.status==='in_progress'?'primary':item.status==='review'?'purple':'warning'" size="x-small" variant="tonal">
          {{ {todo:'К выполнению',in_progress:'В работе',review:'На проверке',done:'Готово',cancelled:'Отменена'}[item.status]||item.status }}
        </v-chip>
      </template>
      <template #item.assignees="{ item }">
        <span class="text-caption">{{ item.assignees?.map((a:any) => a.user_name?.split(' ')[0]).join(', ') || '—' }}</span>
      </template>
      <template #item.due_date="{ item }">
        <v-chip v-if="item.due_date" :color="deadlineColor(item.due_date)" size="x-small" variant="tonal">{{ formatDate(item.due_date.split('T')[0]) }}</v-chip>
        <span v-else class="text-caption text-medium-emphasis">—</span>
      </template>
      <template #item.purchase_subject="{ item }">
        <v-chip v-if="item.purchase_id" size="x-small" variant="tonal" color="deep-purple"
          @click.stop="$emit('navigate-purchase', item.purchase_id)">
          {{ item.purchase_subject || `#${item.purchase_number || item.purchase_id}` }}
        </v-chip>
      </template>
      <template #item.actions="{ item }">
        <v-btn v-if="linkPurchaseId" size="x-small" variant="tonal" color="deep-purple"
          prepend-icon="mdi-link-variant" @click.stop="$emit('link-purchase', item.id)">Привязать</v-btn>
        <template v-else-if="item.status === 'review' && item.created_by_id === currentUserId">
          <v-btn size="x-small" color="success" variant="tonal" prepend-icon="mdi-check" class="mr-1" @click.stop="$emit('confirm-done', item.id)">Подтвердить</v-btn>
          <v-btn size="x-small" color="warning" variant="tonal" prepend-icon="mdi-undo" @click.stop="$emit('reject-done', item.id)">Вернуть</v-btn>
        </template>
        <v-btn v-else icon="mdi-pencil" variant="text" size="small" @click.stop="$emit('open-task', item)" />
      </template>
    </v-data-table>
</template>

<script setup lang="ts">
/**
 * TasksTable — list view (v-data-table) for the General Tasks tab in MyTasksView (D-16).
 * Pure presentation: all data comes via props, all mutations are emitted back to parent.
 * No apiFetch, no router, no store access.
 */

export interface TaskAssignee {
  user_id: number
  user_name: string
}

export interface GeneralTask {
  id: number
  task_number?: string | null
  title: string
  description?: string | null
  priority: string
  status: string
  due_date?: string | null
  org_id?: number | null
  purchase_id?: number | null
  purchase_subject?: string | null
  purchase_number?: string | null
  purchase_status?: string | null
  assignees?: TaskAssignee[]
  created_by_id?: number | null
  created_by_name?: string | null
  unseen_changes_count?: number
  unseen_fields?: string[]
  last_comment?: string | null
  last_comment_user?: string | null
  comment_count?: number
  subtask_count?: number
  parent_task_id?: number | null
  category?: string | null
  updated_at?: string | null
}

interface Props {
  /** Filtered list of general tasks to display */
  tasks: GeneralTask[]
  /** Current user id — used to show confirm/reject buttons for 'review' tasks */
  currentUserId: number
  /** Non-null when user clicked "Привязать к закупке" from another view — shows link button */
  linkPurchaseId: number | null
}

defineProps<Props>()

defineEmits<{
  /** User clicked a task row or pencil icon — parent opens the task dialog */
  (e: 'open-task', task: GeneralTask): void
  /** User clicked "Привязать" to link a purchase to this task */
  (e: 'link-purchase', taskId: number): void
  /** User clicked the linked purchase chip — parent navigates to /orders/:id/edit */
  (e: 'navigate-purchase', purchaseId: number): void
  /** Task creator confirmed "review" status → mark as done */
  (e: 'confirm-done', taskId: number): void
  /** Task creator rejected "review" status → move back to in_progress */
  (e: 'reject-done', taskId: number): void
}>()

// ── Column definitions ──────────────────────────────────────────────────────
const taskListHeaders = [
  { title: '№', key: 'task_number', width: 60 },
  { title: 'Название', key: 'title', minWidth: 200 },
  { title: 'Приоритет', key: 'priority', width: 100 },
  { title: 'Статус', key: 'status', width: 120 },
  { title: 'Исполнители', key: 'assignees', width: 160, sortable: false },
  { title: 'Срок', key: 'due_date', width: 110 },
  { title: 'Закупка', key: 'purchase_subject', width: 150, sortable: false },
  { title: '', key: 'actions', width: 80, sortable: false },
]

// ── Priority labels/colors ───────────────────────────────────────────────────
const PRIORITY_LABEL: Record<string, string> = {
  low: 'Низкий',
  medium: 'Средний',
  high: 'Высокий',
  urgent: 'Срочно',
}
const PRIORITY_COLOR: Record<string, string> = {
  low: 'grey',
  medium: 'blue',
  high: 'orange',
  urgent: 'red',
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
</script>

<style scoped>
/**
 * TasksTable scoped styles.
 * Status chip colours are applied via Vuetify's `color` prop (no custom class needed).
 * These rules cover hover states and layout refinements inside the data table.
 */

/* Ensure rows show pointer cursor for click affordance */
:deep(tbody tr) {
  cursor: pointer;
}

/* Tighten dense row height so the table feels compact */
:deep(.v-data-table .v-data-table__tr > td) {
  padding-top: 6px;
  padding-bottom: 6px;
  vertical-align: middle;
}

/* Highlight rows on hover with a subtle background */
:deep(tbody tr:hover td) {
  background: rgba(var(--v-theme-primary), 0.04);
}

/* Cap the task title column width so long titles wrap cleanly */
:deep(.v-data-table th:nth-child(2)),
:deep(.v-data-table td:nth-child(2)) {
  min-width: 200px;
  max-width: 360px;
}

/* Actions column: keep buttons aligned at the end */
:deep(.v-data-table td:last-child) {
  white-space: nowrap;
  text-align: right;
}

/* Purchase chip inside table — shrink overflow gracefully */
:deep(.v-chip) {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Assignees column: allow wrapping if multiple names */
:deep(.v-data-table td .text-caption) {
  line-height: 1.4;
  white-space: normal;
  word-break: break-word;
}

/* Due-date chip: consistent min-width so dates don't jump */
:deep(.v-data-table .v-chip--size-x-small) {
  min-width: 72px;
  justify-content: center;
}

/* Row selected state (when using v-data-table selection) */
:deep(tbody tr.v-data-table__tr--selected td) {
  background: rgba(var(--v-theme-primary), 0.08);
}

/* No-data message centering */
:deep(.v-data-table__td--no-data) {
  text-align: center;
  padding: 32px 16px;
  color: rgba(0, 0, 0, 0.45);
}

/* Items-per-page selector alignment */
:deep(.v-data-table-footer) {
  padding: 4px 8px;
  font-size: 12px;
}

/* Responsive: on narrow screens allow table to scroll horizontally */
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

/* Priority chip consistent width */
:deep(.v-chip--size-x-small.priority-chip) {
  min-width: 60px;
  justify-content: center;
}

/* Cancelled row: dim text */
:deep(tbody tr[data-status='cancelled'] td) {
  opacity: 0.55;
}
</style>
