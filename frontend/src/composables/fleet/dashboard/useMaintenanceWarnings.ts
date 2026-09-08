// Предупреждения по документам ТС (ОСАГО/ТО/СТС) — счётчик и список для дашборда автопарка.
// Перенесено без изменений из VehicleDashboardView.vue при разбиении на модули (ПРАВИЛО №5).
import { ref } from 'vue'
import { apiFetch } from '@/api'

export interface MaintenanceWarning {
  vehicle_id: number
  warning_type: string
  days_left: number | null
  km_left: number | null
}

export function useMaintenanceWarnings() {
  const maintenanceWarnings = ref<MaintenanceWarning[]>([])

  async function fetchWarnings() {
    try {
      maintenanceWarnings.value = await apiFetch<MaintenanceWarning[]>('/vehicles-dashboard/maintenance-warning')
    } catch (e) {
      console.error('[VehicleDash] warnings', e)
    }
  }

  return { maintenanceWarnings, fetchWarnings }
}
