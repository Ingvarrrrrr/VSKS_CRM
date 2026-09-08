// Упоминания (@) в поле ввода — вынесено 1:1 из ChatView.vue (ПРАВИЛО №5).
// inputText переиспользуется из useChatComposer, второе текстовое поле не заводится.

import { ref, computed, type Ref } from 'vue'
import type { Participant, Room } from './chatTypes'

export function useChatMentions(
  selectedRoom: Ref<Room | null>,
  currentUserId: Ref<number | null>,
  inputText: Ref<string>
) {
  const mentionOpen = ref(false)
  const mentionFilter = ref('')
  const mentionCursorPos = ref(0)

  const mentionCandidates = computed(() => {
    if (!selectedRoom.value) return []
    const myId = currentUserId.value
    return selectedRoom.value.participants
      .filter(p => p.id !== myId)
      .filter(p => {
        if (!mentionFilter.value) return true
        return p.full_name.toLowerCase().includes(mentionFilter.value.toLowerCase())
      })
  })

  function onInputKeydown(e: KeyboardEvent) {
    if (mentionOpen.value) {
      if (e.key === 'Escape') { mentionOpen.value = false; e.preventDefault() }
      return
    }
  }

  function onInputChange() {
    const val = inputText.value
    const pos = (document.activeElement as HTMLInputElement)?.selectionStart ?? val.length
    const beforeCursor = val.slice(0, pos)
    const match = beforeCursor.match(/@([\wЀ-ӿ ]*)$/)
    if (match) {
      mentionFilter.value = match[1]
      mentionOpen.value = true
      mentionCursorPos.value = pos - match[0].length
    } else {
      mentionOpen.value = false
    }
  }

  function insertMention(participant: Participant) {
    const before = inputText.value.slice(0, mentionCursorPos.value)
    const after = inputText.value.slice(
      (document.activeElement as HTMLInputElement)?.selectionStart ?? inputText.value.length
    )
    inputText.value = before + '@' + participant.full_name + ' ' + after
    mentionOpen.value = false
  }

  function insertAtSymbol() {
    inputText.value += '@'
    mentionFilter.value = ''
    mentionOpen.value = true
    mentionCursorPos.value = inputText.value.length - 1
  }

  function mentionAll() {
    if (!selectedRoom.value) return
    const myId = currentUserId.value
    const others = selectedRoom.value.participants.filter(p => p.id !== myId)
    const mentions = others.map(p => '@' + p.full_name).join(' ')
    inputText.value = mentions + ' ' + inputText.value
  }

  return {
    mentionOpen,
    mentionFilter,
    mentionCursorPos,
    mentionCandidates,
    onInputKeydown,
    onInputChange,
    insertMention,
    insertAtSymbol,
    mentionAll,
  }
}
