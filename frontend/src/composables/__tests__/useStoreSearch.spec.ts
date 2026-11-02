// Тесты useStoreSearch.ts (живой поиск товара в магазинах, этап 1,
// владелец, 28.10.2026 + «Взять», этап 2, 29.10.2026) — fetchStoreSearch/
// fetchStoreTake (api.ts) подменены: сеть сюда не ходит, проверяем только
// состояние композабла (loading/error/offers/stores/takingUrl/takeError).
import { describe, it, expect, vi, beforeEach } from 'vitest'

const fetchStoreSearchMock = vi.fn()
const fetchStoreTakeMock = vi.fn()

vi.mock('@/api', () => ({
  fetchStoreSearch: (...args: unknown[]) => fetchStoreSearchMock(...args),
  fetchStoreTake: (...args: unknown[]) => fetchStoreTakeMock(...args),
}))

import { useStoreSearch } from '@/composables/products/useStoreSearch'

beforeEach(() => {
  fetchStoreSearchMock.mockReset()
  fetchStoreTakeMock.mockReset()
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

  // ── takeOffer (этап 2, «Взять», владелец 29.10.2026) ──────────────────────

  it('takeOffer — шлёт store_key/url и ИСХОДНЫЙ (не очищенный) текст поиска', async () => {
    fetchStoreSearchMock.mockResolvedValue({ query_sent: 'Makita 125', offers: [], stores: [] })
    fetchStoreTakeMock.mockResolvedValue({ id: 1, name: 'Болгарка Makita 125', created: true })

    const api = useStoreSearch()
    await api.search('болгарка макита 125 с регулировкой')

    const offer = { store_key: 'kuvalda', store_name: 'Кувалда.ру', name: 'Болгарка', price: 1500, url: 'https://x/1' } as any
    const product = await api.takeOffer(offer)

    expect(fetchStoreTakeMock).toHaveBeenCalledWith('kuvalda', 'https://x/1', 'болгарка макита 125 с регулировкой')
    expect(product).toEqual({ id: 1, name: 'Болгарка Makita 125', created: true })
    expect(api.takingUrl.value).toBeNull()
    expect(api.takeError.value).toBeNull()
  })

  it('takeOffer — выставляет takingUrl на время запроса', async () => {
    let resolveTake: (v: unknown) => void = () => {}
    fetchStoreTakeMock.mockImplementation(() => new Promise(r => { resolveTake = r }))

    const api = useStoreSearch()
    const offer = { store_key: 'kuvalda', store_name: 'Кувалда.ру', name: 'Болгарка', price: 1500, url: 'https://x/1' } as any
    const promise = api.takeOffer(offer)
    expect(api.takingUrl.value).toBe('https://x/1')

    resolveTake({ id: 1, created: true })
    await promise
    expect(api.takingUrl.value).toBeNull()
  })

  it('takeOffer — ошибка бэка кладётся в takeError текстом и пробрасывается дальше', async () => {
    const err: any = new Error('Предложение устарело, повторите поиск')
    err.payload = { message: 'Предложение устарело, повторите поиск' }
    fetchStoreTakeMock.mockRejectedValue(err)

    const api = useStoreSearch()
    const offer = { store_key: 'kuvalda', store_name: 'Кувалда.ру', name: 'Болгарка', price: 1500, url: 'https://x/1' } as any

    await expect(api.takeOffer(offer)).rejects.toThrow()
    expect(api.takeError.value).toBe('Предложение устарело, повторите поиск')
    expect(api.takingUrl.value).toBeNull()
  })
})
