import { describe, expect, it } from 'vitest'
import { orgShortName } from '../orgShortName'

describe('orgShortName', () => {
  it('ООО с вложенным названием в кавычках — пример владельца (27.10.2026)', () => {
    const full = 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ТОРГОВАЯ СЕТЬ "МАГАЗИН 01""'
    expect(orgShortName(full)).toBe('ООО «Торговая сеть «Магазин 01»»')
  })

  it('ООО без вложенного названия', () => {
    expect(orgShortName('ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "МАГАЗИН 01"')).toBe('ООО «Магазин 01»')
  })

  it('АО', () => {
    expect(orgShortName('АКЦИОНЕРНОЕ ОБЩЕСТВО "РОМАШКА"')).toBe('АО «Ромашка»')
  })

  it('ИП без кавычек', () => {
    expect(orgShortName('ИНДИВИДУАЛЬНЫЙ ПРЕДПРИНИМАТЕЛЬ ИВАНОВ ИВАН ИВАНОВИЧ')).toBe('ИП Иванов иван иванович')
  })

  it('неизвестная форма — возвращает как есть', () => {
    expect(orgShortName('Иванов Иван Иванович')).toBe('Иванов Иван Иванович')
  })

  it('пусто/null — возвращает как есть', () => {
    expect(orgShortName(null)).toBe('')
    expect(orgShortName('')).toBe('')
  })
})
