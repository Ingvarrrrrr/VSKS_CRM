// Единый источник русских подписей для строкового поля Vehicle.type («Тип ТС»).
//
// Дублирует backend/app/services/vehicle_enum_labels.py::TYPE_LABELS (значения
// синхронизированы намеренно — см. комментарий в том файле про то, почему
// backend и frontend не объединены в общий JSON: две технологии, два рантайма).
// На фронте же до 2026-09 существовало НЕСКОЛЬКО параллельных копий этой карты
// (VehicleDetailView.vue, VehicleListView.vue, VehicleLayoutPreview.vue) — эта
// не заменяет их все (см. отчёт задачи «разъезд иконок ТС»), а останавливает
// разрастание: новые места (VehicleCard.vue) обязаны использовать этот модуль,
// не заводить ещё одну карту рядом (Правило №5 — модульность).
export const VEHICLE_TYPE_LABEL: Record<string, string> = {
  car_light:   'Легковой',
  suv:         'Внедорожник',
  pickup:      'Пикап',
  minivan:     'Минивэн',
  truck_van:   'Фургон',
  truck_board: 'Грузовой',
  truck_tank:  'Цистерна',
  truck_metal: 'Металловоз',
  bus:         'Автобус',
  special:     'Спецтехника',
  quadbike:    'Квадроцикл',
  snowmobile:  'Снегоход',
  boat:        'Лодка',
  boat_motor:  'Лодка (мотор)',
  trailer:     'Прицеп',
  other:       'Другой',
}

export function vehicleTypeLabel(type?: string | null): string {
  if (!type) return ''
  return VEHICLE_TYPE_LABEL[type] ?? type
}

// Владелец (2026-09): «Тип ТС» шёл вразнобой в выпадающих списках карточки ТС
// и фильтрах реестра — отсортировать по алфавиту. Коды (car_light, suv, ...)
// не меняются, меняется только порядок отображения подписи. localeCompare с
// локалью 'ru' в браузере/Node корректно ставит «Ё» на словарное место (в
// отличие от сравнения по code point) — в отличие от backend (Python), где
// это не гарантировано без явной locale, здесь Intl-коллация надёжна.
export const VEHICLE_TYPE_OPTIONS: Array<{ value: string; label: string }> =
  Object.entries(VEHICLE_TYPE_LABEL)
    .map(([value, label]) => ({ value, label }))
    .sort((a, b) => a.label.localeCompare(b.label, 'ru'))
