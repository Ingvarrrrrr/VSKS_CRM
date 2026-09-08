<template>
  <div class="contractors-page">

    <ContractorsToolbar
      :is-owner-plus="isOwnerPlus"
      :enrich-all-loading="enrichAllLoading"
      @download-template="im.downloadTemplate"
      @open-import="im.openContractorImport"
      @enrich-all="enrichAllFromFns"
      @open-duplicates="openDuplicatesDialog"
      @add="openAdd"
    />

    <ContractorsFilterBar
      v-model:search="search"
      v-model:filter-category="filterCategory"
      v-model:view-mode="viewMode"
      :categories="allProductCategories"
      :count="filtered.length"
      :total="contractorsTotal"
      :mobile="mobile"
      @search-input="onSearchInput"
      @clear="clearFilters"
    />

    <v-alert v-if="enrichAllResult" type="info" variant="tonal" density="compact" class="mb-4" closable @click:close="enrichAllResult = null">
      Обновлено: {{ enrichAllResult.updated }} из {{ enrichAllResult.total }}.
      Пропущено (уже заполнены): {{ enrichAllResult.skipped }}.
      <span v-if="enrichAllResult.errors.length"> Ошибок: {{ enrichAllResult.errors.length }}.</span>
    </v-alert>

    <!-- ── Bulk actions ── -->
    <div v-if="selectedIds.size > 0" class="d-flex align-center gap-3 mb-3 pa-3 bg-blue-lighten-5 rounded-lg">
      <v-icon icon="mdi-checkbox-marked-outline" color="primary" />
      <span class="text-body-2 font-weight-medium">Выбрано: {{ selectedIds.size }}</span>
      <v-spacer />
      <v-btn color="error" variant="tonal" size="small" prepend-icon="mdi-delete" @click="confirmBulkDelete">
        Удалить выбранных
      </v-btn>
      <v-btn variant="text" size="small" @click="selectedIds = new Set()">Снять выделение</v-btn>
    </div>

    <v-progress-linear v-if="loading" indeterminate color="primary" class="mb-4" />

    <ContractorsTable
      v-if="effectiveView === 'table'"
      :items="filtered"
      :loading="loading"
      :selected-ids="selectedIds"
      :page="contractorsPage"
      :total-pages="totalPages"
      @toggle-all="toggleAll"
      @toggle-one="toggleOne"
      @open-edit="openEdit"
      @open-categories="openCategoriesDialog"
      @delete="confirmDelete"
      @go-page="goPage"
    />

    <ContractorsCards
      v-else
      :items="pagedCards"
      :selected-ids="selectedIds"
      v-model:page="cardsPage"
      :total-pages="cardsTotalPages"
      @toggle-one="toggleOne"
      @open-edit="openEdit"
      @open-categories="openCategoriesDialog"
      @delete="confirmDelete"
    />

    <ContractorCategoriesDialog v-model="categoriesDialog" :contractor="categoriesDialogContractor" :mobile="mobile" />

    <!-- ── Add / Edit Dialog (reusable component, общая карточка контрагента) ── -->
    <ContractorEditDialog v-model="dialog" :contractor-id="editId" @saved="onContractorSaved" />

    <ContractorsBulkDeleteDialog
      v-model="bulkDeleteDialog"
      :count="selectedIds.size"
      v-model:confirm-count="bulkDeleteConfirmCount"
      :saving="saving"
      @cancel="cancelBulkDelete"
      @confirm="doBulkDelete"
    />

    <ContractorDeleteDialog v-model="deleteDialog" :target="deleteTarget" :saving="saving" @confirm="doDelete" />

    <ContractorsImportDialog :im="im" :mobile="mobile" />

    <ContractorsDuplicatesDialog
      v-model="showDuplicatesDialog"
      :loading="duplicatesLoading"
      :error="duplicatesError"
      :data="duplicatesData"
      :mobile="mobile"
      @open-contractor="openContractorCard"
    />

  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import ContractorEditDialog from '@/components/ContractorEditDialog.vue'
import { useCardView } from '@/composables/useCardView'
import { useToast, type ToastType } from '@/composables/useToast'

import ContractorsToolbar from '@/components/contractors/ContractorsToolbar.vue'
import ContractorsFilterBar from '@/components/contractors/ContractorsFilterBar.vue'
import ContractorsTable from '@/components/contractors/ContractorsTable.vue'
import ContractorsCards from '@/components/contractors/ContractorsCards.vue'
import ContractorCategoriesDialog from '@/components/contractors/ContractorCategoriesDialog.vue'
import ContractorDeleteDialog from '@/components/contractors/ContractorDeleteDialog.vue'
import ContractorsBulkDeleteDialog from '@/components/contractors/ContractorsBulkDeleteDialog.vue'
import ContractorsImportDialog from '@/components/contractors/ContractorsImportDialog.vue'
import ContractorsDuplicatesDialog from '@/components/contractors/ContractorsDuplicatesDialog.vue'

import { useContractorsData } from '@/composables/contractors/useContractorsData'
import { useContractorsEnrich } from '@/composables/contractors/useContractorsEnrich'
import { useContractorsSelection } from '@/composables/contractors/useContractorsSelection'
import { useContractorsImport } from '@/composables/contractors/useContractorsImport'
import { useContractorsDuplicates } from '@/composables/contractors/useContractorsDuplicates'
import type { ContractorWithStats } from '@/composables/contractors/contractorsTypes'

import '@/styles/contractors.css'

const userRole = localStorage.getItem('user_role') || ''
const isOwnerPlus = ['superadmin', 'account_owner'].includes(userRole)

const toast = useToast()
function showSnack(text: string, color: ToastType = 'success') {
  toast.addToast(text, color)
}

const dialog = ref(false)
const editId = ref<number | null>(null)

// Categories dialog
const categoriesDialog = ref(false)
const categoriesDialogContractor = ref<ContractorWithStats | null>(null)

const {
  contractorsTotal,
  contractorsPage,
  loading,
  search,
  filterCategory,
  allProductCategories,
  filtered,
  totalPages,
  clearFilters,
  onSearchInput,
  goPage,
  loadContractors,
} = useContractorsData(showSnack)

const { enrichAllLoading, enrichAllResult, enrichAllFromFns } = useContractorsEnrich(loadContractors)

const {
  saving,
  selectedIds,
  deleteDialog,
  deleteTarget,
  bulkDeleteDialog,
  bulkDeleteConfirmCount,
  toggleOne,
  toggleAll,
  confirmBulkDelete,
  doBulkDelete,
  confirmDelete,
  doDelete,
} = useContractorsSelection({ filtered: () => filtered.value, reload: loadContractors, showSnack })

const im = useContractorsImport({ reload: loadContractors, showSnack })

const {
  showDuplicatesDialog,
  duplicatesLoading,
  duplicatesError,
  duplicatesData,
  openDuplicatesDialog,
} = useContractorsDuplicates()

// ── Card view (table ↔ cards toggle) ─────────────────
// IMPORTANT: called AFTER `filtered` to avoid Temporal Dead Zone
const {
  mobile,
  viewMode,
  effectiveView,
  page: cardsPage,
  totalPages: cardsTotalPages,
  paged: pagedCards,
} = useCardView({
  storageKey: 'contractors_view_mode',
  source: () => filtered.value,
  search: () => search.value,
  searchFields: (c: any) => [c.name, c.inn, c.kpp, c.full_name],
  pageSize: 24,
})

function openContractorCard(cid: number) {
  // Карточка грузится компонентом по id — работает и для контрагентов не из текущей страницы
  editId.value = cid
  dialog.value = true
}

// ── Categories dialog ──────────────────────────────
function openCategoriesDialog(c: ContractorWithStats) {
  categoriesDialogContractor.value = c
  categoriesDialog.value = true
}

// ── Add / Edit ────────────────────────────────────
// Форма редактирования/создания вынесена в компонент ContractorEditDialog.
// Здесь только управление открытием диалога (editId + dialog) и перезагрузка списка.
function openAdd() {
  editId.value = null
  dialog.value = true
}

function openEdit(c: ContractorWithStats) {
  editId.value = c.id
  dialog.value = true
}

// Вызывается после успешного сохранения внутри ContractorEditDialog
async function onContractorSaved() {
  dialog.value = false
  await loadContractors()
}

function cancelBulkDelete() {
  bulkDeleteDialog.value = false
  bulkDeleteConfirmCount.value = ''
}

watch(filterCategory, () => { contractorsPage.value = 1; loadContractors() })
onMounted(() => { loadContractors() })
</script>
