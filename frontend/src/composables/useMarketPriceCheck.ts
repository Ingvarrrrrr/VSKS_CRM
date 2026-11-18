import { reactive } from 'vue'
import { apiFetch } from '@/api'
import { batchLabelFromQuantity } from '@/utils/avgPrice'

export interface MarketPriceOffer {
  store_key: string
  store_name: string
  price: number
  url?: string | null
  is_live: boolean
}

export interface MarketPriceCheckResult {
  product_id: number | null
  product_name: string | null
  catalog_price: number | null
  live_refreshed: boolean
  retail_price: number | null
  retail_min: number | null
  retail_max: number | null
  retail_count: number
  volume_price: number | null
  volume_batch: string
  volume_basis_count: number
  volume_source: string
  volume_note: string
  offers: MarketPriceOffer[]
}

export interface MarketStatusInfo {
  status: 'in_market' | 'above_market' | 'below_market' | 'none'
  diffPct: number | null
  label: string
  color: string
}

const cache = reactive<Record<string, MarketPriceCheckResult>>({})

function cacheKey(productId: number | null | undefined, itemName: string | null | undefined, quantity: number | null | undefined): string {
  const idPart = productId != null ? `p:${productId}` : `n:${(itemName || '').trim().toLowerCase()}`
  const batchPart = batchLabelFromQuantity(quantity) || '1-9'
  return `${idPart}:${batchPart}`
}

export function isSubsidyPlanItem(item: any, planRow?: any): boolean {
  return Boolean(item?.from_plan || item?.feo_planned_item_id != null || planRow)
}

export function applyMarketPriceToItem(item: any, price: number): void {
  if (!item || !price || price <= 0) return
  item.unit_price = Math.round(Number(price) * 100) / 100
  item._unit_price_display = undefined
  item.price_from_catalog = false
  if (item.quantity != null) {
    item.total_price = Math.round(Number(item.quantity) * item.unit_price * 100) / 100
  }
}

export function evaluateMarketStatus(
  unitPrice: number | null | undefined,
  marketData: MarketPriceCheckResult | null | undefined,
): MarketStatusInfo {
  if (!unitPrice || unitPrice <= 0 || !marketData) {
    return { status: 'none', diffPct: null, label: '', color: 'grey' }
  }
  const ref = marketData.volume_price ?? marketData.retail_price
  if (!ref || ref <= 0) {
    return { status: 'none', diffPct: null, label: '', color: 'grey' }
  }
  const diffPct = Math.round(((Number(unitPrice) - ref) / ref) * 100)
  const sign = diffPct > 0 ? '+' : ''
  if (Math.abs(diffPct) <= 10) {
    return { status: 'in_market', diffPct, label: `В рынке (${sign}${diffPct}%)`, color: 'success' }
  }
  if (diffPct > 10) {
    return { status: 'above_market', diffPct, label: `Выше рынка (+${diffPct}%)`, color: 'warning' }
  }
  return { status: 'below_market', diffPct, label: `Ниже рынка (${diffPct}%)`, color: 'info' }
}

export function useMarketPriceCheck() {
  async function checkMarketPrice(params: {
    productId?: number | null
    itemName?: string | null
    quantity?: number | null
    unit?: string | null
    refreshLive?: boolean
    background?: boolean
  }): Promise<MarketPriceCheckResult | null> {
    const key = cacheKey(params.productId, params.itemName, params.quantity)
    if (!params.refreshLive && cache[key]) {
      return cache[key]
    }
    if (params.productId == null && !(params.itemName || '').trim()) {
      return null
    }
    const res = await apiFetch<MarketPriceCheckResult>('/products/market-price-check', {
      method: 'POST',
      body: JSON.stringify({
        product_id: params.productId ?? null,
        item_name: params.itemName ? params.itemName.trim() : null,
        quantity: params.quantity && params.quantity > 0 ? Number(params.quantity) : null,
        unit: params.unit || null,
        refresh_live: Boolean(params.refreshLive),
      }),
      background: params.background ?? !params.refreshLive,
      suppressErrorDialog: true,
    })
    if (res) {
      cache[key] = res
    }
    return res
  }

  function cachedFor(params: {
    productId?: number | null
    itemName?: string | null
    quantity?: number | null
  }): MarketPriceCheckResult | null {
    return cache[cacheKey(params.productId, params.itemName, params.quantity)] ?? null
  }

  return { checkMarketPrice, cachedFor }
}
