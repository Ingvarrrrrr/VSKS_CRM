// vehicleListLookups.ts — справочники (тип/состояние/топливо) и форматтеры
// ячеек реестра ТС. Дословный перенос из VehicleListView.vue.
import { VEHICLE_TYPE_LABEL, VEHICLE_TYPE_OPTIONS } from '@/utils/vehicleLabels'
import type { VehicleListItem } from './vehicleListTypes'

// Единый источник — frontend/src/utils/vehicleLabels.ts (Правило №5: раньше
// здесь была отдельная копия этой карты; убрана 2026-09 при сортировке «Тип
// ТС» по алфавиту, чтобы не держать два места с порядком/подписями).
export const TYPE_LABEL = VEHICLE_TYPE_LABEL

export const STATE_LABEL: Record<string, string> = {
  working:      'Рабочее',
  broken:       'Неисправно',
  in_repair:    'В ремонте',
  needs_repair: 'Требует ремонта',
  destroyed:    'Уничтожено',
  utilized:     'Утилизировано',
}

export const FUEL_TYPE_LABEL: Record<string, string> = {
  petrol:  'Бензин',
  diesel:  'Дизель',
  gas:     'Газ',
  hybrid:  'Гибрид',
  electric:'Электро',
  other:   'Другое',
}

export const TYPE_COLOR: Record<string, string> = {
  car_light: 'blue', suv: 'green', pickup: 'lime',
  minivan: 'cyan', truck_van: 'indigo',
  truck_board: 'brown', truck_tank: 'teal', bus: 'purple',
  special: 'orange', other: 'grey',
}

export const STATE_COLOR: Record<string, string> = {
  working: 'success', broken: 'error', in_repair: 'warning',
  needs_repair: 'orange', destroyed: 'grey', utilized: 'grey',
}

// Отсортировано по алфавиту (владелец, 2026-09) — см. VEHICLE_TYPE_OPTIONS.
export const typeOptions = VEHICLE_TYPE_OPTIONS
export const stateOptions = Object.entries(STATE_LABEL).map(([value, label]) => ({ value, label }))
export const fuelTypeOptions = Object.entries(FUEL_TYPE_LABEL).map(([value, label]) => ({ value, label }))

export function typeLabel(t?: string | null) { return t ? (TYPE_LABEL[t] ?? t) : '—' }
export function typeColor(t?: string | null) { return TYPE_COLOR[t ?? ''] ?? 'grey' }
export function stateLabel(s?: string | null) { return s ? (STATE_LABEL[s] ?? s) : '—' }
export function stateColor(s?: string | null) { return STATE_COLOR[s ?? ''] ?? 'grey' }
export function fuelTypeLabel(f?: string | null) { return f ? (FUEL_TYPE_LABEL[f] ?? f) : '—' }

// ─────────────── Date / warning helpers ───────────────

export function formatDate(d?: string | null): string {
  if (!d) return '—'
  try {
    return new Date(d).toLocaleDateString('ru-RU')
  } catch {
    return d
  }
}

export function isInsuranceExpiring(item: VehicleListItem): boolean {
  if (!item.insurance_until) return false
  const diff = new Date(item.insurance_until).getTime() - Date.now()
  return diff < 30 * 24 * 3600 * 1000
}

export function insuranceClass(item: VehicleListItem): string {
  if (!item.insurance_until) return 'text-medium-emphasis'
  const diff = new Date(item.insurance_until).getTime() - Date.now()
  if (diff < 0) return 'text-error font-weight-bold'
  if (diff < 30 * 24 * 3600 * 1000) return 'text-warning font-weight-medium'
  return ''
}

export function nextToClass(item: VehicleListItem): string {
  if (item.next_to_km == null || item.current_odometer_km == null) return ''
  const remaining = item.next_to_km - item.current_odometer_km
  if (remaining < 0) return 'text-error font-weight-bold'
  if (remaining < 1000) return 'text-warning'
  return ''
}
