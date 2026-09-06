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
