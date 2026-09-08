// Диалог создания нового чата (личного/группового) — вынесено 1:1 из
// ChatView.vue (ПРАВИЛО №5). loadRooms и переход к созданной комнате
// передаются коллбэками, чтобы не дублировать состояние rooms/selectedRoom.

import { ref, computed, type Ref } from 'vue'
import { apiFetch } from '@/api'
import type { Room, StaffMember } from './chatTypes'

export function useChatNewRoom(loadRooms: () => Promise<void>, onRoomCreated: (room: Room) => Promise<void> | void) {
  const showNewChatDialog = ref(false)
  const staff = ref<StaffMember[]>([])
  const staffSearch = ref('')
  const selectedStaffIds = ref<number[]>([])
  const newGroupName = ref('')
  const creatingChat = ref(false)

  const filteredStaff = computed(() => {
    const q = staffSearch.value.toLowerCase()
    if (!q) return staff.value
    return staff.value.filter(p =>
      p.full_name.toLowerCase().includes(q) ||
      (p.department || '').toLowerCase().includes(q) ||
      (p.position || '').toLowerCase().includes(q)
    )
  })

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

  async function createChat(rooms: Ref<Room[]>) {
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
      if (found) await onRoomCreated(found)
    } catch (e) {
      // errors handled globally
    } finally {
      creatingChat.value = false
    }
  }

  return {
    showNewChatDialog,
    staff,
    staffSearch,
    selectedStaffIds,
    newGroupName,
    creatingChat,
    filteredStaff,
    openNewChatDialog,
    closeNewChatDialog,
    toggleStaff,
    createChat,
  }
}
