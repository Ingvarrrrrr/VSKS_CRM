import { onMounted, onUnmounted, getCurrentInstance } from 'vue'
import { useGalaContextMenu, extractNumericValue } from '@/composables/useGalaContextMenu'
import { useCellMarks } from '@/composables/useCellMarks'

/**
 * Universal delegated contextmenu & selection listener for any table cells across the app.
 * Automatically extracts entityType, entityId, fieldName, fieldLabel and cell values
 * from DOM tables without requiring manual boilerplate on every single <td>.
 */
export function useUniversalTableContext() {
  const { openCellContextMenu } = useGalaContextMenu()
  const { handleCellSelectClick, openCommentAt } = useCellMarks()

  function isInputOrExcluded(target: HTMLElement | null): boolean {
    if (!target) return false
    return !!target.closest(
      'input, textarea, [contenteditable="true"], .gala-context-menu, .gala-history-popover, .gala-comment-popover'
    )
  }

  function handleContextMenu(e: MouseEvent) {
    if (e.defaultPrevented) return
    const target = e.target as HTMLElement | null
    if (!target || isInputOrExcluded(target)) return

    const cell = target.closest('td, [data-gala-cell]') as HTMLElement | null
    if (!cell) return

    const row = cell.closest('tr, [data-gala-row], [data-gala-focus]') as HTMLElement | null

    // Extract entity context
    let entityType = cell.dataset.entityType || row?.dataset.entityType
    let entityIdStr = cell.dataset.entityId || row?.dataset.entityId

    const focusVal = cell.dataset.galaFocus || cell.dataset.galaRow || row?.dataset.galaFocus || row?.dataset.galaRow
    if (focusVal && (!entityType || !entityIdStr)) {
      const parts = focusVal.split(':')
      if (parts.length >= 2) {
        entityType = entityType || parts[0]
        entityIdStr = entityIdStr || parts[1]
      }
    }

    if (!entityType) {
      entityType = 'table_row'
    }
    const entityId = entityIdStr ? parseInt(entityIdStr, 10) || entityIdStr : 0

    // Determine field label from corresponding <th>
    let fieldLabel = cell.dataset.fieldLabel || ''
    if (!fieldLabel && cell instanceof HTMLTableCellElement) {
      const table = cell.closest('table')
      if (table) {
        const ths = table.querySelectorAll('thead tr:last-child th')
        const idx = cell.cellIndex
        if (ths && idx >= 0 && idx < ths.length) {
          fieldLabel = ths[idx]?.textContent?.trim() || ''
        }
      }
    }

    // Determine field name
    const fieldName = cell.dataset.field || cell.dataset.fieldName || (fieldLabel ? fieldLabel.toLowerCase().replace(/\s+/g, '_') : '*')

    // Extract cell text and numeric value
    const selText = (typeof window !== 'undefined' ? window.getSelection?.()?.toString().trim() : '') || ''
    const cellText = selText || cell.innerText?.trim() || cell.textContent?.trim() || ''
    const rawNumber = extractNumericValue(cellText)

    const openUrl = cell.dataset.openUrl || row?.dataset.openUrl || (cell.querySelector('a') as HTMLAnchorElement | null)?.href || null

    e.preventDefault()

    openCellContextMenu(e, {
      entityType,
      entityId,
      fieldName,
      fieldLabel: fieldLabel || fieldName,
      cellValue: cellText,
      rawNumber,
      openUrl,
    })
  }

  function handleClick(e: MouseEvent) {
    const target = e.target as HTMLElement | null
    if (!target || isInputOrExcluded(target)) return

    const cell = target.closest('td, [data-gala-cell]') as HTMLElement | null
    if (!cell) return
    const row = cell.closest('tr, [data-gala-row], [data-gala-focus]') as HTMLElement | null

    // Check entity context
    let entityType = cell.dataset.entityType || row?.dataset.entityType
    let entityIdStr = cell.dataset.entityId || row?.dataset.entityId
    const focusVal = cell.dataset.galaFocus || cell.dataset.galaRow || row?.dataset.galaFocus || row?.dataset.galaRow
    if (focusVal && (!entityType || !entityIdStr)) {
      const parts = focusVal.split(':')
      if (parts.length >= 2) {
        entityType = parts[0]
        entityIdStr = parts[1]
      }
    }

    if (!entityType || !entityIdStr) return
    const entityId = parseInt(entityIdStr, 10) || 0
    if (!entityId) return

    // Ctrl / Meta / Shift + click for cell selection
    if (e.ctrlKey || e.metaKey || e.shiftKey) {
      const fieldName = cell.dataset.field || cell.dataset.fieldName || '*'
      const fieldLabel = cell.dataset.fieldLabel || fieldName
      handleCellSelectClick(
        e,
        {
          entityType,
          entityId,
          fieldName,
          fieldLabel,
        }
      )
      e.preventDefault()
      return
    }

    // Direct click on comment triangle indicator
    const rect = cell.getBoundingClientRect()
    const isTopRightCorner = (e.clientX >= rect.right - 14) && (e.clientY <= rect.top + 14)
    if (isTopRightCorner && (cell.classList.contains('gala-cell-has-comment') || row?.classList.contains('gala-row-has-comment'))) {
      const fieldName = cell.dataset.field || cell.dataset.fieldName || '*'
      const fieldLabel = cell.dataset.fieldLabel || fieldName
      openCommentAt(
        { x: e.clientX, y: e.clientY },
        [{ entityType, entityId, fieldName, fieldLabel }]
      )
      e.preventDefault()
    }
  }

  if (getCurrentInstance()) {
    onMounted(() => {
      if (typeof document !== 'undefined') {
        document.addEventListener('contextmenu', handleContextMenu)
        document.addEventListener('click', handleClick)
      }
    })

    onUnmounted(() => {
      if (typeof document !== 'undefined') {
        document.removeEventListener('contextmenu', handleContextMenu)
        document.removeEventListener('click', handleClick)
      }
    })
  }

  return {
    handleContextMenu,
    handleClick,
    isInputOrExcluded,
  }
}
