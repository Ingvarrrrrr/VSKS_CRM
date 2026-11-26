// useWishFilters.ts — состояние фильтров панели «Заявки» (WishFilterPanel.vue) +
// buildFilterParams, вынесены из WishesView.vue без изменения поведения.
// Дословный перенос: watchers на debounce и на filterAccountId — те же 300мс/сброс.
import { reactive, ref, watch } from 'vue'
import type { Ref } from 'vue'

export interface WishFiltersState {
  subsidyIds: number[]
  creatorIds: number[]
  assignedToIds: number[]
  wishTypes: string[]
  createdFrom: string
  createdTo: string
  deadlineFrom: string
  deadlineTo: string
  // SaaS-фильтры: аккаунты (корневая орг + дочерние) и конкретные организации
  accountIds: number[]
  orgIds: number[]
}

export const WISH_TYPE_OPTIONS = [
  { value: 'regular', title: 'Обычная заявка' },
  { value: 'advance_report', title: 'Авансовый отчёт' },
]

export function useWishFilters(options: {
  allOrgs: Ref<{ id: number; name: string; root_org_id?: number | null; parent_org_id?: number | null }[]>
  onChange: () => void
}) {
  const { allOrgs, onChange } = options

  const filters = reactive<WishFiltersState>({
    subsidyIds: [],
    creatorIds: [],
    assignedToIds: [],
    wishTypes: [],
    createdFrom: '',
    createdTo: '',
    deadlineFrom: '',
    deadlineTo: '',
    accountIds: [],
    orgIds: [],
  })

  const accountOptions = ref<typeof allOrgs.value>([])
  const orgOptionsFiltered = ref<typeof allOrgs.value>([])
  function recomputeOrgOptions() {
    accountOptions.value = allOrgs.value.filter(o => !o.root_org_id && !o.parent_org_id)
    const accs = filters.accountIds
    orgOptionsFiltered.value = accs.length
      ? allOrgs.value.filter(o =>
          accs.includes(o.id)
          || (o.root_org_id != null && accs.includes(o.root_org_id))
          || (o.parent_org_id != null && accs.includes(o.parent_org_id))
        )
      : allOrgs.value
  }
  watch(() => allOrgs.value, recomputeOrgOptions, { immediate: true })
  watch(() => filters.accountIds.join(','), () => {
    recomputeOrgOptions()
    if (filters.orgIds.length) {
      const allowed = new Set(orgOptionsFiltered.value.map(o => o.id))
      const kept = filters.orgIds.filter(id => allowed.has(id))
      if (kept.length !== filters.orgIds.length) filters.orgIds = kept
    }
  })

  function buildFilterParams(extra: Record<string, any> = {}) {
    const params = new URLSearchParams()
    if (filters.accountIds.length) params.set('account_org_ids', filters.accountIds.join(','))
    if (filters.orgIds.length) params.set('org_ids', filters.orgIds.join(','))
    if (filters.subsidyIds.length) params.set('subsidy_ids', filters.subsidyIds.join(','))
    if (filters.creatorIds.length) params.set('creator_ids', filters.creatorIds.join(','))
    if (filters.assignedToIds.length) params.set('assigned_to_ids', filters.assignedToIds.join(','))
    if (filters.wishTypes.length) params.set('wish_types', filters.wishTypes.join(','))
    if (filters.createdFrom) params.set('created_from', filters.createdFrom)
    if (filters.createdTo) params.set('created_to', filters.createdTo)
    if (filters.deadlineFrom) params.set('deadline_from', filters.deadlineFrom)
    if (filters.deadlineTo) params.set('deadline_to', filters.deadlineTo)
    for (const [k, v] of Object.entries(extra)) {
      if (v !== undefined && v !== null && v !== '') params.set(k, String(v))
    }
    const qs = params.toString()
    return qs ? `?${qs}` : ''
  }

  function resetFilters() {
    filters.accountIds = []
    filters.orgIds = []
    filters.subsidyIds = []
    filters.creatorIds = []
    filters.assignedToIds = []
    filters.wishTypes = []
    filters.createdFrom = ''
    filters.createdTo = ''
    filters.deadlineFrom = ''
    filters.deadlineTo = ''
  }

  // Debounced filter watcher
  let filterTimer: any = null
  watch(
    () => [
      filters.accountIds.join(','), filters.orgIds.join(','), filters.subsidyIds.join(','),
      filters.creatorIds.join(','), filters.assignedToIds.join(','), filters.wishTypes.join(','),
      filters.createdFrom, filters.createdTo, filters.deadlineFrom, filters.deadlineTo,
    ],
    () => {
      clearTimeout(filterTimer)
      filterTimer = setTimeout(() => onChange(), 300)
    },
  )

  return {
    filters,
    accountOptions,
    orgOptionsFiltered,
    buildFilterParams,
    resetFilters,
  }
}
