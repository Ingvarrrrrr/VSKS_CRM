import { ref, computed, watch, toValue, type MaybeRefOrGetter } from 'vue'
import { useDisplay } from 'vuetify'

export interface ColumnDef {
  key: string
  title: string
  width?: number
  sortable?: boolean
  group?: string  // для табов: 'core' | 'file' | 'all' | свой
  align?: 'start' | 'center' | 'end'
}

export interface ColumnConfigState {
  visible: string[]   // массив видимых ключей (Set сериализуется хуже)
  order: string[]     // полный порядок (включая невидимые — чтобы при тогле visible вернуть на исходную позицию)
  widths: Record<string, number>
}

const LS_PREFIX = 'col_config_v1_'  // v1 чтобы будущие миграции не ломались

export function useColumnConfig(tableId: string, allColumns: MaybeRefOrGetter<ColumnDef[]>) {
  const lsKey = LS_PREFIX + tableId
  // На mobile inline width/overflow-wrap превращают текст в вертикальный «по букве».
  // useDisplay reactive: при ротации устройства автоматически переключаемся.
  // Защита если composable вызван вне Vuetify-context (например в тестах).
  let smAndDown: { value: boolean }
  try {
    smAndDown = useDisplay().smAndDown
  } catch {
    smAndDown = { value: false }
  }

  function defaultState(): ColumnConfigState {
    const cols = toValue(allColumns)
    return {
      visible: cols.filter(c => c.group !== 'all').map(c => c.key),
      order: cols.map(c => c.key),
      widths: Object.fromEntries(cols.filter(c => c.width).map(c => [c.key, c.width!])),
    }
  }

  function loadState(): ColumnConfigState {
    try {
      const raw = localStorage.getItem(lsKey)
      if (!raw) return defaultState()
      const parsed = JSON.parse(raw) as Partial<ColumnConfigState>
      const def = defaultState()
      const cols = toValue(allColumns)
      // Защита от устаревших ключей (новые колонки добавлены в код, не было в storage)
      const knownKeys = new Set(cols.map(c => c.key))
      const visible = (parsed.visible ?? def.visible).filter(k => knownKeys.has(k))
      const orderFromLS = (parsed.order ?? def.order).filter(k => knownKeys.has(k))
      // Добавить новые колонки в конец order
      const missingInOrder = cols.map(c => c.key).filter(k => !orderFromLS.includes(k))
      const order = [...orderFromLS, ...missingInOrder]
      return {
        visible,
        order,
        widths: parsed.widths ?? def.widths,
      }
    } catch {
      return defaultState()
    }
  }

  const state = ref<ColumnConfigState>(loadState())

  // Persist on every change
  watch(state, () => {
    try { localStorage.setItem(lsKey, JSON.stringify(state.value)) } catch {}
  }, { deep: true })

  // When allColumns changes (e.g. raw_* arrive from API), extend order with new keys
  watch(
    () => toValue(allColumns),
    (cols) => {
      const knownInOrder = new Set(state.value.order)
      const newKeys = cols.map(c => c.key).filter(k => !knownInOrder.has(k))
      if (newKeys.length > 0) {
        state.value = {
          ...state.value,
          order: [...state.value.order, ...newKeys],
        }
      }
    },
    { deep: false },
  )

  // visibleHeaders = order.filter(visible) → map to ColumnDef + inline style for width
  // Vuetify v-data-table игнорирует поле width в reactive headers без явного inline style
  // на <th> и <td> — поэтому добавляем cellProps/headerProps.
  const visibleHeaders = computed(() => {
    const cols = toValue(allColumns)
    const isMobile = smAndDown.value
    return state.value.order
      .filter(k => state.value.visible.includes(k))
      .map(k => {
        const def = cols.find(c => c.key === k)
        if (!def) return null
        const w = state.value.widths[k] ?? def.width
        // На mobile: inline width/wrap снимаем — даём таблице auto-layout с horizontal scroll.
        // Без этого узкие колонки (60-200px на 375px viewport) ломали текст посимвольно.
        if (isMobile) {
          return { ...def, width: undefined, headerProps: undefined, cellProps: undefined }
        }
        // word-wrap: длинный текст переносится на новые строки, ячейка растёт по высоте.
        // overflow-wrap: anywhere ломает даже слова без пробелов (длинные ИНН/UUID/etc).
        const cellStyle = w
          ? `width: ${w}px; min-width: ${w}px; max-width: ${w}px; white-space: normal; word-wrap: break-word; overflow-wrap: anywhere;`
          : ''
        const headerStyle = w
          ? `width: ${w}px; min-width: ${w}px; max-width: ${w}px; white-space: normal; word-wrap: break-word;`
          : ''
        return {
          ...def,
          width: w,
          headerProps: headerStyle ? { style: headerStyle } : undefined,
          cellProps: cellStyle ? { style: cellStyle, title: undefined } : undefined,
        }
      })
      .filter(Boolean) as any[]
  })

  function toggleVisible(key: string, show?: boolean) {
    const isVisible = state.value.visible.includes(key)
    const target = show ?? !isVisible
    if (target && !isVisible) state.value.visible = [...state.value.visible, key]
    else if (!target && isVisible) state.value.visible = state.value.visible.filter(k => k !== key)
  }

  /** position: 1-based, среди visible колонок */
  function setPosition(key: string, position: number) {
    const visibleOrdered = state.value.order.filter(k => state.value.visible.includes(k))
    const currentIdx = visibleOrdered.indexOf(key)
    if (currentIdx < 0) return
    const target = Math.max(1, Math.min(position, visibleOrdered.length)) - 1
    if (target === currentIdx) return
    visibleOrdered.splice(currentIdx, 1)
    visibleOrdered.splice(target, 0, key)
    // Восстановить полный order: видимые в новом порядке + невидимые в старом
    const invisibleOrdered = state.value.order.filter(k => !state.value.visible.includes(k))
    state.value.order = [...visibleOrdered, ...invisibleOrdered]
  }

  function setWidth(key: string, px: number) {
    state.value.widths = { ...state.value.widths, [key]: px }
  }

  function reset() {
    localStorage.removeItem(lsKey)
    state.value = defaultState()
  }

  /** Миграция со старого формата (для PaymentRegistryView). Вызывается из view ОДИН РАЗ. */
  function migrateFrom(oldKeys: { visible?: string; widths?: string }) {
    if (localStorage.getItem(lsKey)) return  // уже мигрировано
    const cols = toValue(allColumns)
    const migrated = defaultState()
    if (oldKeys.visible) {
      try {
        const v = JSON.parse(localStorage.getItem(oldKeys.visible) || 'null')
        if (Array.isArray(v)) migrated.visible = v.filter(k => cols.some(c => c.key === k))
      } catch {}
    }
    if (oldKeys.widths) {
      try {
        const w = JSON.parse(localStorage.getItem(oldKeys.widths) || 'null')
        if (w && typeof w === 'object') migrated.widths = w
      } catch {}
    }
    localStorage.setItem(lsKey, JSON.stringify(migrated))
    state.value = migrated
  }

  return { state, visibleHeaders, toggleVisible, setPosition, setWidth, reset, migrateFrom }
}
