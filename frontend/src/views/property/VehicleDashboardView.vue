<template>
  <div class="fleet-dash" :class="{ 'fleet-dash--light': !isDark }" :style="dashboardAccentStyle">
    <FleetTopbar
      v-model:search-query="searchQuery"
      @export="onExport"
      @trip-picker="goToTripPicker"
    />

    <FleetFilterBar
      v-model:selected-types="selectedTypes"
      v-model:selected-regions="selectedRegions"
      :vehicle-type-options="VEHICLE_TYPE_OPTIONS"
      :vehicle-type-labels="VEHICLE_TYPE_LABELS"
      :available-regions="availableRegions"
    />

    <FleetKpiCards
      :kpi="kpi"
      :filter-counts="filterCounts"
      :working-pct="workingPct"
      :repair-pct="repairPct"
      :not-running-pct="notRunningPct"
      :docs-pct="docsPct"
      :active-filter="activeFilter"
      :selected-types="selectedTypes"
      :selected-regions="selectedRegions"
      :search-query="searchQuery"
      :drill-docs-open="drillDocsOpen"
      :maintenance-warnings-count="maintenanceWarnings.length"
      @reset-all="resetAllFilters"
      @apply-filter="applyKpiFilter"
      @open-docs-drill="openDocsDrill"
    />

    <!-- ── Two-column: Regions + Driver reports ── -->
    <section class="fleet-two-col">
      <FleetRegionsPanel
        :region-items="regionItems"
        :top-regions="topRegions"
        :other-regions="otherRegions"
        :other-regions-total-count="otherRegionsTotalCount"
        :max-reg-count="MAX_REG_COUNT"
        :selected-regions="selectedRegions"
        :show-other-regions="showOtherRegions"
        :loading-regions="loadingRegions"
        @apply-region-filter="applyRegionFilter"
        @toggle-other="showOtherRegions = !showOtherRegions"
      />

      <FleetDriverReportsPanel
        :driver-reports="driverReports"
        :loading-reports="loadingReports"
      />
    </section>

    <FleetDocsDrillSection
      :open="drillDocsOpen"
      :loading="drillDocsLoading"
      :horizon="drillDocsHorizon"
      :vehicles="drillDocsVehicles"
      :drivers="drillDocsDrivers"
      @update:horizon="onDocsHorizonChange"
      @close="closeDocsDrill"
    />

    <!-- ── Filter chips + view toggle ── -->
    <FleetFilterChips
      :active-filter="activeFilter"
      :filter-counts="filterCounts"
      :maintenance-warnings-count="maintenanceWarnings.length"
      :mobile="mobile"
      :view-mode="viewMode"
      @update:active-filter="activeFilter = $event"
      @update:view-mode="viewMode = $event"
    />

    <!-- ── Cards view ── -->
    <FleetVehicleGrid
      v-if="effectiveViewMode === 'cards'"
      :vehicles="filteredVehicles"
      :loading="loadingAll"
      :to-card-data="toCardData"
      @detail="goToVehicle"
      @action="onCardAction"
    />

    <!-- ── Table view (existing functionality) ── -->
    <FleetVehicleTable
      v-else-if="effectiveViewMode === 'table'"
      :vehicles="filteredVehicles"
      :table-headers="tableHeaders"
      :search-query="searchQuery"
      :state-labels="STATE_LABELS"
      @row-click="goToVehicle"
    />

    <!-- ── Regions view ── -->
    <FleetRegionsView
      v-else-if="effectiveViewMode === 'regions'"
      :region-groups="regionGroups"
      :to-card-data="toCardData"
      @detail="goToVehicle"
      @action="onCardAction"
    />

    <!-- ── Fine Leaders Widget ── -->
    <section class="fleet-fine-leaders-section">
      <FineLeadersPodiumWidget @leader-click="onLeaderClick" />
      <DriverFinesDrill
        v-if="selectedDriver"
        :driver="selectedDriver"
        @close="selectedDriver = null"
      />
    </section>

    <!-- Phase 29.3-drill-inline: клик KPI/региона → activeFilter/selectedRegions inline -->
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useTheme, useDisplay } from 'vuetify'
import '@/styles/fleet-dashboard.css'

import FleetTopbar from '@/components/fleet/dashboard/FleetTopbar.vue'
import FleetFilterBar from '@/components/fleet/dashboard/FleetFilterBar.vue'
import FleetKpiCards from '@/components/fleet/dashboard/FleetKpiCards.vue'
import FleetRegionsPanel from '@/components/fleet/dashboard/FleetRegionsPanel.vue'
import FleetDriverReportsPanel from '@/components/fleet/dashboard/FleetDriverReportsPanel.vue'
import FleetDocsDrillSection from '@/components/fleet/dashboard/FleetDocsDrillSection.vue'
import FleetFilterChips from '@/components/fleet/dashboard/FleetFilterChips.vue'
import FleetVehicleGrid from '@/components/fleet/dashboard/FleetVehicleGrid.vue'
import FleetVehicleTable from '@/components/fleet/dashboard/FleetVehicleTable.vue'
import FleetRegionsView from '@/components/fleet/dashboard/FleetRegionsView.vue'
import FineLeadersPodiumWidget from '@/components/vehicles/FineLeadersPodiumWidget.vue'
import DriverFinesDrill from '@/components/fleet/DriverFinesDrill.vue'

import { VEHICLE_TYPE_LABELS, VEHICLE_TYPE_OPTIONS, STATE_LABELS } from '@/composables/fleet/dashboard/fleetDashboardShared'
import { useFleetKpi } from '@/composables/fleet/dashboard/useFleetKpi'
import { useMaintenanceWarnings } from '@/composables/fleet/dashboard/useMaintenanceWarnings'
import { useDocsDrill } from '@/composables/fleet/dashboard/useDocsDrill'
import { useFleetRegions } from '@/composables/fleet/dashboard/useFleetRegions'
import { useDriverReports } from '@/composables/fleet/dashboard/useDriverReports'
import { useFleetFilters } from '@/composables/fleet/dashboard/useFleetFilters'
import { useFleetVehicles, type VehicleCardData } from '@/composables/fleet/dashboard/useFleetVehicles'
import { useFleetOrgAccent } from '@/composables/fleet/dashboard/useFleetOrgAccent'
import { useFleetExport } from '@/composables/fleet/dashboard/useFleetExport'

const router = useRouter()
const theme = useTheme()
const { mobile } = useDisplay()
const isDark = computed(() => theme.global.current.value.dark)

// Клик по рекордсмену → список штрафов прямо на дашборде (без перехода)
const selectedDriver = ref<{ driver_key: string; driver_name: string | null; driver_kind: string } | null>(null)
function onLeaderClick(payload: { key: string; name: string | null; kind: string; id: number | null }): void {
  selectedDriver.value = { driver_key: payload.key, driver_name: payload.name, driver_kind: payload.kind }
}

// ── Docs drill ───────────────────────────────────────────────────────────────
const {
  drillDocsOpen, drillDocsLoading, drillDocsVehicles, drillDocsDrivers, drillDocsHorizon,
  openDocsDrill, closeDocsDrill,
} = useDocsDrill()

function onDocsHorizonChange(value: number) {
  drillDocsHorizon.value = value
  openDocsDrill()
}

// ── Filters / view mode ───────────────────────────────────────────────────────
const {
  viewMode, effectiveViewMode, searchQuery, activeFilter, selectedTypes, selectedRegions,
  applyKpiFilter, applyRegionFilter, resetAllFilters,
} = useFleetFilters(mobile, drillDocsOpen)

// ── Maintenance warnings ──────────────────────────────────────────────────────
const { maintenanceWarnings, fetchWarnings } = useMaintenanceWarnings()

// ── KPI ──────────────────────────────────────────────────────────────────────
const maintenanceWarningsCount = computed(() => maintenanceWarnings.value.length)
const { kpi, fetchKpi, filterCounts, fetchFilterCounts, workingPct, repairPct, notRunningPct, docsPct } =
  useFleetKpi(maintenanceWarningsCount)

// ── Regions ───────────────────────────────────────────────────────────────────
const {
  regionItems, loadingRegions, availableRegions, MAX_REG_COUNT,
  showOtherRegions, topRegions, otherRegions, otherRegionsTotalCount, fetchRegions,
} = useFleetRegions()

// ── Driver reports ────────────────────────────────────────────────────────────
const { driverReports, loadingReports, fetchDriverReports } = useDriverReports()

// ── All vehicles table data ───────────────────────────────────────────────────
const { loadingAll, fetchAllVehicles, filteredVehicles, regionGroups, tableHeaders, toCardData } =
  useFleetVehicles({ searchQuery, activeFilter, selectedTypes, selectedRegions, maintenanceWarnings })

// ── Orgs list (for accent color) ─────────────────────────────────────────────
const { fetchOrgs, dashboardAccentStyle } = useFleetOrgAccent()

// ── Export / navigation ───────────────────────────────────────────────────────
const { onExport, goToTripPicker } = useFleetExport(activeFilter, selectedTypes, router)

function goToVehicle(vehicleId: number) {
  router.push(`/property/vehicles/${vehicleId}`)
}

function onCardAction(payload: { type: string; vehicle: VehicleCardData }) {
  if (payload.type === 'card' || payload.type === 'detail') {
    router.push(`/property/vehicles/${payload.vehicle.id}`)
  }
}

// ── Init ──────────────────────────────────────────────────────────────────────
onMounted(() => {
  fetchKpi()
  fetchFilterCounts()
  fetchWarnings()
  fetchRegions()
  fetchDriverReports()
  fetchAllVehicles()
  fetchOrgs()
})
</script>

<style scoped></style>
