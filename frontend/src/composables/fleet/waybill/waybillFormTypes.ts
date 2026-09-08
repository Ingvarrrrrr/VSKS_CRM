// Общие типы формы путевого листа. Вынесено из FleetWaybillFormView.vue при
// разбиении на components/fleet/waybill/* и composables/fleet/waybill/*
// (рефакторинг без изменения поведения, ПРАВИЛО №5).
import type { RouteStop } from '@/components/fleet/RouteStopsEditor.vue'

export interface Vehicle {
  id: number
  plate: string
  brand_model: string
  brand?: string
  model?: string
  year?: number
  vin?: string
  current_mileage_km?: number
  fuel_norm_summer?: number
  fuel_norm_winter?: number
  type?: string
}

export interface Driver {
  id: number
  full_name: string
  license_categories?: string
  license_number?: string
  experience_years?: number
  driver_tab_number?: string
}

export interface UserOption {
  id: number
  fullName: string
  role?: string
}

export interface WaybillForm {
  id?: number
  number: string
  status: string
  date_start: string
  date_end: string
  waybill_type: string
  vehicle_id?: number
  driver_user_id?: number
  purpose: string
  route_stops: RouteStop[]
  planned_mileage_km?: number
  planned_duration?: string
  work_hours_norm?: string
  odometer_start?: number
  odometer_finish?: number
  fuel_remaining_start?: number
  fuel_issued_l?: number
  fuel_remaining_finish?: number
  cargo_description?: string
  cargo_weight_t?: number
  passengers_count?: number
  // Pre inspections
  pre_mechanic_id?: number
  pre_mechanic_at?: string
  pre_mechanic_result?: string
  pre_doctor_id?: number
  pre_doctor_at?: string
  pre_doctor_result?: string
  // Post inspections
  post_mechanic_id?: number
  post_mechanic_at?: string
  post_mechanic_result?: string
  post_doctor_id?: number
  post_doctor_at?: string
  post_doctor_result?: string
  // Signature
  driver_signature?: string
  // Aside helpers
  tech_inspect_ok?: boolean
  med_inspect_ok?: boolean
  fill_percent?: number
  planned_duration_h?: number
  status_history?: any[]
  related_docs?: any[]
}

export const waybillTypes = [
  { label: 'Легковой (Форма № 3)', value: 'passenger' },
  { label: 'Грузовой (Форма № 4)', value: 'truck' },
  { label: 'Автобус (Форма № 6)', value: 'bus' },
]
