// Переключатель «Только изменённые / Всё дерево» для оверлея корректировки —
// волна 3B. Переиспользуемый (владелец: «у исполнителя по умолчанию выключен,
// у проверяющего включён» — ОДИН компонент/композабл с параметром default, не
// два похожих). FeoTreeTable.vue (исполнитель, default=false) и экран
// проверяющего (другая волна, default=true) используют этот же composable.
import { computed, ref, type ComputedRef } from 'vue'
import type { RevisionOverlayApi } from './useRevisionOverlay'

export interface RevisionChangedFilterApi {
  onlyChanged: ReturnType<typeof ref<boolean>>
  visibleCategoryIds: ComputedRef<Set<number> | null> // null = фильтр выключен, показывать всё
  changedCount: ComputedRef<number>
  totalCount: ComputedRef<number>
  currentIndex: ReturnType<typeof ref<number>>
  orderedChangedIds: ComputedRef<Array<number | string>>
  goToIndex: (i: number) => void
  next: () => void
  prev: () => void
}

function scrollToNodeId(id: number | string) {
  const el = document.querySelector<HTMLElement>(`[data-feo-node-id="${id}"]`)
  el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

/**
 * @param defaultOn — исходное состояние переключателя (исполнитель: false —
 *   видно всё дерево; проверяющий: true — сразу только изменённое).
 * @param allCategoryIds — ВСЕ id категорий текущего дерева (для totalCount и
 *   для выдачи «показать всё», когда фильтр выключен).
 * @param parentOf — волна 3C-доп.: parent_id категории по её id — нужен, чтобы
 *   докинуть в visibleCategoryIds категорию ИЗМЕНЁННОЙ ПОЗИЦИИ и её предков.
 *   preview.ancestors (бэкенд) считает цепочку только от touched КАТЕГОРИЙ
 *   (см. subsidy_revision_preview.py::_collect_touched_category_ids) — правка
 *   плановой позиции без правки самой категории не делает категорию видимой
 *   под фильтром без этого докидывания. Один источник видимости (Правило №6):
 *   адаптирован этот composable, второй фильтр не заводится. Необязателен —
 *   старые вызовы (FeoTreeTable.vue до этой правки) без него просто не получат
 *   докидывание, т.е. прежнее поведение не ломается.
 */
export function useRevisionChangedFilter(
  defaultOn: boolean,
  overlay: () => RevisionOverlayApi | null,
  allCategoryIds: () => number[],
  parentOf?: (categoryId: number) => number | null,
) {
  const onlyChanged = ref(defaultOn)
  const currentIndex = ref(0)

  const orderedChangedIds = computed<Array<number | string>>(() => {
    const ov = overlay()
    if (!ov?.preview.value) return []
    const cats = ov.preview.value.changed.categories
    const items = ov.preview.value.changed.items
    return [...cats, ...items]
  })

  const changedCount = computed(() => orderedChangedIds.value.length)
  const totalCount = computed(() => allCategoryIds().length)

  // Множество id, которые должны остаться видимыми в режиме «только
  // изменённые»: сами изменённые строки + цепочка родителей над ними
  // (ancestors из /preview) — остальное скрыто. null = показать всё дерево.
  const visibleCategoryIds = computed<Set<number> | null>(() => {
    if (!onlyChanged.value) return null
    const ov = overlay()
    if (!ov?.preview.value) return null
    const set = new Set<number>()
    for (const c of ov.preview.value.changed.categories) {
      const n = Number(c)
      if (!Number.isNaN(n)) set.add(n)
    }
    for (const a of ov.preview.value.ancestors) set.add(a)
    if (parentOf) {
      // Категория изменённой позиции + вся цепочка предков над ней (см. докстринг
      // параметра parentOf выше) — preview.ancestors её не несёт.
      const itemsAfter = ov.preview.value.after?.items || {}
      const itemsBefore = ov.preview.value.before?.items || {}
      for (const itemId of ov.preview.value.changed.items) {
        const it = itemsAfter[String(itemId)] || itemsBefore[String(itemId)]
        let cur: number | null = it?.feo_category_id ?? null
        const seen = new Set<number>()
        while (cur != null && !seen.has(cur)) {
          seen.add(cur)
          set.add(cur)
          cur = parentOf(cur)
        }
      }
    }
    return set
  })

  function goToIndex(i: number) {
    const ids = orderedChangedIds.value
    if (!ids.length) return
    const idx = ((i % ids.length) + ids.length) % ids.length
    currentIndex.value = idx
    const id = ids[idx]
    if (id != null) scrollToNodeId(id)
  }
  function next() { goToIndex(currentIndex.value + 1) }
  function prev() { goToIndex(currentIndex.value - 1) }

  return {
    onlyChanged, visibleCategoryIds, changedCount, totalCount,
    currentIndex, orderedChangedIds, goToIndex, next, prev,
  }
}

export type RevisionChangedFilterApi2 = ReturnType<typeof useRevisionChangedFilter>
