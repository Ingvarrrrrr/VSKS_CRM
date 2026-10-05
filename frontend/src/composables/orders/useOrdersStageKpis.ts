// useOrdersStageKpis.ts — КПИ-карточки этапов на вкладке «Закупки» (решение
// владельца 05.10.2026): «Заключён договор / Заказано / Поставлено /
// Оплачено», накопительно, ТОТ ЖЕ бэк-источник, что карточка субсидии
// (SubsidyKpiCards.vue) и дашборд — GET /dashboard/charts?scope=managed →
// subsidy_stats[] (total_contracts/total_ordered/total_delivered/
// paid_declared), ПРАВИЛО №6: здесь только суммирование готовых чисел по
// видимым (не sandbox) субсидиям, никакой второй формулы этапа.
import { ref, computed, type Ref } from 'vue'
import { apiFetch } from '@/api'

interface SubsidyStatRow {
  id: number
  is_sandbox?: boolean
  total_contracts?: number
  total_ordered?: number
  total_delivered?: number
  paid_declared?: number
  total_paid?: number
}

export function useOrdersStageKpis(subsidyId: Ref<number | null>) {
  const rows = ref<SubsidyStatRow[]>([])
  const loading = ref(false)
  const loaded = ref(false)

  async function load() {
    loading.value = true
    try {
      const data = await apiFetch<any>('/dashboard/charts?scope=managed')
      rows.value = (data?.subsidy_stats || []) as SubsidyStatRow[]
      loaded.value = true
    } catch {
      // КПИ — вспомогательная подсказка, не критичные данные реестра
      // (lesson feedback_no_generic_error_snackbar — тут достаточно молча
      // не показать карточки, реестр закупок работает независимо от них).
    } finally {
      loading.value = false
    }
  }

  const scopedRows = computed(() => {
    const visible = rows.value.filter(r => !r.is_sandbox)
    if (subsidyId.value) return visible.filter(r => r.id === subsidyId.value)
    return visible
  })

  const contracts = computed(() => scopedRows.value.reduce((s, r) => s + (r.total_contracts || 0), 0))
  const ordered   = computed(() => scopedRows.value.reduce((s, r) => s + (r.total_ordered || 0), 0))
  const delivered = computed(() => scopedRows.value.reduce((s, r) => s + (r.total_delivered || 0), 0))
  const paid      = computed(() => scopedRows.value.reduce((s, r) => s + (r.paid_declared ?? r.total_paid ?? 0), 0))

  return { load, loading, loaded, contracts, ordered, delivered, paid }
}
