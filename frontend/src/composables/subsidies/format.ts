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

// roundMoney — единая защита от шума плавающей точки (бюджет ФЭО − план
// считается в нескольких местах через суммирование десятков строк ФЭО;
// «равно нулю» на деле выходит 0.000000002 ₽, что переворачивало подпись
// карточки «Свободно/Превышение» на «Превышение 0 ₽», см. SubsidyKpiCards.vue
// 2026-10-06). Округление до копейки (2 знака) — тот же порядок точности,
// что formatCurrency уже показывает пользователю.
export function roundMoney(v: number): number {
  return Math.round((v + Number.EPSILON) * 100) / 100
}

export function formatCurrencyShort(v: number): string {
  if (!v) return '0 ₽'
  if (Math.abs(v) >= 1_000_000_000) return (v / 1_000_000_000).toFixed(1) + ' млрд ₽'
  if (Math.abs(v) >= 1_000_000)     return (v / 1_000_000).toFixed(1)     + ' млн ₽'
  if (Math.abs(v) >= 1_000)         return (v / 1_000).toFixed(0)         + ' тыс ₽'
  return v.toLocaleString('ru-RU') + ' ₽'
}
