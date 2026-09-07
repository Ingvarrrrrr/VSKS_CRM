<template>
  <!-- ── Phase 32: Quick File Viewer Dialog ── -->
  <v-dialog v-model="state.show" max-width="560" scrollable>
    <v-card>
      <v-card-title class="pa-4 d-flex align-center">
        <v-icon icon="mdi-paperclip" color="teal" class="mr-2" />
        Файлы закупки
        <span v-if="state.purchaseSubject" class="text-body-2 text-medium-emphasis ml-2">— {{ state.purchaseSubject }}</span>
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="state.show = false" />
      </v-card-title>
      <v-divider />
      <v-card-text class="pa-0" style="min-height:120px">
        <div v-if="state.loading" class="d-flex justify-center align-center py-8">
          <v-progress-circular indeterminate color="teal" />
        </div>
        <v-list v-else-if="state.files.length" density="compact">
          <v-list-item
            v-for="f in state.files"
            :key="f.id"
            :prepend-icon="fileIcon(f.mime_type)"
            class="py-2"
          >
            <template #title>
              <span class="text-body-2">{{ f.filename }}</span>
            </template>
            <template #subtitle>
              <v-chip size="x-small" :color="fileTypeColor(f.file_type)" variant="tonal" class="mr-1">
                {{ fileTypeLabel(f.file_type) }}
              </v-chip>
              <span v-if="f.size" class="text-caption text-medium-emphasis">{{ (f.size / 1024).toFixed(0) }} КБ</span>
            </template>
            <template #append>
              <v-btn size="small" variant="tonal" color="teal" @click.stop="openFile(f)">
                Открыть
              </v-btn>
            </template>
          </v-list-item>
        </v-list>
        <div v-else class="text-center text-medium-emphasis py-8">Нет файлов</div>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { reactive } from 'vue'
import { apiFetch } from '@/api'
import type { ToastType } from '@/composables/useToast'
import type { Purchase, QuickFile } from '@/composables/orders/ordersTypes'

const props = defineProps<{
  showSnack: (text: string, color?: ToastType) => void
}>()

const FILE_TYPE_LABELS_QV: Record<string, string> = {
  contract: 'Договор', act: 'Акт', invoice: 'Счёт', payment: 'Платёж',
  acceptance_doc: 'Приёмка', scan: 'Скан', other: 'Прочее',
}

const state = reactive({
  show: false,
  loading: false,
  purchaseId: 0,
  purchaseSubject: '',
  files: [] as QuickFile[],
})

function fileIcon(mime?: string): string {
  if (mime === 'application/pdf') return 'mdi-file-pdf-box'
  if (mime?.startsWith('image/')) return 'mdi-file-image'
  return 'mdi-file-document-outline'
}
function fileTypeColor(t?: string): string {
  const m: Record<string, string> = { contract: 'blue', act: 'green', invoice: 'orange', payment: 'teal', acceptance_doc: 'purple', scan: 'grey' }
  return m[t || ''] || 'grey'
}
function fileTypeLabel(t?: string): string {
  return FILE_TYPE_LABELS_QV[t || ''] || t || 'Прочее'
}
async function openFile(f: QuickFile) {
  const token = localStorage.getItem('auth_token')
  const res = await fetch(`/api/purchases/${state.purchaseId}/files/${f.id}/download`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) { return }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  window.open(url, '_blank')
  setTimeout(() => URL.revokeObjectURL(url), 10000)
}

async function open(item: Purchase) {
  state.purchaseId = item.id
  state.purchaseSubject = item.subject || item.item_name || `#${item.id}`
  state.files = []
  state.loading = true
  state.show = true
  try {
    state.files = await apiFetch<QuickFile[]>(`/purchases/${item.id}/files`)
  } catch (e: any) {
    props.showSnack(`[${e?.status || ''}] ${e?.detail || e?.message || 'Ошибка загрузки файлов'}`, 'error')
    state.show = false
  } finally {
    state.loading = false
  }
}

defineExpose({ open })
</script>
