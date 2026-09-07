<template>
  <!-- Excel Export Dialog -->
  <v-dialog v-model="state.show" max-width="680" scrollable :fullscreen="mobile">
    <v-card>
      <v-card-title class="d-flex align-center pa-4">
        <v-icon icon="mdi-microsoft-excel" color="success" class="mr-2" />
        Экспорт в Excel
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
import type { ExportColumn } from '@/composables/orders/ordersTypes'
import type { OrdersFiltersState } from '@/composables/orders/useOrdersFilters'

const props = defineProps<{
  filters: OrdersFiltersState
  showSnack: (text: string, color?: ToastType) => void
}>()

const { mobile } = useDisplay()

const DEFAULT_EXPORT_KEYS = [
  'purchase_number', 'registry_number', 'item_name', 'item_type', 'unit', 'quantity',
  'nmck', 'contract_price', 'economy', 'purchase_method',
  'contract_number', 'contract_date', 'contractor',
  'execution_term', 'country_origin',
  'acceptance_doc_name', 'acceptance_doc_number', 'acceptance_doc_date', 'acceptance_doc_amount',
  'payment_doc_number', 'payment_doc_date', 'payment_amount', 'payment_federal',
  'status',
]
const SAVED_PRESET_KEY = 'export_columns_preset'

const state = reactive({
  show: false,
  loading: false,
  exporting: false,
  allColumns: [] as ExportColumn[],
  selected: [...DEFAULT_EXPORT_KEYS],
})

const exportColumnGroups = computed(() => {
  const map: Record<string, ExportColumn[]> = {}
  for (const col of state.allColumns) {
    if (!map[col.group]) map[col.group] = []
    map[col.group]!.push(col)
  }
  return Object.entries(map).map(([name, cols]) => ({ name, cols }))
})

const hasSavedPreset = computed(() => !!localStorage.getItem(SAVED_PRESET_KEY))
const savedPresetCount = computed(() => {
  try { return JSON.parse(localStorage.getItem(SAVED_PRESET_KEY) || '[]').length } catch { return 0 }
})

async function open() {
  state.show = true
  if (state.allColumns.length === 0) {
    state.loading = true
    try {
      state.allColumns = await apiFetch<ExportColumn[]>('/purchases/export/columns')
    } finally {
      state.loading = false
    }
  }
}

function applyPreset(type: 'default' | 'all' | 'saved') {
  if (type === 'default') {
    state.selected = [...DEFAULT_EXPORT_KEYS]
  } else if (type === 'all') {
    state.selected = state.allColumns.map(c => c.key)
  } else {
    try {
      const saved = JSON.parse(localStorage.getItem(SAVED_PRESET_KEY) || '[]')
      if (saved.length) state.selected = saved
    } catch {}
  }
}

function savePreset() {
  localStorage.setItem(SAVED_PRESET_KEY, JSON.stringify(state.selected))
  props.showSnack('Пресет сохранён', 'success')
}

function toggleGroup(groupName: string, select: boolean) {
  const group = exportColumnGroups.value.find(g => g.name === groupName)
  if (!group) return
  const keys = group.cols.map(c => c.key)
  if (select) {
    state.selected = [...new Set([...state.selected, ...keys])]
  } else {
    state.selected = state.selected.filter(k => !keys.includes(k))
  }
}

async function doExport() {
  state.exporting = true
  try {
    const token = localStorage.getItem('auth_token')
    const params = new URLSearchParams()
    if (props.filters.subsidyId) params.set('subsidy_id', String(props.filters.subsidyId))
    if (props.filters.status) params.set('status', props.filters.status)
    params.set('columns', state.selected.join(','))
    const response = await fetch(`/api/purchases/export/excel?${params}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!response.ok) {
      let msg = `Ошибка экспорта (HTTP ${response.status})`
      try { const j = await response.json(); if (j?.message) msg = j.message } catch { /* not json */ }
      throw new Error(msg)
    }
    const missingRaw = response.headers.get('X-Missing-Columns')
    const missing = missingRaw ? decodeURIComponent(missingRaw) : null
    const blob = await response.blob()
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `Закупки_${new Date().toISOString().slice(0, 10)}.xlsx`
    document.body.appendChild(a)
    a.click()
    window.URL.revokeObjectURL(url)
    document.body.removeChild(a)
    state.show = false
    if (missing) {
      props.showSnack(`Предупреждение: мало данных в колонках: ${missing}`, 'warning')
    }
  } catch (e: any) {
    props.showSnack(e?.message || 'Ошибка экспорта', 'error')
  } finally {
    state.exporting = false
  }
}

defineExpose({ open })
</script>

<style scoped>
.export-col-check { min-width: 180px; max-width: 220px; }
.border-b { border-bottom: 1px solid var(--crm-border-strong); }
</style>
