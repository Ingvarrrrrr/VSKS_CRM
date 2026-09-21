// Единственный фронтовый источник строк ТЗ (Правило №6) — читает
// GET /api/purchases/{id}/tz-rows | GET /api/wishes/{id}/tz-rows,
// пишет решения по дублям через PUT /api/purchases/{id}/tz-duplicates.
// Формы ответа — 1:1 с backend/app/services/tz_items.py::serialize_tz_result
// (сверено по коду, не по описанию задачи — там расходится: item_type в
// ответе НЕТ, поле называется source_item_ids, а не source_items).
//
// Никакого локального пересчёта дублей здесь и в компонентах, которые этим
// пользуются (TzRowsSection.vue, CreateOrderView.vue секция 2.5,
// WishTzSection.vue) — группировка/merge/итоги всегда идут с сервера.
import { computed, ref, unref, type ComputedRef, type Ref } from 'vue'
import { apiFetch } from '@/api'
import { describeApiError } from '@/utils/apiErrorMessage'

export interface TzRow {
  item_id: number | null
  item_name: string
  unit: string
  quantity: number | null
  unit_price: number | null
  total_price: number | null
  price_averaged: boolean
  feo_category_ids: number[]
  source_item_ids: (number | null)[]
}

export interface TzDuplicateGroup {
  key: string
  name: string
  unit: string
  item_ids: (number | null)[]
  qty_sum: number | null
  total_sum: number | null
  prices_differ: boolean
  feo_category_ids: number[]
  decision: 'merge' | 'keep' | null
}

export interface TzRowsResult {
  rows: TzRow[]
  duplicate_groups: TzDuplicateGroup[]
  unresolved_keys: string[]
  decisions: Record<string, string>
}

type IdRef = Ref<number | null | undefined> | ComputedRef<number | null | undefined>

export function useTzRows(purchaseId: IdRef, wishId: IdRef) {
  const rows = ref<TzRow[]>([])
  const duplicateGroups = ref<TzDuplicateGroup[]>([])
  const unresolvedKeys = ref<string[]>([])
  const decisions = ref<Record<string, string>>({})
  const loading = ref(false)
  const applying = ref(false)
  const error = ref<string | null>(null)

  // decisions разрешены только у закупки (у заявки своего хранилища нет —
  // см. backend/app/routers/wish_tz.py).
  const canDecide = computed(() => !!unref(purchaseId))

  function _base(): string | null {
    const pid = unref(purchaseId)
    if (pid) return `/purchases/${pid}`
    const wid = unref(wishId)
    if (wid) return `/wishes/${wid}`
    return null
  }

  function _applyResult(data: TzRowsResult) {
    rows.value = data.rows || []
    duplicateGroups.value = data.duplicate_groups || []
    unresolvedKeys.value = data.unresolved_keys || []
    decisions.value = data.decisions || {}
  }

  async function refresh() {
    const base = _base()
    if (!base) {
      rows.value = []
      duplicateGroups.value = []
      unresolvedKeys.value = []
      decisions.value = {}
      return
    }
    loading.value = true
    error.value = null
    try {
      const data = await apiFetch<TzRowsResult>(`${base}/tz-rows`)
      _applyResult(data)
    } catch (e: any) {
      error.value = describeApiError(e, { fallback: 'Не удалось загрузить ТЗ' })
    } finally {
      loading.value = false
    }
  }

  /** decisions — карта group_key → 'merge'|'keep', мержится с уже сохранёнными
   * решениями на бэкенде (см. purchase_tz.py::put_purchase_tz_duplicates). */
  async function applyDecisions(next: Record<string, 'merge' | 'keep'>): Promise<TzRowsResult> {
    const pid = unref(purchaseId)
    if (!pid) throw new Error('Решения по дублям доступны только для сохранённой закупки')
    applying.value = true
    try {
      // apiFetch сериализует body сам (JSON.stringify внутри), но его тип —
      // RequestInit['body'] (BodyInit); как и везде в проекте (см.
      // useItemsCatalog.ts) — типизируем объект как any перед передачей.
      const body: any = { decisions: next }
      const data = await apiFetch<TzRowsResult>(`/purchases/${pid}/tz-duplicates`, {
        method: 'PUT',
        body,
      })
      _applyResult(data)
      return data
    } finally {
      applying.value = false
    }
  }

  const hasUnresolved = computed(() => unresolvedKeys.value.length > 0)
  const resolvedGroups = computed(() =>
    duplicateGroups.value.filter((g) => g.decision === 'merge' || g.decision === 'keep'),
  )
  const mergedCount = computed(() => resolvedGroups.value.filter((g) => g.decision === 'merge').length)
  const keptCount = computed(() => resolvedGroups.value.filter((g) => g.decision === 'keep').length)

  /** Для нерешённой группы rows всё ещё содержат её строки по отдельности —
   * находим их по пересечению source_item_ids с item_ids группы, чтобы
   * показать «Огнетушитель — 2 шт и 3 шт» без второго алгоритма группировки. */
  function rowsForGroup(group: TzDuplicateGroup): TzRow[] {
    const ids = new Set(group.item_ids)
    return rows.value.filter((r) => r.source_item_ids.length && r.source_item_ids.every((id) => ids.has(id)))
  }

  return {
    rows,
    duplicateGroups,
    unresolvedKeys,
    decisions,
    loading,
    applying,
    error,
    canDecide,
    hasUnresolved,
    resolvedGroups,
    mergedCount,
    keptCount,
    refresh,
    applyDecisions,
    rowsForGroup,
  }
}
