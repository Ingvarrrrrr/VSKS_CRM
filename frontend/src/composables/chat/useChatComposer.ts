// Поле ввода и отправка сообщения — вынесено 1:1 из ChatView.vue (ПРАВИЛО №5).
// Переиспользует messages/scrollToBottom из useChatMessages вместо второго
// списка сообщений (ПРАВИЛО №6 — одно хранилище ленты).

import { ref, nextTick, type Ref } from 'vue'
import { apiFetch } from '@/api'
import type { Message, Room } from './chatTypes'

export function useChatComposer(
  selectedRoom: Ref<Room | null>,
  messages: Ref<Message[]>,
  scrollToBottom: () => void
) {
  const inputText = ref('')
  const fileInput = ref<File | null>(null)
  const sending = ref(false)

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

  return {
    inputText,
    fileInput,
    sending,
    sendMessage,
  }
}
