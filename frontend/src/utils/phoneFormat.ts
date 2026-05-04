/**
 * Утилиты форматирования телефона в российском формате: 1-111-111-11-11
 */

/** Только цифры из строки */
export function unformatPhone(s: string): string {
  return s.replace(/\D/g, '')
}

/**
 * Форматирует строку с цифрами в вид 1-111-111-11-11.
 * Принимает любую строку: убирает нецифровые символы, затем форматирует.
 * Если цифр < 11 — возвращает только цифры без маски (частичный ввод).
 * Если передана пустая строка — возвращает пустую строку.
 */
export function formatPhoneRu(raw: string | null | undefined): string {
  if (!raw) return ''
  const digits = raw.replace(/\D/g, '')
  if (digits.length === 0) return ''
  if (digits.length < 11) return digits

  // Берём ровно 11 цифр
  const d = digits.slice(0, 11)
  // Формат: d[0]-d[1-3]-d[4-6]-d[7-8]-d[9-10]
  return `${d[0]}-${d.slice(1, 4)}-${d.slice(4, 7)}-${d.slice(7, 9)}-${d.slice(9, 11)}`
}
