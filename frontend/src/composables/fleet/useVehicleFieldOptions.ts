import { computed } from 'vue'
import { useVehicleFields } from '@/composables/useVehicleFields'
import { VEHICLE_TYPE_LABEL, VEHICLE_TYPE_OPTIONS } from '@/utils/vehicleLabels'

// ─────────────────────────────────────────────────────────────────────────
// Справочники карточки ТС — вынесены из VehicleDetailView.vue как есть
// (ПРАВИЛО №6: единственный источник, используется хедером и всеми
// карточками секции «Общее»). Часть списков — статические константы, часть
// (жёсткие справочники автоблока) — производные от useVehicleFields
// (единственный источник — backend/app/services/vehicle_sheet_dictionaries.py).
// ─────────────────────────────────────────────────────────────────────────

// Единый источник подписей типа ТС — frontend/src/utils/vehicleLabels.ts
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
  petrol:   'Бензин',
  diesel:   'Дизель',
  gas:      'Газ',
  hybrid:   'Гибрид',
  electric: 'Электро',
  other:    'Другое',
}

export const TYPE_COLOR: Record<string, string> = {
  car_light:   'blue',
  minivan:     'cyan',
  truck_van:   'indigo',
  truck_board: 'brown',
  truck_tank:  'teal',
  bus:         'purple',
  special:     'orange',
  other:       'grey',
}

export const STATE_COLOR: Record<string, string> = {
  working:      'success',
  broken:       'error',
  in_repair:    'warning',
  needs_repair: 'orange',
  destroyed:    'grey',
  utilized:     'grey',
}

// Отсортировано по алфавиту (владелец, 2026-09) — см. VEHICLE_TYPE_OPTIONS
// в frontend/src/utils/vehicleLabels.ts (единый источник, коды не меняются).
export const typeOptions = VEHICLE_TYPE_OPTIONS
export const stateOptions = Object.entries(STATE_LABEL).map(([value, label]) => ({ value, label }))
export const fuelTypeOptions = Object.entries(FUEL_TYPE_LABEL).map(([value, label]) => ({ value, label }))

// Полный список типов топлива для select в карточке ТС (Phase 29.3)
export const fuelTypeSelectItems = [
  { value: 'AI-92',  title: 'АИ-92' },
  { value: 'AI-95',  title: 'АИ-95' },
  { value: 'AI-98',  title: 'АИ-98' },
  { value: 'AI-100', title: 'АИ-100' },
  { value: 'DT',     title: 'Дизель' },
  { value: 'GAS',    title: 'Газ' },
  { value: 'other',  title: 'Другое' },
]

export const ptsCategoryOptions = ['A', 'B', 'BE', 'C', 'CE', 'D', 'DE', 'M', 'Tb', 'Tm']

export const ownershipBasisOptions = [
  'Договор купли-продажи',
  'Договор дарения',
  'Свидетельство о праве на наследство',
  'Судебное решение',
  'Договор пожертвования',
  'Передача из другой организации',
]

export const ptsKindOptions = [
  { value: 'paper', title: 'Бумажный' },
  { value: 'electronic', title: 'Электронный' },
]

// Пропуска — 5 пар (номер + дата истечения), рендерятся в цикле в секции «Пропуска»
export const passFieldDefs: { key: string; untilKey: string; label: string }[] = [
  { key: 'pass_zo', untilKey: 'pass_zo_until', label: 'Пропуск ЗО' },
  { key: 'pass_ho', untilKey: 'pass_ho_until', label: 'Пропуск ХО' },
  { key: 'pass_dnr', untilKey: 'pass_dnr_until', label: 'Пропуск ДНР' },
  { key: 'pass_lnr', untilKey: 'pass_lnr_until', label: 'Пропуск ЛНР' },
  { key: 'pass_moscow', untilKey: 'pass_moscow_until', label: 'Пропуск Москва' },
]

// ── Автоблок (актуализация 2026-08-31): списки ниже ограничены правилами
// проверки данных листа владельца — единственный источник значений теперь
// backend (GET /api/vehicle-fields → options), см. useVehicleFields.getFieldOptions.
// Вторую копию списков здесь не держим: если backend ещё не загрузил реестр,
// список временно пуст (а не устаревший хардкод).
export function useVehicleFieldOptions() {
  const { getFieldOptions } = useVehicleFields()

  const paintConditionOptions = computed(() => getFieldOptions('paint_condition') ?? [])
  const tiresTypeOptions = computed(() => getFieldOptions('tires_type') ?? [])
  const bodyTypeOptions = computed(() => getFieldOptions('body_type') ?? [])
  const tiresConditionOptions = computed(() => getFieldOptions('tires_condition') ?? [])
  const techInspectionStatusOptions = computed(() => getFieldOptions('tech_inspection_status') ?? [])
  // Пять полей «Пропуск X» делят один набор значений (Да/Нет/Не требуется/Не выпускался).
  const passStatusOptions = computed(() => getFieldOptions('pass_zo') ?? [])

  return {
    paintConditionOptions,
    tiresTypeOptions,
    bodyTypeOptions,
    tiresConditionOptions,
    techInspectionStatusOptions,
    passStatusOptions,
  }
}
