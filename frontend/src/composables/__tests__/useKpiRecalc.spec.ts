// Задача владельца (23.10.2026, доп. к payroll_view): при быстрых повторных
// кликах по переключателю «ФОТ»/«Целиком-Товары-услуги» устаревший ответ не
// должен ни гасить индикатор раньше времени, ни позволить применить свои
// (уже не актуальные) данные. Тест закрепляет это поведение токена
// useKpiRecalc.ts — чистая логика, без Vue-компонентов.
import { describe, expect, it } from 'vitest'
import { useKpiRecalc } from '../useKpiRecalc'

describe('useKpiRecalc', () => {
  it('singleton: повторный вызов возвращает тот же экземпляр (общий между дашбордом и карточкой субсидии)', () => {
    expect(useKpiRecalc()).toBe(useKpiRecalc())
  })

  it('startRecalc включает флаг, finishRecalc с актуальным токеном гасит его', () => {
    const recalc = useKpiRecalc()
    const t = recalc.startRecalc()
    expect(recalc.recalculating.value).toBe(true)
    expect(recalc.isCurrent(t)).toBe(true)
    recalc.finishRecalc(t)
    expect(recalc.recalculating.value).toBe(false)
  })

  it('быстрый повторный клик: более старый вызов не гасит индикатор и не считается актуальным', () => {
    const recalc = useKpiRecalc()
    const t1 = recalc.startRecalc() // первый клик — ушёл запрос
    const t2 = recalc.startRecalc() // владелец кликнул ещё раз, не дождавшись ответа

    // Ответ на t1 прилетел первым (из сети) — его данные устарели, не применяем.
    expect(recalc.isCurrent(t1)).toBe(false)
    expect(recalc.isCurrent(t2)).toBe(true)

    // finishRecalc(t1) не должен погасить индикатор — t2 ещё летит.
    recalc.finishRecalc(t1)
    expect(recalc.recalculating.value).toBe(true)

    // Ответ на t2 (актуальный) — гасим.
    recalc.finishRecalc(t2)
    expect(recalc.recalculating.value).toBe(false)
  })

  it('finishRecalc по устаревшему токену, пришедшему ПОСЛЕ актуального, не включает индикатор заново', () => {
    const recalc = useKpiRecalc()
    const t1 = recalc.startRecalc()
    const t2 = recalc.startRecalc()
    recalc.finishRecalc(t2) // актуальный ответ погасил индикатор
    expect(recalc.recalculating.value).toBe(false)
    recalc.finishRecalc(t1) // опоздавший старый ответ — no-op
    expect(recalc.recalculating.value).toBe(false)
  })
})
