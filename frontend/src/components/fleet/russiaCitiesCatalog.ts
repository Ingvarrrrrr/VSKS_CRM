/**
 * russiaCitiesCatalog.ts (geo-fix #4, 2026-09)
 *
 * Справочник населённых пунктов России — источник координат для карты
 * /fleet/regions и данные для автодополнения поля «Место нахождения, город»
 * в карточке ТС (VehicleDetailView.vue). Заменяет прежнюю зашитую таблицу
 * KNOWN_CITY_COORDS на 20 городов (russiaMapPins.ts) — тот список ловил
 * только явно перечисленные ключевые слова и не находил малые города
 * ("Верея" — контрольный пример владельца).
 *
 * Данные — статический JSON (russiaCitiesGeo.json), собранный из OSM
 * (place=city/place=town) скриптом frontend/scripts/fetch-russia-cities.mjs.
 * В рантайме к сети не обращаемся — только читаем уже сохранённый файл через
 * динамический import() (Vite кладёт его в отдельный чанк, не раздувает
 * общий бандл — см. Vite build report в отчёте задачи).
 *
 * Модуль вынесен отдельно от компонентов (Правило №5 — не размазывать логику
 * поиска/нормализации по вьюхам): и RussiaMapSvg/FleetRegionsView (карта), и
 * VehicleDetailView (автодополнение) используют один и тот же справочник и
 * одну и ту же логику нормализации свободного текста.
 */

export interface CityEntry {
  name: string
  region: string
  lat: number
  lon: number
  place: 'city' | 'town'
  population?: number
}

interface CitiesGeoJson {
  count: number
  cityCount: number
  townCount: number
  cities: { n: string; r: string; lat: number; lon: number; p: 'city' | 'town'; pop?: number }[]
}

let catalog: CityEntry[] = []
// Индекс: нормализованное (lower-case) имя города → все совпадающие записи
// (в России немало городов-омонимов в разных регионах — см. отчёт задачи).
let byName: Map<string, CityEntry[]> = new Map()
let loadingPromise: Promise<CityEntry[]> | null = null

/** Реактивный флаг готовности — используется computed-выражениями (например
 * mapPins в FleetRegionsView.vue), чтобы пересчитаться, когда каталог
 * догрузится (import() асинхронный, а findCityInCatalog — синхронный API). */
import { ref } from 'vue'
export const citiesCatalogReady = ref(false)

function buildIndex(entries: CityEntry[]) {
  byName = new Map()
  for (const c of entries) {
    const key = c.name.toLowerCase()
    const arr = byName.get(key)
    if (arr) arr.push(c)
    else byName.set(key, [c])
  }
}

/** Загружает справочник (однократно, дальнейшие вызовы возвращают тот же
 * промис/результат). Вызывать в onMounted перед первым использованием
 * findCityInCatalog/searchCities, если критично не пропустить первую отрисовку —
 * при работе с computed достаточно прочитать citiesCatalogReady.value внутри
 * computed, чтобы он пересчитался после загрузки. */
export function loadCitiesCatalog(): Promise<CityEntry[]> {
  if (catalog.length) return Promise.resolve(catalog)
  if (loadingPromise) return loadingPromise
  loadingPromise = import('./russiaCitiesGeo.json')
    .then((mod) => {
      const data = (mod as unknown as { default: CitiesGeoJson }).default
      catalog = data.cities.map((c) => ({
        name: c.n,
        region: c.r,
        lat: c.lat,
        lon: c.lon,
        place: c.p,
        population: c.pop,
      }))
      buildIndex(catalog)
      citiesCatalogReady.value = true
      return catalog
    })
    .catch((err) => {
      // Справочник — статический файл в бандле, к сети не обращается; сбой
      // возможен только при повреждении/отсутствии файла. Деградация мягкая:
      // каталог остаётся пустым, поиск/автодополнение просто ничего не находят,
      // ручной ввод текста (свободный) продолжает работать.
      console.error('russiaCitiesCatalog: не удалось загрузить russiaCitiesGeo.json', err)
      catalog = []
      byName = new Map()
      citiesCatalogReady.value = true
      return catalog
    })
  return loadingPromise
}

/** Отображаемая подпись для пункта выпадающего списка/выбранного значения —
 * с регионом в скобках, чтобы различать омонимы ("Верея (Московская область)"). */
export function cityDisplayLabel(c: CityEntry): string {
  return `${c.name} (${c.region})`
}

// ── Нормализация свободного текста location_city ────────────────────────────
// В базе уже есть значения вида "ДНР г. Донецк", "Курск", "Ростов-на-Дону" —
// свободный текст с необязательными региональными префиксами. Разбиваем на
// слова по пробелам/запятым (дефисы внутри слова — часть названия города,
// напр. "Ростов-на-Дону" — не трогаем), отбрасываем только служебные токены.
const NOISE_TOKENS = new Set([
  'г', 'город', 'гор', 'пос', 'посёлок', 'поселок', 'п', 'рп',
  'обл', 'область', 'респ', 'республика', 'край', 'ао',
  'днр', 'лнр',
])

function stripPunct(word: string): string {
  return word.replace(/^[.,;:()«»"']+|[.,;:()«»"']+$/g, '')
}

/** Разбирает свободный текст на "базовое" имя (без региональных префиксов) и
 * необязательную "подсказку региона" из скобок в конце (формат, в который
 * автодополнение записывает значение — cityDisplayLabel выше). */
function parseLocationCity(raw: string): { base: string; regionHint: string | null } {
  const trimmed = (raw || '').trim()
  if (!trimmed) return { base: '', regionHint: null }

  const parenMatch = trimmed.match(/\(([^)]+)\)\s*$/)
  const regionHint = parenMatch ? parenMatch[1].trim().toLowerCase() : null
  const withoutParen = parenMatch ? trimmed.slice(0, parenMatch.index).trim() : trimmed

  const words = withoutParen.split(/[\s,]+/).filter(Boolean)
  const meaningful = words
    .map(stripPunct)
    .filter((w) => w && !NOISE_TOKENS.has(w.toLowerCase()))

  const base = (meaningful.length ? meaningful : words).join(' ').trim()
  return { base, regionHint }
}

/** Ищет запись справочника по свободному тексту location_city. Возвращает
 * null, если совпадений нет (город идёт в группу "не найден на карте" —
 * список/карточки продолжают показывать raw-текст как есть, см. задачу). */
export function findCityInCatalog(raw: string): CityEntry | null {
  const { base, regionHint } = parseLocationCity(raw)
  if (!base) return null

  const candidates = byName.get(base.toLowerCase())
  if (!candidates || !candidates.length) return null
  if (candidates.length === 1) return candidates[0]

  // Омонимы (несколько городов с одинаковым именем в разных регионах) —
  // сперва пробуем подсказку региона (из скобок или из остатка raw-строки),
  // иначе берём самый крупный по населению (best-effort, см. отчёт задачи).
  if (regionHint) {
    const hinted = candidates.find(
      (c) => c.region.toLowerCase().includes(regionHint) || regionHint.includes(c.region.toLowerCase())
    )
    if (hinted) return hinted
  }
  const lowRaw = raw.toLowerCase()
  const hintedInRaw = candidates.find((c) => lowRaw.includes(c.region.toLowerCase()))
  if (hintedInRaw) return hintedInRaw

  return [...candidates].sort((a, b) => (b.population || 0) - (a.population || 0))[0]
}

/** Поиск для автодополнения — сортировка: точное совпадение с начала слова
 * (город или второе слово в названии, напр. "Нижний Новгород" по "новг") >
 * вхождение подстрокой > остальное; при равном ранге — короче название вперёд
 * (доделка 2026-09: короткое имя, начинающееся на запрос, — более точное
 * совпадение, чем длинное составное; population в качестве ЕДИНСТВЕННОГО
 * тай-брейка хоронил маленькие города за миллионниками с тем же префиксом —
 * контрольный пример владельца "Верея" по запросу "Вер" был 23-м из 34
 * совпадений, глубоко под сгибом списка, хотя название "Верея" самое
 * короткое и по факту ближе всего к запросу), затем крупнее население (тай-
 * брейк для городов-омонимов с ОДИНАКОВЫМ именем — напр. оба "Донецка" по
 * запросу "донецк", где длина имени не различает варианты), иначе по алфавиту.
 * Ограничение limit — не рендерить тысячи строк в выпадающем списке разом. */
export function searchCities(query: string, limit = 30): CityEntry[] {
  const q = query.trim().toLowerCase()
  if (!q || !catalog.length) return []

  const scored: { c: CityEntry; score: number }[] = []
  for (const c of catalog) {
    const nameLow = c.name.toLowerCase()
    let score = -1
    if (nameLow.startsWith(q)) score = 3
    else if (nameLow.split(/[\s-]+/).some((w) => w.startsWith(q))) score = 2
    else if (nameLow.includes(q)) score = 1
    if (score >= 0) scored.push({ c, score })
  }

  scored.sort((a, b) =>
    b.score - a.score ||
    a.c.name.length - b.c.name.length ||
    (b.c.population || 0) - (a.c.population || 0) ||
    a.c.name.localeCompare(b.c.name, 'ru')
  )
  return scored.slice(0, limit).map((s) => s.c)
}

/** Только для диагностики/тестов — текущий размер каталога (0, пока не загружен). */
export function getCatalogSize(): number {
  return catalog.length
}
