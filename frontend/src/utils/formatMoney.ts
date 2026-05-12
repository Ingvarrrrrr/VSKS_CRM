export function formatMoney(n: number | string | null | undefined, suffix = ' ₽'): string {
  if (n === null || n === undefined || n === '') return '—'
  const num = typeof n === 'string' ? parseFloat(n) : Number(n)
  if (isNaN(num)) return '—'
  return num.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + suffix
}
