// useFeoLeaves — encapsulates loading leaf FeoCategory rows (level=3, no children)
// with budget/used/residual aggregates for per-item ФЭО selection.
// Also loads all nodes (feoNodes) for cascade select.
// Extracted from PurchaseItemsEditor.vue (monolith refactor).
import { ref, watch, type Ref } from 'vue'
import { apiFetch } from '@/api'

export interface FeoLeaf {
  id: number
  name: string
  parent_id: number | null
  level: number
  budget: number
  used_amount: number
  residual: number
  path: string // "Экипировка › Комплекты › Костюм-двойка"
}

/** All FeoCategory nodes (including non-leaf) for cascade select. */
export interface FeoNode {
  id: number
  name: string
  parent_id: number | null
  level: number
  is_leaf: boolean
  /** Собственная (ручная) сумма финансирования узла; null — не задана. */
  budget?: number | null
  /** Пояснение: что входит в направление. */
  description?: string | null
  /** Плановое количество (CRM-план), независимо от budget; null — не задано. */
  planned_quantity?: number | null
  /** Плановая стоимость за единицу (CRM-план), независимо от budget; null — не задано. */
  planned_amount?: number | null
  /** Структурный признак «есть финансирование» — НЕ гейтится правом feo_budget.view_leaf,
   *  в отличие от budget (который приходит null без права). Используй его, а не числовой
   *  budget, для решений «показать/скрыть узел». */
  has_budget?: boolean
  /** Структурный признак «есть план» (planned_quantity × planned_amount > 0) — НЕ
   *  гейтится правом. Используй его, а не planned_quantity/planned_amount, для решений
   *  «показать/скрыть узел». */
  has_plan?: boolean
}

/**
 * Узлы без заданного финансирования И без планового показателя (ни у себя, ни у
 * потомков) не являются уровнем ФЭО и не предлагаются к выбору. Оставляем узлы,
 * у которых задан budget ИЛИ planned_quantity×planned_amount > 0 — конечная
 * категория может иметь план (использована в плане закупок) без собственного
 * budget, и раньше такие узлы ошибочно вырезались из дерева, хотя реально
 * существуют и используются (баг «категория ФЭО была удалена из справочника,
 * структуру пересоздавали» при клике на плановую позицию — сессия 2026-08-05).
 * Пересчитываем is_leaf по оставшимся узлам.
 *
 * Решаем по булевым признакам has_budget/has_plan (не гейтятся правом
 * feo_budget.view_leaf — приходят всегда, даже когда числовые budget/planned_amount
 * скрыты за правом и равны null). Фолбэк на прежнюю числовую логику — на случай
 * если бэкенд ещё не отдаёт эти поля (сессия 2026-08-06, ревью гейта: без фолбэка
 * снятие права у роли делало дерево выбора категорий ФЭО полностью пустым).
 */
export function filterFundedNodes(nodes: FeoNode[]): FeoNode[] {
  if (!nodes.length) return nodes
  const childrenByParent = new Map<number | null, FeoNode[]>()
  for (const n of nodes) {
    const arr = childrenByParent.get(n.parent_id) || []
    arr.push(n)
    childrenByParent.set(n.parent_id, arr)
  }
  const fundedMemo = new Map<number, boolean>()
  function isFunded(n: FeoNode): boolean {
    const cached = fundedMemo.get(n.id)
    if (cached !== undefined) return cached
    const funded = n.has_budget ?? (n.budget != null)
    const planned = n.has_plan ?? (Number(n.planned_quantity || 0) * Number(n.planned_amount || 0) > 0)
    let ok = funded || planned
    if (!ok) ok = (childrenByParent.get(n.id) || []).some(isFunded)
    fundedMemo.set(n.id, ok)
    return ok
  }
  const kept = nodes.filter(isFunded)
  const keptHasChildren = new Set<number>()
  for (const n of kept) {
    if (n.parent_id != null) keptHasChildren.add(n.parent_id)
  }
  return kept.map(n => ({ ...n, is_leaf: !keptHasChildren.has(n.id) }))
}

export interface UseFeoLeavesOptions {
  /** Subsidy whose ФЭО tree leaves we load (null → empty list). */
  subsidyId: Ref<number | null | undefined>
  /** Optional purchase to exclude from residual computation (current edit). */
  excludePurchaseId?: Ref<number | null | undefined>
}

export function useFeoLeaves(opts: UseFeoLeavesOptions) {
  const feoLeaves = ref<FeoLeaf[]>([])
  const feoNodes = ref<FeoNode[]>([])

  watch(
    () => [opts.subsidyId.value, opts.excludePurchaseId?.value] as const,
    async ([subsidyId, excludeId]) => {
      if (!subsidyId) {
        feoLeaves.value = []
        feoNodes.value = []
        return
      }
      try {
        const qs = excludeId != null ? `&exclude_purchase_id=${excludeId}` : ''
        const [leaves, nodes] = await Promise.all([
          apiFetch<FeoLeaf[]>(`/feo-categories/leaves?subsidy_id=${subsidyId}${qs}`),
          apiFetch<FeoNode[]>(`/feo-categories/flat?subsidy_id=${subsidyId}`),
        ])
        feoLeaves.value = leaves
        feoNodes.value = filterFundedNodes(nodes)
      } catch {
        feoLeaves.value = []
        feoNodes.value = []
      }
    },
    { immediate: true },
  )

  function getFeoLeaf(id: number | undefined | null): FeoLeaf | null {
    if (!id) return null
    return feoLeaves.value.find(r => r.id === id) ?? null
  }

  /** Whether assigning `totalPrice` to leaf `feoCategoryId` exceeds its budget. */
  function isOverBudget(feoCategoryId: number | null | undefined, totalPrice: number | null | undefined): boolean {
    if (!feoCategoryId) return false
    const r = getFeoLeaf(feoCategoryId)
    if (!r) return false
    return (r.used_amount + Number(totalPrice || 0)) > r.budget
  }

  /** By how much `totalPrice` exceeds the leaf budget (0 if within). */
  function overBudgetDelta(feoCategoryId: number | null | undefined, totalPrice: number | null | undefined): number {
    const r = getFeoLeaf(feoCategoryId)
    if (!r) return 0
    return (r.used_amount + Number(totalPrice || 0)) - r.budget
  }

  return { feoLeaves, feoNodes, getFeoLeaf, isOverBudget, overBudgetDelta }
}
