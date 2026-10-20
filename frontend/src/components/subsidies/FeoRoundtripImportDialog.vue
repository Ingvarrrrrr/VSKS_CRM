<template>
  <v-dialog v-model="show" max-width="760" scrollable>
    <v-card>
      <v-card-title class="d-flex align-center pa-4">
        <v-icon icon="mdi-file-upload-outline" color="teal" class="mr-2" />
        Загрузить выгрузку ФЭО
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="close" />
      </v-card-title>

      <v-card-text class="pa-4">
        <!-- Шаг 1: выбор файла -->
        <template v-if="!preview">
          <p class="text-body-2 text-medium-emphasis mb-3">
            Файл из «Выгрузить ФЭО»: изменённые суммы и названия, новые строки.
            Для новой субсидии — выгрузите пустой файл, заполните и загрузите.
          </p>
          <v-file-input
            v-model="file"
            label="Файл .xlsx"
            accept=".xlsx"
            density="compact"
            variant="outlined"
            prepend-icon="mdi-microsoft-excel"
            hide-details
            @update:model-value="onFileChange"
          />
          <div v-if="loading" class="d-flex align-center mt-4" style="gap:8px">
            <v-progress-circular indeterminate size="20" width="2" color="teal" />
            <span class="text-caption text-medium-emphasis">Разбор файла…</span>
          </div>
          <div v-if="loadError" class="text-caption text-error mt-3">{{ loadError }}</div>
        </template>

        <!-- Шаг 2: предпросмотр -->
        <template v-else>
          <div class="text-caption text-medium-emphasis mb-3">Файл: {{ file?.name }}</div>

          <v-alert v-if="preview.errors.length" type="error" variant="tonal" density="compact" class="mb-3">
            <div class="font-weight-medium mb-1">Ошибки — загрузка невозможна</div>
            <div v-for="(err, i) in preview.errors" :key="i" class="d-flex align-start" style="gap:6px">
              <v-icon icon="mdi-arrow-right-thin" size="14" class="mt-1" />
              <span>{{ err.row != null ? `Строка ${err.row}: ` : '' }}{{ err.message }}</span>
            </div>
          </v-alert>

          <v-alert v-if="preview.warnings.length" type="warning" variant="tonal" density="compact" class="mb-3">
            <div v-for="(w, i) in preview.warnings" :key="i">{{ w.message }}</div>
          </v-alert>

          <v-expansion-panels v-model="openPanels" multiple variant="accordion" class="mb-2">
            <v-expansion-panel v-if="preview.changes.length" value="changes">
              <v-expansion-panel-title>Изменения было → стало ({{ preview.changes.length }})</v-expansion-panel-title>
              <v-expansion-panel-text>
                <div v-for="(c, i) in preview.changes" :key="i" class="roundtrip-row">
                  <span class="text-caption text-medium-emphasis mr-1">стр. {{ c.row }}</span>
                  <b>{{ c.name }}</b> — {{ fieldLabel(c.field) }}:
                  <span class="text-medium-emphasis">{{ fmtVal(c.old) }}</span>
                  <v-icon icon="mdi-arrow-right-thin" size="14" class="mx-1" />
                  <span class="font-weight-medium">{{ fmtVal(c.new) }}</span>
                </div>
              </v-expansion-panel-text>
            </v-expansion-panel>

            <v-expansion-panel v-if="preview.created.length" value="created">
              <v-expansion-panel-title>Новые строки ({{ preview.created.length }})</v-expansion-panel-title>
              <v-expansion-panel-text>
                <div v-for="(c, i) in preview.created" :key="i" class="roundtrip-row">
                  <span class="text-caption text-medium-emphasis mr-1">стр. {{ c.row }}</span>
                  {{ c.kind === 'category' ? 'Категория' : 'Позиция' }} «{{ c.name }}»
                  <span v-if="c.parent_name" class="text-medium-emphasis"> — в «{{ c.parent_name }}»</span>
                </div>
              </v-expansion-panel-text>
            </v-expansion-panel>

            <v-expansion-panel v-if="preview.moved.length" value="moved">
              <v-expansion-panel-title>Перенесены ({{ preview.moved.length }})</v-expansion-panel-title>
              <v-expansion-panel-text>
                <div v-for="(m, i) in preview.moved" :key="i" class="roundtrip-row">
                  <span class="text-caption text-medium-emphasis mr-1">стр. {{ m.row }}</span>
                  «{{ m.name }}»: {{ m.old_parent_name || '—' }}
                  <v-icon icon="mdi-arrow-right-thin" size="14" class="mx-1" />
                  {{ m.new_parent_name || '—' }}
                </div>
              </v-expansion-panel-text>
            </v-expansion-panel>

            <v-expansion-panel v-if="preview.missing.length" value="missing">
              <v-expansion-panel-title>Нет в файле ({{ preview.missing.length }})</v-expansion-panel-title>
              <v-expansion-panel-text>
                <div class="text-caption text-medium-emphasis mb-2">
                  Эти записи не трогаются — они просто отсутствуют в загруженном файле.
                </div>
                <div v-for="(m, i) in preview.missing" :key="i" class="roundtrip-row">
                  {{ m.type === 'category' ? 'Категория' : 'Позиция' }} «{{ m.name }}»
                </div>
              </v-expansion-panel-text>
            </v-expansion-panel>
          </v-expansion-panels>

          <div v-if="!preview.changes.length && !preview.created.length && !preview.moved.length" class="text-body-2 text-medium-emphasis">
            Изменений не найдено.
          </div>
        </template>
      </v-card-text>

      <v-card-actions class="pa-4 pt-0">
        <v-btn v-if="preview" variant="text" :disabled="applying" @click="reset">Назад</v-btn>
        <v-spacer />
        <v-btn variant="text" :disabled="applying" @click="close">Отмена</v-btn>
        <v-btn
          v-if="preview"
          color="success" variant="flat" prepend-icon="mdi-upload"
          :disabled="preview.errors.length > 0"
          :loading="applying"
          @click="doApply"
        >
          Загрузить
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { apiFetch } from '@/api'
import type { ToastType } from '@/composables/useToast'

const props = defineProps<{
  subsidyId: number | null
  showSnack: (text: string, color?: ToastType) => void
  onApplied: () => void | Promise<void>
}>()

interface RoundtripChange { row: number; kind: string; id: number; name: string; field: string; old: any; new: any }
interface RoundtripCreated { row: number; kind: string; name: string; parent_name: string | null }
interface RoundtripMoved { row: number; kind: string; id: number; name: string; old_parent_name: string | null; new_parent_name: string | null }
interface RoundtripMissing { id: number; name: string; type: string }
interface RoundtripError { row: number | null; message: string }
interface RoundtripWarning { message: string }
interface RoundtripPreview {
  changes: RoundtripChange[]
  created: RoundtripCreated[]
  moved: RoundtripMoved[]
  missing: RoundtripMissing[]
  errors: RoundtripError[]
  warnings: RoundtripWarning[]
}

const show = ref(false)
const file = ref<File | null>(null)
const loading = ref(false)
const applying = ref(false)
const loadError = ref('')
const preview = ref<RoundtripPreview | null>(null)
const openPanels = ref<string[]>(['changes', 'created', 'moved'])

const FIELD_LABELS: Record<string, string> = {
  name: 'Наименование', code: 'Код', appendix: 'Прил.', is_active: 'Активна',
  feo_amount: 'Финансирование по ФЭО', quantity: 'Кол-во по ФЭО', unit: 'Ед.',
  amount: 'Запланировано',
}
function fieldLabel(f: string): string { return FIELD_LABELS[f] ?? f }
function fmtVal(v: any): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'boolean') return v ? 'Да' : 'Нет'
  if (typeof v === 'number') return v.toLocaleString('ru-RU', { maximumFractionDigits: 2 })
  return String(v)
}

function open() {
  reset()
  show.value = true
}
function close() {
  show.value = false
  reset()
}
function reset() {
  file.value = null
  preview.value = null
  loadError.value = ''
}

async function onFileChange(f: File[] | File | null) {
  const picked = Array.isArray(f) ? f[0] : f
  file.value = picked ?? null
  if (!picked || !props.subsidyId) return
  loading.value = true
  loadError.value = ''
  try {
    const fd = new FormData()
    fd.append('subsidy_id', String(props.subsidyId))
    fd.append('file', picked)
    preview.value = await apiFetch<RoundtripPreview>('/feo-categories/roundtrip/preview', {
      method: 'POST', body: fd,
    })
  } catch (e: any) {
    loadError.value = e?.payload?.message || e?.message || 'Не удалось разобрать файл'
    file.value = null
  } finally {
    loading.value = false
  }
}

async function doApply() {
  if (!file.value || !props.subsidyId) return
  applying.value = true
  try {
    const fd = new FormData()
    fd.append('subsidy_id', String(props.subsidyId))
    fd.append('file', file.value)
    const result = await apiFetch<{ created: number; updated: number; moved: number }>(
      '/feo-categories/roundtrip/apply', { method: 'POST', body: fd },
    )
    props.showSnack(
      `Загружено: создано ${result.created}, изменено ${result.updated}, перенесено ${result.moved}`,
      'success',
    )
    close()
    await props.onApplied()
  } catch (e: any) {
    const errs = e?.payload?.details?.errors as RoundtripError[] | undefined
    if (errs?.length) {
      preview.value = { changes: [], created: [], moved: [], missing: [], errors: errs, warnings: [] }
    }
    props.showSnack(e?.payload?.message || e?.message || 'Ошибка загрузки', 'error')
  } finally {
    applying.value = false
  }
}

defineExpose({ open })
</script>

<style scoped>
.roundtrip-row {
  padding: 2px 0;
  font-size: 13px;
  border-bottom: 1px solid var(--crm-border);
}
.roundtrip-row:last-child {
  border-bottom: none;
}
</style>
