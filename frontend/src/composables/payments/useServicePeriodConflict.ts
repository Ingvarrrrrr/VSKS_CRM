// Задача 04.10.2026 («Помесячные платежи — разные месяцы»): бэк при конфликте
// месяца оказания (app/services/payment_service_period.py, см. ServicePeriodConflict
// / ServicePeriodAttachConflict) отвечает 409 со СТРУКТУРИРОВАННЫМ detail —
// {code: 'service_period_conflict', purchase_id, message, occupied_period} —
// см. app/services/payment_service_period.py::service_period_conflict_detail
// (ПРАВИЛО №6: один хелпер формирования на бэке, один модуль распознавания на
// фронте — больше НИКАКИХ регулярок по тексту причины, это единственное место,
// где фронт отличает «конфликт месяца» от любой другой 409-ошибки).
//
// frontend/src/api.ts::apiFetch уже распаковывает структурированный detail сам:
// err.payload.code = detail.code, err.payload.details = detail (весь объект),
// err.detail = detail.message (строка, для обычного текста ошибки). Race-backstop
// без привязки к одной закупке (app/services/purchase_payments.py, IntegrityError
// на flush) приходит с тем же code, но purchase_id/occupied_period = null —
// вызывающий код сам решает, на какую закупку отнести выбор (обычно единственная
// помесячная в наборе).

export interface ApiErrorLike {
  status?: number
  detail?: string
  payload?: {
    code?: string
    details?: {
      code?: string
      purchase_id?: number | null
      message?: string
      occupied_period?: string | null
    } | string | null
  } | null
}

function detailObject(err: ApiErrorLike | null | undefined) {
  const d = err?.payload?.details
  return d && typeof d === 'object' ? d : null
}

/** 409-ответ, где причина — конфликт месяца оказания (а не «уже подтверждён» и т.п.). */
export function isServicePeriodConflict(err: ApiErrorLike | null | undefined): boolean {
  if (!err || err.status !== 409) return false
  if (err.payload?.code === 'service_period_conflict') return true
  return detailObject(err)?.code === 'service_period_conflict'
}

/** Номер закупки из структурированного detail — null, если бэк его не указал (race-backstop). */
export function extractConflictPurchaseId(err: ApiErrorLike | null | undefined): number | null {
  const pid = detailObject(err)?.purchase_id
  return typeof pid === 'number' ? pid : null
}

/** Человекочитаемый текст причины конфликта. */
export function extractConflictMessage(err: ApiErrorLike | null | undefined): string | null {
  return detailObject(err)?.message ?? err?.detail ?? null
}

/** Месяц (YYYY-MM-01), который уже занят другим платежом — null, если конфликт
 * другого вида (нет service_start_date / все месяцы периода заняты). */
export function extractOccupiedPeriod(err: ApiErrorLike | null | undefined): string | null {
  return detailObject(err)?.occupied_period ?? null
}
