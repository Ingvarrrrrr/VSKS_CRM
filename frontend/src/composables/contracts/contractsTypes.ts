// contractsTypes.ts — общие интерфейсы реестра договоров.
// Дословный перенос из ContractsView.vue, без изменения полей.
import type { PurchaseAmounts } from '@/types/purchaseAmounts'

export interface ContractSubsidyItem { id: number; subsidy_id: number; subsidy_name?: string }

export interface Contract {
  id: number
  number: string
  date?: string
  contract_type: string
  purchase_method?: string
  contractor_id?: number
  contractor_name?: string
  contractor_inn?: string
  reimbursement_user_id?: number | null
  reimbursement_user_name?: string | null
  multi_contractor_label?: string | null
  subsidy_id?: number
  subsidy_name?: string
  extra_subsidies?: ContractSubsidyItem[]
  subject?: string
  max_amount?: number
  total_ordered?: number
  total_paid?: number
  remaining?: number
  start_date?: string
  end_date?: string
  status?: string
  notes?: string
  planned_monthly?: number
  // Владелец, 2026-09-02: состояние согласования рамочной ГОЛОВЫ (см. contracts.py::list_contracts) —
  // 'pending' | 'approved' | null. Затемняем строку/карточку только при 'pending'.
  approval_state?: string | null
}

export interface Subsidy { id: number; name: string; year: number }
export interface Contractor { id: number; name: string; inn?: string }
export interface PurchaseItem { item_name: string; quantity?: number; unit_price?: number; total_price?: number }
export interface Purchase {
  id: number
  registry_number?: string
  purchase_number?: number
  subject?: string
  item_name?: string
  contract_price?: number
  status: string
  etp_url?: string | null
  items?: PurchaseItem[]
  purchase_method?: string | null
  amounts?: PurchaseAmounts | null
}
