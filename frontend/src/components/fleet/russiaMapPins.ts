/**
 * 2026-09 (geo-fix #3 — честная проекция): раньше все координаты на карте
 * (пины городов, контуры регионов) были подобраны НА ГЛАЗ по пиксельной
 * геометрии рисованной схемы (см. историю правок ниже и в git-логе) — две
 * калибровки провалились (разброс масштаба до 170% при цели 15%, Донецк с
 * Курском оказывались в Поволжье). Теперь карта строится из настоящих
 * географических данных OSM (см. russiaRegionsGeo.json + fetch-russia-geodata.mjs)
 * и единой картографической проекции — этот файл её и определяет.
 *
 * Проекция: РАВНОПРОМЕЖУТОЧНАЯ КОНИЧЕСКАЯ (Equidistant Conic, сферическая
 * аппроксимация), стандартные параллели 50°N/70°N, центральный меридиан
 * 100°E, опорная широта 56°N — параметры близки к тем, что реально
 * используются в атласах для карт России целиком (в отличие от Меркатора,
 * который на широтах 41–82° резко раздувает северные регионы, и от
 * азимутальной равнопромежуточной, которая при центре около Москвы
 * УВОДИТ Владивосток к северу от Москвы на плоскости — проверено расчётом,
 * не годится для узнаваемой карты).
 *
 * ВАЖНО: и пины городов (findKnownCityCoords), и контуры регионов
 * (RussiaMapSvg.vue) переводятся из широты/долготы в SVG-координаты ОДНОЙ И
 * ТОЙ ЖЕ функцией projectLatLonToSvg — руками подогнанных чисел здесь больше
 * нет. Долгота при этом не выбрасывается «как есть» в sin/cos от центра
 * (см. dLambda через normalizeLonDelta) — поэтому Чукотка, лежащая за 180-м
 * меридианом, не улетает на другую сторону карты (нет разрыва по долготе).
 *
 * Масштаб/смещение (PROJ_SCALE/PROJ_ORIGIN_X/PROJ_ORIGIN_Y) — результат
 * подгонки реальной спроецированной геометрии всех 89 регионов
 * (russiaRegionsGeo.json) под viewBox 0 0 1171 611 (см. RussiaMapSvg.vue) с
 * отступом 30px по краям, посчитан один раз офлайн. Если geodata заметно
 * изменится (перегенерация fetch-russia-geodata.mjs с другим допуском
 * упрощения существенно сдвинет bbox) — числа надо пересчитать (см. функцию
 * ниже, применить к bbox всех точек регионов + городов и переподставить).
 *
 * Контрольная проверка (масштаб px/км), пары городов, дистанция по
 * гаверсинусу против пиксельного расстояния через projectLatLonToSvg:
 *   Москва–СПб        px/km ≈ 0.1235
 *   Москва–Ростов     px/km ≈ 0.1242
 *   Ростов–Донецк     px/km ≈ 0.1248
 *   Донецк–Курск      px/km ≈ 0.1242
 *   Москва–Калининград px/km ≈ 0.1229
 *   Москва–Владивосток px/km ≈ 0.1232
 * Разброс ~1.5% (цель — не больше 15%) — см. отчёт задачи geo-fix #3.
 *
 * ОСТАТОЧНОЕ ОГРАНИЧЕНИЕ (честно, не скрываю): у любой конической проекции
 * меридианы сходятся к полюсу, поэтому x точки зависит не только от долготы,
 * но и от широты (через ρ). На периферии карты, где широта и долгота ОБЕИХ
 * точек сильно разные (Калининград 54.7°N/20.5°E против Крыма 45.0°N/34.1°E),
 * это может слегка нарушить строгий порядок «левее по долготе = левее на
 * карте» — Калининград на пиксельной карте оказывается чуть правее Крыма,
 * хотя географически он западнее. Оба они всё равно однозначно попадают в
 * западную часть карты и Калининград остаётся отдельным анклавом (полигон не
 * граничит с остальной Россией) — см. Playwright-скриншот в отчёте задачи.
 */

export interface MapPin {
  id: string | number
  name?: string
  x: number
  y: number
  radius: number
  count: number
  color: string  // цвет пина — присваивается циклически по месту нахождения (см. PIN_COLORS в FleetRegionsView.vue), без смысловой категории
  textColor?: string
  // 2026-09 (geo-fix #4): "истинная" геопроекция точки ДО раздвижки соседних
  // пинов (declutterPins в FleetRegionsView.vue). Если после раздвижки пин
  // сместился заметно (близкие города — см. Донецк/Луганск/Курск в отчёте
  // задачи), RussiaMapSvg.vue рисует тонкую выноску anchor→(x,y), чтобы не
  // терять привязку к реальной географии. Не задано — выноска не рисуется.
  anchorX?: number
  anchorY?: number
  // 2026-09 (отслеживание местоположения сотрудников) — опциональные поля для
  // пинов-ЛЮДЕЙ (StaffLocationMapView.vue / StaffTrackDialog.vue), которых
  // владелец попросил отличать от пинов-ТС визуально. Ни одно из полей не
  // используется существующими пинами ТС (FleetRegionsView.vue) — их
  // undefined воспроизводит прежнее поведение один в один, никакой пин ТС не
  // меняется этим расширением.
  glyph?: string               // текст внутри маркера вместо pin.count (буква фамилии; '' — без текста)
  shape?: 'circle' | 'person'  // 'person' — скруглённый квадрат вместо кружка (другая форма = другой смысл маркера)
  hint?: string                // нативная SVG-подсказка (title) при наведении, напр. точное время последней точки
}

export interface MapConnection {
  from: { x: number; y: number }
  to: { x: number; y: number }
}

// ── Проекция: Equidistant Conic (сферическая), см. комментарий выше ────────
const EARTH_R_KM = 6371
const STD_PARALLEL_1 = 50 // °N
const STD_PARALLEL_2 = 70 // °N
const REF_LATITUDE = 56   // °N — опорная широта origin
const CENTRAL_MERIDIAN = 100 // °E

const toRad = (deg: number) => (deg * Math.PI) / 180

const PHI1 = toRad(STD_PARALLEL_1)
const PHI2 = toRad(STD_PARALLEL_2)
const PHI0 = toRad(REF_LATITUDE)
// n и G — стандартные параметры конической равнопромежуточной проекции
// (Snyder, "Map Projections — A Working Manual", формулы 16-1..16-4).
const CONIC_N = (Math.cos(PHI1) - Math.cos(PHI2)) / (PHI2 - PHI1)
const CONIC_G = Math.cos(PHI1) / CONIC_N + PHI1
const CONIC_RHO0 = EARTH_R_KM * (CONIC_G - PHI0)

/** Нормализует разницу долгот в диапазон (-180, 180] — без этого Чукотка
 * (реальная долгота ~-169.9°, т.е. 190°E) давала бы разрыв относительно
 * центрального меридиана 100°E. */
function normalizeLonDelta(lonDeg: number, refLonDeg: number): number {
  let d = lonDeg - refLonDeg
  while (d > 180) d -= 360
  while (d <= -180) d += 360
  return d
}

/** Широта/долгота → координаты проекции в километрах (x: восток+, y: север+
 * относительно опорной точки проекции). Экспортируется для пересчёта
 * PROJ_SCALE/PROJ_ORIGIN_* при перегенерации geodata. */
export function projectLatLonToKm(lat: number, lon: number): { x: number; y: number } {
  const phi = toRad(lat)
  const dLambda = toRad(normalizeLonDelta(lon, CENTRAL_MERIDIAN))
  const rho = EARTH_R_KM * (CONIC_G - phi)
  const theta = CONIC_N * dLambda
  return {
    x: rho * Math.sin(theta),
    y: CONIC_RHO0 - rho * Math.cos(theta),
  }
}

// Подгонка km-координат под viewBox RussiaMapSvg.vue (0 0 1171 611, отступ
// 30px) — посчитана один раз офлайн по bbox всех 89 регионов
// (russiaRegionsGeo.json) + всех городов из KNOWN_CITY_COORDS ниже.
const PROJ_SCALE = 0.12423860574712026     // px на км
const PROJ_ORIGIN_X = 640.3775426601177    // px
const PROJ_ORIGIN_Y = 463.53108883471015   // px

/** Единая функция проекции широта/долгота → SVG-координаты (px в viewBox
 * карты). Используется и для пинов городов (findKnownCityCoords ниже), и
 * для контуров регионов (RussiaMapSvg.vue) — намеренно, чтобы никогда больше
 * не разъезжались две независимые калибровки одной и той же карты. */
export function projectLatLonToSvg(lat: number, lon: number): { x: number; y: number } {
  const { x, y } = projectLatLonToKm(lat, lon)
  return {
    x: PROJ_ORIGIN_X + x * PROJ_SCALE,
    y: PROJ_ORIGIN_Y - y * PROJ_SCALE,
  }
}

// ── Демо-координаты для DEFAULT_PINS (не боевой путь) ───────────────────────
// 2026-09 (geo-fix #4): раньше этот список (KNOWN_CITY_COORDS, было публичным
// API) был и единственным источником координат для реальных пинов на карте
// (findKnownCityCoords), и источником для демо-набора DEFAULT_PINS ниже.
// Реальные пины теперь строятся через справочник городов
// (russiaCitiesCatalog.ts — OSM place=city/town, см. fetch-russia-cities.mjs),
// который заведомо шире и умеет искать по названию, а не только по
// зашитому ключевому слову. Этот список остаётся ТОЛЬКО ради DEFAULT_PINS —
// демо-fallback, который на практике не используется (FleetRegionsView всегда
// передаёт реальные pins), поэтому не вынесен в общий справочник.
const _DEMO_CITY_LATLON: Record<string, { lat: number; lon: number }> = {
  москва:      { lat: 55.7558, lon: 37.6173 },
  ростов:      { lat: 47.2357, lon: 39.7015 },
  луганск:     { lat: 48.5740, lon: 39.3078 },
  донецк:      { lat: 48.0159, lon: 37.8028 },
  запорожье:   { lat: 47.8388, lon: 35.1396 },
  курск:       { lat: 51.7304, lon: 36.1926 },
  белгород:    { lat: 50.5977, lon: 36.5858 },
  иркутск:     { lat: 52.2871, lon: 104.3050 },
  тула:        { lat: 54.1961, lon: 37.6182 },
  крым:        { lat: 44.9521, lon: 34.1024 },
  херсон:      { lat: 46.6354, lon: 32.6169 },
}

function coordsByKeyword(keyword: string): { x: number; y: number } {
  const hit = _DEMO_CITY_LATLON[keyword]
  if (!hit) throw new Error(`DEFAULT_PINS: unknown demo city keyword "${keyword}"`)
  return projectLatLonToSvg(hit.lat, hit.lon)
}

/** Default pins — демо-набор для fallback-ветки (см. RussiaMapSvg.vue), на
 * практике не используется (FleetRegionsView всегда передаёт реальные pins).
 * Координаты — той же проекцией от реальных городов, что и остальная карта. */
export const DEFAULT_PINS: MapPin[] = [
  { id: 'msk',     name: 'ЦУ Москва',       ...coordsByKeyword('москва'),      radius: 31, count: 9,  color: '#6aa6ff' },
  { id: 'rnd',     name: 'Ростов-на-Дону',  ...coordsByKeyword('ростов'),      radius: 43, count: 18, color: '#f6b34a' },
  { id: 'lnr',     name: 'Луганск (ЛНР)',   ...coordsByKeyword('луганск'),     radius: 23, count: 6,  color: '#22c997' },
  { id: 'dnr',     name: 'Донецк (ДНР)',    ...coordsByKeyword('донецк'),      radius: 21, count: 5,  color: '#22c997' },
  { id: 'zp',      name: 'Запорожье',       ...coordsByKeyword('запорожье'),   radius: 18, count: 4,  color: '#8b5cf6' },
  { id: 'kursk',   name: 'Курск',           ...coordsByKeyword('курск'),       radius: 16, count: 2,  color: '#5dd0ff' },
  { id: 'belg',    name: '',                ...coordsByKeyword('белгород'),    radius: 12, count: 1,  color: '#5dd0ff' },
  { id: 'irk',     name: 'Иркутск',         ...coordsByKeyword('иркутск'),     radius: 18, count: 3,  color: '#8b5cf6' },
  { id: 'tula',    name: '',                ...coordsByKeyword('тула'),        radius: 10, count: 1,  color: '#5dd0ff' },
  { id: 'crimea',  name: 'Крым',            ...coordsByKeyword('крым'),        radius: 10, count: 1,  color: '#5dd0ff' },
  { id: 'kherson', name: '',                ...coordsByKeyword('херсон'),      radius: 10, count: 1,  color: '#5dd0ff' },
]
