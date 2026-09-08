<template>
  <div
    :ref="containerRef"
    class="chat-messages flex-grow-1 overflow-y-auto pa-3"
    @scroll="$emit('scroll', $event)"
  >
    <!-- Load more indicator -->
    <div v-if="loading" class="text-center py-2">
      <v-progress-circular indeterminate size="24" />
    </div>

    <!-- Messages -->
    <template v-for="(item, idx) in items" :key="'type' in item ? 'sep-' + item.date + idx : item.id">
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
          <div v-if="item.content" class="message-text" v-html="highlightSearch(item.content || '', searchQuery)"></div>

          <!-- File attachment -->
          <div v-if="item.has_file && item.file_name" class="message-file">
            <!-- Inline image preview -->
            <a
              v-if="isImage(item)"
              :href="fileUrl(room?.id, item.id)"
              target="_blank"
              class="message-image-link"
            >
              <img
                :src="fileUrl(room?.id, item.id)"
                :alt="item.file_name"
                class="message-image"
                loading="lazy"
              />
            </a>
            <!-- Non-image file chip -->
            <v-chip
              v-else
              :href="fileUrl(room?.id, item.id)"
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
              :color="room?.unread_count === 0 ? 'blue' : 'grey'"
            >mdi-check-all</v-icon>
          </div>
        </div>
      </div>
    </template>

    <!-- Empty state -->
    <div v-if="isEmpty && !loading" class="text-center mt-8 text-medium-emphasis">
      <v-icon icon="mdi-message-outline" size="48" class="mb-2 opacity-30" />
      <p class="text-body-2">Нет сообщений. Начните переписку!</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { stringToColor, formatDateTime, formatSize, isImage, fileUrl, highlightSearch } from '@/composables/chat/chatFormat'
import type { MessageOrSeparator, Room } from '@/composables/chat/chatTypes'

defineProps<{
  items: MessageOrSeparator[]
  loading: boolean
  isEmpty: boolean
  currentUserId: number | null
  searchQuery: string
  room: Room | null
  // any: должно быть присвоено VNodeRef Vue (Element | ComponentPublicInstance | null) —
  // конкретная реализация в useChatMessages.ts типизирована уже (Element | null).
  containerRef: (el: any) => void
}>()

defineEmits<{
  (e: 'scroll', ev: Event): void
}>()
</script>
