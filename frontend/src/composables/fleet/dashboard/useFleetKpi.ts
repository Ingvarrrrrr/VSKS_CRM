// KPI-плитки дашборда автопарка: общие счётчики + проценты по статусам.
// Перенесено без изменений из VehicleDashboardView.vue при разбиении на модули.
import { ref, computed, type Ref } from 'vue'
import { apiFetch } from '@/api'

export interface KpiData {
  total_vehicles: number
  fuel_total_cost: number
  repairs_total_cost: number
  total_mileage_km: number
}

export interface FilterCounts {
  all: number
  working: number
  in_repair: number
  not_running: number
  no_report_30d: number
  for_disposal: number
  mock_demo?: boolean
}

export function useFleetKpi(maintenanceWarningsCount: Ref<number>) {
  const kpi = ref<KpiData>({ total_vehicles: 0, fuel_total_cost: 0, repairs_total_cost: 0, total_mileage_km: 0 })

  async function fetchKpi() {
    try {
      kpi.value = await apiFetch<KpiData>('/vehicles-dashboard/kpi')
    } catch (e) {
      console.error('[VehicleDash] kpi', e)
    }
  }

  const filterCounts = ref<FilterCounts>({
    all: 0, working: 0, in_repair: 0, not_running: 0, no_report_30d: 0, for_disposal: 0,
  })

  async function fetchFilterCounts() {
    try {
      filterCounts.value = await apiFetch<FilterCounts>('/vehicles-dashboard/filter-counts')
    } catch (e) {
      console.error('[VehicleDash] filter-counts', e)
    }
  }

  const total = computed(() => filterCounts.value.all || 1)
  const workingPct = computed(() => Math.round(filterCounts.value.working / total.value * 100))
  const repairPct = computed(() => Math.round(filterCounts.value.in_repair / total.value * 100))
  const notRunningPct = computed(() => Math.round(filterCounts.value.not_running / total.value * 100))
  const docsPct = computed(() => {
    const n = maintenanceWarningsCount.value
    return Math.round(Math.min(n / total.value * 100, 100))
  })

  return {
    kpi, fetchKpi,
    filterCounts, fetchFilterCounts,
    total, workingPct, repairPct, notRunningPct, docsPct,
  }
}
