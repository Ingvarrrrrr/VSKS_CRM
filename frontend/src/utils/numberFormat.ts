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

/**
 * Единый хелпер подсветки «остаток/превышение плана» (владелец, сессия
 * 2026-08-21: «Подсвечено должно быть везде такое несоответствие. Основная
 * проблема» — до этого в проекте было ЧЕТЫРЕ разных способа красить
 * отрицательный остаток по-разному: .feo-planned-shortfall (FeoPlannedItemsSelect.vue,
 * привязано к isShort()/props.amount — другому условию, не к самому остатку),
 * инлайн-стиль в SubsidiesView.vue (feoFinDiff), .feo-excess-culprit
 * (SubsidiesView.vue, отдельная крупная плашка), .feo-tree-residual--negative
 * (FeoTreeSelect.vue). Эталон текста и вида — SubsidiesView.vue:833-839
 * («план X · в закупках Y · больше плана на N ₽», красный жирный) — эта
 * функция даёт то же самое: единственный источник и числа, и цвета, чтобы
 * они не могли разойтись (баг, который был в FeoPlannedItemsSelect.vue:242-256 —
 * число бралось из row.residual, а класс из isShort()/residualFor()).
 *
 * residual — planned_amount минус реально занятое; отрицательное значение =
 * позиция обошлась/набрана дороже плана (превышение), а не просто «остаток
 * со знаком минус».
 */
export interface PlanResidualDisplay {
  /** true — остаток отрицательный, т.е. реальное превышение плана. */
  negative: boolean
  /** Готовая подпись целиком: «остаток 1 500 ₽» либо «превышение на 1 500 ₽». */
  text: string
  /** CSS-класс для подсветки (см. .plan-residual--negative в styles/gala.css) — вешать
   *  на элемент, который показывает text (или само число), рядом с остальными классами. */
  cssClass: string
}

const PLAN_RESIDUAL_EPSILON = 0.005

export function formatPlanResidual(
  residual: number | null | undefined,
  opts?: { label?: string; money?: (n: number) => string }
): PlanResidualDisplay {
  const label = opts?.label ?? 'остаток'
  const money = opts?.money ?? fmtRub
  const n = residual == null ? 0 : Number(residual)
  const negative = n < -PLAN_RESIDUAL_EPSILON
  return {
    negative,
    text: negative ? `превышение на ${money(-n)}` : `${label} ${money(n)}`,
    cssClass: negative ? 'plan-residual--negative' : '',
  }
}
