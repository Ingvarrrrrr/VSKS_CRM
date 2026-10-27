// Единственный источник обхода поддерева категорий ФЭО по parent_id — раньше
// collectSubtreeIds жила только как локальная функция в SubsidiesView.vue и уже
// использовалась в четырёх местах (feoParentOptions, feoDeleteChildrenCount,
// drag&drop категорий). Вынесена сюда параметризованной по списку категорий,
// чтобы компоненты диалогов ФЭО (FeoCategoryDialog/FeoCategoryDeleteDialog) не
// заводили свою копию (Правило №6).
import type { FeoActualItem, FeoCategory, FeoLeftGroupInfo } from './types'

// Нормализация имени для сопоставления позиций «из заявок» с категориями/друг другом —
// используется useFeoLevel5.ts (fallbackAbsorbedByCategory/stagesWithDiff) и
// useFeoReqItems.ts (mergedReqByCat/allReqGroupsByCat) — единственный источник (Правило №6).
export function normName(s: string | null | undefined): string {
  return (s || '').trim().toLowerCase().replace(/\s+/g, ' ')
}

export function collectSubtreeIds(categories: FeoCategory[], nodeId: number): number[] {
  const ids = [nodeId]
  const find = (pid: number) => {
    for (const c of categories) {
      if (c.parent_id === pid) { ids.push(c.id); find(c.id) }
    }
  }
  find(nodeId)
  return ids
}

// Нижний порог ширины колонки «Наименование» дерева ФЭО (координатор, регресс
// приёмки 2026-09-20 №2): несжимаемые шеврон/папка (+чекбокс категории/позиции
// в режиме выбора) перед текстом съедают ~70px, при сохранённой в localStorage
// узкой ширине ('feo-table' colWidths.name) текст рвался по буквам. Единственный
// источник формулы (Правило №6): FeoTreeTable.vue (шапка дерева) и
// FeoLevel5Panel.vue (своя вложенная <table> внутри панели «План vs факт» —
// table-layout:fixed считает ширины НЕЗАВИСИМО от внешней таблицы, поэтому ей
// нужен тот же порог отдельно) оборачивают им СВОЙ resizeStyle('name'), второй
// копии формулы/чисел не заводят. minWidth ПЕРЕКРЫВАЕТ уже сохранённое узкое
// значение при каждом чтении (не разовая миграция localStorage) — по CSS-спеке
// min-width всегда побеждает над меньшим width/max-width.
export const FEO_NAME_COLUMN_MIN = 230
// +24 → +110 → +40 (правка 2026-09-21, приёмка: подпись «Выбрано k из N
// незакупленных» снова рвала «Наименование» по буквам; подпись сжата до чипа
// «k из N» — FeoTreeRow.vue, feo-tree-select-label — короткому чипу хватает
// прежнего +40 (чекбокс + короткий чип), полный текст ушёл в tooltip.
// Единственный источник порога (Правило №6).
export const FEO_NAME_COLUMN_MIN_SELECT_MODE = FEO_NAME_COLUMN_MIN + 40

export function withNameColumnFloor(base: Record<string, string>, selectModeActive: boolean): Record<string, string> {
  const min = selectModeActive ? FEO_NAME_COLUMN_MIN_SELECT_MODE : FEO_NAME_COLUMN_MIN
  // resizeStyle() (useResizableColumns.ts) отдаёт width/minWidth/maxWidth одним
  // числом — при table-layout: fixed колонку держит width, а maxWidth не даёт
  // расти, поэтому один только minWidth ничего не менял (приёмка 20.09:
  // названия по-прежнему рвались по буквам). Порог применяем ко всем трём.
  const stored = parseInt(String(base.width ?? ''), 10)
  const w = Number.isFinite(stored) ? Math.max(stored, min) : min
  return { ...base, width: `${w}px`, minWidth: `${w}px`, maxWidth: `${w}px` }
}

// ── Левая группа колонок панели «план vs факт»: ДВА состояния, не «план» ──────
// Правка владельца (2026-08-09): левая группа у строк ФАКТА — это НЕ план (план —
// только строка самой плановой позиции, помечена чипом «план»). До заключения
// договора показываем, как товар завели в заявке/ТЗ (stage 'purchase' в
// _build_item_stages, backend/app/routers/feo_planned_items.py — снимок
// PurchaseItem.item_name/quantity/unit_price/total_price); как только появилась
// договорная позиция — номенклатуру, количество и цену подрядчика (stage
// 'contract' — ContractItem). Источник — уже загруженный actual.stages, второй
// запрос/расчёт не делает. Фолбэк на actual.* — на случай отсутствия stages
// (защитный код: 'purchase' стадия в _build_item_stages есть всегда, но панель
// не должна показывать пустые клетки, если что-то разошлось).
//
// Функция ЧИСТАЯ (не зависит от состояния дерева) — используется и в самом дереве
// ФЭО (SubsidiesView.vue), и в PlannedItemAddDialog.vue (openCreatePlannedFromActual)
// — один источник, не две копии (Правило №6).
// ── Группировка «Позиции: По категориям / Категории + виды» — общее ядро ────
// Переключатель FeoTreeToolbar.vue (ctx.feoItemsGroupBy) группирует ДВА разных
// списка: виртуальные позиции «из заявок» (useFeoReqItems.ts::reqItemRowsFor)
// и плановые позиции листа (useFeoPlannedItemGroups.ts, задача владельца
// 27.10.2026 — категория/вид у них теперь из каталога по точному совпадению
// имени, см. FeoPlannedItem.catalog_category/catalog_product_type). Сама
// механика сортировки/вставки строк-заголовков («Без категории»/«Без вида» —
// фолбэк, как и у виртуальных позиций закупок, feo_plan_reads.py) — ОДНА
// функция (Правило №6), второй копии цикла с curCat/curType не заводим.
export interface CategoryGroupRow<T, I = never> {
  key: string
  header: string
  level: number
  count: number
  sum: number
  // Опционально: сумма количества (round-4) и плоский список вложенных элементов
  // группы — нужны useFeoReqItems.ts::reqItemRowsFor (виртуальные позиции
  // закупок состоят из нескольких FeoReqItem), useFeoPlannedItemGroups.ts их не
  // запрашивает (opts не передаёт) — поля остаются undefined, старое поведение
  // не меняется.
  sumQty?: number
  items?: I[]
  item: T | null
}

export interface BuildCategoryGroupedRowsOpts<T, I> {
  getQty?: (x: T) => number
  getItems?: (x: T) => I[]
  // Префикс ключа строки-позиции (`${prefix}-${normName(name)}`) — по умолчанию
  // 'i', useFeoReqItems.ts передаёт 'g' (исторический ключ `g-...` виртуальных
  // групп, совпадает с reqPanelKey/normName в этом же файле).
  itemKeyPrefix?: string
}

export function buildCategoryGroupedRows<T, I = never>(
  items: T[],
  mode: 'none' | 'category' | 'category_type',
  getCategory: (x: T) => string,
  getProductType: (x: T) => string,
  getName: (x: T) => string,
  getSum: (x: T) => number,
  opts?: BuildCategoryGroupedRowsOpts<T, I>,
): CategoryGroupRow<T, I>[] {
  const prefix = opts?.itemKeyPrefix ?? 'i'
  const getQty = opts?.getQty
  const getItems = opts?.getItems
  const itemRow = (x: T): CategoryGroupRow<T, I> => ({
    key: `${prefix}-${normName(getName(x))}`,
    header: '',
    level: 0,
    count: getItems ? getItems(x).length : 1,
    sum: getSum(x),
    ...(getQty ? { sumQty: getQty(x) } : {}),
    ...(getItems ? { items: getItems(x) } : {}),
    item: x,
  })
  if (mode === 'none') {
    return items.map(itemRow)
  }
  const sorted = [...items].sort((a, b) =>
    getCategory(a).localeCompare(getCategory(b), 'ru')
    || getProductType(a).localeCompare(getProductType(b), 'ru')
    || getName(a).localeCompare(getName(b), 'ru'))
  const rows: CategoryGroupRow<T, I>[] = []
  let curCat: string | null = null
  let curType: string | null = null
  const headerRow = (key: string, header: string, level: number, grp: T[]): CategoryGroupRow<T, I> => ({
    key,
    header,
    level,
    count: getItems ? grp.reduce((s, x) => s + getItems(x).length, 0) : grp.length,
    sum: grp.reduce((s, x) => s + getSum(x), 0),
    ...(getQty ? { sumQty: Math.round(grp.reduce((s, x) => s + getQty(x), 0) * 10000) / 10000 } : {}),
    ...(getItems ? { items: grp.flatMap(getItems) } : {}),
    item: null,
  })
  for (const g of sorted) {
    const cat = getCategory(g)
    if (cat !== curCat) {
      curCat = cat
      curType = null
      rows.push(headerRow(`c-${curCat}`, curCat, 1, sorted.filter(x => getCategory(x) === curCat)))
    }
    if (mode === 'category_type') {
      const type = getProductType(g)
      if (type !== curType) {
        curType = type
        rows.push(headerRow(`c-${curCat}-t-${type}`, type, 2, sorted.filter(x => getCategory(x) === curCat && getProductType(x) === curType)))
      }
    }
    rows.push(itemRow(g))
  }
  return rows
}

export function leftGroupInfo(actual: FeoActualItem): FeoLeftGroupInfo {
  const stages = actual.stages || []
  const contract = stages.find(s => s.key === 'contract')
  const purchase = stages.find(s => s.key === 'purchase')
  const chosen = contract || purchase
  if (chosen) {
    return {
      name: chosen.name || '',
      quantity: chosen.quantity,
      unit: chosen.unit,
      unitPrice: chosen.unit_price,
      total: chosen.total,
      isContract: !!contract,
    }
  }
  return {
    name: actual.item_name,
    quantity: actual.quantity,
    unit: actual.unit,
    unitPrice: actual.unit_price,
    total: actual.total_price,
    isContract: false,
  }
}
