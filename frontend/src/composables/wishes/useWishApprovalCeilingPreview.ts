// useWishApprovalCeilingPreview.ts — предпросмотр жёсткого потолка ФЭО ДО
// нажатия «Согласовать» на заявке (владелец, 19.10.2026, решение по жёсткому
// потолку субсидии, п.1 задания «заметнее»): согласующий обязан увидеть
// крупное предупреждение с суммой превышения ДО решения, не только после.
//
// Вся формула — на бэкенде (GET /wishes/{id}/approval-ceiling-preview, см.
// app.services.wish_approval_ceiling_preview.preview_wish_approval_ceiling) —
// фронт только отображает (ПРАВИЛО №6, вторую формулу не считаем).
import { ref } from 'vue'
import { apiFetch } from '@/api'

export interface WishApprovalCeilingPreview {
  applicable: boolean
  subsidy_id: number | null
  subsidy_name: string | null
  ceiling: number | null
  total_plan_before: number | null
  total_plan_after: number | null
  over_amount: number
  error: string | null
}

export function useWishApprovalCeilingPreview() {
  const data = ref<WishApprovalCeilingPreview | null>(null)
  const loading = ref(false)
  const loadedForWishId = ref<number | null>(null)

  async function load(wishId: number) {
    if (loadedForWishId.value === wishId && data.value) return
    loading.value = true
    try {
      data.value = await apiFetch<WishApprovalCeilingPreview>(`/wishes/${wishId}/approval-ceiling-preview`)
      loadedForWishId.value = wishId
    } catch {
      // Превью — не критичный путь (ничего не блокирует): молча нет значка.
      data.value = null
      loadedForWishId.value = null
    } finally {
      loading.value = false
    }
  }

  function reset() {
    data.value = null
    loadedForWishId.value = null
  }

  return { data, loading, load, reset }
}
