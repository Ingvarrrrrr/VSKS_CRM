// item-forms-accommodation-transport.md: ЕДИНСТВЕННАЯ фронтовая формула итога
// строки позиции со спец-формой («Проживание»/«Перевозки автобусом») — превью
// того же расчёта, что делает бэк (backend/app/services/item_amounts.py::
// compute_item_total/apply_item_amounts). Сервер пересчитывает и побеждает при
// сохранении (как с суммами закупки, см. ПРАВИЛО №6) — эта функция только
// показывает пользователю ожидаемое «Итого» до отправки формы.
//
// composables/items/useItemsTotals.ts::calcItemTotal — ЕДИНСТВЕННЫЙ вызывающий
// на фронте (для обычных позиций он же продолжает делать quantity × unit_price,
// см. line_total ниже). Второй копии этой формулы в проекте быть не должно —
// таблицы (ItemsTableFlat/Stages/Wish/ItemsCardsView) сами total_price не считают.

export type ItemFormFieldType = 'text' | 'number' | 'select' | 'datetime' | 'switch'

export interface ItemFormFieldOption {
  value: string
  label: string
}

export interface ItemFormField {
  key: string
  label: string
  type: ItemFormFieldType
  options?: ItemFormFieldOption[]
  default?: string | number | null
  hint?: string
}

export interface ItemFormDescriptor {
  label: string
  formula: string
  fields: ItemFormField[]
}

export type ItemFormCode = 'accommodation' | 'transport'

export type ExtraAttrs = Record<string, any>

function toNum(v: unknown): number {
  if (v === null || v === undefined || v === '') return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// Округление до копеек — тот же ROUND_HALF_UP-совместимый результат для типичных
// денежных величин, что и Decimal.quantize на бэке (см. item_amounts.py::_q2).
function round2(v: number): number {
  return Math.round((v + Number.EPSILON) * 100) / 100
}

function extraOf(extra: ExtraAttrs | null | undefined): ExtraAttrs {
  return extra && typeof extra === 'object' ? extra : {}
}

// Проживание: quantity = номера ИЛИ люди — по переключателю price_basis
// (см. item_amounts.py::_accommodation_quantity).
function accommodationQuantity(extra: ExtraAttrs): number {
  const basis = extra.price_basis || 'room'
  return basis === 'person' ? toNum(extra.persons) : toNum(extra.rooms)
}

// nights по умолчанию 1, если поле пустое или явно 0 (см. _accommodation_nights).
function accommodationNights(extra: ExtraAttrs): number {
  const raw = extra.nights
  const nights = raw === null || raw === undefined || raw === '' ? 1 : toNum(raw)
  return nights !== 0 ? nights : 1
}

// Перевозки: cost_mode='trip' → готовая стоимость рейса (quantity=1); иначе —
// (work_hours + supply_hours, по умолч. 2) × hourly_rate (см. _transport_quantity_and_rate).
function transportQuantityAndRate(extra: ExtraAttrs): [number, number] {
  const mode = extra.cost_mode || 'hours'
  if (mode === 'trip') return [1, toNum(extra.trip_cost)]
  const workHours = toNum(extra.work_hours)
  const supplyRaw = extra.supply_hours
  const supplyHours = supplyRaw === null || supplyRaw === undefined || supplyRaw === '' ? 2 : toNum(supplyRaw)
  return [workHours + supplyHours, toNum(extra.hourly_rate)]
}

/** Обычная позиция (item_form=null): количество × цена за единицу. */
export function lineTotal(quantity: unknown, unitPrice: unknown): number {
  return round2(toNum(quantity) * toNum(unitPrice))
}

/**
 * Итог строки по форме — превью-эквивалент backend::compute_item_total. НЕ мутирует
 * входные данные.
 */
export function computeItemTotal(
  extra: ExtraAttrs | null | undefined,
  itemForm: ItemFormCode | null | undefined,
  quantity: unknown,
  unitPrice: unknown,
): number {
  const ex = extraOf(extra)
  if (itemForm === 'accommodation') {
    const qty = accommodationQuantity(ex)
    const nights = accommodationNights(ex)
    return round2(toNum(unitPrice) * qty * nights)
  }
  if (itemForm === 'transport') {
    const [qty, rate] = transportQuantityAndRate(ex)
    return round2(qty * rate)
  }
  return lineTotal(quantity, unitPrice)
}

/**
 * Выставляет quantity/unit_price/total_price на переданный item по правилам формы
 * (превью-эквивалент backend::apply_item_amounts) и возвращает total_price. Для
 * accommodation/transport quantity (и для transport ещё unit_price) — производные
 * от extra_attrs, не вводятся напрямую пользователем в этих режимах.
 */
export function applyItemAmounts(
  item: { quantity?: unknown; unit_price?: unknown; total_price?: unknown; extra_attrs?: ExtraAttrs | null },
  itemForm: ItemFormCode | null | undefined,
): number {
  const extra = extraOf(item.extra_attrs)
  if (itemForm === 'accommodation') {
    item.quantity = accommodationQuantity(extra)
    // unit_price — цена за номер/человека в сутки, вводится пользователем напрямую.
  } else if (itemForm === 'transport') {
    const [qty, rate] = transportQuantityAndRate(extra)
    item.quantity = qty
    item.unit_price = rate
  }
  const total = computeItemTotal(extra, itemForm, item.quantity, item.unit_price)
  item.total_price = total
  return total
}

/**
 * Однострочная человекочитаемая расшифровка extra_attrs по описанию полей формы
 * (для компактных мест, где полный ItemFormFields.vue не помещается — напр.
 * свёрнутая строка ItemsTableStages.vue). Подписи/варианты — из fields (Правило
 * №6: единственный источник — item_forms.json), никакой второй копии текстов.
 */
export function formatExtraAttrsSummary(
  extra: ExtraAttrs | null | undefined,
  fields: ItemFormField[] | null | undefined,
): string {
  const ex = extraOf(extra)
  if (!fields || !fields.length) return ''
  const parts: string[] = []
  for (const f of fields) {
    const raw = ex[f.key]
    if (raw === null || raw === undefined || raw === '') continue
    let display: string = String(raw)
    if ((f.type === 'select' || f.type === 'switch') && f.options) {
      display = f.options.find(o => o.value === raw)?.label ?? display
    }
    parts.push(`${f.label}: ${display}`)
  }
  return parts.join(' · ')
}
