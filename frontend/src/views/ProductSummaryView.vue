<template>
  <v-container fluid class="pa-6">
    <!-- Header -->
    <div class="d-flex align-center justify-space-between mb-4">
      <div>
        <h1 class="page-title text-h5 font-weight-bold">Сводная по продукции</h1>
        <span class="page-subtitle text-body-2">
          {{ groups.length }} продуктов, {{ totalPurchases }} закупок
        </span>
      </div>
      <v-btn variant="outlined" size="small" prepend-icon="mdi-refresh" :loading="loading" @click="loadData">
        Обновить
      </v-btn>
    </div>

    <!-- Filters -->
    <v-card class="filter-card mb-4" variant="outlined">
      <v-card-text class="py-3">
        <div class="d-flex align-center gap-3 flex-wrap">
          <v-select
            v-model="filterCategory" :items="categoryOptions" label="Категория"
            variant="outlined" density="compact" clearable hide-details
            style="min-width: 200px; max-width: 250px"
          />
          <v-select
            v-model="filterSubsidy" :items="subsidyOptions" item-title="name" item-value="id"
            label="Субсидия" variant="outlined" density="compact" clearable hide-details
            style="min-width: 200px; max-width: 250px"
          />
          <v-text-field
            v-model="searchText" prepend-inner-icon="mdi-magnify" label="Поиск по названию"
            variant="outlined" density="compact" clearable hide-details
            style="min-width: 200px; max-width: 300px"
          />
        </div>
      </v-card-text>
    </v-card>

    <!-- Loading -->
    <div v-if="loading" class="text-center py-10">
      <v-progress-circular indeterminate color="primary" size="48" />
    </div>

    <!-- Empty state -->
    <div v-else-if="filteredGroups.length === 0" class="text-center py-10">
      <v-icon icon="mdi-package-variant-remove" size="64" class="mb-3" style="color: var(--crm-text-faint)" />
      <div class="text-body-1" style="color: var(--crm-text-muted)">
        {{ groups.length === 0 ? 'Нет данных о закупках с привязкой к товарам' : 'Ничего не найдено' }}
      </div>
    </div>

    <!-- Table -->
    <div v-else class="summary-wrap">
      <table class="summary-table">
        <!-- SINGLE thead — headers only once at the top -->
        <thead>
          <tr>
            <th :style="resizeStyle('org')">
              Организация
              <span class="col-resize-handle" @mousedown="onResizeStart($event, 'org')">&nbsp;</span>
            </th>
            <th :style="resizeStyle('sub')">
              Субсидия
              <span class="col-resize-handle" @mousedown="onResizeStart($event, 'sub')">&nbsp;</span>
            </th>
            <th class="th-num" :style="resizeStyle('qty')">
              Кол-во
              <span class="col-resize-handle" @mousedown="onResizeStart($event, 'qty')">&nbsp;</span>
            </th>
            <th class="th-num" :style="resizeStyle('amt')">
              Сумма
              <span class="col-resize-handle" @mousedown="onResizeStart($event, 'amt')">&nbsp;</span>
            </th>
            <th :style="resizeStyle('status')">
              Статус
              <span class="col-resize-handle" @mousedown="onResizeStart($event, 'status')">&nbsp;</span>
            </th>
            <th :style="resizeStyle('method')">
              Способ
              <span class="col-resize-handle" @mousedown="onResizeStart($event, 'method')">&nbsp;</span>
            </th>
            <th :style="resizeStyle('deliv')">
              Доставка
              <span class="col-resize-handle" @mousedown="onResizeStart($event, 'deliv')">&nbsp;</span>
            </th>
            <th :style="resizeStyle('date')">
              Дата закупки
              <span class="col-resize-handle" @mousedown="onResizeStart($event, 'date')">&nbsp;</span>
            </th>
            <th :style="resizeStyle('addr')">
              Адрес
            </th>
          </tr>
        </thead>

        <!-- SINGLE tbody with template iteration — guarantees one thead, aligned columns -->
        <tbody>
          <template v-for="group in filteredGroups" :key="group.product_id">
            <!-- Group header row -->
            <tr class="group-row" @click="toggleGroup(group.product_id)">
              <td colspan="2" class="group-name-cell">
                <div class="d-flex align-center gap-2">
                  <v-icon
                    :icon="expandedGroups.has(group.product_id) ? 'mdi-chevron-down' : 'mdi-chevron-right'"
                    size="17" class="flex-shrink-0" style="color: var(--crm-text-muted)"
                  />
                  <span class="group-name">{{ group.product_name }}</span>
                  <v-chip v-if="group.category" size="x-small" variant="tonal" color="primary">{{ group.category }}</v-chip>
                  <v-chip v-if="group.product_type" size="x-small" variant="tonal">{{ group.product_type }}</v-chip>
                </div>
              </td>
              <td class="td-num group-total">
                <strong>{{ formatQty(group.total_quantity) }}</strong>
                <span class="unit-text">&nbsp;шт</span>
              </td>
              <td class="td-num group-total">
                <strong>{{ formatCurrency(group.total_amount) }}</strong>
              </td>
              <td>
                <v-chip size="x-small" variant="tonal" color="info">
                  {{ group.purchase_count }}&nbsp;закуп{{ pluralize(group.purchase_count) }}
                </v-chip>
              </td>
              <td colspan="4"></td>
            </tr>

            <!-- Item rows (expanded) -->
            <template v-if="expandedGroups.has(group.product_id)">
              <tr v-for="item in group.items" :key="item.purchase_id" class="item-row">
                <td class="td-clip">{{ item.org_name || '—' }}</td>
                <td class="td-clip">{{ item.subsidy_name }}</td>
                <td class="td-num">
                  {{ formatQty(item.quantity) }}
                  <span v-if="item.unit" class="unit-text">&nbsp;{{ item.unit }}</span>
                </td>
                <td class="td-num">{{ item.total_price ? formatCurrency(item.total_price) : '—' }}</td>
                <td>
                  <v-chip :color="statusColor(item.status)" size="x-small" variant="tonal">
                    {{ statusLabel(item.status) }}
                  </v-chip>
                </td>
                <td class="td-clip">{{ methodLabel(item.purchase_method) }}</td>
                <td>{{ item.delivery_date || '—' }}</td>
                <td>{{ item.procurement_planned_date || '—' }}</td>
                <td class="td-clip">{{ item.delivery_address || '—' }}</td>
              </tr>
            </template>
          </template>
        </tbody>
      </table>
    </div>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { apiFetch } from '@/api'
import { useResizableColumns } from '@/composables/useResizableColumns'

interface SummaryItem {
  purchase_id: number
  subsidy_name: string
  org_name: string | null
  quantity: number | null
  unit: string | null
  unit_price: number | null
  total_price: number | null
  status: string | null
  delivery_date: string | null
  delivery_address: string | null
  procurement_planned_date: string | null
  purchase_method: string | null
}

interface SummaryGroup {
  product_id: number
  product_name: string
  category: string | null
  product_type: string | null
  total_quantity: number
  total_amount: number
  purchase_count: number
  items: SummaryItem[]
}

interface SubsidyOption {
  id: number
  name: string
}

const { onResizeStart, resizeStyle } = useResizableColumns('product-summary', {
  org: 220, sub: 140, qty: 90, amt: 130, status: 110, method: 110, deliv: 110, date: 110, addr: 160,
})

const loading = ref(false)
const groups = ref<SummaryGroup[]>([])
const subsidies = ref<SubsidyOption[]>([])
const expandedGroups = ref(new Set<number>())

const filterCategory = ref<string | null>(null)
const filterSubsidy = ref<number | null>(null)
const searchText = ref('')

const totalPurchases = computed(() =>
  groups.value.reduce((sum, g) => sum + g.purchase_count, 0)
)

const categoryOptions = computed(() => {
  const cats = new Set<string>()
  groups.value.forEach(g => { if (g.category) cats.add(g.category) })
  return Array.from(cats).sort()
})

const subsidyOptions = computed(() => subsidies.value)

const filteredGroups = computed(() => {
  let result = groups.value

  if (filterCategory.value)
    result = result.filter(g => g.category === filterCategory.value)

  if (filterSubsidy.value) {
    result = result
      .map(g => ({
        ...g,
        items: g.items.filter(i => {
          const sub = subsidies.value.find(s => s.id === filterSubsidy.value)
          return sub ? i.subsidy_name === sub.name : true
        }),
      }))
      .filter(g => g.items.length > 0)
      .map(g => ({
        ...g,
        purchase_count: g.items.length,
        total_quantity: g.items.reduce((s, i) => s + (i.quantity || 0), 0),
        total_amount: g.items.reduce((s, i) => s + (i.total_price || 0), 0),
      }))
  }

  if (searchText.value) {
    const q = searchText.value.toLowerCase()
    result = result.filter(g => g.product_name.toLowerCase().includes(q))
  }

  return result
})

const toggleGroup = (id: number) => {
  if (expandedGroups.value.has(id)) expandedGroups.value.delete(id)
  else expandedGroups.value.add(id)
}

const formatCurrency = (v: number | null) => {
  if (v == null) return '—'
  return Number(v).toLocaleString('ru-RU', { maximumFractionDigits: 2 }) + ' ₽'
}

const formatQty = (v: number | null) => {
  if (v == null) return '0'
  return Number(v).toLocaleString('ru-RU', { maximumFractionDigits: 2 })
}

const pluralize = (n: number) => {
  const m = n % 10, m100 = n % 100
  if (m100 >= 11 && m100 <= 19) return 'ок'
  if (m === 1) return 'ка'
  if (m >= 2 && m <= 4) return 'ки'
  return 'ок'
}

const statusColor = (s: string | null) => {
  const map: Record<string, string> = {
    wishes: 'grey', planned: 'blue', confirmed: 'indigo',
    contracted: 'orange', delivered: 'teal', paid: 'green',
  }
  return map[s || ''] || 'grey'
}

const statusLabel = (s: string | null) => {
  const map: Record<string, string> = {
    wishes: 'Пожелание', planned: 'Запланировано', confirmed: 'Подтверждено',
    contracted: 'Договор', delivered: 'Доставлено', paid: 'Оплачено',
  }
  return map[s || ''] || s || '—'
}

const methodLabel = (m: string | null) => {
  if (!m) return '—'
  return ({ single: 'Единственный', competitive: 'Конкурентная' } as Record<string, string>)[m] || m
}

const loadData = async () => {
  loading.value = true
  try {
    const params = new URLSearchParams()
    if (filterSubsidy.value) params.set('subsidy_id', String(filterSubsidy.value))
    if (filterCategory.value) params.set('category', filterCategory.value)
    const qs = params.toString()
    groups.value = await apiFetch<SummaryGroup[]>(`/products/summary${qs ? '?' + qs : ''}`)
  } catch (e) {
    console.error('Failed to load product summary:', e)
  } finally {
    loading.value = false
  }
}

const loadSubsidies = async () => {
  try { subsidies.value = await apiFetch<SubsidyOption[]>('/subsidies/') } catch { /* ok */ }
}

onMounted(async () => {
  await Promise.all([loadData(), loadSubsidies()])
  if (groups.value.length > 0) expandedGroups.value.add(groups.value[0].product_id)
})
</script>

<style scoped>
.page-title  { color: var(--crm-text); }
.page-subtitle { color: var(--crm-text-muted); }
.filter-card { background: var(--crm-surface); border-color: var(--crm-border); }

/* Table wrapper */
.summary-wrap {
  background: var(--crm-surface);
  border: 1px solid var(--crm-border);
  border-radius: 8px;
  overflow: hidden;
  overflow-x: auto;
  box-shadow: 0 1px 3px var(--crm-shadow);
}

/* Table base */
.summary-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
  table-layout: fixed;
}

/* Header */
.summary-table thead th {
  position: relative;
  padding: 10px 12px;
  text-align: left;
  font-weight: 600;
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--crm-text-muted);
  background: var(--crm-table-header);
  border-bottom: 2px solid var(--crm-border-strong);
  white-space: nowrap;
  overflow: hidden;
}
.th-num { text-align: right !important; }

/* Resize handle */
.col-resize-handle {
  position: absolute;
  right: 0;
  top: 0;
  bottom: 0;
  width: 5px;
  cursor: col-resize;
  background: transparent;
  display: block;
}
.col-resize-handle:hover {
  background: rgba(var(--v-theme-primary, 25,118,210), 0.25);
}

/* Cells */
.summary-table td {
  padding: 7px 12px;
  color: var(--crm-text-secondary);
  border-bottom: 1px solid var(--crm-border);
  vertical-align: middle;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.td-num  { text-align: right !important; }
.td-clip { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* Group separator row */
.group-row {
  cursor: pointer;
  background: var(--crm-table-header);
  border-top: 2px solid var(--crm-border-strong) !important;
}
.group-row:hover td { background: var(--crm-surface-hover); }
.group-row td { border-bottom: 1px solid var(--crm-border-strong); }

/* Product name cell — allow text wrapping */
.group-name-cell {
  overflow: visible !important;
  white-space: normal !important;
}
.group-name {
  font-weight: 600;
  font-size: 0.9rem;
  color: var(--crm-text);
}

/* Group totals */
.group-total {
  color: var(--crm-text) !important;
  font-size: 0.88rem;
}
.unit-text {
  font-size: 0.75rem;
  color: var(--crm-text-muted);
  font-weight: normal;
}

/* Item rows */
.item-row:hover td { background: var(--crm-surface-alt); }
.item-row:last-child td { border-bottom: none; }
</style>
