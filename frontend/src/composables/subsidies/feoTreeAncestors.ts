// Общий хелпер «предки узла дерева ФЭО по feoCategories» — раньше жил только
// внутри useKpiDrilldown.ts (feoParentMap/feoAncestorIds/feoHasChildren), не
// был доступен снаружи. useExcessDrilldown.ts (задание владельца 06.10.2026,
// «раскрыть субсидию и привести стрелочками к каждому пункту превышения»)
// нужен тот же механизм раскрытия предков — вынесено сюда, ОБА composable
// вызывают эту функцию, а не копируют её (Правило №6).
import { computed, type Ref } from 'vue'
import type { FeoCategory } from './types'

export function buildFeoAncestors(feoCategories: Ref<FeoCategory[]>) {
  function feoHasChildren(id: number): boolean {
    return feoCategories.value.some(c => c.parent_id === id)
  }

  const feoParentMap = computed<Record<number, number | null>>(() => {
    const map: Record<number, number | null> = {}
    for (const c of feoCategories.value) map[c.id] = c.parent_id
    return map
  })

  // Строгие предки узла (без самого узла), до корня
  function feoAncestorIds(id: number): number[] {
    const result: number[] = []
    let pid = feoParentMap.value[id] ?? null
    while (pid != null) {
      result.push(pid)
      pid = feoParentMap.value[pid] ?? null
    }
    return result
  }

  return { feoHasChildren, feoParentMap, feoAncestorIds }
}
