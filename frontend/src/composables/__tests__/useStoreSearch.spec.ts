// Тесты useStoreSearch.ts (живой поиск товара в магазинах, этап 1,
// владелец, 28.10.2026) — fetchStoreSearch (api.ts) подменён: сеть сюда не
// ходит, проверяем только состояние композабла (loading/error/offers/stores).
import { describe, it, expect, vi, beforeEach } from 'vitest'

const fetchStoreSearchMock = vi.fn()

vi.mock('@/api', () => ({
  fetchStoreSearch: (...args: unknown[]) => fetchStoreSearchMock(...args),
}))

import { useStoreSearch } from '@/composables/products/useStoreSearch'

beforeEach(() => {
  fetchStoreSearchMock.mockReset()
})

describe('useStoreSearch', () => {
  it('пустой запрос не уходит на сервер — выставляет текстовую ошибку', async () => {
    const api = useStoreSearch()
    await api.search('   ')
    expect(fetchStoreSearchMock).not.toHaveBeenCalled()
    expect(api.error.value).toBeTruthy()
    expect(api.hasSearched.value).toBe(false)
  })

  it('успешный ответ заполняет offers/stores/querySent', async () => {
    fetchStoreSearchMock.mockResolvedValue({
      query_sent: 'дрель',
      offers: [{ store_key: 'kuvalda', store_name: 'Кувалда.ру', name: 'Дрель', price: 1000, url: 'https://x' }],
      stores: [{ key: 'kuvalda', name: 'Кувалда.ру', status: 'ok', count: 1, ms: 120 }],
    })

    const api = useStoreSearch()
    await api.search('дрель')

    expect(api.offers.value).toHaveLength(1)
    expect(api.stores.value).toHaveLength(1)
    expect(api.querySent.value).toBe('дрель')
    expect(api.loading.value).toBe(false)
    expect(api.error.value).toBeNull()
    expect(api.hasSearched.value).toBe(true)
  })

  it('ошибка сети — текст причины в error, offers очищены', async () => {
    fetchStoreSearchMock.mockRejectedValue(new Error('Сеть недоступна'))

    const api = useStoreSearch()
    await api.search('дрель')

    expect(api.error.value).toContain('Сеть недоступна')
    expect(api.offers.value).toEqual([])
  })

  it('reset() возвращает композабл в исходное состояние', async () => {
    fetchStoreSearchMock.mockResolvedValue({
      query_sent: 'дрель', offers: [], stores: [],
    })
    const api = useStoreSearch()
    await api.search('дрель')
    expect(api.hasSearched.value).toBe(true)

    api.reset()
    expect(api.hasSearched.value).toBe(false)
    expect(api.offers.value).toEqual([])
    expect(api.error.value).toBeNull()
  })
})
