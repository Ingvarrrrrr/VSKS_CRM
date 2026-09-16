// productsTypes.ts — общие типы каталога товаров. Дословный перенос из ProductsView.vue.
import type { PriceFreshness } from '@/composables/usePriceFreshness'

export interface PriceLink { url: string; price: number | null }

// Справочник категорий закупки (2026-09-16): отдельный от свободнотекстовой
// «Категории» мультивыбор — по нему товар выставляется в закупку. Один
// источник CRUD — composables/products/usePurchaseCategories.ts (Правило №6):
// и мультивыбор в карточке товара, и диалог управления справочником читают/
// пишут один и тот же модульный список, второй copy состояния не заводим.
export interface PurchaseCategory { id: number; name: string; sort_order: number; is_active: boolean }

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
  // Категории закупки (2026-09-16) — покупается create/update как id[], отдаётся
  // в Out развёрнутым {id,name}[] (см. решение владельца от 2026-09-16, п.1).
  purchase_category_ids?: number[]
  purchase_categories?: { id: number; name: string }[]
  // Средняя цена за 60 дней — считается бэкендом из price_history (Правило №6:
  // единственный источник; фронт не пересчитывает сам). basis — сколько цен
  // легло в основу, stale — все они старше окна.
  avg_price?: number | null
  avg_price_basis?: number
  avg_price_stale?: boolean
}

export interface PriceHistoryEntry {
  id: number; price: number; source: string; source_ref?: string | null
  contractor_id?: number | null; contractor_name?: string | null
  collected_at?: string | null; note?: string | null
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

// Универсальное русское склонение по числу (1 / 2-4 / 5+, с учётом 11-14) —
// тот же mod10/mod100-приём, что и в utils/relativeTime.ts (там не
// экспортирован — см. аналогичный локальный dup в FeoCategoryDeleteDialog.vue::
// plannedItemsCountWord). Экспортируем один раз для каталога товаров: и блок
// «Средняя цена», и колонки таблицы/карточек читают отсюда (Правило №6).
export function pluralRu(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return one
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return few
  return many
}

// «На основании …» требует родительного падежа: «на основании 1 цены»,
// «на основании 2 цен», «на основании 5 цен» (родительный мн. числа у «цена»
// совпадает для few/many — проверено на примерах владельца из ТЗ).
export function priceCountGenitive(n: number): string {
  return pluralRu(n, 'цены', 'цен', 'цен')
}

export function avgPriceBasisText(n: number): string {
  return `${n} ${priceCountGenitive(n)}`
}

// Человеческая подпись источника записи в истории цен — единственное место,
// где текст решается (Правило №6): таблица истории, тултип «Средняя» в
// каталоге — все читают отсюда, не дублируют switch/case у себя.
const PRICE_SOURCE_LABELS: Record<string, string> = {
  contract: 'Договор', kp: 'КП', import: 'Импорт', monitoring: 'Мониторинг', manual: 'Вручную',
}
export function priceSourceLabel(source: string, sourceRef?: string | null): string {
  const base = PRICE_SOURCE_LABELS[source] || source
  if (!sourceRef) return base
  if (source === 'contract') return `${base} № ${sourceRef}`
  if (source === 'import') return `${base}: ${sourceRef}`
  return base
}
