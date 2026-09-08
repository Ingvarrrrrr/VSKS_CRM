<template>
  <v-container fluid class="pa-4">
    <PaymentsHeader
      :total-count="totalCount"
      :import-id="importId"
      :pr-mobile="prMobile"
      v-model:pr-view-mode="prViewMode"
      v-model:show-column-picker="showColumnPicker"
      :get-columns="getExportColumns"
      :get-rows="getExportRows"
      :get-capture-el="getExportCaptureEl"
      @open-reconciliation="openReconciliation"
      @error="(msg) => error(msg)"
    />

    <PaymentReconciliationDialog
      v-model="reconciliationDialog"
      v-model:filter="reconciliationFilter"
      :loading="reconciliationLoading"
      :reconciliation="reconciliation"
      :filtered-rows="filteredReconciliationRows"
      :import-id="importId"
      :mobile="mobile"
      :reconciliation-row-class="reconciliationRowClass"
      :reconciliation-status-color="reconciliationStatusColor"
      :reconciliation-status-label="reconciliationStatusLabel"
      @match="openMatchById"
    />

    <PaymentsFilterBar
      :has-stale-parsed="hasStaleParsed"
      :import-id="importId"
      :active-filter-count="activeFilterCount"
      :has-filters="hasFilters"
      :loading="loading"
      :filtered-sum="filteredSum"
      :subsidies-list="subsidiesList"
      v-model:search-query="searchQuery"
      v-model:filter-subsidy-id="filterSubsidyId"
      v-model:f-date-from="fDateFrom"
      v-model:f-date-to="fDateTo"
      v-model:f-status="fStatus"
      v-model:f-matched="fMatched"
      v-model:f-confirmed="fConfirmed"
      v-model:f-inn="fInn"
      v-model:f-disposition="fDisposition"
      @dismiss-stale="staleParsedDismissed = true"
      @clear-import="clearImport"
      @clear-filters="clearFilters"
      @apply="applyFilters"
    />

    <!-- Table / Cards -->
    <div ref="registryArea">
      <PaymentsTable
        v-if="prEffectiveView === 'table'"
        :headers="tableHeaders"
        :items="searchedItemsWithRowNum"
        :loading="loading"
        :payments="payments"
        :col-filters="colConfigState.filters"
        :get-sort-by="getSortBy"
        :set-filter="setFilter"
        :apply-sort="applySort"
        :toggle-visible="toggleVisible"
        :uniq-values="uniqValues"
        :unbinding-id="unbindingId"
        v-model:expanded="expanded"
        v-model:page="page"
        @confirm="openConfirm"
        @match="openMatch"
        @unbind="unbind"
      />
      <PaymentsCards
        v-else
        :items="prPaged"
        :total-pages="prCardsTotalPages"
        :unbinding-id="unbindingId"
        v-model:page="prCardsPage"
        @confirm="openConfirm"
        @match="openMatch"
        @unbind="unbind"
      />
    </div>

    <!-- Column picker dialog -->
    <ColumnConfigDialog
      v-model="showColumnPicker"
      :all-columns="allColumnsRef"
      :state="colConfigState"
      :show-width="true"
      :groups="[
        { key: 'core', label: `Основные (${coreColumnDefs.length})` },
        { key: 'file', label: `В этом файле (${rawColumns.length})` },
        { key: 'all', label: `Все возможные (${masterListLength})` },
      ]"
      :toggle-visible="toggleVisible"
      :set-position="setPosition"
      :set-width="setColWidth"
      :reset="resetColumns"
    />

    <!-- Match dialog -->
    <PaymentMatchDialog
      v-model="matchDialog"
      :bank-payment-id="selectedPaymentId"
      @updated="onMatchUpdated"
    />

    <!-- Unbind confirm dialog -->
    <PaymentsUnbindDialog
      v-model="unbindDialog"
      :loading="unbindLoading"
      @confirm="doUnbind"
    />
  </v-container>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useToast } from '@/composables/useToast'
import ColumnConfigDialog from '@/components/ColumnConfigDialog.vue'
import PaymentMatchDialog from '@/components/PaymentMatchDialog.vue'
import PaymentsHeader from '@/components/payments/PaymentsHeader.vue'
import PaymentsFilterBar from '@/components/payments/PaymentsFilterBar.vue'
import PaymentsTable from '@/components/payments/PaymentsTable.vue'
import PaymentsCards from '@/components/payments/PaymentsCards.vue'
import PaymentReconciliationDialog from '@/components/payments/PaymentReconciliationDialog.vue'
import PaymentsUnbindDialog from '@/components/payments/PaymentsUnbindDialog.vue'
import { useCardView } from '@/composables/useCardView'
import { useDisplay } from 'vuetify'
import { usePaymentsColumns } from '@/composables/payments/usePaymentsColumns'
import { usePaymentsFilters } from '@/composables/payments/usePaymentsFilters'
import { usePaymentsData } from '@/composables/payments/usePaymentsData'
import { usePaymentsMatch } from '@/composables/payments/usePaymentsMatch'
import { usePaymentsReconciliation } from '@/composables/payments/usePaymentsReconciliation'

// ── Route & auth ───────────────────────────────────────────────────────────
const route = useRoute()
const router = useRouter()
const { success, error } = useToast()

// ── Import filter from query ────────────────────────────────────────────────
const importId = computed<number | null>(() => {
  const v = route.query.import_id
  return v ? Number(v) : null
})

function clearImport() {
  const q = { ...route.query }
  delete q.import_id
  router.replace({ query: q })
}

// ── Composables (Правило №5: логика по модулям, view — только оркестрация) ──
const {
  coreColumnDefs, showColumnPicker, rawColumns, masterListLength,
  allColumnsRef, colConfigState, visibleColumnHeaders,
  toggleVisible, setPosition, setColWidth, resetColumns, migrateFrom,
  setFilter, clearAllFilters, activeFilterCount,
  tableHeaders, localSort, getSortBy, applySort, uniqValues, matchesColumnFilters,
} = usePaymentsColumns({ importId })

const {
  fDateFrom, fDateTo, fStatus, fMatched, fConfirmed, fInn, fDisposition,
  searchQuery, filterSubsidyId, subsidiesList, loadSubsidies,
} = usePaymentsFilters()

const {
  payments, loading, totalCount, page, expanded,
  staleParsedDismissed, hasStaleParsed,
  loadPayments, applyFilters,
  searchedItems, searchedItemsWithRowNum, filteredSum,
} = usePaymentsData({
  filters: { fDateFrom, fDateTo, fStatus, fMatched, fConfirmed, fInn, fDisposition },
  importId,
  searchQuery,
  filterSubsidyId,
  colConfigState,
  matchesColumnFilters,
  localSort,
  onError: error,
})

const {
  reconciliationDialog, reconciliationLoading, reconciliation, reconciliationFilter,
  filteredReconciliationRows, openReconciliation,
  reconciliationRowClass, reconciliationStatusColor, reconciliationStatusLabel,
} = usePaymentsReconciliation({ importId, error })

const {
  matchDialog, selectedPaymentId, openMatch, openConfirm, openMatchById, onMatchUpdated,
  unbindDialog, unbindingId, unbindLoading, unbind, doUnbind,
} = usePaymentsMatch({
  onMatchUpdated() {
    loadPayments()
    // 27.4-22: если диалог сверки открыт — перезагружаем счётчики/строки
    if (reconciliationDialog.value) openReconciliation()
  },
  loadPayments,
  success,
  error,
})

// ── hasFilters / clearFilters — пересекает filters+columns composables ─────
const hasFilters = computed(() =>
  !!(fDateFrom.value || fDateTo.value || fStatus.value || fMatched.value || fConfirmed.value ||
    fInn.value || fDisposition.value || activeFilterCount.value > 0)
)

function clearFilters() {
  fDateFrom.value = ''
  fDateTo.value = ''
  fStatus.value = null
  fMatched.value = null
  fConfirmed.value = null
  fInn.value = ''
  fDisposition.value = null
  searchQuery.value = ''
  filterSubsidyId.value = null
  clearAllFilters()
  localSort.value = null
  applyFilters()
}

// ── Watch import_id changes in URL ──────────────────────────────────────────
watch(importId, () => {
  applyFilters()
})

// ── Export button getters (RegistryExportButton, через PaymentsHeader) ─────
const registryArea = ref<HTMLElement | null>(null)
function getExportColumns() {
  return visibleColumnHeaders.value
    .filter(h => !['actions', 'avatar', 'data-table-expand', 'data-table-select'].includes(h.key) && !!h.title)
    .map(h => ({ key: h.key, title: h.title, align: (h as any).align }))
}
function getExportRows() {
  return searchedItems.value
}
function getExportCaptureEl() {
  return registryArea.value
}

// ── Card view (table↔cards toggle) ───────────────────────────────────────────
const { mobile } = useDisplay()
const {
  mobile: prMobile,
  viewMode: prViewMode,
  effectiveView: prEffectiveView,
  page: prCardsPage,
  totalPages: prCardsTotalPages,
  paged: prPaged,
} = useCardView({
  storageKey: 'payment_registry_view_mode',
  // source returns already-filtered + sorted list (searchedItemsWithRowNum)
  source: () => searchedItemsWithRowNum.value,
})

// ── Init ──────────────────────────────────────────────────────────────────────
onMounted(() => {
  // Мигрируем старые LS ключи в новый формат (один раз, потом игнорируется)
  migrateFrom({ visible: 'payment_registry_columns', widths: 'payment_registry_col_widths' })
  loadPayments()
  loadSubsidies()
})
</script>
