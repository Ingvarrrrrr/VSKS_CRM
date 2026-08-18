// useFeoPlanMatching — Шаг 4 плана zany-fluttering-mountain.md: «когда заявки
// заведены, и если в субсидии уже есть плановая позиция, предлагать плановые
// позиции, похожие по имени, и предлагать поставить их... человек может
// подтвердить, что позиция выбрана правильно, а может отвергнуть и выбрать свою».
//
// Зеркалит useItemMatching.ts (тот же паттерн для сопоставления товара с каталогом),
// только источник — POST /feo-planned-items/match (плановые позиции субсидии, не
// каталог товаров). См. backend/app/routers/feo_planned_items.py::match_planned_items.
import { ref } from 'vue'
import { apiFetch } from '@/api'

export type FeoMatchKind = 'plan_position' | 'feo_article' | 'planned_item'
export type FeoMatchStatus = 'auto' | 'suggest' | 'create'

export interface FeoMatchCandidate {
  kind: FeoMatchKind
  id: number
  /** `${kind}:${id}` — тот же составной ключ, что и FeoPlanPosition.key (useFeoPlannedResiduals). */
  key: string
  name: string
  path: string
  category_id: number
  /** [0, 1] — доля совпадения токенов запроса, НЕ проценты (умножать на 100 в UI). */
  score: number
  /** false — кандидат из категории, отличной от переданной feo_category_id (или её
   *  ветки предков). С 2026-08-18 /feo-planned-items/map разрешает привязку и к
   *  таким кандидатам — она ПЕРЕНОСИТ позицию закупки (и связанную позицию заявки)
   *  в категорию выбранной плановой позиции, ничего не блокируя. same_category
   *  оставлен только для группировки «своя категория / другая категория» в UI —
   *  визуальная подсказка, не жёсткое ограничение, — не подмешиваются молча к «своим». */
  same_category: boolean
}

export interface FeoMatchResult {
  query: string
  status: FeoMatchStatus
  candidates: FeoMatchCandidate[]
}

export function useFeoPlanMatching() {
  const matching = ref(false)

  /** Batch-запрос POST /feo-planned-items/match. */
  async function matchQueries(
    queries: string[],
    subsidyId: number,
    feoCategoryId?: number | null,
  ): Promise<FeoMatchResult[]> {
    if (!queries.length || !subsidyId) return []
    matching.value = true
    try {
      const data = await apiFetch<{ results: FeoMatchResult[] }>('/feo-planned-items/match', {
        method: 'POST',
        body: {
          queries,
          subsidy_id: subsidyId,
          feo_category_id: feoCategoryId ?? null,
        },
      })
      return data?.results ?? []
    } finally {
      matching.value = false
    }
  }

  /** Удобная обёртка: один запрос, лучший результат (для заголовочной подсказки заявки). */
  async function matchOne(
    query: string,
    subsidyId: number,
    feoCategoryId?: number | null,
  ): Promise<FeoMatchResult | null> {
    const q = (query || '').trim()
    if (!q) return null
    const results = await matchQueries([q], subsidyId, feoCategoryId)
    return results[0] ?? null
  }

  return { matching, matchQueries, matchOne }
}
