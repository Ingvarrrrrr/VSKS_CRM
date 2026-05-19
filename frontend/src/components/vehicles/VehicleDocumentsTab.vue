<template>
  <div class="vehicle-documents-tab pa-4">
    <!-- Loading skeleton -->
    <template v-if="loading">
      <v-row dense>
        <v-col v-for="n in 6" :key="n" cols="12" sm="6" md="4">
          <v-skeleton-loader type="card" />
        </v-col>
      </v-row>
    </template>

    <!-- Load error -->
    <v-alert
      v-else-if="loadError"
      type="error"
      variant="tonal"
      class="mb-4"
    >
      <div class="text-body-2">{{ loadError.message }}</div>
      <div v-if="loadError.code" class="text-caption text-medium-emphasis">
        Код: {{ loadError.code }}<span v-if="loadError.correlation_id"> &middot; {{ loadError.correlation_id }}</span>
      </div>
      <template #append>
        <v-btn size="small" variant="text" @click="loadAttachments">Повторить</v-btn>
      </template>
    </v-alert>

    <template v-else>
      <!-- Fixed document slots -->
      <div class="text-subtitle-1 font-weight-medium mb-3">Документы ТС</div>
      <v-row dense>
        <v-col
          v-for="slot in FIXED_SLOTS"
          :key="slot.kind"
          cols="12"
          sm="6"
          md="4"
        >
          <VehicleAttachmentSlot
            :vehicle-id="vehicleId"
            :kind="slot.kind"
            :label="slot.label"
            :support-policy-dates="slot.supportPolicyDates"
            :attachment="attachmentByKind(slot.kind)"
            @uploaded="onUploaded"
            @deleted="onDeleted"
          />
        </v-col>
      </v-row>

      <!-- Other documents section -->
      <v-divider class="my-4" />
      <div class="d-flex align-center justify-space-between mb-3">
        <span class="text-subtitle-1 font-weight-medium">Прочее</span>
        <v-btn
          size="small"
          variant="tonal"
          prepend-icon="mdi-plus"
          @click="openOtherDialog"
        >Добавить документ</v-btn>
      </div>

      <v-row v-if="otherAttachments.length" dense>
        <v-col
          v-for="att in otherAttachments"
          :key="att.id"
          cols="12"
          sm="6"
          md="4"
        >
          <VehicleAttachmentSlot
            :vehicle-id="vehicleId"
            kind="other"
            :label="att.name"
            :attachment="att"
            @uploaded="onUploaded"
            @deleted="onDeleted"
          />
        </v-col>
      </v-row>
      <p v-else class="text-body-2 text-medium-emphasis">Нет дополнительных документов.</p>
    </template>

    <!-- Add "other" document dialog -->
    <v-dialog v-model="otherDialog" max-width="420">
      <v-card>
        <v-card-title class="text-subtitle-1">Добавить документ</v-card-title>
        <v-card-text>
          <v-text-field
            v-model="otherName"
            label="Название документа"
            density="compact"
            variant="outlined"
            hide-details="auto"
            class="mb-3"
            autofocus
          />
          <FileDropZone
            v-model="otherFile"
            accept=".pdf,.jpg,.jpeg,.png,.webp,.heic,.doc,.docx"
            hint="PDF, JPG, PNG, DOCX до 25 МБ"
          />
          <div v-if="otherUploadError" class="mt-2">
            <v-alert
              type="error"
              density="compact"
              variant="tonal"
              closable
              @click:close="otherUploadError = null"
            >
              <div class="text-body-2">{{ otherUploadError.message }}</div>
              <div v-if="otherUploadError.code" class="text-caption text-medium-emphasis">
                Код: {{ otherUploadError.code }}<span v-if="otherUploadError.correlation_id"> &middot; {{ otherUploadError.correlation_id }}</span>
              </div>
            </v-alert>
          </div>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" :disabled="otherUploading" @click="otherDialog = false">Отмена</v-btn>
          <v-btn
            color="primary"
            variant="tonal"
            :loading="otherUploading"
            :disabled="!otherFile || !otherName.trim()"
            @click="uploadOther"
          >Загрузить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import VehicleAttachmentSlot, { type VehicleAttachment } from '@/components/vehicles/VehicleAttachmentSlot.vue'
import FileDropZone from '@/components/FileDropZone.vue'

// ── Types ─────────────────────────────────────────────────────────────────────

interface ApiError {
  message: string
  code?: string
  correlation_id?: string
}

interface FixedSlot {
  kind: 'sts' | 'pts' | 'osago' | 'kasko' | 'dk' | 'permit_to'
  label: string
  supportPolicyDates?: boolean
}

// ── Props ─────────────────────────────────────────────────────────────────────

const props = defineProps<{
  vehicleId: number
}>()

// ── Constants ─────────────────────────────────────────────────────────────────

const FIXED_SLOTS: FixedSlot[] = [
  { kind: 'sts', label: 'СТС (свидетельство о регистрации)' },
  { kind: 'pts', label: 'ПТС (паспорт ТС)' },
  { kind: 'osago', label: 'ОСАГО', supportPolicyDates: true },
  { kind: 'kasko', label: 'КАСКО', supportPolicyDates: true },
  { kind: 'dk', label: 'Диагностическая карта', supportPolicyDates: true },
  { kind: 'permit_to', label: 'Разрешение ТО' },
]

// ── State ─────────────────────────────────────────────────────────────────────

const attachments = ref<VehicleAttachment[]>([])
const loading = ref(false)
const loadError = ref<ApiError | null>(null)

const otherDialog = ref(false)
const otherName = ref('')
const otherFile = ref<File | null>(null)
const otherUploading = ref(false)
const otherUploadError = ref<ApiError | null>(null)

// ── Computed ──────────────────────────────────────────────────────────────────

const otherAttachments = computed(() =>
  attachments.value.filter((a) => a.kind === 'other'),
)

function attachmentByKind(kind: string): VehicleAttachment | null {
  return attachments.value.find((a) => a.kind === kind) ?? null
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function parseApiError(err: unknown): ApiError {
  if (typeof err === 'object' && err !== null) {
    const e = err as Record<string, unknown>
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

// ── Load ──────────────────────────────────────────────────────────────────────

async function loadAttachments() {
  loading.value = true
  loadError.value = null
  try {
    const res = await fetch(`/api/vehicle-attachments?vehicle_id=${props.vehicleId}`)
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw body
    }
    attachments.value = await res.json()
  } catch (err) {
    loadError.value = parseApiError(err)
  } finally {
    loading.value = false
  }
}

// ── Event handlers ────────────────────────────────────────────────────────────

function onUploaded(att: VehicleAttachment) {
  const idx = attachments.value.findIndex((a) => a.id === att.id)
  if (idx >= 0) {
    attachments.value[idx] = att
  } else {
    attachments.value.push(att)
  }
}

function onDeleted(id: number) {
  attachments.value = attachments.value.filter((a) => a.id !== id)
}

// ── Other document upload ─────────────────────────────────────────────────────

function openOtherDialog() {
  otherName.value = ''
  otherFile.value = null
  otherUploadError.value = null
  otherDialog.value = true
}

async function uploadOther() {
  if (!otherFile.value || !otherName.value.trim()) return
  otherUploading.value = true
  otherUploadError.value = null
  try {
    const fd = new FormData()
    fd.append('vehicle_id', String(props.vehicleId))
    fd.append('kind', 'other')
    fd.append('name', otherName.value.trim())
    fd.append('file', otherFile.value)

    const res = await fetch('/api/vehicle-attachments/upload', {
      method: 'POST',
      body: fd,
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw body
    }
    const att: VehicleAttachment = await res.json()
    attachments.value.push(att)
    otherDialog.value = false
  } catch (err) {
    otherUploadError.value = parseApiError(err)
  } finally {
    otherUploading.value = false
  }
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────

onMounted(loadAttachments)
</script>

<style scoped>
.vehicle-documents-tab {
  min-height: 200px;
}
</style>
