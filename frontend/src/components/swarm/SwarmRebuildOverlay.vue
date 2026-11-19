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

        <!-- Figma рамки поверх реальных элементов страницы -->
        <div
          v-for="item in renderedItems"
          :key="item.id"
          class="gala-swarm-item"
          :class="[
            item.snapped ? 'gala-swarm-item--snapped' : 'gala-swarm-item--draft',
            { 'gala-swarm-item--accent': item.accent },
          ]"
          :style="item.boxStyle"
        >
          <template v-if="item.showHandles && !item.snapped">
            <span class="gala-swarm-handle gala-swarm-handle--tl" />
            <span class="gala-swarm-handle gala-swarm-handle--tr" />
            <span class="gala-swarm-handle gala-swarm-handle--bl" />
            <span class="gala-swarm-handle gala-swarm-handle--br" />
            <span class="gala-swarm-size-tag">{{ item.sizeHint }}</span>
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
  isSwarmDisabled, isSwarmPreview, isSwarmVisible, startSwarmPreview, swarmLiveDomMode, swarmPreviewRunId, swarmTargetPath,
} from '../../composables/useLongWait'
import { isLoggedIn } from '../../composables/useAuthFlag'
import { cacheLiveRouteSnapshot, getCachedRouteSnapshot, snapshotLiveWorkspace } from './swarmDomSnapshot'
import { computeActiveGuides, computeRenderedItems, computeRulerTicks, computeTargetCursors } from './swarmEngine'
import { SWARM_AGENTS, type SwarmItem, type SwarmTool } from './swarmTypes'
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
  if (isSwarmDisabled.value && !isSwarmPreview.value) return false
  if (!isSwarmVisible.value || isGameOpen.value) return false
  if (isSwarmPreview.value) return true
  if (suppressedByDialog.value) return false
  if (PUBLIC_PATHS.includes(activePath.value) && !(isSwarmBooting.value && isLoggedIn())) return false
  return true
})

const activeItems = computed(() => liveItems.value || [])
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

const completingStartTime = ref(0)
let domObserver: MutationObserver | null = null
let scanDebounceTimer: number | null = null

const elapsedMs = computed(() => {
  const raw = Math.max(0, nowMs.value - startTimestamp.value)
  if (!isSwarmCompleting.value) return raw
  if (completingStartTime.value === 0) {
    completingStartTime.value = nowMs.value
  }
  return raw + (nowMs.value - completingStartTime.value) * 2.2
})
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

function applyRebuildStylesToElements() {
  if (!activeItems.value || !activeItems.value.length) return
  for (const item of activeItems.value) {
    if (item.el) {
      item.el.classList.add('gala-swarm-target')
      item.el.style.transition = 'opacity 0.28s cubic-bezier(0.2, 0.8, 0.3, 1), transform 0.28s cubic-bezier(0.2, 0.8, 0.3, 1)'
      item.el.style.opacity = '0.2'
      item.el.style.transform = 'scale(0.99)'
    }
  }
}

function restoreAllElements() {
  if (typeof document === 'undefined') return
  document.querySelectorAll<HTMLElement>('.gala-swarm-target').forEach((el) => {
    el.style.opacity = ''
    el.style.transform = ''
    el.style.transition = ''
    el.classList.remove('gala-swarm-target')
  })
}

function setupDomObserver(mainEl: HTMLElement | null) {
  if (domObserver) {
    domObserver.disconnect()
    domObserver = null
  }
  if (typeof MutationObserver === 'undefined' || !mainEl) return
  domObserver = new MutationObserver(() => {
    if (!showOverlay.value) return
    if (scanDebounceTimer !== null) cancelAnimationFrame(scanDebounceTimer)
    scanDebounceTimer = requestAnimationFrame(() => {
      scanDebounceTimer = null
      syncNewlyRenderedElements()
    })
  })
  domObserver.observe(mainEl, { childList: true, subtree: true })
}

function syncNewlyRenderedElements() {
  const mainEl = typeof document !== 'undefined' ? (document.querySelector('.v-main') as HTMLElement | null) : null
  if (!mainEl) return
  const currentSnap = snapshotLiveWorkspace(mainEl, isDark.value, isMobile.value)
  if (!currentSnap || !currentSnap.length) return

  const existingEls = new Set((liveItems.value || []).map((it) => it.el).filter(Boolean))
  const newItems: SwarmItem[] = []

  for (const item of currentSnap) {
    if (item.el && !existingEls.has(item.el)) {
      newItems.push(item)
    }
  }

  if (newItems.length === 0) return

  const currentElapsed = Math.max(0, nowMs.value - startTimestamp.value)
  const agentLimit = isMobile.value ? 3 : SWARM_AGENTS.length
  const baseOffset = (liveItems.value?.length || 0) > 0 ? 50 : 20

  newItems.forEach((item, idx) => {
    if (item.el) {
      item.el.classList.add('gala-swarm-target')
      item.el.style.transition = 'opacity 0.28s cubic-bezier(0.2, 0.8, 0.3, 1), transform 0.28s cubic-bezier(0.2, 0.8, 0.3, 1)'
      item.el.style.opacity = '0.2'
      item.el.style.transform = 'scale(0.99)'
    }
    item.startMs = currentElapsed + baseOffset + idx * 45
    item.durationMs = 240
    item.cursorIndex = ((liveItems.value?.length || 0) + idx) % agentLimit
  })

  liveItems.value = [...(liveItems.value || []), ...newItems]
}

function tick(frameTime: number) {
  const dt = lastFrameTime ? Math.max(8, frameTime - lastFrameTime) : 16
  lastFrameTime = frameTime
  nowMs.value = frameTime
  updateSmoothCursors(dt)
  for (const item of renderedItems.value) {
    if (item.snapped && item.el && item.el.style.opacity !== '1') {
      item.el.style.opacity = '1'
      item.el.style.transform = 'none'
    }
  }

  if (isSwarmCompleting.value) {
    const allSnapped = activeItems.value.length === 0 || activeItems.value.every((it) => snappedIds.has(it.id))
    const timeSinceCompleting = completingStartTime.value ? frameTime - completingStartTime.value : 0
    if (allSnapped || timeSinceCompleting > 750) {
      if (!completePlayed) {
        completePlayed = true
        playSwarmCompleteSound()
      }
      stopLoop()
      return
    }
  }

  if (showOverlay.value) rafId = requestAnimationFrame(tick)
  else rafId = null
}

function captureIfLiveMode() {
  const mainEl = typeof document !== 'undefined' ? (document.querySelector('.v-main') as HTMLElement | null) : null
  const live = snapshotLiveWorkspace(mainEl, isDark.value, isMobile.value)
  if (live && live.length > 0) {
    liveItems.value = live
    applyRebuildStylesToElements()
    return
  }
  const cached = getCachedRouteSnapshot(activePath.value, isMobile.value)
  if (cached && cached.length > 0) {
    liveItems.value = cached
    return
  }
  liveItems.value = []
}

function startLoop() {
  if (rafId !== null) cancelAnimationFrame(rafId)
  startTimestamp.value = performance.now()
  nowMs.value = startTimestamp.value
  lastFrameTime = startTimestamp.value
  completingStartTime.value = 0
  smoothCursors.value = {}
  snappedIds.clear()
  completePlayed = false
  applyRebuildStylesToElements()
  const mainEl = typeof document !== 'undefined' ? (document.querySelector('.v-main') as HTMLElement | null) : null
  setupDomObserver(mainEl)
  rafId = requestAnimationFrame(tick)
}

function stopLoop() {
  if (domObserver) {
    domObserver.disconnect()
    domObserver = null
  }
  if (scanDebounceTimer !== null) {
    cancelAnimationFrame(scanDebounceTimer)
    scanDebounceTimer = null
  }
  restoreAllElements()
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
