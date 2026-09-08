// usePaymentsFilters.ts — состояние панели фильтров реестра платежей
// (серверные + клиентские: поиск, субсидия) и список субсидий для селекта.
// Дословный перенос из PaymentRegistryView.vue.
import { ref } from 'vue'
import { apiFetch } from '@/api'

export interface SubsidyItem { id: number; name: string }

export const statusOptions = [
  { label: 'ИСПОЛНЕН', value: 'ИСПОЛНЕН' },
  { label: 'АННУЛИРОВАН', value: 'АННУЛИРОВАН' },
  { label: 'Прочие', value: 'OTHER' },
]
export const yesNoOptions = [
  { label: 'Только сматченные', value: 'true' },
  { label: 'Только не сматченные', value: 'false' },
]
// Этап 7в: «свободные / разнесённые» — разнесение через новое групповое
// сопоставление (app/services/payment_lookup.py::attach), не старая matched_*.
export const dispositionOptions = [
  { label: 'Свободные (не разнесены)', value: 'free' },
  { label: 'Разнесённые', value: 'attached' },
]

export function usePaymentsFilters() {
  const fDateFrom = ref<string>('')
  const fDateTo = ref<string>('')
  const fStatus = ref<string | null>(null)
  const fMatched = ref<string | null>(null)
  const fConfirmed = ref<string | null>(null)
  const fInn = ref<string>('')
  const fDisposition = ref<string | null>(null)

  // ── Global search + subsidy filter ─────────────────────────────────────
  const searchQuery = ref('')
  const filterSubsidyId = ref<number | null>(null)

  const subsidiesList = ref<SubsidyItem[]>([])

  async function loadSubsidies() {
    try {
      const data = await apiFetch<any[]>('/subsidies/')
      subsidiesList.value = (data || []).map((s: any) => ({ id: s.id, name: s.name }))
    } catch {}
  }

  return {
    fDateFrom, fDateTo, fStatus, fMatched, fConfirmed, fInn, fDisposition,
    searchQuery, filterSubsidyId,
    subsidiesList, loadSubsidies,
  }
}
