// Ядро данных дашборда: субсидии/закупки/виджеты с бэкенда + агрегаты + KPI-карточки.
// Перенесено без изменений из DashboardView.vue при разбиении на модули.
import { ref, computed, type Ref } from 'vue'
import { apiFetch } from '@/api'
import { useAnimatedNumber } from '@/composables/useAnimatedNumber'
import { pct, truncate } from './dashboardFormat'

export interface WidgetMetric {
  amount: number
  count: number
  monthly_payments_total?: number
}

export interface WidgetsData {
  plan_schedule: WidgetMetric
  work: WidgetMetric
  ordered: WidgetMetric
  delivered: WidgetMetric
  delivered_unpaid: WidgetMetric
  paid: WidgetMetric
  contracts: WidgetMetric
}

export interface SubsidyRow {
  id: number; name: string; shortName: string; description: string; year: number
  budget: number; contracted: number; paid: number; planned: number
  plan_schedule: number; ordered: number
  total_feo_planned: number  // 12-01
  // Phase 31-05: canonical budget fields
  remaining?: number | null
  planned_amount?: number | null
  budget_discrepancy?: number | null
  widget?: WidgetsData | null
}

// Владелец (2026-08-30): «субсидии у потолка» — сумма заказанного (включая
// ежемесячные платежи, весь график) приблизилась/превысила потолок ФЭО.
// Приходит готовым списком с бэкенда (см. app/routers/dashboard.py
// dashboard_charts → subsidies_near_ceiling), не пересчитывается на фронте.
export interface CeilingWarningRow {
  subsidy_id: number; name: string
  ceiling_total: number; ceiling_committed_total: number
  ceiling_committed_percent: number; ceiling_warn_percent: number
  ceiling_exceeded: boolean
}

export function useDashboardData(selectedYear: Ref<number>, selectedSubsidyIds: Ref<number[]>) {
  const loading = ref(false)
  const loadingPurchases = ref(false)

  const allSubsidies    = ref<SubsidyRow[]>([])
  const allPurchases    = ref<any[]>([])
  const statusCounts    = ref<Record<string, number>>({})
  const widgetsData     = ref<WidgetsData | null>(null)
  const subsidiesNearCeiling = ref<CeilingWarningRow[]>([])

  const availableYears = computed(() =>
    [...new Set(allSubsidies.value.map(s => s.year))].sort((a, b) => b - a)
  )

  const yearSubsidies = computed((): SubsidyRow[] =>
    allSubsidies.value.filter((s: SubsidyRow) => s.year === selectedYear.value)
  )

  const filteredSubsidies = computed(() => {
    let res = allSubsidies.value.filter(s => s.year === selectedYear.value)
    if (selectedSubsidyIds.value.length > 0)
      res = res.filter(s => selectedSubsidyIds.value.includes(s.id))
    return res
  })

  // Recent purchases filtered to selected subsidies
  const recentPurchases = computed(() => {
    const subsidyIds = filteredSubsidies.value.map(s => s.id)
    return allPurchases.value
      .filter(p => subsidyIds.length === 0 || subsidyIds.includes(p.subsidy_id))
      .slice(0, 8)
  })

  const totalBudget       = computed(() => filteredSubsidies.value.reduce((s, x) => s + x.budget, 0))
  const totalContracted   = computed(() => filteredSubsidies.value.reduce((s, x) => s + x.contracted, 0))
  const totalPaid         = computed(() => filteredSubsidies.value.reduce((s, x) => s + x.paid, 0))
  const totalPlanned      = computed(() => filteredSubsidies.value.reduce((s, x) => s + x.planned, 0))
  const totalPlanSchedule = computed(() => filteredSubsidies.value.reduce((s, x) => s + x.plan_schedule, 0))
  const totalOrdered      = computed(() => filteredSubsidies.value.reduce((s, x) => s + x.ordered, 0))
  const totalFeoPlanned   = computed(() => filteredSubsidies.value.reduce((s: number, x: SubsidyRow) => s + (x.total_feo_planned ?? 0), 0))  // 12-01
  const totalRemaining    = computed(() => totalBudget.value - totalPaid.value)
  const totalUsagePct   = computed(() => pct(totalPaid.value, totalBudget.value))

  const overrunSubsidies = computed(() =>
    filteredSubsidies.value.filter(s => s.planned > s.budget || s.contracted > s.budget)
  )

  // ── Effective widgets: global or summed over selected subsidies ───
  const effectiveWidgets = computed((): WidgetsData | null => {
    if (selectedSubsidyIds.value.length === 0) return widgetsData.value
    const keys = ['plan_schedule', 'work', 'ordered', 'delivered', 'delivered_unpaid', 'paid', 'contracts'] as const
    const zero = (): WidgetMetric => ({ amount: 0, count: 0, monthly_payments_total: 0 })
    const acc: WidgetsData = {
      plan_schedule: zero(), work: zero(), ordered: zero(),
      delivered: zero(), delivered_unpaid: zero(), paid: zero(), contracts: zero(),
    }
    for (const row of filteredSubsidies.value) {
      if (!row.widget) continue
      for (const key of keys) {
        acc[key].amount += row.widget[key].amount ?? 0
        acc[key].count  += row.widget[key].count  ?? 0
        if (key === 'ordered') {
          acc.ordered.monthly_payments_total =
            (acc.ordered.monthly_payments_total ?? 0) + (row.widget.ordered.monthly_payments_total ?? 0)
        }
      }
    }
    return acc
  })

  // ── Animated KPI targets (mirrors kpiCards amount logic) ─────────────
  const kpiTarget_budget           = computed(() => totalBudget.value)
  const kpiTarget_plan_schedule    = computed(() => effectiveWidgets.value?.plan_schedule.amount    ?? totalPlanSchedule.value)
  const kpiTarget_work             = computed(() => effectiveWidgets.value?.work.amount             ?? 0)
  const kpiTarget_ordered          = computed(() => effectiveWidgets.value?.ordered.amount          ?? totalOrdered.value)
  const kpiTarget_contracts        = computed(() => effectiveWidgets.value?.contracts.amount        ?? 0)
  const kpiTarget_delivered        = computed(() => effectiveWidgets.value?.delivered.amount        ?? 0)
  const kpiTarget_delivered_unpaid = computed(() => effectiveWidgets.value?.delivered_unpaid.amount ?? 0)
  const kpiTarget_paid             = computed(() => effectiveWidgets.value?.paid.amount             ?? totalPaid.value)
  const kpiTarget_free             = computed(() => totalBudget.value - totalPlanSchedule.value)

  const kpiAnim_budget           = useAnimatedNumber(kpiTarget_budget,           800)
  const kpiAnim_plan_schedule    = useAnimatedNumber(kpiTarget_plan_schedule,    800)
  const kpiAnim_work             = useAnimatedNumber(kpiTarget_work,             800)
  const kpiAnim_ordered          = useAnimatedNumber(kpiTarget_ordered,          800)
  const kpiAnim_contracts        = useAnimatedNumber(kpiTarget_contracts,        800)
  const kpiAnim_delivered        = useAnimatedNumber(kpiTarget_delivered,        800)
  const kpiAnim_delivered_unpaid = useAnimatedNumber(kpiTarget_delivered_unpaid, 800)
  const kpiAnim_paid             = useAnimatedNumber(kpiTarget_paid,             800)
  const kpiAnim_free             = useAnimatedNumber(kpiTarget_free,             800)

  // ── KPI Cards (widgets — накопительная логика) ────
  const kpiCards = computed(() => {
    const w = effectiveWidgets.value
    const freeRaw = totalBudget.value - totalPlanSchedule.value
    return [
      {
        key: 'budget',
        label: 'Бюджет',
        icon: 'mdi-wallet',
        amount: kpiAnim_budget.value,
        count: 0,
        countLabel: '',
        tooltip: 'суммарный бюджет по дереву ФЭО выбранных субсидий',
        monthly: null,
        over: undefined as boolean | undefined,
      },
      {
        key: 'plan_schedule',
        label: 'План-График',
        icon: 'mdi-calendar-clock',
        amount: kpiAnim_plan_schedule.value,
        count: w?.plan_schedule.count ?? 0,
        countLabel: 'закупок',
        tooltip: 'включает все последующие этапы',
        monthly: null,
        over: undefined as boolean | undefined,
      },
      {
        key: 'work',
        label: 'Ведётся работа',
        icon: 'mdi-progress-wrench',
        amount: kpiAnim_work.value,
        count: w?.work.count ?? 0,
        countLabel: 'закупок',
        tooltip: 'включает заказанные, поставленные и оплаченные',
        monthly: null,
        over: undefined as boolean | undefined,
      },
      {
        key: 'ordered',
        label: 'Заказано',
        icon: 'mdi-cart-check',
        amount: kpiAnim_ordered.value,
        count: w?.ordered.count ?? 0,
        countLabel: 'закупок',
        tooltip: 'включает поставленные и оплаченные',
        monthly: (w?.ordered.monthly_payments_total ?? 0) > 0
          ? w!.ordered.monthly_payments_total!
          : null,
        over: undefined as boolean | undefined,
      },
      {
        key: 'contracts',
        label: 'Заключено договоров',
        icon: 'mdi-file-sign',
        amount: kpiAnim_contracts.value,
        count: w?.contracts.count ?? 0,
        countLabel: 'договоров',
        tooltip: 'суммарная стоимость заключённых договоров',
        monthly: null,
        over: undefined as boolean | undefined,
      },
      {
        key: 'delivered',
        label: 'Поставлено',
        icon: 'mdi-truck-check',
        amount: kpiAnim_delivered.value,
        count: w?.delivered.count ?? 0,
        countLabel: 'закупок',
        tooltip: 'включает оплаченные',
        monthly: null,
        over: undefined as boolean | undefined,
      },
      {
        key: 'delivered_unpaid',
        label: 'Поставлено, не оплачено',
        icon: 'mdi-truck-alert',
        amount: kpiAnim_delivered_unpaid.value,
        count: w?.delivered_unpaid.count ?? 0,
        countLabel: 'закупок',
        tooltip: 'поставлено, но оплата ещё не прошла',
        monthly: null,
        over: undefined as boolean | undefined,
      },
      {
        key: 'paid',
        label: 'Оплачено',
        icon: 'mdi-cash-check',
        amount: kpiAnim_paid.value,
        count: w?.paid.count ?? 0,
        countLabel: 'закупок',
        tooltip: null,
        monthly: null,
        over: undefined as boolean | undefined,
      },
      {
        key: 'free',
        label: freeRaw < 0 ? 'Превышение' : 'Свободно',
        icon: 'mdi-cash-lock-open',
        amount: Math.abs(kpiAnim_free.value),
        count: 0,
        countLabel: '',
        tooltip: 'бюджет минус запланировано',
        monthly: null,
        over: freeRaw < 0,
      },
    ]
  })

  // ── Load data ─────────────────────────────────────
  async function loadAll() {
    loading.value = true
    loadingPurchases.value = true
    try {
      const [chartsData, purchasesData] = await Promise.all([
        apiFetch<any>('/dashboard/charts?scope=dashboard'),
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
        // plan_schedule = единый источник «Запланировано» = план дерева ФЭО (ручные позиции + из заявок).
        // Совпадает с KPI «Запланировано» на вкладке «Субсидии».
        // Fallback: total_plan_schedule (SUM confirmed/wip) если planned_tree отсутствует (legacy).
        plan_schedule: s.planned_tree ?? s.total_plan_schedule ?? 0,
        ordered: s.total_ordered ?? 0,
        total_feo_planned: s.total_feo_planned ?? 0,  // 12-01: SUM FeoPlannedItem.amount (для колонки «ФЭО план»)
        // Phase 31-05: canonical budget fields (D-17) — from server, not recalculated on client
        // remaining = «Свободно» = budget − planned_tree (совпадает с панелью ФЭО вкладки «Субсидии»)
        remaining: s.remaining ?? null,
        planned_amount: s.planned_amount ?? null,
        budget_discrepancy: s.budget_discrepancy ?? null,
        widget: s.widget ?? null,
      }))

      statusCounts.value = chartsData.status_counts
      subsidiesNearCeiling.value = chartsData.subsidies_near_ceiling ?? []

      // Store widgets data from backend
      if (chartsData.widgets) {
        widgetsData.value = chartsData.widgets as WidgetsData
      }

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

  return {
    loading, loadingPurchases,
    allSubsidies, allPurchases, statusCounts, widgetsData, subsidiesNearCeiling,
    availableYears, yearSubsidies, filteredSubsidies, recentPurchases,
    totalBudget, totalContracted, totalPaid, totalPlanned, totalPlanSchedule, totalOrdered,
    totalFeoPlanned, totalRemaining, totalUsagePct,
    overrunSubsidies, effectiveWidgets, kpiCards,
    loadAll,
  }
}
