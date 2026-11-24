import { onMounted, onBeforeUnmount, type Ref } from 'vue'
import { useTheme } from 'vuetify'
import {
  useCellMarks,
  MARK_COLOR_PALETTE,
  type CellTarget,
  type MarkColor,
} from '@/composables/useCellMarks'
import {
  useGalaContextMenu,
  extractNumericValue,
  type GalaCellContextOptions,
} from '@/composables/useGalaContextMenu'
import { FEO_HISTORY_FIELD_LABELS } from '@/constants/feoHistoryFieldLabels'

function normalizeStyle(style: any): Record<string, any> {
  if (!style) return {}
  if (Array.isArray(style)) {
    return style.reduce((acc, s) => Object.assign(acc, normalizeStyle(s)), {})
  }
  if (typeof style === 'object') {
    return { ...style }
  }
  return {}
}

export function useFeoMarksContext() {
  const cellMarks = useCellMarks()
  const galaContextMenu = useGalaContextMenu()

  let vuetifyTheme: any = null
  try {
    vuetifyTheme = useTheme()
  } catch {
    // Vuetify context might not be available in non-component tests
  }

  function isDark(): boolean {
    return !!vuetifyTheme?.global?.current?.value?.dark
  }

  function getMarkBgColor(colorKey: MarkColor | null | undefined): string | null {
    if (!colorKey) return null
    const pal = MARK_COLOR_PALETTE.find((p) => p.key === colorKey)
    if (!pal) return null
    return isDark() ? pal.darkBg : pal.lightBg
  }

  function mergeRowStyle(baseStyle: any, entityType: string, entityId: number | string): Record<string, any> {
    const idNum = Number(entityId)
    if (!idNum) return normalizeStyle(baseStyle)

    const rowMark = cellMarks.getRowMark(entityType, idNum)
    const markStyle = cellMarks.getRowMarkStyle(entityType, idNum)
    const res = { ...normalizeStyle(baseStyle), ...markStyle }

    if (rowMark?.color) {
      const bg = getMarkBgColor(rowMark.color)
      if (bg) {
        res.background = bg
        res.backgroundColor = bg
      }
    }
    return res
  }

  function mergeCellStyle(
    baseStyle: any,
    entityType: string,
    entityId: number | string,
    fieldName: string,
  ): Record<string, any> {
    const idNum = Number(entityId)
    if (!idNum) return normalizeStyle(baseStyle)

    const cellMark = cellMarks.getMark(entityType, idNum, fieldName)
    const markStyle = cellMarks.getCellMarkStyle(entityType, idNum, fieldName)
    const res = { ...normalizeStyle(baseStyle), ...markStyle }

    if (cellMark?.color) {
      const bg = getMarkBgColor(cellMark.color)
      if (bg) {
        res.background = bg
        res.backgroundColor = bg
      }
    }
    return res
  }

  function feoRowAttrs(entityType: string, entityId: number | string, baseStyle?: any) {
    const idNum = Number(entityId)
    return {
      class: idNum ? cellMarks.getRowMarkClasses(entityType, idNum) : {},
      style: mergeRowStyle(baseStyle, entityType, idNum),
    }
  }

  function feoCellAttrs(entityType: string, entityId: number | string, fieldName: string, baseStyle?: any) {
    const idNum = Number(entityId)
    return {
      class: idNum ? cellMarks.getCellMarkClasses(entityType, idNum, fieldName) : {},
      style: mergeCellStyle(baseStyle, entityType, idNum, fieldName),
    }
  }

  function onFeoCellClick(event: MouseEvent, target: CellTarget): boolean {
    if (cellMarks.handleCellSelectClick(event, target)) {
      event.stopPropagation()
      return true
    }
    const el = event.currentTarget as HTMLElement | null
    if (el) {
      const rect = el.getBoundingClientRect()
      const offsetX = event.clientX - rect.left
      const offsetY = event.clientY - rect.top
      const isTopRight =
        (offsetX >= el.clientWidth - 16 || event.clientX >= rect.right - 18) &&
        (offsetY <= 16 || event.clientY <= rect.top + 18)
      const mark = cellMarks.getMark(target.entityType, Number(target.entityId), target.fieldName)
      if (isTopRight && mark?.comment) {
        event.stopPropagation()
        cellMarks.openCommentAt(event, target)
        return true
      }
    }
    return false
  }

  function onFeoCellContextMenu(event: MouseEvent, opts: GalaCellContextOptions) {
    if (event) {
      event.preventDefault()
      event.stopPropagation()
    }
    const cleanNumber =
      opts.rawNumber !== undefined ? opts.rawNumber : extractNumericValue(opts.cellValue)
    const label = opts.fieldLabel || FEO_HISTORY_FIELD_LABELS[opts.fieldName] || opts.fieldName

    galaContextMenu.openCellContextMenu(event, {
      ...opts,
      fieldLabel: label,
      rawNumber: cleanNumber,
    })
  }

  async function loadMarks(entityType: string, entityIds: (number | string)[], subsidyId?: number | null) {
    const validIds = entityIds
      .map((id) => Number(id))
      .filter((id) => typeof id === 'number' && !isNaN(id) && id > 0)
    if (validIds.length === 0) return
    await cellMarks.loadMarks(entityType, validIds, subsidyId)
  }

  function matchesColorFilter(entityType: string, entityId: number | string): boolean {
    return cellMarks.matchesColorFilter(entityType, Number(entityId))
  }

  function onEntityRestored(
    callback: (detail: { entityType: string; entityId: number | string; fieldName: string; value: any }) => void,
  ) {
    const handler = (e: Event) => {
      const customEv = e as CustomEvent
      if (customEv.detail) {
        callback(customEv.detail)
      }
    }
    onMounted(() => {
      if (typeof window !== 'undefined') window.addEventListener('gala:entity-restored', handler)
    })
    onBeforeUnmount(() => {
      if (typeof window !== 'undefined') window.removeEventListener('gala:entity-restored', handler)
    })
  }

  return {
    cellMarks,
    galaContextMenu,
    activeColorFilter: cellMarks.activeColorFilter as Ref<Record<string, MarkColor | 'any' | null>>,
    mergeRowStyle,
    mergeCellStyle,
    feoRowAttrs,
    feoCellAttrs,
    onFeoCellClick,
    onFeoCellContextMenu,
    loadMarks,
    matchesColorFilter,
    onEntityRestored,
  }
}
