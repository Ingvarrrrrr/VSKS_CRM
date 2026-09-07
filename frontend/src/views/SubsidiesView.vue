<template>
  <div class="subsidies-page">

    <!-- ── Header ── -->
    <SubsidyListHeader v-model:add-open="showAddDialog" :registry-area="registryArea" />

    <!-- ── Loading ── -->
    <div v-if="loading" class="d-flex justify-center py-16">
      <v-progress-circular indeterminate color="primary" size="52" />
    </div>

    <template v-else>
      <!-- ── Empty ── -->
      <div v-if="filteredSubsidies.length === 0" class="empty-state">
        <v-icon icon="mdi-cash-off" size="64" color="grey-lighten-2" />
        <div class="text-h6 text-medium-emphasis mt-3">Нет субсидий за {{ selectedYear }} год</div>
        <v-btn class="mt-4" variant="tonal" color="primary" prepend-icon="mdi-plus" @click="showAddDialog = true">
          Добавить субсидию
        </v-btn>
      </div>

      <template v-else>
       <div ref="registryArea">
        <SubsidyListTable v-if="effectiveView === 'table'" />
        <SubsidyCardsGrid v-else />
       </div>

        <!-- ── Summary bar ── -->
        <SubsidySummaryBar />

        <!-- ── Detail panel ── -->
        <div v-if="selectedSubsidy" class="detail-panel">
          <div class="detail-header">
            <v-icon icon="mdi-folder-open-outline" size="20" color="#3B82F6" class="mr-2" />
            <span class="detail-title">{{ selectedSubsidy.name }} — направления ФЭО</span>
            <v-chip v-if="selectedSubsidy.status === 'draft'" size="x-small" color="warning" variant="flat" class="ml-2">Черновик</v-chip>
            <v-btn
              v-if="canApproveSubsidy(selectedSubsidy)"
              size="small" variant="tonal" color="success" prepend-icon="mdi-check-decagram"
              class="ml-3"
              :loading="approvingSubsidyId === selectedSubsidy.id"
              @click="approveSubsidy(selectedSubsidy)"
            >Утвердить</v-btn>
            <v-btn icon="mdi-close" size="x-small" variant="text" class="ml-auto" @click="selectedId = null" />
          </div>

          <!-- KPI mini-cards for selected subsidy -->
          <SubsidyKpiCards />

          <!-- FEO categories -->
          <div v-if="loadingFeo" class="d-flex justify-center py-8">
            <v-progress-circular indeterminate color="primary" />
          </div>

          <div v-else>
            <FeoTreeToolbar />

            <FeoTreeTable />
          </div>

          <SubsidyEventsPanel ref="eventsPanelRef" :subsidy-id="selectedId" />
        </div>

      </template>
    </template>

    <SubsidyEditDialog ref="subsidyEditDialogRef" v-model:add-open="showAddDialog" v-model:edit-open="showEditDialog" />
    <SubsidyDeleteDialog ref="subsidyDeleteDialogRef" v-model="showDeleteDialog" @deleted="loadAll" />
    <FeoCategoryDialog ref="feoCategoryDialogRef" v-model:add-open="showAddFeoDialog" v-model:edit-open="showEditFeoDialog" />
    <FeoCategoryDeleteDialog ref="feoCategoryDeleteDialogRef" v-model="showDeleteFeoDialog" />

    <AlignBudgetDialog ref="alignBudgetDialogRef" />
    <ExcessRejectDialog ref="excessRejectDialogRef" />
    <ReqItemEditDialog ref="reqItemEditDialogRef" />
    <ReqItemDeleteDialog ref="reqItemDeleteDialogRef" />
    <WishBlockedDeleteDialog ref="wishBlockedDeleteDialogRef" />
    <WishItemFeoEditDialog ref="wishItemFeoEditDialogRef" />

    <SubsidyApproversDialog />
    <SubsidyMembersDialog ref="subsidyMembersDialogRef" />
    <SubsidyCopyApproversDialog />
    <SubsidyApproverFormDialog />
    <SubsidyTemplatesDialog />
    <SubsidyCopyTemplatesDialog />
    <SubsidyContractorOverrideDialog ref="contractorOverrideDialogRef" />

    <FeoImportWizard />

    <PlannedItemEditDialog />
    <CategoryPlanEditDialog />
    <PlannedItemMapDialog />
    <PlannedItemAddDialog />

    <BudgetHistoryDialog ref="historyDialogRef" />

    <PlanGraphVersionHistoryDialog />
    <PlanGraphExportVersionsDialog />
    <PlanGraphSnapshotDialog />
    <PlanGraphSaveVersionDialog />

    <ProductPhotoPreviewDialog />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { apiFetch } from '@/api'
import { useGlobalSubsidy } from '@/composables/useGlobalSubsidy'
import { useResizableColumns } from '@/composables/useResizableColumns'
import { useToast, type ToastType } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'
import BudgetHistoryDialog from '@/components/BudgetHistoryDialog.vue'
import SubsidyListHeader from '@/components/subsidies/SubsidyListHeader.vue'
import SubsidyListTable from '@/components/subsidies/SubsidyListTable.vue'
import SubsidyCardsGrid from '@/components/subsidies/SubsidyCardsGrid.vue'
import SubsidySummaryBar from '@/components/subsidies/SubsidySummaryBar.vue'
import SubsidyKpiCards from '@/components/subsidies/SubsidyKpiCards.vue'
import FeoTreeToolbar from '@/components/subsidies/FeoTreeToolbar.vue'
import FeoTreeTable from '@/components/subsidies/FeoTreeTable.vue'
import { useSubsidyList } from '@/composables/subsidies/useSubsidyList'
import { useKpiDrilldown } from '@/composables/subsidies/useKpiDrilldown'
import SubsidyEventsPanel from '@/components/subsidies/SubsidyEventsPanel.vue'
import SubsidyEditDialog from '@/components/subsidies/SubsidyEditDialog.vue'
import SubsidyDeleteDialog from '@/components/subsidies/SubsidyDeleteDialog.vue'
import FeoCategoryDialog from '@/components/subsidies/FeoCategoryDialog.vue'
import FeoCategoryDeleteDialog from '@/components/subsidies/FeoCategoryDeleteDialog.vue'
import SubsidyApproversDialog from '@/components/subsidies/SubsidyApproversDialog.vue'
import SubsidyApproverFormDialog from '@/components/subsidies/SubsidyApproverFormDialog.vue'
import SubsidyCopyApproversDialog from '@/components/subsidies/SubsidyCopyApproversDialog.vue'
import SubsidyMembersDialog from '@/components/subsidies/SubsidyMembersDialog.vue'
import SubsidyTemplatesDialog from '@/components/subsidies/SubsidyTemplatesDialog.vue'
import SubsidyCopyTemplatesDialog from '@/components/subsidies/SubsidyCopyTemplatesDialog.vue'
import SubsidyContractorOverrideDialog from '@/components/subsidies/SubsidyContractorOverrideDialog.vue'
import ProductPhotoPreviewDialog from '@/components/subsidies/ProductPhotoPreviewDialog.vue'
import PlanGraphVersionHistoryDialog from '@/components/subsidies/PlanGraphVersionHistoryDialog.vue'
import PlanGraphExportVersionsDialog from '@/components/subsidies/PlanGraphExportVersionsDialog.vue'
import PlanGraphSnapshotDialog from '@/components/subsidies/PlanGraphSnapshotDialog.vue'
import PlanGraphSaveVersionDialog from '@/components/subsidies/PlanGraphSaveVersionDialog.vue'
import PlannedItemAddDialog from '@/components/subsidies/PlannedItemAddDialog.vue'
import PlannedItemEditDialog from '@/components/subsidies/PlannedItemEditDialog.vue'
import CategoryPlanEditDialog from '@/components/subsidies/CategoryPlanEditDialog.vue'
import PlannedItemMapDialog from '@/components/subsidies/PlannedItemMapDialog.vue'
import { usePlannedItems } from '@/composables/subsidies/usePlannedItems'
import FeoImportWizard from '@/components/subsidies/FeoImportWizard.vue'
import { provideSubsidyDetail } from '@/composables/subsidies/useSubsidyDetail'
import { useSubsidyTemplates } from '@/composables/subsidies/useSubsidyTemplates'
import AlignBudgetDialog from '@/components/subsidies/AlignBudgetDialog.vue'
import ExcessRejectDialog from '@/components/subsidies/ExcessRejectDialog.vue'
import ReqItemEditDialog from '@/components/subsidies/ReqItemEditDialog.vue'
import ReqItemDeleteDialog from '@/components/subsidies/ReqItemDeleteDialog.vue'
import WishBlockedDeleteDialog from '@/components/subsidies/WishBlockedDeleteDialog.vue'
import WishItemFeoEditDialog from '@/components/subsidies/WishItemFeoEditDialog.vue'
import { useFeoTreePrefs } from '@/composables/subsidies/useFeoTreePrefs'
import { useFeoTreeState } from '@/composables/subsidies/useFeoTreeState'
import { useFeoTreeAmounts } from '@/composables/subsidies/useFeoTreeAmounts'
import { useFeoTreeExcess } from '@/composables/subsidies/useFeoTreeExcess'
import { useFeoTreeDnd } from '@/composables/subsidies/useFeoTreeDnd'
import { useFeoLevel5 } from '@/composables/subsidies/useFeoLevel5'
import { useFeoReqItems } from '@/composables/subsidies/useFeoReqItems'
// Относительный путь (не '@/...'), т.к. tsconfig.app.json не содержит paths-маппинга
// для алиаса '@' (Vite резолвит его сам через vite.config.ts, но чистый tsc/vue-tsc —
// нет) — см. комментарий у остальных импортов типов в этом файле (не менялся волной 5c).
import type { SubsidyRow, FeoCategory, FeoNode, FeoActualItem, FeoReqItem, FeoReqRow, FeoPurchaseFolder } from '../composables/subsidies/types'

const { globalSubsidyId } = useGlobalSubsidy()

// Единственный экземпляр колонок дерева ФЭО ('feo-table') — useResizableColumns()
// НЕ singleton, поэтому создаётся здесь ОДИН раз и прокидывается в FeoTreeTable.vue/
// FeoLevel5Panel.vue через ctx.feoResize (см. их докстринги и useSubsidyDetail.ts).
const feoResize = useResizableColumns('feo-table', {
  name: 0, budget: 180, qty: 0, planned: 0, spent: 180, residual: 0,
})

const router = useRouter()
const route  = useRoute()

// ── State ─────────────────────────────────────────
const registryArea = ref<HTMLElement | null>(null)
const feoTableArea = ref<HTMLElement | null>(null)
const loading    = ref(false)
const loadingFeo = ref(false)

const allSubsidies = ref<SubsidyRow[]>([])

const showAddDialog      = ref(false)
const showEditDialog     = ref(false)
const showDeleteDialog   = ref(false)
const showAddFeoDialog   = ref(false)
const showEditFeoDialog  = ref(false)
const showDeleteFeoDialog = ref(false)

const historyDialogRef = ref<InstanceType<typeof BudgetHistoryDialog> | null>(null)
const approvingSubsidyId = ref<number | null>(null)
const selectedId      = ref<number | null>(null)

const { selectedYear, filteredSubsidies, effectiveView, mobile } = useSubsidyList({ allSubsidies })

const selectedSubsidy = computed(() =>
  allSubsidies.value.find(s => s.id === selectedId.value) ?? null
)

// 12-04: Residuals state
const feoResiduals = ref<Record<number, {
  feo_item_id: number
  name: string
  category_id: number
  planned_amount: number
  used_amount: number
  wish_used_amount: number
  residual: number
  linked_purchase_ids: number[]
}>>({})
const residualsLoading = ref(false)

// B5 (2026-09-01): право на запись в дерево категорий ФЭО.
const authStore = useAuthStore()
const canEditFeo = computed(() => authStore.hasAction('feo_category.edit'))
// SaaS-роли и id пользователя для согласования превышения — см. useFeoTreeExcess.ts.

const toast = useToast()
function showSnack(
  text: string,
  color: ToastType = 'success',
  opts?: { actionText?: string; onAction?: () => void; duration?: number },
) {
  toast.addToast(text, color, opts)
}

// ── Дерево ФЭО: composables (волна 5c) ─────────────────────────────────────
// Порядок вызовов важен только для того, что нужно СРАЗУ (refs/computed) —
// функции-оркестраторы ниже (loadFeo/refreshReqData/openXxx-трамполины)
// объявлены через `function` (hoisting) и могут ссылаться на любые из этих
// composables независимо от текстового порядка.
const feoTreePrefs = useFeoTreePrefs()
const feoTreeState = useFeoTreeState({ expandedIds: feoTreePrefs.expandedIds })
const feoTreeAmounts = useFeoTreeAmounts({
  purchaseTotals: feoTreeState.purchaseTotals,
  plannedPurchaseTotals: feoTreeState.plannedPurchaseTotals,
  plannedPurchaseQty: feoTreeState.plannedPurchaseQty,
  plannedPurchaseTotalsLinked: feoTreeState.plannedPurchaseTotalsLinked,
  plannedPurchaseQtyLinked: feoTreeState.plannedPurchaseQtyLinked,
  plannedPurchaseTotalsOver: feoTreeState.plannedPurchaseTotalsOver,
  plannedPurchaseQtyOver: feoTreeState.plannedPurchaseQtyOver,
  plannedPurchaseForecast: feoTreeState.plannedPurchaseForecast,
  planTreeByCat: feoTreeState.planTreeByCat,
  plannedItemsByCat: feoTreeState.plannedItemsByCat,
  feoTree: feoTreeState.feoTree,
  plannedBase: feoTreePrefs.plannedBase,
  selectedSubsidy, allSubsidies, selectedId,
})
const feoTreeExcess = useFeoTreeExcess({
  planTreeByCat: feoTreeState.planTreeByCat,
  planExcessApprovals: feoTreeState.planExcessApprovals,
  selectedId,
  refreshReqData,
})
const feoLevel5 = useFeoLevel5({
  selectedId,
  feoCategories: feoTreeState.feoCategories,
  feoTree: feoTreeState.feoTree,
  flattenAll: feoTreeState.flattenAll,
  expandedItemPanels: feoTreePrefs.expandedItemPanels,
  expandedPlannedItems: feoTreePrefs.expandedPlannedItems,
  collapsedPlannedItems: feoTreePrefs.collapsedPlannedItems,
  feoResidualNoteFor: feoTreeAmounts.feoResidualNoteFor,
  refreshReqData,
})
// matchedReqQty/matchedReqTotal нужны feoTreeAmounts (feoQtyDisplayFor/feoPlannedDisplayFor/
// mergedQtyDiff), но сами живут в useFeoReqItems.ts, которому в свою очередь нужны
// isManualPosLeaf/hasOwnPlannedAmountFor из feoTreeAmounts — цикл модулей разорван
// косвенной провязкой (см. докстринг setMatchedReqFns в useFeoTreeAmounts.ts).
const feoReqItems = useFeoReqItems({
  router,
  feoTree: feoTreeState.feoTree,
  flattenAll: feoTreeState.flattenAll,
  visibleFeoNodes: feoTreeState.visibleFeoNodes,
  isNodeVisible: feoTreeState.isNodeVisible,
  plannedItemsByCat: feoTreeState.plannedItemsByCat,
  plannedBase: feoTreePrefs.plannedBase,
  feoItemsGroupBy: feoTreePrefs.feoItemsGroupBy,
  expandedIds: feoTreePrefs.expandedIds,
  expandedReqItems: feoTreePrefs.expandedReqItems,
  comparisonData: feoLevel5.comparisonData,
  ensureComparison: feoLevel5.ensureComparison,
  openReqItemEdit,
  confirmReqItemDelete,
  openMapDialog: (a: FeoActualItem, catId: number) => plannedItems.openMapDialog(a, catId),
})
feoTreeAmounts.setMatchedReqFns(feoReqItems.matchedReqQty, feoReqItems.matchedReqTotal)
const feoTreeDnd = useFeoTreeDnd({
  feoCategories: feoTreeState.feoCategories,
  visibleFeoNodes: feoTreeState.visibleFeoNodes,
  selectedId,
  loadFeo,
  syncFeoFilled: feoTreeAmounts.syncFeoFilled,
})

// ── Плановые позиции (usePlannedItems.ts, тот же singleton-паттерн) ────────
const plannedItems = usePlannedItems({
  selectedId,
  feoCategories: feoTreeState.feoCategories,
  loadFeo,
  comparisonData: feoLevel5.comparisonData,
  refreshComparison: feoLevel5.refreshComparison,
  ensureComparison: feoLevel5.ensureComparison,
  refreshReqData,
  factForPlanned: feoLevel5.factForPlanned,
})

// ── Диалоги дерева ФЭО (волна 5c): рефы + трамполины ────────────────────────
const alignBudgetDialogRef = ref<InstanceType<typeof AlignBudgetDialog> | null>(null)
const excessRejectDialogRef = ref<InstanceType<typeof ExcessRejectDialog> | null>(null)
const reqItemEditDialogRef = ref<InstanceType<typeof ReqItemEditDialog> | null>(null)
const reqItemDeleteDialogRef = ref<InstanceType<typeof ReqItemDeleteDialog> | null>(null)
const wishBlockedDeleteDialogRef = ref<InstanceType<typeof WishBlockedDeleteDialog> | null>(null)
const wishItemFeoEditDialogRef = ref<InstanceType<typeof WishItemFeoEditDialog> | null>(null)

function openAlignBudgetConfirm(node: FeoNode) {
  alignBudgetDialogRef.value?.open(node)
}
function openExcessRejectDialog(node: FeoNode) {
  excessRejectDialogRef.value?.open(node)
}
function openReqItemEdit(node: FeoNode, item: FeoReqItem) {
  reqItemEditDialogRef.value?.open(node, item)
}
function openReqItemEditFromActual(node: FeoNode, actual: FeoActualItem) {
  reqItemEditDialogRef.value?.openFromActual(node, actual)
}
// Позиция «из заявки»: точечно удалить её из плана нельзя — заявка уже согласована.
function confirmReqItemDelete(node: FeoNode, item: FeoReqItem) {
  if (item.wish_id) {
    wishBlockedDeleteDialogRef.value?.open(item.wish_id, node.id, item.item_name, item.quantity, item.unit, item.total_price)
    return
  }
  reqItemDeleteDialogRef.value?.open(node.id, item.purchase_id, item.id, item.item_name)
}
function openWishItemFeoEdit(node: FeoNode, item: FeoReqItem) {
  wishItemFeoEditDialogRef.value?.open(node, item)
}

// Подсветка строк дерева при клике по KPI-плитке (useKpiDrilldown.ts) — остаются здесь
// (а не в useFeoReqItems.ts): им нужен `kpi`, а `kpi` сам собирается из mergedReqByCat/
// purchaseFoldersByCat (feoReqItems) — цикл разорван тем, что kpi создаётся ПОСЛЕ
// feoReqItems, а эти три маленькие функции — после kpi (см. их вызов в шаблоне через ctx).
function kpiReqRowClass(row: FeoReqRow): string {
  if (!kpi.activeKpi.value) return ''
  const hit = row.items.some(it => kpi.kpiItemIds.value.has(it.id))
  if (!hit) return 'feo-kpi-dim'
  return row.group ? 'feo-kpi-hl' : 'feo-kpi-path'
}
function kpiItemRowClass(it: FeoReqItem | FeoActualItem): string {
  if (!kpi.activeKpi.value) return ''
  const id = 'id' in it ? it.id : it.purchase_item_id
  return kpi.kpiItemIds.value.has(id) ? 'feo-kpi-hl' : 'feo-kpi-dim'
}
function kpiFolderClass(f: FeoPurchaseFolder): string {
  if (!kpi.activeKpi.value) return ''
  return f.items.some(it => kpi.kpiItemIds.value.has(it.id)) ? 'feo-kpi-path' : 'feo-kpi-dim'
}

// ── Data load (оркестрация — остаётся в view, см. её докстринг) ────────────
async function loadAll() {
  loading.value = true
  try {
    const charts = await apiFetch<any>('/dashboard/charts?scope=managed')
    allSubsidies.value = charts.subsidy_stats.map((s: any) => ({
      id: s.id, name: s.name, year: s.year, budget: s.budget,
      calculated_budget: s.calculated_budget ?? 0,
      planned: s.planned_tree ?? s.total_planned, paid: s.total_paid, contracted: s.total_confirmed,
      plan_schedule: s.total_plan_schedule ?? 0,
      ordered: s.total_ordered ?? 0,
      feo_budget_total: s.feo_budget_total ?? 0,
      feo_filled: s.feo_filled ?? false,
      contractor_id: s.contractor_id ?? null,
      contractor_name: s.contractor_name ?? null,
      contractor_inn: s.contractor_inn ?? null,
      remaining: s.remaining ?? null,
      planned_amount: s.planned_amount ?? null,
      budget_discrepancy: s.budget_discrepancy ?? null,
      work: s.total_work ?? 0,
      contracts: s.total_contracts ?? 0,
      delivered: s.total_delivered ?? 0,
      delivered_unpaid: s.total_delivered_unpaid ?? 0,
      ceiling_warn_percent: s.ceiling_warn_percent ?? 90,
      ceiling_total: s.ceiling_total ?? 0,
      ceiling_committed_total: s.ceiling_committed_total ?? 0,
      ceiling_committed_percent: s.ceiling_committed_percent ?? 0,
      ceiling_near_warning: s.ceiling_near_warning ?? false,
      ceiling_exceeded: s.ceiling_exceeded ?? false,
      status: 'approved', // fallback, перезаписывается ниже реальным значением
    }))
    try {
      const statusRows = await apiFetch<Array<{ id: number; status?: string; created_by?: number | null; approved_by?: number | null; approved_at?: string | null }>>('/subsidies/')
      const byId = new Map(statusRows.map(r => [r.id, r]))
      for (const row of allSubsidies.value) {
        const found = byId.get(row.id)
        if (found) {
          row.status = found.status ?? 'approved'
          row.created_by = found.created_by ?? null
          row.approved_by = found.approved_by ?? null
          row.approved_at = found.approved_at ?? null
        }
      }
    } catch (e) {
      console.warn('[subsidies] status load failed:', e)
    }
    const years = [...new Set(allSubsidies.value.map((s: SubsidyRow) => s.year))].sort((a, b) => b - a)
    if (years.length) selectedYear.value = years[0]!  // always reset to most recent year

    // Handle ?sid=X navigation from Quick Access
    const sidParam = route.query.sid
    if (sidParam) {
      const targetId = Number(sidParam)
      const target = allSubsidies.value.find(s => s.id === targetId)
      if (target) {
        selectedYear.value = target.year
        selectedId.value = targetId
        loadFeo(targetId)
      }
    }
  } catch (e) {
    showSnack('Ошибка загрузки данных', 'error')
  } finally {
    loading.value = false
  }
}

async function downloadFeoTemplate(subsidyId?: number, subsidyName?: string) {
  const token = localStorage.getItem('auth_token')
  const qs = subsidyId ? `?subsidy_id=${subsidyId}` : ''
  const res = await fetch(`/api/feo-categories/import/template${qs}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) { showSnack('Ошибка загрузки шаблона', 'error'); return }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const safeName = subsidyName ? subsidyName.replace(/[\\/:*?"<>|]/g, '_').trim() : ''
  const fname = safeName
    ? `Шаблон_импорта_направлений_ФЭО_${safeName}.xlsx`
    : 'Шаблон_импорта_направлений_ФЭО.xlsx'
  const a = document.createElement('a'); a.href = url; a.download = fname; a.click()
  URL.revokeObjectURL(url)
}

async function loadFeo(subsidyId: number) {
  loadingFeo.value = true
  feoTreeState.feoCategories.value = []
  feoTreeState.purchaseTotals.value = {}
  feoTreeState.plannedPurchaseTotals.value = {}
  feoTreeState.plannedPurchaseQty.value = {}
  feoTreeState.plannedPurchaseTotalsLinked.value = {}
  feoTreeState.plannedPurchaseQtyLinked.value = {}
  feoTreeState.plannedPurchaseTotalsOver.value = {}
  feoTreeState.plannedPurchaseQtyOver.value = {}
  feoTreeState.plannedPurchaseForecast.value = {}
  feoTreeState.planTreeByCat.value = {}
  feoTreeState.planExcessApprovals.value = {}
  feoTreeState.unassignedFeo.value = { amount: 0, purchase_count: 0, purchase_ids: [] }
  feoTreeState.plannedItemsByCat.value = {}
  feoTreeState.plannedItemsLoaded.value = false
  // expandedReqItems больше НЕ сбрасывается здесь безусловно — см. комментарий в
  // useFeoTreePrefs.ts (persist через FEO_DISPLAY_PREFS_KEY).
  try {
    const [cats, totals, plannedTotals, plannedItemsRes, planTree] = await Promise.all([
      apiFetch<FeoCategory[]>(`/feo-categories/?subsidy_id=${subsidyId}`),
      apiFetch<Record<number, number>>(`/feo-categories/purchase-totals?subsidy_id=${subsidyId}`),
      apiFetch<Record<number, { total: number; qty: number; total_linked?: number; qty_linked?: number; total_over?: number; qty_over?: number; forecast?: number; forecast_over?: number; plan_manual?: number }>>(`/feo-categories/planned-purchase-totals?subsidy_id=${subsidyId}`),
      apiFetch<Record<number, FeoReqItem[]>>(`/feo-categories/planned-purchase-items?subsidy_id=${subsidyId}`),
      apiFetch<Record<string, any>>(`/feo-categories/plan-tree?subsidy_id=${subsidyId}`),
    ])
    feoTreeState.feoCategories.value = cats
    feoTreeState.purchaseTotals.value = totals
    feoTreeState.planTreeByCat.value = feoTreeState.splitPlanTree(planTree)
    feoTreeExcess.loadPlanExcessApprovals(subsidyId)
    feoTreeState.plannedItemsByCat.value = plannedItemsRes
    feoTreeState.plannedItemsLoaded.value = true
    const sums: Record<number, number> = {}
    const qtys: Record<number, number> = {}
    const sumsLinked: Record<number, number> = {}
    const qtysLinked: Record<number, number> = {}
    const sumsOver: Record<number, number> = {}
    const qtysOver: Record<number, number> = {}
    const forecasts: Record<number, { forecast: number; forecast_over: number; plan_manual: number }> = {}
    for (const [k, v] of Object.entries(plannedTotals)) {
      const totalLinked = Number(v?.total_linked || 0)
      const qtyLinked = Number(v?.qty_linked || 0)
      const totalOver = Number(v?.total_over || 0)
      const qtyOver = Number(v?.qty_over || 0)
      sums[Number(k)] = Number(v?.total || 0) - totalLinked - totalOver
      qtys[Number(k)] = Number(v?.qty || 0) - qtyLinked - qtyOver
      sumsLinked[Number(k)] = totalLinked
      qtysLinked[Number(k)] = qtyLinked
      sumsOver[Number(k)] = totalOver
      qtysOver[Number(k)] = qtyOver
      forecasts[Number(k)] = {
        forecast: Number(v?.forecast || 0),
        forecast_over: Number(v?.forecast_over || 0),
        plan_manual: Number(v?.plan_manual || 0),
      }
    }
    feoTreeState.plannedPurchaseTotals.value = sums
    feoTreeState.plannedPurchaseQty.value = qtys
    feoTreeState.plannedPurchaseTotalsLinked.value = sumsLinked
    feoTreeState.plannedPurchaseQtyLinked.value = qtysLinked
    feoTreeState.plannedPurchaseTotalsOver.value = sumsOver
    feoTreeState.plannedPurchaseQtyOver.value = qtysOver
    feoTreeState.plannedPurchaseForecast.value = forecasts
    // Восстановленные из localStorage раскрытые панели «план vs факт» не тянут свои
    // данные сами — toggleItemPanel грузит их только по клику. Подгружаем явно.
    for (const id of feoTreePrefs.expandedItemPanels.value) {
      if (feoTreeState.feoCategories.value.some(c => c.id === id)) feoLevel5.refreshComparison(id)
    }
  } catch {
    showSnack('Ошибка загрузки категорий ФЭО', 'error')
  } finally {
    loadingFeo.value = false
  }
}

// Обновление данных «из заявок» без сброса раскрытых папок.
async function refreshReqData(catId?: number) {
  if (!selectedId.value) return
  const [totals, items, planTree] = await Promise.all([
    apiFetch<Record<number, { total: number; qty: number; total_linked?: number; qty_linked?: number; total_over?: number; qty_over?: number; forecast?: number; forecast_over?: number; plan_manual?: number }>>(`/feo-categories/planned-purchase-totals?subsidy_id=${selectedId.value}`),
    apiFetch<Record<number, FeoReqItem[]>>(`/feo-categories/planned-purchase-items?subsidy_id=${selectedId.value}`),
    apiFetch<Record<string, any>>(`/feo-categories/plan-tree?subsidy_id=${selectedId.value}`),
  ])
  feoTreeState.planTreeByCat.value = feoTreeState.splitPlanTree(planTree)
  feoTreeExcess.loadPlanExcessApprovals(selectedId.value)
  const sums: Record<number, number> = {}
  const qtys: Record<number, number> = {}
  const sumsLinked: Record<number, number> = {}
  const qtysLinked: Record<number, number> = {}
  const sumsOver: Record<number, number> = {}
  const qtysOver: Record<number, number> = {}
  const forecasts: Record<number, { forecast: number; forecast_over: number; plan_manual: number }> = {}
  for (const [k, v] of Object.entries(totals)) {
    const totalLinked = Number(v?.total_linked || 0)
    const qtyLinked = Number(v?.qty_linked || 0)
    const totalOver = Number(v?.total_over || 0)
    const qtyOver = Number(v?.qty_over || 0)
    sums[Number(k)] = Number(v?.total || 0) - totalLinked - totalOver
    qtys[Number(k)] = Number(v?.qty || 0) - qtyLinked - qtyOver
    sumsLinked[Number(k)] = totalLinked
    qtysLinked[Number(k)] = qtyLinked
    sumsOver[Number(k)] = totalOver
    qtysOver[Number(k)] = qtyOver
    forecasts[Number(k)] = {
      forecast: Number(v?.forecast || 0),
      forecast_over: Number(v?.forecast_over || 0),
      plan_manual: Number(v?.plan_manual || 0),
    }
  }
  feoTreeState.plannedPurchaseTotals.value = sums
  feoTreeState.plannedPurchaseQty.value = qtys
  feoTreeState.plannedPurchaseTotalsLinked.value = sumsLinked
  feoTreeState.plannedPurchaseQtyLinked.value = qtysLinked
  feoTreeState.plannedPurchaseTotalsOver.value = sumsOver
  feoTreeState.plannedPurchaseQtyOver.value = qtysOver
  feoTreeState.plannedPurchaseForecast.value = forecasts
  feoTreeState.plannedItemsByCat.value = items
  feoTreeState.plannedItemsLoaded.value = true
  if (catId != null) {
    delete feoLevel5.comparisonData.value[catId]
    await feoLevel5.ensureComparison(catId)
  }
}

// ── Actions ───────────────────────────────────────
// 12-04: load FEO residuals for selected subsidy
async function loadResiduals() {
  if (!selectedId.value) return
  residualsLoading.value = true
  try {
    const data = await apiFetch<any[]>(`/feo-planned-items/residuals?subsidy_id=${selectedId.value}`)
    const byItemId: Record<number, any> = {}
    for (const item of data) {
      byItemId[item.feo_item_id] = item
    }
    feoResiduals.value = byItemId
  } catch (e) {
    console.error('Failed to load residuals', e)
  } finally {
    residualsLoading.value = false
  }
}

function toggleSelect(id: number) {
  if (selectedId.value === id) { selectedId.value = null; globalSubsidyId.value = null; return }
  selectedId.value = id
  globalSubsidyId.value = id
  loadFeo(id)
  loadEvents(id)
  loadResiduals()  // 12-04
}

// Sync: global → local
watch(globalSubsidyId, (id: number | null) => {
  if (id !== null && id !== selectedId.value) {
    selectedId.value = id
    loadFeo(id)
    loadEvents(id)
    loadResiduals()  // 12-04
  } else if (id === null) {
    selectedId.value = null
    feoResiduals.value = {}  // 12-04
  }
})

// startEdit/confirmDelete — тонкие прокси в SubsidyEditDialog.vue/SubsidyDeleteDialog.vue.
async function startEdit(s: SubsidyRow) {
  await subsidyEditDialogRef.value?.startEdit(s)
}
async function confirmDelete(s: SubsidyRow) {
  await subsidyDeleteDialogRef.value?.open(s)
}

// openAddFeoDialog/startFeoEdit/confirmFeoDelete — тонкие прокси в
// FeoCategoryDialog.vue/FeoCategoryDeleteDialog.vue.
function openAddFeoDialog(parentId: number | null) {
  feoCategoryDialogRef.value?.openAdd(parentId)
}
function startFeoEdit(node: FeoNode) {
  feoCategoryDialogRef.value?.openEdit(node)
}
function confirmFeoDelete(node: FeoCategory) {
  feoCategoryDeleteDialogRef.value?.open(node)
}

// ── Budget history ────────────────────────────────
function openHistoryDialog(s: any) {
  historyDialogRef.value?.open(s.id, s.name)
}

// ── C4: Draft subsidies — approve + members ────────
function canApproveSubsidy(s: SubsidyRow | null): boolean {
  if (!s) return false
  return s.status === 'draft' && authStore.hasAction('subsidy.edit')
}

async function approveSubsidy(s: SubsidyRow) {
  approvingSubsidyId.value = s.id
  try {
    const updated = await apiFetch<{ status?: string; approved_by?: number | null; approved_at?: string | null }>(
      `/subsidies/${s.id}/approve`, { method: 'POST' }
    )
    const idx = allSubsidies.value.findIndex(x => x.id === s.id)
    if (idx >= 0) {
      allSubsidies.value[idx] = {
        ...allSubsidies.value[idx]!,
        status: updated.status ?? 'approved',
        approved_by: updated.approved_by ?? null,
        approved_at: updated.approved_at ?? null,
      }
    }
    showSnack('Субсидия утверждена')
  } catch (e: any) {
    showSnack(e.detail || 'Ошибка утверждения субсидии', 'error')
  } finally {
    approvingSubsidyId.value = null
  }
}

async function openMembersDialog(s: SubsidyRow) {
  await subsidyMembersDialogRef.value?.open(s)
}

// ── Contractor override ─────────────────────────
async function openContractorOverride(s: SubsidyRow) {
  await contractorOverrideDialogRef.value?.open(s)
}

// ── Events (Мероприятия) ─────────────────────────
async function loadEvents(subsidyId: number) {
  await eventsPanelRef.value?.reload(subsidyId)
}

// ── Ссылки на диалоги, вынесенные в components/subsidies/* ──
const eventsPanelRef = ref<InstanceType<typeof SubsidyEventsPanel> | null>(null)
const subsidyEditDialogRef = ref<InstanceType<typeof SubsidyEditDialog> | null>(null)
const subsidyDeleteDialogRef = ref<InstanceType<typeof SubsidyDeleteDialog> | null>(null)
const feoCategoryDialogRef = ref<InstanceType<typeof FeoCategoryDialog> | null>(null)
const feoCategoryDeleteDialogRef = ref<InstanceType<typeof FeoCategoryDeleteDialog> | null>(null)
const subsidyMembersDialogRef = ref<InstanceType<typeof SubsidyMembersDialog> | null>(null)
const contractorOverrideDialogRef = ref<InstanceType<typeof SubsidyContractorOverrideDialog> | null>(null)

const { loadTemplateVars } = useSubsidyTemplates()

// Контекст детали субсидии для вынесенных диалогов/компонентов (provide/inject,
// см. composables/subsidies/useSubsidyDetail.ts) — единственная точка, откуда они
// читают/пишут состояние, оставшееся в родителе. Волна 5c расширила его деревом
// ФЭО целиком (таблица/строки/Level 5/позиции из заявок/DnD/превышения/6 диалогов) —
// не второй контекст, а расширение существующего (Правило №6).
const subsidyDetailCtx = {
  router,
  allSubsidies,
  loadAll,
  selectedId,
  selectedSubsidy,
  feoCategories: feoTreeState.feoCategories,
  feoTree: feoTreeState.feoTree,
  flattenAll: feoTreeState.flattenAll,
  loadFeo,
  syncFeoFilled: feoTreeAmounts.syncFeoFilled,
  openAddPlannedItem: plannedItems.openAddPlannedItem,
  openConvertManualPlanToItem: plannedItems.openConvertManualPlanToItem,
  getFeoPlanManual: feoTreeAmounts.getFeoPlanManual,
  comparisonData: feoLevel5.comparisonData,
  refreshComparison: feoLevel5.refreshComparison,
  ensureComparison: feoLevel5.ensureComparison,
  refreshReqData,
  factForPlanned: feoLevel5.factForPlanned,
  photoPreview: feoLevel5.photoPreview,
  canEditFeo,
  downloadFeoTemplate,
  toggleSelect,
  canApproveSubsidy,
  approveSubsidy,
  approvingSubsidyId,
  startEdit,
  confirmDelete,
  openMembersDialog,
  openHistoryDialog,
  openContractorOverride,
  openAddFeoDialog,
  startFeoEdit,
  confirmFeoDelete,
  feoTableArea,
  feoItemsGroupBy: feoTreePrefs.feoItemsGroupBy,
  plannedBase: feoTreePrefs.plannedBase,
  plannedSumBase: feoTreePrefs.plannedSumBase,
  plannedQtyBase: feoTreePrefs.plannedQtyBase,
  selectedBudget: feoTreeAmounts.selectedBudget,
  selectedPlannedTotal: feoTreeAmounts.selectedPlannedTotal,
  plannedItemsByCat: feoTreeState.plannedItemsByCat,
  plannedItemsLoaded: feoTreeState.plannedItemsLoaded,
  mergedReqByCat: feoReqItems.mergedReqByCat,
  purchaseFoldersByCat: feoReqItems.purchaseFoldersByCat,
  expandedIds: feoTreePrefs.expandedIds,
  expandedReqItems: feoTreePrefs.expandedReqItems,
  expandedItemPanels: feoTreePrefs.expandedItemPanels,
  expandedPurchases: feoTreePrefs.expandedPurchases,
  expandedPlannedItems: feoTreePrefs.expandedPlannedItems,
  collapsedPlannedItems: feoTreePrefs.collapsedPlannedItems,
  feoSearch: feoTreeState.feoSearch,
  loadingComparison: feoLevel5.loadingComparison,
  feoFinDiff: feoTreeAmounts.feoFinDiff,
  feoPlannedTotalFor: feoTreeAmounts.feoPlannedTotalFor,

  // ── Волна 5c: дерево ФЭО (FeoTreeTable.vue + строки + 6 диалогов) ──
  feoResize,
  planTreeByCat: feoTreeState.planTreeByCat,
  isNodeVisible: feoTreeState.isNodeVisible,
  visibleFeoNodes: feoTreeState.visibleFeoNodes,
  unassignedFeo: feoTreeState.unassignedFeo,
  goToUnassignedFeoPurchases: () => {
    if (!selectedId.value) return
    router.push(`/orders?subsidy_id=${selectedId.value}`)
  },

  expandedStageRows: feoTreePrefs.expandedStageRows,
  togglePurchaseFolder: feoTreePrefs.togglePurchaseFolder,
  toggleStageRow: feoTreePrefs.toggleStageRow,
  toggleExpand: feoTreePrefs.toggleExpand,
  togglePlannedItemFolder: feoTreePrefs.togglePlannedItemFolder,

  residualBase: feoTreeAmounts.residualBase,
  feoBudgetFor: feoTreeAmounts.feoBudgetFor,
  feoEffectiveFor: feoTreeAmounts.feoEffectiveFor,
  manualChildFeoSum: feoTreeAmounts.manualChildFeoSum,
  hasManualChildFeo: feoTreeAmounts.hasManualChildFeo,
  isAutoNode: feoTreeAmounts.isAutoNode,
  feoRollup: feoTreeAmounts.feoRollup,
  feoPurchasedFor: feoTreeAmounts.feoPurchasedFor,
  feoFactFor: feoTreeAmounts.feoFactFor,
  feoResidualBaseFor: feoTreeAmounts.feoResidualBaseFor,
  feoResidualFor: feoTreeAmounts.feoResidualFor,
  feoDisplayedFor: feoTreeAmounts.feoDisplayedFor,
  feoRemainingWithPurchasesNote: feoTreeAmounts.feoRemainingWithPurchasesNote,
  feoIsOverBudget: feoTreeAmounts.feoIsOverBudget,
  feoChildrenBudgetDiff: feoTreeAmounts.feoChildrenBudgetDiff,
  feoHasOverspentDescendant: feoTreeAmounts.feoHasOverspentDescendant,
  feoOverspentDescendantText: feoTreeAmounts.feoOverspentDescendantText,
  feoOverspentDescendantTitle: feoTreeAmounts.feoOverspentDescendantTitle,
  isAutoQtyNode: feoTreeAmounts.isAutoQtyNode,
  feoQtyRequestsFor: feoTreeAmounts.feoQtyRequestsFor,
  feoQtyDisplayFor: feoTreeAmounts.feoQtyDisplayFor,
  mergedQtyDiff: feoTreeAmounts.mergedQtyDiff,
  feoInPlanScheduleFor: feoTreeAmounts.feoInPlanScheduleFor,
  feoPlannedRequestsFor: feoTreeAmounts.feoPlannedRequestsFor,
  feoPlannedDisplayFor: feoTreeAmounts.feoPlannedDisplayFor,
  feoResidualNoteFor: feoTreeAmounts.feoResidualNoteFor,
  feoPlanConsumedNoteFor: feoTreeAmounts.feoPlanConsumedNoteFor,
  feoForecastWarningFor: feoTreeAmounts.feoForecastWarningFor,
  isAutoAmtNode: feoTreeAmounts.isAutoAmtNode,
  isManualPosLeaf: feoTreeAmounts.isManualPosLeaf,
  hasOwnPlannedAmountFor: feoTreeAmounts.hasOwnPlannedAmountFor,
  feoOwnDirectionPlanFor: feoTreeAmounts.feoOwnDirectionPlanFor,
  mergedManualPriority: feoTreeAmounts.mergedManualPriority,
  totalFeoBudget: feoTreeAmounts.totalFeoBudget,
  totalFeoEffective: feoTreeAmounts.totalFeoEffective,
  totalFeoDiff: feoTreeAmounts.totalFeoDiff,
  totalFeoInPlanSchedule: feoTreeAmounts.totalFeoInPlanSchedule,

  isSaas: feoTreeExcess.isSaas,
  excessRequestLoading: feoTreeExcess.excessRequestLoading,
  excessDecideLoading: feoTreeExcess.excessDecideLoading,
  excessFor: feoTreeExcess.excessFor,
  excessCulpritFor: feoTreeExcess.excessCulpritFor,
  excessCulpritText: feoTreeExcess.excessCulpritText,
  isExcessCulpritActual: feoTreeExcess.isExcessCulpritActual,
  excessCulpritChipTooltip: feoTreeExcess.excessCulpritChipTooltip,
  excessFactFor: feoTreeExcess.excessFactFor,
  excessPlanFor: feoTreeExcess.excessPlanFor,
  excessPlanItemPurchaseTitle: feoTreeExcess.excessPlanItemPurchaseTitle,
  excessPlanApprovalPermanent: feoTreeExcess.excessPlanApprovalPermanent,
  excessApprovalFor: feoTreeExcess.excessApprovalFor,
  excessPendingNames: feoTreeExcess.excessPendingNames,
  excessMyPendingStep: feoTreeExcess.excessMyPendingStep,
  excessResolvedByName: feoTreeExcess.excessResolvedByName,
  excessResolvedDate: feoTreeExcess.excessResolvedDate,
  requestPlanExcessApproval: feoTreeExcess.requestPlanExcessApproval,
  decidePlanExcess: feoTreeExcess.decidePlanExcess,
  openExcessRejectDialog,

  toggleItemPanel: feoLevel5.toggleItemPanel,
  anyPlannedExpandedFor: feoLevel5.anyPlannedExpandedFor,
  toggleAllPlannedItemsForCategory: feoLevel5.toggleAllPlannedItemsForCategory,
  factForPlannedTotal: feoLevel5.factForPlannedTotal,
  factExcessReasonItems: feoLevel5.factExcessReasonItems,
  factExcessReasonRemainder: feoLevel5.factExcessReasonRemainder,
  stageChipLabelFor: feoLevel5.stageChipLabelFor,
  stageChipTitleFor: feoLevel5.stageChipTitleFor,
  stageChipColorFor: feoLevel5.stageChipColorFor,
  factStageHeaderFor: feoLevel5.factStageHeaderFor,
  planBreakdownText: feoLevel5.planBreakdownText,
  displayPlannedRowsFor: feoLevel5.displayPlannedRowsFor,
  unplannedActualFor: feoLevel5.unplannedActualFor,
  isOrphanedActual: feoLevel5.isOrphanedActual,
  comparisonPlanTotal: feoLevel5.comparisonPlanTotal,
  plannedItemIndentPx: feoLevel5.plannedItemIndentPx,
  calcDiff: feoLevel5.calcDiff,
  getDiffStyle: feoLevel5.getDiffStyle,
  stagesWithDiff: feoLevel5.stagesWithDiff,
  deletingPlannedItemId: feoLevel5.deletingPlannedItemId,
  deletePlannedItem: feoLevel5.deletePlannedItem,
  descendantCategoriesFor: feoLevel5.descendantCategoriesFor,
  movingPlannedItemId: feoLevel5.movingPlannedItemId,
  movePlannedItemToCategory: feoLevel5.movePlannedItemToCategory,
  reorderingPlannedItemId: feoLevel5.reorderingPlannedItemId,
  reorderPlannedItem: feoLevel5.reorderPlannedItem,

  feoStoppedLine: feoReqItems.feoStoppedLine,
  purchaseFolderTitle: feoReqItems.purchaseFolderTitle,
  matchedReqFor: feoReqItems.matchedReqFor,
  groupPlannedQty: feoReqItems.groupPlannedQty,
  groupPlannedTotal: feoReqItems.groupPlannedTotal,
  groupFactTotal: feoReqItems.groupFactTotal,
  reqOwnersAfter: feoReqItems.reqOwnersAfter,
  reqItemRowsFor: feoReqItems.reqItemRowsFor,
  reqRowIndent: feoReqItems.reqRowIndent,
  expandedReqItemPanels: feoReqItems.expandedReqItemPanels,
  reqPanelKey: feoReqItems.reqPanelKey,
  toggleReqItemPanel: feoReqItems.toggleReqItemPanel,
  virtGroupPurchaseIds: feoReqItems.virtGroupPurchaseIds,
  virtCart: feoReqItems.virtCart,
  virtEdit: feoReqItems.virtEdit,
  virtDelete: feoReqItems.virtDelete,
  reqItemPlanned: feoReqItems.reqItemPlanned,
  reqItemActual: feoReqItems.reqItemActual,
  mapReqItem: feoReqItems.mapReqItem,
  purchaseFoldersFor: feoReqItems.purchaseFoldersFor,
  kpiReqRowClass,
  kpiItemRowClass,
  kpiFolderClass,
  groupStatuses: feoReqItems.groupStatuses,

  dragNodeId: feoTreeDnd.dragNodeId,
  dragOverId: feoTreeDnd.dragOverId,
  onDragStart: feoTreeDnd.onDragStart,
  onDragOver: feoTreeDnd.onDragOver,
  onDragLeave: feoTreeDnd.onDragLeave,
  onDrop: feoTreeDnd.onDrop,
  onDropToRoot: feoTreeDnd.onDropToRoot,
  onDragEnd: feoTreeDnd.onDragEnd,
  reorderFeoNode: feoTreeDnd.reorderFeoNode,
  inlineBudgetId: feoTreeDnd.inlineBudgetId,
  inlineBudgetVal: feoTreeDnd.inlineBudgetVal,
  inlineInputEl: feoTreeDnd.inlineInputEl,
  startInlineBudget: feoTreeDnd.startInlineBudget,
  saveInlineBudget: feoTreeDnd.saveInlineBudget,
  cancelInlineBudget: feoTreeDnd.cancelInlineBudget,
  inlineQtyId: feoTreeDnd.inlineQtyId,
  inlineQtyVal: feoTreeDnd.inlineQtyVal,
  inlineQtyInputEl: feoTreeDnd.inlineQtyInputEl,
  startInlineQty: feoTreeDnd.startInlineQty,
  saveInlineQty: feoTreeDnd.saveInlineQty,
  cancelInlineQty: feoTreeDnd.cancelInlineQty,
  inlineAmtId: feoTreeDnd.inlineAmtId,
  inlineAmtVal: feoTreeDnd.inlineAmtVal,
  inlineAmtInputEl: feoTreeDnd.inlineAmtInputEl,
  startInlineAmt: feoTreeDnd.startInlineAmt,
  saveInlineAmt: feoTreeDnd.saveInlineAmt,

  openAlignBudgetConfirm,
  openReqItemEdit,
  openReqItemEditFromActual,
  confirmReqItemDelete,
  openWishItemFeoEdit,
  loadResiduals,
  mobile,

  openMapDialog: plannedItems.openMapDialog,
  openCreatePlannedFromActual: plannedItems.openCreatePlannedFromActual,
  openEditPlannedItem: plannedItems.openEditPlannedItem,
  openEditCategoryPlan: plannedItems.openEditCategoryPlan,
  mapTarget: plannedItems.mapTarget,
  mapCategoryId: plannedItems.mapCategoryId,
  applyMapping: plannedItems.applyMapping,
}
provideSubsidyDetail(subsidyDetailCtx)

// kpiNodeClass/activeKpi нужны функциям подсветки строк дерева выше (kpiReqRowClass/
// kpiItemRowClass/kpiFolderClass) — тот же module-singleton экземпляр, что получит
// SubsidyKpiCards.vue и FeoTreeRow.vue, вызвав useKpiDrilldown(ctx) самостоятельно.
const kpi = useKpiDrilldown(subsidyDetailCtx)

// Смена режима плана сбрасывает состав KPI-подсветки (те же id при 'manual'/'requests'/
// 'purchases' складываются иначе) — `kpi` объявлен как const выше по СКРИПТУ (не внутри
// callback'а), watch-коллбэк выполнится только при реальном изменении plannedBase (после
// полной инициализации), поэтому обращение к kpi здесь безопасно (тот же приём, что был
// в файле до разбиения).
watch(feoTreePrefs.plannedBase, () => {
  if (kpi.activeKpi.value && feoTreeState.plannedItemsLoaded.value) kpi.applyKpiExpansion()
})

onMounted(() => {
  loadAll()
  loadTemplateVars()
})
</script>

<style scoped>
/* ── Layout ── */
/* Ширина страницы не ограничивается (жалоба владельца 2026-08-12: «какого хуя
   половина окна не задействована»): раньше стоял max-width: 1600px, и на широком
   мониторе правая половина экрана пустовала, хотя таблица ФЭО как раз просит
   ширины — у неё шесть числовых колонок плюс раскрывающиеся панели плана и факта. */
.subsidies-page {
  padding: 20px 24px;
  width: 100%;
  box-sizing: border-box;
}

/* ── Header ── */
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
  flex-wrap: wrap;
  gap: 12px;
}
.page-header-left  { display: flex; align-items: center; }
.page-header-right { display: flex; align-items: center; }
.page-title    { font-size: 26px; font-weight: 700; color: var(--crm-text); line-height: 1.2; }
.page-subtitle { font-size: 13px; color: var(--crm-text-muted); margin-top: 2px; }

/* ── Empty state ── */
.empty-state {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; padding: 64px 0; color: var(--crm-text-faint);
}

/* ── Subsidies grid ── */
.subsidies-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}

.subsidy-card {
  background: var(--crm-surface);
  border-radius: 12px;
  border: 2px solid var(--crm-border);
  box-shadow: 0 1px 4px var(--crm-shadow);
  padding: 18px 20px;
  cursor: grab;
  transition: transform 0.15s, box-shadow 0.15s, border-color 0.15s, opacity 0.15s;
  position: relative;
}
.subsidy-card:active {
  cursor: grabbing;
}
.subsidy-card--dragging {
  opacity: 0.4;
}
.subsidy-card--drag-over {
  outline: 2px dashed rgb(var(--v-theme-primary));
  outline-offset: -2px;
}
.subsidy-card::after {
  content: 'Нажмите для подробностей';
  position: absolute;
  bottom: 6px;
  right: 12px;
  font-size: 10px;
  color: var(--crm-text-faint);
  opacity: 0;
  transition: opacity 0.15s;
}
.subsidy-card:hover::after {
  opacity: 1;
}
.subsidy-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px var(--crm-shadow-hover);
  border-color: rgba(var(--v-theme-primary), 0.3);
}
.subsidy-card--active {
  border-color: #3B82F6;
  box-shadow: 0 0 0 4px rgba(59,130,246,0.12), 0 4px 16px var(--crm-shadow-hover);
}

/* Шапка карточки: название — крупные полупрозрачные буквы в одну строку (фон),
   кнопки управления поверх них */
.sc-title-band {
  margin-bottom: 8px;
  display: flex; flex-direction: column; align-items: center;
}
.sc-actions { display: flex; gap: 2px; align-items: center; justify-content: center; }
.sc-name {
  font-weight: 800; color: var(--crm-text-muted);
  line-height: 1.15; text-align: center;
  white-space: nowrap; overflow: hidden;
  width: 100%; user-select: none;
}
.sc-delta-chip { height: auto !important; max-width: 100%; }
.sc-delta-chip :deep(.v-chip__content) { white-space: normal; line-height: 1.35; padding-top: 3px; padding-bottom: 3px; }
.sc-budget      { font-size: 22px; font-weight: 700; color: var(--crm-text); }
.sc-budget-label{ font-size: 11px; color: var(--crm-text-faint); margin-bottom: 12px; }

.sc-mini-row { display: flex; gap: 20px; }
.sc-mini-label { font-size: 11px; color: var(--crm-text-faint); margin-bottom: 2px; }
.sc-mini-val   { font-size: 13px; font-weight: 600; }

.sc-contractor { font-size: 12px; color: var(--crm-text-faint); display: flex; align-items: center; margin-top: 6px; }
.sc-footer { display: flex; align-items: center; justify-content: space-between; margin-top: 4px; }
.sc-pct { font-size: 11px; color: var(--crm-text-faint); }
.sc-feo-badge { display: flex; align-items: center; font-size: 11px; font-weight: 600; border-radius: 10px; padding: 1px 7px; }
.sc-feo-badge--ok  { color: #16a34a; background: #dcfce7; }
.sc-feo-badge--no  { color: var(--crm-text-faint); background: var(--crm-surface-hover); }

/* ── Summary bar ── */
.summary-bar {
  display: flex; align-items: center; gap: 0;
  background: var(--crm-surface);
  border-radius: 12px;
  border: 1px solid var(--crm-border);
  box-shadow: 0 1px 4px var(--crm-shadow);
  padding: 14px 24px;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 16px;
}
.summary-item  { display: flex; flex-direction: column; gap: 2px; }
.summary-item--link { cursor: pointer; border-radius: 8px; padding: 4px 8px; margin: -4px -8px; transition: background 0.15s; }
.summary-item--link:hover { background: rgba(59,130,246,0.08); }
.summary-item--link:hover .summary-label { color: #3B82F6; }
.summary-sep   { width: 1px; height: 32px; background: var(--crm-border-strong); flex-shrink: 0; }
.summary-label { font-size: 11px; color: var(--crm-text-faint); text-transform: uppercase; letter-spacing: 0.04em; transition: color 0.15s; }
.summary-value { font-size: 15px; font-weight: 700; color: var(--crm-text); }

/* ── Detail panel ── */
.detail-panel {
  background: var(--crm-surface);
  border-radius: 12px;
  border: 1px solid var(--crm-border);
  box-shadow: 0 1px 4px var(--crm-shadow);
  padding: 20px 24px;
  margin-bottom: 20px;
}
.detail-header {
  display: flex; align-items: center;
  margin-bottom: 16px;
}
.detail-title {
  font-size: 15px; font-weight: 600; color: var(--crm-text-secondary);
}

/* Detail KPI mini-cards */
.detail-kpis {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(236px, 1fr));
  grid-auto-rows: 1fr;
  gap: 12px;
  margin-bottom: 20px;
}
.detail-kpis .kpi-card {
  /* 132px даёт запас под 2-строчное значение (самая длинная сумма в проде —
     «1 109 245 278,72 ₽», см. .kpi-value ниже) без клиппинга родительским overflow:hidden */
  min-height: 132px;
  height: 100%;
}

/* ── KPI Cards (copied from DashboardView) ── */
.kpi-card {
  border-radius: 12px;
  padding: 18px 20px;
  display: flex;
  align-items: center;
  gap: 14px;
  cursor: default;
  transition: transform 0.25s cubic-bezier(0.22, 1, 0.36, 1),
              box-shadow 0.25s cubic-bezier(0.22, 1, 0.36, 1),
              border-color 0.25s ease;
  position: relative;
  overflow: hidden;
  border: 1px solid var(--crm-border);
  background: var(--crm-surface);
  box-shadow: 0 1px 4px var(--crm-shadow);
}
.kpi-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 12px 28px var(--crm-shadow-hover);
  border-color: var(--crm-border-strong);
}
.kpi-card:active {
  transform: translateY(-1px) scale(0.985);
  transition-duration: 0.1s;
}
.kpi-card::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  opacity: 0;
  transition: opacity 0.35s ease;
  z-index: -1;
}
.kpi-card:hover::before { opacity: 1; }
.kpi-budget::before            { box-shadow: 0 0 30px rgba(59,130,246,0.15); }
.kpi-plan_schedule::before     { box-shadow: 0 0 30px rgba(245,158,11,0.15); }
.kpi-work::before              { box-shadow: 0 0 30px rgba(99,102,241,0.15); }
.kpi-ordered::before           { box-shadow: 0 0 30px rgba(59,130,246,0.15); }
.kpi-contracts::before         { box-shadow: 0 0 30px rgba(2,132,199,0.15); }
.kpi-delivered::before         { box-shadow: 0 0 30px rgba(20,184,166,0.15); }
.kpi-delivered_unpaid::before  { box-shadow: 0 0 30px rgba(239,68,68,0.15); }
.kpi-paid::before              { box-shadow: 0 0 30px rgba(34,197,94,0.15); }
.kpi-free::before              { box-shadow: 0 0 30px rgba(148,163,184,0.15); }

.kpi-icon-box {
  width: 48px;
  height: 48px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: transform 0.25s cubic-bezier(0.22, 1, 0.36, 1);
}
.kpi-card:hover .kpi-icon-box { transform: scale(1.12) rotate(-3deg); }

.kpi-budget .kpi-icon-box            { background: rgba(59,130,246,0.12);  color: #3B82F6; }
.kpi-plan_schedule .kpi-icon-box     { background: rgba(245,158,11,0.12);  color: #F59E0B; }
.kpi-work .kpi-icon-box              { background: rgba(99,102,241,0.12);  color: #6366F1; }
.kpi-ordered .kpi-icon-box           { background: rgba(59,130,246,0.12);  color: #3B82F6; }
.kpi-contracts .kpi-icon-box         { background: rgba(2,132,199,0.12);   color: #0284C7; }
.kpi-delivered .kpi-icon-box         { background: rgba(20,184,166,0.12);  color: #14B8A6; }
.kpi-delivered_unpaid .kpi-icon-box  { background: rgba(239,68,68,0.12);   color: #EF4444; }
.kpi-paid .kpi-icon-box              { background: rgba(34,197,94,0.12);   color: #22C55E; }
.kpi-free .kpi-icon-box              { background: rgba(148,163,184,0.12); color: #94A3B8; }

.kpi-budget           { border-top: 3px solid #3B82F6; }
.kpi-plan_schedule    { border-top: 3px solid #F59E0B; }
.kpi-work             { border-top: 3px solid #6366F1; }
.kpi-ordered          { border-top: 3px solid #3B82F6; }
.kpi-contracts        { border-top: 3px solid #0284C7; }
.kpi-delivered        { border-top: 3px solid #14B8A6; }
.kpi-delivered_unpaid { border-top: 3px solid #EF4444; }
.kpi-paid             { border-top: 3px solid #22C55E; }
.kpi-free             { border-top: 3px solid #94A3B8; }
.kpi-card.kpi-over { border-top-color: #EF4444; }
.kpi-over .kpi-icon-box { background: rgba(239,68,68,0.12); color: #EF4444; }

.kpi-body  { flex: 1; min-width: 0; }
.kpi-value {
  /* Чуть меньше 20px + разрешённый перенос строк — гарантия, что даже самая длинная
     сумма в проде («1 109 245 278,72 ₽», 19 символов) не будет ни обрезана,
     ни съедена многоточием, независимо от ширины карточки (проверено Playwright,
     см. отчёт в задаче: scrollHeight/scrollWidth не превышают clientHeight/clientWidth) */
  font-size: 18px;
  font-weight: 700;
  color: var(--crm-text);
  white-space: normal;
  overflow-wrap: break-word;
  word-break: break-word;
  line-height: 1.25;
}
.kpi-label {
  font-size: 12px;
  color: var(--crm-text-muted);
  margin-top: 2px;
}
@media (max-width: 599px) {
  .kpi-card {
    flex-direction: column;
    align-items: flex-start;
    gap: 6px;
    padding: 12px;
  }
  .kpi-icon-box {
    width: 34px;
    height: 34px;
    border-radius: 8px;
  }
  .kpi-icon-box :deep(.v-icon) { font-size: 18px !important; }
  .kpi-body  { width: 100%; }
  .kpi-value { font-size: 15px; white-space: normal; overflow-wrap: break-word; word-break: break-word; line-height: 1.25; }
  .kpi-label { font-size: 10px; line-height: 1.2; white-space: normal; margin-top: 1px; }
}

/* FEO section */
.detail-feo-header {
  display: flex; align-items: center;
  margin-bottom: 12px;
}
.chart-card-title {
  font-size: 14px; font-weight: 600; color: var(--crm-text-secondary);
}

/* ── Dialogs ── */
.dialog-card {}
.dialog-title {
  display: flex; align-items: center;
  font-size: 16px !important; font-weight: 600 !important;
  padding: 16px 20px !important;
}

/* ── FEO Column Mapping ── */
.feo-imap-grid {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  padding-bottom: 4px;
}
.feo-imap-col {
  flex: 1;
  min-width: 130px;
  border: 1px dashed #ccc;
  border-radius: 6px;
  background: #fafafa;
  transition: border-color 0.15s, background 0.15s;
}
.feo-imap-col--over {
  border-color: #1976D2;
  background: rgba(25, 118, 210, 0.04);
}
.feo-imap-col--filled {
  border-style: solid;
  border-color: #43A047;
  background: #f6fff6;
}
.feo-imap-col--required {
  border-color: #ef9a9a;
  background: #fff8f8;
}
.feo-imap-col-hdr {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  color: #555;
  padding: 5px 7px 3px;
  border-bottom: 1px solid #e8e8e8;
  white-space: normal;
  word-break: break-word;
}
.feo-imap-col-body {
  padding: 5px;
  min-height: 58px;
}
.feo-imap-col-empty {
  font-size: 10px;
  color: #ccc;
  text-align: center;
  margin-top: 10px;
  font-style: italic;
}
.feo-imap-card {
  border-radius: 4px;
  background: #fff;
  border: 1px solid #e0e0e0;
  padding: 4px 6px;
  cursor: grab;
  user-select: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.feo-imap-card:hover {
  border-color: #1976D2;
  box-shadow: 0 1px 5px rgba(25, 118, 210, 0.15);
}
.feo-imap-card-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 2px;
}
.feo-imap-card-name {
  font-size: 11px;
  font-weight: 600;
  white-space: normal;
  word-break: break-word;
  flex: 1;
}
.feo-imap-card-x {
  font-size: 14px;
  line-height: 1;
  background: none;
  border: none;
  cursor: pointer;
  color: #aaa;
  padding: 0 2px;
  flex-shrink: 0;
}
.feo-imap-card-x:hover { color: #e53935; }
.feo-imap-card-x--grey { color: #bbb; }
.feo-imap-card-samples {
  font-size: 10px;
  color: #999;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 2px;
  line-height: 1.3;
}
.feo-imap-card--free {
  background: #fafafa;
}
.feo-imap-unresolved {
  border: 1px dashed #ccc;
  border-radius: 6px;
  padding: 6px 10px;
  min-height: 44px;
  transition: border-color 0.15s, background 0.15s;
}
.feo-imap-unresolved--over {
  border-color: #1976D2;
  background: rgba(25, 118, 210, 0.04);
}
.feo-imap-unresolved-label {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  color: #aaa;
  letter-spacing: 0.3px;
}
/* 12-05 F3: snapshot tree table */
.snapshot-tree-table { width: 100%; border-collapse: collapse; }
.snapshot-tree-table th, .snapshot-tree-table td { padding: 6px 8px; border-bottom: 1px solid rgba(0,0,0,0.08); font-size: 13px; }
.snapshot-tree-table .level-1 td { font-weight: 600; background: rgba(33,150,243,0.06); }
.snapshot-tree-table .level-2 td { background: rgba(33,150,243,0.03); }
.snapshot-tree-table tfoot td { background: rgba(0,0,0,0.05); padding: 8px; border-top: 2px solid rgba(0,0,0,0.15); }
.snapshot-tree-table .status-orphan td:first-child { color: rgb(180,120,0); }

/* ── KPI drill-down: подсветка карточки по клику (сама подсветка строк дерева —
     .feo-kpi-* — переехала в FeoTreeTable.vue вместе с разметкой строк, волна 5c) ── */
.kpi-card { cursor: pointer; }
.kpi-card--active {
  outline: 2px solid #fb923c; outline-offset: -2px;
  box-shadow: 0 0 0 4px rgba(251,146,60,.22);
}
</style>
