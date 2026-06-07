// Number formatting / parsing helpers shared across item editors.
// Extracted from PurchaseItemsEditor.vue (monolith refactor) so they can be
// reused by segmented item components (tables, dialogs, inline match).
import { formatMoney } from '@/utils/formatMoney'

/**
 * Format a number with ru-RU thousand separators (no currency suffix).
 * Empty / null / NaN → '' (so it can back an editable text-field).
 */
export function formatNumber(v: number | null | undefined): string {
  if (v == null || v === ('' as any)) return ''
  const n = Number(v)
  if (isNaN(n)) return String(v)
  return n.toLocaleString('ru-RU', { maximumFractionDigits: 2, useGrouping: true })
}

/**
 * Parse a user-typed string (with spaces / NBSP / comma decimal) into a number.
 * Empty / unparseable → null.
 */
export function parseNumber(s: string | number | null | undefined): number | null {
  if (s == null || s === ('' as any)) return null
  if (typeof s === 'number') return s
  const cleaned = String(s).replace(/[\s\u00A0]/g, '').replace(',', '.')
  const n = parseFloat(cleaned)
  return isNaN(n) ? null : n
}

/**
 * Format a number as ru-RU rubles with 2 decimals. Null / NaN → '—'.
 * Thin wrapper around formatMoney to keep the historical '—' behaviour and
 * the explicit ' ₽' suffix used by the item editor.
 */
export function fmtRub(n: number | null | undefined): string {
  if (n == null || isNaN(Number(n))) return '—'
  return formatMoney(n)
}
