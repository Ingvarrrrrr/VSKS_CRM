// useVehicleListFilters.ts — панель фильтров реестра ТС + сохранённые
// пресеты фильтров (localStorage). Дословный перенос из VehicleListView.vue.
import { ref, computed, reactive } from 'vue'
import type { FilterPreset } from './vehicleListTypes'

export function useVehicleListFilters(options: {
  /** Сброс фильтров column-header-menu (ColumnHeaderMenu), вызывается вместе с clearAllFilters(). */
  clearColumnFilters: () => void
}) {
  const filterStates = ref<string[]>([])
  const filterTypes = ref<string[]>([])
  const filterFuelTypes = ref<string[]>([])
  const filterOwnerOrgIds = ref<number[]>([])
  const filterAssignedOrgIds = ref<number[]>([])
  const filterSearch = ref('')

  const activeFiltersCount = computed(() => {
    let cnt = 0
    if (filterStates.value.length) cnt++
    if (filterTypes.value.length) cnt++
    if (filterFuelTypes.value.length) cnt++
    if (filterOwnerOrgIds.value.length) cnt++
    if (filterAssignedOrgIds.value.length) cnt++
    if (filterSearch.value.trim()) cnt++
    return cnt
  })

  function clearAllFilters() {
    filterStates.value = []
    filterTypes.value = []
    filterFuelTypes.value = []
    filterOwnerOrgIds.value = []
    filterAssignedOrgIds.value = []
    filterSearch.value = ''
    options.clearColumnFilters()
  }

  // ─────────────── Filter presets ───────────────

  const PRESETS_KEY = 'vehicles_list_presets'

  const savedFilterPresets = ref<FilterPreset[]>([])

  function loadSavedPresets() {
    try {
      const raw = localStorage.getItem(PRESETS_KEY)
      if (raw) savedFilterPresets.value = JSON.parse(raw)
    } catch {}
  }

  const filterPresetDialog = reactive({ show: false, name: '' })

  function saveFilterPreset() {
    filterPresetDialog.name = ''
    filterPresetDialog.show = true
  }

  function confirmSaveFilterPreset() {
    const presetName = filterPresetDialog.name.trim()
    if (!presetName) return
    const newPreset: FilterPreset = {
      name: presetName,
      states: [...filterStates.value],
      types: [...filterTypes.value],
      fuelTypes: [...filterFuelTypes.value],
      ownerOrgIds: [...filterOwnerOrgIds.value],
      assignedOrgIds: [...filterAssignedOrgIds.value],
      search: filterSearch.value,
    }
    const existing = savedFilterPresets.value.filter(p => p.name !== presetName)
    savedFilterPresets.value = [...existing, newPreset]
    try { localStorage.setItem(PRESETS_KEY, JSON.stringify(savedFilterPresets.value)) } catch {}
    filterPresetDialog.show = false
  }

  function applyFilterPreset(preset: FilterPreset) {
    filterStates.value = preset.states ?? []
    filterTypes.value = preset.types ?? []
    filterFuelTypes.value = preset.fuelTypes ?? []
    filterOwnerOrgIds.value = preset.ownerOrgIds ?? []
    filterAssignedOrgIds.value = preset.assignedOrgIds ?? []
    filterSearch.value = preset.search ?? ''
  }

  function removeFilterPreset(name: string) {
    savedFilterPresets.value = savedFilterPresets.value.filter(p => p.name !== name)
    try { localStorage.setItem(PRESETS_KEY, JSON.stringify(savedFilterPresets.value)) } catch {}
  }

  return {
    filterStates,
    filterTypes,
    filterFuelTypes,
    filterOwnerOrgIds,
    filterAssignedOrgIds,
    filterSearch,
    activeFiltersCount,
    clearAllFilters,
    savedFilterPresets,
    loadSavedPresets,
    filterPresetDialog,
    saveFilterPreset,
    confirmSaveFilterPreset,
    applyFilterPreset,
    removeFilterPreset,
  }
}
