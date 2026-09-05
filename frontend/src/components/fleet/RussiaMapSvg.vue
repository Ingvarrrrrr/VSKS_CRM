<template>
  <div class="russia-map" :class="{ 'russia-map--light': !isDark }">
    <svg
      ref="svgEl"
      :viewBox="viewBoxStr"
      xmlns="http://www.w3.org/2000/svg"
      class="russia-map__svg"
      @wheel.prevent="onWheel"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
      @pointerleave="onPointerUp"
    >
      <!-- Grid background (под картой, чтобы не спорить с границами регионов) -->
      <defs>
        <pattern id="grid-bg" width="47" height="47" patternUnits="userSpaceOnUse">
          <path d="M 47 0 L 0 0 0 47" fill="none" :stroke="contourStroke" stroke-width="0.4" opacity="0.35"/>
        </pattern>
      </defs>
      <rect width="1171" height="611" fill="url(#grid-bg)" opacity="0.35" rx="12"/>

      <!-- Настоящие границы субъектов РФ (2026-09, geo-fix #3): раньше здесь
           рисовалась художественная схема (94 контура на глаз, не в
           картографической проекции — пины на неё физически не ложились).
           Теперь контуры — реальная геометрия OSM (Overpass API,
           admin_level=4), см. russiaRegionsGeo.json + fetch-russia-geodata.mjs,
           переведённая в SVG той же функцией проекции (projectLatLonToSvg из
           russiaMapPins.ts), что и пины городов ниже. Данные грузятся
           динамическим import() — отдельный чанк, не раздувает общий бандл
           (см. regionPaths/loadRegionGeodata). Регионы получилось 89 (см.
           отчёт задачи geo-fix #3), но они по-прежнему не кликабельны и не
           подписаны — единый нейтральный стиль подложки под пины. -->
      <path
        v-for="rp in regionPaths"
        :key="rp.key"
        :d="rp.d"
        :fill="contourFill"
        :stroke="contourStroke"
        stroke-width="1"
        stroke-linejoin="round"
      />

      <!-- Connecting lines (transfers between HQs) -->
      <!-- 2026-09: убран безусловный демо-фолбэк (раньше рисовался всегда, когда
           connections пуст, независимо от реальных данных — вводил в заблуждение). -->
      <g v-if="connections.length">
        <line
          v-for="(c, i) in connections"
          :key="`conn-${i}`"
          :x1="c.from.x"
          :y1="c.from.y"
          :x2="c.to.x"
          :y2="c.to.y"
          :stroke="contourStroke"
          stroke-width="1.2"
          stroke-dasharray="3 3"
          opacity="0.4"
        />
      </g>

      <!-- Выноски (leader lines) — 2026-09 (geo-fix #4): близкие города (Донецк/
           Луганск/Курск и т.п.) при равнопромежуточной проекции всей страны
           могут оказаться в считанных пикселях друг от друга — раздвижка
           declutterPins (FleetRegionsView.vue) физически сдвигает пин от его
           истинных координат, чтобы кружки не перекрывались. Тонкая линия к
           точке anchor* (истинная проекция) держит понятную привязку к
           географии — без неё сдвинутый пин выглядел бы просто "рядом, но
           непонятно, откуда взялся". Рисуются под пинами (раньше в разметке),
           чтобы не перекрывать сами маркеры/подписи. -->
      <g v-if="pinsWithLeader.length">
        <g v-for="pin in pinsWithLeader" :key="`leader-${pin.id}`">
          <line
            :x1="pin.anchorX" :y1="pin.anchorY" :x2="pin.x" :y2="pin.y"
            :stroke="pin.color" stroke-width="1.3" stroke-dasharray="2 3" opacity="0.55"
          />
          <circle :cx="pin.anchorX" :cy="pin.anchorY" r="2.5" :fill="pin.color" :stroke="pinStroke" stroke-width="1" opacity="0.9"/>
        </g>
      </g>

      <!-- Pins via props (or default pins when none passed).
           2026-09: раньше hover навешивался CSS-трансформом прямо на группу, у которой
           уже был SVG-атрибут transform="translate(...)" — CSS transform на hover ПОЛНОСТЬЮ
           перекрывал этот атрибут (а не комбинировался с ним), и пин при наведении прыгал
           к началу координат SVG. Теперь позиционирование (translate) живёт на внешней
           <g class="pin-outer">, которую hover не трогает; масштаб на hover применяется
           только к внутренней <g class="pin-marker"> (halo+круг+число) с transform-origin
           в её собственном центре — подписи (имя/под-подпись) вообще не масштабируются. -->
      <g
        v-for="(pin, pinIdx) in activePins"
        :key="pin.id"
        class="pin-outer"
        :class="{
          'pin-outer--match': props.searchActive && props.matchedIds.includes(pin.id),
          'pin-outer--dim':   props.searchActive && !props.matchedIds.includes(pin.id),
        }"
        :transform="`translate(${pin.x},${pin.y})`"
        @click="onPinClick(pin)"
      >
        <!-- 2026-09 (отслеживание местоположения сотрудников): нативная SVG-подсказка
             при наведении — напр. точное время последней точки. Необязательное поле,
             пины ТС его не задают, поведение для них не меняется. -->
        <title v-if="pin.hint">{{ pin.hint }}</title>
        <!-- 2026-09 (владелец: «можно приблизить карту?») — контрмасштаб
             1/zoomLevel: viewBox сжимается при зуме и увеличивает ВСЁ внутри
             него, а кружок/цифра/подпись должны остаться тем же числом
             экранных пикселей — иначе на восьмикратном приближении подпись
             размером с полкарты закрыла бы всё вокруг. SVG-АТРИБУТ transform
             (не CSS style/class) — специально: CSS transform-origin/fill-box
             для группы, чьё содержимое НЕ центрировано в (0,0) (подпись
             торчит вбок от кружка), центрировал бы масштаб не в ту точку —
             кружок "уполз" бы при зуме. Атрибут transform однозначно масштабирует
             вокруг локального (0,0), без этой не­однозначности (сравни с
             translate на .pin-outer выше — тот же самый принцип). Обёртка
             отдельная от .pin-marker (там свой CSS-transform для hover) — будь
             это один элемент, CSS-transform на hover ПОЛНОСТЬЮ перекрыл бы этот
             scale (та же ловушка, что уже была с translate, см. комментарий выше). -->
        <g class="pin-zoom-counter" :transform="`scale(${counterScale})`">
          <g class="pin-marker">
            <!-- 2026-09 (отслеживание местоположения сотрудников): shape='person' рисует
                 скруглённый квадрат вместо кружка — люди на карте физически другой формы,
                 не только другого цвета (владелец: «люди отличаются от машин визуально»).
                 Пины ТС shape не задают → circle, поведение не меняется. -->
            <template v-if="pin.shape === 'person'">
              <!-- Halo -->
              <rect :x="-(pin.radius + HALO_GAP)" :y="-(pin.radius + HALO_GAP)"
                    :width="(pin.radius + HALO_GAP) * 2" :height="(pin.radius + HALO_GAP) * 2"
                    :rx="(pin.radius + HALO_GAP) * 0.35" :fill="pin.color" opacity="0.2"/>
              <!-- Main square -->
              <rect :x="-pin.radius" :y="-pin.radius" :width="pin.radius * 2" :height="pin.radius * 2"
                    :rx="pin.radius * 0.35" :fill="pin.color" :stroke="pinStroke" stroke-width="3"/>
            </template>
            <template v-else>
              <!-- Halo -->
              <circle :r="pin.radius + HALO_GAP" :fill="pin.color" opacity="0.2"/>
              <!-- Main circle -->
              <circle :r="pin.radius" :fill="pin.color" :stroke="pinStroke" stroke-width="3"/>
            </template>
            <!-- Count inside (или pin.glyph, если задан — см. пины-люди выше) -->
            <text
              text-anchor="middle"
              dominant-baseline="central"
              :fill="pin.textColor || '#0a0d14'"
              :font-size="Math.max(10, Math.min(15, pin.radius * 0.85))"
              font-weight="700"
              font-family="JetBrains Mono, monospace"
            >{{ pin.glyph ?? pin.count }}</text>
          </g>
          <!-- Label — два взаимоисключающих способа рисовать имя города, см.
               LABEL_RENDER_MODE выше (эксперимент владельца: «название по
               кругу вокруг кружка»). -->
          <template v-if="pin.name">
            <!-- STRAIGHT — прежний вариант: текст сбоку от кружка, по
                 вертикали — по его центру (не масштабируется на hover, но
                 масштабируется контрмасштабом выше вместе с маркером — иначе
                 при зуме подпись оторвалась бы от кружка). Рисуется, когда
                 владелец выбрал этот стиль в переключателе (labelRenderMode,
                 см. русская-map__label-mode ниже) — сохранён целиком как
                 рабочий путь отката, НЕ используется как fallback для
                 отдельных пинов arc-режима (см. правку владельца №2 в
                 mapLabelLayout.ts — запасной путь для дугового режима убран,
                 длинные имена теперь уходят на внешнюю дугу, а не сюда).
                 Сторону больше не выбирает алгоритм раздвижки — она всегда
                 'right', кроме географического исключения (Владивосток и
                 т.п., см. mapLabelLayout.ts). Раздвижка при тесноте двигает
                 подпись только по Y (nameDy); при исчерпании запаса и всё ещё
                 пересекающихся подписях "проигравшая" (меньше машин) скрыта по
                 умолчанию и появляется по наведению на пин — см.
                 .pin-label-name--hidden. Эта механика сокрытия — ТОЛЬКО для
                 straight-режима; в arc-режиме ничего никогда не прячется. -->
            <text
              v-if="labelRenderMode === 'straight'"
              class="pin-label-name"
              :class="{ 'pin-label-name--hidden': labelOffsets.get(pin.id)?.hidden }"
              :text-anchor="labelOffsets.get(pin.id)?.side === 'left' ? 'end' : 'start'"
              dominant-baseline="central"
              :x="(labelOffsets.get(pin.id)?.side === 'left' ? -1 : 1) * (pin.radius + HALO_GAP + LABEL_NAME_GAP)"
              :y="labelOffsets.get(pin.id)?.nameDy ?? 0"
              :fill="labelColor"
              :font-size="LABEL_NAME_FONT_SIZE"
              font-weight="600"
              font-family="Inter, system-ui, sans-serif"
            >{{ pin.name }}</text>
            <!-- ARC — имя вдоль невидимого дугового <path> над кружком
                 (строго верхняя половина окружности — см. buildArcPath в
                 mapLabelLayout.ts: не даём тексту уйти на нижнюю половину,
                 иначе он читался бы перевёрнутым). Путь уникален на пин
                 (id по индексу v-for — pin.id может содержать пробелы/скобки,
                 в SVG-href это ломается). Радиус/кегль подобраны под длину
                 ИМЕННО этого названия (layoutArcPinLabels, mapLabelLayout.ts):
                 короткие имена рисуются ВНУТРИ ореола (band='inner'), длинные,
                 не влезающие туда даже на ARC_FONT_MIN, — ПО ВНЕШНЕМУ краю
                 ореола (band='outer', радиус может расти дальше, если и
                 внешней дуги не хватило). Никакого per-пинового отката на
                 straight — рисуется всегда, когда владелец выбрал стиль
                 'arc'. startOffsetPercent — угол начала текста вдоль дуги;
                 для внутренних всегда 50% (центр, по вершине), для внешних
                 мог быть смещён раздвижкой resolveOuterArcAngles, чтобы не
                 задеть дугу соседнего пина (см. mapLabelLayout.ts). -->
            <template v-else>
              <path
                :id="`pin-arc-path-${pinIdx}`"
                :d="buildArcPath(arcLabelOffsets.get(pin.id)?.radius ?? (pin.radius + HALO_GAP))"
                fill="none"
                stroke="none"
              />
              <text
                class="pin-label-name pin-label-name--arc"
                text-anchor="middle"
                :fill="labelColor"
                :font-size="arcLabelOffsets.get(pin.id)?.fontSize ?? ARC_FONT_MAX"
                font-weight="600"
                font-family="Inter, system-ui, sans-serif"
              ><textPath :href="`#pin-arc-path-${pinIdx}`" :startOffset="`${arcLabelOffsets.get(pin.id)?.startOffsetPercent ?? 50}%`">{{ pin.name }}</textPath></text>
            </template>
          </template>
        </g>
      </g>
    </svg>

    <!-- 2026-09 (владелец: «можно приблизить карту?») — кнопки зума и
         атрибуция OSM вынесены из SVG в обычный HTML поверх него (позиция
         absolute внутри .russia-map, у которого position:relative). Внутри
         SVG они были бы координатами КАРТЫ и уезжали/раздувались вместе с
         viewBox при зуме/панорамировании — ровно то, чего просят избежать оба
         требования владельца («атрибуция держится угла видимой области»,
         кнопки должны быть на месте на любом уровне приближения). -->
    <div class="russia-map__controls">
      <button type="button" class="russia-map__ctrl-btn" title="Приблизить" @click="zoomIn">+</button>
      <button type="button" class="russia-map__ctrl-btn" title="Отдалить" @click="zoomOut">−</button>
      <button type="button" class="russia-map__ctrl-btn russia-map__ctrl-btn--reset" title="Сбросить вид" @click="resetView">⟲</button>
    </div>

    <!-- 2026-09 (владелец: «переключатель стиля подписей в интерфейс, чтобы
         сравнить оба варианта без пересборки») — сознательно НЕ подверстан под
         существующие кнопки зума (top-right): в равнопромежуточной конической
         проекции этой карты Дальний Восток (Анадырь/Камчатка/Владивосток —
         как раз кластер с самыми длинными именами, которым нужна внешняя дуга)
         географически всегда рисуется у правого края карты, вплотную к
         top-right углу — там же, где уже жили кнопки зума. Утяжелить именно
         этот угол ещё двумя кнопками означало бы закрыть частью ровно тот
         участок карты, ради которого затевалась вся правка. Поэтому
         переключатель — отдельным блоком в top-left (запад карты — Крым/
         Калининград, там пусто) в том же визуальном стиле, что и кнопки зума. -->
    <div class="russia-map__label-mode" role="group" aria-label="Стиль подписей городов на карте">
      <button
        type="button"
        class="russia-map__mode-btn"
        :class="{ 'russia-map__mode-btn--active': labelRenderMode === 'arc' }"
        title="Названия городов — дугой вокруг кружка"
        @click="setLabelRenderMode('arc')"
      >дугой</button>
      <button
        type="button"
        class="russia-map__mode-btn"
        :class="{ 'russia-map__mode-btn--active': labelRenderMode === 'straight' }"
        title="Названия городов — прямой строкой сбоку от кружка"
        @click="setLabelRenderMode('straight')"
      >сбоку</button>
    </div>
    <div class="russia-map__attribution" :style="{ color: mutedColor }">© OpenStreetMap contributors</div>

    <!-- HTML legend below map — 2026-09: раньше дублировала одну и ту же надпись
         «филиал/СТО/регион эксп./ФПГ-источник» и внутри SVG, и здесь, при этом сами
         подписи были из СТАРОЙ логики (география по организации-владельцу), а карта
         теперь показывает место нахождения ТС. Легенда теперь одна и построена из
         реальных пинов на карте (цвет = место нахождения, как и на самой карте). -->
    <div v-if="legendItems.length" class="russia-map__legend">
      <span v-for="item in legendItems" :key="item.id" class="leg-item">
        <i class="leg-dot" :style="{ background: item.color }"></i>{{ item.name }}
      </span>
      <span v-if="hiddenLegendCount > 0" class="leg-item leg-item--more">+{{ hiddenLegendCount }} ещё</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useTheme } from 'vuetify'
import { DEFAULT_PINS, projectLatLonToSvg, type MapPin, type MapConnection } from './russiaMapPins'
import {
  layoutPinLabels, HALO_GAP, LABEL_NAME_GAP, LABEL_NAME_FONT_SIZE, MAP_WIDTH, MAP_HEIGHT,
  layoutArcPinLabels, buildArcPath, ARC_FONT_MAX,
} from './mapLabelLayout'
// 2026-09: DEFAULT_PINS раньше не был импортирован как значение (только типы) —
// activePins() ссылался на неопределённую переменную в ветке "pins не переданы",
// эта ветка сейчас не задействуется (FleetRegionsView всегда рендерит компонент
// только при mapPins.length > 0), но чинится заодно, чтобы не оставлять bomb.

// ── Геоданные регионов (geo-fix #3) ─────────────────────────────────────────
// Динамический import() → Vite кладёт russiaRegionsGeo.json в отдельный чанк,
// который качается только когда реально рендерится карта (не раздувает общий
// бандл приложения, см. отчёт задачи про размер бандла до/после).
interface RegionGeoJson {
  regions: { id: number; name: string; rings: [number, number][][] }[]
}
interface RegionPath { key: string; d: string }

const regionPaths = ref<RegionPath[]>([])

onMounted(async () => {
  try {
    const mod = (await import('./russiaRegionsGeo.json')) as { default: RegionGeoJson }
    const geo = mod.default
    regionPaths.value = geo.regions.map((region) => {
      const d = region.rings
        .map((ring) => {
          const pts = ring.map(([lon, lat]) => projectLatLonToSvg(lat, lon))
          return 'M' + pts.map((p) => `${p.x.toFixed(2)},${p.y.toFixed(2)}`).join('L') + 'Z'
        })
        .join(' ')
      return { key: `region-${region.id}`, d }
    })
  } catch (err) {
    // Геоданные — статический файл в бандле, к сети не обращается; сбой
    // возможен только при повреждении/отсутствии файла — карта тогда просто
    // рисуется без подложки регионов (пины и легенда продолжают работать).
    console.error('RussiaMapSvg: не удалось загрузить russiaRegionsGeo.json', err)
  }
})

const props = withDefaults(defineProps<{
  pins?: MapPin[]
  connections?: MapConnection[]
  // 2026-09 (поиск по машине, владелец: «как в Иерархии»): searchActive
  // включает режим подсветки (пины из matchedIds получают пульсирующее
  // свечение, остальные гаснут) — тот же приём, что hv-node-match/hv-node-dim
  // в HierarchyView.vue, чтобы пользователь узнавал знакомую механику.
  // matchedIds сравниваются с pin.id (===loc.region, см. FleetRegionsView.vue).
  searchActive?: boolean
  matchedIds?: (string | number)[]
}>(), {
  pins: () => [],
  connections: () => [],
  searchActive: false,
  matchedIds: () => [],
})

const emit = defineEmits<{
  (e: 'pin-click', pin: MapPin): void
}>()

// ── Zoom / pan (владелец: «можно сделать так, чтобы карту можно было
// приближать?») ──────────────────────────────────────────────────────────────
// Внешние библиотеки подключать нельзя (политика безопасности) — реализовано
// через SVG viewBox: приближение сжимает его размер, панорамирование сдвигает
// его позицию, координаты пинов/проекция (russiaMapPins.ts) не пересчитываются
// вообще — тот же viewBox 0 0 1171 611, просто окно просмотра внутри него
// уже/шире и сдвинуто. MIN_ZOOM=1 — «дальше некуда», вся карта уже видна
// целиком, поэтому отдалять больше некуда (лишний запас ниже 1x только унёс
// бы карту в угол пустого пространства). MAX_ZOOM=8 — по ориентиру владельца.
const MIN_ZOOM = 1
const MAX_ZOOM = 8

const svgEl = ref<SVGSVGElement | null>(null)
const viewBox = ref({ x: 0, y: 0, w: MAP_WIDTH, h: MAP_HEIGHT })

const zoomLevel = computed(() => MAP_WIDTH / viewBox.value.w)
const viewBoxStr = computed(() => `${viewBox.value.x} ${viewBox.value.y} ${viewBox.value.w} ${viewBox.value.h}`)
// Контрмасштаб на пины/подписи (см. .pin-zoom-counter в шаблоне) — держит их
// экранный размер постоянным, пока viewBox зумит саму географию.
const counterScale = computed(() => 1 / zoomLevel.value)

function clamp(v: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, v))
}

/** Зумит карту в MAP-координатах (anchorX/anchorY), удерживая эту точку
 * неподвижной на экране — стандартная формула "zoom to point": сохраняем её
 * относительную позицию (fx,fy) внутри viewBox до и после изменения размера. */
function zoomAt(factor: number, anchorX: number, anchorY: number) {
  const vb = viewBox.value
  const newW = clamp(vb.w / factor, MAP_WIDTH / MAX_ZOOM, MAP_WIDTH / MIN_ZOOM)
  const newH = newW * (MAP_HEIGHT / MAP_WIDTH)
  const fx = (anchorX - vb.x) / vb.w
  const fy = (anchorY - vb.y) / vb.h
  let newX = anchorX - fx * newW
  let newY = anchorY - fy * newH
  // Не даём панораме/зуму унести окно просмотра за пределы карты — она не
  // должна "теряться" в пустом пространстве ни при каком масштабе.
  newX = clamp(newX, 0, Math.max(0, MAP_WIDTH - newW))
  newY = clamp(newY, 0, Math.max(0, MAP_HEIGHT - newH))
  viewBox.value = { x: newX, y: newY, w: newW, h: newH }
}

function panBy(dxMap: number, dyMap: number) {
  const vb = viewBox.value
  const newX = clamp(vb.x - dxMap, 0, Math.max(0, MAP_WIDTH - vb.w))
  const newY = clamp(vb.y - dyMap, 0, Math.max(0, MAP_HEIGHT - vb.h))
  viewBox.value = { ...vb, x: newX, y: newY }
}

function resetView() {
  viewBox.value = { x: 0, y: 0, w: MAP_WIDTH, h: MAP_HEIGHT }
}

/** Экранные px → координаты карты (SVG user space), через обратную CTM —
 * учитывает и текущий viewBox, и реальный отрендеренный размер контейнера. */
function screenToMap(clientX: number, clientY: number): { x: number; y: number } | null {
  const svg = svgEl.value
  if (!svg) return null
  const ctm = svg.getScreenCTM()
  if (!ctm) return null
  const pt = svg.createSVGPoint()
  pt.x = clientX
  pt.y = clientY
  const p = pt.matrixTransform(ctm.inverse())
  return { x: p.x, y: p.y }
}

function onWheel(e: WheelEvent) {
  const p = screenToMap(e.clientX, e.clientY)
  if (!p) return
  const factor = e.deltaY < 0 ? 1.18 : 1 / 1.18
  zoomAt(factor, p.x, p.y)
}

function zoomIn() {
  const vb = viewBox.value
  zoomAt(1.5, vb.x + vb.w / 2, vb.y + vb.h / 2)
}
function zoomOut() {
  const vb = viewBox.value
  zoomAt(1 / 1.5, vb.x + vb.w / 2, vb.y + vb.h / 2)
}

// ── Drag-to-pan (мышь) + pinch-to-zoom/pan (сенсор), через Pointer Events —
// один API для мыши и тач-экрана, а не два отдельных обработчика. Один
// активный указатель = перетаскивание; два — щипок (zoom) + панорамирование
// по среднему между ними. touch-action:none на самом svg (см. <style>)
// обязателен: без него браузер сам перехватил бы палец под нативный скролл/
// зум страницы вместо наших обработчиков (см. навык pwa — «щипок по карте не
// должен масштабировать всю страницу вместо карты»).
const activePointers = new Map<number, { x: number; y: number }>()
// Порог в экранных px, после которого жест считается перетаскиванием, а не
// тапом/кликом — иначе клик по пину для открытия попапа срабатывал бы
// случайно после того, как палец/мышь чуть дрогнули при простом тапе.
const DRAG_CLICK_THRESHOLD = 6
let dragMoved = 0
let renderedWidthPx = 1

function currentRenderedWidth(): number {
  return svgEl.value?.getBoundingClientRect().width || renderedWidthPx || 1
}

// 2026-09 (найдено при живой проверке в браузере): setPointerCapture нельзя
// вызывать в onPointerDown безусловно — Chromium ретаргетирует последующий
// нативный click НА ЭЛЕМЕНТ-ЗАХВАТЧИК (svg), а не на исходную цель под
// курсором, поэтому @click на конкретном пине (вложенном <g>) переставал
// срабатывать вообще, даже без единого пикселя перетаскивания (клик по
// кружку молча переставал открывать попап места). Захват откладывается до
// ПЕРВОГО реального pointermove — то есть до подтверждённого перетаскивания;
// обычный тап/клик (down→up без движения) капчура вообще не касается, и
// нативный click доходит до пина как обычно.
const capturedPointers = new Set<number>()

function onPointerDown(e: PointerEvent) {
  // dragMoved считается на весь жест целиком (от первого пальца до отпускания
  // последнего) — второй палец, коснувшийся экрана посреди перетаскивания
  // первым, не должен обнулять уже накопленное смещение.
  if (activePointers.size === 0) dragMoved = 0
  activePointers.set(e.pointerId, { x: e.clientX, y: e.clientY })
  renderedWidthPx = currentRenderedWidth()
}

let lastPinchDist: number | null = null
let lastPinchMid: { x: number; y: number } | null = null

function onPointerMove(e: PointerEvent) {
  const prev = activePointers.get(e.pointerId)
  if (!prev) return // указатель не наш (не было pointerdown на этом элементе)
  activePointers.set(e.pointerId, { x: e.clientX, y: e.clientY })

  // Реальное движение подтвердилось — теперь можно (и нужно) захватить
  // указатель, чтобы перетаскивание продолжало работать, даже если палец/
  // курсор уйдёт за пределы svg во время жеста.
  if (!capturedPointers.has(e.pointerId)) {
    try { svgEl.value?.setPointerCapture(e.pointerId) } catch { /* элемент мог уже исчезнуть */ }
    capturedPointers.add(e.pointerId)
  }

  if (activePointers.size === 1) {
    // Перетаскивание одним пальцем/мышью.
    const dxScreen = e.clientX - prev.x
    const dyScreen = e.clientY - prev.y
    dragMoved += Math.abs(dxScreen) + Math.abs(dyScreen)
    const pxToMap = viewBox.value.w / currentRenderedWidth()
    panBy(dxScreen * pxToMap, dyScreen * pxToMap)
    return
  }

  if (activePointers.size === 2) {
    // Щипок — зум + панорамирование по смещению середины между пальцами.
    const [a, b] = Array.from(activePointers.values())
    const newDist = Math.hypot(a.x - b.x, a.y - b.y)
    const newMidScreen = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }
    dragMoved += 1 // щипок всегда считается жестом, не тапом

    if (lastPinchDist != null && lastPinchMid != null) {
      const anchorMap = screenToMap(lastPinchMid.x, lastPinchMid.y)
      if (anchorMap) {
        const factor = newDist / lastPinchDist
        zoomAt(factor, anchorMap.x, anchorMap.y)
      }
      // Панорамирование вслед за смещением середины щипка между кадрами.
      const dxScreen = newMidScreen.x - lastPinchMid.x
      const dyScreen = newMidScreen.y - lastPinchMid.y
      const pxToMap = viewBox.value.w / currentRenderedWidth()
      panBy(dxScreen * pxToMap, dyScreen * pxToMap)
    }
    lastPinchDist = newDist
    lastPinchMid = newMidScreen
  }
}

function onPointerUp(e: PointerEvent) {
  activePointers.delete(e.pointerId)
  if (activePointers.size < 2) {
    lastPinchDist = null
    lastPinchMid = null
  }
  if (activePointers.size === 1) {
    // Остался один палец после щипка — перезаписываем его точку отсчёта,
    // чтобы не было прыжка при продолжении перетаскивания одним пальцем.
    const remaining = activePointers.entries().next().value as [number, { x: number; y: number }] | undefined
    if (remaining) activePointers.set(remaining[0], remaining[1])
  }
  if (capturedPointers.has(e.pointerId)) {
    try { svgEl.value?.releasePointerCapture(e.pointerId) } catch { /* уже отпущен браузером */ }
    capturedPointers.delete(e.pointerId)
  }
}

function onPinClick(pin: MapPin) {
  // Клик после реального перетаскивания/щипка не должен открывать попап —
  // иначе лёгкая дрожь пальца/мыши при панорамировании карты постоянно
  // открывала бы случайный попап места.
  if (dragMoved > DRAG_CLICK_THRESHOLD) return
  emit('pin-click', pin)
}

const theme = useTheme()
const isDark = computed(() => theme.global.current.value.dark)

const contourFill   = computed(() => isDark.value ? 'rgba(106,166,255,0.04)' : 'rgba(106,166,255,0.08)')
const contourStroke = computed(() => isDark.value ? 'rgba(106,166,255,0.18)' : 'rgba(106,166,255,0.35)')
const pinStroke     = computed(() => isDark.value ? '#0a0d14' : '#ffffff')
const labelColor    = computed(() => isDark.value ? '#e9edf5' : '#1a1d23')
const mutedColor    = computed(() => isDark.value ? '#8a93a8' : '#6b7280')

// Use provided pins or fall back to etalon defaults
const activePins = computed(() => props.pins.length ? props.pins : DEFAULT_PINS)

// 2026-09 (правка после ревью): подписи «Курск» / «ДНР г. Донецк» / «1 ТС» и
// т.п. раньше рисовались только по формуле (radius+gap), без учёта того, что
// у соседних, геаграфически близких пинов подписи могут пересечься друг с
// другом или с чужим кружком-маркером — см. mapLabelLayout.ts.
// 2026-09 (владелец: «можно приблизить карту?»): передаём zoomLevel — при
// приближении разъехавшиеся на экране города должны переставать считаться
// тесными (см. комментарий в mapLabelLayout.ts про контрмасштаб).
const labelOffsets = computed(() => layoutPinLabels(activePins.value, zoomLevel.value))

// 2026-09-эксперимент (владелец: «название по кругу вокруг кружка города,
// кегль можно уменьшать, чтобы в два круга не шло») — способ отрисовки
// подписи названия. ДВА ВЗАИМОИСКЛЮЧАЮЩИХ ВАРИАНТА:
//   'straight' — прежний вариант, текст прямой строкой справа/слева от
//                кружка (LABEL_NAME_*/layoutPinLabels выше). Полностью
//                рабочий путь отката — код не удалён.
//   'arc'      — имя вдоль дуги над кружком, радиус/кегль подобраны под
//                длину конкретного имени (layoutArcPinLabels, mapLabelLayout.ts) —
//                короткие имена внутри ореола, длинные — по его внешнему краю.
//                Per-пинового отката на straight внутри arc-режима больше нет
//                (правка владельца №2 — единый стиль на всей карте).
// Оба computed'а ниже вычисляются всегда (дёшево — чистая геометрия без
// сети), реальный рендер в шаблоне выбирает нужный по labelRenderMode.
//
// 2026-09 (владелец: «переключатель — в интерфейс, чтобы сравнить оба
// варианта без пересборки») — раньше это было жёстко зашитой константой
// (правка требовала редактировать код и ждать docker rebuild, т.е. владелец
// не мог сам сравнить варианты вживую). Источник истины теперь — выбор
// пользователя (localStorage), константа ниже — только значение ПО
// УМОЛЧАНИЮ при первом визите/если localStorage недоступен (приватный режим,
// квота и т.п. — try/catch, чтобы такой сбой не ронял всю карту).
const DEFAULT_LABEL_RENDER_MODE: 'straight' | 'arc' = 'arc'
const LABEL_MODE_STORAGE_KEY = 'gala_fleet_map_label_mode'

function loadStoredLabelMode(): 'straight' | 'arc' {
  try {
    const saved = localStorage.getItem(LABEL_MODE_STORAGE_KEY)
    return saved === 'straight' || saved === 'arc' ? saved : DEFAULT_LABEL_RENDER_MODE
  } catch {
    return DEFAULT_LABEL_RENDER_MODE
  }
}

const labelRenderMode = ref<'straight' | 'arc'>(loadStoredLabelMode())

function setLabelRenderMode(mode: 'straight' | 'arc') {
  labelRenderMode.value = mode
  try {
    localStorage.setItem(LABEL_MODE_STORAGE_KEY, mode)
  } catch {
    // Приватный режим/квота исчерпана — переключение всё равно сработало на
    // эту сессию (реактивный ref), просто не переживёт перезагрузку страницы.
  }
}

const arcLabelOffsets = computed(() => layoutArcPinLabels(activePins.value, zoomLevel.value))

// 2026-09 (geo-fix #4): пины, которых декluttering (FleetRegionsView.vue)
// действительно сдвинул от истинных координат — только для них рисуется
// выноска (см. блок <line>/<circle> выше). Порог 3px отсекает субпиксельный
// шум (несдвинутые пины не должны обрастать лишней декоративной точкой).
const LEADER_THRESHOLD = 3
const pinsWithLeader = computed(() =>
  activePins.value.filter(
    (p) => p.anchorX != null && p.anchorY != null &&
      Math.hypot(p.anchorX - p.x, p.anchorY - p.y) > LEADER_THRESHOLD
  )
)

// Легенда строится из реальных пинов (место нахождения → цвет), а не из
// зашитого списка старых категорий («филиал/СТО/регион/ФПГ»). Ограничена,
// чтобы не разъезжалась на много строк при большом числе мест.
const LEGEND_LIMIT = 8
const legendItems = computed(() =>
  activePins.value.slice(0, LEGEND_LIMIT).map(p => ({ id: p.id, name: p.name || String(p.id), color: p.color }))
)
const hiddenLegendCount = computed(() => Math.max(0, activePins.value.length - LEGEND_LIMIT))
</script>

<style scoped>
.russia-map {
  position: relative;
  width: 100%;
  background: transparent;
  border-radius: 14px;
}

.russia-map svg {
  width: 100%;
  height: auto;
  display: block;
  border-radius: 12px;
  background:
    radial-gradient(circle at 60% 50%, rgba(106,166,255,.04), transparent 70%),
    linear-gradient(180deg, rgba(255,255,255,.02), rgba(255,255,255,0));
  border: 1px solid rgba(106,166,255,.1);
  /* 2026-09 (владелец: «можно приблизить карту?») — без этого браузер сам
     разбирает касания как нативный скролл/пинч-зум страницы поверх svg, и
     наши обработчики (onWheel/onPointerMove) либо не получают события, либо
     получают их вперемешку со page-скроллом (см. навык pwa: «щипок по карте
     не должен масштабировать всю страницу вместо карты»). none — полностью
     наш обработчик; скролл СТРАНИЦЫ вне области карты этим не затрагивается,
     ломается только скролл ПАЛЬЦЕМ ПО КАРТЕ (ожидаемо — там теперь перетаскивание).
     user-select:none — иначе перетаскивание мышью попутно выделяло бы текст подписей. */
  touch-action: none;
  user-select: none;
  -webkit-user-select: none;
  cursor: grab;
}
.russia-map svg:active { cursor: grabbing; }

.russia-map--light svg {
  background:
    radial-gradient(circle at 60% 50%, rgba(106,166,255,.06), transparent 70%),
    #f5f7fa;
  border-color: #e2e6f0;
}

/* ── Zoom controls + attribution (владелец: «можно приблизить карту?») ────
   Обычный HTML поверх SVG (position:absolute в .russia-map с position:relative) —
   не координаты карты, поэтому не двигаются и не раздуваются при зуме/панораме. */
.russia-map__controls {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 5;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.russia-map__ctrl-btn {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  border: 1px solid rgba(106,166,255,.25);
  background: rgba(20,24,35,.85);
  color: #e9edf5;
  font-size: 16px;
  font-weight: 700;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  backdrop-filter: blur(4px);
  transition: background 0.12s, border-color 0.12s;
}
.russia-map__ctrl-btn:hover { background: rgba(106,166,255,.25); border-color: #6aa6ff; }
.russia-map__ctrl-btn--reset { font-size: 14px; }
.russia-map--light .russia-map__ctrl-btn {
  background: rgba(255,255,255,.9);
  border-color: #d7deee;
  color: #1a1d23;
}
.russia-map--light .russia-map__ctrl-btn:hover { background: #eaf1ff; border-color: #6aa6ff; }

/* ── Переключатель стиля подписей («дугой»/«сбоку») — владелец: «в
   интерфейс, чтобы сравнить без пересборки». Визуально в одном стиле с
   .russia-map__ctrl-btn (те же цвета/радиус/бордер), но текстовые и не
   квадратные — короткое слово не влезло бы в 30×30px. НАРОЧНО top-left, а не
   рядом с кнопками зума (top-right) — см. комментарий в шаблоне: top-right
   и так уже приходится на Дальний Восток карты (самые длинные имена, ради
   которых и делалась внешняя дуга), лишние кнопки там закрывали бы именно
   этот участок. */
.russia-map__label-mode {
  position: absolute;
  top: 12px;
  left: 12px;
  z-index: 5;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.russia-map__mode-btn {
  min-width: 30px;
  padding: 3px 6px;
  border-radius: 7px;
  border: 1px solid rgba(106,166,255,.25);
  background: rgba(20,24,35,.85);
  color: #b9c1d4;
  font-size: 10px;
  font-family: 'Inter', system-ui, sans-serif;
  font-weight: 600;
  line-height: 1.2;
  cursor: pointer;
  white-space: nowrap;
  backdrop-filter: blur(4px);
  transition: background 0.12s, border-color 0.12s, color 0.12s;
}
.russia-map__mode-btn:hover { background: rgba(106,166,255,.25); border-color: #6aa6ff; color: #e9edf5; }
.russia-map__mode-btn--active {
  background: rgba(106,166,255,.35);
  border-color: #6aa6ff;
  color: #e9edf5;
}
.russia-map--light .russia-map__mode-btn {
  background: rgba(255,255,255,.9);
  border-color: #d7deee;
  color: #5a6274;
}
.russia-map--light .russia-map__mode-btn:hover { background: #eaf1ff; border-color: #6aa6ff; color: #1a1d23; }
.russia-map--light .russia-map__mode-btn--active {
  background: #dbe9ff;
  border-color: #6aa6ff;
  color: #1a1d23;
}

.russia-map__attribution {
  position: absolute;
  bottom: 6px;
  right: 10px;
  z-index: 5;
  font-size: 10px;
  font-family: 'Inter', system-ui, sans-serif;
  opacity: 0.7;
  pointer-events: none;
}

.pin-outer {
  cursor: pointer;
}

/* Масштаб на hover — только у маркера (halo+круг+число), точка отсчёта — его
   собственный центр (fill-box вокруг circle r=pin.radius+6, центрированного в 0,0).
   Позиционирование пина живёт на .pin-outer (SVG-атрибут transform=translate),
   которого этот CSS transform не касается — поэтому пин не «прыгает» при наведении,
   и соседние пины/подписи никак не задеваются. */
.pin-marker {
  transform-box: fill-box;
  transform-origin: center;
  transition: transform 0.15s ease;
}

.pin-outer:hover .pin-marker {
  transform: scale(1.12);
}

/* 2026-09 (правка владельца): подпись, проигравшая раздвижку соседней (у её
   пина меньше машин) — не наложена молча и не обрезана, а скрыта по
   умолчанию и появляется при наведении на пин (см. mapLabelLayout.ts,
   поле hidden). display:none, а не opacity — чтобы скрытая подпись не
   учитывалась в getBoundingClientRect как ложное пересечение. */
.pin-label-name--hidden {
  display: none;
}

.pin-outer:hover .pin-label-name--hidden {
  display: block;
}

/* 2026-09 (поиск по машине, «как в Иерархии»): та же механика подсветки, что
   .hv-node-match/.hv-node-dim в HierarchyView.vue — совпавшие пины пульсируют
   оранжевым свечением (брендовый #fb923c), остальные гаснут. drop-shadow (не
   box-shadow/outline — это SVG, не DOM-прямоугольник) обводит контур
   halo+круга+текста целиком. */
.pin-outer--dim {
  opacity: 0.22;
  filter: grayscale(0.6);
  transition: opacity 0.3s, filter 0.3s;
}
.pin-outer--match .pin-marker {
  animation: pin-match-glow 1.3s ease-in-out infinite;
}
@keyframes pin-match-glow {
  0%, 100% {
    filter: drop-shadow(0 0 3px rgba(251,146,60,.65)) drop-shadow(0 0 8px rgba(251,146,60,.35));
  }
  50% {
    filter: drop-shadow(0 0 7px rgba(251,146,60,.95)) drop-shadow(0 0 16px rgba(251,146,60,.6));
  }
}

.russia-map__legend {
  display: flex;
  gap: 16px;
  padding: 10px 16px;
  flex-wrap: wrap;
  font-size: 12px;
}

.leg-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: currentColor;
  opacity: 0.75;
}

.leg-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
  flex-shrink: 0;
}

.leg-item--more {
  opacity: 0.55;
  font-style: italic;
}
</style>
