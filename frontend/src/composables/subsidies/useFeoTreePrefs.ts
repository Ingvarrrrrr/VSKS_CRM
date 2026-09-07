// Настройки отображения дерева ФЭО (persist в localStorage) + раскрытые
// узлы/панели — вынесено из SubsidiesView.vue (волна 5c). Единственный источник
// этого состояния: FeoTreeTable.vue/FeoTreeRow.vue/FeoLevel5Panel.vue/
// FeoReqItemsRows.vue и usePlannedItems.ts читают/пишут ЭТИ ЖЕ refs через ctx
// (Правило №6), не заводят копий.
//
// Module-level singleton state (как useKpiDrilldown.ts/usePlanGraphVersions.ts
// в этом же проекте) — SubsidiesView.vue вызывает useFeoTreePrefs() один раз и
// прокидывает результат в остальные composables дерева ФЭО через их ctx-параметры.
import { ref, watch } from 'vue'
import type { FeoDisplayPrefs, PlannedBase } from './types'

const FEO_DISPLAY_PREFS_KEY = 'subsidies_feo_display_prefs'

function loadFeoDisplayPrefs(): FeoDisplayPrefs {
  try {
    const raw = localStorage.getItem(FEO_DISPLAY_PREFS_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

let _api: ReturnType<typeof buildFeoTreePrefs> | null = null

export function useFeoTreePrefs() {
  if (!_api) _api = buildFeoTreePrefs()
  return _api
}

function buildFeoTreePrefs() {
  const feoDisplayPrefs = loadFeoDisplayPrefs()

  const expandedIds = ref<number[]>(feoDisplayPrefs.expandedIds || [])
  const expandedReqItems = ref<Set<number>>(new Set(feoDisplayPrefs.expandedReqItems || []))
  const expandedItemPanels = ref<Set<number>>(new Set(feoDisplayPrefs.expandedItemPanels || []))
  // Возвращено из отката e0db76a (план zany-fluttering-mountain.md, п.4): строка плана
  // раскрыта по умолчанию, если под ней есть закупка (см. applyDefaultPlannedExpansion в
  // useFeoLevel5.ts) — но явное решение пользователя СВЕРНУТЬ строку обязано пережить
  // перезагрузку и не быть перезаписано дефолтом. collapsedPlannedItems — id, которые
  // пользователь ЯВНО свернул кликом по шеврону (см. togglePlannedItemFolder ниже) —
  // единственный признак с приоритетом над дефолтом.
  const expandedPlannedItems = ref<Set<number>>(new Set(feoDisplayPrefs.expandedPlannedItems || []))
  const collapsedPlannedItems = ref<Set<number>>(new Set(feoDisplayPrefs.collapsedPlannedItems || []))
  const feoItemsGroupBy = ref<'none' | 'category' | 'category_type'>(feoDisplayPrefs.feoItemsGroupBy || 'none')
  // Режим колонок «Плановая сумма»/«Плановое кол-во» — единый синхронный переключатель.
  const plannedBase = ref<PlannedBase>(feoDisplayPrefs.plannedBase || 'all')
  const plannedSumBase = plannedBase
  const plannedQtyBase = plannedBase

  // НЕ персистятся (не входят в FeoDisplayPrefs) — как и в исходном файле.
  const expandedPurchases = ref<Set<number>>(new Set())
  const expandedStageRows = ref<Set<string>>(new Set())
  const residualBase = ref<'plan' | 'feo'>('plan')

  function toggleExpand(id: number) {
    const idx = expandedIds.value.indexOf(id)
    if (idx >= 0) {
      expandedIds.value.splice(idx, 1)
    } else {
      expandedIds.value.push(id)
    }
  }

  function togglePurchaseFolder(pid: number) {
    if (expandedPurchases.value.has(pid)) expandedPurchases.value.delete(pid)
    else expandedPurchases.value.add(pid)
  }

  function togglePlannedItemFolder(plannedId: number) {
    if (expandedPlannedItems.value.has(plannedId)) {
      expandedPlannedItems.value.delete(plannedId)
      collapsedPlannedItems.value.add(plannedId)
    } else {
      expandedPlannedItems.value.add(plannedId)
      collapsedPlannedItems.value.delete(plannedId)
    }
  }

  function toggleStageRow(key: string) {
    if (expandedStageRows.value.has(key)) expandedStageRows.value.delete(key)
    else expandedStageRows.value.add(key)
  }

  // Сохранение настроек отображения дерева ФЭО — единая точка на все семь настроек,
  // deep:true нужен, т.к. expandedIds/expandedReqItems/expandedItemPanels/
  // expandedPlannedItems/collapsedPlannedItems мутируются на месте (push/add/delete),
  // а не переприсваиваются.
  function saveFeoDisplayPrefs() {
    try {
      localStorage.setItem(FEO_DISPLAY_PREFS_KEY, JSON.stringify({
        plannedBase: plannedBase.value,
        feoItemsGroupBy: feoItemsGroupBy.value,
        expandedIds: expandedIds.value,
        expandedReqItems: [...expandedReqItems.value],
        expandedItemPanels: [...expandedItemPanels.value],
        expandedPlannedItems: [...expandedPlannedItems.value],
        collapsedPlannedItems: [...collapsedPlannedItems.value],
      } satisfies FeoDisplayPrefs))
    } catch {
      // localStorage недоступен (приватный режим и т.п.) — не критично, просто не персистим
    }
  }
  watch(
    [plannedBase, feoItemsGroupBy, expandedIds, expandedReqItems, expandedItemPanels, expandedPlannedItems, collapsedPlannedItems],
    saveFeoDisplayPrefs,
    { deep: true },
  )

  return {
    expandedIds, expandedReqItems, expandedItemPanels, expandedPlannedItems, collapsedPlannedItems,
    expandedPurchases, expandedStageRows,
    feoItemsGroupBy, plannedBase, plannedSumBase, plannedQtyBase, residualBase,
    toggleExpand, togglePurchaseFolder, togglePlannedItemFolder, toggleStageRow,
  }
}
