<template>
  <div class="chat-input pa-3 flex-shrink-0">
    <!-- Selected file preview -->
    <v-chip
      v-if="fileInput"
      closable
      prepend-icon="mdi-paperclip"
      class="mb-2"
      @click:close="$emit('clear-file')"
    >
      {{ fileInput.name }}
    </v-chip>

    <!-- Mention dropdown -->
    <div v-if="mentionOpen && mentionCandidates.length" class="mention-dropdown-chat">
      <div
        v-for="p in mentionCandidates"
        :key="p.id"
        class="mention-dropdown-chat__item"
        @mousedown.prevent="$emit('mention-select', p)"
      >
        <v-avatar :color="stringToColor(p.full_name)" size="22" class="me-2">
          <span class="text-caption text-white" style="font-size:10px">{{ p.full_name[0] }}</span>
        </v-avatar>
        {{ p.full_name }}
      </div>
    </div>

    <div class="d-flex align-end gap-2">
      <!-- Hidden file input -->
      <input
        ref="fileInputEl"
        type="file"
        accept=".pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png"
        style="display: none"
        @change="onFileSelected"
      />

      <!-- Attach button -->
      <v-btn
        icon="mdi-paperclip"
        variant="text"
        :disabled="sending"
        @click="fileInputEl?.click()"
      />

      <!-- @ mention button -->
      <v-btn
        icon="mdi-at"
        variant="text"
        size="small"
        :disabled="sending"
        title="Упомянуть"
        @click="$emit('at-click')"
      />

      <!-- Рупор: mention all -->
      <v-btn
        v-if="showMentionAll"
        icon="mdi-bullhorn-outline"
        variant="text"
        size="small"
        :disabled="sending"
        title="Упомянуть всех"
        @click="$emit('mention-all-click')"
      />

      <!-- Text field -->
      <v-text-field
        :model-value="inputText"
        placeholder="Написать сообщение..."
        variant="outlined"
        density="compact"
        hide-details
        class="flex-grow-1"
        :disabled="sending"
        @update:model-value="$emit('update:inputText', $event ?? '')"
        @input="$emit('input-change')"
        @keydown="$emit('keydown', $event)"
        @keydown.enter.exact.prevent="$emit('send')"
        @keydown.enter.shift.exact="$emit('newline')"
      />

      <!-- Send button -->
      <v-btn
        icon="mdi-send"
        color="primary"
        :disabled="(!inputText.trim() && !fileInput) || sending"
        :loading="sending"
        @click="$emit('send')"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { stringToColor } from '@/composables/chat/chatFormat'
import type { Participant } from '@/composables/chat/chatTypes'

defineProps<{
  inputText: string
  fileInput: File | null
  sending: boolean
  mentionOpen: boolean
  mentionCandidates: Participant[]
  showMentionAll: boolean
}>()

const emit = defineEmits<{
  (e: 'update:inputText', value: string): void
  (e: 'clear-file'): void
  (e: 'file-selected', file: File | null): void
  (e: 'at-click'): void
  (e: 'mention-all-click'): void
  (e: 'input-change'): void
  (e: 'keydown', ev: KeyboardEvent): void
  (e: 'send'): void
  (e: 'newline'): void
  (e: 'mention-select', participant: Participant): void
}>()

const fileInputEl = ref<HTMLInputElement | null>(null)

function onFileSelected(e: Event) {
  const input = e.target as HTMLInputElement
  emit('file-selected', input.files?.[0] || null)
}
</script>
