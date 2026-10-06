// Подтверждение перевода закупки в «Оплачено» по найденной в банковской
// выписке оплате — согласующие субсидии видят запрос и подтверждают/отклоняют
// его. Контракт бэкенда: GET /api/subsidies/{id}/paid-confirmations?status=pending,
// GET /api/purchases/{id}/paid-confirmation, POST /api/paid-confirmations/{id}/confirm,
// POST /api/paid-confirmations/{id}/reject (body {comment}, обязателен),
// POST /api/subsidies/{id}/paid-confirmations/check (body {ids}, ≤20).
//
// Один источник этой логики (ПРАВИЛО №6): и панель на странице «Субсидии»
// (PaidConfirmationsPanel.vue), и плашка в карточке закупки (PaymentsBlock.vue)
// используют этот composable, а не дублируют fetch/confirm/reject.
//
// Перф-доработка 2026-10-06: список pending по субсидии с ~120 строками
// раньше гонял симуляцию перехода НА КАЖДУЮ строку на бэкенде (40-60+ с,
// таймаут фронта REQUEST_TIMEOUT_MS=60000 в api.ts). Теперь список отдаёт
// checked=false для pending без blocked_reason/реального plan_excess_warning —
// панель дозапрашивает проверку порциями через checkRows().
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
  // true — blocked_reason/plan_excess_warning для этой строки прошли
  // реальную симуляцию перехода (одиночный GET/confirm/reject — всегда;
  // список по субсидии — только после checkRows()). false/отсутствует —
  // список ещё не проверял эту строку, кнопка «Подтвердить» должна быть
  // недоступна, чтобы не дать 409 без предупреждения.
  checked?: boolean
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

  // Проверка порции (≤20) pending-строк, уже лежащих в items — мержит
  // результат в тот же массив (реактивно, по id), не трогает остальные поля.
  // Ошибку не глотаем — панель показывает причину и даёт повторить.
  async function checkRows(subsidyId: number | null | undefined, ids: number[]): Promise<void> {
    if (!subsidyId || !ids.length) return
    const res = await apiFetch<{ items: Array<{ id: number; blocked_reason: string | null; plan_excess_warning: string | null }> }>(
      `/subsidies/${subsidyId}/paid-confirmations/check`,
      { method: 'POST', body: JSON.stringify({ ids }) },
    )
    const byId = new Map(res.items.map(it => [it.id, it]))
    items.value = items.value.map(row => {
      const found = byId.get(row.id)
      if (!found) return row
      return { ...row, blocked_reason: found.blocked_reason, plan_excess_warning: found.plan_excess_warning, checked: true }
    })
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

  return { items, loading, loadError, actingId, loadPending, loadForPurchase, checkRows, confirm, reject }
}
