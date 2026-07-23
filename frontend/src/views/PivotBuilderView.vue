<template>
  <v-container fluid class="pa-4">
    <!-- Header -->
    <div class="d-flex align-center mb-4">
      <v-icon size="32" class="mr-2">mdi-pivot</v-icon>
      <h2 class="text-h5">{{ configName || 'Новая сводная' }}</h2>
      <v-chip v-if="configId" size="small" color="primary" class="ml-3">{{ configId }}</v-chip>
      <v-spacer />
      <v-btn color="primary" prepend-icon="mdi-content-save" @click="saveDialog = true" class="mr-2">Сохранить</v-btn>
      <v-btn color="success" prepend-icon="mdi-file-excel" :disabled="!result.rows?.length" class="mr-2" @click="exportExcel">Excel</v-btn>
      <v-btn color="error" prepend-icon="mdi-file-pdf-box" :disabled="!result.rows?.length" @click="exportPdf">PDF</v-btn>
    </div>

    <v-row no-gutters>
      <!-- LEFT: каталог -->
      <v-col cols="3" class="pr-2">
        <v-card class="pa-2" style="height: calc(100vh - 200px); overflow-y: auto">
          <v-text-field v-model="search" prepend-inner-icon="mdi-magnify" density="compact" label="Поиск..." hide-details class="mb-2" />
          <v-tabs v-model="catalogTab" density="compact" grow>
            <v-tab value="dims">Измерения</v-tab>
            <v-tab value="meas">Меры</v-tab>
          </v-tabs>
          <v-window v-model="catalogTab" class="mt-2">
            <v-window-item value="dims">
              <v-expansion-panels variant="accordion" multiple v-model="openGroups">
                <v-expansion-panel v-for="g in groups" :key="g" :title="g">
                  <v-list density="compact">
                    <v-list-item
                      v-for="f in dimensionsByGroup[g] || []"
                      :key="f.key"
                      :title="f.label"
                      :subtitle="f.key"
                      style="cursor: pointer"
                    >
                      <template #append>
                        <v-btn size="x-small" variant="text" icon="mdi-arrow-up" title="В строки" @click.stop="pivot.addRow(f)" />
                        <v-btn size="x-small" variant="text" icon="mdi-arrow-right" title="В колонки" @click.stop="pivot.addCol(f)" />
                      </template>
                    </v-list-item>
                  </v-list>
                </v-expansion-panel>
              </v-expansion-panels>
            </v-window-item>
            <v-window-item value="meas">
              <v-list density="compact">
                <v-list-item
                  v-for="f in measures"
                  :key="f.key"
                  :title="f.label"
                  :subtitle="f.group"
                  @click="pivot.addMeasure(f)"
                  style="cursor: pointer"
                >
                  <template #prepend><v-icon size="16">mdi-numeric</v-icon></template>
                </v-list-item>
              </v-list>
            </v-window-item>
          </v-window>
        </v-card>
      </v-col>

      <!-- CENTER: drop-зоны -->
      <v-col cols="5" class="px-2">
        <v-card class="pa-3 mb-2">
          <strong>Строки</strong>
          <div v-if="!pivot.state.rows.length" class="text-grey text-caption">Перетащите измерения слева</div>
          <v-chip
            v-for="(r, idx) in pivot.state.rows"
            :key="r.key"
            class="ma-1"
            closable
            @click:close="pivot.removeRow(idx)"
          >{{ r.label }}</v-chip>
        </v-card>
        <v-card class="pa-3 mb-2">
          <strong>Колонки</strong>
          <div v-if="!pivot.state.cols.length" class="text-grey text-caption">Опционально</div>
          <v-chip
            v-for="(c, idx) in pivot.state.cols"
            :key="c.key"
            class="ma-1"
            closable
            @click:close="pivot.removeCol(idx)"
          >{{ c.label }}</v-chip>
        </v-card>
        <v-card class="pa-3 mb-2">
          <strong>Значения (меры)</strong>
          <div v-if="!pivot.state.measures.length" class="text-grey text-caption">Перетащите меру слева</div>
          <v-list density="compact">
            <v-list-item v-for="(m, idx) in pivot.state.measures" :key="m.key">
              <v-list-item-title>{{ m.label }}</v-list-item-title>
              <template #append>
                <v-select
                  v-model="m.agg"
                  :items="aggOptions"
                  density="compact"
                  hide-details
                  style="max-width: 130px"
                  @update:model-value="reload"
                />
                <v-btn size="x-small" variant="text" icon="mdi-delete" color="error" @click="pivot.removeMeasure(idx)" />
              </template>
            </v-list-item>
          </v-list>
        </v-card>
        <v-card class="pa-3 mb-2">
          <strong>Фильтры</strong>
          <v-row dense>
            <v-col cols="6">
              <v-autocomplete
                v-model="filterSubsidy"
                :items="subsidies"
                item-title="name"
                item-value="id"
                label="Субсидия"
                density="compact"
                hide-details
                multiple
                chips
                closable-chips
                @update:model-value="(v) => pivot.setFilter('subsidy_id', v)"
              />
            </v-col>
            <v-col cols="6">
              <v-select
                v-model="filterStatus"
                :items="statusOptions"
                label="Статус"
                density="compact"
                hide-details
                multiple
                chips
                closable-chips
                @update:model-value="(v) => pivot.setFilter('status', v)"
              />
            </v-col>
            <v-col cols="6">
              <v-text-field
                v-model="filterDateFrom"
                label="Дата с"
                type="date"
                density="compact"
                hide-details
                @update:model-value="updateDateFilter"
              />
            </v-col>
            <v-col cols="6">
              <v-text-field
                v-model="filterDateTo"
                label="Дата по"
                type="date"
                density="compact"
                hide-details
                @update:model-value="updateDateFilter"
              />
            </v-col>
          </v-row>
        </v-card>
        <v-card class="pa-3 mb-2">
          <div class="d-flex align-center">
            <strong>Расчётные колонки</strong>
            <v-spacer />
            <v-btn size="x-small" prepend-icon="mdi-plus" @click="addCalcColumnDialog = true">Добавить</v-btn>
          </div>
          <v-list density="compact">
            <v-list-item v-for="(cc, idx) in pivot.state.calc_columns" :key="idx">
              <v-list-item-title>{{ calcLabel(cc) }}</v-list-item-title>
              <template #append>
                <v-btn size="x-small" variant="text" icon="mdi-delete" color="error" @click="pivot.removeCalcColumn(idx); reload()" />
              </template>
            </v-list-item>
          </v-list>
        </v-card>
      </v-col>

      <!-- RIGHT: превью pivot -->
      <v-col cols="4" class="pl-2">
        <v-card class="pa-2" style="height: calc(100vh - 200px); overflow: auto">
          <div class="d-flex align-center mb-2">
            <v-icon size="20" class="mr-1">mdi-eye</v-icon>
            <strong>Превью</strong>
            <v-spacer />
            <v-chip size="x-small">{{ result.rows_count || 0 }} стр.</v-chip>
          </div>
          <v-progress-linear v-if="loading" indeterminate />
          <v-table density="compact" v-if="result.rows?.length" hover>
            <thead>
              <tr>
                <th v-for="d in pivot.state.rows" :key="d.key">{{ d.label }}</th>
                <th v-for="d in pivot.state.cols" :key="d.key">{{ d.label }}</th>
                <th v-for="m in pivot.state.measures" :key="m.key" class="text-right">{{ m.label }}</th>
                <th v-for="cc in pivot.state.calc_columns" :key="JSON.stringify(cc)" class="text-right">{{ calcLabel(cc) }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, idx) in result.rows" :key="idx" style="cursor: pointer" @click="drillTo(row)">
                <td v-for="d in pivot.state.rows" :key="d.key">{{ row[d.key] ?? '' }}</td>
                <td v-for="d in pivot.state.cols" :key="d.key">{{ row[d.key] ?? '' }}</td>
                <td v-for="m in pivot.state.measures" :key="m.key" class="text-right">{{ fmtNumber(row[m.key]) }}</td>
                <td v-for="cc in pivot.state.calc_columns" :key="JSON.stringify(cc)" class="text-right">{{ fmtCalc(row, cc) }}</td>
              </tr>
              <tr v-if="result.totals" class="bg-blue-lighten-4 font-weight-bold">
                <td :colspan="pivot.state.rows.length + pivot.state.cols.length">Итого</td>
                <td v-for="m in pivot.state.measures" :key="m.key" class="text-right">{{ fmtNumber(result.totals[m.key]) }}</td>
                <td v-for="cc in pivot.state.calc_columns" :key="JSON.stringify(cc)"></td>
              </tr>
            </tbody>
          </v-table>
          <div v-else class="text-center text-grey pa-4">
            Добавьте строки, меры и фильтры
          </div>
        </v-card>
      </v-col>
    </v-row>

    <!-- Save dialog -->
    <v-dialog v-model="saveDialog" max-width="500" :fullscreen="mobile">
      <v-card>
        <v-card-title>Сохранить сводную</v-card-title>
        <v-card-text>
          <v-text-field v-model="configName" label="Название" autofocus />
          <v-textarea v-model="configDescription" label="Описание" rows="2" />
          <v-checkbox v-model="isShared" label="Доступно всем в организации" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="saveDialog = false">Отмена</v-btn>
          <v-btn color="primary" @click="saveConfig">Сохранить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Add calc column dialog -->
    <v-dialog v-model="addCalcColumnDialog" max-width="500" :fullscreen="mobile">
      <v-card>
        <v-card-title>Добавить расчётную колонку</v-card-title>
        <v-card-text>
          <v-select v-model="newCalc.type" :items="calcTypeOptions" label="Тип" />
          <v-select
            v-if="newCalc.type === 'share' || newCalc.type === 'cumulative'"
            v-model="newCalc.measure"
            :items="pivot.state.measures.map((m) => ({ value: m.key, title: m.label }))"
            label="Мера"
          />
          <v-row v-if="newCalc.type === 'delta'">
            <v-col cols="6">
              <v-select v-model="newCalc.actual" :items="pivot.state.measures.map((m) => ({ value: m.key, title: m.label }))" label="Факт" />
            </v-col>
            <v-col cols="6">
              <v-select v-model="newCalc.plan" :items="pivot.state.measures.map((m) => ({ value: m.key, title: m.label }))" label="План" />
            </v-col>
          </v-row>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="addCalcColumnDialog = false">Отмена</v-btn>
          <v-btn color="primary" @click="saveCalcColumn">Добавить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Drill dialog -->
    <v-dialog v-model="drillDialog" max-width="900" :fullscreen="mobile">
      <v-card>
        <v-card-title>Drill-down: {{ drillContext }}</v-card-title>
        <v-card-text>
          <v-progress-linear v-if="drillLoading" indeterminate />
          <v-table density="compact" v-else>
            <thead>
              <tr>
                <th>№</th>
                <th>Наименование</th>
                <th>Контрагент</th>
                <th>Сумма</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in drillRows" :key="r._id" style="cursor: pointer" @click="navigateToOrder(r._id)">
                <td>{{ r.purchase_number }}</td>
                <td>{{ r.item_name }}</td>
                <td>{{ r.contractor_name }}</td>
                <td class="text-right">{{ fmtNumber(r.planned_total_price) }}</td>
              </tr>
            </tbody>
          </v-table>
        </v-card-text>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useDisplay } from 'vuetify'
import { apiFetch } from '@/api'
import { useToast } from '@/composables/useToast'
import { usePivotConfig } from '@/composables/usePivotConfig'

const route = useRoute()
const router = useRouter()
const { mobile } = useDisplay()
const toast = useToast()
const pivot = usePivotConfig()

const fields = ref<any[]>([])
const groups = ref<string[]>([])
const openGroups = ref<string[]>([])
const search = ref('')
const catalogTab = ref('dims')
const subsidies = ref<any[]>([])

const result = ref<any>({ rows: [], totals: {}, rows_count: 0 })
const loading = ref(false)

const configId = ref<number | null>(null)
const configName = ref('')
const configDescription = ref('')
const isShared = ref(true)
const saveDialog = ref(false)
const addCalcColumnDialog = ref(false)
const newCalc = ref<any>({ type: 'share' })

const drillDialog = ref(false)
const drillLoading = ref(false)
const drillRows = ref<any[]>([])
const drillContext = ref('')

const filterSubsidy = ref<number[]>([])
const filterStatus = ref<string[]>([])
const filterDateFrom = ref('')
const filterDateTo = ref('')

const statusOptions = [
  { value: 'wishes', title: 'Желания' },
  { value: 'planned', title: 'Запланировано' },
  { value: 'work_in_progress', title: 'Ведётся работа' },
  { value: 'contracted', title: 'Договор' },
  { value: 'ordered', title: 'Заказано' },
  { value: 'delivered', title: 'Поставлено' },
  { value: 'paid', title: 'Оплачено' },
]
const aggOptions = [
  { value: 'sum', title: 'Сумма' },
  { value: 'avg', title: 'Среднее' },
  { value: 'count', title: 'Количество' },
  { value: 'count_distinct', title: 'Уникальных' },
  { value: 'min', title: 'Минимум' },
  { value: 'max', title: 'Максимум' },
]
const calcTypeOptions = [
  { value: 'share', title: '% от итога' },
  { value: 'cumulative', title: 'Нарастающий итог' },
  { value: 'delta', title: 'Δ план-факт' },
]

const dimensionsByGroup = computed<Record<string, any[]>>(() => {
  const grouped: Record<string, any[]> = {}
  const q = search.value.toLowerCase().trim()
  for (const f of fields.value) {
    if (!f.is_dimension) continue
    if (q && !f.label.toLowerCase().includes(q) && !f.key.toLowerCase().includes(q)) continue
    if (!grouped[f.group]) grouped[f.group] = []
    grouped[f.group].push(f)
  }
  return grouped
})
const measures = computed(() => fields.value.filter((f) => f.is_measure))

function fmtNumber(v: any) {
  if (v === null || v === undefined || v === '') return ''
  const n = Number(v)
  if (isNaN(n)) return String(v)
  return n.toLocaleString('ru-RU', { maximumFractionDigits: 2 })
}
function fmtCalc(row: any, cc: any) {
  if (cc.type === 'share') {
    const v = row[`share_${cc.measure}`]
    if (v === undefined) return ''
    return (Number(v) * 100).toFixed(1) + '%'
  }
  if (cc.type === 'cumulative') return fmtNumber(row[`cumulative_${cc.measure}`])
  if (cc.type === 'delta') return fmtNumber(row[`delta_${cc.actual}_vs_${cc.plan}`])
  return ''
}
function calcLabel(cc: any) {
  if (cc.type === 'share') return `% от итога: ${cc.measure}`
  if (cc.type === 'cumulative') return `Нараст.: ${cc.measure}`
  if (cc.type === 'delta') return `Δ: ${cc.actual} vs ${cc.plan}`
  return ''
}
function updateDateFilter() {
  if (filterDateFrom.value || filterDateTo.value) {
    pivot.setFilter('contract_date', { from: filterDateFrom.value || undefined, to: filterDateTo.value || undefined })
  } else pivot.setFilter('contract_date', null)
}
function saveCalcColumn() {
  pivot.addCalcColumn({ ...newCalc.value })
  addCalcColumnDialog.value = false
  newCalc.value = { type: 'share' }
  reload()
}
async function reload() {
  if (!pivot.state.rows.length || !pivot.state.measures.length) {
    result.value = { rows: [], totals: {}, rows_count: 0 }
    return
  }
  loading.value = true
  try {
    result.value = await apiFetch<any>('/analytics/query', {
      method: 'POST',
      body: JSON.stringify(pivot.buildQuery()),
    })
  } catch (e: any) {
    toast.error('Ошибка: ' + (e?.message || e))
  } finally {
    loading.value = false
  }
}
let debounceTimer: ReturnType<typeof setTimeout> | null = null
function debouncedReload() {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(reload, 350)
}
async function drillTo(row: any) {
  const dimVals: any = {}
  for (const d of [...pivot.state.rows, ...pivot.state.cols]) {
    if (row[d.key] !== undefined) dimVals[d.key] = row[d.key]
  }
  drillContext.value = Object.entries(dimVals).map(([k, v]) => `${k}=${v}`).join(', ')
  drillDialog.value = true
  drillLoading.value = true
  try {
    const r = await apiFetch<any>('/analytics/drill', {
      method: 'POST',
      body: JSON.stringify({ config: pivot.buildQuery(), dimension_values: dimVals }),
    })
    drillRows.value = r.rows || []
  } catch (e: any) {
    toast.error('Drill: ' + (e?.message || e))
  } finally {
    drillLoading.value = false
  }
}
function navigateToOrder(id: number) {
  if (id) router.push(`/orders/${id}/edit`)
}
async function saveConfig() {
  if (!configName.value.trim()) {
    toast.warning('Введите название')
    return
  }
  const body = {
    kind: 'pivot',
    name: configName.value,
    description: configDescription.value || null,
    config_json: pivot.buildQuery(),
    parameters_json: [],
    is_shared: isShared.value,
  }
  try {
    if (configId.value) {
      await apiFetch(`/report-configs/${configId.value}`, {
        method: 'PUT',
        body: JSON.stringify({
          name: configName.value,
          description: body.description,
          config_json: body.config_json,
          is_shared: body.is_shared,
        }),
      })
      toast.success('Обновлено')
    } else {
      const created = await apiFetch<any>('/report-configs/', {
        method: 'POST',
        body: JSON.stringify(body),
      })
      configId.value = created.id
      router.replace(`/reports/pivots/${created.id}/edit`)
      toast.success('Сохранено')
    }
    saveDialog.value = false
  } catch (e: any) {
    toast.error('Ошибка: ' + (e?.message || e))
  }
}
async function exportExcel() {
  try {
    const token = localStorage.getItem('auth_token')
    const resp = await fetch('/api/analytics/export.xlsx', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ config: pivot.buildQuery(), name: configName.value || 'Сводная' }),
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const blob = await resp.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${configName.value || 'Сводная'}_${new Date().toISOString().slice(0, 10)}.xlsx`
    a.click()
    URL.revokeObjectURL(url)
    toast.success('Excel выгружен')
  } catch (e: any) {
    toast.error('Excel: ' + (e?.message || e))
  }
}
async function exportPdf() {
  try {
    const token = localStorage.getItem('auth_token')
    const resp = await fetch('/api/analytics/export.pdf', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ config: pivot.buildQuery(), name: configName.value || 'Сводная' }),
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const blob = await resp.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${configName.value || 'Сводная'}_${new Date().toISOString().slice(0, 10)}.pdf`
    a.click()
    URL.revokeObjectURL(url)
    toast.success('PDF выгружен')
  } catch (e: any) {
    toast.error('PDF: ' + (e?.message || e))
  }
}

watch(() => pivot.state, debouncedReload, { deep: true })

onMounted(async () => {
  try {
    const f = await apiFetch<any>('/analytics/fields')
    fields.value = f.fields
    groups.value = f.groups
    openGroups.value = [...f.groups]
    const subs = await apiFetch<any>('/subsidies/')
    subsidies.value = Array.isArray(subs) ? subs : subs.items || []
    const idParam = route.params.id
    if (idParam) {
      const cfg = await apiFetch<any>(`/report-configs/${idParam}`)
      configId.value = cfg.id
      configName.value = cfg.name
      configDescription.value = cfg.description || ''
      isShared.value = cfg.is_shared
      pivot.loadFromConfig(cfg.config_json || {})
      filterSubsidy.value = cfg.config_json?.filters?.subsidy_id || []
      filterStatus.value = cfg.config_json?.filters?.status || []
      reload()
    }
  } catch (e: any) {
    toast.error('Load: ' + (e?.message || e))
  }
})
</script>
