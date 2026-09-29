// feoItemLock.ts — единый текст и предикат «категория ФЭО заблокирована, т.к.
// закупка/позиция пришла из заявки и плана закупок» (ПРАВИЛО №6): один и тот
// же текст и одна и та же проверка используются и в шапке закупки
// (CreateOrderView.vue::FeoTreeSelect), и в построчных пикерах категории
// (ItemsTableFlat/ItemsTableStages/ItemsCardsView — те же компоненты рендерит
// и WishFormDialog.vue через PurchaseItemsEditor), а не копия текста/условия
// в каждом файле. Владелец (2026-09-20): «категория закупки из заявки не
// меняется, менять — в плане». Бэкенд (app/routers/purchases.py::_guard_feo_
// category_change_after_approval + app/routers/purchase_items_edit.py::
// _guard_item_feo_category_locked_from_plan) уже отклоняет такую правку 422
// (FEO_CATEGORY_LOCKED_FROM_WISH / ITEM_FEO_CATEGORY_LOCKED_FROM_PLAN) — этот
// предикат лишь UX-подсказка ДО отправки запроса, самой проверки не подменяет.
export const FEO_CATEGORY_LOCKED_HINT =
  'Категория взята из заявки и плана закупок — меняется в плане, до формирования закупки'

export interface FeoLockableItem {
  wish_item_id?: number | null
  feo_planned_item_id?: number | null
}

// Позиция закупки заблокирована, если она пришла из заявки (wish_item_id —
// W1: hard link на WishItem, см. app/models/purchase_item.py) ИЛИ привязана к
// плановой позиции (feo_planned_item_id) — ровно то же условие, что и в
// backend-гейде _guard_item_feo_category_locked_from_plan (не копия формулы,
// а зеркало для мгновенной UI-подсказки).
export function isItemFeoCategoryLocked(item: FeoLockableItem | null | undefined): boolean {
  if (!item) return false
  return item.wish_item_id != null || item.feo_planned_item_id != null
}

// Короткая подпись для чипа у заблокированного пикера — wish_item_id
// приоритетнее (позиция целиком родом из заявки), иначе — привязка к плану.
export function feoLockChipLabel(item: FeoLockableItem | null | undefined): string | null {
  if (!item) return null
  if (item.wish_item_id != null) return 'из заявки'
  if (item.feo_planned_item_id != null) return 'из плана'
  return null
}

// Шапочный замок категории ФЭО закупки (CreateOrderView.vue::FeoTreeSelect).
// Баг 2026-09-29 (авансовый отчёт РЕЕ-2026-00960): purchase.wish_id ставится
// ДЛЯ ЛЮБОГО авансового отчёта — у него всегда есть заявка-компаньон
// «на возмещение» (см. backend/app/routers/purchases.py::create_purchase,
// ветка is_advance, и app/services/wish_advance_conversion.py), но эта заявка
// НЕ источник плана — она создаётся ПОСЛЕ закупки, только чтобы завести
// маршрут согласования возмещения. Прежнее условие `!!purchaseData?.wish_id`
// принимало любую такую закупку за «рождённую из заявки/плана» и намертво
// блокировало выбор категории — ровно симметрично backend-гейду
// _guard_feo_category_change_after_approval в purchases.py (тот же баг был и
// там: проверял голый wish_id, а не purchase_method). Один и тот же предикат
// на фронте и бэке (ПРАВИЛО №6): замок только если закупка НЕ авансовая.
export interface FeoHeaderLockableItem {
  wish_id?: number | null
  purchase_method?: string | null
}

export function isPurchaseFeoHeaderLocked(p: FeoHeaderLockableItem | null | undefined): boolean {
  if (!p) return false
  if (p.wish_id == null) return false
  return p.purchase_method !== 'advance'
}
