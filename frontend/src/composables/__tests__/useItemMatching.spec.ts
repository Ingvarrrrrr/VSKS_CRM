// Тесты applyCandidate/clearBinding (useItemMatching.ts) — баг владельца
// 26.10.2026: цена не синхронизировалась с товаром при смене выбора в той же
// строке (выбрал «Бензопила» → выбрал «Зубная паста» → цена осталась старая).
// Тестируем ТОЛЬКО applyCandidate/clearBinding, не весь composable.
import { describe, it, expect } from 'vitest'
import { useItemMatching, type MatchableRow, type MatchCandidate } from '@/composables/useItemMatching'

function makeCandidate(overrides: Partial<MatchCandidate> = {}): MatchCandidate {
  return {
    product_id: 1,
    name: 'Товар',
    price: null,
    score: 1,
    ...overrides,
  }
}

function makeRow(overrides: Partial<MatchableRow> = {}): MatchableRow {
  return {
    product_id: null,
    item_name: '',
    unit_price: null,
    total_price: null,
    quantity: 2,
    ...overrides,
  }
}

describe('useItemMatching.applyCandidate', () => {
  it('смена товара на другой — unit_price берётся от нового кандидата, total_price пересчитан', () => {
    const { applyCandidate } = useItemMatching()
    const row = makeRow({ product_id: 10, unit_price: 103826, quantity: 1, total_price: 103826 })
    const cand = makeCandidate({ product_id: 20, name: 'Зубная паста', contract_price: 150, price: 140 })
    applyCandidate(row, cand)
    expect(row.product_id).toBe(20)
    expect(row.unit_price).toBe(150)
    expect(row.total_price).toBe(150)
  })

  it('новый товар без цены при смене товара — unit_price становится null', () => {
    const { applyCandidate } = useItemMatching()
    const row = makeRow({ product_id: 10, unit_price: 103826, quantity: 1, total_price: 103826 })
    const cand = makeCandidate({ product_id: 20, name: 'Без цены', contract_price: null, price: null })
    applyCandidate(row, cand)
    expect(row.product_id).toBe(20)
    expect(row.unit_price).toBeNull()
    expect(row.total_price).toBeNull()
  })

  it('выбор того же product_id повторно — unit_price не меняется', () => {
    const { applyCandidate } = useItemMatching()
    const row = makeRow({ product_id: 10, unit_price: 777, quantity: 1, total_price: 777 })
    const cand = makeCandidate({ product_id: 10, name: 'Тот же товар', contract_price: 150, price: 140 })
    applyCandidate(row, cand)
    expect(row.unit_price).toBe(777)
    expect(row.total_price).toBe(777)
  })

  it('row.from_plan=true — unit_price не меняется при любой смене товара', () => {
    const { applyCandidate } = useItemMatching()
    const row = makeRow({ product_id: 10, unit_price: 500, quantity: 1, total_price: 500, from_plan: true } as any)
    const cand = makeCandidate({ product_id: 20, name: 'Другой товар', contract_price: 150, price: 140 })
    applyCandidate(row, cand)
    expect(row.product_id).toBe(20)
    expect(row.unit_price).toBe(500)
    expect(row.total_price).toBe(500)
  })

  it('первичный выбор (product_id и unit_price были null) — цена подставляется (старое поведение)', () => {
    const { applyCandidate } = useItemMatching()
    const row = makeRow({ product_id: null, unit_price: null, quantity: 3, total_price: null })
    const cand = makeCandidate({ product_id: 20, name: 'Первый товар', contract_price: 100, price: 90 })
    applyCandidate(row, cand)
    expect(row.product_id).toBe(20)
    expect(row.unit_price).toBe(100)
    expect(row.total_price).toBe(300)
  })
})

describe('useItemMatching.clearBinding', () => {
  it('сбрасывает товар и связанные служебные поля', () => {
    const { clearBinding } = useItemMatching()
    const row = makeRow({
      product_id: 20,
      item_name: 'Товар',
      _selectedProduct: { product_id: 20 },
      _photo_url: 'x.jpg',
      _description: 'desc',
      _price_meta: { price_source: 'catalog' },
    } as any)
    clearBinding(row)
    expect(row.product_id).toBeNull()
    expect(row.item_name).toBe('')
    expect((row as any)._selectedProduct).toBeNull()
    expect((row as any)._photo_url).toBeUndefined()
    expect((row as any)._description).toBeUndefined()
    expect((row as any)._price_meta).toBeNull()
  })
})
