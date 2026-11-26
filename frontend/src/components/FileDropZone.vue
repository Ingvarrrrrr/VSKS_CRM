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
          <div class="text-body-1 mb-1">Перетащите файл сюда{{ allowPaste ? ' или вставьте (Ctrl+V)' : '' }}</div>
          <div class="text-body-2 text-medium-emphasis">{{ hint || (allowPaste ? 'или нажмите для выбора / вставьте фото из буфера' : 'или нажмите для выбора') }}</div>
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
import { ref, onMounted, onUnmounted } from 'vue'
import { checkUploadSize } from '@/constants/uploadLimits'

const props = defineProps<{
  modelValue?: File | null
  accept?: string
  multiple?: boolean
  hint?: string
  disabled?: boolean
  maxSizeMb?: number
  allowPaste?: boolean
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

function _filterBySize(files: File[]): File[] {
  if (!props.maxSizeMb) { sizeError.value = null; return files }
  for (const f of files) {
    const err = checkUploadSize(f, props.maxSizeMb)
    if (err) { sizeError.value = err; return [] }
  }
  sizeError.value = null
  return files
}

async function onDrop(e: DragEvent) {
  dragging.value = false
  if (props.disabled) return
  const dt = e.dataTransfer
  let rawFiles: File[] = []

  if (dt?.files && dt.files.length > 0) {
    rawFiles = Array.from(dt.files)
  } else if (dt?.items && dt.items.length > 0) {
    for (let i = 0; i < dt.items.length; i++) {
      const item = dt.items[i]
      if (item.kind === 'file') {
        const f = item.getAsFile()
        if (f) rawFiles.push(f)
      }
    }
  }

  // Если всё ещё пусто, попробуем извлечь URL / DataURL / HTML img из text/uri-list или text/html
  if (!rawFiles.length && dt) {
    let targetUrl = ''
    const uriList = dt.getData('text/uri-list')
    if (uriList) {
      targetUrl = uriList.split('\n')[0].trim()
    } else {
      const html = dt.getData('text/html')
      if (html) {
        const match = html.match(/src="([^"]+)"/)
        if (match && match[1]) {
          targetUrl = match[1]
        }
      }
    }

    if (targetUrl && (targetUrl.startsWith('data:') || targetUrl.startsWith('blob:') || targetUrl.startsWith('http://') || targetUrl.startsWith('https://'))) {
      try {
        const resp = await fetch(targetUrl)
        const blob = await resp.blob()
        const mime = blob.type || 'image/jpeg'
        const ext = mime.includes('png') ? 'png' : mime.includes('webp') ? 'webp' : mime.includes('pdf') ? 'pdf' : 'jpg'
        const pastedFile = new File([blob], `pasted-photo.${ext}`, { type: mime })
        rawFiles.push(pastedFile)
      } catch (err) {
        sizeError.value = 'Мессенджер не передал файл напрямую. Скопируйте фото (Ctrl+C) и вставьте сюда (Ctrl+V), или сохраните на компьютер.'
      }
    }
  }

  if (!rawFiles.length) {
    if (!sizeError.value) {
      sizeError.value = 'Файл не обнаружен. Попробуйте сохранить картинку на компьютер или использовать Ctrl+V.'
    }
    return
  }

  const files = _filterBySize(rawFiles)
  if (!files.length) return
  if (props.multiple) {
    emit('files', files)
  } else {
    emit('update:modelValue', files[0])
    emit('files', [files[0]])
  }
}

async function handleClipboardData(clipboard: DataTransfer | null) {
  if (!clipboard || props.disabled) return
  let rawFiles: File[] = []
  if (clipboard.items && clipboard.items.length > 0) {
    for (let i = 0; i < clipboard.items.length; i++) {
      const item = clipboard.items[i]
      if (item.kind === 'file') {
        const f = item.getAsFile()
        if (f) rawFiles.push(f)
      }
    }
  }
  if (!rawFiles.length && clipboard.files && clipboard.files.length > 0) {
    rawFiles = Array.from(clipboard.files)
  }

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

function onGlobalPaste(e: ClipboardEvent) {
  if (!props.allowPaste || props.disabled) return
  // Проверим, что фокус не в инпуте/текстарее, либо компонент активен
  const activeTag = document.activeElement?.tagName?.toLowerCase()
  if (activeTag === 'input' || activeTag === 'textarea' || (document.activeElement as HTMLElement)?.isContentEditable) {
    // Если пользователь в инпуте, не перехватываем вставку
    return
  }
  handleClipboardData(e.clipboardData)
}

onMounted(() => {
  window.addEventListener('paste', onGlobalPaste)
})

onUnmounted(() => {
  window.removeEventListener('paste', onGlobalPaste)
})

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
