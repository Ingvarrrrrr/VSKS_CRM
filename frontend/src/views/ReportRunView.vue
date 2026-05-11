<template>
  <v-container fluid class="pa-4">
    <div class="d-flex align-center mb-4">
      <v-icon size="28" class="mr-2">mdi-play-circle-outline</v-icon>
      <h2 class="text-h5">{{ configName || 'Запуск отчёта' }}</h2>
      <v-chip class="ml-3" size="small" color="primary" v-if="configId">{{ configId }}</v-chip>
      <v-spacer />
      <v-btn variant="outlined" prepend-icon="mdi-pencil" :to="`/reports/lists/${configId}/edit`" class="mr-2" v-if="configId">Редактировать</v-btn>
      <v-btn color="success" prepend-icon="mdi-file-excel" @click="exportExcel" class="mr-2" :disabled="!rows.length">Excel</v-btn>
      <v-btn color="error" prepend-icon="mdi-file-pdf-box" @click="exportPdf" :disabled="!rows.length">PDF</v-btn>
    </div>

    <!-- Parameters form -->
    <v-card v-if="parameters.length" class="pa-4 mb-4">
      <div class="d-flex align-center mb-3">
        <v-icon size="20" class="mr-1">mdi-tune</v-icon>
        <strong>Параметры</strong>
      </div>
      <v-row dense>
        <v-col v-for="p in parameters" :key="p.key" cols="12" sm="6" md="4">
          <v-autocomplete
            v-if="p.type === 'subsidy_id_select'"
            v-model="paramValues[p.key]"
            :items="subsidies"
            item-title="name"
            item-value="id"
            :label="p.label || 'Субсидия'"
            density="compact"
            hide-details
            multiple
            chips
            closable-chips
          />
          <v-text-field
            v-else-if="p.type === 'date'"
            v-model="paramValues[p.key]"
            :label="p.label || p.key"
            type="date"
            density="compact"
            hide-details
          />
          <v-text-field
            v-else
            v-model="paramValues[p.key]"
            :label="p.label || p.key"
            density="compact"
            hide-details
          />
        </v-col>
      </v-row>
      <div class="mt-3">
        <v-btn color="primary" prepend-icon="mdi-play" @click="runReport" :loading="loading">Сформировать</v-btn>
      </div>
    </v-card>

    <!-- Auto-run if no params -->
    <v-progress-linear v-if="loading" indeterminate class="mb-2" />

    <!-- Results -->
    <v-card class="pa-2">
      <div class="d-flex align-center mb-2">
        <v-icon size="20" class="mr-1">mdi-table</v-icon>
        <strong>Результат</strong>
        <v-spacer />
        <v-chip size="x-small">{{ rowsCount }} строк</v-chip>
      </div>
      <div v-if="!rows.length && !loading" class="text-center text-grey pa-6">
        {{ parameters.length ? 'Нажмите «Сформировать»' : 'Нет данных' }}
      </div>
      <div v-else style="overflow-x: auto">
        <v-table density="compact" hover>
          <thead>
            <tr>
              <th v-for="col in columns" :key="col.key || col">{{ col.header || col }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, idx) in rows" :key="idx" :class="rowClass(row)">
              <td v-for="col in columns" :key="col.key || col" :class="cellClass(col)">{{ formatCell(row, col) }}</td>
            </tr>
          </tbody>
        </v-table>
      </div>
    </v-card>
  </v-container>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { apiFetch } from '@/api'
import { useToast } from '@/composables/useToast'

const route = useRoute()
const toast = useToast()

const configId = ref<number | null>(null)
const configName = ref('')
const parameters = ref<any[]>([])
const paramValues = ref<Record<string, any>>({})
const columns = ref<any[]>([])
const rows = ref<any[]>([])
const rowsCount = ref(0)
const loading = ref(false)
const subsidies = ref<any[]>([])

async function runReport() {
  loading.value = true
  try {
    const result = await apiFetch<any>(`/api/report-configs/${configId.value}/run`, {
      method: 'POST',
      body: JSON.stringify({ params: paramValues.value }),
    })
    rows.value = result.rows || []
    rowsCount.value = result.rows_count || result.rows?.length || 0
    if (result.columns) columns.value = result.columns
  } catch (e: any) {
    toast.error('Ошибка запуска: ' + (e?.message || String(e)))
  } finally {
    loading.value = false
  }
}

function rowClass(row: any) {
  const t = row._row_type
  if (t === 'group_header') return 'bg-grey-lighten-3 font-weight-bold'
  if (t === 'subtotal') return 'bg-grey-lighten-4 font-weight-medium'
  if (t === 'grand_total') return 'bg-blue-lighten-4 font-weight-bold'
  return ''
}

function cellClass(col: any) {
  if (col.field_type === 'currency' || col.field_type === 'number') return 'text-right'
  return ''
}

function formatCell(row: any, col: any) {
  const key = col.key || col
  const v = row[`${key}_fmt`] !== undefined ? row[`${key}_fmt`] : row[key]
  if (v === null || v === undefined || v === '') return ''
  return String(v)
}

function exportExcel() {
  toast.info('Excel-экспорт будет в Plan 25-08')
}

function exportPdf() {
  toast.info('PDF-экспорт будет в Plan 25-09')
}

onMounted(async () => {
  const id = Number(route.params.id)
  if (!id) return
  configId.value = id
  try {
    const [cfg, subs] = await Promise.all([
      apiFetch<any>(`/api/report-configs/${id}`),
      apiFetch<any>('/api/subsidies/'),
    ])
    configName.value = cfg.name
    parameters.value = cfg.parameters_json || []
    subsidies.value = Array.isArray(subs) ? subs : subs.items || []
    // Build columns from config_json for header display
    const c = cfg.config_json || {}
    const fieldCols = (c.columns || []).map((k: string) => ({ key: k, header: k, field_type: '' }))
    const compCols = (c.computed_columns || [])
      .filter((cc: any) => cc.type !== 'format')
      .map((cc: any) => ({ key: cc.key, header: cc.key, field_type: '' }))
    columns.value = [...fieldCols, ...compCols]
    // Auto-run if no parameters
    if (!parameters.value.length) {
      await runReport()
    }
  } catch (e: any) {
    toast.error('Ошибка загрузки: ' + (e?.message || String(e)))
  }
})
</script>
