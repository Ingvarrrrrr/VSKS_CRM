// Раскладка сетки виджетов (grid-layout-plus): desktop drag/resize layout из
// useDashboardLayout + отдельная упрощённая мобильная раскладка в одну колонку.
// Перенесено без изменений из DashboardView.vue при разбиении на модули.
import { computed, watch, type Ref, type ComputedRef } from 'vue'
import { useDashboardLayout, type LayoutItem } from '@/composables/useDashboardLayout'
import { useDashboardMode } from '@/composables/useDashboardMode'

// Mobile-only stacked layout (full-width, single column, tuned heights)
// ROW_PX = 125 — высота одного ряда KPI-карточек на мобильном (card ~113px + v-col padding 12px)
const MOBILE_KPI_ROW_PX = 125
const MOBILE_KPI_PADDING = 32 // запас + 12 margin

export function useDashboardGridLayout(
  mobile: Ref<boolean>,
  kpiCardsLength: ComputedRef<number>,
  monthlyContractsRemainingLength: ComputedRef<number>,
  pipelineByTypeHasTotal: ComputedRef<boolean>,
  dashboardToggleMode: Ref<'classic' | 'radar'>,
) {
  const { layout, isEditing, toggleEditing, resetLayout, onLayoutUpdated, DEFAULT_SUMMARY_LAYOUT } = useDashboardLayout()
  const { setMode } = useDashboardMode()

  watch(dashboardToggleMode, (v) => {
    if (v === 'classic' || v === 'radar') setMode(v)
  })

  const MOBILE_ITEMS_BASE: Array<{ i: string; h: number; condition?: () => boolean }> = [
    { i: 'kpi',       h: 0  }, // h вычисляется динамически
    { i: 'donut',     h: 11 },
    { i: 'radial',    h: 7  },
    { i: 'pipeline',  h: 11 },
    { i: 'monthly',   h: 8,  condition: () => monthlyContractsRemainingLength.value > 0 },
    { i: 'breakdown', h: 9,  condition: () => pipelineByTypeHasTotal.value },
    { i: 'purchases', h: 11 },
    { i: 'table',     h: 14 },
    { i: 'finplan',   h: 14 },
  ]

  const mobileLayout = computed<LayoutItem[]>(() => {
    // Фикс 2: динамическая высота KPI под реальное количество карточек (2 в ряд)
    const rows = Math.ceil(kpiCardsLength.value / 2)
    const kpiH = Math.ceil((rows * MOBILE_KPI_ROW_PX + MOBILE_KPI_PADDING) / 42)

    let y = 0
    const result: LayoutItem[] = []
    for (const { i, h: staticH, condition } of MOBILE_ITEMS_BASE) {
      // Фикс 3: пропускать скрытые виджеты (monthly/breakdown) — убирает пустые дырки
      if (condition && !condition()) continue
      const h = i === 'kpi' ? kpiH : staticH
      result.push({ i, x: 0, y, w: 12, h, minW: 12, minH: h })
      y += h
    }
    return result
  })

  const effectiveLayout = computed<LayoutItem[]>(() => mobile.value ? mobileLayout.value : layout.value)

  function handleLayoutUpdated(l: typeof layout.value) {
    if (!mobile.value) onLayoutUpdated(l)
  }

  return {
    layout, isEditing, toggleEditing, resetLayout, DEFAULT_SUMMARY_LAYOUT,
    effectiveLayout, handleLayoutUpdated, setMode,
  }
}
