// Управление прикреплёнными файлами чеков (file_type='receipt') и их миниатюрами.
// Вынесено из usePurchaseReceipts.ts по Правилу №5 (< 500 строк на файл).
import { ref, type ComputedRef } from 'vue'
import { apiFetch } from '@/api'
import type { ToastType } from '@/composables/useToast'

export interface ReceiptFile {
  id: number
  filename: string
  original_name?: string | null
  mime_type?: string | null
  size?: number | null
  created_at?: string | null
}

export type ReceiptSnackFn = (
  text: string,
  color?: ToastType,
  opts?: { actionText?: string; onAction?: () => void; duration?: number },
) => void

export function receiptDuplicateOpenAction(det: any) {
  const refNum = det.purchase_ref || `#${det.purchase_id}`
  const pid = det.purchase_id
  const isAdvance = !!det.is_advance
  const path = isAdvance ? `/advance-reports/${pid}/edit` : `/orders/${pid}`
  const fallbackMessage = isAdvance
    ? `Такой авансовый отчёт уже есть — № ${refNum}. Этот чек уже был загружен в него.`
    : `Чек был загружен ранее в закупку № ${refNum}.`
  const actionText = isAdvance ? `Открыть авансовый отчёт № ${refNum}` : `Открыть закупку № ${refNum}`
  return { fallbackMessage, actionText, onAction: () => window.open(path, '_blank') }
}

export function usePurchaseReceiptFiles(
  purchaseId: ComputedRef<number | null>,
  showSnack: ReceiptSnackFn,
) {
  const receiptFiles = ref<ReceiptFile[]>([])
  const receiptFileThumbs = ref<Record<number, string>>({})

  async function _loadReceiptFileThumb(rf: ReceiptFile) {
    if (!purchaseId.value) return
    if (!rf.mime_type || !rf.mime_type.startsWith('image/')) return
    if (receiptFileThumbs.value[rf.id]) return
    try {
      const res = await fetch(`/api/purchases/${purchaseId.value}/files/${rf.id}/view`, {
        headers: {},
      })
      if (!res.ok) return
      const blob = await res.blob()
      receiptFileThumbs.value = { ...receiptFileThumbs.value, [rf.id]: URL.createObjectURL(blob) }
    } catch {
      /* миниатюра опциональна */
    }
  }

  async function loadReceiptFiles() {
    if (!purchaseId.value) return
    try {
      const all = await apiFetch<any[]>(`/purchases/${purchaseId.value}/files`)
      receiptFiles.value = (all || []).filter(f => f.file_type === 'receipt' && f.is_active !== false)
      void (async () => {
        for (const rf of receiptFiles.value) {
          await _loadReceiptFileThumb(rf)
        }
      })()
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
      await apiFetch(`/purchases/${purchaseId.value}/files`, {
        method: 'POST',
        body: fd as any,
        suppressErrorDialog: true,
      })
      return 'attached'
    } catch (e: any) {
      if (e?.status === 409) {
        const p = e?.payload
        const det = (p?.details && typeof p.details === 'object') ? p.details : null
        if (p?.code === 'RECEIPT_DUPLICATE' && det?.purchase_id) {
          const { fallbackMessage, actionText, onAction } = receiptDuplicateOpenAction(det)
          showSnack(p.message || fallbackMessage, 'warning', { actionText, onAction })
        }
        return 'duplicate'
      }
      showSnack(e?.payload?.message || e?.message || `Не удалось прикрепить файл ${f.name}`, 'error')
      return 'error'
    }
  }

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
    receiptFiles,
    receiptFileThumbs,
    loadReceiptFiles,
    attachReceiptFile,
    deleteReceiptFile,
  }
}
