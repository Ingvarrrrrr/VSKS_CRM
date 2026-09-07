// useOrdersFilters.ts — состояние фильтров реестра закупок (OrdersFilterBar.vue),
// query-синхронизация (?status=, ?subsidy_id=, ?wish_id=, ?method=, ?overdue=,
// ?due_soon=, ?feo_category_id=, ?link_task=) и localStorage-пресеты. Дословный
// перенос из OrdersView.vue, без изменения поведения.
import { reactive, ref, watch } from 'vue'
import type { Ref } from 'vue'
import type { RouteLocationNormalizedLoaded, Router } from 'vue-router'
import { apiFetch } from '@/api'
import type { FilterPreset } from './ordersTypes'

export interface OrdersFiltersState {
  status: string | null
  subsidyId: number | null
  feoCategoryId: number | null
  feoCategoryName: string
  feoCategoryIds: Set<number>
  wishId: number | null
  method: string
  overdue: boolean
  dueSoon: boolean
  types: string[]
  contractorIds: number[]
  product: string
  search: string
  onlyUnseen: boolean
  periodFrom: string
  periodTo: string
}

const FILTER_PRESETS_KEY = 'orders_filter_presets'

export function useOrdersFilters(options: {
  route: RouteLocationNormalizedLoaded
  router: Router
  globalSubsidyId: Ref<number | null>
  showSnack: (text: string, color?: 'success' | 'error' | 'warning' | 'info') => void
}) {
  const { route, router, globalSubsidyId, showSnack } = options

  const filters = reactive<OrdersFiltersState>({
    status: null,
    subsidyId: null,
    feoCategoryId: null,
    feoCategoryName: '',
    feoCategoryIds: new Set<number>(),
    wishId: null,
    method: '',
    overdue: false,
    dueSoon: false,
    types: [],
    contractorIds: [],
    product: '',
    search: '',
    onlyUnseen: false,
    periodFrom: '',
    periodTo: '',
  })

  // ── Link task mode (from ?link_task=ID) ──
  const linkTaskId = ref<number | null>(null)

  async function doLinkTask(purchaseId: number) {
    if (!linkTaskId.value) return
    try {
      await apiFetch(`/tasks/${linkTaskId.value}`, {
        method: 'PATCH', body: JSON.stringify({ purchase_id: purchaseId }),
      })
      const tid = linkTaskId.value
      linkTaskId.value = null
      router.replace({ path: '/my-tasks', query: { task: String(tid) } })
    } catch (e: any) {
      alert(e?.detail || 'Ошибка привязки')
    }
  }

  // ---------------------------------------------------------------------------
  // Saved filter presets
  // ---------------------------------------------------------------------------
  const savedFilterPresets = ref<FilterPreset[]>([])
  const filterPresetDialog = reactive({ show: false, name: '' })

  function loadFilterPresets() {
    try { savedFilterPresets.value = JSON.parse(localStorage.getItem(FILTER_PRESETS_KEY) || '[]') } catch {}
  }
  function saveFilterPreset() {
    filterPresetDialog.name = ''
    filterPresetDialog.show = true
  }
  function confirmSaveFilterPreset() {
    const name = filterPresetDialog.name.trim()
    if (!name) return
    const preset: FilterPreset = {
      name,
      subsidyId: filters.subsidyId,
      status: filters.status as string,
      search: filters.search,
      types: [...filters.types],
      contractorIds: [...filters.contractorIds],
    }
    const existing = savedFilterPresets.value.filter(p => p.name !== name)
    savedFilterPresets.value = [...existing, preset]
    localStorage.setItem(FILTER_PRESETS_KEY, JSON.stringify(savedFilterPresets.value))
    filterPresetDialog.show = false
    showSnack('Пресет сохранён')
  }
  function applyFilterPreset(p: FilterPreset) {
    filters.subsidyId = p.subsidyId
    filters.status = p.status
    filters.search = p.search
    filters.types = p.types ?? []
    filters.contractorIds = p.contractorIds ?? []
  }
  function removeFilterPreset(name: string) {
    savedFilterPresets.value = savedFilterPresets.value.filter(p => p.name !== name)
    localStorage.setItem(FILTER_PRESETS_KEY, JSON.stringify(savedFilterPresets.value))
  }

  // Bidirectional sync with global subsidy
  watch(() => filters.subsidyId, (id: number | null) => { globalSubsidyId.value = id })
  watch(globalSubsidyId, (id: number | null) => { filters.subsidyId = id })

  // Query-параметры при монтировании: применяются в OrdersView.onMounted, после
  // подгрузки списка закупок (feo_category_id ищет имя категории по orders как
  // fallback, если /feo-categories/{id}/subtree недоступен).
  function applyFiltersFromQuery(findFeoCategoryName: () => void) {
    if (route.query.link_task) {
      linkTaskId.value = Number(route.query.link_task)
    }
    const qSub = route.query.subsidy_id
    if (qSub) {
      filters.subsidyId = Number(qSub)
      globalSubsidyId.value = Number(qSub)
    } else if (globalSubsidyId.value) {
      filters.subsidyId = globalSubsidyId.value
    }
    const qStatus = route.query.status
    if (qStatus && typeof qStatus === 'string') filters.status = qStatus
    if (route.query.wish_id) filters.wishId = Number(route.query.wish_id)
    if (route.query.method)   filters.method  = route.query.method as string
    if (route.query.overdue)  filters.overdue  = true
    if (route.query.due_soon) filters.dueSoon  = true
    const qFeo = route.query.feo_category_id
    if (qFeo) {
      filters.feoCategoryId = Number(qFeo)
      filters.feoCategoryName = `ФЭО #${qFeo}`
      // Имя категории + id всего поддерева (закупки часто висят на дочерних)
      apiFetch<{ id: number; name: string; ids: number[] }>(`/feo-categories/${qFeo}/subtree`)
        .then(res => {
          filters.feoCategoryName = res.name
          filters.feoCategoryIds = new Set(res.ids)
        })
        .catch(() => {
          findFeoCategoryName()
        })
    }
  }

  return {
    filters,
    linkTaskId,
    doLinkTask,
    savedFilterPresets,
    filterPresetDialog,
    loadFilterPresets,
    saveFilterPreset,
    confirmSaveFilterPreset,
    applyFilterPreset,
    removeFilterPreset,
    applyFiltersFromQuery,
  }
}
