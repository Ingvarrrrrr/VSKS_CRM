// Файлы к закупке: типизированная загрузка/удаление/переименование типа,
// диалоги «Загрузить файл» / «Тип документа» / предпросмотр. Вынесено из
// CreateOrderView.vue без изменения поведения — те же apiFetch/fetch-пути.
// Карточка «Документы к закупке» остаётся в CreateOrderView.vue и читает
// состояние отсюда (тот же паттерн, что и другие composables/purchase/*).
import { computed, ref, type ComputedRef } from 'vue'
import { apiFetch } from '@/api'
import type { ToastType } from '@/composables/useToast'

export interface UploadedFile {
  id: number; purchase_id: number; filename: string; mime_type?: string; size?: number
  file_type?: string; doc_format?: string; is_active?: boolean
  uploaded_by_name?: string | null; created_at?: string | null
}

const FILE_TYPE_LABELS_BASE: Record<string, string> = {
  kp:                         'КП',
  service_note:               'Служебная записка',
  protocol:                   'Протокол закупки',
  invoice:                    'Счёт',
  order:                      'Приказ',
  upd:                        'УПД',
  contract:                   'Договор',
  act:                        'Закрывающий документ',
  other:                      'Прочее',
  fabrikant_instruction:      'Фабрикант: Инструкция',
  fabrikant_application_form: 'Фабрикант: Форма заявки',
  fabrikant_documentation:    'Фабрикант: Документация',
  fabrikant_contract_project: 'Фабрикант: Проект договора',
  fabrikant_tech_spec:        'Фабрикант: ТЗ',
}

function fileTypeColor(t?: string): string {
  const map: Record<string, string> = {
    kp: 'teal', service_note: 'blue', protocol: 'deep-purple',
    invoice: 'orange', order: 'brown', upd: 'green',
    contract: 'indigo', act: 'cyan', other: 'grey',
  }
  return map[t || 'other'] || 'grey'
}

export function usePurchaseFiles(
  purchaseId: ComputedRef<number | null>,
  showSnack: (text: string, color?: ToastType, opts?: { actionText?: string; onAction?: () => void; duration?: number }) => void,
  contractWord: ComputedRef<string>,
  isEdit: ComputedRef<boolean>,
) {
  const EDITABLE_MIME = new Set([
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  ])

  const FILE_TYPE_LABELS = computed<Record<string, string>>(() => ({
    ...FILE_TYPE_LABELS_BASE,
    contract: contractWord.value,
  }))
  const FILE_TYPE_OPTIONS = computed(() => Object.entries(FILE_TYPE_LABELS.value).map(([value, title]) => ({ value, title })))

  const fileInputEl = ref<HTMLInputElement | null>(null)
  const sectionFileInputEl = ref<HTMLInputElement | null>(null)
  const pendingSectionUpload = ref<string | null>(null)
  const uploading = ref(false)
  const uploadedFiles = ref<UploadedFile[]>([])
  const uploadDialog = ref(false)
  const uploadFileType = ref('other')
  const uploadDocFormat = ref('scan')
  const closingFiles = computed(() => uploadedFiles.value.filter(f => ['act', 'upd', 'contract'].includes(f.file_type || '')))
  const paymentFiles = computed(() => uploadedFiles.value.filter(f => f.file_type === 'invoice'))

  const DOC_UPLOAD_SECTIONS = computed(() => [
    { type: 'contract' as const, label: contractWord.value, icon: 'mdi-file-sign', color: 'indigo' },
    { type: 'act' as const, label: 'Акт', icon: 'mdi-file-check', color: 'cyan' },
    { type: 'upd' as const, label: 'УПД', icon: 'mdi-file-document-check', color: 'green' },
    { type: 'invoice' as const, label: 'Счёт', icon: 'mdi-receipt-text', color: 'orange' },
    { type: 'kp' as const, label: 'КП', icon: 'mdi-file-compare', color: 'teal' },
    { type: 'service_note' as const, label: 'Служебная записка', icon: 'mdi-file-document-edit', color: 'blue' },
    { type: 'protocol' as const, label: 'Протокол закупки', icon: 'mdi-file-certificate', color: 'deep-purple' },
    { type: 'order' as const, label: 'Приказ', icon: 'mdi-file-star', color: 'brown' },
    { type: 'other' as const, label: 'Прочее', icon: 'mdi-file-outline', color: 'grey' },
  ])

  function filesByType(type: string) {
    return uploadedFiles.value.filter(f => f.file_type === type)
  }
  const fileTypeEditDialog = ref(false)
  const fileTypeEditValue = ref('other')
  const fileDocFormatEditValue = ref('scan')
  const fileTypeEditTarget = ref<UploadedFile | null>(null)
  const savingFileType = ref(false)

  function openUploadDialog() {
    uploadFileType.value = 'other'
    uploadDocFormat.value = 'scan'
    uploadDialog.value = true
  }

  function openFileTypeEdit(f: UploadedFile) {
    fileTypeEditTarget.value = f
    fileTypeEditValue.value = f.file_type || 'other'
    fileDocFormatEditValue.value = f.doc_format || 'scan'
    fileTypeEditDialog.value = true
  }

  async function toggleDocFormat(f: UploadedFile) {
    if (!purchaseId.value) return
    const newFormat = f.doc_format === 'editable' ? 'scan' : 'editable'
    const token = localStorage.getItem('auth_token')
    const fd = new FormData()
    fd.append('doc_format', newFormat)
    const res = await fetch(`/api/purchases/${purchaseId.value}/files/${f.id}`, {
      method: 'PATCH',
      headers: { Authorization: `Bearer ${token}` },
      body: fd,
    })
    if (res.ok) {
      const updated = await res.json()
      const idx = uploadedFiles.value.findIndex(x => x.id === updated.id)
      if (idx !== -1) uploadedFiles.value[idx] = updated
    }
  }

  async function saveFileType() {
    if (!fileTypeEditTarget.value || !purchaseId.value) return
    savingFileType.value = true
    try {
      const token = localStorage.getItem('auth_token')
      const fd = new FormData()
      fd.append('file_type', fileTypeEditValue.value)
      fd.append('doc_format', fileDocFormatEditValue.value)
      const res = await fetch(`/api/purchases/${purchaseId.value}/files/${fileTypeEditTarget.value.id}`, {
        method: 'PATCH',
        headers: { Authorization: `Bearer ${token}` },
        body: fd,
      })
      if (res.ok) {
        const updated = await res.json()
        const idx = uploadedFiles.value.findIndex(f => f.id === updated.id)
        if (idx !== -1) uploadedFiles.value[idx] = updated
        fileTypeEditDialog.value = false
      }
    } finally {
      savingFileType.value = false
    }
  }

  // File upload
  const uploadFile = async (event: Event) => {
    const input = event.target as HTMLInputElement
    if (!input.files?.length || !purchaseId.value) return
    uploadDialog.value = false
    uploading.value = true
    try {
      const file = input.files[0]!
      // Auto-detect doc_format: only Word/Excel can be editable
      const resolvedFormat = EDITABLE_MIME.has(file.type) ? uploadDocFormat.value : 'scan'
      const fd = new FormData()
      fd.append('file', file)
      fd.append('file_type', uploadFileType.value)
      fd.append('doc_format', resolvedFormat)
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
      const uploaded = await res.json()
      uploadedFiles.value.push(uploaded)
      showSnack('Файл загружен')
    } catch (e: any) {
      showSnack(e?.message || 'Ошибка загрузки файла', 'error')
    } finally {
      uploading.value = false
      if (fileInputEl.value) fileInputEl.value.value = ''
    }
  }

  // Единая точка загрузки файлов закупки с заданным file_type — используется и
  // плитками drag-n-drop (Документы к закупке), и кнопкой «Загрузить» в разделе
  // «Платёж», и кликом по плитке (открывает системный выбор файла с тем же типом).
  async function uploadFilesForType(files: File[], fileType: string) {
    if (!purchaseId.value || !files.length) return
    uploading.value = true
    pendingSectionUpload.value = fileType
    try {
      for (const file of files) {
        const resolvedFormat = EDITABLE_MIME.has(file.type) ? 'editable' : 'scan'
        const fd = new FormData()
        fd.append('file', file)
        fd.append('file_type', fileType)
        fd.append('doc_format', resolvedFormat)
        const token = localStorage.getItem('auth_token')
        const res = await fetch(`/api/purchases/${purchaseId.value}/files`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` },
          body: fd,
        })
        if (!res.ok) {
          let detail = `Ошибка загрузки (${res.status})`
          try { const err = await res.json(); detail = err.detail || err.message || detail } catch {}
          showSnack(`${file.name}: ${detail}`, 'error')
          continue
        }
        const uploaded = await res.json()
        // Backend деактивирует прежние файлы того же типа при загрузке — синхронизируем оптимистично
        const ft = uploaded.file_type
        uploadedFiles.value.forEach(f => { if (f.file_type === ft) f.is_active = false })
        uploadedFiles.value.push(uploaded)
      }
      showSnack(files.length > 1 ? `Загружено файлов: ${files.length}` : 'Файл загружен')
    } catch (e: any) {
      showSnack(e?.message || 'Ошибка загрузки файлов', 'error')
    } finally {
      uploading.value = false
      pendingSectionUpload.value = null
    }
  }

  async function onAcceptanceDocFilesDropped(files: File[]) {
    if (!isEdit.value) return
    await uploadFilesForType(files, 'other')
  }

  function uploadForSection(section: string) {
    pendingSectionUpload.value = section as any
    sectionFileInputEl.value?.click()
  }

  async function toggleFileActive(f: UploadedFile) {
    const newActive = !(f.is_active ?? true)
    const token = localStorage.getItem('auth_token')
    const fd = new FormData()
    fd.append('is_active', String(newActive))
    try {
      const res = await fetch(`/api/purchases/${f.purchase_id}/files/${f.id}`, {
        method: 'PATCH', headers: { Authorization: `Bearer ${token}` }, body: fd,
      })
      if (res.ok) {
        f.is_active = newActive
      }
    } catch { /* skip */ }
  }

  const uploadSectionFile = async (event: Event) => {
    const input = event.target as HTMLInputElement
    if (!input.files?.length || !purchaseId.value) return
    const file = input.files[0]!
    const fileType = pendingSectionUpload.value || 'other'
    input.value = ''
    await uploadFilesForType([file], fileType)
  }

  const downloadFile = async (fid: number, filename: string) => {
    const token = localStorage.getItem('auth_token')
    const res = await fetch(`/api/purchases/${purchaseId.value}/files/${fid}/download`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) { showSnack('Ошибка скачивания', 'error'); return }
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = filename; a.click()
    URL.revokeObjectURL(url)
  }

  // File preview
  const previewDialog = ref(false)
  const previewFile = ref<UploadedFile | null>(null)
  const previewUrl = ref('')

  const isPreviewable = (mime?: string) => mime === 'application/pdf' || !!mime?.startsWith('image/')

  const openPreview = async (f: UploadedFile) => {
    const token = localStorage.getItem('auth_token')
    const res = await fetch(`/api/purchases/${purchaseId.value}/files/${f.id}/view`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) { showSnack('Ошибка открытия файла', 'error'); return }
    const blob = await res.blob()
    if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = URL.createObjectURL(blob)
    previewFile.value = f
    previewDialog.value = true
  }

  const deleteFile = async (fid: number) => {
    try {
      await apiFetch(`/purchases/${purchaseId.value}/files/${fid}`, { method: 'DELETE' })
      uploadedFiles.value = uploadedFiles.value.filter(f => f.id !== fid)
      showSnack('Файл удалён')
    } catch {
      showSnack('Ошибка удаления', 'error')
    }
  }

  const fileIcon = (mime?: string) => {
    if (!mime) return 'mdi-file'
    if (mime === 'application/pdf') return 'mdi-file-pdf-box'
    if (mime.startsWith('image/')) return 'mdi-file-image'
    if (mime.includes('word')) return 'mdi-file-word'
    return 'mdi-file'
  }
  const formatSize = (bytes?: number) => !bytes ? '' : bytes > 1048576 ? (bytes / 1048576).toFixed(1) + ' МБ' : (bytes / 1024).toFixed(0) + ' КБ'
  const formatDate = (dt?: string | null) => dt ? new Date(dt).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' }) : ''

  return {
    EDITABLE_MIME, FILE_TYPE_LABELS, FILE_TYPE_OPTIONS, fileTypeColor,
    fileInputEl, sectionFileInputEl, pendingSectionUpload,
    uploadedFiles, uploadDialog, uploadFileType, uploadDocFormat, closingFiles, paymentFiles,
    DOC_UPLOAD_SECTIONS, filesByType,
    fileTypeEditDialog, fileTypeEditValue, fileDocFormatEditValue, fileTypeEditTarget, savingFileType,
    openUploadDialog, openFileTypeEdit, toggleDocFormat, saveFileType,
    uploading, uploadFile, uploadFilesForType, onAcceptanceDocFilesDropped, uploadForSection, toggleFileActive, uploadSectionFile,
    downloadFile, deleteFile,
    previewDialog, previewFile, previewUrl, isPreviewable, openPreview,
    fileIcon, formatSize, formatDate,
  }
}
