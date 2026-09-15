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

// Файл чека, прикреплённый как обычный PurchaseFile (file_type='receipt') —
// когда QR/HTML не распознан или формат (PDF/TIF/HEIC) распознавание не
// поддерживает. Показывается в блоке под таблицей распознанных чеков, чтобы
// файл не выглядел «пропавшим» (жалоба владельца 2026-09-15).
export interface ReceiptFile {
  id: number
  filename: string
  original_name?: string | null
  mime_type?: string | null
  size?: number | null
  created_at?: string | null
}

// Экспортируется — save() в CreateOrderView.vue проверяет наличие отложенного
// действия (не показывать снэк «Закупка создана», если сейчас откроется QR/JSON/
// ручной ввод по этому ключу). Один источник ключа (ПРАВИЛО №6).
export const POST_SAVE_ACTION_KEY = 'advance_report_post_save_action'

// Единый accept для FileDropZone во всех 3 местах использования
// PurchaseReceiptsBlock.vue (ПРАВИЛО №6 — один источник, не 3 разных строки).
// Используется и как атрибут accept, и как селектор в document.querySelector
// (см. onJsonBtnClick / consumePostSaveAction ниже) для клика по input,
// который рендерит FileDropZone.
export const RECEIPT_FILE_ACCEPT = '.json,.pdf,.html,.htm,.png,.jpg,.jpeg,.webp,.tif,.tiff,.heic'
export const RECEIPT_FILE_HINT = 'PDF, HTML (proverkacheka), PNG/JPG с QR, JSON ФНС'

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
  const receiptFiles = ref<ReceiptFile[]>([])

  function sourceLabel(s?: string | null) {
    if (!s) return '—'
    return ({ json_import: 'JSON', qr_scan: 'QR', manual: 'Вручную', html_import: 'HTML' } as Record<string, string>)[s] || s
  }

  async function loadReceipts() {
    if (!purchaseId.value) return
    try {
      receipts.value = await apiFetch<Receipt[]>(`/purchases/${purchaseId.value}/receipts`)
    } catch {
      /* silent — no receipts is fine */
    }
  }

  // Файлы чеков без автораспознавания — переиспользует общий эндпоинт файлов
  // закупки (GET /purchases/{id}/files), не заводит отдельный список
  // хранения (ПРАВИЛО №6: один источник — purchase_files, здесь только фильтр).
  async function loadReceiptFiles() {
    if (!purchaseId.value) return
    try {
      const all = await apiFetch<any[]>(`/purchases/${purchaseId.value}/files`)
      receiptFiles.value = (all || []).filter(f => f.file_type === 'receipt' && f.is_active !== false)
    } catch {
      receiptFiles.value = []
    }
  }

  async function attachReceiptFile(f: File): Promise<'attached' | 'duplicate' | 'error'> {
    if (!purchaseId.value) return 'error'
    try {
      const fd = new FormData()
      fd.append('file', f)
      fd.append('file_type', 'receipt')
      fd.append('doc_format', 'scan')
      await apiFetch(`/purchases/${purchaseId.value}/files`, { method: 'POST', body: fd as any })
      return 'attached'
    } catch (e: any) {
      if (e?.status === 409) return 'duplicate'
      showSnack(e?.payload?.message || e?.message || `Не удалось прикрепить файл ${f.name}`, 'error')
      return 'error'
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
      document.querySelector<HTMLInputElement>(`input[type=file][accept="${RECEIPT_FILE_ACCEPT}"]`)?.click()
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

  // Единая точка входа для загрузки чеков — вызывается и из drag-n-drop
  // (FileDropZone @files), и из клика по кнопке «Загрузить чек» (тот же
  // input, см. RECEIPT_FILE_ACCEPT) — было два вида обработчиков (drop
  // отсутствовал вовсе), жалоба владельца 2026-09-15. Имя сохранено (не
  // onReceiptFiles) — так его деструктурируют 3 места использования
  // PurchaseReceiptsBlock.vue в CreateOrderView.vue.
  //
  // Маршрутизация по типу файла:
  //   .json              → import-json (как раньше)
  //   image (png/jpg/webp) → decode QR → from-qr-fetch; QR не найден → файл
  //                        не теряется, прикрепляется как файл чека (п.3)
  //   .html/.htm         → import-html (proverkacheka) → не разобран → тоже
  //                        прикрепляется как файл чека
  //   pdf/tif/tiff/heic/прочее → сразу прикрепляется как файл чека —
  //                        распознавание из них не обещаем (ТЗ)
  async function onJsonReceiptUpload(files: File[]) {
    if (!files.length) return
    if (!purchaseId.value) {
      // Раньше единственный путь открыть file input лежал через кнопку
      // «Загрузить чек» → onJsonBtnClick → ensureSavedThen (сохраняет
      // черновик первым же кликом, ДО открытия пикера) — молчаливый ранний
      // return здесь был безопасен, потому что до него было физически не
      // добраться без сохранения. FileDropZone это предположение ломает:
      // файл можно перетащить в ещё не сохранённый авансовый отчёт напрямую,
      // и старый молчаливый return воспроизвёл бы ту же жалобу «чек никуда
      // не делся, но и не появился». Теперь — сохраняем сначала (как кнопка),
      // предупредив, что перетащенный файл придётся выбрать заново.
      showSnack('Черновик сохраняется — после сохранения повторите загрузку файла', 'info')
      await ensureSavedThen('upload_json')
      return
    }
    const existingIds = new Set(receipts.value.map(r => r.id))
    let added = 0
    let dups = 0
    let qrFails = 0
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
      if (code === 'FNS_RATE_LIMIT') {
        showSnack(p?.message || 'ФНС временно ограничила запросы', 'warning')
        return true
      }
      return false
    }

    for (const f of files) {
      const lower = f.name.toLowerCase()
      const isJson = lower.endsWith('.json')
      const isHtml = lower.endsWith('.html') || lower.endsWith('.htm')
      const isImage = !isJson && !isHtml &&
        ((f.type || '').startsWith('image/') || /\.(png|jpe?g|webp)$/i.test(lower)) &&
        !/\.(tiff?|heic|heif)$/i.test(lower)

      try {
        if (isJson) {
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
        } else if (isImage) {
          // decodeQrFromImageFile может не только вернуть null, но и БРОСИТЬ
          // (canvas/createImageBitmap отказывается декодировать повреждённое
          // или вырожденное изображение) — без своего try/catch это исключение
          // улетало в общий catch ниже и показывало «Ошибка обработки», а файл
          // терялся, что прямо противоречит ТЗ («QR не распознан — НЕ терять
          // файл»). Оба исхода (null и throw) — одна и та же ветка fallback.
          let qr: string | null = null
          try {
            qr = await decodeQrFromImageFile(f)
          } catch {
            qr = null
          }
          if (!qr) {
            qrFails++
            const outcome = await attachReceiptFile(f)
            if (outcome === 'attached') filesAttached++
            else if (outcome === 'duplicate') filesDup++
            continue
          }
          try {
            const r = await apiFetch<Receipt>(
              `/purchases/${purchaseId.value}/receipts/from-qr-fetch`,
              { method: 'POST', body: { qr } as any },
            )
            if (r?.id != null) {
              if (existingIds.has(r.id)) dups++
              else { added++; existingIds.add(r.id) }
            }
          } catch (qrFetchErr: any) {
            if (!handleDuplicate(qrFetchErr?.payload)) {
              // QR прочитан, но получить чек не удалось (ФНС недоступна и т.п.) —
              // тоже не теряем файл, а не только при «QR не распознан».
              qrFails++
              const outcome = await attachReceiptFile(f)
              if (outcome === 'attached') filesAttached++
              else if (outcome === 'duplicate') filesDup++
            }
          }
        } else if (isHtml) {
          try {
            const fd = new FormData()
            fd.append('file', f)
            const res = await apiFetch<Receipt[]>(
              `/purchases/${purchaseId.value}/receipts/import-html`,
              { method: 'POST', body: fd as any }
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
        } else {
          // PDF / TIF / TIFF / HEIC / прочее — распознавание не обещаем
          const outcome = await attachReceiptFile(f)
          if (outcome === 'attached') filesAttached++
          else if (outcome === 'duplicate') filesDup++
        }
      } catch (err: any) {
        if (!handleDuplicate(err?.payload)) {
          showSnack(err?.message || `Ошибка обработки ${f.name}`, 'error')
        }
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
    if (qrFails) parts.push(`QR не распознан: ${qrFails}`)
    if (htmlFails) parts.push(`HTML не распознан: ${htmlFails}`)
    if (filesAttached) parts.push(`файл${filesAttached > 1 ? 'ов' : ''} прикреплено: ${filesAttached}`)
    if (filesDup) parts.push(`файл уже был прикреплён: ${filesDup}`)
    if (parts.length) {
      const hasFailure = (qrFails || htmlFails) && !added
      showSnack(parts.join(', '), hasFailure ? 'warning' : 'success')
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
    receiptFiles, loadReceiptFiles,
    qrScanShow, onScanQrClick, onJsonBtnClick, onManualBtnClick,
    recomputeLoading, recomputeFromReceipts,
    consumePostSaveAction, onQrDetected, onJsonReceiptUpload, deleteReceipt,
  }
}
