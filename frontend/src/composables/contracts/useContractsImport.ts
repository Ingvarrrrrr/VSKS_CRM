// useContractsImport.ts — импорт договоров из файла (Excel/Word/PDF),
// 3 шага: превью колонок → сопоставление → результат. Дословный перенос
// из ContractsView.vue.
import { computed, reactive } from 'vue'
import type { Subsidy } from './contractsTypes'

export const importFields = [
  { key: 'number', label: 'Номер договора', required: true },
  { key: 'date', label: 'Дата договора', required: false },
  { key: 'contractor', label: 'Контрагент (название/ИНН)', required: false },
  { key: 'subject', label: 'Предмет', required: false },
  { key: 'max_amount', label: 'Сумма', required: false },
  { key: 'start_date', label: 'Дата начала', required: false },
  { key: 'end_date', label: 'Дата окончания', required: false },
  { key: 'contract_type', label: 'Тип договора', required: false },
  { key: 'purchase_method', label: 'Способ закупки', required: false },
  { key: 'item_type', label: 'Тип (товар/услуга)', required: false },
  { key: 'status', label: 'Статус', required: false },
  { key: 'notes', label: 'Примечания', required: false },
]

export function useContractsImport(options: {
  subsidies: { value: Subsidy[] }
  loadContracts: () => Promise<void>
}) {
  const { subsidies, loadContracts } = options

  const importDialog = reactive({
    show: false,
    step: 1,
    loading: false,
    dragging: false,
    file: null as File | null,
    subsidyId: null as number | null,
    headers: [] as string[],
    headerOptions: [] as { title: string; value: number }[],
    sample: [] as string[][],
    totalRows: 0,
    headerRowOffset: 0,
    sheetName: '',
    mapping: {} as Record<string, number | null>,
    result: null as { created: number; skipped: number } | null,
    error: '',
  })

  const subsidyOptions = computed(() => subsidies.value)

  function closeImportDialog() {
    importDialog.show = false
    importDialog.step = 1
    importDialog.file = null
    importDialog.headers = []
    importDialog.headerOptions = []
    importDialog.sample = []
    importDialog.mapping = {}
    importDialog.result = null
    importDialog.error = ''
    importDialog.subsidyId = null
    if (importDialog.result?.created) loadContracts()
  }

  async function doImportPreview() {
    if (!importDialog.file) return
    importDialog.loading = true
    importDialog.error = ''
    try {
      const fd = new FormData()
      fd.append('file', importDialog.file)
      const res = await fetch('/api/contracts/import/preview', {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('auth_token')}` },
        body: fd,
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Ошибка загрузки' }))
        throw new Error(err.detail || err.message || 'Ошибка')
      }
      const data = await res.json()
      importDialog.headers = data.headers
      importDialog.headerOptions = data.headers.map((h: string, i: number) => ({ title: h, value: i }))
      importDialog.sample = data.sample
      importDialog.totalRows = data.total_rows
      importDialog.headerRowOffset = data.header_row_offset
      importDialog.sheetName = data.sheet_name || ''
      // Auto-map by header hints
      importDialog.mapping = {}
      for (let i = 0; i < data.headers.length; i++) {
        const h = (data.headers[i] as string).toLowerCase()
        if (/номер|number|№\s*догов/.test(h) && !importDialog.mapping.number) importDialog.mapping.number = i
        else if (/дата\s*(догов|заключ)|date/.test(h) && !importDialog.mapping.date) importDialog.mapping.date = i
        else if (/контрагент|поставщик|исполнитель|contractor/.test(h) && !importDialog.mapping.contractor) importDialog.mapping.contractor = i
        else if (/предмет|subject/.test(h) && !importDialog.mapping.subject) importDialog.mapping.subject = i
        else if (/сумм|цена|amount|стоимость/.test(h) && !importDialog.mapping.max_amount) importDialog.mapping.max_amount = i
        else if (/начал|start/.test(h) && !importDialog.mapping.start_date) importDialog.mapping.start_date = i
        else if (/оконч|end|заверш/.test(h) && !importDialog.mapping.end_date) importDialog.mapping.end_date = i
        else if (/тип\s*догов|type/.test(h) && !importDialog.mapping.contract_type) importDialog.mapping.contract_type = i
        else if (/способ|метод|method/.test(h) && !importDialog.mapping.purchase_method) importDialog.mapping.purchase_method = i
        else if (/примечан|notes|комментар/.test(h) && !importDialog.mapping.notes) importDialog.mapping.notes = i
        else if (/статус|status/.test(h) && !importDialog.mapping.status) importDialog.mapping.status = i
      }
      importDialog.step = 2
    } catch (e: any) {
      importDialog.error = e.message || 'Ошибка'
    } finally {
      importDialog.loading = false
    }
  }

  async function doImportMapped() {
    if (!importDialog.file || importDialog.mapping.number == null) return
    importDialog.loading = true
    importDialog.error = ''
    try {
      const fd = new FormData()
      fd.append('file', importDialog.file)
      const params = new URLSearchParams()
      params.set('header_row_offset', String(importDialog.headerRowOffset))
      for (const [key, val] of Object.entries(importDialog.mapping)) {
        if (val != null) params.set(`col_${key}`, String(val))
      }
      if (importDialog.subsidyId) params.set('subsidy_id', String(importDialog.subsidyId))
      const res = await fetch(`/api/contracts/import/mapped?${params}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('auth_token')}` },
        body: fd,
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Ошибка импорта' }))
        throw new Error(err.detail || err.message || 'Ошибка')
      }
      const data = await res.json()
      importDialog.result = data
      importDialog.step = 3
      if (data.created > 0) await loadContracts()
    } catch (e: any) {
      importDialog.error = e.message || 'Ошибка'
    } finally {
      importDialog.loading = false
    }
  }

  return { importDialog, subsidyOptions, closeImportDialog, doImportPreview, doImportMapped }
}
