import { ref } from 'vue'
import { apiFetch } from '@/api'
import type { FieldHistoryItem } from './vehicleDetailTypes'

// ─────────────────────────────────────────────────────────────────────────
// История изменений полей карточки ТС (вкладка «История» использует
// VehicleHistoryTab.vue отдельно; здесь — только последние 20 записей для
// ленты событий на вкладке «Общее», Slice-2).
// ─────────────────────────────────────────────────────────────────────────

export function useVehicleFieldHistory() {
  const fieldHistory = ref<FieldHistoryItem[]>([])

  async function loadFieldHistory(id: number) {
    try {
      const data = await apiFetch<FieldHistoryItem[] | { items: FieldHistoryItem[]; total: number }>(
        `/vehicles/${id}/field-history?limit=20`
      )
      const arr = Array.isArray(data) ? data : (data as { items: FieldHistoryItem[] }).items ?? []
      fieldHistory.value = arr
    } catch (e) {
      console.warn('[useVehicleFieldHistory] loadFieldHistory failed (silent):', e)
      fieldHistory.value = []
    }
  }

  return { fieldHistory, loadFieldHistory }
}
