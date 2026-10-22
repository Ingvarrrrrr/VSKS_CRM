// Тест задачи владельца «А» (ДНР5, id 97, 13.10.2026): узел БЕЗ собственной
// суммы ФЭО не должен считаться «превысившим лимит», даже если у него есть
// собственные плановые позиции в довесок к планам подкатегорий. Единственный
// источник превышения теперь — серверные excess_over_feo/excess_amount узла
// (см. докстринг feoIsOverBudget/feoServerExcessFor в useFeoTreeAmounts.ts).
import { describe, it, expect } from 'vitest'
import { ref, computed } from 'vue'
import { useFeoTreeAmounts } from '../useFeoTreeAmounts'
import type { FeoNode, PlanTreeEntry } from '../types'

function makeNode(partial: Partial<FeoNode> & { id: number; name: string }): FeoNode {
  return {
    id: partial.id,
    parent_id: partial.parent_id ?? null,
    subsidy_id: 97,
    level: partial.level ?? 1,
    name: partial.name,
    code: null,
    appendix: null,
    is_active: true,
    budget: partial.budget ?? null,
    planned_quantity: null,
    planned_amount: null,
    unit: null,
    feo_quantity: null,
    feo_unit: null,
    description: null,
    feo_amount: null,
    depth: partial.depth ?? 0,
    hasChildren: !!(partial.children && partial.children.length),
    children: partial.children ?? [],
  } as FeoNode
}

function buildCtx(planTreeByCat: Record<number, Partial<PlanTreeEntry>>, feoTreeNodes: FeoNode[]) {
  return {
    purchaseTotals: ref({}),
    plannedPurchaseTotals: ref({}),
    plannedPurchaseQty: ref({}),
    plannedPurchaseTotalsLinked: ref({}),
    plannedPurchaseQtyLinked: ref({}),
    plannedPurchaseTotalsOver: ref({}),
    plannedPurchaseQtyOver: ref({}),
    plannedPurchaseForecast: ref({}),
    planTreeByCat: ref(planTreeByCat as Record<number, PlanTreeEntry>),
    plannedItemsByCat: ref({}),
    feoTree: computed(() => feoTreeNodes),
    plannedBase: ref<'all' | 'manual' | 'requests' | 'purchases'>('all'),
    selectedSubsidy: computed(() => null),
    allSubsidies: ref([]),
    selectedId: ref<number | null>(97),
    silentRefreshSubsidies: async () => {},
  } as any
}

describe('useFeoTreeAmounts — ПРАВКА А: превышение только по серверному excess_over_feo', () => {
  it('узел без собственного budget не считается превысившим лимит, даже когда Σ плана (с собственными позициями) больше Σ budget подкатегорий', () => {
    // «Расходы на приобретение основных средств» (id=2): budget=null, две
    // подкатегории с budget 400000 + 405187.92 = 805187.92, плюс собственные
    // позиции (Чайник 1904.45 + Термопот 6287.04) — план узла (с бэкенда)
    // 813379.41 > 805187.92, но budget этого узла не задан — сервер НЕ пишет
    // excess_over_feo (ровно как в compute_feo_plan_tree).
    const sub1 = makeNode({ id: 3, name: 'Канцелярские расходы', parent_id: 2, budget: 400000 })
    const sub2 = makeNode({ id: 4, name: 'Хозяйственные расходы', parent_id: 2, budget: 405187.92 })
    const rpoos = makeNode({ id: 2, name: 'Расходы на приобретение основных средств', parent_id: 1, budget: null, children: [sub1, sub2] })
    const root = makeNode({ id: 1, name: 'Прочие расходы', parent_id: null, budget: null, children: [rpoos] })

    const planTreeByCat: Record<number, Partial<PlanTreeEntry>> = {
      1: { plan_manual: 813379.41, excess_over_feo: 0, excess_amount: 0 },
      2: { plan_manual: 813379.41, excess_over_feo: 0, excess_amount: 0 },
      3: { plan_manual: 400000, excess_over_feo: 0, excess_amount: 0 },
      4: { plan_manual: 405187.92, excess_over_feo: 0, excess_amount: 0 },
    }
    const ctx = buildCtx(planTreeByCat, [root])
    const api = useFeoTreeAmounts(ctx)

    expect(api.feoIsOverBudget(rpoos)).toBe(false)
    expect(api.feoHasOverspentDescendant(root)).toBe(false)
    expect(api.feoOverspentDescendantText(root)).toBe('')
    // Старая (неверная) формула дала бы отрицательный feoFinDiff — новая не уходит в минус.
    expect(api.feoFinDiff(rpoos)).toBeGreaterThanOrEqual(0)
  })

  it('узел С собственным budget, реально превышенным планом — считается превысившим лимит, текст содержит сумму превышения', () => {
    const over = makeNode({ id: 5, name: 'Расходы на приобретение основных средств', parent_id: 1, budget: 800000 })
    const root = makeNode({ id: 1, name: 'Прочие расходы', parent_id: null, budget: null, children: [over] })

    const planTreeByCat: Record<number, Partial<PlanTreeEntry>> = {
      1: { plan_manual: 813379.41, excess_over_feo: 13379.41, excess_amount: 13379.41 },
      5: { plan_manual: 813379.41, excess_over_feo: 13379.41, excess_amount: 13379.41 },
    }
    const ctx = buildCtx(planTreeByCat, [root])
    const api = useFeoTreeAmounts(ctx)

    expect(api.feoIsOverBudget(over)).toBe(true)
    expect(api.feoHasOverspentDescendant(root)).toBe(true)
    expect(api.feoOverspentDescendantText(root)).toContain('13')
    expect(api.feoOverspentDescendantText(root)).toContain('379,41')
    expect(api.feoOverspentDescendantText(root)).toContain('Расходы на приобретение основных средств')
  })

  it('несколько превысивших подкатегорий — текст «N подкатегорий превышают ФЭО, всего на X»', () => {
    const a = makeNode({ id: 10, name: 'А', parent_id: 1, budget: 100 })
    const b = makeNode({ id: 11, name: 'Б', parent_id: 1, budget: 100 })
    const root = makeNode({ id: 1, name: 'Прочие расходы', parent_id: null, budget: null, children: [a, b] })
    const planTreeByCat: Record<number, Partial<PlanTreeEntry>> = {
      10: { plan_manual: 150, excess_over_feo: 50 },
      11: { plan_manual: 120, excess_over_feo: 20 },
      1: { plan_manual: 270 },
    }
    const ctx = buildCtx(planTreeByCat, [root])
    const api = useFeoTreeAmounts(ctx)

    expect(api.feoOverspentDescendantText(root)).toBe('2 подкатегорий превышают ФЭО, всего на 70,00 ₽')
  })
})

// Задача владельца 22.10.2026 (ДНР_2026 id 105) — потери «расчёта» ФЭО и
// ложный красный «Запланировано» без пояснения.
describe('useFeoTreeAmounts — ДНР_2026: расчёт группы с собственными позициями и честный красный флаг', () => {
  it('группа без своего ФЭО: расчёт = Σ детей + собственные позиции (827 425 + 16 500 = 843 925)', () => {
    const child = makeNode({ id: 20, name: 'Подкатегория', parent_id: 2, budget: null })
    const group = makeNode({ id: 2, name: 'Расходы на приобретение основных средств', parent_id: 1, budget: null, children: [child] })
    const planTreeByCat: Record<number, Partial<PlanTreeEntry>> = {
      20: { plan_manual: 827425 },
      2: { plan_manual: 843925 },
    }
    const ctx = buildCtx(planTreeByCat, [group])
    const api = useFeoTreeAmounts(ctx)

    expect(api.feoEffectiveFor(child)).toBe(827425)
    expect(api.feoOwnDirectionPlanFor(group)).toBe(16500)
    expect(api.feoEffectiveFor(group)).toBe(843925)
  })

  it('лист без своего ФЭО: isAutoNode=true, расчёт = план своих позиций (входит в ИТОГО тем же числом)', () => {
    const leaf = makeNode({ id: 30, name: 'ФОТ', parent_id: null, budget: null })
    const planTreeByCat: Record<number, Partial<PlanTreeEntry>> = {
      30: { plan_manual: 33881012.80 },
    }
    const ctx = buildCtx(planTreeByCat, [leaf])
    const api = useFeoTreeAmounts(ctx)

    expect(api.isAutoNode(leaf)).toBe(true)
    expect(api.feoEffectiveFor(leaf)).toBe(33881012.80)
    expect(api.totalFeoEffective.value).toBe(33881012.80)
  })

  it('узел без своего ФЭО с планом больше расчёта — не настоящее превышение (feoFinDiff=0, feoIsOverBudget=false)', () => {
    const node = makeNode({ id: 40, name: 'Без ФЭО', parent_id: null, budget: null })
    const planTreeByCat: Record<number, Partial<PlanTreeEntry>> = {
      40: { plan_manual: 100000, excess_over_feo: 0, excess_amount: 0 },
    }
    const ctx = buildCtx(planTreeByCat, [node])
    const api = useFeoTreeAmounts(ctx)

    // feoDisplayedFor(node) без budget = feoEffectiveFor = 0 (нет фактов/плана
    // на самом узле с детьми; тут лист без фактов и без собственного budget —
    // возвращает feoPlannedTotalFor, т.е. тот же план) — проверяем именно
    // «не красный», а не конкретные цифры расчёта.
    expect(api.feoFinDiff(node)).toBe(0)
    expect(api.feoIsOverBudget(node)).toBe(false)
    expect(api.feoHasOverspentDescendant(node)).toBe(false)
  })

  it('узел со своим ФЭО, план больше budget — настоящее превышение: feoFinDiff<0 (красный) и есть чем объяснить', () => {
    const node = makeNode({ id: 50, name: 'С ФЭО', parent_id: null, budget: 800000 })
    const planTreeByCat: Record<number, Partial<PlanTreeEntry>> = {
      // display — та же плановая сумма, что читает feoPlannedDisplayFor в
      // режиме plannedBase='all' (умолчание buildCtx) — без неё тест читал бы
      // 0 вместо реального плана и не воспроизвёл бы находку владельца.
      50: { plan_manual: 843925, display: 843925, excess_over_feo: 43925, excess_amount: 43925 },
    }
    const ctx = buildCtx(planTreeByCat, [node])
    const api = useFeoTreeAmounts(ctx)

    expect(api.feoFinDiff(node)).toBeLessThan(0)
    expect(Math.abs(api.feoFinDiff(node))).toBeGreaterThan(0.005)
    expect(api.feoIsOverBudget(node)).toBe(true)
  })
})
