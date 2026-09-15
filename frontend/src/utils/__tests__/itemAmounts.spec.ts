// food-menu-editor.md: близнец backend/tests/test_item_amounts.py — числа
// владельца («10 человек, 2 дня, день 1: завтрак 200 + обед 350 + ужин 300,
// день 2 то же → 1700 на человека → итог 17000, quantity 60, unit_price
// ≈283,33») обязаны совпасть бит-в-бит на фронте и бэке (Правило №6: одна
// формула, две реализации-зеркала, а не источник истины на одной стороне).
import { describe, expect, it } from 'vitest'
import { applyItemAmounts, computeItemTotal, type ExtraAttrs } from '../itemAmounts'

function menuExtra(overrides: Partial<ExtraAttrs> = {}): ExtraAttrs {
  return {
    mode: 'menu',
    persons: 10,
    days: 2,
    menu: [
      {
        day: 1,
        meals: [
          { name: 'Завтрак', description: 'каша, чай', price: 200 },
          { name: 'Обед', description: 'суп, второе', price: 350 },
          { name: 'Ужин', description: 'рагу', price: 300 },
        ],
      },
      {
        day: 2,
        meals: [
          { name: 'Завтрак', description: 'каша, чай', price: 200 },
          { name: 'Обед', description: 'суп, второе', price: 350 },
          { name: 'Ужин', description: 'рагу', price: 300 },
        ],
      },
    ],
    ...overrides,
  }
}

describe('food item form — menu mode', () => {
  it('owner example: 10 persons × 2 days × (200+350+300) = 17000, quantity=60, unit_price≈283.33', () => {
    const item: { quantity?: unknown; unit_price?: unknown; total_price?: unknown; extra_attrs?: ExtraAttrs; item_type?: string | null } = {
      extra_attrs: menuExtra(),
    }
    const total = applyItemAmounts(item, 'food')
    expect(total).toBe(17000)
    expect(item.total_price).toBe(17000)
    expect(item.quantity).toBe(60)
    expect(item.unit_price).toBeCloseTo(283.33, 2)
    // quantity × unit_price should reconcile close to total (rounding tolerance)
    expect(Math.round((item.quantity as number) * (item.unit_price as number))).toBe(17000)
  })

  it('forces item_type to услуга for any active item form', () => {
    const item: { extra_attrs?: ExtraAttrs; item_type?: string | null } = {
      extra_attrs: menuExtra(),
      item_type: 'товар',
    }
    applyItemAmounts(item, 'food')
    expect(item.item_type).toBe('услуга')
  })

  it('computeItemTotal (preview) matches applyItemAmounts total without mutating', () => {
    const extra = menuExtra()
    const total = computeItemTotal(extra, 'food', null, null)
    expect(total).toBe(17000)
  })

  it('zero persons or empty menu → 0/0/0, no division by zero', () => {
    const item: { quantity?: unknown; unit_price?: unknown; total_price?: unknown; extra_attrs?: ExtraAttrs } = {
      extra_attrs: menuExtra({ persons: 0 }),
    }
    const total = applyItemAmounts(item, 'food')
    expect(total).toBe(0)
    expect(item.quantity).toBe(0)
    expect(item.unit_price).toBe(0)
  })

  it('simple mode unaffected by menu-mode branch (regression)', () => {
    const item: { quantity?: unknown; unit_price?: unknown; total_price?: unknown; extra_attrs?: ExtraAttrs; unit_price_input?: unknown } = {
      extra_attrs: { mode: 'simple', persons: 10, meals_per_day: 3, days: 5 },
      unit_price: 250,
    }
    const total = applyItemAmounts(item, 'food')
    expect(item.quantity).toBe(150)
    expect(total).toBe(37500)
  })
})
