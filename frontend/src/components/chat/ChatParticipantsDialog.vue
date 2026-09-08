<template>
  <v-dialog :model-value="modelValue" max-width="400" scrollable :fullscreen="mobile" @update:model-value="$emit('update:modelValue', $event)">
    <v-card v-if="room">
      <v-card-title class="d-flex align-center pa-4">
        <v-icon icon="mdi-account-group" class="me-2" />
        {{ roomDisplayName(room, currentUserId) }}
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="$emit('update:modelValue', false)" />
      </v-card-title>
      <v-divider />
      <v-card-text class="pa-2" style="max-height: 400px; overflow-y: auto">
        <v-list density="compact">
          <v-list-item
            v-for="p in room.participants"
            :key="p.id"
            :title="p.full_name"
          >
            <template #prepend>
              <v-avatar :color="stringToColor(p.full_name)" size="36">
                <span class="text-body-2 font-weight-bold text-white">{{ p.full_name[0] }}</span>
              </v-avatar>
            </template>
            <template #append>
              <v-chip v-if="p.id === currentUserId" size="x-small" color="primary" variant="tonal">Вы</v-chip>
            </template>
          </v-list-item>
        </v-list>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { roomDisplayName, stringToColor } from '@/composables/chat/chatFormat'
import type { Room } from '@/composables/chat/chatTypes'

defineProps<{
  modelValue: boolean
  mobile: boolean
  room: Room | null
  currentUserId: number | null
}>()

defineEmits<{
  (e: 'update:modelValue', value: boolean): void
}>()
</script>
