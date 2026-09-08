<template>
  <div class="crm-dashboard">

    <DashboardHeader
      v-model:selected-year="selectedYear"
      v-model:selected-subsidy-ids="selectedSubsidyIds"
      v-model:dashboard-toggle-mode="dashboardToggleMode"
      :available-years="availableYears"
      :all-subsidies="allSubsidies"
      :is-editing="isEditing"
      :mobile="mobile"
      :loading="loading"
      @toggle-editing="toggleEditing"
      @reset-layout="resetLayout"
      @refresh="loadAll"
    />

    <DashboardSubsidyChips
      :year-subsidies="yearSubsidies"
      :selected-subsidy-ids="selectedSubsidyIds"
      @toggle="toggleSubsidyChip"
      @clear="selectedSubsidyIds = []"
    />

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

    <DashboardBanners
      :is-editing="isEditing"
      :overrun-subsidies="overrunSubsidies"
      :subsidies-near-ceiling="subsidiesNearCeiling"
      :format-currency="formatCurrency"
      @toggle-editing="toggleEditing"
    />

    <GridLayout
      :layout="effectiveLayout"
      :col-num="12"
      :row-height="30"
      :is-draggable="isEditing && !mobile"
      :is-resizable="isEditing && !mobile"
      :margin="[12, 12]"
      :vertical-compact="true"
      :use-css-transforms="true"
      @layout-updated="handleLayoutUpdated"
    >
      <!-- ── KPI Cards ── -->
      <GridItem v-bind="effectiveLayout.find(l => l.i === 'kpi')" key="kpi">
        <DashboardGridWidget :editing="isEditing" label="KPI">
          <KpiCardsWidget
            :loading="loading" :mobile="mobile" :kpi-cards="kpiCards"
            :format-currency="formatCurrency" :format-currency-short="formatCurrencyShort"
            @kpi-click="handleKpiClick"
          />
        </DashboardGridWidget>
      </GridItem>

      <!-- ── Donut Chart ── -->
      <GridItem v-bind="effectiveLayout.find(l => l.i === 'donut')" key="donut">
        <DashboardGridWidget :editing="isEditing" label="Структура бюджета">
          <DonutChartWidget
            v-model:donut-view="donutView"
            :donut-ready="donutReady" :donut-options="donutOptions" :donut-series="donutSeries"
            :drill-down-segment="drillDownSegment"
            :breakdown-bar-options="breakdownBarOptions" :breakdown-bar-series="breakdownBarSeries"
            :segment-labels="SEGMENT_LABELS"
          />
        </DashboardGridWidget>
      </GridItem>

      <!-- ── Radial Gauge ── -->
      <GridItem v-bind="effectiveLayout.find(l => l.i === 'radial')" key="radial">
        <DashboardGridWidget :editing="isEditing" label="Освоение">
          <RadialGaugeWidget
            :radial-options="radialOptions" :total-usage-pct="totalUsagePct"
            :total-paid="totalPaid" :total-budget="totalBudget"
            :format-currency-short="formatCurrencyShort"
          />
        </DashboardGridWidget>
      </GridItem>

      <!-- ── Pipeline ── -->
      <GridItem v-bind="effectiveLayout.find(l => l.i === 'pipeline')" key="pipeline">
        <DashboardGridWidget :editing="isEditing" label="Закупки по этапам">
          <PipelineWidget
            :selected-subsidy-ids="selectedSubsidyIds" :all-subsidies="allSubsidies"
            :total-budget="totalBudget" :pipeline-stages="pipelineStages"
            :delivered-not-paid="deliveredNotPaid" :wishes-amount-for-pie="wishesAmountForPie"
            :chart-muted="chartMuted" :format-currency-short="formatCurrencyShort"
            @stage-click="onPipelineClick" @delivered-not-paid-click="onDeliveredNotPaidClick"
          />
        </DashboardGridWidget>
      </GridItem>

      <!-- ── Monthly Contracts ── -->
      <GridItem v-if="!mobile || monthlyContractsRemaining.length > 0" v-bind="effectiveLayout.find(l => l.i === 'monthly')" key="monthly">
        <DashboardGridWidget :editing="isEditing" label="Ежемесячные договоры">
          <MonthlyContractsWidget
            :monthly-contracts-remaining="monthlyContractsRemaining" :total-monthly-remaining="totalMonthlyRemaining"
            :chart-muted="chartMuted" :format-currency-short="formatCurrencyShort"
          />
        </DashboardGridWidget>
      </GridItem>

      <!-- ── Goods/Services Breakdown ── -->
      <GridItem v-if="!mobile || pipelineByType.some(s => s.total > 0)" v-bind="effectiveLayout.find(l => l.i === 'breakdown')" key="breakdown">
        <DashboardGridWidget :editing="isEditing" label="Товары / Услуги">
          <GoodsServicesWidget
            :pipeline-by-type="pipelineByType" :total-budget="totalBudget"
            :format-currency-short="formatCurrencyShort"
          />
        </DashboardGridWidget>
      </GridItem>

      <!-- ── Recent Purchases ── -->
      <GridItem v-bind="effectiveLayout.find(l => l.i === 'purchases')" key="purchases">
        <DashboardGridWidget :editing="isEditing" label="Последние закупки">
          <RecentPurchasesWidget
            :loading-purchases="loadingPurchases" :recent-purchases="recentPurchases"
            :selected-subsidy-ids="selectedSubsidyIds"
            :format-currency-short="formatCurrencyShort"
            :status-color-hex="statusColorHex" :status-color="statusColor" :status-label="statusLabel"
            :purchase-effective-price="purchaseEffectivePrice"
          />
        </DashboardGridWidget>
      </GridItem>

      <!-- ── Summary Table ── -->
      <GridItem v-bind="effectiveLayout.find(l => l.i === 'table')" key="table">
        <DashboardGridWidget :editing="isEditing" label="Детализация субсидий">
          <SummaryTableWidget
            :selected-year="selectedYear" :filtered-subsidies="filteredSubsidies"
            :total-budget="totalBudget" :total-plan-schedule="totalPlanSchedule"
            :total-feo-planned="totalFeoPlanned" :total-ordered="totalOrdered"
            :total-paid="totalPaid" :total-remaining="totalRemaining" :total-usage-pct="totalUsagePct"
            :format-currency="formatCurrency" :pct="pct" :progress-color="progressColor"
            @open-breakdown="openBreakdown"
          />
        </DashboardGridWidget>
      </GridItem>

      <!-- ── Financial Plan ── -->
      <GridItem v-bind="effectiveLayout.find(l => l.i === 'finplan')" key="finplan">
        <DashboardGridWidget :editing="isEditing" label="Финансовый план">
          <FinancialPlanWidget
            v-model:finplan-granularity="finplanGranularity"
            :finplan-no-deadline-count="finplanNoDeadlineCount"
            :finplan-current-month-kpi="finplanCurrentMonthKpi"
            :finplan-series="finplanSeries" :finplan-options="finplanOptions"
            :format-currency-short="formatCurrencyShort"
            @open-drilldown="openFinplanDrilldown" @export-xlsx="exportFinplanXlsx"
          />
        </DashboardGridWidget>
      </GridItem>
    </GridLayout>

    </v-window-item>

    <v-window-item value="analytics">
      <AnalyticsTab
        :analytics-loading="analyticsLoading" :analytics-data="analyticsData"
        :analytics-total-purchases="analyticsTotalPurchases" :analytics-total-paid="analyticsTotalPaid"
        :analytics-funnel-pct="analyticsFunnelPct" :analytics-top-pct="analyticsTopPct"
        :analytics-bar-height="analyticsBarHeight" :analytics-format-date="analyticsFormatDate"
        :analytics-deadline-color="analyticsDeadlineColor" :format-currency-short="formatCurrencyShort"
        :A_STATUS_LABELS="A_STATUS_LABELS" :A_STATUS_COLORS="A_STATUS_COLORS"
        :A_METHOD_LABELS="A_METHOD_LABELS" :A_METHOD_COLORS="A_METHOD_COLORS"
        :A_MONTH_NAMES="A_MONTH_NAMES"
      />
    </v-window-item>
    </v-window>

    <BudgetDrillDownDialog
      v-model="showBreakdownDialog"
      :subsidies="drillDialogSubsidies.length ? drillDialogSubsidies : filteredSubsidies"
      :metric="breakdownMetric"
      @update:modelValue="v => { if (!v) drillDialogSubsidies.value = [] }"
    />

    <!-- FEO-hierarchical drill для pipeline-этапов -->
    <StageFeoDrillDialog
      :visible="stageFeoDrillVisible"
      :title="stageFeoDrillTitle"
      :stage-statuses="stageFeoDrillStatuses"
      :all-purchases="allPurchases"
      :subsidy-ids="filteredSubsidies.map((s: any) => s.id)"
      :subsidies="filteredSubsidies"
      :effective-price="purchaseEffectivePrice"
      :status-label-map="STATUS_LABELS"
      :status-color-map="STATUS_COLORS"
      @close="stageFeoDrillVisible = false"
      @row-click="(id) => { stageFeoDrillVisible = false; $router.push(`/orders/${id}/edit`) }"
    />

    <StatusDrillDialog
      v-model="statusDrillDialog"
      :mobile="mobile"
      :status-drill-status="statusDrillStatus" :status-drill-statuses="statusDrillStatuses"
      :status-drill-purchases="statusDrillPurchases"
      :status-labels="STATUS_LABELS" :status-colors="STATUS_COLORS"
      :format-currency="formatCurrency" :purchase-effective-price="purchaseEffectivePrice"
      @export-xlsx="exportStatusDrillXlsx"
    />

    <DonutDrillDialog
      v-model="drillDownDialog"
      :mobile="mobile" :drill-down-segment="drillDownSegment" :drill-down-rows="drillDownRows"
      :segment-labels="SEGMENT_LABELS" :format-currency="formatCurrency"
    />

    <!-- ── Financial Plan Drill-Down Dialog ── -->
    <FinplanDrilldownDialog
      :mobile="mobile" :finplan-drilldown="finplanDrilldown"
      :finplan-drilldown-title="finplanDrilldownTitle" :finplan-drilldown-total="finplanDrilldownTotal"
      :finplan-drilldown-chip-color="finplanDrilldownChipColor"
      :status-labels-finplan="STATUS_LABELS_FINPLAN" :format-date="formatDate"
      :go-to-order="goToOrder" :patch-is-likely-needed="patchIsLikelyNeeded"
      @export-xlsx="exportFinplanDrilldownXlsx"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useDisplay } from 'vuetify'
import { GridLayout, GridItem } from 'grid-layout-plus'

import BudgetDrillDownDialog from '@/components/BudgetDrillDownDialog.vue'
import StageFeoDrillDialog from '@/components/StageFeoDrillDialog.vue'

import DashboardHeader from '@/components/dashboard/DashboardHeader.vue'
import DashboardSubsidyChips from '@/components/dashboard/DashboardSubsidyChips.vue'
import DashboardBanners from '@/components/dashboard/DashboardBanners.vue'
import DashboardGridWidget from '@/components/dashboard/DashboardGridWidget.vue'
import KpiCardsWidget from '@/components/dashboard/KpiCardsWidget.vue'
import DonutChartWidget from '@/components/dashboard/DonutChartWidget.vue'
import RadialGaugeWidget from '@/components/dashboard/RadialGaugeWidget.vue'
import PipelineWidget from '@/components/dashboard/PipelineWidget.vue'
import MonthlyContractsWidget from '@/components/dashboard/MonthlyContractsWidget.vue'
import GoodsServicesWidget from '@/components/dashboard/GoodsServicesWidget.vue'
import RecentPurchasesWidget from '@/components/dashboard/RecentPurchasesWidget.vue'
import SummaryTableWidget from '@/components/dashboard/SummaryTableWidget.vue'
import FinancialPlanWidget from '@/components/dashboard/FinancialPlanWidget.vue'
import AnalyticsTab from '@/components/dashboard/AnalyticsTab.vue'
import StatusDrillDialog from '@/components/dashboard/StatusDrillDialog.vue'
import DonutDrillDialog from '@/components/dashboard/DonutDrillDialog.vue'
import FinplanDrilldownDialog from '@/components/dashboard/FinplanDrilldownDialog.vue'

import { STATUS_LABELS, STATUS_COLORS } from '@/composables/dashboard/dashboardStatusMaps'
import {
  pct, progressColor, formatCurrency, formatCurrencyShort,
  purchaseEffectivePrice, statusLabel, statusColor, statusColorHex,
} from '@/composables/dashboard/dashboardFormat'
import { useDashboardChartTheme } from '@/composables/dashboard/useDashboardChartTheme'
import { useDashboardFilters } from '@/composables/dashboard/useDashboardFilters'
import { useDashboardData } from '@/composables/dashboard/useDashboardData'
import { useDashboardGridLayout } from '@/composables/dashboard/useDashboardGridLayout'
import { useBudgetDrilldown } from '@/composables/dashboard/useBudgetDrilldown'
import { useDonutWidget, SEGMENT_LABELS } from '@/composables/dashboard/useDonutWidget'
import { usePipelineWidget } from '@/composables/dashboard/usePipelineWidget'
import { useGoodsServicesWidget } from '@/composables/dashboard/useGoodsServicesWidget'
import { useMonthlyContractsWidget } from '@/composables/dashboard/useMonthlyContractsWidget'
import { useAnalyticsTab, A_STATUS_LABELS, A_STATUS_COLORS, A_METHOD_LABELS, A_METHOD_COLORS, A_MONTH_NAMES } from '@/composables/dashboard/useAnalyticsTab'
import { useFinancialPlanWidget, STATUS_LABELS_FINPLAN } from '@/composables/dashboard/useFinancialPlanWidget'

const router = useRouter()
const { mobile } = useDisplay()

// ── Filters (год / субсидии / вкладка) ──────────────
const { selectedYear, selectedSubsidyIds, activeTab, toggleSubsidyChip } = useDashboardFilters()

// ── Ядро данных дашборда ─────────────────────────────
const {
  loading, loadingPurchases,
  allSubsidies, allPurchases, statusCounts, widgetsData, subsidiesNearCeiling,
  availableYears, yearSubsidies, filteredSubsidies, recentPurchases,
  totalBudget, totalContracted, totalPaid, totalPlanned, totalPlanSchedule, totalOrdered,
  totalFeoPlanned, totalRemaining, totalUsagePct,
  overrunSubsidies, effectiveWidgets, kpiCards,
  loadAll,
} = useDashboardData(selectedYear, selectedSubsidyIds)

// ── Тема графиков (dark mode) ────────────────────────
const chartTheme = useDashboardChartTheme()
const { chartMuted } = chartTheme

// ── Диалог разбивки бюджета по субсидиям (общий для Донат-виджета и Сводной таблицы) ──
const { showBreakdownDialog, breakdownMetric, drillDialogSubsidies, openBreakdown } = useBudgetDrilldown()

// ── Донат-график ──────────────────────────────────────
const {
  donutReady, donutSeries, donutOptions,
  drillDownDialog, drillDownSegment, donutView,
  drillDownRows, breakdownBarSeries, breakdownBarOptions,
} = useDonutWidget(
  { totalPaid, totalOrdered, totalPlanSchedule, totalBudget },
  filteredSubsidies,
  chartTheme,
  { showBreakdownDialog, breakdownMetric, drillDialogSubsidies },
)

// ── Радиальный индикатор освоения ────────────────────
const radialOptions = computed(() => ({
  chart: { type: 'radialBar', background: 'transparent', toolbar: { show: false }, theme: { mode: chartTheme.isDark.value ? 'dark' : 'light' } },
  colors: [totalUsagePct.value >= 90 ? '#EF4444' : totalUsagePct.value >= 70 ? '#F59E0B' : '#22C55E'],
  plotOptions: {
    radialBar: {
      startAngle: -135,
      endAngle: 135,
      hollow: { size: '60%', background: 'transparent' },
      track: { background: chartTheme.chartTrack.value, strokeWidth: '100%' },
      dataLabels: {
        name: {
          show: true, offsetY: -10, color: chartTheme.chartMuted.value,
          fontSize: '13px', fontWeight: '400'
        },
        value: {
          show: true, color: chartTheme.chartText.value,
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

// ── Pipeline (закупки по этапам) + его drill-down диалоги ──
const {
  statusDrillDialog, statusDrillStatus, statusDrillStatuses, statusDrillPurchases,
  exportStatusDrillXlsx,
  stageFeoDrillVisible, stageFeoDrillTitle, stageFeoDrillStatuses,
  pipelineStages, deliveredNotPaid, onPipelineClick, onDeliveredNotPaidClick,
  wishesAmountForPie,
} = usePipelineWidget(allPurchases, filteredSubsidies, totalBudget)

// ── Товары / Услуги ───────────────────────────────────
const { pipelineByType } = useGoodsServicesWidget(allPurchases, filteredSubsidies, totalBudget)

// ── Ежемесячные договоры ──────────────────────────────
const { monthlyContractsRemaining, totalMonthlyRemaining } = useMonthlyContractsWidget(allPurchases, filteredSubsidies)

// ── Раскладка сетки виджетов ──────────────────────────
const dashboardToggleMode = ref<'classic' | 'radar'>('classic')
const {
  isEditing, toggleEditing, resetLayout, effectiveLayout, handleLayoutUpdated, setMode,
} = useDashboardGridLayout(
  mobile,
  computed(() => kpiCards.value.length),
  computed(() => monthlyContractsRemaining.value.length),
  computed(() => pipelineByType.value.some(s => s.total > 0)),
  dashboardToggleMode,
)

// ── Вкладка «Аналитика» (ленивая загрузка) ────────────
const {
  analyticsData, analyticsLoading,
  analyticsTotalPurchases, analyticsTotalPaid, analyticsFunnelPct,
  analyticsTopPct, analyticsBarHeight, analyticsFormatDate, analyticsDeadlineColor,
  loadAnalytics,
} = useAnalyticsTab(activeTab, selectedSubsidyIds)

// ── Финансовый план ────────────────────────────────────
const {
  finplanGranularity,
  finplanDrilldown, openFinplanDrilldown, finplanDrilldownTotal, finplanDrilldownTitle, finplanDrilldownChipColor,
  patchIsLikelyNeeded, finplanNoDeadlineCount, finplanCurrentMonthKpi, goToOrder,
  exportFinplanXlsx, exportFinplanDrilldownXlsx, formatDate,
  loadFinplan, finplanSeries, finplanOptions,
} = useFinancialPlanWidget(selectedSubsidyIds, chartTheme)

function handleKpiClick(key: string) {
  if (key === 'budget')            router.push('/subsidies')
  else if (key === 'plan_schedule')    router.push('/orders?status=plan_schedule')
  else if (key === 'work')         router.push('/orders?status=work_in_progress')
  else if (key === 'ordered')      router.push('/orders?status=contracted')
  else if (key === 'contracts')    router.push('/contracts')
  else if (key === 'delivered')    router.push('/orders?status=delivered')
  else if (key === 'delivered_unpaid') router.push('/orders?status=delivered')
  else if (key === 'paid')         router.push('/orders?status=paid')
  else if (key === 'free')         router.push('/subsidies')
  else openBreakdown(key)
}

onMounted(() => {
  setMode('classic')
  loadAll()
  loadFinplan()
  if (activeTab.value === 'analytics') {
    loadAnalytics()
  }
})
</script>

<style>
/* Дашборд разбит на components/dashboard/* + composables/dashboard/* (рефакторинг
   2026-09-08). CSS-классы виджетов (.chart-card, .kpi-*, .pipeline-*, .purchase-*,
   .analytics-*) используются дочерними компонентами, поэтому стиль здесь НЕ scoped
   (иначе scoped-атрибут DashboardView.vue не долетал бы до элементов, отрисованных
   внутри дочерних SFC) — перенесено без изменений содержимого. */
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

/* ── Ceiling Warning Banner (владелец, 2026-08-30) ── */
.ceiling-warning-banner {
  display: flex;
  align-items: flex-start;
  background: linear-gradient(135deg, #F59E0B, #D97706);
  color: white;
  border-radius: 12px;
  padding: 20px 24px;
  margin-bottom: 20px;
  box-shadow: 0 4px 20px rgba(245,158,11,0.4);
}
.ceiling-warning-banner--critical {
  background: linear-gradient(135deg, #EF4444, #DC2626);
  box-shadow: 0 4px 20px rgba(239,68,68,0.4);
  animation: pulse-border 2s infinite;
}
.ceiling-warning-link { color: white; font-weight: 600; text-decoration: underline; margin-left: 6px; }

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
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}
.subsidy-chip:hover {
  transform: translateY(-1px);
  box-shadow: 0 2px 8px var(--crm-shadow);
}

/* ── KPI Cards ── */
.kpi-row { margin-bottom: 4px; }

/* Equal height: все колонки растягиваются на полную высоту строки */
.kpi-row .v-col { display: flex; }

.kpi-card {
  width: 100%;
  min-height: 110px;
  height: 100%;
  border-radius: 12px;
  padding: 18px 20px;
  display: flex;
  align-items: center;
  gap: 14px;
  cursor: pointer;
  transition: transform 0.25s cubic-bezier(0.22, 1, 0.36, 1),
              box-shadow 0.25s cubic-bezier(0.22, 1, 0.36, 1),
              border-color 0.25s ease;
  position: relative;
  overflow: hidden;
  border: 1px solid var(--crm-border);
  background: var(--crm-surface);
  box-shadow: 0 1px 4px var(--crm-shadow);
}
.kpi-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 12px 28px var(--crm-shadow-hover);
  border-color: var(--crm-border-strong);
}
.kpi-card:active {
  transform: translateY(-1px) scale(0.985);
  transition-duration: 0.1s;
}

/* ── Glassmorphism + Glow (Wiza-inspired) ── */
.kpi-card::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  opacity: 0;
  transition: opacity 0.35s ease;
  z-index: -1;
}
.kpi-card:hover::before {
  opacity: 1;
}
.kpi-budget::before            { box-shadow: 0 0 30px rgba(59,130,246,0.15); }
.kpi-plan_schedule::before     { box-shadow: 0 0 30px rgba(245,158,11,0.15); }
.kpi-work::before              { box-shadow: 0 0 30px rgba(99,102,241,0.15); }
.kpi-ordered::before           { box-shadow: 0 0 30px rgba(59,130,246,0.15); }
.kpi-contracts::before         { box-shadow: 0 0 30px rgba(2,132,199,0.15); }
.kpi-delivered::before         { box-shadow: 0 0 30px rgba(20,184,166,0.15); }
.kpi-delivered_unpaid::before  { box-shadow: 0 0 30px rgba(239,68,68,0.15); }
.kpi-paid::before              { box-shadow: 0 0 30px rgba(34,197,94,0.15); }
.kpi-free::before              { box-shadow: 0 0 30px rgba(148,163,184,0.15); }

.kpi-icon-box {
  width: 48px;
  height: 48px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: transform 0.25s cubic-bezier(0.22, 1, 0.36, 1);
}
.kpi-card:hover .kpi-icon-box {
  transform: scale(1.12) rotate(-3deg);
}

.kpi-budget .kpi-icon-box             { background: var(--crm-kpi-bg-blue); color: #3B82F6; }
.kpi-plan_schedule .kpi-icon-box      { background: rgba(245,158,11,0.12); color: #F59E0B; }
.kpi-work .kpi-icon-box               { background: rgba(99,102,241,0.12); color: #6366F1; }
.kpi-ordered .kpi-icon-box            { background: rgba(59,130,246,0.12); color: #3B82F6; }
.kpi-contracts .kpi-icon-box          { background: var(--crm-kpi-bg-sky); color: #0284C7; }
.kpi-delivered .kpi-icon-box          { background: rgba(20,184,166,0.12); color: #14B8A6; }
.kpi-delivered_unpaid .kpi-icon-box   { background: rgba(239,68,68,0.12); color: #EF4444; }
.kpi-contracted .kpi-icon-box         { background: var(--crm-kpi-bg-sky); color: #0284C7; }
.kpi-paid .kpi-icon-box               { background: var(--crm-kpi-bg-green); color: #22C55E; }
.kpi-free .kpi-icon-box               { background: rgba(148,163,184,0.12); color: #94A3B8; }

.kpi-budget           { border-top: 3px solid #3B82F6; }
.kpi-plan_schedule    { border-top: 3px solid #F59E0B; }
.kpi-work             { border-top: 3px solid #6366F1; }
.kpi-ordered          { border-top: 3px solid #3B82F6; }
.kpi-contracts        { border-top: 3px solid #0284C7; }
.kpi-delivered        { border-top: 3px solid #14B8A6; }
.kpi-delivered_unpaid { border-top: 3px solid #EF4444; }
.kpi-contracted       { border-top: 3px solid #0284C7; }
.kpi-paid             { border-top: 3px solid #22C55E; }
.kpi-free             { border-top: 3px solid #94A3B8; }
.kpi-card.kpi-over    { border-top-color: #EF4444; }
.kpi-over .kpi-icon-box { background: rgba(239,68,68,0.12); color: #EF4444; }

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
.kpi-count {
  font-size: 11px;
  color: var(--crm-text-muted);
  margin-top: 2px;
}
.kpi-monthly {
  font-size: 10px;
  color: var(--crm-text-muted);
  margin-top: 3px;
  line-height: 1.3;
  opacity: 0.85;
}
.kpi-badge {
  font-size: 11px;
  font-weight: 600;
  color: var(--crm-text-muted);
  background: var(--crm-surface-hover);
  padding: 2px 8px;
  border-radius: 20px;
  white-space: nowrap;
  transition: all 0.25s ease;
}
.kpi-card:hover .kpi-badge {
  background: var(--crm-border-strong);
  color: var(--crm-text);
}

/* Mobile: вертикальный стек (как в Radar) — иконка сверху, значение на всю ширину карточки */
@media (max-width: 599px) {
  .kpi-card {
    flex-direction: column;
    align-items: flex-start;
    gap: 6px;
    padding: 12px;
  }
  .kpi-icon-box {
    width: 34px;
    height: 34px;
    border-radius: 8px;
  }
  .kpi-icon-box :deep(.v-icon) {
    font-size: 18px !important;
  }
  .kpi-body {
    width: 100%;
  }
  .kpi-value {
    font-size: 15px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .kpi-label {
    font-size: 10px;
    line-height: 1.2;
    white-space: normal;
    margin-top: 1px;
  }
  .kpi-count {
    font-size: 9px;
  }
  .kpi-monthly {
    font-size: 9px;
  }
  .kpi-badge {
    font-size: 9px;
    padding: 1px 6px;
    align-self: flex-start;
  }
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

/* ── Pipeline Chart ── */
.pipeline-wrap { display: flex; flex-direction: column; gap: 10px; padding: 4px 0; }
.pipeline-row {
  display: grid;
  grid-template-columns: 130px 1fr 110px;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  border-radius: 6px;
  padding: 4px 2px;
  transition: background 0.15s;
}
.pipeline-row:hover { background: var(--crm-surface-alt); }
.pipeline-label {
  display: flex; align-items: center; gap: 6px;
  font-size: 12px; color: var(--crm-text); white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis;
}
.pipeline-dot {
  display: inline-block; width: 8px; height: 8px;
  border-radius: 50%; flex-shrink: 0; margin-right: 6px;
}
.pipeline-bar-track {
  height: 10px; background: var(--crm-border); border-radius: 5px; overflow: hidden;
}
.pipeline-bar-fill {
  height: 100%; border-radius: 5px;
  transition: width 0.4s ease;
  min-width: 2px;
}
.pipeline-meta {
  display: flex; align-items: center; justify-content: flex-end; gap: 6px;
}
.pipeline-amount { font-size: 11px; font-weight: 600; color: var(--crm-text); }
.pipeline-pct { font-size: 11px; color: var(--crm-text-muted); min-width: 36px; text-align: right; }
.pipeline-wishes-hint {
  display: flex; align-items: center;
  font-size: 11px; color: #F59E0B;
  border-top: 1px solid var(--crm-border);
  padding-top: 8px; margin-top: 4px;
}
.chart-card--compact { min-height: unset; }

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
  color: var(--crm-text-secondary) !important;
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
.apexcharts-pie-series path { cursor: pointer; }
.chart-fade-enter-active, .chart-fade-leave-active { transition: opacity 0.25s, transform 0.25s; }
.chart-fade-enter-from { opacity: 0; transform: translateX(12px); }
.chart-fade-leave-to  { opacity: 0; transform: translateX(-12px); }

/* ── Gradient progress bars ── */
.gradient-progress .v-progress-linear__determinate {
  transition: width 0.6s cubic-bezier(0.22, 1, 0.36, 1) !important;
}
.gradient-progress .v-progress-linear__background {
  opacity: 0.15 !important;
}

/* ── Chart card hover (glassmorphism) ── */
.chart-card {
  transition: box-shadow 0.3s cubic-bezier(0.22, 1, 0.36, 1),
              transform 0.3s cubic-bezier(0.22, 1, 0.36, 1),
              border-color 0.3s ease;
}
.chart-card:hover {
  box-shadow: 0 12px 32px var(--crm-shadow-hover);
  transform: translateY(-3px);
  border-color: var(--crm-border-strong);
}

/* ── Smooth skeleton transition ── */
.kpi-row {
  transition: opacity 0.3s ease;
}

/* ── Animated gradient text (Wiza-inspired) ── */
.gradient-text {
  background: linear-gradient(
    90deg,
    #3B82F6 0%,
    #8B5CF6 25%,
    #EC4899 50%,
    #F59E0B 75%,
    #3B82F6 100%
  );
  background-size: 200% auto;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: gradient-shift 4s linear infinite;
}

@keyframes gradient-shift {
  0% { background-position: 0% center; }
  100% { background-position: 200% center; }
}

/* ── Dot grid background (First Internet inspired) ── */
.crm-dashboard {
  position: relative;
}
.crm-dashboard::before {
  content: '';
  position: fixed;
  inset: 0;
  background-image: radial-gradient(circle, var(--crm-border-strong) 1px, transparent 1px);
  background-size: 24px 24px;
  opacity: 0.4;
  pointer-events: none;
  z-index: 0;
}
.crm-dashboard > * {
  position: relative;
  z-index: 1;
}

/* ── Staggered entrance animation ── */
@keyframes card-entrance {
  from {
    opacity: 0;
    transform: translateY(16px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.kpi-row .v-col:nth-child(1) .kpi-card { animation: card-entrance 0.4s cubic-bezier(0.22, 1, 0.36, 1) 0.05s both; }
.kpi-row .v-col:nth-child(2) .kpi-card { animation: card-entrance 0.4s cubic-bezier(0.22, 1, 0.36, 1) 0.10s both; }
.kpi-row .v-col:nth-child(3) .kpi-card { animation: card-entrance 0.4s cubic-bezier(0.22, 1, 0.36, 1) 0.15s both; }
.kpi-row .v-col:nth-child(4) .kpi-card { animation: card-entrance 0.4s cubic-bezier(0.22, 1, 0.36, 1) 0.20s both; }
.kpi-row .v-col:nth-child(5) .kpi-card { animation: card-entrance 0.4s cubic-bezier(0.22, 1, 0.36, 1) 0.25s both; }
.kpi-row .v-col:nth-child(6) .kpi-card { animation: card-entrance 0.4s cubic-bezier(0.22, 1, 0.36, 1) 0.30s both; }
.kpi-row .v-col:nth-child(7) .kpi-card { animation: card-entrance 0.4s cubic-bezier(0.22, 1, 0.36, 1) 0.35s both; }
.kpi-row .v-col:nth-child(8) .kpi-card { animation: card-entrance 0.4s cubic-bezier(0.22, 1, 0.36, 1) 0.40s both; }
.kpi-row .v-col:nth-child(9) .kpi-card { animation: card-entrance 0.4s cubic-bezier(0.22, 1, 0.36, 1) 0.45s both; }

/* Charts entrance */
.chart-row .v-col:nth-child(1) .chart-card { animation: card-entrance 0.5s cubic-bezier(0.22, 1, 0.36, 1) 0.3s both; }
.chart-row .v-col:nth-child(2) .chart-card { animation: card-entrance 0.5s cubic-bezier(0.22, 1, 0.36, 1) 0.38s both; }
.chart-row .v-col:nth-child(3) .chart-card { animation: card-entrance 0.5s cubic-bezier(0.22, 1, 0.36, 1) 0.46s both; }

/* ── Grid layout widgets ── */
.grid-widget {
  height: 100%;
  border-radius: 12px;
  overflow: hidden;
  transition: box-shadow 0.2s ease;
}
/* KPI-виджет: при нехватке высоты (старый сохранённый layout) — скролл, не обрезание */
.grid-widget:has(.kpi-row) {
  overflow-y: auto;
}
.grid-widget--editing {
  box-shadow: 0 0 0 2px rgba(245,158,11,0.4);
  cursor: grab;
}
.grid-widget--editing:active {
  cursor: grabbing;
}

.widget-drag-handle {
  background: linear-gradient(90deg, rgba(245,158,11,0.15), transparent);
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 600;
  color: var(--crm-text-muted);
  display: flex;
  align-items: center;
  gap: 4px;
  border-bottom: 1px solid var(--crm-border);
}

.edit-mode-banner {
  background: linear-gradient(90deg, #F59E0B, #EF4444);
  color: white;
  padding: 8px 16px;
  border-radius: 8px;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  font-size: 13px;
  font-weight: 500;
}

/* grid-layout-plus overrides */
.vue-grid-item {
  transition: all 0.2s ease;
}
.vue-grid-item.vue-grid-placeholder {
  background: rgba(59,130,246,0.15) !important;
  border: 2px dashed #3B82F6 !important;
  border-radius: 12px;
}
.vue-grid-item > .vue-resizable-handle {
  width: 16px;
  height: 16px;
  bottom: 4px;
  right: 4px;
  background: none;
}
.vue-grid-item > .vue-resizable-handle::after {
  content: '';
  position: absolute;
  right: 2px;
  bottom: 2px;
  width: 8px;
  height: 8px;
  border-right: 2px solid var(--crm-text-muted);
  border-bottom: 2px solid var(--crm-text-muted);
  border-radius: 0 0 2px 0;
}
</style>
