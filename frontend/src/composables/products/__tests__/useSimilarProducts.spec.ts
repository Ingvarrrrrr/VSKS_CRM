// defaultMergeIds — дефолт галочек «Объединить в неё» в SimilarProductsDialog.vue
// (владелец, 27.10.2026): «уверенно» — включена у карточек другого магазина;
// «проверить» — выключена; тот же магазин, что у winner — никогда не предлагается.
import { describe, expect, it } from 'vitest'
import { defaultMergeIds, highlightDiffTokens, type SimilarCard } from '../useSimilarProducts'

function card(partial: Partial<SimilarCard> & { id: number }): SimilarCard {
  return {
    id: partial.id,
    name: partial.name ?? `Товар ${partial.id}`,
    manufacturer: partial.manufacturer ?? null,
    price: partial.price ?? null,
    contractor_id: partial.contractor_id ?? null,
    source_ref: partial.source_ref ?? null,
    history_count: partial.history_count ?? 0,
    has_photo: partial.has_photo ?? false,
    has_description: partial.has_description ?? false,
    diff_tokens: partial.diff_tokens ?? [],
    same_store_as_winner: partial.same_store_as_winner ?? false,
  }
}

describe('defaultMergeIds', () => {
  it('confidence="уверенно" — включена у карточек другого магазина', () => {
    const cards = [
      card({ id: 1 }),                                   // winner
      card({ id: 2, same_store_as_winner: false }),
      card({ id: 3, same_store_as_winner: false }),
    ]
    expect(defaultMergeIds(cards, 1, 'уверенно')).toEqual(new Set([2, 3]))
  })

  it('confidence="проверить" — выключена у всех по умолчанию', () => {
    const cards = [
      card({ id: 1 }),
      card({ id: 2, same_store_as_winner: false }),
      card({ id: 3, same_store_as_winner: false }),
    ]
    expect(defaultMergeIds(cards, 1, 'проверить')).toEqual(new Set())
  })

  it('same_store_as_winner — не предлагается даже при "уверенно"', () => {
    const cards = [
      card({ id: 1 }),
      card({ id: 2, same_store_as_winner: true }),
      card({ id: 3, same_store_as_winner: false }),
    ]
    expect(defaultMergeIds(cards, 1, 'уверенно')).toEqual(new Set([3]))
  })

  it('сам winner никогда не попадает в список на объединение', () => {
    const cards = [card({ id: 1 }), card({ id: 2 })]
    expect(defaultMergeIds(cards, 1, 'уверенно')).toEqual(new Set([2]))
  })
})

describe('highlightDiffTokens', () => {
  it('без diff_tokens — всё название не выделено', () => {
    const segs = highlightDiffTokens('Огнетушитель ОП-2', [])
    expect(segs.every(s => !s.bold)).toBe(true)
  })

  it('слово из diff_tokens помечается bold', () => {
    const segs = highlightDiffTokens('Огнетушитель китай', ['китай'])
    const boldTexts = segs.filter(s => s.bold).map(s => s.text)
    expect(boldTexts).toEqual(['китай'])
  })
})
