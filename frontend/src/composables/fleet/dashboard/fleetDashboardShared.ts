// Общие константы и мелкие форматтеры дашборда автопарка.
// Перенесено без изменений из VehicleDashboardView.vue при разбиении на модули (ПРАВИЛО №5).

export const VEHICLE_TYPE_LABELS: Record<string, string> = {
  car_light: 'Легковой',
  suv: 'Внедорожник',
  pickup: 'Пикап',
  minivan: 'Минивэн',
  truck_van: 'Грузовой фургон',
  truck_board: 'Грузовой бортовой',
  truck_tank: 'Грузовой цистерна',
  truck_metal: 'Грузовой металловоз',
  bus: 'Автобус',
  special: 'Спецтехника',
  quadbike: 'Квадроцикл',
  snowmobile: 'Снегоход',
  boat: 'Лодка',
  boat_motor: 'Лодка с мотором',
  trailer: 'Прицеп',
  other: 'Другое',
}
// Отсортировано по алфавиту (владелец, 2026-09). NB: подписи в VEHICLE_TYPE_LABELS
// выше — своя, отличная от frontend/src/utils/vehicleLabels.ts копия (например,
// «Грузовой фургон» вместо «Фургон») — не объединено с общим источником задачей
// сортировки (задание запрещает менять тексты подписей, а объединение сейчас
// изменило бы видимый текст в этом дашборде); сортируется по её собственным
// значениям, коды (car_light, suv, ...) не меняются.
export const VEHICLE_TYPE_OPTIONS = Object.entries(VEHICLE_TYPE_LABELS)
  .map(([value, label]) => ({ value, label }))
  .sort((a, b) => a.label.localeCompare(b.label, 'ru'))

export const IC_ICONS: Record<string, string> = {
  ok: '✓', warn: '⚠', alert: '!', info: 'i',
}

export const STATE_LABELS: Record<string, string> = {
  working: 'Работает', broken: 'Сломан', in_repair: 'В ремонте',
  needs_repair: 'Треб. ремонта', destroyed: 'Уничтожен', utilized: 'Утилизирован',
}

export function fmtTs(ts: string): string {
  if (!ts) return ''
  try {
    return new Date(ts).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit' })
  } catch {
    return ts
  }
}
