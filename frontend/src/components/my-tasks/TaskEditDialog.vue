<template>
  <!-- General Task Dialog (create/edit) -->
  <v-dialog :model-value="show" max-width="680" :fullscreen="mobile" @update:model-value="$emit('update:show', $event)">
    <v-card>
      <v-card-title class="d-flex align-center justify-space-between">
        <span>{{ editingTask ? 'Задача' : 'Новая задача' }}</span>
        <div class="d-flex ga-1 align-center">
          <v-chip v-if="editingTask && editingTask.created_by_name" size="small" variant="tonal" color="indigo" prepend-icon="mdi-account-arrow-right">
            Поставил: {{ editingTask.created_by_name }}
          </v-chip>
          <v-chip v-if="editingTask && isTaskReadonly" size="small" variant="tonal" color="warning" prepend-icon="mdi-lock-outline">
            Только статус
          </v-chip>
          <!-- Phase 31-07: Undo/Redo кнопки -->
          <v-btn
            :disabled="!undoRedo.canUndo.value"
            icon="mdi-undo"
            size="x-small"
            variant="text"
            :color="undoRedo.canUndo.value ? '#fb923c' : undefined"
            title="Отменить (Ctrl+Z)"
            @click="undoRedo.undo()"
          />
          <v-btn
            :disabled="!undoRedo.canRedo.value"
            icon="mdi-redo"
            size="x-small"
            variant="text"
            :color="undoRedo.canRedo.value ? '#fb923c' : undefined"
            title="Повторить (Ctrl+Y)"
            @click="undoRedo.redo()"
          />
        </div>
      </v-card-title>
      <v-card-text>
        <div :class="isFieldUnseen('title') ? 'field-changed mb-2' : 'mb-2'" @click="dismissField('title')">
          <v-text-field v-model="localForm.title" label="Название *" variant="outlined" density="compact" :readonly="isTaskReadonly" :bg-color="isTaskReadonly ? 'grey-lighten-4' : undefined" data-field="title" />
        </div>
        <div :class="isFieldUnseen('description') ? 'field-changed mb-2' : 'mb-2'" @click="dismissField('description')">
          <v-textarea v-model="localForm.description" label="Описание" variant="outlined" density="compact" rows="2" :readonly="isTaskReadonly" :bg-color="isTaskReadonly ? 'grey-lighten-4' : undefined" data-field="description" />
        </div>
        <div class="d-flex ga-2 mb-2">
          <div :class="isFieldUnseen('priority') ? 'field-changed' : ''" style="max-width:200px;flex:0 0 auto" @click="dismissField('priority')">
            <v-select v-model="localForm.priority" :items="priorityItems" label="Приоритет" variant="outlined" density="compact" :disabled="isTaskReadonly" data-field="priority" />
          </div>
          <v-combobox v-model="localForm.category" :items="taskCategories" label="Категория" variant="outlined" density="compact" clearable :disabled="isTaskReadonly" />
        </div>
        <div :class="isFieldUnseen('due_date') ? 'field-changed mb-2' : 'mb-2'" @click="dismissField('due_date')">
          <v-text-field v-model="localForm.due_date" label="Срок исполнения" variant="outlined" density="compact" type="date" :min="todayStr" :rules="[dueDateRule]" :readonly="isTaskReadonly" :bg-color="isTaskReadonly ? 'grey-lighten-4' : undefined" data-field="due_date" />
        </div>
        <div class="mb-2">
          <v-select
            v-model="localForm.org_id"
            :items="orgSummary.filter(o => o.org_id !== null).map(o => ({ title: o.org_name, value: o.org_id }))"
            label="Организация"
            variant="outlined"
            density="compact"
            clearable
            prepend-inner-icon="mdi-domain"
            :disabled="isTaskReadonly"
          />
        </div>
        <div :class="isFieldUnseen('assignees') ? 'field-changed mb-2' : 'mb-2'" @click="dismissField('assignees')">
          <v-autocomplete v-if="!editingTask || !isTaskReadonly" v-model="localForm.assignee_ids" :items="userItems" label="Исполнители" variant="outlined" density="compact" multiple chips closable-chips item-title="text" item-value="value" class="mb-2">
            <template #item="{ item, props }">
              <v-list-item v-bind="props">
                <template #append>
                  <v-chip v-if="item.raw.value !== currentUserId && !subordinateIds.has(item.raw.value) && !managedOrgUserIds.has(item.raw.value)" size="x-small" color="orange" variant="tonal">нужно согласие</v-chip>
                </template>
              </v-list-item>
            </template>
          </v-autocomplete>
        </div>

        <!-- Linked purchase -->
        <div class="mb-2 d-flex align-center ga-1 flex-wrap">
          <template v-if="editingTask?.purchase_id">
            <v-chip color="deep-purple" variant="tonal" prepend-icon="mdi-cart-outline"
              @click="$router.push(`/orders/${editingTask.purchase_id}/edit`); $emit('update:show', false)">
              {{ editingTask.purchase_subject || `Закупка #${editingTask.purchase_number || editingTask.purchase_id}` }}
              <v-icon end size="14">mdi-open-in-new</v-icon>
            </v-chip>
            <v-chip v-if="editingTask.purchase_status" size="x-small" variant="tonal">
              {{ editingTask.purchase_status }}
            </v-chip>
            <v-btn v-if="!isTaskReadonly" icon="mdi-link-variant-off" size="x-small" variant="text"
              color="grey" title="Отвязать закупку" @click="unlinkPurchaseFromTask" />
          </template>
          <v-btn v-else-if="editingTask && !isTaskReadonly" size="small" variant="tonal" color="deep-purple"
            prepend-icon="mdi-cart-plus" @click="openLinkPurchase">
            Привязать закупку
          </v-btn>
        </div>

        <!-- Диалог привязки закупки -->
        <v-dialog v-model="linkPurchaseDialog" max-width="520" :fullscreen="mobile">
          <v-card>
            <v-card-title class="text-subtitle-1 pt-4 px-4">
              <v-icon class="mr-1" size="20">mdi-cart-plus</v-icon>
              Привязать закупку
            </v-card-title>
            <v-card-text>
              <v-text-field v-model="linkPurchaseSearch" label="Поиск по названию / номеру"
                variant="outlined" density="compact" prepend-inner-icon="mdi-magnify" clearable autofocus
                @update:model-value="searchPurchases" />
              <div v-if="linkPurchaseSearching" class="d-flex justify-center py-4"><v-progress-circular indeterminate size="24" /></div>
              <v-list v-else-if="linkPurchaseResults.length" density="compact" class="border rounded"
                style="max-height:300px;overflow-y:auto">
                <v-list-item v-for="p in linkPurchaseResults" :key="p.id" @click="linkPurchaseToTask(p.id)">
                  <v-list-item-title class="text-body-2">
                    {{ p.subject || p.item_name || `Закупка #${p.purchase_number || p.id}` }}
                  </v-list-item-title>
                  <v-list-item-subtitle class="text-caption">
                    {{ p.status }} · {{ p.contractor_name || '' }}
                  </v-list-item-subtitle>
                </v-list-item>
              </v-list>
              <div v-else-if="linkPurchaseSearch" class="text-caption text-medium-emphasis text-center py-4">Не найдено</div>
              <div v-else class="text-caption text-medium-emphasis text-center py-4">Введите текст для поиска</div>
            </v-card-text>
            <v-card-actions>
              <v-spacer />
              <v-btn variant="text" @click="linkPurchaseDialog = false">Закрыть</v-btn>
            </v-card-actions>
          </v-card>
        </v-dialog>

        <!-- Subtasks (delegated) -->
        <template v-if="editingTask && taskSubtasks.length">
          <v-divider class="my-2" />
          <div class="text-subtitle-2 font-weight-medium mb-1 d-flex align-center ga-1">
            <v-icon icon="mdi-sitemap-outline" size="16" color="teal" />
            Делегировано ({{ taskSubtasks.length }})
          </div>
          <v-list density="compact" class="border rounded mb-2">
            <v-list-item v-for="st in taskSubtasks" :key="st.id"
              :prepend-icon="'mdi-circle-small'"
              :subtitle="`${st.assignees?.map((a:any)=>a.user_name?.split(' ')[0]).join(', ') || '—'} · ${st.due_date ? st.due_date.split('T')[0] : 'без срока'}`"
              @click="openSubtask(st)">
              <template #title>
                <span class="text-body-2">{{ st.title }}</span>
                <v-chip :color="PRIORITY_COLOR[st.priority]||'grey'" size="x-small" variant="flat" class="ml-1">{{ PRIORITY_LABEL[st.priority] }}</v-chip>
                <v-chip :color="st.status==='done'?'success':st.status==='in_progress'?'primary':'warning'" size="x-small" variant="tonal" class="ml-1">{{ {todo:'К выполнению',in_progress:'В работе',done:'Готово'}[st.status]||st.status }}</v-chip>
              </template>
            </v-list-item>
          </v-list>
        </template>

        <!-- Chat section (only for existing tasks) -->
        <template v-if="editingTask">
          <v-divider class="my-3" />
          <div class="d-flex align-center mb-2">
            <v-icon icon="mdi-chat-outline" size="18" class="mr-1" />
            <span class="text-subtitle-2 font-weight-medium">Чат</span>
          </div>
          <ChatEmbed
            :entity-type="'task'"
            :entity-id="editingTask.id"
            :title="editingTask.title"
            :participant-ids="[
              editingTask.created_by_id,
              ...(editingTask.assignees || []).map((a: any) => a.user_id)
            ].filter((id: any) => id != null)"
          />
        </template>
      </v-card-text>
      <v-card-actions>
        <v-btn v-if="editingTask && !isTaskReadonly" color="error" variant="text" @click="deleteTask">Удалить</v-btn>
        <v-btn v-if="editingTask" color="teal" variant="tonal" prepend-icon="mdi-account-arrow-right-outline" size="small" @click="openDelegateDialog">
          Делегировать
        </v-btn>
        <v-spacer />
        <v-btn variant="text" @click="closeDialog">Отмена</v-btn>
        <v-btn v-if="!editingTask || !isTaskReadonly" color="primary" :disabled="!localForm.title" @click="saveTask">{{ editingTask ? 'Сохранить' : 'Создать' }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- Delegation dialog -->
  <v-dialog v-model="showDelegateDialog" max-width="520" :fullscreen="mobile">
    <v-card>
      <v-card-title>Делегировать подзадачу</v-card-title>
      <v-card-text>
        <v-alert type="info" variant="tonal" density="compact" class="mb-3">
          Создаётся подзадача на основе текущей. Вы устанавливаете исполнителя, сроки и приоритет сами.
        </v-alert>
        <v-text-field v-model="delegateForm.title" label="Название задачи *" variant="outlined" density="compact" class="mb-2" />
        <v-textarea v-model="delegateForm.description" label="Описание" variant="outlined" density="compact" rows="2" class="mb-2" />
        <div class="d-flex ga-2 mb-2">
          <v-select v-model="delegateForm.priority" :items="priorityItems" label="Приоритет" variant="outlined" density="compact" style="max-width:200px" />
          <v-text-field v-model="delegateForm.due_date" label="Срок" variant="outlined" density="compact" type="date" :min="todayStr" />
        </div>
        <v-autocomplete v-model="delegateForm.assignee_ids" :items="subordinateItems" label="Исполнители (подчинённые) *" variant="outlined" density="compact" multiple chips closable-chips item-title="text" item-value="value" class="mb-2" />
        <v-switch v-model="delegateForm.import_to_parent" label="Показывать в родительской задаче" color="teal" density="compact" hide-details />
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="showDelegateDialog = false">Отмена</v-btn>
        <v-btn color="teal" :disabled="!delegateForm.title || !delegateForm.assignee_ids.length" :loading="delegateSaving" @click="saveDelegate">Делегировать</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- Broadcast dialog -->
  <v-dialog v-model="broadcastDialog" max-width="480" persistent :fullscreen="mobile">
    <v-card>
      <v-card-title class="d-flex align-center gap-2 pt-4">
        <v-icon color="orange">mdi-bullhorn</v-icon>
        Рассылка из задачи
      </v-card-title>
      <v-card-text>
        <div class="text-caption text-medium-emphasis mb-3">
          Сообщение будет отправлено каждому сотруднику индивидуально в Telegram
        </div>
        <v-radio-group v-model="broadcastScope" class="mb-3">
          <v-radio value="department" label="Отдел" />
          <v-radio value="organization" label="Организация" />
          <v-radio v-if="broadcastOrgs.length > 1" value="all" label="Все организации" />
        </v-radio-group>
        <v-select v-if="broadcastScope === 'department'" v-model="broadcastScopeId"
          :items="broadcastDepts" item-title="name" item-value="id"
          label="Выберите отдел" variant="outlined" density="compact" class="mb-3" />
        <v-select v-if="broadcastScope === 'organization'" v-model="broadcastScopeId"
          :items="broadcastOrgs" item-title="name" item-value="id"
          label="Выберите организацию" variant="outlined" density="compact" class="mb-3" />
        <v-textarea v-model="broadcastText" label="Текст сообщения" variant="outlined"
          density="compact" rows="3" autofocus />
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="broadcastDialog = false">Отмена</v-btn>
        <v-btn color="orange" variant="tonal" :loading="broadcastSending"
          :disabled="!broadcastText.trim() || (broadcastScope !== 'all' && !broadcastScopeId)"
          @click="sendBroadcast">
          Отправить
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useUndoRedo } from '@/composables/useUndoRedo'
import { useRouter } from 'vue-router'
import { useDisplay } from 'vuetify'
import { apiFetch } from '@/api'

const { mobile } = useDisplay()
import ChatEmbed from '@/components/ChatEmbed.vue'

const props = defineProps<{
  show: boolean
  editingTask: any | null
  taskForm: { title: string; description: string; priority: string; due_date: string; assignee_ids: number[]; category: string; org_id: number | null }
  orgSummary: { org_id: number | null; org_name: string; task_count: number; purchase_count: number; unseen_count: number }[]
  currentUserId: number
  userItems: { text: string; value: number }[]
  subordinateIds: Set<number>
  managedOrgUserIds: Set<number>
  taskCategories: string[]
}>()

const emit = defineEmits<{
  (e: 'update:show', v: boolean): void
  (e: 'task-saved', task: any, isNew: boolean): void
  (e: 'task-deleted', taskId: number): void
  (e: 'subtask-added', task: any, parentId: number): void
}>()

const router = useRouter()

// Local copy of form to avoid mutating parent prop directly
const localForm = ref({ ...props.taskForm })

watch(() => props.taskForm, (v) => { localForm.value = { ...v } }, { deep: true })

// Phase 31-07: Undo/Redo for task form (in-memory, no autosave — save on button)
const undoRedo = useUndoRedo(localForm as any)
// Clear undo stack when the dialog opens a new/different task
watch(() => props.editingTask, () => { undoRedo.clear() })
// Blur-driven field snapshot for push
let _taskPendingBlur: { field: string; before: unknown } | null = null
const _taskFocusinHandler = (e: FocusEvent) => {
  const t = e.target as HTMLElement | null
  if (!t) return
  const field = t.dataset?.field || (t.closest('[data-field]') as HTMLElement | null)?.dataset?.field
  if (!field) return
  _taskPendingBlur = { field, before: (localForm.value as any)[field] }
}
const _taskFocusoutHandler = (e: FocusEvent) => {
  if (!_taskPendingBlur) return
  const t = e.target as HTMLElement | null
  if (!t) return
  const field = t.dataset?.field || (t.closest('[data-field]') as HTMLElement | null)?.dataset?.field
  if (field && field === _taskPendingBlur.field) {
    undoRedo.push(field, _taskPendingBlur.before, (localForm.value as any)[field])
  }
  _taskPendingBlur = null
}
onMounted(() => {
  document.addEventListener('focusin', _taskFocusinHandler, true)
  document.addEventListener('focusout', _taskFocusoutHandler, true)
})
onBeforeUnmount(() => {
  document.removeEventListener('focusin', _taskFocusinHandler, true)
  document.removeEventListener('focusout', _taskFocusoutHandler, true)
})

const todayStr = new Date().toISOString().split('T')[0]
const dueDateRule = (v: string) => !v || v >= todayStr || 'Срок не может быть раньше сегодня'

const PRIORITY_LABEL: Record<string, string> = { low: 'Низкий', medium: 'Средний', high: 'Высокий', urgent: 'Срочно' }
const PRIORITY_COLOR: Record<string, string> = { low: 'grey', medium: 'blue', high: 'orange', urgent: 'red' }
const priorityItems = [
  { title: 'Низкий', value: 'low' }, { title: 'Средний', value: 'medium' },
  { title: 'Высокий', value: 'high' }, { title: 'Срочно', value: 'urgent' },
]

const isTaskReadonly = computed(() => {
  if (!props.editingTask) return false
  const role = localStorage.getItem('user_role') || ''
  if (['superadmin', 'org_admin', 'admin'].includes(role)) return false
  const t = props.editingTask
  return (t.assignees || []).some((a: any) => a.user_id === props.currentUserId) && t.created_by_id !== props.currentUserId
})

function isFieldUnseen(fieldName: string): boolean {
  return (props.editingTask?.unseen_fields || []).includes(fieldName)
}

async function dismissField(fieldName: string) {
  if (!props.editingTask) return
  if (!isFieldUnseen(fieldName)) return
  try {
    await apiFetch(`/tasks/${props.editingTask.id}/dismiss-field`, {
      method: 'POST',
      body: { field_name: fieldName } as any,
    })
    props.editingTask.unseen_fields = (props.editingTask.unseen_fields || []).filter((f: string) => f !== fieldName)
    props.editingTask.unseen_changes_count = Math.max(0, (props.editingTask.unseen_changes_count || 0) - 1)
  } catch { /* best-effort */ }
}

// Subtasks
const taskSubtasks = ref<any[]>([])

watch(() => props.editingTask, async (t) => {
  taskSubtasks.value = []
  if (t && (t.subtask_count > 0 || t.import_to_parent)) {
    try { taskSubtasks.value = await apiFetch<any[]>(`/tasks/${t.id}/subtasks`) }
    catch { taskSubtasks.value = [] }
  }
})

function openSubtask(st: any) {
  closeDialog()
  setTimeout(() => emit('task-saved', st, false), 100)
}

// Link purchase
const linkPurchaseDialog = ref(false)
const linkPurchaseSearch = ref('')
const linkPurchaseResults = ref<any[]>([])
const linkPurchaseSearching = ref(false)
let _purchaseSearchTimer: ReturnType<typeof setTimeout> | null = null

function openLinkPurchase() {
  linkPurchaseSearch.value = ''
  linkPurchaseResults.value = []
  linkPurchaseDialog.value = true
}

function searchPurchases(q: string | null) {
  if (_purchaseSearchTimer) clearTimeout(_purchaseSearchTimer)
  if (!q || q.length < 2) { linkPurchaseResults.value = []; return }
  _purchaseSearchTimer = setTimeout(async () => {
    linkPurchaseSearching.value = true
    try {
      linkPurchaseResults.value = await apiFetch<any[]>(`/purchases/?search=${encodeURIComponent(q)}&limit=20`)
    } catch { linkPurchaseResults.value = [] }
    finally { linkPurchaseSearching.value = false }
  }, 300)
}

async function linkPurchaseToTask(purchaseId: number) {
  if (!props.editingTask) return
  try {
    const updated = await apiFetch<any>(`/tasks/${props.editingTask.id}`, {
      method: 'PATCH', body: JSON.stringify({ purchase_id: purchaseId }),
    })
    Object.assign(props.editingTask, updated)
    emit('task-saved', props.editingTask, false)
    linkPurchaseDialog.value = false
  } catch (e: any) { alert(e?.detail || 'Ошибка привязки') }
}

async function unlinkPurchaseFromTask() {
  if (!props.editingTask) return
  try {
    const updated = await apiFetch<any>(`/tasks/${props.editingTask.id}`, {
      method: 'PATCH', body: JSON.stringify({ purchase_id: null }),
    })
    Object.assign(props.editingTask, updated, { purchase_id: null, purchase_subject: null, purchase_number: null, purchase_status: null })
    emit('task-saved', props.editingTask, false)
  } catch (e: any) { alert(e?.detail || 'Ошибка') }
}

// Delegation
const showDelegateDialog = ref(false)
const delegateSaving = ref(false)
const subordinateItems = ref<{ text: string; value: number }[]>([])
const delegateForm = ref({ title: '', description: '', priority: 'medium', due_date: '', assignee_ids: [] as number[], import_to_parent: true })

async function openDelegateDialog() {
  if (!props.editingTask) return
  try {
    const subs = await apiFetch<any[]>(`/users/${props.currentUserId}/subordinates`)
    subordinateItems.value = subs.map((u: any) => ({ text: u.full_name || u.username, value: u.id }))
  } catch { subordinateItems.value = props.userItems }
  delegateForm.value = {
    title: props.editingTask.title,
    description: props.editingTask.description || '',
    priority: props.editingTask.priority || 'medium',
    due_date: props.editingTask.due_date ? props.editingTask.due_date.split('T')[0] : '',
    assignee_ids: [],
    import_to_parent: true,
  }
  showDelegateDialog.value = true
}

async function saveDelegate() {
  if (!props.editingTask || !delegateForm.value.assignee_ids.length) return
  delegateSaving.value = true
  try {
    const body: any = { ...delegateForm.value, parent_task_id: props.editingTask.id }
    if (body.due_date) body.due_date = body.due_date + 'T23:59:59Z'
    else delete body.due_date
    const created = await apiFetch<any>('/tasks/', { method: 'POST', body: JSON.stringify(body) })
    emit('subtask-added', created, props.editingTask.id)
    taskSubtasks.value.push(created)
    showDelegateDialog.value = false
  } catch (e: any) {
    alert(e?.detail || 'Ошибка делегирования')
  } finally {
    delegateSaving.value = false
  }
}

// Broadcast
const broadcastDialog = ref(false)
const broadcastScope = ref<'department' | 'organization' | 'all'>('organization')
const broadcastScopeId = ref<number | null>(null)
const broadcastText = ref('')
const broadcastSending = ref(false)
const broadcastOrgs = ref<{ id: number; name: string }[]>([])
const broadcastDepts = ref<{ id: number; name: string }[]>([])

async function openBroadcastDialog() {
  broadcastText.value = ''
  broadcastScopeId.value = null
  broadcastDialog.value = true
  try {
    const data = await apiFetch<any>('/tasks/broadcast/scopes')
    broadcastOrgs.value = data.organizations || []
    broadcastDepts.value = data.departments || []
    if (broadcastOrgs.value.length === 1) broadcastScopeId.value = broadcastOrgs.value[0].id
  } catch {}
}

async function sendBroadcast() {
  if (!props.editingTask || !broadcastText.value.trim()) return
  broadcastSending.value = true
  try {
    const res = await apiFetch<any>(`/tasks/${props.editingTask.id}/broadcast`, {
      method: 'POST',
      body: JSON.stringify({
        text: broadcastText.value.trim(),
        scope: broadcastScope.value,
        scope_id: broadcastScope.value !== 'all' ? broadcastScopeId.value : undefined,
      }),
    })
    broadcastDialog.value = false
    alert(`Отправлено: ${res.sent} из ${res.total_users} сотрудников`)
  } catch (e: any) {
    alert(e?.detail || 'Ошибка рассылки')
  } finally {
    broadcastSending.value = false
  }
}

// Save / Delete / Close
async function saveTask() {
  const body: any = { ...localForm.value }
  if (body.due_date) body.due_date = body.due_date + 'T23:59:59Z'
  else delete body.due_date
  if (!body.category) delete body.category
  if (!body.assignee_ids?.length) body.assignee_ids = []
  try {
    if (props.editingTask) {
      const updated = await apiFetch<any>(`/tasks/${props.editingTask.id}`, { method: 'PATCH', body: JSON.stringify(body) })
      emit('task-saved', updated, false)
    } else {
      const created = await apiFetch<any>('/tasks/', { method: 'POST', body: JSON.stringify(body) })
      emit('task-saved', created, true)
    }
  } catch (e: any) {
    if (e?.detail) alert(e.detail)
    else console.error(e)
    return
  }
  closeDialog()
}

async function deleteTask() {
  if (!props.editingTask) return
  try { await apiFetch(`/tasks/${props.editingTask.id}`, { method: 'DELETE' }) }
  catch (e) { console.error(e); return }
  emit('task-deleted', props.editingTask.id)
  closeDialog()
}

function closeDialog() {
  emit('update:show', false)
}

// Expose openBroadcastDialog so parent can trigger it if needed (unused currently)
defineExpose({ openBroadcastDialog })
</script>

<style scoped>
/* Field change highlight — click to dismiss */
.field-changed {
  border-radius: 6px;
  outline: 2px solid #F59E0B;
  outline-offset: 2px;
  cursor: pointer;
  transition: outline-color 0.2s;
}
.field-changed:hover {
  outline-color: #D97706;
}
</style>
