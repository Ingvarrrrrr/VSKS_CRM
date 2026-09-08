import { ref, computed, watch } from 'vue'
import { apiFetch } from '@/api'

// ─── Vehicle search (владелец: «поиск по автомобилю, как в Иерархии») ────────
// Сервер уже умеет искать по гос.№/марке/модели/VIN одним параметром — см.
// GET /vehicles?q= (переиспользуется тот же параметр, что и реестр ТС,
// VehicleListView.vue). Ограничение лимитом — страница рассчитана на рост
// парка далеко за нынешние 53 машины, тянуть весь список на клиент нельзя.
export interface VehicleSearchItem {
  id: number
  plate: string
  brand: string | null
  model: string | null
  location_city: string | null
}

const VEHICLE_SEARCH_LIMIT = 50

export function useVehicleSearch() {
  const vehicleSearchQuery = ref('')
  const vehicleSearchResults = ref<VehicleSearchItem[]>([])
  const vehicleSearchTotal = ref(0)
  const vehicleSearchLoading = ref(false)
  let vehicleSearchDebounce: ReturnType<typeof setTimeout> | null = null

  const vehicleSearchActive = computed(() => vehicleSearchQuery.value.trim().length > 0)

  // «Место нахождения» пусто/NULL → группа "Место не указано" — та же логика,
  // что normalize_city()+фолбэк на бэкенде (backend/app/services/geo_normalize.py,
  // используется в GET /vehicles-dashboard/by-region). Ключ обязан совпасть с
  // loc.region 1-в-1, иначе подсветка не найдёт свою карточку/пин.
  function vehicleLocationRegion(v: VehicleSearchItem): string {
    return (v.location_city || '').trim() || 'Место не указано'
  }

  const vehicleSearchMatchedRegions = computed(() => {
    const set = new Set<string>()
    for (const v of vehicleSearchResults.value) set.add(vehicleLocationRegion(v))
    return set
  })
  const vehicleSearchMatchedRegionsArray = computed(() => Array.from(vehicleSearchMatchedRegions.value))
  const vehicleSearchMatchCount = computed(() => vehicleSearchResults.value.length)
  const vehicleSearchHasMore = computed(() => vehicleSearchTotal.value > vehicleSearchResults.value.length)

  // 2026-09 (правка после ручной проверки): q — простой SQL ilike '%q%' по
  // сырому Vehicle.plate, а в БД госномер хранится БЕЗ пробела между буквой и
  // цифрами ("Р937ХУ 180"). Задача владельца прямо требует, чтобы работали ОБА
  // варианта — «Р 937» и «Р937» — набранные с живого госномера на машине или
  // скопированные из документа. Раз это ограничение самого хранения (не
  // подключаем tokenized/trigram-поиск ради одной страницы), решаем на клиенте:
  // параллельно пробуем запрос как есть и «сжатый» (без пробелов), сливаем по id.
  async function searchVehicles() {
    const q = vehicleSearchQuery.value.trim()
    if (!q) {
      vehicleSearchResults.value = []
      vehicleSearchTotal.value = 0
      vehicleSearchLoading.value = false
      return
    }
    vehicleSearchLoading.value = true
    try {
      const qCompact = q.replace(/\s+/g, '')
      const variants = qCompact !== q ? [q, qCompact] : [q]
      const responses = await Promise.all(
        variants.map(v =>
          apiFetch<{ items: VehicleSearchItem[]; total: number }>(
            `/vehicles?q=${encodeURIComponent(v)}&limit=${VEHICLE_SEARCH_LIMIT}`
          ).catch((e) => {
            console.error('[FleetRegions] searchVehicles variant failed', v, e)
            return { items: [] as VehicleSearchItem[], total: 0 }
          })
        )
      )
      // Запрос мог устареть, пока летел (пользователь печатает быстрее ответа) —
      // не затираем результат более свежего запроса более старым.
      if (vehicleSearchQuery.value.trim() !== q) return
      const byId = new Map<number, VehicleSearchItem>()
      let totalMax = 0
      for (const r of responses) {
        totalMax = Math.max(totalMax, r?.total ?? 0)
        for (const it of (r?.items ?? [])) byId.set(it.id, it)
      }
      vehicleSearchResults.value = Array.from(byId.values()).slice(0, VEHICLE_SEARCH_LIMIT)
      vehicleSearchTotal.value = Math.max(totalMax, vehicleSearchResults.value.length)
    } catch (e) {
      console.error('[FleetRegions] searchVehicles', e)
      vehicleSearchResults.value = []
      vehicleSearchTotal.value = 0
    } finally {
      if (vehicleSearchQuery.value.trim() === q) vehicleSearchLoading.value = false
    }
  }

  watch(vehicleSearchQuery, () => {
    if (vehicleSearchDebounce) clearTimeout(vehicleSearchDebounce)
    if (!vehicleSearchQuery.value.trim()) {
      // Очистка — карта/карточки должны мгновенно вернуться в обычный вид,
      // без ожидания дебаунса.
      vehicleSearchResults.value = []
      vehicleSearchTotal.value = 0
      vehicleSearchLoading.value = false
      return
    }
    vehicleSearchLoading.value = true
    vehicleSearchDebounce = setTimeout(searchVehicles, 300)
  })

  return {
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
    searchVehicles,
  }
}
