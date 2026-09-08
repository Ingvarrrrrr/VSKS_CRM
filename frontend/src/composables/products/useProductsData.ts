// useProductsData.ts — список товаров, загрузка, фильтры, вид карточек/таблицы.
// Дословный перенос из ProductsView.vue.
import { ref, computed } from 'vue'
import { apiFetch } from '@/api'
import { useCardView } from '@/composables/useCardView'
import type { ToastType } from '@/composables/useToast'
import type { Product } from './productsTypes'

export function useProductsData(showSnack: (text: string, color?: ToastType) => void) {
  const products = ref<Product[]>([])
  const loading  = ref(false)

  const search         = ref('')
  const filterType     = ref<string[]>([])
  const filterCategory = ref<string[]>([])
  const filterActive   = ref<boolean | null>(null)
  const filterPriceMin = ref<number | null>(null)
  const filterPriceMax = ref<number | null>(null)
  // Владелец, сессия 2026-08-29: «подсвечивать требующие актуализации» — быстрый
  // фильтр + счётчик, сколько таких товаров в каталоге прямо сейчас.
  const filterStaleOnly = ref(false)

  function resetFilters() {
    filterType.value = []
    filterCategory.value = []
    filterActive.value = null
    filterPriceMin.value = null
    filterPriceMax.value = null
    filterStaleOnly.value = false
  }

  async function load() {
    loading.value = true
    try { products.value = await apiFetch<Product[]>('/products/') }
    catch { showSnack('Ошибка загрузки', 'error') }
    finally { loading.value = false }
  }

  // Computed options from existing data
  const typeOptions = computed(() => {
    const types = products.value.map(p => p.product_type).filter(Boolean) as string[]
    return [...new Set(types)].sort()
  })

  const categoryOptions = computed(() => {
    const cats = products.value.map(p => p.category).filter(Boolean) as string[]
    return [...new Set(cats)].sort()
  })

  const staleProductsCount = computed(() => products.value.filter(p => p.price_freshness?.is_stale).length)

  const filteredProducts = computed(() => {
    let r = products.value
    if (filterType.value.length)     r = r.filter(p => filterType.value.includes(p.product_type || ''))
    if (filterCategory.value.length) r = r.filter(p => filterCategory.value.includes(p.category || ''))
    if (filterActive.value !== null) r = r.filter(p => p.is_active === filterActive.value)
    if (filterPriceMin.value !== null) r = r.filter(p => p.price != null && Number(p.price) >= filterPriceMin.value!)
    if (filterPriceMax.value !== null) r = r.filter(p => p.price != null && Number(p.price) <= filterPriceMax.value!)
    if (filterStaleOnly.value) r = r.filter(p => p.price_freshness?.is_stale)
    return r
  })

  const {
    mobile,
    viewMode,
    effectiveView,
    page: cardsPage,
    totalPages: cardsTotalPages,
    paged: pagedProducts,
  } = useCardView({
    storageKey: 'products_view_mode',
    source: () => filteredProducts.value,
    search: () => search.value,
    searchFields: (p: Product) => [p.name, p.description, p.product_type, p.category],
    pageSize: 24,
  })

  function cardPhotoSrc(p: Product): string | undefined {
    if (p.has_photo) return `/api/products/${p.id}/photo`
    if (p.photo_url || p.photo_link) return (p.photo_url || p.photo_link) as string
    return undefined
  }

  return {
    products, loading,
    search, filterType, filterCategory, filterActive, filterPriceMin, filterPriceMax, filterStaleOnly,
    resetFilters, load,
    typeOptions, categoryOptions, staleProductsCount, filteredProducts,
    mobile, viewMode, effectiveView, cardsPage, cardsTotalPages, pagedProducts,
    cardPhotoSrc,
  }
}
