<template>
  <div class="spw-wrap">
    <svg :viewBox="`${-HALF} ${-HALF} ${SIZE} ${SIZE}`" :width="SIZE" :height="SIZE">

      <!-- Ring background tracks -->
      <circle
        v-for="i in ringCount" :key="`track-${i}`"
        cx="0" cy="0" :r="ringR(i - 1)"
        fill="none" stroke="#E5E7EB" :stroke-width="RING_W"
      />

      <!-- Pie slices -->
      <path
        v-for="seg in pieSegments" :key="seg.status"
        :d="seg.d" :fill="seg.color"
        stroke="white" stroke-width="1.5"
        style="cursor:pointer"
        @click="$emit('slice-click', seg.status)"
      >
        <title>{{ seg.label }}: {{ seg.count }} шт.</title>
      </path>

      <!-- Center hole (white/surface) for donut look -->
      <circle cx="0" cy="0" :r="PIE_R * 0.42" :fill="centerFill" />

      <!-- Full wish laps -->
      <circle
        v-for="(_, i) in fullLapsArr" :key="`lap-${i}`"
        cx="0" cy="0" :r="ringR(i)"
        fill="none" :stroke="lapColor(i)" :stroke-width="RING_W"
      />

      <!-- Partial wish arc -->
      <path
        v-if="partialRatio > 0.001"
        :d="partialArcD"
        fill="none" :stroke="lapColor(fullLapsArr.length)"
        :stroke-width="RING_W" stroke-linecap="round"
      />

      <!-- Percentage label inside partial ring -->
      <text
        v-if="wishRatio > 0"
        x="0" :y="HALF - 6"
        text-anchor="middle" font-size="9" :fill="lapColor(0)"
        font-weight="600"
      >{{ wishPct }}</text>

      <!-- Center text -->
      <text x="0" y="-5" text-anchor="middle" :font-size="totalCount >= 1000 ? 13 : 15"
        font-weight="700" :fill="textColor">{{ totalCount }}</text>
      <text x="0" y="11" text-anchor="middle" font-size="9" :fill="mutedColor">закупок</text>
    </svg>

    <!-- Legend -->
    <div class="spw-legend">
      <div
        v-for="seg in pieSegments" :key="seg.status"
        class="spw-legend-item" @click="$emit('slice-click', seg.status)"
      >
        <span class="spw-dot" :style="{ background: seg.color }" />
        <span class="spw-lbl">{{ seg.label }}</span>
      </div>
      <div v-if="wishesAmount > 0" class="spw-legend-item">
        <span class="spw-dot spw-dot--wish" />
        <span class="spw-lbl">Желания ({{ fmtShort(wishesAmount) }})</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface StatusEntry {
  status: string
  count: number
  color: string
  label: string
}

const props = defineProps<{
  statusEntries: StatusEntry[]
  wishesAmount: number
  totalBudget: number
  textColor?: string
  mutedColor?: string
  centerFill?: string
}>()

defineEmits<{ (e: 'slice-click', status: string): void }>()

// ── Layout constants ──────────────────────────────
const SIZE    = 220
const HALF    = SIZE / 2
const PIE_R   = 72
const RING_W  = 11
const RING_GAP = 3
const RING_START = PIE_R + RING_W / 2 + 5  // first ring center

function ringR(lap: number) {
  return RING_START + lap * (RING_W + RING_GAP)
}

// ── Colors ────────────────────────────────────────
const LAP_COLORS = ['#F59E0B', '#EF4444', '#DC2626', '#B91C1C']
function lapColor(i: number) { return LAP_COLORS[Math.min(i, LAP_COLORS.length - 1)] }

const textColor  = computed(() => props.textColor  || '#1F2937')
const mutedColor = computed(() => props.mutedColor || '#9CA3AF')
const centerFill = computed(() => props.centerFill || '#ffffff')

// ── Wish ratio ───────────────────────────────────
const wishRatio      = computed(() => props.totalBudget > 0 ? props.wishesAmount / props.totalBudget : 0)
const fullLapsCount  = computed(() => Math.floor(wishRatio.value))
const partialRatio   = computed(() => wishRatio.value - fullLapsCount.value)
const fullLapsArr    = computed(() => Array.from({ length: fullLapsCount.value }))
const ringCount      = computed(() => props.wishesAmount <= 0 ? 0 : fullLapsCount.value + 1)
const wishPct        = computed(() => {
  const p = wishRatio.value * 100
  return p >= 1000 ? Math.round(p) + '%' : p.toFixed(0) + '%'
})

// ── SVG helpers ──────────────────────────────────
function toXY(r: number, deg: number) {
  const rad = (deg - 90) * Math.PI / 180
  return { x: +(r * Math.cos(rad)).toFixed(3), y: +(r * Math.sin(rad)).toFixed(3) }
}

function piePath(r: number, a1: number, a2: number): string {
  if (a2 - a1 >= 359.9)
    return `M 0 ${-r} A ${r} ${r} 0 1 1 0.001 ${-r} Z`
  const s = toXY(r, a1), e = toXY(r, a2)
  const lg = a2 - a1 > 180 ? 1 : 0
  return `M 0 0 L ${s.x} ${s.y} A ${r} ${r} 0 ${lg} 1 ${e.x} ${e.y} Z`
}

function arcPath(r: number, a1: number, a2: number): string {
  const s = toXY(r, a1), e = toXY(r, a2)
  const lg = a2 - a1 > 180 ? 1 : 0
  return `M ${s.x} ${s.y} A ${r} ${r} 0 ${lg} 1 ${e.x} ${e.y}`
}

// ── Pie segments ──────────────────────────────────
const totalCount = computed(() => props.statusEntries.reduce((s, e) => s + e.count, 0))

const pieSegments = computed(() => {
  const total = totalCount.value
  if (total === 0) return []
  let angle = -90
  return props.statusEntries.map(entry => {
    const span = (entry.count / total) * 360
    const seg = { ...entry, d: piePath(PIE_R, angle, angle + span) }
    angle += span
    return seg
  })
})

// ── Partial arc ───────────────────────────────────
const partialArcD = computed(() => {
  if (partialRatio.value <= 0.001) return ''
  const r = ringR(fullLapsCount.value)
  return arcPath(r, -90, -90 + partialRatio.value * 360)
})

// ── Format helper ─────────────────────────────────
function fmtShort(v: number): string {
  if (!v) return '0 ₽'
  if (Math.abs(v) >= 1_000_000_000) return (v / 1_000_000_000).toFixed(1) + ' млрд ₽'
  if (Math.abs(v) >= 1_000_000) return (v / 1_000_000).toFixed(1) + ' млн ₽'
  if (Math.abs(v) >= 1_000) return (v / 1_000).toFixed(0) + ' тыс ₽'
  return v.toLocaleString('ru-RU') + ' ₽'
}
</script>

<style scoped>
.spw-wrap { display: flex; flex-direction: column; align-items: center; }
.spw-legend {
  display: flex; flex-wrap: wrap; justify-content: center;
  gap: 4px 12px; margin-top: 6px;
}
.spw-legend-item {
  display: flex; align-items: center; gap: 5px;
  cursor: pointer; font-size: 12px;
}
.spw-dot {
  width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0;
}
.spw-dot--wish {
  background: #F59E0B;
  border-radius: 2px;
}
.spw-lbl { color: var(--crm-text-muted, #6B7280); }
</style>
