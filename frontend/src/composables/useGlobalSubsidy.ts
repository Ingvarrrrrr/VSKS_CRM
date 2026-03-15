import { ref, watch } from 'vue'

const stored = localStorage.getItem('global_subsidy_id')
const globalSubsidyId = ref<number | null>(stored ? Number(stored) : null)

watch(globalSubsidyId, (val) => {
  if (val) localStorage.setItem('global_subsidy_id', String(val))
  else localStorage.removeItem('global_subsidy_id')
})

export function useGlobalSubsidy() {
  return { globalSubsidyId }
}
