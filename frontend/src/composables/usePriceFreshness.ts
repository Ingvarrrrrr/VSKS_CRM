// usePriceFreshness — single source of truth for displaying product price
// actualization/freshness (владелец, сессия 2026-08-29: «цена может быть
// неактуальна, надо показывать дату последней актуализации + подсвечивать
// устаревшую»). Backend (see ProductOut.price_freshness) computes ALL
// TTL/FX/category logic; this composable only formats/renders what the
// backend already decided — no business logic duplicated here.

export interface PriceFreshness {
  is_stale: boolean
  age_days: number | null
  ttl_days: number          // эффективный срок с учётом курса
  base_ttl_days: number     // срок по правилу категории
  reason: 'ok' | 'never' | 'expired' | 'fx'
  fx_change_pct: number | null
  label: string
}

export type PriceSource = 'contract' | 'kp' | 'manual' | 'import' | 'monitoring'

export const PRICE_SOURCE_LABELS: Record<string, string> = {
  contract: 'договор',
  kp: 'КП',
  manual: 'вручную',
  import: 'импорт',
  monitoring: 'мониторинг цен',
}

/** Global CSS class (defined in styles/gala.css) — единая подсветка устаревшей
 * цены во всех местах (каталог, позиции заявки/закупки), а не per-component. */
export const PRICE_STALE_CLASS = 'price-freshness-stale'

/** Shared shape carried on editor rows (`_price_meta`) — mirrors the relevant
 * subset of ProductOut so PurchaseItemsEditor / ItemsTable* / useItemMatching
 * can pass price provenance through a row without depending on the full
 * catalog Product type. */
export interface PriceMeta {
  price_updated_at?: string | null
  price_source?: string | null
  price_source_ref?: string | null
  price_freshness?: PriceFreshness | null
}

function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n)
}

/** 'YYYY-MM-DDTHH:mm:ss' → '14.06.2026'. null/invalid → null. */
export function formatDateDDMMYYYY(iso?: string | null): string | null {
  if (!iso) return null
  const d = new Date(iso)
  if (isNaN(d.getTime())) return null
  return `${pad2(d.getDate())}.${pad2(d.getMonth() + 1)}.${d.getFullYear()}`
}

/**
 * 'от 14.06.2026 · договор №123-ОК' — дата актуализации + источник.
 * Без даты → 'дата не указана' (владелец, 2026-08-29: нейтральная подпись,
 * серым, не подсветка — см. reason='never' в price_freshness.py).
 */
export function formatPriceStamp(
  updatedAt?: string | null,
  source?: string | null,
  ref?: string | null,
): string {
  const dateStr = formatDateDDMMYYYY(updatedAt)
  if (!dateStr) return 'дата не указана'
  let out = `от ${dateStr}`
  const label = source ? (PRICE_SOURCE_LABELS[source] || source) : null
  if (label && ref) {
    // Не дублируем «№», если ref уже содержит собственный номер ("Запрос КП №7").
    out += ` · ${label} ${ref.includes('№') ? ref : '№' + ref}`
  } else if (label) {
    out += ` · ${label}`
  } else if (ref) {
    out += ` · ${ref}`
  }
  return out
}

/** Vuetify color name for stale highlighting, undefined когда цена актуальна
 * ИЛИ дата актуализации не указана (reason='never' — backend уже отдаёт
 * is_stale=false для него, владелец 2026-08-29: «дата неизвесна» — серым). */
export function freshnessColor(f?: PriceFreshness | null): string | undefined {
  return f?.is_stale ? 'warning' : undefined
}

/** MDI icon name for stale highlighting, undefined когда цена актуальна
 * ИЛИ reason='never' (см. freshnessColor). */
export function freshnessIcon(f?: PriceFreshness | null): string | undefined {
  return f?.is_stale ? 'mdi-alert-outline' : undefined
}

/**
 * Готовый текст тултипа: backend (см. price_freshness.py _label(), владелец
 * 2026-08-30) уже включает примечание про курс доллара прямо в label —
 * и для reason='fx', и для reason='ok' с курсовым сдвигом ≥10%. Ничего
 * своего сюда не приклеиваем, иначе текст дублируется.
 */
export function freshnessTooltip(f?: PriceFreshness | null): string {
  return f?.label || ''
}

export function usePriceFreshness() {
  return {
    PRICE_SOURCE_LABELS,
    PRICE_STALE_CLASS,
    formatDateDDMMYYYY,
    formatPriceStamp,
    freshnessColor,
    freshnessIcon,
    freshnessTooltip,
  }
}
