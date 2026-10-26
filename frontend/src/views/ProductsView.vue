<template>
  <v-container fluid class="pa-6">
    <ProductsToolbar
      :products-count="total"
      :products-count-capped="totalCapped"
      :deduplicating="deduplicating"
      :mobile="mobile"
      :view-mode="viewMode"
      @download-template="downloadTemplate"
      @open-import="importDialog.show = true"
      @open-download-photos="openDownloadPhotosDialog"
      @deduplicate="deduplicateProducts"
      @create="openCreate"
      @open-column-config="colConfigDialog = true"
      @update:view-mode="viewMode = $event"
    />

    <!-- Предложения правок каталога (Этап В, план item-tz-description.md,
         владелец 14.10.2026, п.3) — видят и решают только сотрудники с
         products.edit_catalog; кнопка заметная, со счётчиком ожидающих. -->
    <div v-if="canEditCatalog" class="mb-4">
      <v-btn
        variant="tonal" color="primary" prepend-icon="mdi-file-edit-outline"
        @click="proposalsDialogShow = true"
      >
        Предложения правок
        <v-chip v-if="pendingProposalsCount" size="small" color="warning" class="ml-2">{{ pendingProposalsCount }}</v-chip>
      </v-btn>
    </div>

    <ProductDescriptionProposals
      v-model="proposalsDialogShow"
      @changed="loadPendingProposalsCount"
    />

    <ProductsFilterBar
      v-model:search="search"
      v-model:filter-type="filterType"
      v-model:filter-category="filterCategory"
      v-model:filter-active="filterActive"
      v-model:filter-price-min="filterPriceMin"
      v-model:filter-price-max="filterPriceMax"
      v-model:filter-stale-only="filterStaleOnly"
      :type-options="typeOptions"
      :category-options="categoryOptions"
      :stale-products-count="staleProductsCount"
      @reset="resetFilters"
    />

    <!-- Table — серверная пагинация/сортировка (владелец, 26.10.2026), items —
         уже страница результатов, не весь каталог (см. useProductsData.ts). -->
    <ProductsTable
      v-if="effectiveView === 'table'"
      :headers="headers"
      :items="products"
      :total-count="total"
      :loading="loading"
      :page="tablePage"
      :items-per-page="tableItemsPerPage"
      :selected-ids="selectedIds"
      :is-superadmin="isSuperadmin"
      :is-admin="isAdmin"
      :tz-verifying="tzVerifying"
      @update:selected-ids="selectedIds = $event"
      @table-options="onTableOptions"
      @row-click="openEdit"
      @toggle-sharing="toggleSharing"
      @verify-tz="verifyTz"
      @unverify-tz="unverifyTz"
      @actualize="openActualizeDialog"
      @delete="confirmDelete"
      @bulk-edit="openBulkEdit"
      @toggle-active="bulkToggleActive"
      @bulk-delete="bulkDeleteDialog = true"
      @delete-all="deleteAllDialog = true"
    />

    <!-- Cards view — пагинация по 24 тем же серверным запросом -->
    <ProductsCards
      v-else
      :items="products"
      :total-count="total"
      :page="cardsPage"
      :total-pages="cardsTotalPages"
      :selected-ids="selectedIds"
      :is-superadmin="isSuperadmin"
      :card-photo-src="cardPhotoSrc"
      @update:selected-ids="selectedIds = $event"
      @update:page="onCardsPage"
      @select-all="selectedIds = products.map(p => p.id)"
      @edit="openEdit"
      @delete="confirmDelete"
      @bulk-edit="openBulkEdit"
      @toggle-active="bulkToggleActive"
      @bulk-delete="bulkDeleteDialog = true"
      @delete-all="deleteAllDialog = true"
    />

    <!-- Add / Edit dialog -->
    <ProductFormDialog
      v-model="dialog"
      v-model:name-search="nameSearch"
      :mobile="mobile"
      :editing-id="editingId"
      :can-edit-catalog="canEditCatalog"
      :empty-at-open="emptyAtOpen"
      :edit-meta="editMeta"
      :form="form"
      :name-suggestions="nameSuggestions"
      :is-duplicate-name="isDuplicateName"
      :type-options="typeOptions"
      :category-options="categoryOptions"
      :avg-price="avgPrice"
      :photo-preview="photoPreview"
      :photo-file="photoFile"
      :photo-file-list="photoFileList"
      :photo-cache-buster="photoCacheBuster"
      :downloading-photo="downloadingPhoto"
      :deleting-photo="deletingPhoto"
      :saving="saving"
      :duplicate-dialog="duplicateDialog"
      :duplicate-existing="duplicateExisting"
      @save="save"
      @clear-photo="clearUploadedPhoto"
      @download-photo="downloadSinglePhoto"
      @confirm-use-existing="confirmUseExisting"
      @confirm-create-new="confirmCreateNew"
      @cancel-duplicate="cancelDuplicate"
      @price-synced="syncPriceFromHistory($event.price)"
      @photo-file-change="onPhotoFileChange"
    />

    <!-- Delete confirm -->
    <ProductDeleteDialog
      v-model="deleteDialog"
      :target="deleteTarget"
      :deleting="deleting"
      :block-message="deleteBlockMessage"
      :block-impact="deleteBlockImpact"
      @confirm="doDelete"
    />

    <!-- Bulk delete confirm -->
    <ProductsBulkDeleteDialog
      v-model="bulkDeleteDialog"
      :count="selectedIds.length"
      :deleting="bulkDeleting"
      :blocked="bulkDeleteBlocked"
      @confirm="doBulkDelete"
    />

    <!-- Bulk edit category/type -->
    <ProductsBulkEditDialog
      v-model="bulkEditDialog"
      v-model:category="bulkEditCategory"
      v-model:type="bulkEditType"
      :count="selectedIds.length"
      :editing="bulkEditing"
      :category-options="categoryOptions"
      :type-options="typeOptions"
      @confirm="doBulkEdit"
    />

    <!-- Delete ALL confirm (superadmin only) -->
    <ProductsDeleteAllDialog
      v-model="deleteAllDialog"
      v-model:confirm-text="deleteAllConfirm"
      :total-count="total"
      :deleting="deletingAll"
      @confirm="doDeleteAll"
    />

    <!-- Import dialog -->
    <ProductsImportDialog
      :wizard="productsImport"
      :mobile="mobile"
    />

    <!-- Download photos dialog -->
    <ProductsDownloadPhotosDialog
      :dialog="dlPhotoDialog"
      :mobile="mobile"
      @download="doDownloadAllPhotos"
    />

    <!-- Column configurator dialog -->
    <ProductsColumnConfigDialog
      v-model="colConfigDialog"
      :col-order="colOrder"
      :drag-src-idx="dragSrcIdx"
      :all-columns="ALL_COLUMNS"
      @reset="resetColOrder"
      @drag-start="onDragStart"
      @drag-over="onDragOver"
      @drag-end="onDragEnd"
      @move="moveCol"
    />

    <!-- Dedup preview dialog -->
    <ProductsDedupDialog
      :dialog="dupDialog"
      :total-to-delete="totalDupsToDelete"
      :deduplicating="deduplicating"
      :mobile="mobile"
      @toggle-skip="toggleSkip"
      @confirm="confirmDeduplicate"
    />

    <!-- Актуализация цены -->
    <ProductsActualizeDialog
      :dialog="actualizeDialog"
      :form="actualizeForm"
      :price-source-options="priceSourceOptions"
      :mobile="mobile"
      @save="saveActualization"
    />
  </v-container>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useToast, type ToastType } from '@/composables/useToast'
import { apiFetch } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { ACTIONS } from '@/constants/permissionActions'

import ProductsToolbar from '@/components/products/ProductsToolbar.vue'
import ProductsFilterBar from '@/components/products/ProductsFilterBar.vue'
import ProductsTable from '@/components/products/ProductsTable.vue'
import ProductsCards from '@/components/products/ProductsCards.vue'
import ProductFormDialog from '@/components/products/ProductFormDialog.vue'
import ProductDeleteDialog from '@/components/products/ProductDeleteDialog.vue'
import ProductsBulkDeleteDialog from '@/components/products/ProductsBulkDeleteDialog.vue'
import ProductsBulkEditDialog from '@/components/products/ProductsBulkEditDialog.vue'
import ProductsDeleteAllDialog from '@/components/products/ProductsDeleteAllDialog.vue'
import ProductsImportDialog from '@/components/products/ProductsImportDialog.vue'
import ProductsDownloadPhotosDialog from '@/components/products/ProductsDownloadPhotosDialog.vue'
import ProductsColumnConfigDialog from '@/components/products/ProductsColumnConfigDialog.vue'
import ProductsDedupDialog from '@/components/products/ProductsDedupDialog.vue'
import ProductsActualizeDialog from '@/components/products/ProductsActualizeDialog.vue'
import ProductDescriptionProposals from '@/components/products/ProductDescriptionProposals.vue'

import { useProductsData } from '@/composables/products/useProductsData'
import { useProductsColumns, ALL_COLUMNS } from '@/composables/products/useProductsColumns'
import { useProductsForm } from '@/composables/products/useProductsForm'
import { useProductsDelete } from '@/composables/products/useProductsDelete'
import { useProductsBulkEdit } from '@/composables/products/useProductsBulkEdit'
import { useProductsImport } from '@/composables/products/useProductsImport'
import { useProductsPhotos } from '@/composables/products/useProductsPhotos'
import { useProductsDedup } from '@/composables/products/useProductsDedup'
import { useProductsTz } from '@/composables/products/useProductsTz'
import { useProductsActualize } from '@/composables/products/useProductsActualize'

const userRole = localStorage.getItem('user_role') || ''
const isSuperadmin = userRole === 'superadmin'
const isAdmin = userRole === 'admin' || userRole === 'superadmin'

// Защита каталога (Этап В, план item-tz-description.md, владелец 14.10.2026) —
// единственная проверка права здесь (ПРАВИЛО №6): тот же механизм
// authStore.hasAction(), что и в FeoCategoriesView.vue (ACTIONS.FEO_CATEGORY_EDIT).
const authStore = useAuthStore()
const canEditCatalog = computed(() => authStore.hasAction(ACTIONS.PRODUCTS_EDIT_CATALOG!))

const proposalsDialogShow = ref(false)
const pendingProposalsCount = ref(0)
async function loadPendingProposalsCount() {
  if (!canEditCatalog.value) { pendingProposalsCount.value = 0; return }
  try {
    const rows = await apiFetch<any[]>('/products/description-proposals?status=pending')
    pendingProposalsCount.value = rows.length
  } catch {
    // Счётчик необязателен — список внутри диалога всё равно подтянется сам.
  }
}

const toast = useToast()
const showSnack = (text: string, color: ToastType = 'success') => { toast.addToast(text, color) }

const {
  products, loading, total, totalCapped,
  search, filterType, filterCategory, filterActive, filterPriceMin, filterPriceMax, filterStaleOnly,
  resetFilters, load,
  typeOptions, categoryOptions, staleProductsCount, loadStaleCount,
  loadProductOptions,
  mobile, viewMode, effectiveView,
  tablePage, tableItemsPerPage, onTableOptions,
  cardsPage, cardsTotalPages, onCardsPage,
  cardPhotoSrc,
} = useProductsData(showSnack)

const {
  colOrder, headers, colConfigDialog, dragSrcIdx,
  onDragStart, onDragOver, onDragEnd, moveCol, resetColOrder,
} = useProductsColumns()

const {
  saving, dialog, editingId,
  photoFile, photoFileList, photoPreview,
  form, photoCacheBuster, editMeta, emptyAtOpen,
  nameSearch, nameSuggestions, isDuplicateName,
  avgPrice,
  onPhotoFileChange,
  openCreate, openEdit, save, toggleSharing,
  downloadingPhoto, deletingPhoto, clearUploadedPhoto, downloadSinglePhoto,
  duplicateDialog, duplicateExisting, confirmUseExisting, confirmCreateNew, cancelDuplicate,
  syncPriceFromHistory,
} = useProductsForm({ products, load, showSnack })

const {
  selectedIds,
  deleting, deleteDialog, deleteTarget, confirmDelete, doDelete,
  deleteBlockMessage, deleteBlockImpact,
  bulkDeleting, bulkDeleteDialog, doBulkDelete, bulkDeleteBlocked,
  deletingAll, deleteAllDialog, deleteAllConfirm, doDeleteAll,
  bulkToggleActive,
} = useProductsDelete({ products, load, showSnack })

const {
  bulkEditDialog, bulkEditCategory, bulkEditType, bulkEditing, openBulkEdit, doBulkEdit,
} = useProductsBulkEdit({ selectedIds, load, showSnack })

const productsImport = useProductsImport({ load, showSnack })
const { importDialog, downloadTemplate } = productsImport

const { dlPhotoDialog, openDownloadPhotosDialog, doDownloadAllPhotos } = useProductsPhotos({ load, showSnack })

const {
  deduplicating, dupDialog, deduplicateProducts, totalDupsToDelete, confirmDeduplicate, toggleSkip,
} = useProductsDedup({ load, showSnack })

const { tzVerifying, verifyTz, unverifyTz } = useProductsTz({ products, showSnack })

const {
  priceSourceOptions, actualizeDialog, actualizeForm, openActualizeDialog, saveActualization,
} = useProductsActualize({ products, showSnack, onActualized: loadStaleCount })

onMounted(() => { load(); loadProductOptions(); loadPendingProposalsCount(); loadStaleCount() })
</script>
