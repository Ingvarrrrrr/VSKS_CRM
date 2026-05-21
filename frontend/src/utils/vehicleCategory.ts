/** Высокоуровневая категория автомобиля от Vehicle.type. */
export type VehicleCategory = 'light' | 'truck' | 'passenger' | 'special' | 'other'

export const CATEGORY_LABEL: Record<VehicleCategory, string> = {
  light: 'Легковой',
  truck: 'Грузовой',
  passenger: 'Пассажирский',
  special: 'Спецтехника',
  other: 'Прочее',
}

export const CATEGORY_COLOR: Record<VehicleCategory, string> = {
  light: 'blue',
  truck: 'brown',
  passenger: 'cyan',
  special: 'orange',
  other: 'grey',
}

export function vehicleCategory(type: string | null | undefined): VehicleCategory {
  if (!type) return 'other'
  if (['car_light', 'suv', 'pickup'].includes(type)) return 'light'
  if (['truck_van', 'truck_board', 'truck_tank', 'truck_metal'].includes(type)) return 'truck'
  if (['minivan', 'bus'].includes(type)) return 'passenger'
  if (['special', 'quadbike', 'snowmobile', 'boat', 'boat_motor', 'trailer'].includes(type)) return 'special'
  return 'other'
}
