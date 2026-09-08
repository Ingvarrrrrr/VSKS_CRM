<template>
  <v-toolbar density="compact" elevation="1" class="flex-shrink-0 chat-toolbar">
    <!-- Back button on mobile -->
    <v-btn
      v-if="!smAndUp"
      icon="mdi-arrow-left"
      variant="text"
      @click="$emit('back')"
    />
    <v-avatar :color="roomColor(room)" size="36" class="ms-2">
      <span class="text-body-2 font-weight-bold text-white">
        {{ roomInitial(room, currentUserId) }}
      </span>
    </v-avatar>
    <v-toolbar-title class="ms-3" style="cursor:pointer" @click="$emit('open-participants')">
      <div class="font-weight-medium">{{ roomDisplayName(room, currentUserId) }}</div>
      <div class="text-caption text-medium-emphasis">
        {{ room.is_group ? `${room.participants.length} участников` : 'Личный чат' }}
      </div>
    </v-toolbar-title>
    <template #append>
      <v-btn
        icon="mdi-account-group"
        variant="text"
        size="small"
        class="me-1"
        title="Участники"
        @click="$emit('open-participants')"
      />
      <v-icon
        :icon="wsConnected ? 'mdi-wifi' : 'mdi-wifi-off'"
        :color="wsConnected ? 'success' : 'error'"
        size="18"
        class="me-2"
      />
    </template>
  </v-toolbar>
</template>

<script setup lang="ts">
import { roomColor, roomDisplayName, roomInitial } from '@/composables/chat/chatFormat'
import type { Room } from '@/composables/chat/chatTypes'

defineProps<{
  room: Room
  currentUserId: number | null
  smAndUp: boolean
  wsConnected: boolean
}>()

defineEmits<{
  (e: 'back'): void
  (e: 'open-participants'): void
}>()
</script>
