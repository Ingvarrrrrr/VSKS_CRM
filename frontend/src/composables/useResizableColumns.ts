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
// Колонки, для которых когда-либо поднимали дефолт и поэтому нужно один раз
// подтянуть сохранённую в localStorage ширину до нового defaults[key] — иначе
// сохранённое старое значение (localStorage перебивает defaults) навсегда
// перекрывает повышение дефолта в коде и пользователь правки не увидит.
// Целевое значение — ВСЕГДА defaults[key], не хардкод, чтобы миграция не
// разъехалась с дефолтом при следующей его смене. Тот же приём, что и
// миграция layout KPI в useDashboardLayout.ts.
//   - type: 2026-08 — ФЭО-каскад перестал рендериться внутри ячейки «Тип»
//     (вынесен в отдельную full-width подстроку, см. ItemsTableFlat.vue),
//     из-за чего «Товар»/«Услуга» + стрелка v-select обрезались в «Т...».
//     Дефолт поднят до 128.
//   - unit: 2026-08 — «Ед. изм.» (v-combobox) со стрелкой съедала почти всю
//     90px ширину, самое длинное значение («компл.») обрезалось в «ш..».
//     Дефолт поднят до 120 (замерено scrollWidth/clientWidth в браузере).
const BUMP_TO_DEFAULT_KEYS = ['type', 'unit']

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
        let migrated = false

        // «Тип» отдельно: у части пользователей ширина сохранена растянутой ещё
        // со старого дефолта (>140px) сверх разумного. Этот верхний клэмп нужен
        // только «Типу» (так исторически растягивали только его) — на «unit»
        // и будущие ключи не распространяем без явной причины.
        if (typeof colWidths.value.type === 'number' && colWidths.value.type > 140) {
          colWidths.value.type = defaults.type
          migrated = true
        }

        // Общая миграция «подтянуть сохранённое к новому дефолту, если меньше»
        // для всех ключей из BUMP_TO_DEFAULT_KEYS.
        for (const key of BUMP_TO_DEFAULT_KEYS) {
          const w = colWidths.value[key]
          if (typeof w === 'number' && typeof defaults[key] === 'number' && w < defaults[key]) {
            colWidths.value[key] = defaults[key]
            migrated = true
          }
        }

        if (migrated) save()
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
