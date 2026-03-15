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
          :items="allSubsidies.filter((s: SubsidyRow) => s.year === selectedYear)"
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

    <!-- ── Quick subsidy chips ── -->
    <div v-if="yearSubsidies.length > 0" class="subsidy-chips-bar">
      <v-chip
        v-for="s in yearSubsidies" :key="s.id"
        :color="selectedSubsidyIds.includes(s.id) ? 'primary' : undefined"
        :variant="selectedSubsidyIds.includes(s.id) ? 'flat' : 'outlined'"
        size="small"
        class="subsidy-chip"
        @click="toggleSubsidyChip(s.id)"
      >
        {{ s.shortName || s.name }}
      </v-chip>
      <v-chip
        v-if="selectedSubsidyIds.length > 0"
        variant="text" size="small" class="subsidy-chip"
        prepend-icon="mdi-close-circle-outline"
        @click="selectedSubsidyIds = []"
      >Все</v-chip>
    </div>

    <!-- ── Tabs ── -->
    <v-tabs v-model="activeTab" color="primary" class="mb-4">
      <v-tab value="summary">
        <v-icon icon="mdi-view-dashboard" class="mr-2" size="18" />Сводка
      </v-tab>
      <v-tab value="analytics">
        <v-icon icon="mdi-chart-line" class="mr-2" size="18" />Аналитика
      </v-tab>
    </v-tabs>

    <v-window v-model="activeTab">
    <v-window-item value="summary">

    <!-- ── Budget Overflow Alert ── -->
    <div v-if="overrunSubsidies.length > 0" class="budget-overrun-banner">
      <v-icon icon="mdi-alert" size="28" color="white" class="mr-3 flex-shrink-0" />
      <div class="overrun-content">
        <div class="overrun-title">Превышение бюджета субсидий!</div>
        <div v-for="s in overrunSubsidies" :key="s.id" class="overrun-row">
          <strong>{{ s.name }}</strong>:
          бюджет {{ formatCurrency(s.budget) }},
          НМЦК {{ formatCurrency(s.planned) }}
          <span v-if="s.contracted > s.budget">
            · законтрактовано {{ formatCurrency(s.contracted) }}
          </span>
          → <strong>перерасход {{ formatCurrency(Math.max(s.planned, s.contracted) - s.budget) }}</strong>
        </div>
        <div class="overrun-hint">Уменьшите НМЦК закупок или увеличьте размер субсидии</div>
      </div>
    </div>

    <!-- ── KPI Cards ── -->
    <v-row class="kpi-row">
      <v-col cols="6" lg="3" v-for="card in kpiCards" :key="card.key">
        <div class="kpi-card" :class="'kpi-' + card.key" @click="openBreakdown(card.key)">
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
          <apexchart type="radialBar" height="270" :options="radialOptions" :series="[totalUsagePct]" :key="'gauge-' + totalUsagePct" />
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
            <apexchart
              :key="statusPieKey"
              type="pie" height="270"
              :options="statusPieOptions"
              :series="statusPieSeries"
            />
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
            <span class="chart-link ml-auto" style="cursor:pointer" @click="goToOrders">Все →</span>
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
              @click="$router.push(`/orders/${p.id}/edit`)"
            >
              <div class="purchase-num">
                <v-icon icon="mdi-package-variant" size="16" :color="statusColorHex(p.status)" />
              </div>
              <div class="purchase-main">
                <div class="purchase-name">{{ p.subject || p.items?.[0]?.item_name || p.item_name || 'Без названия' }}</div>
                <div class="purchase-meta">
                  {{ p.registry_number || p.order_number || '—' }}
                  <span v-if="p.contractor_name"> · {{ p.contractor_name }}</span>
                </div>
              </div>
              <div class="purchase-right">
                <div class="purchase-amount">{{ formatCurrencyShort(purchaseEffectivePrice(p)) }}</div>
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
            @click="openBreakdown('budget')"
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
            @click="openBreakdown('budget')"
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
              <v-btn icon="mdi-magnify" size="x-small" variant="text" @click.stop="openBreakdown('budget')" />
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

    </v-window-item>

    <v-window-item value="analytics">
      <div v-if="analyticsLoading" class="d-flex justify-center py-12">
        <v-progress-circular indeterminate color="primary" size="48" />
      </div>
      <template v-else-if="analyticsData">
        <!-- KPI row -->
        <v-row class="mb-4">
          <v-col cols="6" md="3">
            <v-card variant="outlined" class="pa-4 text-center">
              <div class="text-h4 font-weight-bold text-error">{{ analyticsData.overdue_count }}</div>
              <div class="text-body-2 text-medium-emphasis mt-1">Просрочено</div>
              <v-icon icon="mdi-alert-circle" color="error" class="mt-1" />
            </v-card>
          </v-col>
          <v-col cols="6" md="3">
            <v-card variant="outlined" class="pa-4 text-center">
              <div class="text-h4 font-weight-bold text-warning">{{ analyticsData.upcoming_deadlines.length }}</div>
              <div class="text-body-2 text-medium-emphasis mt-1">Срок до 30 дней</div>
              <v-icon icon="mdi-clock-alert" color="warning" class="mt-1" />
            </v-card>
          </v-col>
          <v-col cols="6" md="3">
            <v-card variant="outlined" class="pa-4 text-center">
              <div class="text-h4 font-weight-bold text-success">{{ analyticsTotalPaid }}</div>
              <div class="text-body-2 text-medium-emphasis mt-1">Оплачено за год</div>
              <v-icon icon="mdi-cash-check" color="success" class="mt-1" />
            </v-card>
          </v-col>
          <v-col cols="6" md="3">
            <v-card variant="outlined" class="pa-4 text-center">
              <div class="text-h4 font-weight-bold text-primary">{{ analyticsTotalPurchases }}</div>
              <div class="text-body-2 text-medium-emphasis mt-1">Всего закупок</div>
              <v-icon icon="mdi-clipboard-list" color="primary" class="mt-1" />
            </v-card>
          </v-col>
        </v-row>

        <v-row>
          <!-- Purchase funnel -->
          <v-col cols="12" md="6">
            <v-card variant="outlined" class="pa-4">
              <div class="text-subtitle-1 font-weight-bold mb-3">Воронка закупок</div>
              <div v-for="item in analyticsData.funnel" :key="item.status" class="mb-2">
                <div class="d-flex justify-space-between mb-1">
                  <span class="text-body-2">{{ A_STATUS_LABELS[item.status] || item.status }}</span>
                  <span class="text-body-2 font-weight-medium">{{ item.count }}</span>
                </div>
                <v-progress-linear
                  :model-value="analyticsFunnelPct(item.count)"
                  :color="A_STATUS_COLORS[item.status] || 'grey'"
                  rounded height="20" bg-color="grey-lighten-3"
                >
                  <template v-slot:default>
                    <span v-if="item.total" class="text-caption text-white font-weight-bold">
                      {{ formatCurrencyShort(item.total) }}
                    </span>
                  </template>
                </v-progress-linear>
              </div>
            </v-card>
          </v-col>

          <!-- Purchase method distribution -->
          <v-col cols="12" md="3">
            <v-card variant="outlined" class="pa-4" style="height:100%">
              <div class="text-subtitle-1 font-weight-bold mb-3">Способы закупки</div>
              <div v-for="(cnt, method) in analyticsData.method_distribution" :key="method" class="mb-3">
                <div class="d-flex justify-space-between mb-1">
                  <span class="text-body-2">{{ A_METHOD_LABELS[method] || method }}</span>
                  <span class="text-body-2 font-weight-medium">{{ cnt }}</span>
                </div>
                <v-progress-linear
                  :model-value="analyticsTotalPurchases > 0 ? (cnt / analyticsTotalPurchases) * 100 : 0"
                  :color="A_METHOD_COLORS[method] || 'blue-grey'"
                  rounded height="14" bg-color="grey-lighten-3"
                />
              </div>
            </v-card>
          </v-col>

          <!-- Upcoming deadlines -->
          <v-col cols="12" md="3">
            <v-card variant="outlined" class="pa-4" style="height:100%">
              <div class="text-subtitle-1 font-weight-bold mb-3">
                Ближайшие сроки
                <v-chip size="x-small" color="warning" variant="tonal" class="ml-1">{{ analyticsData.upcoming_deadlines.length }}</v-chip>
              </div>
              <div v-if="analyticsData.upcoming_deadlines.length === 0" class="text-caption text-medium-emphasis">
                Нет сроков в ближайшие 30 дней
              </div>
              <div v-for="d in analyticsData.upcoming_deadlines" :key="d.id" class="analytics-deadline-item">
                <div class="d-flex align-center justify-space-between">
                  <router-link :to="`/orders/${d.id}`" class="text-body-2 analytics-deadline-link">
                    {{ d.name || `Закупка #${d.purchase_number || d.id}` }}
                  </router-link>
                  <v-chip :color="analyticsDeadlineColor(d.execution_term)" size="x-small" variant="tonal">
                    {{ analyticsFormatDate(d.execution_term) }}
                  </v-chip>
                </div>
              </div>
            </v-card>
          </v-col>
        </v-row>

        <!-- Plan vs Fact -->
        <v-row class="mt-4">
          <v-col cols="12">
            <v-card variant="outlined" class="pa-4">
              <div class="text-subtitle-1 font-weight-bold mb-3">План / Факт по субсидиям</div>
              <v-table density="compact">
                <thead>
                  <tr>
                    <th>Субсидия</th>
                    <th class="text-right">НМЦК (план)</th>
                    <th class="text-right">Законтрактовано</th>
                    <th class="text-right">Оплачено</th>
                    <th>Исполнение</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="pf in analyticsData.plan_fact" :key="pf.subsidy">
                    <td class="text-body-2">{{ pf.subsidy }}</td>
                    <td class="text-right text-body-2">{{ formatCurrencyShort(pf.plan) }}</td>
                    <td class="text-right text-body-2">{{ formatCurrencyShort(pf.contracted) }}</td>
                    <td class="text-right text-body-2 text-success">{{ formatCurrencyShort(pf.paid) }}</td>
                    <td style="min-width:150px">
                      <v-progress-linear
                        v-if="pf.plan > 0"
                        :model-value="Math.min((pf.contracted / pf.plan) * 100, 100)"
                        color="blue" height="12" rounded bg-color="grey-lighten-3"
                        :title="`Законтрактовано: ${Math.round((pf.contracted / pf.plan)*100)}%`"
                      />
                    </td>
                  </tr>
                  <tr v-if="analyticsData.plan_fact.length === 0">
                    <td colspan="5" class="text-center text-medium-emphasis text-caption pa-4">Нет данных</td>
                  </tr>
                </tbody>
              </v-table>
            </v-card>
          </v-col>
        </v-row>

        <!-- Monthly paid + Top contractors -->
        <v-row class="mt-4">
          <v-col cols="12" md="7">
            <v-card variant="outlined" class="pa-4">
              <div class="text-subtitle-1 font-weight-bold mb-3">Ежемесячные оплаты</div>
              <div v-if="analyticsData.monthly_payments.length === 0" class="text-caption text-medium-emphasis text-center py-4">
                Нет данных об оплатах
              </div>
              <div v-else class="analytics-monthly-chart">
                <div v-for="m in analyticsData.monthly_payments" :key="`${m.year}-${m.month}`" class="analytics-bar-col">
                  <div class="analytics-bar-label">{{ formatCurrencyShort(m.total) }}</div>
                  <div class="analytics-bar-wrap">
                    <div class="analytics-bar-fill" :style="{ height: analyticsBarHeight(m.total) + '%' }" />
                  </div>
                  <div class="analytics-bar-x">{{ A_MONTH_NAMES[m.month - 1].slice(0,3) }}<br/>{{ m.year }}</div>
                </div>
              </div>
            </v-card>
          </v-col>

          <v-col cols="12" md="5">
            <v-card variant="outlined" class="pa-4">
              <div class="text-subtitle-1 font-weight-bold mb-3">Топ контрагентов по сумме</div>
              <div v-for="(c, i) in analyticsData.top_contractors" :key="c.name" class="mb-2">
                <div class="d-flex justify-space-between mb-1">
                  <span class="text-body-2 text-truncate" style="max-width:200px" :title="c.name">
                    {{ i + 1 }}. {{ c.name }}
                  </span>
                  <span class="text-body-2 font-weight-medium ml-2 flex-shrink-0">{{ formatCurrencyShort(c.total) }}</span>
                </div>
                <v-progress-linear
                  :model-value="analyticsTopPct(c.total)"
                  color="indigo" rounded height="10" bg-color="grey-lighten-3"
                />
              </div>
              <div v-if="analyticsData.top_contractors.length === 0" class="text-caption text-medium-emphasis text-center py-4">
                Нет данных
              </div>
            </v-card>
          </v-col>
        </v-row>
      </template>
    </v-window-item>
    </v-window>

    <BudgetDrillDownDialog v-model="showBreakdownDialog" :subsidies="filteredSubsidies" :metric="breakdownMetric" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useTheme } from 'vuetify'
import BudgetDrillDownDialog from '@/components/BudgetDrillDownDialog.vue'
import { apiFetch } from '@/api'
import { useGlobalSubsidy } from '@/composables/useGlobalSubsidy'

const { globalSubsidyId } = useGlobalSubsidy()

const theme = useTheme()
const router = useRouter()
const route = useRoute()
const loading = ref(false)
const loadingPurchases = ref(false)
const selectedYear = ref(new Date().getFullYear())
const selectedSubsidyIds = ref<number[]>([])
const showBreakdownDialog = ref(false)
const activeTab = ref((route.query.tab as string) || 'summary')

// ── Data ──────────────────────────────────────────
interface SubsidyRow {
  id: number; name: string; shortName: string; description: string; year: number
  budget: number; contracted: number; paid: number; planned: number
}

const allSubsidies    = ref<SubsidyRow[]>([])
const allPurchases    = ref<any[]>([])
const statusCounts    = ref<Record<string, number>>({})
const breakdownMetric = ref('budget')

// Dark mode aware colors for ApexCharts
const isDark = computed(() => theme.global.name.value === 'dark')
const chartText = computed(() => isDark.value ? '#CBD5E1' : '#374151')
const chartMuted = computed(() => isDark.value ? '#94A3B8' : '#6B7280')
const chartGrid = computed(() => isDark.value ? 'rgba(255,255,255,0.08)' : '#E2E8F0')
const chartTrack = computed(() => isDark.value ? '#334155' : '#E2E8F0')

// ── Derived ──────────────────────────────────────
const availableYears = computed(() =>
  [...new Set(allSubsidies.value.map(s => s.year))].sort((a, b) => b - a)
)

const yearSubsidies = computed((): SubsidyRow[] =>
  allSubsidies.value.filter((s: SubsidyRow) => s.year === selectedYear.value)
)

// Sync: global → local
watch(globalSubsidyId, (id: number | null) => {
  if (id !== null) selectedSubsidyIds.value = [id]
  else selectedSubsidyIds.value = []
}, { immediate: true })

// Sync: local → global (only single selection)
watch(selectedSubsidyIds, (ids: number[]) => {
  if (ids.length === 1) globalSubsidyId.value = ids[0]
  else if (ids.length === 0) globalSubsidyId.value = null
})

function toggleSubsidyChip(id: number) {
  const idx = selectedSubsidyIds.value.indexOf(id)
  if (idx >= 0) {
    selectedSubsidyIds.value = selectedSubsidyIds.value.filter((x: number) => x !== id)
  } else {
    selectedSubsidyIds.value = [...selectedSubsidyIds.value, id]
  }
}

const filteredSubsidies = computed(() => {
  let res = allSubsidies.value.filter(s => s.year === selectedYear.value)
  if (selectedSubsidyIds.value.length > 0)
    res = res.filter(s => selectedSubsidyIds.value.includes(s.id))
  return res
})

const filteredSubsidyStats = computed(() => filteredSubsidies.value)

// Recent purchases filtered to selected subsidies
const recentPurchases = computed(() => {
  const subsidyIds = filteredSubsidies.value.map(s => s.id)
  return allPurchases.value
    .filter(p => subsidyIds.length === 0 || subsidyIds.includes(p.subsidy_id))
    .slice(0, 8)
})

const totalBudget     = computed(() => filteredSubsidies.value.reduce((s, x) => s + x.budget, 0))
const totalContracted = computed(() => filteredSubsidies.value.reduce((s, x) => s + x.contracted, 0))
const totalPaid       = computed(() => filteredSubsidies.value.reduce((s, x) => s + x.paid, 0))
const totalPlanned    = computed(() => filteredSubsidies.value.reduce((s, x) => s + x.planned, 0))
const totalRemaining  = computed(() => totalBudget.value - totalPaid.value)
const totalUsagePct   = computed(() => pct(totalPaid.value, totalBudget.value))

const overrunSubsidies = computed(() =>
  filteredSubsidies.value.filter(s => s.planned > s.budget || s.contracted > s.budget)
)

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
  legend: { position: 'bottom', fontSize: '12px', labels: { colors: chartText.value } },
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
            color: chartMuted.value,
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
      track: { background: chartTrack.value, strokeWidth: '100%' },
      dataLabels: {
        name: {
          show: true, offsetY: -10, color: chartMuted.value,
          fontSize: '13px', fontWeight: '400'
        },
        value: {
          show: true, color: chartText.value,
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
  planned: 'Планируется', confirmed: 'Подтверждено',
  in_progress: 'Ведётся работа',
  contracted: 'Договор', delivered: 'Поставлено', paid: 'Оплачено'
}

// Status counts filtered by selected subsidies
const filteredStatusCounts = computed(() => {
  const subsidyIds = filteredSubsidies.value.map(s => s.id)
  const counts: Record<string, number> = {}
  for (const p of allPurchases.value) {
    if (subsidyIds.length > 0 && !subsidyIds.includes(p.subsidy_id)) continue
    counts[p.status] = (counts[p.status] || 0) + 1
  }
  return counts
})

const STATUS_COLORS: Record<string, string> = {
  planned: '#94A3B8', confirmed: '#3B82F6', in_progress: '#14B8A6',
  contracted: '#6366F1', delivered: '#8B5CF6', paid: '#22C55E',
}

const statusPieReady = computed(() =>
  Object.keys(filteredStatusCounts.value).length > 0 &&
  Object.values(filteredStatusCounts.value).some(v => v > 0)
)

// Sorted entries so chart is stable
const statusPieEntries = computed(() => {
  const ORDER = ['planned', 'confirmed', 'in_progress', 'contracted', 'delivered', 'paid']
  return Object.entries(filteredStatusCounts.value)
    .filter(([, v]) => v > 0)
    .sort((a, b) => ORDER.indexOf(a[0]) - ORDER.indexOf(b[0]))
})

const statusPieSeries = computed(() => statusPieEntries.value.map(([, v]) => v))
const statusPieLabels = computed(() => statusPieEntries.value.map(([k]) => STATUS_LABELS[k] || k))
const statusPieColors = computed(() => statusPieEntries.value.map(([k]) => STATUS_COLORS[k] || '#94A3B8'))
const statusPieKey    = computed(() => statusPieEntries.value.map(e => e[0]).join('-'))

const statusPieOptions = computed(() => ({
  chart: { type: 'pie', background: 'transparent', toolbar: { show: false }, animations: { speed: 400 } },
  colors: statusPieColors.value,
  labels: statusPieLabels.value,
  legend: { position: 'bottom', fontSize: '12px', labels: { colors: chartText.value } },
  dataLabels: { enabled: true, style: { fontSize: '11px', colors: ['#fff'] }, dropShadow: { enabled: false } },
  tooltip: { y: { formatter: (v: number) => `${v} шт.` } },
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
    style: { fontSize: '10px', colors: [chartText.value] },
    formatter: (val: number) => formatCurrencyShort(val),
    offsetX: 5
  },
  xaxis: {
    categories: filteredSubsidyStats.value.map(s => truncate(s.name, 28)),
    labels: {
      style: { colors: chartMuted.value, fontSize: '11px' },
      formatter: (val: number) => formatCurrencyShort(val)
    }
  },
  yaxis: { labels: { style: { colors: chartText.value, fontSize: '11px' } } },
  legend: {
    show: true, position: 'top',
    fontSize: '12px', labels: { colors: chartText.value }
  },
  grid: { borderColor: chartGrid.value },
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
      budget: s.calculated_budget || s.feo_budget_total || s.budget,
      contracted: s.total_confirmed,
      paid: s.total_paid,
      planned: s.total_planned,
    }))

    statusCounts.value = chartsData.status_counts

    // Store all purchases for filtering
    allPurchases.value = purchasesData

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

function openBreakdown(metric = 'budget') {
  breakdownMetric.value = metric
  showBreakdownDialog.value = true
}

function goToOrders() {
  const ids = selectedSubsidyIds.value
  if (ids.length === 1) {
    router.push(`/orders?subsidy_id=${ids[0]}`)
  } else {
    router.push('/orders')
  }
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

function purchaseEffectivePrice(p: any): number {
  const status = p.status
  if (status === 'paid') return parseFloat(p.payment_amount || 0)
  if (status === 'delivered') return parseFloat(p.acceptance_doc_amount || 0)
  if (status === 'contracted') {
    return p.purchase_method === 'single'
      ? parseFloat(p.contract_price || 0)
      : parseFloat(p.delivery_payment_amount || 0)
  }
  return parseFloat(p.total_nmck || p.planned_total_price || 0)
}

function statusLabel(s: string): string {
  return STATUS_LABELS[s] || s
}

function statusColor(s: string): string {
  const map: Record<string, string> = {
    planned: 'grey', confirmed: 'primary', in_progress: 'teal',
    contracted: 'indigo', delivered: 'deep-purple', paid: 'success'
  }
  return map[s] || 'grey'
}

function statusColorHex(s: string): string {
  const map: Record<string, string> = {
    planned: '#94A3B8', confirmed: '#3B82F6', in_progress: '#14B8A6',
    contracted: '#6366F1', delivered: '#8B5CF6', paid: '#22C55E'
  }
  return map[s] || '#94A3B8'
}

// ── Analytics Tab ─────────────────────────────────
interface AnalyticsData {
  funnel: { status: string; count: number; total: number }[]
  monthly_payments: { year: number; month: number; total: number }[]
  top_contractors: { name: string; count: number; total: number }[]
  upcoming_deliveries: { count: number; total: number }
  economy: number
  overdue_count: number
  upcoming_deadlines: { id: number; name: string; purchase_number?: number; execution_term: string; status: string }[]
  method_distribution: Record<string, number>
  plan_fact: { subsidy: string; plan: number; contracted: number; paid: number }[]
}

const analyticsData = ref<AnalyticsData | null>(null)
const analyticsLoading = ref(false)

const A_STATUS_LABELS: Record<string, string> = {
  planned: 'Планирование', confirmed: 'Подтверждена', in_progress: 'В работе',
  contracted: 'Законтрактована', delivered: 'Поставлена', paid: 'Оплачена',
}
const A_STATUS_COLORS: Record<string, string> = {
  planned: 'orange', confirmed: 'blue', in_progress: 'teal',
  contracted: 'indigo', delivered: 'deep-purple', paid: 'green',
}
const A_METHOD_LABELS: Record<string, string> = {
  single: 'Единственный исполнитель', competitive: 'Конкурсная процедура',
  quote_request: 'Запрос котировок', unknown: 'Не указано',
}
const A_METHOD_COLORS: Record<string, string> = {
  single: 'blue', competitive: 'teal', quote_request: 'purple', unknown: 'grey',
}
const A_MONTH_NAMES = ['Янв','Фев','Мар','Апр','Май','Июн','Июл','Авг','Сен','Окт','Ноя','Дек']

const analyticsTotalPurchases = computed(() =>
  analyticsData.value ? analyticsData.value.funnel.reduce((s, i) => s + i.count, 0) : 0
)
const analyticsTotalPaid = computed(() => {
  if (!analyticsData.value) return '—'
  const total = analyticsData.value.monthly_payments.reduce((s, i) => s + i.total, 0)
  return formatCurrencyShort(total)
})
const analyticsMaxFunnel = computed(() =>
  analyticsData.value ? Math.max(...analyticsData.value.funnel.map(i => i.count), 1) : 1
)
const analyticsFunnelPct = (count: number) => (count / analyticsMaxFunnel.value) * 100
const analyticsMaxContractor = computed(() =>
  analyticsData.value?.top_contractors?.length ? analyticsData.value.top_contractors[0].total : 1
)
const analyticsTopPct = (total: number) => (total / analyticsMaxContractor.value) * 100
const analyticsMaxMonthly = computed(() =>
  analyticsData.value?.monthly_payments?.length ? Math.max(...analyticsData.value.monthly_payments.map(m => m.total)) : 1
)
const analyticsBarHeight = (total: number) => Math.max((total / analyticsMaxMonthly.value) * 100, 4)

function analyticsFormatDate(d: string): string {
  if (!d) return ''
  const [y, m, day] = d.split('-')
  return `${day}.${m}.${y}`
}
function analyticsDeadlineColor(d: string): string {
  const diff = (new Date(d).getTime() - Date.now()) / 86400000
  if (diff <= 7) return 'error'
  if (diff <= 14) return 'warning'
  return 'success'
}

async function loadAnalytics() {
  analyticsLoading.value = true
  try {
    analyticsData.value = await apiFetch<AnalyticsData>('/dashboard/analytics')
  } finally {
    analyticsLoading.value = false
  }
}

// Load analytics on tab switch (lazy)
watch(activeTab, (tab) => {
  if (tab === 'analytics' && !analyticsData.value) {
    loadAnalytics()
  }
})

onMounted(() => {
  loadAll()
  if (activeTab.value === 'analytics') {
    loadAnalytics()
  }
})
</script>

<style scoped>
/* ── Budget Overrun Banner ── */
.budget-overrun-banner {
  display: flex;
  align-items: flex-start;
  background: linear-gradient(135deg, #EF4444, #DC2626);
  color: white;
  border-radius: 12px;
  padding: 20px 24px;
  margin-bottom: 20px;
  box-shadow: 0 4px 20px rgba(239,68,68,0.4);
  animation: pulse-border 2s infinite;
}
@keyframes pulse-border {
  0%, 100% { box-shadow: 0 4px 20px rgba(239,68,68,0.4); }
  50%       { box-shadow: 0 4px 32px rgba(239,68,68,0.7); }
}
.overrun-content { flex: 1; }
.overrun-title { font-size: 18px; font-weight: 700; margin-bottom: 8px; }
.overrun-row { font-size: 14px; margin-bottom: 4px; line-height: 1.5; opacity: 0.95; }
.overrun-hint { font-size: 12px; opacity: 0.8; margin-top: 8px; font-style: italic; }

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
  color: var(--crm-text);
  line-height: 1.2;
}
.dash-subtitle {
  font-size: 13px;
  color: var(--crm-text-muted);
  margin-top: 2px;
}
.dash-header-right {
  display: flex;
  align-items: center;
}

/* ── Subsidy quick chips ── */
.subsidy-chips-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 12px;
  padding: 0 2px;
}
.subsidy-chip {
  font-size: 12px;
  letter-spacing: 0;
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
  border: 1px solid var(--crm-border);
  background: var(--crm-surface);
  box-shadow: 0 1px 4px var(--crm-shadow);
}
.kpi-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px var(--crm-shadow-hover);
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

.kpi-budget .kpi-icon-box  { background: var(--crm-kpi-bg-blue); color: #3B82F6; }
.kpi-contracted .kpi-icon-box { background: var(--crm-kpi-bg-sky); color: #0284C7; }
.kpi-paid .kpi-icon-box    { background: var(--crm-kpi-bg-green); color: #22C55E; }
.kpi-remaining .kpi-icon-box { background: var(--crm-kpi-bg-amber); color: #F59E0B; }

.kpi-budget { border-top: 3px solid #3B82F6; }
.kpi-contracted { border-top: 3px solid #0284C7; }
.kpi-paid { border-top: 3px solid #22C55E; }
.kpi-remaining { border-top: 3px solid #F59E0B; }

.kpi-body { flex: 1; min-width: 0; }
.kpi-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--crm-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.kpi-label {
  font-size: 12px;
  color: var(--crm-text-muted);
  margin-top: 2px;
}
.kpi-badge {
  font-size: 11px;
  font-weight: 600;
  color: var(--crm-text-muted);
  background: var(--crm-surface-hover);
  padding: 2px 8px;
  border-radius: 20px;
  white-space: nowrap;
}

/* ── Chart Cards ── */
.chart-row { margin-bottom: 4px; }

.chart-card {
  background: var(--crm-surface);
  border-radius: 12px;
  border: 1px solid var(--crm-border);
  box-shadow: 0 1px 4px var(--crm-shadow);
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
  color: var(--crm-text-secondary);
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
  color: var(--crm-text-faint);
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
  border-bottom: 1px solid var(--crm-border);
  cursor: pointer;
  transition: background 0.12s;
  border-radius: 6px;
}
.purchase-row:last-child { border-bottom: none; }
.purchase-row:hover { background: var(--crm-surface-alt); }
.purchase-num { padding-top: 2px; }
.purchase-main { flex: 1; min-width: 0; }
.purchase-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--crm-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.purchase-meta {
  font-size: 11px;
  color: var(--crm-text-faint);
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
  color: var(--crm-text-secondary);
  white-space: nowrap;
}

/* ── Summary Table ── */
.table-card { margin-bottom: 20px; }

.dash-table thead th {
  font-size: 12px !important;
  font-weight: 600 !important;
  color: var(--crm-text-muted) !important;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  background: var(--crm-table-header);
  white-space: nowrap;
  padding: 10px 12px !important;
}
.dash-table tbody td { padding: 10px 12px !important; }

.table-row-hover:hover td { background: var(--crm-surface-alt); }

.total-row td {
  background: var(--crm-table-stripe) !important;
  font-weight: 600;
  font-size: 13px;
}

/* ── Analytics Tab ── */
.analytics-deadline-item { padding: 6px 0; border-bottom: 1px solid var(--crm-border); }
.analytics-deadline-item:last-child { border-bottom: none; }
.analytics-deadline-link { text-decoration: none; color: inherit; }
.analytics-deadline-link:hover { text-decoration: underline; }
.analytics-monthly-chart {
  display: flex; align-items: flex-end; gap: 6px;
  height: 160px; padding: 0 4px;
}
.analytics-bar-col {
  flex: 1; display: flex; flex-direction: column; align-items: center;
}
.analytics-bar-label {
  font-size: 9px; color: var(--crm-text-muted); text-align: center; min-height: 24px;
  display: flex; align-items: flex-end; justify-content: center; margin-bottom: 2px;
  transform: rotate(-30deg); transform-origin: bottom right;
}
.analytics-bar-wrap {
  flex: 1; width: 100%; display: flex; align-items: flex-end;
  min-height: 100px;
}
.analytics-bar-fill {
  width: 100%; background: linear-gradient(180deg, #6366f1 0%, #4338ca 100%);
  border-radius: 4px 4px 0 0; min-height: 4px;
  transition: height 0.5s ease;
}
.analytics-bar-x { font-size: 9px; text-align: center; color: var(--crm-text-faint); margin-top: 4px; line-height: 1.2; }
</style>
