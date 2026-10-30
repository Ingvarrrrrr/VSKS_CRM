import { describe, expect, it } from 'vitest'
import { isAllowedNumberChar, sanitizeNumberInput } from '../numberInput'

describe('sanitizeNumberInput', () => {
  it('пропускает целое число как есть', () => {
    expect(sanitizeNumberInput('123')).toBe('123')
  })

  it('нормализует запятую в точку (дробное количество, м/кг)', () => {
    expect(sanitizeNumberInput('12,5')).toBe('12.5')
  })

  it('точка остаётся точкой', () => {
    expect(sanitizeNumberInput('12.5')).toBe('12.5')
  })

  it('минус вырезается целиком — количество/цена не бывают отрицательными', () => {
    expect(sanitizeNumberInput('-123')).toBe('123')
  })

  it('экспонента (e/E) вырезается — не число с т.з. пользователя', () => {
    expect(sanitizeNumberInput('1e5')).toBe('15')
    expect(sanitizeNumberInput('1E5')).toBe('15')
  })

  it('плюс вырезается', () => {
    expect(sanitizeNumberInput('+123')).toBe('123')
  })

  it('буквы и прочий текст вырезаются (вставка произвольной строки)', () => {
    expect(sanitizeNumberInput('abc123def')).toBe('123')
  })

  it('вторая точка/запятая не создаёт второй разделитель — просто удаляется', () => {
    expect(sanitizeNumberInput('1.2.3')).toBe('1.23')
    expect(sanitizeNumberInput('1,2,3')).toBe('1.23')
    expect(sanitizeNumberInput('1.2,3')).toBe('1.23')
  })

  it('пустая строка и строка без цифр дают пустую строку', () => {
    expect(sanitizeNumberInput('')).toBe('')
    expect(sanitizeNumberInput('abc')).toBe('')
    expect(sanitizeNumberInput('---')).toBe('')
  })

  it('вставка целого текста из буфера с мусором вокруг числа', () => {
    expect(sanitizeNumberInput('Кол-во: 86,40 шт.')).toBe('86.40')
  })

  it('ведущая точка/запятая сохраняется как разделитель (пригодно для добавления позже)', () => {
    expect(sanitizeNumberInput(',5')).toBe('.5')
  })
})

describe('isAllowedNumberChar', () => {
  it('цифры допустимы', () => {
    for (const d of '0123456789') expect(isAllowedNumberChar(d)).toBe(true)
  })

  it('точка и запятая допустимы (разделитель дробной части)', () => {
    expect(isAllowedNumberChar('.')).toBe(true)
    expect(isAllowedNumberChar(',')).toBe(true)
  })

  it('минус, плюс, e/E недопустимы', () => {
    expect(isAllowedNumberChar('-')).toBe(false)
    expect(isAllowedNumberChar('+')).toBe(false)
    expect(isAllowedNumberChar('e')).toBe(false)
    expect(isAllowedNumberChar('E')).toBe(false)
  })

  it('буквы и прочие символы недопустимы', () => {
    expect(isAllowedNumberChar('a')).toBe(false)
    expect(isAllowedNumberChar(' ')).toBe(false)
    expect(isAllowedNumberChar('/')).toBe(false)
  })
})
