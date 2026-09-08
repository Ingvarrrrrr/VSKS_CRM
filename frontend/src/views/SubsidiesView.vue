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
    <SubsidyDeleteDialog ref="subsidyDeleteDialogRef" v-model="showDeleteDialog" @deleted="onSubsidyDeleted" />
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
import '@/styles/subsidies.css'
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

// SubsidyDeleteDialog.vue уже убрала удалённую строку из allSubsidies оптимистично
// (единственный источник — ctx.allSubsidies, Правило №6). loadAll() здесь нужен
// только чтобы подтянуть пересчитанные сервером агрегаты (бюджеты/суммы других
// субсидий) — но его источник (/dashboard/charts) на проде иногда отдавал ответ
// на миг раньше, чем DELETE долетал до этого же чтения, и «удалённая» строка
// возвращалась в список: владелец видел карточку живой и жал «Удалить» ещё раз
// на уже удалённой субсидии (лог прода: DELETE 200, затем 404 ×3). Подтверждённое
// удаление ЭТОГО id в рамках текущей сессии сильнее устаревшего чтения — не даём
// loadAll() воскресить строку, которую сервер только что подтвердил как удалённую.
async function onSubsidyDeleted(deletedId: number) {
  await loadAll()
  allSubsidies.value = allSubsidies.value.filter(s => s.id !== deletedId)
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
