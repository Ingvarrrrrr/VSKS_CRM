<template>
  <div class="canister-wrapper">
    <div class="canister-title">Топливный бюджет</div>
    <div class="canister-svg-container">
      <svg
        viewBox="0 0 100 150"
        class="canister-svg"
        xmlns="http://www.w3.org/2000/svg"
        aria-label="Топливный бюджет"
      >
        <defs>
          <!-- Gradient for liquid -->
          <linearGradient :id="gradientId" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" :stop-color="liquidColorLight" stop-opacity="0.9" />
            <stop offset="100%" :stop-color="liquidColorDark" stop-opacity="1" />
          </linearGradient>

          <!-- Canister shape clip -->
          <clipPath :id="canisterClipId">
            <!-- Canister body -->
            <rect x="12" y="20" width="76" height="118" rx="8" ry="8" />
            <!-- Canister nozzle -->
            <rect x="32" y="12" width="24" height="12" rx="3" ry="3" />
          </clipPath>

          <!-- Liquid level clip — wave path clipping the fill rect -->
          <clipPath :id="liquidClipId">
            <path :d="wavePath" />
          </clipPath>
        </defs>

        <!-- Canister nozzle body -->
        <rect
          x="32" y="12" width="24" height="12" rx="3" ry="3"
          fill="none"
          :stroke="outlineColor"
          stroke-width="2"
        />
        <!-- Nozzle cap -->
        <rect
          x="38" y="8" width="12" height="6" rx="2" ry="2"
          fill="none"
          :stroke="outlineColor"
          stroke-width="2"
        />
        <!-- Canister outline -->
        <rect
          x="12" y="20" width="76" height="118" rx="8" ry="8"
          fill="none"
          :stroke="outlineColor"
          stroke-width="2.5"
        />

        <!-- Handle left -->
        <path
          d="M 12 50 Q 4 50 4 60 Q 4 70 12 70"
          fill="none"
          :stroke="outlineColor"
          stroke-width="2"
          stroke-linecap="round"
        />

        <!-- Liquid fill — clipped by canister shape first, then wave path -->
        <g :clip-path="`url(#${canisterClipId})`">
          <rect
            x="12" y="20" width="76" height="118"
            :fill="`url(#${gradientId})`"
            :clip-path="`url(#${liquidClipId})`"
            class="liquid-rect"
          />
        </g>

        <!-- Tick marks (25%, 50%, 75%) -->
        <g :stroke="tickColor" stroke-width="1" opacity="0.5">
          <line x1="82" :y1="tickY(0.75)" x2="88" :y2="tickY(0.75)" />
          <line x1="82" :y1="tickY(0.50)" x2="88" :y2="tickY(0.50)" />
          <line x1="82" :y1="tickY(0.25)" x2="88" :y2="tickY(0.25)" />
        </g>

        <!-- Percent label inside canister (large) -->
        <text
          x="50" y="78"
          text-anchor="middle"
          dominant-baseline="middle"
          font-size="18"
          font-weight="bold"
          :fill="labelColor"
          class="canister-label-pct"
        >{{ displayPct }}%</text>

        <!-- Liters label inside canister (smaller) -->
        <text
          x="50" y="96"
          text-anchor="middle"
          dominant-baseline="middle"
          font-size="8"
          :fill="labelColorSub"
          class="canister-label-liters"
        >{{ liters.toLocaleString('ru') }} л / {{ budget.toLocaleString('ru') }} л</text>
      </svg>
    </div>

    <!-- Period label below canister -->
    <div class="canister-period">{{ periodLabel }}</div>

    <!-- Status bar -->
    <div class="canister-status">
      <span class="canister-status-dot" :style="{ background: liquidColorDark }" />
      <span class="canister-status-text">{{ statusText }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'

const props = defineProps<{
  /** 0..1 fill fraction (clamped automatically) */
  level: number
  /** Spent litres */
  liters: number
  /** Budget in litres */
  budget: number
  /** Human-readable period, e.g. "Май 2026" */
  periodLabel: string
}>()

// ── Unique IDs to avoid SVG id collisions when multiple instances rendered ──
const uid = Math.random().toString(36).slice(2, 8)
const gradientId = `canister-grad-${uid}`
const canisterClipId = `canister-clip-${uid}`
const liquidClipId = `liquid-clip-${uid}`

// ── Clamp level 0..1 (Lesson 2026-04-19 clampScore) ──
const safeLevel = computed<number>(() => {
  const v = props.level
  if (typeof v !== 'number' || isNaN(v)) return 0
  return Math.min(1, Math.max(0, v))
})

const displayPct = computed(() => Math.round(safeLevel.value * 100))

// ── SVG geometry ──
const CANISTER_TOP = 20      // rect y start
const CANISTER_BOTTOM = 138  // rect y end (20 + 118)
const CANISTER_LEFT = 12
const CANISTER_RIGHT = 88    // 12 + 76

/** Pixel Y position of liquid surface (top) */
const fillY = computed(() =>
  CANISTER_BOTTOM - (CANISTER_BOTTOM - CANISTER_TOP) * safeLevel.value
)

/** Wave amplitude shrinks at extremes to avoid clipping artefacts */
const waveAmp = computed(() => {
  const lv = safeLevel.value
  if (lv < 0.05 || lv > 0.95) return 1
  if (lv < 0.15 || lv > 0.85) return 2
  return 4
})

/**
 * wavePath = closed shape from wave-top down to canister bottom.
 * The liquid-clip clips the fill rect, so only the area below the wave is filled.
 * Animation: wave-sway shifts the fill rect horizontally → wave appears to move.
 *
 * Mental check for level=0.5: fillY ≈ 79 (centre). Wave bumps ±4px around y=79.
 * For level=0.1: fillY ≈ 127 (near bottom), amp=2. Still inside canister. ✓
 * For level=0.9: fillY ≈ 31 (near top),    amp=2. Still inside canister. ✓
 */
const wavePath = computed(() => {
  const y = fillY.value
  const a = waveAmp.value
  const x0 = CANISTER_LEFT
  const x4 = CANISTER_RIGHT
  // Two sinusoidal bumps across the 76px width
  const x1 = x0 + 19  // Q control
  const x2 = x0 + 38  // midpoint
  const x3 = x0 + 57  // Q control

  return [
    `M ${x0} ${y + a}`,
    `Q ${x1} ${y - a} ${x2} ${y + a}`,
    `Q ${x3} ${y - a} ${x4} ${y + a}`,
    `L ${x4} ${CANISTER_BOTTOM}`,
    `L ${x0} ${CANISTER_BOTTOM}`,
    'Z',
  ].join(' ')
})

/** Y position of tick marks (25/50/75%) */
function tickY(fraction: number): number {
  return CANISTER_BOTTOM - (CANISTER_BOTTOM - CANISTER_TOP) * fraction
}

// ── Colours ──
const liquidColorDark = computed(() => {
  const lv = safeLevel.value
  if (lv < 0.15) return '#ef4444'   // red — critical
  if (lv < 0.30) return '#f97316'   // orange — warning
  return '#1976d2'                   // blue — normal
})

const liquidColorLight = computed(() => {
  const lv = safeLevel.value
  if (lv < 0.15) return '#fca5a5'
  if (lv < 0.30) return '#fdba74'
  return '#64b5f6'
})

const outlineColor = '#546e7a'
const tickColor = '#90a4ae'

/** Label text is white when submerged (level>50%), dark otherwise */
const labelColor = computed(() =>
  safeLevel.value > 0.5 ? '#ffffff' : '#1e293b'
)
const labelColorSub = computed(() =>
  safeLevel.value > 0.5 ? 'rgba(255,255,255,0.85)' : 'rgba(30,41,59,0.7)'
)

const statusText = computed(() => {
  const lv = safeLevel.value
  if (lv < 0.15) return 'Критично — бюджет почти исчерпан'
  if (lv < 0.30) return 'Осторожно — остаток менее 30%'
  return 'Норма'
})

// ── Guard: warn on invalid input in dev ──
watch(() => props.level, (v) => {
  if (process.env.NODE_ENV !== 'production' && (typeof v !== 'number' || isNaN(v))) {
    console.warn('[FuelCanisterWidget] level prop is NaN/invalid, defaulting to 0')
  }
}, { immediate: true })
</script>

<style scoped>
.canister-wrapper {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 100%;
  max-width: 300px;
  margin: 0 auto;
  padding: 8px 0;
}

.canister-title {
  font-size: 13px;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), 0.7);
  letter-spacing: 0.5px;
  text-transform: uppercase;
  margin-bottom: 8px;
}

.canister-svg-container {
  width: 100%;
  max-width: 220px;
}

.canister-svg {
  width: 100%;
  height: auto;
  display: block;
  filter: drop-shadow(0 4px 12px rgba(0, 0, 0, 0.18));
}

/* Liquid wave sway animation */
.liquid-rect {
  animation: wave-sway 2.5s ease-in-out infinite;
  transform-origin: 50px 79px;
}

@keyframes wave-sway {
  0%, 100% {
    transform: scaleX(1) translateX(0px);
  }
  33% {
    transform: scaleX(1.05) translateX(-2px);
  }
  66% {
    transform: scaleX(0.97) translateX(2px);
  }
}

/* Smooth fill transition when level prop changes */
.canister-label-pct {
  transition: fill 0.4s ease;
  font-family: 'Roboto', sans-serif;
}

.canister-label-liters {
  font-family: 'Roboto', sans-serif;
}

.canister-period {
  margin-top: 10px;
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  font-weight: 500;
}

.canister-status {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.7);
}

.canister-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.canister-status-text {
  font-weight: 500;
}
</style>
