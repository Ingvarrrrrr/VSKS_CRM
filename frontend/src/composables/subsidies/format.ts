// formatCurrency вынесен из SubsidiesView.vue (использовался локально ~140 раз) в
// общий модуль, потому что FeoCategoryDialog.vue тоже показывает суммы «старого
// формата» плана категории и не должен заводить свою копию форматирования
// (Правило №6 — один источник истины). Поведение не изменено: та же строка с
// разделителями разрядов ru-RU и двумя знаками после запятой.
export function formatCurrency(v: number | string): string {
  // API отдаёт Decimal строками — без Number() toLocaleString вернёт строку как есть, без пробелов-разрядов
  const n = Number(v) || 0
  return n.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' ₽'
}

// formatCurrencyRound/formatCurrencyShort — вынесены сюда же при разбиении
// SubsidiesView.vue (волна 5b: SubsidyListHeader/SubsidyListTable/SubsidyCardsGrid/
// SubsidySummaryBar/SubsidyKpiCards) — использовались локально и в списке субсидий,
// и в KPI-карточках, и в дереве ФЭО (остаётся в SubsidiesView.vue). Один источник,
// не копия (Правило №6). Поведение не изменено.
export function formatCurrencyRound(v: number | string): string {
  const n = typeof v === 'string' ? parseFloat(v) : v
  return (n || 0).toLocaleString('ru-RU', { maximumFractionDigits: 0 }) + ' ₽'
}

export function formatCurrencyShort(v: number): string {
  if (!v) return '0 ₽'
  if (Math.abs(v) >= 1_000_000_000) return (v / 1_000_000_000).toFixed(1) + ' млрд ₽'
  if (Math.abs(v) >= 1_000_000)     return (v / 1_000_000).toFixed(1)     + ' млн ₽'
  if (Math.abs(v) >= 1_000)         return (v / 1_000).toFixed(0)         + ' тыс ₽'
  return v.toLocaleString('ru-RU') + ' ₽'
}
