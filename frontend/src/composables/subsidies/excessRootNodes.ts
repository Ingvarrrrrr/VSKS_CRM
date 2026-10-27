// excessRootNodes.ts — «верхний узел с несогласованным превышением плана над
// ФЭО на каждой ветке дерева», без двойного счёта (задача владельца
// 27.10.2026, живой пример — субсидия 108).
//
// Баг, который этот модуль чинит: usePendingExcessTotal.ts раньше суммировал
// excess_amount КАЖДОГО узла дерева подряд. Родитель и его дети могут ОБА
// одновременно иметь ненулевой excess_amount (родитель накопил через
// plan_manual/full_display Σ позиций всего поддерева, включая позиции,
// которые у ребёнка и дали его собственное превышение) — суммирование обоих
// считает одно и то же превышение дважды. Пример владельца: раздел «Закупка
// товаров…» budget 27 545 297,60, позиций 27 802 530,36 → excess 257 232,76;
// его дети по отдельности дают ЕЩЁ 5 530 788,02 excess — старая сумма
// 5 788 020,78 неверна, правильный итог — 257 232,76 (ТОЛЬКО превышение
// раздела, дети не добавляются поверх).
//
// Правило: узел попадает в сумму, только если НИ У ОДНОГО из его ПРЕДКОВ
// (цепочка parent_id вверх по дереву ФЭО) нет СВОЕГО несогласованного
// превышения — т.е. берём самый верхний уровень с превышением на каждой
// ветке, а не все уровни сразу.
import type { FeoCategory, PlanTreeEntry } from './types'

export interface ExcessRootNode {
  categoryId: number
  amount: number
}

export interface ExcessRootNodesResult {
  total: number
  nodes: ExcessRootNode[]
}

/** «Несогласованное превышение „план дороже ФЭО“» узла — та же трактовка,
 * что у чипа «требуется согласование» (FeoTreeRow.vue/ctx.excessFor): сумма
 * больше нуля И не approved, НЕЗАВИСИМО от того, создан ли уже запрос на
 * согласование (excess_pending лишь уточняет, отправлен ли запрос). */
export function isUnapprovedExcessNode(entry: PlanTreeEntry | undefined): boolean {
  const amount = Number(entry?.excess_amount || 0)
  return amount > 0.005 && !entry?.excess_approved
}

/** {total, nodes} — Σ excess_amount ТОЛЬКО по «корневым» узлам превышения
 * (см. докстринг модуля за правилом), БЕЗ двойного счёта предок+потомок.
 *
 * planTreeByCat — {categoryId: PlanTreeEntry} (ключи-строки из Object.keys,
 * как хранит ctx.planTreeByCat — нечисловые ключи типа 'subsidy_type_excess'/
 * 'subsidy_type_totals' пропускаются, это не узлы категорий).
 * feoCategories — список категорий ЭТОЙ субсидии (для parent_id — цепочка
 * предков строится по нему, не по дереву компонента, Правило №6: тот же
 * список, что уже грузит SubsidiesView.vue). */
export function excessRootNodes(
  planTreeByCat: Record<number, PlanTreeEntry>,
  feoCategories: FeoCategory[],
): ExcessRootNodesResult {
  const parentOf = new Map<number, number | null>()
  for (const c of feoCategories) parentOf.set(c.id, c.parent_id)

  function hasUnapprovedExcessAncestor(categoryId: number): boolean {
    const seen = new Set<number>() // защита от случайного цикла в данных
    let cur = parentOf.get(categoryId) ?? null
    while (cur != null && !seen.has(cur)) {
      seen.add(cur)
      if (isUnapprovedExcessNode(planTreeByCat[cur])) return true
      cur = parentOf.get(cur) ?? null
    }
    return false
  }

  const nodes: ExcessRootNode[] = []
  let total = 0
  for (const [key, entry] of Object.entries(planTreeByCat)) {
    const categoryId = Number(key)
    if (!Number.isFinite(categoryId)) continue
    if (!isUnapprovedExcessNode(entry)) continue
    if (hasUnapprovedExcessAncestor(categoryId)) continue
    const amount = Number(entry.excess_amount || 0)
    nodes.push({ categoryId, amount })
    total += amount
  }
  return { total, nodes }
}
