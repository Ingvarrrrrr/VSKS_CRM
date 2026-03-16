<template>
  <div>
    <!-- Members section -->
    <div class="mb-4">
      <div class="d-flex align-center mb-2">
        <span class="text-body-2 font-weight-medium">Участники</span>
        <v-spacer />
        <v-btn
          v-if="canManage"
          size="x-small" variant="tonal" color="primary"
          prepend-icon="mdi-account-plus"
          @click="addMemberDialog.show = true">
          Добавить
        </v-btn>
      </div>
      <div v-if="members.length" class="d-flex flex-wrap gap-2">
        <v-chip
          v-for="m in members" :key="m.id"
          size="small" :color="roleColor(m.role)" variant="tonal"
          :title="m.added_by_name ? `Добавил: ${m.added_by_name}` : m.role"
          :closable="canManage"
          @click:close="removeMember(m.user_id)">
          {{ m.full_name || m.username }}
          <span v-if="m.added_by_name" class="text-caption ml-1 opacity-60">↑{{ m.added_by_name.split(' ')[0] }}</span>
        </v-chip>
      </div>
      <div v-else class="text-caption text-medium-emphasis">Нет участников</div>
    </div>

    <v-divider class="mb-3" />

    <!-- Event feed -->
    <div class="d-flex align-center mb-2">
      <span class="text-body-2 font-weight-medium">Чат согласования</span>
      <v-spacer />
      <v-btn size="x-small" variant="text" prepend-icon="mdi-refresh" @click="loadEvents">Обновить</v-btn>
    </div>

    <!-- Add comment -->
    <div class="d-flex gap-2 mb-3 align-start">
      <v-textarea
        v-model="newComment"
        variant="outlined"
        density="compact"
        rows="2"
        placeholder="Добавить комментарий..."
        hide-details
        auto-grow
        style="flex:1"
        @keydown.ctrl.enter="postComment"
      />
      <v-btn
        icon="mdi-send"
        size="small"
        color="primary"
        variant="tonal"
        :disabled="!newComment.trim()"
        @click="postComment"
        title="Отправить (Ctrl+Enter)"
      />
    </div>

    <!-- Events list -->
    <div v-if="loading" class="text-center py-4">
      <v-progress-circular indeterminate size="24" />
    </div>
    <div v-else-if="events.length === 0" class="text-caption text-medium-emphasis text-center py-4">
      Нет событий
    </div>
    <div v-else class="event-feed">
      <div v-for="e in events" :key="e.id" class="event-item">
        <div class="event-icon">
          <v-icon :icon="eventIcon(e.event_type)" :color="eventColor(e.event_type)" size="18" />
        </div>
        <div class="event-body">
          <div class="event-meta">
            <span class="font-weight-medium text-body-2">{{ e.full_name || e.username || 'Система' }}</span>
            <span class="text-caption text-medium-emphasis ml-2">{{ formatTime(e.created_at) }}</span>
          </div>
          <div class="event-text text-body-2">{{ renderEvent(e) }}</div>
        </div>
      </div>
    </div>

    <!-- Add member dialog -->
    <v-dialog v-model="addMemberDialog.show" max-width="400">
      <v-card>
        <v-card-title class="pa-4">Добавить участника</v-card-title>
        <v-card-text class="pa-4 pt-0">
          <v-autocomplete
            v-model="addMemberDialog.user_id"
            :items="availableUsers"
            item-title="display"
            item-value="id"
            label="Пользователь"
            variant="outlined" density="compact" class="mb-3"
            :loading="addMemberDialog.loadingUsers"
          />
          <v-select
            v-model="addMemberDialog.role"
            :items="roleItems"
            item-title="label"
            item-value="value"
            label="Роль"
            variant="outlined" density="compact"
          />
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="addMemberDialog.show = false">Отмена</v-btn>
          <v-btn
            color="primary" variant="flat"
            :disabled="!addMemberDialog.user_id"
            :loading="addMemberDialog.saving"
            @click="addMember">
            Добавить
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { apiFetch } from '@/api'

const props = defineProps<{ purchaseId: number }>()

const canManage = computed(() => {
  const role = localStorage.getItem('user_role')
  return role === 'admin' || role === 'manager'
})

interface Member { id: number; purchase_id: number; user_id: number; role: string; username: string; full_name?: string; added_by_id?: number; added_by_name?: string }
interface Event { id: number; purchase_id: number; user_id?: number; username?: string; full_name?: string; event_type: string; data?: any; created_at: string }
interface UserItem { id: number; username: string; full_name?: string; display?: string }

const members = ref<Member[]>([])
const events = ref<Event[]>([])
const loading = ref(false)
const newComment = ref('')

const roleItems = [
  { value: 'viewer',    label: 'Наблюдатель' },
  { value: 'editor',   label: 'Редактор' },
  { value: 'manager',  label: 'Куратор' },
]

const addMemberDialog = reactive({
  show: false,
  user_id: null as number | null,
  role: 'viewer',
  saving: false,
  loadingUsers: false,
  allUsers: [] as UserItem[],
})

const availableUsers = computed(() =>
  addMemberDialog.allUsers
    .filter(u => !members.value.some(m => m.user_id === u.id))
    .map(u => ({ ...u, display: u.full_name ? `${u.full_name} (${u.username})` : u.username }))
)

const roleColor = (role: string) =>
  ({ viewer: 'blue-grey', editor: 'blue', manager: 'teal' }[role] || 'grey')

const eventIcon = (type: string) => {
  const icons: Record<string, string> = {
    status_changed: 'mdi-swap-horizontal',
    comment: 'mdi-comment-outline',
    file_uploaded: 'mdi-file-plus-outline',
    member_added: 'mdi-account-plus-outline',
    member_removed: 'mdi-account-minus-outline',
    created: 'mdi-plus-circle-outline',
  }
  return icons[type] || 'mdi-circle-small'
}

const eventColor = (type: string) => {
  const colors: Record<string, string> = {
    status_changed: 'blue',
    comment: 'green',
    file_uploaded: 'purple',
    member_added: 'teal',
    member_removed: 'red',
    created: 'primary',
  }
  return colors[type] || 'grey'
}

const STATUS_LABELS: Record<string, string> = {
  planned: 'Планирование', confirmed: 'Подтверждена', in_progress: 'В работе',
  contracted: 'Законтрактована', delivered: 'Поставлена', paid: 'Оплачена',
}

function renderEvent(e: Event): string {
  if (e.event_type === 'status_changed' && e.data) {
    const from = STATUS_LABELS[e.data.from] || e.data.from
    const to = STATUS_LABELS[e.data.to] || e.data.to
    return `Статус изменён: ${from} → ${to}`
  }
  if (e.event_type === 'comment' && e.data?.text) return e.data.text
  if (e.event_type === 'file_uploaded' && e.data?.name) return `Загружен файл: ${e.data.name}`
  if (e.event_type === 'member_added' && e.data?.username) return `Добавлен участник: ${e.data.username}`
  if (e.event_type === 'member_removed' && e.data?.username) return `Удалён участник: ${e.data.username}`
  if (e.event_type === 'created') return 'Закупка создана'
  return e.event_type
}

function formatTime(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const diff = (now.getTime() - d.getTime()) / 1000
  if (diff < 60) return 'только что'
  if (diff < 3600) return `${Math.floor(diff / 60)} мин назад`
  if (diff < 86400) return `${Math.floor(diff / 3600)} ч назад`
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' })
}

async function loadEvents() {
  loading.value = true
  try {
    events.value = await apiFetch<Event[]>(`/purchases/${props.purchaseId}/events`)
  } finally {
    loading.value = false
  }
}

async function loadMembers() {
  members.value = await apiFetch<Member[]>(`/purchases/${props.purchaseId}/members`)
}

async function postComment() {
  const text = newComment.value.trim()
  if (!text) return
  newComment.value = ''
  try {
    const ev = await apiFetch<Event>(`/purchases/${props.purchaseId}/events`, {
      method: 'POST',
      body: { event_type: 'comment', data: { text } },
    })
    events.value = [ev, ...events.value]
  } catch {}
}

async function addMember() {
  if (!addMemberDialog.user_id) return
  addMemberDialog.saving = true
  try {
    const m = await apiFetch<Member>(`/purchases/${props.purchaseId}/members`, {
      method: 'POST',
      body: { user_id: addMemberDialog.user_id, role: addMemberDialog.role },
    })
    members.value = [...members.value, m]
    addMemberDialog.show = false
    const u = addMemberDialog.allUsers.find(x => x.id === addMemberDialog.user_id)
    if (u) {
      events.value = [{ id: Date.now(), purchase_id: props.purchaseId, event_type: 'member_added',
        data: { username: u.full_name || u.username }, created_at: new Date().toISOString() }, ...events.value]
    }
  } catch {} finally {
    addMemberDialog.saving = false
  }
}

async function removeMember(userId: number) {
  try {
    await apiFetch(`/purchases/${props.purchaseId}/members/${userId}`, { method: 'DELETE' })
    const removed = members.value.find(m => m.user_id === userId)
    members.value = members.value.filter(m => m.user_id !== userId)
    if (removed) {
      events.value = [{ id: Date.now(), purchase_id: props.purchaseId, event_type: 'member_removed',
        data: { username: removed.full_name || removed.username }, created_at: new Date().toISOString() }, ...events.value]
    }
  } catch {}
}

watch(() => addMemberDialog.show, async (v) => {
  if (v && addMemberDialog.allUsers.length === 0) {
    addMemberDialog.loadingUsers = true
    try {
      const users = await apiFetch<UserItem[]>('/users/')
      addMemberDialog.allUsers = users
    } finally {
      addMemberDialog.loadingUsers = false
    }
  }
})

onMounted(() => {
  loadMembers()
  loadEvents()
})
</script>

<style scoped>
.event-feed { display: flex; flex-direction: column; gap: 12px; }
.event-item { display: flex; gap: 10px; align-items: flex-start; }
.event-icon { margin-top: 2px; flex-shrink: 0; }
.event-body { flex: 1; min-width: 0; }
.event-meta { display: flex; align-items: baseline; flex-wrap: wrap; }
.event-text { color: var(--crm-text-secondary); word-break: break-word; white-space: pre-wrap; }
</style>
