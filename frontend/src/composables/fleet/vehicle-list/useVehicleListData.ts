// useVehicleListData.ts — загрузка реестра ТС (/vehicles) с серверной
// пагинацией/фильтрами/сортировкой, список организаций, выбор строк.
// Дословный перенос из VehicleListView.vue.
import { ref, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch } from '@/api'
import type { OrgItem, VehicleListItem, VehicleListResponse } from './vehicleListTypes'

export function useVehicleListData(options: {
  filters: {
    filterStates: Ref<string[]>
    filterTypes: Ref<string[]>
    filterFuelTypes: Ref<string[]>
    filterOwnerOrgIds: Ref<number[]>
    filterAssignedOrgIds: Ref<number[]>
    filterSearch: Ref<string>
  }
  sortBy: Ref<string | null>
  sortDesc: Ref<boolean>
  onError: (err: any) => void
}) {
  const router = useRouter()
  const { filterStates, filterTypes, filterFuelTypes, filterOwnerOrgIds, filterAssignedOrgIds, filterSearch } = options.filters
  const { sortBy, sortDesc } = options

  const vehicles = ref<VehicleListItem[]>([])
  const total = ref(0)
  const loading = ref(false)
  const page = ref(1)
  const itemsPerPage = ref(25)
  const orgsList = ref<OrgItem[]>([])
  const selectedVehicles = ref<VehicleListItem[]>([])
  const expandedRows = ref<VehicleListItem[]>([])

  async function loadVehicles() {
    loading.value = true
    try {
      const params = new URLSearchParams()
      params.set('limit', String(itemsPerPage.value))
      params.set('offset', String((page.value - 1) * itemsPerPage.value))
      filterStates.value.forEach(s => params.append('state', s))
      filterTypes.value.forEach(t => params.append('type', t))
      filterFuelTypes.value.forEach(f => params.append('fuel_type', f))
      filterOwnerOrgIds.value.forEach(id => params.append('owner_org_id', String(id)))
      filterAssignedOrgIds.value.forEach(id => params.append('assigned_org_id', String(id)))
      if (filterSearch.value.trim()) params.set('q', filterSearch.value.trim())
      if (sortBy.value) { params.set('sort_by', sortBy.value); params.set('sort_desc', String(sortDesc.value)) }

      const data = await apiFetch<VehicleListResponse>(`/vehicles?${params.toString()}`)
      vehicles.value = data.items ?? []
      total.value = data.total ?? 0
    } catch (err: any) {
      options.onError(err)
    } finally {
      loading.value = false
    }
  }

  async function loadOrgs() {
    // /organizations/ требует superadmin. Используем /auth/my-orgs — admin тоже
    // получает свои организации (через UserOrgAccess), superadmin — все.
    // Ответ — массив объектов [{id,name,is_active}], не {items:[]}.
    try {
      const data = await apiFetch<OrgItem[] | { items: OrgItem[] }>('/auth/my-orgs')
      orgsList.value = Array.isArray(data) ? data : (data?.items ?? [])
    } catch {}
  }

  function onTableOptions(opts: { page: number; itemsPerPage: number; sortBy: any[] }) {
    page.value = opts.page
    itemsPerPage.value = opts.itemsPerPage
    if (opts.sortBy?.length) {
      sortBy.value = opts.sortBy[0].key
      sortDesc.value = opts.sortBy[0].order === 'desc'
    } else {
      sortBy.value = null
      sortDesc.value = false
    }
  }

  function onRowClick(_event: Event, row: { item: VehicleListItem }) {
    router.push(`/property/vehicles/${row.item.id}`)
  }

  return {
    vehicles,
    total,
    loading,
    page,
    itemsPerPage,
    orgsList,
    selectedVehicles,
    expandedRows,
    loadVehicles,
    loadOrgs,
    onTableOptions,
    onRowClick,
  }
}
