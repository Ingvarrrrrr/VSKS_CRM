// Сырое состояние дерева ФЭО (категории, bulk-карты сумм с бэкенда, дерево плана
// с превышениями) + чистая структура дерева (feoTree/flattenAll/visibleFeoNodes) —
// вынесено из SubsidiesView.vue (волна 5c). loadFeo/refreshReqData/loadAll
// остаются в SubsidiesView.vue (оркестрация загрузки, читают/пишут эти же refs) —
// см. её докстринг.
//
// Module-level singleton (как useKpiDrilldown.ts) — единственный источник этих
// refs для остальных composables дерева ФЭО (useFeoTreeAmounts/useFeoTreeExcess/
// useFeoLevel5/useFeoReqItems/useFeoTreeDnd) и компонентов таблицы дерева.
import { computed, ref } from 'vue'
import type { FeoCategory, FeoNode, FeoReqItem, PlanExcessApprovalDto, PlanTreeEntry } from './types'

type ForecastEntry = { forecast: number; forecast_over: number; plan_manual: number }

let _api: ReturnType<typeof buildFeoTreeState> | null = null

interface FeoTreeStateCtx {
  expandedIds: import('vue').Ref<number[]>
}

export function useFeoTreeState(ctx: FeoTreeStateCtx) {
  if (!_api) _api = buildFeoTreeState(ctx)
  return _api
}

function buildFeoTreeState(ctx: FeoTreeStateCtx) {
  const { expandedIds } = ctx

  const feoCategories = ref<FeoCategory[]>([])
  const purchaseTotals = ref<Record<number, number>>({})
  // НЕпривязанные (feo_planned_item_id IS NULL) — см. feoPlannedRequestsFor/feoQtyRequestsFor
  // в useFeoTreeAmounts.ts, чтобы не задваивать ручной план листа (Ур.5) позициями заявок,
  // которые его уже расходуют.
  const plannedPurchaseTotals = ref<Record<number, number>>({})
  const plannedPurchaseQty = ref<Record<number, number>>({})
  // Привязанные (feo_planned_item_id IS NOT NULL) — «выбрано заявками» из плана.
  const plannedPurchaseTotalsLinked = ref<Record<number, number>>({})
  const plannedPurchaseQtyLinked = ref<Record<number, number>>({})
  // «Сверх плана» (over_plan=true, НЕпривязанные) — прибавляется к плановой сумме
  // элемента безусловно, поверх план/заказ.
  const plannedPurchaseTotalsOver = ref<Record<number, number>>({})
  const plannedPurchaseQtyOver = ref<Record<number, number>>({})
  // Прогнозное предупреждение «цена выше плановой» — только для информирования.
  const plannedPurchaseForecast = ref<Record<number, ForecastEntry>>({})
  // Единая формула «Плановой суммы»/«Планового количества» узла — числа готовые с бэкенда
  // (GET /api/feo-categories/plan-tree, см. app.services.feo_plan.compute_feo_plan_tree).
  const planTreeByCat = ref<Record<number, PlanTreeEntry>>({})
  // Детали запросов согласования превышения плана ФЭО — GET /api/plan-excess?subsidy_id=.
  const planExcessApprovals = ref<Record<number, PlanExcessApprovalDto>>({})
  // Закупки субсидии без категории ФЭО (ни у самой закупки, ни у одной позиции) — деньги
  // есть (влияют на KPI), но в дереве ФЭО не видны, т.к. дерево строится по категориям.
  const unassignedFeo = ref<{ amount: number; purchase_count: number; purchase_ids: number[] }>({
    amount: 0, purchase_count: 0, purchase_ids: [],
  })
  // Позиции «из заявок» (Таблица B), bulk-загружены на всю субсидию сразу — см.
  // useFeoReqItems.ts (mergedReqByCat/purchaseFoldersByCat читают этот же ref).
  const plannedItemsByCat = ref<Record<number, FeoReqItem[]>>({})
  const plannedItemsLoaded = ref(false)

  const feoSearch = ref('')

  // GET /plan-tree отдаёт "unassigned" как ДОПОЛНИТЕЛЬНЫЙ ключ рядом с числовыми id категорий —
  // вычленяем его в unassignedFeo, а planTreeByCat остаётся чистым Record<number, ...>.
  function splitPlanTree(raw: Record<string, any>): Record<number, PlanTreeEntry> {
    const { unassigned, ...rest } = raw || {}
    unassignedFeo.value = unassigned && typeof unassigned === 'object'
      ? { amount: Number(unassigned.amount || 0), purchase_count: Number(unassigned.purchase_count || 0), purchase_ids: unassigned.purchase_ids || [] }
      : { amount: 0, purchase_count: 0, purchase_ids: [] }
    return rest as Record<number, PlanTreeEntry>
  }

  // ФИКС (замер на проде 2026-08-13): связи (children/hasChildren/roots) строятся отдельным
  // первым проходом, а depth — вторым проходом обходом уже готового дерева от корней, поэтому
  // не зависит от порядка элементов в исходном списке (см. подробный комментарий в истории
  // SubsidiesView.vue до разбиения).
  const feoTree = computed<FeoNode[]>(() => {
    const cats = feoCategories.value
    const byId: Record<number, FeoNode> = {}
    cats.forEach(c => { byId[c.id] = { ...c, depth: 0, hasChildren: false, children: [] } })
    const roots: FeoNode[] = []
    cats.forEach(c => {
      const node = byId[c.id]!
      const parent = c.parent_id ? byId[c.parent_id] : undefined
      if (parent) {
        parent.children.push(node)
        parent.hasChildren = true
      } else {
        roots.push(node)
      }
    })
    const visited = new Set<number>()
    const assignDepth = (node: FeoNode, depth: number) => {
      if (visited.has(node.id)) return
      visited.add(node.id)
      node.depth = depth
      node.children.forEach(child => assignDepth(child, depth + 1))
    }
    roots.forEach(r => assignDepth(r, 0))
    return roots
  })

  function flattenAll(nodes: FeoNode[]): FeoNode[] {
    return nodes.flatMap(n => [n, ...flattenAll(n.children)])
  }

  function isNodeVisible(node: FeoNode): boolean {
    if (feoSearch.value) return true  // при поиске все найденные видны
    if (!node.parent_id) return true
    const checkParent = (pid: number): boolean => {
      if (!expandedIds.value.includes(pid)) return false
      const p = feoCategories.value.find(c => c.id === pid)
      return !p?.parent_id || checkParent(p.parent_id)
    }
    return checkParent(node.parent_id)
  }

  const visibleFeoNodes = computed(() => {
    const q = feoSearch.value.toLowerCase()
    const all = flattenAll(feoTree.value)
    if (q) return all.filter(n => n.name.toLowerCase().includes(q) || (n.code ?? '').toLowerCase().includes(q))
    // Фильтр по видимости предков стоит в источнике списка (не только на основной строке
    // узла) — иначе при сворачивании родителя дочерние блоки (панель плана, папки закупок)
    // оставались бы висеть на экране.
    return all.filter(isNodeVisible)
  })

  return {
    feoCategories, purchaseTotals,
    plannedPurchaseTotals, plannedPurchaseQty, plannedPurchaseTotalsLinked, plannedPurchaseQtyLinked,
    plannedPurchaseTotalsOver, plannedPurchaseQtyOver, plannedPurchaseForecast,
    planTreeByCat, planExcessApprovals, unassignedFeo,
    plannedItemsByCat, plannedItemsLoaded, feoSearch,
    splitPlanTree, feoTree, flattenAll, isNodeVisible, visibleFeoNodes,
  }
}
