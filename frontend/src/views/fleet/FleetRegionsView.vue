<template>
  <div class="regions-view" :class="{ 'regions-view--light': !isDark }">
    <RegionsTopbar
      :total-vehicles="totalVehicles"
      :locations-count="sortedLocations.length"
      :query="vehicleSearchQuery"
      :results="vehicleSearchResults"
      :total="vehicleSearchTotal"
      :loading="vehicleSearchLoading"
      :active="vehicleSearchActive"
      :match-count="vehicleSearchMatchCount"
      :has-more="vehicleSearchHasMore"
      :vehicle-location-region="vehicleLocationRegion"
      @update:query="vehicleSearchQuery = $event"
      @open-location="openLocationDrill"
    />

    <RegionsDataNotice :unspecified-count="unspecifiedCount" />

    <RegionsKpiStrip
      :total-vehicles="totalVehicles"
      :locations-count="sortedLocations.length"
      :total-working="totalWorking"
      :total-repair="totalRepair"
      :total-broken="totalBroken"
    />

    <!-- ── Map + Top list ── -->
    <section class="rv-map-row">
      <RegionsMapPanel
        :loading="loadingRegions"
        :map-pins="mapPins"
        :search-active="vehicleSearchActive"
        :matched-ids="vehicleSearchMatchedRegionsArray"
        @pin-click="onPinClick"
      />
      <RegionsTopList
        :loading="loadingRegions"
        :top-locations="topLocations"
        @select="openLocationDrill"
      />
    </section>

    <RegionsCardsGrid
      :loading="loadingRegions"
      :sorted-locations="sortedLocations"
      :search-active="vehicleSearchActive"
      :matched-regions="vehicleSearchMatchedRegions"
      @select="openLocationDrill"
    />

    <RegionsTransferLog
      :loading="loadingTransfers"
      :transfers="transfers"
      :format-date="formatDate"
      @go-to-vehicle="goToVehicle"
    />

    <RegionsLocationDrillPopup
      :is-dark="isDark"
      :selected-location="selectedLocation"
      :selected-location-item="selectedLocationItem"
      :drill-loading="drillLoading"
      :drill-vehicles="drillVehicles"
      :filtered-drill-vehicles="filteredDrillVehicles"
      :drill-filter-query="drillFilterQuery"
      @close="closeLocationDrill"
      @go-to-vehicle="goToVehicle"
      @update:drillFilterQuery="drillFilterQuery = $event"
    />
  </div>
</template>

<script setup lang="ts">
// FleetRegionsView.vue — оркестратор страницы «География парка» (карта
// регионов автопарка). Разрезан на components/fleet/regions/* +
// composables/fleet/regions/* (ПРАВИЛО №5) — сам файл только собирает
// композаблы и прокидывает их состояние вниз пропсами/эмитами; apiFetch
// живёт исключительно внутри composables/fleet/regions/*.
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useTheme } from 'vuetify'
import '@/styles/fleet-regions.css'

import { loadCitiesCatalog } from '@/components/fleet/russiaCitiesCatalog'

import RegionsTopbar from '@/components/fleet/regions/RegionsTopbar.vue'
import RegionsDataNotice from '@/components/fleet/regions/RegionsDataNotice.vue'
import RegionsKpiStrip from '@/components/fleet/regions/RegionsKpiStrip.vue'
import RegionsMapPanel from '@/components/fleet/regions/RegionsMapPanel.vue'
import RegionsTopList from '@/components/fleet/regions/RegionsTopList.vue'
import RegionsCardsGrid from '@/components/fleet/regions/RegionsCardsGrid.vue'
import RegionsTransferLog from '@/components/fleet/regions/RegionsTransferLog.vue'
import RegionsLocationDrillPopup from '@/components/fleet/regions/RegionsLocationDrillPopup.vue'

import { useRegionsData } from '@/composables/fleet/regions/useRegionsData'
import { useVehicleSearch } from '@/composables/fleet/regions/useVehicleSearch'
import { useLocationDrill } from '@/composables/fleet/regions/useLocationDrill'
import { useMapPins } from '@/composables/fleet/regions/useMapPins'

// ─── Theme ───────────────────────────────────────────────────────────────────

const theme = useTheme()
const isDark = computed(() => theme.global.current.value.dark)
const router = useRouter()

// ─── Data: места нахождения + журнал передач (единственный источник сумм) ────

const {
  regionData,
  transfers,
  loadingRegions,
  loadingTransfers,
  sortedLocations,
  topLocations,
  unspecifiedCount,
  totalVehicles,
  totalWorking,
  totalRepair,
  totalBroken,
  fetchRegions,
  fetchTransfers,
  formatDate,
} = useRegionsData()

// ─── Vehicle search (владелец: «поиск по автомобилю, как в Иерархии») ────────

const {
  vehicleSearchQuery,
  vehicleSearchResults,
  vehicleSearchTotal,
  vehicleSearchLoading,
  vehicleSearchActive,
  vehicleSearchMatchedRegions,
  vehicleSearchMatchedRegionsArray,
  vehicleSearchMatchCount,
  vehicleSearchHasMore,
  vehicleLocationRegion,
} = useVehicleSearch()

// ─── Location drill (клик по пину / карточке / строке списка / результату поиска) ─

const {
  selectedLocation,
  drillLoading,
  drillVehicles,
  drillFilterQuery,
  selectedLocationItem,
  filteredDrillVehicles,
  openLocationDrill,
  closeLocationDrill,
  onPinClick,
} = useLocationDrill(regionData)

// ─── Map pins ────────────────────────────────────────────────────────────────

const { mapPins } = useMapPins(sortedLocations)

// ─── Navigation ──────────────────────────────────────────────────────────────

function goToVehicle(id: number) {
  router.push(`/fleet/vehicles/${id}`)
}

// ─── Init ────────────────────────────────────────────────────────────────────

onMounted(() => {
  fetchRegions()
  fetchTransfers()
  loadCitiesCatalog()
})
</script>

<style scoped></style>
