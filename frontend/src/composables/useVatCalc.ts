// useVatCalc — VAT (НДС) helpers extracted from PurchaseItemsEditor.vue.
// Convention (Phase 27.1.16): unit_price / total_price ALREADY INCLUDE VAT
// (prices from ФФД receipts / contracts are gross). vatAmount extracts the VAT
// portion out of the gross total: total * pct / (100 + pct).

export interface VatLike {
  total_price?: number | null
  total?: number | null
  vat_rate?: string | null
}

// Владелец (закупка РЕЕ-2026-00918, 2026-09-16): «список ставок неполный —
// нужны 5% и 7%» (УСН с 2025 г.) — единственный источник построчного списка
// ставок НДС, используется всеми 4 таблицами позиций (ItemsTableFlat/
// ItemsTableStages/ItemsCardsView/ItemsTableWish) через vatRateOptions prop —
// не плодить копии (ПРАВИЛО №6).
export const VAT_RATE_OPTIONS = [
  { title: 'Не облагается', value: null as string | null },
  { title: '0%', value: '0%' },
  { title: '5%', value: '5%' },
  { title: '7%', value: '7%' },
  { title: '10%', value: '10%' },
  { title: '20%', value: '20%' },
  { title: '22%', value: '22%' },
]

/** Parse a rate like "22%" / "22" / "22/122" (легаси расчётная ставка ФНС) /
 * "Без НДС" / null → numeric percent (0 when none). См. комментарий у
 * backend/app/services/documents/stages_amounts.py::_parse_vat_rate_percent —
 * тот же принцип, единственные два места этой математики (Правило №6). */
export function parseVatRatePercent(rate: string | null | undefined): number {
  if (!rate || rate === 'Без НДС') return 0
  const s = String(rate)
  const m = s.match(/^(\d+(?:\.\d+)?)\s*%?$/)
  if (m?.[1]) return parseFloat(m[1])
  const m2 = s.match(/^(\d+(?:\.\d+)?)\s*\/\s*\d+(?:\.\d+)?$/)
  return m2?.[1] ? parseFloat(m2[1]) : 0
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
