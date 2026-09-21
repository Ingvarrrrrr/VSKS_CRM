// Состояние списка субсидий (год/режим таблица-карточки/порядок карточек/пагинация) —
// вынесено из SubsidiesView.vue при разбиении на SubsidyListHeader.vue/
// SubsidyListTable.vue/SubsidyCardsGrid.vue/SubsidySummaryBar.vue (волна 5b).
// Вызывается из ЧЕТЫРЁХ мест (сами эти компоненты + SubsidiesView.vue — ему
// нужны filteredSubsidies/effectiveView для v-if переключения таблица/карточки
// и selectedYear для авто-выбора года при загрузке). Если бы useCardView()
// (внутри которого создаётся viewMode/effectiveView/пагинация) вызывался
// заново в каждом из них — каждый получил бы СВОЙ независимый viewMode, и клик
// по переключателю в шапке не переключал бы вид у остальных (баг, найденный
// при 5b-приёмке: клик по «карточки» не менял таблицу). Поэтому, как и в
// useKpiDrilldown.ts, здесь весь реактивный API строится через makeCtxSingleton
// (ctxSingleton.ts, Правило №6) — по ctx первого вызвавшего, а при новом ctx
// (повторный маунт SubsidiesView.vue) пересобирается заново, иначе рендер
// после возврата на /subsidies читал бы allSubsidies прошлого маунта
// (владелец, 21.09, П2 — строка субсидии не исчезала после удаления до F5).
import { computed, ref } from 'vue'
import { useCardView } from '@/composables/useCardView'
import { formatCurrencyShort } from './format'
import { makeCtxSingleton } from './ctxSingleton'
import type { SubsidyDetailContext } from './useSubsidyDetail'
import type { SubsidyRow } from './types'

const CARD_ORDER_KEY = 'subsidies_card_order'

// makeCtxSingleton (Правило №6, владелец 21.09 П2): переизбор ctx при новом
// маунте SubsidiesView.vue — см. докстринг ctxSingleton.ts.
export const useSubsidyList = makeCtxSingleton(
  buildSubsidyList,
  'useSubsidyList() вызван до первого построения (нужен ctx) — проверьте порядок монтирования SubsidiesView.vue',
)

function buildSubsidyList(ctx: Pick<SubsidyDetailContext, 'allSubsidies'>) {
  const selectedYear = ref<number>(new Date().getFullYear())
  const cardDragIdx = ref(-1)
  const cardDragOverIdx = ref(-1)
  const subsidyOrder = ref<number[]>(JSON.parse(localStorage.getItem(CARD_ORDER_KEY) || '[]'))

  const subsidyTableHeaders = [
    { title: 'Название', key: 'name', minWidth: '200px' },
    { title: 'Бюджет ФЭО', key: 'feo_budget_total', align: 'end' as const },
    { title: 'Запланировано', key: 'planned', align: 'end' as const },
    { title: 'Заказано', key: 'ordered', align: 'end' as const },
    { title: 'Оплачено', key: 'paid', align: 'end' as const },
    { title: 'Контрагент', key: 'contractor_name' },
    { title: 'ФЭО', key: 'feo_filled', align: 'center' as const },
    { title: 'Потолок', key: 'ceiling_committed_percent', align: 'center' as const },
    { title: '', key: 'actions', sortable: false, align: 'end' as const },
  ]

  const availableYears = computed(() =>
    [...new Set((ctx?.allSubsidies.value || []).map(s => s.year))].sort((a, b) => b - a)
  )

  const filteredSubsidies = computed(() => {
    const yearFiltered = (ctx?.allSubsidies.value || []).filter(s => s.year === selectedYear.value)
    if (subsidyOrder.value.length === 0) return yearFiltered
    const orderMap = new Map(subsidyOrder.value.map((id, i) => [id, i]))
    return [...yearFiltered].sort((a, b) => {
      const ai = orderMap.get(a.id) ?? 9999
      const bi = orderMap.get(b.id) ?? 9999
      return ai - bi
    })
  })

  // ── Table ↔ Cards toggle ──────────────────────────
  const { mobile, viewMode, effectiveView, page: subPage, totalPages: subTotalPages, paged: subPaged } = useCardView<SubsidyRow>({
    storageKey: 'subsidies_view_mode',
    source: () => filteredSubsidies.value,
  })

  // Сводная панель (SubsidySummaryBar.vue) — суммы по ВСЕМ отфильтрованным по
  // году субсидиям (не только по текущей странице карточек).
  const totals = computed(() => ({
    budget:           filteredSubsidies.value.reduce((s, x) => s + (x.feo_budget_total || x.budget || 0), 0),
    planned:          filteredSubsidies.value.reduce((s, x) => s + x.planned,            0),
    ordered:          filteredSubsidies.value.reduce((s, x) => s + x.ordered,            0),
    contracted:       filteredSubsidies.value.reduce((s, x) => s + (x.contracted || 0),  0),
    paid:             filteredSubsidies.value.reduce((s, x) => s + x.paid,               0),
    work:             filteredSubsidies.value.reduce((s, x) => s + x.work,               0),
    contracts:        filteredSubsidies.value.reduce((s, x) => s + x.contracts,          0),
    delivered:        filteredSubsidies.value.reduce((s, x) => s + x.delivered,          0),
    delivered_unpaid: filteredSubsidies.value.reduce((s, x) => s + x.delivered_unpaid,   0),
  }))

  function getSubsidyExportColumns() {
    return subsidyTableHeaders
      .filter(h => h.key !== 'actions' && h.title)
      .map(h => ({ key: h.key, title: h.title, align: h.align }))
  }
  function getSubsidyExportRows() {
    return filteredSubsidies.value
  }

  function onCardDragStart(e: DragEvent, idx: number) {
    cardDragIdx.value = idx
    if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move'
  }
  function onCardDragOver(idx: number) {
    cardDragOverIdx.value = idx
  }
  function onCardDrop(targetIdx: number) {
    const srcIdx = cardDragIdx.value
    if (srcIdx < 0 || srcIdx === targetIdx) return
    const ids = filteredSubsidies.value.map(s => s.id)
    const [moved] = ids.splice(srcIdx, 1)
    if (moved === undefined) return
    ids.splice(targetIdx, 0, moved)
    subsidyOrder.value = ids
    localStorage.setItem(CARD_ORDER_KEY, JSON.stringify(ids))
    cardDragOverIdx.value = -1
    cardDragIdx.value = -1
  }

  function pct(part: number, total: number) {
    return total ? Math.round((part / total) * 100) : 0
  }

  function progressColor(p: number) {
    if (p > 100) return '#EF4444'
    if (p >= 80) return '#F59E0B'
    return '#22C55E'
  }

  function cardDelta(s: SubsidyRow): number {
    // Приоритет ручного бюджета субсидии (решение 14.07)
    return (s.feo_budget_total || s.budget || 0) - (s.planned || 0)
  }

  // displayBudget/isBudgetUndefined — единый источник для «какое число бюджета
  // показать в карточке/таблице» (владелец, 2026-09-15: «почему нельзя оставить
  // Бюджет пустым»). Раньше `s.feo_budget_total || s.budget` было продублировано
  // в SubsidyCardsGrid.vue (5 мест) и SubsidyListTable.vue по отдельности —
  // после того как budget стал nullable, каждое место рисковало тихо показать
  // «0 ₽» вместо «Бюджет не определён» (formatCurrencyShort(null) тоже даёт
  // «0 ₽» — 0 и «не задано» неразличимы на выходе). Теперь оба места вызывают
  // ОДНУ функцию для решения «budget задан?» вместо копирования условия.
  function displayBudget(s: SubsidyRow): number {
    return s.feo_budget_total || s.budget || 0
  }
  function isBudgetUndefined(s: SubsidyRow): boolean {
    return !(s.feo_budget_total && s.feo_budget_total > 0) && (s.budget === null || s.budget === undefined)
  }

  return {
    selectedYear, availableYears, filteredSubsidies, subsidyTableHeaders, totals,
    mobile, viewMode, effectiveView, subPage, subTotalPages, subPaged,
    cardDragIdx, cardDragOverIdx,
    onCardDragStart, onCardDragOver, onCardDrop,
    getSubsidyExportColumns, getSubsidyExportRows,
    pct, progressColor, cardDelta, formatCurrencyShort, displayBudget, isBudgetUndefined,
  }
}
