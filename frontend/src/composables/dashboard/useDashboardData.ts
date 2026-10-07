// Ядро данных дашборда: субсидии/закупки/виджеты с бэкенда + агрегаты + KPI-карточки.
// Перенесено без изменений из DashboardView.vue при разбиении на модули.
import { ref, computed, watch, type Ref } from 'vue'
import { apiFetch } from '@/api'
import { useAnimatedNumber } from '@/composables/useAnimatedNumber'
import { pct, truncate, formatCurrency } from './dashboardFormat'
import { useKpiPrefs } from '@/composables/useKpiPrefs'
import { formatEconomyUnmeasuredText, type EconomyUnmeasuredByReason } from '@/utils/economyUnmeasured'

export interface TypeSplitAmounts { goods: number; services: number; unspecified: number }

export interface WidgetMetric {
  amount: number
  count: number
  monthly_payments_total?: number
  // Задача 3 (владелец, 04.10.2026) — остаток помесячных платежей по уже
  // заключённым договорам до конца года, см. backend/app/routers/
  // dashboard_charts.py widgets.ordered (готовое поле, не пересчёт).
  monthly_future_to_year_end?: number
}

export interface WidgetsData {
  plan_schedule: WidgetMetric
  work: WidgetMetric
  ordered: WidgetMetric
  delivered: WidgetMetric
  delivered_unpaid: WidgetMetric
  paid: WidgetMetric
  contracts: WidgetMetric
  // Плашка «Оплачено больше, чем поставлено» (владелец, 07.10.2026, прод
  // id=74 «ЛНР») — Σ excess ПО ЗАКУПКАМ видимого scope (backend app/routers/
  // dashboard_charts.py::widgets["paid_over_delivered"], Правило №6).
  paid_over_delivered?: { amount: number; prepayment_amount: number; count: number }
}

export interface TypeSplitByKind { goods: number; services: number; unspecified: number }

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
  // Квик-план 2026-10-02 («Деньги субсидии», PLAN.md п.4/5) — то же, что и
  // SubsidyRow в composables/subsidies/types.ts (другой модуль, тот же смысл
  // и тот же источник — subsidy_stats[] из /dashboard/charts, Правило №6: не
  // пересчитываем на фронте, только суммируем по выбранным субсидиям).
  committed?: number | null
  planned_not_committed?: number | null
  redistributable?: number | null
  redistributable_by_kind?: TypeSplitByKind | null
  // Задача (владелец, 04.10.2026): «не запланировано» строкой карточки
  // «Можно перераспределить» — free, если бюджет задан, иначе 0.0, одна точка
  // расчёта (Правило №6). Раньше здесь переиспользовался freeRaw (totalBudget
  // − totalPlanSchedule, та же формула, что у отдельной карточки «Свободно»)
  // — на субсидии без введённого бюджета три строки карточки не сходились в
  // сумму с итогом.
  redistributable_unplanned?: number | null
  economy_total?: number | null
  economy_no_planned_price_items?: number | null
  economy_unmeasured_by_reason?: { unlinked: number; no_plan_price: number; monthly: number; no_fact: number } | null
  committed_missing_fact_items?: number | null
  // Задачи 2-3 (владелец, 04.10.2026) — то же, что и SubsidyRow в
  // composables/subsidies/types.ts (один источник, Правило №6): разбивка «в
  // плане без договоров» по need_level + остаток помесячного до конца года.
  not_committed_likely?: number | null
  not_committed_nice?: number | null
  monthly_future_to_year_end?: number | null
  // Решение владельца 06.10.2026 (budget_from_plan, см. докстринг backend
  // app/services/subsidy_money_summary.py) — budget выше временно взят из
  // плана (бюджета по ФЭО/вручную нет). ОТМЕНЕНО 07.10.2026 — всегда false,
  // см. feo_entered ниже (единственный источник теперь).
  budget_from_plan?: boolean
  // feo_entered (владелец 07.10.2026, план .planning/quick/2026-10-07-dnr-
  // feo-cards/PLAN.md шаг 1) — см. docstring у того же поля в
  // composables/subsidies/types.ts (один источник смысла, Правило №6). false —
  // ни официального бюджета, ни суммы ФЭО не введено; budget ниже в этом
  // случае равен 0 намеренно (см. мэппинг budget: ниже), не выдуманному плану.
  feo_entered?: boolean
  // Плашка «Оплачено больше, чем поставлено» (владелец, 07.10.2026, прод
  // id=74 «ЛНР») — тот же источник, что composables/subsidies/types.ts
  // (dashboard_charts.py::subsidy_stats, Правило №6, не пересчитываем здесь).
  paid_over_delivered?: number | null
  paid_over_delivered_prepayment?: number | null
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

  // ── Раздел B/C (план ancient-prancing-music.md, 21.09): товары/услуги по
  // этапам — ленивая догрузка (?type_split=true), запрашивается ТОЛЬКО когда
  // владелец включает переключатель «Товары и услуги» (kpiPrefs.kpiTypeSplit),
  // чтобы не утяжелять обычный первый рендер дашборда. Данные приходят per-
  // subsidy (subsidy_stats[].widget[stage][`${stage}_goods`] и т.п., см.
  // app.services.dashboard_type_split) — единственный источник этих чисел,
  // здесь только суммирование по выбранным субсидиям (та же схема фильтрации,
  // что totalBudget/totalPlanSchedule ниже: filteredSubsidies по году +
  // выбранным id, независимо от того, пуст ли selectedSubsidyIds).
  const kpiPrefs = useKpiPrefs()
  const typeSplitLoaded = ref(false)
  const typeSplitLoading = ref(false)
  const typeSplitSubsidyStats = ref<Record<number, any>>({})
  // Глобальные widgets ИЗ type_split-ответа (chartsData.widgets, ТЕ ЖЕ 7 этапов,
  // что effectiveWidgets читает без фильтра ниже) — нужны отдельно от
  // typeSplitSubsidyStats: без выбранных субсидий «целиком» (effectiveWidgets)
  // берёт widgetsData (весь видимый контур), а Σ по subsidy_stats — ТОЛЬКО по
  // субсидиям, попавшим в этот список (бывают закупки вне него), из-за чего
  // сумма строк по типу расходилась с «целиком» (приёмка 2026-09-21). Тот же
  // источник, что и «целиком» без фильтра — не второй расчёт (Правило №6).
  const typeSplitGlobalWidgets = ref<Record<string, any> | null>(null)

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

  // Σ по типу для одного этапа (STAGE_KEYS бэкенда) по filteredSubsidies —
  // ЕДИНСТВЕННАЯ функция суммирования типа (используется и card.split ниже,
  // и «Бюджет»/«Свободно» — Правило №6, вызывается с разным picker'ом, не
  // копируется). null, пока сами данные не загружены (ensureTypeSplitLoaded).
  function sumTypeSplit(picker: (stat: any) => { g?: number; s?: number; u?: number } | null): TypeSplitAmounts | null {
    if (!typeSplitLoaded.value) return null
    let g = 0, s = 0, u = 0, found = false
    for (const row of filteredSubsidies.value) {
      const stat = typeSplitSubsidyStats.value[row.id]
      if (!stat) continue
      const v = picker(stat)
      if (!v) continue
      found = true
      g += v.g || 0; s += v.s || 0; u += v.u || 0
    }
    return found ? { goods: g, services: s, unspecified: u } : null
  }

  function stageTypeSplit(stage: string): TypeSplitAmounts | null {
    // Без выбранных субсидий «целиком» (kpiTarget_*) читает effectiveWidgets →
    // widgetsData.value (ВЕСЬ видимый контур с бэкенда) — строки по типу ниже
    // обязаны брать ТОТ ЖЕ глобальный источник (chartsData.widgets из
    // type_split-ответа), а не Σ по subsidy_stats: последний не включает
    // закупки без субсидии в списке — расхождение, найденное приёмкой.
    if (selectedSubsidyIds.value.length === 0) {
      if (!typeSplitLoaded.value) return null
      const w = typeSplitGlobalWidgets.value?.[stage]
      if (!w) return null
      const g = w[`${stage}_goods`]
      if (g === undefined) return null
      return { goods: Number(g) || 0, services: Number(w[`${stage}_services`]) || 0, unspecified: Number(w[`${stage}_unspecified`]) || 0 }
    }
    return sumTypeSplit(stat => {
      const w = stat.widget?.[stage]
      if (!w) return null
      return { g: w[`${stage}_goods`], s: w[`${stage}_services`], u: w[`${stage}_unspecified`] }
    })
  }

  const budgetTypeSplit = computed<TypeSplitAmounts | null>(() =>
    sumTypeSplit(stat => ({ g: stat.budget_goods, s: stat.budget_services, u: stat.budget_unspecified }))
  )
  const plannedTypeSplit = computed<TypeSplitAmounts | null>(() =>
    sumTypeSplit(stat => ({ g: stat.planned_goods, s: stat.planned_services, u: stat.planned_unspecified }))
  )
  // «Свободно/Превышение» по типам = ФЭО по типу − план по типу (тот же смысл,
  // что и общая freeRaw = totalBudget − totalPlanSchedule ниже, разложенный по типу).
  const freeTypeSplit = computed<TypeSplitAmounts | null>(() => {
    const b = budgetTypeSplit.value, p = plannedTypeSplit.value
    if (!b || !p) return null
    return { goods: b.goods - p.goods, services: b.services - p.services, unspecified: b.unspecified - p.unspecified }
  })

  async function ensureTypeSplitLoaded() {
    if (typeSplitLoaded.value || typeSplitLoading.value) return
    typeSplitLoading.value = true
    try {
      const chartsData = await apiFetch<any>('/dashboard/charts?scope=dashboard&type_split=true')
      const map: Record<number, any> = {}
      for (const s of chartsData.subsidy_stats || []) map[s.id] = s
      typeSplitSubsidyStats.value = map
      typeSplitGlobalWidgets.value = chartsData.widgets ?? null
      typeSplitLoaded.value = true
    } catch (e) {
      console.error('Dashboard type-split load error:', e)
    } finally {
      typeSplitLoading.value = false
    }
  }

  watch(kpiPrefs.kpiTypeSplit, (v) => { if (v === 'split') ensureTypeSplitLoaded() }, { immediate: true })

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

  // ── Квик-план 2026-10-02 («Деньги субсидии», PLAN.md п.4/5) — Σ по выбранным
  // субсидиям, то же агрегирование, что у totalFeoPlanned выше (не пересчёт
  // формулы, значения уже готовые с бэкенда — Правило №6).
  const totalRedistributable = computed(() =>
    filteredSubsidies.value.reduce((s, x) => s + (x.redistributable ?? 0), 0)
  )
  // ИСПРАВЛЕНО 02.10.2026 (приёмка — «экономия без данных = 0 ₽, должно быть
  // «—»): если НИ У ОДНОЙ выбранной субсидии нет поля economy_total (не
  // пришло/явный null с бэкенда) — агрегат null, а не ложный 0. Если хотя
  // бы у одной есть — считаем Σ как обычно (отсутствующие трактуются как 0
  // внутри суммы, это не то же самое, что «данных нет вообще»).
  const totalEconomy = computed<number | null>(() => {
    const list = filteredSubsidies.value
    const hasAny = list.some(x => x.economy_total !== null && x.economy_total !== undefined)
    if (!hasAny) return null
    return list.reduce((s, x) => s + (x.economy_total ?? 0), 0)
  })
  const totalEconomyNoPlannedPriceItems = computed(() =>
    filteredSubsidies.value.reduce((s, x) => s + (x.economy_no_planned_price_items ?? 0), 0)
  )
  // ИСПРАВЛЕНО 02.10.2026 (приёмка — текст «42 позиций без плановой цены не
  // учтены» был фиксированным и не показывал причину): разбивка по причине —
  // Σ готовых счётчиков economy_unmeasured_by_reason по выбранным субсидиям
  // (Правило №6 — суммирование готовых полей, не формула), текст строит
  // общий форматтер economyUnmeasured.ts (та же функция, что в карточке
  // субсидии и таблице по способам).
  const totalEconomyUnmeasuredByReason = computed<EconomyUnmeasuredByReason>(() => {
    const acc: EconomyUnmeasuredByReason = { unlinked: 0, no_plan_price: 0, monthly: 0, no_fact: 0 }
    for (const x of filteredSubsidies.value) {
      const by = x.economy_unmeasured_by_reason
      if (!by) continue
      acc.unlinked += by.unlinked || 0
      acc.no_plan_price += by.no_plan_price || 0
      acc.monthly += by.monthly || 0
      acc.no_fact += by.no_fact || 0
    }
    return acc
  })
  const totalCommittedMissingFactItems = computed(() =>
    filteredSubsidies.value.reduce((s, x) => s + (x.committed_missing_fact_items ?? 0), 0)
  )
  const totalPlannedNotCommitted = computed(() =>
    filteredSubsidies.value.reduce((s, x) => s + (x.planned_not_committed ?? 0), 0)
  )
  // Задача (владелец, 04.10.2026) — Σ готового поля бэкенда redistributable_unplanned
  // (не freeRaw = totalBudget − totalPlanSchedule, который считался от
  // расчётной оценки бюджета и не сходился с остальными строками карточки у
  // субсидий без введённого бюджета), та же схема суммирования, что у
  // totalRedistributable выше (Правило №6).
  const totalRedistributableUnplanned = computed(() =>
    filteredSubsidies.value.reduce((s, x) => s + (x.redistributable_unplanned ?? 0), 0)
  )
  // Задачи 2-3 (владелец, 04.10.2026) — Σ по видимым субсидиям готовых полей
  // бэкенда, та же схема суммирования, что у totalRedistributable выше
  // (Правило №6: не новая формула).
  const totalNotCommittedLikely = computed(() =>
    filteredSubsidies.value.reduce((s, x) => s + (x.not_committed_likely ?? 0), 0)
  )
  const totalNotCommittedNice = computed(() =>
    filteredSubsidies.value.reduce((s, x) => s + (x.not_committed_nice ?? 0), 0)
  )
  const totalMonthlyFutureToYearEnd = computed(() =>
    filteredSubsidies.value.reduce((s, x) => s + (x.monthly_future_to_year_end ?? 0), 0)
  )
  // «Остаток субсидии» (владелец, 06.10.2026) — Σ готовых полей бэкенда
  // balance_by_marks/balance_by_statement по видимым субсидиям, та же схема
  // суммирования, что у totalRedistributable выше (Правило №6, не формула).
  // Субсидии без бюджета (balance_by_marks == null) не суммируются —
  // отдельный счётчик totalBalanceNoBudgetCount для подписи карточки.
  const totalBalanceByMarks = computed(() =>
    filteredSubsidies.value.reduce((s, x) => s + (x.balance_by_marks ?? 0), 0)
  )
  const totalBalanceByStatement = computed(() =>
    filteredSubsidies.value.reduce((s, x) => s + (x.balance_by_statement ?? 0), 0)
  )
  const totalBalanceNoBudgetCount = computed(() =>
    filteredSubsidies.value.filter(x => x.balance_by_marks == null).length
  )
  const totalBalanceHasAny = computed(() =>
    filteredSubsidies.value.some(x => x.balance_by_marks != null)
  )
  const totalRedistributableByKind = computed<TypeSplitByKind>(() => {
    const acc: TypeSplitByKind = { goods: 0, services: 0, unspecified: 0 }
    for (const x of filteredSubsidies.value) {
      const k = x.redistributable_by_kind
      if (!k) continue
      acc.goods += k.goods || 0; acc.services += k.services || 0; acc.unspecified += k.unspecified || 0
    }
    return acc
  })

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

  // Плашка «Оплачено больше, чем поставлено» (владелец, 07.10.2026) — без
  // фильтра субсидий читает глобальный widgets.paid_over_delivered (готовая
  // Σ по видимому scope), с фильтром — суммирует готовое per-subsidy поле
  // filteredSubsidies[].paid_over_delivered (Правило №6, не пересчитываем
  // формулу excess здесь, только складываем уже посчитанные бэкендом числа).
  const paidOverDeliveredSummary = computed(() => {
    if (selectedSubsidyIds.value.length === 0) {
      const w = widgetsData.value?.paid_over_delivered
      return { amount: w?.amount ?? 0, prepaymentAmount: w?.prepayment_amount ?? 0 }
    }
    let amount = 0
    let prepaymentAmount = 0
    for (const row of filteredSubsidies.value) {
      amount += row.paid_over_delivered ?? 0
      prepaymentAmount += row.paid_over_delivered_prepayment ?? 0
    }
    return { amount, prepaymentAmount }
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
  const kpiTarget_redistributable  = computed(() => totalRedistributable.value)
  const kpiTarget_economy          = computed(() => totalEconomy.value ?? 0)  // useAnimatedNumber требует number; «—» для null решается в карточке ниже
  const kpiTarget_balance          = computed(() => totalBalanceHasAny.value ? totalBalanceByMarks.value : 0)

  const kpiAnim_budget           = useAnimatedNumber(kpiTarget_budget,           800)
  const kpiAnim_plan_schedule    = useAnimatedNumber(kpiTarget_plan_schedule,    800)
  const kpiAnim_work             = useAnimatedNumber(kpiTarget_work,             800)
  const kpiAnim_ordered          = useAnimatedNumber(kpiTarget_ordered,          800)
  const kpiAnim_contracts        = useAnimatedNumber(kpiTarget_contracts,        800)
  const kpiAnim_delivered        = useAnimatedNumber(kpiTarget_delivered,        800)
  const kpiAnim_delivered_unpaid = useAnimatedNumber(kpiTarget_delivered_unpaid, 800)
  const kpiAnim_paid             = useAnimatedNumber(kpiTarget_paid,             800)
  const kpiAnim_free             = useAnimatedNumber(kpiTarget_free,             800)
  const kpiAnim_redistributable  = useAnimatedNumber(kpiTarget_redistributable,  800)
  const kpiAnim_economy          = useAnimatedNumber(kpiTarget_economy,          800)
  const kpiAnim_balance          = useAnimatedNumber(kpiTarget_balance,          800)

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
        split: budgetTypeSplit.value,
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
        split: stageTypeSplit('plan_schedule'),
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
        split: stageTypeSplit('work'),
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
        split: stageTypeSplit('ordered'),
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
        // Задача 3 (владелец, 04.10.2026): остаток помесячных платежей по уже
        // заключённым помесячным договорам до конца года — готовое поле
        // бэкенда (totalMonthlyFutureToYearEnd), не считаем здесь.
        note: totalMonthlyFutureToYearEnd.value > 0
          ? `из них ещё уйдёт помесячно до конца года: ${formatCurrency(totalMonthlyFutureToYearEnd.value)}`
          : null,
        over: undefined as boolean | undefined,
        split: stageTypeSplit('contracts'),
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
        split: stageTypeSplit('delivered'),
      },
      {
        key: 'delivered_unpaid',
        label: 'Поставлено, не оплачено',
        icon: 'mdi-truck-alert',
        amount: kpiAnim_delivered_unpaid.value,
        count: w?.delivered_unpaid.count ?? 0,
        countLabel: 'закупок',
        split: stageTypeSplit('delivered_unpaid'),
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
        split: stageTypeSplit('paid'),
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
        split: freeTypeSplit.value,
      },
      // Квик-план 2026-10-02 («Деньги субсидии», PLAN.md п.5): «Можно
      // перераспределить» = Бюджет − Законтрактовано = Свободно + В плане без
      // договоров (см. SubsidyKpiCards.vue для той же карточки на вкладке
      // «Субсидии» — тот же смысл, тот же набор полей с бэкенда).
      {
        key: 'redistributable',
        label: 'Можно перераспределить',
        icon: 'mdi-swap-horizontal',
        amount: kpiAnim_redistributable.value,
        count: 0,
        countLabel: '',
        tooltip: 'бюджет минус законтрактовано: деньги, ещё не связанные договором. Разовый договор занимает деньги с момента заключения, рамочный — только суммой заказов',
        monthly: null,
        over: undefined as boolean | undefined,
        split: totalRedistributableByKind.value,
        // Задачи 1-2 (владелец, 04.10.2026): раньше одна строка «не
        // запланировано X (Свободно) + в плане без договоров Y» — теперь три
        // строки с разбивкой по статусу плановой позиции (та же разбивка,
        // что и SubsidyMoneyCards.vue на вкладке «Субсидии», Σ готовых полей
        // по видимым субсидиям, не новая формула — Правило №6).
        notes: [
          `не запланировано: ${formatCurrency(totalRedistributableUnplanned.value)}`,
          `хотелось бы, можно отказаться: ${formatCurrency(totalNotCommittedNice.value)}`,
          `скорее всего понадобится, без договоров: ${formatCurrency(totalNotCommittedLikely.value)}`,
        ],
        note: totalCommittedMissingFactItems.value > 0
          ? `${totalCommittedMissingFactItems.value} позиций в договоре без суммы договора — учтены по плановой цене`
          : null,
      },
      {
        key: 'economy',
        label: (totalEconomy.value ?? 0) < 0 ? 'Переплата по закупкам' : 'Экономия по закупкам',
        icon: (totalEconomy.value ?? 0) < 0 ? 'mdi-cash-minus' : 'mdi-cash-plus',
        // null (ни у одной субсидии нет данных) — карточка показывает «—»
        // (см. KpiCardsWidget.vue: card.amount == null -> '—'), не 0 ₽.
        amount: totalEconomy.value == null ? null : Math.abs(kpiAnim_economy.value),
        count: 0,
        countLabel: '',
        tooltip: 'план позиций минус договор по законтрактованным закупкам; переплата — согласованное превышение',
        monthly: null,
        over: (totalEconomy.value ?? 0) < 0,
        // ИСПРАВЛЕНО 02.10.2026 (приёмка — карточка была зелёной даже когда
        // ничего не измерено): нейтральный цвет вместо «экономия» (зелёный)
        // или «переплата» (красный), см. KpiCardsWidget.vue/DashboardView.vue
        // .kpi-unmeasured.
        unmeasured: totalEconomy.value == null,
        split: undefined,
        note: formatEconomyUnmeasuredText(totalEconomyNoPlannedPriceItems.value, totalEconomyUnmeasuredByReason.value) || null,
      },
      // «Остаток субсидии» (владелец, 06.10.2026) = бюджет ФЭО − оплачено, Σ
      // готовых полей по видимым субсидиям (ПРАВИЛО №6, та же схема, что и
      // «Можно перераспределить» выше — не новая формула). Субсидии без
      // бюджета не суммируются — отмечены отдельной строкой.
      {
        key: 'balance',
        label: 'Остаток субсидии',
        icon: 'mdi-bank-outline',
        amount: totalBalanceHasAny.value ? Math.abs(kpiAnim_balance.value) : null,
        count: 0,
        countLabel: '',
        tooltip: 'бюджет ФЭО минус оплаченное. Пока поступление на счёт = бюджету ФЭО (ввод поступлений появится позже)',
        monthly: null,
        over: totalBalanceHasAny.value && totalBalanceByMarks.value < 0,
        split: undefined,
        notes: totalBalanceHasAny.value ? [
          `по отметке: ${formatCurrency(totalBalanceByMarks.value)}`,
          `подтверждено выпиской: ${formatCurrency(totalBalanceByStatement.value)}`,
        ] : undefined,
        note: totalBalanceNoBudgetCount.value > 0
          ? `без бюджета: ${totalBalanceNoBudgetCount.value} субсид${totalBalanceNoBudgetCount.value === 1 ? 'ии' : 'ий'}`
          : null,
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
        // feo_entered=false → calculated_budget/feo_budget_total уже null с
        // бэка (budget_basis, см. docstring выше) — явный 0, а не случайное
        // падение на s.budget (ручной Subsidy.budget может быть стар/не
        // синхронизирован с «ФЭО не введено»). Числом эта карточка дашборда
        // не отличает «0 ₽ бюджет» от «ФЭО не введено» (та разница — в
        // SubsidyKpiCards.vue/SubsidyCardsGrid.vue, где текст «ФЭО не
        // введено» теперь читает feo_entered, а не этот budget).
        budget: s.feo_entered === false ? 0 : (s.calculated_budget || s.feo_budget_total || s.budget),
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
        committed: s.committed ?? null,
        planned_not_committed: s.planned_not_committed ?? null,
        redistributable: s.redistributable ?? null,
        redistributable_by_kind: s.redistributable_by_kind ?? null,
        redistributable_unplanned: s.redistributable_unplanned ?? null,
        economy_total: s.economy_total ?? null,
        economy_no_planned_price_items: s.economy_no_planned_price_items ?? null,
        economy_unmeasured_by_reason: s.economy_unmeasured_by_reason ?? null,
        committed_missing_fact_items: s.committed_missing_fact_items ?? null,
        not_committed_likely: s.not_committed_likely ?? null,
        not_committed_nice: s.not_committed_nice ?? null,
        monthly_future_to_year_end: s.monthly_future_to_year_end ?? null,
        // «Остаток субсидии» (владелец, 06.10.2026) — готовые поля бэкенда,
        // фронт не считает (Правило №6, см. composables/subsidies/types.ts).
        balance_paid_marked: s.balance_paid_marked ?? null,
        balance_paid_confirmed: s.balance_paid_confirmed ?? null,
        balance_by_marks: s.balance_by_marks ?? null,
        balance_by_statement: s.balance_by_statement ?? null,
        // 2026-10-06: «Законтрактовано, не заказано» и перерасход по категориям —
        // те же готовые поля /dashboard/charts, что и в SubsidiesView.vue
        // (pickSubsidyMoneyFields), но тип строки дашборда другой и не весь
        // набор денежных полей здесь используется — добавлены точечно.
        contracted_not_ordered: s.contracted_not_ordered ?? null,
        over_plan_categories: s.over_plan_categories ?? [],
        // Решение владельца 06.10.2026 — см. composables/subsidies/types.ts.
        budget_from_plan: s.budget_from_plan ?? false,
        // 07.10.2026 — см. docstring у поля в interface SubsidyRow выше.
        feo_entered: s.feo_entered ?? true,
        // Плашка «Оплачено больше, чем поставлено» — см. docstring выше.
        paid_over_delivered: s.paid_over_delivered ?? null,
        paid_over_delivered_prepayment: s.paid_over_delivered_prepayment ?? null,
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
        selectedYear.value = years[0]!
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
    totalRedistributable, totalEconomy, totalEconomyNoPlannedPriceItems,
    totalCommittedMissingFactItems, totalPlannedNotCommitted, totalRedistributableByKind,
    totalNotCommittedLikely, totalNotCommittedNice, totalMonthlyFutureToYearEnd,
    totalBalanceByMarks, totalBalanceByStatement, totalBalanceNoBudgetCount, totalBalanceHasAny,
    overrunSubsidies, effectiveWidgets, kpiCards,
    paidOverDeliveredSummary,
    loadAll,
  }
}
