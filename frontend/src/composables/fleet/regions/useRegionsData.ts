import { ref, computed } from 'vue'
import { apiFetch } from '@/api'

// RegionItem = «место нахождения» (Vehicle.location_city), а не организация.
// region: сам город/место ("ДНР г. Донецк") либо "Место не указано".
export interface RegionItem {
  region: string
  count: number
  shtab_label: string
  by_state: Record<string, number>
}

export interface TransferRow {
  id: number
  vehicle_id: number
  plate: string
  brand_model: string | null
  from_owner_org_id: number | null
  to_owner_org_id: number | null
  from_org_name: string | null
  to_org_name: string | null
  from_assigned_text: string | null
  to_assigned_text: string | null
  basis: string | null
  doc_number: string | null
  changed_at: string
  changed_by_user_id: number | null
}

// Данные по местам нахождения ТС + журнал передач — единственное место, где
// они грузятся (fetchRegions/fetchTransfers), остальные компоненты только
// читают агрегаты отсюда (ПРАВИЛО №6: один источник истины для сумм).
export function useRegionsData() {
  const regionData = ref<RegionItem[]>([])
  const transfers = ref<TransferRow[]>([])
  const loadingRegions = ref(false)
  const loadingTransfers = ref(false)

  const sortedLocations = computed(() =>
    [...regionData.value].sort((a, b) => b.count - a.count)
  )

  const topLocations = computed(() => sortedLocations.value.slice(0, 8))

  // 2026-09: доля машин без заполненного «Место нахождения» — показывается
  // пользователю явно, а не прячется тихим фолбэком.
  const unspecifiedCount = computed(() =>
    regionData.value.find(r => r.region === 'Место не указано')?.count ?? 0
  )

  const totalVehicles = computed(() => regionData.value.reduce((s, r) => s + r.count, 0))
  const totalWorking = computed(() => regionData.value.reduce((s, r) => s + (r.by_state?.working || 0), 0))
  const totalRepair = computed(() => regionData.value.reduce((s, r) => s + (r.by_state?.in_repair || 0) + (r.by_state?.needs_repair || 0), 0))
  const totalBroken = computed(() => regionData.value.reduce((s, r) => s + (r.by_state?.broken || 0), 0))

  async function fetchRegions() {
    // 2026-09: раньше сюда же грузился /organizations/?limit=500 для счётчика
    // «Филиалов» — этот эндпоинт требует superadmin и админу отдавал пустой
    // список, поэтому счётчик всегда показывал 0 (см. тот же комментарий в
    // VehicleListView.vue про /auth/my-orgs). Раз речь теперь идёт о месте
    // нахождения ТС, а не об организации-владельце, KPI и подписи строятся из
    // regionData — отдельный список организаций странице больше не нужен.
    loadingRegions.value = true
    try {
      const regionResp = await apiFetch<{ items: RegionItem[]; mock_demo?: boolean }>('/vehicles-dashboard/by-region')
      regionData.value = Array.isArray(regionResp.items) ? regionResp.items : []
    } catch (e) {
      console.error('[FleetRegions] fetchRegions', e)
    } finally {
      loadingRegions.value = false
    }
  }

  async function fetchTransfers() {
    loadingTransfers.value = true
    try {
      // Try global recent endpoint first
      try {
        const data = await apiFetch<TransferRow[]>('/vehicles-dashboard/transfer-history-recent?limit=20')
        transfers.value = Array.isArray(data) ? data : []
        return
      } catch {
        // global endpoint not available — fall through to per-vehicle aggregation
      }

      // Fallback: load recent vehicles and aggregate their transfer histories
      const summary = await apiFetch<{ items: { vehicle_id: number; plate: string; brand_model: string | null }[] }>(
        '/vehicles-dashboard/all-vehicles-summary'
      ).catch(() => ({ items: [] }))

      const vehicleIds = (summary.items || []).slice(0, 10).map((v: any) => v.vehicle_id)
      const rows: TransferRow[] = []

      await Promise.all(vehicleIds.map(async (vid: number) => {
        const vInfo = (summary.items || []).find((v: any) => v.vehicle_id === vid)
        try {
          const hist = await apiFetch<any[]>(`/vehicles/${vid}/transfer-history`)
          if (Array.isArray(hist)) {
            hist.slice(0, 3).forEach(h => {
              rows.push({
                ...h,
                plate: vInfo?.plate ?? '',
                brand_model: vInfo?.brand_model ?? null,
              })
            })
          }
        } catch {}
      }))

      rows.sort((a, b) => new Date(b.changed_at).getTime() - new Date(a.changed_at).getTime())
      transfers.value = rows.slice(0, 20)
    } catch (e) {
      console.error('[FleetRegions] fetchTransfers', e)
      transfers.value = []
    } finally {
      loadingTransfers.value = false
    }
  }

  function formatDate(iso: string): string {
    if (!iso) return '—'
    const d = new Date(iso)
    if (isNaN(d.getTime())) return iso
    return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
  }

  return {
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
  }
}
