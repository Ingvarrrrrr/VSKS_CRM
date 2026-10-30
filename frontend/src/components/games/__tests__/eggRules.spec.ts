import { describe, it, expect } from 'vitest'
import { isLastStep, resolveEggArrival } from '../eggRules'

describe('isLastStep', () => {
  it('is true exactly one step before totalSteps', () => {
    expect(isLastStep(8, 9)).toBe(true)
  })

  it('is false for earlier steps', () => {
    expect(isLastStep(0, 9)).toBe(false)
    expect(isLastStep(7, 9)).toBe(false)
  })

  it('is false once the egg has arrived', () => {
    expect(isLastStep(9, 9)).toBe(false)
  })
})

describe('resolveEggArrival', () => {
  it('catches when the basket is aligned at the exact moment of arrival', () => {
    expect(resolveEggArrival(true, false)).toBe('caught')
  })

  it('catches when the basket was aligned during the grace window even if it moved away by arrival', () => {
    // владелец: корзина была в нужном жёлобе, но игрок увёл её до резолва —
    // должно ловиться, а не считаться промахом
    expect(resolveEggArrival(false, true)).toBe('caught')
  })

  it('catches when aligned both at arrival and during the grace window', () => {
    expect(resolveEggArrival(true, true)).toBe('caught')
  })

  it('breaks only when never aligned, neither during the grace window nor at arrival', () => {
    expect(resolveEggArrival(false, false)).toBe('broken')
  })
})
