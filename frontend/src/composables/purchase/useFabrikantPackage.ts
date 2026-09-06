// Фабрикант: скачивание ZIP-пакета документов процедуры + override отдельных
// файлов пакета (загрузка своего файла вместо шаблона, удаление override).
// Вынесено из CreateOrderView.vue без изменения поведения.
import { ref, type ComputedRef, type Ref } from 'vue'
import { apiFetch } from '@/api'
import type { ToastType } from '@/composables/useToast'

interface UploadedFileLike {
  id: number; file_type?: string; is_active?: boolean
  [key: string]: any
}

export function useFabrikantPackage(
  purchaseId: ComputedRef<number | null>,
  showSnack: (text: string, color?: ToastType, opts?: { actionText?: string; onAction?: () => void; duration?: number }) => void,
  docErrorInfo: Ref<any>,
  docErrorDialog: Ref<boolean>,
  docLoading: Ref<string | null>,
  uploadedFiles: Ref<UploadedFileLike[]>,
  editableMime: Set<string>,
  uploading: Ref<boolean>,
) {
  async function downloadFabrikantPackage() {
    if (!purchaseId.value) return
    docLoading.value = 'fabrikant_package'
    try {
      const token = localStorage.getItem('auth_token')
      const res = await fetch(`/api/purchases/${purchaseId.value}/fabrikant-package`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) {
        const err = await res.json().catch(() => null)
        const d = err?.details || err?.detail
        if (err?.code) {
          const info: any = {
            code: err.code,
            message: err.message || 'Ошибка формирования пакета документов',
            correlation_id: err.correlation_id,
          }
          if (d && typeof d === 'object') Object.assign(info, d)
          else if (typeof d === 'string') info.error_raw = d
          docErrorInfo.value = info
          docErrorDialog.value = true
        } else {
          showSnack(err?.message || 'Ошибка формирования пакета документов', 'error')
        }
        return
      }
      const blob = await res.blob()
      const disposition = res.headers.get('Content-Disposition') || ''
      let filename = `Фабрикант_закупка_${purchaseId.value}.zip`
      const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i)
      if (utf8Match) {
        try { filename = decodeURIComponent(utf8Match[1]!) } catch { filename = utf8Match[1]! }
      } else {
        const plain = disposition.match(/filename="?([^";]+)"?/)
        if (plain) filename = plain[1]!
      }
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = filename; a.click()
      URL.revokeObjectURL(url)
    } catch {
      showSnack('Ошибка скачивания пакета документов', 'error')
    } finally {
      docLoading.value = null
    }
  }

  // ── Фабрикант: override-файлы пакета ─────────────────────────────────────
  const fabrikantFileInputEl = ref<HTMLInputElement | null>(null)
  const fabrikantPendingFt = ref<string>('')

  function fabrikantOverride(ft: string): UploadedFileLike | undefined {
    return uploadedFiles.value.find(f => f.file_type === ft && f.is_active !== false)
  }

  function triggerFabrikantUpload(ft: string) {
    fabrikantPendingFt.value = ft
    fabrikantFileInputEl.value?.click()
  }

  const uploadFabrikantOverride = async (event: Event) => {
    const input = event.target as HTMLInputElement
    if (!input.files?.length || !purchaseId.value) return
    uploading.value = true
    try {
      const file = input.files[0]!
      const docFormat = editableMime.has(file.type) ? 'editable' : 'scan'
      const fd = new FormData()
      fd.append('file', file)
      fd.append('file_type', fabrikantPendingFt.value)
      fd.append('doc_format', docFormat)
      const token = localStorage.getItem('auth_token')
      const res = await fetch(`/api/purchases/${purchaseId.value}/files`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: fd,
      })
      if (!res.ok) {
        let detail = `Ошибка загрузки (${res.status})`
        try { const err = await res.json(); detail = err.detail || err.message || detail } catch {}
        showSnack(detail, 'error')
        return
      }
      const uploaded: UploadedFileLike = await res.json()
      const ft = uploaded.file_type
      uploadedFiles.value.forEach(f => { if (f.file_type === ft) f.is_active = false })
      uploadedFiles.value.push(uploaded)
      showSnack('Файл загружен — будет использован вместо шаблона')
    } catch (e: any) {
      showSnack(e?.message || 'Ошибка загрузки файла', 'error')
    } finally {
      uploading.value = false
      fabrikantPendingFt.value = ''
      if (input) input.value = ''
    }
  }

  const deleteFabrikantOverride = async (fid: number) => {
    try {
      await apiFetch(`/purchases/${purchaseId.value}/files/${fid}`, { method: 'DELETE' })
      uploadedFiles.value = uploadedFiles.value.filter(f => f.id !== fid)
      showSnack('Override удалён — будет использоваться шаблон')
    } catch (e: any) {
      showSnack(e?.payload?.message || e?.message || 'Ошибка удаления', 'error')
    }
  }

  return {
    downloadFabrikantPackage,
    fabrikantFileInputEl, fabrikantPendingFt, fabrikantOverride,
    triggerFabrikantUpload, uploadFabrikantOverride, deleteFabrikantOverride,
  }
}
