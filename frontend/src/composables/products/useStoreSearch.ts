// useStoreSearch.ts — живой поиск товара в магазинах (этап 1, владелец,
// 28.10.2026) + «Взять» в каталог (этап 2, владелец, 29.10.2026). ОДИН
// композабл (ПРАВИЛО №6) на оба места использования — окно выбора товара
// (ProductPickerDialog.vue) и страница «Товары» (ProductsView.vue): запрос в
// магазины дорогой (несколько секунд, сетевые запросы на внешние сайты),
// второй такой же механизм не заводим; takeOffer() — тоже одна функция на
// оба экрана (StoreOffersPanel.vue эмитит 'take', вызывающий код решает, что
// сделать с вернувшимся товаром).
import { ref } from 'vue'
import { fetchStoreSearch, fetchStoreTake, type StoreOfferDTO, type StoreStatusDTO } from '@/api'

export function useStoreSearch() {
  const offers = ref<StoreOfferDTO[]>([])
  const stores = ref<StoreStatusDTO[]>([])
  const querySent = ref('')
  const loading = ref(false)
  const error = ref<string | null>(null)
  const hasSearched = ref(false)
  // url предложения, которое сейчас берётся (POST /store-take в полёте) —
  // StoreOffersPanel.vue рисует спиннер ТОЛЬКО на этой карточке, не на всём
  // списке. null — ничего не берётся.
  const takingUrl = ref<string | null>(null)
  const takeError = ref<string | null>(null)
  // Сырой текст поиска (ДО очистки clean_query на бэкенде) — именно он ушёл
  // в GET /store-search и под ним лежит кэш предложений; querySent — это уже
  // ОЧИЩЕННЫЙ query_sent из ответа (для показа человеку), повторный
  // clean_query() над уже очищенной строкой на бэкенде (find_cached_offer)
  // рискует разойтись с ключом кэша — поэтому takeOffer() ниже шлёт именно
  // исходный текст, не querySent.
  let lastRawQuery = ''

  let abortController: AbortController | null = null

  async function search(q: string, storeKeys?: string[]): Promise<void> {
    const trimmed = (q || '').trim()
    if (!trimmed) {
      error.value = 'Введите текст для поиска в магазинах'
      return
    }
    if (abortController) abortController.abort()
    abortController = new AbortController()
    loading.value = true
    error.value = null
    hasSearched.value = true
    lastRawQuery = trimmed
    try {
      const data = await fetchStoreSearch(trimmed, storeKeys, abortController.signal)
      offers.value = data.offers
      stores.value = data.stores
      querySent.value = data.query_sent
    } catch (e: any) {
      if (e?.name === 'AbortError') return
      // Не глотаем ошибку общим snackbar'ом (ПРАВИЛО/память проекта) —
      // текст с причиной рисует сам StoreOffersPanel.vue из error.value.
      error.value = e?.payload?.message || e?.message || 'Не удалось получить предложения магазинов'
      offers.value = []
      stores.value = []
    } finally {
      loading.value = false
    }
  }

  function reset(): void {
    if (abortController) abortController.abort()
    offers.value = []
    stores.value = []
    querySent.value = ''
    error.value = null
    hasSearched.value = false
    takingUrl.value = null
    takeError.value = null
  }

  /** «Взять» предложение в каталог — POST /api/products/store-take (ПРАВИЛО
   * №8 п.4: цену/название/фото сервер берёт сам, здесь только ключ
   * предложения). Возвращает товар каталога (та же форма, что выбор из
   * нашей базы) — вызывающий код сам решает, что с ним сделать (подставить
   * в строку/открыть карточку), второй путь выбора не заводим. Бросает
   * ошибку дальше (с текстом в takeError.value) — вызывающий код сам решает,
   * показывать ли тост, т.к. контекст («страница Товары» vs «пикер в
   * заявке») разный. */
  async function takeOffer(offer: StoreOfferDTO): Promise<any> {
    takingUrl.value = offer.url
    takeError.value = null
    try {
      return await fetchStoreTake(offer.store_key, offer.url, lastRawQuery)
    } catch (e: any) {
      takeError.value = e?.payload?.message || e?.message || 'Не удалось взять товар в каталог'
      throw e
    } finally {
      takingUrl.value = null
    }
  }

  return {
    offers, stores, querySent, loading, error, hasSearched, search, reset,
    takingUrl, takeError, takeOffer,
  }
}
