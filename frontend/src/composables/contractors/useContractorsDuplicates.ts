// useContractorsDuplicates.ts — поиск дублей контрагентов по ИНН (по всей базе).
// Дословный перенос из ContractorsView.vue.
import { ref } from 'vue'
import { apiFetch } from '@/api'

export interface DuplicateGroup {
  inn: string
  count: number
  contractors: {
    id: number
    name: string
    full_name?: string
    kpp?: string
    address?: string
  }[]
}

export interface DuplicatesData {
  groups: DuplicateGroup[]
  total_groups: number
  total_extra: number
}

export function useContractorsDuplicates() {
  const showDuplicatesDialog = ref(false)
  const duplicatesLoading = ref(false)
  const duplicatesError = ref('')
  const duplicatesData = ref<DuplicatesData | null>(null)

  async function openDuplicatesDialog() {
    showDuplicatesDialog.value = true
    duplicatesData.value = null
    duplicatesError.value = ''
    duplicatesLoading.value = true
    try {
      duplicatesData.value = await apiFetch('/contractors/duplicates-by-inn')
    } catch (e: any) {
      duplicatesError.value = e?.payload?.message || e?.message || 'Ошибка загрузки дублей'
    } finally {
      duplicatesLoading.value = false
    }
  }

  return {
    showDuplicatesDialog,
    duplicatesLoading,
    duplicatesError,
    duplicatesData,
    openDuplicatesDialog,
  }
}
