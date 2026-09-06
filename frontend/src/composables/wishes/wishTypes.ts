// wishTypes.ts — общие типы модуля «Заявки», вынесены из WishesView.vue при
// разбиении файла на компоненты/композаблы (см. WishesView.vue, useWishesContext.ts).
// Поведение не меняется — это чистый перенос интерфейсов без изменений.

// Владелец, 2026-08-13: снимок сопоставленной позиции закупки — приходит на каждой
// позиции карточки заявки (GET /wishes/{id}). В списке заявок этого поля нет.
export interface PurchaseMatch {
  match_method: 'wish_item_id' | 'item_name' | 'item_name_qty' | 'item_name_ambiguous'
  ambiguous_candidates_count?: number | null
  purchase_item_id?: number | null
  purchase_id?: number | null
  purchase_number?: string | null
  purchase_status?: string | null
  purchase_stopped_at?: string | null
  feo_category_id?: number | null
  feo_category_name?: string | null
  quantity?: number | null
  unit_price?: number | null
  total_price?: number | null
}

// Пункт 4 (владелец, 2026-08-13): сводка закупки для меню «Перейти в закупку»
// (см. WishPurchaseSummary в backend/app/schemas/wishes.py).
export interface WishPurchaseSummary {
  id: number
  purchase_number?: number | null
  registry_number?: string | null
  item_name?: string | null
  status?: string | null
  status_label?: string | null
  amount?: number | string | null
  stopped_at?: string | null
}

export interface WishItem {
  item_name: string
  item_type: string
  quantity: number
  unit: string
  unit_price: number
  total_price: number
  country_origin: string
  feo_category_id?: number | null
  purchase_match?: PurchaseMatch | null
}

export interface Wish {
  id: number
  org_id: number
  title: string
  subsidy_id?: number
  subsidy_name?: string
  feo_category_id?: number
  assigned_to?: number
  assigned_to_name?: string
  priority?: string
  desired_date?: string
  justification?: string
  status: 'draft' | 'submitted' | 'approved' | 'rejected' | 'converted'
  rejection_reason?: string
  // Владелец, 2026-08-19: «нужно, чтобы было видно, кто отклонил» — переживает
  // сброс approver_names/цепочки при отклонении (см. backend Wish.rejected_by).
  rejected_by?: number | null
  rejected_at?: string | null
  rejected_by_name?: string | null
  created_by: number
  creator_name?: string
  approved_by?: number
  approver_name?: string
  purchase_id?: number
  items_count?: number
  total_amount?: number
  created_at: string
  updated_at: string
  event_id?: number | null
  event_name?: string | null
  assignee_name?: string
  executor_id?: number | null
  executor_name?: string | null
  execution_deadline?: string | null
  member_names?: string[]
  approver_names?: string[]
  purchase_ids?: number[]
  purchases?: WishPurchaseSummary[]
  contracted_locked?: boolean
  // Правка владельца (2026-08-18): человекочитаемая причина блокировки — номер
  // закупки и её реальная стадия, вместо захардкоженного «на этапе «Договор»».
  contracted_locked_reason?: string | null
  items?: WishItem[]
  // Владелец, 2026-08-13: сумма заявки (Σ total_price позиций) — приходит с бэка
  // батчем в списке; если поле ещё не подъехало (параллельная разработка), считаем
  // сами из items на фронте (см. wishItemsTotal).
  items_total?: number | string | null
  // Остановка заявки (владелец, 2026-08-13, POST /{id}/stop)
  stopped_at?: string | null
  stopped_by?: number | null
  stopped_by_name?: string | null
  stopped_reason?: string | null
  stopped_partial?: boolean
  // Task 2 (сессия 2026-08-17): контрагент заявки — необязателен. contractor_id — из
  // справочника; contractor_name — ручной ввод, если контрагента в справочнике ещё нет;
  // contractor_display_name — готовое имя для показа, считает backend (только чтение).
  contractor_id?: number | null
  contractor_name?: string | null
  contractor_display_name?: string | null
  // Владелец, 2026-08-19: тумблер вернули — режим «одна на всех» / «каждой позиции своя»,
  // NOT NULL колонка бэкенда (см. backend/app/schemas/wishes.py::WishOut.feo_per_item).
  feo_per_item?: boolean
  // Владелец, 2026-09-04: 'advance_report' — заявка уже переоформлена в авансовый
  // отчёт (см. backend app/models/wish.py::Wish.source) — либо это авто-компаньон
  // прямого создания авансового, либо результат «Оформить как авансовый отчёт».
  source?: string | null
  // Дополнительные поля, читаемые через (wish as any) в исходном файле —
  // добавлены явно, чтобы не плодить (as any) по всем новым файлам.
  quantity?: number | null
  estimated_price?: number | null
  vat_mode?: string | null
  approval_mode?: string | null
  // Phase 31-06: бейдж «чужих правок с последнего просмотра».
  unseen_changes_count?: number | null
  // Показывается в карточках (cards view), приходит с бэка на некоторых выборках.
  registry_number?: string | null
}

export interface Subsidy {
  id: number
  name: string
  org_id?: number
}

export interface FeoCategory {
  id: number
  name: string
  subsidy_id?: number
  parent_id?: number | null
}

export interface EventItem { id: number; name: string; subsidy_id: number; is_active?: boolean }

export interface User {
  id: number
  full_name: string
  org_id?: number
}

// Wish members
export interface WishMember {
  id: number
  wish_id: number
  user_id: number
  role: string
  added_by_id: number | null
  consent_pending: boolean
  username: string | null
  full_name: string | null
  added_by_name: string | null
}
export interface PendingWishConsent {
  wish_id: number
  wish_member_id: number
  title: string
  org_id: number | null
  status: string | null
  added_by_name: string | null
  created_at: string | null
}

// Wish approvers (multi-approver cascade)
export interface WishApprover {
  id: number
  wish_id: number
  user_id: number | null
  order_num: number
  role_name: string | null
  full_name: string | null
  is_auto: boolean
  status: string  // pending / approved / rejected / skipped
  comment: string | null
  decided_at: string | null
  decided_by_user_id: number | null
  // Задача 1 (сессия 2026-08-20): кто РЕАЛЬНО принял решение и решал ли не за
  // себя — бэкенд отдаёт оба поля в GET /approvers и в ответе decide.
  decided_by_name?: string | null
  is_on_behalf?: boolean
}

export interface ExcessWarningItem { name: string; amount: number }
export interface ExcessWarning {
  category_id: number
  category_name: string
  budget: number | null
  plan_after: number
  excess_amount: number
  items: ExcessWarningItem[]
}

export interface PurchaseSyncItem { name: string; quantity?: number | null; amount?: number | null }
export interface PurchaseSyncItemChange { name: string; was?: string | number | null; now?: string | number | null }
// QA-правки (2026-08-21, дефекты 2-3 «потеря данных при повторном согласовании»):
// items_conflicted — поля, которые правили ПРЯМО В ЗАКУПКЕ после переноса (значение
// разошлось со снимком planned_*) — из заявки НЕ перезаписаны, показываем конфликт,
// а не молча теряем правку. items_kept_manual — строки закупки без связи с заявкой
// (заведены закупщиком в самой закупке) — при сверке не удаляются; сообщаем, что
// они остались, чтобы не выглядело, будто их «забыли».
export interface PurchaseSyncItemConflict { name: string; field: string; in_purchase?: number | null; in_wish?: number | null }
export interface PurchaseSync {
  purchase_id: number
  registry_number?: string | null
  subject_before?: string | null
  subject_after?: string | null
  items_added?: PurchaseSyncItem[]
  items_removed?: PurchaseSyncItem[]
  items_changed?: PurchaseSyncItemChange[]
  items_conflicted?: PurchaseSyncItemConflict[]
  items_kept_manual?: PurchaseSyncItem[]
  blocked_reason?: string | null
}
