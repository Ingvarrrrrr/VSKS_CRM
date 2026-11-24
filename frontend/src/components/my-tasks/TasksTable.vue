<template>
  <div>
    <!-- Quick filter and color filter chips -->
    <div v-if="cellMarks.activeColorFilter.value?.task || quickFilter" class="d-flex align-center ga-2 mb-2">
      <v-chip
        v-if="cellMarks.activeColorFilter.value?.task"
        size="small"
        color="purple"
        variant="tonal"
        closable
        prepend-icon="mdi-palette"
        @click:close="cellMarks.setColorFilter('task', null)"
      >
        🎨 Фильтр цвета: {{ cellMarks.activeColorFilter.value.task }}
      </v-chip>
      <v-chip
        v-if="quickFilter"
        size="small"
        color="primary"
        variant="tonal"
        closable
        prepend-icon="mdi-filter"
        @click:close="quickFilter = null"
      >
        {{ quickFilter.label }}
      </v-chip>
    </div>

    <v-data-table
      v-resizable-columns="'my-tasks'"
      :headers="taskListHeaders"
      :items="displayTasks"
      density="compact"
      hover
      items-per-page="25"
      :items-per-page-options="[25,50,100]"
      :row-props="getRowProps"
      @click:row="(_e: any, { item }: any) => linkPurchaseId ? $emit('link-purchase', item.id) : $emit('open-task', item)"
    >
      <template #item.task_number="{ item }">
        <span
          class="text-caption font-weight-medium"
          :class="cellMarks.getCellMarkClasses('task', item.id, 'task_number')"
          :style="cellMarks.getCellMarkStyle('task', item.id, 'task_number')"
          @click="onCellClick($event, { entityType: 'task', entityId: item.id, fieldName: 'task_number' })"
          @contextmenu.prevent="onCellContextMenu($event, item, 'task_number', '№', item.task_number)"
        >{{ item.task_number || '—' }}</span>
      </template>

      <template #item.title="{ item }">
        <span
          :class="cellMarks.getCellMarkClasses('task', item.id, 'title')"
          :style="cellMarks.getCellMarkStyle('task', item.id, 'title')"
          @click="onCellClick($event, { entityType: 'task', entityId: item.id, fieldName: 'title' })"
          @contextmenu.prevent="onCellContextMenu($event, item, 'title', 'Название', item.title)"
        >{{ item.title }}</span>
      </template>

      <template #item.priority="{ item }">
        <v-chip
          :color="PRIORITY_COLOR[item.priority]||'grey'"
          size="x-small"
          variant="flat"
          :class="cellMarks.getCellMarkClasses('task', item.id, 'priority')"
          :style="cellMarks.getCellMarkStyle('task', item.id, 'priority')"
          @click="onCellClick($event, { entityType: 'task', entityId: item.id, fieldName: 'priority' })"
          @contextmenu.prevent="onCellContextMenu($event, item, 'priority', 'Приоритет', PRIORITY_LABEL[item.priority] || item.priority)"
        >
          {{ PRIORITY_LABEL[item.priority] }}
        </v-chip>
      </template>

      <template #item.status="{ item }">
        <v-chip
          :color="item.status==='done'?'success':item.status==='in_progress'?'primary':item.status==='review'?'purple':'warning'"
          size="x-small"
          variant="tonal"
          :class="cellMarks.getCellMarkClasses('task', item.id, 'status')"
          :style="cellMarks.getCellMarkStyle('task', item.id, 'status')"
          @click="onCellClick($event, { entityType: 'task', entityId: item.id, fieldName: 'status' })"
          @contextmenu.prevent="onCellContextMenu($event, item, 'status', 'Статус', STATUS_NAMES[item.status]||item.status)"
        >
          {{ STATUS_NAMES[item.status]||item.status }}
        </v-chip>
      </template>

      <template #item.assignees="{ item }">
        <span
          class="text-caption"
          :class="cellMarks.getCellMarkClasses('task', item.id, 'assignees')"
          :style="cellMarks.getCellMarkStyle('task', item.id, 'assignees')"
          @click="onCellClick($event, { entityType: 'task', entityId: item.id, fieldName: 'assignees' })"
          @contextmenu.prevent="onCellContextMenu($event, item, 'assignees', 'Исполнитель', item.assignees?.map((a:any) => a.user_name?.split(' ')[0]).join(', ') || '—')"
        >{{ item.assignees?.map((a:any) => a.user_name?.split(' ')[0]).join(', ') || '—' }}</span>
      </template>

      <template #item.due_date="{ item }">
        <v-chip
          v-if="item.due_date"
          :color="deadlineColor(item.due_date)"
          size="x-small"
          variant="tonal"
          :class="cellMarks.getCellMarkClasses('task', item.id, 'due_date')"
          :style="cellMarks.getCellMarkStyle('task', item.id, 'due_date')"
          @click="onCellClick($event, { entityType: 'task', entityId: item.id, fieldName: 'due_date' })"
          @contextmenu.prevent="onCellContextMenu($event, item, 'due_date', 'Срок', formatDate(item.due_date.split('T')[0]))"
        >
          {{ formatDate(item.due_date.split('T')[0]) }}
        </v-chip>
        <span v-else class="text-caption text-medium-emphasis">—</span>
      </template>

      <template #item.purchase_subject="{ item }">
        <v-chip
          v-if="item.purchase_id"
          size="x-small"
          variant="tonal"
          color="deep-purple"
          @click.stop="$emit('navigate-purchase', item.purchase_id)"
          @contextmenu.prevent="onCellContextMenu($event, item, 'purchase_subject', 'Закупка', item.purchase_subject)"
        >
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
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { apiFetch } from '@/api'
import { useGalaContextMenu } from '@/composables/useGalaContextMenu'
import { useCellMarks, type CellTarget } from '@/composables/useCellMarks'

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
  tasks: GeneralTask[]
  currentUserId: number
  linkPurchaseId: number | null
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'open-task', task: GeneralTask): void
  (e: 'link-purchase', taskId: number): void
  (e: 'navigate-purchase', purchaseId: number): void
  (e: 'confirm-done', taskId: number): void
  (e: 'reject-done', taskId: number): void
  (e: 'task-updated', taskId: number): void
}>()

const cellMarks = useCellMarks()
const { openCellContextMenu } = useGalaContextMenu()

const quickFilter = ref<{ field: string; value: any; label: string } | null>(null)

watch(
  () => props.tasks,
  (tasks) => {
    if (tasks && tasks.length > 0) {
      const ids = tasks.map((t) => t.id).filter(Boolean)
      if (ids.length > 0) {
        void cellMarks.loadMarks('task', ids)
      }
    }
  },
  { immediate: true }
)

const displayTasks = computed(() => {
  let list = props.tasks
  const colorFilter = cellMarks.activeColorFilter.value?.task
  if (colorFilter) {
    list = list.filter((t) => cellMarks.matchesColorFilter('task', t.id))
  }
  if (quickFilter.value) {
    const { field, value } = quickFilter.value
    list = list.filter((t: any) => {
      if (field === 'assignees') {
        return t.assignees?.some((a: any) =>
          String(a.user_name || '').toLowerCase().includes(String(value).toLowerCase())
        )
      }
      return String(t[field] ?? '').toLowerCase().includes(String(value).toLowerCase())
    })
  }
  return list
})

function getRowProps({ item }: { item: any }) {
  return {
    class: cellMarks.getRowMarkClasses('task', item.id),
    style: cellMarks.getRowMarkStyle('task', item.id),
    'data-gala-focus': `task:${item.id}`,
  }
}

function onCellClick(event: MouseEvent, target: CellTarget) {
  if (cellMarks.handleCellSelectClick(event, target)) {
    event.stopPropagation()
    return
  }
  const el = event.currentTarget as HTMLElement | null
  if (el) {
    const rect = el.getBoundingClientRect()
    const isTopRight = event.clientX >= rect.right - 18 && event.clientY <= rect.top + 18
    const mark = cellMarks.getMark(target.entityType, Number(target.entityId), target.fieldName)
    if (isTopRight && mark?.comment) {
      event.stopPropagation()
      cellMarks.openCommentAt(event, target)
    }
  }
}

async function changeTaskPriority(taskId: number, priority: string) {
  try {
    await apiFetch(`/tasks/${taskId}`, {
      method: 'PATCH',
      body: JSON.stringify({ priority }),
    })
    const t = props.tasks.find((x) => x.id === taskId)
    if (t) t.priority = priority
    emit('task-updated', taskId)
  } catch (e) {
    console.warn('Failed to update task priority', e)
  }
}

function onCellContextMenu(
  event: MouseEvent,
  item: GeneralTask,
  fieldName: string,
  fieldLabel: string,
  cellValue: any
) {
  openCellContextMenu(event, {
    entityType: 'task',
    entityId: item.id,
    fieldName,
    fieldLabel,
    cellValue,
    openUrl: item.purchase_id ? `/orders/${item.purchase_id}/edit` : undefined,
    orgId: item.org_id ?? null,
    onFilterValue: (val: any) => {
      quickFilter.value = {
        field: fieldName,
        value: val,
        label: `${fieldLabel}: ${val}`,
      }
    },
    extraItems: [
      {
        key: 'prio_high',
        label: 'Приоритет: Высокий',
        icon: 'mdi-alert-circle',
        onClick: () => changeTaskPriority(item.id, 'high'),
      },
      {
        key: 'prio_medium',
        label: 'Приоритет: Средний',
        icon: 'mdi-minus-circle',
        onClick: () => changeTaskPriority(item.id, 'medium'),
      },
      {
        key: 'prio_low',
        label: 'Приоритет: Низкий',
        icon: 'mdi-arrow-down-circle',
        onClick: () => changeTaskPriority(item.id, 'low'),
      },
    ],
  } as any)
}

function onEntityRestored(e: Event) {
  const customEv = e as CustomEvent<{ entityType: string; entityId: number | string }>
  if (customEv.detail?.entityType === 'task') {
    if (props.tasks && props.tasks.length > 0) {
      void cellMarks.loadMarks('task', props.tasks.map((t) => t.id).filter(Boolean))
    }
  }
}

onMounted(() => {
  window.addEventListener('gala:entity-restored', onEntityRestored)
})

onBeforeUnmount(() => {
  window.removeEventListener('gala:entity-restored', onEntityRestored)
})

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

// ── Priority & Status labels ────────────────────────────────────────────────
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
const STATUS_NAMES: Record<string, string> = {
  todo: 'К выполнению',
  in_progress: 'В работе',
  review: 'На проверке',
  done: 'Готово',
  cancelled: 'Отменена',
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
:deep(tbody tr) {
  cursor: pointer;
}
:deep(.v-data-table .v-data-table__tr > td) {
  padding-top: 6px;
  padding-bottom: 6px;
  vertical-align: middle;
}
:deep(tbody tr:hover td) {
  background: rgba(var(--v-theme-primary), 0.04);
}
:deep(.v-data-table th:nth-child(2)),
:deep(.v-data-table td:nth-child(2)) {
  min-width: 200px;
  max-width: 360px;
}
:deep(.v-data-table td:last-child) {
  white-space: nowrap;
  text-align: right;
}
:deep(.v-chip) {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
:deep(.v-data-table td .text-caption) {
  line-height: 1.4;
  white-space: normal;
  word-break: break-word;
}
:deep(.v-data-table .v-chip--size-x-small) {
  min-width: 72px;
  justify-content: center;
}
:deep(tbody tr.v-data-table__tr--selected td) {
  background: rgba(var(--v-theme-primary), 0.08);
}
:deep(.v-data-table__td--no-data) {
  text-align: center;
  padding: 32px 16px;
  color: rgba(0, 0, 0, 0.45);
}
:deep(.v-data-table-footer) {
  padding: 4px 8px;
  font-size: 12px;
}
:deep(.v-table__wrapper) {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}
:deep(thead th) {
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--crm-surface, #fff);
  white-space: nowrap;
}
:deep(.v-chip--size-x-small.priority-chip) {
  min-width: 60px;
  justify-content: center;
}
:deep(tbody tr[data-status='cancelled'] td) {
  opacity: 0.55;
}
</style>
