<template>
  <div class="chat-embed">
    <!-- Loading state -->
    <div v-if="loading" class="d-flex justify-center align-center pa-4">
      <v-progress-circular indeterminate size="28" />
    </div>

    <!-- Error state -->
    <div v-else-if="error" class="text-caption text-error pa-3">{{ error }}</div>

    <!-- Chat UI -->
    <template v-else-if="roomId">
      <!-- Add participant toolbar -->
      <div class="d-flex align-center px-2 pt-1 gap-1" style="flex-shrink:0">
        <v-chip v-for="p in roomParticipants" :key="p.id" size="x-small" variant="tonal" class="mr-1">
          {{ p.full_name.split(' ')[0] }}
        </v-chip>
        <v-spacer />
        <v-menu v-model="addParticipantMenu" :close-on-content-click="false" location="bottom end" max-width="400" @update:model-value="v => v && loadStaff()">
          <template #activator="{ props: menuProps }">
            <v-btn v-bind="menuProps" icon="mdi-account-plus" variant="text" size="x-small" title="Добавить участника" />
          </template>
          <v-card min-width="360">
            <v-card-title class="text-subtitle-2 pa-3 pb-1">Добавить участника</v-card-title>
            <v-card-text class="pa-3 pt-1">
              <v-autocomplete
                v-model="addParticipantId"
                :items="groupedStaff"
                item-title="full_name"
                item-value="id"
                label="Поиск сотрудника"
                variant="outlined"
                density="compact"
                hide-no-data
                hide-details
                autofocus
                @update:model-value="doAddParticipant"
              >
                <template #item="{ item, props: itemProps }">
                  <v-list-subheader v-if="item.raw._header" :key="item.raw._header">{{ item.raw._header }}</v-list-subheader>
                  <v-list-item v-else v-bind="itemProps">
                    <template #title>{{ item.raw.full_name }}</template>
                    <template #subtitle>{{ item.raw.position || '' }}</template>
                  </v-list-item>
                </template>
              </v-autocomplete>
            </v-card-text>
          </v-card>
        </v-menu>
      </div>
      <!-- Messages -->
      <div ref="messagesEl" class="chat-embed__messages" @scroll.passive="onScroll">
        <div v-if="loadingMore" class="d-flex justify-center py-2">
          <v-progress-circular indeterminate size="20" />
        </div>
        <div
          v-for="msg in messages"
          :key="msg.id"
          class="chat-embed__msg"
          :class="msg.sender_id === myId ? 'chat-embed__msg--mine' : 'chat-embed__msg--other'"
        >
          <div class="chat-embed__msg-meta">
            <span class="chat-embed__msg-author">{{ msg.sender_name }}</span>
            <span class="chat-embed__msg-time">{{ formatTime(msg.created_at) }}</span>
          </div>
          <!-- Image inline -->
          <template v-if="msg.has_file && msg.file_mime?.startsWith('image/')">
            <img
              :src="fileUrl(msg.id)"
              :alt="msg.file_name ?? 'image'"
              class="chat-embed__img"
              loading="lazy"
            />
          </template>
          <!-- File chip -->
          <template v-else-if="msg.has_file">
            <a :href="fileUrl(msg.id)" target="_blank" class="chat-embed__file-link">
              <v-icon icon="mdi-paperclip" size="14" class="mr-1" />{{ msg.file_name }}
            </a>
          </template>
          <!-- Text -->
          <div v-if="msg.content" class="chat-embed__msg-text" v-html="renderMentions(msg.content)" />
        </div>
        <div v-if="messages.length === 0" class="text-caption text-medium-emphasis text-center pa-4">
          Начните обсуждение
        </div>
      </div>

      <!-- Input -->
      <div class="chat-embed__input-wrap">
        <!-- Mention dropdown -->
        <div v-if="mentionOpen && mentionCandidates.length" class="chat-embed__mention-dropdown">
          <div
            v-for="p in mentionCandidates"
            :key="p.id"
            class="chat-embed__mention-item"
            @mousedown.prevent="insertEmbedMention(p)"
          >
            {{ p.full_name }}
          </div>
        </div>
        <div class="chat-embed__input">
          <!-- @ button -->
          <v-btn icon="mdi-at" variant="text" size="x-small" :disabled="sending" title="Упомянуть" @click="insertAt" />
          <!-- рупор: mention all (only in groups) -->
          <v-btn
            v-if="roomParticipants.length > 2"
            icon="mdi-bullhorn-outline"
            variant="text"
            size="x-small"
            :disabled="sending"
            title="Упомянуть всех"
            @click="mentionAllEmbed"
          />
          <v-textarea
            v-model="inputText"
            placeholder="Сообщение... (Enter — отправить)"
            variant="outlined"
            density="compact"
            rows="1"
            auto-grow
            max-rows="4"
            hide-details
            class="flex-grow-1"
            @input="onEmbedInput"
            @keydown.enter.exact.prevent="sendMessage"
            @keydown.shift.enter.exact="() => {}"
          />
          <v-btn
            icon="mdi-send"
            color="primary"
            variant="flat"
            size="small"
            class="ml-2 mt-1"
            :disabled="!inputText.trim() || sending"
            :loading="sending"
            @click="sendMessage"
          />
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { onChatEvent, roomParticipantCounts } from '@/composables/useChat'
import { apiFetch } from '@/api'

const props = defineProps<{
  entityType: 'purchase' | 'task'
  entityId: number
  title?: string
  participantIds?: number[]
}>()

const loading = ref(true)
const error = ref<string | null>(null)
const roomId = ref<number | null>(null)
const messages = ref<any[]>([])
const inputText = ref('')
const sending = ref(false)
const loadingMore = ref(false)
const messagesEl = ref<HTMLElement | null>(null)
const myId = Number(localStorage.getItem('user_id') ?? '0')
let oldestId: number | null = null
let allLoaded = false

const mentionOpen = ref(false)
const mentionFilter = ref('')
const mentionCursorPos = ref(0)
const roomParticipants = ref<{id: number, full_name: string}[]>([])
const addParticipantMenu = ref(false)
const addParticipantId = ref<number | null>(null)
const availableStaff = ref<{id: number, full_name: string, department?: string, position?: string}[]>([])

const groupedStaff = computed(() => {
  const byDept: Record<string, typeof availableStaff.value> = {}
  for (const s of availableStaff.value) {
    const dept = s.department || 'Без отдела'
    if (!byDept[dept]) byDept[dept] = []
    byDept[dept].push(s)
  }
  const result: any[] = []
  for (const [dept, members] of Object.entries(byDept).sort(([a], [b]) => a.localeCompare(b))) {
    result.push({ _header: dept, id: `hdr_${dept}`, full_name: dept })
    result.push(...members)
  }
  return result
})

async function loadStaff() {
  try {
    const staff = await apiFetch<any[]>('/chat/staff')
    const participantIds = new Set(roomParticipants.value.map(p => p.id))
    availableStaff.value = staff
      .filter(s => !participantIds.has(s.id))
      .map(s => ({ id: s.id, full_name: s.full_name, department: s.department, position: s.position }))
  } catch { availableStaff.value = [] }
}

async function doAddParticipant(userId: number | null) {
  if (!userId || !roomId.value) return
  try {
    await apiFetch(`/chat/rooms/${roomId.value}/participants`, {
      method: 'POST',
      body: { user_id: userId },
    })
    const user = availableStaff.value.find(s => s.id === userId)
    if (user) {
      roomParticipants.value.push(user)
      availableStaff.value = availableStaff.value.filter(s => s.id !== userId)
    }
    addParticipantId.value = null
    addParticipantMenu.value = false
  } catch {}
}

function formatTime(dt: string) {
  return new Date(dt).toLocaleString('ru', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' })
}

function fileUrl(msgId: number) {
  const token = localStorage.getItem('auth_token') ?? ''
  return `/api/chat/rooms/${roomId.value}/files/${msgId}?token=${encodeURIComponent(token)}`
}

function renderMentions(text: string) {
  return text.replace(/@([\w\u0400-\u04FF][\w\u0400-\u04FF ]*)/g,
    '<span class="chat-mention">@$1</span>')
}

async function loadMessages() {
  if (!roomId.value) return
  try {
    const data = await apiFetch<any[]>(`/chat/rooms/${roomId.value}/messages?limit=30`)
    messages.value = data
    if (data.length > 0) oldestId = data[0].id
    if (data.length < 30) allLoaded = true
    await nextTick()
    scrollToBottom()
  } catch {}
}

async function loadMore() {
  if (!roomId.value || allLoaded || loadingMore.value || !oldestId) return
  loadingMore.value = true
  try {
    const data = await apiFetch<any[]>(`/chat/rooms/${roomId.value}/messages?before_id=${oldestId}&limit=30`)
    if (data.length === 0) { allLoaded = true; return }
    messages.value = [...data, ...messages.value]
    oldestId = data[0].id
    if (data.length < 30) allLoaded = true
  } catch {} finally {
    loadingMore.value = false
  }
}

function onScroll(e: Event) {
  const el = e.target as HTMLElement
  if (el.scrollTop < 60) loadMore()
}

function scrollToBottom() {
  if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
}

async function sendMessage() {
  if (!inputText.value.trim() || !roomId.value || sending.value) return
  sending.value = true
  const text = inputText.value
  inputText.value = ''
  try {
    const form = new FormData()
    form.append('content', text)
    const token = localStorage.getItem('auth_token') ?? ''
    const res = await fetch(`/api/chat/rooms/${roomId.value}/messages`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: form,
    })
    if (res.ok) {
      const msg = await res.json()
      messages.value.push(msg)
      await nextTick()
      scrollToBottom()
    }
  } catch {} finally {
    sending.value = false
  }
}

async function markRead() {
  if (!roomId.value) return
  try {
    await apiFetch(`/chat/rooms/${roomId.value}/read`, { method: 'POST' })
  } catch {}
}

const mentionCandidates = computed(() => {
  if (!mentionOpen.value) return []
  const myId2 = myId
  return roomParticipants.value
    .filter(p => p.id !== myId2)
    .filter(p => !mentionFilter.value || p.full_name.toLowerCase().includes(mentionFilter.value.toLowerCase()))
})

function onEmbedInput() {
  const val = inputText.value
  const pos = val.length
  const match = val.match(/@([\w\u0400-\u04FF ]*)$/)
  if (match) {
    mentionFilter.value = match[1]
    mentionOpen.value = true
    mentionCursorPos.value = pos - match[0].length
  } else {
    mentionOpen.value = false
  }
}

function insertEmbedMention(p: {id: number, full_name: string}) {
  const before = inputText.value.slice(0, mentionCursorPos.value)
  inputText.value = before + '@' + p.full_name + ' '
  mentionOpen.value = false
}

function insertAt() {
  inputText.value += '@'
  mentionFilter.value = ''
  mentionOpen.value = true
  mentionCursorPos.value = inputText.value.length - 1
}

function mentionAllEmbed() {
  const myId2 = myId
  const others = roomParticipants.value.filter(p => p.id !== myId2)
  inputText.value = others.map(p => '@' + p.full_name).join(' ') + ' ' + inputText.value
}

// Subscribe to WS events for real-time messages
const unsubscribe = onChatEvent((event) => {
  if (event.type === 'message' && event.room_id === roomId.value && event.message) {
    // Avoid duplicate if we already added from optimistic send
    if (!messages.value.find(m => m.id === event.message.id)) {
      messages.value.push(event.message)
      nextTick().then(scrollToBottom)
    }
    markRead()
  }
})

onMounted(async () => {
  try {
    const roomTitle = props.title ?? `${props.entityType} #${props.entityId}`
    const body = {
      entity_type: props.entityType,
      entity_id: props.entityId,
      name: roomTitle,
      participant_ids: props.participantIds ?? [],
    }
    const token = localStorage.getItem('auth_token') ?? ''
    const res = await fetch('/api/chat/rooms/for-entity', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify(body),
    })
    if (!res.ok) throw new Error('Не удалось загрузить чат')
    const room = await res.json()
    roomId.value = room.id
    // Cache participant count for sound notifications
    if (room.participants?.length) {
      roomParticipantCounts.value[room.id] = room.participants.length
      roomParticipants.value = room.participants
    }
    await loadMessages()
    markRead()
  } catch (e: any) {
    error.value = e.message ?? 'Ошибка загрузки чата'
  } finally {
    loading.value = false
  }
})

onUnmounted(() => {
  unsubscribe()
  if (roomId.value) {
    delete roomParticipantCounts.value[roomId.value]
  }
})
</script>

<style scoped>
.chat-embed {
  display: flex;
  flex-direction: column;
  height: 320px;
  min-height: 200px;
}
.chat-embed__messages {
  flex: 1 1 0;
  min-height: 0;
  overflow-y: auto;
  padding: 8px;
}
.chat-embed__msg {
  margin-bottom: 8px;
  padding: 6px 10px;
  border-radius: 12px;
  max-width: 85%;
  position: relative;
  word-break: break-word;
}
.chat-embed__msg--mine {
  background: #1976d2;
  color: white;
  margin-left: auto;
  border-bottom-right-radius: 4px;
}
.chat-embed__msg--other {
  background: var(--crm-surface-hover);
  border: 1px solid var(--crm-border-strong);
  border-bottom-left-radius: 4px;
}
.chat-embed__msg-meta {
  display: flex;
  gap: 6px;
  align-items: center;
  font-size: 11px;
  margin-bottom: 2px;
  opacity: 0.75;
}
.chat-embed__msg-text {
  font-size: 13px;
  line-height: 1.4;
}
.chat-embed__img {
  max-width: 240px;
  max-height: 180px;
  border-radius: 8px;
  display: block;
  margin-top: 4px;
}
.chat-embed__file-link {
  font-size: 12px;
  display: inline-flex;
  align-items: center;
  text-decoration: none;
  color: inherit;
  opacity: 0.9;
}
.chat-embed__input-wrap {
  position: relative;
  flex-shrink: 0;
}
.chat-embed__mention-dropdown {
  position: absolute;
  bottom: 100%;
  left: 0;
  right: 0;
  background: rgb(var(--v-theme-surface));
  border: 1px solid var(--crm-border-strong);
  border-radius: 8px;
  box-shadow: 0 -4px 16px rgba(0,0,0,0.1);
  max-height: 160px;
  overflow-y: auto;
  z-index: 200;
}
.chat-embed__mention-item {
  padding: 6px 12px;
  cursor: pointer;
  font-size: 12px;
  transition: background 0.15s;
}
.chat-embed__mention-item:hover {
  background: var(--crm-surface-hover);
}
.chat-embed__input {
  display: flex;
  align-items: flex-end;
  padding: 6px 8px;
  border-top: 1px solid var(--crm-border);
  flex-shrink: 0;
}
:deep(.chat-mention) {
  color: #1976d2;
  font-weight: 600;
}
.chat-embed__msg--mine :deep(.chat-mention) {
  color: #bbdefb;
}
</style>
