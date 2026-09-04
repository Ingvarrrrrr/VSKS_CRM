<template>
  <v-card variant="outlined" class="attachment-slot pa-3">
    <div class="d-flex align-center justify-space-between mb-2">
      <span class="text-subtitle-2 font-weight-medium">{{ label }}</span>
      <v-chip
        v-if="attachment"
        size="x-small"
        color="success"
        variant="tonal"
      >загружен</v-chip>
      <v-chip v-else size="x-small" color="grey" variant="tonal">нет файла</v-chip>
    </div>

    <!-- Loaded state -->
    <template v-if="attachment">
      <div class="d-flex align-center gap-2 mb-2">
        <v-icon size="20" :color="mimeIconColor(attachment.mime)">{{ mimeIcon(attachment.mime) }}</v-icon>
        <div class="flex-grow-1 min-width-0">
          <div class="text-body-2 text-truncate">{{ attachment.name }}</div>
          <div class="text-caption text-medium-emphasis">
            {{ formatSize(attachment.size) }} &middot; {{ formatDate(attachment.uploaded_at) }}
          </div>
        </div>
        <v-btn
          size="x-small"
          icon
          variant="text"
          color="primary"
          :loading="downloading"
          title="Скачать"
          @click="downloadFile"
        >
          <v-icon size="16">mdi-download</v-icon>
        </v-btn>
        <v-btn
          size="x-small"
          icon
          variant="text"
          color="error"
          :loading="deleting"
          title="Удалить"
          @click="confirmDelete"
        >
          <v-icon size="16">mdi-delete-outline</v-icon>
        </v-btn>
      </div>

      <!-- Policy dates for osago/kasko/dk -->
      <template v-if="supportPolicyDates">
        <v-divider class="mb-2" />
        <v-row dense>
          <v-col cols="12">
            <v-text-field
              v-model="policyForm.policy_number"
              label="Номер полиса / удостоверения"
              density="compact"
              variant="outlined"
              hide-details="auto"
              :loading="patchLoading"
              @blur="savePolicyMeta"
            />
          </v-col>
          <v-col cols="6">
            <v-text-field
              v-model="policyForm.issued_at"
              label="Выдан"
              type="date"
              density="compact"
              variant="outlined"
              hide-details="auto"
              :loading="patchLoading"
              @blur="savePolicyMeta"
            />
          </v-col>
          <v-col cols="6">
            <v-text-field
              v-model="policyForm.expires_at"
              label="Истекает"
              type="date"
              density="compact"
              variant="outlined"
              hide-details="auto"
              :loading="patchLoading"
              :class="isExpired ? 'expired-field' : ''"
              @blur="savePolicyMeta"
            />
          </v-col>
        </v-row>
        <div v-if="patchError" class="mt-1">
          <v-alert
            type="error"
            density="compact"
            variant="tonal"
            closable
            @click:close="patchError = null"
          >
            <div class="text-body-2">{{ patchError.message }}</div>
            <div v-if="patchError.code" class="text-caption text-medium-emphasis">
              Код: {{ patchError.code }}<span v-if="patchError.correlation_id"> &middot; {{ patchError.correlation_id }}</span>
            </div>
          </v-alert>
        </div>
      </template>
    </template>

    <!-- Empty state — FileDropZone -->
    <template v-else>
      <FileDropZone
        v-model="selectedFile"
        :accept="ALLOWED_ACCEPT"
        hint="PDF, JPG, PNG, DOCX до 25 МБ"
        @update:model-value="onFileSelected"
      />
      <div v-if="uploadError" class="mt-2">
        <v-alert
          type="error"
          density="compact"
          variant="tonal"
          closable
          @click:close="uploadError = null"
        >
          <div class="text-body-2">{{ uploadError.message }}</div>
          <div v-if="uploadError.code" class="text-caption text-medium-emphasis">
            Код: {{ uploadError.code }}<span v-if="uploadError.correlation_id"> &middot; {{ uploadError.correlation_id }}</span>
          </div>
        </v-alert>
      </div>
      <v-progress-linear v-if="uploading" indeterminate color="primary" class="mt-2" />
    </template>

    <!-- Delete confirmation dialog -->
    <v-dialog v-model="deleteDialog" max-width="360">
      <v-card>
        <v-card-title class="text-subtitle-1">Удалить документ?</v-card-title>
        <v-card-text>
          <span class="text-body-2">«{{ attachment?.name }}» будет удалён без возможности восстановления.</span>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="deleteDialog = false">Отмена</v-btn>
          <v-btn color="error" variant="tonal" :loading="deleting" @click="doDelete">Удалить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-card>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import FileDropZone from '@/components/FileDropZone.vue'
import { apiFetch } from '@/api'

// ── Types ─────────────────────────────────────────────────────────────────────

export interface VehicleAttachment {
  id: number
  vehicle_id: number
  kind: string
  name: string
  mime: string | null
  size: number | null
  sha256: string | null
  uploaded_at: string
  uploaded_by_id: number | null
  policy_number: string | null
  issued_at: string | null
  expires_at: string | null
}

type AttachmentKind = 'sts' | 'pts' | 'osago' | 'kasko' | 'dk' | 'permit_to' | 'photo' | 'other'

interface ApiError {
  message: string
  code?: string
  correlation_id?: string
}

// ── Props / Emits ─────────────────────────────────────────────────────────────

const props = defineProps<{
  vehicleId: number
  kind: AttachmentKind
  label: string
  supportPolicyDates?: boolean
  attachment: VehicleAttachment | null
}>()

const emit = defineEmits<{
  uploaded: [att: VehicleAttachment]
  deleted: [id: number]
}>()

// ── Constants ─────────────────────────────────────────────────────────────────

const ALLOWED_ACCEPT = '.pdf,.jpg,.jpeg,.png,.webp,.heic,.doc,.docx'

// ── State ─────────────────────────────────────────────────────────────────────

const selectedFile = ref<File | null>(null)
const uploading = ref(false)
const downloading = ref(false)
const uploadError = ref<ApiError | null>(null)
const deleting = ref(false)
const deleteDialog = ref(false)
const patchLoading = ref(false)
const patchError = ref<ApiError | null>(null)

const policyForm = ref({
  policy_number: '',
  issued_at: '',
  expires_at: '',
})

// ── Watchers ──────────────────────────────────────────────────────────────────

watch(
  () => props.attachment,
  (att) => {
    if (att && props.supportPolicyDates) {
      policyForm.value = {
        policy_number: att.policy_number ?? '',
        issued_at: att.issued_at ?? '',
        expires_at: att.expires_at ?? '',
      }
    }
  },
  { immediate: true },
)

// ── Computed ──────────────────────────────────────────────────────────────────

const isExpired = computed(() => {
  if (!policyForm.value.expires_at) return false
  return new Date(policyForm.value.expires_at) < new Date()
})

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatSize(bytes: number | null): string {
  if (!bytes) return '—'
  if (bytes < 1024) return `${bytes} Б`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} КБ`
  return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
  } catch {
    return iso
  }
}

function mimeIcon(mime: string | null): string {
  if (!mime) return 'mdi-file-outline'
  if (mime.startsWith('image/')) return 'mdi-file-image-outline'
  if (mime === 'application/pdf') return 'mdi-file-pdf-box'
  if (mime.includes('word')) return 'mdi-file-word-outline'
  return 'mdi-file-outline'
}

function mimeIconColor(mime: string | null): string {
  if (!mime) return 'grey'
  if (mime.startsWith('image/')) return 'blue'
  if (mime === 'application/pdf') return 'red'
  if (mime.includes('word')) return 'blue-darken-3'
  return 'grey'
}

function parseApiError(err: unknown): ApiError {
  if (typeof err === 'object' && err !== null) {
    const e = err as Record<string, unknown>
    // apiFetch (frontend/src/api.ts) кидает Error с полем payload = {code, message, correlation_id}
    const payload = e['payload'] as Record<string, unknown> | undefined
    if (payload) {
      return {
        message: (payload['message'] as string) ?? 'Неизвестная ошибка',
        code: payload['code'] as string | undefined,
        correlation_id: payload['correlation_id'] as string | undefined,
      }
    }
    const detail = e['detail'] as Record<string, unknown> | undefined
    if (detail) {
      return {
        message: (detail['message'] as string) ?? 'Неизвестная ошибка',
        code: detail['code'] as string | undefined,
        correlation_id: detail['correlation_id'] as string | undefined,
      }
    }
    return { message: (e['message'] as string) ?? String(err) }
  }
  return { message: String(err) }
}

// ── Download ──────────────────────────────────────────────────────────────────

async function downloadFile() {
  if (!props.attachment) return
  downloading.value = true
  try {
    // Бинарный ответ — apiFetch тут не годится, ручной fetch с Bearer-токеном,
    // как в VehicleDetailView.loadHeroPhoto(). Обычный <a href> не может передать
    // заголовок Authorization, поэтому раньше скачивание уходило в 401.
    const token = localStorage.getItem('auth_token')
    const res = await fetch(`/api/vehicle-attachments/${props.attachment.id}/download`, {
      credentials: 'include',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = props.attachment.name
    document.body.appendChild(a)
    a.click()
    a.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (err) {
    uploadError.value = parseApiError(err)
  } finally {
    downloading.value = false
  }
}

// ── Upload ────────────────────────────────────────────────────────────────────

async function onFileSelected(file: File | null) {
  if (!file) return
  uploadError.value = null
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('vehicle_id', String(props.vehicleId))
    fd.append('kind', props.kind)
    fd.append('file', file)

    // apiFetch добавляет Authorization: Bearer автоматически (frontend/src/api.ts) —
    // прямой fetch() без токена уходил в 401, авторизация в проекте не на cookie.
    const att = await apiFetch<VehicleAttachment>('/vehicle-attachments/upload', {
      method: 'POST',
      body: fd,
      suppressErrorDialog: true,
    })
    emit('uploaded', att)
    selectedFile.value = null
  } catch (err) {
    uploadError.value = parseApiError(err)
    selectedFile.value = null
  } finally {
    uploading.value = false
  }
}

// ── Delete ────────────────────────────────────────────────────────────────────

function confirmDelete() {
  deleteDialog.value = true
}

async function doDelete() {
  if (!props.attachment) return
  deleting.value = true
  try {
    await apiFetch(`/vehicle-attachments/${props.attachment.id}`, {
      method: 'DELETE',
      suppressErrorDialog: true,
    })
    deleteDialog.value = false
    emit('deleted', props.attachment.id)
  } catch (err) {
    deleteDialog.value = false
    uploadError.value = parseApiError(err)
  } finally {
    deleting.value = false
  }
}

// ── Patch policy meta ─────────────────────────────────────────────────────────

async function savePolicyMeta() {
  if (!props.attachment) return
  patchError.value = null
  patchLoading.value = true
  try {
    const fd = new FormData()
    if (policyForm.value.policy_number !== (props.attachment.policy_number ?? '')) {
      fd.append('policy_number', policyForm.value.policy_number)
    }
    if (policyForm.value.issued_at !== (props.attachment.issued_at ?? '')) {
      fd.append('issued_at', policyForm.value.issued_at)
    }
    if (policyForm.value.expires_at !== (props.attachment.expires_at ?? '')) {
      fd.append('expires_at', policyForm.value.expires_at)
    }
    // Nothing changed
    if (![...fd.entries()].length) return

    const updated = await apiFetch<VehicleAttachment>(`/vehicle-attachments/${props.attachment.id}`, {
      method: 'PATCH',
      body: fd,
      suppressErrorDialog: true,
    })
    emit('uploaded', updated)
  } catch (err) {
    patchError.value = parseApiError(err)
  } finally {
    patchLoading.value = false
  }
}
</script>

<style scoped>
.attachment-slot {
  min-height: 80px;
}
.expired-field :deep(.v-field) {
  --v-field-border-color: rgb(var(--v-theme-error));
}
.min-width-0 {
  min-width: 0;
}
</style>
