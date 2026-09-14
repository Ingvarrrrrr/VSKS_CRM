// productPhotoSrc — ЕДИНЫЙ источник вычисления src для фото товара
// (ПРАВИЛО №6). До 2026-09-15 одна и та же логика («если есть загруженный
// файл — /api/products/{id}/photo, иначе photo_url || photo_link») была
// продублирована минимум в 6 местах: AdvancedProductSelector.vue,
// ProductSelector.vue, CreateOrderView.vue, useProductsData.ts (cardPhotoSrc),
// useItemsCatalog.ts, useWishForm.ts (photoOf) и inline-тернарником в
// useWishActions.ts. Дефект №3 плана (2026-09-15): часть значений
// `photo_link`, оставшихся от Excel-импорта, — не адрес, а буквально текст
// «НЕ смог найти» (парсер не нашёл картинку и записал причину вместо null).
// Все дубли отдавали этот текст как есть в :src, браузер честно пытался
// загрузить «страница/НЕ смог найти» как относительный URL и рисовал
// битую иконку вместо плейсхолдера. Чинить пришлось бы в шести местах —
// вместо этого дубли сведены к этому единственному источнику, и он же
// одним правилом (isLikelyImageUrl) отсекает мусор для всех потребителей.
export interface ProductPhotoLike {
  id: number
  has_photo?: boolean
  photo_url?: string | null
  photo_link?: string | null
}

// Валиден только настоящий http(s) адрес или собственный относительный путь
// (`/api/...`) — этого достаточно, чтобы отличить реальную ссылку от текста
// вроде «НЕ смог найти» или «уточнить у поставщика», которым парсер импорта
// иногда заполняет колонку вместо null.
export function isLikelyImageUrl(link: string | null | undefined): link is string {
  if (!link) return false
  const s = link.trim()
  if (!s) return false
  return /^https?:\/\//i.test(s) || s.startsWith('/api/')
}

export function productPhotoSrc(p: ProductPhotoLike | null | undefined): string | undefined {
  if (!p) return undefined
  if (p.has_photo) return `/api/products/${p.id}/photo`
  const candidate = p.photo_url || p.photo_link || undefined
  return isLikelyImageUrl(candidate) ? candidate : undefined
}
