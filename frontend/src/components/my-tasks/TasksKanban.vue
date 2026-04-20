<template>
  <div class="kanban-board">
    <div
      v-for="col in GT_COLUMNS" :key="col.status"
      :class="['kanban-column', col.status === 'done' && !archiveExpanded ? 'kanban-column--collapsed' : '']"
      @dragover.prevent
      @drop="onDropGeneral($event, col.status)"
    >
      <!-- Collapsed archive column -->
      <div
        v-if="col.status === 'done' && !archiveExpanded"
        class="kanban-column-collapsed-body"
        :style="{ borderColor: col.color }"
        title="Развернуть архив"
        @click="archiveExpanded = true"
      >
        <v-icon size="16" :color="col.color" class="mb-2">mdi-archive-outline</v-icon>
        <span class="kanban-collapsed-label">Архив</span>
        <v-chip size="x-small" :color="col.color" variant="tonal" class="mt-2">{{ generalByStatus(col.status).length }}</v-chip>
      </div>

      <template v-else>
        <div class="kanban-column-header" :style="{ borderTopColor: col.color }">
          <span class="kanban-column-title">{{ col.label }}</span>
          <v-chip size="x-small" :color="col.color" variant="tonal">{{ generalByStatus(col.status).length }}</v-chip>
          <v-btn
            v-if="col.status === 'done'"
            icon
            size="x-small"
            variant="text"
            class="ml-1"
            title="Свернуть"
            @click="archiveExpanded = false"
          >
            <v-icon size="16">mdi-chevron-right</v-icon>
          </v-btn>
        </div>
        <div class="kanban-column-body">
          <div
            v-for="gt in generalByStatus(col.status)" :key="gt.id"
            class="kanban-card"
            :style="gtCardStyle(gt)"
            draggable="true"
            @dragstart="onDragStartGeneral($event, gt)"
            @click="linkPurchaseId ? $emit('link-purchase', gt.id) : $emit('open-task', gt)"
          >
            <div class="d-flex align-center ga-1 mb-1">
              <v-chip :color="PRIORITY_COLOR[gt.priority] || 'grey'" size="x-small" variant="flat">{{ PRIORITY_LABEL[gt.priority] || gt.priority }}</v-chip>
              <v-chip v-if="gt.category" size="x-small" variant="outlined">{{ gt.category }}</v-chip>
              <v-chip v-if="gt.parent_task_id" size="x-small" variant="tonal" color="indigo" title="Подзадача">
                <v-icon icon="mdi-subdirectory-arrow-right" size="10" class="mr-1" />Подзадача
              </v-chip>
              <v-spacer />
              <v-chip v-if="gt.unseen_changes_count" size="x-small" variant="flat" color="warning" :title="`${gt.unseen_changes_count} новых изменений`">
                <v-icon icon="mdi-bell-ring" size="10" class="mr-1" />{{ gt.unseen_changes_count }}
              </v-chip>
              <v-chip v-if="gt.subtask_count" size="x-small" variant="tonal" color="teal" :title="`${gt.subtask_count} делегировано`">
                <v-icon icon="mdi-sitemap-outline" size="10" class="mr-1" />{{ gt.subtask_count }}
              </v-chip>
              <v-chip v-if="gt.comment_count" size="x-small" variant="tonal" color="blue-grey">
                <v-icon icon="mdi-comment-text-outline" size="10" class="mr-1" />{{ gt.comment_count }}
              </v-chip>
            </div>

            <!-- Linked purchase -->
            <div v-if="gt.purchase_id" class="mb-1">
              <v-chip size="x-small" variant="tonal" color="deep-purple" prepend-icon="mdi-cart-outline"
                @click.stop="$emit('navigate-purchase', gt.purchase_id!)">
                {{ gt.purchase_subject || `Закупка #${gt.purchase_number || gt.purchase_id}` }}
              </v-chip>
            </div>

            <div class="kanban-card-title">
              <span v-if="gt.task_number" class="text-caption text-medium-emphasis mr-1">#{{ gt.task_number }}</span>
              {{ gt.title }}
            </div>
            <div v-if="gt.description" class="kanban-card-meta" style="font-size:11px;opacity:.7">
              {{ gt.description.length > 80 ? gt.description.slice(0, 80) + '…' : gt.description }}
            </div>

            <!-- Last comment preview -->
            <div v-if="gt.last_comment" class="kanban-card-comment">
              <v-icon icon="mdi-comment-text-outline" size="12" class="mr-1" />
              <span><strong>{{ gt.last_comment_user }}:</strong> {{ gt.last_comment }}</span>
            </div>

            <div class="kanban-card-footer mt-1">
              <span v-if="gt.assignees?.length" class="kanban-card-meta">
                <v-icon icon="mdi-account-multiple" size="12" class="mr-1"/>
                {{ gt.assignees.map((a: any) => a.user_name?.split(' ')[0] || '?').join(', ') }}
              </span>
              <v-chip v-if="gt.due_date" :color="deadlineColor(gt.due_date)" size="x-small" variant="tonal">{{ formatDate(gt.due_date.split('T')[0]) }}</v-chip>
            </div>

            <!-- Review confirmation buttons for task creator -->
            <div v-if="gt.status === 'review' && gt.created_by_id === currentUserId" class="d-flex ga-1 mt-2" @click.stop>
              <v-btn size="x-small" color="success" variant="tonal" prepend-icon="mdi-check" @click.stop="$emit('confirm-done', gt.id)">Подтвердить</v-btn>
              <v-btn size="x-small" color="warning" variant="tonal" prepend-icon="mdi-undo" @click.stop="$emit('reject-done', gt.id)">Вернуть</v-btn>
            </div>
          </div>
          <div v-if="generalByStatus(col.status).length === 0" class="kanban-empty">Нет задач</div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * TasksKanban — kanban column view for the General Tasks tab in MyTasksView (D-16).
 * Pure presentation: all data via props, mutations emitted back to parent.
 * Drag-drop updates status optimistically via 'update-status' emit.
 * No apiFetch, no router, no store access.
 */
import { ref } from 'vue'

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
  updated_at?: string | null
  org_id?: number | null
  purchase_id?: number | null
  purchase_subject?: string | null
  purchase_number?: string | null
  assignees?: TaskAssignee[]
  created_by_id?: number | null
  unseen_changes_count?: number
  last_comment?: string | null
  last_comment_user?: string | null
  comment_count?: number
  subtask_count?: number
  parent_task_id?: number | null
  category?: string | null
}

interface Props {
  /** Filtered list of general tasks (all statuses) */
  tasks: GeneralTask[]
  /** Current user id — used to show confirm/reject buttons for 'review' tasks */
  currentUserId: number
  /** Non-null when user clicked "Привязать к закупке" — shows link button on card click */
  linkPurchaseId: number | null
}

const props = defineProps<Props>()

// ── Kanban columns definition ────────────────────────────────────────────────
const GT_COLUMNS = [
  { status: 'todo', label: 'К выполнению', color: '#F59E0B' },
  { status: 'in_progress', label: 'В работе', color: '#3B82F6' },
  { status: 'review', label: 'На проверке', color: '#8B5CF6' },
  { status: 'done', label: 'Архив', color: '#22C55E' },
]

// ── Local UI state ───────────────────────────────────────────────────────────
/** Whether the "done" column is expanded (true) or collapsed to a sidebar strip (false) */
const archiveExpanded = ref(false)

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

// ── Derived data helpers ─────────────────────────────────────────────────────
const generalByStatus = (status: string) =>
  props.tasks.filter(t => t.status === status)

// ── Deadline urgency for card background ─────────────────────────────────────
function gtCardStyle(gt: GeneralTask): Record<string, string> {
  if (gt.status === 'done') {
    if (!gt.due_date) return { background: 'rgba(34,197,94,0.08)', borderColor: 'rgba(34,197,94,0.3)' }
    const completedAt = gt.updated_at ? new Date(gt.updated_at) : new Date()
    const dueDate = new Date(gt.due_date)
    const diffDays = (dueDate.getTime() - completedAt.getTime()) / 86400000
    if (diffDays < 0) return { background: 'rgba(239,68,68,0.15)', borderColor: 'rgba(239,68,68,0.5)' }
    if (diffDays < 1) return { background: 'rgba(245,158,11,0.12)', borderColor: 'rgba(245,158,11,0.45)' }
    return { background: 'rgba(34,197,94,0.12)', borderColor: 'rgba(34,197,94,0.45)' }
  }
  if (!gt.due_date) return {}
  const diff = (new Date(gt.due_date).getTime() - Date.now()) / 86400000
  if (diff < 0) return { background: 'rgba(239,68,68,0.15)', borderColor: 'rgba(239,68,68,0.4)' }
  if (diff <= 1) return { background: 'rgba(239,68,68,0.10)', borderColor: 'rgba(239,68,68,0.3)' }
  if (diff <= 3) return { background: 'rgba(249,115,22,0.10)', borderColor: 'rgba(249,115,22,0.3)' }
  if (diff <= 7) return { background: 'rgba(245,158,11,0.08)', borderColor: 'rgba(245,158,11,0.25)' }
  return { background: 'rgba(34,197,94,0.06)', borderColor: 'rgba(34,197,94,0.2)' }
}

// ── Drag & Drop ──────────────────────────────────────────────────────────────
let draggedGeneral: GeneralTask | null = null

function onDragStartGeneral(e: DragEvent, task: GeneralTask) {
  draggedGeneral = task
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', String(task.id))
  }
}

const emit = defineEmits<{
  (e: 'open-task', task: GeneralTask): void
  (e: 'update-status', taskId: number, newStatus: string): void
  (e: 'link-purchase', taskId: number): void
  (e: 'navigate-purchase', purchaseId: number): void
  (e: 'confirm-done', taskId: number): void
  (e: 'reject-done', taskId: number): void
}>()

function onDropGeneral(e: DragEvent, targetStatus: string) {
  e.preventDefault()
  if (!draggedGeneral || draggedGeneral.status === targetStatus) return
  const t = draggedGeneral
  draggedGeneral = null
  // Optimistic update: mutate local task ref so UI responds instantly
  // The actual PATCH is done by the parent via the 'update-status' emit
  t.status = targetStatus
  emit('update-status', t.id, targetStatus)
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

.kanban-column--collapsed {
  min-width: 48px;
  max-width: 48px;
  flex: 0 0 48px;
}

.kanban-column-collapsed-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  padding: 12px 6px;
  height: 100%;
  cursor: pointer;
  border-radius: 12px;
  border: 2px solid;
  transition: opacity 0.2s;
  opacity: 0.7;
  background: var(--crm-surface-alt);
}
.kanban-column-collapsed-body:hover {
  opacity: 1;
}
.kanban-collapsed-label {
  writing-mode: vertical-rl;
  text-orientation: mixed;
  transform: rotate(180deg);
  font-size: 11px;
  font-weight: 600;
  color: var(--crm-text-secondary);
  margin: 4px 0;
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
