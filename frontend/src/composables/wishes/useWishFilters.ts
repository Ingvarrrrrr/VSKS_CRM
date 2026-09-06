// useWishFilters.ts — состояние фильтров панели «Заявки» (WishFilterPanel.vue) +
// buildFilterParams, вынесены из WishesView.vue без изменения поведения.
// Дословный перенос: watchers на debounce и на filterAccountId — те же 300мс/сброс.
import { reactive, ref, watch } from 'vue'
import type { Ref } from 'vue'

export interface WishFiltersState {
  subsidyId: number | null
  creatorId: number | null
  assignedToId: number | null
  createdFrom: string
  createdTo: string
  deadlineFrom: string
  deadlineTo: string
  // SaaS-фильтры: аккаунт (корневая орг + дочерние) и конкретная организация
  accountId: number | null
  orgId: number | null
}

export function useWishFilters(options: {
  allOrgs: Ref<{ id: number; name: string; root_org_id?: number | null; parent_org_id?: number | null }[]>
  onChange: () => void
}) {
  const { allOrgs, onChange } = options

  const filters = reactive<WishFiltersState>({
    subsidyId: null,
    creatorId: null,
    assignedToId: null,
    createdFrom: '',
    createdTo: '',
    deadlineFrom: '',
    deadlineTo: '',
    accountId: null,
    orgId: null,
  })

  const accountOptions = ref<typeof allOrgs.value>([])
  const orgOptionsFiltered = ref<typeof allOrgs.value>([])
  function recomputeOrgOptions() {
    accountOptions.value = allOrgs.value.filter(o => !o.root_org_id && !o.parent_org_id)
    const acc = filters.accountId
    orgOptionsFiltered.value = acc
      ? allOrgs.value.filter(o => o.id === acc || o.root_org_id === acc || o.parent_org_id === acc)
      : allOrgs.value
  }
  watch(() => allOrgs.value, recomputeOrgOptions, { immediate: true })
  watch(() => filters.accountId, () => {
    recomputeOrgOptions()
    if (filters.orgId && !orgOptionsFiltered.value.some(o => o.id === filters.orgId)) {
      filters.orgId = null
    }
  })

  function buildFilterParams(extra: Record<string, any> = {}) {
    const params = new URLSearchParams()
    if (filters.accountId) params.set('account_org_id', String(filters.accountId))
    if (filters.orgId) params.set('org_id', String(filters.orgId))
    if (filters.subsidyId) params.set('subsidy_id', String(filters.subsidyId))
    if (filters.creatorId) params.set('creator_id', String(filters.creatorId))
    if (filters.assignedToId) params.set('assigned_to_id', String(filters.assignedToId))
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
    filters.accountId = null
    filters.orgId = null
    filters.subsidyId = null
    filters.creatorId = null
    filters.assignedToId = null
    filters.createdFrom = ''
    filters.createdTo = ''
    filters.deadlineFrom = ''
    filters.deadlineTo = ''
  }

  // Debounced filter watcher
  let filterTimer: any = null
  watch(
    () => [
      filters.accountId, filters.orgId, filters.subsidyId, filters.creatorId, filters.assignedToId,
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
