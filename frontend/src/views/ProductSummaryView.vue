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
      <v-btn
        variant="outlined"
        size="small"
        prepend-icon="mdi-refresh"
        :loading="loading"
        @click="loadData"
      >
        Обновить
      </v-btn>
    </div>

    <!-- Filters -->
    <v-card class="filter-card mb-4" variant="outlined">
      <v-card-text class="py-3">
        <div class="d-flex align-center gap-3 flex-wrap">
          <v-select
            v-model="filterCategory"
            :items="categoryOptions"
            label="Категория"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            style="min-width: 200px; max-width: 250px"
          />
          <v-select
            v-model="filterSubsidy"
            :items="subsidyOptions"
            item-title="name"
            item-value="id"
            label="Субсидия"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            style="min-width: 200px; max-width: 250px"
          />
          <v-text-field
            v-model="searchText"
            prepend-inner-icon="mdi-magnify"
            label="Поиск по названию"
            variant="outlined"
            density="compact"
            clearable
            hide-details
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
        {{ groups.length === 0 ? 'Нет данных о закупках с привязкой к товарам' : 'Ничего не найдено по заданным фильтрам' }}
      </div>
    </div>

    <!-- Product groups -->
    <div v-else class="product-groups">
      <div
        v-for="group in filteredGroups"
        :key="group.product_id"
        class="product-group mb-3"
      >
        <!-- Group header -->
        <div
          class="group-header"
          @click="toggleGroup(group.product_id)"
        >
          <div class="d-flex align-center gap-2 flex-grow-1">
            <v-icon
              :icon="expandedGroups.has(group.product_id) ? 'mdi-chevron-down' : 'mdi-chevron-right'"
              size="20"
              style="color: var(--crm-text-muted)"
            />
            <span class="group-name">{{ group.product_name }}</span>
            <v-chip v-if="group.category" size="x-small" variant="tonal" color="primary">
              {{ group.category }}
            </v-chip>
            <v-chip v-if="group.product_type" size="x-small" variant="tonal">
              {{ group.product_type }}
            </v-chip>
          </div>
          <div class="d-flex align-center gap-4">
            <span class="group-stat">
              <strong>{{ formatQty(group.total_quantity) }}</strong> шт
            </span>
            <span class="group-stat">
              <strong>{{ formatCurrency(group.total_amount) }}</strong>
            </span>
            <v-chip size="x-small" variant="tonal" color="info">
              {{ group.purchase_count }} закуп{{ pluralize(group.purchase_count) }}
            </v-chip>
          </div>
        </div>

        <!-- Group items table -->
        <div v-if="expandedGroups.has(group.product_id)" class="group-items">
          <table class="items-table">
            <thead>
              <tr>
                <th>Организация</th>
                <th>Субсидия</th>
                <th class="text-right">Кол-во</th>
                <th class="text-right">Сумма</th>
                <th>Статус</th>
                <th>Способ</th>
                <th>Доставка</th>
                <th>Дата закупки</th>
                <th>Адрес</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in group.items" :key="item.purchase_id" class="item-row">
                <td>{{ item.org_name || '—' }}</td>
                <td>{{ item.subsidy_name }}</td>
                <td class="text-right">{{ formatQty(item.quantity) }} {{ item.unit || '' }}</td>
                <td class="text-right">{{ item.total_price ? formatCurrency(item.total_price) : '—' }}</td>
                <td>
                  <v-chip
                    :color="statusColor(item.status)"
                    size="x-small"
                    variant="tonal"
                  >
                    {{ statusLabel(item.status) }}
                  </v-chip>
                </td>
                <td>{{ methodLabel(item.purchase_method) }}</td>
                <td>{{ item.delivery_date || '—' }}</td>
                <td>{{ item.procurement_planned_date || '—' }}</td>
                <td class="text-truncate" style="max-width: 180px">{{ item.delivery_address || '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { apiFetch } from '@/api'

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

const loading = ref(false)
const groups = ref<SummaryGroup[]>([])
const subsidies = ref<SubsidyOption[]>([])
const expandedGroups = ref(new Set<number>())

// Filters
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

  if (filterCategory.value) {
    result = result.filter(g => g.category === filterCategory.value)
  }

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
  if (expandedGroups.value.has(id)) {
    expandedGroups.value.delete(id)
  } else {
    expandedGroups.value.add(id)
  }
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
  const m = n % 10
  const m100 = n % 100
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
  const map: Record<string, string> = {
    single: 'Единственный', competitive: 'Конкурентная',
  }
  return map[m] || m
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
  try {
    subsidies.value = await apiFetch<SubsidyOption[]>('/subsidies/')
  } catch { /* ok */ }
}

onMounted(async () => {
  await Promise.all([loadData(), loadSubsidies()])
  // Expand first group by default
  if (groups.value.length > 0) {
    expandedGroups.value.add(groups.value[0].product_id)
  }
})
</script>

<style scoped>
.page-title {
  color: var(--crm-text);
}
.page-subtitle {
  color: var(--crm-text-muted);
}
.filter-card {
  background: var(--crm-surface);
  border-color: var(--crm-border);
}

.product-group {
  background: var(--crm-surface);
  border: 1px solid var(--crm-border);
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 1px 3px var(--crm-shadow);
}

.group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  cursor: pointer;
  transition: background 0.15s;
}
.group-header:hover {
  background: var(--crm-surface-hover);
}

.group-name {
  font-weight: 600;
  font-size: 0.95rem;
  color: var(--crm-text);
}

.group-stat {
  font-size: 0.85rem;
  color: var(--crm-text-secondary);
}

.group-items {
  border-top: 1px solid var(--crm-border);
  overflow-x: auto;
}

.items-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}
.items-table th {
  padding: 8px 12px;
  text-align: left;
  font-weight: 600;
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: var(--crm-text-muted);
  background: var(--crm-table-header);
  border-bottom: 1px solid var(--crm-border-strong);
  white-space: nowrap;
}
.items-table td {
  padding: 8px 12px;
  color: var(--crm-text-secondary);
  border-bottom: 1px solid var(--crm-border);
}
.item-row:hover td {
  background: var(--crm-surface-alt);
}
.item-row:last-child td {
  border-bottom: none;
}
</style>
