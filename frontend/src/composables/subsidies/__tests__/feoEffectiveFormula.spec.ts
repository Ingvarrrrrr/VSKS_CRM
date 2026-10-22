// ПРАВИЛО №6 — computeFeoEffective — общая форма рекурсии, вынесенная из
// useFeoTreeAmounts.ts и FeoCategoriesView.vue (обе страницы дублировали её,
// находка владельца 22.10.2026: группа без budget теряла собственный прямой
// вклад). Чистая логика, без Vue/ctx.
import { describe, it, expect } from 'vitest'
import { computeFeoEffective, feoBudgetIsSet, isEstimatedNode, type FeoEffectiveNode } from '../feoEffectiveFormula'

interface Node extends FeoEffectiveNode {
  id: number
  children: Node[]
}

function node(id: number, budget: number | null, children: Node[] = []): Node {
  return { id, budget, hasChildren: children.length > 0, children }
}

describe('computeFeoEffective', () => {
  it('узел со своим budget — возвращает его, игнорируя детей/собственный вклад', () => {
    const n = node(1, 500, [node(2, null)])
    expect(computeFeoEffective(n, () => 999)).toBe(500)
  })

  it('лист без budget — ownContributionFor(node)', () => {
    const n = node(1, null)
    expect(computeFeoEffective(n, (x) => x.id * 10)).toBe(10)
  })

  it('группа без budget — Σ детей + СВОЙ прямой вклад (не теряется)', () => {
    const child1 = node(2, null)
    const child2 = node(3, null)
    const group = node(1, null, [child1, child2])
    // own-контрибьюция: 100 для группы (id=1), 7*id для детей.
    const own = (n: Node) => (n.id === 1 ? 100 : n.id * 7)
    expect(computeFeoEffective(group, own)).toBe(100 + 2 * 7 + 3 * 7)
  })

  // ИСПРАВЛЕНИЕ (QA, 22.10.2026, ПРАВИЛО №6): budgetIsSet по умолчанию теперь
  // ВСЕГДА feoBudgetIsSet (0 и null — «не задано») — единое правило для обеих
  // страниц, второй копии (FeoCategoriesView.vue историческое «0 = задано»)
  // больше нет; кастомный предикат всё ещё можно передать явно.
  it('budgetIsSet по умолчанию — budget=0 читается как «не задано» (единое правило, см. feoBudgetIsSet)', () => {
    const n = node(1, 0)
    expect(computeFeoEffective(n, () => 999)).toBe(999)
  })

  it('кастомный budgetIsSet — можно передать свой предикат (например, budget=0 = «задано»)', () => {
    const n = node(1, 0)
    expect(computeFeoEffective(n, () => 42, (x) => x.budget != null)).toBe(0)
  })

  it('вложенная группа (3 уровня) — собственный вклад прибавляется на КАЖДОМ уровне', () => {
    const leaf = node(3, null)
    const mid = node(2, null, [leaf])
    const root = node(1, null, [mid])
    const own = () => 1 // каждый узел добавляет 1 к своей оценке
    // root: (mid: (leaf: 1) + 1) + 1 = (1+1)+1 = 3
    expect(computeFeoEffective(root, own)).toBe(3)
  })
})

describe('feoBudgetIsSet / isEstimatedNode (QA-находка 22.10.2026)', () => {
  it('null и 0 — оба «не задано»', () => {
    expect(feoBudgetIsSet(null)).toBe(false)
    expect(feoBudgetIsSet(undefined)).toBe(false)
    expect(feoBudgetIsSet(0)).toBe(false)
    expect(feoBudgetIsSet('0')).toBe(false)
  })

  it('положительное число — «задано»', () => {
    expect(feoBudgetIsSet(500)).toBe(true)
    expect(feoBudgetIsSet('500')).toBe(true)
  })

  it('isEstimatedNode — ЛИСТ без ФЭО тоже «расчётный» (FeoCategoriesView.vue больше не держит лист в «Задать/—» навечно)', () => {
    const leaf = node(1, null) // hasChildren=false
    expect(isEstimatedNode(leaf)).toBe(true)
    const leafWithZero = node(2, 0)
    expect(isEstimatedNode(leafWithZero)).toBe(true)
    const leafWithBudget = node(3, 500)
    expect(isEstimatedNode(leafWithBudget)).toBe(false)
  })
})
