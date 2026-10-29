// Проверка useLongWait на фейковых таймерах (ПРАВИЛО №6 — один источник
// счётчика запросов, 'api-loading' из api.ts; здесь только эмулируем событие
// как это делает api.ts, не трогая сам api.ts). Проектный default environment
// для vitest — 'node' (vitest.config.ts), jsdom в devDependencies нет и
// добавлять его сюда не стали (чужой package.json сейчас занят параллельной
// сессией) — вместо этого window подставлен настоящим EventTarget (Node
// отдаёт его глобально), CustomEvent тоже глобален в Node 19+.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.stubGlobal('window', new EventTarget())
import {
  __resetLongWaitStateForTests,
  ensureLongWaitListener,
  isBusy,
  isLongWait,
} from '../useLongWait'

function emitApiLoading(count: number) {
  window.dispatchEvent(new CustomEvent('api-loading', { detail: { count } }))
}

describe('useLongWait', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    ensureLongWaitListener()
  })

  afterEach(() => {
    __resetLongWaitStateForTests()
    vi.useRealTimers()
  })

  it('короткий запрос (<2с) — isLongWait никогда не становится true', () => {
    emitApiLoading(1)
    expect(isBusy.value).toBe(true)
    vi.advanceTimersByTime(1500)
    expect(isLongWait.value).toBe(false)
    emitApiLoading(0)
    vi.advanceTimersByTime(1500)
    expect(isLongWait.value).toBe(false)
    expect(isBusy.value).toBe(false)
  })

  it('длинный запрос — isLongWait становится true после 2с', () => {
    emitApiLoading(1)
    vi.advanceTimersByTime(1999)
    expect(isLongWait.value).toBe(false)
    vi.advanceTimersByTime(1)
    expect(isLongWait.value).toBe(true)
  })

  it('два последовательных запроса с разрывом 200мс (итого 2.5с) — isLongWait становится true', () => {
    emitApiLoading(1) // request 1 старт, t=0
    vi.advanceTimersByTime(1500)
    emitApiLoading(0) // request 1 конец, t=1500
    expect(isLongWait.value).toBe(false)

    vi.advanceTimersByTime(200) // разрыв 200мс < 400мс, t=1700
    emitApiLoading(1) // request 2 старт, t=1700
    expect(isBusy.value).toBe(true)
    expect(isLongWait.value).toBe(false) // серия ещё не дошла до 2000мс от t=0

    vi.advanceTimersByTime(300) // t=2000 — порог 2000мс от начала серии достигнут
    expect(isLongWait.value).toBe(true)

    vi.advanceTimersByTime(700) // request 2 идёт ещё 700мс, t=2700 (суммарно занятость 2.5с)
    emitApiLoading(0)
  })

  it('после завершения — isBusy и isLongWait гаснут через 500мс', () => {
    emitApiLoading(1)
    vi.advanceTimersByTime(2000)
    expect(isLongWait.value).toBe(true)

    emitApiLoading(0)
    expect(isBusy.value).toBe(true) // ещё не прошло 500мс
    vi.advanceTimersByTime(499)
    expect(isBusy.value).toBe(true)
    vi.advanceTimersByTime(1)
    expect(isBusy.value).toBe(false)
    expect(isLongWait.value).toBe(false)
  })

  it('разрыв ≥400мс между запросами — серия начинается заново, старый прогресс не засчитывается', () => {
    emitApiLoading(1)
    vi.advanceTimersByTime(1800)
    emitApiLoading(0)

    vi.advanceTimersByTime(450) // разрыв 450мс ≥ 400мс — не непрерывно
    emitApiLoading(1)
    vi.advanceTimersByTime(1800) // 1800мс от нового старта — ещё не 2000
    expect(isLongWait.value).toBe(false)
    vi.advanceTimersByTime(200) // 2000мс от нового старта
    expect(isLongWait.value).toBe(true)
  })
})
