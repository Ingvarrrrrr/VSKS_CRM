// Режим просмотра, поиск и активный фильтр дашборда автопарка + inline drill-переходы.
// Перенесено без изменений из VehicleDashboardView.vue при разбиении на модули (ПРАВИЛО №5).
import { ref, computed, nextTick, type Ref } from 'vue'

export function useFleetFilters(mobile: Ref<boolean>, drillDocsOpen: Ref<boolean>) {
  const viewMode = ref<'cards' | 'table' | 'regions'>('cards')
  // On mobile always force 'cards' view (table is unreadable on small screens)
  const effectiveViewMode = computed<'cards' | 'table' | 'regions'>(() =>
    mobile.value ? 'cards' : viewMode.value
  )
  const searchQuery = ref('')
  const activeFilter = ref<string>('all')
  const selectedTypes = ref<string[]>([])
  const selectedRegions = ref<string[]>([])

  // Phase 29.3-drill-inline: клик KPI/региона → активирует chip-фильтр и скроллит к карточкам
  function applyKpiFilter(stateCode: string) {
    activeFilter.value = stateCode
    nextTick(() => {
      document.querySelector('.fleet-filters')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  }
  function applyRegionFilter(reg: string) {
    if (!selectedRegions.value.includes(reg)) {
      selectedRegions.value = [reg]
    } else {
      selectedRegions.value = []
    }
    nextTick(() => {
      document.querySelector('.fleet-filters')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  }
  function applyRegionAndState(region: string, state: 'working' | 'in_repair' | 'not_running') {
    selectedRegions.value = [region]
    activeFilter.value = state
    nextTick(() => {
      document.querySelector('.fleet-chips-row, .fleet-card-grid, .fleet-filters')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  }
  function resetAllFilters() {
    activeFilter.value = 'all'
    selectedTypes.value = []
    selectedRegions.value = []
    searchQuery.value = ''
    drillDocsOpen.value = false
    nextTick(() => {
      document.querySelector('.fleet-grid, .fleet-filters, .fleet-table')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  }

  return {
    viewMode, effectiveViewMode, searchQuery, activeFilter, selectedTypes, selectedRegions,
    applyKpiFilter, applyRegionFilter, applyRegionAndState, resetAllFilters,
  }
}
