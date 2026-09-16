// useItemsPlanSuggest — «похожие плановые позиции» ПОД КАЖДОЙ построчной позицией
// закупки/заявки (владелец, 2026-09-16, дефекты 2 и 4).
//
// Повод: механизм для этого был построен ПОЛНОСТЬЮ ещё в шаге 4 плана
// zany-fluttering-mountain.md — POST /feo-planned-items/match на бэке,
// FeoMatchCandidate/useFeoPlanMatching.ts, useFeoPlannedMatch.ts (same/other category
// split, bindCandidate) и FeoPlannedMatchSuggestions.vue (UI-блок с кнопкой
// «Привязать») — но проп `candidates` у FeoPlannedItemsSelect.vue НИГДЕ не был
// заполнен для позиций закупки/заявки (см. её собственный докстринг: «PurchaseItems
// Editor.vue его не передаёт»). matchQueries/matchOne не вызывались ни из одного
// реального экрана — отсюда жалоба «раньше было, теперь не вижу»: механизм не
// сломан, он никогда не был подключён к построчному редактору позиций.
//
// Здесь — ТОЛЬКО подключение (Правило №6: движок matchQueries не копируется, вызывается
// как есть). Один батч-запрос на ВСЕ непривязанные позиции формы (а не по одному
// запросу на строку) — так же, как это уже делает /products/match для каталога
// товаров (useItemMatching.ts). feo_category_id в запросе НЕ передаём (в отличие от
// bulk-match ниже это не нужно: same_category здесь пересчитывается локально ниже —
// у каждой позиции своя категория, а тело запроса поддерживает только одну общую).
import { computed, ref, watch, type Ref } from 'vue'
import { useFeoPlanMatching, type FeoMatchCandidate } from '@/composables/useFeoPlanMatching'
import type { FeoPlanPosition } from '@/composables/useFeoPlannedResiduals'

type EditorItem = any

export interface UseItemsPlanSuggestDeps {
  localItems: Ref<EditorItem[]>
  subsidyId: Ref<number | null | undefined>
  plannedItems: Ref<FeoPlanPosition[]>
  /** Эффективная категория позиции — тот же расчёт, что рендерит строку (см.
   *  effectiveCategoryId в ItemsTableFlat.vue/ItemsCardsView.vue/ItemsTableStages.vue),
   *  нужна ТОЛЬКО чтобы пересчитать same_category кандидата относительно СВОЕЙ
   *  категории конкретной позиции (бэк считает same_category по ОДНОЙ переданной
   *  на весь батч feo_category_id, здесь категории у позиций разные). */
  effectiveCategoryId: (item: EditorItem) => number | null
}

const DEBOUNCE_MS = 600
const CANDIDATES_PER_ITEM = 3

export function useItemsPlanSuggest(deps: UseItemsPlanSuggestDeps) {
  const { localItems, subsidyId, plannedItems, effectiveCategoryId } = deps
  const { matchQueries } = useFeoPlanMatching()

  // Ключ — стабильный _uid позиции (не idx: индекс сдвигается при удалении строк
  // выше по списку, а карту кандидатов пересчитывает debounce с задержкой).
  const candidatesByUid = ref<Map<string | number, FeoMatchCandidate[]>>(new Map())

  const unlinkedSignature = computed(() =>
    localItems.value
      .filter(it => !it.feo_planned_item_id && (it.item_name || '').trim())
      .map(it => `${it._uid}:${(it.item_name || '').trim()}`)
      .join('|')
  )

  let timer: ReturnType<typeof setTimeout> | null = null
  let requestToken = 0

  async function runMatch() {
    const rows = localItems.value.filter(it => !it.feo_planned_item_id && (it.item_name || '').trim())
    if (!rows.length || !subsidyId.value) {
      candidatesByUid.value = new Map()
      return
    }
    const token = ++requestToken
    const results = await matchQueries(
      rows.map(it => it.item_name),
      subsidyId.value,
      undefined, // без ограничения категорией — same_category пересчитываем сами ниже
      CANDIDATES_PER_ITEM,
    )
    if (token !== requestToken) return // устарел — пришёл ответ на более старый запрос

    const map = new Map<string | number, FeoMatchCandidate[]>()
    rows.forEach((it, i) => {
      const ownCategoryId = effectiveCategoryId(it)
      const cands = (results[i]?.candidates || []).map(c => ({
        ...c,
        same_category: ownCategoryId == null
          ? c.same_category
          : (c.category_id === ownCategoryId
              || (plannedItems.value.find(p => p.key === c.key)?.ancestor_ids || []).includes(ownCategoryId)),
      }))
      if (cands.length) map.set(it._uid, cands)
    })
    candidatesByUid.value = map
  }

  watch([unlinkedSignature, subsidyId], () => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => { timer = null; void runMatch() }, DEBOUNCE_MS)
  }, { immediate: true })

  function candidatesFor(item: EditorItem): FeoMatchCandidate[] {
    if (!item || item.feo_planned_item_id) return []
    return candidatesByUid.value.get(item._uid) || []
  }

  return { candidatesFor }
}

export type UseItemsPlanSuggest = ReturnType<typeof useItemsPlanSuggest>
