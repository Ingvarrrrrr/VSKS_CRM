// Общий контекст карточки субсидии для диалогов, вынесенных из SubsidiesView.vue
// (components/subsidies/*). Раньше эти диалоги были частью SubsidiesView.vue и
// читали/писали его локальные refs напрямую; после разбиения на компоненты им
// нужен способ достучаться до состояния, которое остаётся в родителе (список
// субсидий, дерево ФЭО) — без копирования этого состояния и без второго
// источника истины (Правило №6).
//
// В контекст положено ТОЛЬКО то, что реально нужно диалогам этой под-волны
// (SubsidyEditDialog/SubsidyDeleteDialog/FeoCategoryDialog/FeoCategoryDeleteDialog/
// SubsidyApproversDialog/SubsidyTemplatesDialog) — не вся карта состояния
// SubsidiesView.vue.
import { inject, provide, type ComputedRef, type InjectionKey, type Ref } from 'vue'
import type { Router } from 'vue-router'
import type { FeoCategory, FeoNode, SubsidyRow } from './types'

export interface SubsidyDetailContext {
  router: Router
  allSubsidies: Ref<SubsidyRow[]>
  loadAll: () => Promise<void>
  selectedId: Ref<number | null>
  selectedSubsidy: ComputedRef<SubsidyRow | null>
  // ── Дерево ФЭО (остаётся в родителе целиком — вне этой волны рефакторинга) ──
  feoCategories: Ref<FeoCategory[]>
  feoTree: ComputedRef<FeoNode[]>
  flattenAll: (nodes: FeoNode[]) => FeoNode[]
  loadFeo: (subsidyId: number) => Promise<void>
  syncFeoFilled: () => void
  openAddPlannedItem: (categoryId: number) => void
  openConvertManualPlanToItem: (node: FeoNode) => void
  // Σ плановых позиций категории (plan_manual из /feo-categories/plan-tree) —
  // нужна только для предупреждения при переключении режима плана категории
  // на «ручную сумму» (feoEditPlanSourceSwitchWarning в FeoCategoryDialog).
  getFeoPlanManual: (categoryId: number) => number
}

export const SUBSIDY_DETAIL_KEY: InjectionKey<SubsidyDetailContext> = Symbol('SubsidyDetailContext')

export function provideSubsidyDetail(ctx: SubsidyDetailContext) {
  provide(SUBSIDY_DETAIL_KEY, ctx)
}

export function useSubsidyDetailCtx(): SubsidyDetailContext {
  const ctx = inject(SUBSIDY_DETAIL_KEY)
  if (!ctx) {
    throw new Error('useSubsidyDetailCtx() вызван вне SubsidiesView.vue — provideSubsidyDetail() не найден')
  }
  return ctx
}
