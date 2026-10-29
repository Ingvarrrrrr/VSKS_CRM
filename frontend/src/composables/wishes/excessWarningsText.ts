// excessWarningsText.ts — единственное место, где текст превышения плана
// (excess_warnings) строится из структурированного ExcessWarning[].
//
// Выделено из useWishesContext.ts::showExcessWarnings (ПРАВИЛО №6, 29.10.2026):
// useWishBulkActions.ts держал вторую копию той же формулы для итогового окна
// массового «Передать в план» — теперь оба зовут отсюда, текст не менялся.
import { formatPrice } from './useWishesContext'
import type { ExcessWarning } from './wishTypes'

export interface FormattedExcessWarnings {
  /** Готовый текст дублей (type==='duplicate') — join(' ') по w.message. */
  duplicateText: string
  /** Текст по каждой категории ФЭО с превышением — join(' ; ') на вызывающей стороне. */
  categoryParts: string[]
}

export function formatExcessWarningsText(warnings: ExcessWarning[]): FormattedExcessWarnings {
  // Владелец (2026-09-29): «дубль занял план молча» — отдельная форма записи
  // в том же канале (type==='duplicate', см. wishTypes.ts) — готовый текст
  // message, без category_name/excess_amount (их там нет).
  const duplicateWarnings = warnings.filter(w => w.type === 'duplicate')
  const categoryWarnings = warnings.filter(w => w.type !== 'duplicate')
  const categoryParts = categoryWarnings.map(w => {
    const itemsText = (w.items || []).map(i => `${i.name} — ${formatPrice(i.amount)}`).join(', ')
    return `Категория «${w.category_name}»: план превышает ФЭО на ${formatPrice(w.excess_amount ?? 0)}${itemsText ? ` (позиции: ${itemsText})` : ''}`
  })
  const duplicateText = duplicateWarnings.map(w => w.message).filter(Boolean).join(' ')
  return { duplicateText, categoryParts }
}
