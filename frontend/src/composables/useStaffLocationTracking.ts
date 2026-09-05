/**
 * Отслеживание местоположения сотрудника — клиентская часть (владелец: спасатели,
 * 2026-09). Backend уже готов (см. backend/app/routers/staff_location.py) — этот
 * модуль только собирает координаты в браузере, копит их офлайн и досылает.
 *
 * Синглтон module-level state, по образцу useChat.ts/useApprovalsBadge.ts
 * (initApprovalsBadge/destroyApprovalsBadge) — один экземпляр на всё
 * приложение, а не по экземпляру на каждый компонент, где стоит кнопка
 * «Я на смене» (кнопка в AppBar и в DriverHomeView/DriverProfileView должны
 * показывать ОДНО и то же состояние, а не гонять свои отдельные таймеры).
 *
 * Интервал опроса координат: periodic getCurrentPosition раз в 90 секунд, а не
 * watchPosition. Причина — задание прямо говорит «точность в сотни метров
 * устраивает, частить запросами не нужно»: watchPosition на телефоне с GPS
 * может слать обновления каждые несколько секунд при движении — избыточно
 * часто для этой задачи и расходует батарею; периодический опрос даёт
 * предсказуемый и редкий трафик, укладывающийся в «минуту-две».
 */
import { ref } from 'vue'
import { apiFetch } from '@/api'
import { enqueue, getAllQueued, removeQueued, countQueued } from './useOfflineQueue'

interface QueuedPoint {
  id?: number
  lat: number
  lon: number
  accuracy_m: number | null
  recorded_at: string
  source: string
}

export interface ShiftInfo {
  id: number
  user_id: number
  started_at: string
  ended_at: string | null
  is_active: boolean
}

const QUEUE_STORE = 'staff_location_points' as const
const POLL_INTERVAL_MS = 90_000 // ~1.5 минуты — см. обоснование выше
const FLUSH_INTERVAL_MS = 20_000 // как часто пробуем досылать накопленную очередь

// ── Публичное реактивное состояние (читают ShiftToggleButton, MyLocationView и т.п.) ──
export const shiftActive = ref(false)
export const shiftStartedAt = ref<string | null>(null)
export const loadingShift = ref(false)
export const togglingShift = ref(false)

export const geoSupported = ref('geolocation' in navigator)
export const geoPermission = ref<'granted' | 'denied' | 'prompt' | 'unknown'>('unknown')
export const geoErrorMessage = ref<string | null>(null)

export const lastSentAt = ref<Date | null>(null)
export const lastAttemptError = ref<string | null>(null)
export const pendingPointsCount = ref(0)

export const isOnline = ref(typeof navigator !== 'undefined' ? navigator.onLine : true)
export const isPageVisible = ref(typeof document !== 'undefined' ? document.visibilityState === 'visible' : true)

let pollTimer: ReturnType<typeof setInterval> | null = null
let flushTimer: ReturnType<typeof setInterval> | null = null
let initialized = false
let flushInFlight = false

function isAuthed(): boolean {
  return !!localStorage.getItem('auth_token')
}

async function refreshPermissionState() {
  try {
    const nav = navigator as any
    if (nav.permissions?.query) {
      const status = await nav.permissions.query({ name: 'geolocation' })
      geoPermission.value = status.state
      status.onchange = () => { geoPermission.value = status.state }
    }
  } catch {
    // Permissions API недоступен (старые Safari) — состояние узнаем по факту первого запроса.
  }
}

function getCurrentPositionOnce(): Promise<GeolocationPosition> {
  return new Promise((resolve, reject) => {
    navigator.geolocation.getCurrentPosition(resolve, reject, {
      enableHighAccuracy: false, // точность в сотни метров устраивает — быстрее фикс, меньше расход батареи
      timeout: 20_000,
      // maximumAge: 0 — всегда свежий фикс, не кэш браузера. Опрос и так редкий
      // (раз в 90с + при возврате в приложение), кэш длиной в минуту рисковал бы
      // отдать устаревшую позицию ровно в тот момент, когда точность важнее
      // всего (человек только что вернулся в сеть/на передний план).
      maximumAge: 0,
    })
  })
}

function describeGeoError(err: GeolocationPositionError): string {
  if (err.code === err.PERMISSION_DENIED) {
    return 'Доступ к геолокации запрещён в браузере. Разрешите его в настройках сайта, чтобы координаты передавались.'
  }
  if (err.code === err.POSITION_UNAVAILABLE) {
    return 'Не удалось определить местоположение устройства — проверьте, включена ли геолокация на телефоне.'
  }
  return 'Истекло время ожидания ответа от GPS. Повторим попытку при следующем опросе.'
}

async function captureAndQueuePoint() {
  if (!shiftActive.value || !isPageVisible.value || !geoSupported.value) return
  try {
    const pos = await getCurrentPositionOnce()
    geoPermission.value = 'granted'
    geoErrorMessage.value = null
    const point: QueuedPoint = {
      lat: pos.coords.latitude,
      lon: pos.coords.longitude,
      accuracy_m: pos.coords.accuracy ?? null,
      recorded_at: new Date(pos.timestamp).toISOString(),
      source: 'browser',
    }
    await enqueue(QUEUE_STORE, point)
    pendingPointsCount.value = await countQueued(QUEUE_STORE)
    await flushQueue()
  } catch (e: any) {
    if (e && typeof e.code === 'number') {
      geoErrorMessage.value = describeGeoError(e)
      if (e.code === e.PERMISSION_DENIED) geoPermission.value = 'denied'
    } else {
      console.warn('[staff-location] capture failed', e)
    }
  }
}

/** Досылка накопленной очереди. Безопасна для многократного параллельного вызова
 * (флаг flushInFlight) — и таймер, и «вернулись в онлайн», и ручной вызов из UI
 * могут сработать почти одновременно. */
export async function flushQueue() {
  if (flushInFlight) return
  if (!isOnline.value || !isAuthed()) return
  flushInFlight = true
  try {
    const items = await getAllQueued<QueuedPoint>(QUEUE_STORE)
    if (!items.length) {
      pendingPointsCount.value = 0
      return
    }
    // Сервер принимает максимум 500 точек за раз (LocationBatchIn) — батчим с запасом.
    const BATCH = 200
    for (let i = 0; i < items.length; i += BATCH) {
      const slice = items.slice(i, i + BATCH)
      try {
        await apiFetch('/staff-location/points', {
          method: 'POST',
          body: { points: slice.map(({ id: _id, ...rest }) => rest) },
          suppressErrorDialog: true,
        })
        await removeQueued(QUEUE_STORE, slice.map(s => s.id))
        lastSentAt.value = new Date()
        lastAttemptError.value = null
      } catch (e: any) {
        lastAttemptError.value = e?.payload?.message || e?.message || 'Не удалось отправить координаты — повторим позже'
        // 400 = смена не активна на сервере (например, кто-то завершил её из другого
        // места) — синхронизируем локальное состояние, чтобы не долбить бесполезными
        // повторами и не копить точки бесконечно.
        if (e?.status === 400) {
          shiftActive.value = false
          stopPolling()
        }
        break // не повторяем внутри одной попытки — подождём следующего тика таймера
      }
    }
    pendingPointsCount.value = await countQueued(QUEUE_STORE)
  } finally {
    flushInFlight = false
  }
}

function startPolling() {
  if (pollTimer) return
  captureAndQueuePoint() // сразу первая точка — не ждать полторы минуты ради обратной связи
  pollTimer = setInterval(captureAndQueuePoint, POLL_INTERVAL_MS)
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

function startFlushLoop() {
  if (flushTimer) return
  flushTimer = setInterval(flushQueue, FLUSH_INTERVAL_MS)
}

function stopFlushLoop() {
  if (flushTimer) { clearInterval(flushTimer); flushTimer = null }
}

export async function refreshShiftState() {
  if (!isAuthed()) return
  loadingShift.value = true
  try {
    const shift = await apiFetch<ShiftInfo | null>('/staff-location/shift/me')
    shiftActive.value = !!shift?.is_active
    shiftStartedAt.value = shift?.started_at ?? null
    if (shiftActive.value) startPolling()
    else stopPolling()
  } catch (e) {
    console.warn('[staff-location] refreshShiftState failed', e)
  } finally {
    loadingShift.value = false
  }
}

export async function startShift() {
  togglingShift.value = true
  geoErrorMessage.value = null
  try {
    await refreshPermissionState()
    const shift = await apiFetch<ShiftInfo>('/staff-location/shift/start', { method: 'POST' })
    shiftActive.value = true
    shiftStartedAt.value = shift.started_at
    pendingPointsCount.value = await countQueued(QUEUE_STORE)
    startPolling()
    startFlushLoop()
  } finally {
    togglingShift.value = false
  }
}

export async function endShift() {
  togglingShift.value = true
  try {
    await apiFetch('/staff-location/shift/end', { method: 'POST' })
  } finally {
    shiftActive.value = false
    shiftStartedAt.value = null
    stopPolling()
    togglingShift.value = false
  }
}

function onOnline() {
  isOnline.value = true
  flushQueue()
}
function onOffline() {
  isOnline.value = false
}
function onVisibility() {
  isPageVisible.value = document.visibilityState === 'visible'
  if (isPageVisible.value && shiftActive.value) {
    // Вернулись в приложение (свернули/развернули, разблокировали телефон) —
    // сразу пробуем свежую точку + досылку очереди, не дожидаясь тика таймера.
    captureAndQueuePoint()
  }
}

/** Вызывается один раз при старте приложения (для уже вошедшего пользователя) —
 * см. AppBar.vue (desktop) и MobileLayout.vue (мобильный кабинет водителя),
 * чтобы передача продолжала идти независимо от того, какой layout сейчас
 * отрендерен. */
export function initStaffLocationTracking() {
  if (initialized) return
  initialized = true
  refreshPermissionState()
  window.addEventListener('online', onOnline)
  window.addEventListener('offline', onOffline)
  document.addEventListener('visibilitychange', onVisibility)
  startFlushLoop()
  refreshShiftState()
  countQueued(QUEUE_STORE).then(n => { pendingPointsCount.value = n }).catch(() => {})
}

/** Вызывается при выходе из аккаунта — прекращает передачу координат немедленно.
 * Саму смену на сервере НЕ завершает (пользователь мог выйти случайно/временно —
 * завершение смены остаётся явным действием кнопки «Смену закончил»); локальный
 * опрос координат просто останавливается, следующий initStaffLocationTracking()
 * после логина заново подтянет реальное состояние с сервера. */
export function destroyStaffLocationTracking() {
  initialized = false
  stopPolling()
  stopFlushLoop()
  window.removeEventListener('online', onOnline)
  window.removeEventListener('offline', onOffline)
  document.removeEventListener('visibilitychange', onVisibility)
}
