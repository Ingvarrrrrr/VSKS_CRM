// usePaymentsReconciliation.ts — сверка платежей vs закупки (27.4-21/22).
// Дословный перенос из PaymentRegistryView.vue.
import { computed, ref, type Ref } from 'vue'
import { apiFetch } from '@/api'

export function usePaymentsReconciliation(options: {
  importId: Ref<number | null>
  error: (msg: string) => void
}) {
  const { importId, error } = options

  const reconciliationDialog = ref(false)
  const reconciliationLoading = ref(false)
  const reconciliation = ref<any>(null)
  const reconciliationFilter = ref('')

  const filteredReconciliationRows = computed(() => {
    const rows = reconciliation.value?.rows || []
    const q = reconciliationFilter.value.trim().toLowerCase()
    if (!q) return rows
    return rows.filter((r: any) =>
      (r.payment_number || '').toLowerCase().includes(q) ||
      (r.registry_payees || []).some((p: string) => p.toLowerCase().includes(q)) ||
      reconciliationStatusLabel(r.status).toLowerCase().includes(q)
    )
  })

  async function openReconciliation() {
    reconciliationDialog.value = true
    reconciliationLoading.value = true
    reconciliation.value = null
    reconciliationFilter.value = ''
    try {
      const url = importId.value
        ? `/payments/reconciliation?import_id=${importId.value}`
        : '/payments/reconciliation'
      reconciliation.value = await apiFetch<any>(url)
    } catch (e: any) {
      error('Ошибка сверки: ' + (e?.payload?.message || e?.message || ''))
    } finally {
      reconciliationLoading.value = false
    }
  }

  function reconciliationRowClass(status: string): string {
    if (status === 'amount_mismatch' || status === 'registry_only') return 'bg-red-lighten-5'
    if (status === 'purchases_only' || status === 'declared_unconfirmed') return 'bg-amber-lighten-5'
    return ''
  }

  function reconciliationStatusColor(status: string): string {
    if (status === 'match') return 'success'
    if (status === 'amount_mismatch') return 'error'
    if (status === 'registry_only') return 'error'
    if (status === 'purchases_only') return 'warning'
    if (status === 'declared_unconfirmed') return 'orange'
    return 'grey'
  }

  function reconciliationStatusLabel(status: string): string {
    const labels: Record<string, string> = {
      match: 'OK',
      amount_mismatch: 'Расхождение сумм',
      registry_only: 'Только в реестре',
      purchases_only: 'Только в закупках',
      declared_unconfirmed: 'Заявлено, не подтверждено',
    }
    return labels[status] || status
  }

  return {
    reconciliationDialog, reconciliationLoading, reconciliation, reconciliationFilter,
    filteredReconciliationRows, openReconciliation,
    reconciliationRowClass, reconciliationStatusColor, reconciliationStatusLabel,
  }
}
