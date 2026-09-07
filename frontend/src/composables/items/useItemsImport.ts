// useItemsImport — Excel (2-step column mapping) + Smart (AI/QR) import, the
// product-match review dialog, the duplicate-merge dialog and the P1-B single
// product "repick" dialog for PurchaseItemsEditor. Extracted from
// PurchaseItemsEditor.vue (monolith refactor) — the presentational half
// (2-step wizard UI) already lives in components/items/ItemsImportWizard.vue;
// this composable owns all the state and business logic that drives it, so the
// parent stays a thin caller (props/emits/expose + composable wiring).
import { ref, computed, reactive, watch } from 'vue'
import { apiFetch } from '@/api'
import type { ContractItem } from '@/types/contractItem'
import type { MatchCandidate } from '@/composables/useItemMatching'
import type { DupGroup, ResolvedGroup } from '@/components/DuplicateMergeDialog.vue'
import type { ToastType } from '@/composables/useToast'

// EditorItem is structurally identical to the parent's; kept loose here (same
// convention as ItemsTableFlat.vue/ItemsCardsView.vue) since the parent owns
// the real shape and this composable only reads/writes the fields it sets
// below.
type EditorItem = any

export interface ResolvedRow {
  query: string
  product_id: number | null
  create_new: boolean
  chosen_candidate?: MatchCandidate | null
}

export interface MatchRow {
  query: string
  status: 'auto' | 'suggest' | 'create'
  candidates: MatchCandidate[]
  _choice?: number | '__create__' | null
}

export interface UseItemsImportDeps {
  props: {
    purchaseId?: number | null
    defaultItemType?: string
    defaultUnit?: string
    defaultCountry?: string
    itemShape: 'purchase' | 'wish'
    defaultFeoPlannedItemId?: number | null
  }
  localItems: { value: EditorItem[] }
  localContractItems: { value: ContractItem[] }
  contractItemImportMode: { value: boolean }
  emitUpdate: () => void
  emitContractItemsUpdate: () => void
  emit: (event: 'reload-requested') => void
  showSnack: (text: string, color?: ToastType, opts?: { actionText?: string; onAction?: () => void; duration?: number }) => void
  nextUid: () => string
  /** From useItemMatching().applyCandidate — shared with inline/bulk matching. */
  applyMatchCandidate: (row: EditorItem, cand: MatchCandidate) => void
}

export function useItemsImport(deps: UseItemsImportDeps) {
  const {
    props, localItems, localContractItems, contractItemImportMode,
    emitUpdate, emitContractItemsUpdate, emit, showSnack, nextUid, applyMatchCandidate,
  } = deps

  // ── Excel import (legacy 2-step column mapping) ──────────────────────────────

  const itemsImportDialog = ref(false)
  const isSmartMode = ref(false)
  const itemsImportFile = ref<File | null>(null)
  const itemsImportLoading = ref(false)
  const itemsImportResult = ref<Record<string, any> | null>(null)
  const importStep = ref(1)
  const importPreviewData = ref<any>(null)
  const importSelectedSheet = ref('')
  const dragMapping = ref<Record<string, number | null>>({})
  const ignoredColumns = ref<number[]>([])
  const dragOverTarget = ref<string | null>(null)
  const importError = ref('')

  const TARGET_FIELDS = [
    { value: 'item_name',     title: 'Наименование',    required: true },
    { value: 'unit_price',    title: 'Цена за ед.',     required: false },
    { value: 'quantity',      title: 'Количество',      required: false },
    { value: 'unit',          title: 'Ед. изм.',        required: false },
    { value: 'total_price',   title: 'Сумма',           required: false },
    { value: 'description',   title: 'Описание',        required: false },
    { value: 'row_num',       title: '№',               required: false, hint: 'Номер строки в исходном документе' },
    { value: 'vat_rate',      title: 'Ставка НДС',      required: false },
    { value: 'vat_amount',    title: 'Сумма НДС',       required: false },
    { value: 'total_with_vat', title: 'Стоимость с НДС', required: false },
    { value: 'category',      title: 'Категория товара', required: false, hint: 'Для группировки/фильтрации; при конфликте главнее категория из каталога' },
    { value: 'product_type',  title: 'Вид товара',      required: false, hint: 'Вид внутри категории; при конфликте главнее вид из каталога' },
  ]

  const currentSheetData = computed(() => {
    if (!importPreviewData.value) return null
    const sheets = importPreviewData.value.sheets
    return sheets.find((s: any) => s.name === importSelectedSheet.value) || sheets[0]
  })

  const currentSheetHeaders = computed(() => currentSheetData.value?.headers || [])

  const mappingHasName = computed(() =>
    dragMapping.value['item_name'] !== null && dragMapping.value['item_name'] !== undefined
  )

  function isMapped(idx: number): boolean {
    return Object.values(dragMapping.value).includes(idx)
  }

  function isIgnored(idx: number): boolean {
    return ignoredColumns.value.includes(idx)
  }

  function isTargetFilled(field: string): boolean {
    return dragMapping.value[field] !== null && dragMapping.value[field] !== undefined
  }

  function getColumnLabel(idx: number): string {
    return (currentSheetHeaders.value[idx] as string) || `Столбец ${idx + 1}`
  }

  const unmappedCount = computed(() =>
    currentSheetHeaders.value.filter((_: any, i: number) => !isMapped(i) && !isIgnored(i)).length
  )

  function getSamples(idx: number): string[] {
    const sample = currentSheetData.value?.sample || []
    return (sample as any[][]).slice(0, 1)
      .map((row: any[]) => String(row[idx] ?? '').trim())
      .filter(Boolean)
  }

  function onDragStart(idx: number, e: DragEvent) {
    e.dataTransfer!.effectAllowed = 'move'
    e.dataTransfer!.setData('text/plain', String(idx))
  }

  function onDropToTarget(field: string, e: DragEvent) {
    const idx = parseInt(e.dataTransfer!.getData('text/plain'))
    for (const f of Object.keys(dragMapping.value)) {
      if (dragMapping.value[f] === idx) dragMapping.value[f] = null
    }
    dragMapping.value[field] = idx
    dragOverTarget.value = null
  }

  function onDropToUnresolved(e: DragEvent) {
    const idx = parseInt(e.dataTransfer!.getData('text/plain'))
    for (const f of Object.keys(dragMapping.value)) {
      if (dragMapping.value[f] === idx) dragMapping.value[f] = null
    }
    dragOverTarget.value = null
  }

  function unmapTarget(field: string) {
    dragMapping.value[field] = null
  }

  function ignoreColumn(idx: number) {
    for (const f of Object.keys(dragMapping.value)) {
      if (dragMapping.value[f] === idx) dragMapping.value[f] = null
    }
    if (!ignoredColumns.value.includes(idx)) ignoredColumns.value.push(idx)
  }

  function autoDetectMapping(headers: string[]): Record<string, number | null> {
    const mapping: Record<string, number | null> = {}
    TARGET_FIELDS.forEach(f => { mapping[f.value] = null })

    // УПД numeric-label detection (Постановление Правительства РФ № 1137):
    // Если хедеры — это сабметки УПД '1а','1б','2','2а','3','4','5','9' — мапим позиционно.
    const normalizedHeaders = headers.map(h => h.trim().toLowerCase().replace(/\s/g, ''))
    const UPD_LABELS = ['1а', '1б', '2', '2а', '3', '4', '5', '9']
    const updMatches = UPD_LABELS.filter(l => normalizedHeaders.includes(l)).length
    if (updMatches >= 4) {
      const idx = (label: string) => normalizedHeaders.indexOf(label)
      if (idx('1б') >= 0) mapping.item_name = idx('1б')
      if (idx('3')  >= 0) mapping.quantity  = idx('3')
      if (idx('4')  >= 0) mapping.unit_price = idx('4')
      // Prefer "с налогом — всего" (col 9), fallback на "без налога" (col 5)
      if      (idx('9') >= 0) mapping.total_price = idx('9')
      else if (idx('5') >= 0) mapping.total_price = idx('5')
      if      (idx('2а') >= 0) mapping.unit = idx('2а')
      else if (idx('2')  >= 0) mapping.unit = idx('2')
      return mapping
    }

    // Keyword fallback. Учитываем УПД headers ("Наименование товара (описание выполненных работ...)",
    // "Цена (тариф) за единицу", "Стоимость... с налогом - всего") + общие случаи.
    const used = new Set<number>()

    // First pass: total_price priority — "с налогом" over plain "стоимость"
    for (let i = 0; i < headers.length; i++) {
      const h = headers[i].toLowerCase()
      if (h.includes('с налогом') && (h.includes('всего') || h.includes('итог'))) {
        mapping.total_price = i; used.add(i); break
      }
    }

    const keywords: Record<string, string[]> = {
      item_name:      ['наименован', 'назван', 'описание выполн', 'описание оказ', 'товара', 'товар', 'предмет', 'name', 'продукц', 'описан', 'маршрут', 'направлени', 'рейс', 'билет', 'услуга', 'работа'],
      description:    ['характерист', 'тз', 'спецификац', 'specification'],
      quantity:       ['кол-во', 'количеств', 'объем', 'qty', 'кол.', 'кол '],
      unit_price:     ['цена (тариф)', 'цена', 'price', 'за единиц', 'за ед', 'тариф', 'стоимость', 'сумма билет', 'цена билет'],
      total_price:    ['всего', 'сумм', 'итого', 'total', 'стоимость'],
      unit:           ['ед. изм', 'единиц', 'ед.изм', 'изм', 'unit', 'ед.'],
      row_num:        ['№', 'n', 'no', '#', 'пп', 'п/п'],
      vat_rate:       ['ставка ндс', 'налоговая ставка', '% ндс', 'ндс %', 'vat rate'],
      vat_amount:     ['сумма ндс', 'налог', 'vat amount'],
      total_with_vat: ['с ндс', 'с учётом ндс', 'с налогом всего', 'итого с ндс', 'total with vat', 'к оплате', 'сумма с налогом'],
      category:       ['категор', 'category'],
      product_type:   ['вид товара'],
    }
    for (const [field, kws] of Object.entries(keywords)) {
      if (mapping[field] !== null) continue  // already set (e.g. total_price by с налогом)
      for (let i = 0; i < headers.length; i++) {
        if (used.has(i)) continue
        const h = headers[i].toLowerCase()
        if (kws.some(kw => h.includes(kw))) {
          mapping[field] = i; used.add(i); break
        }
      }
    }
    return mapping
  }

  watch(importSelectedSheet, (newSheet) => {
    if (!importPreviewData.value) return
    const sheet = importPreviewData.value.sheets.find((s: any) => s.name === newSheet)
    if (sheet) {
      dragMapping.value = autoDetectMapping(sheet.headers)
      ignoredColumns.value = []
    }
  })

  function openImportDialog() {
    isSmartMode.value = false
    itemsImportDialog.value = true
  }

  function openSmartImportDialog() {
    isSmartMode.value = true
    smartImportPreview.value = null
    smartImportResult.value = null
    smartImportFile.value = null
    smartImportFileList.value = []
    itemsImportDialog.value = true
  }

  function switchImportMode(smart: boolean) {
    isSmartMode.value = smart
    // Reset state on mode switch
    smartImportFile.value = null
    smartImportFileList.value = []
    smartImportPreview.value = null
    smartImportColumns.value = null
    smartImportResult.value = null
    importStep.value = 1
    importPreviewData.value = null
    itemsImportFile.value = null
    importError.value = ''
    columnMappingApplied.value = false
  }

  function closeImportDialog() {
    itemsImportDialog.value = false
    importStep.value = 1
    itemsImportFile.value = null
    importPreviewData.value = null
    dragMapping.value = {}
    ignoredColumns.value = []
    itemsImportResult.value = null
    importError.value = ''
    isSmartMode.value = false
  }

  async function doImportPreview() {
    if (!itemsImportFile.value) return
    itemsImportLoading.value = true
    try {
      const token = localStorage.getItem('auth_token')
      const fd = new FormData()
      fd.append('file', itemsImportFile.value)
      const resp = await fetch('/api/purchases/items/import-preview', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` } as HeadersInit,
        body: fd,
      })
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}))
        throw new Error(err.detail || `Ошибка ${resp.status}`)
      }
      const data = await resp.json()
      importPreviewData.value = data
      importSelectedSheet.value = data.sheets[0]?.name || ''
      dragMapping.value = autoDetectMapping(data.sheets[0]?.headers || [])
      ignoredColumns.value = []
      importStep.value = 2
    } catch (e: any) {
      showSnack(e.message || 'Ошибка чтения файла', 'error')
    } finally {
      itemsImportLoading.value = false
    }
  }

  function buildEditorItemFromRow(row: any[], mapping: Record<string, number | null>): EditorItem {
    function getVal(field: string): any {
      const idx = mapping[field]
      if (idx === null || idx === undefined) return null
      return row[idx] ?? null
    }
    const unitPrice = getVal('unit_price') !== null ? Number(getVal('unit_price')) : null
    const quantity = getVal('quantity') !== null ? Number(getVal('quantity')) : null
    const totalPrice = getVal('total_price') !== null
      ? Number(getVal('total_price'))
      : (unitPrice !== null && quantity !== null ? Math.round(unitPrice * quantity * 100) / 100 : null)

    const item: EditorItem = {
      product_id: null,
      item_name: String(getVal('item_name') ?? '').trim(),
      item_type: props.defaultItemType,
      quantity,
      unit: String(getVal('unit') ?? props.defaultUnit).trim() || props.defaultUnit,
      unit_price: unitPrice,
      total_price: totalPrice,
      country_origin: props.defaultCountry,
      _selectedProduct: null,
      _photo_url: undefined,
      _description: String(getVal('description') ?? '').trim() || undefined,
      _description_44fz: undefined,
    }
    if (props.itemShape === 'purchase') {
      item.final_unit_price = null
      item.final_total = null
      // F-PLAN: импортированные строки сразу наследуют шапочную плановую позицию
      item.feo_planned_item_id = props.defaultFeoPlannedItemId ?? null
    }
    return item
  }

  async function doMappedImport() {
    if (!itemsImportFile.value) return
    itemsImportLoading.value = true
    itemsImportResult.value = null
    importError.value = ''
    try {
      if (props.purchaseId) {
        // Purchase context — call pid-bound endpoint
        const token = localStorage.getItem('auth_token')
        const fd = new FormData()
        fd.append('file', itemsImportFile.value)
        const params = new URLSearchParams()
        if (importSelectedSheet.value) params.set('sheet_name', importSelectedSheet.value)
        const headerRowOffset = currentSheetData.value?.header_row_offset ?? 0
        if (headerRowOffset > 0) params.set('header_row_offset', String(headerRowOffset))
        const paramMap: Record<string, string> = {
          item_name:     'col_item_name',
          description:   'col_description',
          quantity:      'col_quantity',
          unit_price:    'col_unit_price',
          total_price:   'col_total_price',
          unit:          'col_unit',
          row_num:       'col_row_num',
          vat_rate:      'col_vat_rate',
          vat_amount:    'col_vat_amount',
          total_with_vat: 'col_total_with_vat',
          category:      'col_category',
          product_type:  'col_product_type',
        }
        for (const [field, colIdx] of Object.entries(dragMapping.value)) {
          if (colIdx !== null && colIdx !== undefined && paramMap[field]) {
            params.set(paramMap[field], String(colIdx))
          }
        }
        const resp = await fetch(`/api/purchases/${props.purchaseId}/items/import-mapped?${params}`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` } as HeadersInit,
          body: fd,
        })
        if (!resp.ok) {
          const errText = await resp.text().catch(() => '')
          let detail = `Ошибка ${resp.status}`
          try { detail = JSON.parse(errText).detail || detail } catch { /* */ }
          throw new Error(detail)
        }
        const data = await resp.json()
        itemsImportResult.value = data
        importStep.value = 3
        if (data.added > 0) {
          showSnack(`Импортировано ${data.added} позиций`)
          emit('reload-requested')
        } else {
          importError.value = 'Не удалось импортировать ни одной позиции. Проверьте маппинг столбцов.'
          if (data.debug) {
            const d = data.debug
            showSnack(
              `Импортировано 0 позиций. Обработано строк: ${d.rows_processed}. ` +
              `Пустое наименование: ${d.skipped_empty_name}. ` +
              `Отброшено как «итого/подпись»: ${d.skipped_junk_row}. ` +
              `Первые строки данных: ${JSON.stringify(d.first_3_rows_sample)}`,
              'warning'
            )
          }
        }
      } else {
        // Wish / no-pid context — вызов backend import-mapped-nopid
        const sheet = importPreviewData.value?.sheets?.find((s: any) => s.name === importSelectedSheet.value)
          ?? importPreviewData.value?.sheets?.[0]
        if (!sheet) { showSnack('Нет данных превью', 'error'); return }
        const fdNoPid = new FormData()
        fdNoPid.append('file', itemsImportFile.value as File)
        const paramsNoPid = new URLSearchParams()
        if (importSelectedSheet.value) paramsNoPid.set('sheet_name', importSelectedSheet.value)
        const headerOffset = sheet.header_row_offset ?? 0
        if (headerOffset > 0) paramsNoPid.set('header_row_offset', String(headerOffset))
        const paramMapNoPid: Record<string, string> = {
          item_name:     'col_item_name',
          description:   'col_description',
          quantity:      'col_quantity',
          unit_price:    'col_unit_price',
          total_price:   'col_total_price',
          unit:          'col_unit',
          row_num:       'col_row_num',
          vat_rate:      'col_vat_rate',
          vat_amount:    'col_vat_amount',
          total_with_vat: 'col_total_with_vat',
          category:      'col_category',
          product_type:  'col_product_type',
        }
        for (const [field, colIdx] of Object.entries(dragMapping.value)) {
          if (colIdx !== null && colIdx !== undefined && paramMapNoPid[field]) {
            paramsNoPid.set(paramMapNoPid[field], String(colIdx))
          }
        }
        const token = localStorage.getItem('auth_token') || ''
        const respNoPid = await fetch(`/api/purchases/items/import-mapped-nopid?${paramsNoPid}`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` } as HeadersInit,
          body: fdNoPid,
        })
        if (!respNoPid.ok) {
          const errText = await respNoPid.text().catch(() => '')
          let detail = `Ошибка ${respNoPid.status}`
          try { detail = JSON.parse(errText).detail || detail } catch { /* */ }
          throw new Error(detail)
        }
        const dataNoPid = await respNoPid.json()
        const backendItems: any[] = dataNoPid.items || []
        const newItems: EditorItem[] = backendItems.map((bi) => ({
          _uid: nextUid(),
          product_id: bi.product_id ?? null,
          item_name: bi.item_name || '',
          item_type: bi.item_type || 'товар',
          quantity: bi.quantity ?? 1,
          unit: bi.unit || 'шт',
          unit_price: bi.unit_price ?? 0,
          total_price: bi.total_price ?? 0,
          country_origin: 'РФ',
          _description: bi.description || '',
          _category: bi.category || '',
          _product_type: bi.product_type || '',
        } as EditorItem))
        localItems.value = [...localItems.value, ...newItems]
        emitUpdate()
        itemsImportResult.value = { imported: newItems.length, added: newItems.length }
        importStep.value = 3
        showSnack(`Добавлено позиций: ${newItems.length}`)
      }
    } catch (e: any) {
      importError.value = e?.message ?? 'Ошибка импорта'
      importStep.value = 3
      showSnack('Ошибка импорта', 'error')
    } finally {
      itemsImportLoading.value = false
    }
  }

  async function doImportAllTables() {
    if (!importPreviewData.value?.sheets?.length) return
    if (!props.purchaseId) {
      showSnack('Множественный импорт доступен только для существующей закупки', 'warning')
      return
    }
    itemsImportLoading.value = true
    let totalAdded = 0
    let totalErrors: any[] = []
    try {
      for (const sheet of importPreviewData.value.sheets) {
        const detected = autoDetectMapping(sheet.headers)
        // Skip tables where we couldn't find item_name column
        if (detected['item_name'] === null || detected['item_name'] === undefined) {
          totalErrors.push({ sheet: sheet.name, reason: 'не найден столбец Наименование' })
          continue
        }
        const params = new URLSearchParams()
        if (sheet.name) params.set('sheet_name', sheet.name)
        params.set('header_row_offset', String(sheet.header_row_offset ?? 0))
        params.set('col_item_name', String(detected['item_name']))
        if (detected['quantity'] !== null) params.set('col_quantity', String(detected['quantity']))
        if (detected['unit_price'] !== null) params.set('col_unit_price', String(detected['unit_price']))
        if (detected['total_price'] !== null) params.set('col_total_price', String(detected['total_price']))
        if (detected['unit'] !== null) params.set('col_unit', String(detected['unit']))
        const fd = new FormData()
        fd.append('file', itemsImportFile.value as File)
        const token = localStorage.getItem('auth_token')
        try {
          const resp = await fetch(`/api/purchases/${props.purchaseId}/items/import-mapped?${params.toString()}`, {
            method: 'POST',
            headers: { Authorization: `Bearer ${token}` } as HeadersInit,
            body: fd,
          })
          if (!resp.ok) {
            const err = await resp.json().catch(() => ({}))
            totalErrors.push({ sheet: sheet.name, reason: err.detail || `HTTP ${resp.status}` })
            continue
          }
          const r = await resp.json()
          totalAdded += (r.added || 0)
        } catch (e: any) {
          totalErrors.push({ sheet: sheet.name, reason: e.message || 'network error' })
        }
      }
      if (totalAdded > 0) {
        showSnack(`Импортировано ${totalAdded} позиций из ${importPreviewData.value.sheets.length} таблиц${totalErrors.length ? ` (с ошибками в ${totalErrors.length})` : ''}`)
        emit('reload-requested')
        itemsImportDialog.value = false
      } else {
        const summary = totalErrors.length
          ? `Все таблицы пропущены. Причины: ${totalErrors.map(e => `${e.sheet}: ${e.reason}`).join('; ')}`
          : 'Ни одной позиции не импортировано'
        showSnack(summary, 'warning')
      }
    } finally {
      itemsImportLoading.value = false
    }
  }

  // ── Smart import ──────────────────────────────────────────────────────────────

  const smartImportFile = ref<File | null>(null)
  const smartImportFileList = ref<File[]>([])
  const smartImportLoading = ref(false)
  const smartImportSkipCatalog = ref(false)   // import-no-clutter: тогл «не добавлять в каталог»
  const smartImportPreview = ref<any[] | null>(null)
  const smartImportColumns = ref<string[] | null>(null)
  const smartImportResult = ref<{ added: number; matched_catalog: number; unmatched: number } | null>(null)

  // ── Product match review dialog ───────────────────────────────────────────────
  const matchReviewShow = ref(false)
  const matchReviewRows = ref<MatchRow[]>([])

  // ── Duplicate merge dialog (by product_id, after smart-import matching) ──────
  const dupMergeShow = ref(false)
  const dupMergeGroups = ref<DupGroup[]>([])
  // Pending items waiting for user decision in DuplicateMergeDialog
  let _pendingMergeItems: EditorItem[] = []

  // ── P1-B: Single product repick dialog ───────────────────────────────────────
  const repickDialog = ref<{ show: boolean; itemIdx: number; itemName: string }>({
    show: false,
    itemIdx: -1,
    itemName: '',
  })

  function openRepickDialog(idx: number) {
    repickDialog.value = {
      show: true,
      itemIdx: idx,
      itemName: localItems.value[idx]?.item_name || '',
    }
  }

  function onRepickPick(candidate: MatchCandidate) {
    const idx = repickDialog.value.itemIdx
    if (idx < 0) return
    const item = localItems.value[idx]
    if (!item) return
    applyMatchCandidate(item as any, candidate)
    repickDialog.value.show = false
    emitUpdate()
    showSnack(`Товар перепривязан: ${candidate.name}`, 'success')
  }

  const CRM_MAPPING_FIELDS: Record<string, string> = {
    item_name: 'Наименование',
    quantity: 'Кол-во',
    unit: 'Ед. изм.',
    unit_price: 'Цена за ед.',
    total_price: 'Сумма',
  }

  const crmFieldSelectItems = [
    { title: 'Наименование', value: 'item_name' },
    { title: 'Кол-во', value: 'quantity' },
    { title: 'Ед. изм.', value: 'unit' },
    { title: 'Цена за ед.', value: 'unit_price' },
    { title: 'Сумма', value: 'total_price' },
    { title: '— игнорировать', value: '_ignore' },
  ]

  const showMappingPanel = ref(false)
  const columnFieldMapping = ref<Record<string, string>>({})
  const columnMappingApplied = ref(false)

  // Layer 2: reactive proxy bundling the mutable UI state the ItemsImportWizard
  // child needs to two-way bind. Getters/setters delegate to the existing refs so
  // ALL business logic and state ownership stay in this composable (no duplication).
  const importWizardState = reactive({
    get isSmartMode() { return isSmartMode.value },
    set isSmartMode(v: boolean) { isSmartMode.value = v },
    get itemsImportFile() { return itemsImportFile.value },
    set itemsImportFile(v: File | null) { itemsImportFile.value = v },
    get importStep() { return importStep.value },
    set importStep(v: number) { importStep.value = v },
    get importSelectedSheet() { return importSelectedSheet.value },
    set importSelectedSheet(v: string) { importSelectedSheet.value = v },
    get dragMapping() { return dragMapping.value },
    set dragMapping(v: Record<string, number | null>) { dragMapping.value = v },
    get dragOverTarget() { return dragOverTarget.value },
    set dragOverTarget(v: string | null) { dragOverTarget.value = v },
    get smartImportFile() { return smartImportFile.value },
    set smartImportFile(v: File | null) { smartImportFile.value = v },
    get smartImportSkipCatalog() { return smartImportSkipCatalog.value },
    set smartImportSkipCatalog(v: boolean) { smartImportSkipCatalog.value = v },
    get showMappingPanel() { return showMappingPanel.value },
    set showMappingPanel(v: boolean) { showMappingPanel.value = v },
    get columnFieldMapping() { return columnFieldMapping.value },
    set columnFieldMapping(v: Record<string, string>) { columnFieldMapping.value = v },
  })

  watch(smartImportPreview, (v) => {
    if (v) {
      columnFieldMapping.value = Object.fromEntries(Object.keys(CRM_MAPPING_FIELDS).map(f => [f, f]))
      columnMappingApplied.value = false
      showMappingPanel.value = false
    }
  })

  function onSmartFileChange(files: File[] | File | null) {
    const fileArr = Array.isArray(files) ? files : (files ? [files] : [])
    smartImportFile.value = fileArr[0] ?? null
    smartImportPreview.value = null
    smartImportResult.value = null
  }

  function applyColumnMapping() {
    if (!smartImportPreview.value) return
    const mapping = columnFieldMapping.value
    smartImportPreview.value = smartImportPreview.value.map(row => {
      const newRow: any = { ...row }
      for (const [field, src] of Object.entries(mapping)) {
        newRow[field] = src === '_ignore' ? null : (row[src as keyof typeof row] ?? null)
      }
      return newRow
    })
    columnMappingApplied.value = true
    showMappingPanel.value = false
  }

  async function doSmartPreview() {
    if (!smartImportFile.value) return

    if (!props.purchaseId) {
      // 27.4-26b: Wish / no-pid context — XLSX через нативный smart парсер (без sample-обрезки).
      // PDF/DOCX/HTML остаются на старом preview-flow (sample 5 строк → требует UI mapping).
      const fileName = (smartImportFile.value?.name || '').toLowerCase()
      const isXlsx = fileName.endsWith('.xlsx') || fileName.endsWith('.xls')
      smartImportLoading.value = true
      smartImportPreview.value = null
      smartImportResult.value = null
      try {
        const token = localStorage.getItem('auth_token')
        const fd = new FormData()
        fd.append('file', smartImportFile.value)
        const endpoint = isXlsx
          ? '/api/purchases/items/import-smart-nopid'
          : '/api/purchases/items/import-preview'
        const resp = await fetch(endpoint, {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` } as HeadersInit,
          body: fd,
        })
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}))
          throw new Error(err.detail || err.message || `Ошибка ${resp.status}`)
        }
        const data = await resp.json()
        if (isXlsx) {
          // /import-smart-nopid возвращает уже распарсенные позиции — без sample-slice
          smartImportPreview.value = data.preview || []
          smartImportColumns.value = ['item_name', 'quantity', 'unit', 'unit_price', 'total_price']
          if (!smartImportPreview.value.length) showSnack('Позиции не распознаны', 'warning')
        } else {
          // legacy path для PDF/DOCX/HTML — sample 5 строк
          const firstSheet = data.sheets?.[0]
          if (!firstSheet) { showSnack('Позиции не распознаны', 'warning'); return }
          const detectedMapping = autoDetectMapping(firstSheet.headers || [])
          const headerOffset = firstSheet.header_row_offset ?? 0
          const dataRows = (firstSheet.sample as any[][]).slice(headerOffset + 1)
          const preview = dataRows
            .filter(row => {
              const nameIdx = detectedMapping['item_name']
              return nameIdx !== null && nameIdx !== undefined && String(row[nameIdx] ?? '').trim()
            })
            .map(row => {
              const item: Record<string, any> = {}
              for (const [field, idx] of Object.entries(detectedMapping)) {
                if (idx !== null && idx !== undefined) item[field] = row[idx]
              }
              return item
            })
          smartImportPreview.value = preview
          smartImportColumns.value = Object.keys(detectedMapping).filter(k => detectedMapping[k] !== null)
          if (!preview.length) showSnack('Позиции не распознаны', 'warning')
        }
      } catch (e: any) {
        showSnack(e.message || 'Ошибка распознавания', 'error')
      } finally {
        smartImportLoading.value = false
      }
      return
    }

    // Purchase context with pid
    smartImportLoading.value = true
    smartImportPreview.value = null
    smartImportResult.value = null
    try {
      const token = localStorage.getItem('auth_token')
      const fd = new FormData()
      fd.append('file', smartImportFile.value)
      const resp = await fetch(`/api/purchases/${props.purchaseId}/items/import-smart?confirm=false`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` } as HeadersInit,
        body: fd,
      })
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}))
        throw new Error(err.detail || err.message || `Ошибка ${resp.status}`)
      }
      const data = await resp.json()
      // QR ФНС: чек сразу создан на сервере (без preview), закрываем диалог
      if (data.source === 'qr_fns') {
        showSnack(data.message || 'Чек импортирован по QR ФНС', 'success')
        emit('reload-requested')
        itemsImportDialog.value = false
        return
      }
      smartImportPreview.value = data.preview || []
      smartImportColumns.value = data.columns_found || []
      if (data.warning) showSnack(data.warning, 'warning')
      if (!smartImportPreview.value.length) showSnack('Позиции не распознаны', 'warning')
    } catch (e: any) {
      showSnack(e.message || 'Ошибка распознавания', 'error')
    } finally {
      smartImportLoading.value = false
    }
  }

  // ── Product match review helpers ─────────────────────────────────────────────

  /** Commit items built from preview rows after product matching.
   *  resolved[i].product_id   — matched catalog id (or null → create_new)
   *  resolved[i].create_new   — true when backend should create a new catalog entry
   *  Both the "confirmed via dialog" and "bypass" paths share this commit logic.
   */
  function commitPreviewItems(resolved: ResolvedRow[]) {
    if (!smartImportPreview.value?.length) return
    const previewRows = smartImportPreview.value

    // Phase 27.1 D-02: contract items branch
    if (contractItemImportMode.value) {
      const newContractItems: ContractItem[] = previewRows.map((row, i) => ({
        id: 0,
        purchase_id: props.purchaseId || 0,
        source_item_id: null,
        contract_id: null,
        product_id: resolved[i]?.product_id ?? null,
        name: row.item_name || row.name || '',
        quantity: row.quantity ?? null,
        unit: row.unit ?? null,
        unit_price: row.unit_price ?? null,
        total: row.total_price ?? row.total ?? null,
        match_confirmed: resolved[i]?.product_id != null,
      }))
      localContractItems.value = newContractItems
      contractItemImportMode.value = false
      emitContractItemsUpdate()
      smartImportResult.value = { added: newContractItems.length, matched_catalog: resolved.filter(r => r.product_id != null).length, unmatched: resolved.filter(r => r.create_new).length }
      showSnack(`${newContractItems.length} позиций договора импортированы.`, 'info')
      itemsImportDialog.value = false
      return
    }

    // Normal items branch
    const newItems: EditorItem[] = previewRows.map((row, i) => {
      const res = resolved[i]
      const cand = res?.chosen_candidate ?? null
      // P0-B: если привязан к каталогу — берём имя/описание/фото из кандидата
      const hasCatalog = res?.product_id != null && cand != null
      const item: EditorItem = {
        _uid: nextUid(),
        product_id: res?.product_id ?? null,
        // item_name: из каталога если привязан, иначе из xlsx
        item_name: hasCatalog ? (cand!.name || row.item_name || '') : (row.item_name || ''),
        // item_type: из каталога если есть, иначе из xlsx или дефолт
        item_type: hasCatalog && cand!.item_type ? cand!.item_type : (row.item_type || props.defaultItemType),
        // qty/unit_price/total_price ВСЕГДА из xlsx
        quantity: row.quantity ?? null,
        unit: row.unit || props.defaultUnit,
        unit_price: row.unit_price ?? null,
        total_price: row.total_price ?? null,
        country_origin: props.defaultCountry,
        _selectedProduct: null,
        _photo_url: hasCatalog ? (cand!.photo_url ?? undefined) : undefined,
        _description: hasCatalog ? (cand!.description ?? undefined) : undefined,
        _description_44fz: undefined,
        _price_meta: hasCatalog ? {
          price_updated_at: cand!.price_updated_at ?? null,
          price_source: cand!.price_source ?? null,
          price_source_ref: cand!.price_source_ref ?? null,
          price_freshness: cand!.price_freshness ?? null,
        } : null,
      }
      if (props.itemShape === 'purchase') {
        item.final_unit_price = null
        item.final_total = null
        // F-PLAN: импортированные строки сразу наследуют шапочную плановую позицию
        item.feo_planned_item_id = props.defaultFeoPlannedItemId ?? null
      }
      return item
    })
    // ── Detect duplicates by product_id ──────────────────────────────────────
    const productGroups = new Map<number, EditorItem[]>()
    for (const item of newItems) {
      if (item.product_id != null) {
        const pid = item.product_id
        if (!productGroups.has(pid)) productGroups.set(pid, [])
        productGroups.get(pid)!.push(item)
      }
    }
    const dupGroups: DupGroup[] = []
    for (const [pid, groupItems] of productGroups.entries()) {
      if (groupItems.length > 1) {
        dupGroups.push({
          product_id: pid,
          name: groupItems[0].item_name || `ID ${pid}`,
          items: groupItems.map(it => ({
            quantity: it.quantity ?? null,
            unit_price: it.unit_price ?? null,
            total_price: it.total_price ?? null,
          })),
          _choice: 'merge',
        })
      }
    }

    if (dupGroups.length > 0) {
      // Show dialog — commit will happen in onDupMergeConfirm
      _pendingMergeItems = newItems
      dupMergeGroups.value = dupGroups
      dupMergeShow.value = true
      // Store resolved count info for later snack
      ;(window as any).__pendingImportMatchedCount = resolved.filter(r => r.product_id != null).length
      itemsImportDialog.value = false
      return
    }

    // No duplicates — commit immediately
    localItems.value.push(...newItems)
    emitUpdate()
    const matchedCount = resolved.filter(r => r.product_id != null).length
    smartImportResult.value = { added: newItems.length, matched_catalog: matchedCount, unmatched: newItems.length - matchedCount }
    showSnack(`${newItems.length} позиций добавлены в список.`, 'info')
    itemsImportDialog.value = false
  }

  /** Handler for DuplicateMergeDialog @confirm */
  function onDupMergeConfirm(resolvedGroups: ResolvedGroup[]) {
    const mergeMap = new Map<number, ResolvedGroup>()
    for (const rg of resolvedGroups) {
      mergeMap.set(rg.product_id, rg)
    }

    // Build final items: for groups with choice=merge keep only merged item, else keep all
    const seenMerged = new Set<number>()
    const finalItems: EditorItem[] = []

    for (const item of _pendingMergeItems) {
      const pid = item.product_id
      if (pid == null) {
        finalItems.push(item)
        continue
      }
      const rg = mergeMap.get(pid)
      if (!rg || rg.choice === 'keep') {
        finalItems.push(item)
        continue
      }
      // merge choice — push merged item once
      if (!seenMerged.has(pid)) {
        seenMerged.add(pid)
        const mi = rg.mergedItem!
        finalItems.push({
          ...item,
          quantity: mi.quantity,
          unit_price: mi.unit_price,
          total_price: mi.total_price,
        })
      }
      // subsequent items in the same group are dropped
    }

    localItems.value.push(...finalItems)
    emitUpdate()
    const matchedCount = (window as any).__pendingImportMatchedCount ?? 0
    delete (window as any).__pendingImportMatchedCount
    smartImportResult.value = { added: finalItems.length, matched_catalog: matchedCount, unmatched: finalItems.length - matchedCount }
    showSnack(`${finalItems.length} позиций добавлены в список.`, 'info')
    _pendingMergeItems = []
  }

  /** Handler for ProductMatchReviewDialog @confirm event */
  function onMatchConfirm(resolved: ResolvedRow[]) {
    matchReviewShow.value = false
    commitPreviewItems(resolved)
  }

  /** Handler for ProductMatchReviewDialog @cancel event */
  function onMatchCancel() {
    matchReviewShow.value = false
    // Do not commit anything — leave import dialog open so user sees the preview
  }

  async function doSmartImport() {
    if (!smartImportPreview.value?.length) return

    // If user applied custom column mapping OR no purchaseId, run product matching first
    if (columnMappingApplied.value || !props.purchaseId) {
      // TODO: contract items mode currently bypasses product matching (needs separate design)
      if (contractItemImportMode.value) {
        const bypassResolved = smartImportPreview.value.map(row => ({
          query: row.item_name || row.name || '',
          product_id: null as number | null,
          create_new: true,
        }))
        commitPreviewItems(bypassResolved)
        return
      }

      // «Не добавлять в каталог» (напр. авансовые платежи): позиции должны быть
      // один-в-один как в чеке. Сопоставление с каталогом не нужно — коммитим как есть,
      // без привязки и без диалога.
      if (smartImportSkipCatalog.value) {
        const skipResolved = smartImportPreview.value.map(row => ({
          query: row.item_name || '',
          product_id: null as number | null,
          create_new: false,
        }))
        commitPreviewItems(skipResolved)
        return
      }

      // Call /api/products/match to get suggestions, then show review dialog
      const queries: string[] = smartImportPreview.value.map(row => row.item_name || '')
      smartImportLoading.value = true
      try {
        const matchData = await apiFetch<{
          results: Array<{ query: string; status: 'auto' | 'suggest' | 'create'; candidates: MatchCandidate[] }>
        }>('/products/match', { method: 'POST', body: { queries } })
        matchReviewRows.value = matchData.results.map(r => ({ ...r, _choice: undefined }))
        matchReviewShow.value = true
      } catch (e: any) {
        // If match endpoint not available yet, fall back to direct commit without matching
        // TODO: remove fallback once /api/products/match is stable
        showSnack('Сопоставление с каталогом недоступно, позиции добавлены без привязки', 'warning')
        const fallbackResolved = smartImportPreview.value.map(row => ({
          query: row.item_name || '',
          product_id: null as number | null,
          create_new: true,
        }))
        commitPreviewItems(fallbackResolved)
      } finally {
        smartImportLoading.value = false
      }
      return
    }

    if (!smartImportFile.value || !props.purchaseId) return
    smartImportLoading.value = true
    try {
      const token = localStorage.getItem('auth_token')
      const fd = new FormData()
      fd.append('file', smartImportFile.value)
      const resp = await fetch(`/api/purchases/${props.purchaseId}/items/import-smart?confirm=true&skip_catalog=${smartImportSkipCatalog.value}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` } as HeadersInit,
        body: fd,
      })
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}))
        throw new Error(err.detail || err.message || `Ошибка ${resp.status}`)
      }
      smartImportResult.value = await resp.json()
      if (smartImportResult.value!.added > 0) {
        showSnack(`Импортировано ${smartImportResult.value!.added} позиций`)
        emit('reload-requested')
      }
    } catch (e: any) {
      showSnack(e.message || 'Ошибка импорта', 'error')
    } finally {
      smartImportLoading.value = false
    }
  }

  // import-pdf-debug C3: скачать debug-отчёт для несработавшего файла
  async function downloadDebugReport() {
    if (!smartImportFile.value) return
    const fd = new FormData()
    fd.append('file', smartImportFile.value)
    try {
      const token = localStorage.getItem('auth_token') || ''
      const res = await fetch('/api/purchases/items/import-pdf-debug', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` } as HeadersInit,
        body: fd,
      })
      const data = await res.json()
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `import-debug-${smartImportFile.value.name}.json`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      showSnack('Не удалось получить debug-отчёт', 'error')
    }
  }

  return {
    // Excel import
    itemsImportDialog, isSmartMode, itemsImportFile, itemsImportLoading, itemsImportResult,
    importStep, importPreviewData, importSelectedSheet, dragMapping, ignoredColumns,
    dragOverTarget, importError, TARGET_FIELDS,
    currentSheetData, currentSheetHeaders, mappingHasName, unmappedCount,
    isMapped, isIgnored, isTargetFilled, getColumnLabel, getSamples,
    onDragStart, onDropToTarget, onDropToUnresolved, unmapTarget, ignoreColumn,
    autoDetectMapping, openImportDialog, openSmartImportDialog, switchImportMode,
    closeImportDialog, doImportPreview, buildEditorItemFromRow, doMappedImport, doImportAllTables,
    // Smart import
    smartImportFile, smartImportFileList, smartImportLoading, smartImportSkipCatalog,
    smartImportPreview, smartImportColumns, smartImportResult,
    onSmartFileChange, applyColumnMapping, doSmartPreview, doSmartImport, downloadDebugReport,
    CRM_MAPPING_FIELDS, crmFieldSelectItems, showMappingPanel, columnFieldMapping,
    columnMappingApplied, importWizardState,
    // Product match review
    matchReviewShow, matchReviewRows, onMatchConfirm, onMatchCancel, commitPreviewItems,
    // Duplicate merge
    dupMergeShow, dupMergeGroups, onDupMergeConfirm,
    // P1-B repick
    repickDialog, openRepickDialog, onRepickPick,
  }
}
