// candidateFromProduct — единственный маппинг Product → PlanToWishCandidate
// (ПРАВИЛО №6), используемый и построчным «Добавить товар»
// (PlanToRequestRow.vue → ProductEditorDialog.vue), и ручным поиском по
// каталогу (PlanToRequestDialog.vue::onPickerPick/onPickerCreateNew).
//
// Раньше здесь же жила usePlanToRequestProductCreate() — тонкая обёртка над
// useProductsForm.ts/ProductFormDialog.vue для одной-единственной строки
// подбора. Убрана (владелец 14.10, «ОДНО окно товара везде»): её роль теперь
// играет components/products/ProductEditorDialog.vue — та же форма/
// валидация/обработка дубликатов, что и на странице «Товары», без второго
// экземпляра диалога/композабла на каждый экран (ПРАВИЛО №6).
import { productPhotoSrc } from '@/utils/productPhoto'
import type { Product } from '@/composables/products/productsTypes'
import type { PlanToWishCandidate } from './usePlanToRequest'

export function candidateFromProduct(p: Product): PlanToWishCandidate {
  return {
    product_id: p.id,
    name: p.name,
    price: p.price ?? null,
    score: 1,
    photo_url: productPhotoSrc(p) ?? null,
    item_type: p.item_kind ?? null,
    category: p.category ?? null,
    product_type: p.product_type ?? null,
    unit: p.unit ?? null,
    price_updated_at: p.price_updated_at ?? null,
    price_source: p.price_source ?? null,
    price_freshness: p.price_freshness ?? null,
  }
}
