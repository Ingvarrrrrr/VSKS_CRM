// useItemMatching — encapsulates catalog product matching for editor rows.
// Extracted from PurchaseItemsEditor.vue (monolith refactor) so per-row inline
// matching, the repick dialog, and batch import review can share one source of
// truth for: the /products/match call, the MatchCandidate type, and the
// mutation that applies a chosen candidate to a row.
import { ref } from 'vue'
import { apiFetch } from '@/api'
import type { PriceFreshness } from '@/composables/usePriceFreshness'

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
  // Price actualization provenance (POST /products/match candidates) — see
  // usePriceFreshness.ts, the single source of truth for displaying these.
  price_updated_at?: string | null
  price_source?: string | null
  price_source_ref?: string | null
  price_freshness?: PriceFreshness | null
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
  // UI-only price actualization stamp (дата + источник) — см. usePriceFreshness.ts.
  // Служебное поле, вырезается перед сохранением (как _selectedProduct и т.п.).
  _price_meta?: {
    price_updated_at?: string | null
    price_source?: string | null
    price_source_ref?: string | null
    price_freshness?: PriceFreshness | null
  } | null
  // Владелец, 26.10.2026 (баг «цена не меняется при смене товара»): признак
  // «цена сейчас подставлена из каталога, а не введена руками». ЕДИНЫЙ флаг,
  // который решает, трогать ли unit_price/total_price при смене/очистке
  // товара — см. applyCandidate() и resetPriceIfFromCatalog() ниже, это
  // единственное место, где считается это решение (ПРАВИЛО №6). Служебное
  // поле строки — вырезается перед сохранением тем же механизмом, что
  // _description и т.п. (useWishForm.ts/CreateOrderView.vue).
  price_from_catalog?: boolean
  [k: string]: any
}

/**
 * Единственное место, решающее, чистить ли цену строки при снятии привязки
 * к товару (крестик, очистка, выбор "не из каталога"). Цена чистится ТОЛЬКО
 * если она была подставлена из каталога (price_from_catalog === true) —
 * цену, введённую руками, очистка товара не трогает (владелец, 26.10.2026).
 * Вынесена из useItemMatching() наружу — используется и там (clearBinding),
 * и в useItemsTable.ts::clearItem, без собственного состояния композабла.
 */
export function resetPriceIfFromCatalog(row: MatchableRow): void {
  // price_from_catalog === false — ЕДИНСТВЕННОЕ явное свидетельство, что цену
  // в этой строке правили руками (ставится только в numberFormat.ts::
  // moneyFieldOnInput на ручной ввод поля «Цена ед.»). Любое другое значение
  // (true — цена только что подставлена из каталога; undefined — строка
  // пришла с сервера/создана без правок цены в этой сессии, флаг не
  // персистится) считается «цена не защищена» и чистится вместе с товаром.
  if (row.price_from_catalog !== false) {
    row.unit_price = null
    row.total_price = null
  }
  row.price_from_catalog = false
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
  async function matchQueries(queries: string[], limit?: number, prefix?: boolean, signal?: AbortSignal): Promise<MatchResult[]> {
    if (!queries.length) return []
    matching.value = true
    try {
      const body: { queries: string[]; limit?: number; prefix?: boolean } = { queries }
      if (limit != null) body.limit = limit
      if (prefix != null) body.prefix = prefix
      const data = await apiFetch<{ results: MatchResult[] }>('/products/match', {
        method: 'POST',
        body,
        signal,
      })
      return data?.results ?? []
    } finally {
      matching.value = false
    }
  }

  /** Convenience: match a single query, return its candidate list (status badge too).
      `signal` (опционально) — отмена устаревшего запроса, см. latestRequest.ts
      (ПРАВИЛО №6); вызывающий, передавший signal, сам ловит AbortError. */
  async function matchOne(query: string, limit?: number, prefix?: boolean, signal?: AbortSignal): Promise<MatchResult | null> {
    const q = (query || '').trim()
    if (!q) return null
    const results = await matchQueries([q], limit, prefix, signal)
    return results[0] ?? null
  }

  /**
   * Apply a chosen catalog candidate to a row in place. Mirrors the historical
   * onItemProductSelect / onRepickPick behaviour:
   *  - sets product_id, item_name, _selectedProduct, _photo_url, _description
   *  - sets item_type from the catalog candidate whenever the catalog has one
   *    (owner, 2026-10-01: an explicit product pick is the single source of
   *    truth for item_type here — a row defaults to 'товар' via
   *    useItemsTable.addItem, so "only if row has none yet" never actually
   *    applied the catalog's "услуга"/"работа"). All callers of this function
   *    are explicit user picks (dialog select, inline match, repick) — never
   *    silent/automatic matching, so overriding is safe. Item-form rows
   *    (accommodation/food/transport) still end up 'услуга' regardless, via
   *    the separate applyItemAmounts()/computeItemTotal() recompute keyed on
   *    itemForm (utils/itemAmounts.ts) — not duplicated here (ПРАВИЛО №6).
   *  - цена (владелец, 26.10.2026, баг «выбрал бензопилу → выбрал зубную пасту
   *    → цена осталась от бензопилы»). Единое правило через флаг
   *    `price_from_catalog` (см. тип MatchableRow выше и resetPriceIfFromCatalog
   *    ниже — та же пара решает во ВСЕХ путях: инлайн-подбор, пикер-диалог,
   *    очистка):
   *      · from_plan → цену НЕ трогаем (план закупок всегда главнее, как раньше);
   *      · тот же product_id, что уже стоял в строке (повторный выбор того же
   *        товара) → цену НЕ трогаем, даже если пользователь её поправил руками;
   *      · цена в строке НЕ подставлена из каталога (пуста, либо введена
   *        руками — price_from_catalog не true) → подставляем цену нового
   *        товара (contract_price ?? price), включая null, если у товара цены
   *        нет. Так закрывается и «первичный выбор в пустую строку» (цены не
   *        было — подставится), и «цену правили руками» (мануальная цена не
   *        затирается при смене товара) ОДНИМ условием;
   *      · цена в строке УЖЕ была подставлена из каталога (price_from_catalog
   *        true, от предыдущего товара) → при смене товара синхронизируется с
   *        новым (включая очистку в null, если у нового товара цены нет).
   *    total_price пересчитывается по той же формуле qty × unit_price либо
   *    тоже становится null (тот же приём, что useItemsTotals.ts::calcItemTotal
   *    — Правило №6, вторая конвенция не заводится).
   *  - marks match_confirmed = true
   */
  function applyCandidate(row: MatchableRow, cand: MatchCandidate): void {
    const prevProductId = row.product_id
    row.product_id = cand.product_id
    row.item_name = cand.name || row.item_name
    row._selectedProduct = cand
    row._photo_url = cand.photo_url ?? undefined
    row._description = cand.description ?? undefined
    // Владелец, 2026-08-29: штамп даты/источника актуализации цены едет вместе
    // с товаром, откуда бы он ни попал в строку (пикер, инлайн-матчинг, репик).
    row._price_meta = {
      price_updated_at: cand.price_updated_at ?? null,
      price_source: cand.price_source ?? null,
      price_source_ref: cand.price_source_ref ?? null,
      price_freshness: cand.price_freshness ?? null,
    }
    if (cand.item_type) row.item_type = cand.item_type
    // Владелец (14.10.2026, решение (в)): у позиции из Плана закупок цена
    // ВСЕГДА плановая — выбор товара каталога её не перебивает, даже если
    // плановая цена по какой-то причине пуста (не подставляем цену каталога).
    const isSameProduct = prevProductId != null && prevProductId === cand.product_id
    // Защищена только явно отмеченная ручная правка (price_from_catalog===false
    // — см. resetPriceIfFromCatalog выше про остальные значения флага).
    const manualPrice = row.unit_price != null && row.price_from_catalog === false
    if (!(row as any).from_plan && !isSameProduct && !manualPrice) {
      const best = cand.contract_price ?? cand.price
      row.unit_price = best != null ? Number(best) : null
      if (row.unit_price != null && row.quantity != null) {
        row.total_price = Math.round(Number(row.quantity) * Number(row.unit_price) * 100) / 100
      } else {
        row.total_price = null
      }
      row.price_from_catalog = true
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
    row._price_meta = null
    resetPriceIfFromCatalog(row)
  }

  return { matching, matchQueries, matchOne, applyCandidate, clearBinding, resetPriceIfFromCatalog }
}
