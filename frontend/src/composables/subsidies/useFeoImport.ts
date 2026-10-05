// Состояние и логика мастера импорта категорий ФЭО из Excel/Word/PDF —
// вынесены из SubsidiesView.vue. Module-level singleton state, как
// useSubsidyApprovers.ts/usePlanGraphVersions.ts/usePlannedItems.ts в этом же
// проекте: родитель триггерит открытие мастера напрямую (`feoImport.show = true`
// на кнопке «Импорт» в тулбаре дерева ФЭО — тот же приём, что и раньше, когда
// feoImport была локальным reactive() в SubsidiesView.vue), а FeoImportWizard.vue
// читает/пишет то же самое состояние через useFeoImport(useSubsidyDetailCtx()).
import { computed, reactive, ref, watch } from 'vue'
import { useToast, type ToastType } from '@/composables/useToast'
import { uploadHttpErrorMessage } from '@/constants/uploadLimits'
import { fetchWithNetworkRetry } from '@/api'
import type { SubsidyDetailContext } from './useSubsidyDetail'
import type { FeoBudgetConflictGroup, FeoCategorySumConflictGroup, FeoDuplicateGroup, FeoImportResult, FeoItemTypeConflict, FeoUnmatchedNode, FeoWarning } from './types'

export function feoWarnKindLabel(kind: string): string {
  const labels: Record<string, string> = {
    level_gap: 'Пропущенный уровень поднят выше',
    level_duplicate: 'Одинаковые уровни склеены в один узел',
    sum_mismatch: 'Сумма не совпадает с кол-во × цена',
    sum_without_qty: 'Сумма задана без количества',
    parent_sum_mismatch: 'Бюджет родителя ≠ сумма дочерних',
    level_name_in_number_column: 'Название уровня стояло в числовой колонке',
    item_promoted_to_level2: 'Плановая позиция без уровней — создана направлением',
    item_type_unknown: 'Не распознано значение «товар/услуга/работа»',
    column_shift: 'Похоже, колонки сдвинуты — число попало не в ту колонку',
    group_plan_ignored: 'План строки не записан — у категории есть подкатегории',
    plan_vs_items_mismatch: 'План строки не совпадает с суммой плановых позиций',
    plan_skipped_has_items: 'План строки не записан — у категории уже есть позиции',
    subsidy_name_ignored: 'Субсидия из файла проигнорирована — импорт идёт в открытую',
    amount_without_level2: 'Сумма указана, но не заполнен Уровень 2 — строка пропущена',
    duplicate_group_merged: 'Дублирующиеся позиции объединены по вашему выбору',
    budget_overwritten_by_row: 'Сумма по ФЭО узла задана несколькими строками — учтена последняя',
    category_sum_replaced_by_items: 'Взята сумма позиций вместо собственной суммы категории — по вашему выбору',
    item_type_from_catalog: 'Товар/услуга взяты из каталога',
    item_type_conflict_unresolved: 'Товар/услуга расходятся с каталогом — решение не выбрано, взято из файла',
    item_promoted_needs_review: 'Разберите вручную: позиция ниже используется как подраздел',
    item_name_used_as_level: 'Разберите вручную: позиция лежит под чужим подразделом',
    item_promoted_to_level: 'Плановая позиция стала подразделом',
  }
  return labels[kind] ?? kind
}
export function feoWarnSubtitle(w: FeoWarning): string {
  return w.row != null ? `Стр. ${w.row} — ${w.message}` : w.message
}

// Предупреждения, требующие ручного разбора владельцем (не просто информационные) —
// единственное место, где перечислены эти два kind'а: и feoWarnKindIsAlert, и
// сортировка в feoWarnKinds читают отсюда, список не дублируется.
const FEO_WARN_ALERT_KINDS = new Set(['item_promoted_needs_review', 'item_name_used_as_level'])

export function feoWarnKindIsAlert(kind: string): boolean {
  return FEO_WARN_ALERT_KINDS.has(kind)
}

// Уникальные kind'ы предупреждений: алертные (требуют разбора) — первыми, внутри
// каждой группы порядок стабильный (порядок первого появления в массиве).
export function feoWarnKinds(warnings: FeoWarning[] | undefined | null): string[] {
  const seen: string[] = []
  for (const w of warnings || []) {
    if (!seen.includes(w.kind)) seen.push(w.kind)
  }
  const alerts = seen.filter(k => feoWarnKindIsAlert(k))
  const rest = seen.filter(k => !feoWarnKindIsAlert(k))
  return [...alerts, ...rest]
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
  // Волна 4, п.23 (владелец): решение человека ПО КАЖДОЙ ГРУППЕ дублей Ур.5
  // отдельно — ключ = FeoDuplicateGroup.key (стабилен между dry-run и боевым
  // вызовом, см. group_key в app/services/feo_import_duplicates.py), значение
  // 'keep' (по умолчанию, владелец запретил автообъединение) или 'merge'.
  // Тот же словарь (Правило №6, один канал решений на весь импорт) несёт и
  // решения по конфликтам Суммы по ФЭО (владелец, 2026-09-15, опрос) — ключи
  // FeoBudgetConflictGroup.key с префиксом `budget::`, значения
  // 'first'|'last'|'sum' — см. feoBudgetResolutionFor/feoSetBudgetResolution.
  // И (владелец, 2026-09-16) решения «сумма категории / сумма позиций» —
  // FeoCategorySumConflictGroup.key с префиксом `catsum::`, значения
  // 'own'|'items' — см. feoCatSumResolutionFor/feoSetCatSumResolution.
  // И (задача 2026-09-22) решения «тип из файла / тип из каталога» по
  // строке — ключ `itemtype::${row}` (FeoItemTypeConflict.row), значения
  // 'file'|'catalog' — см. feoItemTypeResolutionFor/feoSetItemTypeResolution.
  // В ОТЛИЧИЕ от трёх каналов выше у этого НЕТ дефолта, который сервер и так
  // применит молча: «без выбора — тип из файла, каталог не меняется» — но
  // ключ появляется здесь, только когда человек реально нажал переключатель
  // или кнопку «Все из файла/каталога» (dry-run НЕ проставляет дефолт сам,
  // см. doFeoMappedImport ниже) — пустой канал = решений нет вовсе.
  // budget:: значения — 'first'|'last'|'sum'|`row:<номер строки>` (задача
  // 2026-09-22, динамический выбор строки, см. feoBudgetResolutionFor ниже) —
  // держим string вместо перечисления, полный список допустимых значений
  // проверяет только backend (feo_import_core.py).
  duplicateResolutions: {} as Record<string, 'merge' | 'keep' | 'own' | 'items' | 'file' | 'catalog' | string>,
  // Баг владельца 23.09: смена радио-кнопки на шаге 3 меняла только
  // duplicateResolutions — текст предупреждений и счётчики создано/обновлено/
  // пропущено оставались от ПЕРВОГО dry-run (до решения человека, сервер
  // применял дефолт 'last'). recomputing/resultStale/recomputeError — см.
  // feoScheduleRecompute/feoRecomputeNow ниже, единственный канал пересчёта
  // (Правило №6, тот же doFeoMappedImport(true, true), что и «Пересчитать» на шаге 4).
  recomputing: false,
  resultStale: false,
  recomputeError: null as string | null,
})

// Небольшой дебаунс-планировщик пересчёта прогноза после решения человека —
// module-level (не реактивный), переживает пересоздание компонентов мастера,
// как и сам feoImport выше. _recomputeRunner привязывается к doFeoMappedImport
// внутри useFeoImport(ctx) (там же, где живут ctx/toast) при каждом вызове
// useFeoImport() — то же самое ctx-замыкание, каким уже пользуются
// doFeoImport/doFeoMappedImport/closeFeoImport.
let _recomputeRunner: (() => Promise<void>) | null = null
let _recomputeTimer: ReturnType<typeof setTimeout> | null = null
let _recomputeInFlight = false
let _recomputeQueued = false

function _runRecompute() {
  if (!_recomputeRunner) return
  if (_recomputeInFlight) { _recomputeQueued = true; return }
  _recomputeInFlight = true
  feoImport.recomputing = true
  _recomputeRunner().finally(() => {
    _recomputeInFlight = false
    feoImport.recomputing = false
    // Пока шёл запрос, решение поменялось ещё раз — досчитываем финальное
    // состояние одним следующим запросом, не наслаивая параллельные вызовы.
    if (_recomputeQueued) { _recomputeQueued = false; _runRecompute() }
  })
}
// Дебаунс ~800мс: серия быстрых кликов по радио-кнопкам не порождает серию
// запросов — таймер переставляется каждым новым изменением.
export function feoScheduleRecompute() {
  if (!feoImport.dryResult) return // первого предпросмотра ещё не было — нечего пересчитывать
  feoImport.resultStale = true
  feoImport.recomputeError = null
  if (_recomputeTimer) clearTimeout(_recomputeTimer)
  _recomputeTimer = setTimeout(() => { _recomputeTimer = null; _runRecompute() }, 800)
}
// Ручное «Пересчитать» (шаг 4) — тот же путь, без ожидания дебаунса.
export function feoRecomputeNow() {
  if (_recomputeTimer) { clearTimeout(_recomputeTimer); _recomputeTimer = null }
  feoImport.resultStale = true
  feoImport.recomputeError = null
  _runRecompute()
}

const feoImportTargetSubsidy = ref<number | null>(null)

// FEO column mapping — Правило №6 (один источник списка колонок): целевые
// поля этого списка = РОВНО колонки актуального шаблона A-AB
// (backend/app/routers/feo_import_template.py::headers, зафиксировано тестом
// test_feo_import_mapped_fact_and_need_level.py::EXPECTED_TEMPLATE_HEADERS),
// в том же порядке и с теми же подписями. Устаревшие поля старого
// 37-колоночного формата (qty_lvl2/3/4, unit_lvl2/3/4, amt_lvl2/3/4,
// feo_qty_lvl*/feo_unit_lvl*/feo_amount_lvl*/feo_sum_lvl*, plan_sum_lvl2/3/4,
// generic Ур.5 quantity/unit/item_amt/item_price) убраны из ручного выбора
// (владелец, 05.10.2026) — они дублируют row_feo_*/row_plan_* нового
// шаблона. Backend продолжает их ЧИТАТЬ (не трогали ни _do_feo_import, ни
// find_col в app/routers/feo_import.py) — старые файлы грузятся как раньше
// через автоопределение (/import, FeoCategoriesView.vue), просто в этом
// ручном мастере (SubsidiesView → FeoImportWizard) их больше нельзя выбрать
// руками. `group` — только для подсветки блока «Факт» в сетке
// (ImportMappingGrid.vue), на мэппинг/отправку не влияет.
const FEO_TARGET_FIELDS = [
  { value: 'subsidy',  title: 'Субсидия (название)',                          required: true },
  { value: 'lvl2',     title: 'Уровень 2 — Направление расходов по ФЭО',     required: true },
  { value: 'lvl3',          title: 'Уровень 3 — Тип расходов по ФЭО',            required: false },
  { value: 'lvl4',          title: 'Уровень 4 — Конкретизированный',              required: false },
  { value: 'lvl5',          title: 'Плановая позиция (папку не создаёт)',        required: false },
  { value: 'item_type',       title: 'Товар/услуга/работа',                     required: false },
  // Плоский шаблон (2026-08-14): одна пара колонок «по ФЭО»/«плана» на всю
  // строку — вместо колонок-на-каждый-уровень. См. col_row_* в _do_feo_import.
  { value: 'row_feo_qty',     title: 'Количество по ФЭО',                        required: false },
  { value: 'row_feo_unit',    title: 'Ед. изм. по ФЭО',                          required: false },
  { value: 'row_feo_price',   title: 'Цена за единицу по ФЭО',                   required: false },
  { value: 'row_feo_sum',     title: 'Сумма по ФЭО',                             required: false },
  { value: 'row_plan_qty',    title: 'Плановое количество',                      required: false },
  { value: 'row_plan_unit',   title: 'Ед. изм. плана',                           required: false },
  { value: 'row_plan_price',  title: 'Плановая цена за единицу',                 required: false },
  { value: 'row_plan_sum',    title: 'Сумма плана',                              required: false },
  { value: 'code',     title: 'Код',                                        required: false },
  { value: 'appendix', title: 'Приложение',                                 required: false },
  { value: 'active',   title: 'Активна',                                    required: false },
  { value: 'budget',   title: 'Финансирование (устар., можно не заполнять)', required: false },
  // Владелец, 22.09: уходит в ленту комментариев плановой позиции строки
  // (или категории строки, если позиции нет) — см. c_comment в
  // app/routers/feo_import.py, register_*_comment_intent в
  // app/services/feo_import_comments.py.
  { value: 'comment',  title: 'Комментарий',                                 required: false },
  // Владелец, 2026-10-04: насколько нужна плановая позиция (выпадающий
  // список на листе «Справочники» шаблона) — см. c_need_level в
  // app/services/feo_import_core.py, plan_need_level.py.
  { value: 'need_level', title: 'Нужность',                                  required: false },
  // --- Блок «Факт» (владелец, 05.10.2026) — НЕОБЯЗАТЕЛЬНЫЙ, заполняется
  // только для строк, по которым закупка уже прошла. На план/дерево НЕ
  // влияет (_do_feo_import эти поля не принимает вовсе) — считается только
  // для has_fact_columns/fact_rows (app/services/feo_import_fact_summary.py)
  // и передаётся мастеру «Импорт факта» при переходе с тем же файлом
  // (useFactImport.ts::openWizardWithFile).
  { value: 'fact_status',       title: 'Правильный статус',  required: false, group: 'fact' },
  { value: 'fact_qty',          title: 'Факт: Количество',   required: false, group: 'fact' },
  { value: 'fact_price',        title: 'Факт: Цена',          required: false, group: 'fact' },
  { value: 'fact_amount',       title: 'Факт: Сумма',         required: false, group: 'fact' },
  { value: 'fact_paid',         title: 'Оплачено',            required: false, group: 'fact' },
  { value: 'fact_contracted',   title: 'Законтрактовано',     required: false, group: 'fact' },
  { value: 'fact_supplier',     title: 'Поставщик',           required: false, group: 'fact' },
  { value: 'fact_purchase_no',  title: '№ закупки',           required: false, group: 'fact' },
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

// Волна 4, п.23 (владелец): группы дублей Ур.5 — читаются из ответа
// предпросмотра (dry-run), решение по каждой группе живёт в
// feoImport.duplicateResolutions отдельно от самого ответа (сервер на
// dry-run всегда возвращает resolution='keep' для новой группы — реальный
// выбор человека применяется только следующим вызовом).
const feoDuplicateGroups = computed<FeoDuplicateGroup[]>(() => feoImport.dryResult?.duplicate_groups || [])
function feoResolutionFor(key: string): 'merge' | 'keep' {
  return feoImport.duplicateResolutions[key] === 'merge' ? 'merge' : 'keep'
}
function feoSetResolution(key: string, value: 'merge' | 'keep') {
  feoImport.duplicateResolutions[key] = value
  feoScheduleRecompute()
}

// Владелец (2026-09-15, опрос): группы конфликтов Суммы по ФЭО — читаются из
// того же ответа предпросмотра (dry-run), тем же приёмом, что и feoDuplicateGroups
// выше; решение живёт в ТОМ ЖЕ feoImport.duplicateResolutions (ключи различаются
// префиксом `budget::`, Правило №6 — один канал, не два).
const feoBudgetConflictGroups = computed<FeoBudgetConflictGroup[]>(() => feoImport.dryResult?.budget_conflict_groups || [])
// Задача 2026-09-22: значение — 'sum' (кнопка «Сложить») или `row:<номер
// строки>` (выбор конкретной строки, столько пунктов, сколько строк реально
// задают сумму этой категории — динамически, options.rows). 'first'/'last'
// как отдельные ярлыки больше не показываются в UI (см. FeoImportWizard.vue) —
// принимает группу целиком (не просто key), чтобы транслировать дефолт 'last'
// (серверный дефолт, хранится в duplicateResolutions буквально как 'last' —
// _isDefaultFeoResolution ниже завязана на это буквальное значение, Правило
// №6, второй способ пометить «решение не менялось» не заводим) в конкретную
// `row:<N>` кнопку для визуального выделения; сам канал решений не трогает.
function feoBudgetResolutionFor(g: FeoBudgetConflictGroup): string {
  const v = feoImport.duplicateResolutions[g.key]
  const resolved = typeof v === 'string' ? v : 'last'
  if (resolved === 'last') return `row:${g.options.last.row}`
  if (resolved === 'first') return `row:${g.options.first.row}`
  return resolved
}
function feoSetBudgetResolution(key: string, value: string) {
  feoImport.duplicateResolutions[key] = value
  feoScheduleRecompute()
}

// Владелец (2026-09-16, дословно): категория, у которой в файле заполнены И
// собственная сумма, И собственные позиции с feo_amount — читаются из того
// же ответа предпросмотра, тем же приёмом, что и feoBudgetConflictGroups
// выше; решение живёт в ТОМ ЖЕ feoImport.duplicateResolutions (ключи с
// префиксом `catsum::`, Правило №6 — один канал, не три).
const feoCategorySumConflictGroups = computed<FeoCategorySumConflictGroup[]>(() => feoImport.dryResult?.category_sum_conflict_groups || [])
function feoCatSumResolutionFor(key: string): 'own' | 'items' {
  return feoImport.duplicateResolutions[key] === 'items' ? 'items' : 'own'
}
function feoSetCatSumResolution(key: string, value: 'own' | 'items') {
  feoImport.duplicateResolutions[key] = value
  feoScheduleRecompute()
}

// Задача 2026-09-22: строки, где товар/услуга/работа из файла отличается от
// значения уже сопоставленного товара в каталоге — читаются из
// того же ответа предпросмотра, тем же приёмом, что и группы выше; решение
// живёт в ТОМ ЖЕ feoImport.duplicateResolutions (ключи с префиксом
// `itemtype::${row}`, Правило №6 — один канал, не четыре). В отличие от
// budget::/catsum:: у этого канала НЕТ дефолтного значения — «нет решения»
// означает, что ключ отсутствует вовсе (см. комментарий у duplicateResolutions).
const feoItemTypeConflicts = computed<FeoItemTypeConflict[]>(() => feoImport.dryResult?.item_type_conflicts || [])
function feoItemTypeKey(row: number): string {
  return `itemtype::${row}`
}
function feoItemTypeResolutionFor(row: number): 'file' | 'catalog' | null {
  const v = feoImport.duplicateResolutions[feoItemTypeKey(row)]
  return v === 'file' || v === 'catalog' ? v : null
}
function feoSetItemTypeResolution(row: number, value: 'file' | 'catalog' | null | undefined) {
  const key = feoItemTypeKey(row)
  if (value === 'file' || value === 'catalog') feoImport.duplicateResolutions[key] = value
  // v-btn-toggle без mandatory отдаёт undefined при повторном клике по уже
  // активной кнопке (снятие выбора) — «решения нет» здесь означает ОТСУТСТВИЕ
  // ключа в канале (см. комментарий у duplicateResolutions), не значение.
  else delete feoImport.duplicateResolutions[key]
  feoScheduleRecompute()
}
// Кнопки «Все из файла» / «Все из каталога» — применяют один выбор ко ВСЕМ
// текущим конфликтам разом (тот же канал, точечный выбор по строке остаётся
// доступен после — просто перезаписывает значение по своему ключу).
function feoSetAllItemTypeResolutions(value: 'file' | 'catalog') {
  for (const c of feoItemTypeConflicts.value) feoSetItemTypeResolution(c.row, value)
}

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
  // Владелец, 05.10.2026: КЛЮЧИ ограничены полями актуального шаблона (см.
  // докстринг FEO_TARGET_FIELDS выше) — старые per-level/Ур.5-generic ключи
  // убраны ВМЕСТЕ с полями, которые они заполняли (поле больше не
  // существует в FEO_TARGET_FIELDS — оставлять для него ключ автоподбора
  // было бы мёртвым кодом, подбирающим невидимое поле).
  const KEYWORDS: Record<string, string[]> = {
    subsidy:  ['субсидия'],
    lvl2:     ['уровень 2', 'направление расходов', 'level 2'],
    lvl3:     ['уровень 3', 'тип расходов', 'level 3'],
    lvl4:     ['уровень 4', 'конкретизир', 'level 4'],
    lvl5:     ['плановая позиция', 'уровень 5', 'плановый товар', 'level 5'],
    // Плоский шаблон (2026-08-14): одна пара «по ФЭО»/«плана» на всю строку.
    // lvl5 объявлен строкой выше item_type — иначе «товар/услуга» в заголовке
    // lvl5 старого формата перехватил бы item_type.
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
    active:   ['активна', 'активен'],
    // Слово в слово те же ключи, что и c_comment в app/routers/feo_import.py
    // (find_col) — рассинхрон мастера и бэкенда уже ломал импорт 14.08.
    comment:  ['комментарий', 'примечание'],
    // Владелец, 2026-10-04 — слово в слово c_need_level (find_col) в
    // app/routers/feo_import.py.
    need_level: ['нужность'],
    // Владелец, 05.10.2026 — слово в слово _FACT_KEYWORDS в
    // app/services/feo_import_fact_summary.py (Правило №6: та же дублирующая
    // пара ключевых слов на фронте/бэке, какой уже пользуется comment выше).
    fact_status:      ['правильный статус'],
    fact_qty:         ['факт: количество', 'факт количество'],
    fact_price:       ['факт: цена', 'факт цена'],
    fact_amount:      ['факт: сумма', 'факт сумма'],
    fact_paid:        ['оплачено'],
    fact_contracted:  ['законтрактовано'],
    fact_supplier:    ['поставщик'],
    fact_purchase_no: ['№ закупки', 'номер закупки'],
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

  // D (баг 2026-09-09, владелец): в предпросмотре должно быть явно видно, В
  // КАКУЮ субсидию идёт импорт — backend с этой сессии ВСЕГДА пишет ровно в
  // неё (default_subsidy_id побеждает безусловно, см. resolve_target_subsidy_id
  // в app/services/feo_import_common.py), но пока это было не видно в UI,
  // владелец не мог заметить проблему до того, как она уже случилась.
  const feoImportTargetSubsidyName = computed(() => {
    const id = feoImportTargetSubsidy.value
    if (id == null) return null
    return ctx?.allSubsidies.value.find(s => s.id === id)?.name ?? null
  })

  async function doFeoImport() {
    if (!feoImport.file) return
    feoImport.loading = true
    try {
      const fd = new FormData()
      fd.append('file', feoImport.file)
      const token = localStorage.getItem('auth_token')
      // Чтение файла ничего не пишет в БД (см. докстринг эндпоинта) — можно
      // один раз тихо повторить при обрыве сети (Правило №6: тот же хелпер
      // и то же сообщение «Нет связи с сервером», что у apiFetch, см. api.ts).
      const res = await fetchWithNetworkRetry(() => fetch('/api/feo-categories/import-preview', {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: fd,
      }), { retryable: true, suppressErrorDialog: true })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        showSnack(uploadHttpErrorMessage(res.status) || err.detail || 'Ошибка чтения файла', 'error'); return
      }
      const data = await res.json()
      feoImport.previewData = data
      feoImport.selectedSheet = data.sheets[0]?.name || ''
      feoIgnoredCols.value = []
      feoAutoMap(data.sheets[0]?.headers || [])
      feoImportTargetSubsidy.value = ctx?.selectedId.value ?? null
      feoImport.step = 2
    } catch (e: any) {
      // fetchWithNetworkRetry уже перевела сетевую ошибку в человекочитаемый
      // payload.message («Нет связи с сервером — повторите действие») —
      // читаем его, а не голый e.message (см. владелец, 29.09).
      showSnack(e?.payload?.message || 'Ошибка чтения файла', 'error')
    } finally {
      feoImport.loading = false
    }
  }

  // Владелец (2026-09-15/16, опрос): дефолт «ничего не выбрано» для КАЖДОГО
  // канала duplicateResolutions — ровно то же значение, что бэкенд применяет
  // при ОТСУТСТВИИ ключа (finalize_lvl5_items/apply_budget_conflict_
  // resolutions/apply_category_sum_conflicts в feo_import_duplicates.py и
  // feo_import_budget_conflicts.py, Правило №6 — сверено с бэкендом, не
  // задублировано вслепую). Строка, где человек ничего не менял, не должна
  // раздувать duplicate_resolutions — это и есть источник HTTP 414 на
  // больших субсидиях (десятки catsum-групп по числу категорий).
  function _isDefaultFeoResolution(key: string, value: string): boolean {
    if (key.startsWith('budget::')) return value === 'last'
    if (key.startsWith('catsum::')) return value === 'own'
    // itemtype:: уходит СВОИМ полем item_type_decisions (см. блок ниже в
    // doFeoMappedImport), не через duplicate_resolutions — бэкенд не знает
    // такого kind группы и отвечает 400. Эта функция фильтрует только
    // duplicate_resolutions, поэтому для itemtype:: всегда «считать
    // дефолтом» = исключить отсюда (не значит «решения нет»).
    if (key.startsWith('itemtype::')) return true
    return value === 'keep'
  }

  // opts.silent — вызов из автоматического пересчёта после смены решения
  // человека (feoScheduleRecompute/feoRecomputeNow): не трогает feoImport.loading
  // (иначе Отмена/Назад и т.п. мигали бы спиннером на КАЖДЫЙ клик по радио),
  // ошибки идут в feoImport.recomputeError (инлайн в мастере, п.6 задачи),
  // а не в общий toast, и прежний feoImport.dryResult не перетирается.
  async function doFeoMappedImport(dryRun = false, keepStep = false, opts?: { silent?: boolean }) {
    if (!feoImport.file) return
    const silent = !!opts?.silent
    if (!silent) feoImport.loading = true
    try {
      const m = feoDragMapping.value
      const sheet = feoCurrentSheet.value
      // remap задаётся путём, а не id: у целевого узла в момент показа таблицы ещё нет id — он появится только при записи
      const remapEntries = Object.entries(feoImport.remap)
        .filter(([, newPath]) => !!newPath)
        .map(([oldId, newPath]) => ({ old_id: Number(oldId), new_path: newPath as string }))

      // Баг владельца 2026-09-17 (HTTP 414 на субсидии "Центрпоиск_3"): все
      // параметры ниже раньше шли в query-строку GET-подобным способом при
      // POST'е — ~70 col_* плюс remap плюс duplicate_resolutions (кириллица,
      // по группе на каждую категорию) уходили на десятки КБ, выше лимита
      // nginx (large_client_header_buffers). Файл и так шёл в теле FormData —
      // теперь ВСЁ идёт туда же, в URL не остаётся ничего, что растёт от
      // данных файла (backend принимает то же самое и из формы, и из query
      // для обратной совместимости — см. app/services/feo_import_params.py).
      const fd = new FormData()
      fd.append('file', feoImport.file)
      fd.append('sheet_name', feoImport.selectedSheet)
      fd.append('header_row_offset', String(sheet?.header_row_offset ?? 0))
      fd.append('dry_run', dryRun ? 'true' : 'false')
      fd.append('apply_remap', 'true')
      fd.append('col_subsidy',  String(m['subsidy']  ?? -1))
      fd.append('default_subsidy_id', String(feoImportTargetSubsidy.value ?? -1))
      fd.append('col_lvl2',     String(m['lvl2']     ?? -1))
      fd.append('col_lvl3',     String(m['lvl3']     ?? -1))
      fd.append('col_lvl4',     String(m['lvl4']     ?? -1))
      fd.append('col_lvl5',     String(m['lvl5']     ?? -1))
      fd.append('col_code',     String(m['code']     ?? -1))
      fd.append('col_appendix', String(m['appendix'] ?? -1))
      fd.append('col_budget',   String(m['budget']   ?? -1))
      fd.append('col_active',    String(m['active']    ?? -1))
      // Устаревшие поля старого 37-колоночного формата (qty_lvl2/3/4,
      // unit_lvl2/3/4, amt_lvl2/3/4, feo_qty_lvl*/feo_unit_lvl*/
      // feo_amount_lvl*/feo_sum_lvl*, plan_sum_lvl2/3/4, generic Ур.5
      // quantity/unit/item_amt/item_price) убраны из FEO_TARGET_FIELDS
      // (владелец, 05.10.2026, см. докстринг там) — m[...] для них уже не
      // определён, backend принимает их параметры дефолтом -1 (Query(-1)),
      // второй раз явно слать не нужно.
      // Новый плоский шаблон (2026-08-14)
      fd.append('col_row_feo_qty',    String(m['row_feo_qty']    ?? -1))
      fd.append('col_row_feo_unit',   String(m['row_feo_unit']   ?? -1))
      fd.append('col_row_feo_price',  String(m['row_feo_price']  ?? -1))
      fd.append('col_row_feo_sum',    String(m['row_feo_sum']    ?? -1))
      fd.append('col_row_plan_qty',   String(m['row_plan_qty']   ?? -1))
      fd.append('col_row_plan_unit',  String(m['row_plan_unit']  ?? -1))
      fd.append('col_row_plan_price', String(m['row_plan_price'] ?? -1))
      fd.append('col_row_plan_sum',   String(m['row_plan_sum']   ?? -1))
      fd.append('col_item_type',      String(m['item_type']      ?? -1))
      fd.append('col_comment',        String(m['comment']        ?? -1))
      // Владелец, 2026-10-04: «Нужность».
      fd.append('col_need_level',     String(m['need_level']     ?? -1))
      // Владелец, 05.10.2026: блок «Факт» — на план/дерево не влияет, см.
      // докстринг FEO_TARGET_FIELDS. col_fact_status передаётся и в
      // «Импорт факта» при переходе (goToFactImport в FeoImportWizard.vue).
      fd.append('col_fact_status',      String(m['fact_status']      ?? -1))
      fd.append('col_fact_qty',         String(m['fact_qty']         ?? -1))
      fd.append('col_fact_price',       String(m['fact_price']       ?? -1))
      fd.append('col_fact_amount',      String(m['fact_amount']      ?? -1))
      fd.append('col_fact_paid',        String(m['fact_paid']        ?? -1))
      fd.append('col_fact_contracted',  String(m['fact_contracted']  ?? -1))
      fd.append('col_fact_supplier',    String(m['fact_supplier']    ?? -1))
      fd.append('col_fact_purchase_no', String(m['fact_purchase_no'] ?? -1))
      if (remapEntries.length) fd.append('remap', JSON.stringify(remapEntries))
      // Волна 4, п.23 + не слать то, что ничего не меняет (см.
      // _isDefaultFeoResolution выше): решения человека по группам дублей
      // Ур.5/конфликтов Суммы по ФЭО/суммы категории — только те, что
      // РЕАЛЬНО отличаются от дефолта, который backend и так применит при
      // отсутствии ключа. Раньше сюда клался дефолт для КАЖДОЙ группы, даже
      // нетронутой человеком — на субсидии с сотнями catsum-групп это и
      // раздувало запрос до HTTP 414.
      const _resolutionsToSend: Record<string, string> = {}
      for (const [key, value] of Object.entries(feoImport.duplicateResolutions)) {
        if (!_isDefaultFeoResolution(key, value)) _resolutionsToSend[key] = value
      }
      if (Object.keys(_resolutionsToSend).length) {
        fd.append('duplicate_resolutions', JSON.stringify(_resolutionsToSend))
      }
      // Задача 2026-09-22: решения «тип из файла / тип из каталога» живут в
      // ТОМ ЖЕ duplicateResolutions (ключи `itemtype::${row}`), но контракт
      // бэкенда — ОТДЕЛЬНОЕ поле формы item_type_decisions, JSON-объект
      // {"<row>": "file"|"catalog"} (тот же способ передачи — поле формы с
      // JSON-строкой, — каким уже уходит duplicate_resolutions выше; второй
      // транспорт не заводим, второе ИМЯ поля задано контрактом бэкенда).
      // Отсутствие ключа = «решения нет» — ничего не отправляем, если пусто.
      const _itemTypeDecisions: Record<string, 'file' | 'catalog'> = {}
      for (const [key, value] of Object.entries(feoImport.duplicateResolutions)) {
        if (key.startsWith('itemtype::') && (value === 'file' || value === 'catalog')) {
          _itemTypeDecisions[key.slice('itemtype::'.length)] = value
        }
      }
      if (Object.keys(_itemTypeDecisions).length) {
        fd.append('item_type_decisions', JSON.stringify(_itemTypeDecisions))
      }
      const token = localStorage.getItem('auth_token')
      // dryRun (предпросмотр/«Пересчитать») ничего не пишет в БД — безопасен
      // для одного тихого повтора при обрыве сети; настоящий импорт (dryRun
      // false) — без повтора, чтобы не задвоить запись (Правило №6, тот же
      // хелпер/сообщение, что у apiFetch, см. api.ts).
      const res = await fetchWithNetworkRetry(() => fetch('/api/feo-categories/import-mapped', {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: fd,
      }), { retryable: dryRun, suppressErrorDialog: true })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        const msg = uploadHttpErrorMessage(res.status) || err.detail || err.message || `Ошибка импорта (HTTP ${res.status})`
        if (silent) {
          // п.6: не глотать generic-снэкбаром — причина видна инлайн в
          // мастере (FeoImportWizard.vue), прежний dryResult НЕ трогаем —
          // resultStale уже true (выставлено в feoScheduleRecompute/feoRecomputeNow).
          feoImport.recomputeError = msg
        } else {
          showSnack(msg, 'error')
        }
        console.error('FEO import error:', err)
        return
      }
      const data: FeoImportResult = await res.json()
      if (dryRun) {
        // Dry-run: show preview on step 3 (или остаёмся на шаге 4 при «Пересчитать»), no DB write, no snackbar, no tree reload
        feoImport.dryResult = data
        feoImport.resultStale = false
        feoImport.recomputeError = null
        ;(data.unmatched || []).forEach(u => {
          if (u.kind === 'needs_mapping' && !(u.id in feoImport.remap)) feoImport.remap[u.id] = null
        })
        // Волна 4, п.23: новая группа дублей получает дефолт «оставить как
        // есть» — если человек уже выбирал по этому же ключу раньше
        // («Пересчитать» на шаге 4 не должен сбрасывать сделанный выбор),
        // существующее значение не трогаем.
        ;(data.duplicate_groups || []).forEach(g => {
          if (!(g.key in feoImport.duplicateResolutions)) feoImport.duplicateResolutions[g.key] = 'keep'
        })
        // Владелец (2026-09-15): новая группа конфликта Суммы по ФЭО получает
        // дефолт 'last' (прежнее поведение «последняя побеждает») — «Пересчитать»
        // на шаге 4 не должен сбрасывать уже сделанный человеком выбор.
        ;(data.budget_conflict_groups || []).forEach(g => {
          if (!(g.key in feoImport.duplicateResolutions)) feoImport.duplicateResolutions[g.key] = 'last'
        })
        // Владелец (2026-09-16): новая группа «сумма категории / сумма
        // позиций» получает дефолт 'own' (прежнее поведение — явная сумма
        // узла главнее) — «Пересчитать» на шаге 4 не сбрасывает уже
        // сделанный человеком выбор.
        ;(data.category_sum_conflict_groups || []).forEach(g => {
          if (!(g.key in feoImport.duplicateResolutions)) feoImport.duplicateResolutions[g.key] = 'own'
        })
        if (!keepStep) feoImport.step = 3
      } else {
        feoImport.result = data
        feoImport.step = 5
        let msg = `Импорт завершён: создано ${data.created}`
        if (data.relinked_count) msg += `, перенесено ссылок ${data.relinked_count}`
        if (data.deleted_count) msg += `, удалено узлов ${data.deleted_count}`
        if (data.comments_created) msg += `, комментариев ${data.comments_created}`
        showSnack(msg)
        if (ctx?.selectedId.value) { await ctx.loadFeo(ctx.selectedId.value); ctx.syncFeoFilled() }
      }
    } catch (e: any) {
      // fetchWithNetworkRetry переводит сетевую ошибку в e.payload.message
      // («Нет связи с сервером — повторите действие») — читаем его в
      // приоритете, иначе голый e.message показывал буквальный текст
      // браузера «Failed to fetch» (владелец, 29.09).
      const reason = e?.payload?.message || e?.message
      const msg = reason ? `Ошибка импорта: ${reason}` : 'Ошибка импорта'
      if (silent) feoImport.recomputeError = msg
      else showSnack(msg, 'error')
    } finally {
      if (!silent) feoImport.loading = false
    }
  }
  // Привязка пересчёта (feoScheduleRecompute/feoRecomputeNow, module-level
  // выше) к doFeoMappedImport этого ctx-замыкания — тот же приём переиспользования,
  // что и весь остальной канал решений (Правило №6, второй путь не заводим).
  _recomputeRunner = () => doFeoMappedImport(true, true, { silent: true })

  function closeFeoImport() {
    const wasCreated = (feoImport.result?.created ?? 0) > 0
    feoImport.show = false; feoImport.step = 1
    feoImport.file = null; feoImport.fileList = []; feoImport.result = null; feoImport.dryResult = null
    feoImport.previewData = null; feoImport.selectedSheet = ''
    feoDragMapping.value = {}; feoIgnoredCols.value = []; feoImport.remap = {}
    feoImport.duplicateResolutions = {}
    feoImport.recomputing = false; feoImport.resultStale = false; feoImport.recomputeError = null
    if (_recomputeTimer) { clearTimeout(_recomputeTimer); _recomputeTimer = null }
    _recomputeQueued = false
    if (wasCreated && ctx?.selectedId.value) { ctx.loadFeo(ctx.selectedId.value); ctx.syncFeoFilled() }
  }

  return {
    feoImport, feoImportTargetSubsidy, feoImportTargetSubsidyName, FEO_TARGET_FIELDS,
    feoDragMapping, feoIgnoredCols, feoDragOverTarget, feoResultPanels, feoToggleResultPanel,
    feoDuplicateGroups, feoResolutionFor, feoSetResolution,
    feoBudgetConflictGroups, feoBudgetResolutionFor, feoSetBudgetResolution,
    feoCategorySumConflictGroups, feoCatSumResolutionFor, feoSetCatSumResolution,
    feoItemTypeConflicts, feoItemTypeResolutionFor, feoSetItemTypeResolution, feoSetAllItemTypeResolutions,
    feoUnmatchedNeedsMapping, feoHasSuggestions, feoRemapPlannedCount, feoAcceptAllSuggestions,
    feoStep4MainLabel, feoLoadSummary, feoPluralRu, feoCurrentSheet, feoCurrentHeaders, feoMappingValid, feoUnmappedCount,
    feoIsMapped, feoIsIgnored, feoIsTargetFilled, feoGetColumnLabel, feoGetSamples,
    feoOnDragStart, feoOnDropToTarget, feoOnDropToUnresolved, feoUnmapTarget, feoIgnoreColumn, feoAutoMap,
    feoWarnKindLabel, feoWarnSubtitle, feoWarnKindIsAlert, feoWarnKinds,
    doFeoImport, doFeoMappedImport, closeFeoImport, feoRecomputeNow,
    // allSubsidies — источник для выбора «Субсидия назначения» на шаге 2 (только чтение)
    allSubsidies: ctx?.allSubsidies,
  }
}
