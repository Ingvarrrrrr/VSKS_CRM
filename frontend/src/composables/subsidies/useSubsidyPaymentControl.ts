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
//   POST /subsidies/{id}/payment-control/bank-payments/{bp_id}/attach-combo { purchase_ids, merge_purchases }
//   GET  /subsidies/{id}/payment-control/find-discrepancy?amount=...
//   POST /subsidies/{id}/payment-control/bank-payments/{bp_id}/create-purchase  { feo_category_id? }
import { ref } from 'vue'
import { apiFetch } from '@/api'
import { useLatestRequest } from '@/composables/useLatestRequest'

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
  statement_count?: number
  attached_count?: number
  unattached_count?: number
  unattached_total?: number
  unattached_numbers?: string[]
  in_other_subsidies_count?: number
  in_other_subsidies_total?: number
}

export interface PaymentControlOtherSubsidy {
  id: number
  name: string
  count: number
  total: number
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
  | 'duplicate' | 'not_reconciled' | 'declared_unconfirmed' | 'in_other_subsidy'

export interface PaymentControlRowOtherSubsidy {
  id: number
  name: string
}

export interface PaymentControlRowPurchase {
  id: number
  registry_number: string | null
  subject: string | null
  amount: number
  sheet_ref?: string | null
}

export type PaymentControlNearMissReason = 'amount_close' | 'same_act' | 'orders_sum' | string

export interface PaymentControlNearMiss {
  purchase_id: number
  purchase_ids?: number[]
  registry_number: string | null
  subject: string | null
  contractor_name: string | null
  amount: number
  delta: number
  reason: PaymentControlNearMissReason
  probability?: 'high' | 'medium' | 'low'
  probability_label?: string
  coherence_reason?: string
  can_fix_amount: boolean
  can_merge?: boolean
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
  near_miss?: PaymentControlNearMiss[]
  other_subsidy?: PaymentControlRowOtherSubsidy | null
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
  other_subsidies?: PaymentControlOtherSubsidy[]
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

export interface PaymentControlComboItem {
  purchase_id: number
  registry_number: string | null
  subject: string | null
  amount: number
  contractor_id: number | null
  contractor_name: string | null
  feo_category_name: string | null
  product_category: string | null
  semantic_cluster: string | null
  sheet_ref: string | null
}

export interface PaymentControlComboSuggestion {
  purchase_ids: number[]
  items: PaymentControlComboItem[]
  total_amount: number
  delta: number
  count: number
  score: number
  probability: 'high' | 'medium' | 'low'
  probability_label: string
  coherence_reason: string
  can_merge: boolean
}

export interface PaymentControlSignErrorHint {
  purchase_id: number
  registry_number: string | null
  subject: string | null
  amount: number
  discrepancy_explained: number
  contractor_name: string | null
  feo_category_name: string | null
  sheet_ref: string | null
  reason: string
}

export interface PaymentControlCandidatesResponse {
  items: PaymentControlCandidate[]
  combo_suggestions?: PaymentControlComboSuggestion[]
  sign_error_hints?: PaymentControlSignErrorHint[]
}

export interface PaymentControlDiscrepancyResponse {
  target_amount: number
  combo_suggestions: PaymentControlComboSuggestion[]
  sign_error_hints: PaymentControlSignErrorHint[]
}

export interface PaymentControlBatchComboMatch {
  bank_payment_id: number
  payment_number: string | null
  payment_date: string | null
  amount: number
  payee_name: string | null
  payee_inn: string | null
  purpose_text: string | null
  combo: PaymentControlComboSuggestion
}

export interface PaymentControlBatchCombosResponse {
  unattached_payments_count: number
  matches_count: number
  matches: PaymentControlBatchComboMatch[]
}

export function useSubsidyPaymentControl() {
  const data = ref<PaymentControlData | null>(null)
  const loading = ref(false)
  const loadError = ref<string | null>(null)

  const codesData = ref<PaymentControlCodesResponse | null>(null)
  const codesLoading = ref(false)
  const codesSaving = ref(false)

  let currentSubsidyId: number | null | undefined = null
  const loadGuard = useLatestRequest()
  const codesGuard = useLatestRequest()

  async function load(subsidyId: number | null | undefined) {
    currentSubsidyId = subsidyId
    const token = loadGuard.next()
    if (!subsidyId) { data.value = null; return }
    loading.value = true
    loadError.value = null
    try {
      const res = await apiFetch<PaymentControlData>(`/subsidies/${subsidyId}/payment-control`)
      if (!loadGuard.isCurrent(token)) return
      data.value = res
    } catch (e: any) {
      if (!loadGuard.isCurrent(token)) return
      loadError.value = e?.payload?.message || e?.detail || e?.message || 'Не удалось загрузить сверку по выписке'
      data.value = null
    } finally {
      if (loadGuard.isCurrent(token)) loading.value = false
    }
  }

  async function reload() {
    if (currentSubsidyId) await load(currentSubsidyId)
  }

  async function loadCodes(subsidyId: number | null | undefined) {
    const token = codesGuard.next()
    if (!subsidyId) { codesData.value = null; return }
    codesLoading.value = true
    try {
      const res = await apiFetch<PaymentControlCodesResponse>(`/subsidies/${subsidyId}/payment-control/codes`)
      if (!codesGuard.isCurrent(token)) return
      codesData.value = res
    } finally {
      if (codesGuard.isCurrent(token)) codesLoading.value = false
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
    const res = await apiFetch<PaymentControlCandidatesResponse>(
      `/subsidies/${subsidyId}/payment-control/bank-payments/${bpId}/candidates`,
    )
    return res.items || []
  }

  async function fetchCandidatesFull(subsidyId: number, bpId: number): Promise<PaymentControlCandidatesResponse> {
    return apiFetch<PaymentControlCandidatesResponse>(
      `/subsidies/${subsidyId}/payment-control/bank-payments/${bpId}/candidates`,
    )
  }

  async function attachPurchase(
    subsidyId: number,
    bpId: number,
    purchaseId: number,
    fixAmount?: boolean,
  ): Promise<{ ok: boolean; warnings: string[]; fixed_amount?: { from: number; to: number } }> {
    return apiFetch(`/subsidies/${subsidyId}/payment-control/bank-payments/${bpId}/attach`, {
      method: 'POST',
      body: JSON.stringify(fixAmount ? { purchase_id: purchaseId, fix_amount: true } : { purchase_id: purchaseId }),
    })
  }

  async function attachCombo(
    subsidyId: number,
    bpId: number,
    purchaseIds: number[],
    mergePurchases = true,
  ): Promise<{ ok: boolean; merged: boolean; primary_purchase_id: number; registry_number: string | null; merged_count: number; warnings: string[] }> {
    return apiFetch(`/subsidies/${subsidyId}/payment-control/bank-payments/${bpId}/attach-combo`, {
      method: 'POST',
      body: JSON.stringify({ purchase_ids: purchaseIds, merge_purchases: mergePurchases }),
    })
  }

  async function findDiscrepancy(
    subsidyId: number,
    amount: number,
  ): Promise<PaymentControlDiscrepancyResponse> {
    return apiFetch<PaymentControlDiscrepancyResponse>(
      `/subsidies/${subsidyId}/payment-control/find-discrepancy?amount=${encodeURIComponent(amount)}`,
    )
  }

  const exporting = ref(false)
  async function exportXlsx(subsidyId: number): Promise<void> {
    exporting.value = true
    try {
      const res = await fetch(`/api/subsidies/${subsidyId}/payment-control/export.xlsx`, {
        headers: {},
      })
      if (!res.ok) {
        let msg = `HTTP ${res.status}`
        try { const j = await res.json(); if (j?.message) msg = j.message } catch { /* not json */ }
        throw new Error(msg)
      }
      const blob = await res.blob()
      const cd = res.headers.get('Content-Disposition') ?? ''
      const match = cd.match(/filename[^;=\n]*=(?:(['"])(.+?)\1|([^;\n]+))/i)
      const filename = (match ? (match[2] ?? match[3]) : null)?.trim() || `Сверка_выписки_${subsidyId}.xlsx`
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } finally {
      exporting.value = false
    }
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

  async function getBatchCombos(subsidyId: number): Promise<PaymentControlBatchCombosResponse> {
    return apiFetch<PaymentControlBatchCombosResponse>(`/subsidies/${subsidyId}/payment-control/batch-combos`)
  }

  async function batchApplyCombos(
    subsidyId: number,
    matches: { bank_payment_id: number; purchase_ids: number[]; merge_purchases: boolean }[],
  ): Promise<{ applied: number; errors: { bank_payment_id: number; error: string }[] }> {
    return apiFetch(`/subsidies/${subsidyId}/payment-control/batch-apply-combos`, {
      method: 'POST',
      body: JSON.stringify({ matches }),
    })
  }

  return {
    data, loading, loadError, load, reload,
    codesData, codesLoading, codesSaving, loadCodes, saveCodes,
    fetchCandidates, fetchCandidatesFull, attachPurchase, attachCombo, findDiscrepancy, createPurchaseFromPayment,
    exporting, exportXlsx,
    getBatchCombos, batchApplyCombos,
  }
}
