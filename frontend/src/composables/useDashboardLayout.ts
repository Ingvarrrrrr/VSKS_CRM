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

// Default layout for Summary tab (12 columns, rowHeight=30px)
const DEFAULT_SUMMARY_LAYOUT: LayoutItem[] = [
  { i: 'kpi',        x: 0, y: 0,  w: 12, h: 8,  minW: 6,  minH: 3 },
  { i: 'donut',      x: 0, y: 8,  w: 4,  h: 11, minW: 3,  minH: 7 },
  { i: 'radial',     x: 4, y: 8,  w: 2,  h: 11, minW: 2,  minH: 7 },
  { i: 'pipeline',   x: 6, y: 8,  w: 6,  h: 11, minW: 4,  minH: 7 },
  { i: 'monthly',    x: 0, y: 19, w: 8,  h: 7,  minW: 4,  minH: 4 },
  { i: 'breakdown',  x: 0, y: 26, w: 8,  h: 8,  minW: 4,  minH: 5 },
  { i: 'purchases',  x: 7, y: 34, w: 5,  h: 10, minW: 3,  minH: 6 },
  { i: 'table',      x: 0, y: 44, w: 12, h: 12, minW: 6,  minH: 6 },
  { i: 'finplan',    x: 0, y: 56, w: 12, h: 12, minW: 6,  minH: 8 },
]

function getStorageKey(): string {
  const userId = localStorage.getItem('user_id') || 'default'
  return `dashboard_layout_v2_${userId}`
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

export function useDashboardLayout() {
  const isEditing = ref(false)
  const layout = ref<LayoutItem[]>(loadLayout() || structuredClone(DEFAULT_SUMMARY_LAYOUT))

  function resetLayout() {
    layout.value = structuredClone(DEFAULT_SUMMARY_LAYOUT)
    localStorage.removeItem(getStorageKey())
  }

  function onLayoutUpdated(newLayout: LayoutItem[]) {
    layout.value = newLayout
    saveLayoutToStorage(newLayout)
  }

  function toggleEditing() {
    isEditing.value = !isEditing.value
  }

  // Ensure all default widgets exist in loaded layout (in case new widgets were added)
  const currentIds = new Set(layout.value.map(l => l.i))
  for (const def of DEFAULT_SUMMARY_LAYOUT) {
    if (!currentIds.has(def.i)) {
      layout.value.push(structuredClone(def))
    }
  }

  return {
    layout,
    isEditing,
    toggleEditing,
    resetLayout,
    onLayoutUpdated,
    DEFAULT_SUMMARY_LAYOUT,
  }
}
