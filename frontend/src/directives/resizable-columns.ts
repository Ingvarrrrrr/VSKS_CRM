/**
 * Vue directive: v-resizable-columns="tableId"
 * Adds drag-to-resize handles on all <th> columns.
 * Widths saved to localStorage per tableId.
 *
 * Usage: <table v-resizable-columns="'my-table'">
 *        <v-data-table v-resizable-columns="'orders'">
 */
import type { Directive } from 'vue'

function findTable(el: HTMLElement): HTMLTableElement | null {
  if (el.tagName === 'TABLE') return el as HTMLTableElement
  return el.querySelector('table')
}

function applyHandles(tableEl: HTMLTableElement, tableId: string) {
  const ths = tableEl.querySelectorAll('thead th')
  if (!ths.length) return

  ths.forEach((th) => {
    const thEl = th as HTMLElement
    if (thEl.querySelector('.vrc-handle')) return

    thEl.style.position = 'relative'
    const handle = document.createElement('div')
    handle.className = 'vrc-handle'
    handle.addEventListener('mousedown', (e: MouseEvent) => {
      e.preventDefault()
      e.stopPropagation()

      const startX = e.clientX
      const startWidth = thEl.offsetWidth

      document.body.style.cursor = 'col-resize'
      document.body.style.userSelect = 'none'
      handle.classList.add('vrc-active')

      const onMove = (ev: MouseEvent) => {
        const newWidth = Math.max(40, startWidth + ev.clientX - startX)
        thEl.style.width = newWidth + 'px'
        thEl.style.minWidth = newWidth + 'px'
      }

      const onUp = () => {
        document.removeEventListener('mousemove', onMove)
        document.removeEventListener('mouseup', onUp)
        document.body.style.cursor = ''
        document.body.style.userSelect = ''
        handle.classList.remove('vrc-active')
        saveWidths(tableEl, tableId)
      }

      document.addEventListener('mousemove', onMove)
      document.addEventListener('mouseup', onUp)
    })
    thEl.appendChild(handle)
  })

  restoreWidths(tableEl, tableId)
}

function saveWidths(tableEl: HTMLTableElement, tableId: string) {
  const ths = tableEl.querySelectorAll('thead th')
  const widths: number[] = []
  ths.forEach(th => widths.push((th as HTMLElement).offsetWidth))
  try { localStorage.setItem(`vrc_${tableId}`, JSON.stringify(widths)) } catch {}
}

function restoreWidths(tableEl: HTMLTableElement, tableId: string) {
  try {
    const saved = localStorage.getItem(`vrc_${tableId}`)
    if (!saved) return
    const widths: number[] = JSON.parse(saved)
    const ths = tableEl.querySelectorAll('thead th')
    ths.forEach((th, i) => {
      if (widths[i]) {
        const el = th as HTMLElement
        el.style.width = widths[i] + 'px'
        el.style.minWidth = widths[i] + 'px'
      }
    })
  } catch {}
}

export const vResizableColumns: Directive<HTMLElement, string> = {
  mounted(el, binding) {
    const tableId = binding.value || 'default'
    // Retry until table is rendered (Vuetify renders async)
    let attempts = 0
    const tryApply = () => {
      const table = findTable(el)
      if (table && table.querySelector('thead th')) {
        applyHandles(table, tableId)
      } else if (attempts < 20) {
        attempts++
        setTimeout(tryApply, 200)
      }
    }
    tryApply()
  },
  updated(el, binding) {
    const tableId = binding.value || 'default'
    // Re-apply after data updates (new columns may appear)
    setTimeout(() => {
      const table = findTable(el)
      if (table) applyHandles(table, tableId)
    }, 100)
  },
}
