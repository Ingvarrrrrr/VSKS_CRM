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
        // Миграция: колонка «Тип» (Товар/Услуга) у части пользователей сохранена
        // растянутой ещё со старого дефолта (120px) сверх разумного. Подрезаем
        // единожды к текущему дефолту (defaults.type, НЕ хардкод — иначе разъедется
        // с ним при следующей смене дефолта) — иначе «Ед. изм.» уезжает за край
        // таблицы. Верхняя граница (>140) — та же, что и была; поменялось только
        // целевое значение отката (было жёстко 90).
        // Тот же приём, что и миграция layout KPI в useDashboardLayout.ts.
        if (typeof colWidths.value.type === 'number' && colWidths.value.type > 140) {
          colWidths.value.type = defaults.type
          save()
        // Миграция (2026-08-06): ФЭО-каскад перестал рендериться внутри ячейки «Тип»
        // (вынесен в отдельную full-width подстроку, см. ItemsTableFlat.vue) — раньше
        // именно он растягивал ячейку своим min-width, поэтому колонка держалась на
        // 90px. Без него «Товар»/«Услуга» + стрелка v-select обрезаются в «Т...».
        // Дефолт поднят до 128 — тем, у кого в localStorage уже лежит меньшее
        // значение (в т.ч. 90 от миграции выше), поднимаем один раз до нового дефолта.
        } else if (typeof colWidths.value.type === 'number' && colWidths.value.type < defaults.type) {
          colWidths.value.type = defaults.type
          save()
        }
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
    // Для авто-колонок (default 0) стартуем от фактической ширины th, чтобы не было скачка
    const th = (e.currentTarget as HTMLElement | null)?.closest('th')
    startWidth = colWidths.value[colKey] || th?.offsetWidth || defaults[colKey] || 100

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
