<template>
  <div class="crm-dashboard">

    <!-- ── Header ── -->
    <div class="dash-header">
      <div class="dash-header-left">
        <v-icon icon="mdi-view-dashboard-outline" size="34" color="#3B82F6" class="mr-3" />
        <div>
          <div class="dash-title">Дашборд</div>
          <div class="dash-subtitle">ВСКС · Управление субсидиями · {{ selectedYear }}</div>
        </div>
      </div>
      <div class="dash-header-right">
        <v-chip-group v-model="selectedYear" mandatory class="year-chips">
          <v-chip
            v-for="year in availableYears" :key="year" :value="year"
            filter variant="elevated" color="primary" size="small"
          >{{ year }}</v-chip>
        </v-chip-group>
        <v-select
          v-model="selectedSubsidyIds"
          :items="allSubsidies.filter(s => s.year === selectedYear)"
          item-title="name" item-value="id"
          label="Субсидии"
          variant="outlined" multiple chips clearable density="compact"
          style="min-width: 220px; max-width: 340px;"
          hide-details class="ml-3"
        />
        <v-btn
          icon="mdi-refresh" variant="tonal" color="primary"
          :loading="loading" @click="loadAll" size="small" class="ml-3"
        />
      </div>
    </div>

    <!-- ── KPI Cards ── -->
    <v-row class="kpi-row">
      <v-col cols="6" lg="3" v-for="card in kpiCards" :key="card.key">
        <div class="kpi-card" :class="'kpi-' + card.key" @click="openBreakdown">
          <div class="kpi-icon-box">
            <v-icon :icon="card.icon" size="26" />
          </div>
          <div class="kpi-body">
            <div class="kpi-value">{{ formatCurrencyShort(card.value) }}</div>
            <div class="kpi-label">{{ card.label }}</div>
          </div>
          <div class="kpi-badge" v-if="card.badge">{{ card.badge }}</div>
        </div>
      </v-col>
    </v-row>

    <!-- ── Charts Row 1: Donut + Radial + Pie ── -->
    <v-row class="chart-row">
      <!-- Budget Donut -->
      <v-col cols="12" md="4">
        <div class="chart-card">
          <div class="chart-card-header">
            <v-icon icon="mdi-chart-donut" size="18" color="#3B82F6" class="mr-2" />
            <span class="chart-card-title">Структура бюджета</span>
          </div>
          <div v-if="donutReady">
            <apexchart type="donut" height="270" :options="donutOptions" :series="donutSeries" />
          </div>
          <div v-else class="chart-empty">
            <v-icon icon="mdi-chart-donut" size="48" color="grey-lighten-2" />
            <div class="text-caption text-medium-emphasis mt-2">Нет данных о бюджете</div>
          </div>
        </div>
      </v-col>

      <!-- Radial Gauge -->
      <v-col cols="12" md="4">
        <div class="chart-card">
          <div class="chart-card-header">
            <v-icon icon="mdi-gauge" size="18" color="#22C55E" class="mr-2" />
            <span class="chart-card-title">Освоение бюджета</span>
          </div>
          <apexchart type="radialBar" height="270" :options="radialOptions" :series="[totalUsagePct]" />
          <div class="radial-footer">
            <span class="text-caption text-medium-emphasis">
              {{ formatCurrencyShort(totalPaid) }} из {{ formatCurrencyShort(totalBudget) }}
            </span>
          </div>
        </div>
      </v-col>

      <!-- Status Pie -->
      <v-col cols="12" md="4">
        <div class="chart-card">
          <div class="chart-card-header">
            <v-icon icon="mdi-chart-pie" size="18" color="#F59E0B" class="mr-2" />
            <span class="chart-card-title">Закупки по статусам</span>
          </div>
          <div v-if="statusPieReady">
            <apexchart type="pie" height="270" :options="statusPieOptions" :series="statusPieSeries" />
          </div>
          <div v-else class="chart-empty">
            <v-icon icon="mdi-cart-outline" size="48" color="grey-lighten-2" />
            <div class="text-caption text-medium-emphasis mt-2">Нет данных о закупках</div>
          </div>
        </div>
      </v-col>
    </v-row>

    <!-- ── Charts Row 2: Bar + Recent Purchases ── -->
    <v-row class="chart-row">
      <!-- Subsidy Bar Chart -->
      <v-col cols="12" md="7">
        <div class="chart-card">
          <div class="chart-card-header">
            <v-icon icon="mdi-chart-bar" size="18" color="#8B5CF6" class="mr-2" />
            <span class="chart-card-title">Субсидии — бюджет и исполнение</span>
          </div>
          <div v-if="barReady">
            <apexchart type="bar" :height="Math.max(220, filteredSubsidyStats.length * 70)" :options="barOptions" :series="barSeries" />
          </div>
          <div v-else class="chart-empty">
            <v-icon icon="mdi-chart-bar" size="48" color="grey-lighten-2" />
            <div class="text-caption text-medium-emphasis mt-2">Нет субсидий за {{ selectedYear }} год</div>
          </div>
        </div>
      </v-col>

      <!-- Recent Purchases -->
      <v-col cols="12" md="5">
        <div class="chart-card" style="height: 100%;">
          <div class="chart-card-header">
            <v-icon icon="mdi-clipboard-list-outline" size="18" color="#14B8A6" class="mr-2" />
            <span class="chart-card-title">Последние закупки</span>
            <router-link to="/orders" class="chart-link ml-auto">Все →</router-link>
          </div>
          <div v-if="loadingPurchases" class="chart-empty">
            <v-progress-circular indeterminate size="32" color="primary" />
          </div>
          <div v-else-if="recentPurchases.length === 0" class="chart-empty">
            <v-icon icon="mdi-cart-off" size="48" color="grey-lighten-2" />
            <div class="text-caption text-medium-emphasis mt-2">Нет закупок</div>
          </div>
          <div v-else class="purchase-list">
            <div
              v-for="p in recentPurchases" :key="p.id"
              class="purchase-row"
              @click="$router.push('/orders')"
            >
              <div class="purchase-num">
                <v-icon icon="mdi-package-variant" size="16" :color="statusColorHex(p.status)" />
              </div>
              <div class="purchase-main">
                <div class="purchase-name">{{ p.item_name || 'Без названия' }}</div>
                <div class="purchase-meta">
                  {{ p.order_number || '—' }}
                  <span v-if="p.contractor_name"> · {{ p.contractor_name }}</span>
                </div>
              </div>
              <div class="purchase-right">
                <div class="purchase-amount">{{ formatCurrencyShort(parseFloat(p.planned_total_price || 0)) }}</div>
                <v-chip size="x-small" :color="statusColor(p.status)" variant="flat" class="mt-1">
                  {{ statusLabel(p.status) }}
                </v-chip>
              </div>
            </div>
          </div>
        </div>
      </v-col>
    </v-row>

    <!-- ── Summary Table ── -->
    <div class="chart-card table-card">
      <div class="chart-card-header">
        <v-icon icon="mdi-table" size="18" color="#1976D2" class="mr-2" />
        <span class="chart-card-title">Детализация субсидий — {{ selectedYear }}</span>
        <div class="ml-auto d-flex align-center" style="gap: 12px;">
          <v-btn
            variant="tonal" color="primary" size="small"
            prepend-icon="mdi-chart-pie"
            @click="showBreakdownDialog = true"
          >
            Аналитика
          </v-btn>
        </div>
      </div>

      <v-table density="compact" class="dash-table mt-3">
        <thead>
          <tr>
            <th>Субсидия</th>
            <th class="text-right">Бюджет</th>
            <th class="text-right">Законтрактовано</th>
            <th class="text-right">Оплачено</th>
            <th class="text-right">Остаток</th>
            <th style="width: 180px;" class="text-center">% освоения</th>
            <th style="width: 60px;"></th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="s in filteredSubsidies" :key="s.id"
            class="table-row-hover"
            @click="showBreakdownDialog = true"
            style="cursor: pointer;"
          >
            <td>
              <div class="font-weight-medium">{{ s.name }}</div>
              <div v-if="s.description" class="text-caption text-medium-emphasis">{{ s.description }}</div>
            </td>
            <td class="text-right font-weight-medium">{{ formatCurrency(s.budget) }}</td>
            <td class="text-right text-info">{{ formatCurrency(s.contracted) }}</td>
            <td class="text-right text-success">{{ formatCurrency(s.paid) }}</td>
            <td class="text-right" :class="s.budget - s.paid >= 0 ? 'text-success' : 'text-error'">
              {{ formatCurrency(s.budget - s.paid) }}
            </td>
            <td>
              <v-progress-linear
                :model-value="pct(s.paid, s.budget)" height="18"
                :color="progressColor(pct(s.paid, s.budget))" rounded
              >
                <template #default>
                  <span class="text-caption font-weight-bold">{{ pct(s.paid, s.budget) }}%</span>
                </template>
              </v-progress-linear>
            </td>
            <td>
              <v-btn icon="mdi-magnify" size="x-small" variant="text" @click.stop="showBreakdownDialog = true" />
            </td>
          </tr>

          <!-- Total row -->
          <tr class="total-row">
            <td><strong>ИТОГО</strong></td>
            <td class="text-right"><strong>{{ formatCurrency(totalBudget) }}</strong></td>
            <td class="text-right text-info"><strong>{{ formatCurrency(totalContracted) }}</strong></td>
            <td class="text-right text-success"><strong>{{ formatCurrency(totalPaid) }}</strong></td>
            <td class="text-right" :class="totalRemaining >= 0 ? 'text-success' : 'text-error'">
              <strong>{{ formatCurrency(totalRemaining) }}</strong>
            </td>
            <td>
              <v-progress-linear
                :model-value="totalUsagePct" height="18"
                :color="progressColor(totalUsagePct)" rounded
              >
                <template #default>
                  <span class="text-caption font-weight-bold">{{ totalUsagePct }}%</span>
                </template>
              </v-progress-linear>
            </td>
            <td></td>
          </tr>
        </tbody>
      </v-table>
    </div>

    <BudgetDrillDownDialog v-model="showBreakdownDialog" :subsidies="filteredSubsidies" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import BudgetDrillDownDialog from '@/components/BudgetDrillDownDialog.vue'
import { apiFetch } from '@/api'

const router = useRouter()
const loading = ref(false)
const loadingPurchases = ref(false)
const selectedYear = ref(new Date().getFullYear())
const selectedSubsidyIds = ref<number[]>([])
const showBreakdownDialog = ref(false)

// ── Data ──────────────────────────────────────────
interface SubsidyRow {
  id: number; name: string; shortName: string; description: string; year: number
  budget: number; contracted: number; paid: number; planned: number
}

const allSubsidies = ref<SubsidyRow[]>([])
const recentPurchases = ref<any[]>([])
const statusCounts = ref<Record<string, number>>({})

// ── Derived ──────────────────────────────────────
const availableYears = computed(() =>
  [...new Set(allSubsidies.value.map(s => s.year))].sort((a, b) => b - a)
)

const filteredSubsidies = computed(() => {
  let res = allSubsidies.value.filter(s => s.year === selectedYear.value)
  if (selectedSubsidyIds.value.length > 0)
    res = res.filter(s => selectedSubsidyIds.value.includes(s.id))
  return res
})

const filteredSubsidyStats = computed(() => filteredSubsidies.value)

const totalBudget     = computed(() => filteredSubsidies.value.reduce((s, x) => s + x.budget, 0))
const totalContracted = computed(() => filteredSubsidies.value.reduce((s, x) => s + x.contracted, 0))
const totalPaid       = computed(() => filteredSubsidies.value.reduce((s, x) => s + x.paid, 0))
const totalPlanned    = computed(() => filteredSubsidies.value.reduce((s, x) => s + x.planned, 0))
const totalRemaining  = computed(() => totalBudget.value - totalPaid.value)
const totalUsagePct   = computed(() => pct(totalPaid.value, totalBudget.value))

// ── KPI Cards ─────────────────────────────────────
const kpiCards = computed(() => [
  {
    key: 'budget', label: 'Общий бюджет', value: totalBudget.value,
    icon: 'mdi-bank-outline',
    badge: `${filteredSubsidies.value.length} субс.`
  },
  {
    key: 'contracted', label: 'Законтрактовано', value: totalContracted.value,
    icon: 'mdi-file-sign',
    badge: `${pct(totalContracted.value, totalBudget.value)}%`
  },
  {
    key: 'paid', label: 'Оплачено', value: totalPaid.value,
    icon: 'mdi-cash-check',
    badge: `${pct(totalPaid.value, totalBudget.value)}%`
  },
  {
    key: 'remaining', label: 'Остаток', value: totalRemaining.value,
    icon: 'mdi-cash-clock',
    badge: `${pct(totalRemaining.value, totalBudget.value)}%`
  },
])

// ── Chart: Donut ──────────────────────────────────
const donutReady = computed(() => totalBudget.value > 0)

const donutSeries = computed(() => {
  const paid = totalPaid.value
  const contracted = Math.max(0, totalContracted.value - paid)
  const planned = Math.max(0, totalPlanned.value - totalContracted.value)
  const free = Math.max(0, totalBudget.value - totalPlanned.value)
  return [paid, contracted, planned, free]
})

const donutOptions = computed(() => ({
  chart: { type: 'donut', background: 'transparent', toolbar: { show: false }, animations: { speed: 500 } },
  colors: ['#22C55E', '#3B82F6', '#F59E0B', '#94A3B8'],
  labels: ['Оплачено', 'Законтрактовано', 'Запланировано', 'Свободно'],
  legend: { position: 'bottom', fontSize: '12px', labels: { colors: '#374151' } },
  dataLabels: { enabled: true, style: { fontSize: '11px', colors: ['#fff'] }, dropShadow: { enabled: false } },
  plotOptions: {
    pie: {
      donut: {
        size: '68%',
        labels: {
          show: true,
          total: {
            show: true,
            label: 'Бюджет',
            color: '#6B7280',
            fontSize: '13px',
            formatter: () => formatCurrencyShort(totalBudget.value)
          }
        }
      }
    }
  },
  tooltip: { y: { formatter: (v: number) => formatCurrency(v) } }
}))

// ── Chart: Radial ─────────────────────────────────
const radialOptions = computed(() => ({
  chart: { type: 'radialBar', background: 'transparent', toolbar: { show: false } },
  colors: [totalUsagePct.value >= 90 ? '#EF4444' : totalUsagePct.value >= 70 ? '#F59E0B' : '#22C55E'],
  plotOptions: {
    radialBar: {
      startAngle: -135,
      endAngle: 135,
      hollow: { size: '60%', background: 'transparent' },
      track: { background: '#E2E8F0', strokeWidth: '100%' },
      dataLabels: {
        name: {
          show: true, offsetY: -10, color: '#6B7280',
          fontSize: '13px', fontWeight: '400'
        },
        value: {
          show: true, color: '#111827',
          fontSize: '30px', fontWeight: '700',
          formatter: (val: number) => `${val}%`
        }
      }
    }
  },
  labels: ['Освоение'],
  fill: {
    type: 'gradient',
    gradient: {
      shade: 'light', type: 'horizontal',
      gradientToColors: [totalUsagePct.value >= 90 ? '#B91C1C' : '#3B82F6'],
      stops: [0, 100]
    }
  }
}))

// ── Chart: Status Pie ─────────────────────────────
const STATUS_LABELS: Record<string, string> = {
  planned: 'Планируется', confirmed: 'Подтверждён',
  contracted: 'Подписан', delivered: 'Поставлено', paid: 'Оплачено'
}

const statusPieReady = computed(() =>
  Object.keys(statusCounts.value).length > 0 &&
  Object.values(statusCounts.value).some(v => v > 0)
)

const statusPieSeries = computed(() => Object.values(statusCounts.value))
const statusPieLabels = computed(() =>
  Object.keys(statusCounts.value).map(k => STATUS_LABELS[k] || k)
)

const statusPieOptions = computed(() => ({
  chart: { type: 'pie', background: 'transparent', toolbar: { show: false }, animations: { speed: 500 } },
  colors: ['#94A3B8', '#3B82F6', '#F59E0B', '#8B5CF6', '#22C55E'],
  labels: statusPieLabels.value,
  legend: { position: 'bottom', fontSize: '12px', labels: { colors: '#374151' } },
  dataLabels: { enabled: true, style: { fontSize: '11px', colors: ['#fff'] }, dropShadow: { enabled: false } },
  tooltip: { y: { formatter: (v: number) => `${v} шт.` } }
}))

// ── Chart: Bar ────────────────────────────────────
const barReady = computed(() => filteredSubsidyStats.value.length > 0)

const barSeries = computed(() => [
  { name: 'Бюджет',          data: filteredSubsidyStats.value.map(s => s.budget) },
  { name: 'Законтрактовано', data: filteredSubsidyStats.value.map(s => s.contracted) },
  { name: 'Оплачено',        data: filteredSubsidyStats.value.map(s => s.paid) },
])

const barOptions = computed(() => ({
  chart: {
    type: 'bar', background: 'transparent', toolbar: { show: false },
    animations: { speed: 500 }
  },
  colors: ['#CBD5E1', '#3B82F6', '#22C55E'],
  plotOptions: {
    bar: {
      horizontal: true,
      dataLabels: { position: 'top' },
      barHeight: '60%',
      borderRadius: 3,
      borderRadiusApplication: 'end'
    }
  },
  dataLabels: {
    enabled: true,
    style: { fontSize: '10px', colors: ['#374151'] },
    formatter: (val: number) => formatCurrencyShort(val),
    offsetX: 5
  },
  xaxis: {
    categories: filteredSubsidyStats.value.map(s => truncate(s.name, 28)),
    labels: {
      style: { colors: '#6B7280', fontSize: '11px' },
      formatter: (val: number) => formatCurrencyShort(val)
    }
  },
  yaxis: { labels: { style: { colors: '#374151', fontSize: '11px' } } },
  legend: {
    show: true, position: 'top',
    fontSize: '12px', labels: { colors: '#374151' }
  },
  grid: { borderColor: '#E2E8F0' },
  tooltip: { y: { formatter: (v: number) => formatCurrency(v) } }
}))

// ── Load data ─────────────────────────────────────
async function loadAll() {
  loading.value = true
  loadingPurchases.value = true
  try {
    const [chartsData, purchasesData] = await Promise.all([
      apiFetch<any>('/dashboard/charts'),
      apiFetch<any[]>('/purchases/')
    ])

    // Build subsidy rows from charts endpoint
    allSubsidies.value = chartsData.subsidy_stats.map((s: any) => ({
      id: s.id,
      name: s.name,
      shortName: truncate(s.name, 20),
      description: '',
      year: s.year,
      budget: s.budget,
      contracted: s.total_confirmed,
      paid: s.total_paid,
      planned: s.total_planned,
    }))

    statusCounts.value = chartsData.status_counts

    // Most recent 8 purchases
    recentPurchases.value = purchasesData.slice(0, 8)

    // Set default year to most recent available
    const years = [...new Set(allSubsidies.value.map((s: SubsidyRow) => s.year))].sort((a, b) => b - a)
    if (years.length > 0 && !years.includes(selectedYear.value)) {
      selectedYear.value = years[0]
    }
  } catch (e) {
    console.error('Dashboard load error:', e)
  } finally {
    loading.value = false
    loadingPurchases.value = false
  }
}

function openBreakdown() {
  showBreakdownDialog.value = true
}

// ── Helpers ───────────────────────────────────────
function pct(part: number, total: number): number {
  if (!total) return 0
  return Math.round((part / total) * 100)
}

function progressColor(p: number): string {
  if (p >= 90) return 'error'
  if (p >= 70) return 'warning'
  return 'primary'
}

function formatCurrency(v: number): string {
  return (v || 0).toLocaleString('ru-RU', { maximumFractionDigits: 0 }) + ' ₽'
}

function formatCurrencyShort(v: number): string {
  if (!v) return '0 ₽'
  if (Math.abs(v) >= 1_000_000_000) return (v / 1_000_000_000).toFixed(1) + ' млрд ₽'
  if (Math.abs(v) >= 1_000_000) return (v / 1_000_000).toFixed(1) + ' млн ₽'
  if (Math.abs(v) >= 1_000) return (v / 1_000).toFixed(0) + ' тыс ₽'
  return v.toLocaleString('ru-RU') + ' ₽'
}

function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n) + '…' : s
}

function statusLabel(s: string): string {
  return STATUS_LABELS[s] || s
}

function statusColor(s: string): string {
  const map: Record<string, string> = {
    planned: 'grey', confirmed: 'primary',
    contracted: 'warning', delivered: 'purple', paid: 'success'
  }
  return map[s] || 'grey'
}

function statusColorHex(s: string): string {
  const map: Record<string, string> = {
    planned: '#94A3B8', confirmed: '#3B82F6',
    contracted: '#F59E0B', delivered: '#8B5CF6', paid: '#22C55E'
  }
  return map[s] || '#94A3B8'
}

onMounted(loadAll)
</script>

<style scoped>
/* ── Layout ── */
.crm-dashboard {
  padding: 20px 24px;
  max-width: 1600px;
}

/* ── Header ── */
.dash-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
  flex-wrap: wrap;
  gap: 12px;
}
.dash-header-left {
  display: flex;
  align-items: center;
}
.dash-title {
  font-size: 26px;
  font-weight: 700;
  color: #111827;
  line-height: 1.2;
}
.dash-subtitle {
  font-size: 13px;
  color: #6B7280;
  margin-top: 2px;
}
.dash-header-right {
  display: flex;
  align-items: center;
}

/* ── KPI Cards ── */
.kpi-row { margin-bottom: 4px; }

.kpi-card {
  border-radius: 12px;
  padding: 18px 20px;
  display: flex;
  align-items: center;
  gap: 14px;
  cursor: pointer;
  transition: transform 0.15s, box-shadow 0.15s;
  position: relative;
  overflow: hidden;
  border: 1px solid rgba(0,0,0,0.07);
  background: #fff;
  box-shadow: 0 1px 4px rgba(0,0,0,0.07);
}
.kpi-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(0,0,0,0.12);
}

.kpi-icon-box {
  width: 48px;
  height: 48px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.kpi-budget .kpi-icon-box  { background: #EFF6FF; color: #3B82F6; }
.kpi-contracted .kpi-icon-box { background: #E0F2FE; color: #0284C7; }
.kpi-paid .kpi-icon-box    { background: #F0FDF4; color: #22C55E; }
.kpi-remaining .kpi-icon-box { background: #FFF7ED; color: #F59E0B; }

.kpi-budget { border-top: 3px solid #3B82F6; }
.kpi-contracted { border-top: 3px solid #0284C7; }
.kpi-paid { border-top: 3px solid #22C55E; }
.kpi-remaining { border-top: 3px solid #F59E0B; }

.kpi-body { flex: 1; min-width: 0; }
.kpi-value {
  font-size: 20px;
  font-weight: 700;
  color: #111827;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.kpi-label {
  font-size: 12px;
  color: #6B7280;
  margin-top: 2px;
}
.kpi-badge {
  font-size: 11px;
  font-weight: 600;
  color: #6B7280;
  background: #F3F4F6;
  padding: 2px 8px;
  border-radius: 20px;
  white-space: nowrap;
}

/* ── Chart Cards ── */
.chart-row { margin-bottom: 4px; }

.chart-card {
  background: #fff;
  border-radius: 12px;
  border: 1px solid rgba(0,0,0,0.07);
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  padding: 18px 20px;
  height: 100%;
}

.chart-card-header {
  display: flex;
  align-items: center;
  margin-bottom: 4px;
}
.chart-card-title {
  font-size: 14px;
  font-weight: 600;
  color: #374151;
}
.chart-link {
  font-size: 13px;
  color: #3B82F6;
  text-decoration: none;
  font-weight: 500;
}
.chart-link:hover { text-decoration: underline; }

.chart-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 220px;
  color: #9CA3AF;
}

.radial-footer {
  text-align: center;
  margin-top: -8px;
  padding-bottom: 4px;
}

/* ── Recent Purchases ── */
.purchase-list { margin-top: 4px; }
.purchase-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 4px;
  border-bottom: 1px solid #F3F4F6;
  cursor: pointer;
  transition: background 0.12s;
  border-radius: 6px;
}
.purchase-row:last-child { border-bottom: none; }
.purchase-row:hover { background: #F9FAFB; }
.purchase-num { padding-top: 2px; }
.purchase-main { flex: 1; min-width: 0; }
.purchase-name {
  font-size: 13px;
  font-weight: 500;
  color: #111827;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.purchase-meta {
  font-size: 11px;
  color: #9CA3AF;
  margin-top: 1px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.purchase-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  flex-shrink: 0;
}
.purchase-amount {
  font-size: 12px;
  font-weight: 600;
  color: #374151;
  white-space: nowrap;
}

/* ── Summary Table ── */
.table-card { margin-bottom: 20px; }

.dash-table thead th {
  font-size: 12px !important;
  font-weight: 600 !important;
  color: #6B7280 !important;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  background: #F9FAFB;
  white-space: nowrap;
  padding: 10px 12px !important;
}
.dash-table tbody td { padding: 10px 12px !important; }

.table-row-hover:hover td { background: #F9FAFB; }

.total-row td {
  background: #F3F4F6 !important;
  font-weight: 600;
  font-size: 13px;
}
</style>
