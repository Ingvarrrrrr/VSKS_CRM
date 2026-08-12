// useItemMatching — encapsulates catalog product matching for editor rows.
// Extracted from PurchaseItemsEditor.vue (monolith refactor) so per-row inline
// matching, the repick dialog, and batch import review can share one source of
// truth for: the /products/match call, the MatchCandidate type, and the
// mutation that applies a chosen candidate to a row.
import { ref } from 'vue'
import { apiFetch } from '@/api'

export interface MatchCandidate {
  product_id: number
  name: string
  price: number | null
  score: number
  description?: string | null
  photo_url?: string | null
  item_type?: string | null
  category?: string | null
  /** Optional contract price; preferred over price when applying. */
  contract_price?: number | null
}

export type MatchStatus = 'auto' | 'suggest' | 'create'

export interface MatchResult {
  query: string
  status: MatchStatus
  candidates: MatchCandidate[]
}

/** Minimal shape of an editor row this composable mutates. */
export interface MatchableRow {
  product_id: number | null
  item_name: string
  item_type?: string
  unit_price?: number | null
  total_price?: number | null
  quantity?: number | null
  match_confirmed?: boolean
  _selectedProduct?: any
  _photo_url?: string
  _description?: string
  [k: string]: any
}

export function useItemMatching() {
  const matching = ref(false)

  /**
   * Call POST /products/match for a batch of query strings.
   * `prefix` (default: unset → backend defaults to false) enables prefix-stem
   * matching for interactive typing in the row's inline product search — words
   * longer than 6 chars otherwise only match starting at the 6th typed
   * character (see backend text_match._stem_hits). Batch/import callers must
   * leave it unset so matching stays strict.
   */
  async function matchQueries(queries: string[], limit?: number, prefix?: boolean): Promise<MatchResult[]> {
    if (!queries.length) return []
    matching.value = true
    try {
      const body: { queries: string[]; limit?: number; prefix?: boolean } = { queries }
      if (limit != null) body.limit = limit
      if (prefix != null) body.prefix = prefix
      const data = await apiFetch<{ results: MatchResult[] }>('/products/match', {
        method: 'POST',
        body,
      })
      return data?.results ?? []
    } finally {
      matching.value = false
    }
  }

  /** Convenience: match a single query, return its candidate list (status badge too). */
  async function matchOne(query: string, limit?: number, prefix?: boolean): Promise<MatchResult | null> {
    const q = (query || '').trim()
    if (!q) return null
    const results = await matchQueries([q], limit, prefix)
    return results[0] ?? null
  }

  /**
   * Apply a chosen catalog candidate to a row in place. Mirrors the historical
   * onItemProductSelect / onRepickPick behaviour:
   *  - sets product_id, item_name, _selectedProduct, _photo_url, _description
   *  - sets item_type only if the row has none yet
   *  - sets unit_price (contract_price ?? price) only if the row has none yet,
   *    then recomputes total_price = qty × unit_price
   *  - marks match_confirmed = true
   */
  function applyCandidate(row: MatchableRow, cand: MatchCandidate): void {
    row.product_id = cand.product_id
    row.item_name = cand.name || row.item_name
    row._selectedProduct = cand
    row._photo_url = cand.photo_url ?? undefined
    row._description = cand.description ?? undefined
    if (cand.item_type && !row.item_type) row.item_type = cand.item_type
    if (row.unit_price == null) {
      const best = cand.contract_price ?? cand.price
      if (best != null) {
        row.unit_price = Number(best)
        if (row.quantity != null) {
          row.total_price = Math.round(Number(row.quantity) * Number(row.unit_price) * 100) / 100
        }
      }
    }
    row.match_confirmed = true
  }

  /** Clear a row's catalog binding (when the user removes the chosen product). */
  function clearBinding(row: MatchableRow): void {
    row.item_name = ''
    row.product_id = null
    row._selectedProduct = null
    row._photo_url = undefined
    row._description = undefined
  }

  return { matching, matchQueries, matchOne, applyCandidate, clearBinding }
}
