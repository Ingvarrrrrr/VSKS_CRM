<template>
  <Teleport to="body">
    <SwarmPreviewControls v-if="showPreviewControls" :auto-open="hasPreviewQuery" />
    <div
      v-if="showOverlay"
      ref="overlayRef"
      class="gala-swarm-overlay"
      :class="{
        'gala-swarm-overlay--dark': isDark,
        'gala-swarm-overlay--completing': isSwarmCompleting,
      }"
      :style="overlayStyle"
      aria-live="polite"
      aria-label="Сборка раздела"
    >
      <div class="gala-swarm-canvas">
        <!-- Пиксельные линейки как в графическом редакторе -->
        <div v-if="!isMobile" class="gala-swarm-ruler-top">
          <div
            v-for="t in rulers.xTicks"
            :key="`tx-${t.pos}`"
            class="gala-swarm-tick-x"
            :style="{ left: `${t.pos}px`, height: t.major ? '10px' : '5px' }"
          >
            <span v-if="t.label" class="gala-swarm-tick-lbl">{{ t.label }}</span>
          </div>
        </div>
        <div v-if="!isMobile" class="gala-swarm-ruler-left">
          <div
            v-for="t in rulers.yTicks"
            :key="`ty-${t.pos}`"
            class="gala-swarm-tick-y"
            :style="{ top: `${t.pos}px`, width: t.major ? '10px' : '5px' }"
          >
            <span v-if="t.label" class="gala-swarm-tick-lbl gala-swarm-tick-lbl--y">{{ t.label }}</span>
          </div>
        </div>

        <!-- Логотип GALA на холодном старте -->
        <div v-if="isFullScreenMode" class="gala-swarm-boot-brand">
          <svg viewBox="0 0 44 44" width="22" height="22" fill="none">
            <path d="M30 8 L10 8 L10 36 L30 36 L30 24 L21 24" stroke="currentColor" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
          <span class="gala-swarm-boot-word">GA<span class="gala-swarm-boot-l">L</span>A</span>
        </div>

        <!-- Направляющие линии выравнивания -->
        <template v-if="!isSwarmCompleting">
          <div
            v-for="g in activeGuides"
            :key="g.id"
            :class="g.axis === 'x' ? 'gala-swarm-guide-x' : 'gala-swarm-guide-y'"
            :style="g.axis === 'x' ? { top: `${g.pos}px`, borderColor: g.color } : { left: `${g.pos}px`, borderColor: g.color }"
          >
            <span class="gala-swarm-guide-pill">{{ g.label }}</span>
          </div>
        </template>

        <!-- SVG слой векторов ⌥-дублирования -->
        <svg v-if="!isSwarmCompleting && dupVectors.length" class="gala-swarm-vectors">
          <line
            v-for="v in dupVectors"
            :key="v.id"
            :x1="v.x1" :y1="v.y1" :x2="v.x2" :y2="v.y2"
            stroke="#2563eb" stroke-width="1.5" stroke-dasharray="4 3" opacity="0.78"
          />
        </svg>
        <div
          v-for="v in dupVectors"
          :key="`lbl-${v.id}`"
          class="gala-swarm-dup-tag"
          :style="{ left: `${Math.round((v.x1 + v.x2) / 2)}px`, top: `${Math.round((v.y1 + v.y2) / 2) - 10}px` }"
        >
          {{ v.distLabel }}
        </div>

        <!-- Плотные элементы интерфейса -->
        <div
          v-for="item in renderedItems"
          :key="item.id"
          class="gala-swarm-item"
          :class="[
            `gala-swarm-item--${item.kind}`,
            item.snapped ? 'gala-swarm-item--snapped' : 'gala-swarm-item--draft',
            { 'gala-swarm-item--accent': item.accent },
          ]"
          :style="item.boxStyle"
        >
          <template v-if="item.showHandles">
            <span class="gala-swarm-handle gala-swarm-handle--tl" />
            <span class="gala-swarm-handle gala-swarm-handle--tr" />
            <span class="gala-swarm-handle gala-swarm-handle--bl" />
            <span class="gala-swarm-handle gala-swarm-handle--br" />
            <span class="gala-swarm-size-tag">{{ item.sizeHint }}</span>
          </template>

          <template v-if="item.showContent && item.kind !== 'divider'">
            <div v-if="item.kind === 'heading'" class="gala-swarm-inner gala-swarm-inner--col" style="padding:0">
              <div class="gala-swarm-heading-txt">
                {{ item.typedText }}<span v-if="item.isTyping" class="gala-swarm-caret" />
              </div>
              <span v-if="item.subtext" style="font-size:11px;opacity:0.62">{{ item.subtext }}</span>
            </div>

            <div v-else-if="item.kind === 'kpi'" class="gala-swarm-inner gala-swarm-inner--col">
              <span class="gala-swarm-kpi-val">{{ item.subtext || '—' }}</span>
              <span style="font-size:11px;opacity:0.72">{{ item.typedText }}<span v-if="item.isTyping" class="gala-swarm-caret" /></span>
            </div>

            <div v-else-if="item.kind === 'table-head' || item.kind === 'table-row'" class="gala-swarm-inner">
              <div
                class="gala-swarm-cells"
                :style="{
                  gridTemplateColumns: `repeat(${(item.cells?.length || 4) + (item.statusText ? 1 : 0)}, minmax(0, 1fr))`,
                  fontWeight: item.kind === 'table-head' ? 600 : 400,
                  opacity: item.kind === 'table-head' ? 0.78 : 0.94,
                }"
              >
                <span
                  v-for="(cell, cIdx) in item.cells || [item.typedText]"
                  :key="cIdx"
                  class="text-truncate"
                  style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1 1 0"
                >
                  {{ cIdx === 0 && item.isTyping ? item.typedText : cell }}
                </span>
                <span v-if="item.statusText" class="gala-swarm-status-badge" :style="{ backgroundColor: item.statusColor || '#c2620a' }">
                  {{ item.statusText }}
                </span>
              </div>
            </div>

            <div v-else-if="item.kind === 'chart'" class="gala-swarm-inner gala-swarm-inner--col">
              <span style="font-size:12px;font-weight:600">{{ item.typedText }}</span>
              <svg viewBox="0 0 400 140" style="width:100%;flex:1" preserveAspectRatio="none">
                <path
                  d="M 10 120 Q 75 95, 130 78 T 250 56 T 390 18"
                  fill="none" :stroke="isDark ? '#fb923c' : '#c2620a'" stroke-width="2.5" stroke-linecap="round"
                  :stroke-dasharray="440" :stroke-dashoffset="Math.max(0, 440 * (1 - item.detailProgress))"
                />
                <path
                  d="M 10 126 L 90 112 L 175 114 L 280 86 L 390 62"
                  fill="none" :stroke="isDark ? '#60a5fa' : '#2563eb'" stroke-width="2" stroke-dasharray="5 4" opacity="0.72"
                />
              </svg>
            </div>

            <div v-else-if="item.kind === 'card'" class="gala-swarm-inner gala-swarm-inner--col">
              <template v-if="item.cells && item.cells.length >= 6">
                <div style="display:flex;justify-content:space-between;align-items:center;width:100%;gap:4px">
                  <span style="font-size:12px;font-weight:700;line-height:1.2" class="text-truncate">{{ item.typedText }}</span>
                  <span style="font-size:9px;opacity:0.6;letter-spacing:1px;white-space:nowrap">✎ ⚙ 📄 📊 📋 ↗ 🗑</span>
                </div>
                <div style="display:flex;flex-direction:column;align-items:center;text-align:center;margin:2px 0">
                  <span style="font-size:15px;font-weight:700;line-height:1.2">{{ item.subtext }}</span>
                  <span style="font-size:9px;opacity:0.6">Бюджет ВСКС (расчёт)</span>
                </div>
                <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:2px;font-size:9px;text-align:center;width:100%">
                  <div>
                    <div style="opacity:0.6;font-size:8px">Запланировано</div>
                    <div style="font-weight:600" class="text-truncate">{{ item.cells[0] }}</div>
                  </div>
                  <div>
                    <div style="opacity:0.6;font-size:8px">Заказано</div>
                    <div style="font-weight:600" class="text-truncate">{{ item.cells[1] }}</div>
                  </div>
                  <div>
                    <div style="opacity:0.6;font-size:8px">Оплачено</div>
                    <div style="font-weight:600" class="text-truncate">{{ item.cells[2] }}</div>
                  </div>
                </div>
                <div style="width:100%;height:5px;border-radius:3px;background:linear-gradient(90deg, #facc15 65%, #38bdf8 65% 85%, #22c55e 85%);margin:2px 0" />
                <div style="display:flex;justify-content:space-between;align-items:center;width:100%;font-size:9px">
                  <span class="gala-swarm-status-badge" :style="{ backgroundColor: item.statusColor || '#16a34a', fontSize: '8px', padding: '1px 4px' }">
                    {{ item.cells[3] }}
                  </span>
                  <span style="opacity:0.75" class="text-truncate">🏛 {{ item.cells[4] }}</span>
                </div>
                <div style="display:flex;justify-content:space-between;align-items:center;width:100%;font-size:9px;opacity:0.8">
                  <span class="text-truncate">{{ item.cells[5] }}</span>
                  <span style="color:#22c55e;font-size:8px;font-weight:600">● ФЭО</span>
                </div>
              </template>
              <template v-else>
                <div style="display:flex;justify-content:space-between;align-items:center;width:100%;gap:4px">
                  <span v-if="item.typedText" style="font-size:12px;font-weight:600" class="text-truncate">{{ item.typedText }}</span>
                  <span v-if="item.statusText" class="gala-swarm-status-badge" :style="{ backgroundColor: item.statusColor || '#16a34a', fontSize: '9px', padding: '1px 5px' }">
                    {{ item.statusText }}
                  </span>
                </div>
                <span v-if="item.subtext" style="font-size:11px;opacity:0.75" class="text-truncate">{{ item.subtext }}</span>
                <span v-if="item.rightText" style="font-size:10px;font-family:var(--font-mono,monospace);opacity:0.65" class="text-truncate">{{ item.rightText }}</span>
              </template>
            </div>

            <div v-else class="gala-swarm-inner">
              <span class="text-truncate" :style="{ fontWeight: item.kind.startsWith('btn') ? 600 : 500 }">
                {{ item.kind === 'input' ? `🔍 ${item.typedText}` : item.typedText }}<span v-if="item.isTyping" class="gala-swarm-caret" />
              </span>
              <span v-if="item.rightText" style="font-family:var(--font-mono,monospace);font-size:11px;opacity:0.82">{{ item.rightText }}</span>
            </div>
          </template>
        </div>

        <!-- Курсоры GALA (по завершению исчезают на месте) -->
        <div
          v-for="cursor in cursorStates"
          :key="cursor.id"
          class="gala-swarm-cursor"
          :class="{ 'gala-swarm-cursor--vanishing': isSwarmCompleting }"
          :style="{
            transform: isSwarmCompleting
              ? `translate3d(${cursor.px}px, ${cursor.py}px, 0) scale(0.72)`
              : `translate3d(${cursor.px}px, ${cursor.py}px, 0)`,
            opacity: isSwarmCompleting ? 0 : cursor.opacity,
          }"
        >
          <svg width="17" height="19" viewBox="0 0 18 20" fill="none">
            <path d="M2 1.5L15.5 10.5L9.2 12L6.2 18.2L2 1.5Z" :fill="cursor.color" :stroke="isDark ? '#0f0e0c' : '#ffffff'" stroke-width="1.5" stroke-linejoin="round" />
          </svg>
          <span class="gala-swarm-cursor-pill" :style="{ backgroundColor: cursor.color }">
            <span>{{ cursor.name }}</span>
            <span class="gala-swarm-tool-mark">{{ TOOL_MARK[cursor.activeTool] }}</span>
          </span>
        </div>

        <!-- Плашка статуса внизу слева -->
        <div v-if="!isSwarmCompleting" class="gala-swarm-status-pill" @pointerdown.stop @mousedown.stop>
          <span class="gala-swarm-pulse" />
          <span>Сборка: <strong>{{ activeTitle }}</strong></span>
          <button type="button" class="gala-swarm-pill-btn" :title="soundOn ? 'Выключить звук' : 'Включить тихий звук'" @click="toggleSound">
            {{ soundOn ? '🔊' : '🔇' }}
          </button>
          <button type="button" class="gala-swarm-pill-btn" title="Скрыть (Esc)" @click="dismissSwarm">Скрыть</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useTheme } from 'vuetify'
import {
  dismissSwarm, ensureLongWaitListener, isGameOpen, isSwarmBooting, isSwarmCompleting,
  isSwarmPreview, isSwarmVisible, startSwarmPreview, swarmLiveDomMode, swarmPreviewRunId, swarmTargetPath,
} from '../../composables/useLongWait'
import { isLoggedIn } from '../../composables/useAuthFlag'
import { buildSwarmBlueprint, describeRouteForSwarm } from './swarmBlueprints'
import { cacheLiveRouteSnapshot, getCachedRouteSnapshot } from './swarmDomSnapshot'
import { computeActiveGuides, computeRenderedItems, computeRulerTicks, computeTargetCursors } from './swarmEngine'
import type { SwarmItem, SwarmTool } from './swarmTypes'
import { isSwarmSoundEnabled, playSwarmCompleteSound, playSwarmSnapSound, setSwarmSoundEnabled } from './swarmAudio'
import SwarmPreviewControls from './SwarmPreviewControls.vue'
import './swarm-overlay.css'

const PUBLIC_PATHS = ['/', '/login', '/register', '/verify-email', '/reset-password', '/consent-required']
const TOOL_MARK: Record<SwarmTool, string> = { rect: '▭', type: 'I', dup: '⌥', pen: '✒' }

const route = useRoute()
const theme = useTheme()
const nowMs = ref(0)
const startTimestamp = ref(0)
const soundOn = ref(isSwarmSoundEnabled())
const suppressedByDialog = ref(false)
const liveItems = ref<SwarmItem[] | null>(null)
const canvasSize = ref({ top: 0, left: 0, width: 1200, height: 760, fullScreen: true })
const smoothCursors = ref<Record<string, { x: number; y: number }>>({})

let rafId: number | null = null
let lastFrameTime = 0
let resizeObserver: ResizeObserver | null = null
const snappedIds = new Set<string>()
let completePlayed = false

const isDark = computed(() => theme.global.name.value === 'dark')
const isMobile = computed(() => canvasSize.value.width < 768)
const activePath = computed(() => (swarmTargetPath.value && swarmTargetPath.value !== '/' ? swarmTargetPath.value : route.path))
const isFullScreenMode = computed(() => canvasSize.value.fullScreen || isSwarmBooting.value)
const isLocalhost = typeof window !== 'undefined' && ['localhost', '127.0.0.1'].includes(window.location.hostname)

const hasPreviewQuery = computed(() => {
  if (typeof window === 'undefined') return false
  return new URLSearchParams(window.location.search).get('swarm_preview') === '1' || route.query.swarm_preview === '1'
})

const showPreviewControls = computed(() => hasPreviewQuery.value || isLocalhost)

const showOverlay = computed(() => {
  if (!isSwarmVisible.value || isGameOpen.value) return false
  if (isSwarmPreview.value) return true
  if (suppressedByDialog.value) return false
  if (PUBLIC_PATHS.includes(activePath.value) && !(isSwarmBooting.value && isLoggedIn())) return false
  return true
})

const activeTitle = computed(() => describeRouteForSwarm(activePath.value).title)
const blueprint = computed(() =>
  buildSwarmBlueprint(activePath.value, isMobile.value, isSwarmBooting.value, canvasSize.value.width, canvasSize.value.height),
)
const activeItems = computed(() => liveItems.value || blueprint.value.items)
const rulers = computed(() => computeRulerTicks(canvasSize.value.width, canvasSize.value.height))
const overlayStyle = computed(() => {
  const { top, left, width, height, fullScreen } = canvasSize.value
  return fullScreen || isSwarmBooting.value
    ? { inset: '0px', zIndex: 9500 }
    : { top: `${top}px`, left: `${left}px`, width: `${width}px`, height: `${height}px`, zIndex: 900 }
})

function measureWorkspace() {
  if (typeof window === 'undefined') return
  const vw = window.innerWidth || 1200
  const vh = window.innerHeight || 760
  const mainEl = document.querySelector('.v-main') as HTMLElement | null
  if (!mainEl || isSwarmBooting.value || PUBLIC_PATHS.includes(route.path)) {
    canvasSize.value = { top: 0, left: 0, width: vw, height: vh, fullScreen: true }
    return
  }
  const rect = mainEl.getBoundingClientRect()
  const cs = getComputedStyle(mainEl)
  const pt = parseFloat(cs.paddingTop) || 0
  const pl = parseFloat(cs.paddingLeft) || 0
  canvasSize.value = {
    top: rect.top + pt, left: rect.left + pl,
    width: Math.max(280, rect.width - pl - (parseFloat(cs.paddingRight) || 0)),
    height: Math.max(240, rect.height - pt - (parseFloat(cs.paddingBottom) || 0)),
    fullScreen: false,
  }
}

const elapsedMs = computed(() => (isSwarmCompleting.value ? 3200 : Math.max(0, nowMs.value - startTimestamp.value)))
const renderedItems = computed(() =>
  computeRenderedItems(activeItems.value, elapsedMs.value, isSwarmCompleting.value, snappedIds, (idx) => playSwarmSnapSound(idx)),
)
const activeGuides = computed(() => computeActiveGuides(renderedItems.value, isDark.value))
const dupVectors = computed(() =>
  renderedItems.value.filter((i) => i.dupVector).map((i) => ({ id: i.id, ...i.dupVector! })),
)
const targetCursors = computed(() =>
  computeTargetCursors(activeItems.value, elapsedMs.value, canvasSize.value.width, canvasSize.value.height, isMobile.value, isDark.value, isSwarmCompleting.value),
)
const cursorStates = computed(() =>
  targetCursors.value.map((c) => {
    const s = smoothCursors.value[c.id]
    return { ...c, px: Math.round(s ? s.x : c.rawX), py: Math.round(s ? s.y : c.rawY) }
  }),
)

function updateSmoothCursors(dtMs: number) {
  const factor = 1 - Math.exp(-Math.min(dtMs, 50) / 55)
  const next: Record<string, { x: number; y: number }> = {}
  for (const c of targetCursors.value) {
    const prev = smoothCursors.value[c.id]
    next[c.id] = prev ? { x: prev.x + (c.rawX - prev.x) * factor, y: prev.y + (c.rawY - prev.y) * factor } : { x: c.rawX, y: c.rawY }
  }
  smoothCursors.value = next
}

function tick(frameTime: number) {
  const dt = lastFrameTime ? Math.max(8, frameTime - lastFrameTime) : 16
  lastFrameTime = frameTime
  nowMs.value = frameTime
  updateSmoothCursors(dt)
  if (showOverlay.value && !isSwarmCompleting.value) rafId = requestAnimationFrame(tick)
  else rafId = null
}

function captureIfLiveMode() {
  const mainEl = typeof document !== 'undefined' ? (document.querySelector('.v-main') as HTMLElement | null) : null
  if (swarmLiveDomMode.value || (route.path === activePath.value && !isSwarmBooting.value)) {
    const live = cacheLiveRouteSnapshot(activePath.value, mainEl, isDark.value, isMobile.value)
    if (live) {
      liveItems.value = live
      return
    }
  }
  const cached = getCachedRouteSnapshot(activePath.value, isMobile.value)
  if (cached) {
    liveItems.value = cached
    return
  }
  liveItems.value = null
}

function startLoop() {
  if (rafId !== null) cancelAnimationFrame(rafId)
  startTimestamp.value = performance.now()
  nowMs.value = startTimestamp.value
  lastFrameTime = startTimestamp.value
  smoothCursors.value = {}
  snappedIds.clear()
  completePlayed = false
  rafId = requestAnimationFrame(tick)
}

function stopLoop() {
  if (rafId !== null) { cancelAnimationFrame(rafId); rafId = null }
}

function toggleSound() {
  soundOn.value = !soundOn.value
  setSwarmSoundEnabled(soundOn.value)
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && showOverlay.value && !isSwarmCompleting.value) {
    dismissSwarm()
  } else if (e.altKey && e.shiftKey && (e.code === 'KeyS' || e.key.toLowerCase() === 's' || e.key.toLowerCase() === 'ы')) {
    e.preventDefault()
    if (showOverlay.value) dismissSwarm()
    else startSwarmPreview(route.path, { liveDom: true })
  }
}

watch(showOverlay, (visible) => {
  if (visible) {
    try { ;(window as any).__galaStopBootSwarm?.() } catch {}
  }
})

watch(swarmPreviewRunId, () => {
  if (isSwarmVisible.value) {
    measureWorkspace()
    captureIfLiveMode()
    startLoop()
  }
})

watch(isSwarmVisible, (visible) => {
  if (visible) {
    const hasOpenDialog = !isSwarmBooting.value && !isSwarmPreview.value && typeof document !== 'undefined' && !!document.querySelector('.v-overlay--active .v-dialog')
    suppressedByDialog.value = hasOpenDialog
    if (!hasOpenDialog) {
      measureWorkspace()
      captureIfLiveMode()
      startLoop()
    }
  } else {
    suppressedByDialog.value = false
    liveItems.value = null
    stopLoop()
    setTimeout(() => {
      const mainEl = typeof document !== 'undefined' ? (document.querySelector('.v-main') as HTMLElement | null) : null
      cacheLiveRouteSnapshot(route.path, mainEl, isDark.value, isMobile.value)
    }, 280)
  }
}, { immediate: true })

watch(isSwarmCompleting, (completing) => {
  if (completing && !completePlayed && showOverlay.value) {
    completePlayed = true
    playSwarmCompleteSound()
    stopLoop()
  }
})

watch([() => route.path, isSwarmBooting], () => {
  if (isSwarmVisible.value) measureWorkspace()
})

onMounted(() => {
  ensureLongWaitListener()
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('resize', measureWorkspace)
  if (typeof ResizeObserver !== 'undefined') {
    const mainEl = document.querySelector('.v-main')
    if (mainEl) { resizeObserver = new ResizeObserver(measureWorkspace); resizeObserver.observe(mainEl) }
  }
  setTimeout(() => {
    const mainEl = typeof document !== 'undefined' ? (document.querySelector('.v-main') as HTMLElement | null) : null
    cacheLiveRouteSnapshot(route.path, mainEl, isDark.value, isMobile.value)
  }, 700)
})

onUnmounted(() => {
  stopLoop()
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('resize', measureWorkspace)
  resizeObserver?.disconnect()
})
</script>
