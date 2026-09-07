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
import type {
  ExcessPlanItem, ExcessPlanItemPurchase, ExcessCulprit, FeoActualItem, FeoCategory, FeoNode,
  FeoPlannedItem, FeoPurchaseFolder, FeoReqItem, FeoReqRow, FeoStage, FeoStageRow, FeoVirtualGroup,
  PlanExcessApprovalDto, PlanExcessStep, PlannedBase, PlanTreeEntry, SubsidyRow,
} from './types'

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
  startFeoEdit: (node: FeoNode) => void
  confirmFeoDelete: (node: FeoCategory) => void
  feoTableArea: Ref<HTMLElement | null>
  feoItemsGroupBy: Ref<'none' | 'category' | 'category_type'>
  plannedBase: Ref<PlannedBase>
  plannedSumBase: Ref<PlannedBase>
  plannedQtyBase: Ref<PlannedBase>

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

  // ── Волна 5c: дерево ФЭО — FeoTreeTable.vue/FeoTreeRow.vue/FeoLevel5Panel.vue/
  // FeoReqItemsRows.vue/FeoByPurchasesRows.vue + 6 диалогов дерева (AlignBudgetDialog/
  // ExcessRejectDialog/ReqItemEditDialog/ReqItemDeleteDialog/WishBlockedDeleteDialog/
  // WishItemFeoEditDialog). Формулы/состояние живут в composables/subsidies/
  // useFeoTree{State,Amounts,Excess,Dnd}.ts, useFeoLevel5.ts, useFeoReqItems.ts,
  // useFeoTreePrefs.ts — единственный источник (Правило №6), здесь только ссылки.

  // Единственный экземпляр useResizableColumns('feo-table', ...) — composable САМ
  // не singleton (каждый вызов создаёт свой colWidths), поэтому и основная таблица
  // (FeoTreeTable.vue), и вложенная таблица плановых позиций КАЖДОГО узла
  // (FeoLevel5Panel.vue) обязаны получать ЭТОТ ЖЕ объект через ctx — иначе их
  // ширины колонок разъезжаются между собой при изменении пользователем.
  feoResize: { resizeStyle: (key: string) => Record<string, string>; onResizeStart: (e: MouseEvent, key: string) => void }

  // useFeoTreeState.ts
  planTreeByCat: Ref<Record<number, PlanTreeEntry>>
  isNodeVisible: (node: FeoNode) => boolean
  visibleFeoNodes: ComputedRef<FeoNode[]>
  unassignedFeo: Ref<{ amount: number; purchase_count: number; purchase_ids: number[] }>
  goToUnassignedFeoPurchases: () => void

  // useFeoTreePrefs.ts
  expandedStageRows: Ref<Set<string>>
  togglePurchaseFolder: (pid: number) => void
  toggleStageRow: (key: string) => void
  toggleExpand: (id: number) => void
  togglePlannedItemFolder: (plannedId: number) => void

  // useFeoTreeAmounts.ts
  residualBase: Ref<'plan' | 'feo'>
  feoBudgetFor: (node: FeoNode) => number
  feoEffectiveFor: (node: FeoNode) => number
  manualChildFeoSum: (node: FeoNode) => number
  hasManualChildFeo: (node: FeoNode) => boolean
  isAutoNode: (node: FeoNode) => boolean
  feoRollup: (node: FeoNode) => { qty: number | null; qtyAuto: boolean; amount: number | null; amountAuto: boolean }
  feoPurchasedFor: (node: FeoNode) => number
  feoFactFor: (node: FeoNode) => number
  feoResidualBaseFor: (node: FeoNode) => number
  feoResidualFor: (node: FeoNode) => number
  feoDisplayedFor: (node: FeoNode) => number
  feoRemainingWithPurchasesNote: (node: FeoNode) => string | null
  feoIsOverBudget: (node: FeoNode) => boolean
  feoChildrenBudgetDiff: (node: FeoNode) => number
  feoHasOverspentDescendant: (node: FeoNode) => boolean
  feoOverspentDescendantText: (node: FeoNode) => string
  feoOverspentDescendantTitle: (node: FeoNode) => string
  isAutoQtyNode: (node: FeoNode) => boolean
  feoQtyRequestsFor: (node: FeoNode) => number
  feoQtyDisplayFor: (node: FeoNode) => number
  mergedQtyDiff: (node: FeoNode) => number
  feoInPlanScheduleFor: (node: FeoNode) => number
  feoPlannedRequestsFor: (node: FeoNode) => number
  feoPlannedDisplayFor: (node: FeoNode) => number
  feoResidualNoteFor: (node: FeoNode) => { planned: number; consumed: number; residual: number } | null
  feoPlanConsumedNoteFor: (node: FeoNode) => { planned: number; consumed: number; residual: number } | null
  feoForecastWarningFor: (node: FeoNode) => { forecast: number; forecastOver: number; planManual: number } | null
  isAutoAmtNode: (node: FeoNode) => boolean
  isManualPosLeaf: (node: FeoNode) => boolean
  hasOwnPlannedAmountFor: (node: FeoNode) => boolean
  feoOwnDirectionPlanFor: (node: FeoNode) => number
  mergedManualPriority: (node: FeoNode) => boolean
  totalFeoBudget: ComputedRef<number | null>
  totalFeoEffective: ComputedRef<number>
  totalFeoDiff: ComputedRef<number>
  totalFeoInPlanSchedule: ComputedRef<number>

  // useFeoTreeExcess.ts
  isSaas: ComputedRef<boolean>
  excessRequestLoading: Ref<number | null>
  excessDecideLoading: Ref<number | null>
  excessFor: (node: FeoNode) => { amount: number; pending: boolean; approved: boolean } | null
  excessCulpritFor: (node: FeoNode) => ExcessCulprit | null
  excessCulpritText: (node: FeoNode) => string
  isExcessCulpritActual: (node: FeoNode, actual: { purchase_id: number; item_name: string }) => boolean
  excessCulpritChipTooltip: (node: FeoNode) => string
  excessFactFor: (node: FeoNode) => { amount: number; pending: boolean; approved: boolean } | null
  excessPlanFor: (node: FeoNode) => { amount: number; pending: boolean; approved: boolean; manualEntered: number; items: ExcessPlanItem[] } | null
  excessPlanItemPurchaseTitle: (p: ExcessPlanItemPurchase) => string
  excessPlanApprovalPermanent: (node: FeoNode) => { amount: number; at: string; by: string; planBefore: number | null; planAfter: number | null } | null
  excessApprovalFor: (node: FeoNode) => PlanExcessApprovalDto | null
  excessPendingNames: (node: FeoNode) => string
  excessMyPendingStep: (node: FeoNode) => PlanExcessStep | null
  excessResolvedByName: (node: FeoNode) => string
  excessResolvedDate: (node: FeoNode) => string
  requestPlanExcessApproval: (node: FeoNode) => Promise<void>
  decidePlanExcess: (node: FeoNode, decision: 'approved' | 'rejected', comment?: string) => Promise<void>
  openExcessRejectDialog: (node: FeoNode) => void

  // useFeoLevel5.ts
  toggleItemPanel: (node: FeoNode) => Promise<void>
  anyPlannedExpandedFor: (node: FeoNode) => boolean
  toggleAllPlannedItemsForCategory: (node: FeoNode) => void
  factForPlannedTotal: (catId: number, plannedId: number) => number
  factExcessReasonItems: (node: FeoNode) => { key: string; name: string; amount: number; purchases: { id: number; label: string; amount: number; stopped: boolean }[] }[]
  factExcessReasonRemainder: (node: FeoNode) => number
  stageChipLabelFor: (status: string | null | undefined) => string
  stageChipTitleFor: (status: string | null | undefined) => string
  stageChipColorFor: (status: string | null | undefined) => string
  factStageHeaderFor: (catId: number, plannedId: number) => string
  planBreakdownText: (catId: number, planned: FeoPlannedItem & { isManual?: boolean }) => string
  displayPlannedRowsFor: (node: FeoNode) => (FeoPlannedItem & { isManual?: boolean })[]
  unplannedActualFor: (node: FeoNode) => FeoActualItem[]
  isOrphanedActual: (actual: FeoActualItem) => boolean
  comparisonPlanTotal: (node: FeoNode) => number
  plannedItemIndentPx: (node: FeoNode) => number
  calcDiff: (plannedAmount: number | string | null | undefined, actuals: { total_price?: number | string | null; fact_amount?: number | string | null; purchase_status?: string | null }[]) => number
  getDiffStyle: (plannedAmount: number | string | null | undefined, actuals: { total_price?: number | string | null; fact_amount?: number | string | null; purchase_status?: string | null }[]) => string
  stagesWithDiff: (stages: FeoStage[] | undefined) => FeoStageRow[]
  deletingPlannedItemId: Ref<number | null>
  deletePlannedItem: (item: FeoPlannedItem) => Promise<void>
  descendantCategoriesFor: (node: FeoNode) => FeoNode[]
  movingPlannedItemId: Ref<number | null>
  movePlannedItemToCategory: (item: FeoPlannedItem, targetCategoryId: number) => Promise<void>
  reorderingPlannedItemId: Ref<number | null>
  reorderPlannedItem: (node: FeoNode, pIdx: number, direction: 'up' | 'down') => Promise<void>

  // useFeoReqItems.ts
  feoStoppedLine: (row: { stopped_by_name?: string | null; stopped_at?: string | null }) => string
  purchaseFolderTitle: (f: FeoPurchaseFolder) => string
  matchedReqFor: (node: FeoNode) => FeoReqItem[]
  groupPlannedQty: (g: FeoVirtualGroup) => number
  groupPlannedTotal: (g: FeoVirtualGroup) => number
  groupFactTotal: (g: FeoVirtualGroup) => number | null
  reqOwnersAfter: ComputedRef<Record<number, FeoNode[]>>
  reqItemRowsFor: (node: FeoNode) => FeoReqRow[]
  reqRowIndent: (node: FeoNode, row: FeoReqRow) => string
  expandedReqItemPanels: Ref<Set<string>>
  reqPanelKey: (node: FeoNode, g: FeoVirtualGroup) => string
  toggleReqItemPanel: (node: FeoNode, g: FeoVirtualGroup) => void
  virtGroupPurchaseIds: (g: FeoVirtualGroup) => number[]
  virtCart: (node: FeoNode, g: FeoVirtualGroup) => void
  virtEdit: (node: FeoNode, g: FeoVirtualGroup) => void
  virtDelete: (node: FeoNode, g: FeoVirtualGroup) => void
  reqItemPlanned: (catId: number, itemId: number) => FeoPlannedItem | null
  reqItemActual: (catId: number, itemId: number) => FeoActualItem | null
  mapReqItem: (node: FeoNode, item: FeoReqItem) => void
  purchaseFoldersFor: (node: FeoNode) => FeoPurchaseFolder[]
  kpiReqRowClass: (row: FeoReqRow) => string
  kpiItemRowClass: (it: FeoReqItem | FeoActualItem) => string
  kpiFolderClass: (f: FeoPurchaseFolder) => string
  groupStatuses: (g: FeoVirtualGroup) => { status: string; count: number; label: string }[]

  // useFeoTreeDnd.ts
  dragNodeId: Ref<number | null>
  dragOverId: Ref<number | null>
  onDragStart: (e: DragEvent, node: FeoNode) => void
  onDragOver: (e: DragEvent, node: FeoNode) => void
  onDragLeave: () => void
  onDrop: (e: DragEvent, targetNode: FeoNode) => Promise<void>
  onDropToRoot: (e: DragEvent) => Promise<void>
  onDragEnd: () => void
  reorderFeoNode: (node: FeoNode, direction: 'up' | 'down') => Promise<void>
  inlineBudgetId: Ref<number | null>
  inlineBudgetVal: Ref<string>
  inlineInputEl: Ref<HTMLInputElement | null>
  startInlineBudget: (node: FeoNode) => Promise<void>
  saveInlineBudget: (node: FeoNode) => Promise<void>
  inlineQtyId: Ref<number | null>
  inlineQtyVal: Ref<string>
  inlineQtyInputEl: Ref<HTMLInputElement | null>
  startInlineQty: (node: FeoNode) => Promise<void>
  saveInlineQty: (node: FeoNode) => Promise<void>
  inlineAmtId: Ref<number | null>
  inlineAmtVal: Ref<string>
  inlineAmtInputEl: Ref<HTMLInputElement | null>
  startInlineAmt: (node: FeoNode) => Promise<void>
  saveInlineAmt: (node: FeoNode) => Promise<void>

  // Диалоги дерева ФЭО (открываются трамполинами SubsidiesView.vue через ref .open()):
  openAlignBudgetConfirm: (node: FeoNode) => void
  openReqItemEdit: (node: FeoNode, item: FeoReqItem) => void
  openReqItemEditFromActual: (node: FeoNode, actual: FeoActualItem) => void
  confirmReqItemDelete: (node: FeoNode, item: FeoReqItem) => void
  openWishItemFeoEdit: (node: FeoNode, item: FeoReqItem) => void
  loadResiduals: () => Promise<void>
  mobile: Ref<boolean>

  // usePlannedItems.ts — уже вызывается в SubsidiesView.vue, но дерево ФЭО (теперь в
  // FeoLevel5Panel.vue/FeoReqItemsRows.vue) тоже вызывает эти функции напрямую из
  // шаблона (кнопки «Редактировать плановую», «Снять сопоставление», «Сопоставить с
  // плановой», «Завести из закупки») — раньше это были бэйр top-level refs/функции
  // SubsidiesView.vue, теперь читаются через ctx (Правило №6, один источник).
  openMapDialog: (actual: FeoActualItem, categoryId: number) => void
  openCreatePlannedFromActual: (node: FeoNode, actual: FeoActualItem) => void
  openEditPlannedItem: (item: FeoPlannedItem) => void
  openEditCategoryPlan: (node: FeoNode) => void
  mapTarget: Ref<FeoActualItem | null>
  mapCategoryId: Ref<number | null>
  applyMapping: (plannedId: number | null) => Promise<void>
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
