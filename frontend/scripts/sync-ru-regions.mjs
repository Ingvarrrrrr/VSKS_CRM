#!/usr/bin/env node
// Синхронизирует frontend/src/data/ru_regions.json из ЕДИНОГО ИСТОЧНИКА
// backend/app/data/ru_regions.json (ПРАВИЛО №6 — один показатель/справочник,
// один источник истины).
//
// Зачем копия, а не прямой импорт '../../backend/...' из фронтового кода:
// Docker собирает frontend с build-контекстом ./frontend (docker-compose.yml,
// docker-compose.prod.yml, frontend/Dockerfile: `COPY . .` внутри builder-стадии
// видит только frontend/) — файла backend/app/data/ru_regions.json там физически
// нет, прямой импорт этого пути упал бы на `npm run build` при деплое.
//
// Поэтому: backend/app/data/ru_regions.json — источник; frontend/src/data/ru_regions.json
// — закоммиченная копия, которую импортируют фронтовые константы. Этот скрипт:
//   - без флагов: если backend-источник доступен (локальная разработка, монорепо-checkout) —
//     перезаписывает копию из источника. Если источник недоступен (сборка Docker-образа
//     фронта, где backend/ не скопирован) — молча завершается 0, копия остаётся как есть
//     (её обязаны закоммитить после последней синхронизации).
//   - с флагом --check: ничего не пишет, только проверяет побайтное совпадение копии
//     с источником; если источник недоступен — тоже 0 (нечего сверять); если копия
//     разошлась или отсутствует — падает с ненулевым кодом. Использовать в CI:
//       node frontend/scripts/sync-ru-regions.mjs --check
//
// npm-хуки (frontend/package.json): "sync:regions" — ручной запуск; "prebuild" —
// авто-запуск перед `npm run build` (в Docker источника нет → выходит 0 мгновенно,
// сборка использует закоммиченную копию).

import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const SOURCE_PATH = path.resolve(scriptDir, '..', '..', 'backend', 'app', 'data', 'ru_regions.json')
const DEST_PATH = path.resolve(scriptDir, '..', 'src', 'data', 'ru_regions.json')

const checkOnly = process.argv.includes('--check')

if (!existsSync(SOURCE_PATH)) {
  console.log(
    '[sync-ru-regions] backend/app/data/ru_regions.json недоступен (ожидаемо при Docker-сборке ' +
      'фронта, build-контекст ./frontend) — используется уже закоммиченная frontend/src/data/ru_regions.json.',
  )
  process.exit(0)
}

const sourceContent = readFileSync(SOURCE_PATH, 'utf-8')

if (checkOnly) {
  if (!existsSync(DEST_PATH)) {
    console.error(
      '[sync-ru-regions] frontend/src/data/ru_regions.json отсутствует. Запустите: npm run sync:regions',
    )
    process.exit(1)
  }
  const destContent = readFileSync(DEST_PATH, 'utf-8')
  if (destContent !== sourceContent) {
    console.error(
      '[sync-ru-regions] frontend/src/data/ru_regions.json РАСХОДИТСЯ с backend/app/data/ru_regions.json. ' +
        'Запустите: npm run sync:regions — и закоммитьте обновлённую копию.',
    )
    process.exit(1)
  }
  console.log('[sync-ru-regions] OK — frontend/src/data/ru_regions.json синхронизирована с источником.')
  process.exit(0)
}

writeFileSync(DEST_PATH, sourceContent, 'utf-8')
console.log('[sync-ru-regions] frontend/src/data/ru_regions.json обновлена из backend/app/data/ru_regions.json.')
