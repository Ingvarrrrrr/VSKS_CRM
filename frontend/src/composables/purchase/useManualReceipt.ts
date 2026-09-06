// Ручной ввод чека (Phase 21) — отдельный маленький диалог внутри общей фичи
// «Чеки» (QR/JSON-импорт остаются в CreateOrderView.vue, эта волна выносит
// только ручной ввод). Вынесено без изменения поведения.
import { reactive, type ComputedRef } from 'vue'
import { apiFetch } from '@/api'
import { numOrNull } from '@/utils/numberFormat'
import type { ToastType } from '@/composables/useToast'

export function useManualReceipt(
  purchaseId: ComputedRef<number | null>,
  showSnack: (text: string, color?: ToastType, opts?: { actionText?: string; onAction?: () => void; duration?: number }) => void,
  loadReceipts: () => Promise<void>,
) {
  const manualReceiptDialog = reactive({
    show: false,
    saving: false,
    error: '',
    form: {
      fiscal_drive_number: '',
      fiscal_document_number: null as number | null,
      fiscal_sign: '',
      receipt_datetime: '',
      total_sum: null as number | null,
      seller_name: '',
      seller_inn: '',
      retail_place: '',
    },
  })

  function openManualReceiptDialog() {
    manualReceiptDialog.error = ''
    manualReceiptDialog.form = {
      fiscal_drive_number: '',
      fiscal_document_number: null,
      fiscal_sign: '',
      receipt_datetime: '',
      total_sum: null,
      seller_name: '',
      seller_inn: '',
      retail_place: '',
    }
    manualReceiptDialog.show = true
  }

  async function saveManualReceipt() {
    if (!purchaseId.value) return
    manualReceiptDialog.saving = true
    manualReceiptDialog.error = ''
    try {
      const payload: any = { source: 'manual' }
      const f = manualReceiptDialog.form
      if (f.fiscal_drive_number) payload.fiscal_drive_number = f.fiscal_drive_number
      // fiscal_document_number/total_sum — v-model.number; `!= null` не ловит '' после
      // очистки поля. При null поле в payload не попадает вовсе (как и раньше для
      // остальных необязательных полей формы). numOrNull: '' → null, 0 сохраняется
      // как число.
      const fiscalDocNumber = numOrNull(f.fiscal_document_number)
      if (fiscalDocNumber != null) payload.fiscal_document_number = fiscalDocNumber
      if (f.fiscal_sign) payload.fiscal_sign = f.fiscal_sign
      if (f.receipt_datetime) payload.receipt_datetime = f.receipt_datetime
      const totalSum = numOrNull(f.total_sum)
      if (totalSum != null) payload.total_sum = totalSum
      if (f.seller_name) payload.seller_name = f.seller_name
      if (f.seller_inn) payload.seller_inn = f.seller_inn
      if (f.retail_place) payload.retail_place = f.retail_place
      await apiFetch(`/purchases/${purchaseId.value}/receipts`, {
        method: 'POST',
        body: JSON.stringify(payload) as any,
      })
      manualReceiptDialog.show = false
      await loadReceipts()
      showSnack('Чек добавлен')
    } catch (e: any) {
      manualReceiptDialog.error = e?.message || 'Ошибка сохранения'
    } finally {
      manualReceiptDialog.saving = false
    }
  }

  return { manualReceiptDialog, openManualReceiptDialog, saveManualReceipt }
}
