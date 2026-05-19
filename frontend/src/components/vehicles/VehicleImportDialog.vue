<template>
  <v-dialog :model-value="modelValue" max-width="640" persistent @update:model-value="$emit('update:modelValue', $event)">
    <v-card>
      <v-card-title class="pa-5 pb-2 d-flex align-center">
        <v-icon icon="mdi-file-excel" color="green" class="mr-2" />
        Импорт ТС из Excel
        <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="close" />
      </v-card-title>

      <v-card-text class="pa-5 pt-2">

        <!-- Step 1: File upload -->
        <template v-if="step === 1">
          <v-alert type="info" variant="tonal" density="compact" class="mb-4" icon="mdi-information-outline">
            <div class="text-body-2">
              Загрузите файл реестра ТС (.xlsx). После загрузки вы увидите предпросмотр и сможете настроить сопоставление регионов с организациями.
            </div>
          </v-alert>
          <FileDropZone
            v-model="selectedFile"
            accept=".xlsx"
            hint="Excel (.xlsx) — перетащите или нажмите"
            class="mb-3"
          />
        </template>

        <!-- Step 2: Preview + region mapping -->
        <template v-else-if="step === 2">
          <!-- Stats row -->
          <div class="d-flex gap-4 mb-4">
            <v-card variant="tonal" color="success" class="flex-1 pa-3 text-center rounded">
              <div class="text-h6 font-weight-bold">{{ preview.parseable }}</div>
              <div class="text-caption">Валидных</div>
            </v-card>
            <v-card variant="tonal" color="error" class="flex-1 pa-3 text-center rounded">
              <div class="text-h6 font-weight-bold">{{ preview.total_rows - preview.parseable }}</div>
              <div class="text-caption">Ошибок</div>
            </v-card>
            <v-card variant="tonal" color="blue" class="flex-1 pa-3 text-center rounded">
              <div class="text-h6 font-weight-bold">{{ preview.total_rows }}</div>
              <div class="text-caption">Всего строк</div>
            </v-card>
          </div>

          <!-- Parse errors -->
          <div v-if="preview.errors?.length" class="mb-4">
            <div class="text-caption font-weight-bold text-error mb-1">Ошибки парсинга:</div>
            <v-list density="compact" class="border rounded">
              <v-list-item
                v-for="(err, idx) in preview.errors.slice(0, 5)" :key="idx"
                :subtitle="err"
                prepend-icon="mdi-alert-circle-outline"
                color="error"
              />
              <v-list-item v-if="preview.errors.length > 5"
                :subtitle="`... и ещё ${preview.errors.length - 5} ошибок`"
                prepend-icon="mdi-dots-horizontal"
              />
            </v-list>
          </div>

          <!-- Region mapping -->
          <div v-if="preview.regions_to_map?.length" class="mb-4">
            <div class="d-flex align-center mb-2">
              <div class="text-subtitle-2 font-weight-bold">Сопоставление регионов</div>
              <v-spacer />
              <v-btn size="x-small" variant="text" @click="skipAllRegions">Пропустить все (оставить текст)</v-btn>
            </div>
            <div class="text-caption text-medium-emphasis mb-3">
              Выберите организацию для каждого текстового значения «У кого в эксплуатации» или оставьте как текст.
            </div>
            <v-table density="compact" class="border rounded">
              <thead>
                <tr class="bg-grey-lighten-4">
                  <th style="width:180px">Текст из файла</th>
                  <th>Организация</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="region in preview.regions_to_map" :key="region.raw_text">
                  <td>
                    <div class="font-weight-medium">{{ region.raw_text }}</div>
                    <div class="text-caption text-medium-emphasis">{{ region.occurrences }} раз</div>
                  </td>
                  <td class="py-1">
                    <v-autocomplete
                      v-model="regionMapping[region.raw_text]"
                      :items="orgs"
                      item-title="name"
                      item-value="id"
                      placeholder="Оставить как текст"
                      variant="outlined"
                      density="compact"
                      clearable
                      hide-details
                    />
                  </td>
                </tr>
              </tbody>
            </v-table>
          </div>

          <!-- Preview rows -->
          <div v-if="preview.preview_rows?.length" class="mb-2">
            <div class="text-caption font-weight-bold mb-1">Предпросмотр (первые {{ preview.preview_rows.length }} строк):</div>
            <div class="border rounded overflow-auto" style="max-height:200px">
              <v-table density="compact">
                <thead>
                  <tr class="bg-grey-lighten-4">
                    <th>Гос. №</th>
                    <th>Марка/Модель</th>
                    <th>Тип</th>
                    <th>Состояние</th>
                    <th>Эксплуатант</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, idx) in preview.preview_rows" :key="idx">
                    <td>{{ row.plate }}</td>
                    <td>{{ [row.brand, row.model].filter(Boolean).join(' ') || '—' }}</td>
                    <td>{{ row.type || '—' }}</td>
                    <td>{{ row.state || '—' }}</td>
                    <td>{{ row.assigned_text || '—' }}</td>
                  </tr>
                </tbody>
              </v-table>
            </div>
          </div>
        </template>

        <!-- Step 3: Result -->
        <template v-else-if="step === 3">
          <div class="d-flex gap-4 mb-4">
            <v-card variant="tonal" color="success" class="flex-1 pa-3 text-center rounded">
              <div class="text-h6 font-weight-bold">{{ importResult.inserted }}</div>
              <div class="text-caption">Импортировано</div>
            </v-card>
            <v-card variant="tonal" color="blue" class="flex-1 pa-3 text-center rounded">
              <div class="text-h6 font-weight-bold">{{ importResult.skipped_existing }}</div>
              <div class="text-caption">Пропущено (дубли)</div>
            </v-card>
            <v-card v-if="importResult.errors?.length" variant="tonal" color="error" class="flex-1 pa-3 text-center rounded">
              <div class="text-h6 font-weight-bold">{{ importResult.errors.length }}</div>
              <div class="text-caption">Ошибок</div>
            </v-card>
          </div>

          <div v-if="importResult.errors?.length" class="mt-2">
            <div class="text-caption font-weight-bold text-error mb-1">Ошибки при импорте:</div>
            <v-list density="compact" class="border rounded">
              <v-list-item
                v-for="(importErr, idx) in importResult.errors" :key="idx"
                :subtitle="importErr"
                prepend-icon="mdi-alert-circle-outline"
                color="error"
              />
            </v-list>
          </div>

          <!-- Error copy -->
          <div v-if="errorInfo.show" class="mt-4 pa-3 border rounded bg-red-lighten-5">
            <div class="d-flex align-center mb-1">
              <span class="text-caption font-weight-bold text-error">Ошибка</span>
              <v-spacer />
              <v-btn size="x-small" variant="text" prepend-icon="mdi-content-copy" @click="copyErrorInfo">Скопировать</v-btn>
            </div>
            <div class="text-body-2">{{ errorInfo.message }}</div>
            <div v-if="errorInfo.code" class="text-caption text-medium-emphasis mt-1">Код: {{ errorInfo.code }}</div>
            <div v-if="errorInfo.correlationId" class="text-caption text-medium-emphasis">ID: {{ errorInfo.correlationId }}</div>
          </div>
        </template>

      </v-card-text>

      <v-card-actions class="pa-5 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="close">
          {{ step === 3 ? 'Закрыть' : 'Отмена' }}
        </v-btn>
        <v-btn
          v-if="step === 1"
          color="blue" variant="flat"
          :loading="loadingPreview"
          :disabled="!selectedFile"
          @click="doPreview">
          Загрузить
        </v-btn>
        <v-btn
          v-else-if="step === 2"
          color="primary" variant="flat"
          :loading="loadingCommit"
          @click="doCommit">
          Подтвердить импорт
        </v-btn>
        <v-btn
          v-else-if="step === 3"
          color="primary" variant="flat"
          @click="close">
          Готово
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, watch } from 'vue'
import { apiFetch } from '@/api'
import FileDropZone from '@/components/FileDropZone.vue'

// ─────────────── Props / Emits ───────────────

interface OrgItem {
  id: number
  name: string
}

interface RegionToMap {
  raw_text: string
  occurrences: number
}

interface PreviewRow {
  plate?: string
  brand?: string
  model?: string
  type?: string
  state?: string
  assigned_text?: string
}

interface ImportPreviewResponse {
  total_rows: number
  parseable: number
  errors: string[]
  regions_to_map: RegionToMap[]
  preview_rows: PreviewRow[]
  import_session_id: string
}

interface ImportCommitResponse {
  inserted: number
  skipped_existing: number
  errors: string[]
}

const props = defineProps<{
  modelValue: boolean
  orgs: OrgItem[]
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
  (e: 'imported'): void
}>()

// ─────────────── State ───────────────

const step = ref<1 | 2 | 3>(1)
const selectedFile = ref<File | null>(null)
const loadingPreview = ref(false)
const loadingCommit = ref(false)

const preview = reactive<ImportPreviewResponse>({
  total_rows: 0,
  parseable: 0,
  errors: [],
  regions_to_map: [],
  preview_rows: [],
  import_session_id: '',
})

const regionMapping = ref<Record<string, number | null>>({})

const importResult = reactive<ImportCommitResponse>({
  inserted: 0,
  skipped_existing: 0,
  errors: [],
})

const errorInfo = reactive({
  show: false,
  message: '',
  code: '',
  correlationId: '',
})

// ─────────────── Helpers ───────────────

function close() {
  emit('update:modelValue', false)
}

function reset() {
  step.value = 1
  selectedFile.value = null
  loadingPreview.value = false
  loadingCommit.value = false
  preview.total_rows = 0
  preview.parseable = 0
  preview.errors = []
  preview.regions_to_map = []
  preview.preview_rows = []
  preview.import_session_id = ''
  regionMapping.value = {}
  importResult.inserted = 0
  importResult.skipped_existing = 0
  importResult.errors = []
  errorInfo.show = false
  errorInfo.message = ''
  errorInfo.code = ''
  errorInfo.correlationId = ''
}

function skipAllRegions() {
  for (const region of preview.regions_to_map) {
    regionMapping.value[region.raw_text] = null
  }
}

function showErr(err: any) {
  const payload = err?.payload ?? err?.detail ?? err
  errorInfo.message = payload?.message ?? payload?.detail ?? String(err)
  errorInfo.code = payload?.code ?? ''
  errorInfo.correlationId = payload?.correlation_id ?? ''
  errorInfo.show = true
}

function copyErrorInfo() {
  const text = [
    errorInfo.message,
    errorInfo.code ? `Код: ${errorInfo.code}` : '',
    errorInfo.correlationId ? `ID: ${errorInfo.correlationId}` : '',
  ].filter(Boolean).join('\n')
  navigator.clipboard.writeText(text).catch(() => {})
}

// ─────────────── API calls ───────────────

async function doPreview() {
  if (!selectedFile.value) return
  loadingPreview.value = true
  errorInfo.show = false
  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)

    const data = await apiFetch<ImportPreviewResponse>('/api/vehicles-import/preview', {
      method: 'POST',
      body: formData,
    })

    preview.total_rows = data.total_rows
    preview.parseable = data.parseable
    preview.errors = data.errors ?? []
    preview.regions_to_map = data.regions_to_map ?? []
    preview.preview_rows = data.preview_rows ?? []
    preview.import_session_id = data.import_session_id

    // Initialize region mapping with null (leave as text)
    for (const region of preview.regions_to_map) {
      regionMapping.value[region.raw_text] = null
    }

    step.value = 2
  } catch (err: any) {
    showErr(err)
  } finally {
    loadingPreview.value = false
  }
}

async function doCommit() {
  loadingCommit.value = true
  errorInfo.show = false
  try {
    const regionOrgMap: Record<string, number | null> = {}
    for (const [regionText, orgId] of Object.entries(regionMapping.value)) {
      regionOrgMap[regionText] = orgId ?? null
    }

    const data = await apiFetch<ImportCommitResponse>('/api/vehicles-import/commit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        import_session_id: preview.import_session_id,
        region_org_map: regionOrgMap,
        conflict_strategy: 'skip',
      }),
    })

    importResult.inserted = data.inserted ?? 0
    importResult.skipped_existing = data.skipped_existing ?? 0
    importResult.errors = data.errors ?? []

    step.value = 3
    emit('imported')
  } catch (err: any) {
    showErr(err)
    step.value = 3
  } finally {
    loadingCommit.value = false
  }
}

// Reset when dialog closes
watch(() => props.modelValue, (val) => {
  if (!val) {
    // delay to avoid visual flash on close
    setTimeout(() => reset(), 300)
  }
})
</script>
