<template>
  <v-container fluid class="pa-6">
    <VehicleListHeader
      :total="total"
      :mobile="mobile"
      v-model:view-mode="vehicleViewMode"
      v-model:show-trip-banner="showTripBanner"
      :loading-template="loadingTemplate"
      :can-import="canImport"
      @download-template="downloadTemplate"
      @open-import="importDialogShow = true"
      @create="createDialogShow = true"
    />

    <VehicleListFilterBar
      v-model:filter-states="filterStates"
      v-model:filter-types="filterTypes"
      v-model:filter-fuel-types="filterFuelTypes"
      v-model:filter-owner-org-ids="filterOwnerOrgIds"
      v-model:filter-assigned-org-ids="filterAssignedOrgIds"
      v-model:filter-search="filterSearch"
      :state-options="stateOptions"
      :type-options="typeOptions"
      :fuel-type-options="fuelTypeOptions"
      :orgs-list="orgsList"
      :active-filters-count="activeFiltersCount"
      :saved-filter-presets="savedFilterPresets"
      @save-preset="saveFilterPreset"
      @open-columns="showColumnPicker = true"
      @reset-columns="cfg.reset()"
      @clear-all="clearAllFilters"
      @apply-preset="applyFilterPreset"
      @remove-preset="removeFilterPreset"
    />

    <!-- Table view -->
    <VehicleListTable
      v-if="vehicleEffectiveView === 'table'"
      :headers="dtHeaders"
      :items="vehicles"
      :loading="loading"
      :total="total"
      v-model:selected="selectedVehicles"
      v-model:expanded="expandedRows"
      v-model:page="page"
      v-model:items-per-page="itemsPerPage"
      :filters-state="cfg.state.value.filters"
      :get-sort-by="getSortBy"
      :type-options="typeOptions"
      :state-options="stateOptions"
      @set-filter="(key, v) => cfg.setFilter(key, v)"
      @sort="(key, dir) => applySort(key, dir)"
      @hide-column="key => cfg.toggleVisible(key, false)"
      @table-options="onTableOptions"
      @row-click="onRowClick"
    />

    <!-- Cards view -->
    <VehicleListCards
      v-else-if="vehicleEffectiveView === 'cards'"
      :items="vehicles"
      :loading="loading"
      :total="total"
      v-model:page="page"
      :items-per-page="itemsPerPage"
    />

    <!-- ── Create dialog ── -->
    <VehicleCreateDialog
      v-model="createDialogShow"
      :orgs-list="orgsList"
      :type-options="typeOptions"
      :state-options="stateOptions"
      @error="showError"
    />

    <!-- ── Import Dialog ── -->
    <VehicleImportDialog
      v-model="importDialogShow"
      :orgs="orgsList"
      @imported="onImported"
    />

    <!-- ── Column Config Dialog ── -->
    <ColumnConfigDialog
      v-model="showColumnPicker"
      :all-columns="allColumns"
      :state="cfg.state.value"
      :show-width="true"
      :toggle-visible="cfg.toggleVisible"
      :set-position="cfg.setPosition"
      :set-width="cfg.setWidth"
      :reset="cfg.reset"
    />

    <!-- ── Save Filter Preset Dialog ── -->
    <VehicleFilterPresetDialog
      v-model="filterPresetDialog.show"
      v-model:name="filterPresetDialog.name"
      @confirm="confirmSaveFilterPreset"
    />

    <!-- Error Dialog -->
    <VehicleListErrorDialog
      v-model="errorDialog.show"
      :message="errorDialog.message"
      :code="errorDialog.code"
      :correlation-id="errorDialog.correlationId"
      @copy="copyError"
    />

  </v-container>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { ACTIONS } from '@/constants/permissionActions'
import ColumnConfigDialog from '@/components/ColumnConfigDialog.vue'
import VehicleImportDialog from '@/components/vehicles/VehicleImportDialog.vue'
import VehicleListHeader from '@/components/fleet/vehicle-list/VehicleListHeader.vue'
import VehicleListFilterBar from '@/components/fleet/vehicle-list/VehicleListFilterBar.vue'
import VehicleListTable from '@/components/fleet/vehicle-list/VehicleListTable.vue'
import VehicleListCards from '@/components/fleet/vehicle-list/VehicleListCards.vue'
import VehicleCreateDialog from '@/components/fleet/vehicle-list/VehicleCreateDialog.vue'
import VehicleFilterPresetDialog from '@/components/fleet/vehicle-list/VehicleFilterPresetDialog.vue'
import VehicleListErrorDialog from '@/components/fleet/vehicle-list/VehicleListErrorDialog.vue'
import { useCardView } from '@/composables/useCardView'
import { useToast, type ToastType } from '@/composables/useToast'
import { useVehicleListColumns } from '@/composables/fleet/vehicle-list/useVehicleListColumns'
import { useVehicleListFilters } from '@/composables/fleet/vehicle-list/useVehicleListFilters'
import { useVehicleListData } from '@/composables/fleet/vehicle-list/useVehicleListData'
import { useVehicleListTemplate } from '@/composables/fleet/vehicle-list/useVehicleListTemplate'
import { useVehicleListErrorDialog } from '@/composables/fleet/vehicle-list/useVehicleListErrorDialog'
import { typeOptions, stateOptions, fuelTypeOptions } from '@/composables/fleet/vehicle-list/vehicleListLookups'

// ─────────────── Stores / Composables ───────────────

const route = useRoute()
const authStore = useAuthStore()

const canImport = computed(() => authStore.hasAction(ACTIONS.VEHICLE_IMPORT!))

// Trip picker banner — показывается если открыли список через кнопку «Путевой лист»
const showTripBanner = ref(false)

// ─────────────── Error dialog ───────────────

const { errorDialog, showError, copyError } = useVehicleListErrorDialog()

// ─────────────── Column config / sort ───────────────

const { cfg, allColumns, dtHeaders, showColumnPicker, sortBy, sortDesc, getSortBy, applySort } = useVehicleListColumns()

// ─────────────── Filters + presets ───────────────

const {
  filterStates, filterTypes, filterFuelTypes, filterOwnerOrgIds, filterAssignedOrgIds, filterSearch,
  activeFiltersCount, clearAllFilters,
  savedFilterPresets, loadSavedPresets, filterPresetDialog,
  saveFilterPreset, confirmSaveFilterPreset, applyFilterPreset, removeFilterPreset,
} = useVehicleListFilters({ clearColumnFilters: () => cfg.clearAllFilters() })

// ─────────────── Data loading ───────────────

const {
  vehicles, total, loading, page, itemsPerPage, orgsList, selectedVehicles, expandedRows,
  loadVehicles, loadOrgs, onTableOptions, onRowClick,
} = useVehicleListData({
  filters: { filterStates, filterTypes, filterFuelTypes, filterOwnerOrgIds, filterAssignedOrgIds, filterSearch },
  sortBy,
  sortDesc,
  onError: showError,
})

// ─────────────── Create dialog ───────────────

const createDialogShow = ref(false)

// ─────────────── Import reload ───────────────

const importDialogShow = ref(false)

function onImported() {
  loadVehicles()
}

// ─────────────── Template download (шапка реестра) ───────────────

const { loadingTemplate, downloadTemplate } = useVehicleListTemplate({ onError: showError })

// ─────────────── Card view (table ↔ cards toggle) ───────────────
const {
  mobile,
  viewMode: vehicleViewMode,
  effectiveView: vehicleEffectiveView,
} = useCardView({
  storageKey: 'vehicle_list_view_mode',
  source: () => Array.isArray(vehicles.value) ? vehicles.value : [],
  pageSize: 200, // server already paginates; use large size so useCardView doesn't re-paginate
})

// ─────────────── Snackbar ─────────────── единый механизм (useToast + ToastContainer)

const toast = useToast()

function showSnack(text: string, color: ToastType = 'success') {
  toast.addToast(text, color)
}

// ─────────────── Watchers ───────────────

watch(
  [filterStates, filterTypes, filterFuelTypes, filterOwnerOrgIds, filterAssignedOrgIds, filterSearch, sortBy, sortDesc],
  () => {
    page.value = 1
    loadVehicles()
  },
  { deep: true }
)

watch([page, itemsPerPage], () => { loadVehicles() })

// ─────────────── Lifecycle ───────────────

onMounted(() => {
  loadSavedPresets()
  loadOrgs()
  // Если открыли через кнопку «Путевой лист» — показать подсказку и активировать фильтр working
  if (route.query.pick_for === 'trip') {
    showTripBanner.value = true
    if (route.query.state === 'working') {
      filterStates.value = ['working']
    }
  }
  loadVehicles()
})

// Expose showSnack for import dialog
defineExpose({ showSnack })
</script>
