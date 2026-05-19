<template>
  <div class="repair-attachment-slot">
    <div class="d-flex align-center mb-2">
      <span class="text-body-2 font-weight-medium">{{ label }}</span>
      <v-spacer />
      <v-btn
        v-if="!uploading"
        size="x-small"
        variant="tonal"
        color="primary"
        prepend-icon="mdi-upload"
        @click="openPicker"
      >
        Загрузить
      </v-btn>
      <v-progress-circular v-else size="20" width="2" indeterminate color="primary" class="mr-1" />
    </div>

    <input
      ref="fileInputRef"
      type="file"
      hidden
      accept=".pdf,.doc,.docx,.jpg,.jpeg,.png,.webp,.heic"
      @change="onFileSelected"
    />

    <div v-if="attachments.length === 0" class="text-caption text-medium-emphasis py-1">
      Нет файлов
    </div>

    <v-list v-else density="compact" class="pa-0">
      <v-list-item
        v-for="att in attachments"
        :key="att.id"
        class="px-0"
        min-height="36"
      >
        <template #prepend>
          <v-icon size="16" class="mr-1" :color="iconColor(att.mime)">
            {{ fileIcon(att.mime) }}
          </v-icon>
        </template>
        <v-list-item-title class="text-caption">{{ att.name }}</v-list-item-title>
        <template #append>
          <v-btn
            icon
            size="x-small"
            variant="text"
            :href="`/api/repair-attachments/${att.id}/download`"
            target="_blank"
            title="Скачать"
          >
            <v-icon size="14">mdi-download</v-icon>
          </v-btn>
          <v-btn
            icon
            size="x-small"
            variant="text"
            color="error"
            title="Удалить"
            @click="confirmDelete(att)"
          >
            <v-icon size="14">mdi-delete</v-icon>
          </v-btn>
        </template>
      </v-list-item>
    </v-list>

    <!-- Delete confirmation dialog -->
    <v-dialog v-model="deleteDialog" max-width="360">
      <v-card>
        <v-card-title>Удалить файл?</v-card-title>
        <v-card-text>
          «{{ pendingDelete?.name }}» будет удалён без возможности восстановления.
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="deleteDialog = false">Отмена</v-btn>
          <v-btn color="error" variant="tonal" :loading="deleting" @click="doDelete">Удалить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { apiFetch } from '@/api'
import { useToast } from '@/composables/useToast'

interface RepairAttachment {
  id: number
  repair_id: number
  kind: string
  name: string
  mime: string | null
  size: number | null
  sha256: string | null
  uploaded_at: string
  uploaded_by_id: number | null
}

const props = defineProps<{
  repairId: number
  kind: string
  label: string
  attachments: RepairAttachment[]
}>()

const emit = defineEmits<{
  uploaded: [att: RepairAttachment]
  deleted: [id: number]
}>()

const { success, error: toastError } = useToast()

const fileInputRef = ref<HTMLInputElement>()
const uploading = ref(false)
const deleteDialog = ref(false)
const deleting = ref(false)
const pendingDelete = ref<RepairAttachment | null>(null)

function openPicker() {
  fileInputRef.value?.click()
}

async function onFileSelected(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return

  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('repair_id', String(props.repairId))
    fd.append('kind', props.kind)
    fd.append('name', file.name)
    fd.append('file', file)

    const att = await apiFetch<RepairAttachment>('/repair-attachments/upload', {
      method: 'POST',
      body: fd,
    })
    emit('uploaded', att)
    success(`Файл «${att.name}» загружен`)
  } catch (err: any) {
    const msg = err?.payload?.message ?? err?.message ?? 'Ошибка загрузки'
    toastError(msg, 0)
  } finally {
    uploading.value = false
  }
}

function confirmDelete(att: RepairAttachment) {
  pendingDelete.value = att
  deleteDialog.value = true
}

async function doDelete() {
  if (!pendingDelete.value) return
  deleting.value = true
  try {
    await apiFetch(`/api/repair-attachments/${pendingDelete.value.id}`, { method: 'DELETE' })
    emit('deleted', pendingDelete.value.id)
    deleteDialog.value = false
    success('Файл удалён')
  } catch (err: any) {
    const msg = err?.payload?.message ?? err?.message ?? 'Ошибка удаления'
    toastError(msg, 0)
  } finally {
    deleting.value = false
    pendingDelete.value = null
  }
}

function fileIcon(mime: string | null): string {
  if (!mime) return 'mdi-file-outline'
  if (mime.startsWith('image/')) return 'mdi-image-outline'
  if (mime === 'application/pdf') return 'mdi-file-pdf-box'
  if (mime.includes('word')) return 'mdi-file-word-box'
  return 'mdi-file-outline'
}

function iconColor(mime: string | null): string {
  if (!mime) return 'grey'
  if (mime.startsWith('image/')) return 'teal'
  if (mime === 'application/pdf') return 'red'
  if (mime.includes('word')) return 'blue'
  return 'grey'
}
</script>
