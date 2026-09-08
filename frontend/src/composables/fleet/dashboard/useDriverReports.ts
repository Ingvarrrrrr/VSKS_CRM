// Свежие отчёты водителей (лента) на дашборде автопарка.
// Перенесено без изменений из VehicleDashboardView.vue при разбиении на модули (ПРАВИЛО №5).
import { ref } from 'vue'
import { apiFetch } from '@/api'

export interface ReportItem {
  vehicle_id: number
  plate: string
  type: string
  ic: string
  title: string
  author: string
  timestamp: string
}

export function useDriverReports() {
  const driverReports = ref<ReportItem[]>([])
  const loadingReports = ref(false)

  async function fetchDriverReports() {
    loadingReports.value = true
    try {
      const data = await apiFetch<ReportItem[]>('/vehicles-dashboard/driver-reports?limit=8')
      driverReports.value = Array.isArray(data) ? data : []
    } catch (e) {
      console.error('[VehicleDash] driver-reports', e)
      driverReports.value = []
    } finally {
      loadingReports.value = false
    }
  }

  return { driverReports, loadingReports, fetchDriverReports }
}
