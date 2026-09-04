<template>
  <v-dialog :model-value="modelValue" max-width="640" persistent :fullscreen="mobile" @update:model-value="$emit('update:modelValue', $event)">
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
          <v-btn
            variant="tonal" color="primary" size="small" prepend-icon="mdi-file-download-outline"
            :loading="loadingTemplate"
            class="mb-2"
            @click="downloadTemplate">
            Скачать шаблон
          </v-btn>
          <v-alert
            v-if="templateError"
            type="error" variant="tonal" density="compact" class="mb-3"
            closable @click:close="templateError = ''">
            {{ templateError }}
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
              <div class="text-h6 font-weight-bold">{{ preview.rows_valid }}</div>
              <div class="text-caption">Валидных</div>
            </v-card>
            <v-card variant="tonal" color="error" class="flex-1 pa-3 text-center rounded">
              <div class="text-h6 font-weight-bold">{{ preview.rows_invalid }}</div>
              <div class="text-caption">Ошибок</div>
            </v-card>
            <v-card variant="tonal" color="blue" class="flex-1 pa-3 text-center rounded">
              <div class="text-h6 font-weight-bold">{{ preview.rows_total }}</div>
              <div class="text-caption">Всего строк</div>
            </v-card>
          </div>

          <!-- Parse warnings -->
          <div v-if="preview.warnings?.length" class="mb-4">
            <div class="text-caption font-weight-bold text-error mb-1">Предупреждения:</div>
            <v-list density="compact" class="border rounded">
              <v-list-item
                v-for="(warn, idx) in preview.warnings.slice(0, 5)" :key="idx"
                :subtitle="warn"
                prepend-icon="mdi-alert-circle-outline"
                color="error"
              />
              <v-list-item v-if="preview.warnings.length > 5"
                :subtitle="`... и ещё ${preview.warnings.length - 5} предупреждений`"
                prepend-icon="mdi-dots-horizontal"
              />
            </v-list>
          </div>

          <!-- Owner mapping (собственник — приоритетнее по ИНН, затем по названию) -->
          <div v-if="preview.owner_stats" class="mb-3">
            <v-chip size="small" color="success" variant="tonal" class="mr-1">По ИНН: {{ preview.owner_stats.matched_by_inn }}</v-chip>
            <v-chip size="small" color="info" variant="tonal" class="mr-1">По названию: {{ preview.owner_stats.matched_by_name }}</v-chip>
            <v-chip v-if="preview.unmapped_owners?.length" size="small" color="warning" variant="tonal">
              Вручную: {{ preview.unmapped_owners.reduce((s, o) => s + o.occurrences, 0) }}
            </v-chip>
          </div>
          <div v-if="preview.unmapped_owners?.length" class="mb-4">
            <div class="d-flex align-center mb-2">
              <div class="text-subtitle-2 font-weight-bold">Сопоставление собственника</div>
              <v-spacer />
              <v-btn size="x-small" variant="text" @click="skipAllOwners">Сбросить выбор</v-btn>
            </div>
            <div class="text-caption text-medium-emphasis mb-3">
              Не удалось определить организацию-собственника по ИНН или названию для этих значений колонки «Собственник».
              Собственник обязателен — строки без сопоставления не будут импортированы, выберите организацию вручную.
            </div>
            <v-table density="compact" class="border rounded">
              <thead>
                <tr class="bg-grey-lighten-4">
                  <th style="width:180px">Текст из файла</th>
                  <th>Организация</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="owner in preview.unmapped_owners" :key="owner.raw_text">
                  <td>
                    <div class="font-weight-medium">{{ owner.raw_text }}</div>
                    <div class="text-caption text-medium-emphasis">{{ owner.occurrences }} раз</div>
                  </td>
                  <td class="py-1">
                    <v-autocomplete
                      v-model="ownerMapping[owner.raw_text]"
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

          <!-- Region mapping (У кого в эксплуатации) -->
          <div v-if="preview.unmapped_regions?.length" class="mb-4">
            <div class="d-flex align-center mb-2">
              <div class="text-subtitle-2 font-weight-bold">Сопоставление эксплуатанта</div>
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
                <tr v-for="region in preview.unmapped_regions" :key="region.raw_text">
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
          <div v-if="preview.preview_items?.length" class="mb-2">
            <div class="text-caption font-weight-bold mb-1">Предпросмотр (первые {{ preview.preview_items.length }} строк):</div>
            <div class="border rounded overflow-auto" style="max-height:240px">
              <v-table density="compact">
                <thead>
                  <tr class="bg-grey-lighten-4">
                    <th>Гос. №</th>
                    <th>Марка/Модель</th>
                    <th>Собственник</th>
                    <th>Эксплуатант</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in preview.preview_items" :key="row.row_n">
                    <td>{{ row.plate }}</td>
                    <td>{{ [row.brand, row.model].filter(Boolean).join(' ') || '—' }}</td>
                    <td>
                      <div>{{ orgNameById(row.owner_org_id) || row.owner_text || '—' }}</div>
                      <div v-if="row.owner_match_method" class="text-caption text-medium-emphasis">
                        по {{ row.owner_match_method === 'inn' ? 'ИНН' : 'названию' }}
                      </div>
                      <div v-else-if="row.owner_text" class="text-caption text-warning">не определена</div>
                    </td>
                    <td>
                      <div>{{ orgNameById(row.assigned_org_id) || row.assigned_text || '—' }}</div>
                      <div v-if="row.assigned_match_method" class="text-caption text-medium-emphasis">
                        по {{ row.assigned_match_method === 'inn' ? 'ИНН' : 'названию' }}
                      </div>
                    </td>
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
              <div class="text-h6 font-weight-bold">{{ importResult.skipped }}</div>
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
                :subtitle="formatCommitError(importErr)"
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
import { useDisplay } from 'vuetify'
import { apiFetch } from '@/api'
import FileDropZone from '@/components/FileDropZone.vue'

const { mobile } = useDisplay()

// ─────────────── Props / Emits ───────────────

interface OrgItem {
  id: number
  name: string
}

interface RegionToMap {
  raw_text: string
  occurrences: number
}

interface MatchedOrg {
  raw_text: string
  org_id: number
  org_name: string
  method?: 'inn' | 'name'
}

interface OrgStats {
  matched_by_inn: number
  matched_by_name: number
}

interface PreviewRow {
  row_n?: number
  plate?: string
  brand?: string
  model?: string
  owner_text?: string
  owner_org_id?: number | null
  owner_match_method?: 'inn' | 'name' | null
  assigned_text?: string
  assigned_org_id?: number | null
  assigned_match_method?: 'inn' | 'name' | null
  type?: string
  state?: string
  fuel_type?: string
}

interface ImportPreviewResponse {
  session_id: string
  rows_total: number
  rows_valid: number
  rows_invalid: number
  unmapped_regions: RegionToMap[]
  matched_orgs: MatchedOrg[]
  unmapped_owners: RegionToMap[]
  matched_owners: MatchedOrg[]
  owner_stats: OrgStats | null
  assigned_stats: OrgStats | null
  preview_items: PreviewRow[]
  warnings: string[]
}

interface CommitRowError {
  row: number | string
  plate?: string | null
  msg: string
}

interface ImportCommitResponse {
  inserted: number
  updated: number
  skipped: number
  errors: CommitRowError[]
  total_processed: number
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
const loadingTemplate = ref(false)
const templateError = ref('')

const preview = reactive<ImportPreviewResponse>({
  session_id: '',
  rows_total: 0,
  rows_valid: 0,
  rows_invalid: 0,
  unmapped_regions: [],
  matched_orgs: [],
  unmapped_owners: [],
  matched_owners: [],
  owner_stats: null,
  assigned_stats: null,
  preview_items: [],
  warnings: [],
})

const regionMapping = ref<Record<string, number | null>>({})
const ownerMapping = ref<Record<string, number | null>>({})

function orgNameById(orgId?: number | null): string {
  if (!orgId) return ''
  return props.orgs.find(o => o.id === orgId)?.name || ''
}

const importResult = reactive<ImportCommitResponse>({
  inserted: 0,
  updated: 0,
  skipped: 0,
  errors: [],
  total_processed: 0,
})

function formatCommitError(err: CommitRowError): string {
  const plateInfo = err.plate ? ` (${err.plate})` : ''
  return `Строка ${err.row}${plateInfo}: ${err.msg}`
}

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
  preview.session_id = ''
  preview.rows_total = 0
  preview.rows_valid = 0
  preview.rows_invalid = 0
  preview.unmapped_regions = []
  preview.matched_orgs = []
  preview.unmapped_owners = []
  preview.matched_owners = []
  preview.owner_stats = null
  preview.assigned_stats = null
  preview.preview_items = []
  preview.warnings = []
  regionMapping.value = {}
  ownerMapping.value = {}
  importResult.inserted = 0
  importResult.updated = 0
  importResult.skipped = 0
  importResult.errors = []
  importResult.total_processed = 0
  errorInfo.show = false
  errorInfo.message = ''
  errorInfo.code = ''
  errorInfo.correlationId = ''
  templateError.value = ''
  loadingTemplate.value = false
}

function skipAllRegions() {
  for (const region of preview.unmapped_regions) {
    regionMapping.value[region.raw_text] = null
  }
}

function skipAllOwners() {
  for (const owner of preview.unmapped_owners) {
    ownerMapping.value[owner.raw_text] = null
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

async function downloadTemplate() {
  loadingTemplate.value = true
  templateError.value = ''
  try {
    const token = localStorage.getItem('auth_token')
    const res = await fetch('/api/vehicles/import-template', {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!res.ok) {
      let detail = `HTTP ${res.status}`
      try {
        const err = await res.json()
        detail = err?.detail || err?.message || err?.payload?.message || detail
      } catch {
        // тело ответа не JSON — оставляем причину по умолчанию (HTTP-статус)
      }
      throw new Error(detail)
    }
    const blob = await res.blob()

    let filename = 'Шаблон_импорта_транспорта.xlsx'
    const cd = res.headers.get('Content-Disposition') || ''
    const utf8Match = cd.match(/filename\*=UTF-8''([^;]+)/i)
    const plainMatch = cd.match(/filename="?([^";]+)"?/i)
    if (utf8Match) {
      try { filename = decodeURIComponent(utf8Match[1]) } catch { /* оставляем дефолт */ }
    } else if (plainMatch) {
      filename = plainMatch[1]
    }

    const blobUrl = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = blobUrl
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    window.URL.revokeObjectURL(blobUrl)
  } catch (err: any) {
    templateError.value = err?.message || 'Не удалось скачать шаблон'
  } finally {
    loadingTemplate.value = false
  }
}

async function doPreview() {
  if (!selectedFile.value) return
  loadingPreview.value = true
  errorInfo.show = false
  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)

    const data = await apiFetch<ImportPreviewResponse>('/vehicles-import/preview', {
      method: 'POST',
      body: formData,
    })

    preview.session_id = data.session_id
    preview.rows_total = data.rows_total
    preview.rows_valid = data.rows_valid
    preview.rows_invalid = data.rows_invalid
    preview.unmapped_regions = data.unmapped_regions ?? []
    preview.matched_orgs = data.matched_orgs ?? []
    preview.unmapped_owners = data.unmapped_owners ?? []
    preview.matched_owners = data.matched_owners ?? []
    preview.owner_stats = data.owner_stats ?? null
    preview.assigned_stats = data.assigned_stats ?? null
    preview.preview_items = data.preview_items ?? []
    preview.warnings = data.warnings ?? []

    // Initialize mapping with null (leave as text) so v-model has a starting value
    for (const region of preview.unmapped_regions) {
      regionMapping.value[region.raw_text] = null
    }
    for (const owner of preview.unmapped_owners) {
      ownerMapping.value[owner.raw_text] = null
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
    // region_mapping/owner_mapping: Dict[str, int] на backend — записи без
    // выбранной организации (null/undefined) не включаем вовсе, иначе
    // Pydantic отклонит тело запроса (int, не Optional[int]).
    const regionMapping_: Record<string, number> = {}
    for (const [regionText, orgId] of Object.entries(regionMapping.value)) {
      if (orgId !== null && orgId !== undefined) {
        regionMapping_[regionText] = orgId
      }
    }
    const ownerMapping_: Record<string, number> = {}
    for (const [ownerText, orgId] of Object.entries(ownerMapping.value)) {
      if (orgId !== null && orgId !== undefined) {
        ownerMapping_[ownerText] = orgId
      }
    }

    const data = await apiFetch<ImportCommitResponse>('/vehicles-import/commit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: preview.session_id,
        region_mapping: regionMapping_,
        owner_mapping: ownerMapping_,
        conflict_strategy: 'skip',
      }),
    })

    importResult.inserted = data.inserted ?? 0
    importResult.updated = data.updated ?? 0
    importResult.skipped = data.skipped ?? 0
    importResult.errors = data.errors ?? []
    importResult.total_processed = data.total_processed ?? 0

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
