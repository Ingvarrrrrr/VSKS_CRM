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
import type { FeoActualItem, FeoCategory, FeoNode, FeoPlannedItem, FeoReqItem, PlannedBase, SubsidyRow } from './types'

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

  // ── Волна 5a-2: панель «План vs факт» ФЭО — общие для PlannedItem*Dialog.vue/
  // PlanGraphVersions*Dialog.vue/useFeoImport.ts/useSubsidyApprovers-подобных
  // композаблов куски состояния, остающиеся в родителе (используются и деревом
  // ФЭО напрямую). Один источник — не копия (Правило №6).
  comparisonData: Ref<Record<number, { planned: FeoPlannedItem[]; actual: FeoActualItem[] }>>
  refreshComparison: (categoryId: number) => Promise<void>
  ensureComparison: (catId: number) => Promise<void>
  refreshReqData: (catId?: number) => Promise<void>
  // Позиции закупок категории, привязанные (plannedId>=0) или НЕ привязанные
  // (plannedId<0, см. вызовы в SubsidiesView.vue) к плановой позиции.
  factForPlanned: (catId: number, plannedId: number) => FeoActualItem[]
  // Превью фото товара (несколько мест в дереве ФЭО открывают его напрямую) —
  // вынесено в ProductPhotoPreviewDialog.vue, но ставится строками дерева,
  // которое остаётся в родителе.
  photoPreview: Ref<{ src: string; title: string } | null>

  // ── Волна 5b: список субсидий (SubsidyListHeader/Table/CardsGrid, useSubsidyList.ts) —
  // тонкие прокси к диалогам, чьи <ref> остаются в SubsidiesView.vue (сами диалоги
  // рендерятся там же, не переехали), плюс пара прав/действий верхнего уровня.
  canEditFeo: ComputedRef<boolean>
  downloadFeoTemplate: (subsidyId?: number, subsidyName?: string) => Promise<void>
  toggleSelect: (id: number) => void
  canApproveSubsidy: (s: SubsidyRow | null) => boolean
  approveSubsidy: (s: SubsidyRow) => Promise<void>
  approvingSubsidyId: Ref<number | null>
  startEdit: (s: SubsidyRow) => Promise<void>
  confirmDelete: (s: SubsidyRow) => Promise<void>
  openMembersDialog: (s: SubsidyRow) => Promise<void>
  openHistoryDialog: (s: SubsidyRow) => void

  // ── Волна 5b: контрагент + тулбар дерева ФЭО (FeoTreeToolbar.vue) ──
  openContractorOverride: (s: SubsidyRow) => Promise<void>
  openAddFeoDialog: (parentId: number | null) => void
  feoTableArea: Ref<HTMLElement | null>
  feoItemsGroupBy: Ref<'none' | 'category' | 'category_type'>
  plannedBase: Ref<PlannedBase>

  // ── Волна 5b: KPI drill-down (useKpiDrilldown.ts/SubsidyKpiCards.vue) — сырые
  // ингредиенты дерева ФЭО, которые composable читает/раскрывает по клику на
  // KPI-плитку. Формулы/состав дерева остаются в SubsidiesView.vue (вне этой
  // волны) — здесь только ссылки на те же реактивные значения (Правило №6).
  selectedBudget: ComputedRef<number>
  selectedPlannedTotal: ComputedRef<number>
  plannedItemsByCat: Ref<Record<number, FeoReqItem[]>>
  plannedItemsLoaded: Ref<boolean>
  mergedReqByCat: ComputedRef<{
    matched: Record<number, FeoReqItem[]>
    virtualByCat: Record<number, { items: FeoReqItem[] }[]>
    linkedByPlanned: Record<number, FeoReqItem[]>
  }>
  purchaseFoldersByCat: ComputedRef<Record<number, { items: FeoReqItem[] }[]>>
  expandedIds: Ref<number[]>
  expandedReqItems: Ref<Set<number>>
  expandedItemPanels: Ref<Set<number>>
  expandedPurchases: Ref<Set<number>>
  expandedPlannedItems: Ref<Set<number>>
  collapsedPlannedItems: Ref<Set<number>>
  feoSearch: Ref<string>
  loadingComparison: Ref<Set<number>>
  feoFinDiff: (node: FeoNode) => number
  feoPlannedTotalFor: (node: FeoNode) => number
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
