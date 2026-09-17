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

// Файлы, перетащенные в блок «Чеки» ДО того, как черновик авансового/закупки
// сохранён. save() при создании делает router.push('/…/{id}/edit') — вид
// смонтирован по route.path как :key, поэтому переход /create → /edit
// полностью размонтирует CreateOrderView и уничтожает все локальные
// замыкания (включая переданные File-объекты). sessionStorage хранит только
// строковый флаг действия (POST_SAVE_ACTION_KEY) — File туда не положить.
// Модульная переменная переживает remount в пределах SPA-сессии (JS-модуль
// не перезагружается при router.push), поэтому здесь держим сами файлы и
// дозавершаем их обработку в consumePostSaveAction() на новом инстансе —
// не заставляя владельца выбирать файл заново после каждого drag-n-drop в
// ещё не сохранённый документ (жалоба 2026-09-16, «драг-н-дроп не работает»,
// закупка 914: раньше просто показывался снэк «повторите загрузку» и файл
// терялся).
let pendingDroppedFiles: File[] | null = null

export function usePurchaseReceipts(
  purchaseId: ComputedRef<number | null>,
  formMode: ComputedRef<string>,
  isEdit: ComputedRef<boolean>,
  form: ReceiptsFormSlice,
  showSnack: (text: string, color?: ToastType, opts?: { actionText?: string; onAction?: () => void; duration?: number }) => void,
  guideArrowTo: (target: string) => void,
  // Пункт 1 (владелец, 2026-09-17): boolean успеха — раньше doSave() глотал
  // ошибки сохранения в своём catch и всегда резолвился, recomputeFromReceipts
  // ниже продолжала пересчёт и loadPurchase() даже при непрошедшем save(),
  // стирая ручные позиции. См. CreateOrderView.vue::save()/doSave().
  save: () => Promise<boolean>,
  loadPurchase: () => Promise<void>,
  openManualReceiptDialog: () => void,
  logRefetchDebug?: () => void,
) {
  const receipts = ref<Receipt[]>([])
  const receiptFiles = ref<ReceiptFile[]>([])
  // Владелец (п.8, 2026-09-17): «нераспознанный чек должен выводиться той
  // картинкой, которой его загрузили». Миниатюры — objectURL по id файла,
  // получены через ТОТ ЖЕ /files/{id}/view, что использует общий просмотрщик
  // вложений (usePurchaseFiles::openPreview в CreateOrderView.vue) — второй
  // эндпоинт показа не заводим (ПРАВИЛО №6). Ключ — receipt-файл может быть
  // не только картинкой (PDF/TIF/HEIC) — для них миниатюры нет, остаётся иконка.
  const receiptFileThumbs = ref<Record<number, string>>({})

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
      for (const rf of receiptFiles.value) {
        void _loadReceiptFileThumb(rf)
      }
    } catch {
      receiptFiles.value = []
    }
  }

  // Подгрузить миниатюру одного файла (только изображения — PDF/TIF/HEIC
  // остаются с иконкой в списке, превью открывается по клику через общий
  // диалог просмотра). Не перезапрашивает уже закешированные id.
  async function _loadReceiptFileThumb(rf: ReceiptFile) {
    if (!purchaseId.value) return
    if (!rf.mime_type || !rf.mime_type.startsWith('image/')) return
    if (receiptFileThumbs.value[rf.id]) return
    try {
      const token = localStorage.getItem('auth_token')
      const res = await fetch(`/api/purchases/${purchaseId.value}/files/${rf.id}/view`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) return
      const blob = await res.blob()
      receiptFileThumbs.value = { ...receiptFileThumbs.value, [rf.id]: URL.createObjectURL(blob) }
    } catch {
      /* миниатюра — приятная мелочь, не критично при сбое */
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
      if (e?.status === 409) {
        // Владелец (п.6б, 2026-09-17): «внёс один и тот же нераспознанный чек в
        // 945 и 941 — везде пропустило» — бэкенд теперь при file_type='receipt'
        // сверяет хеш содержимого файла кросс-закупочно (purchase_files.py) и
        // отдаёт structured RECEIPT_DUPLICATE с номером/ссылкой на документ, где
        // чек уже лежит — тот же формат и та же функция открытия документа
        // (receiptDuplicateOpenAction), что и у распознанных чеков (ПРАВИЛО №6).
        const p = e?.payload
        const code = p?.code
        const det = (p?.details && typeof p.details === 'object') ? p.details : null
        if (code === 'RECEIPT_DUPLICATE' && det?.purchase_id) {
          const { fallbackMessage, actionText, onAction } = receiptDuplicateOpenAction(det)
          showSnack(p.message || fallbackMessage, 'warning', { actionText, onAction })
        }
        return 'duplicate'
      }
      showSnack(e?.payload?.message || e?.message || `Не удалось прикрепить файл ${f.name}`, 'error')
      return 'error'
    }
  }

  const qrScanShow = ref(false)

  // beforeSave — вызывается только когда мы реально собираемся сохранять
  // (субсидия на месте), непосредственно перед save(). Используется
  // onJsonReceiptUpload, чтобы застолбить pendingDroppedFiles ровно в тот
  // момент, когда известно, что save() будет вызван — без повторения самой
  // проверки субсидии второй раз (ПРАВИЛО №6 — одна проверка, не дубль).
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
      // Владелец (п.5, 2026-09-17): «"Пересчитать из чеков" выкидывает то, что
      // я вносил вручную». Сам пересчёт на бэкенде НЕ удаляет и не трогает
      // PurchaseItem без receipt_id — он только связывает/дополняет позиции из
      // чеков (см. app/services/receipts_recompute.py::_recompute_from_receipts_core).
      // Реальная потеря происходила на клиенте: позиции, добавленные вручную,
      // но ещё НЕ отправленные на сервер (items сохраняются целиком через
      // save(), не построчным автосохранением — см. serializeFormForAutosave()
      // в CreateOrderView.vue, которая items не включает), стирались строкой
      // ниже loadPurchase(), перезатирающей форму серверным состоянием.
      // Технически можно сохранить ручной ввод вместо предупреждения — просто
      // сохраняем форму ПЕРЕД пересчётом тем же save(), что и кнопка
      // «Сохранить» (ПРАВИЛО №6, второй механизм сохранения не заводим). Для
      // авансового отчёта (единственный режим, где кнопка вообще показана —
      // см. showReceiptsOnTop) save() сохраняет черновик всегда, без
      // блокирующей валидации.
      // КРИТИЧНО (независимая приёмка, 2026-09-17, п.1): save() теперь
      // возвращает boolean успеха. Раньше doSave() глотал ошибку сохранения
      // в своём catch (просто показывал снэк) и промис резолвился как
      // «успешный» — код ниже (recompute-from-receipts + loadPurchase())
      // выполнялся, даже когда save() реально не сохранил форму, и
      // loadPurchase() перезатирал форму серверным состоянием БЕЗ ручных
      // позиций. Если save() вернул false — прерываемся, ничего не пересчитываем
      // и не перезагружаем, человек остаётся со своими несохранёнными данными
      // на экране и уже увиденной причиной отказа (снэк от save()/doSave()).
      const saved = await save()
      if (!saved) return
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
      if (pendingDroppedFiles && pendingDroppedFiles.length) {
        // Файлы уже были выбраны/перетащены до сохранения — довершаем их
        // загрузку напрямую, без повторного открытия пикера (см. комментарий
        // у pendingDroppedFiles).
        const filesToUpload = pendingDroppedFiles
        pendingDroppedFiles = null
        onJsonReceiptUpload(filesToUpload)
      } else {
        // Старый путь (кнопка «Загрузить чек» без drag-n-drop) — файла ещё
        // не было, открываем пикер как раньше.
        document.querySelector<HTMLInputElement>(`input[type=file][accept="${RECEIPT_FILE_ACCEPT}"]`)?.click()
      }
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
      } else if (code === 'FNS_RATE_LIMIT' || code === 'RECEIPT_PENDING') {
        // Владелец (п.6а): честный текст вместо «лимита» — см.
        // classify_proverkacheka_error (backend/app/services/receipts_parsing.py),
        // единственный источник этих формулировок.
        showSnack(p?.message || 'ФНС ещё не вернула данные по чеку', 'warning', { duration: 10000 })
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
      // Черновик ещё не сохранён — файл перетащили (или выбрали) раньше, чем
      // появился purchaseId. Раньше здесь просто показывали снэк «повторите
      // загрузку файла» и всё — сам файл терялся, потому что save() делает
      // router.push на /…/{id}/edit, а RouterView держит вид на :key=route.path,
      // то есть при создании авансового компонент полностью пересоздаётся и
      // теряет любые локальные переменные. Теперь сами File-объекты кладём в
      // pendingDroppedFiles (модульная переменная, переживает remount — см.
      // комментарий у объявления), и consumePostSaveAction() на новом
      // инстансе дозавершает загрузку САМИХ этих файлов автоматически, не
      // прося владельца выбрать файл ещё раз (жалоба 2026-09-16, закупка 914).
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
        // См. комментарий в onQrDetected — тот же источник текста, не дублируем.
        showSnack(p?.message || 'ФНС ещё не вернула данные по чеку', 'warning', { duration: 10000 })
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

  // Удаление прикреплённого файла чека без автораспознавания (жалоба
  // владельца 2026-09-16: «файл прикрепился, а как его удалить?»). Переиспользует
  // общий эндпоинт DELETE /purchases/{id}/files/{fid} (purchase_files.py) — тот
  // же, которым удаляются остальные файлы закупки, права те же
  // (_check_upload_permission), второй механизм не заводится (ПРАВИЛО №6).
  async function deleteReceiptFile(id: number) {
    if (!purchaseId.value) return
    if (!confirm('Удалить файл чека?')) return
    try {
      await apiFetch(`/purchases/${purchaseId.value}/files/${id}`, { method: 'DELETE' })
      await loadReceiptFiles()
      showSnack('Файл удалён')
    } catch (e: any) {
      const status = e?.status
      if (status === 403) {
        showSnack(e?.payload?.message || e?.message || 'Нет прав на удаление этого файла', 'error')
      } else if (status === 404) {
        showSnack('Файл уже удалён или не найден', 'warning')
        await loadReceiptFiles()
      } else {
        showSnack(e?.payload?.message || e?.message || 'Ошибка удаления файла', 'error')
      }
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
