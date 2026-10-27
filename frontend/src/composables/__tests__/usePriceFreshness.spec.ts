// Дефект на проде (27.10.2026): «от 26.10.2026 · импорт №https://www.sima-land.ru/3854076/» —
// полная ссылка с приклеенным «№», переносится по символам в строке позиции
// заявки. Источник — formatSourceRef (Правило №6: единственное место, где
// price_source_ref/source_ref превращается в показываемый текст — ссылка →
// домен, иначе → «№ref», без дублирования, если «№» уже есть).
import { describe, expect, it } from 'vitest'
import { formatPriceStamp, formatSourceRef, sourceRefFullUrl } from '../usePriceFreshness'

describe('formatSourceRef', () => {
  it('ссылка на магазин → короткий домен, без «№»', () => {
    expect(formatSourceRef('https://www.sima-land.ru/3854076/')).toBe('sima-land.ru')
  })
  it('ref уже содержит «№» → не дублируем', () => {
    expect(formatSourceRef('Запрос КП №7')).toBe('Запрос КП №7')
  })
  it('обычный номер без «№» → добавляем «№»', () => {
    expect(formatSourceRef('123-ОК')).toBe('№123-ОК')
  })
  it('пусто/нет ref → пустая строка', () => {
    expect(formatSourceRef(null)).toBe('')
    expect(formatSourceRef(undefined)).toBe('')
    expect(formatSourceRef('')).toBe('')
  })
})

describe('sourceRefFullUrl', () => {
  it('ссылка → полный URL (для :title/подсказки)', () => {
    expect(sourceRefFullUrl('https://www.sima-land.ru/3854076/')).toBe('https://www.sima-land.ru/3854076/')
  })
  it('не ссылка → пустая строка', () => {
    expect(sourceRefFullUrl('123-ОК')).toBe('')
    expect(sourceRefFullUrl(null)).toBe('')
  })
})

describe('formatPriceStamp', () => {
  it('источник «импорт» + ref-ссылка → домен, не полный URL', () => {
    expect(formatPriceStamp('2026-10-26T00:00:00', 'import', 'https://www.sima-land.ru/3854076/'))
      .toBe('от 26.10.2026 · импорт sima-land.ru')
  })
  it('источник «договор» + номер без «№» → «№...»', () => {
    expect(formatPriceStamp('2026-10-26T00:00:00', 'contract', '123-ОК'))
      .toBe('от 26.10.2026 · договор №123-ОК')
  })
  it('ref уже содержит «№» → не дублируем', () => {
    expect(formatPriceStamp('2026-10-26T00:00:00', 'kp', 'Запрос КП №7'))
      .toBe('от 26.10.2026 · КП Запрос КП №7')
  })
  it('без даты → «дата не указана», ref игнорируется', () => {
    expect(formatPriceStamp(null, 'import', 'https://www.sima-land.ru/3854076/')).toBe('дата не указана')
  })
  it('без источника и без ref → только дата', () => {
    expect(formatPriceStamp('2026-10-26T00:00:00', null, null)).toBe('от 26.10.2026')
  })
  it('без источника, только ref-ссылка → дата + домен', () => {
    expect(formatPriceStamp('2026-10-26T00:00:00', null, 'https://www.sima-land.ru/3854076/'))
      .toBe('от 26.10.2026 · sima-land.ru')
  })
})
