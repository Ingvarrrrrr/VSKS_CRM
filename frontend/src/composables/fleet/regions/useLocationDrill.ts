import { ref, computed, type Ref } from 'vue'
import { apiFetch } from '@/api'
import type { MapPin } from '@/components/fleet/russiaMapPins'
import type { RegionItem } from './useRegionsData'

// Попап «список машин места нахождения» (клик по пину / карточке / строке
// списка / результату поиска ТС) — единственное место, где живёт это
// состояние; клики отовсюду вызывают openLocationDrill(region).
export function useLocationDrill(regionData: Ref<RegionItem[]>) {
  const selectedLocation = ref<string | null>(null)
  const drillLoading = ref(false)
  const drillVehicles = ref<any[]>([])
  // Фильтр ВНУТРИ попапа (владелец: «в попапе трудно найти нужный автомобиль») —
  // работает по уже загруженному drillVehicles, без похода на сервер.
  const drillFilterQuery = ref('')

  const selectedLocationItem = computed(() =>
    selectedLocation.value ? regionData.value.find(r => r.region === selectedLocation.value) ?? null : null
  )

  const filteredDrillVehicles = computed(() => {
    const q = drillFilterQuery.value.trim().toLowerCase()
    if (!q) return drillVehicles.value
    return drillVehicles.value.filter((v: any) =>
      String(v.plate || '').toLowerCase().includes(q) ||
      String(v.brand_model || '').toLowerCase().includes(q) ||
      String(v.brand || '').toLowerCase().includes(q) ||
      String(v.model || '').toLowerCase().includes(q)
    )
  })

  async function openLocationDrill(region: string) {
    selectedLocation.value = region
    drillVehicles.value = []
    drillFilterQuery.value = ''
    drillLoading.value = true
    try {
      const resp = await apiFetch<{ items: any[] }>(`/vehicles-dashboard/drill?dimension=region&value=${encodeURIComponent(region)}`)
      drillVehicles.value = Array.isArray(resp?.items) ? resp.items : []
    } catch (e) {
      console.error('[FleetRegions] openLocationDrill', e)
    } finally {
      drillLoading.value = false
    }
  }

  function closeLocationDrill() {
    selectedLocation.value = null
    drillFilterQuery.value = ''
  }

  function onPinClick(pin: MapPin) {
    openLocationDrill(String(pin.id))
  }

  return {
    selectedLocation,
    drillLoading,
    drillVehicles,
    drillFilterQuery,
    selectedLocationItem,
    filteredDrillVehicles,
    openLocationDrill,
    closeLocationDrill,
    onPinClick,
  }
}
