// productsTypes.ts — общие типы каталога товаров. Дословный перенос из ProductsView.vue.
import type { PriceFreshness } from '@/composables/usePriceFreshness'

export interface PriceLink { url: string; price: number | null }

export interface Product {
  id: number; name: string; category?: string; product_type?: string; item_kind?: string
  unit?: string | null  // Единица измерения (владелец, 2026-09-01)
  price?: number; description?: string; description_44fz?: string; photo_url?: string
  photo_link?: string; clarification_link?: string
  is_active: boolean; is_reusable?: boolean; feo_category_id?: number
  price_links?: PriceLink[]
  contract_price?: number; contract_number?: string; contract_date?: string; contract_org_id?: number; price_shared?: boolean
  tz_verified_at?: string; tz_verified_by?: string
  tz_44fz_verified_at?: string; tz_44fz_verified_by?: string
  has_photo?: boolean; photo_size?: number; photo_mime?: string
  country_origin?: string
  // Владелец, сессия 2026-08-29: «показывать дату последней актуализации цены,
  // устаревшее — подсвечивать». Backend считает всю TTL/FX-логику (см. ProductOut).
  price_updated_at?: string | null
  price_source?: string | null
  price_source_ref?: string | null
  price_source_contractor_id?: number | null
  price_ttl_days?: number | null
  price_freshness?: PriceFreshness | null
}

export interface PriceHistoryEntry {
  id: number; price: number; source: string; source_ref?: string | null
  contractor_id?: number | null; collected_at?: string | null; note?: string | null
  created_by?: string | null; created_at?: string
}

export interface DupProduct { id: number; name: string; category?: string; product_type?: string; has_photo?: boolean; has_description?: boolean; score?: number; match?: 'exact' | 'fuzzy' }
export interface DupGroup { winner: DupProduct; duplicates: DupProduct[] }

// «РФ» — актуальный формат; «Россия» остаётся у старых записей до миграции/повторного сохранения.
export const DOMESTIC_COUNTRY_VALUES = new Set(['РФ', 'Россия'])
export function isDomesticCountry(v?: string | null): boolean {
  return !!v && DOMESTIC_COUNTRY_VALUES.has(v.trim())
}

// Hash-based color for any free-text type
const PALETTE = ['blue', 'teal', 'orange', 'purple', 'pink', 'green', 'indigo', 'cyan', 'deep-orange']
export function typeColor(t: string): string {
  const h = Math.abs([...t].reduce((acc, c) => acc * 31 + c.charCodeAt(0), 0))
  return PALETTE[h % PALETTE.length]
}

export function formatDate(d: string | null) {
  if (!d) return ''
  const dt = new Date(d)
  return dt.toLocaleDateString('ru-RU') + ' ' + dt.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
}
