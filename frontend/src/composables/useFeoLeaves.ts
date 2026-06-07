// useFeoLeaves — encapsulates loading leaf FeoCategory rows (level=3, no children)
// with budget/used/residual aggregates for per-item ФЭО selection.
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

export interface UseFeoLeavesOptions {
  /** Subsidy whose ФЭО tree leaves we load (null → empty list). */
  subsidyId: Ref<number | null | undefined>
  /** Optional purchase to exclude from residual computation (current edit). */
  excludePurchaseId?: Ref<number | null | undefined>
}

export function useFeoLeaves(opts: UseFeoLeavesOptions) {
  const feoLeaves = ref<FeoLeaf[]>([])

  watch(
    () => [opts.subsidyId.value, opts.excludePurchaseId?.value] as const,
    async ([subsidyId, excludeId]) => {
      if (!subsidyId) {
        feoLeaves.value = []
        return
      }
      try {
        const qs = excludeId != null ? `&exclude_purchase_id=${excludeId}` : ''
        feoLeaves.value = await apiFetch<FeoLeaf[]>(
          `/feo-categories/leaves?subsidy_id=${subsidyId}${qs}`,
        )
      } catch {
        feoLeaves.value = []
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

  return { feoLeaves, getFeoLeaf, isOverBudget, overBudgetDelta }
}
