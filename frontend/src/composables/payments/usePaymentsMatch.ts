// usePaymentsMatch.ts — диалог привязки платежа (PaymentMatchDialog) и откат
// подтверждения (unbind). Дословный перенос из PaymentRegistryView.vue.
import { ref } from 'vue'
import { apiFetch } from '@/api'
import type { BankPayment } from './paymentsTypes'

export function usePaymentsMatch(options: {
  // @updated из PaymentMatchDialog: перезагрузить реестр И (если открыта) сверку
  onMatchUpdated: () => void
  // Успешный откат подтверждения: перезагрузить реестр (сверка НЕ обновляется —
  // так было в исходном doUnbind, отличие от onMatchUpdated сохранено намеренно)
  loadPayments: () => void
  success: (msg: string) => void
  error: (msg: string) => void
}) {
  const { onMatchUpdated, loadPayments, success, error } = options

  // ── Match dialog ─────────────────────────────────────────────────────────
  const matchDialog = ref(false)
  const selectedPaymentId = ref<number | null>(null)

  function openMatch(item: BankPayment) {
    selectedPaymentId.value = item.id
    matchDialog.value = true
  }

  function openConfirm(item: BankPayment) {
    // Open match dialog with pre-loaded contract for confirmation flow
    selectedPaymentId.value = item.id
    matchDialog.value = true
  }

  function openMatchById(bpId: number) {
    // Открываем PaymentMatchDialog поверх сверки (диалог-над-диалогом OK)
    selectedPaymentId.value = bpId
    matchDialog.value = true
  }

  // ── Unbind ───────────────────────────────────────────────────────────────
  const unbindDialog = ref(false)
  const unbindingId = ref<number | null>(null)
  const unbindLoading = ref(false)

  function unbind(item: BankPayment) {
    unbindingId.value = item.id
    unbindDialog.value = true
  }

  async function doUnbind() {
    if (!unbindingId.value) return
    unbindLoading.value = true
    try {
      await apiFetch(`/payments/registry/${unbindingId.value}/unbind`, { method: 'POST' })
      success('Подтверждение откатено')
      unbindDialog.value = false
      loadPayments()
    } catch (e: any) {
      error('Ошибка при откате: ' + (e.detail || ''))
    } finally {
      unbindLoading.value = false
      unbindingId.value = null
    }
  }

  return {
    matchDialog, selectedPaymentId,
    openMatch, openConfirm, openMatchById,
    onMatchUpdated,
    unbindDialog, unbindingId, unbindLoading,
    unbind, doUnbind,
  }
}
