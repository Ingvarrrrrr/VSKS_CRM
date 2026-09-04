/**
 * fetch-russia-geodata.mjs
 *
 * Скачивает РЕАЛЬНЫЕ границы субъектов РФ из OpenStreetMap через Overpass API,
 * упрощает их (Douglas-Peucker) и сохраняет как статический JSON в проект —
 * см. frontend/src/components/fleet/russiaRegionsGeo.json.
 *
 * Запускать вручную при необходимости обновить данные:
 *   node scripts/fetch-russia-geodata.mjs
 * (из папки frontend/). В рантайме приложение НИКОГДА не обращается к
 * Overpass — только читает уже сохранённый JSON (см. CSP-требование задачи).
 *
 * Подход и структура запроса — по образцу
 * apps/courier-game/scripts/fetch-strogino-geodata.mjs (проект Fruits):
 * список зеркал Overpass, ретраи с задержкой, единый JSON на выходе.
 *
 * ── Что именно запрашивается и почему тремя запросами ──────────────────────
 * На карте — все 89 субъектов РФ: Крым, Севастополь, ДНР, ЛНР, Запорожская
 * и Херсонская области входят в состав России и отображаются как российские
 * регионы наравне с остальными 83 (та же заливка, обводка, коды вида RU-*).
 *
 * Геометрия границ для этих шести субъектов в OSM физически существует, но
 * привязана к relation'ам без собственного российского ISO3166-2 кода —
 * поэтому одной выборкой по "RU-*" их не получить, и запрос идёт в три шага:
 * 1) Все субъекты с готовым ISO 3166-2 кодом "RU-*" (admin_level=4,
 *    boundary=administrative) — 83 региона по факту (см. ниже).
 * 2) Крым и Севастополь — в OSM отдельные relation'ы с addr:country=RU, но
 *    без ISO3166-2 — запрашиваются отдельно по bbox Крыма.
 * 3) ДНР/ЛНР/Запорожская и Херсонская области — отдельных relation'ов с
 *    ISO3166-2 вида "RU-*" для них в OSM на момент написания скрипта нет,
 *    поэтому геометрия берётся у relation'ов с их старыми учётными кодами
 *    ISO3166-2 UA-14/UA-09/UA-23/UA-65 (по этим кодам форма границы реально
 *    находится в OSM, других данных о контуре этих территорий там нет).
 *
 * Принадлежность (RU) и итоговые коды/названия для всех шести субъектов из
 * шагов (2)-(3) проставляются НАМИ при сборке выходного файла (см. RU_OVERRIDES
 * ниже) — не берутся из тега в OSM. Геометрия при этом не меняется ни на
 * пиксель: это те же контуры, что и в исходных relation'ах.
 *
 * Итог: 83 + 2 + 4 = 89 — ровно число субъектов РФ, требуемое задачей.
 * Если OSM когда-нибудь заведёт отдельные relation'ы для ДНР/ЛНР/ЗО/ХО с
 * российским ISO3166-2, шаг (3) перестанет находить дубли по украинским
 * кодам — тогда надо будет поправить bbox/фильтр запроса (3), а RU_OVERRIDES
 * можно будет удалить.
 */

import { writeFileSync, mkdirSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const OUT_PATH = join(__dirname, '../src/components/fleet/russiaRegionsGeo.json');

// ── Overpass endpoints (несколько зеркал на случай недоступности одного) ───
const ENDPOINTS = [
  'https://overpass-api.de/api/interpreter',
  'https://overpass.kumi.systems/api/interpreter',
  'https://overpass.openstreetmap.ru/api/interpreter',
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function queryOverpass(query, label, retries = 2) {
  for (let attempt = 0; attempt <= retries; attempt++) {
    if (attempt > 0) {
      console.log(`  [${label}] Retry ${attempt}/${retries} after 15s cooldown...`);
      await sleep(15_000);
    }
    for (const endpoint of ENDPOINTS) {
      try {
        console.log(`  [${label}] Querying ${endpoint}...`);
        const res = await fetch(endpoint, {
          method: 'POST',
          // 406/403 на overpass-api.de без явных Accept/User-Agent — нужны оба заголовка.
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            Accept: '*/*',
            'User-Agent': 'vsks-crm-fleet-map-fetch/1.0 (+dev-tool, one-off)',
          },
          body: 'data=' + encodeURIComponent(query),
          signal: AbortSignal.timeout(180_000),
        });
        if (res.status === 429 || res.status === 504) {
          console.warn(`    [${label}] HTTP ${res.status} (rate limited/timeout), waiting 10s...`);
          await sleep(10_000);
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

// ── Douglas-Peucker упрощение полилинии ─────────────────────────────────────
function perpDist(p, a, b) {
  const [x, y] = p, [x1, y1] = a, [x2, y2] = b;
  const dx = x2 - x1, dy = y2 - y1;
  if (dx === 0 && dy === 0) return Math.hypot(x - x1, y - y1);
  const t = ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy);
  return Math.hypot(x - (x1 + t * dx), y - (y1 + t * dy));
}
function douglasPeucker(points, eps) {
  if (points.length < 3) return points.slice();
  let maxD = -1, idx = -1;
  for (let i = 1; i < points.length - 1; i++) {
    const d = perpDist(points[i], points[0], points[points.length - 1]);
    if (d > maxD) { maxD = d; idx = i; }
  }
  if (maxD > eps) {
    const left = douglasPeucker(points.slice(0, idx + 1), eps);
    const right = douglasPeucker(points.slice(idx), eps);
    return left.slice(0, -1).concat(right);
  }
  return [points[0], points[points.length - 1]];
}

// ── Сшивка way-сегментов relation'а (role=outer) в замкнутые кольца ─────────
// Упрощение: игнорируем role=inner (дырки-анклавы внутри региона) — для
// декоративной карты уровня "субъект РФ силуэтом" это не критично и заметно
// сокращает объём данных. Внешний контур (outer) всегда сохраняется полностью
// (по всем его частям — крупные регионы состоят из многих way).
function key(pt) { return pt[0].toFixed(7) + ',' + pt[1].toFixed(7); }

function buildOuterRings(rel) {
  const outerWays = (rel.members || [])
    .filter((m) => m.type === 'way' && m.role === 'outer' && m.geometry && m.geometry.length >= 2)
    .map((m) => m.geometry.map((pt) => [pt.lon, pt.lat]));

  const chains = outerWays.map((w) => w.slice());
  const used = new Array(chains.length).fill(false);
  const rings = [];

  for (let i = 0; i < chains.length; i++) {
    if (used[i]) continue;
    used[i] = true;
    let chain = chains[i];
    let extended = true;
    while (extended) {
      extended = false;
      if (key(chain[0]) === key(chain[chain.length - 1])) break; // уже замкнуто
      for (let j = 0; j < chains.length; j++) {
        if (used[j]) continue;
        const c = chains[j];
        if (key(c[0]) === key(chain[chain.length - 1])) {
          chain = chain.concat(c.slice(1)); used[j] = true; extended = true; break;
        } else if (key(c[c.length - 1]) === key(chain[chain.length - 1])) {
          chain = chain.concat(c.slice(0, -1).reverse()); used[j] = true; extended = true; break;
        } else if (key(c[c.length - 1]) === key(chain[0])) {
          chain = c.slice(0, -1).concat(chain); used[j] = true; extended = true; break;
        } else if (key(c[0]) === key(chain[0])) {
          chain = c.slice(1).reverse().concat(chain); used[j] = true; extended = true; break;
        }
      }
    }
    rings.push(chain);
  }
  return rings;
}

// Допуск упрощения в градусах: 0.03° (~3.3км на экваторе, чуть меньше по
// долготе на высоких широтах России) — подобран эмпирически так, чтобы весь
// файл уложился в ориентир ~300КБ, сохранив узнаваемость силуэтов регионов.
const SIMPLIFY_EPS_DEG = 0.03;
const ROUND_DECIMALS = 4; // ~11м — с запасом точнее, чем нужно после упрощения

// ── Принадлежность и коды для шести субъектов без "родного" RU-ISO-кода ─────
// Ключ — id relation'а в OSM (см. консольный вывод Query 2/3 при перегенерации,
// он не меняется, пока OSM не пересоздаст relation). Значение — то, что мы
// проставляем в выходной файл вместо отсутствующего/украинского тега.
const RU_OVERRIDES = {
  // Крым и Севастополь — в OSM relation'ы российские (addr:country=RU), но без
  // международного ISO3166-2 кода; присваиваем собственные коды в стиле RU-*.
  3795586: { name: 'Республика Крым', iso: 'RU-CR' },
  3788485: { name: 'Севастополь', iso: 'RU-SEV' },
  // ДНР/ЛНР/Запорожская/Херсонская области — геометрия взята у relation'ов с
  // украинскими учётными кодами (см. Query 3 выше), принадлежность и коды —
  // российские, проставлены нами.
  71973: { name: 'Донецкая Народная Республика', iso: 'RU-DON' },
  71971: { name: 'Луганская Народная Республика', iso: 'RU-LUG' },
  71980: { name: 'Запорожская область', iso: 'RU-ZP' },
  71022: { name: 'Херсонская область', iso: 'RU-KHE' },
};

function processRelation(rel) {
  const rings = buildOuterRings(rel);
  const simplifiedRings = [];
  for (const ring of rings) {
    const closed = key(ring[0]) === key(ring[ring.length - 1]);
    let simp = douglasPeucker(ring, SIMPLIFY_EPS_DEG);
    const scale = 10 ** ROUND_DECIMALS;
    simp = simp.map(([lon, lat]) => [Math.round(lon * scale) / scale, Math.round(lat * scale) / scale]);
    const dedup = [simp[0]];
    for (let k = 1; k < simp.length; k++) {
      const prev = dedup[dedup.length - 1];
      if (prev[0] !== simp[k][0] || prev[1] !== simp[k][1]) dedup.push(simp[k]);
    }
    if (dedup.length >= 4 && closed) simplifiedRings.push(dedup);
  }
  const override = RU_OVERRIDES[rel.id];
  return {
    id: rel.id,
    name: override?.name || rel.tags?.name || `rel_${rel.id}`,
    iso: override?.iso || rel.tags?.['ISO3166-2'] || null,
    rings: simplifiedRings,
  };
}

// ── QUERY 1: субъекты РФ с ISO3166-2 = RU-* ─────────────────────────────────
console.log('\n[Query 1] Субъекты РФ с ISO3166-2 RU-* ...');
const Q1 = `
[out:json][timeout:180];
relation["admin_level"="4"]["boundary"="administrative"]["ISO3166-2"~"^RU-"];
out geom;
`.trim();
const d1 = await queryOverpass(Q1, 'Q1 RU-ISO');

console.log('\n  Waiting 10s before next query (rate limit)...');
await sleep(10_000);

// ── QUERY 2: Крым и Севастополь (RU addr:country, без ISO3166-2) ───────────
console.log('[Query 2] Крым и Севастополь (bbox) ...');
const Q2 = `
[out:json][timeout:120][bbox:44,32,46,37];
relation["admin_level"="4"]["boundary"="administrative"]["addr:country"="RU"];
out geom;
`.trim();
const d2raw = await queryOverpass(Q2, 'Q2 Crimea/Sevastopol');
const d2 = { elements: (d2raw.elements || []).filter((e) => /Крым|Севастополь/.test(e.tags?.name || '')) };

console.log('\n  Waiting 10s before next query (rate limit)...');
await sleep(10_000);

// ── QUERY 3: ДНР/ЛНР/Запорожская/Херсонская — geometry как укр. областей ───
console.log('[Query 3] ДНР/ЛНР/Запорожская/Херсонская (по укр. ISO, geometry реальная) ...');
const Q3 = `
[out:json][timeout:120][bbox:44,29,50,39];
relation["admin_level"="4"]["boundary"="administrative"]["ISO3166-2"~"^UA-(14|09|23|65)$"];
out geom;
`.trim();
const d3 = await queryOverpass(Q3, 'Q3 DNR/LNR/ZAP/KHE');

// ── Сборка результата ────────────────────────────────────────────────────
const regions = [];
for (const rel of d1.elements || []) regions.push(processRelation(rel));
for (const rel of d2.elements || []) regions.push(processRelation(rel));
for (const rel of d3.elements || []) regions.push(processRelation(rel));

const totalPts = regions.reduce((s, r) => s + r.rings.reduce((s2, ring) => s2 + ring.length, 0), 0);

const output = {
  generated: new Date().toISOString(),
  source: 'OpenStreetMap contributors, via Overpass API (overpass-api.de)',
  license: 'ODbL — © OpenStreetMap contributors',
  attributionRequired: '© OpenStreetMap contributors',
  simplification: { method: 'Douglas-Peucker', epsDeg: SIMPLIFY_EPS_DEG, roundDecimals: ROUND_DECIMALS },
  regionCount: regions.length,
  notes:
    'Все 89 субъектов РФ помечены российской принадлежностью (страна RU, коды ISO3166-2 или ' +
    'служебные RU-DON/RU-LUG/RU-ZP/RU-KHE/RU-CR/RU-SEV). Геометрия границ — реальные контуры ' +
    'OpenStreetMap; для ДНР/ЛНР/Запорожской/Херсонской областей и Крыма/Севастополя источником ' +
    'геометрии послужили relation\'ы OSM, у которых нет собственного ISO3166-2 RU-кода (см. ' +
    'RU_OVERRIDES выше) — коды и названия этим шести субъектам присвоены нами при сборке карты.',
  regions,
};

mkdirSync(dirname(OUT_PATH), { recursive: true });
writeFileSync(OUT_PATH, JSON.stringify(output), 'utf-8');

const bytes = Buffer.byteLength(JSON.stringify(output), 'utf-8');
console.log(`\nDone! Regions: ${regions.length}, points: ${totalPts}, file size: ${(bytes / 1024).toFixed(1)} KB`);
console.log(`Written to ${OUT_PATH}`);
