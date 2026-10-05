// Вкладка «Выписка» окна сверки (квик-план 2026-10-06, statement-control) —
// отдельный GET, не путать с payment-control: это сырые строки банковской
// выписки ТОЛЬКО этой субсидии (бэкенд фильтрует по номеру соглашения), а
// payment-control — уже агрегированная сверка. Отдельный composable по
// ПРАВИЛУ №5 (useSubsidyPaymentControl.ts и так не маленький).
import { ref } from 'vue'
import { apiFetch } from '@/api'

export interface StatementRowAttachment {
  purchase_id: number
  registry_number: string | null
  sheet_ref: string | null
}

export interface StatementRow {
  id: number
  payment_number: string | null
  payment_date: string | null
  status: string
  payee_name: string | null
  payee_inn: string | null
  amount: number
  purpose_text: string | null
  expense_code: string | null
  expense_name: string | null
  is_procurement: boolean
  attached: StatementRowAttachment[]
  import_file_name: string | null
}

export function useSubsidyStatement() {
  const rows = ref<StatementRow[]>([])
  const loading = ref(false)
  const loadError = ref<string | null>(null)
  let loaded = false

  async function load(subsidyId: number | null | undefined) {
    if (!subsidyId) { rows.value = []; loaded = false; return }
    loading.value = true
    loadError.value = null
    try {
      rows.value = await apiFetch<StatementRow[]>(`/subsidies/${subsidyId}/statement`)
      loaded = true
    } catch (e: any) {
      loadError.value = e?.payload?.message || e?.detail || e?.message || 'Не удалось загрузить выписку'
      rows.value = []
      loaded = false
    } finally {
      loading.value = false
    }
  }

  function isLoaded(): boolean {
    return loaded
  }

  return { rows, loading, loadError, load, isLoaded }
}
