<template>
  <div
    class="file-drop-zone"
    :class="{ 'file-drop-zone--active': dragging, 'file-drop-zone--has-file': !!modelValue }"
    @dragenter.prevent.stop="dragging = true"
    @dragover.prevent.stop="dragging = true"
    @dragleave.prevent.stop="dragging = false"
    @drop.prevent.stop="onDrop"
    @click="openPicker"
  >
    <slot :file="modelValue" :dragging="dragging" :clear="clear" :open="openPicker">
      <div class="text-center pa-6">
        <v-icon size="40" :color="dragging ? 'primary' : 'grey-lighten-1'" class="mb-2">mdi-file-upload-outline</v-icon>
        <div v-if="modelValue" class="d-flex align-center justify-center gap-2">
          <v-icon size="18">mdi-file-document-outline</v-icon>
          <span class="text-body-2">{{ modelValue.name }}</span>
          <v-btn icon size="x-small" variant="text" @click.stop="clear">
            <v-icon size="16">mdi-close</v-icon>
          </v-btn>
        </div>
        <template v-else>
          <div class="text-body-1 mb-1">Перетащите файл сюда</div>
          <div class="text-body-2 text-medium-emphasis">{{ hint || 'или нажмите для выбора' }}</div>
        </template>
      </div>
    </slot>
    <input
      ref="fileInput"
      type="file"
      hidden
      :accept="accept"
      :multiple="multiple"
      @change="onFileSelect"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{
  modelValue?: File | null
  accept?: string
  multiple?: boolean
  hint?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [file: File | null]
  'files': [files: File[]]
}>()

const dragging = ref(false)
const fileInput = ref<HTMLInputElement>()

function onDrop(e: DragEvent) {
  dragging.value = false
  const files = Array.from(e.dataTransfer?.files || [])
  if (!files.length) return
  if (props.multiple) {
    emit('files', files)
  } else {
    emit('update:modelValue', files[0])
    emit('files', [files[0]])
  }
}

function onFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  const files = Array.from(input.files || [])
  if (!files.length) return
  if (props.multiple) {
    emit('files', files)
  } else {
    emit('update:modelValue', files[0])
    emit('files', [files[0]])
  }
  input.value = ''
}

function openPicker() {
  fileInput.value?.click()
}

function clear() {
  emit('update:modelValue', null)
}

defineExpose({ openPicker, clear })
</script>

<style scoped>
.file-drop-zone {
  border: 2px dashed rgba(var(--v-border-color), 0.3);
  border-radius: 8px;
  transition: all 0.2s;
  cursor: pointer;
  min-height: 80px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.file-drop-zone:hover,
.file-drop-zone--active {
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.04);
}
.file-drop-zone--has-file {
  border-style: solid;
  border-color: rgb(var(--v-theme-success));
}
</style>
