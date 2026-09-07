// Общие типы карточки субсидии, вынесенные из SubsidiesView.vue при разбиении на
// компоненты (components/subsidies/*) и композаблы (composables/subsidies/*).
// Единственный источник этих интерфейсов — SubsidiesView.vue раньше объявлял их
// локально; теперь оба импортируют отсюда (Правило №6 — один показатель/тип,
// один источник истины).

export interface SubsidyRow {
  id: number; name: string; year: number; budget: number
  calculated_budget?: number
  description?: string; planned: number; paid: number; contracted: number
  plan_schedule: number; ordered: number
  feo_filled?: boolean
  feo_budget_total?: number
  contractor_id?: number
  contractor_name?: string
  contractor_inn?: string
  basis_doc_number?: string
  basis_doc_date?: string
  // Phase 31-05: canonical budget fields
  remaining?: number | null
  planned_amount?: number | null
  budget_discrepancy?: number | null
  require_planned_dates?: boolean
  // Phase 32: dashboard KPI fields
  work: number
  contracts: number
  delivered: number
  delivered_unpaid: number
  // Владелец (2026-08-30): предупреждение «сумма заказанного приближается к
  // потолку субсидии» — см. app/services/feo_plan.py calculate_ceiling_forecast*.
  ceiling_warn_percent?: number | null
  ceiling_total?: number | null
  ceiling_committed_total?: number | null
  ceiling_committed_percent?: number | null
  ceiling_near_warning?: boolean
  ceiling_exceeded?: boolean
  // C4: черновые субсидии — статус/автор/утвердивший.
  status?: string
  created_by?: number | null
  approved_by?: number | null
  approved_at?: string | null
}

// C4: участник (соредактор) черновой субсидии — калька wish_member без
// consent-флоу, см. backend/app/routers/subsidy_members.py.
export interface SubsidyMember {
  id: number
  subsidy_id: number
  user_id: number
  added_by_id: number | null
  username?: string | null
  full_name?: string | null
  added_by_name?: string | null
  created_at?: string | null
}

export interface FeoCategory {
  id: number; parent_id: number | null; subsidy_id: number
  level: number; name: string; code: string | null; appendix: string | null
  is_active: boolean; budget: number | null; planned_quantity: number | null; planned_amount: number | null; unit: string | null
  feo_quantity: number | null; feo_unit: string | null
  description: string | null; feo_amount: number | null
  // План zany-fluttering-mountain.md, п.1/п.5: способ расчёта плана — переключатель
  // «по плановым позициям» / «по вручную заданной сумме».
  plan_source?: 'planned_items' | 'manual_sum'
  manual_plan_amount?: number | null
}

export interface FeoNode extends FeoCategory {
  depth: number
  hasChildren: boolean
  children: FeoNode[]
}

// ── Approvers types ───────────────────────────────
export interface SubsidyApprover {
  id: number
  subsidy_id: number
  role_name: string
  full_name: string
  order_num: number
  is_default: boolean
  can_initiate: boolean
  show_feo_path: boolean
  user_id?: number | null
}

// ── Events (Мероприятия) ──────────────────────────
export interface EventItem {
  id: number; subsidy_id: number; name: string; is_active: boolean
  region?: string; date_from?: string; date_to?: string
  order_decree?: string; planned_indicators?: string; actual_indicators?: string
  media_link_1?: string; media_link_2?: string; media_link_3?: string
}

export interface SubsidyDeleteImpact {
  feo_categories: number
  planned_items: number
  purchases: number
  contracts: number
}

// ── Плановые/фактические позиции ФЭО (панель «План vs факт», волна 5a-2) ──────
// Вынесены из SubsidiesView.vue при разбиении на PlannedItem*/PlanGraph*-диалоги —
// единственный источник этих интерфейсов, парент и новые компоненты импортируют
// отсюда (Правило №6).
export interface FeoPlannedItem {
  id: number
  feo_category_id: number
  name: string
  quantity: number | null
  unit: string | null
  amount: number | null
  // Цена ЗА ЕДИНИЦУ (владелец, 2026-09-02) — необязательное поле, см. докстринг
  // FeoPlannedItem.unit_price (backend/app/models/feo_planned_item.py) и
  // assert_tz_not_over_plan (backend/app/services/feo_plan.py): задана → план
  // полноценный (кол-во/цена/сумма проверяются); NULL → amount сама по себе
  // итоговая сумма, quantity ориентировочное. PUT здесь — ПОЛНАЯ замена (см.
  // остальные PATCHABLE-комментарии в файле) — все места, шлющие PUT
  // /feo-planned-items/{id}, обязаны передавать unit_price существующей
  // позиции явно, иначе он молча обнулится.
  unit_price?: number | null
  notes: string | null
  is_active: boolean
  payment_mode?: 'one_time' | 'monthly'
  planned_date?: string | null
  monthly_start_date?: string | null
  months_count?: number | null
  monthly_amount?: number | null
  // Владелец (2026-08-12, замечание 2): порядок позиций внутри категории —
  // настраиваемый (стрелки вверх/вниз), см. reorderPlannedItem в SubsidiesView.vue.
  sort_order?: number | null
  // Блок 1 (план zany-fluttering-mountain.md, 2026-08-14): товар / услуга / работа.
  item_type?: string | null
  // Владелец (2026-08-18): «данные есть [у связанных позиций закупок], почему
  // не подтягиваются?» — свой item_type, иначе унаследованный от purchase_items,
  // иначе null (GET /feo-planned-items/comparison, см. FeoPlannedItemOut в бэкенде).
  item_type_effective?: string | null
  item_type_inherited?: boolean
  // Происхождение плановой позиции (владелец, 2026-09-01) — ДВЕ НЕЗАВИСИМЫЕ
  // галочки, не переключатель: is_feo_breakdown — жёсткая построчная разбивка
  // ФЭО реально есть (покупать будут именно это, отчётность строгая);
  // is_internal_plan — в ФЭО была только более широкая категория (или позиции
  // не было вовсе), состав придумали сами. См. backend/app/models/feo_planned_item.py.
  is_feo_breakdown?: boolean
  is_internal_plan?: boolean
}

// Стадия уточнения позиции (ФЭО → План → Что выставили на закупку → Номенклатура
// подрядчика → Приняли) — справочная детализация, отдаётся бэкендом внутри FeoActualItem.stages.
export interface FeoStage {
  key: string
  label: string
  name: string
  quantity: number | null
  unit: string | null
  unit_price: number | null
  total: number | null
}

export interface FeoActualItem {
  purchase_item_id: number
  item_name: string
  quantity: number | null
  unit: string | null
  unit_price: number | null
  total_price: number | null
  feo_planned_item_id: number | null
  purchase_id: number
  purchase_number: number | null
  registry_number: string | null
  purchase_status: string | null
  wish_id?: number | null
  contract_number: string | null
  contractor_name: string | null
  product_photo?: string | null
  // Требование владельца (2026-08-05): факт появляется с «Заказано», уточняется закрывающими
  // документами при «Поставлено»/«Оплачено» — см. calcDiff/FACT_STATUSES в SubsidiesView.vue.
  final_unit_price?: number | null
  final_total?: number | null
  acceptance_doc_amount?: number | null
  contract_price?: number | null
  purchase_items_count?: number | null
  fact_amount?: number | null
  fact_confirmed?: boolean
  fact_allocated?: boolean
  over_plan?: boolean
  // Разворот по стадиям уточнения наименования/кол-ва (панель «план vs факт», см. FeoStage)
  stages?: FeoStage[]
  // Владелец, 2026-08-13: остановка закупки — read-only, системой проставляется в
  // POST /api/wishes/{wish_id}/stop. ⚠️ /feo-planned-items/comparison пока не
  // выбирает и не отдаёт эти поля на строке позиции (только Purchase.status) —
  // поля опциональны и на практике сейчас всегда undefined, маркер «ЗАКУПКА
  // ОСТАНОВЛЕНА» ниже по файлу не появится, пока бэкенд их не добавит.
  stopped_at?: string | null
  stopped_by_name?: string | null
}

// ── Левая группа колонок панели «план vs факт» (см. leftGroupInfo в feoCategoryUtils.ts) ──
export interface FeoLeftGroupInfo {
  name: string
  quantity: number | null
  unit: string | null
  unitPrice: number | null
  total: number | null
  isContract: boolean
}

// ── Позиции заявок «из закупок», привязанные к категории ФЭО (панель «План vs
// факт», волна 5b) — вынесены из SubsidiesView.vue (interface FeoReqItem) при
// разбиении useKpiDrilldown.ts: используется и деревом ФЭО (остаётся в
// SubsidiesView.vue), и KPI drill-down (kpiItemMatches из constants/kpiMetrics.ts
// принимает эту форму структурно). Единственный источник — не копия (Правило №6).
export interface FeoReqItem {
  id: number
  item_name: string
  quantity: number
  unit: string | null
  unit_price: number
  total_price: number
  purchase_id: number
  purchase_number: number | null
  registry_number: string | null
  purchase_status: string
  wish_id: number | null
  category: string
  product_type: string
  product_photo?: string | null
  // Phase KPI-drilldown: расширено бэкендом, старый бэк может не отдавать — все опциональны
  contract_id?: number | null
  purchase_contract_type?: string | null
  contract_type?: string | null
  contract_status?: string | null
  contract_number?: string | null
  // Anti-doublecount: позиция привязана к плановой позиции (feo_planned_items) — РАСХОДУЕТ
  // её план, а не складывается с ним поверх. wish_item_id — исходная позиция заявки (справочно).
  feo_planned_item_id?: number | null
  wish_item_id?: number | null
  // Задача владельца «план ≠ факт» (сессия 2026-08-06, шаг 5): снимок ТЗ — заморожен
  // с момента объявления закупки (см. purchase_items.planned_*), фолбэк на текущие
  // quantity/unit_price/total_price для старых записей без снимка — см. backend
  // /feo-categories/planned-purchase-items.
  planned_quantity?: number | null
  planned_unit_price?: number | null
  planned_total?: number | null
  // Факт — та же формула, что и FeoActualItem.fact_amount (comparison-эндпоинт):
  // точное сопоставление по ContractItem.source_item_id, иначе пропорция от
  // purchases.contract_price. null — факта ещё нет (план_schedule/нет договорных данных).
  fact_amount?: number | null
  fact_quantity?: number | null
  fact_unit_price?: number | null
  fact_confirmed?: boolean
  fact_allocated?: boolean
  // Владелец, 2026-08-13: остановка закупки — см. аналогичный комментарий у
  // FeoActualItem.stopped_at. /feo-categories/planned-purchase-items тоже пока
  // не отдаёт эти поля — на практике всегда undefined.
  stopped_at?: string | null
  stopped_by_name?: string | null
}

// Режим базы для колонок «Плановое кол-во/сумма/остаток» дерева ФЭО — вынесен
// сюда вместе с FeoReqItem (используется и useKpiDrilldown.ts, и деревом).
export type PlannedBase = 'all' | 'manual' | 'requests' | 'purchases'

// ── Импорт ФЭО из Excel (FeoImportWizard.vue/useFeoImport.ts) ─────────────────
export interface FeoWarning {
  kind: 'level_gap' | 'level_duplicate' | 'sum_mismatch' | 'sum_without_qty' | 'parent_sum_mismatch'
    | 'level_name_in_number_column' | 'item_promoted_to_level2' | 'item_type_unknown'
    | 'column_shift' | 'group_plan_ignored' | 'plan_vs_items_mismatch' | 'plan_skipped_has_items'
  row: number | null
  name: string
  message: string
}
export interface FeoUnmatchedNode {
  id: number
  path: string
  kind: 'empty' | 'needs_mapping'
  suggestion: string | null
  suggestion_reason: string | null
  load: {
    purchases?: number
    purchase_items?: number
    wishes?: number
    wish_items?: number
    products?: number
    feo_planned_items?: number
  }
  blocking_purchases: { id: number; purchase_number: number | null; subject: string; status: string; status_label: string }[]
}
export interface FeoRemapApplied {
  old_path: string
  new_path: string
  counts: Record<string, number>
}
export interface FeoImportResult {
  created: number
  updated?: number
  skipped: number
  errors: { row: number; name: string; message: string }[]
  updated_details?: { row: number; name: string; reason: string }[]
  skipped_details?: { row: number; name: string; reason: string }[]
  created_details?: { row: number; name: string; reason: string }[]
  warnings?: FeoWarning[]
  unmatched?: FeoUnmatchedNode[]
  new_paths?: string[]
  deleted_count?: number
  relinked_count?: number
  deleted_details?: { path: string; reason: string }[]
  remap_applied?: FeoRemapApplied[]
  remap_aborted_reason?: string | null
  version_created?: boolean
  deletes_applied?: boolean
}
