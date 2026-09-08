// Раскрытие «Истекают документы» на дашборде автопарка: горизонт дней, список ТС и водителей.
// Перенесено без изменений из VehicleDashboardView.vue при разбиении на модули (ПРАВИЛО №5).
import { ref, nextTick } from 'vue'
import { apiFetch } from '@/api'

export function useDocsDrill() {
  const drillDocsOpen = ref(false)
  const drillDocsLoading = ref(false)
  const drillDocsVehicles = ref<any[]>([])
  const drillDocsDrivers = ref<any[]>([])
  const drillDocsHorizon = ref(30)

  async function openDocsDrill() {
    drillDocsOpen.value = true
    drillDocsLoading.value = true
    try {
      const res = await apiFetch<any>(`/vehicles-dashboard/expiring-docs-drill?days=${drillDocsHorizon.value}`)
      drillDocsVehicles.value = res.vehicles || []
      drillDocsDrivers.value = res.drivers || []
    } catch (e) {
      drillDocsVehicles.value = []
      drillDocsDrivers.value = []
    } finally {
      drillDocsLoading.value = false
    }
    nextTick(() => {
      document.querySelector('.docs-drill-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  }

  function closeDocsDrill() {
    drillDocsOpen.value = false
    drillDocsVehicles.value = []
    drillDocsDrivers.value = []
  }

  return {
    drillDocsOpen, drillDocsLoading, drillDocsVehicles, drillDocsDrivers, drillDocsHorizon,
    openDocsDrill, closeDocsDrill,
  }
}
