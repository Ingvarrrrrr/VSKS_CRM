// Единый источник состояния загрузки — слушает 'api-loading' из api.ts,
// навигацию роутера (загрузка чанков) и холодный старт (boot), переводя их
// в реактивные флаги для SwarmRebuildOverlay, AppBar-индикатора и PlayWhileWaiting
// (ПРАВИЛО №6 — один счётчик/источник правды на всё приложение).
//
//   isBusy            — true при активной загрузке, false через 500мс простоя
//   isLongWait        — true когда загрузка идёт непрерывно ≥ 2000мс подряд
//   isSwarmVisible    — true когда загрузка идёт ≥ 550мс (показываем сборку роем)
//   isSwarmCompleting — true в финальные 220мс: блоки дощёлкиваются, курсоры
//                       сразу исчезают на месте и оверлей прозрачно растворяется

import { readonly, ref } from 'vue'

const LONG_WAIT_THRESHOLD_MS = 2000
const CONTINUITY_GAP_MS = 400
const BUSY_OFF_DELAY_MS = 500

const SWARM_SHOW_DELAY_MS = 550
const SWARM_SETTLE_GAP_MS = 180
const SWARM_COMPLETING_MS = 220
const KEEP_ALIVE_QUIET_WINDOW_MS = 250
const SIM_NAV_DURATION_MS = 2600
const SIM_STORAGE_KEY = 'gala_swarm_sim_ms'

function readInitialSimFlag(): boolean {
  try {
    return typeof sessionStorage !== 'undefined' && sessionStorage.getItem(SIM_STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

const _isBusy = ref(false)
const _isLongWait = ref(false)
const _isSwarmVisible = ref(false)
const _isSwarmCompleting = ref(false)
const _isSwarmBooting = ref(false)
const _isGameOpen = ref(false)
const _swarmTargetPath = ref('/')
const _isSwarmPreview = ref(false)
const _swarmPreviewRunId = ref(0)
const _swarmLiveDomMode = ref(false)
const _swarmSimEnabled = ref(readInitialSimFlag())

export const isBusy = readonly(_isBusy)
export const isLongWait = readonly(_isLongWait)
export const isSwarmVisible = readonly(_isSwarmVisible)
export const isSwarmCompleting = readonly(_isSwarmCompleting)
export const isSwarmBooting = readonly(_isSwarmBooting)
export const isGameOpen = readonly(_isGameOpen)
export const swarmTargetPath = readonly(_swarmTargetPath)
export const isSwarmPreview = readonly(_isSwarmPreview)
export const swarmPreviewRunId = readonly(_swarmPreviewRunId)
export const swarmLiveDomMode = readonly(_swarmLiveDomMode)
export const swarmSimEnabled = readonly(_swarmSimEnabled)

let listenerInstalled = false
let inflightCount = 0
let routePending = false
let bootPending = false
let simPending = false

let seriesStartedAt: number | null = null
let lastZeroAt: number | null = null
let seriesDismissed = false
let seriesSuppressedByCache = false
let quietCacheWindowUntil = 0

let longWaitTimer: ReturnType<typeof setTimeout> | null = null
let busyOffTimer: ReturnType<typeof setTimeout> | null = null
let swarmShowTimer: ReturnType<typeof setTimeout> | null = null
let swarmSettleTimer: ReturnType<typeof setTimeout> | null = null
let swarmCompleteTimer: ReturnType<typeof setTimeout> | null = null
let swarmSimTimer: ReturnType<typeof setTimeout> | null = null

function clearTimer(refTimer: 'long' | 'busy' | 'show' | 'settle' | 'complete' | 'sim') {
  if (refTimer === 'long' && longWaitTimer !== null) {
    clearTimeout(longWaitTimer)
    longWaitTimer = null
  } else if (refTimer === 'busy' && busyOffTimer !== null) {
    clearTimeout(busyOffTimer)
    busyOffTimer = null
  } else if (refTimer === 'show' && swarmShowTimer !== null) {
    clearTimeout(swarmShowTimer)
    swarmShowTimer = null
  } else if (refTimer === 'settle' && swarmSettleTimer !== null) {
    clearTimeout(swarmSettleTimer)
    swarmSettleTimer = null
  } else if (refTimer === 'complete' && swarmCompleteTimer !== null) {
    clearTimeout(swarmCompleteTimer)
    swarmCompleteTimer = null
  } else if (refTimer === 'sim' && swarmSimTimer !== null) {
    clearTimeout(swarmSimTimer)
    swarmSimTimer = null
  }
}

function clearAllTimers() {
  clearTimer('long')
  clearTimer('busy')
  clearTimer('show')
  clearTimer('settle')
  clearTimer('complete')
  clearTimer('sim')
}

function hideSwarmImmediately() {
  clearTimer('show')
  clearTimer('settle')
  clearTimer('complete')
  _isSwarmVisible.value = false
  _isSwarmCompleting.value = false
}

function triggerSwarmComplete() {
  clearTimer('show')
  clearTimer('settle')
  clearTimer('complete')
  if (!_isSwarmVisible.value) return
  _isSwarmCompleting.value = true
  swarmCompleteTimer = setTimeout(() => {
    swarmCompleteTimer = null
    _isSwarmVisible.value = false
    _isSwarmCompleting.value = false
  }, SWARM_COMPLETING_MS)
}

function scheduleSwarmShow(delayMs: number) {
  clearTimer('show')
  if (seriesDismissed || seriesSuppressedByCache) return
  if (_isSwarmVisible.value) {
    _isSwarmCompleting.value = false
    return
  }
  swarmShowTimer = setTimeout(() => {
    swarmShowTimer = null
    if (!seriesDismissed && !seriesSuppressedByCache && (inflightCount > 0 || routePending || bootPending || simPending)) {
      _isSwarmCompleting.value = false
      _isSwarmVisible.value = true
    }
  }, Math.max(0, delayMs))
}

function endSeriesAndGoIdle() {
  seriesStartedAt = null
  lastZeroAt = null
  seriesDismissed = false
  seriesSuppressedByCache = false
  clearTimer('long')
  clearTimer('busy')
  clearTimer('show')
  _isBusy.value = false
  _isLongWait.value = false
  if (_isSwarmVisible.value && !_isSwarmCompleting.value) {
    triggerSwarmComplete()
  }
}

function getBootElapsedMs(): number {
  if (typeof window === 'undefined') return 0
  const started = (window as any).__galaBootStart
  return typeof started === 'number' ? Math.max(0, Date.now() - started) : 0
}

function reconcileActiveLoading() {
  const active = inflightCount > 0 || routePending || bootPending || simPending
  const now = Date.now()

  if (active) {
    clearTimer('busy')
    clearTimer('settle')
    clearTimer('complete')
    _isBusy.value = true

    if (_isSwarmVisible.value && _isSwarmCompleting.value) {
      // Во время фазы растворения начался новый запрос — продолжаем сборку без мигания.
      _isSwarmCompleting.value = false
    }

    if (seriesStartedAt === null) {
      seriesStartedAt = now
      seriesDismissed = false
      seriesSuppressedByCache =
        !routePending && !bootPending && quietCacheWindowUntil > 0 && now <= quietCacheWindowUntil

      clearTimer('long')
      longWaitTimer = setTimeout(() => {
        _isLongWait.value = true
        longWaitTimer = null
      }, LONG_WAIT_THRESHOLD_MS)

      const bootOffset = bootPending ? getBootElapsedMs() : 0
      scheduleSwarmShow(SWARM_SHOW_DELAY_MS - bootOffset)
    } else if (lastZeroAt !== null && now - lastZeroAt >= CONTINUITY_GAP_MS) {
      seriesStartedAt = now
      seriesDismissed = false
      seriesSuppressedByCache =
        !routePending && !bootPending && quietCacheWindowUntil > 0 && now <= quietCacheWindowUntil
      _isLongWait.value = false

      clearTimer('long')
      longWaitTimer = setTimeout(() => {
        _isLongWait.value = true
        longWaitTimer = null
      }, LONG_WAIT_THRESHOLD_MS)

      scheduleSwarmShow(SWARM_SHOW_DELAY_MS)
    } else if (!seriesDismissed && !seriesSuppressedByCache && !_isSwarmVisible.value && swarmShowTimer === null) {
      const elapsed = now - seriesStartedAt + (bootPending ? getBootElapsedMs() : 0)
      scheduleSwarmShow(SWARM_SHOW_DELAY_MS - elapsed)
    }

    lastZeroAt = null
  } else {
    lastZeroAt = now
    clearTimer('show')

    if (_isSwarmVisible.value && !_isSwarmCompleting.value && swarmSettleTimer === null) {
      swarmSettleTimer = setTimeout(() => {
        swarmSettleTimer = null
        if (inflightCount === 0 && !routePending && !bootPending && !simPending) {
          triggerSwarmComplete()
        }
      }, SWARM_SETTLE_GAP_MS)
    }

    clearTimer('busy')
    busyOffTimer = setTimeout(() => {
      busyOffTimer = null
      endSeriesAndGoIdle()
    }, BUSY_OFF_DELAY_MS)
  }
}

function onApiLoading(e: Event) {
  const count = (e as CustomEvent).detail?.count ?? 0
  inflightCount = Math.max(0, Number(count) || 0)
  reconcileActiveLoading()
}

/** Навешивает слушатель 'api-loading' один раз на всё приложение. Безопасно звать из нескольких компонентов. */
export function ensureLongWaitListener(): void {
  if (listenerInstalled) return
  listenerInstalled = true
  window.addEventListener('api-loading', onApiLoading)
}

/** Управляет фазой холодного старта приложения (авторизованный вход / F5). */
export function setSwarmBooting(active: boolean): void {
  bootPending = active
  _isSwarmBooting.value = active
  if (active) {
    quietCacheWindowUntil = 0
    seriesSuppressedByCache = false
  }
  reconcileActiveLoading()
}

/** Начало перехода на маршрут (учитывает загрузку ленивого чанка до первого apiFetch). */
export function beginRouteNavigation(path: string): void {
  _swarmTargetPath.value = path || '/'
  _swarmLiveDomMode.value = false
  routePending = true
  quietCacheWindowUntil = 0
  seriesSuppressedByCache = false
  if (_swarmSimEnabled.value) {
    clearTimer('sim')
    simPending = true
    seriesDismissed = false
    _isSwarmCompleting.value = false
    _isSwarmVisible.value = true
    _swarmPreviewRunId.value += 1
    swarmSimTimer = setTimeout(() => {
      swarmSimTimer = null
      simPending = false
      reconcileActiveLoading()
    }, SIM_NAV_DURATION_MS)
  }
  reconcileActiveLoading()
}

/** Включает/выключает локальную симуляцию долгого перехода (2.6с) на localhost. */
export function setSwarmSimEnabled(enabled: boolean): void {
  _swarmSimEnabled.value = enabled
  try {
    if (typeof sessionStorage !== 'undefined') {
      sessionStorage.setItem(SIM_STORAGE_KEY, enabled ? '1' : '0')
    }
  } catch {}
  if (!enabled) {
    clearTimer('sim')
    simPending = false
    reconcileActiveLoading()
  }
}

/** Завершение навигации роутера (последующая загрузка данных подхватывается через api-loading). */
export function finishRouteNavigation(path?: string): void {
  if (path) _swarmTargetPath.value = path
  routePending = false
  reconcileActiveLoading()
}

/** Помечает возврат на кэшированную (keep-alive) страницу: фоновый refresh() не перекрывает уже отрисованный экран. */
export function markKeepAliveRefresh(): void {
  quietCacheWindowUntil = Date.now() + KEEP_ALIVE_QUIET_WINDOW_MS
}

/** Открытие/закрытие окна мини-игры (рой ставится на паузу, чтобы не крутиться под игрой). */
export function setSwarmGameOpen(open: boolean): void {
  _isGameOpen.value = open
}

/** Ручной пропуск оверлея сборки (Esc или кнопка «Скрыть») для текущей серии загрузки. */
export function dismissSwarm(): void {
  seriesDismissed = true
  simPending = false
  clearTimer('sim')
  _isSwarmPreview.value = false
  _swarmLiveDomMode.value = false
  hideSwarmImmediately()
}

/** Запуск интерактивного локального демо сборки (?swarm_preview=1 или Alt+Shift+S) без реального ожидания сети. */
export function startSwarmPreview(
  path = '/subsidies',
  opts?: { booting?: boolean; longWait?: boolean; liveDom?: boolean },
): void {
  clearAllTimers()
  simPending = false
  seriesDismissed = false
  seriesSuppressedByCache = false
  _swarmTargetPath.value = path
  bootPending = !!opts?.booting
  _isSwarmBooting.value = !!opts?.booting
  _swarmLiveDomMode.value = !!opts?.liveDom
  _isSwarmCompleting.value = false
  _isSwarmPreview.value = true
  _isSwarmVisible.value = true
  _isBusy.value = true
  _isLongWait.value = !!opts?.longWait
  _swarmPreviewRunId.value += 1
}

/** Плавное завершение демо-сборки (блоки дощёлкиваются, курсоры исчезают на месте). */
export function completeSwarmPreview(): void {
  bootPending = false
  simPending = false
  _isSwarmBooting.value = false
  _swarmLiveDomMode.value = false
  _isBusy.value = false
  _isLongWait.value = false
  triggerSwarmComplete()
}

/** Только для тестов: полный сброс module-level состояния между кейсами. */
export function __resetLongWaitStateForTests(): void {
  window.removeEventListener('api-loading', onApiLoading)
  listenerInstalled = false
  clearAllTimers()
  inflightCount = 0
  routePending = false
  bootPending = false
  simPending = false
  seriesStartedAt = null
  lastZeroAt = null
  seriesDismissed = false
  seriesSuppressedByCache = false
  quietCacheWindowUntil = 0
  _isBusy.value = false
  _isLongWait.value = false
  _isSwarmVisible.value = false
  _isSwarmCompleting.value = false
  _isSwarmBooting.value = false
  _isGameOpen.value = false
  _swarmTargetPath.value = '/'
  _isSwarmPreview.value = false
  _swarmPreviewRunId.value = 0
  _swarmLiveDomMode.value = false
  _swarmSimEnabled.value = false
}
