// useRowJump — ЕДИНЫЙ механизм «перейти к строке» для ВСЕХ сводных
// предупреждений мастера «Импорт факта» (жалоба владельца 05.10.2026:
// предупреждения не говорят, какие строки, по ним нельзя кликнуть).
// ПРАВИЛО №6/№5: один механизм на весь мастер, не копия по месту — шаг
// «Строки» (FactImportStepRows.vue) и шаг «Закупки» (FactImportStepGroups.vue)
// оба используют этот модуль-синглтон (та же схема, что useFactImport.ts).
//
// Состояние простое: кто-то вызывает jumpToRow(row) — кладёт номер строки в
// pendingRow; активный в данный момент шаг-компонент (только один виден
// одновременно, см. FactImportWizard.vue v-if/v-else-if) сам решает, как
// «показать» строку (снять свой локальный фильтр, раскрыть панель) и когда
// снять pendingRow — вызовом clearPendingRow() после скролла. highlightedRow
// держит номер строки, которую нужно кратко подсветить (сбрасывается само
// через таймер).
import { reactive } from 'vue'

interface RowJumpState {
  pendingRow: number | null
  highlightedRow: number | null
}

const state = reactive<RowJumpState>({ pendingRow: null, highlightedRow: null })

let highlightTimer: ReturnType<typeof setTimeout> | null = null

export function useRowJump() {
  /** Запросить переход к строке — шаг-компонент подхватит через watch(pendingRow). */
  function jumpToRow(row: number) {
    state.pendingRow = row
  }

  function clearPendingRow() {
    state.pendingRow = null
  }

  /** Подсветить строку на ~1.6с (кратко мигает/рамка — см. стили .row-jump-flash). */
  function highlightRow(row: number) {
    if (highlightTimer) clearTimeout(highlightTimer)
    state.highlightedRow = row
    highlightTimer = setTimeout(() => {
      if (state.highlightedRow === row) state.highlightedRow = null
      highlightTimer = null
    }, 1600)
  }

  /** Найти элемент строки в пределах контейнера (таблица/список шага) по
   *  data-row-anchor и проскроллить к нему — общий финальный шаг для обоих
   *  шагов мастера, разница только в том, ЧТО нужно сначала раскрыть/отфильтровать. */
  function scrollToRowEl(container: HTMLElement | null | undefined, row: number) {
    if (!container) return false
    const el = container.querySelector<HTMLElement>(`[data-row-anchor="${row}"]`)
    if (!el) return false
    el.scrollIntoView({ block: 'center', behavior: 'smooth' })
    highlightRow(row)
    return true
  }

  return { state, jumpToRow, clearPendingRow, highlightRow, scrollToRowEl }
}
