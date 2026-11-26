import { describe, it, expect } from 'vitest'
import { getOrderTypeKey, purchaseTypeLabel } from '../ordersLabels'
import type { Purchase } from '../ordersTypes'

describe('ordersLabels order type classification', () => {
  it('classifies advance correctly', () => {
    const p: Purchase = { id: 1, purchase_method: 'advance' } as any
    expect(getOrderTypeKey(p)).toBe('advance')
    expect(purchaseTypeLabel(p)).toBe('Авансовый')
  })

  it('classifies framework correctly when purchase_method is single but contract type is framework_cumulative', () => {
    const p: Purchase = {
      id: 2,
      purchase_method: 'single',
      purchase_contract_type: 'framework_cumulative'
    } as any
    expect(getOrderTypeKey(p)).toBe('framework')
    expect(purchaseTypeLabel(p)).toBe('В рамках рамочного')
  })

  it('classifies framework correctly with framework_with_amount', () => {
    const p: Purchase = {
      id: 3,
      purchase_contract_type: 'framework_with_amount'
    } as any
    expect(getOrderTypeKey(p)).toBe('framework')
    expect(purchaseTypeLabel(p)).toBe('В рамках рамочного')
  })

  it('classifies invoice correctly', () => {
    const p: Purchase = {
      id: 4,
      purchase_basis: 'invoice'
    } as any
    expect(getOrderTypeKey(p)).toBe('invoice')
    expect(purchaseTypeLabel(p)).toBe('По счёту')
  })

  it('classifies competitive correctly', () => {
    const p: Purchase = {
      id: 5,
      purchase_method: 'competitive'
    } as any
    expect(getOrderTypeKey(p)).toBe('competitive')
    expect(purchaseTypeLabel(p)).toBe('Конкурентный')
  })

  it('classifies one_time correctly', () => {
    const p: Purchase = {
      id: 6,
      purchase_method: 'single',
      purchase_contract_type: 'single'
    } as any
    expect(getOrderTypeKey(p)).toBe('one_time')
    expect(purchaseTypeLabel(p)).toBe('Разовый')
  })
})
