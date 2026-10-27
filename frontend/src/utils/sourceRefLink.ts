// sourceRefLink.ts — распознавание ссылки в текстовом поле "номер/ссылка" на
// источник цены (price_source_ref / source_ref) и показ её коротким текстом
// (доменом), а не полным URL (Правило №6: единственное место этой логики).
// Перенесено из composables/products/productsTypes.ts (27.10.2026), чтобы
// usePriceFreshness.ts мог использовать это без цикла импортов (productsTypes
// импортирует тип PriceFreshness оттуда) — productsTypes реэкспортирует отсюда,
// существующие импорты из productsTypes продолжают работать как раньше.
export function isUrl(v: string | null | undefined): boolean {
  return !!v && /^https?:\/\//i.test(v.trim())
}

export function linkDomain(url: string | null | undefined): string {
  if (!url) return 'ссылка'
  try {
    return new URL(url).hostname.replace(/^www\./, '') || url
  } catch {
    return url
  }
}
