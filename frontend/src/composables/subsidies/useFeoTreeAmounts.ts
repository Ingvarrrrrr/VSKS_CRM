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

// ctx необязателен НАЧИНАЯ СО ВТОРОГО вызова (раздел C0, план ancient-prancing-
// music.md, 2026-09-21) — тот же паттерн, что и useFeoTreeExcess.ts/
// useFeoLevel5Api(): FeoTreeRow.vue вызывает БЕЗ аргумента, чтобы достать
// feoTypeSplitFor/planTypeSplitFor/remainingTypeSplitFor напрямую, не проходя
// через ctx (SubsidyDetailContext собирается в SubsidiesView.vue — файл вне
// этой задачи, см. докстринг useFeoLevel5Api() в FeoLevel5Panel.vue).
export function useFeoTreeAmounts(ctx?: FeoTreeAmountsCtx) {
  if (!_api) {
    if (!ctx) throw new Error('useFeoTreeAmounts() вызван до первого построения (нужен ctx) — проверьте порядок монтирования SubsidiesView.vue')
    _api = buildFeoTreeAmounts(ctx)
  }
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
  // Ноль в node.budget означает «не задано» наравне с NULL (владелец, сессия
  // 2026-09-05 — п.8: «когда введено 0, это значит, что не задана сумма»;
  // зеркалит правку backend/app/services/feo_plan_tree.py, где узел с budget=0
  // тоже не даёт превышения). ВСЕ места, решающие «задано ли финансирование
  // узла», обязаны спрашивать feoBudgetIsSet, а не сравнивать budget != null
  // напрямую — иначе 0 снова читается как «есть значение» (Правило №6, один
  // источник этой проверки). Функция внутренняя — наружу (ctx) не отдаётся,
  // потребители уже получают её эффект через feoEffectiveFor/feoDisplayedFor/
  // isAutoNode ниже.
  function feoBudgetIsSet(node: FeoNode): boolean {
    return node.budget != null && Number(node.budget) !== 0
  }

  // Для АРИФМЕТИКИ (суммирование по дереву) ноль как слагаемое безопасен — эта
  // функция НЕ используется для решения «показать ли узел как заданный», см.
  // feoBudgetIsSet выше.
  function feoBudgetFor(node: FeoNode): number {
    return node.budget != null ? Number(node.budget) : 0
  }

  function feoEffectiveFor(node: FeoNode): number {
    if (feoBudgetIsSet(node)) return Number(node.budget)
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
    return !feoBudgetIsSet(node)
  }

  // ИСПРАВЛЕНИЕ (ревью координатора, та же сессия 2026-09-05): node.feo_amount —
  // это ЦЕНА ЗА ЕДИНИЦУ по документу ФЭО (см. комментарий в
  // backend/app/models/feo_category.py: «Стоимость за ед. по документу ФЭО»),
  // НЕ сумма. Backend сам так её и использует — feo_import_apply.py считает
  // `feo_amt = feo_sum / feo_qty` при импорте, а feo_planned_items_reports.py
  // строит total через `_safe_mul(cat.feo_quantity, cat.feo_amount)` (Правило
  // №6 — та же формула qty × unit_price, что уже есть в бэкенде, а не новая).
  // Первая версия этой правки (п.15б) убрала «qty × amount» из вёрстки, но
  // подписала «Сумма» той же ЦЕНОЙ ЗА ЕДИНИЦУ — то есть перенесла ошибку
  // владельца («129 шт × 8200 ₽ читается как цена за единицу») в обратную
  // сторону (голая цена за единицу выдавалась за сумму). Теперь `amount` —
  // ВСЕГДА итоговые деньги (qty × unit_price), а не голая цена.
  function feoRollup(node: FeoNode): { qty: number | null; qtyAuto: boolean; amount: number | null; amountAuto: boolean } {
    // 0 в feo_quantity/feo_amount (значения «по документу ФЭО») трактуется как
    // «не задано» тем же правилом, что и node.budget выше — иначе колонка
    // «Количество и финансирование по ФЭО» рисует буквальное «0 ₽» вместо того,
    // чтобы промолчать (задача владельца, п.15б).
    const ownQtyRaw = node.feo_quantity != null ? Number(node.feo_quantity) : null
    const ownQty = ownQtyRaw != null && ownQtyRaw !== 0 ? ownQtyRaw : null
    const ownUnitPriceRaw = node.feo_amount != null ? Number(node.feo_amount) : null
    const ownUnitPrice = ownUnitPriceRaw != null && ownUnitPriceRaw !== 0 ? ownUnitPriceRaw : null
    if (ownQty != null || ownUnitPrice != null) {
      // Сумма считается ТОЛЬКО когда известны ОБА сомножителя. Если задано
      // только количество или только цена за единицу — сумма посчитана быть
      // не может; молча выдавать одно из этих чисел под подписью «Сумма»
      // нельзя (это и была найденная ошибка) — amount остаётся null, и
      // FeoTreeRow.vue целиком скрывает блок (показывать его владелец просил
      // только когда сумма реально задана в ФЭО).
      const ownTotal = (ownQty != null && ownUnitPrice != null) ? ownQty * ownUnitPrice : null
      return { qty: ownQty, qtyAuto: false, amount: ownTotal, amountAuto: false }
    }
    if (!node.hasChildren) return { qty: null, qtyAuto: false, amount: null, amountAuto: false }
    let sumQty = 0; let hasQty = false
    let sumAmt = 0; let hasAmt = false
    const walkChildren = (children: FeoNode[]) => {
      for (const c of children) {
        const r = feoRollup(c)
        if (r.qty != null) { sumQty += r.qty; hasQty = true }
        // r.amount у ребёнка — уже деньги (собственный итог или сумма итогов его
        // детей, см. return выше и этот же комментарий рекурсивно) — поэтому
        // складывать amount по дереву корректно: сумма денег остаётся деньгами,
        // в отличие от суммы цен за единицу.
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
    if (feoBudgetIsSet(node)) return Number(node.budget)
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

  // ИСПРАВЛЕНИЕ (расследование «Запланировано 75 896 105 vs 101 415 814,62»,
  // субсидия 46 «ЦентрПоиск_2026», 2026-09-21): раньше эта функция САМА
  // пересчитывала «ручной план» узла — для листа qty×unitPrice старых полей
  // FeoCategory.planned_quantity/planned_amount с фолбэком на
  // planTreeByCat.plan_manual, для узла с детьми — ТОЛЬКО Σ детей, БЕЗ
  // собственного plan_manual узла. Это была ВТОРАЯ, более старая формула
  // (Правило №6): backend/app/services/feo_plan_tree.py::compute_feo_plan_tree
  // уже считает plan_manual КАЖДОГО узла (и листа, и группы) — для листа Σ
  // активных FeoPlannedItem (те самые старые поля FeoCategory давно не
  // участвуют в сумме, см. её докстринг), для группы Σ plan_manual детей ПЛЮС
  // собственные FeoPlannedItem, заведённые прямо на направлении (ФОРМУЛА v3,
  // сессия 2026-08-12, «направление со временем может наполниться»). Клиент
  // эту v3-часть никогда не пересчитывал — на «ЦентрПоиск_2026» 9 направлений
  // с собственным планом (Σ 25 519 709,48) выпадали из карточки KPI
  // «Запланировано» (selectedPlannedTotal ниже), хотя ИТОГО дерева (через
  // feoPlannedDisplayRaw → planTreeByCat.display) их уже показывало —
  // карточка и ИТОГО расходились. Теперь функция просто ЧИТАЕТ готовое
  // plan_manual с бэкенда для ЛЮБОГО узла (тот же приём, что и
  // feoPlannedDisplayRaw/feoQtyDisplayRaw ниже) — второй формулы больше нет.
  function feoPlannedTotalFor(node: FeoNode): number {
    return Number(planTreeByCat.value[node.id]?.plan_manual || 0)
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

  // Сумма плана дочерних подкатегорий узла (по plan_manual каждого прямого
  // ребёнка) — единственное место, где считается эта сумма (Правило №6);
  // feoOwnDirectionPlanFor/hasOwnPlannedAmountFor и подпись «состав суммы» в
  // FeoTreeRow.vue читают её отсюда, а не пересчитывают вторым способом.
  function feoChildrenPlanManualFor(node: FeoNode): number {
    if (!node.hasChildren) return 0
    return (node.children || []).reduce(
      (sum, ch) => sum + Number(planTreeByCat.value[ch.id]?.plan_manual || 0), 0
    )
  }

  // Сколько прямых подкатегорий узла реально несут план (plan_manual > 0) —
  // для подписи «по N подкатегориям» в составе суммы направления.
  function feoChildrenWithPlanCountFor(node: FeoNode): number {
    if (!node.hasChildren) return 0
    return (node.children || []).filter(
      ch => Number(planTreeByCat.value[ch.id]?.plan_manual || 0) > 0.005
    ).length
  }

  // Направление со временем может наполниться — раскрывать панель «Плановые позиции»
  // у узла с детьми имеет смысл, только если у него САМОГО есть активные FeoPlannedItem.
  function hasOwnPlannedAmountFor(node: FeoNode): boolean {
    if (!node.hasChildren) return false
    const t = planTreeByCat.value[node.id]
    if (t) {
      const ownAmt = Number(t.plan_manual || 0) - feoChildrenPlanManualFor(node)
      if (ownAmt > 0.005) return true
    }
    return (plannedItemsByCat.value[node.id]?.length || 0) > 0
  }

  function feoOwnDirectionPlanFor(node: FeoNode): number {
    if (!node.hasChildren) return 0
    const t = planTreeByCat.value[node.id]
    if (!t) return 0
    const own = Number(t.plan_manual || 0) - feoChildrenPlanManualFor(node)
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
  // ИСПРАВЛЕНИЕ (то же расследование, что и у feoPlannedTotalFor выше, 2026-09-21):
  // КПИ-карточка «Запланировано» (SubsidyKpiCards.vue::kpiSubTarget_plan_schedule)
  // и «Свободно»/«Превышение» (selectedBudget − это) читали ЭТУ сумму — раньше
  // feoPlannedTotalFor(r) + feoPlannedRequestsFor(r), третья формула плановой суммы
  // параллельно ИТОГО дерева (FeoTreeTable.vue, Σ feoPlannedDisplayFor) и дашборду
  // (_calculate_feo_planned_tree_bulk). Правило №6 — один показатель, один источник:
  // backend/app/services/feo_plan_tree.py::compute_feo_plan_tree сам документирует
  // (docstring _calculate_feo_planned_tree_bulk, subsidies.py), что его planned_tree
  // «Совпадает с тем, что показывает панель ФЭО... feoPlannedDisplayFor(root)... режим
  // 'all'» — то есть feoPlannedDisplayFor(root) уже ЯВЛЯЕТСЯ контрактом с дашбордом,
  // его и переиспользуем здесь вместо повторной сборки той же суммы другим способом.
  // Теперь карточка, ИТОГО дерева и дашборд читают ровно одну формулу.
  const selectedPlannedTotal = computed(() => {
    if (feoTree.value.length) {
      return feoTree.value.reduce((acc, r) => acc + feoPlannedDisplayFor(r), 0)
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

  // ── Раздел C0 (план ancient-prancing-music.md, 2026-09-21): «товары/услуги» —
  // читают ГОТОВЫЕ поля узла plan_tree (compute_feo_plan_tree, backend/app/
  // services/feo_plan_tree.py), ничего не пересчитывают (Правило №6 — та же
  // Σ, что и excess-контроли useFeoTreeExcess.ts::typeExcessFor). null — нечего
  // показать (все три доли нулевые), чтобы FeoTreeRow.vue не рисовал пустую
  // строку «товары 0 ₽ · услуги 0 ₽».
  type TypeSplit = { goods: number; services: number; unspecified: number }
  function nodeTypeSplit(node: FeoNode, prefix: 'plan' | 'feo' | 'fact'): TypeSplit | null {
    const t = planTreeByCat.value[node.id] as any
    const goods = Number(t?.[`${prefix}_goods`] || 0)
    const services = Number(t?.[`${prefix}_services`] || 0)
    const unspecified = Number(t?.[`${prefix}_unspecified`] || 0)
    if (Math.abs(goods) <= 0.005 && Math.abs(services) <= 0.005 && Math.abs(unspecified) <= 0.005) return null
    return { goods, services, unspecified }
  }
  function planTypeSplitFor(node: FeoNode): TypeSplit | null {
    return nodeTypeSplit(node, 'plan')
  }
  function feoTypeSplitFor(node: FeoNode): TypeSplit | null {
    return nodeTypeSplit(node, 'feo')
  }
  // Остаток по типам = ФЭО по типу − план по типу (владелец, раздел C0) — НЕ
  // тот же переключатель «от плановой/от ФЭО», что у общей колонки «Остаток»
  // (residualBase выше) — по типам он один, зафиксированная формула. Не может
  // вернуться null «отсутствия» — 0−0=0 тоже валидный остаток (в отличие от
  // planTypeSplitFor/feoTypeSplitFor, где null значит «нечего показать»).
  function remainingTypeSplitFor(node: FeoNode): TypeSplit {
    const feo = feoTypeSplitFor(node) || { goods: 0, services: 0, unspecified: 0 }
    const plan = planTypeSplitFor(node) || { goods: 0, services: 0, unspecified: 0 }
    return {
      goods: feo.goods - plan.goods,
      services: feo.services - plan.services,
      unspecified: feo.unspecified - plan.unspecified,
    }
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
    isManualPosLeaf, hasOwnPlannedAmountFor, feoOwnDirectionPlanFor,
    feoChildrenPlanManualFor, feoChildrenWithPlanCountFor, mergedManualPriority,
    setMatchedReqFns,
    totalFeoBudget, totalFeoEffective, totalFeoDiff, totalFeoPurchased, totalFeoInPlanSchedule,
    selectedBudget, selectedPlannedTotal, syncFeoFilled, getFeoPlanManual,
    // Раздел C0 — «товары/услуги» по узлу (см. докстринги функций выше).
    planTypeSplitFor, feoTypeSplitFor, remainingTypeSplitFor,
  }
}

