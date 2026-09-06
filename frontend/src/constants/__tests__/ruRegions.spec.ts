import { describe, it, expect } from 'vitest'
import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import { RU_SUBJECTS_89, DELIVERY_REGIONS, RUSSIAN_REGIONS } from '../russian_regions'
import { RU_REGION_OKATO, resolveRegionOkato, type RegionOkatoInfo } from '../ru_region_okato'

// ПРАВИЛО №6 — источник истины: backend/app/data/ru_regions.json.
// Константы импортируют закоммиченную копию frontend/src/data/ru_regions.json
// (прямой импорт backend/... сломал бы Docker-сборку фронта — build-контекст
// ./frontend не видит backend/), которую поддерживает в актуальном состоянии
// frontend/scripts/sync-ru-regions.mjs. Здесь: (1) форма экспортов на основе
// закоммиченной копии, (2) копия побайтно равна backend-источнику — ТОЛЬКО если
// источник доступен в этом окружении (в Docker-сборке фронта его нет — тест
// пропускается, а не падает).

const testDir = path.dirname(fileURLToPath(import.meta.url))

const COPY_PATH = path.join(testDir, '..', '..', 'data', 'ru_regions.json')
const BACKEND_SOURCE_PATH = path.join(testDir, '..', '..', '..', '..', 'backend', 'app', 'data', 'ru_regions.json')
const backendSourceAvailable = existsSync(BACKEND_SOURCE_PATH)

interface RawRegion {
  name: string
  okato: string
  district: string
}

function loadJson(): RawRegion[] {
  return JSON.parse(readFileSync(COPY_PATH, 'utf-8'))
}

describe('russian_regions.ts / ru_region_okato.ts — читают frontend/src/data/ru_regions.json', () => {
  it('RU_SUBJECTS_89 содержит ровно 89 субъектов', () => {
    expect(RU_SUBJECTS_89.length).toBe(89)
  })

  it('RU_SUBJECTS_89 без дублей', () => {
    expect(new Set(RU_SUBJECTS_89).size).toBe(89)
  })

  it('RU_SUBJECTS_89 совпадает с именами и порядком из JSON (единый источник)', () => {
    const data = loadJson()
    expect(RU_SUBJECTS_89).toEqual(data.map((r) => r.name))
  })

  it('DELIVERY_REGIONS — тот же массив, что RU_SUBJECTS_89 (форма сохранена)', () => {
    expect(DELIVERY_REGIONS).toEqual(RU_SUBJECTS_89)
    expect(DELIVERY_REGIONS.length).toBe(89)
  })

  it('RUSSIAN_REGIONS — 3 спец-значения + 89 субъектов, спец-значения первые', () => {
    expect(RUSSIAN_REGIONS.length).toBe(92)
    expect(RUSSIAN_REGIONS.slice(0, 3)).toEqual([
      'Не определён',
      'Несколько регионов',
      'Федеральное мероприятие',
    ])
    expect(RUSSIAN_REGIONS.slice(3)).toEqual(RU_SUBJECTS_89)
  })

  it('RU_REGION_OKATO содержит ровно 89 ключей с okato/district из JSON', () => {
    const data = loadJson()
    expect(Object.keys(RU_REGION_OKATO).length).toBe(89)
    for (const item of data) {
      const entry: RegionOkatoInfo | undefined = RU_REGION_OKATO[item.name]
      expect(entry).toBeDefined()
      expect(entry).toEqual({ okato: item.okato, district: item.district })
    }
  })

  it('resolveRegionOkato: точное совпадение и устойчивость к алиасам/тире', () => {
    expect(resolveRegionOkato('Москва')).toEqual({ okato: '45', district: 'Центральный федеральный округ' })
    expect(resolveRegionOkato('ХМАО')).toEqual(
      RU_REGION_OKATO['Ханты-Мансийский автономный округ — Югра'],
    )
    expect(
      resolveRegionOkato('Ханты-Мансийский автономный округ - Югра'), // обычный дефис вместо тире
    ).toEqual(RU_REGION_OKATO['Ханты-Мансийский автономный округ — Югра'])
  })

  it('resolveRegionOkato: неизвестное значение → undefined', () => {
    expect(resolveRegionOkato('Не определён')).toBeUndefined()
    expect(resolveRegionOkato(null)).toBeUndefined()
    expect(resolveRegionOkato(undefined)).toBeUndefined()
  })

  it.skipIf(!backendSourceAvailable)(
    'frontend/src/data/ru_regions.json побайтно равна backend/app/data/ru_regions.json (sync-ru-regions.mjs не забыт)',
    () => {
      const copy = readFileSync(COPY_PATH, 'utf-8')
      const source = readFileSync(BACKEND_SOURCE_PATH, 'utf-8')
      expect(copy).toBe(source)
    },
  )
})
