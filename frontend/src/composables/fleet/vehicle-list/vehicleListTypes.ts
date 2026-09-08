// vehicleListTypes.ts — типы реестра ТС (VehicleListView.vue). Дословный
// перенос из VehicleListView.vue, без изменения формы данных.

export interface OrgItem {
  id: number
  name: string
}

export interface VehicleListItem {
  id: number
  owner_org_id: number
  owner_org_name?: string
  assigned_org_id?: number | null
  assigned_org_name?: string | null
  assigned_text?: string | null
  brand?: string | null
  model?: string | null
  color?: string | null
  plate: string
  vin?: string | null
  type?: string | null
  state?: string | null
  fuel_type?: string | null
  current_odometer_km?: number | null
  next_to_km?: number | null
  insurance_until?: string | null
  created_at: string
  updated_at: string
  props?: Record<string, string>
}

export interface VehicleListResponse {
  items: VehicleListItem[]
  total: number
}

export interface FilterPreset {
  name: string
  states: string[]
  types: string[]
  fuelTypes: string[]
  ownerOrgIds: number[]
  assignedOrgIds: number[]
  search: string
}
