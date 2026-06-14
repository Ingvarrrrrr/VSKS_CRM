<template>
  <v-container fluid class="waybills-list pa-6">
    <!-- Header -->
    <div class="wb-top">
      <div>
        <div class="wb-crumbs">
          <router-link to="/fleet">Автопарк</router-link>
          <span class="sep">/</span>
          <span class="current">Путевые листы</span>
        </div>
        <h1 class="wb-title">Журнал путевых листов</h1>
      </div>
      <div class="wb-top-actions">
        <v-btn variant="outlined" prepend-icon="mdi-microsoft-excel" size="small">Экспорт</v-btn>
        <v-btn
          color="primary"
          prepend-icon="mdi-plus"
          @click="$router.push('/fleet/waybills/new')"
        >Новый ПЛ</v-btn>
      </div>
    </div>

    <!-- KPI Strip -->
    <div class="wb-kpis">
      <KpiCard
        label="Всего за месяц"
        :value="stats.total ?? '—'"
        :trend="stats.total_vs_prev ? `+${stats.total_vs_prev} к пред. месяцу` : undefined"
        trend-type="ok"
        variant="default"
      />
      <KpiCard
        label="Активных"
        :value="stats.in_progress ?? '—'"
        sub="в работе на маршруте"
        variant="ok"
      />
      <KpiCard
        label="На проверке"
        :value="stats.on_review ?? '—'"
        sub="ожидают закрытия"
        variant="warn"
      />
      <KpiCard
        label="Закрыто"
        :value="stats.closed ?? '—'"
        sub="проведены в учёте"
        variant="default"
      />
      <KpiCard
        label="Просрочены"
        :value="stats.overdue ?? '—'"
        sub="требуют внимания"
        variant="alert"
        :trend="stats.overdue ? 'требует внимания' : undefined"
        trend-type="alert"
      />
    </div>

    <!-- Filter chips -->
    <div class="wb-filters">
      <button
        v-for="f in filterOptions"
        :key="f.value"
        class="wb-chip"
        :class="{ 'wb-chip--active': activeFilter === f.value }"
        @click="activeFilter = f.value"
      >
        {{ f.label }}
        <span class="wb-chip-num">{{ f.count }}</span>
      </button>
      <v-text-field
        v-model="search"
        placeholder="Поиск по номеру, водителю, маршруту…"
        density="compact"
        variant="outlined"
        prepend-inner-icon="mdi-magnify"
        hide-details
        clearable
        class="wb-search"
      />
      <v-btn-toggle
        v-if="!mobile"
        v-model="viewMode"
        mandatory
        density="compact"
        variant="outlined"
        divided
      >
        <v-btn value="table" size="small" icon="mdi-table" />
        <v-btn value="cards" size="small" icon="mdi-view-grid" />
      </v-btn-toggle>
    </div>

    <!-- Table view -->
    <div v-if="effectiveView === 'table'" class="wb-table-wrap">
      <v-data-table-server
        v-resizable-columns="'fleet-waybills'"
        v-model:items-per-page="tableItemsPerPage"
        v-model:page="tablePage"
        :headers="headers"
        :items="filteredRows"
        :items-length="filteredRows.length"
        :loading="loading"
        item-value="id"
        class="wb-table"
        density="compact"
        hover
        @click:row="(_, { item }) => openWaybill(item)"
      >
        <!-- № -->
        <template #item.number="{ item }">
          <span class="wb-num">{{ item.number }}</span>
        </template>

        <!-- Дата -->
        <template #item.date_start="{ item }">
          <span class="wb-date">{{ formatDate(item.date_start) }}</span>
        </template>

        <!-- Водитель -->
        <template #item.driver="{ item }">
          <div class="wb-driver">
            <GradientAvatar :full-name="item.driver_name || '?'" size="sm" />
            <div>
              <div class="wb-driver-name">{{ item.driver_name || '—' }}</div>
              <div class="wb-driver-sub">{{ item.driver_unit || '' }}</div>
            </div>
          </div>
        </template>

        <!-- Транспорт -->
        <template #item.vehicle="{ item }">
          <div class="wb-veh">
            <div class="wb-veh-icon">
              <v-icon size="18" color="var(--accent)">mdi-car</v-icon>
            </div>
            <div>
              <LicensePlate v-if="item.vehicle_plate" :model-value="item.vehicle_plate" size="sm" />
              <div class="wb-veh-model">{{ item.vehicle_model || '—' }}</div>
            </div>
          </div>
        </template>

        <!-- Маршрут -->
        <template #item.route="{ item }">
          <div class="wb-route">
            <span>{{ item.route_from || '—' }}</span>
            <v-icon size="14" color="var(--muted)">mdi-arrow-right</v-icon>
            <span>{{ item.route_to || '—' }}</span>
          </div>
        </template>

        <!-- Статус -->
        <template #item.status="{ item }">
          <StatusPill
            :variant="statusVariant(item.status)"
            :dot="item.status === 'in_progress'"
          >{{ statusLabel(item.status) }}</StatusPill>
        </template>

        <!-- Пробег -->
        <template #item.mileage="{ item }">
          <div class="wb-mileage">
            <div v-if="item.planned_mileage_km" class="wb-mileage-bar">
              <div
                class="wb-mileage-fill"
                :style="{ width: mileagePct(item) + '%', background: mileageFill(item) }"
              />
            </div>
            <span class="wb-metric">
              {{ item.actual_mileage_km != null ? item.actual_mileage_km : '—' }}
              <span v-if="item.actual_mileage_km != null" class="wb-unit">км</span>
            </span>
          </div>
        </template>

        <!-- Топливо -->
        <template #item.fuel="{ item }">
          <div class="wb-fuel">
            <div v-if="item.fuel_issued_l" class="wb-fuel-bar">
              <div class="wb-fuel-fill" :style="{ width: Math.min((item.fuel_issued_l / 120) * 100, 100) + '%' }" />
            </div>
            <span class="wb-metric">
              {{ item.fuel_issued_l != null ? item.fuel_issued_l : '—' }}
              <span v-if="item.fuel_issued_l != null" class="wb-unit">л</span>
            </span>
          </div>
        </template>

        <!-- Actions -->
        <template #item.actions="{ item }">
          <div class="wb-actions" @click.stop>
            <v-btn
              icon="mdi-open-in-new"
              size="x-small"
              variant="text"
              title="Открыть"
              @click="openWaybill(item)"
            />
            <v-btn
              icon="mdi-download"
              size="x-small"
              variant="text"
              title="Скачать .docx"
              :loading="downloadingId === item.id"
              @click="downloadDocx(item.id, item.number)"
            />
          </div>
        </template>

        <!-- Empty state -->
        <template #no-data>
          <div class="wb-empty">
            <v-icon size="48" color="var(--muted)">mdi-file-document-outline</v-icon>
            <div>Путевые листы не найдены</div>
          </div>
        </template>
      </v-data-table-server>
    </div>

    <!-- Cards view -->
    <div v-else class="py-2">
      <v-progress-linear v-if="loading" indeterminate color="primary" class="mb-3" />
      <div v-if="!loading && pagedCards.length === 0" class="wb-empty">
        <v-icon size="48" color="var(--muted)">mdi-file-document-outline</v-icon>
        <div>Путевые листы не найдены</div>
      </div>
      <v-row dense>
        <v-col v-for="item in pagedCards" :key="item.id" cols="12" sm="6" lg="4">
          <v-card variant="outlined" class="h-100 d-flex flex-column" hover @click="openWaybill(item)">
            <v-card-item class="pb-1">
              <v-card-title class="text-body-2 font-weight-bold">
                <span class="wb-num">{{ item.number }}</span>
              </v-card-title>
              <template #append>
                <StatusPill :variant="statusVariant(item.status)" :dot="item.status === 'in_progress'">
                  {{ statusLabel(item.status) }}
                </StatusPill>
              </template>
            </v-card-item>
            <v-card-text class="py-1 flex-grow-1">
              <div class="text-caption text-medium-emphasis mb-1">{{ formatDate(item.date_start) }}</div>
              <div v-if="item.driver_name" class="d-flex align-center gap-2 mb-1">
                <GradientAvatar :full-name="item.driver_name || '?'" size="sm" />
                <span class="text-body-2">{{ item.driver_name }}</span>
              </div>
              <div v-if="item.vehicle_plate" class="d-flex align-center gap-2 mb-1">
                <LicensePlate v-if="item.vehicle_plate" :model-value="item.vehicle_plate" size="sm" />
                <span v-if="item.vehicle_model" class="text-caption text-medium-emphasis">{{ item.vehicle_model }}</span>
              </div>
              <div v-if="item.route_from || item.route_to" class="text-caption d-flex align-center gap-1">
                <span>{{ item.route_from || '—' }}</span>
                <v-icon size="12" color="var(--muted)">mdi-arrow-right</v-icon>
                <span>{{ item.route_to || '—' }}</span>
              </div>
              <div class="d-flex gap-4 mt-1 text-caption text-medium-emphasis">
                <span v-if="item.actual_mileage_km != null">Пробег: <strong>{{ item.actual_mileage_km }} км</strong></span>
                <span v-if="item.fuel_issued_l != null">Топливо: <strong>{{ item.fuel_issued_l }} л</strong></span>
              </div>
            </v-card-text>
            <v-divider />
            <v-card-actions class="py-1" @click.stop>
              <v-spacer />
              <v-btn icon="mdi-open-in-new" size="x-small" variant="text" title="Открыть" @click.stop="openWaybill(item)" />
              <v-btn
                icon="mdi-download"
                size="x-small"
                variant="text"
                title="Скачать .docx"
                :loading="downloadingId === item.id"
                @click.stop="downloadDocx(item.id, item.number)"
              />
            </v-card-actions>
          </v-card>
        </v-col>
      </v-row>
      <v-pagination
        v-if="cardsTotalPages > 1"
        v-model="cardsPage"
        :length="cardsTotalPages"
        density="compact"
        total-visible="7"
        class="d-flex justify-center mt-4"
      />
    </div>

    <!-- Split panel: chart + top drivers -->
    <div class="wb-split">
      <!-- Chart by days -->
      <div class="wb-panel">
        <div class="wb-panel-header">
          <h3>ПЛ по дням месяца</h3>
        </div>
        <div class="wb-chart" ref="chartRef">
          <div
            v-for="day in chartData"
            :key="day.day"
            class="wb-bar"
            :title="`${day.day}: закрыто ${day.closed}, на проверке ${day.review}, просрочено ${day.overdue}`"
          >
            <div class="wb-bar-stack" :style="{ height: day.totalPx + 'px' }">
              <div class="wb-bar-seg wb-bar-seg--closed" :style="{ height: day.closedPct + '%' }" />
              <div class="wb-bar-seg wb-bar-seg--review" :style="{ height: day.reviewPct + '%' }" />
              <div class="wb-bar-seg wb-bar-seg--overdue" :style="{ height: day.overduePct + '%' }" />
            </div>
            <div class="wb-bar-lbl">{{ day.day }}</div>
          </div>
        </div>
        <div class="wb-chart-legend">
          <span><i class="leg-dot leg-dot--closed" />Закрыты</span>
          <span><i class="leg-dot leg-dot--review" />На проверке / в работе</span>
          <span><i class="leg-dot leg-dot--overdue" />Просрочены</span>
        </div>
      </div>

      <!-- Top 5 drivers -->
      <div class="wb-panel">
        <div class="wb-panel-header">
          <h3>Топ-5 водителей · по пробегу</h3>
        </div>
        <div v-if="topDrivers.length === 0" class="wb-top-empty">Нет данных</div>
        <div
          v-for="(drv, i) in topDrivers"
          :key="drv.driver_user_id"
          class="wb-drv-row"
        >
          <div class="wb-drv-rank">{{ i + 1 }}</div>
          <GradientAvatar :full-name="drv.driver_name || '?'" size="sm" />
          <div class="wb-drv-info">
            <div class="wb-drv-name">{{ drv.driver_name || 'Водитель' }}</div>
            <div class="wb-drv-sub">{{ drv.trips_count }} листов</div>
          </div>
          <div class="wb-drv-km">{{ drv.total_mileage_km.toLocaleString('ru-RU') }} км</div>
        </div>
      </div>
    </div>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch } from '@/api'
import KpiCard from '@/components/fleet/KpiCard.vue'
import StatusPill from '@/components/fleet/StatusPill.vue'
import GradientAvatar from '@/components/fleet/GradientAvatar.vue'
import LicensePlate from '@/components/vehicles/LicensePlate.vue'
import { useCardView } from '@/composables/useCardView'

const router = useRouter()

// ─── Types ───────────────────────────────────────────────────────────────────
interface WaybillRow {
  id: number
  number: string
  date_start: string
  driver_name?: string
  driver_unit?: string
  vehicle_plate?: string
  vehicle_model?: string
  route_from?: string
  route_to?: string
  status: string
  actual_mileage_km?: number
  planned_mileage_km?: number
  fuel_issued_l?: number
}

interface TripStats {
  total?: number
  total_vs_prev?: number
  in_progress?: number
  on_review?: number
  closed?: number
  overdue?: number
  created?: number
  tech_inspect?: number
  med_inspect?: number
}

interface DriverRank {
  driver_user_id: number
  driver_name?: string
  trips_count: number
  total_mileage_km: number
}

// ─── State ───────────────────────────────────────────────────────────────────
const loading = ref(false)
const items = ref<WaybillRow[]>([])
const stats = ref<TripStats>({})
const activeFilter = ref('all')
const search = ref('')
const tablePage = ref(1)
const tableItemsPerPage = ref(25)
const downloadingId = ref<number | null>(null)

const headers = [
  { title: '№ листа',     key: 'number',    sortable: true },
  { title: 'Дата',        key: 'date_start', sortable: true },
  { title: 'Водитель',    key: 'driver',    sortable: false },
  { title: 'Транспорт',   key: 'vehicle',   sortable: false },
  { title: 'Маршрут',     key: 'route',     sortable: false },
  { title: 'Статус',      key: 'status',    sortable: true },
  { title: 'Пробег',      key: 'mileage',   sortable: true, align: 'end' as const },
  { title: 'Топливо',     key: 'fuel',      sortable: false, align: 'end' as const },
  { title: '',            key: 'actions',   sortable: false, align: 'end' as const, width: 80 },
]

// ─── Filter options ───────────────────────────────────────────────────────────
const filterOptions = computed(() => [
  { value: 'all',          label: 'Все',           count: items.value.length },
  { value: 'created',      label: 'Создан',        count: items.value.filter(r => r.status === 'created').length },
  { value: 'tech_inspect', label: 'Тех. осмотр',   count: items.value.filter(r => r.status === 'tech_inspect').length },
  { value: 'med_inspect',  label: 'Медосмотр',     count: items.value.filter(r => r.status === 'med_inspect').length },
  { value: 'in_progress',  label: 'В работе',      count: items.value.filter(r => r.status === 'in_progress').length },
  { value: 'on_review',    label: 'На проверке',   count: items.value.filter(r => r.status === 'on_review').length },
  { value: 'closed',       label: 'Закрыт',        count: items.value.filter(r => r.status === 'closed').length },
  { value: 'overdue',      label: 'Просрочен',     count: items.value.filter(r => r.status === 'overdue').length },
])

const filteredRows = computed(() => {
  let rows = items.value
  if (activeFilter.value !== 'all') {
    rows = rows.filter(r => r.status === activeFilter.value)
  }
  if (search.value.trim()) {
    const q = search.value.trim().toLowerCase()
    rows = rows.filter(r =>
      (r.number || '').toLowerCase().includes(q) ||
      (r.driver_name || '').toLowerCase().includes(q) ||
      (r.vehicle_plate || '').toLowerCase().includes(q) ||
      (r.route_from || '').toLowerCase().includes(q) ||
      (r.route_to || '').toLowerCase().includes(q)
    )
  }
  return rows
})

// ─── Card view (table ↔ cards toggle) ────────────────────────────────────────
const {
  mobile,
  viewMode,
  effectiveView,
  page: cardsPage,
  totalPages: cardsTotalPages,
  paged: pagedCards,
} = useCardView({
  storageKey: 'fleet_waybills_view_mode',
  source: () => filteredRows.value,
  search: () => search.value,
  searchFields: (r: WaybillRow) => [r.number, r.driver_name, r.vehicle_plate, r.route_from, r.route_to],
  pageSize: 24,
})

// ─── Chart data aggregated on client ─────────────────────────────────────────
const chartData = computed(() => {
  // Group by day-of-month from date_start
  const byDay: Record<number, { closed: number; review: number; overdue: number }> = {}
  for (const row of items.value) {
    if (!row.date_start) continue
    const d = new Date(row.date_start).getDate()
    if (!byDay[d]) byDay[d] = { closed: 0, review: 0, overdue: 0 }
    if (row.status === 'closed') byDay[d].closed++
    else if (row.status === 'on_review') byDay[d].review++
    else if (row.status === 'overdue') byDay[d].overdue++
    else byDay[d].review++ // in_progress, tech_inspect, med_inspect, created → review bucket
  }
  const days = Object.keys(byDay).map(Number).sort((a, b) => a - b)
  if (days.length === 0) return []
  const maxTotal = Math.max(...days.map(d => byDay[d].closed + byDay[d].review + byDay[d].overdue))
  const MAX_HEIGHT = 160

  return days.map(d => {
    const { closed, review, overdue } = byDay[d]
    const total = closed + review + overdue
    const totalPx = maxTotal > 0 ? Math.max(4, Math.round((total / maxTotal) * MAX_HEIGHT)) : 4
    return {
      day: d,
      closed, review, overdue, total,
      totalPx,
      closedPct:  total > 0 ? Math.round((closed  / total) * 100) : 0,
      reviewPct:  total > 0 ? Math.round((review  / total) * 100) : 0,
      overduePct: total > 0 ? Math.round((overdue / total) * 100) : 0,
    }
  })
})

// ─── Top 5 drivers ───────────────────────────────────────────────────────────
const topDrivers = computed<DriverRank[]>(() => {
  const map: Record<number, DriverRank> = {}
  for (const row of items.value) {
    if (!row.actual_mileage_km) continue
    const uid = (row as any).driver_user_id as number | undefined
    if (!uid) continue
    if (!map[uid]) map[uid] = { driver_user_id: uid, driver_name: row.driver_name, trips_count: 0, total_mileage_km: 0 }
    map[uid].trips_count++
    map[uid].total_mileage_km += row.actual_mileage_km
  }
  return Object.values(map)
    .sort((a, b) => b.total_mileage_km - a.total_mileage_km)
    .slice(0, 5)
})

// ─── Helpers ──────────────────────────────────────────────────────────────────
function formatDate(iso: string): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })
  } catch { return iso }
}

function statusLabel(s: string): string {
  const map: Record<string, string> = {
    created:      'Создан',
    tech_inspect: 'Тех. осмотр',
    med_inspect:  'Медосмотр',
    in_progress:  'В работе',
    closing:      'Закрытие',
    on_review:    'На проверке',
    closed:       'Закрыт',
    overdue:      'Просрочен',
  }
  return map[s] ?? s
}

function statusVariant(s: string): 'ok' | 'warn' | 'alert' | 'info' | 'muted' {
  const map: Record<string, 'ok' | 'warn' | 'alert' | 'info' | 'muted'> = {
    created:      'info',
    tech_inspect: 'warn',
    med_inspect:  'warn',
    in_progress:  'ok',
    closing:      'warn',
    on_review:    'warn',
    closed:       'muted',
    overdue:      'alert',
  }
  return map[s] ?? 'muted'
}

function mileagePct(item: WaybillRow): number {
  if (!item.planned_mileage_km || !item.actual_mileage_km) return 0
  return Math.min(Math.round((item.actual_mileage_km / item.planned_mileage_km) * 100), 100)
}

function mileageFill(item: WaybillRow): string {
  const pct = mileagePct(item)
  if (pct >= 90) return 'var(--ok, #22c997)'
  if (pct >= 50) return 'var(--warn, #f6b34a)'
  return 'var(--muted, #8a93a8)'
}

function openWaybill(item: WaybillRow) {
  router.push(`/fleet/waybills/${item.id}`)
}

async function downloadDocx(id: number, number: string) {
  downloadingId.value = id
  try {
    const token = localStorage.getItem('auth_token')
    const res = await fetch(`/api/trips/${id}/waybill.docx`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `waybill_${number || id}.docx`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    console.error('[waybills] download error', e)
  } finally {
    downloadingId.value = null
  }
}

// ─── Data loading ─────────────────────────────────────────────────────────────
async function loadStats() {
  try {
    const data = await apiFetch<TripStats>('/trips/stats?period=month')
    stats.value = data
  } catch (e) {
    console.warn('[waybills] stats error', e)
  }
}

async function loadItems() {
  loading.value = true
  try {
    const data = await apiFetch<WaybillRow[]>('/trips/')
    items.value = data
  } catch (e) {
    console.error('[waybills] load error', e)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadStats()
  loadItems()
})

watch(search, () => { tablePage.value = 1 })
watch(activeFilter, () => { tablePage.value = 1 })
</script>

<style scoped>
/* ─── CSS vars (light/dark) ─── */
.waybills-list {
  --panel:   var(--v-theme-surface, #141823);
  --line:    rgba(var(--v-border-color), var(--v-border-opacity, 0.12));
  --text:    var(--v-theme-on-surface, #e9edf5);
  --muted:   #8a93a8;
  --accent:  #6aa6ff;
  --ok:      #22c997;
  --warn:    #f6b34a;
  --alert:   #ff5b6a;
  color: var(--text);
}

/* Header */
.wb-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
}
.wb-crumbs {
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 4px;
}
.wb-crumbs a { color: var(--accent); text-decoration: none; }
.wb-crumbs a:hover { text-decoration: underline; }
.wb-crumbs .sep { margin: 0 6px; opacity: 0.5; }
.wb-crumbs .current { color: var(--text); }
.wb-title { font-size: 22px; font-weight: 700; margin: 0; }
.wb-top-actions { display: flex; gap: 8px; }

/* KPI strip */
.wb-kpis {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}
@media (max-width: 1100px) { .wb-kpis { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 700px)  { .wb-kpis { grid-template-columns: 1fr 1fr; } }

/* Filters */
.wb-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
}
.wb-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 20px;
  border: 1px solid var(--line);
  background: transparent;
  color: var(--muted);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
  transition: border-color 0.15s, color 0.15s, background 0.15s;
}
.wb-chip:hover { color: var(--text); }
.wb-chip--active {
  background: rgba(106, 166, 255, 0.12);
  border-color: var(--accent);
  color: var(--accent);
}
.wb-chip-num {
  padding: 1px 7px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.06);
  font-size: 11px;
}
.wb-chip--active .wb-chip-num {
  background: rgba(106, 166, 255, 0.2);
}
.wb-search { flex: 1; min-width: 220px; max-width: 320px; }

/* Table */
.wb-table-wrap {
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid var(--line);
}
.wb-table { font-size: 13px; }

.wb-num {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  font-weight: 700;
  color: var(--accent);
}
.wb-date { color: var(--muted); font-size: 12px; }

.wb-driver { display: flex; align-items: center; gap: 8px; }
.wb-driver-name { font-weight: 600; font-size: 13px; }
.wb-driver-sub  { font-size: 11px; color: var(--muted); }

.wb-veh { display: flex; align-items: center; gap: 10px; }
.wb-veh-icon {
  width: 36px; height: 24px;
  background: rgba(106,166,255,0.08);
  border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.wb-veh-model { font-size: 11px; color: var(--muted); margin-top: 2px; }

.wb-route { display: flex; align-items: center; gap: 4px; font-size: 12px; }

.wb-mileage, .wb-fuel { display: flex; align-items: center; gap: 6px; justify-content: flex-end; }
.wb-mileage-bar, .wb-fuel-bar {
  width: 48px; height: 4px;
  background: rgba(255,255,255,0.08);
  border-radius: 3px;
  overflow: hidden;
}
.wb-mileage-fill, .wb-fuel-fill { height: 100%; border-radius: 3px; transition: width 0.3s; }
.wb-fuel-fill { background: var(--warn); }

.wb-metric { font-family: 'JetBrains Mono', monospace; font-size: 13px; font-weight: 600; }
.wb-unit   { font-size: 11px; color: var(--muted); font-weight: 400; margin-left: 2px; }

.wb-actions { display: flex; gap: 4px; justify-content: flex-end; }

.wb-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 40px;
  color: var(--muted);
  font-size: 14px;
}

/* Split panels */
.wb-split {
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: 14px;
  margin-top: 18px;
}
@media (max-width: 900px) { .wb-split { grid-template-columns: 1fr; } }

.wb-panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 16px 18px;
}
.wb-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}
.wb-panel-header h3 { font-size: 14px; font-weight: 600; margin: 0; }

/* Chart */
.wb-chart {
  height: 180px;
  display: flex;
  align-items: flex-end;
  gap: 6px;
  padding-top: 12px;
}
.wb-bar {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}
.wb-bar-stack {
  width: 100%;
  display: flex;
  flex-direction: column-reverse;
  border-radius: 4px 4px 0 0;
  overflow: hidden;
  min-height: 4px;
  background: rgba(255,255,255,0.04);
}
.wb-bar-seg { transition: height 0.3s; }
.wb-bar-seg--closed  { background: var(--ok); }
.wb-bar-seg--review  { background: var(--warn); }
.wb-bar-seg--overdue { background: var(--alert); }
.wb-bar-lbl { font-size: 9px; color: var(--muted); }

.wb-chart-legend {
  display: flex;
  gap: 14px;
  margin-top: 10px;
  font-size: 11px;
  color: var(--muted);
}
.leg-dot {
  width: 9px; height: 9px;
  border-radius: 2px;
  display: inline-block;
  margin-right: 4px;
  vertical-align: middle;
}
.leg-dot--closed  { background: var(--ok); }
.leg-dot--review  { background: var(--warn); }
.leg-dot--overdue { background: var(--alert); }

/* Top drivers */
.wb-top-empty { color: var(--muted); font-size: 13px; padding: 12px 0; }
.wb-drv-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 0;
  border-bottom: 1px solid var(--line);
}
.wb-drv-row:last-child { border-bottom: none; }
.wb-drv-rank { width: 22px; color: var(--muted); font-weight: 700; font-size: 12px; text-align: center; flex-shrink: 0; }
.wb-drv-info { flex: 1; }
.wb-drv-name { font-size: 13px; font-weight: 600; }
.wb-drv-sub  { font-size: 11px; color: var(--muted); }
.wb-drv-km   { font-family: 'JetBrains Mono', monospace; font-size: 13px; font-weight: 700; }

/* Light theme */
.v-theme--light .wb-panel { background: #fff; }
.v-theme--light .wb-chip  { border-color: #d0d5e0; }
</style>
