// Группировка плановых позиций листа ФЭО по категории/виду каталога (задача
// владельца, 27.10.2026) — см. докстринг useFeoPlannedItemGroups.ts. Чистая
// функция, без Vue/ctx — проверяем: режим 'none' оставляет исходный порядок и
// index совпадает с позицией в исходном массиве (нужно реордеру), 'category'
// вставляет заголовки с фолбэком «Без категории», 'category_type' добавляет
// подзаголовки вида, count/sum заголовка верно агрегируют группу.
import { describe, it, expect } from 'vitest'
import { buildPlannedGroupEntries } from '../useFeoPlannedItemGroups'
import type { FeoPlannedItem } from '../types'

function item(partial: Partial<FeoPlannedItem> & { id: number; name: string }): FeoPlannedItem {
  return {
    id: partial.id,
    feo_category_id: 1,
    name: partial.name,
    quantity: null,
    unit: null,
    amount: partial.amount ?? 0,
    notes: null,
    is_active: true,
    catalog_category: partial.catalog_category,
    catalog_product_type: partial.catalog_product_type,
  } as FeoPlannedItem
}

describe('buildPlannedGroupEntries', () => {
  it('mode none — исходный порядок без заголовков, index = позиция в массиве', () => {
    const items = [
      item({ id: 1, name: 'Б', amount: 10 }),
      item({ id: 2, name: 'А', amount: 20 }),
    ]
    const rows = buildPlannedGroupEntries(items, 'none')
    expect(rows).toHaveLength(2)
    expect(rows.every(r => r.kind === 'item')).toBe(true)
    expect((rows[0] as any).item.id).toBe(1)
    expect((rows[0] as any).index).toBe(0)
    expect((rows[1] as any).item.id).toBe(2)
    expect((rows[1] as any).index).toBe(1)
  })

  it('mode category — заголовок перед каждой категорией, «Без категории» для null', () => {
    const items = [
      item({ id: 1, name: 'Перчатки', amount: 100, catalog_category: 'Спецодежда' }),
      item({ id: 2, name: 'Каска', amount: 50, catalog_category: 'СИЗ' }),
      item({ id: 3, name: 'Без товара', amount: 30, catalog_category: null }),
    ]
    const rows = buildPlannedGroupEntries(items, 'category')
    const headers = rows.filter(r => r.kind === 'header') as any[]
    expect(headers.map(h => h.label).sort()).toEqual(['Без категории', 'СИЗ', 'Спецодежда'].sort())

    const noCat = headers.find(h => h.label === 'Без категории')!
    expect(noCat.count).toBe(1)
    expect(noCat.sum).toBe(30)

    // Заголовок всегда идёт непосредственно перед своей позицией.
    const sizIdx = rows.findIndex(r => r.kind === 'header' && (r as any).label === 'СИЗ')
    expect(rows[sizIdx + 1]).toMatchObject({ kind: 'item' })
    expect((rows[sizIdx + 1] as any).item.id).toBe(2)
  })

  it('mode category_type — подзаголовок вида внутри категории, «Без вида» для null', () => {
    const items = [
      item({ id: 1, name: 'Перчатки х/б', amount: 100, catalog_category: 'Спецодежда', catalog_product_type: 'Перчатки' }),
      item({ id: 2, name: 'Перчатки кожа', amount: 40, catalog_category: 'Спецодежда', catalog_product_type: 'Перчатки' }),
      item({ id: 3, name: 'Куртка', amount: 200, catalog_category: 'Спецодежда', catalog_product_type: null }),
    ]
    const rows = buildPlannedGroupEntries(items, 'category_type')
    const headers = rows.filter(r => r.kind === 'header') as any[]
    // Один заголовок категории (level 1) + два заголовка вида (level 2).
    expect(headers.filter(h => h.level === 1)).toHaveLength(1)
    expect(headers.filter(h => h.level === 2).map(h => h.label).sort()).toEqual(['Без вида', 'Перчатки'])

    const perchatkiHeader = headers.find(h => h.level === 2 && h.label === 'Перчатки')!
    expect(perchatkiHeader.count).toBe(2)
    expect(perchatkiHeader.sum).toBe(140)
  })

  it('пустой список — пустой результат без заголовков', () => {
    expect(buildPlannedGroupEntries([], 'category')).toEqual([])
    expect(buildPlannedGroupEntries([], 'none')).toEqual([])
  })

  it('index сохраняется относительно ИСХОДНОГО (несгруппированного) массива даже при сортировке', () => {
    const items = [
      item({ id: 10, name: 'Я последний по алфавиту', amount: 1, catalog_category: 'Б-категория' }),
      item({ id: 20, name: 'Я первый по алфавиту', amount: 2, catalog_category: 'А-категория' }),
    ]
    const rows = buildPlannedGroupEntries(items, 'category')
    const entries = rows.filter(r => r.kind === 'item') as any[]
    // 'А-категория' отрисуется раньше 'Б-категория' (сортировка по категории),
    // но index у её позиции (id=20) — ЕЁ исходная позиция в items (1), не 0.
    const forId20 = entries.find(e => e.item.id === 20)!
    const forId10 = entries.find(e => e.item.id === 10)!
    expect(forId20.index).toBe(1)
    expect(forId10.index).toBe(0)
  })
})
