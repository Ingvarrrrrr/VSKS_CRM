import { ref, computed, readonly, type ComputedRef, type Ref } from 'vue'
import { apiFetch } from '@/api'

export type MarkColor = 'yellow' | 'red' | 'green' | 'blue' | 'purple' | 'orange'

export const MARK_COLOR_PALETTE: Array<{
  key: MarkColor
  label: string
  swatch: string
  lightBg: string
  darkBg: string
  corner: string
}> = [
  {
    key: 'yellow',
    label: 'Вопрос',
    swatch: '#fbbf24',
    lightBg: '#fef3c7',
    darkBg: '#453205',
    corner: '#f59e0b',
  },
  {
    key: 'red',
    label: 'Проблема/Стоп',
    swatch: '#ef4444',
    lightBg: '#fee2e2',
    darkBg: '#4c1212',
    corner: '#ef4444',
  },
  {
    key: 'green',
    label: 'Проверено',
    swatch: '#10b981',
    lightBg: '#d1fae5',
    darkBg: '#063d2e',
    corner: '#10b981',
  },
  {
    key: 'blue',
    label: 'Инфо',
    swatch: '#3b82f6',
    lightBg: '#dbeafe',
    darkBg: '#172e54',
    corner: '#3b82f6',
  },
  {
    key: 'purple',
    label: 'На контроль',
    swatch: '#8b5cf6',
    lightBg: '#ede9fe',
    darkBg: '#2f1954',
    corner: '#8b5cf6',
  },
  {
    key: 'orange',
    label: 'Срочно',
    swatch: '#f97316',
    lightBg: '#ffedd5',
    darkBg: '#4d2008',
    corner: '#f97316',
  },
]

export interface CellTarget {
  entityType: string
  entityId: number
  fieldName: string // '*' означает всю строку целиком
  fieldLabel?: string
  orgId?: number | null
  subsidyId?: number | null
}

export interface CellMarkRecord {
  id: number
  group_id: string
  entity_type: string
  entity_id: number
  field_name: string
  org_id?: number | null
  subsidy_id?: number | null
  color: MarkColor | null
  comment: string | null
  visibility: 'shared' | 'private'
  is_resolved: boolean
  resolved_at?: string | null
  resolved_by_name?: string | null
  created_by_id?: number | null
  created_by_name?: string | null
  created_at: string
}

// Module-level reactive singleton state
const marksMap = ref<Map<string, CellMarkRecord>>(new Map())
const selectedTargetsInternal = ref<CellTarget[]>([])
const activeColorFilter = ref<Record<string, MarkColor | 'any' | null>>({})

// Comment popover state
const isCommentOpen = ref(false)
const commentPosition = ref<{ x: number; y: number }>({ x: 0, y: 0 })
const activeCommentTargets = ref<CellTarget[]>([])

// In-flight request deduplication map
const pendingLoads = new Map<string, Promise<void>>()

let escapeListenerRegistered = false
function ensureEscapeListener() {
  if (escapeListenerRegistered || typeof window === 'undefined') return
  escapeListenerRegistered = true
  window.addEventListener('keydown', (e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      if (selectedTargetsInternal.value.length > 0) {
        selectedTargetsInternal.value = []
      }
    }
  })
}

function makeKey(entityType: string, entityId: number, fieldName: string): string {
  return `${entityType}:${entityId}:${fieldName}`
}

export function useCellMarks() {
  ensureEscapeListener()

  const selectedTargets: ComputedRef<CellTarget[]> = computed(() => selectedTargetsInternal.value)

  function isCellSelected(entityType: string, entityId: number, fieldName = '*'): boolean {
    return selectedTargetsInternal.value.some(t => {
      if (t.entityType !== entityType || t.entityId !== entityId) return false
      if (fieldName === '*' || t.fieldName === '*') return true
      return t.fieldName === fieldName
    })
  }

  function handleCellSelectClick(event: MouseEvent, target: CellTarget): boolean {
    if (!event || (!event.ctrlKey && !event.metaKey && !event.shiftKey)) {
      return false
    }

    event.preventDefault()
    event.stopPropagation()

    const idx = selectedTargetsInternal.value.findIndex(
      t => t.entityType === target.entityType && t.entityId === target.entityId && t.fieldName === target.fieldName
    )

    if (idx >= 0) {
      selectedTargetsInternal.value = selectedTargetsInternal.value.filter((_, i) => i !== idx)
    } else {
      selectedTargetsInternal.value = [...selectedTargetsInternal.value, { ...target }]
    }
    return true
  }

  function clearSelection(): void {
    selectedTargetsInternal.value = []
  }

  function setBatchSelection(targets: CellTarget[]): void {
    selectedTargetsInternal.value = [...targets]
  }

  async function loadMarks(entityType: string, entityIds: number[], subsidyId?: number | null): Promise<void> {
    const validIds = Array.from(new Set(entityIds.filter(id => typeof id === 'number' && !isNaN(id))))
    if (validIds.length === 0) return

    const key = `${entityType}:${validIds.slice().sort().join(',')}:${subsidyId ?? ''}`
    if (pendingLoads.has(key)) {
      return pendingLoads.get(key)
    }

    const loadPromise = (async () => {
      try {
        const queryParams = new URLSearchParams()
        queryParams.set('entity_type', entityType)
        queryParams.set('entity_ids', validIds.join(','))
        if (subsidyId !== undefined && subsidyId !== null) {
          queryParams.set('subsidy_id', String(subsidyId))
        }

        const data = await apiFetch<CellMarkRecord[]>(`/cell-marks?${queryParams.toString()}`)
        const list = Array.isArray(data) ? data : []

        const nextMap = new Map(marksMap.value)
        for (const item of list) {
          if (!item.is_resolved) {
            const itemKey = makeKey(item.entity_type, item.entity_id, item.field_name)
            nextMap.set(itemKey, item)
          }
        }
        marksMap.value = nextMap
      } catch (e) {
        console.warn('[useCellMarks] loadMarks failed', e)
      } finally {
        pendingLoads.delete(key)
      }
    })()

    pendingLoads.set(key, loadPromise)
    return loadPromise
  }

  function getExactMark(entityType: string, entityId: number, fieldName: string): CellMarkRecord | null {
    const key = makeKey(entityType, entityId, fieldName)
    return marksMap.value.get(key) || null
  }

  function getRowMark(entityType: string, entityId: number): CellMarkRecord | null {
    const key = makeKey(entityType, entityId, '*')
    return marksMap.value.get(key) || null
  }

  function getMark(entityType: string, entityId: number, fieldName = '*'): CellMarkRecord | null {
    const exact = getExactMark(entityType, entityId, fieldName)
    if (exact && exact.color) return exact
    const row = getRowMark(entityType, entityId)
    if (row && row.color) return row
    return exact || row || null
  }

  function getCellMarkClasses(entityType: string, entityId: number, fieldName: string): Record<string, boolean> {
    const mark = getMark(entityType, entityId, fieldName)
    const exact = getExactMark(entityType, entityId, fieldName)
    const row = getRowMark(entityType, entityId)
    const hasComment = Boolean((exact && exact.comment) || (row && row.comment))

    return {
      'gala-cell-marked': !!(mark && mark.color),
      'gala-cell-has-comment': hasComment,
      'gala-cell-selected': isCellSelected(entityType, entityId, fieldName),
    }
  }

  function getCellMarkStyle(entityType: string, entityId: number, fieldName: string): Record<string, string> {
    const mark = getMark(entityType, entityId, fieldName)
    const exact = getExactMark(entityType, entityId, fieldName)
    const row = getRowMark(entityType, entityId)
    const colorKey = mark?.color

    const commentMark = (exact && exact.comment) ? exact : (row && row.comment ? row : null)
    const cornerColorKey = commentMark?.color || colorKey || 'yellow'

    const paletteItem = MARK_COLOR_PALETTE.find(p => p.key === colorKey)
    const cornerPaletteItem = MARK_COLOR_PALETTE.find(p => p.key === cornerColorKey)

    return {
      '--gala-mark-light': paletteItem ? paletteItem.lightBg : 'transparent',
      '--gala-mark-dark': paletteItem ? paletteItem.darkBg : 'transparent',
      '--gala-mark-corner': cornerPaletteItem ? cornerPaletteItem.corner : '#f59e0b',
    }
  }

  function getRowMarkClasses(entityType: string, entityId: number): Record<string, boolean> {
    const rowMark = getRowMark(entityType, entityId)
    return {
      'gala-row-marked': !!(rowMark && rowMark.color),
      'gala-row-has-comment': !!(rowMark && rowMark.comment),
      'gala-row-selected': isCellSelected(entityType, entityId, '*'),
    }
  }

  function getRowMarkStyle(entityType: string, entityId: number): Record<string, string> {
    const rowMark = getRowMark(entityType, entityId)
    const paletteItem = MARK_COLOR_PALETTE.find(p => p.key === rowMark?.color)
    const cornerPaletteItem = MARK_COLOR_PALETTE.find(p => p.key === rowMark?.color) || MARK_COLOR_PALETTE[0]

    return {
      '--gala-mark-light': paletteItem ? paletteItem.lightBg : 'transparent',
      '--gala-mark-dark': paletteItem ? paletteItem.darkBg : 'transparent',
      '--gala-mark-corner': cornerPaletteItem ? cornerPaletteItem.corner : 'transparent',
    }
  }

  function openCommentAt(posOrEvent: MouseEvent | { x: number; y: number }, target: CellTarget | CellTarget[]): void {
    const x = 'clientX' in posOrEvent ? posOrEvent.clientX : posOrEvent.x
    const y = 'clientY' in posOrEvent ? posOrEvent.clientY : posOrEvent.y

    commentPosition.value = { x, y }
    activeCommentTargets.value = Array.isArray(target) ? target : [target]
    isCommentOpen.value = true
  }

  function closeComment(): void {
    isCommentOpen.value = false
    activeCommentTargets.value = []
  }

  function setColorFilter(entityType: string, color: MarkColor | 'any' | null): void {
    activeColorFilter.value = {
      ...activeColorFilter.value,
      [entityType]: color,
    }
  }

  function matchesColorFilter(entityType: string, entityId: number): boolean {
    const filter = activeColorFilter.value[entityType]
    if (!filter) return true

    const rowMark = getRowMark(entityType, entityId)
    if (filter === 'any') {
      if (rowMark && rowMark.color) return true
    } else if (rowMark && rowMark.color === filter) {
      return true
    }

    const prefix = `${entityType}:${entityId}:`
    for (const [key, mark] of marksMap.value.entries()) {
      if (key.startsWith(prefix) && !mark.is_resolved) {
        if (filter === 'any' && mark.color) return true
        if (mark.color === filter) return true
      }
    }

    return false
  }

  async function applyMarkBatch(payload: {
    targets: CellTarget[]
    color?: MarkColor | null
    comment?: string | null
    visibility?: 'shared' | 'private'
    subsidyId?: number | null
    orgId?: number | null
  }): Promise<void> {
    if (!payload.targets || payload.targets.length === 0) return

    const validTargets = payload.targets.filter(
      t => Number(t.entityId) > 0 && !!t.entityType && t.entityType !== 'table_row'
    )
    if (validTargets.length === 0) return

    const serializedTargets = validTargets.map(t => ({
      entity_type: t.entityType,
      entity_id: Number(t.entityId),
      field_name: t.fieldName || '*',
      org_id: t.orgId ?? payload.orgId ?? null,
      subsidy_id: t.subsidyId ?? payload.subsidyId ?? null,
    }))

    const body: Record<string, any> = {
      targets: serializedTargets,
      visibility: payload.visibility || 'shared',
      subsidy_id: payload.subsidyId ?? null,
      org_id: payload.orgId ?? null,
    }
    if (payload.color !== undefined) {
      body.color = payload.color
    }
    if (payload.comment !== undefined) {
      body.comment = payload.comment
    }

    const res = await apiFetch<CellMarkRecord[] | { items?: CellMarkRecord[] }>('/cell-marks/batch', {
      method: 'POST',
      body: body as any,
    })

    const rawList = Array.isArray(res) ? res : (res && Array.isArray(res.items) ? res.items : [])
    const nextMap = new Map(marksMap.value)

    if (rawList.length > 0) {
      for (const item of rawList) {
        const itemKey = makeKey(item.entity_type, item.entity_id, item.field_name)
        if (item.is_resolved) {
          nextMap.delete(itemKey)
        } else {
          nextMap.set(itemKey, item)
        }
      }
    } else {
      // Optimistic update
      const groupId = `temp_${Date.now()}`
      for (const t of validTargets) {
        const k = makeKey(t.entityType, Number(t.entityId), t.fieldName || '*')
        const prev = nextMap.get(k)
        const updated: CellMarkRecord = {
          id: prev?.id || Math.floor(Math.random() * 100000),
          group_id: prev?.group_id || groupId,
          entity_type: t.entityType,
          entity_id: Number(t.entityId),
          field_name: t.fieldName || '*',
          org_id: t.orgId ?? payload.orgId ?? null,
          subsidy_id: t.subsidyId ?? payload.subsidyId ?? null,
          color: payload.color !== undefined ? payload.color : (prev?.color ?? null),
          comment: payload.comment !== undefined ? payload.comment : (prev?.comment ?? null),
          visibility: payload.visibility || prev?.visibility || 'shared',
          is_resolved: false,
          created_at: prev?.created_at || new Date().toISOString(),
        }
        nextMap.set(k, updated)
      }
    }
    marksMap.value = nextMap
  }

  async function clearMarksColor(targets: CellTarget[]): Promise<void> {
    if (!targets || targets.length === 0) return

    const validTargets = targets.filter(
      t => Number(t.entityId) > 0 && !!t.entityType && t.entityType !== 'table_row'
    )
    if (validTargets.length === 0) return

    const serializedTargets = validTargets.map(t => ({
      entity_type: t.entityType,
      entity_id: Number(t.entityId),
      field_name: t.fieldName || '*',
    }))

    await apiFetch('/cell-marks/clear-color', {
      method: 'POST',
      body: { targets: serializedTargets } as any,
    })

    const nextMap = new Map(marksMap.value)
    for (const t of validTargets) {
      const k = makeKey(t.entityType, Number(t.entityId), t.fieldName || '*')
      const prev = nextMap.get(k)
      if (prev) {
        if (!prev.comment) {
          nextMap.delete(k)
        } else {
          nextMap.set(k, { ...prev, color: null })
        }
      }
    }
    marksMap.value = nextMap
  }

  async function resolveMarkGroup(groupId: string): Promise<void> {
    if (!groupId) return

    await apiFetch(`/cell-marks/${groupId}/resolve`, {
      method: 'POST',
    })

    const nextMap = new Map(marksMap.value)
    for (const [k, mark] of nextMap.entries()) {
      if (mark.group_id === groupId) {
        nextMap.delete(k)
      }
    }
    marksMap.value = nextMap
  }

  return {
    selectedTargets,
    isCellSelected,
    handleCellSelectClick,
    clearSelection,
    setBatchSelection,
    loadMarks,
    getMark,
    getExactMark,
    getRowMark,
    getCellMarkClasses,
    getCellMarkStyle,
    getRowMarkClasses,
    getRowMarkStyle,
    openCommentAt,
    closeComment,
    isCommentOpen: readonly(isCommentOpen),
    commentPosition: readonly(commentPosition),
    activeCommentTargets: readonly(activeCommentTargets),
    activeColorFilter: activeColorFilter as Ref<Record<string, MarkColor | 'any' | null>>,
    setColorFilter,
    matchesColorFilter,
    applyMarkBatch,
    clearMarksColor,
    resolveMarkGroup,
  }
}
