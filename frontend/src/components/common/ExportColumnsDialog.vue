<template>
  <!-- Общий диалог выбора столбцов для экспорта в Excel (закупки + субсидии,
       ПРАВИЛО №5/переиспользование: один компонент, не дублировать). -->
  <v-dialog v-model="state.show" max-width="680" scrollable :fullscreen="mobile">
    <v-card>
      <v-card-title class="d-flex align-center pa-4">
        <v-icon icon="mdi-microsoft-excel" color="success" class="mr-2" />
        {{ title }}
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="state.show = false" />
      </v-card-title>

      <v-card-text class="pa-0">
        <!-- Presets row -->
        <div class="d-flex align-center gap-2 px-4 py-2 bg-grey-lighten-5 border-b">
          <span class="text-caption text-medium-emphasis mr-1">Пресет:</span>
          <v-btn size="x-small" variant="tonal" @click="applyPreset('default')">Стандартный</v-btn>
          <v-btn size="x-small" variant="tonal" @click="applyPreset('all')">Полный</v-btn>
          <v-btn size="x-small" variant="tonal" color="blue" @click="applyPreset('saved')" :disabled="!hasSavedPreset">
            Мой ({{ savedPresetCount }})
          </v-btn>
          <v-spacer />
          <v-btn size="x-small" variant="outlined" prepend-icon="mdi-content-save" @click="savePreset">
            Сохранить
          </v-btn>
        </div>

        <!-- Доп. опции над списком столбцов (напр. чекбокс «Лист Сводная» у субсидии) -->
        <div v-if="$slots['extra-options']" class="px-4 py-2 border-b">
          <slot name="extra-options" />
        </div>

        <!-- Columns by group -->
        <div v-if="state.loading" class="d-flex justify-center py-8">
          <v-progress-circular indeterminate color="primary" />
        </div>
        <div v-else class="px-4 py-2">
          <div v-for="group in exportColumnGroups" :key="group.name" class="mb-3">
            <div class="d-flex align-center mb-1">
              <span class="text-caption font-weight-bold text-medium-emphasis text-uppercase">{{ group.name }}</span>
              <v-btn
                size="x-small" variant="text" class="ml-1"
                @click="toggleGroup(group.name, true)">все</v-btn>
              <v-btn
                size="x-small" variant="text"
                @click="toggleGroup(group.name, false)">ни одного</v-btn>
            </div>
            <div class="d-flex flex-wrap gap-1">
              <v-checkbox
                v-for="col in group.cols" :key="col.key"
                v-model="state.selected"
                :value="col.key"
                :label="col.label"
                density="compact"
                hide-details
                :disabled="requiredKeys.includes(col.key)"
                class="export-col-check"
              />
            </div>
          </div>
        </div>
      </v-card-text>

      <v-card-actions class="pa-4 pt-2">
        <span class="text-caption text-medium-emphasis">Выбрано: {{ state.selected.length }}</span>
        <v-spacer />
        <v-btn variant="text" @click="state.show = false">Отмена</v-btn>
        <v-btn
          color="success" variant="flat"
          prepend-icon="mdi-download"
          :loading="state.exporting"
          :disabled="state.selected.length === 0"
          @click="doExport">
          Скачать Excel
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, reactive } from 'vue'
import { useDisplay } from 'vuetify'
import { apiFetch } from '@/api'
import type { ToastType } from '@/composables/useToast'

export interface ExportColumn { key: string; label: string; group: string; default?: boolean }

const props = defineProps<{
  title: string
  /** Путь для apiFetch (БЕЗ /api — как в OrdersExportDialog: '/purchases/export/columns') */
  columnsUrl: string
  /**
   * Набор столбцов по умолчанию. Если не передан — вычисляется из ответа
   * columnsUrl (поле `default` у каждого столбца, ПРАВИЛО №6: сервер — один
   * источник, какие столбцы "стандартные", а не второй список на фронте,
   * см. SubsidyExportDialog.vue). До первой загрузки каталога пуст.
   */
  defaultKeys?: string[]
  presetStorageKey: string
  /** Ключи, которые всегда отмечены и недоступны для снятия */
  requiredKeys?: string[]
  showSnack: (text: string, color?: ToastType) => void
  /** Выполняет само скачивание файла; бросает Error с текстом для showSnack при ошибке */
  download: (selectedKeys: string[]) => Promise<void>
}>()

const requiredKeys = computed(() => props.requiredKeys ?? [])
const hasStaticDefaultKeys = props.defaultKeys !== undefined

const { mobile } = useDisplay()

const state = reactive({
  show: false,
  loading: false,
  exporting: false,
  allColumns: [] as ExportColumn[],
  selected: hasStaticDefaultKeys
    ? [...new Set([...(props.requiredKeys ?? []), ...(props.defaultKeys ?? [])])]
    : [...(props.requiredKeys ?? [])],
})

/** Столбцы по умолчанию: статический prop, если он передан, иначе — из
 * каталога, пришедшего с сервера (поле `default`); пусто до загрузки. */
const effectiveDefaultKeys = computed<string[]>(() => {
  if (hasStaticDefaultKeys) return props.defaultKeys ?? []
  return state.allColumns.filter(c => c.default).map(c => c.key)
})

const exportColumnGroups = computed(() => {
  const map: Record<string, ExportColumn[]> = {}
  for (const col of state.allColumns) {
    if (!map[col.group]) map[col.group] = []
    map[col.group]!.push(col)
  }
  return Object.entries(map).map(([name, cols]) => ({ name, cols }))
})

const hasSavedPreset = computed(() => !!localStorage.getItem(props.presetStorageKey))
const savedPresetCount = computed(() => {
  try { return JSON.parse(localStorage.getItem(props.presetStorageKey) || '[]').length } catch { return 0 }
})

async function open() {
  state.show = true
  if (state.allColumns.length === 0) {
    state.loading = true
    try {
      state.allColumns = await apiFetch<ExportColumn[]>(props.columnsUrl)
      // defaultKeys не передан статически — набор по умолчанию известен
      // только теперь (после загрузки каталога с сервера); пресет "Мой" из
      // localStorage, если есть, не перетираем.
      if (!hasStaticDefaultKeys && !hasSavedPreset.value) {
        state.selected = ensureRequired(effectiveDefaultKeys.value)
      } else if (!hasStaticDefaultKeys && hasSavedPreset.value) {
        applyPreset('saved')
      }
    } finally {
      state.loading = false
    }
  }
}

function ensureRequired(keys: string[]): string[] {
  const missing = requiredKeys.value.filter(k => !keys.includes(k))
  return missing.length ? [...keys, ...missing] : keys
}

function applyPreset(type: 'default' | 'all' | 'saved') {
  if (type === 'default') {
    state.selected = ensureRequired([...effectiveDefaultKeys.value])
  } else if (type === 'all') {
    state.selected = ensureRequired(state.allColumns.map(c => c.key))
  } else {
    try {
      const saved = JSON.parse(localStorage.getItem(props.presetStorageKey) || '[]')
      if (saved.length) state.selected = ensureRequired(saved)
    } catch {}
  }
}

function savePreset() {
  localStorage.setItem(props.presetStorageKey, JSON.stringify(state.selected))
  props.showSnack('Пресет сохранён', 'success')
}

function toggleGroup(groupName: string, select: boolean) {
  const group = exportColumnGroups.value.find(g => g.name === groupName)
  if (!group) return
  const keys = group.cols.map(c => c.key)
  if (select) {
    state.selected = [...new Set([...state.selected, ...keys])]
  } else {
    state.selected = state.selected.filter(k => !keys.includes(k) || requiredKeys.value.includes(k))
  }
}

async function doExport() {
  state.exporting = true
  try {
    await props.download([...state.selected])
    state.show = false
  } catch (e: any) {
    props.showSnack(e?.message || 'Ошибка экспорта', 'error')
  } finally {
    state.exporting = false
  }
}

defineExpose({ open, selected: computed(() => state.selected) })
</script>

<style scoped>
.export-col-check { min-width: 180px; max-width: 220px; }
.border-b { border-bottom: 1px solid var(--crm-border-strong); }
</style>
