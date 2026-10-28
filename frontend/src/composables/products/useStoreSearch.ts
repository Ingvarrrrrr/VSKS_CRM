// useStoreSearch.ts — живой поиск товара в магазинах (этап 1, владелец,
// 28.10.2026). ОДИН композабл (ПРАВИЛО №6) на оба места использования —
// окно выбора товара (ProductPickerDialog.vue) и страница «Товары»
// (ProductsView.vue): запрос в магазины дорогой (несколько секунд, сетевые
// запросы на внешние сайты), второй такой же механизм не заводим.
//
// В нашу базу ничего не пишет (этап 2 — отдельная задача «взять
// предложение в закупку»): этот композабл только запрашивает и показывает.
import { ref } from 'vue'
import { fetchStoreSearch, type StoreOfferDTO, type StoreStatusDTO } from '@/api'

export function useStoreSearch() {
  const offers = ref<StoreOfferDTO[]>([])
  const stores = ref<StoreStatusDTO[]>([])
  const querySent = ref('')
  const loading = ref(false)
  const error = ref<string | null>(null)
  const hasSearched = ref(false)

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
  }

  return { offers, stores, querySent, loading, error, hasSearched, search, reset }
}
