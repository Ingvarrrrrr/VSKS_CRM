// Год / субсидии / активная вкладка дашборда + синхронизация с глобальной субсидией и query.
// Перенесено без изменений из DashboardView.vue при разбиении на модули.
import { ref, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useGlobalSubsidy } from '@/composables/useGlobalSubsidy'

export function useDashboardFilters() {
  const { globalSubsidyId } = useGlobalSubsidy()
  const router = useRouter()
  const route = useRoute()

  const selectedYear = ref(new Date().getFullYear())
  const selectedSubsidyIds = ref<number[]>([])
  const activeTab = ref((route.query.tab as string) || 'summary')
  watch(activeTab, (tab) => router.replace({ query: { ...route.query, tab } }))

  // Sync: global → local
  watch(globalSubsidyId, (id: number | null) => {
    if (id !== null) selectedSubsidyIds.value = [id]
    else selectedSubsidyIds.value = []
  }, { immediate: true })

  // Clear selection when year changes to avoid stale IDs from other year
  watch(selectedYear, () => { selectedSubsidyIds.value = [] })

  // Sync: local → global (only single selection)
  watch(selectedSubsidyIds, (ids: number[]) => {
    if (ids.length === 1) globalSubsidyId.value = ids[0]
    else if (ids.length === 0) globalSubsidyId.value = null
  })

  function toggleSubsidyChip(id: number) {
    const idx = selectedSubsidyIds.value.indexOf(id)
    if (idx >= 0) {
      selectedSubsidyIds.value = selectedSubsidyIds.value.filter((x: number) => x !== id)
    } else {
      selectedSubsidyIds.value = [...selectedSubsidyIds.value, id]
    }
  }

  return { selectedYear, selectedSubsidyIds, activeTab, toggleSubsidyChip }
}
