// usePlanToRequestProductCreate.ts — «Добавить товар» прямо из строки
// подбора товара для заявки из плана (PlanToRequestRow.vue).
//
// Правило №6 (не плодить второй механизм создания товара): переиспользуем
// каталожный ProductFormDialog.vue + useProductsForm.ts дословно — тот же
// POST/PUT /products/, товар остаётся в общем каталоге для дальнейшего
// использования (владелец, задание). Ранее это было заменено заглушкой
// в PlanToRequestDialog.vue::onPickerCreateNew — недопустимо, переделано.
//
// Справочники (typeOptions/categoryOptions) считаются из узкой search-выборки
// (не полного каталога — см. loadFor ниже); мобильный брейкпоинт — тем же
// useDisplay().mobile, что useProductsData.ts у ProductsView.vue. Строка
// диалога не тянет фильтры/пагинацию/вид карточек ProductsView, только то,
// что реально нужно форме создания товара.
import { ref, computed } from 'vue'
import { useDisplay } from 'vuetify'
import { apiFetch } from '@/api'
import { useToast } from '@/composables/useToast'
import { useProductsForm } from '@/composables/products/useProductsForm'
import { productPhotoSrc } from '@/utils/productPhoto'
import type { Product } from '@/composables/products/productsTypes'
import type { PlanToWishCandidate } from './usePlanToRequest'

// Один и тот же маппинг Product → PlanToWishCandidate, что уже используется
// в PlanToRequestDialog.vue::onPickerPick (поиск в каталоге) — тот же набор
// полей, тот же источник фото (utils/productPhoto.ts, Правило №6).
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

export function usePlanToRequestProductCreate(onCreated: (cand: PlanToWishCandidate) => void) {
  const toast = useToast()
  const showSnack = (text: string, color: 'success' | 'error' | 'info' | 'warning' = 'success') =>
    toast.addToast(text, color)

  // НЕ грузим весь каталог (GET /products/ без фильтра — те самые 4 МБ,
  // источник тормозов у владельца, убирается по всему фронту). Список тут
  // только для подсказок по названию/дублей внутри самой формы — узкий,
  // по текущему search, тем же эндпоинтом и параметрами, что
  // PlanToRequestDialog.vue::runSearch (ручной поиск по каталогу) /
  // ProductPickerDialog.vue.
  const products = ref<Product[]>([])
  let searchedFor = ''
  async function loadFor(q: string) {
    searchedFor = q
    try {
      const params = new URLSearchParams()
      if (q.trim()) params.set('search', q.trim())
      params.set('limit', '20')
      params.set('is_active', 'true')
      products.value = await apiFetch<Product[]>(`/products/?${params.toString()}`)
    } catch {
      // Подсказки необязательны — форма создания товара работает и без них.
    }
  }
  // useProductsForm требует load(): Promise<void> без параметров (например,
  // может перечитать её после открытия диалога) — перечитываем тем же
  // последним поисковым запросом.
  async function load() {
    await loadFor(searchedFor)
  }

  const typeOptions = computed(() =>
    [...new Set(products.value.map(p => p.product_type).filter(Boolean) as string[])].sort(),
  )
  const categoryOptions = computed(() =>
    [...new Set(products.value.map(p => p.category).filter(Boolean) as string[])].sort(),
  )

  const { mobile } = useDisplay()

  const productForm = useProductsForm({
    products,
    load,
    showSnack,
    onSaved: (p) => onCreated(candidateFromProduct(p)),
  })

  // Открыть создание нового товара с предзаполненным наименованием/ед.
  // измерения из плановой позиции (задание владельца).
  function openCreateFor(name: string, unit?: string | null) {
    productForm.openCreate()
    productForm.form.name = name || ''
    if (unit) productForm.form.unit = unit
    // Ленивая узкая подсказка по имени плановой позиции — не весь каталог.
    loadFor(name || '')
  }

  return {
    ...productForm,
    mobile,
    typeOptions,
    categoryOptions,
    openCreateFor,
  }
}
