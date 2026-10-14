// avgPrice.ts — ЕДИНЫЙ форматтер подписи «Средняя цена» (ПРАВИЛО №6): и
// список «Товары» (ProductsTable.vue), и подсказка у позиции заявки/закупки
// (AvgPriceHint.vue) читают отсюда, не собирают текст заново каждый по-своему.
//
// Источник чисел — backend/app/services/product_price_stats.py (лестница
// уровней region_batch → region → nearest_batch → nearest → batch → all,
// план clever-bouncing-lantern.md, Часть 2). Этот файл только переводит уже
// посчитанный {level, region_used, batch, basis_count, stale} в русский
// текст — вторую формулу средней цены здесь не заводим.
import { pluralRu } from '@/composables/products/productsTypes'

export type AvgPriceLevel = 'region_batch' | 'region' | 'nearest_batch' | 'nearest' | 'batch' | 'all'

export interface AvgPriceStats {
  avg_price: number | null
  basis_count: number
  stale: boolean
  level?: AvgPriceLevel | string | null
  region_used?: string | null
  batch?: string | null
  // Форма из ProductOut (список «Товары») — те же данные под другими именами.
  region?: string | null
}

// Партия backend'а ('1-9' …) → читаемая русская подпись. Единственное место
// перевода кодов партии в текст (не дублировать в компонентах).
const BATCH_LABELS_RU: Record<string, string> = {
  '1-9': '1–9', '10-99': '10–99', '100-999': '100–999', '1000+': '1000+',
}
export function batchLabelRu(batch?: string | null): string {
  if (!batch) return ''
  return BATCH_LABELS_RU[batch] || batch
}

// Количество → метка партии — зеркало backend/app/services/product_price_stats.py::batch_label
// (ПРАВИЛО №6 — одна и та же лестница границ, не придумывать вторую на фронте;
// нужна фронту только чтобы СГРУППИРОВАТЬ bulk-запрос по партии — число
// считает backend, здесь только группировка одинаковых запросов).
const BATCH_RANGES: [string, number, number | null][] = [
  ['1-9', 1, 9], ['10-99', 10, 99], ['100-999', 100, 999], ['1000+', 1000, null],
]
export function batchLabelFromQuantity(quantity: number | null | undefined): string | null {
  if (quantity == null) return null
  const qty = Number(quantity)
  if (!Number.isFinite(qty) || qty < 1) return null
  for (const [label, lo, hi] of BATCH_RANGES) {
    if (hi == null) { if (qty >= lo) return label }
    else if (qty >= lo && qty <= hi) return label
  }
  return null
}

function contractsWord(n: number): string {
  return pluralRu(n, 'договор', 'договора', 'договоров')
}

function rub(v: number): string {
  return Number(v).toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' ₽'
}

/** Полная подпись для тултипа: «Средняя по {регион}, партия {X}: {сумма} ₽
 * ({N} договора)», с вариантами nearest/batch/all — см. докстринг модуля. */
export function formatAvgPriceLabel(stats: AvgPriceStats | null | undefined): string {
  if (!stats || stats.avg_price == null) return ''
  const level = stats.level || 'all'
  const region = stats.region_used ?? stats.region ?? null
  const batch = batchLabelRu(stats.batch)
  let head: string
  switch (level) {
    case 'region_batch':
      head = `Средняя по ${region}, партия ${batch} шт.`
      break
    case 'region':
      head = `Средняя по ${region}`
      break
    case 'nearest_batch':
      head = `Средняя по ${region} — ближайший регион с данными, партия ${batch} шт.`
      break
    case 'nearest':
      head = `Средняя по ${region} — ближайший регион с данными`
      break
    case 'batch':
      head = `Средняя по всем регионам, партия ${batch} шт.`
      break
    default:
      head = 'Средняя по всем договорам'
  }
  const n = stats.basis_count || 0
  const tail = ` (${n} ${contractsWord(n)})`
  const stale = stats.stale ? ' — устарела' : ''
  return `${head}: ${rub(stats.avg_price)}${tail}${stale}`
}

/** Короткая подпись «на чём основано» без суммы — для компактных мест
 * (используется той же лестницей уровней, что и formatAvgPriceLabel). */
export function avgPriceBasisLabel(stats: AvgPriceStats | null | undefined): string {
  if (!stats) return ''
  const level = stats.level || 'all'
  const region = stats.region_used ?? stats.region ?? null
  const batch = batchLabelRu(stats.batch)
  switch (level) {
    case 'region_batch': return `по ${region}, партия ${batch} шт.`
    case 'region': return `по ${region}`
    case 'nearest_batch': return `по ${region} — ближайший регион, партия ${batch} шт.`
    case 'nearest': return `по ${region} — ближайший регион с данными`
    case 'batch': return `по всем регионам, партия ${batch} шт.`
    default: return 'по всем договорам'
  }
}
