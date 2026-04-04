<template>
  <div class="chat-layout">
    <!-- Sidebar: Chat list -->
    <v-navigation-drawer
      v-if="showSidebar"
      :permanent="smAndUp"
      :temporary="!smAndUp"
      :model-value="showSidebar"
      width="320"
      class="chat-sidebar"
    >
      <!-- Header -->
      <v-list-item class="py-3 px-4">
        <template #prepend>
          <v-icon icon="mdi-chat" class="me-2" />
        </template>
        <v-list-item-title class="text-h6 font-weight-bold">Чат</v-list-item-title>
        <template #append>
          <v-btn
            icon="mdi-plus"
            variant="text"
            size="small"
            @click="openNewChatDialog"
          />
        </template>
      </v-list-item>

      <v-divider />

      <!-- Search field -->
      <div class="px-3 pt-2 pb-1">
        <v-text-field
          v-model="searchQuery"
          :placeholder="selectedRoom ? 'Поиск в чате...' : 'Поиск по чатам...'"
          prepend-inner-icon="mdi-magnify"
          variant="outlined"
          density="compact"
          hide-details
          clearable
          @click:clear="searchQuery = ''"
        />
      </div>

      <!-- Room list -->
      <v-list v-if="filteredRooms.length > 0" lines="two" nav class="pa-1">
        <v-list-item
          v-for="room in filteredRooms"
          :key="room.id"
          :class="{ 'bg-primary-lighten-4': selectedRoom?.id === room.id }"
          :active="selectedRoom?.id === room.id"
          rounded="lg"
          class="mb-1"
          @click="selectRoom(room)"
        >
          <template #prepend>
            <v-avatar :color="roomColor(room)" size="44">
              <span class="text-subtitle-1 font-weight-bold text-white">
                {{ roomInitial(room) }}
              </span>
            </v-avatar>
          </template>

          <v-list-item-title class="font-weight-medium">
            {{ roomDisplayName(room) }}
          </v-list-item-title>
          <v-list-item-subtitle class="text-truncate">
            {{ room.last_message?.content || (room.last_message?.has_file ? '📎 Файл' : 'Нет сообщений') }}
          </v-list-item-subtitle>

          <template #append>
            <div class="d-flex flex-column align-end">
              <span v-if="room.last_message" class="text-caption text-medium-emphasis mb-1">
                {{ formatTime(room.last_message.created_at) }}
              </span>
              <v-badge
                v-if="room.unread_count > 0"
                :content="room.unread_count"
                color="primary"
                inline
              />
            </div>
          </template>
        </v-list-item>
      </v-list>

      <v-empty-state
        v-else
        icon="mdi-chat-outline"
        text="Нет чатов"
        class="mt-8"
      />
    </v-navigation-drawer>

    <!-- Main message area -->
    <div class="chat-main flex-grow-1">
      <!-- No room selected placeholder -->
      <div v-if="!selectedRoom" class="d-flex flex-column align-center justify-center fill-height text-medium-emphasis">
        <v-icon icon="mdi-chat-outline" size="80" class="mb-4 opacity-30" />
        <p class="text-h6">Выберите чат</p>
        <p class="text-body-2">Или создайте новый с помощью кнопки «+»</p>
      </div>

      <template v-else>
        <!-- Toolbar -->
        <v-toolbar density="compact" elevation="1" class="flex-shrink-0 chat-toolbar">
          <!-- Back button on mobile -->
          <v-btn
            v-if="!smAndUp"
            icon="mdi-arrow-left"
            variant="text"
            @click="backToList"
          />
          <v-avatar :color="roomColor(selectedRoom)" size="36" class="ms-2">
            <span class="text-body-2 font-weight-bold text-white">
              {{ roomInitial(selectedRoom) }}
            </span>
          </v-avatar>
          <v-toolbar-title class="ms-3">
            <div class="font-weight-medium">{{ roomDisplayName(selectedRoom) }}</div>
            <div class="text-caption text-medium-emphasis">
              {{ selectedRoom.is_group ? `${selectedRoom.participants.length} участников` : 'Личный чат' }}
            </div>
          </v-toolbar-title>
          <template #append>
            <v-icon
              :icon="wsConnected ? 'mdi-wifi' : 'mdi-wifi-off'"
              :color="wsConnected ? 'success' : 'error'"
              size="18"
              class="me-2"
            />
          </template>
        </v-toolbar>

        <!-- Messages area -->
        <div
          ref="messagesContainer"
          class="chat-messages flex-grow-1 overflow-y-auto pa-3"
          @scroll="onScroll"
        >
          <!-- Load more indicator -->
          <div v-if="loadingMessages" class="text-center py-2">
            <v-progress-circular indeterminate size="24" />
          </div>

          <!-- Messages -->
          <template v-for="(item, idx) in messagesWithSeparators" :key="'type' in item ? 'sep-' + item.date + idx : item.id">
            <!-- Date separator -->
            <div v-if="'type' in item" class="date-separator">
              <span>{{ item.date }}</span>
            </div>

            <!-- Message bubble -->
            <div
              v-else
              class="message-row"
              :class="item.sender_id === currentUserId ? 'message-row-self' : 'message-row-other'"
            >
              <!-- Avatar (only if showAvatar) -->
              <v-avatar
                v-if="item.sender_id !== currentUserId && item.showAvatar"
                :color="stringToColor(item.sender_name || '')"
                size="32"
                class="message-avatar"
              >
                <span class="text-caption text-white">{{ (item.sender_name || '?')[0] }}</span>
              </v-avatar>
              <div v-else-if="item.sender_id !== currentUserId" class="message-avatar-spacer" />

              <div
                class="message-bubble"
                :class="item.sender_id === currentUserId ? 'bubble-self' : 'bubble-other'"
              >
                <!-- Sender name (only if showAvatar and not self) -->
                <div v-if="item.showAvatar && item.sender_id !== currentUserId" class="message-sender">
                  {{ item.sender_name }}
                </div>

                <!-- Text content -->
                <div v-if="item.content" class="message-text" v-html="highlightSearch(item.content || '')"></div>

                <!-- File attachment -->
                <div v-if="item.has_file && item.file_name" class="message-file">
                  <!-- Inline image preview -->
                  <a
                    v-if="isImage(item)"
                    :href="`/api/chat/rooms/${selectedRoom.id}/files/${item.id}`"
                    target="_blank"
                    class="message-image-link"
                  >
                    <img
                      :src="`/api/chat/rooms/${selectedRoom.id}/files/${item.id}`"
                      :alt="item.file_name"
                      class="message-image"
                      loading="lazy"
                    />
                  </a>
                  <!-- Non-image file chip -->
                  <v-chip
                    v-else
                    :href="`/api/chat/rooms/${selectedRoom.id}/files/${item.id}`"
                    target="_blank"
                    prepend-icon="mdi-paperclip"
                    size="small"
                    variant="tonal"
                    class="mt-1 text-decoration-none"
                    :class="item.sender_id === currentUserId ? 'bg-white text-primary' : 'bg-primary-lighten-5'"
                    style="cursor: pointer;"
                  >
                    {{ item.file_name }}
                    <span v-if="item.file_size" class="ms-1 text-caption opacity-70">
                      ({{ formatSize(item.file_size) }})
                    </span>
                  </v-chip>
                </div>

                <!-- Timestamp -->
                <div class="message-time">
                  {{ formatDateTime(item.created_at) }}
                  <v-icon
                    v-if="item.sender_id === currentUserId"
                    size="14"
                    class="ms-1"
                    :color="selectedRoom?.unread_count === 0 ? 'blue' : 'grey'"
                  >mdi-check-all</v-icon>
                </div>
              </div>
            </div>
          </template>

          <!-- Empty state -->
          <div v-if="filteredMessages.length === 0 && !loadingMessages" class="text-center mt-8 text-medium-emphasis">
            <v-icon icon="mdi-message-outline" size="48" class="mb-2 opacity-30" />
            <p class="text-body-2">Нет сообщений. Начните переписку!</p>
          </div>
        </div>

        <!-- Input area -->
        <div class="chat-input pa-3 flex-shrink-0">
          <!-- Selected file preview -->
          <v-chip
            v-if="fileInput"
            closable
            prepend-icon="mdi-paperclip"
            class="mb-2"
            @click:close="fileInput = null"
          >
            {{ fileInput.name }}
          </v-chip>

          <div class="d-flex align-end gap-2">
            <!-- Hidden file input -->
            <input
              ref="fileInputEl"
              type="file"
              accept=".pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png"
              style="display: none"
              @change="onFileSelected"
            />

            <!-- Attach button -->
            <v-btn
              icon="mdi-paperclip"
              variant="text"
              :disabled="sending"
              @click="fileInputEl?.click()"
            />

            <!-- Text field -->
            <v-text-field
              v-model="inputText"
              placeholder="Написать сообщение..."
              variant="outlined"
              density="compact"
              hide-details
              class="flex-grow-1"
              :disabled="sending"
              @keydown.enter.exact.prevent="sendMessage"
              @keydown.enter.shift.exact="inputText += '\n'"
            />

            <!-- Send button -->
            <v-btn
              icon="mdi-send"
              color="primary"
              :disabled="(!inputText.trim() && !fileInput) || sending"
              :loading="sending"
              @click="sendMessage"
            />
          </div>
        </div>
      </template>
    </div>

    <!-- New Chat Dialog -->
    <v-dialog v-model="showNewChatDialog" max-width="500" scrollable>
      <v-card>
        <v-card-title class="d-flex align-center">
          <v-icon icon="mdi-chat-plus" class="me-2" />
          Новый чат
        </v-card-title>
        <v-card-text>
          <!-- Staff search -->
          <v-text-field
            v-model="staffSearch"
            placeholder="Поиск сотрудника..."
            prepend-inner-icon="mdi-magnify"
            variant="outlined"
            density="compact"
            class="mb-3"
            clearable
          />

          <!-- Staff list -->
          <v-list lines="two" max-height="300" class="overflow-y-auto border rounded">
            <v-list-item
              v-for="person in filteredStaff"
              :key="person.id"
              :class="{ 'bg-primary-lighten-5': selectedStaffIds.includes(person.id) }"
              rounded
              @click="toggleStaff(person.id)"
            >
              <template #prepend>
                <v-avatar color="secondary" size="36">
                  <span class="text-body-2 text-white">{{ person.full_name.charAt(0) }}</span>
                </v-avatar>
              </template>
              <v-list-item-title>{{ person.full_name }}</v-list-item-title>
              <v-list-item-subtitle>{{ person.department || person.position || person.username }}</v-list-item-subtitle>
              <template #append>
                <v-checkbox-btn :model-value="selectedStaffIds.includes(person.id)" readonly />
              </template>
            </v-list-item>
            <v-empty-state
              v-if="filteredStaff.length === 0"
              icon="mdi-account-search"
              text="Сотрудники не найдены"
              class="py-4"
            />
          </v-list>

          <!-- Group name (shown when 2+ selected) -->
          <v-text-field
            v-if="selectedStaffIds.length >= 2"
            v-model="newGroupName"
            label="Название группы"
            variant="outlined"
            density="compact"
            class="mt-3"
            prepend-inner-icon="mdi-account-group"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="closeNewChatDialog">Отмена</v-btn>
          <v-btn
            color="primary"
            variant="flat"
            :disabled="selectedStaffIds.length === 0 || (selectedStaffIds.length >= 2 && !newGroupName.trim())"
            :loading="creatingChat"
            @click="createChat"
          >
            {{ selectedStaffIds.length === 1 ? 'Написать' : 'Создать группу' }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useDisplay } from 'vuetify'
import { apiFetch } from '@/api'
import { wsConnected, onChatEvent, connect } from '@/composables/useChat'

// ─── Types ────────────────────────────────────────────────────────────────────

interface LastMessage {
  id: number
  content: string | null
  sender_name: string | null
  created_at: string
  has_file: boolean
}

interface Participant {
  id: number
  full_name: string
  username: string
  avatar: string | null
  department: string | null
  position: string | null
}

interface Room {
  id: number
  name: string | null
  is_group: boolean
  org_id: number
  created_at: string
  last_message: LastMessage | null
  unread_count: number
  participants: Participant[]
}

interface Message {
  id: number
  room_id: number
  sender_id: number | null
  sender_name: string | null
  content: string | null
  file_name: string | null
  file_mime: string | null
  file_size: number | null
  has_file: boolean
  created_at: string
}

interface StaffMember {
  id: number
  full_name: string
  username: string
  avatar: string | null
  department: string | null
  position: string | null
}

// ─── Composables ──────────────────────────────────────────────────────────────

const { smAndUp } = useDisplay()

// ─── State ────────────────────────────────────────────────────────────────────

const rooms = ref<Room[]>([])
const selectedRoom = ref<Room | null>(null)
const messages = ref<Message[]>([])
const inputText = ref('')
const fileInput = ref<File | null>(null)
const fileInputEl = ref<HTMLInputElement | null>(null)
const messagesContainer = ref<HTMLElement | null>(null)
const loadingMessages = ref(false)
const sending = ref(false)

// New chat dialog
const showNewChatDialog = ref(false)
const staff = ref<StaffMember[]>([])
const staffSearch = ref('')
const selectedStaffIds = ref<number[]>([])
const newGroupName = ref('')
const creatingChat = ref(false)

// Current user
const currentUserId = ref<number | null>(null)

// Mobile: show sidebar or messages
const showingSidebar = ref(true)

// Search
const searchQuery = ref('')

// ─── Computed ─────────────────────────────────────────────────────────────────

const showSidebar = computed(() => {
  if (smAndUp.value) return true
  return !selectedRoom.value || showingSidebar.value
})

const filteredStaff = computed(() => {
  const q = staffSearch.value.toLowerCase()
  if (!q) return staff.value
  return staff.value.filter(p =>
    p.full_name.toLowerCase().includes(q) ||
    (p.department || '').toLowerCase().includes(q) ||
    (p.position || '').toLowerCase().includes(q)
  )
})

const filteredRooms = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return rooms.value
  return rooms.value.filter(r =>
    roomDisplayName(r).toLowerCase().includes(q) ||
    (r.last_message?.content || '').toLowerCase().includes(q)
  )
})

const filteredMessages = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q || !selectedRoom.value) return messages.value
  return messages.value.filter(m =>
    (m.content || '').toLowerCase().includes(q) ||
    (m.sender_name || '').toLowerCase().includes(q)
  )
})

// Clear search on room switch
watch(selectedRoom, () => { searchQuery.value = '' })

// ─── Telegram-style types & computed ─────────────────────────────────────────

interface DateSeparator { type: 'separator'; date: string }
type MessageOrSeparator = (Message & { showAvatar?: boolean }) | DateSeparator

const messagesWithSeparators = computed((): MessageOrSeparator[] => {
  const source = filteredMessages.value
  const result: MessageOrSeparator[] = []
  let lastDate = ''
  let lastSenderId: number | null = null
  let lastTime: number | null = null

  for (const msg of source) {
    const d = new Date(msg.created_at).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' })
    if (d !== lastDate) {
      result.push({ type: 'separator', date: d })
      lastDate = d
      lastSenderId = null
      lastTime = null
    }

    const msgTime = new Date(msg.created_at).getTime()
    const showAvatar = msg.sender_id !== lastSenderId ||
      (lastTime !== null && msgTime - lastTime > 2 * 60 * 1000)

    result.push({ ...msg, showAvatar })
    lastSenderId = msg.sender_id
    lastTime = msgTime
  }
  return result
})

// ─── Colors ───────────────────────────────────────────────────────────────────

const COLORS = ['blue', 'teal', 'deep-purple', 'indigo', 'cyan', 'green', 'orange', 'pink']

function colorFromId(id: number): string {
  return COLORS[id % COLORS.length]
}

function roomColor(room: Room): string {
  return colorFromId(room.id)
}

function senderColor(senderId: number | null): string {
  return colorFromId(senderId ?? 0)
}

function stringToColor(str: string): string {
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash)
  }
  const colors = ['#E57373', '#81C784', '#64B5F6', '#FFD54F', '#BA68C8', '#4DB6AC', '#FF8A65', '#A1887F']
  return colors[Math.abs(hash) % colors.length]
}

// ─── Display helpers ─────────────────────────────────────────────────────────

function roomDisplayName(room: Room): string {
  if (room.is_group) return room.name || 'Группа'
  // For direct chat: show the other participant's name
  const other = room.participants.find(p => p.id !== currentUserId.value)
  return other?.full_name || room.name || 'Чат'
}

function roomInitial(room: Room): string {
  return roomDisplayName(room).charAt(0).toUpperCase()
}

function formatTime(dateStr: string): string {
  const d = new Date(dateStr)
  const now = new Date()
  if (d.toDateString() === now.toDateString()) {
    return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
  }
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' })
}

function formatDateTime(dateStr: string): string {
  const d = new Date(dateStr)
  return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} Б`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} КБ`
  return `${(bytes / 1024 / 1024).toFixed(1)} МБ`
}

function isImage(msg: Message): boolean {
  if (!msg.file_mime) return false
  return msg.file_mime.startsWith('image/')
}

function highlightSearch(text: string): string {
  const q = searchQuery.value.trim()
  if (!q || !selectedRoom.value) return text
  const regex = new RegExp(`(${q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi')
  return text.replace(regex, '<mark>$1</mark>')
}

// ─── API methods ──────────────────────────────────────────────────────────────

async function loadRooms() {
  try {
    const data = await apiFetch<Room[]>('/chat/rooms')
    rooms.value = data
  } catch (e) {
    // errors handled globally
  }
}

async function selectRoom(room: Room) {
  selectedRoom.value = room
  messages.value = []
  showingSidebar.value = false
  await loadMessages()
  await markAsRead()
}

function backToList() {
  selectedRoom.value = null
  showingSidebar.value = true
}

async function loadMessages(beforeId?: number) {
  if (!selectedRoom.value) return
  loadingMessages.value = true
  try {
    const params = beforeId ? `?before_id=${beforeId}&limit=50` : '?limit=50'
    const data = await apiFetch<Message[]>(`/chat/rooms/${selectedRoom.value.id}/messages${params}`)
    if (beforeId) {
      messages.value = [...data, ...messages.value]
    } else {
      messages.value = data
      await nextTick(scrollToBottom)
    }
  } catch (e) {
    // errors handled globally
  } finally {
    loadingMessages.value = false
  }
}

async function sendMessage() {
  if (!selectedRoom.value) return
  if (!inputText.value.trim() && !fileInput.value) return

  sending.value = true
  const roomId = selectedRoom.value.id
  try {
    const form = new FormData()
    if (inputText.value.trim()) form.append('content', inputText.value.trim())
    if (fileInput.value) form.append('file', fileInput.value)

    const sent = await apiFetch<Message>(`/chat/rooms/${roomId}/messages`, {
      method: 'POST',
      body: form,
    })

    inputText.value = ''
    fileInput.value = null

    // Optimistic update — show message immediately without waiting for WS
    if (roomId === selectedRoom.value?.id) {
      const exists = messages.value.some(m => m.id === sent.id)
      if (!exists) {
        messages.value.push(sent)
        await nextTick(scrollToBottom)
      }
    }
  } catch (e) {
    // errors handled globally
  } finally {
    sending.value = false
  }
}

async function markAsRead() {
  if (!selectedRoom.value) return
  try {
    await apiFetch(`/chat/rooms/${selectedRoom.value.id}/read`, { method: 'POST' })
    selectedRoom.value.unread_count = 0
    // WS event unread_count will update totalUnread automatically
  } catch (e) {
    // ignore
  }
}

// ─── Scroll ───────────────────────────────────────────────────────────────────

function scrollToBottom() {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

function onScroll(e: Event) {
  const el = e.target as HTMLElement
  if (el.scrollTop < 50 && messages.value.length >= 50 && !loadingMessages.value) {
    loadMessages(messages.value[0]?.id)
  }
}

// ─── File input ───────────────────────────────────────────────────────────────

function onFileSelected(e: Event) {
  const input = e.target as HTMLInputElement
  fileInput.value = input.files?.[0] || null
}

// ─── WS event handler ─────────────────────────────────────────────────────────

let removeChatListener: (() => void) | null = null

function handleChatEvent(event: any) {
  if (event.type === 'connected') {
    loadRooms()
    if (selectedRoom.value) loadMessages()
  }

  if (event.type === 'message') {
    const msg: Message = event.message
    if (event.room_id === selectedRoom.value?.id) {
      const exists = messages.value.some(m => m.id === msg.id)
      if (!exists) {
        messages.value.push(msg)
        nextTick(scrollToBottom)
        markAsRead()
      }
    }
    // Update last_message in room list and sort
    const room = rooms.value.find(r => r.id === event.room_id)
    if (room) {
      room.last_message = msg
      room.unread_count = event.room_id === selectedRoom.value?.id ? 0 : room.unread_count + 1
      // Move room to top
      const idx = rooms.value.indexOf(room)
      if (idx > 0) {
        rooms.value.splice(idx, 1)
        rooms.value.unshift(room)
      }
    }
  }

  if (event.type === 'unread_count') {
    // totalUnread updated automatically in useChat.ts
    // Reload rooms to get accurate per-room unread counts
    loadRooms()
  }

  if (event.type === 'read') {
    // Another user read our messages — update their room unread count
    if (event.user_id !== currentUserId.value) {
      const room = rooms.value.find(r => r.id === event.room_id)
      if (room) {
        // Reload to get accurate counts
        loadRooms()
      }
    }
  }
}

// ─── New chat dialog ──────────────────────────────────────────────────────────

async function openNewChatDialog() {
  showNewChatDialog.value = true
  selectedStaffIds.value = []
  newGroupName.value = ''
  staffSearch.value = ''
  try {
    const data = await apiFetch<StaffMember[]>('/chat/staff')
    staff.value = data
  } catch (e) {
    // errors handled globally
  }
}

function closeNewChatDialog() {
  showNewChatDialog.value = false
}

function toggleStaff(id: number) {
  const idx = selectedStaffIds.value.indexOf(id)
  if (idx >= 0) {
    selectedStaffIds.value.splice(idx, 1)
  } else {
    selectedStaffIds.value.push(id)
  }
}

async function createChat() {
  if (selectedStaffIds.value.length === 0) return
  creatingChat.value = true
  try {
    let room: Room
    if (selectedStaffIds.value.length === 1) {
      // Direct chat
      room = await apiFetch<Room>('/chat/rooms/direct', {
        method: 'POST',
        body: { target_user_id: selectedStaffIds.value[0] },
      })
    } else {
      // Group chat
      room = await apiFetch<Room>('/chat/rooms', {
        method: 'POST',
        body: {
          name: newGroupName.value.trim(),
          participant_ids: selectedStaffIds.value,
        },
      })
    }
    closeNewChatDialog()
    await loadRooms()
    // Find and select the created room
    const found = rooms.value.find(r => r.id === room.id)
    if (found) await selectRoom(found)
  } catch (e) {
    // errors handled globally
  } finally {
    creatingChat.value = false
  }
}

// ─── Lifecycle ────────────────────────────────────────────────────────────────

onMounted(async () => {
  // Get current user id from localStorage (set at login)
  const userIdStr = localStorage.getItem('user_id')
  currentUserId.value = userIdStr ? parseInt(userIdStr, 10) : null

  // Ensure WS is connected (AppBar may have tried before token was available)
  if (!wsConnected.value) {
    connect()
  }
  await loadRooms()
  removeChatListener = onChatEvent(handleChatEvent)
})

onUnmounted(() => {
  if (removeChatListener) removeChatListener()
})
</script>

<style scoped>
.chat-layout {
  display: flex !important;
  height: calc(100vh - 64px) !important;
  overflow: hidden !important;
  width: 100%;
  position: relative;
}

.chat-main {
  min-width: 0;
  height: 100% !important;
  max-height: 100% !important;
  overflow: hidden !important;
  display: flex !important;
  flex-direction: column !important;
  flex: 1 1 0 !important;
}

.chat-messages {
  background: rgb(var(--v-theme-background));
  min-height: 0 !important;
  flex: 1 1 0 !important;
  overflow-y: auto !important;
  overflow-x: hidden;
}

/* Message rows */
.message-row {
  display: flex;
  align-items: flex-end;
  margin-bottom: 2px;
  padding: 0 16px;
}
.message-row-self {
  justify-content: flex-end;
}
.message-row-other {
  justify-content: flex-start;
}

/* Avatar */
.message-avatar {
  margin-right: 8px;
  flex-shrink: 0;
  align-self: flex-end;
  margin-bottom: 2px;
}
.message-avatar-spacer {
  width: 32px;
  margin-right: 8px;
  flex-shrink: 0;
}

/* Message bubbles */
.message-bubble {
  position: relative;
  max-width: 65%;
  padding: 8px 12px 4px;
  border-radius: 12px;
  word-break: break-word;
  line-height: 1.4;
}

.bubble-self {
  background: rgb(var(--v-theme-primary));
  color: rgb(var(--v-theme-on-primary));
  border-bottom-right-radius: 4px !important;
}

.bubble-other {
  background: rgb(var(--v-theme-surface-variant));
  color: rgb(var(--v-theme-on-surface-variant));
  border-bottom-left-radius: 4px !important;
}

/* Bubble tails */
.bubble-self::after {
  content: '';
  position: absolute;
  bottom: 0;
  right: -6px;
  width: 0;
  height: 0;
  border-left: 6px solid rgb(var(--v-theme-primary));
  border-top: 6px solid transparent;
}
.bubble-other::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: -6px;
  width: 0;
  height: 0;
  border-right: 6px solid rgb(var(--v-theme-surface-variant));
  border-top: 6px solid transparent;
}

/* Sender name */
.message-sender {
  font-size: 0.75rem;
  font-weight: 600;
  color: rgb(var(--v-theme-primary));
  margin-bottom: 2px;
}
.bubble-self .message-sender {
  color: rgba(255,255,255,0.8);
}

/* Message text */
.message-text {
  font-size: 0.9rem;
  line-height: 1.35;
  white-space: pre-wrap;
}
.message-text :deep(mark) {
  background: rgba(255,235,59,0.5);
  border-radius: 2px;
  padding: 0 2px;
}

/* Time */
.message-time {
  font-size: 0.68rem;
  text-align: right;
  opacity: 0.6;
  margin-top: 2px;
  display: flex;
  align-items: center;
  justify-content: flex-end;
}

/* Date separator */
.date-separator {
  display: flex;
  justify-content: center;
  padding: 12px 0 8px;
}
.date-separator span {
  background: rgba(var(--v-theme-surface-variant), 0.7);
  padding: 4px 16px;
  border-radius: 12px;
  font-size: 0.75rem;
  font-weight: 500;
}

/* Message file chip */
.message-file {
  margin-top: 4px;
}

/* Active room in sidebar */
.chat-sidebar .v-list-item--active {
  background: rgb(var(--v-theme-primary)) !important;
  color: white !important;
}
.chat-sidebar .v-list-item--active .v-list-item-subtitle {
  color: rgba(255,255,255,0.7) !important;
}

.chat-input {
  background: rgb(var(--v-theme-surface));
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  flex-shrink: 0;
}

.chat-toolbar {
  position: sticky;
  top: 0;
  z-index: 2;
  flex-shrink: 0;
}

.chat-sidebar {
  border-right: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

/* Inline image messages */
.message-image {
  max-width: 280px;
  max-height: 300px;
  border-radius: 8px;
  display: block;
  margin-top: 4px;
  object-fit: cover;
}
.message-image-link {
  display: block;
}
</style>
