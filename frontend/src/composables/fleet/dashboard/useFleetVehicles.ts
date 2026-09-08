// Сводная таблица ТС дашборда автопарка: загрузка, фильтрация, группировка по регионам.
// Перенесено без изменений из VehicleDashboardView.vue при разбиении на модули (ПРАВИЛО №5).
import { ref, computed, type Ref } from 'vue'
import { apiFetch } from '@/api'
import type { MaintenanceWarning } from './useMaintenanceWarnings'

export interface AllVehicleRow {
  vehicle_id: number
  plate: string
  brand_model: string
  state: string
  owner_org_name: string
  owner_org_color?: string | null
  assigned_org_color?: string | null
  fuel_cost: number
  repair_cost: number
  mileage_km: number
  insurance_overdue: boolean
  insurance_until: string | null
  // extra fields from detailed endpoint (may be absent)
  assigned_text?: string
  responsible_name?: string
  last_report_at?: string
  vin?: string
  type?: string
  year?: number
  color?: string
  odometer_km?: number
  akb_ok?: boolean | null
  tires_ok?: boolean | null
  mirrors_ok?: boolean | null
  has_radio?: boolean | null
  first_aid_kit_ok?: boolean | null
  fire_ext_ok?: boolean | null
  spare_wheel_ok?: boolean | null
  paint_ok?: boolean | null
  technical_state_note?: string
  sts_number?: string
  last_maintenance_at?: string
}

// ── Card data adapter ─────────────────────────────────────────────────────────
// Вынесена на верхний уровень модуля (не внутрь useFleetVehicles), чтобы её
// возвращаемый тип был доступен дочерним компонентам через VehicleCardData —
// без этого TS не мог сверить payload события @action с параметром обработчика.
export function toCardData(v: AllVehicleRow) {
  const [brand, ...rest] = (v.brand_model || '').split(' ')
  return {
    id: v.vehicle_id,
    plate: v.plate,
    brand: brand || '',
    model: rest.join(' '),
    year: v.year,
    color: v.color,
    type: v.type,
    state: v.state,
    vin: v.vin,
    owner_org_name: v.owner_org_name,
    owner_org_color: v.owner_org_color,
    assigned_org_color: v.assigned_org_color,
    assigned_text: v.assigned_text,
    responsible_name: v.responsible_name,
    last_report_at: v.last_report_at,
    insurance_until: v.insurance_until || undefined,
    sts_number: v.sts_number,
    odometer_km: v.odometer_km || v.mileage_km,
    last_maintenance_at: v.last_maintenance_at,
    technical_state_note: v.technical_state_note,
    akb_ok: v.akb_ok,
    tires_ok: v.tires_ok,
    mirrors_ok: v.mirrors_ok,
    has_radio: v.has_radio,
    first_aid_kit_ok: v.first_aid_kit_ok,
    fire_ext_ok: v.fire_ext_ok,
    spare_wheel_ok: v.spare_wheel_ok,
    paint_ok: v.paint_ok,
  }
}

export type VehicleCardData = ReturnType<typeof toCardData>

export interface FleetVehiclesFilters {
  searchQuery: Ref<string>
  activeFilter: Ref<string>
  selectedTypes: Ref<string[]>
  selectedRegions: Ref<string[]>
  maintenanceWarnings: Ref<MaintenanceWarning[]>
}

export function useFleetVehicles(filters: FleetVehiclesFilters) {
  const { searchQuery, activeFilter, selectedTypes, selectedRegions, maintenanceWarnings } = filters

  const allVehicles = ref<AllVehicleRow[]>([])
  const loadingAll = ref(false)

  async function fetchAllVehicles() {
    loadingAll.value = true
    try {
      const data = await apiFetch<AllVehicleRow[]>('/vehicles-dashboard/all-vehicles-summary')
      allVehicles.value = Array.isArray(data) ? data : []
    } catch (e) {
      console.error('[VehicleDash] all-vehicles', e)
    } finally {
      loadingAll.value = false
    }
  }

  // ── Filtering ─────────────────────────────────────────────────────────────────
  const filteredVehicles = computed(() => {
    let list = allVehicles.value

    // Search by plate/brand_model/vin/responsible
    if (searchQuery.value) {
      const q = searchQuery.value.toLowerCase().trim()
      list = list.filter(v => {
        const hay = `${v.plate} ${v.brand_model} ${v.vin || ''} ${v.responsible_name || ''}`.toLowerCase()
        return hay.includes(q)
      })
    }

    // Filter chip
    if (activeFilter.value === 'working') {
      list = list.filter(v => v.state === 'working')
    } else if (activeFilter.value === 'in_repair') {
      list = list.filter(v => ['in_repair', 'broken', 'needs_repair'].includes(v.state))
    } else if (activeFilter.value === 'not_running') {
      list = list.filter(v => ['destroyed', 'utilized'].includes(v.state))
    } else if (activeFilter.value === 'no_report') {
      const cutoff = Date.now() - 30 * 24 * 60 * 60 * 1000
      list = list.filter(v => {
        if (!v.last_report_at) return true
        return new Date(v.last_report_at).getTime() < cutoff
      })
    } else if (activeFilter.value === 'disposal') {
      list = list.filter(v => v.state === 'destroyed' || v.state === 'utilized')
    } else if (activeFilter.value === 'docs_expiring') {
      const warnIds = new Set(maintenanceWarnings.value.map(m => m.vehicle_id))
      list = list.filter(v => warnIds.has(v.vehicle_id))
    }

    // Type filter (multi)
    if (selectedTypes.value.length) {
      list = list.filter(v => v.type && selectedTypes.value.includes(v.type))
    }

    // Region filter (multi) — match against assigned_text with trim,
    // consistent with backend by_region which uses coalesce(assigned_text, 'Не указан')
    if (selectedRegions.value.length) {
      list = list.filter(v => {
        const vRegion = (v.assigned_text || '').trim() || 'Не указан'
        return selectedRegions.value.includes(vRegion)
      })
    }

    return list
  })

  // ── Region groups (for regions view) ─────────────────────────────────────────
  const regionGroups = computed(() => {
    const map: Record<string, { name: string; vehicles: AllVehicleRow[] }> = {}
    for (const v of filteredVehicles.value) {
      const key = v.assigned_text || v.owner_org_name || 'Не указан'
      if (!map[key]) map[key] = { name: key, vehicles: [] }
      map[key].vehicles.push(v)
    }
    return Object.values(map).sort((a, b) => b.vehicles.length - a.vehicles.length)
  })

  // ── Table headers ─────────────────────────────────────────────────────────────
  const tableHeaders = [
    { title: 'Гос.№', key: 'plate', width: 130 },
    { title: 'Марка/Модель', key: 'brand_model' },
    { title: 'Состояние', key: 'state', width: 140 },
    { title: 'Владелец', key: 'owner_org_name' },
    { title: 'Пробег км', key: 'mileage_km', align: 'end' as const, width: 100 },
    { title: 'ОСАГО', key: 'insurance_until', width: 130 },
  ]

  return {
    allVehicles, loadingAll, fetchAllVehicles,
    filteredVehicles, regionGroups, tableHeaders, toCardData,
  }
}
