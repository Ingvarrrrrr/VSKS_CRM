// Позиции «из заявок» как узлы дерева ФЭО (после поддерева владельца) — слияние
// с ручными дочерними позициями, группировка по категории/виду, режим «по
// закупкам» (папки без слияния). Вынесено из SubsidiesView.vue (волна 5c) —
// единственный источник этой логики (Правило №6); FeoReqItemsRows.vue/
// FeoByPurchasesRows.vue/FeoTreeRow.vue читают/вызывают через ctx.
//
// Module-level singleton (как useKpiDrilldown.ts).
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import type { Router } from 'vue-router'
import { normName } from './feoCategoryUtils'
import { PURCHASE_STATUS_META, PURCHASE_STATUS_ORDER } from '@/constants/purchaseStatus'
import type {
  FeoActualItem, FeoNode, FeoPlannedItem, FeoPurchaseFolder, FeoReqItem, FeoReqRow, FeoStage,
  FeoVirtualGroup, PlannedBase,
} from './types'

interface FeoReqItemsCtx {
  router: Router
  feoTree: ComputedRef<FeoNode[]>
  flattenAll: (nodes: FeoNode[]) => FeoNode[]
  visibleFeoNodes: ComputedRef<FeoNode[]>
  isNodeVisible: (node: FeoNode) => boolean
  plannedItemsByCat: Ref<Record<number, FeoReqItem[]>>
  plannedBase: Ref<PlannedBase>
  feoItemsGroupBy: Ref<'none' | 'category' | 'category_type'>
  expandedIds: Ref<number[]>
  expandedReqItems: Ref<Set<number>>
  comparisonData: Ref<Record<number, { planned: FeoPlannedItem[]; actual: FeoActualItem[] }>>
  ensureComparison: (catId: number) => Promise<void>
  openReqItemEdit: (node: FeoNode, item: FeoReqItem) => void
  confirmReqItemDelete: (node: FeoNode, item: FeoReqItem) => void
  openMapDialog: (actual: FeoActualItem, categoryId: number) => void
}

let _api: ReturnType<typeof buildFeoReqItems> | null = null

export function useFeoReqItems(ctx: FeoReqItemsCtx) {
  if (!_api) _api = buildFeoReqItems(ctx)
  return _api
}

function buildFeoReqItems(ctx: FeoReqItemsCtx) {
  const {
    router, feoTree, flattenAll, visibleFeoNodes, isNodeVisible, plannedItemsByCat, plannedBase, feoItemsGroupBy,
    expandedIds, expandedReqItems, comparisonData, ensureComparison,
    openReqItemEdit, confirmReqItemDelete, openMapDialog,
  } = ctx

  // Уникальные статусы товаров виртуальной группы, отсортированные по жизненному циклу закупки
  function groupStatuses(g: FeoVirtualGroup): { status: string; count: number; label: string }[] {
    const counts = new Map<string, number>()
    for (const it of g.items) counts.set(it.purchase_status, (counts.get(it.purchase_status) || 0) + 1)
    return PURCHASE_STATUS_ORDER
      .filter(s => counts.has(s))
      .map(s => ({ status: s, count: counts.get(s)!, label: PURCHASE_STATUS_META[s]?.label ?? s }))
  }

  function feoStoppedLine(row: { stopped_by_name?: string | null; stopped_at?: string | null }): string {
    const who = row.stopped_by_name || 'неизвестно кем'
    const when = row.stopped_at ? new Date(row.stopped_at).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' }) : ''
    return `остановлена ${who}${when ? ', ' + when : ''}`
  }
  function purchaseFolderTitle(f: FeoPurchaseFolder): string {
    return 'Закупка ' + (f.registry_number || (f.purchase_number != null ? '№ ' + f.purchase_number : '#' + f.purchase_id))
  }

  // Слияние: позиции заявок ↔ ручные дочерние позиции ФЭО (сопоставление по имени листа).
  const mergedReqByCat = computed(() => {
    const matched: Record<number, FeoReqItem[]> = {}
    const virtualByCat: Record<number, FeoVirtualGroup[]> = {}
    // Позиции, привязанные к плановой позиции (feo_planned_item_id) — расходуют план Ур.5,
    // а не складываются с ним поверх.
    const linkedByPlanned: Record<number, FeoReqItem[]> = {}
    const byId: Record<number, FeoNode> = {}
    for (const n of flattenAll(feoTree.value)) byId[n.id] = n
    for (const [catIdStr, items] of Object.entries(plannedItemsByCat.value)) {
      const catId = Number(catIdStr)
      const node = byId[catId]
      const leafByName: Record<string, number> = {}
      for (const ch of node?.children || []) {
        if (!ch.hasChildren) leafByName[normName(ch.name)] = ch.id
      }
      const groups = new Map<string, FeoVirtualGroup>()
      for (const it of items || []) {
        if (it.feo_planned_item_id != null) {
          ;(linkedByPlanned[it.feo_planned_item_id] ||= []).push(it)
          continue
        }
        const key = normName(it.item_name)
        const childId = leafByName[key]
        if (childId != null) {
          ;(matched[childId] ||= []).push(it)
          continue
        }
        let g = groups.get(key)
        if (!g) {
          g = { name: it.item_name, unit: it.unit, qty: 0, total: 0, category: it.category, product_type: it.product_type, items: [] }
          groups.set(key, g)
        }
        g.qty = Math.round((g.qty + Number(it.quantity || 0)) * 10000) / 10000
        g.total += Number(it.total_price || 0)
        if (!g.unit && it.unit) g.unit = it.unit
        g.items.push(it)
      }
      const list = [...groups.values()]
      if (list.length) virtualByCat[catId] = list
    }
    return { matched, virtualByCat, linkedByPlanned }
  })

  // Все позиции заявок сгруппированные по cat (без исключения matched) — для режима 'requests'.
  const allReqGroupsByCat = computed<Record<number, FeoVirtualGroup[]>>(() => {
    const result: Record<number, FeoVirtualGroup[]> = {}
    for (const [catIdStr, items] of Object.entries(plannedItemsByCat.value)) {
      const catId = Number(catIdStr)
      const groups = new Map<string, FeoVirtualGroup>()
      for (const it of items || []) {
        const key = normName(it.item_name)
        let g = groups.get(key)
        if (!g) {
          g = { name: it.item_name, unit: it.unit, qty: 0, total: 0, category: it.category, product_type: it.product_type, items: [] }
          groups.set(key, g)
        }
        g.qty = Math.round((g.qty + Number(it.quantity || 0)) * 10000) / 10000
        g.total += Number(it.total_price || 0)
        if (!g.unit && it.unit) g.unit = it.unit
        g.items.push(it)
      }
      const list = [...groups.values()]
      if (list.length) result[catId] = list
    }
    return result
  })

  const purchaseFoldersByCat = computed<Record<number, FeoPurchaseFolder[]>>(() => {
    const res: Record<number, FeoPurchaseFolder[]> = {}
    for (const [catIdStr, items] of Object.entries(plannedItemsByCat.value)) {
      const byPid = new Map<number, FeoPurchaseFolder>()
      for (const it of items || []) {
        let f = byPid.get(it.purchase_id)
        if (!f) {
          f = { purchase_id: it.purchase_id, purchase_number: it.purchase_number, registry_number: it.registry_number, purchase_status: it.purchase_status, wish_id: it.wish_id, qty: 0, unit: it.unit, total: 0, items: [], stopped_at: it.stopped_at, stopped_by_name: it.stopped_by_name }
          byPid.set(it.purchase_id, f)
        }
        f.qty = Math.round((f.qty + Number(it.quantity || 0)) * 10000) / 10000
        f.total += Number(it.total_price || 0)
        if (f.unit !== it.unit) f.unit = null
        f.items.push(it)
      }
      const list = [...byPid.values()].sort((a, b) => (a.registry_number || String(a.purchase_number ?? a.purchase_id)).localeCompare(b.registry_number || String(b.purchase_number ?? b.purchase_id), 'ru'))
      if (list.length) res[Number(catIdStr)] = list
    }
    return res
  })
  function purchaseFoldersFor(node: FeoNode): FeoPurchaseFolder[] {
    return purchaseFoldersByCat.value[node.id] || []
  }

  function matchedReqFor(node: FeoNode): FeoReqItem[] {
    return mergedReqByCat.value.matched[node.id] || []
  }
  function virtualGroupsFor(node: FeoNode): FeoVirtualGroup[] {
    if (plannedBase.value === 'requests') return allReqGroupsByCat.value[node.id] || []
    return mergedReqByCat.value.virtualByCat[node.id] || []
  }

  // Снимок ТЗ (правка «план ≠ факт», Шаг 5, п.1): заморожен с момента объявления закупки,
  // фолбэк на текущие quantity/total_price для старых записей без снимка.
  function groupPlannedQty(g: FeoVirtualGroup): number {
    return Math.round(g.items.reduce((s, it) => s + Number(it.planned_quantity ?? it.quantity ?? 0), 0) * 10000) / 10000
  }
  function groupPlannedTotal(g: FeoVirtualGroup): number {
    return g.items.reduce((s, it) => s + Number(it.planned_total ?? it.total_price ?? 0), 0)
  }
  function groupFactTotal(g: FeoVirtualGroup): number | null {
    const withFact = g.items.filter(it => it.fact_amount != null)
    if (!withFact.length) return null
    return withFact.reduce((s, it) => s + Number(it.fact_amount || 0), 0)
  }
  function matchedReqQty(node: FeoNode): number {
    return Math.round(matchedReqFor(node).reduce((s, x) => s + Number(x.quantity || 0), 0) * 10000) / 10000
  }
  function matchedReqTotal(node: FeoNode): number {
    return matchedReqFor(node).reduce((s, x) => s + Number(x.total_price || 0), 0)
  }

  // Раскрыт ли узел для показа виртуальных позиций из заявок.
  function reqExpandedFor(node: FeoNode): boolean {
    return node.hasChildren ? expandedIds.value.includes(node.id) : expandedReqItems.value.has(node.id)
  }
  function ownerReqRowCount(n: FeoNode): number {
    if (plannedBase.value === 'manual') return 0
    return plannedBase.value === 'purchases' ? purchaseFoldersFor(n).length : virtualGroupsFor(n).length
  }

  // Карта: после какой строки дерева (последний узел поддерева) рисовать виртуальные позиции
  // владельца (ШАГ 1 плана дедупликации дерева ФЭО, 2026-08-07): листья исключены —
  // их позиции уже показаны в Таблице A (панель Level 5).
  const reqOwnersAfter = computed<Record<number, FeoNode[]>>(() => {
    const map: Record<number, FeoNode[]> = {}
    const all = visibleFeoNodes.value
    for (let i = all.length - 1; i >= 0; i--) {
      const n = all[i]!
      if (!n.hasChildren || !ownerReqRowCount(n) || !reqExpandedFor(n) || !isNodeVisible(n)) continue
      let j = i
      while (j + 1 < all.length && all[j + 1]!.depth > n.depth) j++
      ;(map[all[j]!.id] ||= []).push(n)
    }
    return map
  })

  function reqItemRowsFor(node: FeoNode): FeoReqRow[] {
    const groupsList = virtualGroupsFor(node)
    const mode = feoItemsGroupBy.value
    const groupRowOf = (g: FeoVirtualGroup): FeoReqRow =>
      ({ key: `g-${normName(g.name)}`, header: '', level: 0, count: g.items.length, sumQty: g.qty, sum: g.total, group: g, items: g.items })
    if (mode === 'none') {
      return [...groupsList].sort((a, b) => a.name.localeCompare(b.name, 'ru')).map(groupRowOf)
    }
    const sorted = [...groupsList].sort((a, b) =>
      a.category.localeCompare(b.category, 'ru')
      || a.product_type.localeCompare(b.product_type, 'ru')
      || a.name.localeCompare(b.name, 'ru'))
    const rows: FeoReqRow[] = []
    let curCat: string | null = null
    let curType: string | null = null
    const headerRow = (key: string, header: string, level: number, grp: FeoVirtualGroup[]): FeoReqRow => ({
      key, header, level,
      count: grp.reduce((s, x) => s + x.items.length, 0),
      sumQty: Math.round(grp.reduce((s, x) => s + x.qty, 0) * 10000) / 10000,
      sum: grp.reduce((s, x) => s + x.total, 0),
      group: null,
      items: grp.flatMap(x => x.items),
    })
    for (const g of sorted) {
      if (g.category !== curCat) {
        curCat = g.category
        curType = null
        rows.push(headerRow(`c-${curCat}`, curCat, 1, sorted.filter(x => x.category === curCat)))
      }
      if (mode === 'category_type' && g.product_type !== curType) {
        curType = g.product_type
        rows.push(headerRow(`c-${curCat}-t-${curType}`, curType, 2,
          sorted.filter(x => x.category === curCat && x.product_type === curType)))
      }
      rows.push(groupRowOf(g))
    }
    return rows
  }

  function reqRowIndent(node: FeoNode, row: FeoReqRow): string {
    const extra = row.group
      ? (feoItemsGroupBy.value === 'none' ? 0 : feoItemsGroupBy.value === 'category' ? 1 : 2)
      : row.level - 1
    return `${(node.depth + 1 + extra) * 20 + 8}px`
  }

  // ── Панель источников виртуальной позиции «план vs факт» + правка/удаление ──
  const expandedReqItemPanels = ref<Set<string>>(new Set())
  function reqPanelKey(node: FeoNode, g: FeoVirtualGroup): string {
    return `${node.id}|${normName(g.name)}`
  }
  function toggleReqItemPanel(node: FeoNode, g: FeoVirtualGroup) {
    const key = reqPanelKey(node, g)
    if (expandedReqItemPanels.value.has(key)) {
      expandedReqItemPanels.value.delete(key)
      return
    }
    expandedReqItemPanels.value.add(key)
    ensureComparison(node.id)
  }
  function openReqItemPanel(node: FeoNode, g: FeoVirtualGroup) {
    expandedReqItemPanels.value.add(reqPanelKey(node, g))
    ensureComparison(node.id)
  }
  function virtGroupPurchaseIds(g: FeoVirtualGroup): number[] {
    return [...new Set(g.items.map(i => i.purchase_id))]
  }
  function virtCart(node: FeoNode, g: FeoVirtualGroup) {
    const ids = virtGroupPurchaseIds(g)
    if (ids.length === 1) router.push(`/orders/${ids[0]}`)
    else openReqItemPanel(node, g)
  }
  function virtEdit(node: FeoNode, g: FeoVirtualGroup) {
    if (g.items.length === 1) openReqItemEdit(node, g.items[0]!)
    else openReqItemPanel(node, g)
  }
  function virtDelete(node: FeoNode, g: FeoVirtualGroup) {
    if (g.items.length === 1) confirmReqItemDelete(node, g.items[0]!)
    else openReqItemPanel(node, g)
  }

  function reqItemActual(catId: number, itemId: number): FeoActualItem | null {
    return comparisonData.value[catId]?.actual.find(a => a.purchase_item_id === itemId) || null
  }
  // Стадии позиции «из заявок» (matchedReqFor) — сама FeoReqItem их не содержит, но одна и та
  // же позиция закупки, как правило, приходит и в comparisonData.actual, где бэкенд уже
  // проставил stages.
  function stagesForReqItem(catId: number, itemId: number): FeoStage[] {
    return reqItemActual(catId, itemId)?.stages || []
  }
  function reqItemPlanned(catId: number, itemId: number): FeoPlannedItem | null {
    const a = reqItemActual(catId, itemId)
    if (!a?.feo_planned_item_id) return null
    return comparisonData.value[catId]?.planned.find(p => p.id === a.feo_planned_item_id) || null
  }
  function mapReqItem(node: FeoNode, item: FeoReqItem) {
    const a = reqItemActual(node.id, item.id)
    if (a) openMapDialog(a, node.id)
  }

  return {
    feoStoppedLine, purchaseFolderTitle,
    mergedReqByCat, allReqGroupsByCat, purchaseFoldersByCat, purchaseFoldersFor,
    matchedReqFor, virtualGroupsFor, groupPlannedQty, groupPlannedTotal, groupFactTotal,
    matchedReqQty, matchedReqTotal, reqExpandedFor, ownerReqRowCount, reqOwnersAfter,
    reqItemRowsFor, reqRowIndent,
    expandedReqItemPanels, reqPanelKey, toggleReqItemPanel, openReqItemPanel,
    virtGroupPurchaseIds, virtCart, virtEdit, virtDelete,
    reqItemActual, stagesForReqItem, reqItemPlanned, mapReqItem,
    groupStatuses,
  }
}
