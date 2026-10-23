// Шаг 6 (план humble-stirring-emerson.md, 23.10.2026) — «на согласовании +N»
// под карточкой «Запланировано»: сценарий владельца — статья с планом (ФЭО)
// 100, заявка/закупка подняла план позиций до 102,1 → до согласования
// «Запланировано» остаётся 100 (plan_manual), а превышение видно рядом
// ссылкой «на согласовании +2,1»; после согласования «Запланировано» = 102,1.
//
// ПРАВИЛО №6 — НЕ второй расчёт превышения: читает ТЕ ЖЕ готовые поля узла
// дерева ФЭО (PlanTreeEntry.excess_amount/excess_approved/excess_culprit),
// что и чип «превышение N — требуется согласование» (FeoTreeRow.vue,
// ctx.excessFor — backend/app/services/feo_plan_tree.py, excess_amount =
// full_display − budget, excess_over_feo kind, см. find_excess_culprit в
// feo_plan_excess.py). Берётся ТОЛЬКО превышение «план дороже ФЭО»
// (excess_amount), а не «факт дороже плана»/«позиции дороже заданной на
// категорию суммы» — эти два отдельных вида (excess_fact_over_plan/
// excess_plan_over_manual) НЕ входят в формулу «Запланировано» (см.
// docstring compute_feo_plan_tree._visit) и не являются «тем же источником»,
// что «Запланировано».
//
// pending ЗДЕСЬ означает «не согласовано» (excess_amount > 0 И НЕ approved),
// НЕЗАВИСИМО от того, создан ли уже запрос на согласование (PlanExcessApproval)
// — та же трактовка, что и у чипа «требуется согласование» (ctx.excessFor
// возвращает ненулевой объект, когда amount>0.005, вне зависимости от t.
// excess_pending — pending там лишь уточняет, ОТПРАВЛЕН ли запрос).
//
// ФОТ без права «Видеть ФОТ» — отдельной фильтрации здесь не нужно: скрытые
// категории ФОТ полностью удаляются из ответа GET /feo-categories/plan-tree
// на бэкенде (payroll_visibility.strip_hidden_payroll_from_tree_result),
// поэтому их узлов просто нет в planTreeByCat для такого пользователя.
import { computed, type Ref } from 'vue'
import type { ExcessCulprit, FeoCategory, PlanTreeEntry } from './types'

export interface PendingExcessRow {
  categoryId: number
  categoryName: string
  nodeExcessAmount: number
  purchaseId: number | null
  purchaseNumber: string | number | null
  itemName: string | null
  amount: number
}

interface PendingExcessCtx {
  planTreeByCat: Ref<Record<number, PlanTreeEntry>>
  feoCategories: Ref<FeoCategory[]>
}

function isPendingExcessNode(t: PlanTreeEntry | undefined): boolean {
  const amount = Number(t?.excess_amount || 0)
  return amount > 0.005 && !t?.excess_approved
}

function rowsForNode(nodeId: number, categoryName: string, amount: number, culprit: ExcessCulprit | null | undefined): PendingExcessRow[] {
  if (culprit?.culprits?.length) {
    return culprit.culprits.map(c => ({
      categoryId: nodeId, categoryName, nodeExcessAmount: amount,
      purchaseId: c.purchase_id, purchaseNumber: c.purchase_number, itemName: c.item_name,
      amount: c.amount,
    }))
  }
  if (culprit) {
    return [{
      categoryId: nodeId, categoryName, nodeExcessAmount: amount,
      purchaseId: culprit.purchase_id, purchaseNumber: culprit.purchase_number, itemName: culprit.item_name,
      amount: culprit.amount_at_crossing,
    }]
  }
  // Нет culprit (напр. старый бэкенд/ещё не рассчитан) — хотя бы строка
  // категории с суммой превышения, без привязки к конкретной закупке.
  return [{ categoryId: nodeId, categoryName, nodeExcessAmount: amount, purchaseId: null, purchaseNumber: null, itemName: null, amount }]
}

/** Строит {total, rows} для ссылки «на согласовании +N» под карточкой
 * «Запланировано» — вызывать с ctx = useSubsidyDetailCtx() (не ctx-синглтон
 * этого модуля, в отличие от useFeoTreeExcess — читает только planTreeByCat/
 * feoCategories, которые уже есть в общем ctx субсидии). */
export function usePendingExcessTotal(ctx: PendingExcessCtx) {
  const total = computed(() => {
    let sum = 0
    for (const [key, entry] of Object.entries(ctx.planTreeByCat.value)) {
      const nodeId = Number(key)
      if (!Number.isFinite(nodeId)) continue // 'subsidy_type_excess'/'subsidy_type_totals' — не узлы
      if (isPendingExcessNode(entry)) sum += Number(entry.excess_amount || 0)
    }
    return sum
  })

  const rows = computed<PendingExcessRow[]>(() => {
    const out: PendingExcessRow[] = []
    const nameFor = (id: number) => ctx.feoCategories.value.find(c => c.id === id)?.name || `#${id}`
    for (const [key, entry] of Object.entries(ctx.planTreeByCat.value)) {
      const nodeId = Number(key)
      if (!Number.isFinite(nodeId)) continue
      if (!isPendingExcessNode(entry)) continue
      out.push(...rowsForNode(nodeId, nameFor(nodeId), Number(entry.excess_amount || 0), entry.excess_culprit))
    }
    return out
  })

  return { total, rows }
}
