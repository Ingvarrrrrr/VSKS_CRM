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
  // Квик-план 2026-10-06 (statement-control): контрольный итог сверху окна
  // «Сверка» — «привязано N из M платёжек · A из B ₽ · не хватает C ₽».
  statement_count?: number
  attached_count?: number
  unattached_count?: number
  unattached_total?: number
  unattached_numbers?: string[]
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
  // Строка листа «закупка N, заказ M» (квик-план 06.10) — null, если бэкенд
  // ещё не прислал (старый контракт), тогда показываем только РЕЕ.
  sheet_ref?: string | null
}

// «Почти совпало» — подсказки к непривязанной платёжке (status=registry_only),
// квик-план 2026-10-06: тот же ИНН/акт/сумма нескольких заказов, причина
// словами владельца собирается на фронте по коду reason.
export type PaymentControlNearMissReason = 'amount_close' | 'same_act' | 'orders_sum' | string

export interface PaymentControlNearMiss {
  purchase_id: number
  registry_number: string | null
  subject: string | null
  contractor_name: string | null
  amount: number
  delta: number
  reason: PaymentControlNearMissReason
  can_fix_amount: boolean
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
  // Только для status==='registry_only' — подсказки «почти совпало».
  near_miss?: PaymentControlNearMiss[]
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

  // Выгрузка контрольного листа в Excel (квик-план 06.10) — файл, не JSON:
  // тот же способ скачивания, что и useFleetExport.ts (fetch + bearer-токен +
  // blob), apiFetch здесь не подходит — он парсит JSON-ответ.
  const exporting = ref(false)
  async function exportXlsx(subsidyId: number): Promise<void> {
    exporting.value = true
    try {
      const token = localStorage.getItem('auth_token') || ''
      const res = await fetch(`/api/subsidies/${subsidyId}/payment-control/export.xlsx`, {
        headers: { Authorization: `Bearer ${token}` },
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

  return {
    data, loading, loadError, load, reload,
    codesData, codesLoading, codesSaving, loadCodes, saveCodes,
    fetchCandidates, attachPurchase, createPurchaseFromPayment,
    exporting, exportXlsx,
  }
}
