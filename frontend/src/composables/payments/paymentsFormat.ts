// paymentsFormat.ts — чистые функции форматирования реестра платежей.
// Дословный перенос из PaymentRegistryView.vue.
//
// ВАЖНО (Правило №6): это единственный источник formatMoney для реестра
// платежей. Раньше в файле параллельно существовал неиспользуемый импорт
// `formatMoney` из '@/utils/formatMoney' (другая реализация — toLocaleString +
// суффикс « ₽») — локальное объявление функции ниже его затеняло, и bundler
// (esbuild) полностью выпиливал импорт как мёртвый код (проверено по
// собранному чанку: 0 вхождений toLocaleString, только Intl.NumberFormat).
// Реально в проде работала ТОЛЬКО версия на Intl.NumberFormat — она и
// перенесена сюда как единственная. Второй источник не заводим.
export function fmtDate(d: string | null): string {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('ru-RU')
}

export function formatMoney(v: number | null | undefined): string {
  if (v == null) return '—'
  return new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 2 }).format(v)
}

// Doc display: тип + номер.
// Соглашение убрано — оно в 100% платежей через basis_doc, неинформативно в этой колонке.
export function docDisplay(item: any): string {
  const pd = item.parsed_documents || {}
  if (pd.contracts?.[0]) return `Договор ${pd.contracts[0].number}`
  if (pd.advance_reports?.[0]) return `Авансовый отчёт ${pd.advance_reports[0].number}`
  if (pd.acts?.[0]) return `Акт ${pd.acts[0].number}`
  if (pd.upd?.[0]) return `УПД ${pd.upd[0].number}`
  if (pd.invoices?.[0]) return `Счёт ${pd.invoices[0].number}`
  if (pd.ttn?.[0]) return `ТТН ${pd.ttn[0].number}`
  if (pd.registry?.[0]) return `Реестр ${pd.registry[0].number}`
  if (item.parsed_contract_number) return `Договор ${item.parsed_contract_number}`
  return '—'
}

export function statusColor(s: string | null): string {
  if (!s) return 'grey'
  if (s === 'ИСПОЛНЕН') return 'success'
  if (s === 'АННУЛИРОВАН') return 'error'
  return 'warning'
}
