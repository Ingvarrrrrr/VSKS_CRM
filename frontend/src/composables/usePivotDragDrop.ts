import { ref } from 'vue'

/**
 * Drag-and-drop для конструктора сводных (PivotBuilderView.vue).
 *
 * Нативный HTML5 DnD (draggable/dragstart/dragover/drop) — без новых
 * зависимостей (vuedraggable в package.json уже есть, но он рассчитан на
 * сортировку ОДНОГО списка; здесь четыре разных типа зон с разной логикой
 * допуска поля — проще и явнее на нативном DnD).
 *
 * ПРАВИЛО модульности: вся логика DnD — здесь, отдельно от PivotBuilderView.vue
 * и от usePivotConfig.ts (который остаётся единственным местом, меняющим
 * состояние конфигуратора — addRow/addCol/addMeasure/moveDimension).
 *
 * Правила допуска (owner, 23.10.2026):
 * - измерение (is_dimension) → можно в Строки/Колонки; в Значения — только
 *   если поле ОДНОВРЕМЕННО и мера (is_measure=true, напр. subsidy_budget).
 * - мера (is_measure) → можно в Значения; в Строки/Колонки — только если
 *   поле одновременно измерение (is_dimension=true).
 * - Фильтры — вне DnD (не входит в задачу).
 */

export type PivotDropZone = 'rows' | 'cols' | 'measures'

export interface DragCatalogField {
  key: string
  label: string
  is_dimension?: boolean
  is_measure?: boolean
  agg_default?: string
}

interface ChipOrigin {
  zone: 'rows' | 'cols'
  idx: number
}

export interface PivotConfigDragAdapter {
  addRow: (field: { key: string; label: string }) => void
  addCol: (field: { key: string; label: string }) => void
  addMeasure: (field: { key: string; label: string; agg_default?: string }, agg?: string) => void
  moveDimension: (
    from: 'rows' | 'cols', fromIdx: number,
    to: 'rows' | 'cols', toIdx: number,
  ) => void
}

export function usePivotDragDrop(pivot: PivotConfigDragAdapter) {
  // Поле, которое тащат ПРЯМО СЕЙЧАС — либо из каталога (новое), либо чип
  // из Строк/Колонок (перемещение/переупорядочивание).
  const draggedField = ref<DragCatalogField | null>(null)
  const draggedChip = ref<ChipOrigin | null>(null)

  // Подсветка: какая зона сейчас активна под курсором + индекс чипа внутри
  // зоны (для вставки между конкретными чипами, не только в конец).
  const activeZone = ref<PivotDropZone | null>(null)
  const activeChipIndex = ref<number | null>(null)

  function canDrop(field: DragCatalogField | null, zone: PivotDropZone): boolean {
    if (!field) return false
    if (zone === 'measures') return !!field.is_measure
    return !!field.is_dimension
  }

  function resetDrag() {
    draggedField.value = null
    draggedChip.value = null
    activeZone.value = null
    activeChipIndex.value = null
  }

  // --- Источник: поле из каталога слева (вкладки «Измерения» / «Меры») ---
  function onCatalogDragStart(e: DragEvent, field: DragCatalogField) {
    draggedField.value = field
    draggedChip.value = null
    try {
      e.dataTransfer?.setData('text/plain', field.key)
      if (e.dataTransfer) e.dataTransfer.effectAllowed = 'copy'
    } catch { /* некоторые браузеры в тестовом окружении могут не поддерживать dataTransfer */ }
  }

  // --- Источник: уже существующий чип в Строках/Колонках ---
  function onChipDragStart(
    e: DragEvent, zone: 'rows' | 'cols', idx: number, field: DragCatalogField,
  ) {
    draggedChip.value = { zone, idx }
    // Баг (приёмка 23.10.2026): pivot.state.rows/cols хранят только {key,label} —
    // без is_dimension/is_measure. Положенный «как есть» field давал canDrop()=false
    // на ЛЮБОЙ зоне (и dragover, и drop отклонялись) — перенос/переупорядочивание чипов
    // не работало вовсе. Чип в Строках/Колонках по определению измерение (иначе он
    // не мог там оказаться — addRow/addCol зовутся только для is_dimension-полей),
    // и НЕ мера — в Значения такой чип не переносится (см. onZoneDrop: zone==='measures' → return).
    draggedField.value = { ...field, is_dimension: true, is_measure: false }
    try {
      e.dataTransfer?.setData('text/plain', field.key)
      if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move'
    } catch { /* см. выше */ }
  }

  // --- Приёмник: сама карточка зоны (Строки/Колонки/Значения) ---
  function onZoneDragOver(e: DragEvent, zone: PivotDropZone) {
    if (!canDrop(draggedField.value, zone)) {
      if (activeZone.value === zone) activeZone.value = null
      return
    }
    e.preventDefault()
    activeZone.value = zone
    if (!draggedChip.value) activeChipIndex.value = null  // над пустым местом зоны — вставка в конец
    if (e.dataTransfer) e.dataTransfer.dropEffect = draggedChip.value ? 'move' : 'copy'
  }

  function onZoneDragLeave(e: DragEvent, zone: PivotDropZone) {
    // relatedTarget внутри той же карточки (например, переход на чип) — не гасим подсветку.
    const related = e.relatedTarget as Node | null
    const current = e.currentTarget as Node | null
    if (related && current && current.contains(related)) return
    if (activeZone.value === zone) {
      activeZone.value = null
      activeChipIndex.value = null
    }
  }

  // --- Приёмник: конкретный чип внутри Строк/Колонок — для вставки МЕЖДУ чипами ---
  function onChipDragOver(e: DragEvent, zone: 'rows' | 'cols', idx: number) {
    if (!canDrop(draggedField.value, zone)) return
    e.preventDefault()
    e.stopPropagation()  // не даём карточке-контейнеру сбросить activeChipIndex в null
    activeZone.value = zone
    // Левая половина чипа → вставить ПЕРЕД ним (idx), правая половина → ПОСЛЕ (idx+1).
    // Без этого деления «вставить перед idx» всегда давала idx как индекс в
    // ДОРЕМУВ-массиве — соседний обмен местами (A,B → перетащить A на B) не менял
    // порядок: moveDimension сдвигает insertAt на -1 при перемещении вперёд внутри
    // той же зоны (см. её докстринг), так что «перед idx» для соседнего элемента
    // возвращало исходную позицию. idx+1 на правой половине даёт реальный обмен.
    let insertIdx = idx
    const target = e.currentTarget as HTMLElement | null
    if (target && typeof target.getBoundingClientRect === 'function') {
      const rect = target.getBoundingClientRect()
      const midX = rect.left + rect.width / 2
      insertIdx = e.clientX < midX ? idx : idx + 1
    }
    activeChipIndex.value = insertIdx
    if (e.dataTransfer) e.dataTransfer.dropEffect = draggedChip.value ? 'move' : 'copy'
  }

  function onZoneDrop(e: DragEvent, zone: PivotDropZone) {
    e.preventDefault()
    const field = draggedField.value
    const dropIdx = activeChipIndex.value
    const chipOrigin = draggedChip.value
    resetDrag()
    if (!field || !canDrop(field, zone)) return

    if (chipOrigin) {
      if (zone === 'measures') return  // меры — отдельная структура (PivotMeasure), чипы Строк/Колонок туда не переносятся
      const target = zone as 'rows' | 'cols'
      const toIdx = dropIdx !== null ? dropIdx : (
        target === chipOrigin.zone ? chipOrigin.idx : Number.MAX_SAFE_INTEGER
      )
      pivot.moveDimension(chipOrigin.zone, chipOrigin.idx, target, toIdx)
    } else if (zone === 'rows') {
      pivot.addRow(field)
    } else if (zone === 'cols') {
      pivot.addCol(field)
    } else if (zone === 'measures') {
      pivot.addMeasure(field)
    }
  }

  return {
    draggedField,
    draggedChip,
    activeZone,
    activeChipIndex,
    canDrop,
    onCatalogDragStart,
    onChipDragStart,
    onZoneDragOver,
    onZoneDragLeave,
    onChipDragOver,
    onZoneDrop,
    resetDrag,
  }
}
