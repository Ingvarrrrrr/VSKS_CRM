<template>
  <v-dialog :model-value="modelValue" max-width="400" @update:model-value="$emit('update:modelValue', $event)">
    <v-card>
      <v-card-title class="d-flex align-center pa-4">
        <v-icon icon="mdi-exit-to-app" class="me-2" color="error" />
        Удалить чат у себя?
      </v-card-title>
      <v-card-text>
        Чат «{{ room ? roomDisplayName(room, currentUserId) : '' }}» будет удалён из вашего списка.
        Другие участники не пострадают.
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="$emit('cancel')">Отмена</v-btn>
        <v-btn color="error" variant="flat" :loading="leaving" @click="$emit('confirm')">Удалить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { roomDisplayName } from '@/composables/chat/chatFormat'
import type { Room } from '@/composables/chat/chatTypes'

defineProps<{
  modelValue: boolean
  room: Room | null
  currentUserId: number | null
  leaving: boolean
}>()

defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'cancel'): void
  (e: 'confirm'): void
}>()
</script>
