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
  { i: 'kpi-vehicles',  x: 0,  y: 0,  w: 3,  h: 4,  minW: 2, minH: 3 },
  { i: 'kpi-fuel',      x: 3,  y: 0,  w: 3,  h: 4,  minW: 2, minH: 3 },
  { i: 'kpi-repairs',   x: 6,  y: 0,  w: 3,  h: 4,  minW: 2, minH: 3 },
  { i: 'kpi-mileage',   x: 9,  y: 0,  w: 3,  h: 4,  minW: 2, minH: 3 },
  { i: 'canister',      x: 0,  y: 4,  w: 3,  h: 10, minW: 2, minH: 8 },
  { i: 'in_repair',     x: 3,  y: 4,  w: 4,  h: 10, minW: 3, minH: 6 },
  { i: 'to_warning',    x: 7,  y: 4,  w: 5,  h: 10, minW: 3, minH: 6 },
  { i: 'bar_org',       x: 0,  y: 14, w: 6,  h: 9,  minW: 4, minH: 6 },
  { i: 'donut_state',   x: 6,  y: 14, w: 3,  h: 9,  minW: 2, minH: 6 },
  { i: 'line_fuel',     x: 9,  y: 14, w: 3,  h: 9,  minW: 2, minH: 6 },
  { i: 'top10_table',   x: 0,  y: 23, w: 12, h: 10, minW: 6, minH: 6 },
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
    if (Array.isArray(parsed) && parsed.length > 0) return parsed
    return null
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

  // Ensure all default widgets exist in loaded layout
  const currentIds = new Set(layout.value.map(l => l.i))
  for (const def of DEFAULT_LAYOUT) {
    if (!currentIds.has(def.i)) {
      layout.value.push(structuredClone(def))
    }
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
    DEFAULT_LAYOUT,
  }
}
