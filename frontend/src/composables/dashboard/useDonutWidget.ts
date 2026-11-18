// Донат-график «Структура бюджета» + переключаемый бар-график разбивки сегмента
// по субсидиям + связь с общим диалогом BudgetDrillDownDialog.
// Единый источник истины и визуализация «второго круга» (Вариант А).
import { ref, computed, type Ref } from 'vue'
import { formatCurrency, formatCurrencyShort, truncate } from './dashboardFormat'
import { deferChartAction } from './deferChartAction'
import type { SubsidyRow } from './useDashboardData'

export const SEGMENT_LABELS = [
  'Подтверждено выпиской',
  'Оплачено (по отметке)',
  'Заказано',
  'Ведётся работа',
  'В плане',
  'Свободно',
]

export const SEGMENT_COLORS = [
  '#059669', // тёмно-изумрудный (подтверждено выпиской)
  '#22C55E', // светло-зелёный (по отметке)
  '#3B82F6', // насыщенный синий (заказано)
  '#8B5CF6', // контрастный фиолетовый (ведётся работа)
  '#F59E0B', // тёплый янтарь (в плане)
  '#64748B', // графитово-серый (свободно)
]

export const SEGMENT_ICONS = [
  'mdi-check-decagram',
  'mdi-cash-check',
  'mdi-cart-check',
  'mdi-progress-wrench',
  'mdi-calendar-clock',
  'mdi-cash-lock-open',
]

export const SEGMENT_ICON_COLORS = [
  '#059669',
  '#22C55E',
  '#3B82F6',
  '#8B5CF6',
  '#F59E0B',
  '#64748B',
]

export const SEGMENT_METRICS = [
  'paid',
  'paid',
  'ordered',
  'work',
  'plan_schedule',
  'budget',
]

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
    totalPaidConfirmed: Ref<number>
    totalOrdered: Ref<number>
    totalWork: Ref<number>
    totalPlanSchedule: Ref<number>
    totalBudget: Ref<number>
  },
  filteredSubsidies: Ref<SubsidyRow[]>,
  theme: ChartTheme,
  budgetDrilldown: BudgetDrilldown,
) {
  const { isDark, chartText, chartMuted, chartGrid } = theme
  const { totalPaid, totalPaidConfirmed, totalOrdered, totalWork, totalPlanSchedule, totalBudget } = totals

  const donutReady = computed(() => totalBudget.value > 0 || totalPlanSchedule.value > 0)

  // Перерасход плана относительно утверждённого бюджета
  const overrunAmount = computed(() => Math.max(0, totalPlanSchedule.value - totalBudget.value))
  const overrunPct = computed(() => (totalBudget.value > 0 ? Math.round((overrunAmount.value / totalBudget.value) * 100) : 0))
  const hasOverrun = computed(() => totalBudget.value > 0 && totalPlanSchedule.value > totalBudget.value)

  // 6 контрастных сегментов структуры бюджета
  const donutSeries = computed(() => {
    const paidConfirmed = totalPaidConfirmed.value
    const paid          = totalPaid.value
    const ordered       = totalOrdered.value
    const work          = totalWork.value
    const plan_schedule = totalPlanSchedule.value
    const budget        = totalBudget.value

    const s1 = Math.max(0, paidConfirmed)
    const s2 = Math.max(0, paid - paidConfirmed)
    const s3 = Math.max(0, ordered - paid)
    const s4 = Math.max(0, work - ordered)
    const s5 = Math.max(0, plan_schedule - Math.max(work, ordered, paid))
    const s6 = Math.max(0, budget - plan_schedule)

    return [s1, s2, s3, s4, s5, s6]
  })

  const drillDownDialog  = ref(false)
  const drillDownSegment = ref<number | null>(null)
  const donutView        = ref<'donut' | 'breakdown'>('donut')

  const drillDownRows = computed(() => {
    if (drillDownSegment.value === null) return []
    return filteredSubsidies.value.map(s => {
      const paidConfirmed = s.paid_confirmed ?? 0
      const paid          = s.paid ?? 0
      const ordered       = s.ordered ?? 0
      const work          = s.widget?.work?.amount ?? 0
      const plan_schedule = s.plan_schedule ?? 0
      const budget        = s.budget ?? 0

      const values = [
        Math.max(0, paidConfirmed),
        Math.max(0, paid - paidConfirmed),
        Math.max(0, ordered - paid),
        Math.max(0, work - ordered),
        Math.max(0, plan_schedule - Math.max(work, ordered, paid)),
        Math.max(0, budget - plan_schedule),
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
            deferChartAction(() => {
              budgetDrilldown.drillDialogSubsidies.value = [sub]
              budgetDrilldown.breakdownMetric.value = SEGMENT_METRICS[drillDownSegment.value ?? 0]
              budgetDrilldown.showBreakdownDialog.value = true
            })
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
          deferChartAction(() => {
            drillDownSegment.value = idx
            donutView.value = 'breakdown'
          })
        }
      }
    },
    colors: SEGMENT_COLORS,
    labels: SEGMENT_LABELS,
    legend: { position: 'bottom', fontSize: '11px', labels: { colors: chartText.value } },
    dataLabels: {
      enabled: true,
      style: { fontSize: '11px', colors: ['#fff', '#fff', '#fff', '#fff', '#fff', '#fff'] },
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
              label: hasOverrun.value ? 'Превышение' : 'Бюджет',
              color: hasOverrun.value ? '#EF4444' : chartMuted.value,
              fontSize: '13px',
              formatter: () => hasOverrun.value
                ? `+${formatCurrencyShort(overrunAmount.value)} (+${overrunPct.value}%)`
                : formatCurrencyShort(totalBudget.value)
            },
            value: {
              show: true,
              fontSize: '17px',
              fontWeight: '600',
              color: hasOverrun.value ? '#EF4444' : chartText.value,
              formatter: (v: string) => formatCurrencyShort(Number(v))
            },
            name: { show: true, color: hasOverrun.value ? '#EF4444' : chartMuted.value }
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
    hasOverrun, overrunAmount, overrunPct,
  }
}
