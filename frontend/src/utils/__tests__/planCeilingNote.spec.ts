// Три случая красной строки под карточкой «Запланировано» (SubsidyKpiCards.vue)
// — числа из живого примера владельца, субсидия ФАДМ 2026 (23.10.2026):
// Бюджет (ФЭО) 15 880 100, «Запланировано» 15 620 782, «на согласовании»
// +292 905, plan_over_ceiling_amount (backend) = 33 587.
import { describe, expect, it } from 'vitest'
import { planCeilingNote } from '../planCeilingNote'

const formatCurrency = (n: number) => n.toLocaleString('ru-RU', { minimumFractionDigits: 2 }) + ' ₽'

describe('planCeilingNote', () => {
  it('а) план карточки + «на согласовании» − бюджет == plan_over_ceiling_amount, план карточки ещё НЕ выше бюджета', () => {
    const result = planCeilingNote({
      planOverCeilingAmount: 33_587,
      planCardValue: 15_620_782,
      budgetCardValue: 15_880_100,
      pendingTotal: 292_905,
      ceilingOverMatchesCards: false,
      formatCurrency,
    })
    expect(result.case).toBe('pending_would_exceed')
    expect(result.text).toContain('если согласовать всё')
    expect(result.text).toContain('33')
  })

  it('б) план карточки уже выше бюджета — «уменьшите план»', () => {
    const result = planCeilingNote({
      planOverCeilingAmount: 40_000,
      planCardValue: 15_920_100,
      budgetCardValue: 15_880_100,
      pendingTotal: 0,
      ceilingOverMatchesCards: true,
      formatCurrency,
    })
    expect(result.case).toBe('already_over')
    expect(result.text).toContain('план выше бюджета')
    expect(result.text).toContain('уменьшите план')
  })

  it('в) расхождение из-за статей без ФЭО — не сходится ни с планом, ни с планом+ожидающим', () => {
    const result = planCeilingNote({
      planOverCeilingAmount: 115_690.7,
      planCardValue: 15_620_782,
      budgetCardValue: 15_880_100,
      pendingTotal: 0,
      ceilingOverMatchesCards: false,
      formatCurrency,
    })
    expect(result.case).toBe('excess_feo_only')
    expect(result.text).toContain('в статьях, где задан бюджет ФЭО, план выше')
    expect(result.text).toContain('уменьшите план')
  })
})
