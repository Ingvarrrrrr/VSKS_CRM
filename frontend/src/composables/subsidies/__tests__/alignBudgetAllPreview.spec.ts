// alignBudgetAllPreview.spec.ts — НАЙДЕНО владельцем 27.10.2026
// (ДНР_актуальная): «у 41 статьи на сумму 99 215 853,86 ₽» при плане
// 62 973 630,53 ₽ — старая формула задваивала деньги группы и её детей.
// Синтетическое дерево: группа (кумулятивный план 150 000) + 2 листа-ребёнка
// (100 000 + 50 000) — та же форма, что регрессия в backend/tests/
// test_feo_align_all.py::test_align_all_group_and_children_no_double_count.
import { describe, it, expect } from 'vitest'
import { computeAlignBudgetAllPreview, alignTargetBudget } from '../alignBudgetAllPreview'

describe('computeAlignBudgetAllPreview', () => {
  it('группа+дети — count считает только листья, budgetAfter == план корня, без задвоения', () => {
    const categories = [
      { id: 1, parent_id: null, hasChildren: true, budget: null },   // группа, план кумулятивный = 150000
      { id: 2, parent_id: 1, hasChildren: false, budget: null },     // лист А, план 100000
      { id: 3, parent_id: 1, hasChildren: false, budget: null },     // лист Б, план 50000
    ]
    const planTreeByCat = {
      1: { plan: 150_000, over: 0 },
      2: { plan: 100_000, over: 0 },
      3: { plan: 50_000, over: 0 },
    }
    const result = computeAlignBudgetAllPreview(categories, planTreeByCat)
    expect(result.count).toBe(2)            // только листья, группа не считается статьёй
    expect(result.budgetAfter).toBe(150_000) // Σ по корню, НЕ 150000+100000+50000=300000
  })

  it('несколько независимых направлений (корней) — budgetAfter складывает их отдельно', () => {
    const categories = [
      { id: 1, parent_id: null, hasChildren: true, budget: 0 },
      { id: 2, parent_id: 1, hasChildren: false, budget: 0 },
      { id: 10, parent_id: null, hasChildren: false, budget: 5_000 }, // уже равна плану
    ]
    const planTreeByCat = {
      1: { plan: 40_000, over: 0 },
      2: { plan: 40_000, over: 0 },
      10: { plan: 5_000, over: 0 },
    }
    const result = computeAlignBudgetAllPreview(categories, planTreeByCat)
    expect(result.count).toBe(1)             // только категория 2 (лист, меняется); 10 не меняется
    expect(result.budgetAfter).toBe(45_000)  // 40000 (направление 1) + 5000 (направление 10, без изменений)
  })

  it('ни одна статья не меняется — count=0, budgetAfter == текущему бюджету корней', () => {
    const categories = [
      { id: 1, parent_id: null, hasChildren: false, budget: 5_000 },
    ]
    const planTreeByCat = { 1: { plan: 5_000, over: 0 } }
    const result = computeAlignBudgetAllPreview(categories, planTreeByCat)
    expect(result.count).toBe(0)
    expect(result.budgetAfter).toBe(5_000)
  })

  it('alignTargetBudget — plan+over, 0 при отсутствующей записи дерева', () => {
    expect(alignTargetBudget({ plan: 10, over: 5 })).toBe(15)
    expect(alignTargetBudget(undefined)).toBe(0)
  })
})
