// Единый источник «идёт долгая загрузка» — читает тот же счётчик запросов,
// что уже используется в App.vue (api.ts dispatches 'api-loading' с
// detail.count = число активных запросов, см. frontend/src/api.ts ~строка 20).
// Не заводим второй счётчик (ПРАВИЛО №6) — только слушаем существующее
// событие и переводим его в два debounced флага:
//   isBusy      — true когда count>0, false через 500мс после того как
//                 count стабильно остаётся 0 (новый запрос за эти 500мс
//                 отменяет выключение)
//   isLongWait  — true когда запросы идут НЕПРЕРЫВНО (разрыв < 400мс между
//                 соседними запросами тоже считается непрерывностью) суммарно
//                 ≥ 2000мс подряд; гасится вместе с isBusy
//
// Module-level singleton: состояние общее для всего приложения, слушатель
// 'api-loading' навешивается один раз (ensureLongWaitListener идемпотентна),
// а не в каждом компоненте, который хочет знать isLongWait/isBusy.

import { readonly, ref } from 'vue'

const LONG_WAIT_THRESHOLD_MS = 2000
const CONTINUITY_GAP_MS = 400
const BUSY_OFF_DELAY_MS = 500

const _isBusy = ref(false)
const _isLongWait = ref(false)

export const isBusy = readonly(_isBusy)
export const isLongWait = readonly(_isLongWait)

let listenerInstalled = false

// Момент начала текущей непрерывной серии запросов (null — серии сейчас нет)
let seriesStartedAt: number | null = null
// Момент, когда count последний раз упал до 0 (null — сейчас count>0)
let lastZeroAt: number | null = null
// Таймер, переводящий isLongWait в true после LONG_WAIT_THRESHOLD_MS от начала серии
let longWaitTimer: ReturnType<typeof setTimeout> | null = null
// Таймер, выключающий isBusy/серию после BUSY_OFF_DELAY_MS простоя без новых запросов
let busyOffTimer: ReturnType<typeof setTimeout> | null = null

function clearLongWaitTimer() {
  if (longWaitTimer !== null) {
    clearTimeout(longWaitTimer)
    longWaitTimer = null
  }
}

function clearBusyOffTimer() {
  if (busyOffTimer !== null) {
    clearTimeout(busyOffTimer)
    busyOffTimer = null
  }
}

function endSeriesAndGoIdle() {
  seriesStartedAt = null
  lastZeroAt = null
  clearLongWaitTimer()
  clearBusyOffTimer()
  _isBusy.value = false
  _isLongWait.value = false
}

function onApiLoading(e: Event) {
  const count = (e as CustomEvent).detail?.count ?? 0
  const now = Date.now()

  if (count > 0) {
    clearBusyOffTimer()
    _isBusy.value = true

    if (seriesStartedAt === null) {
      // Новая серия с нуля.
      seriesStartedAt = now
      clearLongWaitTimer()
      longWaitTimer = setTimeout(() => {
        _isLongWait.value = true
        longWaitTimer = null
      }, LONG_WAIT_THRESHOLD_MS)
    } else if (lastZeroAt !== null && now - lastZeroAt >= CONTINUITY_GAP_MS) {
      // Разрыв между запросами оказался слишком большим — серия начинается заново.
      seriesStartedAt = now
      _isLongWait.value = false
      clearLongWaitTimer()
      longWaitTimer = setTimeout(() => {
        _isLongWait.value = true
        longWaitTimer = null
      }, LONG_WAIT_THRESHOLD_MS)
    }
    // иначе: разрыв < CONTINUITY_GAP_MS — серия продолжается, таймер не трогаем.

    lastZeroAt = null
  } else {
    lastZeroAt = now
    clearBusyOffTimer()
    busyOffTimer = setTimeout(() => {
      busyOffTimer = null
      endSeriesAndGoIdle()
    }, BUSY_OFF_DELAY_MS)
  }
}

/** Навешивает слушатель 'api-loading' один раз на всё приложение. Безопасно звать из нескольких компонентов. */
export function ensureLongWaitListener(): void {
  if (listenerInstalled) return
  listenerInstalled = true
  window.addEventListener('api-loading', onApiLoading)
}

/** Только для тестов: полный сброс module-level состояния между кейсами. */
export function __resetLongWaitStateForTests(): void {
  window.removeEventListener('api-loading', onApiLoading)
  listenerInstalled = false
  clearLongWaitTimer()
  clearBusyOffTimer()
  seriesStartedAt = null
  lastZeroAt = null
  _isBusy.value = false
  _isLongWait.value = false
}
