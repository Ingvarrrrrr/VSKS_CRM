// usePurchaseCategories.ts — справочник категорий закупки (решение владельца
// 2026-09-16, п.1): по этим категориям товар выставляется в закупку — отдельно
// от свободнотекстовой «Категории» на товаре. Состояние — модульный ref, а не
// новый ref на каждый вызов: мультивыбор в карточке товара (ProductFormDialog)
// и диалог управления справочником (PurchaseCategoriesDialog) обязаны читать и
// писать ОДИН и тот же список, иначе правка в диалоге не отразится в открытой
// форме товара без дополнительного reload (Правило №6 — один источник, не
// копия состояния на компонент).
import { ref, computed } from 'vue'
import { apiFetch } from '@/api'
import type { PurchaseCategory } from './productsTypes'

const categories = ref<PurchaseCategory[]>([])
const loading = ref(false)
const loaded = ref(false)

type MutationResult =
  | { ok: true; item: PurchaseCategory }
  | { ok: false; error: string }

async function load(force = false): Promise<void> {
  if (loaded.value && !force) return
  loading.value = true
  try {
    categories.value = await apiFetch<PurchaseCategory[]>('/purchase-categories/')
    loaded.value = true
  } catch {
    // Справочник недоступен (бэкенд ещё не выкатил ручку/сеть) — мультивыбор
    // просто останется пустым, форма товара не должна падать из-за этого.
  } finally {
    loading.value = false
  }
}

async function createCategory(name: string): Promise<MutationResult> {
  try {
    const item = await apiFetch<PurchaseCategory>('/purchase-categories/', {
      method: 'POST',
      body: JSON.stringify({ name: name.trim(), is_active: true }),
    })
    categories.value = [...categories.value, item]
    return { ok: true, item }
  } catch (e: any) {
    return { ok: false, error: e?.detail || 'Ошибка добавления категории' }
  }
}

async function updateCategory(
  id: number,
  patch: Partial<Pick<PurchaseCategory, 'name' | 'sort_order' | 'is_active'>>,
): Promise<MutationResult> {
  const existing = categories.value.find(c => c.id === id)
  if (!existing) return { ok: false, error: 'Категория не найдена' }
  try {
    const item = await apiFetch<PurchaseCategory>(`/purchase-categories/${id}`, {
      method: 'PUT',
      body: JSON.stringify({
        name: existing.name, sort_order: existing.sort_order, is_active: existing.is_active,
        ...patch,
      }),
    })
    categories.value = categories.value.map(c => (c.id === id ? item : c))
    return { ok: true, item }
  } catch (e: any) {
    return { ok: false, error: e?.detail || 'Ошибка сохранения категории' }
  }
}

// 409 — «привязано N товаров» (текст формирует бэкенд, фронт его не
// переизобретает — тот же принцип, что и у FeoCategoryDeleteDialog.vue).
async function removeCategory(id: number): Promise<{ ok: true } | { ok: false; error: string }> {
  try {
    await apiFetch(`/purchase-categories/${id}`, { method: 'DELETE' })
    categories.value = categories.value.filter(c => c.id !== id)
    return { ok: true }
  } catch (e: any) {
    return { ok: false, error: e?.detail || 'Ошибка удаления категории' }
  }
}

export function usePurchaseCategories() {
  const activeCategories = computed(() => categories.value.filter(c => c.is_active))
  return {
    categories, activeCategories, loading, loaded,
    load, createCategory, updateCategory, removeCategory,
  }
}
