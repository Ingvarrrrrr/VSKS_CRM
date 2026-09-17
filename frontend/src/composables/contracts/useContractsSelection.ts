// useContractsSelection.ts — множественный выбор строк реестра договоров и
// массовые действия (удаление, экспорт). По образцу выбора/массовых действий
// в закупках (useOrdersData.ts::confirmBulkDelete + OrdersView.vue bulk bar),
// но без второго bulk-delete endpoint — сервера для этого нет (ПРАВИЛО №6:
// не заводить новый роут, использовать существующий DELETE /contracts/{id}
// последовательно).
//
// Регресс 2026-09-17 (владелец): изначально selected хранил Contract[] через
// return-object на v-data-table, но return-object в Vuetify 3 ломает ТАКЖЕ
// v-model:expanded (тот перестаёт быть number[], в /purchases/by-contract/
// уходит [object Object]). Убрали return-object у таблицы — selected теперь
// number[] (id, как и expanded), а полные Contract для показа номеров/
// экспорта резолвятся здесь по id из уже загруженного списка contracts
// (второй источник данных не заводим).
import { computed, reactive, ref } from 'vue'
import { apiFetch } from '@/api'
import type { ToastType } from '@/composables/useToast'
import type { Contract } from './contractsTypes'

export interface BulkDeleteFailure { id: number; number: string; reason: string }

export function useContractsSelection(options: {
  contracts: { value: Contract[] }
  loadContracts: () => Promise<void>
  showSnack: (text: string, color?: ToastType) => void
}) {
  const { contracts, loadContracts, showSnack } = options

  const selected = ref<number[]>([])
  const clearSelection = () => { selected.value = [] }

  const selectedContracts = computed<Contract[]>(() => {
    const byId = new Map(contracts.value.map(c => [c.id, c]))
    return selected.value.map(id => byId.get(id)).filter((c): c is Contract => !!c)
  })

  // ── Массовое удаление ────────────────────────────────────────────────────
  const bulkDeleteDialog = reactive({
    show: false,
    deleting: false,
    progress: 0,
    total: 0,
    failures: [] as BulkDeleteFailure[],
  })

  const confirmBulkDelete = () => {
    if (!selected.value.length) return
    bulkDeleteDialog.failures = []
    bulkDeleteDialog.progress = 0
    bulkDeleteDialog.total = selected.value.length
    bulkDeleteDialog.show = true
  }

  const doBulkDelete = async () => {
    bulkDeleteDialog.deleting = true
    bulkDeleteDialog.failures = []
    bulkDeleteDialog.progress = 0
    const items = [...selectedContracts.value]
    let ok = 0
    for (const c of items) {
      try {
        await apiFetch(`/contracts/${c.id}`, { method: 'DELETE' })
        ok++
      } catch (e: any) {
        // ПРАВИЛО: причина отказа — из тела ответа сервера, не generic «ошибка».
        const reason = e?.payload?.message || e?.payload?.detail || e?.detail || e?.message || 'неизвестная причина'
        bulkDeleteDialog.failures.push({ id: c.id, number: c.number || String(c.id), reason })
      } finally {
        bulkDeleteDialog.progress++
      }
    }
    bulkDeleteDialog.deleting = false
    selected.value = []
    await loadContracts()
    if (bulkDeleteDialog.failures.length) {
      const list = bulkDeleteDialog.failures.map(f => `№${f.number}: ${f.reason}`).join('; ')
      showSnack(`Удалено ${ok} из ${items.length}; не удалено: ${list}`, 'warning')
    } else {
      showSnack(`Удалено ${ok} из ${items.length}`, 'warning')
      bulkDeleteDialog.show = false
    }
  }

  return {
    selected, selectedContracts, clearSelection,
    bulkDeleteDialog, confirmBulkDelete, doBulkDelete,
  }
}
