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

// Черновая запись цены для ТОВАРА, который ещё не сохранён (пункт 2,
// владелец 14.10: «пока товар не сохранил, невозможно добавить цену — хотелось
// бы сразу»). Живёт в form.pendingPrices (useProductsForm.ts) до первого
// успешного создания товара, затем каждая отправляется ТЕМ ЖЕ
// postPriceHistoryEntry, что и обычное «Добавить цену» (ПРАВИЛО №6 — один
// механизм записи в историю, не два).
export interface DraftPriceEntry {
  price: number
  collected_at: string
  source: PriceHistorySource
  source_ref: string | null
  contractor_id: number | null
  note: string | null
}

// Единая точка отправки ОДНОЙ записи истории цен — POST
// /products/{id}/price-history. Вызывается и из addEntry() ниже (товар уже
// существует), и из useProductsForm.ts::flushPendingPrices (товар только что
// создан, черновые записи накопились до сохранения) — не копия тела запроса
// в двух местах (ПРАВИЛО №6).
export async function postPriceHistoryEntry(productId: number, entry: DraftPriceEntry): Promise<void> {
  await apiFetch(`/products/${productId}/price-history`, {
    method: 'POST',
    body: JSON.stringify({
      price: entry.price,
      collected_at: entry.collected_at,
      source: entry.source,
      source_ref: entry.source_ref,
      contractor_id: entry.contractor_id,
      note: entry.note,
    }),
  })
}

export function useProductPriceHistory(options: {
  showSnack: (text: string, color?: ToastType) => void
  // Пункт 8 (владелец, 14.10, баг «добавил цену — не сохранилась»): addEntry/
  // removeEntry меняют Product.price на сервере своим путём (actualize_
  // product_price) — форма товара (useProductsForm.ts) должна узнать о новой
  // цене, иначе её следующее «Сохранить» отправит PUT со СТАРЫМ form.price,
  // backend увидит price!=old_price и перетрёт обратно. Колбэк получает
  // свежий товар сразу после load().
  onProductRefreshed?: (p: { price: number | null }) => void
  // Пункт 2 (владелец, 14.10): товар ещё не сохранён (productId=null) —
  // «Добавить цену» копит черновик здесь вместо POST (см. DraftPriceEntry).
  onDraftAdd?: (entry: DraftPriceEntry) => void
}) {
  const { showSnack, onProductRefreshed, onDraftAdd } = options

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
    if (!form.price || Number(form.price) <= 0) { showSnack('Укажите цену', 'error'); return }
    if (!form.collected_at) { showSnack('Укажите дату', 'error'); return }
    const entry: DraftPriceEntry = {
      price: Number(form.price),
      collected_at: form.collected_at,
      source: form.source,
      source_ref: form.source_ref.trim() || null,
      contractor_id: form.contractor_id || null,
      note: form.note.trim() || null,
    }
    if (!currentProductId) {
      // Пункт 2 (владелец, 14.10): товар ещё не сохранён — в черновик, уйдёт
      // на сервер вместе с товаром (useProductsForm.ts::flushPendingPrices).
      onDraftAdd?.(entry)
      resetForm()
      showSnack('Цена добавлена — сохранится вместе с товаром')
      return
    }
    saving.value = true
    try {
      await postPriceHistoryEntry(currentProductId, entry)
      resetForm()
      showSnack('Цена добавлена')
      await load(currentProductId)
      await refreshProductPrice()
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
      await refreshProductPrice()
    } catch (e: any) {
      showSnack(e?.detail || 'Ошибка удаления записи', 'error')
    } finally {
      deletingId.value = null
    }
  }

  // Пункт 8: сообщить форме товара актуальную цену после add/remove.
  async function refreshProductPrice(): Promise<void> {
    if (!onProductRefreshed || !currentProductId) return
    const fresh = await apiFetch<{ price: number | null }>(`/products/${currentProductId}`).catch(() => null)
    if (fresh) onProductRefreshed(fresh)
  }

  // Пункт 8в: цена введена в форме «Добавить цену», но кнопка не нажата —
  // досохранить её тем же addEntry(), не второй механизм (ПРАВИЛО №6).
  function hasPendingEntry(): boolean {
    // Пункт 2 (владелец, 14.10): раньше требовал currentProductId — незакрытая
    // мини-форма у НЕСОХРАНЁННОГО товара тоже должна досохраняться в черновик
    // перед основным «Добавить» (см. addEntry выше).
    return form.price != null && Number(form.price) > 0
  }
  async function commitPendingEntry(): Promise<void> {
    if (hasPendingEntry()) await addEntry()
  }

  return {
    entries, stats, loading, saving, deletingId, form,
    load, addEntry, removeEntry, resetForm,
    hasPendingEntry, commitPendingEntry,
  }
}
