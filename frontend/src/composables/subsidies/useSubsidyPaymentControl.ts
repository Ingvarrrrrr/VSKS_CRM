// Контроль «выписка ↔ закупки» по субсидии — сверка исполненных платежей из
// банковской выписки со статьями расходов и закупками. Один источник данных
// (ПРАВИЛО №6) для баннера (SubsidyPaymentControlBanner.vue) и диалога
// (SubsidyPaymentControlDialog.vue + вкладки) — оба читают это состояние, не
// дублируют fetch. Контракт бэкенда — см. .planning/quick/2026-10-05-payment-control/PLAN.md:
//   GET  /subsidies/{id}/payment-control
//   GET  /subsidies/{id}/payment-control/codes
//   PUT  /subsidies/{id}/payment-control/codes            { codes }
//   GET  /subsidies/{id}/payment-control/bank-payments/{bp_id}/candidates
//   POST /subsidies/{id}/payment-control/bank-payments/{bp_id}/attach       { purchase_id }
//   POST /subsidies/{id}/payment-control/bank-payments/{bp_id}/create-purchase  { feo_category_id? }
import { ref } from 'vue'
import { apiFetch } from '@/api'

export interface PaymentControlTotals {
  executed_total: number
  executed_count: number
  reconciled_total: number
  found_in_purchases: number
  difference: number
  not_reconciled_total: number
  not_executed_count: number
  not_executed_total: number
  unknown_code_total: number
  from_payment_unrefined_count: number
}

export interface PaymentControlCounts {
  match: number
  amount_mismatch: number
  registry_only: number
  purchases_only: number
  duplicate: number
  not_reconciled: number
  declared_unconfirmed: number
}

export type PaymentControlArticleKind =
  | 'товар' | 'услуга' | 'работа' | 'персонал' | 'налог' | 'накладные' | 'аванс' | 'командировка' | 'прочее' | string

export interface PaymentControlArticle {
  code: string
  name: string
  kind: PaymentControlArticleKind
  is_procurement: boolean
  search_purchase: boolean
  unknown: boolean
  statement_total: number
  statement_count: number
  matched_total: number
  difference: number
}

export type PaymentControlRowStatus =
  | 'match' | 'amount_mismatch' | 'registry_only' | 'purchases_only'
  | 'duplicate' | 'not_reconciled' | 'declared_unconfirmed'

export interface PaymentControlRowPurchase {
  id: number
  registry_number: string | null
  subject: string | null
  amount: number
}

export interface PaymentControlRow {
  key: string
  bank_payment_ids: number[]
  payment_number: string | null
  payment_date: string | null
  payee_name: string | null
  payee_inn: string | null
  amount: number
  purpose_text: string | null
  expense_code: string | null
  expense_name: string | null
  status: PaymentControlRowStatus
  purchases: PaymentControlRowPurchase[]
  amount_diff: number
  unknown_code: boolean
  duplicate_with: string[]
}

export interface PaymentControlNotExecuted {
  id: number
  payment_number: string | null
  payment_date: string | null
  status: string
  payee_name: string | null
  amount: number
}

export interface PaymentControlData {
  as_of: string | null
  alarm: boolean
  totals: PaymentControlTotals
  counts: PaymentControlCounts
  articles: PaymentControlArticle[]
  rows: PaymentControlRow[]
  not_executed: PaymentControlNotExecuted[]
}

export interface PaymentControlDirectoryEntry {
  code: string
  name: string
  kind: PaymentControlArticleKind
  is_procurement: boolean
}

export interface PaymentControlCodesResponse {
  codes: string[]
  is_default: boolean
  directory: PaymentControlDirectoryEntry[]
}

export interface PaymentControlCandidate {
  purchase_id: number
  registry_number: string | null
  subject: string | null
  contractor_name: string | null
  contract_price: number | null
  paid_by_statement: number | null
  reason: string | null
}

export function useSubsidyPaymentControl() {
  const data = ref<PaymentControlData | null>(null)
  const loading = ref(false)
  const loadError = ref<string | null>(null)

  const codesData = ref<PaymentControlCodesResponse | null>(null)
  const codesLoading = ref(false)
  const codesSaving = ref(false)

  let currentSubsidyId: number | null | undefined = null

  async function load(subsidyId: number | null | undefined) {
    currentSubsidyId = subsidyId
    if (!subsidyId) { data.value = null; return }
    loading.value = true
    loadError.value = null
    try {
      data.value = await apiFetch<PaymentControlData>(`/subsidies/${subsidyId}/payment-control`)
    } catch (e: any) {
      loadError.value = e?.payload?.message || e?.detail || e?.message || 'Не удалось загрузить сверку по выписке'
      data.value = null
    } finally {
      loading.value = false
    }
  }

  async function reload() {
    if (currentSubsidyId) await load(currentSubsidyId)
  }

  async function loadCodes(subsidyId: number | null | undefined) {
    if (!subsidyId) { codesData.value = null; return }
    codesLoading.value = true
    try {
      codesData.value = await apiFetch<PaymentControlCodesResponse>(`/subsidies/${subsidyId}/payment-control/codes`)
    } finally {
      codesLoading.value = false
    }
  }

  async function saveCodes(subsidyId: number, codes: string[]): Promise<PaymentControlCodesResponse> {
    codesSaving.value = true
    try {
      const res = await apiFetch<PaymentControlCodesResponse>(`/subsidies/${subsidyId}/payment-control/codes`, {
        method: 'PUT',
        body: JSON.stringify({ codes }),
      })
      codesData.value = res
      return res
    } finally {
      codesSaving.value = false
    }
  }

  async function fetchCandidates(subsidyId: number, bpId: number): Promise<PaymentControlCandidate[]> {
    const res = await apiFetch<{ items: PaymentControlCandidate[] }>(
      `/subsidies/${subsidyId}/payment-control/bank-payments/${bpId}/candidates`,
    )
    return res.items || []
  }

  async function attachPurchase(subsidyId: number, bpId: number, purchaseId: number): Promise<{ ok: boolean; warnings: string[] }> {
    return apiFetch(`/subsidies/${subsidyId}/payment-control/bank-payments/${bpId}/attach`, {
      method: 'POST',
      body: JSON.stringify({ purchase_id: purchaseId }),
    })
  }

  async function createPurchaseFromPayment(
    subsidyId: number,
    bpId: number,
    feoCategoryId?: number | null,
  ): Promise<{ purchase_id: number; registry_number: string | null; warnings: string[] }> {
    return apiFetch(`/subsidies/${subsidyId}/payment-control/bank-payments/${bpId}/create-purchase`, {
      method: 'POST',
      body: JSON.stringify(feoCategoryId != null ? { feo_category_id: feoCategoryId } : {}),
    })
  }

  return {
    data, loading, loadError, load, reload,
    codesData, codesLoading, codesSaving, loadCodes, saveCodes,
    fetchCandidates, attachPurchase, createPurchaseFromPayment,
  }
}
