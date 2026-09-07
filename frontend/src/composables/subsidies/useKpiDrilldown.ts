// KPI drill-down: клик по одной из 9 мини-карточек детали субсидии подсвечивает
// в дереве ФЭО состав суммы (какие узлы/позиции заявок в неё вошли) и раскрывает
// соответствующие ветки/панели. Вынесено из SubsidiesView.vue при разбиении на
// SubsidyKpiCards.vue (волна 5b). Module-level singleton state, как
// useSubsidyApprovers.ts/usePlanGraphVersions.ts в этом же проекте — оба
// потребителя (SubsidyKpiCards.vue и оставшееся в SubsidiesView.vue дерево ФЭО,
// которому нужны kpiNodeClass/activeKpi для подсветки строк) видят одно и то же
// состояние.
//
// Типы/константы/kpiItemMatches — в @/constants/kpiMetrics.ts (логика покрыта
// тестом на паритет с backend/app/routers/dashboard.py, не менять «по здравому
// смыслу», см. комментарий там).
//
// Само дерево ФЭО (feo_categories, узлы, панели позиций, папки закупок) —
// вне этой волны рефакторинга (5c); ctx здесь — те же реактивные ссылки на
// состояние, что и раньше жили в SubsidiesView.vue, без копирования (Правило №6).
// Три маленькие функции подсветки строк «Позиция плана»/«Позиция закупки»/
// «Папка закупки» (kpiReqRowClass/kpiItemRowClass/kpiFolderClass) остаются в
// SubsidiesView.vue — им нужны локальные типы дерева (FeoReqRow/FeoPurchaseFolder),
// которые сам этот композабл не трогает; они читают набор id отсюда напрямую
// (kpi.kpiItemIds), не дублируя его.
import { computed, nextTick, ref, watch } from 'vue'
import { type KpiKey, KPI_MODE, kpiItemMatches } from '@/constants/kpiMetrics'
import type { SubsidyDetailContext } from './useSubsidyDetail'
import type { FeoNode, PlannedBase } from './types'

interface KpiSnapshot {
  expandedIds: number[]
  expandedReqItems: number[]
  expandedPurchases: number[]
  expandedItemPanels: number[]
  expandedPlannedItems: number[]
  plannedBase: PlannedBase
  feoSearch: string
}

const activeKpi = ref<KpiKey | null>(null)
const kpiSnapshot = ref<KpiSnapshot | null>(null)

type KpiCtx = Pick<SubsidyDetailContext,
  | 'selectedSubsidy' | 'feoCategories' | 'feoTree' | 'flattenAll'
  | 'plannedItemsByCat' | 'plannedItemsLoaded' | 'mergedReqByCat' | 'purchaseFoldersByCat'
  | 'expandedIds' | 'expandedReqItems' | 'expandedItemPanels' | 'expandedPurchases'
  | 'expandedPlannedItems' | 'collapsedPlannedItems' | 'feoSearch' | 'plannedBase'
  | 'comparisonData' | 'loadingComparison' | 'refreshComparison' | 'feoTableArea'
  | 'feoFinDiff' | 'feoPlannedTotalFor' | 'selectedId'>

// useKpiDrilldown() вызывается из ДВУХ мест — SubsidyKpiCards.vue (плитки) и
// самого SubsidiesView.vue (kpiNodeClass нужна дереву ФЭО, оставшемуся там же).
// В отличие от useSubsidyApprovers.ts/usePlanGraphVersions.ts (там только refs
// без watch()), здесь есть watch() — регистрировать их дважды означало бы
// применять applyKpiExpansion/сброс KPI по два раза на одно событие. _api
// кэширует результат первого вызова — оба потребителя получают ОДИН и тот же
// объект (первый вызов строит его по СВОЕМУ ctx, но обе стороны всегда передают
// один и тот же набор реактивных ссылок — либо из SubsidyDetailContext, либо
// напрямую из SubsidiesView.vue, что структурно то же самое, см. useSubsidyDetail.ts).
let _api: ReturnType<typeof buildKpiDrilldown> | null = null

export function useKpiDrilldown(ctx: KpiCtx) {
  if (!_api) _api = buildKpiDrilldown(ctx)
  return _api
}

function buildKpiDrilldown(ctx: KpiCtx) {
  function feoHasChildren(id: number): boolean {
    return ctx.feoCategories.value.some(c => c.parent_id === id)
  }

  const feoParentMap = computed<Record<number, number | null>>(() => {
    const map: Record<number, number | null> = {}
    for (const c of ctx.feoCategories.value) map[c.id] = c.parent_id
    return map
  })

  // Строгие предки узла (без самого узла), до корня
  function feoAncestorIds(id: number): number[] {
    const result: number[] = []
    let pid = feoParentMap.value[id] ?? null
    while (pid != null) {
      result.push(pid)
      pid = feoParentMap.value[pid] ?? null
    }
    return result
  }

  // Все id позиций (FeoReqItem.id), из которых складывается активная метрика
  // ('items' и 'mixed' считают позиции заявок; чистый 'nodes' — нет)
  const kpiItemIds = computed<Set<number>>(() => {
    const key = activeKpi.value
    const set = new Set<number>()
    if (!key || KPI_MODE[key] === 'nodes') return set
    for (const items of Object.values(ctx.plannedItemsByCat.value)) {
      for (const it of items) if (kpiItemMatches(key, it)) set.add(it.id)
    }
    return set
  })

  // Закупки (purchase_id), содержащие подходящие позиции — для режима «по закупкам»
  const kpiPurchaseIds = computed<Set<number>>(() => {
    const key = activeKpi.value
    const set = new Set<number>()
    if (!key || KPI_MODE[key] === 'nodes') return set
    for (const items of Object.values(ctx.plannedItemsByCat.value)) {
      for (const it of items) if (kpiItemMatches(key, it)) set.add(it.purchase_id)
    }
    return set
  })

  // Листья ФЭО, в которые слиты одноимённые позиции заявок (mergedReqByCat.matched)
  const kpiMatchedLeafIds = computed<Set<number>>(() => {
    const key = activeKpi.value
    const set = new Set<number>()
    if (!key || KPI_MODE[key] === 'nodes') return set
    for (const [leafIdStr, items] of Object.entries(ctx.mergedReqByCat.value.matched)) {
      if (items.some(it => kpiItemMatches(key, it))) set.add(Number(leafIdStr))
    }
    return set
  })

  // Категории-владельцы «виртуальных» позиций заявок (не слитых в существующий лист)
  const kpiOwnerCatIds = computed<Set<number>>(() => {
    const key = activeKpi.value
    const set = new Set<number>()
    if (!key || KPI_MODE[key] === 'nodes') return set
    if (ctx.plannedBase.value === 'purchases') {
      for (const [catIdStr, folders] of Object.entries(ctx.purchaseFoldersByCat.value)) {
        if (folders.some(f => f.items.some(it => kpiItemMatches(key, it)))) set.add(Number(catIdStr))
      }
      return set
    }
    for (const [catIdStr, groups] of Object.entries(ctx.mergedReqByCat.value.virtualByCat)) {
      if (groups.some(g => g.items.some(it => kpiItemMatches(key, it)))) set.add(Number(catIdStr))
    }
    return set
  })

  // Регресс владельца (2026-08-13): подсветка выше искала подходящие позиции ТОЛЬКО среди
  // mergedReqByCat (matched/virtualByCat) — а туда попадают лишь позиции БЕЗ привязки к плановой
  // позиции (feo_planned_item_id == null). plannedItemsByCat — источник истины: ВСЕ позиции
  // закупок категории, привязанные и нет. Категория попадает сюда, если у неё директно
  // (не у потомков — ключ карты это feo_category_id самой позиции) есть хоть одна позиция
  // под активную метрику — не важно, лист это или направление.
  const kpiPlannedOwnerCatIds = computed<Set<number>>(() => {
    const key = activeKpi.value
    const set = new Set<number>()
    if (!key || KPI_MODE[key] === 'nodes') return set
    for (const [catIdStr, items] of Object.entries(ctx.plannedItemsByCat.value)) {
      if (items.some(it => kpiItemMatches(key, it))) set.add(Number(catIdStr))
    }
    return set
  })

  // Плановые позиции (FeoPlannedItem.id), к которым привязана подходящая позиция закупки —
  // нужно раскрыть саму строку «Позиция плана» (expandedPlannedItems), иначе панель категории
  // откроется (см. kpiPlannedOwnerCatIds выше), а строка «План vs факт» под конкретной плановой
  // позицией останется свёрнутой. mergedReqByCat.linkedByPlanned уже группирует ВСЕ привязанные
  // позиции закупок по feo_planned_item_id.
  const kpiPlannedRowIds = computed<Set<number>>(() => {
    const key = activeKpi.value
    const set = new Set<number>()
    if (!key || KPI_MODE[key] === 'nodes') return set
    for (const [plannedIdStr, items] of Object.entries(ctx.mergedReqByCat.value.linkedByPlanned)) {
      if (items.some(it => kpiItemMatches(key, it))) set.add(Number(plannedIdStr))
    }
    return set
  })

  // Узлы дерева ФЭО, попадающие в метрику напрямую: режим 'nodes' (budget/free)
  // и режим 'mixed' (plan_schedule — ручные листья ФЭО, которые эндпоинт planned-purchase-items
  // вообще не видит).
  const kpiNodeIds = computed<Set<number>>(() => {
    const key = activeKpi.value
    const set = new Set<number>()
    if (!key || KPI_MODE[key] === 'items') return set
    for (const n of ctx.flattenAll(ctx.feoTree.value)) {
      if (key === 'budget' && n.budget != null) set.add(n.id)
      if (key === 'free' && Math.abs(ctx.feoFinDiff(n)) > 0.005) set.add(n.id)
      if (key === 'plan_schedule' && !n.hasChildren && ctx.feoPlannedTotalFor(n) > 0) set.add(n.id)
    }
    return set
  })

  // Что нужно раскрыть, чтобы показать состав активной метрики
  const kpiExpandTargets = computed<{ ids: Set<number>; reqItems: Set<number>; itemPanels: Set<number>; purchases: Set<number>; plannedItems: Set<number> }>(() => {
    const ids = new Set<number>()
    const reqItems = new Set<number>()
    const itemPanels = new Set<number>()
    const purchases = new Set<number>()
    const plannedItems = new Set<number>()
    if (!activeKpi.value) return { ids, reqItems, itemPanels, purchases, plannedItems }

    for (const catId of kpiOwnerCatIds.value) {
      for (const a of feoAncestorIds(catId)) ids.add(a)
      if (feoHasChildren(catId)) ids.add(catId)
      else itemPanels.add(catId)
    }
    for (const catId of kpiPlannedOwnerCatIds.value) {
      for (const a of feoAncestorIds(catId)) ids.add(a)
      itemPanels.add(catId)
      if (feoHasChildren(catId)) ids.add(catId)
    }
    for (const plannedId of kpiPlannedRowIds.value) plannedItems.add(plannedId)
    for (const leafId of kpiMatchedLeafIds.value) {
      for (const a of feoAncestorIds(leafId)) ids.add(a)
    }
    for (const nodeId of kpiNodeIds.value) {
      for (const a of feoAncestorIds(nodeId)) ids.add(a)
    }
    if (ctx.plannedBase.value === 'purchases') {
      for (const pid of kpiPurchaseIds.value) purchases.add(pid)
    }
    return { ids, reqItems, itemPanels, purchases, plannedItems }
  })

  // Одно присваивание на каждый ref — именно это даёт автосворачивание лишних папок
  function applyKpiExpansion() {
    const t = kpiExpandTargets.value
    ctx.expandedIds.value = [...t.ids]
    ctx.expandedReqItems.value = new Set(t.reqItems)
    ctx.expandedItemPanels.value = new Set(t.itemPanels)
    ctx.expandedPurchases.value = new Set(t.purchases)
    ctx.expandedPlannedItems.value = new Set(t.plannedItems)
    for (const pid of t.plannedItems) ctx.collapsedPlannedItems.value.delete(pid)
    // Панели раскрыты напрямую присваиванием (не через toggleItemPanel) — данные для новых
    // id надо подгрузить отдельно, иначе KPI-подсветка откроет пустую панель.
    for (const id of t.itemPanels) {
      if (!ctx.comparisonData.value[id] && !ctx.loadingComparison.value.has(id)) ctx.refreshComparison(id)
    }
  }

  async function scrollToFirstKpiHighlight() {
    await nextTick()
    const el = ctx.feoTableArea.value?.querySelector('.feo-kpi-hl')
    el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  function onKpiCardClick(key: KpiKey) {
    if (!ctx.selectedSubsidy.value) return
    if (activeKpi.value === key) { resetKpi(); return }
    if (activeKpi.value === null) {
      kpiSnapshot.value = {
        expandedIds: [...ctx.expandedIds.value],
        expandedReqItems: [...ctx.expandedReqItems.value],
        expandedPurchases: [...ctx.expandedPurchases.value],
        expandedItemPanels: [...ctx.expandedItemPanels.value],
        expandedPlannedItems: [...ctx.expandedPlannedItems.value],
        plannedBase: ctx.plannedBase.value,
        feoSearch: ctx.feoSearch.value,
      }
    }
    activeKpi.value = key
    ctx.feoSearch.value = '' // поиск ломает isNodeVisible (при поиске видно всё без учёта expandedIds)
    if ((KPI_MODE[key] === 'items' || KPI_MODE[key] === 'mixed') && ctx.plannedBase.value !== 'all') {
      ctx.plannedBase.value = 'all' // единственный режим, показывающий все позиции без утраты части
    }
    if (!ctx.plannedItemsLoaded.value) return // раскрытие применит watch(plannedItemsLoaded) после загрузки
    applyKpiExpansion()
    scrollToFirstKpiHighlight()
  }

  function resetKpi() {
    const snap = kpiSnapshot.value
    if (snap) {
      ctx.expandedIds.value = [...snap.expandedIds]
      ctx.expandedReqItems.value = new Set(snap.expandedReqItems)
      ctx.expandedPurchases.value = new Set(snap.expandedPurchases)
      ctx.expandedItemPanels.value = new Set(snap.expandedItemPanels)
      ctx.expandedPlannedItems.value = new Set(snap.expandedPlannedItems)
      ctx.plannedBase.value = snap.plannedBase
      ctx.feoSearch.value = snap.feoSearch
    }
    activeKpi.value = null
    kpiSnapshot.value = null
  }

  // watch(plannedBase, ...) остаётся в SubsidiesView.vue (там же, где сам ref объявлен и
  // сохраняется в localStorage) — этот watch не про KPI.
  watch(ctx.plannedItemsLoaded, (v) => {
    if (v && activeKpi.value) applyKpiExpansion()
  })
  watch(ctx.selectedId, () => {
    // узлы другой субсидии — просто гасим kpi-режим, без восстановления снапшота
    activeKpi.value = null
    kpiSnapshot.value = null
  })
  watch(ctx.feoSearch, (v) => {
    if (v && activeKpi.value) resetKpi()
  })

  function kpiCardClass(key: KpiKey): string {
    return activeKpi.value === key ? 'kpi-card--active' : ''
  }

  const kpiHasMatches = computed(() => {
    const key = activeKpi.value
    if (!key) return false
    const mode = KPI_MODE[key]
    if (mode === 'nodes') return kpiNodeIds.value.size > 0
    if (mode === 'mixed') return kpiNodeIds.value.size > 0 || kpiItemIds.value.size > 0
    return kpiItemIds.value.size > 0
  })

  // Класс строки узла дерева ФЭО (feo-tr): совпал / на пути к совпадению / ни при чём
  function kpiNodeClass(node: FeoNode): string {
    if (!activeKpi.value) return ''
    if (kpiNodeIds.value.has(node.id) || kpiMatchedLeafIds.value.has(node.id)) return 'feo-kpi-hl'
    if (kpiOwnerCatIds.value.has(node.id) || kpiPlannedOwnerCatIds.value.has(node.id)) return 'feo-kpi-path'
    const ancestors = feoAncestorIds(node.id)
    if (ancestors.some(pid => kpiOwnerCatIds.value.has(pid) || kpiPlannedOwnerCatIds.value.has(pid) || kpiMatchedLeafIds.value.has(pid) || kpiNodeIds.value.has(pid))) {
      return 'feo-kpi-path'
    }
    return 'feo-kpi-dim'
  }

  return {
    activeKpi, kpiCardClass, onKpiCardClick, resetKpi, kpiHasMatches, kpiNodeClass,
    // applyKpiExpansion — нужна watch(plannedBase) в SubsidiesView.vue (переключение
    // режима «все/ручные/из заявок/по закупкам» переприменяет текущую подсветку).
    applyKpiExpansion,
    // Наборы id — нужны kpiReqRowClass/kpiItemRowClass/kpiFolderClass, оставшимся
    // в SubsidiesView.vue (используют локальные типы дерева FeoReqRow/FeoPurchaseFolder).
    kpiItemIds,
  }
}
