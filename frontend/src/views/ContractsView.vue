<template>
  <v-container fluid class="pa-4">
    <ContractsToolbar
      :filtered-count="filtered.length"
      :total-count="contracts.length"
      :is-admin="isAdmin"
      :dup-loading="dupLoading"
      :mobile="mobile"
      v-model:view-mode="viewMode"
      @open-migrate="migrateDialog = true"
      @open-import="importDialog.show = true"
      @check-duplicates="checkDuplicates"
      @open-enrich="enrichDialog = true"
      @open-export="exportDialog = true"
      @add="openCreate"
      @open-columns="showColumnPicker = true"
      @file-dropped="onFileDropped"
    />

    <ContractsFilterBar
      v-model:search="search"
      v-model:f-subsidy="fSubsidy"
      v-model:f-type="fType"
      v-model:f-method="fMethod"
      v-model:f-contractor="fContractor"
      v-model:f-product="fProduct"
      v-model:f-date-from="fDateFrom"
      v-model:f-date-to="fDateTo"
      :used-subsidies="usedSubsidies"
      :used-contract-types="usedContractTypes"
      :used-purchase-methods="usedPurchaseMethods"
      :used-contractors="usedContractors"
      :filtered-sum="filteredSum"
      :has-filters="hasFilters"
      :cfg-active-filter-count="cfgActiveFilterCount"
      @clear-filters="clearFilters"
      @clear-column-filters="cfgClearAllFilters()"
    />

    <!-- ── Table ── -->
    <ContractsTable
      v-if="effectiveView === 'table'"
      :headers="tableHeaders"
      :items="filteredWithRowNum"
      :contracts="contracts"
      :loading="loading"
      v-model:expanded="expanded"
      :col-filters="colState.filters"
      :local-sort="localSort"
      :get-sort-by="getSortBy"
      :apply-sort="applySort"
      :set-filter="cfgSetFilter"
      :toggle-visible="toggleVisible"
      :uniq-values="uniqValues"
      :is-admin="isAdmin"
      :purchases-by-contract="purchasesByContract"
      :expanded-purchases="expandedPurchases"
      :load-purchases-for-contract="loadPurchasesForContract"
      :f-product="fProduct"
      @edit="openEdit"
      @confirm-delete="confirmDelete"
    />

    <!-- ── Cards view ── -->
    <ContractsCards
      v-else
      :paged-cards="pagedCards"
      v-model:cards-page="cardsPage"
      :cards-total-pages="cardsTotalPages"
      :is-admin="isAdmin"
      @edit="openEdit"
      @confirm-delete="confirmDelete"
    />

    <!-- Column Config Dialog -->
    <ColumnConfigDialog
      v-model="showColumnPicker"
      :all-columns="allColumns"
      :state="colState"
      :show-width="true"
      :groups="groups"
      :toggle-visible="toggleVisible"
      :set-position="setPosition"
      :set-width="setWidth"
      :reset="resetColumns"
    />

    <ContractsExportDialog
      v-model="exportDialog"
      :export-columns="exportColumns"
      :export-loading="exportLoading"
      :mobile="mobile"
      :on-export="doExport"
    />

    <ContractsDuplicatesDialog
      v-model="dupDialog"
      :duplicate-groups="duplicateGroups"
      :mobile="mobile"
      :on-merge="mergeContract"
    />

    <ContractsEditDialog
      :dialog="dialog"
      :dialog-initial-contractor="dialogInitialContractor"
      :on-contractor-picked="onContractorPicked"
      :subsidies="subsidies"
      :is-admin="isAdmin"
      :mobile="mobile"
      :approval-purchase-loading="approvalPurchaseLoading"
      :on-save="saveContract"
      :on-delete-from-dialog="startDeleteFromDialog"
      :on-open-monthly-stages="openMonthlyStagesFromDialog"
      :on-open-approval-purchase="openApprovalPurchase"
    />

    <!-- Monthly Stages Dialog -->
    <MonthlyStagesDialog
      v-model="monthlyStagesDialog.show"
      :contract-id="monthlyStagesDialog.contractId"
      :contract-name="monthlyStagesDialog.contractName"
      :contract-type="monthlyStagesDialog.contractType"
      :default-subsidy-id="monthlyStagesDialog.subsidyId"
      :default-amount="monthlyStagesDialog.defaultAmount"
      @created="onMonthlyStagesCreated"
    />

    <ContractsDeleteDialog :dialog="deleteDialog" :on-delete="doDelete" />

    <ContractsMigrateDialog
      v-model="migrateDialog"
      :migrating="migrating"
      :migrate-result="migrateResult"
      :on-migrate="doMigrate"
    />

    <ContractsEnrichDialog
      v-model="enrichDialog"
      :enriching="enriching"
      :enrich-result="enrichResult"
      :on-enrich="doEnrich"
    />

    <ContractsImportDialog
      :import-dialog="importDialog"
      :subsidy-options="subsidyOptions"
      :mobile="mobile"
      :on-close="closeImportDialog"
      :on-preview="doImportPreview"
      :on-import="doImportMapped"
    />

  </v-container>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiFetch } from '@/api'
import MonthlyStagesDialog from '@/components/MonthlyStagesDialog.vue'
import ColumnConfigDialog from '@/components/ColumnConfigDialog.vue'
import { useCardView } from '@/composables/useCardView'
import { useToast, type ToastType } from '@/composables/useToast'

import ContractsToolbar from '@/components/contracts/ContractsToolbar.vue'
import ContractsFilterBar from '@/components/contracts/ContractsFilterBar.vue'
import ContractsTable from '@/components/contracts/ContractsTable.vue'
import ContractsCards from '@/components/contracts/ContractsCards.vue'
import ContractsExportDialog from '@/components/contracts/ContractsExportDialog.vue'
import ContractsDuplicatesDialog from '@/components/contracts/ContractsDuplicatesDialog.vue'
import ContractsEditDialog from '@/components/contracts/ContractsEditDialog.vue'
import ContractsDeleteDialog from '@/components/contracts/ContractsDeleteDialog.vue'
import ContractsMigrateDialog from '@/components/contracts/ContractsMigrateDialog.vue'
import ContractsEnrichDialog from '@/components/contracts/ContractsEnrichDialog.vue'
import ContractsImportDialog from '@/components/contracts/ContractsImportDialog.vue'

import { useContractsColumns } from '@/composables/contracts/useContractsColumns'
import { useContractsData } from '@/composables/contracts/useContractsData'
import { useContractsFilters } from '@/composables/contracts/useContractsFilters'
import { useContractsDialog } from '@/composables/contracts/useContractsDialog'
import { useContractsMaintenance } from '@/composables/contracts/useContractsMaintenance'
import { useContractsExport } from '@/composables/contracts/useContractsExport'
import { useContractsImport } from '@/composables/contracts/useContractsImport'

const router = useRouter()
const route = useRoute()

// Prevent browser from opening dropped files globally
const preventDrop = (e: DragEvent) => { e.preventDefault(); e.stopPropagation() }
onMounted(() => {
  document.addEventListener('dragover', preventDrop)
  document.addEventListener('drop', preventDrop)
})
onUnmounted(() => {
  document.removeEventListener('dragover', preventDrop)
  document.removeEventListener('drop', preventDrop)
})

function onFileDropped(file: File) {
  importDialog.file = file
  importDialog.show = true
}

const userRole = localStorage.getItem('user_role') || ''
const isAdmin = ['admin', 'superadmin', 'org_admin'].includes(userRole)

const toast = useToast()
const showSnack = (text: string, color: ToastType = 'success') => { toast.addToast(text, color) }

// ── Composables (порядок важен: maintenance до dialog — dialog зовёт confirmDelete) ──
const {
  allColumns, groups,
  colState, toggleVisible, setPosition, setWidth, resetColumns, cfgSetFilter, cfgClearAllFilters, cfgActiveFilterCount,
  tableHeaders, showColumnPicker,
  localSort, getSortBy, applySort, uniqValues, matchesColumnFilters,
} = useContractsColumns(isAdmin)

const {
  contracts, subsidies, contractors, loading, expanded,
  purchasesByContract, expandedPurchases,
  loadContracts, loadSubsidies, loadContractors,
  loadPurchasesForContract, loadAllPurchases,
} = useContractsData({ showSnack })

const {
  dupDialog, dupLoading, duplicateGroups, checkDuplicates, mergeContract,
  migrateDialog, migrating, migrateResult, doMigrate,
  enrichDialog, enriching, enrichResult, doEnrich,
  deleteDialog, confirmDelete, doDelete,
} = useContractsMaintenance({ contracts, loadContracts, showSnack })

const {
  search,
  fSubsidy, fType, fMethod, fContractor, fProduct, fDateFrom, fDateTo,
  hasFilters, clearFilters,
  usedSubsidies, usedContractors, usedContractTypes, usedPurchaseMethods,
  filtered, filteredWithRowNum, filteredSum,
} = useContractsFilters({
  contracts, subsidies, contractors, purchasesByContract, expandedPurchases, expanded,
  matchesColumnFilters, localSort, loadAllPurchases,
})

const {
  dialog, dialogInitialContractor, onContractorPicked,
  openCreate, openEdit, saveContract, startDeleteFromDialog,
  monthlyStagesDialog, openMonthlyStagesFromDialog, onMonthlyStagesCreated,
  approvalPurchaseLoading, openApprovalPurchase,
} = useContractsDialog({ contracts, contractors, loadContracts, showSnack, router, confirmDelete })

const { exportDialog, exportColumns, exportLoading, doExport } = useContractsExport({
  filtered, purchasesByContract, showSnack,
})

const { importDialog, subsidyOptions, closeImportDialog, doImportPreview, doImportMapped } = useContractsImport({
  subsidies, loadContracts,
})

// ── Card view (table↔cards toggle) ────────────────────────────────────────
const { mobile, viewMode, effectiveView, page: cardsPage, totalPages: cardsTotalPages, paged: pagedCards } = useCardView({
  storageKey: 'contracts_view_mode',
  source: () => filteredWithRowNum.value,
  searchFields: (c: any) => [c.number, c.contractor_name, c.subsidy_name, c.subject, c.contractor_inn],
  pageSize: 24,
})

onMounted(async () => {
  // Читаем ?subsidy_id из URL и выставляем фильтр
  const qSub = route.query.subsidy_id
  if (qSub) {
    const id = Number(qSub)
    if (!Number.isNaN(id)) fSubsidy.value = [id]
  }
  // Phase 27.1.7: auto-enrich pending contracts on view load (idempotent, fire-and-forget)
  try {
    await apiFetch('/contracts/bulk-enrich-from-purchases', { method: 'POST', suppressErrorDialog: true })
  } catch (_) {
    // 403 для не-admin — игнорируем, не критично
  }
  loadContracts(); loadSubsidies()
  // База контрагентов ~51k — bulk-load первых 5000 не покрывал всю базу
  // (поиск промахивался по 46k). Грузим только первые 50 для начального
  // показа; полноценный поиск — server-side через onContractorSearch (вся база).
  await loadContractors()
})
</script>

<style scoped>
.import-dropzone {
  border: 2px dashed rgba(var(--v-border-color), 0.3);
  transition: all 0.2s;
  cursor: pointer;
}
.import-dropzone--active,
.import-dropzone:hover {
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.04);
}
</style>
