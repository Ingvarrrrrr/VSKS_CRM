// useContractorsSelection.ts — выделение строк, одиночное и массовое удаление.
// Дословный перенос из ContractorsView.vue.
import { ref } from 'vue'
import { apiFetch } from '@/api'
import type { ToastType } from '@/composables/useToast'
import type { ContractorWithStats } from './contractorsTypes'

export function useContractorsSelection(options: {
  filtered: () => ContractorWithStats[]
  reload: () => Promise<void>
  showSnack: (text: string, color?: ToastType) => void
}) {
  const { filtered, reload, showSnack } = options

  const saving = ref(false)
  const selectedIds = ref(new Set<number>())

  const deleteDialog = ref(false)
  const deleteTarget = ref<ContractorWithStats | null>(null)

  const bulkDeleteDialog = ref(false)
  const bulkDeleteConfirmCount = ref('')

  function toggleOne(id: number) {
    const s = new Set(selectedIds.value)
    s.has(id) ? s.delete(id) : s.add(id)
    selectedIds.value = s
  }

  function toggleAll(val: boolean | null) {
    selectedIds.value = val ? new Set(filtered().map(c => c.id)) : new Set()
  }

  function confirmBulkDelete() {
    bulkDeleteDialog.value = true
  }

  async function doBulkDelete() {
    saving.value = true
    const ids = [...selectedIds.value]
    try {
      const res = await apiFetch<{ deleted: number; skipped_linked: number; skipped_not_found: number }>('/contractors/bulk', {
        method: 'DELETE',
        body: { ids } as any,
      })
      selectedIds.value = new Set()
      bulkDeleteDialog.value = false
      bulkDeleteConfirmCount.value = ''
      let msg = `Удалено: ${res.deleted}`
      if (res.skipped_linked) msg += `, пропущено (есть закупки): ${res.skipped_linked}`
      if (res.skipped_not_found) msg += `, не найдено: ${res.skipped_not_found}`
      showSnack(msg, res.skipped_linked ? 'warning' : 'success')
      await reload()
    } catch (e: any) {
      showSnack(e.message || 'Ошибка удаления', 'error')
    } finally {
      saving.value = false
    }
  }

  function confirmDelete(c: ContractorWithStats) {
    deleteTarget.value = c
    deleteDialog.value = true
  }

  async function doDelete() {
    if (!deleteTarget.value) return
    saving.value = true
    try {
      await apiFetch(`/contractors/${deleteTarget.value.id}`, { method: 'DELETE' })
      deleteDialog.value = false
      showSnack('Контрагент удалён', 'warning')
      await reload()
    } catch (e: any) {
      showSnack(e.message || 'Ошибка удаления', 'error')
    } finally {
      saving.value = false
    }
  }

  return {
    saving,
    selectedIds,
    deleteDialog,
    deleteTarget,
    bulkDeleteDialog,
    bulkDeleteConfirmCount,
    toggleOne,
    toggleAll,
    confirmBulkDelete,
    doBulkDelete,
    confirmDelete,
    doDelete,
  }
}
