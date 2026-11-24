import { ref, readonly } from 'vue'
import { useToast } from '@/composables/useToast'
import type { CellTarget } from '@/composables/useCellMarks'

export interface ContextMenuItem {
  key: string
  label: string
  icon?: string
  disabled?: boolean
  danger?: boolean
  dividerBefore?: boolean
  onClick?: () => void | Promise<void>
}

export interface CellHistoryEvent {
  id: number | string
  changedAt: string | Date
  changedByName?: string | null
  oldValue?: string | number | boolean | null
  newValue?: string | number | boolean | null
  action?: 'added' | 'replaced' | 'deleted' | 'created'
  isCreated?: boolean
  source?: string | null
  comment?: string | null
  originLabel?: string | null
  isCalculatedOrEmpty?: boolean
}

export interface GalaCellContextOptions {
  entityType: string // 'feo_item' | 'feo_category' | 'purchase' | 'task' | 'vehicle' | etc.
  entityId: number | string
  fieldName: string
  fieldLabel: string
  cellValue?: any
  historyLoader?: (options: GalaCellContextOptions) => Promise<CellHistoryEvent[]>
  extraItems?: ContextMenuItem[]
  // Новые опциональные поля расширенного ядра
  rawNumber?: number | string | null
  openUrl?: string | null
  rowUrl?: string | null
  subsidyId?: number | null
  orgId?: number | null
  bulkTargets?: CellTarget[]
  onFilterValue?: (value: any, mode: 'include' | 'exclude') => void
  canRestoreHistory?: boolean
}

export interface ContextMenuPosition {
  x: number
  y: number
}

// Module-level singleton state for context menu & cell history popover
const isMenuOpen = ref(false)
const menuPosition = ref<ContextMenuPosition>({ x: 0, y: 0 })
const activeCellOptions = ref<GalaCellContextOptions | null>(null)

const isHistoryOpen = ref(false)
const historyPosition = ref<ContextMenuPosition>({ x: 0, y: 0 })
const historyCellOptions = ref<GalaCellContextOptions | null>(null)

export function extractNumericValue(val: any): string | null {
  if (val === null || val === undefined || val === '') return null
  if (typeof val === 'number') {
    return isFinite(val) ? String(val) : null
  }
  const str = String(val).trim()
  // Clean out common formatting: spaces, non-breaking spaces, currency symbols
  const cleaned = str
    .replace(/[\s\u00A0\u202F]/g, '')
    .replace(/[₽$€%]/g, '')
    .replace(',', '.')

  if (!cleaned) return null
  const num = Number(cleaned)
  if (!isNaN(num) && isFinite(num) && /\d/.test(cleaned)) {
    return String(num)
  }
  return null
}

export function useGalaContextMenu() {
  const { addToast } = useToast()

  function openCellContextMenu(event: MouseEvent, options: GalaCellContextOptions) {
    if (event) {
      event.preventDefault()
      event.stopPropagation()
    }
    // Close history popover if open
    isHistoryOpen.value = false

    activeCellOptions.value = { ...options }
    menuPosition.value = {
      x: event ? event.clientX : window.innerWidth / 2,
      y: event ? event.clientY : window.innerHeight / 2,
    }
    isMenuOpen.value = true
  }

  function closeContextMenu() {
    isMenuOpen.value = false
  }

  function openCellHistory(options?: GalaCellContextOptions, pos?: ContextMenuPosition) {
    const targetOptions = options || activeCellOptions.value
    if (!targetOptions) return

    closeContextMenu()
    historyCellOptions.value = { ...targetOptions }
    historyPosition.value = pos || { ...menuPosition.value }
    isHistoryOpen.value = true
  }

  function closeCellHistory() {
    isHistoryOpen.value = false
    historyCellOptions.value = null
  }

  async function copyTextToClipboard(text: string, successMessage = 'Скопировано в буфер') {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text)
      } else {
        const textarea = document.createElement('textarea')
        textarea.value = text
        textarea.style.position = 'fixed'
        textarea.style.opacity = '0'
        document.body.appendChild(textarea)
        textarea.select()
        document.execCommand('copy')
        document.body.removeChild(textarea)
      }
      addToast(successMessage, 'success', { duration: 2000 })
    } catch (e) {
      console.warn('Failed to copy to clipboard', e)
      addToast('Не удалось скопировать в буфер', 'error', { duration: 2500 })
    }
  }

  async function copyCellValue(val?: any) {
    const rawVal = val !== undefined ? val : activeCellOptions.value?.cellValue
    let textToCopy = ''
    if (rawVal !== null && rawVal !== undefined) {
      textToCopy = typeof rawVal === 'object' ? JSON.stringify(rawVal) : String(rawVal)
    }

    if (!textToCopy) {
      addToast('Ячейка пуста, нечего копировать', 'info', { duration: 2000 })
      closeContextMenu()
      return
    }

    await copyTextToClipboard(textToCopy, 'Значение скопировано в буфер')
    closeContextMenu()
  }

  async function copyCleanNumber(num?: number | string | null) {
    let target = num
    if (target === undefined) {
      if (activeCellOptions.value?.rawNumber !== undefined && activeCellOptions.value.rawNumber !== null) {
        target = activeCellOptions.value.rawNumber
      } else {
        target = extractNumericValue(activeCellOptions.value?.cellValue)
      }
    }

    if (target === null || target === undefined || target === '') {
      addToast('Числовое значение не найдено', 'info', { duration: 2000 })
      closeContextMenu()
      return
    }

    await copyTextToClipboard(String(target), `Число ${target} скопировано`)
    closeContextMenu()
  }

  async function copyRowLink() {
    const opts = activeCellOptions.value
    if (!opts) return

    let url = opts.rowUrl
    if (!url && typeof window !== 'undefined') {
      const urlObj = new URL(window.location.href)
      urlObj.searchParams.set('gala_focus', `${opts.entityType}:${opts.entityId}`)
      url = urlObj.toString()
    }

    if (!url) {
      addToast('Не удалось сформировать ссылку', 'error', { duration: 2000 })
      closeContextMenu()
      return
    }

    await copyTextToClipboard(url, 'Прямая ссылка на строку скопирована')
    closeContextMenu()
  }

  return {
    // Context menu state
    isMenuOpen: readonly(isMenuOpen),
    menuPosition: readonly(menuPosition),
    activeCellOptions: readonly(activeCellOptions),

    // History popover state
    isHistoryOpen: readonly(isHistoryOpen),
    historyPosition: readonly(historyPosition),
    historyCellOptions: readonly(historyCellOptions),

    // Actions
    openCellContextMenu,
    closeContextMenu,
    openCellHistory,
    closeCellHistory,
    copyCellValue,
    copyCleanNumber,
    copyRowLink,
  }
}
