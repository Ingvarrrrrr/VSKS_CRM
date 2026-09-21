// Единственный источник правила «тип позиции → товары/услуги» на фронте —
// зеркалит backend/app/services/item_type_split.py (kind_of/purchase_type_shares,
// normalize_item_type из backend/app/routers/feo_planned_items.py). План
// ancient-prancing-music.md, раздел A/C1 (21.09.2026), Правило №6 проекта — не
// заводить второй словарь нормализации типа ни на фронте, ни по компонентам:
// KpiCardsWidget.vue/SubsidyKpiCards.vue/StageFeoDrillDialog.vue читают только
// отсюда.
export type ItemTypeKind = 'goods' | 'services' | 'unspecified'

export const KIND_GOODS: ItemTypeKind = 'goods'
export const KIND_SERVICES: ItemTypeKind = 'services'
export const KIND_UNSPECIFIED: ItemTypeKind = 'unspecified'

export const KIND_LABELS: Record<ItemTypeKind, string> = {
  goods: 'товары',
  services: 'услуги',
  unspecified: 'без типа',
}

// Владелец (21.09, AskUserQuestion): работы считаются услугами; пустой/непонятный
// тип — отдельная корзина «без типа» (нельзя молча приписывать к товарам).
function normalizeItemType(raw?: string | null): 'товар' | 'услуга' | 'работа' | null {
  if (!raw) return null
  const s = String(raw).trim().toLowerCase()
  if (!s) return null
  if (s.startsWith('тов')) return 'товар'
  if (s.startsWith('усл')) return 'услуга'
  if (s.startsWith('раб')) return 'работа'
  return null
}

export function kindOf(itemType?: string | null): ItemTypeKind {
  const n = normalizeItemType(itemType)
  if (n === 'товар') return KIND_GOODS
  if (n === 'услуга' || n === 'работа') return KIND_SERVICES
  return KIND_UNSPECIFIED
}

export interface TypeShares { goods: number; services: number; unspecified: number }

export interface ShareableItem {
  item_type?: string | null
  total_price?: number | string | null
}

// Зеркалит purchase_type_shares() (item_type_split.py) — доли (0..1) по Σ
// total_price позиций закупки; закупка без позиций/с нулевыми суммами → всё
// «без типа» (как и на бэкенде, молчаливое приписывание к товарам запрещено).
export function purchaseTypeShares(items: ShareableItem[] | null | undefined): TypeShares {
  let g = 0, s = 0, u = 0
  for (const it of items || []) {
    const amt = Number(it?.total_price) || 0
    const k = kindOf(it?.item_type)
    if (k === KIND_GOODS) g += amt
    else if (k === KIND_SERVICES) s += amt
    else u += amt
  }
  const total = g + s + u
  if (total <= 0) return { goods: 0, services: 0, unspecified: 1 }
  const goods = g / total
  const services = s / total
  return { goods, services, unspecified: 1 - goods - services }
}

// Доля ОДНОЙ позиции внутри Σ total_price её закупки — используется, чтобы
// разложить сумму этапа закупки (effectivePrice) по её позициям
// (StageFeoDrillDialog.vue, режим typeKind, план раздел C1): сумма позиции на
// этапе = amount_этапа_закупки × item.total_price / Σ item.total_price. Эта же
// доля, применённая ко ВСЕМ позициям одного kind, в сумме даёт РОВНО ту же
// величину, что и purchaseTypeShares(...)[kind] × amount_этапа — те же числа,
// что покажет карточка (Правило №6, один источник формулы деления).
// Закупка без валидных сумм позиций (Σ ⩽ 0) — 0 (как и purchaseTypeShares,
// деньги молча ни одной позиции не приписываются).
export function itemShareOfPurchase(item: ShareableItem, items: ShareableItem[] | null | undefined): number {
  const all = items || []
  const total = all.reduce((sum, it) => sum + (Number(it?.total_price) || 0), 0)
  if (total <= 0) return 0
  return (Number(item?.total_price) || 0) / total
}

// Кумулятивные статусы закупки для каждого накопительного этапа KPI-карточек —
// единственный источник для расшифровки по клику (StageFeoDrillDialog) и на
// дашборде (DashboardView.vue), и в карточке субсидии (SubsidyKpiCards.vue) —
// не дублировать таблицу по компонентам. 'budget'/'free' сюда намеренно не
// входят — это не список закупок конкретного статуса (бюджет/остаток
// считаются деревом ФЭО), для них расшифровка по клику не открывается.
export const KPI_STAGE_CUMULATIVE_STATUSES: Record<string, string[]> = {
  plan_schedule: ['plan_schedule', 'work_in_progress', 'contracted', 'ordered', 'delivered', 'paid'],
  work: ['work_in_progress', 'contracted', 'ordered', 'delivered', 'paid'],
  ordered: ['ordered', 'delivered', 'paid'],
  // 'Заключено договоров' на бэкенде считается из Contract (framework_cumulative/
  // single/framework_with_amount, см. app.services.dashboard_type_split), а не
  // напрямую по Purchase.status — приближение по статусам закупок здесь
  // информативно, но сумма расшифровки может не сойтись до копейки с карточкой.
  contracts: ['contracted', 'ordered', 'delivered', 'paid'],
  delivered: ['delivered', 'paid'],
  delivered_unpaid: ['delivered'],
  paid: ['paid'],
}

// Есть ли у этапа список закупок для расшифровки по клику (StageFeoDrillDialog,
// typeKind-режим) — 'budget'/'free' считаются деревом ФЭО, не списком закупок
// одного статуса, поэтому их строки товары/услуги НЕкликабельны (владелец,
// приёмка 21.09: «мёртвая подсветка» без диалога). Единственный источник
// признака — KpiCardsWidget.vue/SubsidyKpiCards.vue проверяют ЭТУ функцию,
// не свой список ключей (Правило №6).
export function hasStageDrill(stage: string): boolean {
  return stage in KPI_STAGE_CUMULATIVE_STATUSES
}

// Три допустимых значения поля «Тип» плановой позиции ФЭО/товара каталога
// (владелец, 21.09, раздел W2 плана corrections-21-09.md) — зеркалит ITEM_TYPES
// (backend/app/services/item_types.py). Единственный источник вариантов для
// v-select «Тип» на фронте — PlannedItemAddDialog.vue, PlannedItemEditDialog.vue,
// FeoLevel5Panel.vue (инлайн-правка колонки «Тип»), ProductFormDialog.vue и
// FullProductDialog.vue (селект «Товар/Услуга» на самом товаре каталога) читают
// ЭТОТ список, второй такой же массив по компонентам не заводим (Правило №6).
export const ITEM_TYPE_OPTIONS: { value: 'товар' | 'услуга' | 'работа'; title: string }[] = [
  { value: 'товар', title: 'Товар' },
  { value: 'услуга', title: 'Услуга' },
  { value: 'работа', title: 'Работа' },
]

export const KPI_STAGE_LABELS: Record<string, string> = {
  plan_schedule: 'План-график',
  work: 'Ведётся работа',
  ordered: 'Заказано',
  contracts: 'Заключено договоров',
  delivered: 'Поставлено',
  delivered_unpaid: 'Поставлено, не оплачено',
  paid: 'Оплачено',
}
