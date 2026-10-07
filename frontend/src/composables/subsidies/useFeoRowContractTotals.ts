// «Законтрактовано / из них заказано / зарезервировано» по статье ФЭО —
// расшифровка колонки «В закупках» строки дерева (решение владельца
// 06.10.2026, .planning/quick/2026-10-06-feo-row-sums/PLAN.md, шаг 4).
//
// Бэкенд (GET /feo-categories/row-contract-totals?subsidy_id=N) отдаёт
// СОБСТВЕННЫЕ суммы каждой категории (не поддерева) — поддерево суммируется
// здесь ТЕМ ЖЕ способом, что и соседние колонки дерева (feoPlannedRequestsFor/
// feoPlannedConsumedFor в useFeoTreeAmounts.ts — own + Σ детей), второй способ
// суммирования поддерева не заводим (Правило №6).
//
// Module-level singleton (как useFeoTreeAmounts.ts/useExcessDrilldown.ts) —
// строится в SubsidiesView.vue с ctx {feoTree, selectedId} одновременно с
// loadFeoTree/refreshReqData (тот же триггер обновления, что у
// plannedPurchaseTotals), FeoTreeRow.vue переиспользует вызовом без аргумента.
import { ref, type Ref } from 'vue'
import { apiFetch } from '@/api'
import type { FeoNode } from './types'
import { makeCtxSingleton } from './ctxSingleton'

export interface RowContractTotalsEntry { contracted: number; ordered: number; reserved: number }

interface FeoRowContractTotalsCtx {
  feoTree: Ref<FeoNode[]>
  selectedId: Ref<number | null>
}

export const useFeoRowContractTotals = makeCtxSingleton(
  buildFeoRowContractTotals,
  'useFeoRowContractTotals() вызван до первого построения (нужен ctx) — проверьте порядок монтирования SubsidiesView.vue',
)

function buildFeoRowContractTotals(_ctx: FeoRowContractTotalsCtx) {
  const rowTotals = ref<Record<string, RowContractTotalsEntry>>({})

  // Эндпоинт делает параллельный исполнитель (см. PLAN.md) — на время, пока
  // его ещё нет на бэке, запрос падает 404/500: дерево не должно из-за этого
  // сломаться, просто строки «законтрактовано/заказано/резерв» молчат
  // (ownFor вернёт нули), как и было задание («убедись, что дерево не падает»).
  async function loadRowContractTotals(subsidyId: number) {
    try {
      const res = await apiFetch<Record<string, RowContractTotalsEntry>>(
        `/feo-categories/row-contract-totals?subsidy_id=${subsidyId}`,
      )
      rowTotals.value = res || {}
    } catch {
      rowTotals.value = {}
    }
  }

  function ownFor(node: FeoNode): RowContractTotalsEntry {
    const e = rowTotals.value[String(node.id)]
    return {
      contracted: Number(e?.contracted || 0),
      ordered: Number(e?.ordered || 0),
      reserved: Number(e?.reserved || 0),
    }
  }

  function contractedFor(node: FeoNode): number {
    const own = ownFor(node).contracted
    if (!node.hasChildren) return own
    return own + node.children.reduce((acc, c) => acc + contractedFor(c), 0)
  }
  function orderedFor(node: FeoNode): number {
    const own = ownFor(node).ordered
    if (!node.hasChildren) return own
    return own + node.children.reduce((acc, c) => acc + orderedFor(c), 0)
  }
  function reservedFor(node: FeoNode): number {
    const own = ownFor(node).reserved
    if (!node.hasChildren) return own
    return own + node.children.reduce((acc, c) => acc + reservedFor(c), 0)
  }
  // Решение владельца В2 (PLAN.md): законтрактовано − заказано − зарезервировано.
  function unallocatedFor(node: FeoNode): number {
    return contractedFor(node) - orderedFor(node) - reservedFor(node)
  }

  return { rowTotals, loadRowContractTotals, contractedFor, orderedFor, reservedFor, unallocatedFor }
}
