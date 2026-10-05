// Подтверждение перевода закупки в «Оплачено» по найденной в банковской
// выписке оплате — согласующие субсидии видят запрос и подтверждают/отклоняют
// его. Контракт бэкенда: GET /api/subsidies/{id}/paid-confirmations?status=pending,
// GET /api/purchases/{id}/paid-confirmation, POST /api/paid-confirmations/{id}/confirm,
// POST /api/paid-confirmations/{id}/reject (body {comment}, обязателен).
//
// Один источник этой логики (ПРАВИЛО №6): и панель на странице «Субсидии»
// (PaidConfirmationsPanel.vue), и плашка в карточке закупки (PaymentsBlock.vue)
// используют этот composable, а не дублируют fetch/confirm/reject.
import { ref } from 'vue'
import { apiFetch } from '@/api'

export interface PaidConfirmationPayment {
  id: number
  payment_date: string | null
  document_number: string | null
  amount: number | string | null
  payment_purpose: string | null
}

export interface PaidConfirmationPurchase {
  id: number
  registry_number: string | null
  subject: string | null
  contractor_name: string | null
  contract_price: number | string | null
  payment_amount: number | string | null
  status: string | null
  // Может отсутствовать в старом ответе бэкенда (до добавления поля) — везде
  // читать опционально, не падать.
  status_label?: string | null
}

export interface PaidConfirmation {
  id: number
  purchase_id: number
  subsidy_id: number
  status: 'pending' | 'confirmed' | 'rejected' | string
  requested_at: string | null
  amount_confirmed: number | string | null
  decided_by: string | null
  decided_at: string | null
  comment: string | null
  purchase: PaidConfirmationPurchase
  payments: PaidConfirmationPayment[]
  // Причина, почему подтвердить сейчас нельзя (напр. нет закрывающих
  // документов) — может отсутствовать в старом ответе, не падать.
  blocked_reason?: string | null
  // Превышение плана по категории ФЭО — информационное, НЕ блокирует
  // подтверждение (в отличие от blocked_reason). Может отсутствовать.
  plan_excess_warning?: string | null
}

export function usePaidConfirmations() {
  const items = ref<PaidConfirmation[]>([])
  const loading = ref(false)
  const loadError = ref<string | null>(null)
  // id запросов, для которых сейчас идёт подтверждение/отклонение (кнопки-лоадеры)
  const actingId = ref<number | null>(null)

  async function loadPending(subsidyId: number | null | undefined) {
    if (!subsidyId) { items.value = []; return }
    loading.value = true
    loadError.value = null
    try {
      const res = await apiFetch<{ items: PaidConfirmation[] }>(
        `/subsidies/${subsidyId}/paid-confirmations?status=pending`,
      )
      items.value = res.items || []
    } catch (e: any) {
      loadError.value = e?.payload?.message || e?.detail || e?.message || 'Не удалось загрузить запросы на подтверждение оплаты'
      items.value = []
    } finally {
      loading.value = false
    }
  }

  async function loadForPurchase(purchaseId: number | null | undefined): Promise<PaidConfirmation | null> {
    if (!purchaseId) return null
    try {
      return await apiFetch<PaidConfirmation | null>(`/purchases/${purchaseId}/paid-confirmation`)
    } catch {
      return null
    }
  }

  async function confirm(id: number): Promise<PaidConfirmation> {
    actingId.value = id
    try {
      const updated = await apiFetch<PaidConfirmation>(`/paid-confirmations/${id}/confirm`, { method: 'POST' })
      items.value = items.value.filter(it => it.id !== id)
      return updated
    } finally {
      actingId.value = null
    }
  }

  async function reject(id: number, comment: string): Promise<PaidConfirmation> {
    actingId.value = id
    try {
      const updated = await apiFetch<PaidConfirmation>(`/paid-confirmations/${id}/reject`, {
        method: 'POST',
        body: JSON.stringify({ comment }),
      })
      items.value = items.value.filter(it => it.id !== id)
      return updated
    } finally {
      actingId.value = null
    }
  }

  return { items, loading, loadError, actingId, loadPending, loadForPurchase, confirm, reject }
}
