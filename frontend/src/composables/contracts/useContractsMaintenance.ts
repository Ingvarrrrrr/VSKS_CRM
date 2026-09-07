// useContractsMaintenance.ts — обслуживающие операции реестра: поиск и
// объединение дублей, миграция из закупок, массовое обогащение полей,
// удаление записи. Дословный перенос из ContractsView.vue.
import { reactive, ref, watch } from 'vue'
import { apiFetch } from '@/api'
import type { ToastType } from '@/composables/useToast'
import type { Contract } from './contractsTypes'

export function useContractsMaintenance(options: {
  contracts: { value: Contract[] }
  loadContracts: () => Promise<void>
  showSnack: (text: string, color?: ToastType) => void
}) {
  const { contracts, loadContracts, showSnack } = options

  // ── Duplicates ─────────────────────────────────────────────────────────────
  const dupDialog = ref(false)
  const dupLoading = ref(false)
  const duplicateGroups = ref<any[][]>([])

  async function checkDuplicates() {
    dupLoading.value = true
    try {
      // Group contracts by number+contractor_id+subsidy_id
      const groups = new Map<string, any[]>()
      for (const c of contracts.value) {
        const key = `${c.number}|${c.contractor_id || ''}|${c.subsidy_id || ''}`
        if (!groups.has(key)) groups.set(key, [])
        groups.get(key)!.push(c)
      }
      // Filter groups with >1 contract
      const dups: any[][] = []
      for (const group of groups.values()) {
        if (group.length > 1) {
          // Count purchases per contract
          for (const c of group) {
            try {
              const p = await apiFetch<any[]>(`/purchases/by-contract/${c.id}`)
              c._purchaseCount = p.length
            } catch { c._purchaseCount = 0 }
          }
          dups.push(group)
        }
      }
      duplicateGroups.value = dups
      dupDialog.value = true
    } finally {
      dupLoading.value = false
    }
  }

  async function mergeContract(sourceId: number, targetId: number) {
    if (!confirm(`Объединить договор #${sourceId} в #${targetId}? Закупки будут перепривязаны, #${sourceId} удалён.`)) return
    try {
      await apiFetch(`/contracts/${sourceId}/merge/${targetId}`, { method: 'POST' })
      showSnack('Договоры объединены')
      dupDialog.value = false
      await loadContracts()
    } catch (e: any) {
      showSnack(e.message || 'Ошибка объединения', 'error')
    }
  }

  // ── Migration ──────────────────────────────────────────────────────────────
  const migrateDialog = ref(false)
  const migrating = ref(false)
  const migrateResult = ref<{ created: number; skipped: number } | null>(null)

  watch(migrateDialog, (v) => { if (!v) migrateResult.value = null })

  const doMigrate = async () => {
    migrating.value = true
    try {
      const res = await apiFetch<{ created: number; skipped: number }>('/contracts/migrate-from-purchases', { method: 'POST' })
      migrateResult.value = res
      if (res.created > 0) await loadContracts()
      showSnack(`Создано: ${res.created}`)
    } catch (e: any) {
      showSnack(e?.detail || 'Ошибка миграции', 'error')
    } finally {
      migrating.value = false
    }
  }

  // ── Bulk enrich ────────────────────────────────────────────────────────────
  const enrichDialog = ref(false)
  const enriching = ref(false)
  const enrichResult = ref<{
    created: number
    scanned_purchases: number
    enriched_existing: number
    scanned_contracts: number
    relinked_orphans?: number
    purchases_linked?: number
  } | null>(null)

  watch(enrichDialog, (v) => { if (!v) enrichResult.value = null })

  const doEnrich = async () => {
    enriching.value = true
    try {
      const res = await apiFetch<{
        created: number
        scanned_purchases: number
        enriched_existing: number
        scanned_contracts: number
        relinked_orphans?: number
        purchases_linked?: number
      }>('/contracts/bulk-enrich-from-purchases', { method: 'POST' })
      enrichResult.value = res
      if (res.enriched_existing > 0 || res.created > 0) {
        await loadContracts()
      }
      showSnack(`Обогащено: ${res.enriched_existing}, создано: ${res.created}, связей восстановлено: ${res.relinked_orphans || 0}, закупок привязано: ${res.purchases_linked || 0}`)
    } catch (e: any) {
      showSnack(e?.detail || e?.message || 'Ошибка обогащения', 'error')
    } finally {
      enriching.value = false
    }
  }

  // ── Delete ─────────────────────────────────────────────────────────────────
  const deleteDialog = reactive({ show: false, deleting: false, item: null as Contract | null })
  const confirmDelete = (c: Contract) => { deleteDialog.item = c; deleteDialog.show = true }
  const doDelete = async () => {
    if (!deleteDialog.item) return
    deleteDialog.deleting = true
    try {
      await apiFetch(`/contracts/${deleteDialog.item.id}`, { method: 'DELETE' })
      showSnack('Удалено', 'warning')
      deleteDialog.show = false
      await loadContracts()
    } catch (e: any) {
      showSnack(e?.detail || 'Ошибка удаления', 'error')
    } finally {
      deleteDialog.deleting = false
    }
  }

  return {
    dupDialog, dupLoading, duplicateGroups, checkDuplicates, mergeContract,
    migrateDialog, migrating, migrateResult, doMigrate,
    enrichDialog, enriching, enrichResult, doEnrich,
    deleteDialog, confirmDelete, doDelete,
  }
}
