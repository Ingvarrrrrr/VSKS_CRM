// Состояние и логика мастера импорта категорий ФЭО из Excel/Word/PDF —
// вынесены из SubsidiesView.vue. Module-level singleton state, как
// useSubsidyApprovers.ts/usePlanGraphVersions.ts/usePlannedItems.ts в этом же
// проекте: родитель триггерит открытие мастера напрямую (`feoImport.show = true`
// на кнопке «Импорт» в тулбаре дерева ФЭО — тот же приём, что и раньше, когда
// feoImport была локальным reactive() в SubsidiesView.vue), а FeoImportWizard.vue
// читает/пишет то же самое состояние через useFeoImport(useSubsidyDetailCtx()).
import { computed, reactive, ref, watch } from 'vue'
import { useToast, type ToastType } from '@/composables/useToast'
import type { SubsidyDetailContext } from './useSubsidyDetail'
import type { FeoImportResult, FeoUnmatchedNode, FeoWarning } from './types'

export function feoWarnKindLabel(kind: string): string {
  const labels: Record<string, string> = {
    level_gap: 'Пропущенный уровень поднят выше',
    level_duplicate: 'Одинаковые уровни склеены в один узел',
    sum_mismatch: 'Сумма не совпадает с кол-во × цена',
    sum_without_qty: 'Сумма задана без количества',
    parent_sum_mismatch: 'Бюджет родителя ≠ сумма дочерних',
    level_name_in_number_column: 'Название уровня стояло в числовой колонке',
    item_promoted_to_level2: 'Плановая позиция без уровней — создана направлением',
    item_type_unknown: 'Не распознан тип товар/услуга',
    column_shift: 'Похоже, колонки сдвинуты — число попало не в ту колонку',
    group_plan_ignored: 'План строки не записан — у категории есть подкатегории',
    plan_vs_items_mismatch: 'План строки не совпадает с суммой плановых позиций',
    plan_skipped_has_items: 'План строки не записан — у категории уже есть позиции',
  }
  return labels[kind] ?? kind
}
export function feoWarnSubtitle(w: FeoWarning): string {
  return w.row != null ? `Стр. ${w.row} — ${w.message}` : w.message
}

const feoImport = reactive({
  show: false, step: 1, file: null as File | null, fileList: [] as File[],
  loading: false,
  result: null as FeoImportResult | null,
  dryResult: null as FeoImportResult | null,
  previewData: null as any,
  selectedSheet: '',
  // ключ = unmatched.id, значение = выбранный new_path либо null («оставить как есть»)
  remap: {} as Record<number, string | null>,
})

const feoImportTargetSubsidy = ref<number | null>(null)

// FEO column mapping
const FEO_TARGET_FIELDS = [
  { value: 'subsidy',  title: 'Субсидия (название)',                          required: true },
  { value: 'lvl2',     title: 'Уровень 2 — Направление расходов по ФЭО',     required: true },
  { value: 'qty_lvl2',      title: 'Количество для Уровня 2 (Направление)',       required: false },
  { value: 'unit_lvl2',     title: 'Единица измерения для Уровня 2',              required: false },
  { value: 'amt_lvl2',      title: 'Плановая стоимость за ед. для Уровня 2 (Направление)', required: false },
  { value: 'plan_sum_lvl2', title: 'Сумма плана (Ур.2)',                          required: false },
  { value: 'lvl3',          title: 'Уровень 3 — Тип расходов по ФЭО',            required: false },
  { value: 'qty_lvl3',      title: 'Количество для Уровня 3 (Тип расходов)',      required: false },
  { value: 'unit_lvl3',     title: 'Единица измерения для Уровня 3',              required: false },
  { value: 'amt_lvl3',      title: 'Плановая стоимость за ед. для Уровня 3 (Тип расходов)', required: false },
  { value: 'plan_sum_lvl3', title: 'Сумма плана (Ур.3)',                          required: false },
  { value: 'lvl4',          title: 'Уровень 4 — Конкретизированный',              required: false },
  { value: 'qty_lvl4',      title: 'Количество для Уровня 4 (Конкретизир.)',      required: false },
  { value: 'unit_lvl4',     title: 'Единица измерения для Уровня 4',              required: false },
  { value: 'amt_lvl4',      title: 'Плановая стоимость за ед. для Уровня 4 (Конкретизир.)', required: false },
  { value: 'plan_sum_lvl4', title: 'Сумма плана (Ур.4)',                          required: false },
  { value: 'lvl5',          title: 'Плановая позиция (папку не создаёт)',        required: false },
  { value: 'item_type',       title: 'Товар/услуга',                             required: false },
  // Новый плоский 18-колоночный шаблон (2026-08-14): одна пара колонок «по ФЭО»/«плана»
  // на всю строку — вместо колонок-на-каждый-уровень выше. См. col_row_* в _do_feo_import.
  { value: 'row_feo_qty',     title: 'Количество по ФЭО',                        required: false },
  { value: 'row_feo_unit',    title: 'Ед. изм. по ФЭО',                          required: false },
  { value: 'row_feo_price',   title: 'Цена за единицу по ФЭО',                   required: false },
  { value: 'row_feo_sum',     title: 'Сумма по ФЭО',                             required: false },
  { value: 'row_plan_qty',    title: 'Плановое количество',                      required: false },
  { value: 'row_plan_unit',   title: 'Ед. изм. плана',                           required: false },
  { value: 'row_plan_price',  title: 'Плановая цена за единицу',                 required: false },
  { value: 'row_plan_sum',    title: 'Сумма плана',                              required: false },
  { value: 'quantity',      title: 'Количество для Уровня 5 (Товар/услуга)',      required: false },
  { value: 'unit',          title: 'Единица измерения (Ур.5: шт, кг, услуга)',   required: false },
  { value: 'item_amt',      title: 'Сумма по позиции (Ур.5)',                     required: false },
  { value: 'item_price',    title: 'Цена за ед. (Ур.5)',                          required: false },
  { value: 'feo_qty_lvl2',    title: 'Кол-во по ФЭО (Ур.2)',                     required: false },
  { value: 'feo_unit_lvl2',   title: 'Ед. изм. по ФЭО (Ур.2)',                  required: false },
  { value: 'feo_amount_lvl2', title: 'Стоимость по ФЭО (Ур.2)',                  required: false },
  { value: 'feo_sum_lvl2',    title: 'Сумма по ФЭО (Ур.2)',                      required: false },
  { value: 'feo_qty_lvl3',    title: 'Кол-во по ФЭО (Ур.3)',                     required: false },
  { value: 'feo_unit_lvl3',   title: 'Ед. изм. по ФЭО (Ур.3)',                  required: false },
  { value: 'feo_amount_lvl3', title: 'Стоимость по ФЭО (Ур.3)',                  required: false },
  { value: 'feo_sum_lvl3',    title: 'Сумма по ФЭО (Ур.3)',                      required: false },
  { value: 'feo_qty_lvl4',    title: 'Кол-во по ФЭО (Ур.4)',                     required: false },
  { value: 'feo_unit_lvl4',   title: 'Ед. изм. по ФЭО (Ур.4)',                  required: false },
  { value: 'feo_amount_lvl4', title: 'Стоимость по ФЭО (Ур.4)',                  required: false },
  { value: 'feo_sum_lvl4',    title: 'Сумма по ФЭО (Ур.4)',                      required: false },
  { value: 'code',     title: 'Код категории ФЭО (Ур.2–4)',                 required: false },
  { value: 'appendix', title: 'Номер приложения (Ур.2–4: Прил. 1, Прил. 2...)', required: false },
  { value: 'budget',   title: 'Финансирование по ФЭО (Ур.2–4)', required: false },
  { value: 'active',   title: 'Активна (да / нет)',                          required: false },
]
const feoDragMapping = ref<Record<string, number | null>>({})
const feoIgnoredCols = ref<number[]>([])
const feoDragOverTarget = ref<string | null>(null)
const feoResultPanels = ref<string[]>([])
function feoToggleResultPanel(key: string) {
  const i = feoResultPanels.value.indexOf(key)
  if (i >= 0) feoResultPanels.value.splice(i, 1)
  else feoResultPanels.value.push(key)
}
// При переходе на шаг 3 (dry-run) или шаг 5 (результат) раскрываем панели предупреждений
watch(() => feoImport.step, (step) => {
  if (step === 3 && feoImport.dryResult?.warnings?.length) {
    const warnKeys = [...new Set(feoImport.dryResult.warnings.map(w => w.kind))].map(k => 'dw_' + k)
    warnKeys.forEach(k => { if (!feoResultPanels.value.includes(k)) feoResultPanels.value.push(k) })
  } else if (step === 5 && feoImport.result?.warnings?.length) {
    const warnKeys = [...new Set(feoImport.result.warnings.map(w => w.kind))].map(k => 'rw_' + k)
    warnKeys.forEach(k => { if (!feoResultPanels.value.includes(k)) feoResultPanels.value.push(k) })
  }
})

// Узлы, которым не хватает цели переезда — требуют решения человека (шаг «Сопоставление»)
const feoUnmatchedNeedsMapping = computed<FeoUnmatchedNode[]>(() =>
  (feoImport.dryResult?.unmatched || []).filter(u => u.kind === 'needs_mapping'))
const feoHasSuggestions = computed(() => feoUnmatchedNeedsMapping.value.some(n => !!n.suggestion))
const feoRemapPlannedCount = computed(() =>
  feoUnmatchedNeedsMapping.value.filter(n => !!feoImport.remap[n.id]).length)
function feoAcceptAllSuggestions() {
  feoUnmatchedNeedsMapping.value.forEach(n => { if (n.suggestion) feoImport.remap[n.id] = n.suggestion })
}
const feoStep4MainLabel = computed(() => {
  const parts = ['Импортировать']
  if (feoRemapPlannedCount.value) parts.push(`перенести ${feoRemapPlannedCount.value}`)
  const deleted = feoImport.dryResult?.deleted_count ?? 0
  if (deleted) parts.push(`удалить ${deleted}`)
  return parts.join(', ')
})
function feoPluralRu(n: number, forms: [string, string, string]): string {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return forms[0]
  if ([2, 3, 4].includes(mod10) && ![12, 13, 14].includes(mod100)) return forms[1]
  return forms[2]
}
function feoLoadSummary(load: FeoUnmatchedNode['load'] | undefined): string {
  if (!load) return 'ничего'
  const parts: string[] = []
  if (load.purchases) parts.push(`${load.purchases} ${feoPluralRu(load.purchases, ['закупка', 'закупки', 'закупок'])}`)
  if (load.purchase_items) parts.push(`${load.purchase_items} ${feoPluralRu(load.purchase_items, ['позиция закупки', 'позиции закупки', 'позиций закупки'])}`)
  if (load.wishes) parts.push(`${load.wishes} ${feoPluralRu(load.wishes, ['заявка', 'заявки', 'заявок'])}`)
  if (load.wish_items) parts.push(`${load.wish_items} ${feoPluralRu(load.wish_items, ['позиция заявки', 'позиции заявки', 'позиций заявки'])}`)
  if (load.products) parts.push(`${load.products} ${feoPluralRu(load.products, ['товар', 'товара', 'товаров'])}`)
  if (load.feo_planned_items) parts.push(`${load.feo_planned_items} ${feoPluralRu(load.feo_planned_items, ['плановая позиция', 'плановые позиции', 'плановых позиций'])}`)
  return parts.length ? parts.join(', ') : 'ничего'
}

const feoCurrentSheet = computed(() => {
  if (!feoImport.previewData) return null
  const sheets = feoImport.previewData.sheets
  return sheets.find((s: any) => s.name === feoImport.selectedSheet) || sheets[0]
})
const feoCurrentHeaders = computed<string[]>(() => feoCurrentSheet.value?.headers || [])
const feoMappingValid = computed(() =>
  feoDragMapping.value['lvl2'] != null &&
  (feoDragMapping.value['subsidy'] != null || feoImportTargetSubsidy.value != null)
)
const feoUnmappedCount = computed(() =>
  feoCurrentHeaders.value.filter((_: any, i: number) => !feoIsMapped(i) && !feoIsIgnored(i)).length
)

function feoIsMapped(idx: number): boolean {
  return Object.values(feoDragMapping.value).includes(idx)
}
function feoIsIgnored(idx: number): boolean {
  return feoIgnoredCols.value.includes(idx)
}
function feoIsTargetFilled(field: string): boolean {
  return feoDragMapping.value[field] != null
}
function feoGetColumnLabel(idx: number): string {
  return (feoCurrentHeaders.value[idx] as string) || `Столбец ${idx + 1}`
}
function feoGetSamples(idx: number): string[] {
  const sample = feoCurrentSheet.value?.sample || []
  return (sample as any[][]).slice(0, 3)
    .map((row: any[]) => String(row[idx] ?? '').trim())
    .filter(Boolean)
}
function feoOnDragStart(idx: number, e: DragEvent) {
  e.dataTransfer!.effectAllowed = 'move'
  e.dataTransfer!.setData('text/plain', String(idx))
}
function feoOnDropToTarget(field: string, e: DragEvent) {
  const idx = parseInt(e.dataTransfer!.getData('text/plain'))
  for (const f of Object.keys(feoDragMapping.value)) {
    if (feoDragMapping.value[f] === idx) feoDragMapping.value[f] = null
  }
  feoDragMapping.value[field] = idx
  feoDragOverTarget.value = null
}
function feoOnDropToUnresolved(e: DragEvent) {
  const idx = parseInt(e.dataTransfer!.getData('text/plain'))
  for (const f of Object.keys(feoDragMapping.value)) {
    if (feoDragMapping.value[f] === idx) feoDragMapping.value[f] = null
  }
  feoDragOverTarget.value = null
}
function feoUnmapTarget(field: string) {
  feoDragMapping.value[field] = null
}
function feoIgnoreColumn(idx: number) {
  for (const f of Object.keys(feoDragMapping.value)) {
    if (feoDragMapping.value[f] === idx) feoDragMapping.value[f] = null
  }
  if (!feoIgnoredCols.value.includes(idx)) feoIgnoredCols.value.push(idx)
}

function feoAutoMap(headers: string[]) {
  const mapping: Record<string, number | null> = {}
  for (const f of FEO_TARGET_FIELDS) mapping[f.value] = null
  const KEYWORDS: Record<string, string[]> = {
    subsidy:  ['субсидия'],
    lvl2:     ['уровень 2', 'направление расходов', 'level 2'],
    qty_lvl2:  ['кол-во (ур.2)', 'кол-во ур.2', 'количество (ур.2)'],
    unit_lvl2: ['ед. изм. (ур.2)', 'ед.изм. ур.2', 'единица ур.2'],
    // amt_lvl2 = цена за ед. — только специфичные алиасы, без «сумма» (сумму забирает plan_sum_lvl2)
    amt_lvl2:  ['плановая стоимость за ед. (ур.2)', 'плановая стоимость (ур.2)', 'стоимость за ед. (ур.2)', 'стоимость ур.2'],
    plan_sum_lvl2: ['сумма плана (ур.2)', 'плановая сумма (ур.2)', 'сумма ур.2'],
    lvl3:      ['уровень 3', 'тип расходов', 'level 3'],
    qty_lvl3:  ['кол-во (ур.3)', 'кол-во ур.3', 'количество (ур.3)'],
    unit_lvl3: ['ед. изм. (ур.3)', 'ед.изм. ур.3', 'единица ур.3'],
    // amt_lvl3 = цена за ед.
    amt_lvl3:  ['плановая стоимость за ед. (ур.3)', 'плановая стоимость (ур.3)', 'стоимость за ед. (ур.3)', 'стоимость ур.3'],
    plan_sum_lvl3: ['сумма плана (ур.3)', 'плановая сумма (ур.3)', 'сумма ур.3'],
    lvl4:         ['уровень 4', 'конкретизир', 'level 4'],
    qty_lvl4:     ['кол-во (ур.4)', 'кол-во ур.4', 'количество (ур.4)'],
    unit_lvl4:    ['ед. изм. (ур.4)', 'ед.изм. ур.4', 'единица ур.4'],
    // amt_lvl4 = цена за ед.
    amt_lvl4:     ['плановая стоимость за ед. (ур.4)', 'плановая стоимость (ур.4)', 'стоимость за ед. (ур.4)', 'стоимость ур.4'],
    plan_sum_lvl4: ['сумма плана (ур.4)', 'плановая сумма (ур.4)', 'сумма ур.4'],
    // feo_sum_* идут ДО feo_amount_* (более специфичны «сумма по фэо»)
    feo_sum_lvl2:    ['сумма по фэо (ур.2)', 'сумма по фэо ур.2'],
    // Бэкенд (see find_col в import_feo_from_excel) НЕ имеет generic-фолбэка без
    // «(Ур.2)» для этих трёх — иначе эти ключи перехватывали бы плоские колонки
    // нового 18-колоночного шаблона («Количество по ФЭО» и т.п.), которые обязаны
    // достаться row_feo_qty/row_feo_unit/row_feo_price ниже
    feo_qty_lvl2:    ['кол-во по фэо (ур.2)', 'кол-во по фэо ур.2'],
    feo_unit_lvl2:   ['ед. изм. по фэо (ур.2)', 'ед. изм. по фэо ур.2'],
    feo_amount_lvl2: ['стоимость по фэо (ур.2)', 'стоимость по фэо ур.2'],
    feo_sum_lvl3:    ['сумма по фэо (ур.3)', 'сумма по фэо ур.3'],
    feo_qty_lvl3:    ['кол-во по фэо (ур.3)', 'кол-во по фэо ур.3'],
    feo_unit_lvl3:   ['ед. изм. по фэо (ур.3)', 'ед. изм. по фэо ур.3'],
    feo_amount_lvl3: ['стоимость по фэо (ур.3)', 'стоимость по фэо ур.3'],
    feo_sum_lvl4:    ['сумма по фэо (ур.4)', 'сумма по фэо ур.4'],
    feo_qty_lvl4:    ['кол-во по фэо (ур.4)', 'кол-во по фэо ур.4'],
    feo_unit_lvl4:   ['ед. изм. по фэо (ур.4)', 'ед. изм. по фэо ур.4'],
    feo_amount_lvl4: ['стоимость по фэо (ур.4)', 'стоимость по фэо ур.4'],
    lvl5:     ['плановая позиция', 'уровень 5', 'плановый товар', 'level 5'],
    // Новый плоский 18-колоночный шаблон (2026-08-14): одна пара «по ФЭО»/«плана» на
    // всю строку. Объявлены ПОСЛЕ всех per-level ключей выше и ДО generic-фолбэков
    // ниже (quantity/unit/item_amt/item_price) — порядок и слова совпадают с
    // col_row_* в import_feo_mapped/import_feo_from_excel (backend). lvl5 обязан
    // резолвиться раньше item_type, иначе «Уровень 5 (Плановый товар/услуга)»
    // старого шаблона перехватит item_type своим «товар/услуга» — здесь lvl5 уже
    // объявлен строкой выше, порядок соблюдён.
    row_feo_qty:    ['количество по фэо'],
    row_feo_unit:   ['ед. изм. по фэо'],
    row_feo_price:  ['цена за единицу по фэо', 'цена за ед. по фэо'],
    row_feo_sum:    ['сумма по фэо'],
    row_plan_qty:   ['плановое количество'],
    row_plan_unit:  ['ед. изм. плана'],
    row_plan_price: ['плановая цена за единицу', 'плановая цена за ед.'],
    row_plan_sum:   ['сумма плана'],
    item_type:      ['товар/услуга', 'тип позиции'],
    code:     ['код'],
    appendix: ['приложение'],
    budget:   ['финансирование', 'бюджет'],
    quantity: ['количество (ур.5)', 'количество ур.5', 'кол-во (ур.5)', 'кол-во ур.5'],
    unit:     ['ед. измерения (ур.5)', 'ед. изм. (ур.5)', 'ед.изм. ур.5', 'единица ур.5', 'ед. изм', 'ед.изм', 'единица'],
    // item_amt = итог позиции (amount); item_price = цена за ед. — специфичные ключи первыми
    item_amt:   ['сумма по позиции (ур.5)', 'сумма плановая', 'сумма (ур.5)', 'плановая стоимость за ед. (ур.5)', 'плановая стоимость (ур.5)', 'стоимость за ед. (ур.5)', 'стоимость ур.5', 'сумма ур'],
    item_price: ['цена за ед. (ур.5)', 'стоимость за ед. (ур.5)'],
    active:   ['активна', 'активен'],
  }
  // Каждая колонка достаётся ровно одному полю: без этого generic-ключи
  // («ед. изм») утаскивали колонку Ур.2 в поле Ур.5
  const used = new Set<number>()
  for (const [field, kws] of Object.entries(KEYWORDS)) {
    for (const kw of kws) {
      let found = -1
      for (let i = 0; i < headers.length; i++) {
        if (used.has(i)) continue
        if (headers[i]!.toLowerCase().includes(kw)) { found = i; break }
      }
      if (found >= 0) {
        mapping[field] = found
        used.add(found)
        break
      }
    }
  }
  feoDragMapping.value = mapping
}

// Нужные диалогу куски общего контекста детали субсидии — Pick вместо полного
// SubsidyDetailContext (см. тот же приём в usePlanGraphVersions.ts/usePlannedItems.ts).
type FeoImportCtx = Pick<SubsidyDetailContext, 'selectedId' | 'allSubsidies' | 'loadFeo' | 'syncFeoFilled'>

// ctx — опциональный: сам SubsidiesView.vue не вызывает useFeoImport() вовсе (кнопка
// «Импорт» в тулбаре просто ставит feoImport.show = true — тот же reactive-объект,
// импортированный напрямую), только FeoImportWizard.vue — настоящий потомок,
// вызывает useFeoImport(useSubsidyDetailCtx()).
export function useFeoImport(ctx?: FeoImportCtx) {
  const toast = useToast()
  function showSnack(text: string, color: ToastType = 'success', opts?: { actionText?: string; onAction?: () => void; duration?: number }) {
    toast.addToast(text, color, opts)
  }

  async function doFeoImport() {
    if (!feoImport.file) return
    feoImport.loading = true
    try {
      const fd = new FormData()
      fd.append('file', feoImport.file)
      const token = localStorage.getItem('auth_token')
      const res = await fetch('/api/feo-categories/import-preview', {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: fd,
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        showSnack(err.detail || 'Ошибка чтения файла', 'error'); return
      }
      const data = await res.json()
      feoImport.previewData = data
      feoImport.selectedSheet = data.sheets[0]?.name || ''
      feoIgnoredCols.value = []
      feoAutoMap(data.sheets[0]?.headers || [])
      feoImportTargetSubsidy.value = ctx?.selectedId.value ?? null
      feoImport.step = 2
    } catch {
      showSnack('Ошибка чтения файла', 'error')
    } finally {
      feoImport.loading = false
    }
  }

  async function doFeoMappedImport(dryRun = false, keepStep = false) {
    if (!feoImport.file) return
    feoImport.loading = true
    try {
      const m = feoDragMapping.value
      const sheet = feoCurrentSheet.value
      // remap задаётся путём, а не id: у целевого узла в момент показа таблицы ещё нет id — он появится только при записи
      const remapEntries = Object.entries(feoImport.remap)
        .filter(([, newPath]) => !!newPath)
        .map(([oldId, newPath]) => ({ old_id: Number(oldId), new_path: newPath as string }))
      const params = new URLSearchParams({
        sheet_name: feoImport.selectedSheet,
        header_row_offset: String(sheet?.header_row_offset ?? 0),
        dry_run: dryRun ? 'true' : 'false',
        apply_remap: 'true',
        col_subsidy:  String(m['subsidy']  ?? -1),
        default_subsidy_id: String(feoImportTargetSubsidy.value ?? -1),
        col_lvl2:     String(m['lvl2']     ?? -1),
        col_lvl3:     String(m['lvl3']     ?? -1),
        col_lvl4:     String(m['lvl4']     ?? -1),
        col_lvl5:     String(m['lvl5']     ?? -1),
        col_code:     String(m['code']     ?? -1),
        col_appendix: String(m['appendix'] ?? -1),
        col_budget:   String(m['budget']   ?? -1),
        col_quantity: String(m['quantity'] ?? -1),
        col_unit:      String(m['unit']      ?? -1),
        col_item_amt:  String(m['item_amt']  ?? -1),
        col_active:    String(m['active']    ?? -1),
        col_qty_lvl2:  String(m['qty_lvl2']  ?? -1),
        col_qty_lvl3:  String(m['qty_lvl3']  ?? -1),
        col_qty_lvl4:  String(m['qty_lvl4']  ?? -1),
        col_unit_lvl2: String(m['unit_lvl2'] ?? -1),
        col_unit_lvl3: String(m['unit_lvl3'] ?? -1),
        col_unit_lvl4: String(m['unit_lvl4'] ?? -1),
        col_amt_lvl2:  String(m['amt_lvl2']  ?? -1),
        col_amt_lvl3:  String(m['amt_lvl3']  ?? -1),
        col_amt_lvl4:  String(m['amt_lvl4']  ?? -1),
        col_feo_qty_lvl2:    String(m['feo_qty_lvl2']    ?? -1),
        col_feo_unit_lvl2:   String(m['feo_unit_lvl2']   ?? -1),
        col_feo_amount_lvl2: String(m['feo_amount_lvl2'] ?? -1),
        col_feo_qty_lvl3:    String(m['feo_qty_lvl3']    ?? -1),
        col_feo_unit_lvl3:   String(m['feo_unit_lvl3']   ?? -1),
        col_feo_amount_lvl3: String(m['feo_amount_lvl3'] ?? -1),
        col_feo_qty_lvl4:    String(m['feo_qty_lvl4']    ?? -1),
        col_feo_unit_lvl4:   String(m['feo_unit_lvl4']   ?? -1),
        col_feo_amount_lvl4: String(m['feo_amount_lvl4'] ?? -1),
        col_feo_sum_lvl2: String(m['feo_sum_lvl2'] ?? -1),
        col_feo_sum_lvl3: String(m['feo_sum_lvl3'] ?? -1),
        col_feo_sum_lvl4: String(m['feo_sum_lvl4'] ?? -1),
        col_plan_sum_lvl2: String(m['plan_sum_lvl2'] ?? -1),
        col_plan_sum_lvl3: String(m['plan_sum_lvl3'] ?? -1),
        col_plan_sum_lvl4: String(m['plan_sum_lvl4'] ?? -1),
        col_item_price:    String(m['item_price']    ?? -1),
        // Новый плоский 18-колоночный шаблон (2026-08-14)
        col_row_feo_qty:    String(m['row_feo_qty']    ?? -1),
        col_row_feo_unit:   String(m['row_feo_unit']   ?? -1),
        col_row_feo_price:  String(m['row_feo_price']  ?? -1),
        col_row_feo_sum:    String(m['row_feo_sum']    ?? -1),
        col_row_plan_qty:   String(m['row_plan_qty']   ?? -1),
        col_row_plan_unit:  String(m['row_plan_unit']  ?? -1),
        col_row_plan_price: String(m['row_plan_price'] ?? -1),
        col_row_plan_sum:   String(m['row_plan_sum']   ?? -1),
        col_item_type:      String(m['item_type']      ?? -1),
      })
      if (remapEntries.length) params.set('remap', JSON.stringify(remapEntries))
      const fd = new FormData()
      fd.append('file', feoImport.file)
      const token = localStorage.getItem('auth_token')
      const res = await fetch(`/api/feo-categories/import-mapped?${params}`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: fd,
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        const msg = err.detail || err.message || `Ошибка импорта (HTTP ${res.status})`
        showSnack(msg, 'error')
        console.error('FEO import error:', err)
        return
      }
      const data: FeoImportResult = await res.json()
      if (dryRun) {
        // Dry-run: show preview on step 3 (или остаёмся на шаге 4 при «Пересчитать»), no DB write, no snackbar, no tree reload
        feoImport.dryResult = data
        ;(data.unmatched || []).forEach(u => {
          if (u.kind === 'needs_mapping' && !(u.id in feoImport.remap)) feoImport.remap[u.id] = null
        })
        if (!keepStep) feoImport.step = 3
      } else {
        feoImport.result = data
        feoImport.step = 5
        let msg = `Импорт завершён: создано ${data.created}`
        if (data.relinked_count) msg += `, перенесено ссылок ${data.relinked_count}`
        if (data.deleted_count) msg += `, удалено узлов ${data.deleted_count}`
        showSnack(msg)
        if (ctx?.selectedId.value) { await ctx.loadFeo(ctx.selectedId.value); ctx.syncFeoFilled() }
      }
    } catch {
      showSnack('Ошибка импорта', 'error')
    } finally {
      feoImport.loading = false
    }
  }

  function closeFeoImport() {
    const wasCreated = (feoImport.result?.created ?? 0) > 0
    feoImport.show = false; feoImport.step = 1
    feoImport.file = null; feoImport.fileList = []; feoImport.result = null; feoImport.dryResult = null
    feoImport.previewData = null; feoImport.selectedSheet = ''
    feoDragMapping.value = {}; feoIgnoredCols.value = []; feoImport.remap = {}
    if (wasCreated && ctx?.selectedId.value) { ctx.loadFeo(ctx.selectedId.value); ctx.syncFeoFilled() }
  }

  return {
    feoImport, feoImportTargetSubsidy, FEO_TARGET_FIELDS,
    feoDragMapping, feoIgnoredCols, feoDragOverTarget, feoResultPanels, feoToggleResultPanel,
    feoUnmatchedNeedsMapping, feoHasSuggestions, feoRemapPlannedCount, feoAcceptAllSuggestions,
    feoStep4MainLabel, feoLoadSummary, feoCurrentSheet, feoCurrentHeaders, feoMappingValid, feoUnmappedCount,
    feoIsMapped, feoIsIgnored, feoIsTargetFilled, feoGetColumnLabel, feoGetSamples,
    feoOnDragStart, feoOnDropToTarget, feoOnDropToUnresolved, feoUnmapTarget, feoIgnoreColumn, feoAutoMap,
    feoWarnKindLabel, feoWarnSubtitle,
    doFeoImport, doFeoMappedImport, closeFeoImport,
    // allSubsidies — источник для выбора «Субсидия назначения» на шаге 2 (только чтение)
    allSubsidies: ctx?.allSubsidies,
  }
}
