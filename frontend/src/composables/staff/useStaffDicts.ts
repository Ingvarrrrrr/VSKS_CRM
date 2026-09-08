// useStaffDicts.ts — справочники «Отдел»/«Должность» по организации.
// Дословный перенос из StaffView.vue.
import { ref } from 'vue'
import { apiFetch } from '@/api'

export function useStaffDicts() {
  const knownDepartments = ref<string[]>([])
  const knownPositions = ref<string[]>([])
  // Per-org dict cache: orgId → { departments, positions }
  const dictsCache = ref<Record<number, { departments: string[]; positions: string[] }>>({})

  async function loadDicts(orgId?: number | null) {
    const suffix = orgId ? `?org_id=${orgId}` : ''
    if (orgId && dictsCache.value[orgId]) return // already cached
    try {
      const [depts, positions] = await Promise.all([
        apiFetch<string[]>(`/users/dictionaries/departments${suffix}`),
        apiFetch<string[]>(`/users/dictionaries/positions${suffix}`),
      ])
      if (orgId) {
        dictsCache.value[orgId] = { departments: depts, positions: positions }
      } else {
        knownDepartments.value = depts
        knownPositions.value = positions
      }
    } catch {}
  }

  function getDepartmentsForOrg(orgId?: number | null): string[] {
    // Строго по орге: без орги и до загрузки кеша список пуст —
    // иначе в диалоге показывались отделы ВСЕХ организаций.
    if (!orgId) return []
    return dictsCache.value[orgId]?.departments ?? []
  }

  function getPositionsForOrg(orgId?: number | null): string[] {
    if (!orgId) return knownPositions.value
    return dictsCache.value[orgId]?.positions ?? knownPositions.value
  }

  return {
    knownDepartments, knownPositions, dictsCache,
    loadDicts, getDepartmentsForOrg, getPositionsForOrg,
  }
}
