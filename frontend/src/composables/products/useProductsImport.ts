// useProductsImport.ts — мастер импорта товаров: лист → маппинг → предпросмотр
// (dry_run) → импорт. Переписан на POST /api/products/import-preview +
// POST /api/products/import-mapped (план dreamy-booping-piglet.md, задача B):
// повод — 2026-09-09 старый POST /api/products/import сам угадал колонки,
// принял «Категорию товара» за «Наименование» и создал 1022 мусорных товара
// на проде. Подсказка маппинга (`mapping_hint` из /import-preview) теперь
// только ПРЕДЛАГАЕТСЯ — пользователь обязан её увидеть и подтвердить на
// сетке (ImportMappingGrid.vue) до того, как что-либо запишется в базу.
// Старый POST /import из этого экрана больше не вызывается (он остаётся
// эндпоинтом для импорта позиций закупки — routers/purchase_items_import.py
// и т.п., этот файл его не трогает).
import { computed, reactive } from 'vue'
import type { ToastType } from '@/composables/useToast'

export interface ProductsImportTargetField {
  key: string
  label: string
  required?: boolean
  hint?: string
}

// Ключи — те же query-параметры col_<key>, что принимает POST
// /api/products/import-mapped (routers/products_import.py) и та же подсказка
// products_import_map.COLUMN_MAP — один источник соответствий имён полей,
// сетка ничего не переизобретает.
export const PRODUCTS_IMPORT_TARGET_FIELDS: ProductsImportTargetField[] = [
  { key: 'name', label: 'Наименование', required: true, hint: 'Обязательное поле — без него строка пропускается' },
  { key: 'description', label: 'Описание' },
  { key: 'category', label: 'Категория' },
  { key: 'product_type', label: 'Вид' },
  { key: 'unit', label: 'Ед. изм.' },
  { key: 'price', label: 'Цена' },
  { key: 'quantity', label: 'Количество', hint: 'Только если импорт сразу добавляет позиции в закупку' },
  { key: 'photo_link', label: 'Фото (URL)' },
  { key: 'is_reusable', label: 'Многоразовое' },
  { key: 'is_active', label: 'Активен' },
  { key: 'feo_category_name', label: 'Категория ФЭО' },
  { key: 'link_url_1', label: 'Ссылка 1' },
  { key: 'link_price_1', label: 'Цена ссылки 1' },
  { key: 'link_url_2', label: 'Ссылка 2' },
  { key: 'link_price_2', label: 'Цена ссылки 2' },
  { key: 'link_url_3', label: 'Ссылка 3' },
  { key: 'link_price_3', label: 'Цена ссылки 3' },
]

interface PreviewSheet {
  name: string
  headers: string[]
  sample: string[][]
  total_rows: number
  header_row_offset: number
  // mapping_hint приходит из suggest_products_column_mapping_with_hints
  // (backend/app/services/products_import_map.py) — смесь {field: index} и
  // одного служебного ключа mapping_hint_fuzzy (список полей, подставленных
  // ВТОРЫМ, менее строгим проходом — «Категория товара»/«Ед. изм.»/«Цена за
  // ед.» и т.п., где заголовок не совпал буквально с эталоном). Их нужно
  // разобрать в applySheet(), а не спредить как есть в mapping.
  mapping_hint: Record<string, number> & { mapping_hint_fuzzy?: string[] }
}

interface ImportReportRow {
  row: number
  action: 'created' | 'updated' | 'skipped' | 'error'
  name: string | null
  reason: string | null
}

interface ImportMappedResult {
  created: number
  updated: number
  skipped: number
  errors: { row: number; name: string; message: string }[]
  product_ids: number[]
  rows: ImportReportRow[]
}

function emptyMapping(): Record<string, number | null> {
  const m: Record<string, number | null> = {}
  for (const f of PRODUCTS_IMPORT_TARGET_FIELDS) m[f.key] = null
  return m
}

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('auth_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export function useProductsImport(options: {
  load: () => Promise<void>
  showSnack: (text: string, color?: ToastType) => void
}) {
  const { load, showSnack } = options

  const importDialog = reactive({
    show: false,
    step: 1, // 1 файл+лист, 2 маппинг, 3 предпросмотр (dry_run), 4 импорт
    loading: false,
    error: '',
    file: null as File | null,
    fileList: [] as File[],
    sheets: [] as PreviewSheet[],
    selectedSheet: '',
    headers: [] as string[],
    sample: [] as string[][],
    totalRowsInSheet: 0,
    headerRowOffset: 0,
    detectedHeaderRowOffset: 0, // для «сбросить к автоопределению»
    mapping: emptyMapping(),
    // Поля mapping, подставленные вторым (менее строгим) проходом подсказки —
    // владелец обязан их проверить внимательнее, чем точные совпадения.
    fuzzyFields: [] as string[],
    dryResult: null as ImportMappedResult | null,
    result: null as ImportMappedResult | null,
  })

  const hasPreview = computed(() => importDialog.sheets.length > 0)
  const mappingValid = computed(() => importDialog.mapping.name != null)

  // Пропуски и ошибки — в начало таблицы (владелец должен видеть их первыми,
  // а не листать до конца списка из 1000+ строк).
  const sortedDryRows = computed(() => {
    const rows = importDialog.dryResult?.rows || []
    const rank: Record<string, number> = { skipped: 0, error: 0, updated: 1, created: 2 }
    return [...rows].sort((a, b) => (rank[a.action] ?? 3) - (rank[b.action] ?? 3))
  })

  function closeImportDialog() {
    const shouldReload = (importDialog.result?.created ?? 0) > 0 || (importDialog.result?.updated ?? 0) > 0
    importDialog.show = false
    importDialog.step = 1
    importDialog.loading = false
    importDialog.error = ''
    importDialog.file = null
    importDialog.fileList = []
    importDialog.sheets = []
    importDialog.selectedSheet = ''
    importDialog.headers = []
    importDialog.sample = []
    importDialog.totalRowsInSheet = 0
    importDialog.headerRowOffset = 0
    importDialog.detectedHeaderRowOffset = 0
    importDialog.mapping = emptyMapping()
    importDialog.fuzzyFields = []
    importDialog.dryResult = null
    importDialog.result = null
    if (shouldReload) load()
  }

  async function downloadTemplate() {
    const res = await fetch('/api/products/import/template', { headers: authHeaders() })
    if (!res.ok) { showSnack('Ошибка загрузки шаблона', 'error'); return }
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a'); a.href = url; a.download = 'Шаблон_импорта_товаров.xlsx'; a.click()
    URL.revokeObjectURL(url)
  }

  function applySheet(sheet: PreviewSheet) {
    importDialog.selectedSheet = sheet.name
    importDialog.headers = [...sheet.headers]
    importDialog.sample = sheet.sample.map(r => [...r])
    importDialog.totalRowsInSheet = sheet.total_rows
    importDialog.headerRowOffset = sheet.header_row_offset
    importDialog.detectedHeaderRowOffset = sheet.header_row_offset
    const { mapping_hint_fuzzy, ...numericHint } = sheet.mapping_hint || {}
    importDialog.mapping = { ...emptyMapping(), ...numericHint }
    importDialog.fuzzyFields = mapping_hint_fuzzy || []
  }

  function selectSheet(name: string) {
    const sheet = importDialog.sheets.find(s => s.name === name)
    if (sheet) applySheet(sheet)
  }

  // Сдвинуть строку заголовка ниже: первая строка примера становится
  // заголовком (её содержимое у нас уже есть в предпросмотре — сдвиг вверх
  // за пределы автоопределённой строки недоступен, т.к. пропущенные до неё
  // строки на бэкенде не возвращаются, см. read_preview_sheets()).
  function shiftHeaderRowDown() {
    if (!importDialog.sample.length) return
    const nextHeaderRow = importDialog.sample[0] ?? []
    importDialog.headers = importDialog.headers.map((h, i) => String(nextHeaderRow[i] ?? '').trim() || h)
    importDialog.sample = importDialog.sample.slice(1)
    importDialog.headerRowOffset += 1
    importDialog.totalRowsInSheet = Math.max(0, importDialog.totalRowsInSheet - 1)
  }

  function resetHeaderRow() {
    const sheet = importDialog.sheets.find(s => s.name === importDialog.selectedSheet)
    if (sheet) applySheet(sheet)
  }

  async function doImportPreview() {
    if (!importDialog.file) return
    importDialog.loading = true
    importDialog.error = ''
    try {
      const fd = new FormData()
      fd.append('file', importDialog.file)
      const res = await fetch('/api/products/import-preview', {
        method: 'POST', headers: authHeaders(), body: fd,
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || 'Не удалось прочитать файл')
      }
      const data = await res.json()
      importDialog.sheets = data.sheets
      applySheet(data.sheets[0])
    } catch (e: any) {
      importDialog.error = e.message || 'Ошибка чтения файла'
      importDialog.sheets = []
    } finally {
      importDialog.loading = false
    }
  }

  function goToMapping() {
    if (hasPreview.value) importDialog.step = 2
  }

  async function runImportMapped(dryRun: boolean) {
    if (!importDialog.file || !mappingValid.value) return
    importDialog.loading = true
    importDialog.error = ''
    try {
      const fd = new FormData()
      fd.append('file', importDialog.file)
      const params = new URLSearchParams()
      params.set('sheet_name', importDialog.selectedSheet)
      params.set('header_row_offset', String(importDialog.headerRowOffset))
      params.set('dry_run', String(dryRun))
      for (const [key, val] of Object.entries(importDialog.mapping)) {
        if (val != null) params.set(`col_${key}`, String(val))
      }
      const res = await fetch(`/api/products/import-mapped?${params.toString()}`, {
        method: 'POST', headers: authHeaders(), body: fd,
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || 'Ошибка импорта')
      }
      const data: ImportMappedResult = await res.json()
      if (dryRun) {
        importDialog.dryResult = data
        importDialog.step = 3
      } else {
        importDialog.result = data
        showSnack(`Импорт завершён: создано ${data.created}, обновлено ${data.updated}`)
        await load()
      }
    } catch (e: any) {
      importDialog.error = e.message || 'Ошибка импорта'
    } finally {
      importDialog.loading = false
    }
  }

  const doPreviewDryRun = () => runImportMapped(true)
  const doConfirmImport = () => runImportMapped(false)
  function goToImportStep() { importDialog.step = 4 }

  // reactive(), а не голый объект: hasPreview/mappingValid/sortedDryRows —
  // computed()-refs, а wizard целиком передаётся дальше в ProductsImportDialog.vue
  // одним пропом (`:wizard="productsImport"`) — без reactive() их пришлось бы
  // разворачивать через `.value` на каждое обращение внутри вложенного шаблона
  // (auto-unwrap рефов в шаблоне работает только для top-level биндингов
  // самого <script setup>, а не для вложенных полей объекта-пропа).
  return reactive({
    importDialog, hasPreview, mappingValid, sortedDryRows,
    closeImportDialog, downloadTemplate,
    doImportPreview, selectSheet, shiftHeaderRowDown, resetHeaderRow,
    goToMapping, doPreviewDryRun, goToImportStep, doConfirmImport,
  })
}
