// Загрузка и отображение ленты сообщений выбранной комнаты — вынесено 1:1
// из ChatView.vue (ПРАВИЛО №5). Отправка сообщения — в useChatComposer,
// который переиспользует messages/scrollToBottom отсюда, а не дублирует их.

import { ref, computed, nextTick, type Ref } from 'vue'
import { apiFetch } from '@/api'
import { groupMessagesWithSeparators } from './chatFormat'
import type { Message, Room } from './chatTypes'

export function useChatMessages(selectedRoom: Ref<Room | null>, searchQuery: Ref<string>) {
  const messages = ref<Message[]>([])
  const loadingMessages = ref(false)
  const messagesContainer = ref<HTMLElement | null>(null)

  function setContainerRef(el: Element | null) {
    messagesContainer.value = (el as HTMLElement) ?? null
  }

  const filteredMessages = computed(() => {
    const q = searchQuery.value.trim().toLowerCase()
    if (!q || !selectedRoom.value) return messages.value
    return messages.value.filter(m =>
      (m.content || '').toLowerCase().includes(q) ||
      (m.sender_name || '').toLowerCase().includes(q)
    )
  })

  const messagesWithSeparators = computed(() => groupMessagesWithSeparators(filteredMessages.value))

  function scrollToBottom() {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
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

  function onScroll(e: Event) {
    const el = e.target as HTMLElement
    if (el.scrollTop < 50 && messages.value.length >= 50 && !loadingMessages.value) {
      loadMessages(messages.value[0]?.id)
    }
  }

  return {
    messages,
    loadingMessages,
    messagesContainer,
    setContainerRef,
    filteredMessages,
    messagesWithSeparators,
    scrollToBottom,
    loadMessages,
    onScroll,
  }
}
