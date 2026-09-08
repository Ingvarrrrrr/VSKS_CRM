// Донат-график «Структура бюджета» + переключаемый бар-график разбивки сегмента
// по субсидиям + связь с общим диалогом BudgetDrillDownDialog.
// Перенесено без изменений из DashboardView.vue при разбиении на модули.
import { ref, computed, type Ref } from 'vue'
import { formatCurrency, formatCurrencyShort, truncate } from './dashboardFormat'
import type { SubsidyRow } from './useDashboardData'

export const SEGMENT_LABELS  = ['Оплачено', 'Заказано', 'Запланировано', 'Свободно']
export const SEGMENT_COLORS  = ['#22C55E', '#3B82F6', '#F59E0B', '#94A3B8']
export const SEGMENT_METRICS = ['paid', 'ordered', 'budget', 'budget'] // maps to BudgetDrillDownDialog metric

interface ChartTheme {
  isDark: Ref<boolean>
  chartText: Ref<string>
  chartMuted: Ref<string>
  chartGrid: Ref<string>
}

interface BudgetDrilldown {
  showBreakdownDialog: Ref<boolean>
  breakdownMetric: Ref<string>
  drillDialogSubsidies: Ref<any[]>
}

export function useDonutWidget(
  totals: {
    totalPaid: Ref<number>
    totalOrdered: Ref<number>
    totalPlanSchedule: Ref<number>
    totalBudget: Ref<number>
  },
  filteredSubsidies: Ref<SubsidyRow[]>,
  theme: ChartTheme,
  budgetDrilldown: BudgetDrilldown,
) {
  const { isDark, chartText, chartMuted, chartGrid } = theme
  const { totalPaid, totalOrdered, totalPlanSchedule, totalBudget } = totals

  const donutReady = computed(() => totalBudget.value > 0)

  const donutSeries = computed(() => {
    const paid       = totalPaid.value
    const ordered    = Math.max(0, totalOrdered.value - paid)         // заказано (договор), не оплачено
    const planned    = totalPlanSchedule.value                        // запланировано (confirmed+wip)
    const free       = Math.max(0, totalBudget.value - totalOrdered.value - planned)
    return [paid, ordered, planned, free]
  })

  const drillDownDialog  = ref(false)
  const drillDownSegment = ref<number | null>(null)
  const donutView        = ref<'donut' | 'breakdown'>('donut')

  const drillDownRows = computed(() => {
    if (drillDownSegment.value === null) return []
    return filteredSubsidies.value.map(s => {
      const values = [
        s.paid,
        Math.max(0, s.ordered - s.paid),
        s.plan_schedule,
        Math.max(0, s.budget - s.ordered - s.plan_schedule),
      ]
      return { name: s.name, value: values[drillDownSegment.value!] }
    }).filter(r => r.value > 0).sort((a, b) => b.value - a.value)
  })

  const breakdownBarSeries = computed(() => [{
    name: drillDownSegment.value !== null ? SEGMENT_LABELS[drillDownSegment.value] : '',
    data: drillDownRows.value.map(r => r.value)
  }])

  const breakdownBarOptions = computed(() => ({
    chart: {
      type: 'bar', background: 'transparent', toolbar: { show: false },
      animations: { speed: 350 },
      theme: { mode: isDark.value ? 'dark' : 'light' },
      events: {
        dataPointSelection: (_e: any, _ctx: any, config: any) => {
          const row = drillDownRows.value[config.dataPointIndex]
          if (!row) return
          const sub = filteredSubsidies.value.find((s: any) => s.name === row.name)
          if (sub) {
            budgetDrilldown.drillDialogSubsidies.value = [sub]
            budgetDrilldown.breakdownMetric.value = SEGMENT_METRICS[drillDownSegment.value ?? 0]
            budgetDrilldown.showBreakdownDialog.value = true
          }
        }
      }
    },
    colors: [drillDownSegment.value !== null ? SEGMENT_COLORS[drillDownSegment.value] : '#3B82F6'],
    plotOptions: { bar: { horizontal: true, barHeight: '55%', borderRadius: 4, borderRadiusApplication: 'end' } },
    dataLabels: {
      enabled: true,
      formatter: (v: number) => formatCurrencyShort(v),
      style: { fontSize: '10px', colors: [chartText.value] }
    },
    xaxis: {
      categories: drillDownRows.value.map(r => truncate(r.name, 22)),
      labels: { formatter: (v: number) => formatCurrencyShort(v), style: { colors: chartMuted.value, fontSize: '10px' } }
    },
    yaxis: { labels: { style: { colors: chartText.value, fontSize: '11px' } } },
    grid: { borderColor: chartGrid.value },
    tooltip: {
      theme: isDark.value ? 'dark' : 'light',
      y: { formatter: (v: number) => formatCurrency(v) },
      custom: () => `<div style="padding:6px 10px;font-size:12px">Нажмите для детализации →</div>`
    }
  }))

  const donutOptions = computed(() => ({
    chart: {
      type: 'donut', background: 'transparent', toolbar: { show: false },
      animations: { speed: 500 },
      theme: { mode: isDark.value ? 'dark' : 'light' },
      events: {
        dataPointSelection: (_e: any, _ctx: any, config: any) => {
          const idx = config.dataPointIndex
          drillDownSegment.value = idx
          donutView.value = 'breakdown'
        }
      }
    },
    colors: ['#22C55E', '#3B82F6', '#F59E0B', '#94A3B8'],
    labels: SEGMENT_LABELS,
    legend: { position: 'bottom', fontSize: '12px', labels: { colors: chartText.value } },
    dataLabels: {
      enabled: true,
      style: { fontSize: '11px', colors: ['#fff', '#fff', '#fff', '#374151'] },
      dropShadow: { enabled: false }
    },
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
            },
            value: {
              show: true,
              fontSize: '18px',
              fontWeight: '600',
              color: chartText.value,
              formatter: (v: string) => formatCurrencyShort(Number(v))
            },
            name: { show: true, color: chartMuted.value }
          }
        }
      }
    },
    tooltip: { y: { formatter: (v: number) => formatCurrency(v) } }
  }))

  return {
    donutReady, donutSeries, donutOptions,
    drillDownDialog, drillDownSegment, donutView,
    drillDownRows, breakdownBarSeries, breakdownBarOptions,
  }
}
