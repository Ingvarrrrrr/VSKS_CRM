import { ref } from 'vue'
import { apiFetch } from '@/api'
import type { TransferHistoryItem } from './vehicleDetailTypes'

// ─────────────────────────────────────────────────────────────────────────
// История передач ТС между владельцами/эксплуатантами (карточка «История
// передач» на вкладке «Общее»).
// ─────────────────────────────────────────────────────────────────────────

export function useVehicleTransferHistory() {
  const transferHistory = ref<TransferHistoryItem[]>([])
  const loadingTransferHistory = ref(false)

  async function loadTransferHistory(id: number) {
    loadingTransferHistory.value = true
    try {
      const data = await apiFetch<TransferHistoryItem[]>(`/vehicles/${id}/transfer-history`)
      transferHistory.value = Array.isArray(data) ? data : []
    } catch {
      transferHistory.value = []
    } finally {
      loadingTransferHistory.value = false
    }
  }

  return { transferHistory, loadingTransferHistory, loadTransferHistory }
}
