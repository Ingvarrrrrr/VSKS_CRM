<template>
  <div class="chat-sidebar" :class="{ 'chat-sidebar--full': !smAndUp }">
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
          @click="$emit('new-chat')"
        />
      </template>
    </v-list-item>

    <v-divider />

    <!-- Search field -->
    <div class="px-3 pt-2 pb-1">
      <v-text-field
        :model-value="searchQuery"
        :placeholder="selectedRoomId ? 'Поиск в чате...' : 'Поиск по чатам...'"
        prepend-inner-icon="mdi-magnify"
        variant="outlined"
        density="compact"
        hide-details
        clearable
        @update:model-value="$emit('update:searchQuery', $event ?? '')"
        @click:clear="$emit('update:searchQuery', '')"
      />
    </div>

    <!-- Room list -->
    <v-list v-if="rooms.length > 0" lines="two" nav class="pa-1 chat-room-list">
      <v-list-item
        v-for="room in rooms"
        :key="room.id"
        :class="{ 'bg-primary-lighten-4': selectedRoomId === room.id }"
        :active="selectedRoomId === room.id"
        rounded="lg"
        class="mb-1"
        @click="$emit('select', room)"
      >
        <template #prepend>
          <v-badge
            :model-value="room.unread_count > 0"
            :content="room.unread_count > 99 ? '99+' : room.unread_count"
            color="error"
            offset-x="6"
            offset-y="6"
            overlap
          >
            <v-avatar :color="roomColor(room)" size="44">
              <span class="text-subtitle-1 font-weight-bold text-white">
                {{ roomInitial(room, currentUserId) }}
              </span>
            </v-avatar>
          </v-badge>
        </template>

        <v-list-item-title class="font-weight-medium" :class="{ 'room-has-unread': room.unread_count > 0 }">
          {{ roomDisplayName(room, currentUserId) }}
        </v-list-item-title>
        <v-list-item-subtitle class="text-truncate">
          {{ room.last_message?.content || (room.last_message?.has_file ? '📎 Файл' : 'Нет сообщений') }}
        </v-list-item-subtitle>

        <template #append>
          <div class="d-flex flex-column align-end" @click.stop>
            <span v-if="room.last_message" class="text-caption text-medium-emphasis mb-1">
              {{ formatTime(room.last_message.created_at) }}
            </span>
            <v-chip
              v-if="room.unread_count > 0"
              color="error"
              size="small"
              variant="flat"
              class="font-weight-bold unread-chip"
              density="compact"
            >
              {{ room.unread_count > 99 ? '99+' : room.unread_count }}
            </v-chip>
            <v-menu location="bottom end">
              <template #activator="{ props: menuProps }">
                <v-btn
                  v-bind="menuProps"
                  icon="mdi-dots-vertical"
                  variant="text"
                  size="x-small"
                  density="compact"
                  class="room-menu-btn"
                />
              </template>
              <v-list density="compact">
                <v-list-item
                  prepend-icon="mdi-exit-to-app"
                  title="Удалить у себя"
                  @click="$emit('leave', room)"
                />
              </v-list>
            </v-menu>
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
  </div>
</template>

<script setup lang="ts">
import { roomColor, roomDisplayName, roomInitial, formatTime } from '@/composables/chat/chatFormat'
import type { Room } from '@/composables/chat/chatTypes'

defineProps<{
  rooms: Room[]
  selectedRoomId: number | null
  searchQuery: string
  currentUserId: number | null
  smAndUp: boolean
}>()

defineEmits<{
  (e: 'update:searchQuery', value: string): void
  (e: 'select', room: Room): void
  (e: 'new-chat'): void
  (e: 'leave', room: Room): void
}>()
</script>
