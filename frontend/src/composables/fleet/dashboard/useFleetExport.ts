// Экспорт в Excel и переход к пикеру путевого листа на дашборде автопарка.
// Перенесено без изменений из VehicleDashboardView.vue при разбиении на модули (ПРАВИЛО №5).
import type { Ref } from 'vue'
import type { Router } from 'vue-router'

export function useFleetExport(activeFilter: Ref<string>, selectedTypes: Ref<string[]>, router: Router) {
  async function onExport() {
    const token = localStorage.getItem('auth_token') || localStorage.getItem('access_token') || ''
    const params = new URLSearchParams()
    if (activeFilter.value && activeFilter.value !== 'all' && activeFilter.value !== 'docs_expiring') {
      params.set('state', activeFilter.value)
    }
    if (selectedTypes.value.length === 1) {
      const singleType = selectedTypes.value[0]
      if (singleType) params.set('type', singleType)
    }
    const url = `/api/vehicles/export/excel${params.toString() ? '?' + params.toString() : ''}`
    try {
      const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const blob = await res.blob()
      const dlUrl = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = dlUrl
      a.download = `Транспорт_${new Date().toISOString().slice(0, 10)}.xlsx`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(dlUrl)
    } catch (e) {
      console.error('[VehicleDash] export failed:', e)
      alert('Ошибка экспорта')
    }
  }

  function goToTripPicker() {
    // Переход в список ТС с фильтром «Рабочие» — юзер кликает машину → карточка → вкладка «Путёвки»
    router.push({ path: '/property/vehicles', query: { state: 'working', pick_for: 'trip' } })
  }

  return { onExport, goToTripPicker }
}
