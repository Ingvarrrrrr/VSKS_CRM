<template>
  <div class="related-purchases-tab pa-4">
    <!-- Backend filter banner -->
    <v-alert
      v-if="backendFilterMissing"
      type="info"
      variant="tonal"
      density="compact"
      class="mb-4"
      icon="mdi-information-outline"
    >
      Backend-фильтр <code>?vehicle_id</code> добавляется в 29-21 — пока показываем все закупки с
      фильтрацией в браузере.
    </v-alert>

    <!-- Error -->
    <v-alert
      v-if="error"
      type="error"
      variant="tonal"
      density="compact"
      class="mb-4"
      closable
      @click:close="error = ''"
    >{{ error }}</v-alert>

    <!-- Loading -->
    <v-progress-linear v-if="loading" indeterminate color="primary" height="3" rounded class="mb-4" />

    <!-- Groups -->
    <template v-if="!loading">
      <div
        v-for="group in groupedPurchases"
        :key="group.key"
        class="mb-6"
      >
        <div class="d-flex align-center justify-space-between mb-2">
          <div class="text-subtitle-1 font-weight-medium d-flex align-center gap-2">
            <v-icon size="18" :color="group.color">{{ group.icon }}</v-icon>
            {{ group.label }}
            <v-chip size="x-small" variant="tonal" :color="group.color">{{ group.rows.length }}</v-chip>
          </div>
          <div class="text-body-2 font-weight-medium text-medium-emphasis">
            Итого: {{ formatMoney(group.total) }} ₽
          </div>
        </div>

        <v-data-table
          v-resizable-columns="'vehicle-related-purchases'"
          :headers="headers"
          :items="group.rows"
          density="compact"
          hide-default-footer
          :items-per-page="-1"
          class="elevation-0 border rounded"
        >
          <template #item.purchase_date="{ item }">
            {{ formatDate(item.purchase_date) }}
          </template>
          <template #item.total_amount="{ item }">
            {{ formatMoney(item.total_amount) }} ₽
          </template>
          <template #item.status="{ item }">
            <v-chip :color="statusColor(item.status)" size="x-small" variant="tonal">
              {{ statusLabel(item.status) }}
            </v-chip>
          </template>
          <template #item.contractor_name="{ item }">
            {{ item.contractor_name || '—' }}
          </template>
          <template #item.actions="{ item }">
            <v-btn
              size="x-small"
              variant="text"
              color="primary"
              :to="`/orders/${item.id}`"
              @click.stop
            >
              Открыть
            </v-btn>
          </template>
        </v-data-table>
      </div>

      <!-- Empty state -->
      <div
        v-if="!loading && filteredPurchases.length === 0"
        class="text-center text-medium-emphasis py-8"
      >
        <v-icon size="40" class="mb-2">mdi-cart-outline</v-icon>
        <div>Нет связанных закупок для этого ТС</div>
      </div>
    </template>

    <!-- Repairs without purchase -->
    <v-divider class="my-6" />
    <div class="mb-2 d-flex align-center justify-space-between">
      <div class="text-subtitle-1 font-weight-medium d-flex align-center gap-2">
        <v-icon size="18" color="orange">mdi-wrench-outline</v-icon>
        Ремонты без закупки
        <v-chip size="x-small" variant="tonal" color="orange">{{ repairsWithoutPurchase.length }}</v-chip>
      </div>
      <div class="text-body-2 font-weight-medium text-medium-emphasis">
        Итого: {{ formatMoney(repairsWithoutPurchaseTotal) }} ₽
      </div>
    </div>

    <div v-if="loadingRepairs">
      <v-progress-linear indeterminate color="orange" height="2" rounded class="mb-2" />
    </div>

    <div
      v-else-if="repairsWithoutPurchase.length === 0"
      class="text-body-2 text-medium-emphasis py-2"
    >
      Все ремонты привязаны к закупкам
    </div>

    <v-data-table
      v-resizable-columns="'vehicle-related-repairs'"
      v-else
      :headers="repairHeaders"
      :items="repairsWithoutPurchase"
      density="compact"
      hide-default-footer
      :items-per-page="-1"
      class="elevation-0 border rounded"
    >
      <template #item.repair_date="{ item }">
        {{ formatDate(item.repair_date) }}
      </template>
      <template #item.cost_amount="{ item }">
        {{ formatMoney(item.cost_amount) }} ₽
      </template>
      <template #item.status="{ item }">
        <v-chip :color="repairStatusColor(item.status)" size="x-small" variant="tonal">
          {{ item.status || '—' }}
        </v-chip>
      </template>
      <template #item.actions>
        <v-btn
          size="x-small"
          variant="text"
          color="orange"
          :to="`/vehicles/${vehicleId}?tab=repairs`"
          @click.stop
        >
          В ремонты
        </v-btn>
      </template>
    </v-data-table>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { apiFetch } from '@/api'

const props = defineProps<{
  vehicleId: number
}>()

// ── State ──────────────────────────────────────────────────────────────────
const loading = ref(false)
const loadingRepairs = ref(false)
const error = ref('')
const backendFilterMissing = ref(false)
const allPurchases = ref<PurchaseRow[]>([])
const repairs = ref<RepairRow[]>([])

// ── Types ──────────────────────────────────────────────────────────────────
interface PurchaseRow {
  id: number
  purchase_date?: string
  subject?: string
  contractor_name?: string
  total_amount?: number
  status?: string
  vehicle_id?: number | null
  purchase_method?: string
}

interface RepairRow {
  id: number
  repair_date?: string
  description?: string
  cost_amount?: number
  performed_by_name?: string
  status?: string
  purchase_id?: number | null
}

// ── Table headers ──────────────────────────────────────────────────────────
const headers = [
  { title: '№', key: 'id', width: 70, sortable: true },
  { title: 'Дата', key: 'purchase_date', width: 110, sortable: true },
  { title: 'Тип / Предмет', key: 'subject', sortable: false },
  { title: 'Контрагент', key: 'contractor_name', sortable: false },
  { title: 'Сумма', key: 'total_amount', width: 130, align: 'end' as const, sortable: true },
  { title: 'Статус', key: 'status', width: 120, sortable: false },
  { title: '', key: 'actions', width: 90, sortable: false },
]

const repairHeaders = [
  { title: '№', key: 'id', width: 70, sortable: true },
  { title: 'Дата', key: 'repair_date', width: 110, sortable: true },
  { title: 'Описание', key: 'description', sortable: false },
  { title: 'Исполнитель', key: 'performed_by_name', sortable: false },
  { title: 'Стоимость', key: 'cost_amount', width: 130, align: 'end' as const, sortable: true },
  { title: 'Статус', key: 'status', width: 120, sortable: false },
  { title: '', key: 'actions', width: 110, sortable: false },
]

// ── Fetch ──────────────────────────────────────────────────────────────────
async function fetchPurchases () {
  loading.value = true
  error.value = ''
  backendFilterMissing.value = false
  try {
    const res = await apiFetch<{ items?: PurchaseRow[] } | PurchaseRow[]>(
      '/purchases/?vehicle_id=' + props.vehicleId
    )
    const data: PurchaseRow[] = (res as any)?.items ?? (res as PurchaseRow[]) ?? []

    // Check if backend actually filtered or returned everything
    const hasUnrelated = data.some(p => p.vehicle_id !== props.vehicleId && p.vehicle_id != null)
    if (hasUnrelated || data.length > 50) {
      // Backend didn't filter — do client-side
      backendFilterMissing.value = true
      allPurchases.value = data.filter(p => p.vehicle_id === props.vehicleId)
    } else {
      allPurchases.value = data
    }
  } catch (e: unknown) {
    const status = (e as any)?.status as number | undefined
    if (status === 422 || status === 400) {
      // Param not supported — fetch all and filter client-side
      backendFilterMissing.value = true
      try {
        const fallback = await apiFetch<{ items?: PurchaseRow[] } | PurchaseRow[]>('/purchases/')
        const fallbackData: PurchaseRow[] = (fallback as any)?.items ?? (fallback as PurchaseRow[]) ?? []
        allPurchases.value = fallbackData.filter(p => p.vehicle_id === props.vehicleId)
      } catch (e2: unknown) {
        error.value = (e2 as any)?.payload?.message ?? (e2 as any)?.message ?? 'Ошибка загрузки закупок'
      }
    } else {
      error.value = (e as any)?.payload?.message ?? (e as any)?.message ?? 'Ошибка загрузки закупок'
    }
  } finally {
    loading.value = false
  }
}

async function fetchRepairs () {
  loadingRepairs.value = true
  try {
    const res = await apiFetch<{ items?: RepairRow[] } | RepairRow[]>(
      '/vehicle-repairs/?vehicle_id=' + props.vehicleId
    )
    const data: RepairRow[] = (res as any)?.items ?? (res as RepairRow[]) ?? []
    repairs.value = data
  } catch {
    repairs.value = []
  } finally {
    loadingRepairs.value = false
  }
}

// ── Computed ───────────────────────────────────────────────────────────────
const filteredPurchases = computed(() => allPurchases.value)

// Classify purchase into a group based on subject/purchase_method keywords
function classifyPurchase (p: PurchaseRow): 'repair' | 'fuel' | 'insurance' | 'other' {
  const text = ((p.subject ?? '') + ' ' + (p.purchase_method ?? '')).toLowerCase()
  if (/ремонт|техобслуж|то |технич|шин|запчас/.test(text)) return 'repair'
  if (/топлив|бензин|дизел|газ|гсм|заправ/.test(text)) return 'fuel'
  if (/страхов|осаго|каско/.test(text)) return 'insurance'
  return 'other'
}

interface PurchaseGroup {
  key: string
  label: string
  icon: string
  color: string
  rows: PurchaseRow[]
  total: number
}

const groupedPurchases = computed<PurchaseGroup[]>(() => {
  const map: Record<string, PurchaseRow[]> = { repair: [], fuel: [], insurance: [], other: [] }
  for (const p of filteredPurchases.value) {
    map[classifyPurchase(p)].push(p)
  }
  const meta: Record<string, { label: string; icon: string; color: string }> = {
    repair:    { label: 'Ремонт и ТО',   icon: 'mdi-wrench',             color: 'orange'  },
    fuel:      { label: 'Топливо / ГСМ', icon: 'mdi-gas-station',        color: 'blue'    },
    insurance: { label: 'Страхование',   icon: 'mdi-shield-check',       color: 'green'   },
    other:     { label: 'Прочее',        icon: 'mdi-dots-horizontal-circle', color: 'grey' },
  }
  return (['repair', 'fuel', 'insurance', 'other'] as const)
    .filter(k => map[k].length > 0)
    .map(k => ({
      key: k,
      ...meta[k],
      rows: map[k],
      total: map[k].reduce((s, p) => s + (p.total_amount ?? 0), 0),
    }))
})

const repairsWithoutPurchase = computed(() =>
  repairs.value.filter(r => !r.purchase_id)
)

const repairsWithoutPurchaseTotal = computed(() =>
  repairsWithoutPurchase.value.reduce((s, r) => s + (r.cost_amount ?? 0), 0)
)

// ── Helpers ────────────────────────────────────────────────────────────────
function formatDate (d?: string): string {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

function formatMoney (v?: number): string {
  if (v == null) return '0'
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(v)
}

const STATUS_LABELS: Record<string, string> = {
  draft:       'Черновик',
  planned:     'Запланирована',
  in_progress: 'В работе',
  completed:   'Завершена',
  cancelled:   'Отменена',
}

const STATUS_COLORS: Record<string, string> = {
  draft:       'grey',
  planned:     'blue',
  in_progress: 'orange',
  completed:   'green',
  cancelled:   'red',
}

function statusLabel (s?: string): string {
  return s ? (STATUS_LABELS[s] ?? s) : '—'
}

function statusColor (s?: string): string {
  return s ? (STATUS_COLORS[s] ?? 'grey') : 'grey'
}

function repairStatusColor (s?: string): string {
  const map: Record<string, string> = {
    planned: 'blue', in_progress: 'orange', completed: 'green', cancelled: 'grey',
  }
  return s ? (map[s] ?? 'grey') : 'grey'
}

// ── Lifecycle ──────────────────────────────────────────────────────────────
onMounted(() => {
  fetchPurchases()
  fetchRepairs()
})
</script>
