// usePaymentsData.ts — загрузка реестра платежей (/payments/registry),
// клиентские searchedItems/searchedItemsWithRowNum/filteredSum поверх
// серверных фильтров + column-header фильтров/сортировки из
// usePaymentsColumns. Дословный перенос из PaymentRegistryView.vue.
import { computed, ref, type Ref } from 'vue'
import { apiFetch } from '@/api'
import type { BankPayment } from './paymentsTypes'

export function usePaymentsData(options: {
  filters: {
    fDateFrom: Ref<string>
    fDateTo: Ref<string>
    fStatus: Ref<string | null>
    fMatched: Ref<string | null>
    fConfirmed: Ref<string | null>
    fInn: Ref<string>
    fDisposition: Ref<string | null>
  }
  importId: Ref<number | null>
  searchQuery: Ref<string>
  filterSubsidyId: Ref<number | null>
  colConfigState: { value: { filters: Record<string, any> } }
  matchesColumnFilters: (row: any) => boolean
  localSort: Ref<{ key: string; order: 'asc' | 'desc' } | null>
  onError: (message: string) => void
}) {
  const { filters, importId, searchQuery, filterSubsidyId, colConfigState, matchesColumnFilters, localSort, onError } = options

  const payments = ref<BankPayment[]>([])
  const loading = ref(false)
  const totalCount = ref(0)
  const page = ref(1)
  const expanded = ref<number[]>([])

  // Stale parsed detection: записи где parsed_contract_number совпадает с basis_doc_number (номер субсидии)
  const staleParsedDismissed = ref(false)
  const hasStaleParsed = computed(() =>
    !staleParsedDismissed.value &&
    payments.value.some(
      p => p.parsed_contract_number && p.basis_doc_number &&
        p.parsed_contract_number === p.basis_doc_number
    )
  )

  async function loadPayments() {
    loading.value = true
    try {
      const params = new URLSearchParams({ limit: '200' })
      if (filters.fDateFrom.value) params.set('date_from', filters.fDateFrom.value)
      if (filters.fDateTo.value) params.set('date_to', filters.fDateTo.value)
      if (filters.fStatus.value) params.set('status', filters.fStatus.value)
      if (filters.fMatched.value !== null && filters.fMatched.value !== '') params.set('matched', filters.fMatched.value)
      if (filters.fConfirmed.value !== null && filters.fConfirmed.value !== '') params.set('confirmed', filters.fConfirmed.value)
      if (filters.fInn.value) params.set('payee_inn', filters.fInn.value)
      if (filters.fDisposition.value) params.set('disposition', filters.fDisposition.value)
      if (importId.value) params.set('import_id', String(importId.value))

      const data = await apiFetch<any>(`/payments/registry?${params}`)
      const raw: BankPayment[] = Array.isArray(data) ? data : (data as any).items ?? []
      payments.value = raw
      totalCount.value = (data as any).total ?? raw.length
    } catch (e: any) {
      onError('Не удалось загрузить реестр: ' + (e.detail || ''))
    } finally {
      loading.value = false
    }
  }

  function applyFilters() {
    page.value = 1
    loadPayments()
  }

  const searchedItems = computed(() => {
    let items = payments.value as any[]
    if (filterSubsidyId.value) {
      items = items.filter(i => i.matched_subsidy_id === filterSubsidyId.value)
    }
    if (searchQuery.value.trim()) {
      const q = searchQuery.value.toLowerCase()
      items = items.filter((item: any) => {
        const haystack = [
          item.payer_name, item.payer_name_resolved, item.payer_inn,
          item.payee_name, item.payee_name_resolved, item.payee_inn,
          item.purpose_text, item.basis_doc_text, item.basis_doc_number,
          item.parsed_contract_number, item.payment_number, item.subsidy_code,
        ].filter(Boolean).join(' ').toLowerCase()
        return haystack.includes(q)
      })
    }
    // column-header filters
    if (colConfigState.value && Object.keys(colConfigState.value.filters).length > 0) {
      items = items.filter(matchesColumnFilters)
    }
    return items
  })

  const searchedItemsWithRowNum = computed(() => {
    // Нумерация по возрастанию id: более раннее (меньший id) = меньший _rownum
    const sorted = [...searchedItems.value].sort((a, b) => (Number(a.id) || 0) - (Number(b.id) || 0))
    const map = new Map<string, number>()
    sorted.forEach((p, idx) => map.set(String(p.id), idx + 1))
    let items = searchedItems.value.map(p => ({ ...p, _rownum: map.get(String(p.id)) ?? '' }))
    // Apply localSort from ColumnHeaderMenu
    if (localSort.value) {
      const { key, order } = localSort.value
      items = [...items].sort((a, b) => {
        const av = a?.[key] ?? null
        const bv = b?.[key] ?? null
        const cmp = String(av ?? '').localeCompare(String(bv ?? ''), 'ru', { numeric: true })
        return order === 'asc' ? cmp : -cmp
      })
    }
    return items
  })

  const filteredSum = computed(() =>
    searchedItems.value.reduce((acc, p) => acc + (p.amount ? Number(p.amount) : 0), 0)
  )

  return {
    payments,
    loading,
    totalCount,
    page,
    expanded,
    staleParsedDismissed,
    hasStaleParsed,
    loadPayments,
    applyFilters,
    searchedItems,
    searchedItemsWithRowNum,
    filteredSum,
  }
}
