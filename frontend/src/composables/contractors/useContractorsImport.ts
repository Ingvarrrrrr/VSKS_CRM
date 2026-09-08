// useContractorsImport.ts — импорт контрагентов из Excel/Word/PDF с drag&drop маппингом колонок
// + скачивание шаблона. Дословный перенос из ContractorsView.vue.
import { ref } from 'vue'
import type { ToastType } from '@/composables/useToast'
import { CONTRACTOR_TARGET_FIELDS } from './contractorsTypes'

const _FIELD_KEYWORDS: Record<string, string[]> = {
  name:                       ['назван', 'наимен', 'name', 'органи'],
  inn:                        ['инн', 'inn', 'идентиф'],
  kpp:                        ['кпп', 'kpp'],
  ogrn:                       ['огрн', 'ogrn'],
  org_type:                   ['тип орг', 'org_type', 'юр.лицо', 'форма'],
  address:                    ['адрес', 'address'],
  postal_address:             ['почтов', 'postal'],
  email:                      ['email', 'e-mail', 'mail'],
  phone:                      ['телефон', 'phone', 'тел'],
  org_phone:                  ['тел. орг', 'org_phone'],
  org_email:                  ['email орг', 'org_email'],
  contact_person:             ['контакт', 'contact', 'лицо'],
  signatory:                  ['подписант', 'signatory', 'директор', 'руководит'],
  signatory_basis:            ['основан', 'basis', 'устав', 'действует'],
  settlement_account:         ['расч', 'р/с', 'settlement'],
  bank_name:                  ['банк', 'bank'],
  bik:                        ['бик', 'bik'],
  correspondent_account:      ['корр', 'к/с', 'correspondent'],
  manual_product_categories:  ['категор', 'товар', 'product', 'categ'],
  website:                    ['сайт', 'website'],
  registration_date:          ['дата регистрац', 'зарегистр'],
  okpo:                       ['окпо'],
  okved:                      ['оквэд', 'оквед'],
  treasury_account:           ['казначейск'],
  single_treasury_account:    ['единый казн'],
  signatory_position:         ['должност'],
}

function contractorAutoDetect(headers: string[]): Record<string, number | null> {
  const mapping: Record<string, number | null> = {}
  const used = new Set<number>()
  for (const field of CONTRACTOR_TARGET_FIELDS) {
    const kws = _FIELD_KEYWORDS[field.value] || []
    for (let i = 0; i < headers.length; i++) {
      if (used.has(i)) continue
      const h = (headers[i] || '').toLowerCase()
      if (kws.some(k => h.includes(k))) {
        mapping[field.value] = i
        used.add(i)
        break
      }
    }
  }
  return mapping
}

export function useContractorsImport(options: {
  reload: () => Promise<void>
  showSnack: (text: string, color?: ToastType) => void
}) {
  const { reload, showSnack } = options

  const contractorImportDialog  = ref(false)
  const contractorImportStep    = ref(1)
  const contractorImportFile    = ref<File | null>(null)
  const contractorImportLoading = ref(false)
  const contractorImportPreview = ref<{
    headers: string[]
    sample: string[][]
    total_rows: number
    header_row_offset: number
  } | null>(null)
  const contractorDragMapping   = ref<Record<string, number | null>>({})
  const contractorIgnoredCols   = ref<number[]>([])
  const contractorDragOverTarget = ref<string | null>(null)
  const contractorImportResult  = ref<{ created: number; updated?: number; skipped: number; skipped_empty?: number; update_details?: string[]; errors?: string[] } | null>(null)
  const contractorImportError   = ref('')

  function openContractorImport() {
    contractorImportDialog.value = true
    contractorImportStep.value = 1
  }

  function contractorIsMapped(idx: number): boolean {
    return Object.values(contractorDragMapping.value).includes(idx)
  }

  function contractorIsIgnored(idx: number): boolean {
    return contractorIgnoredCols.value.includes(idx)
  }

  function contractorIsTargetFilled(field: string): boolean {
    return contractorDragMapping.value[field] != null
  }

  function contractorGetLabel(idx: number): string {
    return contractorImportPreview.value?.headers[idx] || `Столбец ${idx + 1}`
  }

  function contractorGetSamples(idx: number): string[] {
    if (!contractorImportPreview.value) return []
    return contractorImportPreview.value.sample
      .slice(0, 1)
      .map(row => (row[idx] != null ? String(row[idx]).trim() : ''))
      .filter(Boolean)
  }

  let _dragIdx: number | null = null

  function contractorOnDragStart(idx: number, e: DragEvent) {
    _dragIdx = idx
    e.dataTransfer?.setData('text/plain', String(idx))
  }

  function contractorOnDropToTarget(field: string, e: DragEvent) {
    contractorDragOverTarget.value = null
    const raw = e.dataTransfer?.getData('text/plain')
    const idx = raw != null ? parseInt(raw) : _dragIdx
    if (idx == null || isNaN(idx as number)) return
    // Unmap if this idx was in another target
    for (const [f, v] of Object.entries(contractorDragMapping.value)) {
      if (v === idx) contractorDragMapping.value[f] = null
    }
    contractorDragMapping.value[field] = idx as number
    // Remove from ignored
    contractorIgnoredCols.value = contractorIgnoredCols.value.filter(i => i !== idx)
  }

  function contractorOnDropToUnresolved(e: DragEvent) {
    contractorDragOverTarget.value = null
    const raw = e.dataTransfer?.getData('text/plain')
    const idx = raw != null ? parseInt(raw) : _dragIdx
    if (idx == null || isNaN(idx as number)) return
    for (const [f, v] of Object.entries(contractorDragMapping.value)) {
      if (v === idx) contractorDragMapping.value[f] = null
    }
  }

  function contractorUnmapTarget(field: string) {
    contractorDragMapping.value[field] = null
  }

  function contractorIgnoreCol(idx: number) {
    if (!contractorIgnoredCols.value.includes(idx)) {
      contractorIgnoredCols.value.push(idx)
    }
  }

  async function doContractorImportPreview() {
    if (!contractorImportFile.value) return
    contractorImportLoading.value = true
    contractorImportError.value = ''
    try {
      const token = localStorage.getItem('auth_token') || ''
      const fd = new FormData()
      // contractorImportFile from v-file-input may be a File[] or File
      const fileObj = Array.isArray(contractorImportFile.value)
        ? contractorImportFile.value[0]
        : contractorImportFile.value
      fd.append('file', fileObj)
      const res = await fetch('/api/contractors/import/preview', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: fd,
      })
      if (!res.ok) {
        let detail = await res.text()
        try { detail = JSON.parse(detail).detail } catch {}
        throw new Error(detail)
      }
      const data = await res.json()
      contractorImportPreview.value = data
      contractorDragMapping.value = contractorAutoDetect(data.headers)
      contractorIgnoredCols.value = []
      contractorImportStep.value = 2
    } catch (e: any) {
      contractorImportError.value = e.message || 'Ошибка чтения файла'
    } finally {
      contractorImportLoading.value = false
    }
  }

  async function doContractorImportMapped() {
    if (!contractorImportFile.value || !contractorImportPreview.value) return
    contractorImportLoading.value = true
    contractorImportError.value = ''
    try {
      const token = localStorage.getItem('auth_token') || ''
      const fd = new FormData()
      const fileObj = Array.isArray(contractorImportFile.value)
        ? contractorImportFile.value[0]
        : contractorImportFile.value
      fd.append('file', fileObj)

      const params = new URLSearchParams()
      params.set('header_row_offset', String(contractorImportPreview.value.header_row_offset))
      const m = contractorDragMapping.value
      const colFields = [
        'name', 'inn', 'kpp', 'ogrn', 'org_type', 'address', 'postal_address',
        'signatory', 'signatory_basis', 'contact_person', 'phone', 'email',
        'org_phone', 'org_email',
        'settlement_account', 'bank_name', 'bik', 'correspondent_account', 'bank_details',
        'manual_product_categories',
        'website', 'registration_date', 'okpo', 'okved',
        'treasury_account', 'single_treasury_account', 'signatory_position',
      ]
      for (const f of colFields) {
        if (m[f] != null) params.set(`col_${f}`, String(m[f]))
      }

      const res = await fetch(`/api/contractors/import/mapped?${params.toString()}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: fd,
      })
      if (!res.ok) {
        let detail = await res.text()
        try { detail = JSON.parse(detail).detail } catch {}
        throw new Error(detail)
      }
      const data = await res.json()
      contractorImportResult.value = data
      contractorImportStep.value = 3
      showSnack(`Добавлено: ${data.created}, дополнено: ${data.updated || 0}, пропущено: ${data.skipped}`, 'success')
      await reload()
    } catch (e: any) {
      contractorImportError.value = e.message || 'Ошибка импорта'
    } finally {
      contractorImportLoading.value = false
    }
  }

  function closeContractorImport() {
    contractorImportDialog.value = false
    contractorImportStep.value = 1
    contractorImportFile.value = null
    contractorImportPreview.value = null
    contractorDragMapping.value = {}
    contractorIgnoredCols.value = []
    contractorImportResult.value = null
    contractorImportError.value = ''
  }

  async function downloadTemplate() {
    const token = localStorage.getItem('auth_token') || ''
    const res = await fetch('/api/contractors/import/template', {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) { showSnack('Ошибка скачивания шаблона', 'error'); return }
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = 'Шаблон_импорта_контрагентов.xlsx'; a.click()
    URL.revokeObjectURL(url)
  }

  return {
    CONTRACTOR_TARGET_FIELDS,
    contractorImportDialog,
    contractorImportStep,
    contractorImportFile,
    contractorImportLoading,
    contractorImportPreview,
    contractorDragMapping,
    contractorIgnoredCols,
    contractorDragOverTarget,
    contractorImportResult,
    contractorImportError,
    openContractorImport,
    contractorIsMapped,
    contractorIsIgnored,
    contractorIsTargetFilled,
    contractorGetLabel,
    contractorGetSamples,
    contractorOnDragStart,
    contractorOnDropToTarget,
    contractorOnDropToUnresolved,
    contractorUnmapTarget,
    contractorIgnoreCol,
    doContractorImportPreview,
    doContractorImportMapped,
    closeContractorImport,
    downloadTemplate,
  }
}

export type ContractorsImportApi = ReturnType<typeof useContractorsImport>
