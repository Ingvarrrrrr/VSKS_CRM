// useOrdersColumns.ts — конфигурация колонок таблицы закупок (ColumnHeaderMenu:
// per-column filter/sort), сохранение выбора колонок. Дословный перенос из
// OrdersView.vue, без изменения поведения.
import { computed, ref } from 'vue'
import { useColumnConfig, type ColumnDef } from '@/composables/useColumnConfig'
import { effectivePrice } from './ordersLabels'

export const allColumns: ColumnDef[] = [
  // core — видимые по умолчанию
  // _rownum добавляется отдельно через tableHeaders computed (всегда первая колонка, не зависит от LS)
  { title: '', key: 'data-table-expand', width: 48, sortable: false, group: 'core' },
  { title: 'Реестр. №', key: 'registry_number', width: 140, group: 'core' },
  { title: 'Предмет договора', key: 'subject', group: 'core' },
  { title: 'Контрагент', key: 'contractor_name', width: 220, group: 'core' },
  { title: 'Субсидия', key: 'subsidy_name', group: 'core' },
  { title: 'Цена', key: 'effective_price', align: 'end', sortable: false, group: 'core' },
  { title: '№ договора', key: 'contract_number', group: 'core' },
  { title: 'Дата договора', key: 'contract_date', group: 'core' },
  { title: 'Тип', key: 'purchase_type', width: 110, sortable: false, group: 'core' },
  { title: 'Статус', key: 'status', width: 130, group: 'core' },
  { title: 'Согласование', key: 'approval_status', width: 130, sortable: true, group: 'core' },
  { title: 'Действия', key: 'actions', sortable: false, width: 200, group: 'core' },
  // all — все остальные поля из PurchaseOut / Purchase модели
  { title: 'Наименование', key: 'item_name', group: 'all' },
  { title: 'Отображаемое название', key: 'display_name', sortable: false, group: 'all' },
  { title: 'Кол-во', key: 'planned_quantity', width: 100, align: 'end', group: 'all' },
  { title: 'Ед. изм.', key: 'unit', width: 90, group: 'all' },
  { title: 'Цена ед. (план)', key: 'planned_unit_price', width: 140, align: 'end', group: 'all' },
  { title: 'Сумма (план)', key: 'planned_total_price', width: 130, align: 'end', group: 'all' },
  { title: 'Цена ед. (факт)', key: 'final_unit_price', width: 140, align: 'end', group: 'all' },
  { title: 'Сумма (факт)', key: 'final_total_amount', width: 130, align: 'end', group: 'all' },
  { title: 'Сумма доставки', key: 'delivery_payment_amount', width: 150, align: 'end', group: 'all' },
  { title: 'НМЦД', key: 'nmck', width: 130, align: 'end', group: 'all' },
  { title: 'Итого НМЦД', key: 'total_nmck', width: 130, align: 'end', group: 'all' },
  { title: 'Цена договора', key: 'contract_price', width: 130, align: 'end', group: 'all' },
  // Phase 26-N: денежные показатели по закупке (скрыты по умолчанию, group:'all')
  { title: 'Заказано', key: 'ordered_amount', width: 130, align: 'end', group: 'all' },
  { title: 'Поставлено', key: 'delivered_amount', width: 130, align: 'end', group: 'all' },
  { title: 'Оплачено (закупка)', key: 'paid_amount', width: 130, align: 'end', group: 'all' },
  { title: 'Заказано − Поставлено', key: 'diff_ordered_delivered', width: 160, align: 'end', group: 'all' },
  { title: 'Поставлено − Оплачено', key: 'diff_delivered_paid', width: 160, align: 'end', group: 'all' },
  { title: 'Заказано − Оплачено', key: 'diff_ordered_paid', width: 160, align: 'end', group: 'all' },
  { title: 'Экономия', key: 'economy', width: 120, align: 'end', group: 'all' },
  { title: 'Превышение', key: 'price_increase', width: 130, align: 'end', group: 'all' },
  { title: 'Срок исполнения', key: 'execution_term', width: 150, group: 'all' },
  { title: 'Срок (изменён)', key: 'execution_term_changed', width: 150, group: 'all' },
  { title: 'Дата поставки', key: 'delivery_date', width: 140, group: 'all' },
  { title: 'Страна происхождения', key: 'country_origin', width: 180, group: 'all' },
  { title: 'Способ закупки', key: 'purchase_method', width: 150, group: 'all' },
  { title: 'Тип договора (контракт)', key: 'purchase_contract_type', width: 190, group: 'all' },
  { title: 'Порядковый № (рамочный)', key: 'framework_seq', width: 190, group: 'all' },
  { title: 'Основание закупки', key: 'purchase_basis', width: 160, group: 'all' },
  { title: 'Тип позиции', key: 'item_type', width: 120, group: 'all' },
  { title: 'ФЭО категория', key: 'feo_category_name', group: 'all' },
  { title: 'Ответственный', key: 'responsible_person', group: 'all' },
  { title: 'Кому возмещать', key: 'reimbursement_user_name', width: 180, group: 'all' },
  { title: 'Мн. контрагент', key: 'multi_contractor_label', width: 180, group: 'all' },
  { title: 'Предоплата', key: 'is_prepayment', width: 120, group: 'all' },
  { title: 'Дата предоплаты', key: 'prepayment_date', width: 150, group: 'all' },
  { title: 'Ежемесячный платёж', key: 'is_monthly_payment', width: 180, group: 'all' },
  { title: 'Кол-во платежей', key: 'monthly_payment_count', width: 150, group: 'all' },
  { title: 'Сумма платежа', key: 'monthly_payment_amount', width: 150, align: 'end', group: 'all' },
  { title: 'Скорее всего нужно', key: 'is_likely_needed', width: 170, group: 'all' },
  { title: 'Этап', key: 'stage_label', width: 160, group: 'all' },
  { title: 'Подстатус', key: 'substatus', width: 150, group: 'all' },
  { title: 'Место доставки', key: 'delivery_location', group: 'all' },
  { title: 'Регион мероприятия', key: 'region', width: 200, group: 'all' },
  { title: 'Регион поставки', key: 'delivery_region', width: 200, group: 'all' },
  { title: 'Тип места', key: 'delivery_location_kind', width: 130, group: 'all' },
  { title: 'Адрес доставки', key: 'delivery_address', group: 'all' },
  { title: 'Срок подачи заявок', key: 'submission_deadline', width: 170, group: 'all' },
  { title: 'Режим срока услуги', key: 'service_term_mode', width: 170, group: 'all' },
  { title: 'Дней услуги', key: 'service_term_days', width: 140, group: 'all' },
  { title: 'Тип дней', key: 'service_term_type', width: 130, group: 'all' },
  { title: 'Нач. период услуги', key: 'service_start_date', width: 170, group: 'all' },
  { title: 'Кон. период услуги', key: 'service_end_date', width: 170, group: 'all' },
  { title: 'Дедлайн услуги', key: 'service_deadline_date', width: 150, group: 'all' },
  { title: 'Плановая дата закупки', key: 'procurement_planned_date', width: 190, group: 'all' },
  { title: 'Закрывающий документ', key: 'acceptance_doc_name', width: 190, group: 'all' },
  { title: '№ закрывающего', key: 'acceptance_doc_number', width: 160, group: 'all' },
  { title: 'Дата закрывающего', key: 'acceptance_doc_date', width: 170, group: 'all' },
  { title: 'Сумма закрывающего', key: 'acceptance_doc_amount', width: 180, align: 'end', group: 'all' },
  { title: '№ ПП', key: 'payment_doc_number', width: 110, group: 'all' },
  { title: 'Дата ПП', key: 'payment_doc_date', width: 130, group: 'all' },
  { title: 'Оплачено (подтверждено)', key: 'payment_amount', width: 170, align: 'end', group: 'all' },
  // Владелец (2026-08-19): «заявлено, ждёт подтверждения» — ручные платежи,
  // не подтверждённые казначейской выпиской. Показывается рядом с
  // payment_amount, но визуально слабее (см. слот в OrdersTable.vue) — чтобы не
  // выдавать заявленное за подтверждённое.
  { title: 'Заявлено (не подтв.)', key: 'payment_amount_declared', width: 170, align: 'end', group: 'all' },
  { title: 'Оплачено (федерал.)', key: 'payment_federal', width: 170, align: 'end', group: 'all' },
  { title: 'НДС применяется', key: 'vat_applicable', width: 150, group: 'all' },
  { title: 'Ставка НДС', key: 'vat_rate', width: 120, group: 'all' },
  { title: 'Ст. НК РФ (НДС)', key: 'vat_exemption_article', width: 160, group: 'all' },
  { title: 'Третьи лица', key: 'third_party_involved', width: 140, group: 'all' },
  { title: 'Срок договора (до)', key: 'contract_end_date', width: 160, group: 'all' },
  { title: 'Тип периода услуги', key: 'service_period_type', width: 170, group: 'all' },
  { title: 'Режим описания', key: 'description_mode', width: 150, group: 'all' },
  { title: 'Режим согласования', key: 'approval_mode', width: 170, group: 'all' },
  { title: 'Тип подписи', key: 'approval_sign_type', width: 140, group: 'all' },
  { title: 'Казначейский код', key: 'treasury_code', width: 160, group: 'all' },
  { title: 'Претензионная работа', key: 'has_pretension', width: 180, group: 'all' },
  { title: 'Основание оплаты', key: 'payment_basis_type', width: 170, group: 'all' },
  { title: 'Служебная записка', key: 'service_note_text', group: 'all' },
  { title: 'Мероприятие', key: 'event_name', group: 'all' },
  { title: 'ID субсидии', key: 'subsidy_id', width: 110, group: 'all' },
  { title: 'ID договора', key: 'contract_id', width: 110, group: 'all' },
  // Phase 26-K: доп. соглашение и дата заказа — скрыты по умолчанию
  { title: '№ доп.соглашения', key: 'agreement_number', width: 170, group: 'all' },
  { title: 'Дата доп.соглашения', key: 'agreement_date', width: 180, group: 'all' },
  { title: '№ заказа', key: 'order_number', width: 140, group: 'all' },
  { title: 'Дата заказа', key: 'order_date', width: 140, group: 'all' },
]

export const groups = [
  { key: 'core', label: 'Основные' },
  { key: 'all', label: 'Все возможные' },
]

// Phase 26-N: helper for delivered amount (acceptance_doc_amount → delivery_payment_amount → last acceptance_docs entry)
function _deliveredAmount(r: any): number | null {
  if (r.acceptance_doc_amount != null) return Number(r.acceptance_doc_amount)
  if (r.delivery_payment_amount != null) return Number(r.delivery_payment_amount)
  if (Array.isArray(r.acceptance_docs) && r.acceptance_docs.length) {
    const last = r.acceptance_docs[r.acceptance_docs.length - 1]
    if (last?.amount != null) return Number(last.amount)
  }
  return null
}

// Field getters for computed/derived columns where row[key] is undefined.
export const FIELD_GETTERS: Record<string, (r: any) => any> = {
  effective_price: (r) => effectivePrice(r),
  // phase26-m: для рамочного показываем суммарную цену договора (max_amount or SUM)
  contract_price: (r: any) => {
    const isFw = (r.purchase_contract_type || '').startsWith('framework')
    if (isFw && r.framework_contract_total != null) return Number(r.framework_contract_total)
    return r.contract_price != null ? Number(r.contract_price) : null
  },
  // Phase 26-N: денежные показатели
  ordered_amount: (r: any) => r.contract_price != null ? Number(r.contract_price) : null,
  delivered_amount: (r: any) => _deliveredAmount(r),
  paid_amount: (r: any) => r.payment_amount != null ? Number(r.payment_amount) : null,
  diff_ordered_delivered: (r: any) => {
    const o = r.contract_price != null ? Number(r.contract_price) : null
    const d = _deliveredAmount(r)
    return (o != null && d != null) ? o - d : null
  },
  diff_delivered_paid: (r: any) => {
    const d = _deliveredAmount(r)
    const p = r.payment_amount != null ? Number(r.payment_amount) : null
    return (d != null && p != null) ? d - p : null
  },
  diff_ordered_paid: (r: any) => {
    const o = r.contract_price != null ? Number(r.contract_price) : null
    const p = r.payment_amount != null ? Number(r.payment_amount) : null
    return (o != null && p != null) ? o - p : null
  },
  // purchase_type — виртуальное поле, матчим по purchase_contract_type напрямую
  purchase_type: (r: any) => {
    if (r.purchase_method === 'advance') return 'advance'
    if (r.purchase_basis === 'invoice') return 'invoice'
    const ct: string = r.purchase_contract_type || ''
    if (ct === 'framework_cumulative') return 'framework_cumulative'
    if (ct === 'framework_with_amount') return 'framework_with_amount'
    return 'one_time'
  },
}
export function getRowField(row: any, key: string): any {
  const getter = FIELD_GETTERS[key]
  return getter ? getter(row) : (row?.[key] ?? null)
}

export function uniqValues(rows: any[], key: string): (string | number | null)[] {
  const set = new Set<any>()
  rows.forEach(r => set.add(r?.[key] ?? null))
  return [...set].sort((a, b) => String(a ?? '').localeCompare(String(b ?? '')))
}

export function useOrdersColumns() {
  const cfg = useColumnConfig('orders', allColumns)
  const { state: colState, visibleHeaders, toggleVisible, setPosition, setWidth, reset: resetColumns, setFilter, clearAllFilters, activeFilterCount } = cfg
  // _rownum — всегда первая колонка, не зависит от useColumnConfig состояния
  const tableHeaders = computed(() => [
    { title: '№ п/п', key: '_rownum', width: 60, sortable: false },
    ...visibleHeaders.value,
  ])
  const showColumnPicker = ref(false)

  // ── Column-header sort / filter helpers ──────────────────────────────────────
  const localSort = ref<{ key: string; order: 'asc' | 'desc' } | null>(null)
  function getSortBy(k: string) { return localSort.value?.key === k ? localSort.value.order : null }
  function applySort(k: string, dir: 'asc' | 'desc' | null) { localSort.value = dir ? { key: k, order: dir } : null }

  function matchesColumnFilters(row: any): boolean {
    const filters = cfg.state.value.filters
    for (const [k, f] of Object.entries(filters)) {
      const v = getRowField(row, k)
      if (f.type === 'text') {
        if (!f.q) continue
        if (!String(v ?? '').toLowerCase().includes(f.q.toLowerCase())) return false
      } else if (f.type === 'enum') {
        if (!f.values || f.values.length === 0) continue
        if (!f.values.includes(v)) return false
      } else if (f.type === 'number') {
        const n = typeof v === 'number' ? v : parseFloat(v)
        if (f.min != null && !(n >= f.min)) return false
        if (f.max != null && !(n <= f.max)) return false
      } else if (f.type === 'date') {
        if (!v) { if (f.from || f.to) return false; continue }
        const d = String(v).slice(0, 10)
        if (f.from && d < f.from) return false
        if (f.to && d > f.to) return false
      } else if (f.type === 'boolean') {
        if (f.value == null) continue
        if (Boolean(v) !== f.value) return false
      }
    }
    return true
  }

  return {
    cfg, colState, visibleHeaders, toggleVisible, setPosition, setWidth, resetColumns, setFilter, clearAllFilters, activeFilterCount,
    tableHeaders, showColumnPicker,
    localSort, getSortBy, applySort,
    matchesColumnFilters,
  }
}
