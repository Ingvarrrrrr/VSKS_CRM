// useProductSearch.ts — ЕДИНЫЙ механизм серверного поиска каталога товаров
// (ПРАВИЛО №6): страница «Товары» (ProductsView.vue/useProductsData.ts),
// подсказки по имени при создании/правке товара (useProductsForm.ts) и пикер
// товара в закупке (useItemsCatalog.ts) заводят СВОЙ экземпляр этого
// композабла (разные debounce/лимиты/фильтры), но не второй механизм
// запроса — все зовут GET /api/products/page (backend/app/routers/
// products_page.py), ничего не грузят целиком.
//
// Повод (владелец, 26.10.2026): каталог — 54 тыс. строк, вырастет до 250+
// тыс. — GET /api/products/ без ids/limit больше не отдаёт полный список.
//
// Отмена устаревших ответов — ДВА независимых механизма сразу (не одно
// вместо другого): AbortController прерывает сетевой запрос физически,
// счётчик seq отбрасывает ответ, даже если он успел прилететь до того, как
// abort долетел до браузера (гонка), — так же, как и зачем это сделано в
// api.ts для инфлайт-дедупа, но здесь нужна отмена, а не дедуп одного и того
// же запроса. Реализация обоих механизмов — в latestRequest.ts
// (createLatestRequestGuard, ПРАВИЛО №6): это же единое место используют
// InlineProductMatch.vue и ProductMatchReviewDialog.vue для той же задачи на
// других ручках (инлайн-подбор позиции заявки, ручной поиск при импорте) —
// второй раз эту логику не пишем.
import { ref } from 'vue'
import { apiFetch } from '@/api'
import { createLatestRequestGuard } from './latestRequest'
import type { Product } from './productsTypes'

// Минимум символов для запуска поиска товара — ЕДИНОЕ место (ПРАВИЛО №6),
// решение владельца 26.10.2026: короче 3 символов запрос на сервер не
// уходит — каталог 54 тыс.+ строк, поиск по 1-2 буквам почти всегда либо
// ничего не находит, либо отдаёт слишком широкий результат. Все потребители
// (useProductsData.ts, useItemsCatalog.ts::runPickerSearch,
// useProductsForm.ts::nameSearch) берут константу и подсказки отсюда, а не
// копируют число/текст у себя.
export const MIN_SEARCH_CHARS = 3

// Текст подсказки — placeholder поля ДО ввода (всегда виден).
export const SEARCH_PLACEHOLDER = `Введите от ${MIN_SEARCH_CHARS} символов`

/** Подсказка «Ещё N символ(а) для поиска» под полем, когда введено 1..MIN_SEARCH_CHARS-1
    символов (после trim). Пустая строка — когда поле пустое или уже достаточно длинное
    (ничего не показываем). */
export function searchRemainingHint(raw: string): string {
  const len = (raw || '').trim().length
  if (len === 0 || len >= MIN_SEARCH_CHARS) return ''
  const remaining = MIN_SEARCH_CHARS - len
  return `Ещё ${remaining} символ${remaining === 1 ? '' : 'а'} для поиска`
}

/** true, если строка после trim короче MIN_SEARCH_CHARS (0 включительно) —
    общий предикат для решения «считать поиск отсутствующим»/«не слать запрос». */
export function isSearchTooShort(raw: string | undefined | null): boolean {
  return (raw || '').trim().length < MIN_SEARCH_CHARS
}

export interface ProductSearchParams {
  search?: string
  category?: string[]
  productType?: string[]
  isActive?: boolean | null
  feoCategoryId?: number | null
  priceMin?: number | null
  priceMax?: number | null
  staleOnly?: boolean
  sort?: string
  order?: 'asc' | 'desc'
  limit?: number
  offset?: number
}

interface ProductSearchPageOut {
  items: Product[]
  total: number
  total_capped: boolean
}

export interface ProductSearchResult {
  items: Product[]
  total: number
  totalCapped: boolean
}

function buildQuery(params: ProductSearchParams): string {
  const q = new URLSearchParams()
  if (params.search?.trim()) q.set('search', params.search.trim())
  for (const c of params.category || []) q.append('category', c)
  for (const t of params.productType || []) q.append('product_type', t)
  if (params.isActive !== null && params.isActive !== undefined) q.set('is_active', String(params.isActive))
  if (params.feoCategoryId != null) q.set('feo_category_id', String(params.feoCategoryId))
  // Number.isFinite — не только null/undefined (как было), но и NaN/''
  // (владелец, 29.10.2026: '' после стирания в <v-text-field type="number">
  // v-model.number не приводит к null, см. useProductsData.ts::
  // normalizePriceFilter — та же защита здесь ещё раз, на случай другого
  // вызывающего той же ручки, не второй механизм, тот же критерий).
  if (Number.isFinite(params.priceMin)) q.set('price_min', String(params.priceMin))
  if (Number.isFinite(params.priceMax)) q.set('price_max', String(params.priceMax))
  if (params.staleOnly) q.set('stale_only', 'true')
  if (params.sort) q.set('sort', params.sort)
  if (params.order) q.set('order', params.order)
  q.set('limit', String(params.limit ?? 50))
  q.set('offset', String(params.offset ?? 0))
  return q.toString()
}

export function useProductSearch(opts: { debounceMs?: number } = {}) {
  const debounceMs = opts.debounceMs ?? 300

  const items = ref<Product[]>([])
  const total = ref(0)
  const totalCapped = ref(false)
  const loading = ref(false)

  const guard = createLatestRequestGuard()
  let timer: ReturnType<typeof setTimeout> | null = null

  async function run(params: ProductSearchParams): Promise<ProductSearchResult | null> {
    if (timer) { clearTimeout(timer); timer = null }
    const { signal, isStale } = guard.begin()
    loading.value = true
    try {
      const data = await apiFetch<ProductSearchPageOut>(
        `/products/page?${buildQuery(params)}`,
        { signal },
      )
      // Ответ мог прилететь ПОСЛЕ более нового запроса (гонка, abort ещё не
      // долетел) — отбрасываем его счётчиком, а не только AbortController'ом.
      if (isStale()) return null
      items.value = data.items
      total.value = data.total
      totalCapped.value = data.total_capped
      return { items: data.items, total: data.total, totalCapped: data.total_capped }
    } catch (e: any) {
      if (e?.name === 'AbortError') return null
      throw e
    } finally {
      if (!isStale()) loading.value = false
    }
  }

  /** Немедленный запрос (клик по фильтру/странице/сортировке) — отменяет
      предыдущий незавершённый запрос/debounce-таймер. */
  function load(params: ProductSearchParams): Promise<ProductSearchResult | null> {
    return run(params)
  }

  /** Отложенный запрос (ввод в текстовое поле поиска) — debounceMs мс простоя
      ввода. Повторный вызов до срабатывания сдвигает таймер, не копит их. */
  function loadDebounced(params: ProductSearchParams): void {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => { void run(params) }, debounceMs)
  }

  return { items, total, totalCapped, loading, load, loadDebounced }
}
