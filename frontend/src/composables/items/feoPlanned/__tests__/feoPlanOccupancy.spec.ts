// Жалоба владельца (30.09.2026): в окне «Привязать к плану» строка «Доставка»
// из чека авансового была отмечена «точное совпадение» и привязана к плановой
// позиции «Доставка», уже израсходованной ДРУГОЙ закупкой (остаток −113,60 ₽).
// checkPlanOccupancy — единственное место (ПРАВИЛО №6), где решается, можно ли
// подставить кандидата автоматически; тест закрепляет ровно эти числа.
import { describe, expect, it } from 'vitest'
import { checkPlanOccupancy } from '../feoPlanOccupancy'
import type { FeoPlanPosition } from '@/composables/useFeoPlannedResiduals'

function planRow(overrides: Partial<FeoPlanPosition> = {}): FeoPlanPosition {
  return {
    id: 1,
    name: 'Доставка',
    path: 'Транспорт › Доставка',
    category_id: 10,
    kind: 'planned_item',
    planned_quantity: null,
    unit: '',
    planned_amount: 1000,
    unit_price: null,
    consumed: 1113.6,
    consumed_quantity: 0,
    residual: -113.6,
    residual_quantity: 0,
    key: 'planned_item:1',
    ...overrides,
  }
}

describe('checkPlanOccupancy', () => {
  it('владелец, 30.09.2026: остаток −113,60 ₽ и линк на другую закупку — occupied=true, авто-галочка запрещена', () => {
    const row = planRow({
      linked_purchases: [{ id: 5, registry_number: 'РЕЕ-2026-00771', amount: 1113.6, status_label: 'В работе' }],
    })
    const result = checkPlanOccupancy(row, { amount: 500 })
    expect(result.occupied).toBe(true)
    expect(result.linkedByOther).toBe(true)
    expect(result.insufficientAmount).toBe(true)
  })

  it('кандидат свободен (нет линков, остатка достаточно) — occupied=false, авто-галочка разрешена', () => {
    const row = planRow({ residual: 5000, linked_purchases: [], linked_wishes: [] })
    const result = checkPlanOccupancy(row, { amount: 500 })
    expect(result.occupied).toBe(false)
  })

  it('позиция из чека (receipt_id) — любой линк на другую закупку блокирует авто, даже если денег формально хватает', () => {
    // «Доставка из чека должна быть создана отдельно, она не должна
    // объединяться ни с чем» — линк уже есть, поэтому occupied=true независимо
    // от того, что остаток (residual=5000) арифметически покрыл бы сумму.
    const row = planRow({
      residual: 5000,
      linked_purchases: [{ id: 9, registry_number: 'РЕЕ-2026-00500', amount: 100, status_label: 'В работе' }],
    })
    const result = checkPlanOccupancy(row, { amount: 500 })
    expect(result.occupied).toBe(true)
    expect(result.linkedByOther).toBe(true)
    expect(result.insufficientAmount).toBe(false)
  })

  it('остатка по количеству не хватает (план считается количеством) — occupied=true', () => {
    const row = planRow({
      planned_quantity: 10,
      residual: 100000, // денег с избытком
      residual_quantity: 2,
      linked_purchases: [],
    })
    const result = checkPlanOccupancy(row, { amount: 100, quantity: 5 })
    expect(result.occupied).toBe(true)
    expect(result.insufficientQuantity).toBe(true)
  })

  it('количество не проверяется, если у плановой позиции количество не задано', () => {
    const row = planRow({ planned_quantity: null, residual: 5000, residual_quantity: 0, linked_purchases: [] })
    const result = checkPlanOccupancy(row, { amount: 500, quantity: 100 })
    expect(result.occupied).toBe(false)
    expect(result.insufficientQuantity).toBe(false)
  })

  it('кандидат не резолвится (row отсутствует) — occupied=true по умолчанию (безопаснее не подставлять вслепую)', () => {
    const result = checkPlanOccupancy(null, { amount: 500 })
    expect(result.occupied).toBe(true)
  })
})
