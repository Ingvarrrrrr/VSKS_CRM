import { computed, type Ref } from 'vue'
import { type MapPin, projectLatLonToSvg } from '@/components/fleet/russiaMapPins'
import { HALO_GAP } from '@/components/fleet/mapLabelLayout'
import { citiesCatalogReady, findCityInCatalog } from '@/components/fleet/russiaCitiesCatalog'
import type { RegionItem } from './useRegionsData'

// 2026-09 (geo-fix #4): пины строятся из regionData (место нахождения ТС), а
// НЕ из организаций (у которых к тому же lat/lon в БД не заполнены). Места,
// для которых справочник городов (russiaCitiesCatalog.ts — OSM place=city/
// town, см. fetch-russia-cities.mjs) не находит совпадения, на карту не
// попадают — они по-прежнему видны в списке/карточках ниже как есть.
//
// Владелец (задача geo-fix #4, п.2): "Луганск над Донецком — вообще
// непонятно". Причина — при равнопромежуточной проекции ВСЕЙ России соседние
// города (Донецк/Луганск ~50км друг от друга) оказываются в считанных
// пикселях, а старые кружки росли пропорционально числу машин ВПЛОТЬ до 43px
// радиуса — крупный кружок физически накрывал соседний мелкий город и его
// подпись. Теперь:
//  - радиус кружка ограничен жёстким потолком (см. PIN_MIN_R/PIN_MAX_R —
//    заметно меньше прежних 10..43) — кружок остаётся "бейджем с числом",
//    а не разрастается до размера, способного перекрыть соседа;
//  - declutterPins раздвигает центры не по сумме радиусов, а по сумме
//    (радиус + HALO_GAP) — тот же запас, что использует mapLabelLayout.ts
//    для проверки "подпись vs чужой маркер", поэтому даже полупрозрачный
//    ореол (halo) одного пина не перекрывает круг соседнего;
//  - у каждого пина сохраняется anchorX/anchorY (истинная гео-проекция ДО
//    раздвижки) — RussiaMapSvg.vue рисует тонкую выноску к этой точке, если
//    раздвижка сдвинула пин заметно, чтобы не терять привязку к географии.
const PIN_MIN_R = 12
const PIN_MAX_R = 20
const PIN_COLORS = ['#6aa6ff', '#f6b34a', '#22c997', '#8b5cf6', '#5dd0ff', '#ff5b6a']

// Раздвигаем так, чтобы не пересекались даже ореолы (halo) — HALO_GAP тот же,
// что использует RussiaMapSvg.vue/mapLabelLayout.ts для самого рисования и
// для раздвижки подписей (единая константа, не дублируем магическое число).
function declutterPins(pins: MapPin[]): MapPin[] {
  const MARGIN = 6
  for (let pass = 0; pass < 30; pass++) {
    let moved = false
    for (let i = 0; i < pins.length; i++) {
      for (let j = i + 1; j < pins.length; j++) {
        const a = pins[i]
        const b = pins[j]
        const dx = b.x - a.x
        const dy = b.y - a.y
        const dist = Math.hypot(dx, dy) || 0.01
        const minDist = (a.radius + HALO_GAP) + (b.radius + HALO_GAP) + MARGIN
        if (dist < minDist) {
          const push = (minDist - dist) / 2
          const ux = dx / dist
          const uy = dy / dist
          a.x -= ux * push
          a.y -= uy * push
          b.x += ux * push
          b.y += uy * push
          moved = true
        }
      }
    }
    if (!moved) break
  }
  return pins
}

// 2026-09 (правка владельца): некоторые location_city в БД содержат регион,
// дописанный в скобках при выборе города из справочника (например «Ростов-
// на-Дону (Ростовская область)») — это часть сырых данных, её не трогаем ни
// в списке, ни в карточках, ни в заголовке попапа (locationSubtitle там же
// показывает регион отдельной строкой — вместе это не дублирование, а
// уточнение для одноимённых городов). На самой КАРТЕ владелец попросил
// оставить только имя города — карта и так однозначно показывает регион
// географически. Отбрасываем ТОЛЬКО хвостовую скобочную группу для
// отображения — raw region ("ДНР г. Донецк", без скобок) функцию не
// затрагивает, id пина (используется для drill) остаётся сырым loc.region.
function mapPinDisplayName(region: string): string {
  const stripped = region.replace(/\s*\([^()]*\)\s*$/, '').trim()
  return stripped || region
}

export function useMapPins(sortedLocations: Ref<RegionItem[]>) {
  const mapPins = computed<MapPin[]>(() => {
    // Зависимость от готовности каталога — computed пересчитается сам, когда
    // fetch/import() догрузит справочник (см. onMounted во view), до этого
    // пины просто отсутствуют (каталог обычно грузится за десятки мс).
    void citiesCatalogReady.value

    const geoLocations = sortedLocations.value
      .map(loc => ({ loc, hit: findCityInCatalog(loc.region) }))
      .filter((x): x is { loc: RegionItem; hit: NonNullable<ReturnType<typeof findCityInCatalog>> } => x.hit !== null)

    if (!geoLocations.length) return []

    const maxCount = Math.max(...geoLocations.map(g => g.loc.count), 1)

    const pins = geoLocations.map(({ loc, hit }, idx) => {
      const pct = loc.count / maxCount
      const { x, y } = projectLatLonToSvg(hit.lat, hit.lon)
      return {
        id: loc.region,
        // 2026-09 (доделка): раньше здесь ещё был sub: `${loc.count} ТС` —
        // отдельная под-подпись под пином. Требование владельца: у пина ровно
        // две вещи — кружок с числом ВНУТРИ (уже есть, см. RussiaMapSvg.vue
        // <text>{{ pin.count }}</text>) и название города рядом. Отдельная
        // под-подпись с тем же числом дублировала то, что уже написано в
        // кружке, — убрана полностью (pin.sub не задаём).
        // 2026-09 (правка владельца): на самой КАРТЕ — только название города,
        // без региона в скобках (владелец: «карта это и так решает»). id
        // остаётся сырым loc.region (используется для дриллдауна и должен
        // точно совпадать с location_city в БД) — усечение только для name,
        // т.е. только для того, что реально печатается на карте. Список «Топ
        // мест нахождения», карточки и заголовок попапа регион не теряют —
        // там он различает одноимённые города (см. locationSubtitle рядом).
        name: mapPinDisplayName(loc.region),
        x, y,
        anchorX: x,
        anchorY: y,
        // sqrt — differences менее экстремальны, чем линейный рост: 1 машина
        // и 50 машин не должны давать 12px против 43px (см. геометрический разбор выше).
        radius: Math.round(PIN_MIN_R + Math.sqrt(pct) * (PIN_MAX_R - PIN_MIN_R)),
        count: loc.count,
        color: PIN_COLORS[idx % PIN_COLORS.length],
      }
    })

    return declutterPins(pins)
  })

  return { mapPins }
}
