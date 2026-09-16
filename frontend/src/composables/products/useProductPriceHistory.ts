// useProductPriceHistory.ts — история цен товара + средняя цена (решение
// владельца 2026-09-16, п.2/п.3). Заменяет собой редактируемые «Ссылки для
// сравнения цен» (price_links) в карточке товара: те остаются только как
// read-only строки «мониторинг (старая ссылка)» — см. PurchasePriceHistory.vue.
import { ref, reactive } from 'vue'
import { apiFetch } from '@/api'
import type { ToastType } from '@/composables/useToast'
import type { PriceHistoryEntry } from './productsTypes'

export interface PriceStats {
  avg_price: number | null
  basis_count: number
  window_days: number
  stale: boolean
  from_date: string
  to_date: string
}

export type PriceHistorySource = 'manual' | 'kp' | 'monitoring'

export function useProductPriceHistory(options: { showSnack: (text: string, color?: ToastType) => void }) {
  const { showSnack } = options

  const entries = ref<PriceHistoryEntry[]>([])
  const stats = ref<PriceStats | null>(null)
  const loading = ref(false)
  const saving = ref(false)
  const deletingId = ref<number | null>(null)

  let currentProductId: number | null = null

  function todayISO(): string {
    return new Date().toISOString().slice(0, 10)
  }

  const emptyForm = () => ({
    price: null as number | null,
    collected_at: todayISO(),
    source: 'manual' as PriceHistorySource,
    source_ref: '' as string,
    contractor_id: null as number | null,
    note: '' as string,
  })
  const form = reactive(emptyForm())

  function resetForm() {
    Object.assign(form, emptyForm())
  }

  async function load(productId: number | null): Promise<void> {
    currentProductId = productId
    entries.value = []
    stats.value = null
    if (!productId) return
    loading.value = true
    try {
      const [hist, st] = await Promise.all([
        apiFetch<PriceHistoryEntry[]>(`/products/${productId}/price-history`),
        apiFetch<PriceStats>(`/products/${productId}/price-stats`),
      ])
      entries.value = hist
      stats.value = st
    } catch (e: any) {
      showSnack(e?.detail || 'Не удалось загрузить историю цен', 'error')
    } finally {
      loading.value = false
    }
  }

  async function addEntry(): Promise<void> {
    if (!currentProductId) return
    if (!form.price || Number(form.price) <= 0) { showSnack('Укажите цену', 'error'); return }
    if (!form.collected_at) { showSnack('Укажите дату', 'error'); return }
    saving.value = true
    try {
      await apiFetch(`/products/${currentProductId}/price-history`, {
        method: 'POST',
        body: JSON.stringify({
          price: Number(form.price),
          collected_at: form.collected_at,
          source: form.source,
          source_ref: form.source_ref.trim() || null,
          contractor_id: form.contractor_id || null,
          note: form.note.trim() || null,
        }),
      })
      resetForm()
      showSnack('Цена добавлена')
      await load(currentProductId)
    } catch (e: any) {
      showSnack(e?.detail || 'Ошибка добавления цены', 'error')
    } finally {
      saving.value = false
    }
  }

  async function removeEntry(id: number): Promise<void> {
    if (!currentProductId) return
    deletingId.value = id
    try {
      await apiFetch(`/products/${currentProductId}/price-history/${id}`, { method: 'DELETE' })
      showSnack('Запись удалена')
      await load(currentProductId)
    } catch (e: any) {
      showSnack(e?.detail || 'Ошибка удаления записи', 'error')
    } finally {
      deletingId.value = null
    }
  }

  return {
    entries, stats, loading, saving, deletingId, form,
    load, addEntry, removeEntry, resetForm,
  }
}
