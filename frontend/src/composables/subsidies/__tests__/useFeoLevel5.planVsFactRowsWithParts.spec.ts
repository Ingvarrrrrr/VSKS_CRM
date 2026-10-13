// Владелец, чек-лист 13.10.2026: развёртка «План vs факт» у объединённой
// позиции (parts) должна показать по строке на КАЖДУЮ часть, в порядке
// частей — часть с закупкой как обычную фактическую строку, часть без
// закупки как «запланировано». Контрольный пример — прод «ДНР 3», «Gaz
// A22R35 Х920АЕ 180» (352 400 = 317 400 договор/оплачено + 20 000 + 10 000 +
// 5 000 запланировано). buildPlanVsFactRowsWithParts — чистая функция (без
// Vue/ctx), тест закрепляет группировку без монтирования компонента.
import { describe, expect, it } from 'vitest'
import { buildPlanVsFactRowsWithParts } from '../useFeoLevel5'
import type { FeoActualItem } from '../types'

type Part = { key: string; row: number | null; qty: number | null; unit: string | null; unit_price: number | null; amount: number | null; purchases: any[] }

function part(overrides: Partial<Part>): Part {
  return { key: '0', row: null, qty: null, unit: null, unit_price: null, amount: null, purchases: [], ...overrides }
}

function actual(overrides: Partial<FeoActualItem>): FeoActualItem {
  return {
    purchase_item_id: 1,
    item_name: 'Gaz A22R35 Х920АЕ 180',
    quantity: 1,
    unit: null,
    unit_price: null,
    total_price: null,
    feo_planned_item_id: 25808,
    purchase_id: 1,
    purchase_number: null,
    registry_number: null,
    purchase_status: 'delivered',
    contract_number: null,
    contractor_name: null,
    feo_plan_part_key: null,
    ...overrides,
  }
}

describe('buildPlanVsFactRowsWithParts', () => {
  it('позиция без parts — все actuals как kind=actual, в исходном порядке', () => {
    const actuals = [actual({ purchase_item_id: 1 }), actual({ purchase_item_id: 2 })]
    const rows = buildPlanVsFactRowsWithParts([], actuals)
    expect(rows).toEqual([
      { kind: 'actual', actual: actuals[0] },
      { kind: 'actual', actual: actuals[1] },
    ])
  })

  it('прод «ДНР 3», Gaz 352 400: часть 20 (закупка 317 400) — actual; 27/28/31 — planned_only, в порядке parts', () => {
    const parts = [
      part({ key: '20', row: 20, amount: 317400 }),
      part({ key: '27', row: 27, amount: 20000 }),
      part({ key: '28', row: 28, amount: 10000 }),
      part({ key: '31', row: 31, amount: 5000 }),
    ]
    const purchaseForPart20 = actual({
      purchase_item_id: 100, purchase_id: 3465, registry_number: 'РЕЕ-2026-03465',
      purchase_status: 'delivered', feo_plan_part_key: '20', total_price: 317400,
    })
    const rows = buildPlanVsFactRowsWithParts(parts, [purchaseForPart20])

    expect(rows).toHaveLength(4)
    expect(rows[0]).toEqual({ kind: 'actual', actual: purchaseForPart20 })
    expect(rows[1]).toEqual({ kind: 'planned_only', part: parts[1] })
    expect(rows[2]).toEqual({ kind: 'planned_only', part: parts[2] })
    expect(rows[3]).toEqual({ kind: 'planned_only', part: parts[3] })
  })

  it('часть без закупки сохраняет порядок parts, даже когда закупленная часть — не первая', () => {
    const parts = [part({ key: '151', row: 151, amount: 407184.1 }), part({ key: '152', row: 152, amount: 292815.9 })]
    const purchaseForPart151 = actual({ purchase_item_id: 200, feo_plan_part_key: '151' })
    const rows = buildPlanVsFactRowsWithParts(parts, [purchaseForPart151])
    expect(rows).toEqual([
      { kind: 'actual', actual: purchaseForPart151 },
      { kind: 'planned_only', part: parts[1] },
    ])
  })

  it('закупки без feo_plan_part_key идут ПОСЛЕ всех строк частей', () => {
    const parts = [part({ key: '20', row: 20, amount: 317400 })]
    const partPurchase = actual({ purchase_item_id: 1, feo_plan_part_key: '20' })
    const looseePurchase = actual({ purchase_item_id: 2, feo_plan_part_key: null })
    const rows = buildPlanVsFactRowsWithParts(parts, [looseePurchase, partPurchase])
    expect(rows).toEqual([
      { kind: 'actual', actual: partPurchase },
      { kind: 'actual', actual: looseePurchase },
    ])
  })

  it('несколько закупок на ОДНУ часть — все выводятся как actual-строки этой части', () => {
    const parts = [part({ key: '20', row: 20, amount: 317400 })]
    const a1 = actual({ purchase_item_id: 1, feo_plan_part_key: '20' })
    const a2 = actual({ purchase_item_id: 2, feo_plan_part_key: '20' })
    const rows = buildPlanVsFactRowsWithParts(parts, [a1, a2])
    expect(rows).toEqual([
      { kind: 'actual', actual: a1 },
      { kind: 'actual', actual: a2 },
    ])
  })
})
