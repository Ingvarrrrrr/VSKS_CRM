// ordersTypes.ts — общие типы модуля «Закупки» (OrdersView.vue и его
// компоненты/композаблы в components/orders и composables/orders).
// Дословный перенос интерфейсов из OrdersView.vue, без изменения поведения.
import type { PurchaseAmounts } from '@/types/purchaseAmounts'

export interface PurchaseItem {
  id: number
  item_name: string
  item_type?: string
  quantity?: number
  unit?: string
  unit_price?: number
  total_price?: number
  feo_category_id?: number | null
}

export interface Subsidy { id: number; name: string; year: number }
export interface Contractor { id: number; name: string; inn?: string }

export interface Purchase {
  id: number
  purchase_number?: number
  item_name?: string
  contractor_id?: number
  contractor_name?: string
  contractor_inn?: string
  reimbursement_user_id?: number | null
  reimbursement_user_name?: string | null
  multi_contractor_label?: string | null
  feo_category_name?: string
  feo_category_id?: number
  subsidy_name?: string
  subsidy_id?: number
  subject?: string
  planned_total_price?: number
  total_nmck?: number
  purchase_method?: string
  purchase_basis?: string
  purchase_contract_type?: string
  registry_number?: string
  responsible_person?: string
  assigned_user_id?: number
  contract_price?: number
  framework_contract_total?: number | string | null
  delivery_payment_amount?: number
  status: string
  substatus?: string
  is_monthly_payment?: boolean
  delivery_date?: string
  contract_number?: string
  contract_date?: string
  acceptance_doc_name?: string
  acceptance_doc_date?: string
  acceptance_doc_number?: string
  acceptance_doc_amount?: number
  payment_doc_number?: string
  payment_doc_date?: string
  payment_amount?: number
  // Владелец (2026-08-19): «заявлено, ждёт подтверждения» — см. PaymentsBlock.vue
  payment_amount_declared?: number
  items?: PurchaseItem[]
  approval_status?: string
  execution_term?: string
  // Phase 26-K
  agreement_number?: string
  agreement_date?: string
  order_number?: string
  order_date?: string
  // Phase 32: file count from backend
  files_count?: number
  // Задача владельца 2026-08-12: «согласовали заявку — закупка всё равно
  // создаётся, но на ней должен стоять значок превышения ФЭО». Поля опциональны —
  // пока бэкенд их не отдаёт (или список не запрошен с with_feo_excess=true),
  // просто нет чипа, без ошибок.
  feo_excess?: boolean
  feo_excess_hint?: string | null
  // QA-правка (2026-08-21, дефект 4): согласованное превышение больше НЕ гасит
  // feo_excess (см. _compute_purchase_feo_excess) — состояние отдельно в
  // feo_excess_state: 'not_requested' | 'pending' | 'approved' | 'none'. Чип
  // не может красить любое feo_excess красным с текстом про блокировку —
  // approved-превышение уже никого не блокирует.
  feo_excess_state?: 'not_requested' | 'pending' | 'approved' | 'none' | null
  // Остановка закупки (владелец, 2026-08-13, см. POST /api/wishes/{wish_id}/stop) —
  // read-only, проставляется системой при остановке заявки. Закупка НЕ удаляется —
  // просто помечается, чтобы видна была история.
  stopped_at?: string | null
  stopped_by?: number | null
  stopped_by_name?: string | null
  stopped_wish_id?: number | null
  // Владелец (2026-09-02): «уведомление глобально, если позиция категории ФЭО
  // вверху и в каждом товаре не соответствует друг другу — об этом должен быть
  // алярм прям стоять». Считается ВСЕГДА бэкендом (не под флагом, в отличие от
  // feo_excess) — см. app.routers.purchases._compute_purchase_feo_mismatch.
  feo_mismatch?: boolean
  feo_mismatch_items?: { item_id: number; item_name: string; message: string; reason: string }[]
  // ПРАВИЛО №6 (2026-09-05/06): единый расчёт суммы закупки — см.
  // backend/app/services/purchase_amounts.py. Optional/null — защита на
  // случай, если конкретный ответ бэкенда его не проставил.
  amounts?: PurchaseAmounts | null
}

export interface FilterPreset {
  name: string
  subsidyId: number | null
  status: string
  search: string
  types?: string[]
  contractorIds?: number[]
}

export interface ExportColumn { key: string; label: string; group: string }

export interface QuickFile { id: number; filename: string; mime_type?: string; size?: number; file_type?: string }

export interface ImportError { row: number; name: string; missing?: string[]; message?: string }
export interface ImportPreviewPurchase {
  group_key: string; contract_number?: string; contractor?: string; feo_path?: string
  items_count: number; plan_total?: number; fact_total?: number; status?: string
  skipped: boolean; skip_reason?: string; payments_count?: number
  purchase_group?: string; order_number?: string
  duplicate_matches?: Array<{ source: 'db' | 'file'; id: number | null; purchase_number: string | null; name: string; amount: number; status: string | null; contract_date: string | null }>
  event_id?: number | null; event_name?: string | null
}
export interface ImportPreview {
  purchases: ImportPreviewPurchase[]
  skipped: number
  errors: ImportError[]
  warnings?: ImportError[]
  without_event?: number
  payments_count?: number
  payments_total?: number
  payments_errors?: Array<{ row?: number; contract_number?: string; message?: string }>
  duplicates_count?: number
  feo_to_create?: Array<{ level: number; name: string; path: string }>
  subsidy_has_feo?: boolean
}
export interface ImportResult {
  created_purchases: number; created_items: number; skipped: number; errors: ImportError[]
  warnings?: ImportError[]
  without_event?: number
  created_payments?: number
}

export interface ScanFolder {
  folder: string; inn?: string; sum?: number; purchase_id?: number; contract_number?: string
  files: { name: string; file_type?: string; doc_format?: string }[]
  status: 'attached' | 'skipped'; reason?: string
}
export interface ScanPreviewResult { dry_run: boolean; attached: number; skipped: number; folders: ScanFolder[] }
export interface ScanResult { attached: number; skipped: number }

export interface PaymentMatchGroupItem { kind: string; bank_payment_id: number; amount: number; basis_label?: string | null; reason?: string }
export interface PaymentMatchGroupRow { group_key: string; registry_number: string | null; items: PaymentMatchGroupItem[] }
export interface PaymentMatchReport {
  subsidy_id: number
  dry_run: boolean
  groups_total: number
  attached: PaymentMatchGroupRow[]
  ambiguous: PaymentMatchGroupRow[]
  not_found: { group_key: string; registry_number: string | null }[]
  suspicious: any[]
}
