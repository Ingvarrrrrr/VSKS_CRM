// Своё ТЗ позиции (владелец, 14.10.2026, план item-tz-description.md, Этап Б) —
// ЕДИНСТВЕННОЕ место, где фронт считает «действующее ТЗ позиции» и «откуда оно
// взялось» (ПРАВИЛО №6: та же формула, что backend/app/services/item_tz.py::
// effective_item_tz — tz_description позиции, если непустое, иначе каталожное).
// Используется WishTzSection.vue, ItemsTableStages.vue (ТЗ sub-row) и
// ItemTzCompareDialog.vue — не дублировать эту проверку где-либо ещё.

export interface ItemWithTz {
  tz_description?: string | null
  // Подсказка «каталожное описание» — для закупки это РАЗ (product_description,
  // не меняется при правке своего ТЗ); для заявки WishItemOut.description уже
  // "действующее" (effective), поэтому оно совпадает с каталожным РОВНО когда
  // своё (tz_description) пусто — других данных с бэкенда нет, и больше не нужно.
  _description?: string | null
  // Каталожное описание для режима 44-ФЗ (см. effective_item_tz_44fz) — то же
  // замечание про заявку/закупку, что и у _description выше.
  _description_44fz?: string | null
}

function trimmed(v: string | null | undefined): string {
  return (v || '').trim()
}

/** Действующее ТЗ позиции для показа — своё, если заполнено, иначе каталожное
 * (mirrors backend/app/services/item_tz.py::effective_item_tz). mode='44fz' —
 * каталожный фолбэк берётся из _description_44fz (effective_item_tz_44fz);
 * своё ТЗ (tz_description) не различает режим — то же поле для обеих формулировок. */
export function effectiveTz(item: ItemWithTz, mode: 'exact' | '44fz' = 'exact'): string {
  const own = trimmed(item.tz_description)
  if (own) return own
  return trimmed(mode === '44fz' ? item._description_44fz : item._description)
}

/** true — показанное выше значение взято из каталога (своего ТЗ нет). */
export function isTzFromCatalog(item: ItemWithTz): boolean {
  return !trimmed(item.tz_description) && !!trimmed(item._description)
}

/** Очищает своё ТЗ — дальше действует каталожное (см. effectiveTz выше). */
export function resetTzToCatalog(item: ItemWithTz): void {
  item.tz_description = null
}

/** true — два текста ТЗ реально различаются (после схлопывания пробелов),
 * оба непусты. Используется окном сравнения при импорте (ItemTzCompareDialog,
 * см. useItemsImport.ts::maybeResolveTzCompare) — ОДИН критерий «показывать
 * строку в сравнении», не дублировать его при добавлении новых путей импорта. */
export function tzTextsDiffer(a: string | null | undefined, b: string | null | undefined): boolean {
  const na = (a || '').replace(/\s+/g, ' ').trim()
  const nb = (b || '').replace(/\s+/g, ' ').trim()
  return !!na && !!nb && na !== nb
}
