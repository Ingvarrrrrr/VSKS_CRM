// paymentsTypes.ts — модель строки реестра платежей и определения core-колонок.
// Дословный перенос из PaymentRegistryView.vue (Правило №5: разрезка на модули).
import type { ColumnDef } from '@/composables/useColumnConfig'

export interface BankPayment {
  id: number
  import_id: number | null
  payment_date: string | null
  payment_number: string | null
  amount: number | null
  // Плательщик
  payer_name: string | null
  payer_name_resolved: string | null
  payer_inn: string | null
  payer_kpp: string | null
  payer_account: string | null
  payer_bank: string | null
  payer_bik: string | null
  // Получатель
  payee_name: string | null
  payee_name_resolved: string | null
  payee_inn: string | null
  payee_kpp: string | null
  payee_account: string | null
  payee_bank: string | null
  payee_bik: string | null
  // Парсинг
  parsed_contract_number: string | null
  parsed_contract_date: string | null
  parsed_kbk: string | null
  parsed_documents: Record<string, Array<{ number: string; date: string | null }>> | null
  status: string | null
  purpose_text: string | null
  basis_doc_text: string | null
  basis_doc_number: string | null
  basis_doc_date: string | null
  subsidy_code: string | null
  execution_datetime: string | null
  // raw_json (for raw_* columns)
  raw_json: Record<string, any> | null
  // Match
  matched_contract_id: number | null
  matched_contractor_id: number | null
  matched_purchase_id: number | null
  matched_subsidy_id: number | null
  matched_confirmed: boolean
  // 27.4-23: human-readable enriched поля для match-колонок
  matched_contractor_name: string | null
  matched_subsidy_name: string | null
  matched_contract_number: string | null
  matched_contract_subject: string | null
  matched_contract_date: string | null
  matched_purchase_number: number | null
  matched_purchase_item_name: string | null
  matched_purchase_amount: number | null
  created_at: string | null
  // Этап 7в
  expense_code: string | null
  expense_code_name: string | null
  attached_purchases: Array<{
    purchase_id: number
    purchase_number: number | null
    item_name: string | null
    amount: number | null
    basis_label: string | null
  }> | null
}

// Map from key to column definition including width/sortable
export const colMetaDefaults: Record<string, { width?: number; sortable?: boolean }> = {
  index:                      { sortable: false, width: 50 },
  payment_number:              { width: 130 },
  payment_date:                { width: 100 },
  execution_datetime:          { width: 150 },
  // Плательщик
  payer_name:                  { sortable: false, width: 180 },
  payer_inn:                   { width: 130 },
  payer_kpp:                   { width: 110 },
  payer_account:               { width: 160 },
  payer_bank:                  { sortable: false, width: 180 },
  payer_bik:                   { width: 110 },
  // Получатель
  payee_name:                  { sortable: false, width: 180 },
  payee_inn:                   { width: 130 },
  payee_kpp:                   { width: 110 },
  payee_account:               { width: 160 },
  payee_bank:                  { sortable: false, width: 180 },
  payee_bik:                   { width: 110 },
  // Прочее
  amount:                      { width: 130 },
  status:                      { width: 130 },
  purpose_text:                { sortable: false, width: 280 },
  basis_doc_text:              { sortable: false, width: 220 },
  basis_doc_number:            { width: 160 },
  basis_doc_date:              { width: 130 },
  subsidy_code:                { width: 130 },
  parsed_contract_number:      { width: 200 },
  parsed_contract_date:        { width: 130 },
  parsed_kbk:                  { width: 120 },
  matched:                     { width: 90, sortable: false },
  matched_confirmed:           { width: 110, sortable: false },
  matched_contractor_id:       { width: 200, sortable: false },
  matched_contract_id:         { width: 240, sortable: false },
  matched_purchase_id:         { width: 240, sortable: false },
  matched_subsidy_id:          { width: 200, sortable: false },
  expense_code:                { width: 150 },
  attached_purchases:          { width: 220, sortable: false },
  created_at:                  { width: 150 },
  actions:                     { sortable: false, width: 110 },
  'data-table-expand':         { width: 48 },
}

// Core typed columns — все имеют backing-поля в модели BankPayment
export const coreColumnDefs: ColumnDef[] = [
  // _rownum добавляется отдельно через tableHeaders computed (всегда первая колонка, не зависит от LS)
  { title: '', key: 'data-table-expand', group: 'core', ...colMetaDefaults['data-table-expand'] },
  { title: '№', key: 'index', group: 'core', ...colMetaDefaults['index'] },
  // Метаданные документа
  { title: 'Номер документа', key: 'payment_number', group: 'core', ...colMetaDefaults['payment_number'] },
  { title: 'Дата документа', key: 'payment_date', group: 'core', ...colMetaDefaults['payment_date'] },
  { title: 'Дата исполнения операции', key: 'execution_datetime', group: 'core', ...colMetaDefaults['execution_datetime'] },
  { title: 'Статус документа', key: 'status', group: 'core', ...colMetaDefaults['status'] },
  { title: 'Сумма', key: 'amount', group: 'core', ...colMetaDefaults['amount'] },
  // Плательщик
  { title: 'ИНН плательщика', key: 'payer_inn', group: 'core', ...colMetaDefaults['payer_inn'] },
  { title: 'КПП плательщика', key: 'payer_kpp', group: 'core', ...colMetaDefaults['payer_kpp'] },
  { title: 'Плательщик', key: 'payer_name', group: 'core', ...colMetaDefaults['payer_name'] },
  { title: 'Лицевой счёт плательщика', key: 'payer_account', group: 'core', ...colMetaDefaults['payer_account'] },
  { title: 'Банк плательщика', key: 'payer_bank', group: 'core', ...colMetaDefaults['payer_bank'] },
  { title: 'БИК плательщика', key: 'payer_bik', group: 'core', ...colMetaDefaults['payer_bik'] },
  // Получатель
  { title: 'ИНН получателя', key: 'payee_inn', group: 'core', ...colMetaDefaults['payee_inn'] },
  { title: 'КПП получателя', key: 'payee_kpp', group: 'core', ...colMetaDefaults['payee_kpp'] },
  { title: 'Получатель', key: 'payee_name', group: 'core', ...colMetaDefaults['payee_name'] },
  { title: 'Лицевой счёт получателя', key: 'payee_account', group: 'core', ...colMetaDefaults['payee_account'] },
  { title: 'Банк получателя', key: 'payee_bank', group: 'core', ...colMetaDefaults['payee_bank'] },
  { title: 'БИК получателя', key: 'payee_bik', group: 'core', ...colMetaDefaults['payee_bik'] },
  // Назначение и парсинг
  { title: 'Назначение платежа', key: 'purpose_text', group: 'core', ...colMetaDefaults['purpose_text'] },
  { title: 'Документ-основание (raw)', key: 'basis_doc_text', group: 'core', ...colMetaDefaults['basis_doc_text'] },
  { title: '№ документа-основания', key: 'basis_doc_number', group: 'core', ...colMetaDefaults['basis_doc_number'] },
  { title: 'Дата документа-основания', key: 'basis_doc_date', group: 'core', ...colMetaDefaults['basis_doc_date'] },
  { title: 'Шифр субсидии', key: 'subsidy_code', group: 'core', ...colMetaDefaults['subsidy_code'] },
  { title: 'Договор (авто)', key: 'parsed_contract_number', group: 'core', ...colMetaDefaults['parsed_contract_number'] },
  { title: 'Дата договора (авто)', key: 'parsed_contract_date', group: 'core', ...colMetaDefaults['parsed_contract_date'] },
  { title: 'КБК', key: 'parsed_kbk', group: 'core', ...colMetaDefaults['parsed_kbk'] },
  // Этап 7в: код расходов (КРЦС) + куда фактически разнесён (новое групповое сопоставление)
  { title: 'Код расходов', key: 'expense_code', group: 'core', ...colMetaDefaults['expense_code'] },
  { title: 'Куда отнесён', key: 'attached_purchases', group: 'core', ...colMetaDefaults['attached_purchases'] },
  // Match
  { title: 'Match: Контрагент', key: 'matched_contractor_id', group: 'core', ...colMetaDefaults['matched_contractor_id'] },
  { title: 'Match: Субсидия', key: 'matched_subsidy_id', group: 'core', ...colMetaDefaults['matched_subsidy_id'] },
  { title: 'Match: Договор', key: 'matched_contract_id', group: 'core', ...colMetaDefaults['matched_contract_id'] },
  { title: 'Match: Закупка', key: 'matched_purchase_id', group: 'core', ...colMetaDefaults['matched_purchase_id'] },
  { title: 'Сматчен', key: 'matched', group: 'core', ...colMetaDefaults['matched'] },
  { title: 'Подтверждён', key: 'matched_confirmed', group: 'core', ...colMetaDefaults['matched_confirmed'] },
  // Audit
  { title: 'Создано', key: 'created_at', group: 'core', ...colMetaDefaults['created_at'] },
  { title: 'Действия', key: 'actions', group: 'core', ...colMetaDefaults['actions'] },
]
