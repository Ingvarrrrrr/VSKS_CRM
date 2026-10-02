// Авто-высота виджета KPI-карточек в десктопной сетке дашборда (grid-layout-plus).
//
// Проблема: DEFAULT_SUMMARY_LAYOUT держит фиксированную h для виджета 'kpi' (строки
// grid-layout). Карточек становится больше (добавлены «Можно перераспределить» и
// «Экономия по закупкам» — сейчас 11), на узких/средних ширинах они переносятся на
// 2-3 ряда, и фиксированная h перестаёт хватать: виджет 'kpi' — position:absolute
// с явной высотой, и более поздние по DOM-порядку виджеты (donut/radial/pipeline)
// рисуются поверх переполнения, а не ниже него — наезжают на карточки.
// Любая следующая магическая константа строк — то же самое другими словами, плюс
// у части пользователей уже СОХРАНЁН старый layout в localStorage (useDashboardLayout
// хранит по user_id), так что фикс не должен зависеть от сброса раскладки.
//
// Решение: измерять фактическую высоту отрендеренного содержимого виджета
// (ResizeObserver) и держать h в layout синхронизированной с ней — независимо от
// числа карточек, ширины окна (переносы Vuetify-колонок) и от того, что лежит в
// localStorage. Работает только для desktop-ветки (mobile считает высоту отдельной
// формулой в useDashboardGridLayout.ts — там уже динамика по числу карточек).
import { ref, onMounted, onBeforeUnmount, watch, nextTick, type Ref } from 'vue'
import type { LayoutItem } from '@/composables/useDashboardLayout'

// Должны совпадать с :row-height и :margin на <GridLayout> в DashboardView.vue
const ROW_HEIGHT = 30
const ROW_MARGIN = 12

export function useKpiAutoHeight(
  layout: Ref<LayoutItem[]>,
  handleLayoutUpdated: (l: LayoutItem[]) => void,
  isEditing: Ref<boolean>,
  mobile: Ref<boolean>,
) {
  const kpiWidgetEl = ref<HTMLElement | null>(null)
  let observer: ResizeObserver | null = null

  function syncHeight() {
    // Пока пользователь вручную тащит/резайзит виджеты — не перебиваем его жест.
    // На мобильной раскладке высота уже считается формулой в useDashboardGridLayout.ts.
    if (mobile.value || isEditing.value) return
    const el = kpiWidgetEl.value
    if (!el) return
    const contentPx = el.scrollHeight
    if (!contentPx) return
    const neededH = Math.max(6, Math.ceil((contentPx + ROW_MARGIN) / (ROW_HEIGHT + ROW_MARGIN)))
    const kpiItem = layout.value.find(l => l.i === 'kpi')
    if (!kpiItem || kpiItem.h === neededH) return
    handleLayoutUpdated(layout.value.map(l => (l.i === 'kpi' ? { ...l, h: neededH } : l)))
  }

  onMounted(() => {
    if (typeof ResizeObserver === 'undefined') return
    observer = new ResizeObserver(() => { nextTick(syncHeight) })
    watch(kpiWidgetEl, (el, prevEl) => {
      if (prevEl && observer) observer.unobserve(prevEl)
      if (el && observer) observer.observe(el)
    }, { immediate: true })
  })

  onBeforeUnmount(() => observer?.disconnect())

  // Пересчитать сразу после выхода из режима редактирования и при переключении mobile/desktop.
  watch([isEditing, mobile], () => nextTick(syncHeight))

  return { kpiWidgetEl }
}
