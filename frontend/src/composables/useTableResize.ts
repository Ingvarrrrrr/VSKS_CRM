/**
 * Global table column resize functionality.
 * Call initTableResize() on mounted to enable resize on all tables with class "resizable-table".
 *
 * Usage: add class="resizable-table" to any <table>, <v-table>, or wrapper of <v-data-table>.
 * Column widths are saved to localStorage per data-table-id attribute.
 */

let initialized = false

export function initTableResize() {
  if (initialized) return
  initialized = true

  document.addEventListener('mousedown', (e) => {
    const handle = (e.target as HTMLElement).closest('.vtr-handle') as HTMLElement
    if (!handle) return

    e.preventDefault()
    const th = handle.parentElement as HTMLElement
    if (!th) return

    const startX = e.clientX
    const startWidth = th.offsetWidth

    const tableEl = th.closest('table') as HTMLElement
    const tableId = tableEl?.getAttribute('data-resize-id') || 'default'

    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
    handle.classList.add('vtr-active')

    const onMove = (ev: MouseEvent) => {
      const newWidth = Math.max(40, startWidth + ev.clientX - startX)
      th.style.width = newWidth + 'px'
      th.style.minWidth = newWidth + 'px'
    }

    const onUp = () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
      handle.classList.remove('vtr-active')

      // Save all column widths
      const ths = tableEl?.querySelectorAll('thead th')
      if (ths) {
        const widths: number[] = []
        ths.forEach(t => widths.push((t as HTMLElement).offsetWidth))
        try { localStorage.setItem(`table-cols-${tableId}`, JSON.stringify(widths)) } catch {}
      }
    }

    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  })
}

/**
 * Restore saved column widths for a table.
 * Call after the table is rendered.
 */
export function restoreTableWidths(tableEl: HTMLElement | null) {
  if (!tableEl) return
  const tableId = tableEl.getAttribute('data-resize-id') || 'default'
  try {
    const saved = localStorage.getItem(`table-cols-${tableId}`)
    if (!saved) return
    const widths: number[] = JSON.parse(saved)
    const ths = tableEl.querySelectorAll('thead th')
    ths.forEach((th, i) => {
      if (widths[i]) {
        ;(th as HTMLElement).style.width = widths[i] + 'px'
        ;(th as HTMLElement).style.minWidth = widths[i] + 'px'
      }
    })
  } catch {}
}

/**
 * Add resize handles to all <th> in a table.
 */
export function addResizeHandles(tableEl: HTMLElement | null) {
  if (!tableEl) return
  const ths = tableEl.querySelectorAll('thead th')
  ths.forEach((th) => {
    if (th.querySelector('.vtr-handle')) return // already has handle
    const handle = document.createElement('div')
    handle.className = 'vtr-handle'
    ;(th as HTMLElement).style.position = 'relative'
    th.appendChild(handle)
  })
}
