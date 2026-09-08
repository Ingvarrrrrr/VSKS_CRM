// useContractorsData.ts — список контрагентов: загрузка, серверная пагинация/поиск/фильтр по категории.
// Дословный перенос из ContractorsView.vue.
import { ref, computed } from 'vue'
import { apiFetch } from '@/api'
import type { ToastType } from '@/composables/useToast'
import type { ContractorWithStats } from './contractorsTypes'

export function useContractorsData(showSnack: (text: string, color?: ToastType) => void) {
  const contractors = ref<ContractorWithStats[]>([])
  const contractorsTotal = ref(0)
  const contractorsPage = ref(1)
  const contractorsPerPage = 50
  const loading = ref(false)
  const search = ref('')
  const filterCategory = ref<string | null>(null)

  const allProductCategories = computed(() => {
    const cats = new Set<string>()
    contractors.value.forEach(c => c.product_categories.forEach(p => { if (p !== 'Все') cats.add(p) }))
    return [...cats].sort()
  })

  // Server-side filtering — all filtering done on server
  const filtered = computed(() => contractors.value)

  const totalPages = computed(() => Math.ceil(contractorsTotal.value / contractorsPerPage))

  function clearFilters() {
    search.value = ''
    filterCategory.value = null
    contractorsPage.value = 1
    loadContractors()
  }

  let _searchTimeout: any = null
  function onSearchInput() {
    clearTimeout(_searchTimeout)
    _searchTimeout = setTimeout(() => {
      contractorsPage.value = 1
      loadContractors()
    }, 400)
  }

  function goPage(page: number) {
    contractorsPage.value = page
    loadContractors()
  }

  async function loadContractors() {
    loading.value = true
    try {
      const params = new URLSearchParams()
      params.set('offset', String((contractorsPage.value - 1) * contractorsPerPage))
      params.set('limit', String(contractorsPerPage))
      if (search.value) params.set('search', search.value)
      if (filterCategory.value) params.set('category', filterCategory.value)
      const data = await apiFetch<{ items: ContractorWithStats[]; total: number }>(`/contractors/with-stats?${params}`)
      contractors.value = data.items
      contractorsTotal.value = data.total
    } catch (e: any) {
      showSnack(e.message || 'Ошибка загрузки', 'error')
    } finally {
      loading.value = false
    }
  }

  return {
    contractors,
    contractorsTotal,
    contractorsPage,
    contractorsPerPage,
    loading,
    search,
    filterCategory,
    allProductCategories,
    filtered,
    totalPages,
    clearFilters,
    onSearchInput,
    goPage,
    loadContractors,
  }
}
