// useVatCalc — VAT (НДС) helpers extracted from PurchaseItemsEditor.vue.
// Convention (Phase 27.1.16): unit_price / total_price ALREADY INCLUDE VAT
// (prices from ФФД receipts / contracts are gross). vatAmount extracts the VAT
// portion out of the gross total: total * pct / (100 + pct).

export interface VatLike {
  total_price?: number | null
  total?: number | null
  vat_rate?: string | null
}

export const VAT_RATE_OPTIONS = [
  { title: '5%', value: '5%' },
  { title: '10%', value: '10%' },
  { title: '22%', value: '22%' },
  { title: 'Без НДС', value: null as string | null },
]

/** Parse a rate like "22%" / "22" / "Без НДС" / null → numeric percent (0 when none). */
export function parseVatRatePercent(rate: string | null | undefined): number {
  if (!rate || rate === 'Без НДС') return 0
  const m = String(rate).match(/^(\d+(?:\.\d+)?)\s*%?$/)
  return m ? parseFloat(m[1]) : 0
}

/** VAT portion extracted from a gross (VAT-inclusive) total. */
export function vatAmount(item: VatLike): number {
  const total = Number(item.total_price ?? item.total ?? 0)
  const pct = parseVatRatePercent(item.vat_rate)
  if (pct <= 0) return 0
  return Number((total * pct / (100 + pct)).toFixed(2))
}

/** Total WITH VAT — total_price is already gross, so return it as-is. */
export function totalWithVat(item: VatLike): number {
  return Number(item.total_price ?? item.total ?? 0)
}

/**
 * Normalize a user-entered VAT rate value into the stored canonical form.
 * null / '' / 'Без НДС' → null. A bare number → "<n>%". Anything else as-is.
 */
export function normalizeVatRate(v: any): string | null {
  if (v == null || v === '' || v === 'Без НДС') return null
  const s = String(v)
  return /^\d+(?:\.\d+)?$/.test(s.trim()) ? s.trim() + '%' : s
}

export function useVatCalc() {
  return {
    VAT_RATE_OPTIONS,
    parseVatRatePercent,
    vatAmount,
    totalWithVat,
    normalizeVatRate,
  }
}
