<template>
  <v-container fluid class="pa-6">
    <ProductsToolbar
      :products-count="products.length"
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

    <!-- Table -->
    <ProductsTable
      v-if="effectiveView === 'table'"
      :headers="headers"
      :items="filteredProducts"
      :loading="loading"
      :search="search"
      :selected-ids="selectedIds"
      :is-superadmin="isSuperadmin"
      :is-admin="isAdmin"
      :tz-verifying="tzVerifying"
      @update:selected-ids="selectedIds = $event"
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

    <!-- Cards view -->
    <ProductsCards
      v-else
      :items="pagedProducts"
      :total-count="filteredProducts.length"
      :page="cardsPage"
      :total-pages="cardsTotalPages"
      :selected-ids="selectedIds"
      :is-superadmin="isSuperadmin"
      :card-photo-src="cardPhotoSrc"
      @update:selected-ids="selectedIds = $event"
      @update:page="cardsPage = $event"
      @select-all="selectedIds = filteredProducts.map(p => p.id)"
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
      @save="save"
      @clear-photo="clearUploadedPhoto"
      @download-photo="downloadSinglePhoto"
      @photo-file-change="onPhotoFileChange"
      @add-price-link="addPriceLink"
      @remove-price-link="removePriceLink"
    />

    <!-- Delete confirm -->
    <ProductDeleteDialog
      v-model="deleteDialog"
      :target="deleteTarget"
      :deleting="deleting"
      @confirm="doDelete"
    />

    <!-- Bulk delete confirm -->
    <ProductsBulkDeleteDialog
      v-model="bulkDeleteDialog"
      :count="selectedIds.length"
      :deleting="bulkDeleting"
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
      :total-count="products.length"
      :deleting="deletingAll"
      @confirm="doDeleteAll"
    />

    <!-- Import dialog -->
    <ProductsImportDialog
      :dialog="importDialog"
      :mobile="mobile"
      @close="closeImportDialog"
      @import="doImport"
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
import { onMounted } from 'vue'
import { useToast, type ToastType } from '@/composables/useToast'

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

const toast = useToast()
const showSnack = (text: string, color: ToastType = 'success') => { toast.addToast(text, color) }

const {
  products, loading,
  search, filterType, filterCategory, filterActive, filterPriceMin, filterPriceMax, filterStaleOnly,
  resetFilters, load,
  typeOptions, categoryOptions, staleProductsCount, filteredProducts,
  mobile, viewMode, effectiveView, cardsPage, cardsTotalPages, pagedProducts,
  cardPhotoSrc,
} = useProductsData(showSnack)

const {
  colOrder, headers, colConfigDialog, dragSrcIdx,
  onDragStart, onDragOver, onDragEnd, moveCol, resetColOrder,
} = useProductsColumns()

const {
  saving, dialog, editingId,
  photoFile, photoFileList, photoPreview,
  form, photoCacheBuster, editMeta,
  nameSearch, nameSuggestions, isDuplicateName,
  avgPrice,
  onPhotoFileChange, addPriceLink, removePriceLink,
  openCreate, openEdit, save, toggleSharing,
  downloadingPhoto, deletingPhoto, clearUploadedPhoto, downloadSinglePhoto,
} = useProductsForm({ products, load, showSnack })

const {
  selectedIds,
  deleting, deleteDialog, deleteTarget, confirmDelete, doDelete,
  bulkDeleting, bulkDeleteDialog, doBulkDelete,
  deletingAll, deleteAllDialog, deleteAllConfirm, doDeleteAll,
  bulkToggleActive,
} = useProductsDelete({ products, load, showSnack })

const {
  bulkEditDialog, bulkEditCategory, bulkEditType, bulkEditing, openBulkEdit, doBulkEdit,
} = useProductsBulkEdit({ selectedIds, load, showSnack })

const { importDialog, closeImportDialog, downloadTemplate, doImport } = useProductsImport({ load, showSnack })

const { dlPhotoDialog, openDownloadPhotosDialog, doDownloadAllPhotos } = useProductsPhotos({ load, showSnack })

const {
  deduplicating, dupDialog, deduplicateProducts, totalDupsToDelete, confirmDeduplicate, toggleSkip,
} = useProductsDedup({ load, showSnack })

const { tzVerifying, verifyTz, unverifyTz } = useProductsTz({ products, showSnack })

const {
  priceSourceOptions, actualizeDialog, actualizeForm, openActualizeDialog, saveActualization,
} = useProductsActualize({ products, showSnack })

onMounted(() => { load() })
</script>
