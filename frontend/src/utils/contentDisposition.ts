// Разбор заголовка Content-Disposition для скачиваемых файлов (экспорт в Excel/Word/шаблоны).
// Предпочитаем filename*=UTF-8'' (кириллица корректно), иначе filename="...".
// Голый /filename=([^;]+)/ без кавычек ловит их в имя → браузер превращает в «_» → битое расширение.
// Было по месту в нескольких файлах (usePlanGraphVersions.ts, useVehicleListTemplate.ts,
// CreateOrderView.vue, FeoCategoriesView.vue и др.) — здесь общий хелпер для новых мест
// (ПРАВИЛО №6: один источник истины), старые места не трогаем, если их не затрагивает задача.
export function filenameFromContentDisposition(cd: string | null | undefined, fallback: string): string {
  if (!cd) return fallback
  const star = cd.match(/filename\*\s*=\s*UTF-8''([^;\n]+)/i)
  if (star && star[1]) {
    try { return decodeURIComponent(star[1].trim()) } catch { /* fallthrough */ }
  }
  const plain = cd.match(/filename\s*=\s*(?:"([^"]+)"|([^;\n]+))/i)
  if (plain) {
    const name = (plain[1] ?? plain[2])?.trim()
    if (name) return name
  }
  return fallback
}
