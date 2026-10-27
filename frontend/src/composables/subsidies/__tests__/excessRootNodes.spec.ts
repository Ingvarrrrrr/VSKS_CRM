// excessRootNodes.spec.ts — покрытие excessRootNodes.ts (задача владельца
// 27.10.2026): узел превышения считается в сумму ТОЛЬКО если ни у одного из
// его предков нет СВОЕГО несогласованного превышения — иначе превышение
// родителя и ребёнка складывалось бы дважды (баг usePendingExcessTotal.ts,
// найденный на дереве субсидии 108).
import { describe, it, expect } from 'vitest'
import { excessRootNodes, isUnapprovedExcessNode } from '../excessRootNodes'
import type { FeoCategory, PlanTreeEntry } from '../types'

function cat(id: number, parentId: number | null): FeoCategory {
  return { id, parent_id: parentId, subsidy_id: 108, level: 1, name: `#${id}`, code: null, appendix: null,
    is_active: true, budget: null, planned_quantity: null, planned_amount: null, unit: null,
    feo_quantity: null, feo_unit: null, description: null, feo_amount: null } as FeoCategory
}

function entry(partial: Partial<PlanTreeEntry>): PlanTreeEntry {
  return { excess_amount: 0, excess_approved: false, ...partial } as PlanTreeEntry
}

describe('excessRootNodes', () => {
  it('структура владельца (субсидия 108): раздел-родитель с превышением 257 232,76 ' +
     'и дети со СВОИМИ превышениями — итог = ТОЛЬКО превышение раздела, дети не суммируются', () => {
    // 1 = «Закупка товаров…» (раздел), budget 27 545 297,60, позиций
    // 27 802 530,36 → excess_amount = 257 232,76 (несогласовано).
    // 2 = «Материальные запасы», 3 = «Основные средства», 4 = «Прочие работы,
    // услуги» — дети раздела 1, у каждого СВОЁ несогласованное превышение.
    // 5 = «Налоги» — budget == позиции, без превышения (excess_amount=0).
    const feoCategories = [
      cat(1, null),
      cat(2, 1), cat(3, 1), cat(4, 1), cat(5, 1),
    ]
    const planTreeByCat: Record<number, PlanTreeEntry> = {
      1: entry({ excess_amount: 257232.76, excess_approved: false }),
      2: entry({ excess_amount: 120000, excess_approved: false }),
      3: entry({ excess_amount: 95000, excess_approved: false }),
      4: entry({ excess_amount: 15788.02, excess_approved: false }),
      5: entry({ excess_amount: 0, excess_approved: false }),
    }

    const result = excessRootNodes(planTreeByCat, feoCategories)

    expect(result.total).toBeCloseTo(257232.76, 2)
    expect(result.nodes).toEqual([{ categoryId: 1, amount: 257232.76 }])
  })

  it('превышения на НЕЗАВИСИМЫХ ветках (разные корни) суммируются оба', () => {
    const feoCategories = [cat(1, null), cat(2, null), cat(3, 1)]
    const planTreeByCat: Record<number, PlanTreeEntry> = {
      1: entry({ excess_amount: 1000, excess_approved: false }),
      2: entry({ excess_amount: 2000, excess_approved: false }),
      3: entry({ excess_amount: 0, excess_approved: false }),
    }

    const result = excessRootNodes(planTreeByCat, feoCategories)

    expect(result.total).toBeCloseTo(3000, 2)
    expect(result.nodes.map(n => n.categoryId).sort()).toEqual([1, 2])
  })

  it('превышение ребёнка БЕЗ превышения родителя — ребёнок сам становится «корнем»', () => {
    const feoCategories = [cat(1, null), cat(2, 1)]
    const planTreeByCat: Record<number, PlanTreeEntry> = {
      1: entry({ excess_amount: 0, excess_approved: false }),
      2: entry({ excess_amount: 500, excess_approved: false }),
    }

    const result = excessRootNodes(planTreeByCat, feoCategories)

    expect(result.total).toBeCloseTo(500, 2)
    expect(result.nodes).toEqual([{ categoryId: 2, amount: 500 }])
  })

  it('согласованное превышение (excess_approved=true) не считается и не блокирует потомков', () => {
    const feoCategories = [cat(1, null), cat(2, 1)]
    const planTreeByCat: Record<number, PlanTreeEntry> = {
      1: entry({ excess_amount: 10000, excess_approved: true }), // согласовано — не входит
      2: entry({ excess_amount: 300, excess_approved: false }),  // предок approved, не «висит» — узел 2 сам становится корнем
    }

    const result = excessRootNodes(planTreeByCat, feoCategories)

    expect(result.total).toBeCloseTo(300, 2)
    expect(result.nodes).toEqual([{ categoryId: 2, amount: 300 }])
  })

  it('isUnapprovedExcessNode: порог 0.005 и approved=true гасят узел', () => {
    expect(isUnapprovedExcessNode(entry({ excess_amount: 0.001, excess_approved: false }))).toBe(false)
    expect(isUnapprovedExcessNode(entry({ excess_amount: 10, excess_approved: true }))).toBe(false)
    expect(isUnapprovedExcessNode(entry({ excess_amount: 10, excess_approved: false }))).toBe(true)
    expect(isUnapprovedExcessNode(undefined)).toBe(false)
  })

  it('пустое дерево — total=0, nodes=[]', () => {
    const result = excessRootNodes({}, [])
    expect(result.total).toBe(0)
    expect(result.nodes).toEqual([])
  })
})
