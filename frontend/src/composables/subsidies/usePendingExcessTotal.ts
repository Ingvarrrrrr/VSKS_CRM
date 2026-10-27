// Шаг 6 (план humble-stirring-emerson.md, 23.10.2026) — ссылка «выше ФЭО на
// N» под карточкой «Запланировано»: сценарий владельца — статья с планом
// (ФЭО) 100, заявка/закупка подняла план позиций до 102,1 → карточка теперь
// (задача владельца 27.10.2026) показывает ПОЛНУЮ сумму 102,1 сразу, а
// ссылка рядом поясняет, что 2,1 из них — выше бюджета ФЭО и ждут решения
// согласующего (не блокирует карточку, см. docstring excessRootNodes.ts).
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
// ИСПРАВЛЕНО (27.10.2026, живой пример владельца — субсидия 108): раньше
// суммировался excess_amount КАЖДОГО узла дерева подряд — родитель и его
// дети могли ОБА нести ненулевой excess_amount одновременно (родитель
// накопил через full_display Σ позиций ВСЕГО поддерева, включая позиции,
// которые у ребёнка и дали его собственное превышение), поэтому старая сумма
// задваивала одно и то же превышение (257 232,76 раздела + 5 530 788,02 его
// детей = неверные 5 788 020,78). Дедуп — отдельный чистый модуль
// excessRootNodes.ts (ПРАВИЛО №5 — не раздувать этот файл формулой дедупа):
// «корневой» узел превышения — самый верхний уровень с превышением на
// каждой ветке (ни у одного предка нет СВОЕГО несогласованного
// превышения); на примере владельца итог = 257 232,76 (только раздел).
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
import { excessRootNodes, isUnapprovedExcessNode } from './excessRootNodes'

export interface PendingExcessRow {
  categoryId: number
  categoryName: string
  nodeExcessAmount: number
  purchaseId: number | null
  purchaseNumber: string | number | null
  itemName: string | null
  amount: number
  // excess_pending узла (PlanTreeEntry.excess_pending) — true, когда по
  // этому узлу УЖЕ создан запрос на согласование (PlanExcessApproval в
  // статусе pending), а не просто есть несогласованное превышение без
  // запроса. Строка списка дописывает «отправлено на согласование» (задача
  // владельца 27.10.2026) — слово «согласование» больше НЕ используется в
  // самой подписи-сумме (см. PendingExcessNote.vue), только здесь, когда
  // запрос реально существует.
  nodePending: boolean
}

interface PendingExcessCtx {
  planTreeByCat: Ref<Record<number, PlanTreeEntry>>
  feoCategories: Ref<FeoCategory[]>
}

function rowsForNode(
  nodeId: number, categoryName: string, amount: number,
  culprit: ExcessCulprit | null | undefined, nodePending: boolean,
): PendingExcessRow[] {
  if (culprit?.culprits?.length) {
    return culprit.culprits.map(c => ({
      categoryId: nodeId, categoryName, nodeExcessAmount: amount, nodePending,
      purchaseId: c.purchase_id, purchaseNumber: c.purchase_number, itemName: c.item_name,
      amount: c.amount,
    }))
  }
  if (culprit) {
    return [{
      categoryId: nodeId, categoryName, nodeExcessAmount: amount, nodePending,
      purchaseId: culprit.purchase_id, purchaseNumber: culprit.purchase_number, itemName: culprit.item_name,
      amount: culprit.amount_at_crossing,
    }]
  }
  // Нет culprit (напр. старый бэкенд/ещё не рассчитан) — хотя бы строка
  // категории с суммой превышения, без привязки к конкретной закупке.
  return [{ categoryId: nodeId, categoryName, nodeExcessAmount: amount, nodePending, purchaseId: null, purchaseNumber: null, itemName: null, amount }]
}

/** Строит {total, rows} для ссылки «выше ФЭО на N» под карточкой
 * «Запланировано» — вызывать с ctx = useSubsidyDetailCtx() (не ctx-синглтон
 * этого модуля, в отличие от useFeoTreeExcess — читает только planTreeByCat/
 * feoCategories, которые уже есть в общем ctx субсидии). */
export function usePendingExcessTotal(ctx: PendingExcessCtx) {
  const roots = computed(() => excessRootNodes(ctx.planTreeByCat.value, ctx.feoCategories.value))

  const total = computed(() => roots.value.total)

  const rows = computed<PendingExcessRow[]>(() => {
    const out: PendingExcessRow[] = []
    const nameFor = (id: number) => ctx.feoCategories.value.find(c => c.id === id)?.name || `#${id}`
    for (const { categoryId, amount } of roots.value.nodes) {
      const entry = ctx.planTreeByCat.value[categoryId]
      out.push(...rowsForNode(categoryId, nameFor(categoryId), amount, entry?.excess_culprit, Boolean(entry?.excess_pending)))
    }
    return out
  })

  return { total, rows }
}

// Экспорт для прямых проверок (чип «требуется согласование» и т.п.) — тот же
// предикат, что и у excessRootNodes.ts, не дублируем здесь.
export { isUnapprovedExcessNode }
