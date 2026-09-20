// ordersSearch.ts — единая функция поиска по реестру закупок (Правило №6:
// один показатель — один источник истины). Владелец (2026-09-20): строка
// «Поиск» во вкладке «Закупки» искала только по полям шапки закупки
// (registry_number/subject/item_name/…) — «Рукав пожарный», лежащий позицией
// ВНУТРИ другой закупки, не находился ни разу. Отдельное поле «Поиск товара»
// (filters.product, см. useOrdersData.ts) уже умело искать по items[].item_name —
// этот файл выносит проверку «есть ли совпадение среди позиций» в общую
// функцию, чтобы «Поиск» переиспользовал её, а не дублировал цикл по items.
import type { Purchase } from './ordersTypes'

/** Есть ли среди позиций закупки (items[].item_name) совпадение с query. */
export function itemsMatchQuery(items: any[] | undefined | null, query: string): boolean {
  if (!items || !items.length) return false
  const q = query.trim().toLowerCase()
  if (!q) return false
  return items.some((it: any) => String(it?.item_name ?? '').toLowerCase().includes(q))
}

/**
 * Строка «Поиск» в реестре закупок: совпадение по любому идентифицирующему
 * полю шапки закупки ИЛИ по наименованию хотя бы одной её позиции.
 * Используется и для табличного, и для карточного представления (OrdersTable
 * больше не полагается на встроенный :search v-data-table — он видит только
 * отображаемые колонки и не находит совпадения внутри items[]).
 */
export function purchaseMatchesSearch(o: Purchase, query: string): boolean {
  const q = query.trim().toLowerCase()
  if (!q) return true
  const headerFields = [
    (o as any).registry_number, o.subject, o.item_name, (o as any).contractor_name,
    (o as any).subsidy_name, (o as any).contract_number, (o as any).order_number,
    (o as any).agreement_number,
  ]
  if (headerFields.some(v => String(v ?? '').toLowerCase().includes(q))) return true
  return itemsMatchQuery((o as any).items, q)
}
