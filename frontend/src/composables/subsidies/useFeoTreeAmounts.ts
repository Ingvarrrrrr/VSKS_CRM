// Формулы дерева ФЭО: финансирование по ФЭО / плановое количество / плановая
// сумма / «в плане-графике» / остаток по каждому узлу, плюс итоговая строка
// дерева и synFeoFilled — вынесено из SubsidiesView.vue (волна 5c). Единственный
// источник этих формул (Правило №6) — FeoTreeRow.vue/FeoTreeTable.vue и
// useFeoReqItems.ts/useFeoLevel5.ts читают их через ctx, не считают заново.
//
// Module-level singleton (как useKpiDrilldown.ts).
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import type { FeoNode, FeoReqItem, PlanTreeEntry, SubsidyRow } from './types'
import { formatCurrency as fmtLocal } from './format'

interface FeoTreeAmountsCtx {
  purchaseTotals: Ref<Record<number, number>>
  plannedPurchaseTotals: Ref<Record<number, number>>
  plannedPurchaseQty: Ref<Record<number, number>>
  plannedPurchaseTotalsLinked: Ref<Record<number, number>>
  plannedPurchaseQtyLinked: Ref<Record<number, number>>
  plannedPurchaseTotalsOver: Ref<Record<number, number>>
  plannedPurchaseQtyOver: Ref<Record<number, number>>
  plannedPurchaseForecast: Ref<Record<number, { forecast: number; forecast_over: number; plan_manual: number }>>
  planTreeByCat: Ref<Record<number, PlanTreeEntry>>
  plannedItemsByCat: Ref<Record<number, FeoReqItem[]>>
  feoTree: ComputedRef<FeoNode[]>
  plannedBase: Ref<'all' | 'manual' | 'requests' | 'purchases'>
  selectedSubsidy: ComputedRef<SubsidyRow | null>
  allSubsidies: Ref<SubsidyRow[]>
  selectedId: Ref<number | null>
}

let _api: ReturnType<typeof buildFeoTreeAmounts> | null = null

export function useFeoTreeAmounts(ctx: FeoTreeAmountsCtx) {
  if (!_api) _api = buildFeoTreeAmounts(ctx)
  return _api
}

function buildFeoTreeAmounts(ctx: FeoTreeAmountsCtx) {
  const {
    purchaseTotals,
    plannedPurchaseTotals, plannedPurchaseQty, plannedPurchaseTotalsLinked, plannedPurchaseQtyLinked,
    plannedPurchaseTotalsOver, plannedPurchaseQtyOver, plannedPurchaseForecast,
    planTreeByCat, plannedItemsByCat, feoTree, plannedBase, selectedSubsidy, allSubsidies, selectedId,
  } = ctx
  const plannedSumBase = plannedBase
  const plannedQtyBase = plannedBase

  // База остатка: от плановой суммы или от финансирования по ФЭО
  const residualBase = ref<'plan' | 'feo'>('plan')

  // ── Финансирование ФЭО ───────────────────────────
  function feoBudgetFor(node: FeoNode): number {
    return node.budget != null ? Number(node.budget) : 0
  }

  function feoEffectiveFor(node: FeoNode): number {
    if (node.budget != null) return Number(node.budget)
    if (!node.hasChildren) {
      const fact = purchaseTotals.value[node.id] || 0
      return fact > 0 ? fact : feoPlannedTotalFor(node)
    }
    return node.children.reduce((acc, child) => acc + feoEffectiveFor(child), 0)
  }

  function manualChildFeoSum(node: FeoNode): number {
    const walk = (n: FeoNode): number =>
      Number(n.budget) > 0 ? Number(n.budget) : n.children.reduce((a, c) => a + walk(c), 0)
    return node.children.reduce((a, c) => a + walk(c), 0)
  }

  function hasManualChildFeo(node: FeoNode): boolean {
    const walk = (n: FeoNode): boolean => Number(n.budget) > 0 || n.children.some(walk)
    return node.children.some(walk)
  }

  function isAutoNode(node: FeoNode): boolean {
    if (!node.hasChildren) return false
    return node.budget == null
  }

  function feoRollup(node: FeoNode): { qty: number | null; qtyAuto: boolean; amount: number | null; amountAuto: boolean } {
    const ownQty = node.feo_quantity != null ? Number(node.feo_quantity) : null
    const ownAmt = node.feo_amount != null ? Number(node.feo_amount) : null
    if (ownQty != null || ownAmt != null) {
      return { qty: ownQty, qtyAuto: false, amount: ownAmt, amountAuto: false }
    }
    if (!node.hasChildren) return { qty: null, qtyAuto: false, amount: null, amountAuto: false }
    let sumQty = 0; let hasQty = false
    let sumAmt = 0; let hasAmt = false
    const walkChildren = (children: FeoNode[]) => {
      for (const c of children) {
        const r = feoRollup(c)
        if (r.qty != null) { sumQty += r.qty; hasQty = true }
        if (r.amount != null) { sumAmt += r.amount; hasAmt = true }
      }
    }
    walkChildren(node.children)
    return {
      qty: hasQty ? sumQty : null, qtyAuto: hasQty,
      amount: hasAmt ? sumAmt : null, amountAuto: hasAmt,
    }
  }

  function feoPurchasedFor(node: FeoNode): number {
    if (!node.hasChildren) {
      return purchaseTotals.value[node.id] || 0
    }
    return node.children.reduce((acc, child) => acc + feoPurchasedFor(child), 0)
  }

  function feoFactFor(node: FeoNode): number {
    return planTreeByCat.value[node.id]?.fact || 0
  }

  function feoResidualBaseFor(node: FeoNode): number {
    return residualBase.value === 'feo' ? feoEffectiveFor(node) : feoPlannedDisplayFor(node)
  }

  function feoResidualFor(node: FeoNode): number {
    return feoResidualBaseFor(node) - feoInPlanScheduleFor(node)
  }

  function feoDisplayedFor(node: FeoNode): number {
    if (node.budget != null) return Number(node.budget)
    return node.hasChildren ? feoEffectiveFor(node) : 0
  }

  function feoFinDiff(node: FeoNode): number {
    return feoDisplayedFor(node) - feoPlannedDisplayFor(node)
  }

  function feoRemainingWithPurchasesNote(node: FeoNode): string | null {
    if (residualBase.value === 'feo') return null
    if (feoFinDiff(node) <= 0.005) return null
    const note = feoResidualNoteFor(node) || feoPlanConsumedNoteFor(node)
    if (!note || note.residual >= -0.005) return null
    const remaining = feoDisplayedFor(node) - note.consumed
    return `с учётом уже размещённых закупок (${fmtLocal(note.consumed)}) до потолка ФЭО реально остаётся ${fmtLocal(remaining)}`
  }

  function feoIsOverBudget(node: FeoNode): boolean {
    return feoDisplayedFor(node) > 0 && feoFinDiff(node) < -0.005
  }

  function feoChildrenBudgetDiff(node: FeoNode): number {
    if (!node.hasChildren || node.budget == null || node.budget <= 0) return 0
    if (!hasManualChildFeo(node)) return 0
    return manualChildFeoSum(node) - node.budget
  }

  // Для каждого узла — потомки (любой глубины), у которых feoIsOverBudget === true.
  interface FeoOverspentInfo { names: string[]; count: number }
  const feoOverspentDescendantMap = computed<Map<number, FeoOverspentInfo>>(() => {
    const map = new Map<number, FeoOverspentInfo>()
    function walk(node: FeoNode): string[] {
      let names: string[] = []
      for (const child of node.children) {
        if (feoIsOverBudget(child)) names.push(child.name)
        names = names.concat(walk(child))
      }
      map.set(node.id, { names, count: names.length })
      return names
    }
    for (const root of feoTree.value) walk(root)
    return map
  })

  function feoHasOverspentDescendant(node: FeoNode): boolean {
    return (feoOverspentDescendantMap.value.get(node.id)?.count ?? 0) > 0
  }

  function feoOverspentDescendantText(node: FeoNode): string {
    const info = feoOverspentDescendantMap.value.get(node.id)
    if (!info || info.count === 0) return ''
    if (info.count === 1) return `подкатегория «${info.names[0]}» превышает лимит`
    return 'одна из подкатегорий превышает лимит'
  }

  function feoOverspentDescendantTitle(node: FeoNode): string {
    const info = feoOverspentDescendantMap.value.get(node.id)
    if (!info || info.count === 0) return ''
    const shown = info.names.slice(0, 3)
    const suffix = info.count > 3 ? ` и ещё ${info.count - 3}` : ''
    const verb = info.count === 1 ? 'Превышает' : 'Превышают'
    return `${verb} лимит ФЭО: ${shown.join(', ')}${suffix}`
  }

  // ── Плановое количество ───────────────────────────
  function feoQtyFor(node: FeoNode): number {
    if (!node.hasChildren) {
      if (node.planned_quantity != null) return Number(node.planned_quantity)
      const t = planTreeByCat.value[node.id]
      if (t && t.qty_plan != null) return Number(t.qty_plan)
      return 0
    }
    if (node.planned_quantity != null) return Number(node.planned_quantity)
    return node.children.reduce((acc, child) => acc + feoQtyFor(child), 0)
  }

  function isAutoQtyNode(node: FeoNode): boolean {
    if (!node.hasChildren) return false
    return node.planned_quantity == null
  }

  function feoQtyRequestsFor(node: FeoNode): number {
    const own = plannedPurchaseQty.value[node.id] || 0
    if (!node.hasChildren) return own
    return own + node.children.reduce((acc, child) => acc + feoQtyRequestsFor(child), 0)
  }

  function feoQtyConsumedFor(node: FeoNode): number {
    const own = plannedPurchaseQtyLinked.value[node.id] || 0
    if (!node.hasChildren) return own
    return own + node.children.reduce((acc, child) => acc + feoQtyConsumedFor(child), 0)
  }

  function feoQtyOverFor(node: FeoNode): number {
    const own = plannedPurchaseQtyOver.value[node.id] || 0
    if (!node.hasChildren) return own
    return own + node.children.reduce((acc, child) => acc + feoQtyOverFor(child), 0)
  }

  function feoQtyDisplayRaw(node: FeoNode): number {
    return planTreeByCat.value[node.id]?.display_quantity || 0
  }

  function feoQtyDisplayFor(node: FeoNode): number {
    if (plannedQtyBase.value === 'manual') return feoQtyFor(node)
    if (plannedQtyBase.value === 'purchases') return feoQtyFor(node) + feoQtyRequestsFor(node) + feoQtyConsumedFor(node) + feoQtyOverFor(node)
    if (plannedQtyBase.value === 'requests') {
      return feoQtyRequestsFor(node) + feoQtyConsumedFor(node) + feoQtyOverFor(node) + (!node.hasChildren ? matchedReqQtyRef.value(node) : 0)
    }
    return feoQtyDisplayRaw(node)
  }

  function mergedQtyDiff(node: FeoNode): number {
    if (!mergedManualPriority(node) || node.feo_quantity == null) return 0
    const total = feoQtyFor(node) + matchedReqQtyRef.value(node) + feoQtyRequestsFor(node)
    return Math.round((total - Number(node.feo_quantity)) * 10000) / 10000
  }

  // ── Плановая сумма ────────────────────────────────
  function feoAmtFor(node: FeoNode): number {
    if (!node.hasChildren) return node.planned_amount != null ? Number(node.planned_amount) : 0
    if (node.planned_amount != null) return Number(node.planned_amount)
    return node.children.reduce((acc, child) => acc + feoAmtFor(child), 0)
  }

  function feoPlannedTotalFor(node: FeoNode): number {
    if (node.hasChildren) {
      return node.children.reduce((acc, child) => acc + feoPlannedTotalFor(child), 0)
    }
    const qty = node.planned_quantity != null ? Number(node.planned_quantity) : 0
    const unitPrice = node.planned_amount != null ? Number(node.planned_amount) : 0
    if (qty > 0 && unitPrice > 0) return qty * unitPrice
    if (node.planned_quantity == null && node.planned_amount == null) {
      const t = planTreeByCat.value[node.id]
      if (t && t.plan_manual != null) return Number(t.plan_manual)
    }
    return 0
  }

  function feoPlannedRequestsFor(node: FeoNode): number {
    const own = plannedPurchaseTotals.value[node.id] || 0
    if (!node.hasChildren) return own
    return own + node.children.reduce((acc, child) => acc + feoPlannedRequestsFor(child), 0)
  }

  function feoPlannedConsumedFor(node: FeoNode): number {
    const own = plannedPurchaseTotalsLinked.value[node.id] || 0
    if (!node.hasChildren) return own
    return own + node.children.reduce((acc, child) => acc + feoPlannedConsumedFor(child), 0)
  }

  function feoInPlanScheduleFor(node: FeoNode): number {
    return feoPlannedRequestsFor(node) + feoPlannedConsumedFor(node)
  }

  function feoPlannedOverFor(node: FeoNode): number {
    const own = plannedPurchaseTotalsOver.value[node.id] || 0
    if (!node.hasChildren) return own
    return own + node.children.reduce((acc, child) => acc + feoPlannedOverFor(child), 0)
  }

  function feoPlannedDisplayRaw(node: FeoNode): number {
    return planTreeByCat.value[node.id]?.display || 0
  }

  function feoPlannedDisplayFor(node: FeoNode): number {
    if (plannedSumBase.value === 'manual') return feoPlannedTotalFor(node)
    if (plannedSumBase.value === 'purchases') return feoPlannedTotalFor(node) + feoPlannedRequestsFor(node) + feoPlannedConsumedFor(node) + feoPlannedOverFor(node)
    if (plannedSumBase.value === 'requests') {
      return feoPlannedRequestsFor(node) + feoPlannedConsumedFor(node) + feoPlannedOverFor(node) + (!node.hasChildren ? matchedReqTotalRef.value(node) : 0)
    }
    return feoPlannedDisplayRaw(node)
  }

  function feoResidualNoteFor(node: FeoNode): { planned: number; consumed: number; residual: number } | null {
    if (node.hasChildren) return null
    const t = planTreeByCat.value[node.id]
    if (!t) return null
    const planned = Number(t.plan_manual ?? 0)
    const consumed = feoInPlanScheduleFor(node)
    const residual = planned - consumed
    if (planned <= 0 && consumed <= 0) return null
    return { planned, consumed, residual }
  }

  function feoPlanConsumedNoteFor(node: FeoNode): { planned: number; consumed: number; residual: number } | null {
    const t = planTreeByCat.value[node.id]
    const planned = (t && t.plan_manual != null) ? Number(t.plan_manual) : feoPlannedTotalFor(node)
    const consumed = feoInPlanScheduleFor(node)
    if (planned <= 0 && consumed <= 0) return null
    return { planned, consumed, residual: planned - consumed }
  }

  function feoForecastWarningFor(node: FeoNode): { forecast: number; forecastOver: number; planManual: number } | null {
    const v = plannedPurchaseForecast.value[node.id]
    if (!v || !(v.forecast_over > 0)) return null
    return { forecast: v.forecast, forecastOver: v.forecast_over, planManual: v.plan_manual }
  }

  function isAutoAmtNode(node: FeoNode): boolean {
    if (!node.hasChildren) return false
    return node.planned_amount == null
  }

  // ── Слияние с позициями из заявок (флаги, используемые и деревом, и useFeoReqItems.ts) ──
  // Миграция плана категории → плановые позиции: у мигрированного листа
  // planned_quantity/planned_amount оба null, хотя план есть (живёт в активных плановых
  // позициях) — фолбэк на planTreeByCat.plan_manual > 0.
  function isManualPosLeaf(node: FeoNode): boolean {
    if (node.hasChildren) return false
    if (node.planned_quantity != null || node.planned_amount != null) return true
    const t = planTreeByCat.value[node.id]
    return !!(t && Number(t.plan_manual || 0) > 0)
  }

  // Направление со временем может наполниться — раскрывать панель «Плановые позиции»
  // у узла с детьми имеет смысл, только если у него САМОГО есть активные FeoPlannedItem.
  function hasOwnPlannedAmountFor(node: FeoNode): boolean {
    if (!node.hasChildren) return false
    const t = planTreeByCat.value[node.id]
    if (t) {
      const childrenPlanManual = (node.children || []).reduce(
        (sum, ch) => sum + Number(planTreeByCat.value[ch.id]?.plan_manual || 0), 0
      )
      const ownAmt = Number(t.plan_manual || 0) - childrenPlanManual
      if (ownAmt > 0.005) return true
    }
    return (plannedItemsByCat.value[node.id]?.length || 0) > 0
  }

  function feoOwnDirectionPlanFor(node: FeoNode): number {
    if (!node.hasChildren) return 0
    const t = planTreeByCat.value[node.id]
    if (!t) return 0
    const childrenPlanManual = (node.children || []).reduce(
      (sum, ch) => sum + Number(planTreeByCat.value[ch.id]?.plan_manual || 0), 0
    )
    const own = Number(t.plan_manual || 0) - childrenPlanManual
    return own > 0.005 ? own : 0
  }

  // Финансирование задано вручную → ручные план-значения приоритетнее заявок
  function mergedManualPriority(node: FeoNode): boolean {
    return feoBudgetFor(node) > 0
  }

  // matchedReqQty/matchedReqTotal реально живут в useFeoReqItems.ts (сопоставление по
  // имени с позициями заявок) — но нужны здесь (feoQtyDisplayFor/feoPlannedDisplayFor/
  // mergedQtyDiff), а useFeoReqItems.ts в свою очередь использует hasOwnPlannedAmountFor/
  // isManualPosLeaf отсюда. Разрываем цикл модуля косвенной ссылкой: useFeoReqItems.ts
  // подключает свои функции сюда один раз через setMatchedReqFns при сборке ctx в
  // SubsidiesView.vue — единственная точка провязки, само значение не копируется
  // (Правило №6).
  const matchedReqQtyRef = { value: (_node: FeoNode): number => 0 }
  const matchedReqTotalRef = { value: (_node: FeoNode): number => 0 }
  function setMatchedReqFns(qtyFn: (node: FeoNode) => number, totalFn: (node: FeoNode) => number) {
    matchedReqQtyRef.value = qtyFn
    matchedReqTotalRef.value = totalFn
  }

  // ── Итоги дерева (строка ИТОГО) ────────────────────
  const totalFeoBudget = computed(() => {
    const b = selectedSubsidy.value?.budget
    return b != null && Number(b) > 0 ? Number(b) : null
  })
  const totalFeoEffective = computed(() => feoTree.value.reduce((a, r) => a + feoEffectiveFor(r), 0))
  const totalFeoDiff = computed(() =>
    totalFeoBudget.value != null ? totalFeoEffective.value - totalFeoBudget.value : 0
  )
  const totalFeoPurchased = computed(() => feoTree.value.reduce((a, r) => a + feoPurchasedFor(r), 0))
  const totalFeoInPlanSchedule = computed(() => feoTree.value.reduce((a, r) => a + feoInPlanScheduleFor(r), 0))

  const selectedBudget = computed(() => {
    if (!selectedSubsidy.value) return 0
    if (feoTree.value.length) return totalFeoEffective.value
    return selectedSubsidy.value.feo_budget_total || selectedSubsidy.value.budget || 0
  })
  const selectedPlannedTotal = computed(() => {
    if (feoTree.value.length) {
      return feoTree.value.reduce((acc, r) => acc + feoPlannedTotalFor(r) + feoPlannedRequestsFor(r), 0)
    }
    return selectedSubsidy.value?.planned || 0
  })

  // Обновляет справочный расчёт (feo_filled/feo_budget_total/calculated_budget) карточки
  // субсидии в списке после любой правки дерева ФЭО.
  function syncFeoFilled() {
    if (!selectedId.value) return
    const total = feoTree.value.reduce((sum, root) => sum + feoEffectiveFor(root), 0)
    const s = allSubsidies.value.find(x => x.id === selectedId.value)
    if (s) {
      s.feo_filled = total > 0
      s.feo_budget_total = total
      s.calculated_budget = total
    }
  }

  function getFeoPlanManual(categoryId: number): number {
    return Number(planTreeByCat.value[categoryId]?.plan_manual || 0)
  }

  return {
    residualBase,
    feoBudgetFor, feoEffectiveFor, manualChildFeoSum, hasManualChildFeo, isAutoNode, feoRollup,
    feoPurchasedFor, feoFactFor, feoResidualBaseFor, feoResidualFor, feoDisplayedFor, feoFinDiff,
    feoRemainingWithPurchasesNote, feoIsOverBudget, feoChildrenBudgetDiff,
    feoOverspentDescendantMap, feoHasOverspentDescendant, feoOverspentDescendantText, feoOverspentDescendantTitle,
    feoQtyFor, isAutoQtyNode, feoQtyRequestsFor, feoQtyConsumedFor, feoQtyOverFor,
    feoQtyDisplayRaw, feoQtyDisplayFor, mergedQtyDiff,
    feoAmtFor, feoPlannedTotalFor, feoPlannedRequestsFor, feoPlannedConsumedFor, feoInPlanScheduleFor,
    feoPlannedOverFor, feoPlannedDisplayRaw, feoPlannedDisplayFor,
    feoResidualNoteFor, feoPlanConsumedNoteFor, feoForecastWarningFor, isAutoAmtNode,
    isManualPosLeaf, hasOwnPlannedAmountFor, feoOwnDirectionPlanFor, mergedManualPriority,
    setMatchedReqFns,
    totalFeoBudget, totalFeoEffective, totalFeoDiff, totalFeoPurchased, totalFeoInPlanSchedule,
    selectedBudget, selectedPlannedTotal, syncFeoFilled, getFeoPlanManual,
  }
}

