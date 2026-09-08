<template>
  <div class="chat-layout">
    <!-- Sidebar: Chat list (плоская панель, без v-navigation-drawer — temporary-drawer
         с односторонним :model-value залипал после первого закрытия на мобиле) -->
    <ChatSidebar
      v-if="showSidebar"
      :rooms="filteredRooms"
      :selected-room-id="selectedRoom?.id ?? null"
      :search-query="searchQuery"
      :current-user-id="currentUserId"
      :sm-and-up="smAndUp"
      @update:search-query="searchQuery = $event"
      @select="onRoomClick"
      @new-chat="openNewChatDialog"
      @leave="confirmLeaveRoom"
    />

    <!-- Main message area: на мобиле показываем только когда чат выбран -->
    <div v-if="smAndUp || !showSidebar" class="chat-main flex-grow-1">
      <!-- No room selected placeholder -->
      <div v-if="!selectedRoom" class="d-flex flex-column align-center justify-center fill-height text-medium-emphasis">
        <v-icon icon="mdi-chat-outline" size="80" class="mb-4 opacity-30" />
        <p class="text-h6">Выберите чат</p>
        <p class="text-body-2">Или создайте новый с помощью кнопки «+»</p>
      </div>

      <template v-else>
        <ChatToolbar
          :room="selectedRoom"
          :current-user-id="currentUserId"
          :sm-and-up="smAndUp"
          :ws-connected="wsConnected"
          @back="backToList"
          @open-participants="showParticipantsDialog = true"
        />

        <ChatMessageList
          :items="messagesWithSeparators"
          :loading="loadingMessages"
          :is-empty="filteredMessages.length === 0"
          :current-user-id="currentUserId"
          :search-query="searchQuery"
          :room="selectedRoom"
          :container-ref="setContainerRef"
          @scroll="onScroll"
        />

        <ChatComposer
          :input-text="inputText"
          :file-input="fileInput"
          :sending="sending"
          :mention-open="mentionOpen"
          :mention-candidates="mentionCandidates"
          :show-mention-all="!!(selectedRoom?.is_group && selectedRoom.participants.length > 2)"
          @update:input-text="inputText = $event"
          @clear-file="fileInput = null"
          @file-selected="fileInput = $event"
          @at-click="insertAtSymbol"
          @mention-all-click="mentionAll"
          @input-change="onInputChange"
          @keydown="onInputKeydown"
          @send="sendMessage"
          @newline="inputText += '\n'"
          @mention-select="insertMention"
        />
      </template>
    </div>

    <!-- New Chat Dialog -->
    <ChatNewRoomDialog
      :model-value="showNewChatDialog"
      :mobile="mobile"
      :staff-search="staffSearch"
      :filtered-staff="filteredStaff"
      :selected-staff-ids="selectedStaffIds"
      :new-group-name="newGroupName"
      :creating-chat="creatingChat"
      @update:model-value="showNewChatDialog = $event"
      @update:staff-search="staffSearch = $event"
      @update:new-group-name="newGroupName = $event"
      @toggle-staff="toggleStaff"
      @cancel="closeNewChatDialog"
      @create="onCreateChat"
    />

    <!-- Leave Room Confirm Dialog -->
    <ChatLeaveDialog
      :model-value="showLeaveDialog"
      :room="leaveRoomTarget"
      :current-user-id="currentUserId"
      :leaving="leavingRoom"
      @update:model-value="showLeaveDialog = $event"
      @cancel="showLeaveDialog = false"
      @confirm="doLeaveRoom"
    />

    <!-- Participants Dialog -->
    <ChatParticipantsDialog
      :model-value="showParticipantsDialog"
      :mobile="mobile"
      :room="selectedRoom"
      :current-user-id="currentUserId"
      @update:model-value="showParticipantsDialog = $event"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useDisplay } from 'vuetify'
import { wsConnected, onChatEvent, connect } from '@/composables/useChat'
import { useChatRooms } from '@/composables/chat/useChatRooms'
import { useChatMessages } from '@/composables/chat/useChatMessages'
import { useChatComposer } from '@/composables/chat/useChatComposer'
import { useChatMentions } from '@/composables/chat/useChatMentions'
import { useChatNewRoom } from '@/composables/chat/useChatNewRoom'
import type { Message, Room } from '@/composables/chat/chatTypes'
import ChatSidebar from '@/components/chat/ChatSidebar.vue'
import ChatToolbar from '@/components/chat/ChatToolbar.vue'
import ChatMessageList from '@/components/chat/ChatMessageList.vue'
import ChatComposer from '@/components/chat/ChatComposer.vue'
import ChatNewRoomDialog from '@/components/chat/ChatNewRoomDialog.vue'
import ChatLeaveDialog from '@/components/chat/ChatLeaveDialog.vue'
import ChatParticipantsDialog from '@/components/chat/ChatParticipantsDialog.vue'
import '@/styles/chat.css'

const { smAndUp, mobile } = useDisplay()

// ─── Composables (ПРАВИЛО №5/№6: одно состояние на фичу, без дублей) ─────────

const {
  rooms, selectedRoom, currentUserId, searchQuery, showSidebar, filteredRooms,
  loadRooms, selectRoom, backToList, markAsRead,
  showLeaveDialog, leaveRoomTarget, leavingRoom, confirmLeaveRoom, doLeaveRoom,
} = useChatRooms(smAndUp)

const {
  messages, loadingMessages, setContainerRef, filteredMessages, messagesWithSeparators,
  scrollToBottom, loadMessages, onScroll,
} = useChatMessages(selectedRoom, searchQuery)

const { inputText, fileInput, sending, sendMessage } = useChatComposer(selectedRoom, messages, scrollToBottom)

const {
  mentionOpen, mentionCandidates, onInputKeydown, onInputChange,
  insertMention, insertAtSymbol, mentionAll,
} = useChatMentions(selectedRoom, currentUserId, inputText)

// Переход к выбранной/созданной комнате тянет и ленту сообщений, и прочтение —
// вынесено ниже (onRoomClick), поэтому useChatNewRoom получает его коллбэком.
const {
  showNewChatDialog, staffSearch, selectedStaffIds, newGroupName, creatingChat, filteredStaff,
  openNewChatDialog, closeNewChatDialog, toggleStaff, createChat,
} = useChatNewRoom(loadRooms, (room: Room) => onRoomClick(room))

// Participants dialog (единственное состояние, не относящееся ни к одной фиче)
const showParticipantsDialog = ref(false)

// ─── Orchestration: выбор комнаты тянет и ленту сообщений, и прочтение ───────

async function onRoomClick(room: Room) {
  selectRoom(room)
  messages.value = []
  await loadMessages()
  await markAsRead()
}

// Обёртка нужна, чтобы передать сам Ref `rooms` (для поиска созданной комнаты
// ПОСЛЕ loadRooms(), который меняет ссылку на массив) — в шаблоне `rooms`
// авто-разворачивается в Room[], поэтому вызов идёт из script, а не инлайном.
function onCreateChat() {
  createChat(rooms)
}

// ─── WS event handler ─────────────────────────────────────────────────────

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
        scrollToBottom()
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

// ─── Lifecycle ────────────────────────────────────────────────────────────

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
