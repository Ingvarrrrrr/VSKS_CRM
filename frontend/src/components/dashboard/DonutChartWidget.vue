<template>
  <div class="chart-card" style="height:100%;overflow:auto">
    <div class="chart-card-header">
      <template v-if="donutView === 'breakdown'">
        <v-btn icon="mdi-arrow-left" variant="text" size="x-small" class="mr-1" @click="donutView = 'donut'" />
        <v-icon
          size="18"
          class="mr-2"
          :icon="segmentIcons[drillDownSegment ?? 0] || 'mdi-chart-bar'"
          :color="segmentColors[drillDownSegment ?? 0] || 'primary'"
        />
        <span class="chart-card-title">{{ segmentLabels[drillDownSegment ?? 0] }}</span>
      </template>
      <template v-else>
        <v-icon icon="mdi-chart-donut" size="18" color="#3B82F6" class="mr-2" />
        <span class="chart-card-title">Структура бюджета</span>
        <v-chip
          v-if="hasOverrun && overrunAmount > 0"
          size="x-small"
          color="error"
          variant="tonal"
          class="ml-2 font-weight-bold"
          prepend-icon="mdi-alert-circle-outline"
        >
          План: {{ formatCurrencyShort(totalPlanSchedule) }} (превышение +{{ formatCurrencyShort(overrunAmount) }} / +{{ overrunPct }}%)
        </v-chip>
        <span v-else class="text-caption text-medium-emphasis ml-2">(нажмите на сегмент)</span>
      </template>
    </div>
    <Transition name="chart-fade" mode="out-in">
      <div v-if="donutView === 'donut'" key="donut" ref="donutContainerRef" class="donut-chart-wrapper" style="position:relative">
        <apexchart v-if="donutReady && chartAlive" type="donut" height="270" :options="donutOptions" :series="donutSeries" />
        <!-- Внешняя красная SVG-дуга превышения (Вариант А: «Второй круг») -->
        <svg
          v-if="hasOverrun && donutReady && chartAlive && overrunArcPath"
          class="donut-overrun-svg"
          style="position:absolute;top:0;left:0;width:100%;height:270px;pointer-events:none;z-index:2"
        >
          <path
            :d="overrunArcPath"
            fill="none"
            stroke="#EF4444"
            stroke-width="5"
            stroke-linecap="round"
          />
        </svg>
        <div v-else-if="!donutReady" class="chart-empty">
          <v-icon icon="mdi-chart-donut" size="48" color="grey-lighten-2" />
          <div class="text-caption text-medium-emphasis mt-2">Нет данных о бюджете</div>
        </div>
      </div>
      <div v-else key="breakdown">
        <apexchart v-if="chartAlive" type="bar" height="270" :options="breakdownBarOptions" :series="breakdownBarSeries" />
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch, defineAsyncComponent } from 'vue'
import { useKeepAliveChartGuard } from '@/composables/dashboard/useKeepAliveChartGuard'
import { formatCurrencyShort } from '@/composables/dashboard/dashboardFormat'
import { SEGMENT_ICONS, SEGMENT_COLORS } from '@/composables/dashboard/useDonutWidget'

// vue3-apexcharts тянется динамически только там, где есть <apexchart>
const apexchart = defineAsyncComponent(() => import('vue3-apexcharts').then(m => m.default))
const chartAlive = useKeepAliveChartGuard()

const props = withDefaults(defineProps<{
  donutReady: boolean
  donutOptions: any
  donutSeries: number[]
  drillDownSegment: number | null
  breakdownBarOptions: any
  breakdownBarSeries: any[]
  segmentLabels: string[]
  segmentIcons?: string[]
  segmentColors?: string[]
  hasOverrun?: boolean
  overrunAmount?: number
  overrunPct?: number
  totalPlanSchedule?: number
}>(), {
  segmentIcons: () => SEGMENT_ICONS,
  segmentColors: () => SEGMENT_COLORS,
  hasOverrun: false,
  overrunAmount: 0,
  overrunPct: 0,
  totalPlanSchedule: 0,
})

const donutView = defineModel<'donut' | 'breakdown'>('donutView', { required: true })

const donutContainerRef = ref<HTMLElement | null>(null)
const pieCenter = ref<{ cx: number; cy: number; r: number } | null>(null)

function toXY(cx: number, cy: number, r: number, deg: number) {
  const rad = (deg - 90) * Math.PI / 180
  return {
    x: +(cx + r * Math.cos(rad)).toFixed(2),
    y: +(cy + r * Math.sin(rad)).toFixed(2),
  }
}

function arcPath(cx: number, cy: number, r: number, a1: number, a2: number): string {
  const span = a2 - a1
  if (span <= 0.1) return ''
  if (span >= 359.9) {
    const mid = a1 + 180
    const p1 = toXY(cx, cy, r, a1)
    const p2 = toXY(cx, cy, r, mid)
    const p3 = toXY(cx, cy, r, a2)
    return `M ${p1.x} ${p1.y} A ${r} ${r} 0 1 1 ${p2.x} ${p2.y} A ${r} ${r} 0 1 1 ${p3.x} ${p3.y}`
  }
  const s = toXY(cx, cy, r, a1)
  const e = toXY(cx, cy, r, a2)
  const lg = span > 180 ? 1 : 0
  return `M ${s.x} ${s.y} A ${r} ${r} 0 ${lg} 1 ${e.x} ${e.y}`
}

function updatePieCenter() {
  if (!donutContainerRef.value) return
  const pieEl = donutContainerRef.value.querySelector('.apexcharts-pie')
  if (!pieEl) return
  const parentG = pieEl.parentElement
  if (!parentG) return
  const transform = parentG.getAttribute('transform') || ''
  const match = transform.match(/translate\(\s*([0-9.-]+)\s*[, ]\s*([0-9.-]+)\s*\)/)
  if (match) {
    const cx = parseFloat(match[1])
    const cy = parseFloat(match[2])
    const slice = pieEl.querySelector('path')
    let r = 98
    if (slice) {
      try {
        const bbox = (slice as SVGGraphicsElement).getBBox()
        const dx = Math.max(Math.abs(bbox.x), Math.abs(bbox.x + bbox.width))
        const dy = Math.max(Math.abs(bbox.y), Math.abs(bbox.y + bbox.height))
        const calcR = Math.sqrt(dx * dx + dy * dy)
        if (calcR > 40 && calcR < 150) {
          r = calcR
        }
      } catch (_) {
        // SVG graphics element bbox fallback
      }
    }
    pieCenter.value = { cx, cy, r: r + 7 }
  }
}

const overrunArcPath = computed(() => {
  if (!props.hasOverrun || !props.overrunPct || props.overrunPct <= 0) return ''
  const center = pieCenter.value
  const fallbackWidth = donutContainerRef.value?.clientWidth || 360
  const cx = center ? center.cx : fallbackWidth / 2
  const cy = center ? center.cy : 108
  const r = center ? center.r : 105

  // Доля перерасхода от 0 до 100% (или более, если перерасход > 100%, дуга замыкается)
  const ratio = Math.min(props.overrunPct / 100, 1)
  const deg = ratio * 360

  return arcPath(cx, cy, r, 0, deg)
})

let observer: MutationObserver | null = null
let ro: ResizeObserver | null = null

onMounted(() => {
  nextTick(() => {
    updatePieCenter()
    if (donutContainerRef.value) {
      observer = new MutationObserver(() => {
        updatePieCenter()
      })
      observer.observe(donutContainerRef.value, { childList: true, subtree: true, attributes: true })
      ro = new ResizeObserver(() => {
        updatePieCenter()
      })
      ro.observe(donutContainerRef.value)
    }
  })
})

onBeforeUnmount(() => {
  observer?.disconnect()
  ro?.disconnect()
})

watch([() => props.donutSeries, () => props.hasOverrun], () => {
  nextTick(() => updatePieCenter())
})
</script>
