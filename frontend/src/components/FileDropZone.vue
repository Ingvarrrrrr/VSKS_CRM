<template>
  <div
    class="file-drop-zone"
    :class="{ 'file-drop-zone--active': dragging, 'file-drop-zone--has-file': !!modelValue, 'file-drop-zone--disabled': disabled }"
    @dragenter.prevent.stop="onDragEnter"
    @dragover.prevent.stop="onDragEnter"
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
          <div v-if="maxSizeMb" class="text-caption text-medium-emphasis mt-1">Максимум {{ maxSizeMb }} МБ</div>
        </template>
      </div>
    </slot>
    <v-alert v-if="sizeError" type="error" density="compact" variant="tonal" class="mt-2" closable @click:close="sizeError = null">
      {{ sizeError }}
    </v-alert>
    <input
      ref="fileInput"
      type="file"
      hidden
      :accept="accept"
      :multiple="multiple"
      :disabled="disabled"
      @change="onFileSelect"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { checkUploadSize } from '@/constants/uploadLimits'

const props = defineProps<{
  modelValue?: File | null
  accept?: string
  multiple?: boolean
  hint?: string
  disabled?: boolean
  /** Клиентская проверка размера ДО отправки (владелец, 2026-09-17: раньше
   * нигде не было видно допустимого размера файла, а превышение узнавалось
   * только по голому HTTP 413 от nginx). Не задан по умолчанию — остальные
   * потребители FileDropZone (фото/документы ТС, чеки, вложения к закупке)
   * имеют СВОИ лимиты вне этого компонента и не должны получить чужую
   * подпись/проверку молча (Правило №6 — трогаем только явно подключённые
   * диалоги импорта, см. frontend/src/constants/uploadLimits.ts). */
  maxSizeMb?: number
}>()

const emit = defineEmits<{
  'update:modelValue': [file: File | null]
  'files': [files: File[]]
}>()

const dragging = ref(false)
const fileInput = ref<HTMLInputElement>()
const sizeError = ref<string | null>(null)

function onDragEnter() {
  if (props.disabled) return
  dragging.value = true
}

/** Возвращает файлы, прошедшие проверку размера (если maxSizeMb задан) —
 * первый превысивший лимит файл останавливает приём и показывает ошибку
 * прямо под зоной сброса, ничего не эмитится наверх. */
function _filterBySize(files: File[]): File[] {
  if (!props.maxSizeMb) { sizeError.value = null; return files }
  for (const f of files) {
    const err = checkUploadSize(f, props.maxSizeMb)
    if (err) { sizeError.value = err; return [] }
  }
  sizeError.value = null
  return files
}

function onDrop(e: DragEvent) {
  dragging.value = false
  if (props.disabled) return
  const rawFiles = Array.from(e.dataTransfer?.files || [])
  if (!rawFiles.length) return
  const files = _filterBySize(rawFiles)
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
  const rawFiles = Array.from(input.files || [])
  if (!rawFiles.length) return
  const files = _filterBySize(rawFiles)
  if (!files.length) { input.value = ''; return }
  if (props.multiple) {
    emit('files', files)
  } else {
    emit('update:modelValue', files[0])
    emit('files', [files[0]])
  }
  input.value = ''
}

function openPicker() {
  if (props.disabled) return
  fileInput.value?.click()
}

function clear() {
  sizeError.value = null
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
  min-height: 120px;
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
.file-drop-zone--disabled {
  cursor: not-allowed;
  opacity: 0.55;
  background: rgba(var(--v-border-color), 0.03);
}
.file-drop-zone--disabled:hover {
  border-color: rgba(var(--v-border-color), 0.3);
  background: rgba(var(--v-border-color), 0.03);
}
</style>
