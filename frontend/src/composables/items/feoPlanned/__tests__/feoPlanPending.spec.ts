import { describe, it, expect } from 'vitest'
import { pendingForRow, consumedForRow, residualForRow } from '../feoPlanPending'

// Дефект-пример владельца (прод, 13.10.2026): план 352 400, серверные
// consumed=0/residual=352 400 (своя закупка уже исключена exclude_purchase_id),
// текущая сумма редактируемой строки — 317 400.
describe('feoPlanPending — выбрано/остаток строки с учётом текущей суммы формы', () => {
  const plannedRow = { kind: 'planned_item' as const, id: 42, consumed: 0, residual: 352_400 }

  it('позиция выбрана — текущая сумма учтена: выбрано 317 400, остаток 35 000', () => {
    const pending = { 42: 317_400 }
    expect(pendingForRow(plannedRow, pending)).toBe(317_400)
    expect(consumedForRow(plannedRow, pending)).toBe(317_400)
    expect(residualForRow(plannedRow, pending)).toBe(35_000)
  })

  it('позиция не выбрана — карта пустая: выбрано 0, остаток весь план', () => {
    expect(pendingForRow(plannedRow, null)).toBe(0)
    expect(consumedForRow(plannedRow, null)).toBe(0)
    expect(residualForRow(plannedRow, null)).toBe(352_400)
  })

  it('выключили переключатель — карта без этого id: тоже выбрано 0', () => {
    const pending = {}
    expect(consumedForRow(plannedRow, pending)).toBe(0)
    expect(residualForRow(plannedRow, pending)).toBe(352_400)
  })

  it('kind !== planned_item (категория/статья ФЭО с планом) — pendingFor всегда 0, даже если id совпадает', () => {
    const categoryRow = { kind: 'plan_position' as const, id: 42 }
    expect(pendingForRow(categoryRow, { 42: 317_400 })).toBe(0)
  })

  it('невыбранная позиция с чужим расходом не трогается этой картой', () => {
    const otherRow = { kind: 'planned_item' as const, id: 7, consumed: 100, residual: 200 }
    const pending = { 42: 317_400 }
    expect(consumedForRow(otherRow, pending)).toBe(100)
    expect(residualForRow(otherRow, pending)).toBe(200)
  })
})
