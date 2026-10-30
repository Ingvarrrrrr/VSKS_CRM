// feoItemLock.ts — единый текст и предикат «категория ФЭО заблокирована, т.к.
// позиция ЗАГРУЖЕНА из Плана закупок» (ПРАВИЛО №6): один и тот же текст и
// одна и та же проверка используются и в шапке закупки
// (CreateOrderView.vue::FeoTreeSelect), и в построчных пикерах категории
// (ItemsTableFlat/ItemsTableStages/ItemsCardsView — те же компоненты рендерит
// и WishFormDialog.vue через PurchaseItemsEditor), а не копия текста/условия
// в каждом файле. Владелец (2026-09-20, сужено 14.10.2026 — жалоба (а)):
// «категория закупки из заявки не меняется, менять — в плане» — НО это
// касается только позиций, РЕАЛЬНО загруженных из плана (from_plan), а не
// любой позиции с wish_item_id/feo_planned_item_id (та связь появляется и у
// ручных позиций — автозаведённая плановая или выбор человеком, см.
// app/services/feo_item_lock.py). Бэкенд (app/routers/purchases.py::_guard_feo_
// category_change_after_approval + app/routers/purchase_items_edit.py::
// _guard_item_feo_category_locked_from_plan, оба читают is_item_feo_locked) уже
// отклоняет такую правку 422 (FEO_CATEGORY_LOCKED_FROM_WISH /
// ITEM_FEO_CATEGORY_LOCKED_FROM_PLAN) — этот предикат лишь UX-подсказка ДО
// отправки запроса, самой проверки не подменяет.
export const FEO_CATEGORY_LOCKED_HINT =
  'Категория взята из Плана закупок — меняется в плане, до формирования закупки/заявки'

export interface FeoLockableItem {
  wish_item_id?: number | null
  feo_planned_item_id?: number | null
  from_plan?: boolean | null
}

// Позиция закупки/заявки заблокирована, если она ЗАГРУЖЕНА из Плана закупок
// (from_plan — mirrors PurchaseItem.from_plan/WishItem.from_plan) — ровно то
// же условие, что и backend is_item_feo_locked (app/services/feo_item_lock.py,
// не копия формулы, а зеркало для мгновенной UI-подсказки). Простая связь
// wish_item_id/feo_planned_item_id БЕЗ from_plan (ручная позиция) больше не
// блокирует — см. жалобу (а).
export function isItemFeoCategoryLocked(item: FeoLockableItem | null | undefined): boolean {
  if (!item) return false
  return !!item.from_plan
}

// Короткая подпись для чипа у заблокированного пикера — показывается только
// у позиций, реально загруженных из плана (см. isItemFeoCategoryLocked выше),
// либо (isWishStage=true) у ЛЮБОЙ позиции заявки с feo_planned_item_id — см.
// isWishItemCategoryLockedByPlan ниже.
export function feoLockChipLabel(item: FeoLockableItem | null | undefined, isWishStage = false): string | null {
  if (!item) return null
  if (item.from_plan) return item.wish_item_id != null ? 'из заявки' : 'из плана'
  if (isWishStage && item.feo_planned_item_id != null) return 'из плана'
  return null
}

// Владелец (пакет 2, 22.10.2026, заявка №209): «категория позиции по плану не
// меняется» — ШИРЕ, чем isItemFeoCategoryLocked (from_plan) выше: В ЗАЯВКЕ
// (isWishStage=true) ЛЮБАЯ позиция с feo_planned_item_id блокирует выбор
// категории построчно, не только from_plan-позиции из «Закупка по плану».
// Сервер держит это же правило безусловно для WishItem (ПРАВИЛО №6, см.
// app/services/wish_item_category_guard.py) — этот предикат только UI-замок ДО
// отправки запроса. isWishStage=false (закупка, по умолчанию) — поведение НЕ
// меняется, функция всегда false (редактор общий с закупкой, см. докстринг
// isItemFeoCategoryLocked выше).
export function isWishItemCategoryLockedByPlan(
  item: FeoLockableItem | null | undefined, isWishStage: boolean,
): boolean {
  if (!isWishStage || !item) return false
  return item.feo_planned_item_id != null
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

// Владелец (сессия 2026-10-29, закупки PEE-2026-00957/РЕЕ-2026-00912):
// «привязка позиции к плановой должна быть видна всегда» — строка с категорией
// ФЭО/плановой позицией (feo-attrs-row в ItemsTableFlat.vue/ItemsTableStages.vue,
// её аналог в ItemsCardsView.vue) раньше рендерилась ТОЛЬКО при feoPerItem/
// allowPerItemPlan и пропадала целиком, если позиция уже привязана, но режим
// построчного ФЭО выключен — привязка «терялась» из вида. Единый предикат
// (ПРАВИЛО №6, не копия по трём файлам): строка показывается ДОПОЛНИТЕЛЬНО,
// когда у позиции есть собственная категория/узел ФЭО или плановая позиция,
// независимо от режима; редактирование остаётся под теми же условиями, что
// и раньше (см. feoPerItem/allowPerItemPlan в вызывающих компонентах).
export interface FeoBoundItem {
  feo_planned_item_id?: number | null
  feo_category_id?: number | null
  feo_node_id?: number | null
}

export function hasFeoBinding(item: FeoBoundItem | null | undefined): boolean {
  if (!item) return false
  return item.feo_planned_item_id != null || item.feo_category_id != null || item.feo_node_id != null
}
