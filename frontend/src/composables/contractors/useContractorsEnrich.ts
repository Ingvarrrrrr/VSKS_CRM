// useContractorsEnrich.ts — массовое обновление реквизитов контрагентов из ЕГРЮЛ.
// Дословный перенос из ContractorsView.vue.
import { ref } from 'vue'
import { apiFetch } from '@/api'

export function useContractorsEnrich(reload: () => Promise<void>) {
  const enrichAllLoading = ref(false)
  const enrichAllResult = ref<{ total: number; updated: number; skipped: number; errors: any[] } | null>(null)

  async function enrichAllFromFns() {
    enrichAllLoading.value = true
    enrichAllResult.value = null
    try {
      const data = await apiFetch<{ total: number; updated: number; skipped: number; errors: any[] }>('/contractors/enrich-all-fns', { method: 'POST' })
      enrichAllResult.value = data
      if (data.updated > 0) reload()
    } catch (e: any) {
      enrichAllResult.value = { total: 0, updated: 0, skipped: 0, errors: [{ error: e.message }] }
    } finally {
      enrichAllLoading.value = false
    }
  }

  return { enrichAllLoading, enrichAllResult, enrichAllFromFns }
}
