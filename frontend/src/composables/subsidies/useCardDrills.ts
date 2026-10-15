// useCardDrills.ts — ОДНО место «клик по числу карточки субсидии → какое окно
// и с какими параметрами» (план abstract-noodling-pelican.md, п.9, Правило №6:
// не плодить состояние открытых диалогов по компонентам). SubsidyKpiCards.vue и
// SubsidyMoneyCards.vue только навешивают клики на свою разметку — само
// состояние «что открыто» (какой диалог, какая стадия/карточка/метрика) живёт
// здесь, тем же приёмом module-level singleton, что и useKpiDrilldown.ts/
// useFeoTreeExcess.ts (см. ctxSingleton.ts): SubsidyKpiCards.vue строит API
// первым (useCardDrills(ctx)), SubsidyMoneyCards.vue переиспользует уже
// построенный (useCardDrills() без аргумента).
//
// Четыре вида диалогов:
//  - stageDrill (StageFeoDrillDialog) — список закупок одной стадии; kind='all'
//    передаётся напрямую диалогу, который сам группирует строки на товары/
//    услуги/без типа (backend отдаёт плоский список, группировка — на фронте,
//    Правило №6: это группировка уже посчитанных строк, не вторая формула);
//  - cardDrill (FeoCardDrillDialog) — «Бюджет (ФЭО)»/«Запланировано»/«Свободно»,
//    уже существовавший механизм (card-drill), перенесён сюда из
//    SubsidyKpiCards.vue без изменений логики;
//  - metricDrill (НОВЫЙ MetricDrillDialog.vue) — GET /dashboard/metric-drill;
//  - monthlyFutureTree (НОВЫЙ MonthlyFutureTreeDialog.vue) — дерево договор →
//    месяцы для metric=monthly_future / monthly_future_not_started;
//  - contractsDrill (ContractsDrillDialog) — список договоров, не изменился.
import { ref } from 'vue'
import { makeCtxSingleton } from './ctxSingleton'
import type { ItemTypeKind } from '@/utils/itemTypeKind'
import type { FeoCardDrillCard } from '@/components/subsidies/FeoCardDrillDialog.vue'
import type { SubsidyDetailContext } from './useSubsidyDetail'

export type MetricDrillMetric =
  | 'monthly_future' | 'not_committed_nice' | 'not_committed_likely'
  | 'paid_declared' | 'paid_confirmed' | 'balance_marked' | 'balance_confirmed'
  | 'economy' | 'monthly_future_not_started'

type CardDrillsCtx = Pick<SubsidyDetailContext, 'selectedId'>

function buildCardDrills(ctx: CardDrillsCtx) {
  // ── StageFeoDrillDialog (клик по ВСЕЙ карточке стадии — kind='all', а также
  // клик по строке «товары»/«услуги» конкретной стадии — kind=goods/services)
  const stageDrillVisible = ref(false)
  const stageDrillTitle = ref('')
  const stageDrillStatuses = ref<string[]>([])
  const stageDrillTypeKind = ref<ItemTypeKind | 'all' | null>(null)
  const stageDrillStageKey = ref<string | null>(null)

  function openStageKind(stage: string, kind: ItemTypeKind | 'all', title: string, statuses: string[]) {
    if (!ctx.selectedId.value) return
    stageDrillStageKey.value = stage
    stageDrillTypeKind.value = kind
    stageDrillTitle.value = title
    stageDrillStatuses.value = statuses
    stageDrillVisible.value = true
  }
  function closeStageDrill() {
    stageDrillVisible.value = false
    stageDrillTypeKind.value = null
    stageDrillStageKey.value = null
  }

  // ── FeoCardDrillDialog («Бюджет (ФЭО)»/«Запланировано»/«Свободно») ─────────
  const cardDrillVisible = ref(false)
  const cardDrillCard = ref<FeoCardDrillCard>('budget')
  const cardDrillKind = ref<ItemTypeKind | 'all'>('all')
  function openCard(stage: 'budget' | 'plan_schedule' | 'free', kind: ItemTypeKind | 'all') {
    if (!ctx.selectedId.value) return
    cardDrillCard.value = stage === 'plan_schedule' ? 'planned' : stage
    cardDrillKind.value = kind
    cardDrillVisible.value = true
  }
  // «не запланировано» (SubsidyMoneyCards.vue) — то же окно, что «Свободно»
  // целиком в SubsidyKpiCards.vue (card='free', kind='all').
  function openFree() {
    openCard('free', 'all')
  }

  // ── ContractsDrillDialog («Заключено договоров») ───────────────────────────
  const contractsDrillVisible = ref(false)
  function openContracts() {
    if (!ctx.selectedId.value) return
    contractsDrillVisible.value = true
  }

  // ── MetricDrillDialog (НОВЫЙ, GET /dashboard/metric-drill) ─────────────────
  const metricDrillVisible = ref(false)
  const metricDrillMetric = ref<MetricDrillMetric>('paid_declared')
  const metricDrillKind = ref<'goods' | 'services' | null>(null)
  function openMetric(metric: MetricDrillMetric, kind?: 'goods' | 'services' | null) {
    if (!ctx.selectedId.value) return
    metricDrillMetric.value = metric
    metricDrillKind.value = kind ?? null
    metricDrillVisible.value = true
  }

  // ── MonthlyFutureTreeDialog (НОВЫЙ, metric=monthly_future[_not_started]) ───
  const monthlyFutureVisible = ref(false)
  const monthlyFutureMetric = ref<'monthly_future' | 'monthly_future_not_started'>('monthly_future')
  function openMonthlyTree(metric: 'monthly_future' | 'monthly_future_not_started') {
    if (!ctx.selectedId.value) return
    monthlyFutureMetric.value = metric
    monthlyFutureVisible.value = true
  }

  return {
    stageDrillVisible, stageDrillTitle, stageDrillStatuses, stageDrillTypeKind, stageDrillStageKey,
    openStageKind, closeStageDrill,
    cardDrillVisible, cardDrillCard, cardDrillKind, openCard, openFree,
    contractsDrillVisible, openContracts,
    metricDrillVisible, metricDrillMetric, metricDrillKind, openMetric,
    monthlyFutureVisible, monthlyFutureMetric, openMonthlyTree,
  }
}

export const useCardDrills = makeCtxSingleton(
  buildCardDrills,
  'useCardDrills() вызван до первого построения (нужен ctx) — проверьте порядок монтирования SubsidyKpiCards.vue',
)
