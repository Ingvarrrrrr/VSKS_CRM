// Задача владельца 22.10.2026: история ФЭО (FeoItemHistory.vue/
// FeoImportRunsPanel.vue) показывала денежные поля сырым Decimal-текстом с
// бэкенда («1710.0000000000002») вместо «1 710,00 ₽», как везде в дереве ФЭО.
import { describe, it, expect } from 'vitest'
import { formatFeoHistoryValue } from '../feoHistoryValueFormat'
import { formatCurrency } from '@/composables/subsidies/format'

describe('formatFeoHistoryValue', () => {
  it('денежное поле с хвостом плавающей точки — как formatCurrency везде в дереве', () => {
    expect(formatFeoHistoryValue('amount', '1710.0000000000002')).toBe(formatCurrency(1710))
    expect(formatFeoHistoryValue('amount', '1710.00')).toBe(formatCurrency(1710))
  })

  it('денежные поля из задания — budget/unit_price/feo_amount/feo_unit_price/manual_plan_amount/planned_amount/monthly_amount', () => {
    expect(formatFeoHistoryValue('budget', '50000')).toBe(formatCurrency(50000))
    expect(formatFeoHistoryValue('unit_price', '99.9')).toBe(formatCurrency(99.9))
    expect(formatFeoHistoryValue('feo_amount', '1000')).toBe(formatCurrency(1000))
    expect(formatFeoHistoryValue('feo_unit_price', '1000')).toBe(formatCurrency(1000))
    expect(formatFeoHistoryValue('manual_plan_amount', '1000')).toBe(formatCurrency(1000))
    expect(formatFeoHistoryValue('planned_amount', '1000')).toBe(formatCurrency(1000))
    expect(formatFeoHistoryValue('monthly_amount', '1000')).toBe(formatCurrency(1000))
  })

  it('количество — без «₽», до 4 знаков без хвостовых нулей', () => {
    expect(formatFeoHistoryValue('quantity', '2.0')).toBe('2')
    expect(formatFeoHistoryValue('quantity', '0.3330000000000001')).toBe('0.333')
    expect(formatFeoHistoryValue('feo_quantity', '5')).toBe('5')
  })

  it('прочие поля (не денежные/количественные) — выводятся как есть', () => {
    expect(formatFeoHistoryValue('name', 'Чайник')).toBe('Чайник')
    expect(formatFeoHistoryValue('is_active', 'true')).toBe('true')
  })

  it('null/undefined/пустая строка — тире', () => {
    expect(formatFeoHistoryValue('amount', null)).toBe('—')
    expect(formatFeoHistoryValue('amount', undefined)).toBe('—')
    expect(formatFeoHistoryValue('amount', '')).toBe('—')
  })
})
