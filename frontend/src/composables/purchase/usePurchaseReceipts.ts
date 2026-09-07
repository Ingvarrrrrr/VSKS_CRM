// Чеки закупки (Phase 21: multi-receipts) — QR-скан / JSON-импорт / удаление /
// пересчёт позиций из чеков. Вынесено из CreateOrderView.vue без изменения
// поведения. Ручной ввод чека (диалог) уже был вынесен раньше в
// composables/purchase/useManualReceipt.ts + components/purchase/ManualReceiptDialog.vue —
// эта волна его не трогает, а только принимает openManualReceiptDialog как параметр,
// чтобы не заводить второй механизм ручного ввода (ПРАВИЛО №6).
import { ref, type ComputedRef } from 'vue'
import { apiFetch } from '@/api'
import { decodeQrFromImageFile } from '@/utils/qrDecode'
import type { ToastType } from '@/composables/useToast'

export interface Receipt {
  id: number
  purchase_id: number
  fiscal_drive_number?: string | null
  fiscal_document_number?: number | null
  fiscal_sign?: string | null
  receipt_datetime?: string | null
  total_sum?: number | string | null
  seller_name?: string | null
  seller_inn?: string | null
  retail_place?: string | null
  operator?: string | null
  source?: string | null
  created_at?: string | null
}

export interface ReceiptsFormSlice {
  subsidy_id: number | null | undefined
  purchase_method?: string | null
}

// Экспортируется — save() в CreateOrderView.vue проверяет наличие отложенного
// действия (не показывать снэк «Закупка создана», если сейчас откроется QR/JSON/
// ручной ввод по этому ключу). Один источник ключа (ПРАВИЛО №6).
export const POST_SAVE_ACTION_KEY = 'advance_report_post_save_action'

export function usePurchaseReceipts(
  purchaseId: ComputedRef<number | null>,
  formMode: ComputedRef<string>,
  isEdit: ComputedRef<boolean>,
  form: ReceiptsFormSlice,
  showSnack: (text: string, color?: ToastType, opts?: { actionText?: string; onAction?: () => void; duration?: number }) => void,
  guideArrowTo: (target: string) => void,
  save: () => Promise<void>,
  loadPurchase: () => Promise<void>,
  openManualReceiptDialog: () => void,
  logRefetchDebug?: () => void,
) {
  const receipts = ref<Receipt[]>([])

  function sourceLabel(s?: string | null) {
    if (!s) return '—'
    return ({ json_import: 'JSON', qr_scan: 'QR', manual: 'Вручную' } as Record<string, string>)[s] || s
  }

  async function loadReceipts() {
    if (!purchaseId.value) return
    try {
      receipts.value = await apiFetch<Receipt[]>(`/purchases/${purchaseId.value}/receipts`)
    } catch {
      /* silent — no receipts is fine */
    }
  }

  const qrScanShow = ref(false)

  async function ensureSavedThen(action: 'scan_qr' | 'upload_json' | 'manual_receipt') {
    if (purchaseId.value) return true
    if (!form.subsidy_id && formMode.value !== 'advance_report') {
      showSnack('Сначала выберите субсидию (вверху страницы)', 'warning', {
        actionText: 'Показать поле',
        onAction: () => guideArrowTo('subsidy'),
      })
      guideArrowTo('subsidy')
      return false
    }
    sessionStorage.setItem(POST_SAVE_ACTION_KEY, action)
    await save()
    // save() либо успешно перенаправит (тогда после loadPurchase сработает action),
    // либо покажет snack с ошибкой валидации (FEO/etc) — флаг останется до следующей попытки.
    return false
  }

  async function onScanQrClick() {
    if (!(await ensureSavedThen('scan_qr'))) return
    qrScanShow.value = true
  }

  async function onJsonBtnClick() {
    if (!(await ensureSavedThen('upload_json'))) return
    document.querySelector<HTMLInputElement>('input[type=file][accept="image/*,.json"]')?.click()
  }

  async function onManualBtnClick() {
    if (!(await ensureSavedThen('manual_receipt'))) return
    openManualReceiptDialog()
  }

  const recomputeLoading = ref(false)
  async function recomputeFromReceipts() {
    if (!purchaseId.value) return
    recomputeLoading.value = true
    try {
      const result = await apiFetch<any>(
        `/purchases/${purchaseId.value}/recompute-from-receipts`,
        { method: 'POST' }
      )
      const msg = `Обновлено позиций: ${result.items_updated}, прикреплено файлов чеков: ${result.files_attached}, добавлено записей закр.документов: ${result.acceptance_docs_added}`
      showSnack(msg, 'success')
      await loadPurchase()
    } catch (e: any) {
      showSnack(e?.message || 'Не удалось пересчитать', 'error')
    } finally {
      recomputeLoading.value = false
    }
  }

  function consumePostSaveAction() {
    if (!purchaseId.value) return
    if (formMode.value !== 'advance_report' && formMode.value !== 'order') return
    const pending = sessionStorage.getItem(POST_SAVE_ACTION_KEY)
    if (!pending) return
    sessionStorage.removeItem(POST_SAVE_ACTION_KEY)
    if (pending === 'scan_qr') qrScanShow.value = true
    else if (pending === 'upload_json') {
      document.querySelector<HTMLInputElement>('input[type=file][accept="image/*,.json"]')?.click()
    }
    else if (pending === 'manual_receipt') openManualReceiptDialog()
  }

  // Дубликат чека может лежать в обычной закупке или в авансовом отчёте — это
  // разные документы с разными карточками. Бэкенд отдаёт признак is_advance в
  // detail (RECEIPT_DUPLICATE), чтобы не угадывать вид документа по тексту.
  function receiptDuplicateOpenAction(det: any) {
    const ref = det.purchase_ref || `#${det.purchase_id}`
    const pid = det.purchase_id
    const isAdvance = !!det.is_advance
    const path = isAdvance ? `/advance-reports/${pid}/edit` : `/orders/${pid}`
    const fallbackMessage = isAdvance
      ? `Такой авансовый отчёт уже есть — № ${ref}. Этот чек уже был загружен в него.`
      : `Чек был загружен ранее в закупку № ${ref}.`
    const actionText = isAdvance ? `Открыть авансовый отчёт № ${ref}` : `Открыть закупку № ${ref}`
    return { fallbackMessage, actionText, onAction: () => window.open(path, '_blank') }
  }

  async function onQrDetected(qr: string) {
    qrScanShow.value = false
    if (!purchaseId.value) {
      showSnack('Сначала сохраните закупку', 'error')
      return
    }
    try {
      const existingIds = new Set(receipts.value.map(r => r.id))
      const created = await apiFetch<{ id: number }>(
        `/purchases/${purchaseId.value}/receipts/from-qr-fetch`,
        { method: 'POST', body: { qr } as any },
      )
      await loadReceipts()
      if (isEdit.value) {
        await new Promise(r => setTimeout(r, 50))
        await loadPurchase()
        logRefetchDebug?.()
      }
      if (created?.id && existingIds.has(created.id)) {
        showSnack('Этот чек уже был загружен ранее', 'warning')
      } else {
        showSnack('Чек получен из ФНС, позиции добавлены')
      }
    } catch (e: any) {
      const p = e?.payload
      const code = p?.code
      const det = (p?.details && typeof p.details === 'object') ? p.details : null
      if (code === 'RECEIPT_DUPLICATE' && det?.purchase_id) {
        const { fallbackMessage, actionText, onAction } = receiptDuplicateOpenAction(det)
        showSnack(p.message || fallbackMessage, 'warning', { actionText, onAction })
      } else if (code === 'FNS_RATE_LIMIT') {
        showSnack(p?.message || 'ФНС временно ограничила запросы', 'warning')
      } else {
        showSnack(e?.message || 'Не удалось получить чек из ФНС', 'error')
      }
    }
  }

  async function onJsonReceiptUpload(e: Event) {
    const input = e.target as HTMLInputElement
    const files = Array.from(input.files || [])
    if (!files.length || !purchaseId.value) {
      if (input) input.value = ''
      return
    }
    const existingIds = new Set(receipts.value.map(r => r.id))
    let added = 0
    let dups = 0
    let qrFails = 0
    for (const f of files) {
      const isImage = (f.type || '').startsWith('image/') || /\.(png|jpe?g|webp|heic|heif)$/i.test(f.name)
      try {
        if (isImage) {
          const qr = await decodeQrFromImageFile(f)
          if (!qr) { qrFails++; continue }
          const r = await apiFetch<Receipt>(
            `/purchases/${purchaseId.value}/receipts/from-qr-fetch`,
            { method: 'POST', body: { qr } as any },
          )
          if (r?.id != null) {
            if (existingIds.has(r.id)) dups++
            else { added++; existingIds.add(r.id) }
          }
        } else {
          const fd = new FormData()
          fd.append('file', f)
          const res = await apiFetch<Receipt[]>(
            `/purchases/${purchaseId.value}/receipts/import-json`,
            { method: 'POST', body: fd as any }
          )
          for (const r of (res || [])) {
            if (existingIds.has(r.id)) dups++
            else { added++; existingIds.add(r.id) }
          }
        }
      } catch (err: any) {
        const p2 = err?.payload
        const code2 = p2?.code
        const det2 = (p2?.details && typeof p2.details === 'object') ? p2.details : null
        if (code2 === 'RECEIPT_DUPLICATE' && det2?.purchase_id) {
          const { fallbackMessage, actionText, onAction } = receiptDuplicateOpenAction(det2)
          showSnack(p2.message || fallbackMessage, 'warning', { actionText, onAction })
        } else if (code2 === 'FNS_RATE_LIMIT') {
          showSnack(p2?.message || 'ФНС временно ограничила запросы', 'warning')
        } else {
          showSnack(err?.message || `Ошибка обработки ${f.name}`, 'error')
        }
      }
    }
    input.value = ''
    await loadReceipts()
    if (isEdit.value && purchaseId.value) {
      await new Promise(r => setTimeout(r, 50))
      await loadPurchase()
      logRefetchDebug?.()
    }
    const parts: string[] = []
    if (added) parts.push(`добавлено: ${added}`)
    if (dups) parts.push(`уже было: ${dups}`)
    if (qrFails) parts.push(`QR не распознан: ${qrFails}`)
    if (parts.length) showSnack(parts.join(', '), qrFails && !added ? 'warning' : 'success')
  }

  async function deleteReceipt(id: number) {
    if (!purchaseId.value) return
    if (!confirm('Удалить чек? Связанные позиции в закупке останутся.')) return
    try {
      await apiFetch(`/purchases/${purchaseId.value}/receipts/${id}`, { method: 'DELETE' })
      await loadReceipts()
    } catch (e: any) {
      showSnack(e?.message || 'Ошибка удаления', 'error')
    }
  }

  return {
    receipts, sourceLabel, loadReceipts,
    qrScanShow, onScanQrClick, onJsonBtnClick, onManualBtnClick,
    recomputeLoading, recomputeFromReceipts,
    consumePostSaveAction, onQrDetected, onJsonReceiptUpload, deleteReceipt,
  }
}
