// Группировка плановых позиций листа ФЭО (Таблица A / Level 5,
// FeoLevel5Panel.vue) по переключателю «Позиции: Нет / По категориям /
// Категории + виды» (FeoTreeToolbar.vue, ctx.feoItemsGroupBy) — задача
// владельца 27.10.2026.
//
// До этой задачи переключатель группировал только виртуальные позиции
// ЗАКУПОК, не привязанные к плановой позиции (useFeoReqItems.ts::reqItemRowsFor,
// категория = Product.category/product_type товара закупки). Сами плановые
// позиции (FeoPlannedItem — импорт ФЭО и ручные) не группировались никак — у
// них нет product_id. Бэкенд (app/services/feo_plan_catalog_category.py,
// GET /feo-planned-items/comparison) теперь находит категорию/вид по ТОЧНОМУ
// совпадению нормализованного имени позиции с товаром каталога и кладёт их в
// FeoPlannedItem.catalog_category/catalog_product_type. Здесь — только
// раскладка готовых позиций на строки-заголовки/позиции для рендера; сама
// механика сортировки/вставки заголовков — buildCategoryGroupedRows
// (feoCategoryUtils.ts, ОБЩАЯ с useFeoReqItems.ts::reqItemRowsFor, Правило №6).
//
// index на строке-позиции — ИСХОДНЫЙ индекс в ctx.displayPlannedRowsFor(node)
// (несгруппированный, «как сейчас» порядок sort_order): FeoLevel5Panel.vue
// вызывает ctx.reorderPlannedItem(node, index, direction) и сверяет
// index===0/length-1 для стрелок вверх/вниз — эта логика работает с
// ПОЛНЫМ несгруппированным списком независимо от того, как позиции сейчас
// визуально разбиты на группы (перестановка местами внутри категории не
// обязана совпадать с «первый/последний в своей группе» — задача владельца
// просит группировку только для ОБЗОРА, сортировку внутри группы оставляет
// «как сейчас», т.е. по sort_order).
import { buildCategoryGroupedRows, type CategoryGroupRow } from './feoCategoryUtils'
import type { FeoPlannedItem } from './types'

export type FeoPlannedGroupMode = 'none' | 'category' | 'category_type'

export type FeoPlannedGroupEntry =
  | { kind: 'header'; key: string; label: string; level: number; count: number; sum: number }
  | { kind: 'item'; key: string; item: FeoPlannedItem & { isManual?: boolean }; index: number }

const NO_CATEGORY_LABEL = 'Без категории'
const NO_TYPE_LABEL = 'Без вида'

/** Чистая функция (без Vue/ctx) — строит плоский список строк для рендера
 * таблицы плановых позиций. `items` — РОВНО то, что отдаёт
 * ctx.displayPlannedRowsFor(node), в исходном порядке (index сохраняет позицию
 * в этом массиве для реордера). */
export function buildPlannedGroupEntries(
  items: (FeoPlannedItem & { isManual?: boolean })[],
  mode: FeoPlannedGroupMode,
): FeoPlannedGroupEntry[] {
  const withIndex = items.map((item, index) => ({ item, index }))
  const rows: CategoryGroupRow<{ item: FeoPlannedItem & { isManual?: boolean }; index: number }>[] = buildCategoryGroupedRows(
    withIndex,
    mode,
    (x) => x.item.catalog_category || NO_CATEGORY_LABEL,
    (x) => x.item.catalog_product_type || NO_TYPE_LABEL,
    (x) => x.item.name,
    (x) => Number(x.item.amount || 0),
  )
  return rows.map((row): FeoPlannedGroupEntry => {
    if (!row.item) {
      return { kind: 'header', key: row.key, label: row.header, level: row.level, count: row.count, sum: row.sum }
    }
    return { kind: 'item', key: `p-${row.item.item.id}`, item: row.item.item, index: row.item.index }
  })
}
