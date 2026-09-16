// Средняя цена (решение владельца 2026-09-16, п.3): «на основании N цен» — родительный
// падеж, обязан склоняться правильно на контрольных числах владельца (1/2/5),
// плюс граничные 11/21 (тот же mod10/mod100-приём, что и в relativeTime.ts).
import { describe, expect, it } from 'vitest'
import { avgPriceBasisText, priceCountGenitive, priceSourceLabel } from '../productsTypes'

describe('priceCountGenitive / avgPriceBasisText', () => {
  it('1 → цены (родительный падеж единственного числа)', () => {
    expect(priceCountGenitive(1)).toBe('цены')
    expect(avgPriceBasisText(1)).toBe('1 цены')
  })
  it('2 → цен', () => {
    expect(priceCountGenitive(2)).toBe('цен')
    expect(avgPriceBasisText(2)).toBe('2 цен')
  })
  it('5 → цен', () => {
    expect(priceCountGenitive(5)).toBe('цен')
    expect(avgPriceBasisText(5)).toBe('5 цен')
  })
  it('11 → цен (исключение из mod10=1 — «одиннадцать»)', () => {
    expect(avgPriceBasisText(11)).toBe('11 цен')
  })
  it('21 → цены (mod10=1, mod100!=11)', () => {
    expect(avgPriceBasisText(21)).toBe('21 цены')
  })
})

describe('priceSourceLabel', () => {
  it('contract — с номером договора', () => {
    expect(priceSourceLabel('contract', '42')).toBe('Договор № 42')
  })
  it('contract — без номера, просто подпись', () => {
    expect(priceSourceLabel('contract', null)).toBe('Договор')
  })
  it('kp', () => {
    expect(priceSourceLabel('kp', null)).toBe('КП')
  })
  it('import — с именем файла', () => {
    expect(priceSourceLabel('import', 'прайс_2026.xlsx')).toBe('Импорт: прайс_2026.xlsx')
  })
  it('monitoring', () => {
    expect(priceSourceLabel('monitoring', null)).toBe('Мониторинг')
  })
  it('manual', () => {
    expect(priceSourceLabel('manual', null)).toBe('Вручную')
  })
})
