// useFeoPlannedSearch — поле поиска по ВСЕМ плановым позициям СУБСИДИИ внутри
// FeoPlannedItemsSelect.vue (владелец, 2026-09-16, дефект 1: «Весло разборное для
// поворотной уключины 150см» — плановая позиция существует (id 5580, категория
// «Водный транспорт»), но закупка привязана к другой категории (6151), и старый
// пикер показывал только плановые ТЕКУЩЕЙ категории — позиция была физически
// недостижима из формы).
//
// Источник данных — тот же POST /feo-planned-items/match, что и уже существующий
// блок «похожие плановые позиции» (useFeoPlannedMatch.ts/FeoPlannedMatchSuggestions.vue,
// см. Правило №6 — второй движок сравнения имён не заводим). Отличие от него: тот
// блок подсказывает по имени ТЕКУЩЕЙ позиции автоматически, этот — по тому, что
// человек ВВОДИТ в поле поиска, без ограничения текущей категорией
// (feo_category_id не передаём — /match тогда ищет по всей субсидии и не
// фильтрует по ветке, same_category у всех кандидатов будет true и не используется
// здесь; «своя ветка или нет» считаем сами по ancestor_ids — тем же способом, что
// useFeoPlannedRows.ts::filteredItems).
//
// Сортировка результата (владелец, дословно): «сначала точные совпадения по имени,
// затем частичные по токенам, затем остальные по алфавиту» — само совпадение считает
// backend (score = generic_progressive_match, тот же токенайзер/стемминг, что и
// везде), здесь только раскладываем уже посчитанный score по трём корзинам
// (planMatchThresholds.ts, зеркалит text_match.py) и сортируем внутри корзин.
import { computed, ref, watch } from 'vue'
import { useFeoPlanMatching, type FeoMatchCandidate } from '@/composables/useFeoPlanMatching'
import type { FeoPlanPosition } from '@/composables/useFeoPlannedResiduals'
import { PLAN_MATCH_SCORE_EXACT, PLAN_MATCH_SCORE_SUGGEST } from '@/constants/planMatchThresholds'

/** Строка результата поиска — полная FeoPlanPosition (остаток/план/ед. — те же
 *  серверные числа, что уже загружены в props.items, см. лукап по key ниже) плюс
 *  то, что даёт только /match: путь по дереву и признак «выбор перенесёт категорию». */
export interface FeoPlannedSearchRow extends FeoPlanPosition {
  // path уже объявлен на FeoPlanPosition (путь по дереву ФЭО, «Транспорт › …») —
  // второго поля не заводим (ПРАВИЛО №6); значение здесь всегда из кандидата
  // /match (build_category_path на бэке), даже когда base найден в props.items —
  // оба источника формируют путь одной и той же функцией, расхождения не бывает.
  score: number
  /** true — кандидат ВНЕ ветки текущей category_id (сама категория или её потомок).
   *  Выбор такого кандидата в FeoPlannedItemsSelect.vue переносит категорию позиции
   *  вслед за плановой (см. onItemPlannedChange/onSplitPartPlannedChange/applyBulkFeo/
   *  ReqItemEditDialog.onPlanSelect — единая правка синхронизации категории). */
  crossCategory: boolean
}

export interface UseFeoPlannedSearchDeps {
  props: {
    items: FeoPlanPosition[]
    categoryId: number | null
    subsidyId?: number | null
  }
}

const MIN_QUERY_LEN = 2
const DEBOUNCE_MS = 300
const SEARCH_LIMIT = 25

function inCurrentBranch(row: { category_id: number; ancestor_ids?: number[] }, categoryId: number | null): boolean {
  if (categoryId == null) return true
  return row.category_id === categoryId || (row.ancestor_ids || []).includes(categoryId)
}

export function useFeoPlannedSearch(deps: UseFeoPlannedSearchDeps) {
  const { props } = deps
  const { matching, matchQueries } = useFeoPlanMatching()

  const searchText = ref('')
  const rawCandidates = ref<FeoMatchCandidate[]>([])
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  // Токен последнего запроса — ответ на устаревший запрос (быстро сменили текст)
  // не должен перезаписать результат более свежего ввода.
  let requestToken = 0

  const searchActive = computed(() => searchText.value.trim().length >= MIN_QUERY_LEN)

  async function runSearch() {
    const q = searchText.value.trim()
    if (q.length < MIN_QUERY_LEN || !props.subsidyId) {
      rawCandidates.value = []
      return
    }
    const token = ++requestToken
    const results = await matchQueries([q], props.subsidyId, undefined, SEARCH_LIMIT)
    if (token !== requestToken) return // устарел
    rawCandidates.value = results[0]?.candidates || []
  }

  watch([searchText, () => props.subsidyId], () => {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; void runSearch() }, DEBOUNCE_MS)
  })

  /** Лукап по составному ключу — тот же, что и useFeoPlannedResiduals::getPlannedItem,
   *  не копия (просто Map поверх уже загрученного props.items для O(1) на кандидата). */
  const itemsByKey = computed(() => {
    const map = new Map<string, FeoPlanPosition>()
    for (const r of props.items) map.set(r.key, r)
    return map
  })

  const searchRows = computed((): FeoPlannedSearchRow[] => {
    const rows: FeoPlannedSearchRow[] = rawCandidates.value.map(c => {
      const full = itemsByKey.value.get(c.key)
      const base: FeoPlanPosition = full ?? {
        id: c.id, name: c.name, path: c.path, category_id: c.category_id, kind: c.kind,
        planned_quantity: null, unit: '', planned_amount: null, unit_price: null,
        consumed: 0, consumed_quantity: 0, residual: 0, residual_quantity: 0, key: c.key,
      }
      return {
        ...base,
        // Путь — ВСЕГДА из кандидата /match (см. комментарий у интерфейса выше),
        // даже когда base найден в props.items (тот же build_category_path на бэке).
        path: c.path,
        score: c.score,
        crossCategory: !inCurrentBranch(base, props.categoryId),
      }
    })

    const exact = rows.filter(r => r.score >= PLAN_MATCH_SCORE_EXACT).sort((a, b) => b.score - a.score)
    const partial = rows
      .filter(r => r.score >= PLAN_MATCH_SCORE_SUGGEST && r.score < PLAN_MATCH_SCORE_EXACT)
      .sort((a, b) => b.score - a.score)
    const rest = rows
      .filter(r => r.score < PLAN_MATCH_SCORE_SUGGEST)
      .sort((a, b) => a.name.localeCompare(b.name, 'ru'))

    return [...exact, ...partial, ...rest]
  })

  function clearSearch() {
    searchText.value = ''
    rawCandidates.value = []
  }

  return { searchText, searchActive, searchLoading: matching, searchRows, clearSearch }
}

export type UseFeoPlannedSearch = ReturnType<typeof useFeoPlannedSearch>
