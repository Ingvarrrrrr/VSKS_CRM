import { ref } from 'vue'

export interface LayoutItem {
  x: number
  y: number
  w: number
  h: number
  i: string
  minW?: number
  minH?: number
}

const DEFAULT_LAYOUT: LayoutItem[] = [
  { i: 'kpi-vehicles',   x: 0,  y: 0,  w: 3,  h: 4,  minW: 2, minH: 3 },
  { i: 'kpi-fuel',       x: 3,  y: 0,  w: 3,  h: 4,  minW: 2, minH: 3 },
  { i: 'kpi-repairs',    x: 6,  y: 0,  w: 3,  h: 4,  minW: 2, minH: 3 },
  { i: 'kpi-mileage',    x: 9,  y: 0,  w: 3,  h: 4,  minW: 2, minH: 3 },
  { i: 'canister',       x: 0,  y: 4,  w: 3,  h: 10, minW: 2, minH: 8 },
  { i: 'in_repair',      x: 3,  y: 4,  w: 4,  h: 10, minW: 3, minH: 6 },
  { i: 'to_warning',     x: 7,  y: 4,  w: 5,  h: 10, minW: 3, minH: 6 },
  { i: 'bar_org',        x: 0,  y: 14, w: 6,  h: 9,  minW: 4, minH: 6 },
  { i: 'donut_state',    x: 6,  y: 14, w: 3,  h: 9,  minW: 2, minH: 6 },
  { i: 'line_fuel',      x: 9,  y: 14, w: 3,  h: 9,  minW: 2, minH: 6 },
  { i: 'top10_table',    x: 0,  y: 23, w: 12, h: 10, minW: 6, minH: 6 },
  { i: 'all_vehicles',   x: 0,  y: 33, w: 12, h: 8,  minW: 6, minH: 6 },
]

function getStorageKey(): string {
  const userId = localStorage.getItem('user_id') || 'default'
  return `vehicle_dashboard_layout_u${userId}`
}

function loadLayout(): LayoutItem[] | null {
  try {
    const raw = localStorage.getItem(getStorageKey())
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed) || parsed.length === 0) return null
    // Reset if any DEFAULT widget ID is missing (cache stale after feature evolution)
    const cachedIds = new Set(parsed.map((l: LayoutItem) => l.i))
    const allPresent = DEFAULT_LAYOUT.every(d => cachedIds.has(d.i))
    if (!allPresent) return null
    return parsed
  } catch {
    return null
  }
}

function saveLayoutToStorage(layout: LayoutItem[]) {
  try {
    localStorage.setItem(getStorageKey(), JSON.stringify(layout))
  } catch {}
}

export function useVehicleDashboardLayout() {
  const isEditing = ref(false)
  const layout = ref<LayoutItem[]>(loadLayout() || structuredClone(DEFAULT_LAYOUT))

  function getLayoutItem(id: string): LayoutItem {
    return layout.value.find(l => l.i === id) || { i: id, x: 0, y: 100, w: 6, h: 4 }
  }

  function resetLayout() {
    layout.value = structuredClone(DEFAULT_LAYOUT)
    localStorage.removeItem(getStorageKey())
  }

  function onLayoutUpdated(newLayout: LayoutItem[]) {
    layout.value = newLayout
    saveLayoutToStorage(newLayout)
  }

  function toggleEditing() {
    isEditing.value = !isEditing.value
  }

  return {
    layout,
    isEditing,
    toggleEditing,
    resetLayout,
    onLayoutUpdated,
    getLayoutItem,
    DEFAULT_LAYOUT,
  }
}
