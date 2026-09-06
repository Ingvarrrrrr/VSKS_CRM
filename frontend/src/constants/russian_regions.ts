/**
 * Справочник субъектов и регионов РФ — два отдельных экспорта:
 *
 *  RU_SUBJECTS_89      — ровно 89 субъектов РФ (алфавит, ОКТМО).
 *                        Данные читаются из frontend/src/data/ru_regions.json —
 *                        это КОПИЯ единого источника (ПРАВИЛО №6)
 *                        backend/app/services/ru_regions.py читает тот же
 *                        backend/app/data/ru_regions.json напрямую; фронт не может
 *                        импортировать его напрямую, потому что Docker собирает
 *                        frontend с build-контекстом ./frontend (backend/ туда не
 *                        попадает) — см. frontend/src/data/README.md и
 *                        frontend/scripts/sync-ru-regions.mjs. Копию руками не
 *                        править: `npm run sync:regions` перегенерирует её из
 *                        источника, `npm run build` (prebuild) делает это
 *                        автоматически, когда источник доступен.
 *
 *  DELIVERY_REGIONS    — для поля «Регион поставки (субъект РФ)»:
 *                        только 89 субъектов, без спец-значений.
 *                        Используется для ОКАТО/федерального округа Фабриканта.
 *
 *  RUSSIAN_REGIONS     — для поля «Регион проведения мероприятия»:
 *                        3 спец-значения + 89 субъектов.
 *                        Имя экспорта сохранено для обратной совместимости.
 */

import ruRegionsData from '@/data/ru_regions.json'

export const RU_SUBJECTS_89: string[] = ruRegionsData.map((r) => r.name)

/** Для поля «Регион поставки (субъект РФ)» — только 89 субъектов, без спец-значений */
export const DELIVERY_REGIONS: string[] = RU_SUBJECTS_89

/** Для поля «Регион проведения мероприятия» — спец-значения + 89 субъектов */
export const RUSSIAN_REGIONS: string[] = [
  // Спец-значения
  'Не определён',
  'Несколько регионов',
  'Федеральное мероприятие',
  // 89 субъектов РФ
  ...RU_SUBJECTS_89,
]
