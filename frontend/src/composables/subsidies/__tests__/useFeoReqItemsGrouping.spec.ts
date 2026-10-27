// Регресс: useFeoReqItems.ts::reqItemRowsFor переведён на общий билдер
// buildCategoryGroupedRows (feoCategoryUtils.ts, тот же, что и
// useFeoPlannedItemGroups.ts, Правило №6) — раньше сам строил заголовки
// категория/вид. Эталон ниже — точная копия СТАРОЙ реализации (до правки),
// новая обёртка (newReqItemRowsFor) повторяет текущий код reqItemRowsFor.
// Тест сверяет точное совпадение результата (порядок строк, ключи, level,
// count/sumQty/sum/items) на нескольких наборах виртуальных групп и во всех
// трёх режимах группировки.
import { describe, it, expect } from 'vitest'
import { buildCategoryGroupedRows, normName } from '../feoCategoryUtils'
import type { FeoReqItem, FeoReqRow, FeoVirtualGroup } from '../types'

type GroupMode = 'none' | 'category' | 'category_type'

// ── Эталон: старая реализация reqItemRowsFor (до перевода на buildCategoryGroupedRows) ──
function referenceReqItemRowsFor(groupsList: FeoVirtualGroup[], mode: GroupMode): FeoReqRow[] {
  const groupRowOf = (g: FeoVirtualGroup): FeoReqRow =>
    ({ key: `g-${normName(g.name)}`, header: '', level: 0, count: g.items.length, sumQty: g.qty, sum: g.total, group: g, items: g.items })
  if (mode === 'none') {
    return [...groupsList].sort((a, b) => a.name.localeCompare(b.name, 'ru')).map(groupRowOf)
  }
  const sorted = [...groupsList].sort((a, b) =>
    a.category.localeCompare(b.category, 'ru')
    || a.product_type.localeCompare(b.product_type, 'ru')
    || a.name.localeCompare(b.name, 'ru'))
  const rows: FeoReqRow[] = []
  let curCat: string | null = null
  let curType: string | null = null
  const headerRow = (key: string, header: string, level: number, grp: FeoVirtualGroup[]): FeoReqRow => ({
    key, header, level,
    count: grp.reduce((s, x) => s + x.items.length, 0),
    sumQty: Math.round(grp.reduce((s, x) => s + x.qty, 0) * 10000) / 10000,
    sum: grp.reduce((s, x) => s + x.total, 0),
    group: null,
    items: grp.flatMap(x => x.items),
  })
  for (const g of sorted) {
    if (g.category !== curCat) {
      curCat = g.category
      curType = null
      rows.push(headerRow(`c-${curCat}`, curCat, 1, sorted.filter(x => x.category === curCat)))
    }
    if (mode === 'category_type' && g.product_type !== curType) {
      curType = g.product_type
      rows.push(headerRow(`c-${curCat}-t-${curType}`, curType, 2,
        sorted.filter(x => x.category === curCat && x.product_type === curType)))
    }
    rows.push(groupRowOf(g))
  }
  return rows
}

// ── Новая реализация: ровно то, что сейчас делает useFeoReqItems.ts::reqItemRowsFor ──
function newReqItemRowsFor(groupsList: FeoVirtualGroup[], mode: GroupMode): FeoReqRow[] {
  const sortedGroups = [...groupsList].sort((a, b) => a.name.localeCompare(b.name, 'ru'))
  const rows = buildCategoryGroupedRows<FeoVirtualGroup, FeoReqItem>(
    sortedGroups,
    mode,
    g => g.category,
    g => g.product_type,
    g => g.name,
    g => g.total,
    { getQty: g => g.qty, getItems: g => g.items, itemKeyPrefix: 'g' },
  )
  return rows.map((row): FeoReqRow => ({
    key: row.key, header: row.header, level: row.level, count: row.count,
    sumQty: row.sumQty ?? 0, sum: row.sum, group: row.item, items: row.items ?? [],
  }))
}

function reqItem(partial: Partial<FeoReqItem> & { id: number }): FeoReqItem {
  return {
    id: partial.id,
    purchase_id: partial.purchase_id ?? 1,
    purchase_number: null,
    registry_number: null,
    purchase_status: 'draft',
    wish_id: null,
    item_name: partial.item_name ?? 'товар',
    quantity: partial.quantity ?? 1,
    unit: partial.unit ?? 'шт',
    total_price: partial.total_price ?? 0,
    category: partial.category ?? '',
    product_type: partial.product_type ?? '',
    feo_planned_item_id: null,
    stopped_at: null,
    stopped_by_name: null,
  } as unknown as FeoReqItem
}

function group(partial: Partial<FeoVirtualGroup> & { name: string; items: FeoReqItem[] }): FeoVirtualGroup {
  return {
    name: partial.name,
    unit: partial.unit ?? 'шт',
    qty: partial.qty ?? partial.items.reduce((s, it) => s + Number(it.quantity || 0), 0),
    total: partial.total ?? partial.items.reduce((s, it) => s + Number(it.total_price || 0), 0),
    category: partial.category ?? '',
    product_type: partial.product_type ?? '',
    items: partial.items,
  }
}

function buildGroups(): FeoVirtualGroup[] {
  return [
    group({
      name: 'Перчатки х/б', category: 'Спецодежда', product_type: 'Перчатки',
      items: [reqItem({ id: 1, quantity: 10, total_price: 1000 }), reqItem({ id: 2, quantity: 5, total_price: 500 })],
    }),
    group({
      name: 'Перчатки кожа', category: 'Спецодежда', product_type: 'Перчатки',
      items: [reqItem({ id: 3, quantity: 2, total_price: 400 })],
    }),
    group({
      name: 'Каска', category: 'Спецодежда', product_type: 'Каски',
      items: [reqItem({ id: 4, quantity: 3, total_price: 900 })],
    }),
    group({
      name: 'Болт М8', category: 'Крепёж', product_type: 'Болты',
      items: [reqItem({ id: 5, quantity: 100, total_price: 200 })],
    }),
  ]
}

describe('useFeoReqItems::reqItemRowsFor — перевод на buildCategoryGroupedRows', () => {
  for (const mode of ['none', 'category', 'category_type'] as GroupMode[]) {
    it(`режим '${mode}' — точное совпадение со старой реализацией`, () => {
      const groups = buildGroups()
      const expected = referenceReqItemRowsFor(groups, mode)
      const actual = newReqItemRowsFor(groups, mode)
      expect(actual).toEqual(expected)
    })
  }

  it('sumQty округляется до 4 знаков в заголовке (как в эталоне)', () => {
    const groups = [
      group({ name: 'А', category: 'К', product_type: 'В', qty: 1.00001, items: [reqItem({ id: 1, quantity: 1.00001 })] }),
      group({ name: 'Б', category: 'К', product_type: 'В', qty: 2.00002, items: [reqItem({ id: 2, quantity: 2.00002 })] }),
    ]
    const expected = referenceReqItemRowsFor(groups, 'category')
    const actual = newReqItemRowsFor(groups, 'category')
    expect(actual).toEqual(expected)
    const header = actual.find(r => r.key === 'c-К')!
    expect(header.sumQty).toBe(Math.round((1.00001 + 2.00002) * 10000) / 10000)
  })

  it('пустой список — пустой результат в любом режиме', () => {
    expect(newReqItemRowsFor([], 'none')).toEqual([])
    expect(newReqItemRowsFor([], 'category')).toEqual([])
    expect(newReqItemRowsFor([], 'category_type')).toEqual([])
  })
})
