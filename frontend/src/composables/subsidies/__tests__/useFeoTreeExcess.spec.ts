// useFeoTreeExcess.ts читает localStorage (user_role/user_id для isSaas) при
// построении — окружение теста по умолчанию 'node' (vitest.config.ts), jsdom
// не установлен как зависимость; минимальный полифил ниже (ТОЛЬКО getItem,
// больше здесь не нужно) — без добавления новой зависимости проекта.
//
// Задача владельца 22.10.2026, дословно: «должно подсвечивать красным
// последнее добавленное, из-за чего произошёл переход через лимит плана или
// ФЭО» — пример: чайник и термопот, добавленные в «Бытовую технику». Эти
// тесты проверяют excessCulpritIndex/plannedItemExcessHit/purchaseItemExcessHit
// (useFeoTreeExcess.ts) — ВСЯ цепочка culprits подсвечивается, не только
// первая позиция, и поиск идёт по ВСЕМ узлам planTreeByCat (не только узлу,
// на котором «висит» само превышение — задание «ЛЮБОГО узла-предка»).
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useFeoTreeExcess, excessHitTooltip } from '../useFeoTreeExcess'
import type { PlanTreeEntry } from '../types'

if (typeof (globalThis as any).localStorage === 'undefined') {
  ;(globalThis as any).localStorage = { getItem: () => null }
}

function buildCtx(planTreeByCat: Record<string, any>) {
  return {
    planTreeByCat: ref(planTreeByCat as Record<number, PlanTreeEntry>),
    planExcessApprovals: ref({}),
    selectedId: ref<number | null>(1),
    refreshReqData: async () => {},
  } as any
}

describe('useFeoTreeExcess — culprits (цепочка позиций-виновников, не только первая)', () => {
  it('plannedItemExcessHit находит ВСЕ позиции из culprits, в т.ч. когда excess_culprit висит на узле-предке', () => {
    // Превышение — на узле 1 (ancestor-группа), сами позиции («Чайник»/
    // «Термопот») физически лежат в категории 2 (вложенный лист «Бытовая
    // техника») — category_id контрибьютора ≠ nodeId, у которого excess_culprit.
    const planTreeByCat = {
      1: {
        excess_amount: 25, excess_over_feo: 25, budget: 100,
        excess_culprit: {
          purchase_id: null, purchase_number: null, item_name: 'Чайник',
          amount_before: 90, amount_at_crossing: 25, cumulative_after: 115,
          total_plan_amount: 125, total_excess: 25,
          culprits: [
            { planned_item_id: 501, purchase_id: null, purchase_number: null, purchase_item_id: null, category_id: 2, item_name: 'Чайник', amount: 25 },
            { planned_item_id: 502, purchase_id: null, purchase_number: null, purchase_item_id: null, category_id: 2, item_name: 'Термопот', amount: 10 },
          ],
        },
      },
      2: { excess_amount: 0 },
    }
    const ctx = buildCtx(planTreeByCat)
    const api = useFeoTreeExcess(ctx)

    expect(api.isExcessCulpritPlannedItem(501)).toBe(true)
    expect(api.isExcessCulpritPlannedItem(502)).toBe(true)
    expect(api.isExcessCulpritPlannedItem(503)).toBe(false)

    const hit501 = api.plannedItemExcessHit(501)
    expect(hit501).not.toBeNull()
    expect(hit501!.nodeId).toBe(1) // excess_culprit живёт на узле-предке 1
    expect(hit501!.totalExcess).toBe(25)
    expect(hit501!.budget).toBe(100)
  })

  it('purchaseItemExcessHit матчит по purchase_item_id (точнее, чем старый purchase_id+item_name)', () => {
    const planTreeByCat = {
      5: {
        excess_amount: 10, budget: 50,
        excess_culprit: {
          purchase_id: 77, purchase_number: 'РЕЕ-1', item_name: 'Болгарка',
          amount_before: 40, amount_at_crossing: 10, cumulative_after: 50,
          total_plan_amount: 60, total_excess: 10,
          culprits: [
            { planned_item_id: null, purchase_id: 77, purchase_number: 'РЕЕ-1', purchase_item_id: 900, category_id: 5, item_name: 'Болгарка', amount: 10 },
          ],
        },
      },
    }
    const ctx = buildCtx(planTreeByCat)
    const api = useFeoTreeExcess(ctx)

    expect(api.purchaseItemExcessHit({ purchase_id: 77, item_name: 'Болгарка', purchase_item_id: 900 })).not.toBeNull()
    // Контрибьютор С purchase_item_id индексируется ТОЛЬКО по нему (точнее) —
    // вызов без purchase_item_id для такого контрибьютора не матчит фолбэком
    // (фолбэк по purchase_id+item_name строится лишь для контрибьюторов БЕЗ
    // purchase_item_id — старый бэкенд/синтетические записи, см. следующий тест).
    expect(api.purchaseItemExcessHit({ purchase_id: 77, item_name: 'Болгарка' })).toBeNull()
    expect(api.purchaseItemExcessHit({ purchase_id: 77, item_name: 'Другая позиция' })).toBeNull()
  })

  it('фолбэк: excess_culprit без culprits (старый бэкенд) — одна позиция, как раньше', () => {
    const planTreeByCat = {
      9: {
        excess_amount: 5, budget: 20,
        excess_culprit: {
          purchase_id: null, purchase_number: null, item_name: 'Старый формат',
          amount_before: 15, amount_at_crossing: 5, cumulative_after: 20,
          total_plan_amount: 25, total_excess: 5,
          // culprits отсутствует вовсе — старый бэкенд.
        },
      },
    }
    const ctx = buildCtx(planTreeByCat)
    const api = useFeoTreeExcess(ctx)

    expect(api.isExcessCulpritActual({ id: 9 } as any, { purchase_id: 0, item_name: 'Старый формат' })).toBe(false)
    // Без purchase_id фолбэк не матчит по id=0 (purchase_id в фикстуре null) —
    // но planned_item_id-поиска через fallback-запись (category_id=9) быть не
    // должно, т.к. planned_item_id в синтетической записи — null.
    expect(api.isExcessCulpritPlannedItem(123)).toBe(false)
  })
})

describe('excessHitTooltip', () => {
  it('называет категорию по имени (если найдена) и суммы через formatCurrency', () => {
    const text = excessHitTooltip({ nodeId: 2, totalExcess: 25, budget: 100 }, [{ id: 2, name: 'Бытовая техника' }] as any)
    expect(text).toContain('Бытовая техника')
    expect(text).toContain('100,00')
    expect(text).toContain('25,00')
  })

  it('категория не найдена — подставляет #id, не падает', () => {
    const text = excessHitTooltip({ nodeId: 404, totalExcess: 1, budget: null }, [])
    expect(text).toContain('#404')
  })
})
