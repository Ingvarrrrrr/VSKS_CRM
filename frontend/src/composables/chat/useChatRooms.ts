// Список комнат, выбор комнаты и «удалить чат у себя» — вынесено 1:1 из
// ChatView.vue (ПРАВИЛО №5). Загрузка сообщений/прочтение выбранной комнаты
// остаются в useChatMessages — здесь только состояние списка комнат.

import { ref, computed, watch, type Ref } from 'vue'
import { apiFetch } from '@/api'
import { roomDisplayName } from './chatFormat'
import type { Room } from './chatTypes'

export function useChatRooms(smAndUp: Ref<boolean>) {
  const rooms = ref<Room[]>([])
  const selectedRoom = ref<Room | null>(null)
  const currentUserId = ref<number | null>(null)

  // Mobile: show sidebar or messages
  const showingSidebar = ref(true)

  // Search (shared with message search-highlight)
  const searchQuery = ref('')

  const showSidebar = computed(() => {
    if (smAndUp.value) return true
    return !selectedRoom.value || showingSidebar.value
  })

  const filteredRooms = computed(() => {
    const q = searchQuery.value.trim().toLowerCase()
    if (!q) return rooms.value
    return rooms.value.filter(r =>
      roomDisplayName(r, currentUserId.value).toLowerCase().includes(q) ||
      (r.last_message?.content || '').toLowerCase().includes(q)
    )
  })

  // Clear search on room switch
  watch(selectedRoom, () => { searchQuery.value = '' })

  async function loadRooms() {
    try {
      const data = await apiFetch<Room[]>('/chat/rooms')
      rooms.value = data
    } catch (e) {
      // errors handled globally
    }
  }

  function selectRoom(room: Room) {
    selectedRoom.value = room
    showingSidebar.value = false
  }

  function backToList() {
    selectedRoom.value = null
    showingSidebar.value = true
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

  // ─── Leave room ─────────────────────────────────────────────────────────

  const showLeaveDialog = ref(false)
  const leaveRoomTarget = ref<Room | null>(null)
  const leavingRoom = ref(false)

  function confirmLeaveRoom(room: Room) {
    leaveRoomTarget.value = room
    showLeaveDialog.value = true
  }

  async function doLeaveRoom() {
    if (!leaveRoomTarget.value) return
    leavingRoom.value = true
    try {
      await apiFetch(`/chat/rooms/${leaveRoomTarget.value.id}/leave`, { method: 'POST' })
      // Remove from local state
      rooms.value = rooms.value.filter(r => r.id !== leaveRoomTarget.value!.id)
      if (selectedRoom.value?.id === leaveRoomTarget.value.id) {
        selectedRoom.value = null
        showingSidebar.value = true
      }
      showLeaveDialog.value = false
      leaveRoomTarget.value = null
    } catch (e) {
      // errors handled globally
    } finally {
      leavingRoom.value = false
    }
  }

  return {
    rooms,
    selectedRoom,
    currentUserId,
    showingSidebar,
    searchQuery,
    showSidebar,
    filteredRooms,
    loadRooms,
    selectRoom,
    backToList,
    markAsRead,
    showLeaveDialog,
    leaveRoomTarget,
    leavingRoom,
    confirmLeaveRoom,
    doLeaveRoom,
  }
}
