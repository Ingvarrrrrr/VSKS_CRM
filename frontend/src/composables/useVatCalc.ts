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
//
// Владелец (2026-09-30): value=null у «Не облагается» было неоднозначно с
// «ставка ещё не выбрана» (документный гейт VAT_RATE_REQUIRED в
// documents/templates.py читал оба случая одинаково — «не заполнено»).
// value теперь 'Без НДС' — тот же литерал, что уже пишут чеки без НДС
// (backend/app/services/receipts_parsing.py::NDS_CODE_TO_RATE_STR код 6 и
// отсутствие тега nds) и что уже был в комментарии models/contract_item.py::
// vat_rate ('22%', '10%', 'Без НДС', custom). null остаётся ТОЛЬКО за «не
// выбрано» — не показывается как отдельный пункт списка.
export const VAT_RATE_OPTIONS = [
  { title: 'Не облагается', value: 'Без НДС' as string | null },
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

/** VAT «в т.ч.» извлечённый из суммы, которая ВСЕГДА хранится с НДС (плейн
 * (total, rate) сигнатура — ЕДИНСТВЕННОЕ место этой формулы на фронте,
 * ПРАВИЛО №6, см. .planning/quick/2026-10-02-vat-on-top/PLAN.md). vatAmount()
 * ниже — обёртка над ней для вызывающих с объектом позиции. */
export function vatIncludedAmount(total: unknown, rate: string | null | undefined): number {
  const t = Number(total ?? 0)
  const pct = parseVatRatePercent(rate)
  if (pct <= 0 || !t) return 0
  return Number((t * pct / (100 + pct)).toFixed(2))
}

/** VAT portion extracted from a gross (VAT-inclusive) total. */
export function vatAmount(item: VatLike): number {
  const total = item.total_price ?? item.total ?? 0
  return vatIncludedAmount(total, item.vat_rate)
}

/**
 * Разрешает действующий флаг «НДС сверху» для строки: в режиме per_item
 * построчный флаг побеждает (null у строки = «как у закупки» — фолбэк на
 * заголовок), в режиме uniform всегда действует заголовок. ЕДИНСТВЕННОЕ место
 * этой логики на фронте (ПРАВИЛО №6) — вызывают useItemsTotals.calcItemTotal,
 * PurchaseItemsEditor.vue::recalcContractTotal и построчные таблицы позиций.
 */
export function effectiveVatOnTop(
  itemFlag: boolean | null | undefined,
  headerFlag: boolean | null | undefined,
  vatMode: string | null | undefined,
): boolean {
  if ((vatMode || 'uniform') === 'per_item' && itemFlag != null) return !!itemFlag
  return !!headerFlag
}

/**
 * Сумма строки: цена введена «как есть» (с НДС или без — решает onTop).
 * onTop и ставка > 0 → qty×price×(1+p/100) (цена без НДС, сумма — с), иначе
 * (включая ставку «не облагается»/«ещё не знаю»/пустую) — qty×price как есть.
 * Округление до копеек. ЕДИНСТВЕННАЯ формула суммы строки с учётом «НДС
 * сверху» на фронте (ПРАВИЛО №6) — зеркало backend item_amounts.py::
 * line_total. Для позиций со спец-формой (Проживание/Перевозки/Питание)
 * формулу считает applyItemAmounts/computeItemTotal в utils/itemAmounts.ts —
 * «НДС сверху» на них не распространяется (цена там не разделяется на тип
 * позиции и ставку в этом релизе).
 */
export function lineTotalWithVat(
  qty: unknown,
  price: unknown,
  rate: string | null | undefined,
  onTop: boolean,
): number {
  const base = Number(qty ?? 0) * Number(price ?? 0)
  if (!onTop) return Math.round(base * 100) / 100
  const pct = parseVatRatePercent(rate)
  if (pct <= 0) return Math.round(base * 100) / 100
  return Math.round(base * (1 + pct / 100) * 100) / 100
}

/** Total WITH VAT — total_price is already gross, so return it as-is. */
export function totalWithVat(item: VatLike): number {
  return Number(item.total_price ?? item.total ?? 0)
}

/**
 * Normalize a user-entered VAT rate value into the stored canonical form.
 * null / '' → null ("не выбрано"). 'Без НДС' stays 'Без НДС' — distinct from
 * null (владелец, 2026-09-30: "не выбрано" и "явно без НДС" — разные вещи,
 * см. комментарий у VAT_RATE_OPTIONS). A bare number → "<n>%". Anything else
 * as-is.
 */
export function normalizeVatRate(v: any): string | null {
  if (v == null || v === '') return null
  if (v === 'Без НДС') return 'Без НДС'
  const s = String(v)
  return /^\d+(?:\.\d+)?$/.test(s.trim()) ? s.trim() + '%' : s
}

// 2026-10-02 (владелец, после приёмки): построчный флаг «НДС сверху» в
// per_item — три состояния (null/false/true), нужен способ вернуться в null
// («как у закупки») из явно выставленных true/false. Единственное место этой
// туда-обратно-мэппинга строка↔boolean|null (ПРАВИЛО №6) — используют
// ItemsTableStages/ItemsTableFlat/ItemsCardsView.vue для v-btn-toggle с 3
// кнопками вместо checkbox (у checkbox нет пути назад в indeterminate).
// 2026-10-02 (дефект приёмки — заявка, уже после правки toggle'а): в
// uniform-режиме у строки НЕТ своего поля ввода ставки (v-select ставки
// рендерится только при vatMode==='per_item' — ItemsTableFlat/Stages/
// CardsView), поэтому item.vat_rate там всегда null. Формула «НДС сверху»
// читала ИМЕННО item.vat_rate → ставка всегда резолвилась в 0%, и сумма
// 10×100 оставалась 1000 даже при включённом тумблере. headerVatRateString +
// effectiveVatRateForItem — единственное место, где ставка строки получает
// фолбэк на заголовочную (vat_applicable/vat_rate закупки/заявки), в uniform-
// режиме. per_item со своей (непустой) ставкой строки эту пару не трогает.
export function headerVatRateString(
  vatApplicable: boolean | null | undefined,
  vatRate: number | null | undefined,
): string | null {
  if (vatApplicable === false) return 'Без НДС'
  if (vatApplicable === true && vatRate != null) return `${vatRate}%`
  return null
}

export function effectiveVatRateForItem(
  itemRate: string | null | undefined,
  vatMode: string | null | undefined,
  headerRate: string | null | undefined,
): string | null {
  if (itemRate) return itemRate
  return (vatMode || 'uniform') === 'uniform' ? (headerRate ?? null) : null
}

export type VatOnTopTriState = 'default' | 'included' | 'on_top'
export function vatOnTopToTriState(v: boolean | null | undefined): VatOnTopTriState {
  return v === true ? 'on_top' : v === false ? 'included' : 'default'
}
export function triStateToVatOnTop(s: VatOnTopTriState): boolean | null {
  return s === 'default' ? null : s === 'on_top'
}

export function useVatCalc() {
  return {
    VAT_RATE_OPTIONS,
    parseVatRatePercent,
    vatAmount,
    vatIncludedAmount,
    totalWithVat,
    normalizeVatRate,
    effectiveVatOnTop,
    lineTotalWithVat,
    vatOnTopToTriState,
    triStateToVatOnTop,
    headerVatRateString,
    effectiveVatRateForItem,
  }
}
