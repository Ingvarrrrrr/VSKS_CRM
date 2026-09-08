// useProductsTz.ts — подтверждение/снятие отметки «ТЗ проверено» (стандартное
// и 44-ФЗ). Дословный перенос из ProductsView.vue.
import { ref } from 'vue'
import { apiFetch } from '@/api'
import type { ToastType } from '@/composables/useToast'
import type { Product } from './productsTypes'

export function useProductsTz(options: {
  products: { value: Product[] }
  showSnack: (text: string, color?: ToastType) => void
}) {
  const { products, showSnack } = options

  const tzVerifying = ref<string | null>(null)

  async function verifyTz(item: Product, tzType: 'standard' | '44fz') {
    tzVerifying.value = `${item.id}_${tzType}`
    try {
      const updated = await apiFetch<Product>(`/products/${item.id}/verify-tz?tz_type=${tzType}`, { method: 'PATCH' })
      const idx = products.value.findIndex(p => p.id === item.id)
      if (idx !== -1) products.value[idx] = { ...products.value[idx], ...updated }
      showSnack('ТЗ подтверждено')
    } catch {
      showSnack('Ошибка подтверждения ТЗ', 'error')
    } finally {
      tzVerifying.value = null
    }
  }

  async function unverifyTz(item: Product, tzType: 'standard' | '44fz') {
    tzVerifying.value = `${item.id}_${tzType}`
    try {
      const updated = await apiFetch<Product>(`/products/${item.id}/verify-tz?tz_type=${tzType}`, { method: 'DELETE' })
      const idx = products.value.findIndex(p => p.id === item.id)
      if (idx !== -1) products.value[idx] = { ...products.value[idx], ...updated }
      showSnack('Отметка снята')
    } catch {
      showSnack('Ошибка снятия отметки', 'error')
    } finally {
      tzVerifying.value = null
    }
  }

  return { tzVerifying, verifyTz, unverifyTz }
}
