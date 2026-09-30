// feoPlanOccupancy — единая проверка «эту плановую позицию сейчас безопасно
// подставить автоматически» (владелец, 30.09.2026: в окне «Привязать к плану»
// строка «Доставка» из чека авансового была отмечена «точное совпадение» и
// привязана к плановой позиции «Доставка», которую уже израсходовала ДРУГАЯ
// закупка — остаток стал −113,60 ₽. «Доставка из чека должна быть создана
// отдельно, она не должна объединяться ни с чем»).
//
// ПРАВИЛО №6 — один расчёт «занято/остатка не хватает», используется и в
// bulk-match (useFeoPlannedBulkMatch.ts::openBulkMatchDialog — решение,
// отмечать ли галочку по умолчанию) и в построчных подсказках
// (useItemsPlanSuggest.ts — та же логика для одиночной подсказки под строкой).
// Числа (residual/residual_quantity/linked_purchases/linked_wishes) НЕ
// считаются здесь заново — они уже готовы с сервера (GET
// /feo-categories/plan-positions → useFeoPlannedResiduals.ts, exclude_purchase_id/
// exclude_wish_id там уже исключают ТЕКУЩУЮ закупку/заявку из linked_*, второй раз
// вычитать «своё» не нужно). Здесь только правило сравнения.
import type { FeoPlanPosition } from '@/composables/useFeoPlannedResiduals'

export interface PlanOccupancyCheck {
  /** Сумма позиции закупки/заявки, которую пытаются привязать (total_price). */
  amount: number | null
  /** Количество позиции — сравнивается с residual_quantity, только когда у
   *  самой плановой позиции задано количество (planned_quantity != null);
   *  когда плановая позиция считается только суммой — по количеству не судим. */
  quantity?: number | null
}

export interface PlanOccupancyResult {
  /** true — НЕ отмечать галочку/не предлагать как свободную автоматически:
   *  остатка не хватает, или позиция уже занята другой закупкой/заявкой.
   *  Осознанный РУЧНОЙ выбор человека (галочка в bulk-match, кнопка
   *  «Привязать» в построчной подсказке) этим НЕ блокируется. */
  occupied: boolean
  insufficientAmount: boolean
  insufficientQuantity: boolean
  /** linked_purchases/linked_wishes НЕпустые — другая закупка/заявка уже
   *  ссылается на эту плановую позицию. Позиции из чека авансового
   *  (item.receipt_id задан) по сути уникальные покупки («Доставка» и т.п.) —
   *  для них это САМО ПО СЕБЕ достаточная причина никогда не подставлять
   *  автоматически, даже если арифметически остаток пока формально хватает. */
  linkedByOther: boolean
}

export function checkPlanOccupancy(
  row: FeoPlanPosition | null | undefined,
  check: PlanOccupancyCheck,
): PlanOccupancyResult {
  if (!row) {
    // Кандидат не резолвится в уже загруженных плановых позициях (не должно
    // происходить в норме — /match и /plan-positions читают одну и ту же
    // субсидию) — остаток неизвестен, безопаснее считать занятым, чем
    // подставить вслепую.
    return { occupied: true, insufficientAmount: false, insufficientQuantity: false, linkedByOther: false }
  }
  const linkedByOther = !!(row.linked_purchases?.length || row.linked_wishes?.length)
  const insufficientAmount = check.amount != null && (row.residual ?? 0) < check.amount
  const insufficientQuantity = !!(
    row.planned_quantity != null
    && check.quantity != null
    && (row.residual_quantity ?? 0) < check.quantity
  )
  return {
    occupied: linkedByOther || insufficientAmount || insufficientQuantity,
    insufficientAmount,
    insufficientQuantity,
    linkedByOther,
  }
}
