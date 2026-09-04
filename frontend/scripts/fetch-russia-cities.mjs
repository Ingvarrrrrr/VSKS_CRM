/**
 * fetch-russia-cities.mjs
 *
 * Скачивает справочник населённых пунктов России (place=city, place=town) из
 * OpenStreetMap через Overpass API и сохраняет как статический JSON —
 * frontend/src/components/fleet/russiaCitiesGeo.json. Нужен для автодополнения
 * поля «Место нахождения, город» в карточке ТС и для координат на карте
 * /fleet/regions (см. russiaCitiesCatalog.ts) — вместо зашитой таблицы на
 * 20 городов (KNOWN_CITY_COORDS в russiaMapPins.ts, задача geo-fix #4).
 *
 * Запускать вручную при необходимости обновить справочник:
 *   node scripts/fetch-russia-cities.mjs
 * (из папки frontend/). В рантайме приложение НИКОГДА не обращается к
 * Overpass — только читает уже сохранённый JSON.
 *
 * Подход — по образцу fetch-russia-geodata.mjs (те же зеркала, ретраи,
 * User-Agent/Accept заголовки, задержки между запросами).
 *
 * ── Почему bbox, а не area["ISO3166-1"="RU"] ────────────────────────────────
 * У relation'а РФ в OSM (admin_level=2) — международно признанные границы,
 * БЕЗ Крыма/Севастополя/ДНР/ЛНР/Запорожской и Херсонской областей (это уже
 * встречалось в fetch-russia-geodata.mjs — там же объяснение, почему для этих
 * шести субъектов пришлось запрашивать geometry отдельно). Здесь решение
 * другое и проще: тянем ВСЕ place=city/town из широкого bbox, покрывающего
 * Россию целиком (включая все шесть спорных субъектов), а не фильтруем по
 * стране на стороне Overpass — принадлежность России определяем САМИ, точной
 * геометрией регионов, которая уже лежит в russiaRegionsGeo.json (89 субъектов,
 * включая корректные контуры для всех шести). Точка-в-полигоне против реальных
 * контуров надёжнее, чем полагаться на то, как теги/relation'ы могут быть (не)
 * расставлены в OSM для новых регионов.
 *
 * Bbox широкий (захватывает соседние страны — Казахстан, Монголию, Китай,
 * Балтию, Финляндию, Грузию, Азербайджан и т.д.) — лишние точки отсекаются
 * тем же point-in-polygon фильтром. Россия пересекает 180° меридиан
 * (Чукотка) — Overpass bbox не поддерживает "перенос" через антимеридиан,
 * поэтому запрос идёт двумя частями (западная/восточная).
 */

import { writeFileSync, mkdirSync, readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const OUT_PATH = join(__dirname, '../src/components/fleet/russiaCitiesGeo.json');
const REGIONS_PATH = join(__dirname, '../src/components/fleet/russiaRegionsGeo.json');

const ENDPOINTS = [
  'https://overpass-api.de/api/interpreter',
  'https://overpass.kumi.systems/api/interpreter',
  'https://overpass.openstreetmap.ru/api/interpreter',
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function queryOverpass(query, label, retries = 4) {
  for (let attempt = 0; attempt <= retries; attempt++) {
    if (attempt > 0) {
      const cooldown = 20_000 * attempt;
      console.log(`  [${label}] Retry ${attempt}/${retries} after ${cooldown / 1000}s cooldown...`);
      await sleep(cooldown);
    }
    for (const endpoint of ENDPOINTS) {
      try {
        console.log(`  [${label}] Querying ${endpoint}...`);
        const res = await fetch(endpoint, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            Accept: '*/*',
            'User-Agent': 'vsks-crm-fleet-cities-fetch/1.0 (+dev-tool, one-off)',
          },
          body: 'data=' + encodeURIComponent(query),
          signal: AbortSignal.timeout(240_000),
        });
        if (res.status === 429 || res.status === 504) {
          console.warn(`    [${label}] HTTP ${res.status} (rate limited/timeout), waiting 20s...`);
          await sleep(20_000);
          continue;
        }
        if (!res.ok) {
          console.warn(`    [${label}] HTTP ${res.status}, trying next endpoint...`);
          continue;
        }
        const data = await res.json();
        console.log(`    [${label}] OK — ${data.elements?.length ?? 0} elements`);
        return data;
      } catch (err) {
        console.warn(`    [${label}] Failed: ${err.message}, trying next endpoint...`);
      }
    }
  }
  throw new Error(`[${label}] All Overpass endpoints failed after retries`);
}

// ── Point-in-polygon против реальных контуров регионов (89 субъектов) ──────
const regionsData = JSON.parse(readFileSync(REGIONS_PATH, 'utf-8'));

function ringBBox(ring) {
  let minLon = Infinity, maxLon = -Infinity, minLat = Infinity, maxLat = -Infinity;
  for (const [lon, lat] of ring) {
    if (lon < minLon) minLon = lon;
    if (lon > maxLon) maxLon = lon;
    if (lat < minLat) minLat = lat;
    if (lat > maxLat) maxLat = lat;
  }
  return { minLon, maxLon, minLat, maxLat };
}

// Ray casting (odd-even rule) — стандартный point-in-polygon для одного кольца.
function pointInRing(lon, lat, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    const intersect = ((yi > lat) !== (yj > lat)) &&
      (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi);
    if (intersect) inside = !inside;
  }
  return inside;
}

const regionsIndexed = regionsData.regions.map((r) => ({
  name: r.name,
  rings: r.rings.map((ring) => ({ ring, bbox: ringBBox(ring) })),
  bbox: (() => {
    let minLon = Infinity, maxLon = -Infinity, minLat = Infinity, maxLat = -Infinity;
    for (const ring of r.rings) {
      const b = ringBBox(ring);
      if (b.minLon < minLon) minLon = b.minLon;
      if (b.maxLon > maxLon) maxLon = b.maxLon;
      if (b.minLat < minLat) minLat = b.minLat;
      if (b.maxLat > maxLat) maxLat = b.maxLat;
    }
    return { minLon, maxLon, minLat, maxLat };
  })(),
}));

/** Находит субъект РФ, которому принадлежит точка (или null, если ни один
 * регион её не содержит — точка за пределами России). Bbox-предфильтр на
 * уровне региона и на уровне каждого кольца — иначе 89 контуров × тысячи
 * точек городов было бы слишком медленно. */
function findRegionForPoint(lon, lat) {
  for (const region of regionsIndexed) {
    const b = region.bbox;
    if (lon < b.minLon || lon > b.maxLon || lat < b.minLat || lat > b.maxLat) continue;
    for (const { ring, bbox } of region.rings) {
      if (lon < bbox.minLon || lon > bbox.maxLon || lat < bbox.minLat || lat > bbox.maxLat) continue;
      if (pointInRing(lon, lat, ring)) return region.name;
    }
  }
  return null;
}

// ── QUERY: place=city|town по широкому bbox (запад/восток от антимеридиана) ─
// bbox формат Overpass: (south,west,north,east)
const Q_WEST = `
[out:json][timeout:240];
(
  nwr["place"~"^(city|town)$"](40,18,82,180);
);
out center tags;
`.trim();

const Q_EAST = `
[out:json][timeout:240];
(
  nwr["place"~"^(city|town)$"](40,-180,82,-160);
);
out center tags;
`.trim();

console.log('\n[Query WEST] place=city|town, bbox 40,18,82,180 ...');
const dWest = await queryOverpass(Q_WEST, 'WEST');

console.log('\n  Waiting 12s before next query (rate limit)...');
await sleep(12_000);

console.log('[Query EAST] place=city|town, bbox 40,-180,82,-160 (Чукотка) ...');
const dEast = await queryOverpass(Q_EAST, 'EAST');

// ── Сборка + фильтр по реальной геометрии регионов ──────────────────────────
const rawElements = [...(dWest.elements || []), ...(dEast.elements || [])];
console.log(`\nRaw elements (worldwide bbox, before RF filter): ${rawElements.length}`);

const seen = new Set(); // dedupe by type:id
const candidates = [];
for (const el of rawElements) {
  const idKey = `${el.type}:${el.id}`;
  if (seen.has(idKey)) continue;
  seen.add(idKey);

  // 2026-09: предпочитаем name:ru основному тегу name. Для Донецка, Луганска
  // и части населённых пунктов Крыма/Запорожской/Херсонской областей
  // основной тег name в OSM — украинский ("Донецьк", "Луганськ" и т.п.), а
  // русское название лежит в name:ru (проверено запросом к Overpass по
  // координатам ДНР-Донецка — см. отчёт задачи). Без этой замены поиск по
  // "донецк"/"луганск" находил бы только тёзок в Ростовской/др. областях, а
  // не сами ДНР/ЛНР-города — критичная регрессия для контрольного примера
  // задачи ("ДНР г. Донецк" должен попадать на карту).
  const name = el.tags?.['name:ru'] || el.tags?.name;
  if (!name) continue;
  const lat = el.lat ?? el.center?.lat;
  const lon = el.lon ?? el.center?.lon;
  if (typeof lat !== 'number' || typeof lon !== 'number') continue;

  candidates.push({
    name,
    lat,
    lon,
    place: el.tags?.place,
    population: el.tags?.population ? parseInt(el.tags.population, 10) || undefined : undefined,
  });
}
console.log(`After dedupe/tag validation: ${candidates.length}`);

const cities = [];
let rejectedOutsideRF = 0;
for (const c of candidates) {
  const region = findRegionForPoint(c.lon, c.lat);
  if (!region) { rejectedOutsideRF++; continue; }
  cities.push({ ...c, region });
}
console.log(`Matched to a RF region (kept): ${cities.length}`);
console.log(`Rejected (outside all 89 RF region polygons — likely another country): ${rejectedOutsideRF}`);

// ── Дедуп: тот же населённый пункт очень часто встречается в OSM несколько
// раз — как node (точка) И как way/relation (площадной контур застройки/
// административная граница) с тем же именем. Проверено эмпирически на первом
// прогоне (2026-09): дедуп по имени+координатам с точностью до ~1км оставлял
// заметное число почти-дублей (тот же город, точки на 100–300м друг от
// друга) — дедуп по имени+региону (без учёта координат) даёт куда более
// чистый результат (5398 → 3068 на первом прогоне) и не рискует потерей
// данных: два РАЗНЫХ населённых пункта с одинаковым именем в одном и том же
// субъекте РФ — исключительно редкий случай, которым можно пренебречь ради
// чистоты справочника (в отличие от одноимённых городов в РАЗНЫХ регионах —
// те специально остаются отдельными записями, см. findCityInCatalog в
// russiaCitiesCatalog.ts, который умеет разбирать такие омонимы).
function dedupKey(c) {
  return `${c.name.toLowerCase()}|${c.region}`;
}
const dedupMap = new Map();
for (const c of cities) {
  const k = dedupKey(c);
  const existing = dedupMap.get(k);
  // При дубле оставляем запись с большим population (более информативную),
  // либо ту, что place=city (точнее статуса), если population не задан ни у одной.
  if (!existing) { dedupMap.set(k, c); continue; }
  const cBetter = (c.population || 0) > (existing.population || 0) ||
    (c.place === 'city' && existing.place !== 'city' && !c.population && !existing.population);
  if (cBetter) dedupMap.set(k, c);
}
const deduped = Array.from(dedupMap.values());
console.log(`After node/way dedup: ${deduped.length}`);

// Контрольная проверка — Верея (малый город, place=town, Московская область)
// обязана присутствовать (см. задачу geo-fix #4).
const vereya = deduped.filter((c) => c.name === 'Верея');
console.log(`\nКонтроль «Верея»: ${vereya.length} совпадение(й)`, vereya);

const cityCount = deduped.filter((c) => c.place === 'city').length;
const townCount = deduped.filter((c) => c.place === 'town').length;

// ── Сортировка (по убыванию population, безымянные population — в конец) —
// стабильный порядок, детерминированный вывод, удобно для поиска топ-совпадений.
deduped.sort((a, b) => (b.population || 0) - (a.population || 0) || a.name.localeCompare(b.name, 'ru'));

// ── Компактный формат вывода (короткие ключи — держим файл в разумном
// размере, ориентир ~500КБ, см. задачу): n=name, r=region, lat/lon (3 знака —
// ~111м точности, с запасом достаточно для карты уровня "вся страна" и
// сокращает размер файла), p=place, pop=population. ────────────────────────
const ROUND = (v) => Math.round(v * 1000) / 1000;
const output = {
  generated: new Date().toISOString(),
  source: 'OpenStreetMap contributors, via Overpass API (overpass-api.de)',
  license: 'ODbL — © OpenStreetMap contributors',
  attributionRequired: '© OpenStreetMap contributors',
  method: 'nwr place=city|town по широкому bbox + принадлежность к РФ определена point-in-polygon по russiaRegionsGeo.json (89 субъектов, включая Крым/Севастополь/ДНР/ЛНР/Запорожскую/Херсонскую области)',
  count: deduped.length,
  cityCount,
  townCount,
  cities: deduped.map((c) => ({
    n: c.name,
    r: c.region,
    lat: ROUND(c.lat),
    lon: ROUND(c.lon),
    p: c.place,
    ...(c.population ? { pop: c.population } : {}),
  })),
};

mkdirSync(dirname(OUT_PATH), { recursive: true });
writeFileSync(OUT_PATH, JSON.stringify(output), 'utf-8');

const bytes = Buffer.byteLength(JSON.stringify(output), 'utf-8');
console.log(`\nDone! Cities: ${deduped.length} (city=${cityCount}, town=${townCount}), file size: ${(bytes / 1024).toFixed(1)} KB`);
console.log(`Written to ${OUT_PATH}`);
