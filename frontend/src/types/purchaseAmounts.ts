// ПРАВИЛО №6 (2026-09-05/06) — единый расчёт «суммы закупки».
// Mirrors backend PurchaseAmountsOut (backend/app/schemas/schemas.py) —
// см. докстринг backend/app/services/purchase_amounts.py для формулы.
//
// Один источник истины: фронт БОЛЬШЕ НЕ считает «сумму закупки» сам
// (никаких цепочек `contract_price ?? total_nmck ?? planned_total_price`
// на местах) — читает готовое значение amounts.effective, посчитанное
// бэкендом по стадии закупки (Purchase.status), с фолбэком до
// planned_total_price/Σ purchase_items.total_price.
//
// plan/contract/fact/paid — сырые колонки Purchase БЕЗ фолбэков, на случай,
// если экрану нужно показать именно исходное поле, а не итоговое effective.
//
// QA-находка (2026-09-06): поля Optional[Decimal] в PurchaseAmountsOut
// (backend/app/schemas/schemas.py:1091) уходят в JSON СТРОКОЙ ("10000.00"),
// не числом — таково поведение Pydantic v2 для Decimal в JSON-режиме.
// Наивное `amounts.effective ?? 0`, посаженное прямо в арифметику
// (`sum + amounts.effective`), даёт конкатенацию строк ("0" + "10000.00" =
// "010000.00"), а не сложение — источник NaN/«010000.00 ₽» в OrdersView/
// PlanView/DashboardView. Поэтому тип честно допускает string | number | null,
// а ЛЮБОЕ чтение amounts.plan/contract/fact/paid/effective ПЕРЕД арифметикой
// или числовым форматированием обязано идти через toAmount() ниже —
// не по одному разу на файл, единый хелпер.
export interface PurchaseAmounts {
  plan: string | number | null
  contract: string | number | null
  fact: string | number | null
  paid: string | number | null
  effective: string | number | null
  effective_source: string
}

/** Единая точка приведения amounts.* к числу — см. QA-заметку в докстринге
 * выше. null/undefined/'' → null (означает «бэкенд не нашёл значения»,
 * должно рисоваться как прочерк — НЕ как 0). Валидная строка/число → number.
 * Невалидная строка (не должна приходить с бэкенда, но на всякий случай) → null,
 * а не NaN, чтобы NaN не расползался дальше по суммам/графикам. */
export function toAmount(v: string | number | null | undefined): number | null {
  if (v === null || v === undefined || v === '') return null
  const n = typeof v === 'string' ? parseFloat(v) : v
  return Number.isFinite(n) ? n : null
}
