// useProductsActualize.ts — актуализация цены товара + история актуализаций
// (владелец, сессия 2026-08-29: «цена может быть уже неактуальна, надо
// показывать дату актуализации и уметь её обновить»). Дословный перенос из
// ProductsView.vue.
import { reactive } from 'vue'
import { apiFetch } from '@/api'
import { PRICE_SOURCE_LABELS } from '@/composables/usePriceFreshness'
import type { ToastType } from '@/composables/useToast'
import type { Product, PriceHistoryEntry } from './productsTypes'

export function useProductsActualize(options: {
  products: { value: Product[] }
  showSnack: (text: string, color?: ToastType) => void
}) {
  const { products, showSnack } = options

  const priceSourceOptions = Object.entries(PRICE_SOURCE_LABELS).map(([value, title]) => ({ value, title }))

  const actualizeDialog = reactive({
    show: false,
    product: null as Product | null,
    history: [] as PriceHistoryEntry[],
    historyLoading: false,
    saving: false,
  })
  const actualizeForm = reactive({
    price: null as number | null,
    collected_at: new Date().toISOString().slice(0, 10),
    source: 'manual' as string,
    source_ref: '',
    contractor_id: null as number | null,
    note: '',
  })

  async function openActualizeDialog(p: Product) {
    actualizeDialog.product = p
    actualizeDialog.history = []
    actualizeForm.price = p.price ?? null
    actualizeForm.collected_at = new Date().toISOString().slice(0, 10)
    actualizeForm.source = 'manual'
    actualizeForm.source_ref = ''
    actualizeForm.contractor_id = p.price_source_contractor_id ?? null
    actualizeForm.note = ''
    actualizeDialog.show = true

    actualizeDialog.historyLoading = true
    try {
      actualizeDialog.history = await apiFetch<PriceHistoryEntry[]>(`/products/${p.id}/price-history`)
    } catch (e: any) {
      showSnack(e?.payload?.message || e?.detail || 'Не удалось загрузить историю актуализаций', 'error')
    } finally {
      actualizeDialog.historyLoading = false
    }
  }

  async function saveActualization() {
    const p = actualizeDialog.product
    if (!p || !actualizeForm.price || !actualizeForm.source) return
    actualizeDialog.saving = true
    try {
      const updated = await apiFetch<Product>(`/products/${p.id}/price-actualization`, {
        method: 'POST',
        body: {
          price: actualizeForm.price,
          source: actualizeForm.source,
          source_ref: actualizeForm.source_ref?.trim() || null,
          contractor_id: actualizeForm.contractor_id || null,
          collected_at: actualizeForm.collected_at || null,
          note: actualizeForm.note?.trim() || null,
        },
      })
      const idx = products.value.findIndex(x => x.id === p.id)
      if (idx !== -1) products.value[idx] = { ...products.value[idx], ...updated }
      showSnack('Цена актуализирована')
      actualizeDialog.show = false
    } catch (e: any) {
      showSnack(e?.payload?.message || e?.detail || `Ошибка актуализации цены (HTTP ${e?.status ?? '?'})`, 'error')
    } finally {
      actualizeDialog.saving = false
    }
  }

  return { priceSourceOptions, actualizeDialog, actualizeForm, openActualizeDialog, saveActualization }
}
