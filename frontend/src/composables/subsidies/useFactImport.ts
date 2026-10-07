// useFactImport — состояние и API-вызовы мастера «Импорт факта» (план
// breezy-mixing-lovelace.md, Часть 2). Бэкенд пишется параллельно другим
// агентом строго по контракту из задания (/api/subsidies/{sid}/fact-import/*);
// этот файл — ТОЛЬКО типы и обвязка вокруг него, без собственной бизнес-логики
// сумм (ПРАВИЛО №6 — «план»/«договор»/«оплачено» считает бэкенд, фронт их
// просто показывает).
//
// Module-level singleton state — тот же приём, что у useFeoImport.ts/
// usePlanToRequest.ts: кнопка в FeoTreeToolbar.vue ставит factImport.show =
// true, FactImportWizard.vue (реальный потомок) читает/пишет то же состояние
// через useFactImport().
import { computed, reactive } from 'vue'
import { apiFetch } from '@/api'
import { useToast, type ToastType } from '@/composables/useToast'
import type { ImportMappingTargetField } from '@/components/common/ImportMappingGrid.vue'

// ---- Контракт API (словами владельца, см. задание) -----------------------

export type FactImportMappingField =
  | 'path_l2' | 'path_l3' | 'path_l4' | 'plan_item_name' | 'item_type' | 'unit'
  | 'plan_qty' | 'plan_price' | 'plan_amount'
  | 'fact_qty' | 'fact_price' | 'fact_amount'
  | 'paid' | 'contracted' | 'status' | 'status_raw'
  | 'purchase_no' | 'supplier' | 'comment'

export interface FactImportSheet {
  name: string
  rows: number
  header_row_guess: number
}

export interface FactImportColumn {
  index: number
  letter: string
  header: string
  field: FactImportMappingField | null
}

export interface FactImportMoney {
  qty: number | null
  price: number | null
  amount: number | null
}

export interface FactImportMatchCandidate {
  id: number
  name: string
  path: string
  amount: number | null
}

export type FactImportMatchState = 'found' | 'ambiguous' | 'not_found' | 'already_purchased'

export interface FactImportMatch {
  state: FactImportMatchState
  planned_item_id: number | null
  candidates: FactImportMatchCandidate[]
  // Чек-лист 07.10.2026, п.3: для found/already_purchased — с какой плановой
  // позицией сопоставлено (после override — уже новой), показывается в
  // колонке «Сопоставление» вместо голого значка «найдено».
  planned_item_name?: string | null
  planned_item_path?: string | null
  planned_item_amount?: number | null
}

// 🟢 Задача B («Оплачено, но уже в закупке», 07.10.2026) — строка файла,
// чья плановая позиция уже лежит в этой СУЩЕСТВУЮЩЕЙ закупке; закупка
// обновится по файлу, новая закупка на эту строку не создаётся.
export interface FactImportRowExistingPurchase {
  id: number
  registry_number: string | null
  status: string
}

export interface FactImportRow {
  row: number
  name: string
  path: string[]
  status: string
  status_raw: string
  plan: FactImportMoney
  fact: FactImportMoney
  paid: number | null
  contracted: number | null
  supplier: string | null
  purchase_no: string | null
  match: FactImportMatch
  existing_purchase: FactImportRowExistingPurchase | null
  needs_contract_decision: boolean
  // 🔵 правка 3 (план breezy-mixing-lovelace.md): статус строки не распознан
  // как один из 6 статусов GALA — строка ждёт выбора человеком (см.
  // preview.statuses и FactImportStepRows.vue). Распознанный-но-приведённый
  // статус НЕ ставит этот флаг — для него сервер кладёт пояснение «статус
  // приведён: …» в warnings (см. statusNormalizedHint в StepRows).
  needs_status: boolean
  is_payroll: boolean
  skip: boolean
  warnings: string[]
}

/** Один из 6 статусов GALA (словами владельца) — приходит с бэкенда, фронт
 *  не хардкодит свой список (ПРАВИЛО №6 — один источник). */
export interface FactImportStatusOption {
  code: string
  label: string
}

// 🟢🔵 «Похожие закупки в импорте факта» (план breezy-mixing-lovelace.md,
// Часть А) — существующая закупка того же поставщика/суммы, предложенная
// вместо создания новой. kind: 'same_amount' — поставщик И сумма совпали
// («скорее всего та же», предвыбрано бэкендом — needs_existing_decision=
// false); 'same_supplier' — только поставщик, сумма другая («возможно»,
// решение обязательно).
export type FactImportExistingMatchKind = 'same_amount' | 'same_supplier'

export interface FactImportExistingMatchSuggested {
  planned_item_id: number | null
  reason: 'file_row' | 'same_name'
}

export interface FactImportExistingMatchCategoryChange {
  from: string | null
  to: string | null
}

export interface FactImportExistingMatchItem {
  item_id: number
  name: string
  qty: number | null
  price: number | null
  total: number | null
  feo_planned_item_id: number | null
  planned_item_name: string | null
  feo_category_path: string | null
  suggested: FactImportExistingMatchSuggested | null
  category_change: FactImportExistingMatchCategoryChange | null
  warnings?: string[]
}

export interface FactImportExistingMatch {
  purchase_id: number
  registry_number: string | null
  subject: string | null
  name: string | null
  contractor_name: string | null
  status: string
  kind: FactImportExistingMatchKind
  items: FactImportExistingMatchItem[]
}

export interface FactImportGroup {
  key: string
  supplier: string | null
  purchase_no: string | null
  category_path: string
  status: string
  rows: number[]
  contract_amount: number
  paid_amount: number
  warnings: string[]
  existing_matches: FactImportExistingMatch[]
  needs_existing_decision: boolean
}

export interface FactImportTotals {
  rows: number
  purchases: number
  contract_amount: number
  paid_amount: number
  skipped: number
  existing_updates: number
}

// 🟢 Задача B — одна СУЩЕСТВУЮЩАЯ закупка, которую этот прогон обновит по
// статусу/оплате из файла (не создаёт новую). status_from/status_to — коды
// из того же 6-статусного словаря (statusLabel ниже их переводит).
export interface FactImportExistingUpdate {
  purchase_id: number
  registry_number: string | null
  status_from: string
  status_to: string
  paid_add: number
  rows: number[]
}

export interface FactImportPreview {
  format: 'columns' | 'sections'
  sheet: string
  header_row: number
  columns: FactImportColumn[]
  rows: FactImportRow[]
  groups: FactImportGroup[]
  existing_updates: FactImportExistingUpdate[]
  totals: FactImportTotals
  warnings: string[]
  statuses: FactImportStatusOption[]
}

export type FactImportOverPlanChoice = 'keep_over' | 'trim' | 'skip'

export interface FactImportRowOverride {
  skip?: boolean
  planned_item_id?: number | null
  create_planned_item?: boolean
  status?: string
}

export interface FactImportExistingMatchItemLink {
  planned_item_id?: number | null
  create_planned?: boolean
  skip?: boolean
}

export interface FactImportExistingMatchDecision {
  purchase_id: number
  action: 'same' | 'new'
  // item_links отсутствует/пуст — к НЕпривязанным позициям применяется
  // предложение по умолчанию (item.suggested), см. докстринг
  // existing_link.apply_existing_match_decision на бэкенде.
  item_links?: Record<string, FactImportExistingMatchItemLink>
}

export interface FactImportDecisions {
  include_payroll: boolean
  row_overrides: Record<string, FactImportRowOverride>
  contract_confirmed_rows: number[]
  over_plan: Record<string, FactImportOverPlanChoice>
  // Переразбивка закупок вручную (Шаг 4 «Закупки») — массив групп целиком,
  // отправляется ТОЛЬКО когда человек реально тронул группировку (см.
  // groupsDirty ниже); отсутствие ключа = сервер оставляет автогруппировку.
  groups?: { rows: number[] }[]
  supplier_overrides: Record<string, number | null>
  // 🟢🔵 «Похожие закупки» (Часть А) — решение по группе, ключ — group.key.
  existing_match: Record<string, FactImportExistingMatchDecision>
}

export interface FactImportCommitResult {
  run_id: number
  purchases_created: number
  payments_created: number
  contractors_created: number
  existing_matches_linked: number
  report_url: string | null
}

export interface FactImportRunListItem {
  id: number
  filename: string
  sheet: string
  user_name: string
  created_at: string
  status: 'committed' | 'rolled_back'
  purchases_created: number
  payments_created: number
}

export interface FactImportReportRow {
  purchase_id: number
  registry_number: string | null
  supplier?: string | null
  status?: string
  contract_amount?: number
  paid_amount?: number
  missing: string[]
  // 🟢🔵 «оставлена существующая РЕЕ-…» (Часть А) — закупка НЕ создавалась,
  // её позиции привязаны к плану из файла (см. commit.py).
  existing_match?: boolean
  items_linked?: number
  planned_items_created?: number
}

export interface FactImportRunDetail {
  run: FactImportRunListItem
  report: FactImportReportRow[]
}

export interface FactImportRollbackCheck {
  can_rollback: boolean
  blockers: string[]
  will_delete: { purchases: number; payments: number; contractors: number; contracts: number; planned_items: number }
}

// ---- Поля маппинга (ImportMappingGrid) ------------------------------------

export const FACT_IMPORT_TARGET_FIELDS: ImportMappingTargetField[] = [
  { key: 'path_l2', label: 'Направление (Ур.2)' },
  { key: 'path_l3', label: 'Подраздел (Ур.3)' },
  { key: 'path_l4', label: 'Категория (Ур.4)' },
  { key: 'plan_item_name', label: 'Наименование плановой позиции', required: true },
  { key: 'item_type', label: 'Товар/услуга/работа' },
  { key: 'unit', label: 'Единица' },
  { key: 'plan_qty', label: 'План: количество' },
  { key: 'plan_price', label: 'План: цена' },
  { key: 'plan_amount', label: 'План: сумма' },
  { key: 'fact_qty', label: 'Факт: количество' },
  { key: 'fact_price', label: 'Факт: цена' },
  { key: 'fact_amount', label: 'Факт: сумма', hint: 'Это сумма договора' },
  { key: 'paid', label: 'Оплачено' },
  { key: 'contracted', label: 'Законтрактовано' },
  { key: 'status', label: 'Правильный статус' },
  { key: 'status_raw', label: 'Статус (как в файле)' },
  { key: 'purchase_no', label: '№ Закупки' },
  { key: 'supplier', label: 'Поставщик' },
  { key: 'comment', label: 'Комментарий' },
]

// ---- Состояние мастера -----------------------------------------------------

export interface FactImportState {
  show: boolean
  runsPanelShow: boolean
  step: number // 1..6
  loading: boolean
  // 🔵 правка 3: отдельный индикатор ТОЛЬКО для повторного предпросмотра
  // после клика по решению строки/группы (debounce ниже) — не включает
  // общий factImport.loading (тот гасит кнопки «Далее»/«Назад» целиком),
  // таблица шага 3/4 просто перекрывается полупрозрачным оверлеем.
  previewRefreshing: boolean
  subsidyId: number | null
  file: File | null
  sheets: FactImportSheet[]
  selectedSheet: string | null
  mapping: Record<string, number | null>
  preview: FactImportPreview | null
  decisions: FactImportDecisions
  groupsDirty: boolean
  commitResult: FactImportCommitResult | null
  runDetail: FactImportRunDetail | null
  runs: FactImportRunListItem[]
  runsLoading: boolean
}

function emptyDecisions(): FactImportDecisions {
  return {
    include_payroll: false,
    row_overrides: {},
    contract_confirmed_rows: [],
    over_plan: {},
    supplier_overrides: {},
    existing_match: {},
  }
}

const factImport = reactive<FactImportState>({
  show: false,
  runsPanelShow: false,
  step: 1,
  loading: false,
  previewRefreshing: false,
  subsidyId: null,
  file: null,
  sheets: [],
  selectedSheet: null,
  mapping: {},
  preview: null,
  decisions: emptyDecisions(),
  groupsDirty: false,
  commitResult: null,
  runDetail: null,
  runs: [],
  runsLoading: false,
})

export function useFactImport() {
  const toast = useToast()
  function showSnack(text: string, color: ToastType = 'success') {
    // Правило: ошибки/результаты действия НЕ исчезают сами (duration не задаём).
    toast.addToast(text, color)
  }

  function resetWizard(subsidyId: number | null) {
    factImport.step = 1
    factImport.loading = false
    factImport.subsidyId = subsidyId
    factImport.file = null
    factImport.sheets = []
    factImport.selectedSheet = null
    factImport.mapping = {}
    factImport.preview = null
    factImport.decisions = emptyDecisions()
    factImport.groupsDirty = false
    factImport.commitResult = null
    factImport.runDetail = null
  }

  function openWizard(subsidyId: number) {
    resetWizard(subsidyId)
    factImport.show = true
  }

  // Решение владельца 05.10.2026: после успешной загрузки шаблона ФЭО
  // (блок «Факт» заполнен хоть в одной строке — has_fact_columns/fact_rows,
  // см. FeoImportResult) мастер ФЭО предлагает перейти сюда С ТЕМ ЖЕ файлом
  // и листом — не заставлять выбирать файл повторно (шаг 1 целиком
  // пропускается, минуя `loadSheets`). ПРАВИЛО №6: сам предпросмотр — тот же
  // `loadPreview()`, которым обычный путь (loadSheets → шаг 2) и так
  // пользуется, второй парсер не заводим.
  // mapping (владелец, 05.10.2026) — сопоставление колонок, которое человек
  // уже сделал на шаге мастера ФЭО (useFeoImport.ts::feoDragMapping,
  // переведённое в ключи FACT_IMPORT_TARGET_FIELDS в FeoImportWizard.vue::
  // goToFactImport) — передаём сюда, чтобы loadPreview() ниже отправило его
  // backend'у ГОТОВЫМ (hasMapping=true), не заставляя автоопределение
  // угадывать колонки по заголовку второй раз (Правило №6).
  async function openWizardWithFile(
    subsidyId: number, file: File, sheet: string,
    mapping?: Record<string, number | null>,
  ) {
    resetWizard(subsidyId)
    factImport.file = file
    factImport.selectedSheet = sheet
    factImport.sheets = [{ name: sheet, rows: 0, header_row_guess: 1 }]
    if (mapping && Object.keys(mapping).length) factImport.mapping = mapping
    factImport.show = true
    await loadPreview()
    factImport.step = 2
  }

  function basePath(): string {
    return `/subsidies/${factImport.subsidyId}/fact-import`
  }

  function buildFormData(extra?: { mapping?: boolean; decisions?: boolean }): FormData {
    const fd = new FormData()
    if (factImport.file) fd.append('file', factImport.file)
    if (factImport.selectedSheet) fd.append('sheet', factImport.selectedSheet)
    if (extra?.mapping) fd.append('mapping', JSON.stringify(factImport.mapping))
    if (extra?.decisions) {
      const d: FactImportDecisions = { ...factImport.decisions }
      if (!factImport.groupsDirty) delete d.groups
      else if (factImport.preview) {
        d.groups = factImport.preview.groups.map(g => ({ rows: g.rows }))
      }
      fd.append('decisions', JSON.stringify(d))
    }
    return fd
  }

  // Шаг 1 → список листов. Ничего не пишет в БД — безопасно повторять, но
  // отдельного флага retryOnNetworkError не ставим (apiFetch ретраит GET/POST
  // по умолчанию только для GET; здесь явный POST с файлом — повтор при
  // неопределённом исходе первой попытки нежелателен, см. докстринг apiFetch).
  async function loadSheets() {
    if (!factImport.file || !factImport.subsidyId) return
    factImport.loading = true
    try {
      const fd = new FormData()
      fd.append('file', factImport.file)
      const data = await apiFetch<{ sheets: FactImportSheet[] }>(`${basePath()}/sheets`, {
        method: 'POST', body: fd, suppressErrorDialog: true,
      })
      factImport.sheets = data.sheets || []
      factImport.selectedSheet = factImport.sheets[0]?.name ?? null
      if (factImport.selectedSheet) await loadPreview()
    } catch (e: any) {
      showSnack(e?.payload?.message || `Ошибка чтения файла (${e?.status ?? '?'})`, 'error')
    } finally {
      factImport.loading = false
    }
  }

  // Предпросмотр — вызывается заново при смене листа/маппинга/решений по
  // строкам (Шаги 2-4), сервер каждый раз пересчитывает rows/groups/totals.
  // opts.quiet (🔵 правка 3) — вызов из debounced-реакции на клик по решению
  // строки/группы: крутит ТОЛЬКО previewRefreshing (лёгкий оверлей таблицы),
  // не factImport.loading (тот блокирует кнопки «Далее»/«Назад» мастера
  // целиком — на серии быстрых кликов это дёргало бы их без нужды).
  async function loadPreview(opts?: { quiet?: boolean }) {
    if (!factImport.file || !factImport.subsidyId) return
    const quiet = !!opts?.quiet
    if (quiet) factImport.previewRefreshing = true
    else factImport.loading = true
    try {
      const hasMapping = Object.keys(factImport.mapping).length > 0
      const fd = buildFormData({ mapping: hasMapping, decisions: true })
      const data = await apiFetch<FactImportPreview>(`${basePath()}/preview`, {
        method: 'POST', body: fd, suppressErrorDialog: true,
      })
      factImport.preview = data
      if (!hasMapping) {
        const m: Record<string, number | null> = {}
        for (const col of data.columns) {
          if (col.field) m[col.field] = col.index
        }
        factImport.mapping = m
      }
    } catch (e: any) {
      showSnack(e?.payload?.message || `Ошибка предпросмотра (${e?.status ?? '?'})`, 'error')
    } finally {
      if (quiet) factImport.previewRefreshing = false
      else factImport.loading = false
    }
  }

  // Debounce ~500мс (🔵 правка 3, владелец: «серия галочек не должна слать
  // файл на каждый клик») — ЕДИНСТВЕННОЕ место, которое планирует повторный
  // предпросмотр после решения по строке/группе; таймер module-level (не
  // per-component ref), чтобы клики из разных шагов/компонентов схлопывались
  // в один и тот же отложенный вызов, а не плодили параллельные запросы.
  let previewDebounceTimer: ReturnType<typeof setTimeout> | null = null
  function queuePreviewRefresh(delayMs = 500) {
    if (previewDebounceTimer) clearTimeout(previewDebounceTimer)
    previewDebounceTimer = setTimeout(() => {
      previewDebounceTimer = null
      void loadPreview({ quiet: true })
    }, delayMs)
  }

  // Шаблон импорта факта (🔵 правка 3, Шаг 1) — та же схема blob-скачивания,
  // что и downloadFeoTemplate (SubsidiesView.vue) / остальные export-хелперы
  // проекта (apiFetch не отдаёт Blob, поэтому здесь сырой fetch + auth-заголовок,
  // ПРАВИЛО №6 — переиспользован приём, не апи-обёртка).
  async function downloadTemplate() {
    if (!factImport.subsidyId) return
    try {
      const token = localStorage.getItem('auth_token')
      const res = await fetch(`/api${basePath()}/template`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        showSnack(err?.detail || err?.message || `Ошибка загрузки шаблона (${res.status})`, 'error')
        return
      }
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'Шаблон_импорта_факта.xlsx'
      a.click()
      URL.revokeObjectURL(url)
    } catch (e: any) {
      showSnack(e?.payload?.message || e?.message || 'Ошибка загрузки шаблона', 'error')
    }
  }

  async function commitImport() {
    if (!factImport.file || !factImport.subsidyId) return
    factImport.loading = true
    try {
      const fd = buildFormData({ mapping: true, decisions: true })
      const data = await apiFetch<FactImportCommitResult>(`${basePath()}/commit`, {
        method: 'POST', body: fd, suppressErrorDialog: true,
      })
      factImport.commitResult = data
      showSnack(`Импорт завершён: закупок ${data.purchases_created}, платежей ${data.payments_created}`, 'success')
      await loadRunDetail(data.run_id)
      factImport.step = 6
    } catch (e: any) {
      showSnack(e?.payload?.message || `Ошибка импорта (${e?.status ?? '?'})`, 'error')
    } finally {
      factImport.loading = false
    }
  }

  async function loadRuns() {
    if (!factImport.subsidyId) return
    factImport.runsLoading = true
    try {
      factImport.runs = await apiFetch<FactImportRunListItem[]>(`${basePath()}/runs`, { suppressErrorDialog: true })
    } catch (e: any) {
      showSnack(e?.payload?.message || 'Ошибка загрузки журнала', 'error')
    } finally {
      factImport.runsLoading = false
    }
  }

  async function loadRunDetail(runId: number) {
    if (!factImport.subsidyId) return
    try {
      factImport.runDetail = await apiFetch<FactImportRunDetail>(`${basePath()}/runs/${runId}`, { suppressErrorDialog: true })
    } catch (e: any) {
      showSnack(e?.payload?.message || 'Ошибка загрузки отчёта', 'error')
    }
  }

  async function checkRollback(runId: number): Promise<FactImportRollbackCheck | null> {
    if (!factImport.subsidyId) return null
    try {
      return await apiFetch<FactImportRollbackCheck>(`${basePath()}/runs/${runId}/rollback?dry_run=true`, {
        method: 'POST', suppressErrorDialog: true,
      })
    } catch (e: any) {
      showSnack(e?.payload?.message || 'Ошибка проверки отката', 'error')
      return null
    }
  }

  async function doRollback(runId: number): Promise<boolean> {
    if (!factImport.subsidyId) return false
    try {
      await apiFetch(`${basePath()}/runs/${runId}/rollback?dry_run=false`, { method: 'POST', suppressErrorDialog: true })
      showSnack('Импорт откачен', 'success')
      await loadRuns()
      return true
    } catch (e: any) {
      showSnack(e?.payload?.message || 'Ошибка отката', 'error')
      return false
    }
  }

  const mappingValid = computed(() => factImport.mapping['plan_item_name'] != null)

  const visibleRows = computed(() => factImport.preview?.rows ?? [])
  const visibleGroups = computed(() => factImport.preview?.groups ?? [])
  const totals = computed(() => factImport.preview?.totals ?? null)
  // 🟢 Задача B — список для шага итогов (FactImportStepConfirm.vue).
  const existingUpdates = computed(() => factImport.preview?.existing_updates ?? [])

  function rowOverride(row: number): FactImportRowOverride {
    const key = String(row)
    if (!factImport.decisions.row_overrides[key]) factImport.decisions.row_overrides[key] = {}
    return factImport.decisions.row_overrides[key]
  }

  function setRowSkip(row: number, skip: boolean) {
    rowOverride(row).skip = skip
  }

  function setRowPlannedItem(row: number, plannedItemId: number | null, createNew = false) {
    const o = rowOverride(row)
    o.planned_item_id = plannedItemId
    o.create_planned_item = createNew
  }

  function setContractConfirmed(row: number, confirmed: boolean) {
    const set = new Set(factImport.decisions.contract_confirmed_rows)
    if (confirmed) set.add(row)
    else set.delete(row)
    factImport.decisions.contract_confirmed_rows = Array.from(set)
  }

  function markAllContractsConfirmed() {
    const rows = visibleRows.value.filter(r => r.needs_contract_decision).map(r => r.row)
    const set = new Set(factImport.decisions.contract_confirmed_rows)
    rows.forEach(r => set.add(r))
    factImport.decisions.contract_confirmed_rows = Array.from(set)
  }

  function setOverPlanChoice(row: number, choice: FactImportOverPlanChoice) {
    factImport.decisions.over_plan[String(row)] = choice
  }

  // 🔵 правка 3: выбор одного из 6 статусов GALA для строки, у которой
  // статус не распознан (needs_status) или человек хочет его поменять —
  // row_overrides.status принимает code (не label, см. контракт).
  function setRowStatus(row: number, code: string) {
    rowOverride(row).status = code
  }

  /** Подпись статуса по code — единственный источник сопоставления code→label
   *  (ПРАВИЛО №6): список приходит с бэкенда в preview.statuses, свой справочник
   *  6 статусов GALA фронт не хранит. */
  function statusLabel(code: string): string {
    return factImport.preview?.statuses.find(s => s.code === code)?.label ?? code
  }

  /** Строка warnings вида «статус приведён: …» (бэкенд формулирует текст сам) —
   *  используется как подсказка для маленькой пометки у приведённого статуса. */
  function statusNormalizedHint(r: FactImportRow): string | null {
    return r.warnings?.find(w => w.toLowerCase().startsWith('статус приведён')) ?? null
  }

  function setSupplierOverride(groupKey: string, contractorId: number | null) {
    factImport.decisions.supplier_overrides[groupKey] = contractorId
  }

  // 🟢🔵 «Похожие закупки» (план breezy-mixing-lovelace.md, Часть А) ------

  function existingMatchDecision(groupKey: string): FactImportExistingMatchDecision | null {
    return factImport.decisions.existing_match[groupKey] ?? null
  }

  /** «Это она» / «Нет, создать из импорта» — переключатель на группу.
   *  action='same' фиксирует ВЫБРАННУЮ existing_matches запись (purchase_id)
   *  как решённую — даже для kind='same_amount', где сервер и так
   *  предвыбрал «та же» (явное решение не мешает умолчанию, просто делает
   *  его видимым пользователю/отправляемым в decisions). */
  function setExistingMatchAction(groupKey: string, purchaseId: number, action: 'same' | 'new') {
    const prev = factImport.decisions.existing_match[groupKey]
    factImport.decisions.existing_match[groupKey] = {
      purchase_id: purchaseId,
      action,
      item_links: prev?.purchase_id === purchaseId ? prev.item_links : {},
    }
  }

  function itemLink(groupKey: string, purchaseId: number, itemId: number): FactImportExistingMatchItemLink {
    const d = factImport.decisions.existing_match[groupKey]
    if (!d || d.purchase_id !== purchaseId) {
      factImport.decisions.existing_match[groupKey] = { purchase_id: purchaseId, action: 'same', item_links: {} }
    }
    const links = factImport.decisions.existing_match[groupKey].item_links!
    if (!links[String(itemId)]) links[String(itemId)] = {}
    return links[String(itemId)]
  }

  /** Выбор другой плановой позиции для непривязанной строки существующей
   *  закупки (по умолчанию — предложение item.suggested, см. контракт). */
  function setExistingMatchItemPlanned(groupKey: string, purchaseId: number, itemId: number, plannedItemId: number | null) {
    const link = itemLink(groupKey, purchaseId, itemId)
    link.planned_item_id = plannedItemId
    link.create_planned = false
    link.skip = false
  }

  function setExistingMatchItemCreatePlanned(groupKey: string, purchaseId: number, itemId: number) {
    const link = itemLink(groupKey, purchaseId, itemId)
    link.create_planned = true
    link.planned_item_id = null
    link.skip = false
  }

  function setExistingMatchItemSkip(groupKey: string, purchaseId: number, itemId: number) {
    const link = itemLink(groupKey, purchaseId, itemId)
    link.skip = true
    link.planned_item_id = null
    link.create_planned = false
  }

  /** «Всё на строку плана из файла» — все НЕпривязанные позиции группы на
   *  предложение reason='file_row' (а если сервер уже предложил same_name —
   *  на то же предложение, т.к. бэкенд решает «строка плана из файла» как
   *  запасной вариант САМ, если точного совпадения имени не нашлось). */
  function applyAllUnboundToSuggested(groupKey: string, match: FactImportExistingMatch) {
    for (const it of match.items) {
      if (it.feo_planned_item_id != null) continue
      if (it.suggested?.planned_item_id != null) {
        setExistingMatchItemPlanned(groupKey, match.purchase_id, it.item_id, it.suggested.planned_item_id)
      }
    }
  }

  /** «Создать плановые для всех непривязанных» — ТОЛЬКО для позиций без
   *  готового предложения (suggested.planned_item_id пуст) — у остальных
   *  уже есть на что привязать, создавать вторую плановую позицию поверх
   *  готового предложения не нужно. */
  function createPlannedForAllUnbound(groupKey: string, match: FactImportExistingMatch) {
    for (const it of match.items) {
      if (it.feo_planned_item_id != null) continue
      if (it.suggested?.planned_item_id == null) {
        setExistingMatchItemCreatePlanned(groupKey, match.purchase_id, it.item_id)
      }
    }
  }

  // Перенос строки в другую группу / выделение в отдельную (Шаг 4) — правит
  // ЛОКАЛЬНУЮ копию groups в factImport.preview (чтобы карточки сразу
  // перерисовались), помечает groupsDirty — следующий loadPreview() пошлёт
  // decisions.groups и сервер пересчитает суммы по новому разбиению.
  function moveRowToGroup(row: number, targetGroupKey: string | 'new') {
    const preview = factImport.preview
    if (!preview) return
    const groups = preview.groups.map(g => ({ ...g, rows: g.rows.filter(r => r !== row) }))
    if (targetGroupKey === 'new') {
      groups.push({
        key: `manual:${row}`, supplier: null, purchase_no: null,
        category_path: '', status: '', rows: [row], contract_amount: 0, paid_amount: 0, warnings: [],
      })
    } else {
      const g = groups.find(g => g.key === targetGroupKey)
      if (g) g.rows.push(row)
    }
    preview.groups = groups.filter(g => g.rows.length > 0)
    factImport.groupsDirty = true
  }

  return {
    factImport,
    FACT_IMPORT_TARGET_FIELDS,
    openWizard,
    openWizardWithFile,
    resetWizard,
    loadSheets,
    loadPreview,
    queuePreviewRefresh,
    downloadTemplate,
    commitImport,
    loadRuns,
    loadRunDetail,
    checkRollback,
    doRollback,
    mappingValid,
    visibleRows,
    visibleGroups,
    totals,
    existingUpdates,
    rowOverride,
    setRowSkip,
    setRowPlannedItem,
    setContractConfirmed,
    markAllContractsConfirmed,
    setOverPlanChoice,
    setRowStatus,
    statusLabel,
    statusNormalizedHint,
    setSupplierOverride,
    moveRowToGroup,
    showSnack,
    existingMatchDecision,
    setExistingMatchAction,
    setExistingMatchItemPlanned,
    setExistingMatchItemCreatePlanned,
    setExistingMatchItemSkip,
    applyAllUnboundToSuggested,
    createPlannedForAllUnbound,
  }
}
