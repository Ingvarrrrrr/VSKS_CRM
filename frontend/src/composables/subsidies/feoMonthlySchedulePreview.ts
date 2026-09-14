// Единственное место, вызывающее GET /feo-planned-items/monthly-schedule-preview
// (владелец, Волна 3, п.2-3 — «6 мес. 20 дн. · итого N ₽» вместо ручного ввода
// целого «Количество месяцев»). Используется ОБОИМИ диалогами плановой позиции
// (useFeoPlannedItemAddDialog.ts и useFeoPlannedItemEditDialog.ts) — раньше
// каждый диалог заводил свою копию одного и того же запроса (Правило №6
// проекта: один показатель — один источник истины); здесь — общий.
//
// Дефект (владелец, 2026-09-14, скриншот): «дата окончания, я ещё не успеваю
// год ввести, а эта хуйня уже говорит "дата должна быть позже"... я только
// успеваю 20 ввести, а год-то 2026». Разбор:
//   1) старый watch() у обоих диалогов дёргал refresh на КАЖДОЕ изменение
//      monthly_start_date/monthly_end_date/monthly_amount без задержки —
//      запрос улетал на каждый символ, включая заведомо недописанную дату.
//   2) нативный <input type="date"> (Vuetify v-text-field type="date") отдаёт
//      value на КАЖДОЕ нажатие внутри сегмента года, дополняя нулями то, что
//      уже набрано: набрали "20" из "2026" — value уже "...-...-0020",
//      синтаксически валидная ISO-дата, семантически мусор. isCompleteIsoDate
//      ниже отсекает такие значения по правдоподобному году (>= 1000).
//   3) сервер на недописанную/некорректную пару дат отвечает HTTP 400 —
//      apiFetch по умолчанию кидает это глобальным диалогом ApiErrorDialog
//      поверх формы, хотя это ФОНОВЫЙ предпросмотр, а не действие человека
//      («Добавить»/«Сохранить»). suppressErrorDialog (см. api.ts) гасит
//      только это всплывающее окно — сама ошибка по-прежнему долетает до
//      catch ниже и на её месте остаётся спокойная строка под полем
//      («Проверьте даты…», см. PlannedItemAddDialog.vue/PlannedItemEditDialog.vue).
import { apiFetch } from '@/api'

export interface MonthlySchedulePreview {
  label: string
  total: number | null
}

/** Год из 4 цифр, но ещё не факт, что реальный — native date input подставляет
 * "0020" при вводе "20" из "2026". >= 1000 достаточно, чтобы отсечь именно
 * недописанный ввод (а не отвергать легитимные, но малоправдоподобные годы —
 * это не валидация даты по существу, только фильтр «человек ещё печатает»). */
export function isCompleteIsoDate(v: string | null | undefined): boolean {
  if (!v) return false
  const m = /^(\d{4})-\d{2}-\d{2}$/.exec(v)
  return !!m && Number(m[1]) >= 1000
}

export async function fetchMonthlySchedulePreview(
  startDate: string,
  endDate: string,
  monthlyAmount: number | string | null | undefined,
): Promise<MonthlySchedulePreview | null> {
  if (!isCompleteIsoDate(startDate) || !isCompleteIsoDate(endDate)) return null
  try {
    const qs = new URLSearchParams({ start_date: startDate, end_date: endDate })
    if (monthlyAmount != null && monthlyAmount !== ('' as unknown)) qs.set('monthly_amount', String(monthlyAmount))
    const res = await apiFetch<{ label: string; total: string | null }>(
      `/feo-planned-items/monthly-schedule-preview?${qs.toString()}`,
      { suppressErrorDialog: true },
    )
    return { label: res.label, total: res.total != null ? Number(res.total) : null }
  } catch {
    // Некорректный диапазон (конец раньше начала) или сбой сети — просто не
    // показываем расшифровку, поля остаются редактируемыми. Вызывающий уже
    // показывает спокойную строку-подсказку под полем на основании null.
    return null
  }
}
