import { ref, onMounted } from 'vue'

/**
 * Composable for drag-to-resize table columns with localStorage persistence.
 *
 * Usage:
 *   const { colWidths, onResizeStart, resizeStyle } = useResizableColumns('my-table', {
 *     name: 400, budget: 150, spent: 150, actions: 120
 *   })
 *
 * In template:
 *   <th :style="resizeStyle('name')">
 *     Name
 *     <span class="col-resize-handle" @mousedown="onResizeStart($event, 'name')">&nbsp;</span>
 *   </th>
 */
export function useResizableColumns(tableId: string, defaults: Record<string, number>) {
  const STORAGE_KEY = `col_widths_${tableId}`

  const colWidths = ref<Record<string, number>>({ ...defaults })

  // Load saved widths
  onMounted(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY)
      if (saved) {
        const parsed = JSON.parse(saved)
        colWidths.value = { ...defaults, ...parsed }
      }
    } catch {}
  })

  function save() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(colWidths.value))
  }

  let resizingCol: string | null = null
  let startX = 0
  let startWidth = 0

  function onResizeStart(e: MouseEvent, colKey: string) {
    e.preventDefault()
    e.stopPropagation()
    resizingCol = colKey
    startX = e.clientX
    startWidth = colWidths.value[colKey] || defaults[colKey] || 100

    const onMouseMove = (ev: MouseEvent) => {
      if (!resizingCol) return
      const delta = ev.clientX - startX
      const newWidth = Math.max(50, startWidth + delta)
      colWidths.value[resizingCol] = newWidth
    }

    const onMouseUp = () => {
      document.removeEventListener('mousemove', onMouseMove)
      document.removeEventListener('mouseup', onMouseUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
      save()
      resizingCol = null
    }

    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup', onMouseUp)
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }

  function resizeStyle(colKey: string): Record<string, string> {
    const w = colWidths.value[colKey]
    if (!w) return {}
    return { width: `${w}px`, minWidth: `${w}px`, maxWidth: `${w}px` }
  }

  function resetWidths() {
    colWidths.value = { ...defaults }
    localStorage.removeItem(STORAGE_KEY)
  }

  return { colWidths, onResizeStart, resizeStyle, resetWidths }
}
