<template>
  <v-container fluid class="pa-4">
    <!-- Header bar -->
    <div class="d-flex align-center mb-4">
      <v-icon size="32" class="mr-2">mdi-table-large</v-icon>
      <h2 class="text-h5">{{ configName || 'Новый реестр' }}</h2>
      <v-chip class="ml-3" size="small" color="primary" v-if="configId">{{ configId }}</v-chip>
      <v-spacer />
      <v-btn color="primary" prepend-icon="mdi-content-save" @click="saveDialog = true" class="mr-2">Сохранить</v-btn>
      <v-btn color="success" prepend-icon="mdi-file-excel" @click="exportExcel" class="mr-2" :disabled="!rows.length">Excel</v-btn>
      <v-btn color="error" prepend-icon="mdi-file-pdf-box" @click="exportPdf" :disabled="!rows.length">PDF</v-btn>
    </div>

    <v-row no-gutters>
      <!-- LEFT: каталог полей -->
      <v-col cols="3" class="pr-2">
        <v-card class="pa-3" style="height: calc(100vh - 200px); overflow-y: auto">
          <v-text-field v-model="fieldSearch" prepend-inner-icon="mdi-magnify" density="compact" label="Поиск поля..." hide-details class="mb-2" />
          <v-expansion-panels variant="accordion" multiple v-model="openGroups">
            <v-expansion-panel v-for="g in groups" :key="g" :title="g">
              <template #default>
                <v-list density="compact">
                  <v-list-item
                    v-for="f in fieldsByGroup[g]"
                    :key="f.key"
                    :title="f.label"
                    :subtitle="f.key"
                    @click="addColumn(f)"
                    style="cursor: pointer"
                  >
                    <template #prepend>
                      <v-icon size="16">{{ typeIcon(f.type) }}</v-icon>
                    </template>
                  </v-list-item>
                </v-list>
              </template>
            </v-expansion-panel>
          </v-expansion-panels>
          <v-divider class="my-2" />
          <v-btn block size="small" prepend-icon="mdi-text-recognition" @click="openCompositeDialog">Добавить шаблон-колонку</v-btn>
          <v-btn block size="small" prepend-icon="mdi-flag-outline" @click="openConstantDialog" class="mt-1">Добавить константу</v-btn>
        </v-card>
      </v-col>

      <!-- CENTER: видимые колонки + фильтры -->
      <v-col cols="6" class="px-2">
        <!-- Filters -->
        <v-card class="pa-3 mb-2">
          <div class="d-flex align-center mb-2">
            <v-icon size="20" class="mr-1">mdi-filter</v-icon>
            <strong>Фильтры</strong>
            <v-spacer />
            <v-btn size="x-small" variant="text" @click="resetFilters">Сбросить</v-btn>
          </div>
          <v-row dense>
            <v-col cols="6">
              <v-autocomplete
                v-model="filters.subsidy_id"
                :items="subsidies"
                item-title="name"
                item-value="id"
                label="Субсидия"
                density="compact"
                hide-details
                multiple
                chips
                closable-chips
              />
            </v-col>
            <v-col cols="6">
              <v-select
                v-model="filters.status"
                :items="statusOptions"
                label="Статус"
                density="compact"
                hide-details
                multiple
                chips
                closable-chips
              />
            </v-col>
            <v-col cols="6">
              <v-autocomplete
                v-model="filters.contractor_id"
                :items="contractors"
                item-title="name"
                item-value="id"
                label="Контрагент"
                density="compact"
                hide-details
                multiple
              />
            </v-col>
            <v-col cols="6">
              <v-select
                v-model="filters.item_type"
                :items="['Товары', 'Услуги']"
                label="Тип"
                density="compact"
                hide-details
                multiple
              />
            </v-col>
          </v-row>
        </v-card>

        <!-- Columns list -->
        <v-card class="pa-3">
          <div class="d-flex align-center mb-2">
            <v-icon size="20" class="mr-1">mdi-format-columns</v-icon>
            <strong>Колонки ({{ columns.length }})</strong>
            <v-spacer />
            <v-select
              v-model="groupBy"
              :items="groupableColumns"
              item-title="header"
              item-value="key"
              label="Группировать по"
              density="compact"
              hide-details
              multiple
              chips
              closable-chips
              style="max-width: 350px"
            />
          </div>
          <div v-if="!columns.length" class="text-center text-grey pa-4">Перетащите поля слева</div>
          <div v-else>
            <v-list density="compact">
              <v-list-item v-for="(col, idx) in columns" :key="idx" class="rounded mb-1 elevation-1">
                <template #prepend>
                  <v-icon size="18" class="cursor-grab">mdi-drag</v-icon>
                </template>
                <v-list-item-title>
                  <v-text-field v-model="col.header" density="compact" hide-details variant="plain" />
                </v-list-item-title>
                <v-list-item-subtitle class="text-caption">
                  <v-chip size="x-small" class="mr-1">{{ col.type }}</v-chip>
                  <span v-if="col.type === 'composite'">{{ col.template }}</span>
                  <span v-else-if="col.type === 'constant'">{{ col.value }}</span>
                  <span v-else>{{ col.key }}</span>
                  <span v-if="col.unit && col.unit !== 'none'" class="ml-2 text-primary">{{ unitLabel(col.unit) }}</span>
                </v-list-item-subtitle>
                <template #append>
                  <v-btn size="x-small" variant="text" icon="mdi-cog" @click="editColumn(idx)" />
                  <v-btn size="x-small" variant="text" icon="mdi-arrow-up" @click="moveColumn(idx, -1)" :disabled="idx === 0" />
                  <v-btn size="x-small" variant="text" icon="mdi-arrow-down" @click="moveColumn(idx, 1)" :disabled="idx === columns.length - 1" />
                  <v-btn size="x-small" variant="text" icon="mdi-delete" color="error" @click="removeColumn(idx)" />
                </template>
              </v-list-item>
            </v-list>
          </div>
        </v-card>
      </v-col>

      <!-- RIGHT: превью -->
      <v-col cols="3" class="pl-2">
        <v-card class="pa-2" style="height: calc(100vh - 200px); overflow: auto">
          <div class="d-flex align-center mb-2">
            <v-icon size="20" class="mr-1">mdi-eye</v-icon>
            <strong>Превью</strong>
            <v-spacer />
            <v-chip size="x-small">{{ rowsCount }} стр.</v-chip>
          </div>
          <v-progress-linear v-if="loading" indeterminate />
          <v-table density="compact" v-if="rows.length" hover>
            <thead>
              <tr>
                <th v-for="col in columns" :key="col.key">{{ col.header }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, idx) in rows.slice(0, 100)" :key="idx" :class="rowClass(row)">
                <td v-for="col in columns" :key="col.key" :class="cellClass(row, col)">{{ formatCell(row, col) }}</td>
              </tr>
            </tbody>
          </v-table>
          <div v-else class="text-center text-grey pa-4">Нет данных. Добавьте колонки и фильтры.</div>
        </v-card>
      </v-col>
    </v-row>

    <!-- Save dialog -->
    <v-dialog v-model="saveDialog" max-width="500">
      <v-card>
        <v-card-title>Сохранить шаблон реестра</v-card-title>
        <v-card-text>
          <v-text-field v-model="configName" label="Название" autofocus />
          <v-textarea v-model="configDescription" label="Описание (опц.)" rows="2" />
          <v-checkbox v-model="isShared" label="Доступно всем в организации" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="saveDialog = false">Отмена</v-btn>
          <v-btn color="primary" @click="saveConfig">Сохранить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Composite column dialog -->
    <v-dialog v-model="compositeDialog" max-width="600">
      <v-card>
        <v-card-title>{{ editingIdx >= 0 ? 'Редактировать' : 'Добавить' }} шаблон-колонку</v-card-title>
        <v-card-text>
          <v-text-field v-model="compositeForm.header" label="Заголовок колонки" autofocus />
          <v-text-field
            v-model="compositeForm.template"
            label='Шаблон, например: "{contract_number} от {contract_date|dmy}"'
            placeholder='{contract_number} от {contract_date|dmy}'
          />
          <v-text-field v-model="compositeForm.fallback" label="Текст при пустых полях" placeholder="Платёж не проходил" />
          <v-alert type="info" variant="tonal" density="compact" class="mt-2">
            Используйте {field_key} для подстановки. Доступные ключи: contract_number, contract_date, payment_doc_number, payment_doc_date, item_name, contractor_name, и др. (см. каталог полей слева). Форматы: |dmy, |month, |rub, |thousands, |millions.
          </v-alert>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="compositeDialog = false">Отмена</v-btn>
          <v-btn color="primary" @click="saveCompositeColumn">Сохранить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Constant column dialog -->
    <v-dialog v-model="constantDialog" max-width="500">
      <v-card>
        <v-card-title>Константная колонка</v-card-title>
        <v-card-text>
          <v-text-field v-model="constantForm.header" label="Заголовок" autofocus />
          <v-text-field v-model="constantForm.value" label="Значение" placeholder="Россия" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="constantDialog = false">Отмена</v-btn>
          <v-btn color="primary" @click="saveConstantColumn">Сохранить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Edit column dialog (для field-колонок) -->
    <v-dialog v-model="editFieldDialog" max-width="500">
      <v-card>
        <v-card-title>Настройки колонки</v-card-title>
        <v-card-text v-if="editFieldData">
          <v-text-field v-model="editFieldData.header" label="Заголовок" autofocus />
          <v-select
            v-model="editFieldData.unit"
            :items="[
              { value: 'none', title: 'Как есть' },
              { value: 'rub', title: 'Рубли (₽)' },
              { value: 'thousands', title: 'Тысячи рублей (тыс.₽)' },
              { value: 'millions', title: 'Миллионы (млн.₽)' },
              { value: 'dmy', title: 'Дата ДД.ММ.ГГГГ' },
            ]"
            label="Формат значений"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="editFieldDialog = false">Закрыть</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiFetch } from '@/api'
import { useToast } from '@/composables/useToast'

const route = useRoute()
const router = useRouter()
const toast = useToast()

// State
const fields = ref<any[]>([])
const groups = ref<string[]>([])
const openGroups = ref<string[]>([])
const fieldSearch = ref('')

const columns = ref<any[]>([])
const filters = ref<any>({ subsidy_id: [], status: [], contractor_id: [], item_type: [] })
const groupBy = ref<string[]>([])

const rows = ref<any[]>([])
const rowsCount = ref(0)
const loading = ref(false)

const subsidies = ref<any[]>([])
const contractors = ref<any[]>([])

const configId = ref<number | null>(null)
const configName = ref('')
const configDescription = ref('')
const isShared = ref(true)

const saveDialog = ref(false)
const compositeDialog = ref(false)
const constantDialog = ref(false)
const editFieldDialog = ref(false)
const editingIdx = ref(-1)
const editFieldData = ref<any>(null)
const compositeForm = ref({ key: '', header: '', template: '', fallback: '' })
const constantForm = ref({ key: '', header: '', value: '' })

const statusOptions = [
  { value: 'wishes', title: 'Желания' },
  { value: 'planned', title: 'Запланировано' },
  { value: 'confirmed', title: 'Подтверждена' },
  { value: 'contracted', title: 'Договор' },
  { value: 'ordered', title: 'Заказано' },
  { value: 'delivered', title: 'Поставлено' },
  { value: 'paid', title: 'Оплачено' },
  { value: 'cancelled', title: 'Отменена' },
]

// Computed
const fieldsByGroup = computed<Record<string, any[]>>(() => {
  const grouped: Record<string, any[]> = {}
  const q = fieldSearch.value.toLowerCase().trim()
  for (const f of fields.value) {
    if (q && !f.label.toLowerCase().includes(q) && !f.key.toLowerCase().includes(q)) continue
    if (!grouped[f.group]) grouped[f.group] = []
    grouped[f.group].push(f)
  }
  return grouped
})

const groupableColumns = computed(() =>
  columns.value.filter((c) => c.type === 'field').map((c) => ({ key: c.key, header: c.header }))
)

// Methods
function typeIcon(t: string) {
  if (t === 'number' || t === 'currency') return 'mdi-numeric'
  if (t === 'date' || t === 'datetime') return 'mdi-calendar'
  if (t === 'boolean') return 'mdi-checkbox-marked-outline'
  if (t === 'enum') return 'mdi-format-list-bulleted'
  return 'mdi-text-short'
}

function unitLabel(u: string) {
  return ({ rub: '₽', thousands: 'тыс.₽', millions: 'млн.₽', dmy: 'дата' } as Record<string, string>)[u] || ''
}

function addColumn(f: any) {
  columns.value.push({
    key: f.key,
    header: f.label,
    type: 'field',
    unit: 'none',
    field_type: f.type,
  })
  reload()
}

function removeColumn(idx: number) {
  columns.value.splice(idx, 1)
  reload()
}

function moveColumn(idx: number, delta: number) {
  const target = idx + delta
  if (target < 0 || target >= columns.value.length) return
  ;[columns.value[idx], columns.value[target]] = [columns.value[target], columns.value[idx]]
}

function editColumn(idx: number) {
  const col = columns.value[idx]
  if (col.type === 'composite') {
    editingIdx.value = idx
    compositeForm.value = { ...col }
    compositeDialog.value = true
  } else if (col.type === 'constant') {
    editingIdx.value = idx
    constantForm.value = { ...col }
    constantDialog.value = true
  } else {
    editFieldData.value = col
    editFieldDialog.value = true
  }
}

function openCompositeDialog() {
  editingIdx.value = -1
  compositeForm.value = { key: `_comp_${Date.now()}`, header: 'Новая колонка', template: '', fallback: '' }
  compositeDialog.value = true
}

function saveCompositeColumn() {
  const data = { ...compositeForm.value, type: 'composite' as const, unit: 'none' }
  if (editingIdx.value >= 0) columns.value[editingIdx.value] = data
  else columns.value.push(data)
  compositeDialog.value = false
  reload()
}

function openConstantDialog() {
  editingIdx.value = -1
  constantForm.value = { key: `_const_${Date.now()}`, header: 'Россия', value: 'Россия' }
  constantDialog.value = true
}

function saveConstantColumn() {
  const data = { ...constantForm.value, type: 'constant' as const, unit: 'none' }
  if (editingIdx.value >= 0) columns.value[editingIdx.value] = data
  else columns.value.push(data)
  constantDialog.value = false
  reload()
}

function resetFilters() {
  filters.value = { subsidy_id: [], status: [], contractor_id: [], item_type: [] }
  reload()
}

function buildConfig() {
  const fieldCols = columns.value.filter((c) => c.type === 'field').map((c) => c.key)
  const computedCols: any[] = columns.value
    .filter((c) => c.type === 'composite' || c.type === 'constant')
    .map((c) => ({
      key: c.key,
      type: c.type,
      template: c.template,
      fallback: c.fallback,
      value: c.value,
    }))
  for (const c of columns.value) {
    if (c.type === 'field' && c.unit && c.unit !== 'none') {
      computedCols.push({ key: `${c.key}_fmt`, type: 'format', source: c.key, format: c.unit })
    }
  }
  const cleanFilters: Record<string, any> = {}
  for (const [k, v] of Object.entries(filters.value)) {
    if (Array.isArray(v) ? (v as any[]).length : v) cleanFilters[k] = v
  }
  return {
    kind: 'list',
    columns: fieldCols,
    computed_columns: computedCols,
    filters: cleanFilters,
    group_by: groupBy.value,
    limit: 500,
  }
}

let debounceTimer: ReturnType<typeof setTimeout> | null = null
function reload() {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(runQuery, 350)
}

async function runQuery() {
  if (!columns.value.length) {
    rows.value = []
    rowsCount.value = 0
    return
  }
  loading.value = true
  try {
    const result = await apiFetch<any>('/api/analytics/query', {
      method: 'POST',
      body: JSON.stringify(buildConfig()),
    })
    rows.value = result.rows || []
    rowsCount.value = result.rows_count || result.rows?.length || 0
  } catch (e: any) {
    toast.error('Ошибка запроса: ' + (e?.message || String(e)))
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

function cellClass(_row: any, col: any) {
  if (col.field_type === 'currency' || col.field_type === 'number') return 'text-right'
  return ''
}

function formatCell(row: any, col: any) {
  const v = row[`${col.key}_fmt`] !== undefined ? row[`${col.key}_fmt`] : row[col.key]
  if (v === null || v === undefined || v === '') return ''
  return String(v)
}

async function saveConfig() {
  if (!configName.value.trim()) {
    toast.warning('Введите название')
    return
  }
  const body = {
    kind: 'list',
    name: configName.value,
    description: configDescription.value || null,
    config_json: buildConfig(),
    parameters_json: [],
    is_shared: isShared.value,
  }
  try {
    if (configId.value) {
      await apiFetch(`/api/report-configs/${configId.value}`, {
        method: 'PUT',
        body: JSON.stringify({
          name: configName.value,
          description: body.description,
          config_json: body.config_json,
          is_shared: body.is_shared,
        }),
      })
      toast.success('Шаблон обновлён')
    } else {
      const created = await apiFetch<any>('/api/report-configs/', {
        method: 'POST',
        body: JSON.stringify(body),
      })
      configId.value = created.id
      router.replace(`/reports/lists/${created.id}/edit`)
      toast.success('Шаблон сохранён')
    }
    saveDialog.value = false
  } catch (e: any) {
    toast.error('Ошибка сохранения: ' + (e?.message || String(e)))
  }
}

async function exportExcel() {
  try {
    const config = buildConfig()
    const token = localStorage.getItem('auth_token')
    const resp = await fetch('/api/analytics/export.xlsx', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ config, name: configName.value || 'Реестр' }),
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const blob = await resp.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${configName.value || 'Реестр'}_${new Date().toISOString().slice(0, 10)}.xlsx`
    a.click()
    URL.revokeObjectURL(url)
    toast.success('Excel выгружен')
  } catch (e: any) {
    toast.error('Excel: ' + (e?.message || e))
  }
}

async function exportPdf() {
  try {
    const config = buildConfig()
    const token = localStorage.getItem('auth_token')
    const resp = await fetch('/api/analytics/export.pdf', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ config, name: configName.value || 'Реестр' }),
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const blob = await resp.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${configName.value || 'Реестр'}_${new Date().toISOString().slice(0, 10)}.pdf`
    a.click()
    URL.revokeObjectURL(url)
    toast.success('PDF выгружен')
  } catch (e: any) {
    toast.error('PDF: ' + (e?.message || e))
  }
}

async function loadConfig(id: number) {
  const cfg = await apiFetch<any>(`/api/report-configs/${id}`)
  configId.value = cfg.id
  configName.value = cfg.name
  configDescription.value = cfg.description || ''
  isShared.value = cfg.is_shared
  const c = cfg.config_json || {}
  filters.value = { subsidy_id: [], status: [], contractor_id: [], item_type: [], ...c.filters }
  groupBy.value = c.group_by || []
  const cols: any[] = []
  for (const key of (c.columns || [])) {
    const f = fields.value.find((x: any) => x.key === key)
    if (f) cols.push({ key, header: f.label, type: 'field', unit: 'none', field_type: f.type })
  }
  for (const cc of (c.computed_columns || [])) {
    if (cc.type === 'format') {
      const col = cols.find((x) => x.key === cc.source)
      if (col) col.unit = cc.format
    } else {
      cols.push({ ...cc })
    }
  }
  columns.value = cols
  reload()
}

// Watchers
watch([filters, groupBy], reload, { deep: true })

// Init
onMounted(async () => {
  try {
    const f = await apiFetch<any>('/api/analytics/fields')
    fields.value = f.fields
    groups.value = f.groups
    openGroups.value = [...f.groups]
    const [subs, ctrs] = await Promise.all([
      apiFetch<any>('/api/subsidies/'),
      apiFetch<any>('/api/contractors/?limit=500'),
    ])
    subsidies.value = Array.isArray(subs) ? subs : subs.items || []
    contractors.value = Array.isArray(ctrs) ? ctrs : ctrs.items || []
    const idParam = route.params.id
    if (idParam) await loadConfig(Number(idParam))
  } catch (e: any) {
    toast.error('Ошибка загрузки: ' + (e?.message || String(e)))
  }
})
</script>

<style scoped>
.cursor-grab { cursor: grab; }
</style>
