// Русские названия служебных полей импорта позиций (item_name/quantity/...) —
// план item-tz-description.md, п.5 (владелец, 14.10.2026): подпись «Распознано
// позиций: N (столбцы: item_name, quantity…)» в окне импорта показывала
// английские служебные имена полей. ЕДИНЫЙ словарь (ПРАВИЛО №6) — те же ключи,
// что в useItemsImport.ts::TARGET_FIELDS/_MAPPED_COL_PARAM_NAMES и backend
// (columns_found в ответах import-smart/import-smart-nopid).
export const IMPORT_COLUMN_LABELS: Record<string, string> = {
  item_name: 'Наименование',
  quantity: 'Количество',
  unit: 'Ед. изм.',
  unit_price: 'Цена за ед.',
  total_price: 'Сумма',
  description: 'Характеристики',
  row_num: '№ строки',
  vat_rate: 'Ставка НДС',
  vat_amount: 'Сумма НДС',
  total_with_vat: 'Стоимость с НДС',
  category: 'Категория товара',
  product_type: 'Вид товара',
  item_type: 'Тип',
}

/** Русская подпись для служебного имени поля импорта; неизвестное имя
 * отдаётся как есть (не должно случаться — см. словарь выше). */
export function importColumnLabel(field: string): string {
  return IMPORT_COLUMN_LABELS[field] || field
}
