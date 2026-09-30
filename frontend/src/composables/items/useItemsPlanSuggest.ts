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
import { checkPlanOccupancy } from '@/composables/items/feoPlanned/feoPlanOccupancy'

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
  /** Авансовый отчёт (владелец, 30.09.2026, решение повторное и жёсткое): «не
   *  сопоставляем» — подсказки похожих плановых позиций для авансового отчёта
   *  никогда не показываются (каждая позиция получает свою плановую сама, см.
   *  бэкенд app/services/advance_auto_plan.py). Ref, а не bool — PurchaseItemsEditor.vue
   *  передаёт computed isAdvance, значение может стать известно позже первого рендера. */
  disabled?: Ref<boolean>
}

const DEBOUNCE_MS = 600
const CANDIDATES_PER_ITEM = 3

export function useItemsPlanSuggest(deps: UseItemsPlanSuggestDeps) {
  const { localItems, subsidyId, plannedItems, effectiveCategoryId, disabled } = deps
  const { matchQueries } = useFeoPlanMatching()

  // Ключ — стабильный _uid позиции (не idx: индекс сдвигается при удалении строк
  // выше по списку, а карту кандидатов пересчитывает debounce с задержкой).
  const candidatesByUid = ref<Map<string | number, FeoMatchCandidate[]>>(new Map())

  const unlinkedSignature = computed(() =>
    disabled?.value
      ? ''
      : localItems.value
        .filter(it => !it.feo_planned_item_id && (it.item_name || '').trim())
        .map(it => `${it._uid}:${(it.item_name || '').trim()}`)
        .join('|')
  )

  let timer: ReturnType<typeof setTimeout> | null = null
  let requestToken = 0

  async function runMatch() {
    if (disabled?.value) {
      candidatesByUid.value = new Map()
      return
    }
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
      const cands = (results[i]?.candidates || []).map(c => {
        const row = plannedItems.value.find(p => p.key === c.key) ?? null
        // Владелец (30.09.2026, «Доставка из чека должна быть создана отдельно,
        // она не должна объединяться ни с чем») — то же правило «занято», что и
        // в bulk-match (useFeoPlannedBulkMatch.ts), один расчёт (ПРАВИЛО №6):
        // подсказка под строкой не должна выглядеть чистым совпадением, если
        // кандидата уже держит другая закупка/заявка или остатка не хватает на
        // сумму/количество ЭТОЙ позиции.
        const occ = checkPlanOccupancy(row, { amount: it.total_price ?? null, quantity: it.quantity ?? null })
        return {
          ...c,
          same_category: ownCategoryId == null
            ? c.same_category
            : (c.category_id === ownCategoryId
                || (row?.ancestor_ids || []).includes(ownCategoryId)),
          occupied: occ.occupied,
        }
      })
      if (cands.length) map.set(it._uid, cands)
    })
    candidatesByUid.value = map
  }

  watch([unlinkedSignature, subsidyId, () => disabled?.value], () => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => { timer = null; void runMatch() }, DEBOUNCE_MS)
  }, { immediate: true })

  function candidatesFor(item: EditorItem): FeoMatchCandidate[] {
    if (disabled?.value) return []
    if (!item || item.feo_planned_item_id) return []
    return candidatesByUid.value.get(item._uid) || []
  }

  return { candidatesFor }
}

export type UseItemsPlanSuggest = ReturnType<typeof useItemsPlanSuggest>
