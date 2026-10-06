// Жалоба владельца 06.10.2026: «не могу посмотреть что это за превышение» —
// excessTargetIds() находит самые глубокие статьи-«виновники» активного вида
// превышения (узлы дерева хранят АГРЕГАТ поддерева, см. докстринг функции и
// backend/app/services/feo_plan_tree.py). Тест — чистая логика, без Vue/ctx.
import { describe, expect, it } from 'vitest'
import { compositionTargetIds, excessDiffLine, excessTargetIds, excessTargetsTotal } from '../useExcessDrilldown'
import { formatCurrency } from '../format'
import type { FeoCategory, PlanTreeEntry } from '../types'

type Cat = Pick<FeoCategory, 'id' | 'parent_id'>

function cat(id: number, parent_id: number | null): Cat {
  return { id, parent_id }
}

function tree(entries: Record<number, Partial<PlanTreeEntry>>): Record<number, PlanTreeEntry> {
  return entries as Record<number, PlanTreeEntry>
}

describe('excessTargetIds', () => {
  it('родитель и его ребёнок оба "превышают" (агрегат) — целью только ребёнок', () => {
    const categories: Cat[] = [cat(1, null), cat(2, 1)]
    const planTreeByCat = tree({
      1: { excess_plan_over_feo_services: 100 },
      2: { excess_plan_over_feo_services: 100 },
    })
    const ids = excessTargetIds(categories, planTreeByCat, 'plan_over_feo_services')
    expect(ids).toEqual([2])
  })

  it('два листа в разных ветках — оба попадают, в порядке сверху вниз', () => {
    const categories: Cat[] = [
      cat(1, null), cat(2, 1), cat(3, 1), // ветка A: 1 -> {2, 3}
      cat(10, null), cat(11, 10),          // ветка B: 10 -> 11
    ]
    const planTreeByCat = tree({
      1: { excess_fact_over_plan_goods: 50 },   // агрегат родителя ветки A
      3: { excess_fact_over_plan_goods: 50 },   // реальный виновник — лист 3 (у 2 превышения нет)
      10: { excess_fact_over_plan_goods: 20 },
      11: { excess_fact_over_plan_goods: 20 },
    })
    const ids = excessTargetIds(categories, planTreeByCat, 'fact_over_plan_goods')
    expect(ids).toEqual([3, 11])
  })

  it('поле ≤ 0.005 — не цель (шум округления)', () => {
    const categories: Cat[] = [cat(1, null)]
    const planTreeByCat = tree({ 1: { excess_plan_over_feo_goods: 0.004 } })
    expect(excessTargetIds(categories, planTreeByCat, 'plan_over_feo_goods')).toEqual([])
  })

  it('нет превышения вовсе — пустой список', () => {
    const categories: Cat[] = [cat(1, null), cat(2, 1)]
    const planTreeByCat = tree({ 1: {}, 2: {} })
    expect(excessTargetIds(categories, planTreeByCat, 'plan_over_feo_services')).toEqual([])
  })

  it('несколько независимых листьев-виновников под одним родителем — все три, порядок сохранён', () => {
    const categories: Cat[] = [cat(1, null), cat(2, 1), cat(3, 1), cat(4, 1)]
    const planTreeByCat = tree({
      1: { excess_plan_over_feo_goods: 300 },
      2: { excess_plan_over_feo_goods: 100 },
      3: { excess_plan_over_feo_goods: 0 },
      4: { excess_plan_over_feo_goods: 200 },
    })
    expect(excessTargetIds(categories, planTreeByCat, 'plan_over_feo_goods')).toEqual([2, 4])
  })
})

describe('excessTargetsTotal', () => {
  it('суммирует превышение найденных целей по тому же полю', () => {
    const planTreeByCat = tree({
      2: { excess_fact_over_plan_services: 111.11 },
      4: { excess_fact_over_plan_services: 222.22 },
    })
    expect(excessTargetsTotal([2, 4], planTreeByCat, 'fact_over_plan_services')).toBeCloseTo(333.33, 2)
  })
})

// Дефект 1 приёмки 06.10.2026 (субсидия «ФАДМ 2026_2», id 7320): узловой
// excess_plan_over_feo_services = 0 ВЕЗДЕ, когда ФЭО по услугам целиком лежит
// без разбивки на одной категории («Не определена», 15098), а план по
// услугам разложен по остальным направлениям — ровно случай владельца.
describe('compositionTargetIds (резервный режим, когда excessTargetIds пуст)', () => {
  it('4 корня, ФЭО по услугам сосредоточено на одном — все 4 цели, в порядке дерева', () => {
    const categories: Cat[] = [cat(15094, null), cat(15095, null), cat(15097, null), cat(15098, null)]
    const planTreeByCat = tree({
      15094: { plan_services: 8_048_163.75, feo_services: 0 },
      15095: { plan_services: 3_100_412.49, feo_services: 0 },
      15097: { plan_services: 1_290_582.36, feo_services: 0 },
      15098: { plan_services: 92_338.60, feo_services: 11_500_100.00 },
    })
    // Сам excessTargetIds пуст (узловой контроль не видит превышения нигде) —
    // именно поэтому понадобился composition-режим.
    expect(excessTargetIds(categories, planTreeByCat, 'plan_over_feo_services')).toEqual([])
    const ids = compositionTargetIds(categories, planTreeByCat, 'plan_over_feo_services')
    expect(ids).toEqual([15094, 15095, 15097, 15098])
  })

  it('корень без плана и без ФЭО по этому виду — не попадает в цели', () => {
    const categories: Cat[] = [cat(1, null), cat(2, null)]
    const planTreeByCat = tree({
      1: { plan_goods: 1000, feo_goods: 0 },
      2: { plan_goods: 0, feo_goods: 0 },
    })
    expect(compositionTargetIds(categories, planTreeByCat, 'plan_over_feo_goods')).toEqual([1])
  })
})

// Дефект 3 приёмки: статьи-виновники 15095 (967 160,00) и 15098 (2 302 932,00)
// по fact_over_plan_services суммируются в 3 270 092,00, а в чипе субсидии —
// 14 932,00 (в остальных статьях закупки ниже плана, гасят часть разницы).
describe('excessDiffLine', () => {
  it('объясняет разницу «сумма статей − сумма чипа» словами, без пересчёта контроля', () => {
    const planTreeByCat = tree({
      15095: { excess_fact_over_plan_services: 967_160.00 },
      15098: { excess_fact_over_plan_services: 2_302_932.00 },
    })
    const line = excessDiffLine([15095, 15098], planTreeByCat, 'fact_over_plan_services', 14_932.00)
    expect(line).not.toBeNull()
    expect(line).toContain(formatCurrency(3_270_092.00))
    expect(line).toContain('ниже')
    expect(line).toContain(formatCurrency(3_255_160.00))
    expect(line).toContain(formatCurrency(14_932.00))
  })

  it('суммы совпадают — строки нет', () => {
    const planTreeByCat = tree({ 1: { excess_fact_over_plan_goods: 100 } })
    expect(excessDiffLine([1], planTreeByCat, 'fact_over_plan_goods', 100)).toBeNull()
  })
})
