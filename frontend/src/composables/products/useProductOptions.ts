// useProductOptions.ts — подсказки «Категория»/«Тип товара» по ВСЕМУ каталогу
// (GET /products/options, backend/app/routers/products_options.py). Баг
// владельца (22.10.2026): ProductEditorDialog.vue строил typeOptions/
// categoryOptions только из товаров, найденных поиском по названию РЕДАКТИРУЕМОГО
// товара (≤20 штук) — там обычно только сам товар, подсказывать нечего.
// Подсказки необязательны — форма работает и без них, поэтому ошибки глотаем.
import { ref } from 'vue'
import { apiFetch } from '@/api'

export function useProductOptions() {
  const categories = ref<string[]>([])
  const types = ref<string[]>([])

  async function load() {
    try {
      const data = await apiFetch<{ categories: string[]; types: string[] }>('/products/options')
      categories.value = data.categories || []
      types.value = data.types || []
    } catch {
      // Подсказки необязательны — ничего не делаем, форма работает без них.
    }
  }

  return { categories, types, load }
}
