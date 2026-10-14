// units.ts — единый справочник единиц измерения товара + правило «это
// упаковочная единица?» (владелец, 14.10: «единица измерения не в карточке
// товара; когда товар меряется упаковками, должно быть количество в
// упаковке»). Зеркало backend/app/services/units.py — логика is_pack_unit
// ОДНА (Правило №6), меняется в обоих местах синхронно.

// Подсказка для v-combobox «Ед. изм.» (ProductFormDialog.vue) — можно
// выбрать из списка или ввести свою (combobox, не select).
export const UNIT_OPTIONS = [
  'шт.', 'упак.', 'компл.', 'пара', 'кг', 'г', 'л', 'м', 'м²', 'м³',
  'усл. ед.', 'час', 'сутки',
]

// Порядок важен: INNER_UNIT_OPTIONS считается при загрузке модуля и вызывает
// isPackUnit — поэтому PACK_UNIT_TOKENS и isPackUnit объявлены ВЫШЕ неё
// (иначе TDZ: ReferenceError "Cannot access before initialization").
const PACK_UNIT_TOKENS = new Set(['упак', 'уп', 'упаковка', 'пачка', 'коробка', 'кор', 'рулон', 'набор'])

export function isPackUnit(unit?: string | null): boolean {
  if (!unit) return false
  const normalized = unit.trim().toLowerCase().replace(/\.+$/, '')
  return PACK_UNIT_TOKENS.has(normalized)
}

// Тот же набор без упаковочных единиц — для выбора «единицы ВНУТРИ упаковки».
export const INNER_UNIT_OPTIONS = UNIT_OPTIONS.filter(u => !isPackUnit(u))

// Показ единицы измерения товара с уточнением упаковки — одна функция для
// карточек/таблицы каталога и подсказки в подборе товара (Правило №6): «упак.
// (10 шт.)» / «шт.» / «—» (единица не задана).
export function formatUnitWithPack(product: { unit?: string | null; pack_quantity?: number | string | null; pack_unit?: string | null }): string {
  const unit = (product.unit || '').trim()
  if (!unit) return '—'
  if (isPackUnit(unit) && product.pack_quantity != null && product.pack_unit) {
    return `${unit} (${product.pack_quantity} ${product.pack_unit})`
  }
  return unit
}
