// Чеки закупки (Phase 21: multi-receipts) — QR-скан / загрузка файлов по очереди /
// пересчёт позиций из чеков. Файловые хелперы вынесены в usePurchaseReceiptFiles.ts (< 500 строк).
import { ref, type ComputedRef } from 'vue'
import { apiFetch } from '@/api'
import { decodeQrFromImageFile } from '@/utils/qrDecode'
import type { ToastType } from '@/composables/useToast'
import {
  receiptDuplicateOpenAction,
  usePurchaseReceiptFiles,
  type ReceiptFile,
} from './usePurchaseReceiptFiles'

export type { ReceiptFile }

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

export const POST_SAVE_ACTION_KEY = 'advance_report_post_save_action'
export const RECEIPT_FILE_ACCEPT = '.json,.pdf,.html,.htm,.png,.jpg,.jpeg,.webp,.tif,.tiff,.jtif,.jfif,.heic'
export const RECEIPT_FILE_HINT = 'PDF/фото/TIFF/JTIF/HEIC с QR, HTML (proverkacheka), JSON ФНС'

let pendingDroppedFiles: File[] | null = null

export function usePurchaseReceipts(
  purchaseId: ComputedRef<number | null>,
  formMode: ComputedRef<string>,
  isEdit: ComputedRef<boolean>,
  form: ReceiptsFormSlice,
  showSnack: (text: string, color?: ToastType, opts?: { actionText?: string; onAction?: () => void; duration?: number }) => void,
  guideArrowTo: (target: string) => void,
  save: () => Promise<boolean>,
  loadPurchase: () => Promise<void>,
  openManualReceiptDialog: () => void,
  logRefetchDebug?: () => void,
) {
  const receipts = ref<Receipt[]>([])
  const {
    receiptFiles,
    receiptFileThumbs,
    loadReceiptFiles,
    attachReceiptFile,
    deleteReceiptFile,
  } = usePurchaseReceiptFiles(purchaseId, showSnack)

  function sourceLabel(s?: string | null) {
    if (!s) return '—'
    return ({ json_import: 'JSON', qr_scan: 'QR', manual: 'Вручную', html_import: 'HTML' } as Record<string, string>)[s] || s
  }

  async function loadReceipts() {
    if (!purchaseId.value) return
    try {
      receipts.value = await apiFetch<Receipt[]>(`/purchases/${purchaseId.value}/receipts`)
    } catch {
      /* silent */
    }
  }

  const qrScanShow = ref(false)

  async function ensureSavedThen(action: 'scan_qr' | 'upload_json' | 'manual_receipt', beforeSave?: () => void) {
    if (purchaseId.value) return true
    if (!form.subsidy_id && formMode.value !== 'advance_report') {
      showSnack('Сначала выберите субсидию (вверху страницы)', 'warning', {
        actionText: 'Показать поле',
        onAction: () => guideArrowTo('subsidy'),
      })
      guideArrowTo('subsidy')
      return false
    }
    beforeSave?.()
    sessionStorage.setItem(POST_SAVE_ACTION_KEY, action)
    await save()
    return false
  }

  async function onScanQrClick() {
    if (!(await ensureSavedThen('scan_qr'))) return
    qrScanShow.value = true
  }

  async function onJsonBtnClick() {
    if (!(await ensureSavedThen('upload_json'))) return
    document.querySelector<HTMLInputElement>(`input[type=file][accept="${RECEIPT_FILE_ACCEPT}"]`)?.click()
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
      const saved = await save()
      if (!saved) return
      const result = await apiFetch<any>(
        `/purchases/${purchaseId.value}/recompute-from-receipts`,
        { method: 'POST' },
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
      if (pendingDroppedFiles && pendingDroppedFiles.length) {
        const filesToUpload = pendingDroppedFiles
        pendingDroppedFiles = null
        onJsonReceiptUpload(filesToUpload)
      } else {
        document.querySelector<HTMLInputElement>(`input[type=file][accept="${RECEIPT_FILE_ACCEPT}"]`)?.click()
      }
    } else if (pending === 'manual_receipt') {
      openManualReceiptDialog()
    }
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
        { method: 'POST', body: { qr } as any, suppressErrorDialog: true },
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
      } else if (code === 'FNS_RATE_LIMIT' || code === 'RECEIPT_PENDING') {
        showSnack(p?.message || 'ФНС ещё не вернула данные по чеку', 'warning', { duration: 10000 })
      } else if ((e?.status ?? 0) >= 500) {
        showSnack(
          p?.message || 'Шлюз проверки чеков ФНС временно не отвечает — повторите через минуту или введите вручную',
          'warning',
          { duration: 9000 },
        )
      } else {
        showSnack(e?.message || 'Не удалось получить чек из ФНС', 'error')
      }
    }
  }

  async function onJsonReceiptUpload(files: File[]) {
    if (!files.length) return
    if (!purchaseId.value) {
      await ensureSavedThen('upload_json', () => {
        pendingDroppedFiles = files
        showSnack('Черновик сохраняется — файл будет обработан автоматически после сохранения', 'info')
      })
      return
    }

    const existingIds = new Set(receipts.value.map(r => r.id))
    let added = 0
    let dups = 0
    let qrFails = 0
    let fnsFails = 0
    let htmlFails = 0
    let filesAttached = 0
    let filesDup = 0

    function handleDuplicate(p: any): boolean {
      const code = p?.code
      const det = (p?.details && typeof p.details === 'object') ? p.details : null
      if (code === 'RECEIPT_DUPLICATE' && det?.purchase_id) {
        const { fallbackMessage, actionText, onAction } = receiptDuplicateOpenAction(det)
        showSnack(p.message || fallbackMessage, 'warning', { actionText, onAction })
        return true
      }
      if (code === 'FNS_RATE_LIMIT' || code === 'RECEIPT_PENDING') {
        showSnack(p?.message || 'ФНС ещё не вернула данные по чеку', 'warning', { duration: 10000 })
        return true
      }
      return false
    }

    async function fallbackAttach(f: File, errStatus?: number) {
      if ((errStatus ?? 0) >= 500) fnsFails++
      else qrFails++
      const outcome = await attachReceiptFile(f)
      if (outcome === 'attached') filesAttached++
      else if (outcome === 'duplicate') filesDup++
    }

    async function tryServerFileQr(f: File): Promise<boolean> {
      const fd = new FormData()
      fd.append('file', f)
      const r = await apiFetch<Receipt>(
        `/purchases/${purchaseId.value}/receipts/from-file-qr`,
        { method: 'POST', body: fd as any, suppressErrorDialog: true },
      )
      if (r?.id != null) {
        if (existingIds.has(r.id)) dups++
        else { added++; existingIds.add(r.id) }
        return true
      }
      return false
    }

    for (let i = 0; i < files.length; i++) {
      const f = files[i]
      if (!f) continue
      let accessedFns = false
      if (files.length > 1) {
        showSnack(`Распознавание чеков по очереди: ${i + 1} из ${files.length} (${f.name})…`, 'info')
      }

      const lower = f.name.toLowerCase()
      const isJson = lower.endsWith('.json')
      const isHtml = lower.endsWith('.html') || lower.endsWith('.htm')
      const isImage = !isJson && !isHtml &&
        ((f.type || '').startsWith('image/') || /\.(png|jpe?g|webp|jfif)$/i.test(lower)) &&
        !/\.(tiff?|jtif|heic|heif)$/i.test(lower)
      const isServerQrFile = !isJson && !isHtml && !isImage && /\.(pdf|tiff?|jtif|heic|heif)$/i.test(lower)

      try {
        if (isJson) {
          const fd = new FormData()
          fd.append('file', f)
          const res = await apiFetch<Receipt[]>(
            `/purchases/${purchaseId.value}/receipts/import-json`,
            { method: 'POST', body: fd as any, suppressErrorDialog: true },
          )
          for (const r of (res || [])) {
            if (existingIds.has(r.id)) dups++
            else { added++; existingIds.add(r.id) }
          }
        } else if (isImage) {
          let qr: string | null = null
          try {
            qr = await decodeQrFromImageFile(f)
          } catch {
            qr = null
          }
          if (qr) {
            try {
              accessedFns = true
              const r = await apiFetch<Receipt>(
                `/purchases/${purchaseId.value}/receipts/from-qr-fetch`,
                { method: 'POST', body: { qr } as any, suppressErrorDialog: true },
              )
              if (r?.id != null) {
                if (existingIds.has(r.id)) dups++
                else { added++; existingIds.add(r.id) }
              }
            } catch (qrFetchErr: any) {
              if (!handleDuplicate(qrFetchErr?.payload)) {
                await fallbackAttach(f, qrFetchErr?.status)
              }
            }
          } else {
            // Браузерный jsQR не справился (крупный скан А4, поворот, .jfif) — пробуем серверный pyzbar + cv2
            try {
              accessedFns = true
              await tryServerFileQr(f)
            } catch (srvErr: any) {
              if (!handleDuplicate(srvErr?.payload)) {
                await fallbackAttach(f, srvErr?.status)
              }
            }
          }
        } else if (isHtml) {
          try {
            const fd = new FormData()
            fd.append('file', f)
            const res = await apiFetch<Receipt[]>(
              `/purchases/${purchaseId.value}/receipts/import-html`,
              { method: 'POST', body: fd as any, suppressErrorDialog: true },
            )
            for (const r of (res || [])) {
              if (existingIds.has(r.id)) dups++
              else { added++; existingIds.add(r.id) }
            }
          } catch (htmlErr: any) {
            if (handleDuplicate(htmlErr?.payload)) continue
            htmlFails++
            const outcome = await attachReceiptFile(f)
            if (outcome === 'attached') filesAttached++
            else if (outcome === 'duplicate') filesDup++
          }
        } else if (isServerQrFile) {
          try {
            accessedFns = true
            await tryServerFileQr(f)
          } catch (fileQrErr: any) {
            if (!handleDuplicate(fileQrErr?.payload)) {
              await fallbackAttach(f, fileQrErr?.status)
            }
          }
        } else {
          const outcome = await attachReceiptFile(f)
          if (outcome === 'attached') filesAttached++
          else if (outcome === 'duplicate') filesDup++
        }
      } catch (err: any) {
        if (!handleDuplicate(err?.payload)) {
          showSnack(err?.message || `Ошибка обработки ${f.name}`, 'error')
        }
      }

      if (files.length > 1 && accessedFns && i < files.length - 1) {
        await new Promise(r => setTimeout(r, 1600))
      }
    }

    await loadReceipts()
    await loadReceiptFiles()
    if (isEdit.value && purchaseId.value) {
      await new Promise(r => setTimeout(r, 50))
      await loadPurchase()
      logRefetchDebug?.()
    }

    const parts: string[] = []
    if (added) parts.push(`чеков добавлено: ${added}`)
    if (dups) parts.push(`уже было: ${dups}`)
    if (fnsFails) parts.push(`шлюз ФНС временно не ответил: ${fnsFails}`)
    if (qrFails) parts.push(`QR не распознан: ${qrFails}`)
    if (htmlFails) parts.push(`HTML не распознан: ${htmlFails}`)
    if (filesAttached) parts.push(`файл${filesAttached > 1 ? 'ов' : ''} прикреплено: ${filesAttached}`)
    if (filesDup) parts.push(`файл уже был прикреплён: ${filesDup}`)
    if (parts.length) {
      const hasFailure = (fnsFails || qrFails || htmlFails) && !added
      showSnack(parts.join(', '), hasFailure ? 'warning' : 'success', { duration: fnsFails ? 9000 : 5000 })
    }
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
    receiptFiles, loadReceiptFiles, receiptFileThumbs,
    qrScanShow, onScanQrClick, onJsonBtnClick, onManualBtnClick,
    recomputeLoading, recomputeFromReceipts,
    consumePostSaveAction, onQrDetected, onJsonReceiptUpload, deleteReceipt,
    deleteReceiptFile,
  }
}
