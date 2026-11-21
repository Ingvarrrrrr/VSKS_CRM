import { ref, type Ref } from 'vue'
import { fetchStoreSearch, fetchStoreTake, type StoreOfferDTO, type StoreStatusDTO } from '@/api'

export interface PlannedStoreSummary {
  count: number
  minPrice: number
  offers: StoreOfferDTO[]
  stores: StoreStatusDTO[]
}

const cache = new Map<string, PlannedStoreSummary>()
const inFlight = new Set<string>()
const queue: string[] = []
let isProcessing = false

async function processQueue() {
  if (isProcessing) return
  isProcessing = true
  while (queue.length > 0) {
    const rawName = queue.shift()!
    const query = rawName.trim()
    if (!query || cache.has(query) || inFlight.has(query)) {
      continue
    }
    inFlight.add(query)
    try {
      const res = await fetchStoreSearch(query)
      if (res && res.offers && res.offers.length > 0) {
        const prices = res.offers
          .map(o => Number(o.price))
          .filter(p => !isNaN(p) && p > 0)
        const minPrice = prices.length > 0 ? Math.min(...prices) : 0
        cache.set(query, {
          count: res.offers.length,
          minPrice,
          offers: res.offers,
          stores: res.stores || [],
        })
      } else {
        cache.set(query, {
          count: 0,
          minPrice: 0,
          offers: [],
          stores: res?.stores || [],
        })
      }
    } catch {
      cache.set(query, {
        count: 0,
        minPrice: 0,
        offers: [],
        stores: [],
      })
    } finally {
      inFlight.delete(query)
    }
    // Rate limit delay between background store queries
    await new Promise(resolve => setTimeout(resolve, 800))
  }
  isProcessing = false
}

export function usePlannedStoreOffers() {
  const takingUrl = ref<string | null>(null)
  const takeError = ref<string | null>(null)

  function requestOffers(name: string): Ref<PlannedStoreSummary | null> {
    const result = ref<PlannedStoreSummary | null>(null)
    const query = (name || '').trim()
    if (!query || query.length < 3) {
      return result
    }
    if (cache.has(query)) {
      result.value = cache.get(query) || null
      return result
    }
    if (!queue.includes(query) && !inFlight.has(query)) {
      queue.push(query)
      void processQueue()
    }
    // Poll cache until resolved or queue processed
    const interval = setInterval(() => {
      if (cache.has(query)) {
        result.value = cache.get(query) || null
        clearInterval(interval)
      }
    }, 1000)
    // Clear interval after 60 seconds
    setTimeout(() => clearInterval(interval), 60000)

    return result
  }

  async function take(offer: StoreOfferDTO, rawQuery: string): Promise<any> {
    takingUrl.value = offer.url
    takeError.value = null
    try {
      return await fetchStoreTake(offer.store_key, offer.url, rawQuery)
    } catch (e: any) {
      takeError.value = e?.payload?.message || e?.message || 'Не удалось взять товар в каталог'
      throw e
    } finally {
      takingUrl.value = null
    }
  }

  return {
    requestOffers,
    take,
    takingUrl,
    takeError,
  }
}
