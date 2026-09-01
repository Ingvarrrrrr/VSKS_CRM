// useFeoTreeNodes — общий источник узлов дерева ФЭО для шапочного FeoTreeSelect
// (CreateOrderView, WishesView). Раньше шапка строила дерево из allFeoCategories,
// загруженного через GET /feo-categories/ (list_categories) — этот эндпоинт НЕ отдаёт
// has_budget/has_plan, поэтому filterFundedNodes считал план по числовым полям самой
// категории и не видел план, заданный плановыми позициями или ручной суммой
// (FeoCategory.plan_source='manual_sum'). Построчный выбор (useFeoLeaves) уже ходил в
// GET /feo-categories/flat, который эти признаки считает на сервере — из-за этого
// категория была видна в построчном выборе, но пропадала в шапке (баг задачи «Этап A»).
// Этот composable переносит шапку на тот же /flat, переиспользуя filterFundedNodes
// (useFeoLeaves.ts) и цепочку-фолбэк для уже выбранного непрофинансированного узла
// (перенесена из CreateOrderView.vue:7009-7023 без изменения поведения).
import { computed, ref, watch, type Ref } from 'vue'
import { apiFetch } from '@/api'
import { filterFundedNodes, type FeoNode } from './useFeoLeaves'

export function useFeoTreeNodes(
  subsidyId: Ref<number | null | undefined>,
  selectedId: Ref<number | null | undefined>,
) {
  const rawNodes = ref<FeoNode[]>([])

  watch(
    () => subsidyId.value,
    async (sid) => {
      if (!sid) {
        rawNodes.value = []
        return
      }
      try {
        rawNodes.value = await apiFetch<FeoNode[]>(`/feo-categories/flat?subsidy_id=${sid}`)
      } catch {
        rawNodes.value = []
      }
    },
    { immediate: true },
  )

  // Узлы без финансирования/плана (ни у себя, ни у потомков) исключены — плюс
  // фолбэк-цепочка для уже выбранного узла, который сам не профинансирован (например
  // «Не определена» или ранее сохранённая закупка ссылается на категорию без плана):
  // без фолбэка дерево не может отрисовать выбранный узел и поле окажется пустым.
  // Логика 1:1 перенесена из CreateOrderView.vue feoTreeNodes (было computed на
  // allFeoCategories) — поведение не меняется, меняется только источник узлов.
  const feoTreeNodes = computed<FeoNode[]>(() => {
    if (!subsidyId.value) return []
    const raw = rawNodes.value
    const funded = filterFundedNodes(raw)
    const selId = selectedId.value
    if (selId == null) return funded
    const fundedIds = new Set(funded.map(n => n.id))
    if (fundedIds.has(selId)) return funded
    const byId = new Map(raw.map(n => [n.id, n]))
    const chain: FeoNode[] = []
    let cur = byId.get(selId)
    while (cur) {
      if (!fundedIds.has(cur.id)) chain.push({ ...cur, is_leaf: cur.id === selId })
      cur = cur.parent_id != null ? byId.get(cur.parent_id) : undefined
    }
    return chain.length ? [...funded, ...chain] : funded
  })

  return { feoTreeNodes, rawNodes }
}
