// Отмена устаревших ответов (ПРАВИЛО №6) — createLatestRequestGuard — ЕДИНЫЙ
// механизм для useProductSearch.ts, InlineProductMatch.vue и
// ProductMatchReviewDialog.vue. Проверяем оба механизма сразу: AbortController
// физически прерывает предыдущий запрос, и счётчик seq отбрасывает ответ даже
// если abort не успел до него долететь (гонка) — именно эта гонка была
// причиной бага «болгарка» вместо «боевая» (владелец, 26.10.2026).
import { describe, expect, it } from 'vitest'
import { createLatestRequestGuard } from '../latestRequest'

describe('createLatestRequestGuard', () => {
  it('первый begin() становится устаревшим (isStale=true) после второго begin()', () => {
    const guard = createLatestRequestGuard()
    const first = guard.begin()
    expect(first.isStale()).toBe(false)
    const second = guard.begin()
    expect(first.isStale()).toBe(true)
    expect(second.isStale()).toBe(false)
  })

  it('signal первого запроса помечается aborted после второго begin()', () => {
    const guard = createLatestRequestGuard()
    const first = guard.begin()
    expect(first.signal.aborted).toBe(false)
    guard.begin()
    expect(first.signal.aborted).toBe(true)
  })

  it('единственный begin() не считается устаревшим и его signal не отменён', () => {
    const guard = createLatestRequestGuard()
    const only = guard.begin()
    expect(only.isStale()).toBe(false)
    expect(only.signal.aborted).toBe(false)
  })

  it('третий begin() отменяет и первый, и второй, актуален только третий', () => {
    const guard = createLatestRequestGuard()
    const first = guard.begin()
    const second = guard.begin()
    const third = guard.begin()
    expect(first.isStale()).toBe(true)
    expect(second.isStale()).toBe(true)
    expect(third.isStale()).toBe(false)
    expect(first.signal.aborted).toBe(true)
    expect(second.signal.aborted).toBe(true)
    expect(third.signal.aborted).toBe(false)
  })
})
