<template>
  <div class="regions-view" :class="{ 'regions-view--light': !isDark }">

    <!-- ── Topbar ── -->
    <div class="rv-topbar">
      <div>
        <div class="rv-crumbs">
          <router-link to="/fleet">Автопарк</router-link>
          <span class="rv-crumbs__sep">/</span>
          <b>Регионы и места нахождения</b>
        </div>
        <h1 class="rv-h1">География парка</h1>
        <p class="rv-lead">
          Распределение
          <b>{{ totalVehicles }}</b> единиц техники по
          <b>{{ sortedLocations.length }}</b> местам нахождения ·
          клик по месту нахождения — список машин
        </p>
      </div>

      <!-- 2026-09 (владелец: «нужен поиск по автомобилю... как в Иерархии»):
           поиск по гос.№/марке/модели/VIN — сервер уже умеет это в GET /vehicles?q=
           (см. VehicleListView.vue), здесь просто переиспользуем эндпоинт. Найденные
           машины подсвечивают на карте кружок своего места нахождения (тот же приём,
           что hv-node-match/hv-node-dim в HierarchyView.vue) — см. vehicleSearch* ниже. -->
      <div class="rv-vsearch">
        <div class="rv-vsearch__box">
          <span class="rv-vsearch__ic">⌕</span>
          <input
            v-model="vehicleSearchQuery"
            type="text"
            class="rv-vsearch__input"
            placeholder="Поиск ТС: гос.№, марка, модель, VIN…"
          />
          <button
            v-if="vehicleSearchQuery"
            class="rv-vsearch__clear"
            title="Очистить"
            @click="vehicleSearchQuery = ''"
          >✕</button>
          <span
            v-if="vehicleSearchActive"
            class="rv-vsearch__count"
            :class="vehicleSearchMatchCount ? 'rv-vsearch__count--ok' : 'rv-vsearch__count--zero'"
          >{{ vehicleSearchLoading ? '…' : (vehicleSearchMatchCount || 0) }}</span>
        </div>

        <!-- Результаты — краткий текстовый список, клик открывает попап места -->
        <div v-if="vehicleSearchActive" class="rv-vsearch__results">
          <div v-if="vehicleSearchLoading" class="rv-vsearch__hint">Ищем…</div>
          <template v-else-if="vehicleSearchResults.length">
            <div
              v-for="v in vehicleSearchResults"
              :key="v.id"
              class="rv-vsearch__row"
              @click="openLocationDrill(vehicleLocationRegion(v))"
            >
              <LicensePlate :modelValue="v.plate" size="sm" />
              <span class="rv-vsearch__row-nm">{{ [v.brand, v.model].filter(Boolean).join(' ') || '—' }}</span>
              <span class="rv-vsearch__row-sep">·</span>
              <span class="rv-vsearch__row-loc">{{ vehicleLocationRegion(v) }}</span>
            </div>
            <div v-if="vehicleSearchHasMore" class="rv-vsearch__hint">
              показаны первые {{ vehicleSearchResults.length }} из {{ vehicleSearchTotal }} — уточните запрос
            </div>
          </template>
          <div v-else class="rv-vsearch__hint rv-vsearch__hint--empty">
            Ничего не найдено по «{{ vehicleSearchQuery.trim() }}»
          </div>
        </div>
      </div>
    </div>

    <!-- ── Data notice ── -->
    <div v-if="unspecifiedCount > 0" class="rv-notice">
      У <b>{{ unspecifiedCount }}</b> ед. техники не заполнено «Место нахождения» —
      они показаны отдельной группой «Место не указано» и не попадают на карту.
    </div>

    <!-- ── KPI strip ── -->
    <div class="rv-kpi-row">
      <KpiCard label="Всего ТС" :value="totalVehicles" variant="default" />
      <KpiCard label="Мест нахождения" :value="sortedLocations.length" variant="info" />
      <KpiCard label="В работе" :value="totalWorking" variant="ok" />
      <KpiCard label="В ремонте" :value="totalRepair" variant="warn" />
      <KpiCard label="Сломано" :value="totalBroken" variant="alert" />
    </div>

    <!-- ── Map + Top list ── -->
    <section class="rv-map-row">
      <!-- Map -->
      <div class="rv-panel rv-map-box">
        <div class="rv-panel__head">
          <span>Карта по месту нахождения</span>
          <small>размер кружка ∝ количеству ТС</small>
        </div>
        <div v-if="loadingRegions" class="rv-loading">
          <div class="rv-spinner"></div>
        </div>
        <RussiaMapSvg
          v-else-if="mapPins.length"
          :pins="mapPins"
          :search-active="vehicleSearchActive"
          :matched-ids="vehicleSearchMatchedRegionsArray"
          @pin-click="onPinClick"
        />
        <div v-else class="rv-empty">
          Нет координат для отображения — известные города/регионы не заполнены
          в «Месте нахождения» ни у одной машины
        </div>
      </div>

      <!-- Top-8 locations list -->
      <div class="rv-panel rv-top-list">
        <div class="rv-panel__head">
          <span>Топ мест нахождения</span>
          <small>по количеству ТС</small>
        </div>
        <div v-if="loadingRegions" class="rv-loading">
          <div class="rv-spinner"></div>
        </div>
        <template v-else>
          <div
            v-for="(loc, idx) in topLocations"
            :key="loc.region"
            class="rv-reg-row"
            @click="openLocationDrill(loc.region)"
          >
            <div class="rv-reg-row__ic" :style="{ background: locationBadgeBg(idx), color: locationBadgeColor(idx) }">
              {{ locationAbbr(loc.region) }}
            </div>
            <div class="rv-reg-row__info">
              <div class="rv-reg-row__nm" :title="loc.region">{{ loc.region }}</div>
              <div v-if="locationSubtitle(loc.region)" class="rv-reg-row__ds">{{ locationSubtitle(loc.region) }}</div>
            </div>
            <div class="rv-reg-row__cnt">
              {{ loc.count }}
              <small>ТС</small>
            </div>
          </div>
          <div v-if="!topLocations.length" class="rv-empty">Нет данных</div>
        </template>
      </div>
    </section>

    <!-- ── Location cards grid ── -->
    <h2 class="rv-section-title">
      Карточки по месту нахождения
      <span class="rv-section-title__sub">— распределение техники по месту нахождения, состояние парка</span>
    </h2>
    <section class="rv-cards-grid">
      <div v-if="loadingRegions" class="rv-loading" style="grid-column:1/-1">
        <div class="rv-spinner"></div>
      </div>
      <article
        v-else
        v-for="(loc, idx) in sortedLocations"
        :key="loc.region"
        class="rv-card"
        :class="[
          cardColorClassForLocation(idx),
          {
            'rv-card--match': vehicleSearchActive && vehicleSearchMatchedRegions.has(loc.region),
            'rv-card--dim':   vehicleSearchActive && !vehicleSearchMatchedRegions.has(loc.region),
          },
        ]"
      >
        <div class="rv-card__head">
          <div class="rv-card__flag" :class="cardColorClassForLocation(idx)">
            {{ locationAbbr(loc.region) }}
          </div>
          <div class="rv-card__title">
            <div class="rv-card__nm" :title="loc.region">{{ loc.region }}</div>
            <div v-if="locationSubtitle(loc.region)" class="rv-card__ds" :title="locationSubtitle(loc.region)">{{ locationSubtitle(loc.region) }}</div>
          </div>
          <div class="rv-card__big">
            {{ loc.count }}
            <small>единиц</small>
          </div>
        </div>

        <!-- Status chips. 2026-09 (владелец, дефект «сумма не сходится»): машины
             без заполненного Vehicle.state (у большинства мест — почти все,
             кроме донецких/курских) не попадали ни в один из трёх чипов и
             молча выпадали из подсчёта — 4-й чип делает их видимой категорией,
             а не «потерянными» машинами. Backend отдаёт их как by_state.unknown
             (см. vehicles_dashboard.py). -->
        <div class="rv-card__chips">
          <span class="rv-chip rv-chip--ok">
            {{ loc.by_state.working || 0 }} в работе
          </span>
          <span class="rv-chip rv-chip--warn">
            {{ (loc.by_state.in_repair || 0) + (loc.by_state.needs_repair || 0) }} в ремонте
          </span>
          <span class="rv-chip rv-chip--alert">
            {{ loc.by_state.broken || 0 }} сломано
          </span>
          <span class="rv-chip rv-chip--muted">
            {{ loc.by_state.unknown || 0 }} без состояния
          </span>
        </div>

        <!-- Details button -->
        <div class="rv-card__footer">
          <button class="rv-btn rv-btn--sm" style="margin-left:auto" @click.stop="openLocationDrill(loc.region)">
            Показать машины →
          </button>
        </div>
      </article>
    </section>

    <!-- ── Transfer log ── -->
    <section class="rv-panel rv-transfers" style="margin-top:22px">
      <div class="rv-panel__head">
        <span>Журнал передач между организациями</span>
        <small>последние перемещения</small>
      </div>
      <div v-if="loadingTransfers" class="rv-loading">
        <div class="rv-spinner"></div>
      </div>
      <div v-else-if="!transfers.length" class="rv-empty">
        Журнал передач пуст
      </div>
      <div v-else class="rv-tx-list">
        <div
          v-for="tx in transfers"
          :key="tx.id"
          class="rv-tx"
          @click="goToVehicle(tx.vehicle_id)"
        >
          <!-- 2026-09 (правка после ревью #2): у tx НЕТ полей from_type/to_type —
               backend (/vehicles-dashboard/transfer-history-recent) их не отдаёт,
               поэтому здесь всегда рендерился один и тот же фейковый фолбэк
               «филиал» под КАЖДОЙ записью независимо от реальных данных. Раз
               реальных данных нет — строку просто не показываем, а не подставляем
               выдуманную. -->
          <LicensePlate :modelValue="tx.plate" size="sm" />
          <div class="rv-tx__from">
            <div class="rv-tx__nm">{{ tx.from_org_name || tx.from_assigned_text || '—' }}</div>
          </div>
          <div class="rv-tx__arr">→</div>
          <div class="rv-tx__to">
            <div class="rv-tx__nm">{{ tx.to_org_name || tx.to_assigned_text || '—' }}</div>
          </div>
          <div class="rv-tx__detail">
            <span>{{ tx.brand_model || '' }}</span>
            <span v-if="tx.basis" class="rv-tx__basis"> · {{ tx.basis }}</span>
          </div>
          <div class="rv-tx__when">{{ formatDate(tx.changed_at) }}</div>
        </div>
      </div>
    </section>

    <!-- ── Location drill popup ── -->
    <!-- 2026-09: раньше попап показывал организацию (по названию), к которой якобы
         привязан пин; теперь пин/карточка = место нахождения, попап показывает
         реальный список машин в этом месте (GET /vehicles-dashboard/drill?dimension=region). -->
    <teleport to="body">
      <transition name="rv-popup-fade">
        <div v-if="selectedLocation" class="rv-popup-overlay" @click.self="closeLocationDrill">
          <div class="rv-popup" :class="{ 'rv-popup--light': !isDark }">
            <div class="rv-popup__head">
              <div class="rv-popup__abbr" :style="{ background: '#6aa6ff' }">{{ locationAbbr(selectedLocation) }}</div>
              <div>
                <div class="rv-popup__nm">{{ selectedLocation }}</div>
                <div v-if="selectedLocation && locationSubtitle(selectedLocation)" class="rv-popup__sub">{{ locationSubtitle(selectedLocation) }}</div>
              </div>
              <button class="rv-popup__close" @click="closeLocationDrill">✕</button>
            </div>
            <div class="rv-popup__body">
              <div class="rv-popup__stat">
                <span class="rv-popup__stat-l">ТС всего</span>
                <span class="rv-popup__stat-v">{{ selectedLocationItem?.count ?? 0 }}</span>
              </div>
              <div v-if="drillLoading" class="rv-loading" style="min-height:60px">
                <div class="rv-spinner"></div>
              </div>
              <template v-else>
                <!-- 2026-09 (владелец: «в попапе нужен поиск, иначе трудно найти
                     машину») — фильтр по гос.№/марке/модели прямо по загруженному
                     списку (он уже маленький — конкретное место нахождения). -->
                <div v-if="drillVehicles.length" class="rv-popup__filter">
                  <span class="rv-popup__filter-ic">⌕</span>
                  <input
                    v-model="drillFilterQuery"
                    type="text"
                    class="rv-popup__filter-input"
                    placeholder="Фильтр: гос.№, марка, модель…"
                  />
                  <button
                    v-if="drillFilterQuery"
                    class="rv-popup__filter-clear"
                    title="Очистить"
                    @click="drillFilterQuery = ''"
                  >✕</button>
                </div>
                <div v-if="drillVehicles.length" class="rv-popup__filter-count">
                  {{ filteredDrillVehicles.length }} из {{ drillVehicles.length }}
                </div>
                <div class="rv-popup__vehicles">
                  <div
                    v-for="v in filteredDrillVehicles"
                    :key="v.vehicle_id"
                    class="rv-popup__veh"
                    @click="goToVehicle(v.vehicle_id)"
                  >
                    <!-- 2026-09: иконка по «Кузову» — единое правило (см. VehicleCard.vue) -->
                    <VehicleTypeIcon :body-type="v.body_type" :size="22" class="rv-popup__veh-ic" />
                    <LicensePlate :modelValue="v.plate" size="sm" />
                    <span class="rv-popup__veh-nm">{{ v.brand_model || '—' }}</span>
                  </div>
                  <div v-if="!drillVehicles.length" class="rv-empty">Нет машин</div>
                  <div v-else-if="!filteredDrillVehicles.length" class="rv-empty">
                    Нет машин по запросу «{{ drillFilterQuery.trim() }}»
                  </div>
                </div>
              </template>
            </div>
          </div>
        </div>
      </transition>
    </teleport>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useTheme } from 'vuetify'
import { apiFetch } from '@/api'

import RussiaMapSvg from '@/components/fleet/RussiaMapSvg.vue'
import { type MapPin, projectLatLonToSvg } from '@/components/fleet/russiaMapPins'
import { HALO_GAP } from '@/components/fleet/mapLabelLayout'
import { loadCitiesCatalog, citiesCatalogReady, findCityInCatalog } from '@/components/fleet/russiaCitiesCatalog'
import KpiCard from '@/components/fleet/KpiCard.vue'
import LicensePlate from '@/components/vehicles/LicensePlate.vue'
import VehicleTypeIcon from '@/components/vehicles/VehicleTypeIcon.vue'

// ─── Theme ───────────────────────────────────────────────────────────────────

const theme  = useTheme()
const isDark = computed(() => theme.global.current.value.dark)
const router = useRouter()

// ─── Types ───────────────────────────────────────────────────────────────────

// RegionItem = «место нахождения» (Vehicle.location_city), а не организация.
// region: сам город/место ("ДНР г. Донецк") либо "Место не указано".
interface RegionItem {
  region: string
  count: number
  shtab_label: string
  by_state: Record<string, number>
}

interface TransferRow {
  id: number
  vehicle_id: number
  plate: string
  brand_model: string | null
  from_owner_org_id: number | null
  to_owner_org_id: number | null
  from_org_name: string | null
  to_org_name: string | null
  from_assigned_text: string | null
  to_assigned_text: string | null
  basis: string | null
  doc_number: string | null
  changed_at: string
  changed_by_user_id: number | null
}

// ─── State ───────────────────────────────────────────────────────────────────

const regionData        = ref<RegionItem[]>([])
const transfers         = ref<TransferRow[]>([])
const loadingRegions       = ref(false)
const loadingTransfers  = ref(false)

// Location drill (клик по пину / карточке / строке списка)
const selectedLocation  = ref<string | null>(null)
const drillLoading      = ref(false)
const drillVehicles     = ref<any[]>([])
// Фильтр ВНУТРИ попапа (владелец: «в попапе трудно найти нужный автомобиль») —
// работает по уже загруженному drillVehicles, без похода на сервер.
const drillFilterQuery  = ref('')

// ─── Vehicle search (владелец: «поиск по автомобилю, как в Иерархии») ────────
// Сервер уже умеет искать по гос.№/марке/модели/VIN одним параметром — см.
// GET /vehicles?q= (переиспользуется тот же параметр, что и реестр ТС,
// VehicleListView.vue). Ограничение лимитом — страница рассчитана на рост
// парка далеко за нынешние 53 машины, тянуть весь список на клиент нельзя.
interface VehicleSearchItem {
  id: number
  plate: string
  brand: string | null
  model: string | null
  location_city: string | null
}
const VEHICLE_SEARCH_LIMIT = 50
const vehicleSearchQuery    = ref('')
const vehicleSearchResults  = ref<VehicleSearchItem[]>([])
const vehicleSearchTotal    = ref(0)
const vehicleSearchLoading  = ref(false)
let vehicleSearchDebounce: ReturnType<typeof setTimeout> | null = null

// ─── Computed helpers ────────────────────────────────────────────────────────

const sortedLocations = computed(() =>
  [...regionData.value].sort((a, b) => b.count - a.count)
)

const topLocations = computed(() => sortedLocations.value.slice(0, 8))

// 2026-09: доля машин без заполненного «Место нахождения» — показывается
// пользователю явно, а не прячется тихим фолбэком.
const unspecifiedCount = computed(() =>
  regionData.value.find(r => r.region === 'Место не указано')?.count ?? 0
)

const totalVehicles = computed(() => regionData.value.reduce((s, r) => s + r.count, 0))
const totalWorking  = computed(() => regionData.value.reduce((s, r) => s + (r.by_state?.working || 0), 0))
const totalRepair   = computed(() => regionData.value.reduce((s, r) => s + (r.by_state?.in_repair || 0) + (r.by_state?.needs_repair || 0), 0))
const totalBroken   = computed(() => regionData.value.reduce((s, r) => s + (r.by_state?.broken || 0), 0))

// ─── Vehicle search — computed ────────────────────────────────────────────────

const vehicleSearchActive = computed(() => vehicleSearchQuery.value.trim().length > 0)

// «Место нахождения» пусто/NULL → группа "Место не указано" — та же логика,
// что normalize_city()+фолбэк на бэкенде (backend/app/services/geo_normalize.py,
// используется в GET /vehicles-dashboard/by-region). Ключ обязан совпасть с
// loc.region 1-в-1, иначе подсветка не найдёт свою карточку/пин.
function vehicleLocationRegion(v: VehicleSearchItem): string {
  return (v.location_city || '').trim() || 'Место не указано'
}

const vehicleSearchMatchedRegions = computed(() => {
  const set = new Set<string>()
  for (const v of vehicleSearchResults.value) set.add(vehicleLocationRegion(v))
  return set
})
const vehicleSearchMatchedRegionsArray = computed(() => Array.from(vehicleSearchMatchedRegions.value))
const vehicleSearchMatchCount = computed(() => vehicleSearchResults.value.length)
const vehicleSearchHasMore = computed(() => vehicleSearchTotal.value > vehicleSearchResults.value.length)

// ─── Popup filter (фильтр внутри всплывающего списка машин места) ────────────

const filteredDrillVehicles = computed(() => {
  const q = drillFilterQuery.value.trim().toLowerCase()
  if (!q) return drillVehicles.value
  return drillVehicles.value.filter((v: any) =>
    String(v.plate || '').toLowerCase().includes(q) ||
    String(v.brand_model || '').toLowerCase().includes(q) ||
    String(v.brand || '').toLowerCase().includes(q) ||
    String(v.model || '').toLowerCase().includes(q)
  )
})

// ─── Map pins ────────────────────────────────────────────────────────────────
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

const mapPins = computed<MapPin[]>(() => {
  // Зависимость от готовности каталога — computed пересчитается сам, когда
  // fetch/import() догрузит справочник (см. onMounted ниже); до этого пины
  // просто отсутствуют (каталог обычно грузится за десятки мс).
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
      id:      loc.region,
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
      // там он различает одноимённые города (см. locationSubtitle ниже).
      name:    mapPinDisplayName(loc.region),
      x, y,
      anchorX: x,
      anchorY: y,
      // sqrt — differences менее экстремальны, чем линейный рост: 1 машина
      // и 50 машин не должны давать 12px против 43px (см. геометрический разбор выше).
      radius:  Math.round(PIN_MIN_R + Math.sqrt(pct) * (PIN_MAX_R - PIN_MIN_R)),
      count:   loc.count,
      color:   PIN_COLORS[idx % PIN_COLORS.length],
    }
  })

  return declutterPins(pins)
})

// ─── Pin/card click → popup drill ─────────────────────────────────────────────

const selectedLocationItem = computed(() =>
  selectedLocation.value ? regionData.value.find(r => r.region === selectedLocation.value) ?? null : null
)

async function openLocationDrill(region: string) {
  selectedLocation.value = region
  drillVehicles.value = []
  drillFilterQuery.value = ''
  drillLoading.value = true
  try {
    const resp = await apiFetch<{ items: any[] }>(`/vehicles-dashboard/drill?dimension=region&value=${encodeURIComponent(region)}`)
    drillVehicles.value = Array.isArray(resp?.items) ? resp.items : []
  } catch (e) {
    console.error('[FleetRegions] openLocationDrill', e)
  } finally {
    drillLoading.value = false
  }
}

function closeLocationDrill() {
  selectedLocation.value = null
  drillFilterQuery.value = ''
}

function onPinClick(pin: MapPin) {
  openLocationDrill(String(pin.id))
}

// ─── Vehicle search — загрузка ────────────────────────────────────────────────
// Переиспользуем GET /vehicles?q= — тот же параметр и тот же эндпоинт, что и
// реестр ТС (property/VehicleListView.vue, filterSearch → params.set('q', ...)),
// сервер уже ищет по brand/model/plate/vin с учётом видимости организаций
// (require_tab('vehicles') + _visibility_q) — своей серверной логики не
// придумываем, дублировать не нужно. Дебаунс — чтобы не долбить бэкенд на
// каждое нажатие клавиши.
//
// 2026-09 (правка после ручной проверки): q — простой SQL ilike '%q%' по
// сырому Vehicle.plate, а в БД госномер хранится БЕЗ пробела между буквой и
// цифрами ("Р937ХУ 180"). Задача владельца прямо требует, чтобы работали ОБА
// варианта — «Р 937» и «Р937» — набранные с живого госномера на машине или
// скопированные из документа. Раз это ограничение самого хранения (не
// подключаем tokenized/trigram-поиск ради одной страницы), решаем на клиенте:
// параллельно пробуем запрос как есть и «сжатый» (без пробелов), сливаем по id.
async function searchVehicles() {
  const q = vehicleSearchQuery.value.trim()
  if (!q) {
    vehicleSearchResults.value = []
    vehicleSearchTotal.value = 0
    vehicleSearchLoading.value = false
    return
  }
  vehicleSearchLoading.value = true
  try {
    const qCompact = q.replace(/\s+/g, '')
    const variants = qCompact !== q ? [q, qCompact] : [q]
    const responses = await Promise.all(
      variants.map(v =>
        apiFetch<{ items: VehicleSearchItem[]; total: number }>(
          `/vehicles?q=${encodeURIComponent(v)}&limit=${VEHICLE_SEARCH_LIMIT}`
        ).catch((e) => {
          console.error('[FleetRegions] searchVehicles variant failed', v, e)
          return { items: [] as VehicleSearchItem[], total: 0 }
        })
      )
    )
    // Запрос мог устареть, пока летел (пользователь печатает быстрее ответа) —
    // не затираем результат более свежего запроса более старым.
    if (vehicleSearchQuery.value.trim() !== q) return
    const byId = new Map<number, VehicleSearchItem>()
    let totalMax = 0
    for (const r of responses) {
      totalMax = Math.max(totalMax, r?.total ?? 0)
      for (const it of (r?.items ?? [])) byId.set(it.id, it)
    }
    vehicleSearchResults.value = Array.from(byId.values()).slice(0, VEHICLE_SEARCH_LIMIT)
    vehicleSearchTotal.value = Math.max(totalMax, vehicleSearchResults.value.length)
  } catch (e) {
    console.error('[FleetRegions] searchVehicles', e)
    vehicleSearchResults.value = []
    vehicleSearchTotal.value = 0
  } finally {
    if (vehicleSearchQuery.value.trim() === q) vehicleSearchLoading.value = false
  }
}

watch(vehicleSearchQuery, () => {
  if (vehicleSearchDebounce) clearTimeout(vehicleSearchDebounce)
  if (!vehicleSearchQuery.value.trim()) {
    // Очистка — карта/карточки должны мгновенно вернуться в обычный вид,
    // без ожидания дебаунса.
    vehicleSearchResults.value = []
    vehicleSearchTotal.value = 0
    vehicleSearchLoading.value = false
    return
  }
  vehicleSearchLoading.value = true
  vehicleSearchDebounce = setTimeout(searchVehicles, 300)
})

// ─── Visual helpers ───────────────────────────────────────────────────────────

const BADGE_PALETTES = [
  { bg: 'rgba(106,166,255,.12)', color: '#6aa6ff' },
  { bg: 'rgba(246,179,74,.12)',  color: '#f6b34a' },
  { bg: 'rgba(34,201,151,.12)',  color: '#22c997' },
  { bg: 'rgba(139,92,246,.12)', color: '#8b5cf6' },
  { bg: 'rgba(93,208,255,.12)', color: '#5dd0ff' },
  { bg: 'rgba(255,91,106,.12)', color: '#ff5b6a' },
]

const CARD_COLORS = ['blue', 'amber', 'green', 'purple', 'cyan', 'red'] as const

// 2026-09: раньше абревиатура бралась из первых букв ВСЕХ слов подряд, включая
// региональные префиксы ("ДНР г. Донецк" → "ДГД") — бессмысленный набор букв.
// Теперь префиксы региона/административной единицы отбрасываются, а «Место не
// указано» получает нейтральный прочерк вместо абревиатуры-мусора «МНУ».
const ABBR_NOISE = new Set(['днр', 'лнр', 'г.', 'г', 'обл.', 'область', 'край', 'респ.', 'республика'])

function locationAbbr(name: string): string {
  const trimmed = name.trim()
  if (!trimmed || trimmed === 'Место не указано') return '—'
  const words = trimmed.split(/\s+/).filter(Boolean)
  const meaningful = words.filter(w => !ABBR_NOISE.has(w.toLowerCase()))
  const pick = meaningful.length ? meaningful : words
  const lettersOnly = (w: string) => w.replace(/[^\p{L}]/gu, '')
  if (pick.length === 1) {
    const clean = lettersOnly(pick[0]) || pick[0]
    return clean.slice(0, 3).toUpperCase()
  }
  return pick.slice(0, 3).map(w => (lettersOnly(w)[0] || w[0] || '')).join('').toUpperCase()
}

function locationBadgeBg(idx: number): string {
  return BADGE_PALETTES[idx % BADGE_PALETTES.length].bg
}

function locationBadgeColor(idx: number): string {
  return BADGE_PALETTES[idx % BADGE_PALETTES.length].color
}

function cardColorClassForLocation(idx: number): string {
  return `rv-card--${CARD_COLORS[idx % CARD_COLORS.length]}`
}

// 2026-09 (geo-fix #4, п.1): раньше подпись под названием места нахождения
// («ФПГ ДНР» / «филиал ЦУ» и т.п.) бралась из geo_normalize.shtab_label_for_city
// — жёстко зашитый источник приобретения/штаб по кучке ключевых слов, не
// связанный с реальными данными парка. Владелец: на карте эта подпись лишняя
// (это не место нахождения, а справочная категория). В списке/карточках та же
// подпись настолько же неинформативна («группа не определена» почти всегда),
// поэтому здесь она тоже убрана — вместо неё показываем субъект РФ (регион),
// в котором находится место, если справочник городов (russiaCitiesCatalog.ts)
// смог его определить. Пусто — subtitle не рендерится (см. v-if в шаблоне).
function locationSubtitle(region: string): string {
  if (!region || region === 'Место не указано') return ''
  const hit = findCityInCatalog(region)
  return hit ? hit.region : ''
}

// ─── Navigation ──────────────────────────────────────────────────────────────

function goToVehicle(id: number) {
  router.push(`/fleet/vehicles/${id}`)
}

// ─── Format ──────────────────────────────────────────────────────────────────

function formatDate(iso: string): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

// ─── Data loading ─────────────────────────────────────────────────────────────

async function fetchRegions() {
  // 2026-09: раньше сюда же грузился /organizations/?limit=500 для счётчика
  // «Филиалов» — этот эндпоинт требует superadmin и админу отдавал пустой
  // список, поэтому счётчик всегда показывал 0 (см. тот же комментарий в
  // VehicleListView.vue про /auth/my-orgs). Раз речь теперь идёт о месте
  // нахождения ТС, а не об организации-владельце, KPI и подписи строятся из
  // regionData — отдельный список организаций странице больше не нужен.
  loadingRegions.value = true
  try {
    const regionResp = await apiFetch<{ items: RegionItem[]; mock_demo?: boolean }>('/vehicles-dashboard/by-region')
    regionData.value = Array.isArray(regionResp.items) ? regionResp.items : []
  } catch (e) {
    console.error('[FleetRegions] fetchRegions', e)
  } finally {
    loadingRegions.value = false
  }
}

async function fetchTransfers() {
  loadingTransfers.value = true
  try {
    // Try global recent endpoint first
    try {
      const data = await apiFetch<TransferRow[]>('/vehicles-dashboard/transfer-history-recent?limit=20')
      transfers.value = Array.isArray(data) ? data : []
      return
    } catch {
      // global endpoint not available — fall through to per-vehicle aggregation
    }

    // Fallback: load recent vehicles and aggregate their transfer histories
    const summary = await apiFetch<{ items: { vehicle_id: number; plate: string; brand_model: string | null }[] }>(
      '/vehicles-dashboard/all-vehicles-summary'
    ).catch(() => ({ items: [] }))

    const vehicleIds = (summary.items || []).slice(0, 10).map((v: any) => v.vehicle_id)
    const rows: TransferRow[] = []

    await Promise.all(vehicleIds.map(async (vid: number) => {
      const vInfo = (summary.items || []).find((v: any) => v.vehicle_id === vid)
      try {
        const hist = await apiFetch<any[]>(`/vehicles/${vid}/transfer-history`)
        if (Array.isArray(hist)) {
          hist.slice(0, 3).forEach(h => {
            rows.push({
              ...h,
              plate:       vInfo?.plate       ?? '',
              brand_model: vInfo?.brand_model ?? null,
            })
          })
        }
      } catch {}
    }))

    rows.sort((a, b) => new Date(b.changed_at).getTime() - new Date(a.changed_at).getTime())
    transfers.value = rows.slice(0, 20)
  } catch (e) {
    console.error('[FleetRegions] fetchTransfers', e)
    transfers.value = []
  } finally {
    loadingTransfers.value = false
  }
}

// ─── Init ────────────────────────────────────────────────────────────────────

onMounted(() => {
  fetchRegions()
  fetchTransfers()
  loadCitiesCatalog()
})
</script>

<style scoped>
/* ── CSS vars (dark defaults, overridden in light) ───────────────────────── */
.regions-view {
  --rv-bg:      #0a0d14;
  --rv-panel:   #141823;
  --rv-bg2:     #0f131c;
  --rv-line:    #222838;
  --rv-line2:   #2b3245;
  --rv-text:    #e9edf5;
  --rv-muted:   #8a93a8;
  --rv-muted2:  #5d6478;
  --rv-accent:  #6aa6ff;
  --rv-ok:      #22c997;
  --rv-warn:    #f6b34a;
  --rv-alert:   #ff5b6a;
  --rv-info:    #5dd0ff;

  padding: 22px 28px 60px;
  color: var(--rv-text);
  font-family: 'Inter', system-ui, sans-serif;
  font-size: 14px;
  min-height: 100vh;
}

.regions-view--light {
  --rv-bg:      #f4f6fb;
  --rv-panel:   #ffffff;
  --rv-bg2:     #eef1f7;
  --rv-line:    #e2e6f0;
  --rv-line2:   #d0d5e0;
  --rv-text:    #1a1d23;
  --rv-muted:   #6b7280;
  --rv-muted2:  #9ca3af;
  --rv-accent:  #2563eb;
}

/* ── Topbar ─────────────────────────────────────────────────────────────── */
.rv-topbar {
  display: flex;
  align-items: flex-start;
  gap: 18px;
  justify-content: space-between;
  margin-bottom: 18px;
}
/* Мобильный вьюпорт (владелец, задача про поиск, п.6): поле поиска — под
   заголовком на всю ширину, а не сплющено рядом с ним. */
@media (max-width: 720px) {
  .rv-topbar { flex-direction: column; align-items: stretch; }
}

.rv-crumbs {
  color: var(--rv-muted);
  font-size: 13px;
  margin-bottom: 4px;
}
.rv-crumbs a { color: var(--rv-muted); text-decoration: none; }
.rv-crumbs a:hover { color: var(--rv-accent); }
.rv-crumbs__sep { opacity: 0.5; margin: 0 4px; }
.rv-crumbs b { color: var(--rv-text); font-weight: 600; }

.rv-h1 {
  margin: 0 0 4px;
  font-size: 24px;
  font-weight: 800;
  letter-spacing: -0.4px;
}

.rv-lead {
  color: var(--rv-muted);
  margin: 0;
  font-size: 13px;
}

/* ── Vehicle search (владелец: «поиск по автомобилю, как в Иерархии») ─────── */
.rv-vsearch {
  position: relative;
  width: 320px;
  flex-shrink: 0;
}
@media (max-width: 720px) { .rv-vsearch { width: 100%; } }

.rv-vsearch__box {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--rv-panel);
  border: 1px solid var(--rv-line2);
  border-radius: 999px;
  padding: 8px 12px;
}
.rv-vsearch__box:focus-within { border-color: var(--rv-accent); }
.rv-vsearch__ic { color: var(--rv-muted); font-size: 15px; flex-shrink: 0; }
.rv-vsearch__input {
  flex: 1;
  min-width: 0;
  border: none;
  outline: none;
  background: transparent;
  color: var(--rv-text);
  font-size: 13px;
  font-family: inherit;
}
.rv-vsearch__input::placeholder { color: var(--rv-muted2); }
.rv-vsearch__clear {
  border: none;
  background: none;
  color: var(--rv-muted);
  cursor: pointer;
  font-size: 12px;
  padding: 2px 4px;
  flex-shrink: 0;
}
.rv-vsearch__clear:hover { color: var(--rv-text); }
/* Счётчик совпадений — тот же приём, что в Иерархии (зелёный/красный чип) */
.rv-vsearch__count {
  flex-shrink: 0;
  min-width: 20px;
  text-align: center;
  padding: 2px 7px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 800;
  font-family: 'JetBrains Mono', monospace;
}
.rv-vsearch__count--ok   { background: rgba(34,201,151,.16); color: #22c997; }
.rv-vsearch__count--zero { background: rgba(255,91,106,.16); color: #ff5b6a; }

.rv-vsearch__results {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  right: 0;
  z-index: 40;
  background: var(--rv-panel);
  border: 1px solid var(--rv-line2);
  border-radius: 12px;
  box-shadow: 0 12px 32px rgba(0,0,0,.25);
  max-height: 320px;
  overflow-y: auto;
  padding: 6px;
}
.rv-vsearch__row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 8px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 12.5px;
}
.rv-vsearch__row:hover { background: rgba(255,255,255,.05); }
.regions-view--light .rv-vsearch__row:hover { background: rgba(0,0,0,.04); }
.rv-vsearch__row-nm { font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.rv-vsearch__row-sep { color: var(--rv-muted2); }
.rv-vsearch__row-loc { color: var(--rv-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.rv-vsearch__hint {
  padding: 10px 8px;
  color: var(--rv-muted);
  font-size: 12px;
  text-align: center;
}
.rv-vsearch__hint--empty { color: var(--rv-text); }

/* ── Data notice ────────────────────────────────────────────────────────── */
.rv-notice {
  background: rgba(246,179,74,.08);
  border: 1px solid rgba(246,179,74,.25);
  color: var(--rv-text);
  border-radius: 12px;
  padding: 10px 16px;
  font-size: 12.5px;
  margin-bottom: 16px;
}

/* ── KPI strip ──────────────────────────────────────────────────────────── */
.rv-kpi-row {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 14px;
  margin-bottom: 22px;
}
@media (max-width: 1100px) { .rv-kpi-row { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 700px)  { .rv-kpi-row { grid-template-columns: repeat(2, 1fr); } }

/* ── Panel base ─────────────────────────────────────────────────────────── */
.rv-panel {
  background: linear-gradient(180deg, var(--rv-panel), var(--rv-bg2));
  border: 1px solid var(--rv-line);
  border-radius: 16px;
  padding: 18px;
}

.rv-panel__head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 14px;
  font-size: 14px;
  font-weight: 600;
}
.rv-panel__head small {
  color: var(--rv-muted);
  font-weight: 400;
  font-size: 12px;
  margin-left: auto;
}

/* ── Map row ────────────────────────────────────────────────────────────── */
.rv-map-row {
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: 18px;
  margin-bottom: 22px;
}
@media (max-width: 960px) { .rv-map-row { grid-template-columns: 1fr; } }

.rv-map-box { position: relative; overflow: hidden; }

/* ── Top-list ───────────────────────────────────────────────────────────── */
.rv-reg-row {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 12px;
  padding: 11px 0;
  border-bottom: 1px solid var(--rv-line);
  cursor: pointer;
  border-radius: 0;
  transition: background 0.12s;
}
.rv-reg-row:last-child { border-bottom: none; }
.rv-reg-row:hover {
  background: rgba(255,255,255,.03);
  margin: 0 -12px;
  padding-left: 12px;
  padding-right: 12px;
  border-radius: 10px;
}
.regions-view--light .rv-reg-row:hover { background: rgba(0,0,0,.03); }

.rv-reg-row__ic {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
  font-size: 11px;
  flex-shrink: 0;
}

/* min-width:0 — тот же приём, что и в .rv-card__title (см. комментарий там):
   без него длинное название («Петропавловск-Камчатский (Камчатский край)»)
   расталкивает grid-колонку и заезжает под число справа. */
.rv-reg-row__info { min-width: 0; }
.rv-reg-row__nm {
  font-weight: 700;
  font-size: 13.5px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
}
.rv-reg-row__ds { color: var(--rv-muted); font-size: 11.5px; margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.rv-reg-row__cnt {
  text-align: right;
  font-weight: 800;
  font-size: 18px;
  letter-spacing: -0.3px;
  font-family: 'JetBrains Mono', monospace;
  white-space: nowrap;
}
.rv-reg-row__cnt small {
  display: block;
  color: var(--rv-muted);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0;
  text-align: right;
  margin-top: 1px;
}

/* ── Section title ──────────────────────────────────────────────────────── */
.rv-section-title {
  margin: 8px 0 16px;
  font-size: 18px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 10px;
}
.rv-section-title__sub {
  font-size: 12px;
  font-weight: 400;
  color: var(--rv-muted);
}

/* ── Cards grid ─────────────────────────────────────────────────────────── */
.rv-cards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 16px;
  margin-bottom: 4px;
}
/* На узких экранах (мобильный вьюпорт) minmax(340px,...) шире доступной
   ширины (даже с учётом padding .regions-view) — одна колонка вместо
   вынужденного горизонтального скролла. */
@media (max-width: 420px) {
  .regions-view { padding: 16px 14px 48px; }
  .rv-cards-grid { grid-template-columns: 1fr; }
}

.rv-card {
  --rc-color: rgba(106,166,255,.15);
  background: linear-gradient(180deg, var(--rv-panel), var(--rv-bg2));
  border: 1px solid var(--rv-line);
  border-radius: 16px;
  padding: 18px;
  position: relative;
  overflow: hidden;
  transition: border-color 0.15s, transform 0.15s;
}
.rv-card:hover { border-color: var(--rv-accent); transform: translateY(-2px); }

.rv-card::before {
  content: '';
  position: absolute;
  top: -30px;
  right: -30px;
  width: 160px;
  height: 160px;
  border-radius: 50%;
  background: radial-gradient(circle, var(--rc-color), transparent 70%);
  pointer-events: none;
}

.rv-card--blue   { --rc-color: rgba(106,166,255,.18); }
.rv-card--green  { --rc-color: rgba(34,201,151,.18); }
.rv-card--amber  { --rc-color: rgba(246,179,74,.18); }
.rv-card--purple { --rc-color: rgba(139,92,246,.18); }
.rv-card--red    { --rc-color: rgba(255,91,106,.16); }
.rv-card--cyan   { --rc-color: rgba(93,208,255,.18); }

/* 2026-09 (правка владельца, «адрес не должен наезжать на количество»):
   раньше .rv-card__big был position:absolute поверх .rv-card__head — flex-раскладка
   .rv-card__title вычисляла себе ширину БЕЗ учёта числа (оно вне потока), поэтому
   при длинном названии («Подольск (Московская область)») текст реально доходил до
   правого края карточки и накладывался на число сверху. Теперь три колонки —
   бейдж/название/число — свои, число всегда в собственной колонке фиксированной
   ширины, название переносится в своей и никогда под него не заезжает. */
.rv-card__head {
  display: grid;
  grid-template-columns: 50px minmax(0, 1fr) auto;
  align-items: flex-start;
  gap: 14px;
  margin-bottom: 14px;
}

.rv-card__flag {
  width: 50px;
  height: 50px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
  font-size: 14px;
  flex-shrink: 0;
  background: rgba(106,166,255,.1);
  color: var(--rv-accent);
  border: 1px solid rgba(106,166,255,.2);
}
.rv-card--green  .rv-card__flag { background: rgba(34,201,151,.1);  color: var(--rv-ok);    border-color: rgba(34,201,151,.25); }
.rv-card--amber  .rv-card__flag { background: rgba(246,179,74,.1);  color: var(--rv-warn);  border-color: rgba(246,179,74,.25); }
.rv-card--purple .rv-card__flag { background: rgba(139,92,246,.1);  color: #8b5cf6;          border-color: rgba(139,92,246,.25); }
.rv-card--red    .rv-card__flag { background: rgba(255,91,106,.1);  color: var(--rv-alert); border-color: rgba(255,91,106,.25); }
.rv-card--cyan   .rv-card__flag { background: rgba(93,208,255,.1);  color: var(--rv-info);  border-color: rgba(93,208,255,.25); }

/* 2026-09 (поиск по машине, «как в Иерархии») — та же подсветка, что у пинов
   карты (RussiaMapSvg.vue) и у узлов графа (HierarchyView.vue): совпавшая
   карточка пульсирует оранжевым, остальные гаснут. Карточки — единственное
   место, где видна группа «Место не указано» (на карте у неё нет кружка). */
.rv-card--dim {
  opacity: 0.35;
  filter: grayscale(0.4);
  transition: opacity 0.3s, filter 0.3s;
}
.rv-card--match {
  outline: 3px solid #fb923c;
  outline-offset: 2px;
  animation: rv-card-match-glow 1.3s ease-in-out infinite;
}
@keyframes rv-card-match-glow {
  0%, 100% { box-shadow: 0 0 0 4px rgba(251,146,60,.20), 0 0 16px 2px rgba(251,146,60,.45); }
  50%      { box-shadow: 0 0 0 6px rgba(251,146,60,.35), 0 0 30px 8px rgba(251,146,60,.75); }
}

/* min-width:0 обязателен — без него grid-колонка не сжимается под длинный
   безразрывный текст и всё равно расталкивает соседние колонки (стандартная
   ловушка grid/flex, дефолт min-width:auto). */
.rv-card__title { min-width: 0; }
/* Две строки — нормальный случай для длинных названий («Петропавловск-
   Камчатский», «Анадырь (Чукотский автономный округ)»), карточки не должны
   при этом расползаться по высоте бесконечно — дальше многоточие, полное
   имя остаётся в title="" (см. шаблон) по наведению. */
.rv-card__nm {
  font-weight: 800;
  font-size: 17px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
}
.rv-card__ds {
  color: var(--rv-muted);
  font-size: 12.5px;
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rv-card__big {
  font-size: 32px;
  font-weight: 800;
  letter-spacing: -0.6px;
  color: var(--rv-text);
  line-height: 1;
  font-family: 'JetBrains Mono', monospace;
  white-space: nowrap;
  text-align: right;
}
.rv-card__big small {
  display: block;
  font-size: 11px;
  font-weight: 600;
  color: var(--rv-muted);
  text-transform: uppercase;
  letter-spacing: 0.4px;
  margin-top: 2px;
  text-align: right;
  font-family: 'Inter', sans-serif;
}

/* Status chips */
.rv-card__chips { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 14px; }
.rv-chip {
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  background: rgba(255,255,255,.04);
  border: 1px solid var(--rv-line);
  color: var(--rv-muted);
}
.rv-chip--ok    { background: rgba(34,201,151,.12);  color: #22c997; border-color: rgba(34,201,151,.2); }
.rv-chip--warn  { background: rgba(246,179,74,.12);  color: #f6b34a; border-color: rgba(246,179,74,.2); }
.rv-chip--alert { background: rgba(255,91,106,.12);  color: #ff5b6a; border-color: rgba(255,91,106,.2); }
/* Нейтральный — «без состояния» это не оценка парка (не тревога, не ОК),
   поэтому сознательно НЕ зелёный/жёлтый/красный, как остальные три чипа. */
.rv-chip--muted { background: rgba(148,163,184,.12); color: #94a3b8; border-color: rgba(148,163,184,.2); }

/* Footer */
.rv-card__footer {
  display: flex;
  align-items: center;
  gap: 10px;
  padding-top: 12px;
  border-top: 1px solid var(--rv-line);
}
.rv-card__head-nm { font-weight: 700; font-size: 12.5px; }
.rv-card__head-ro { color: var(--rv-muted); font-size: 11px; }

/* ── Transfer log ───────────────────────────────────────────────────────── */
.rv-tx-list { display: grid; gap: 8px; }

.rv-tx {
  display: grid;
  grid-template-columns: auto 1fr auto 1fr auto auto;
  gap: 12px;
  align-items: center;
  padding: 10px 14px;
  border: 1px solid var(--rv-line);
  border-radius: 12px;
  background: rgba(255,255,255,.02);
  font-size: 13px;
  cursor: pointer;
  transition: border-color 0.12s, background 0.12s;
}
.rv-tx:hover { border-color: var(--rv-accent); background: rgba(106,166,255,.04); }
.regions-view--light .rv-tx { background: rgba(0,0,0,.01); }
.regions-view--light .rv-tx:hover { background: rgba(37,99,235,.04); }

.rv-tx__nm   { font-weight: 700; font-size: 13px; }
.rv-tx__ds   { color: var(--rv-muted); font-size: 11.5px; margin-top: 1px; }
.rv-tx__arr  { color: var(--rv-muted2); font-size: 18px; font-weight: 700; }
.rv-tx__when { color: var(--rv-muted); font-size: 12px; font-weight: 600; white-space: nowrap; text-align: right; }
.rv-tx__detail { color: var(--rv-muted); font-size: 11.5px; }
.rv-tx__basis { font-style: italic; }

@media (max-width: 900px) {
  .rv-tx { grid-template-columns: auto 1fr auto auto; }
  .rv-tx__from, .rv-tx__to { display: none; }
}

/* ── Buttons ────────────────────────────────────────────────────────────── */
.rv-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border-radius: 10px;
  border: 1px solid var(--rv-line2);
  background: var(--rv-panel);
  color: var(--rv-text);
  font-weight: 600;
  font-size: 13px;
  cursor: pointer;
  transition: border-color 0.12s, background 0.12s;
  white-space: nowrap;
}
.rv-btn:hover { border-color: var(--rv-accent); }
.rv-btn--sm { padding: 5px 10px; font-size: 12px; border-radius: 8px; }
.rv-btn--primary {
  background: linear-gradient(180deg, #5a96ff, #4a85f0);
  border-color: #3a74dc;
  color: #fff;
}
.rv-btn--primary:hover { background: linear-gradient(180deg, #6aa6ff, #5a96ff); }

/* ── Pin popup ──────────────────────────────────────────────────────────── */
.rv-popup-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,.45);
  z-index: 9998;
  display: flex;
  align-items: center;
  justify-content: center;
}

.rv-popup {
  background: #141823;
  border: 1px solid #2b3245;
  border-radius: 18px;
  padding: 22px;
  min-width: 300px;
  max-width: 380px;
  width: 90%;
  z-index: 9999;
  box-shadow: 0 20px 60px rgba(0,0,0,.5);
  /* 2026-09 (правка владельца, «10 машин без прокрутки»): попап растёт вместе
     со списком (см. .rv-popup__vehicles ниже), но не дальше 90% высоты
     окна — иначе на ноутбучном/мобильном экране он вылезал бы за край.
     display:flex + overflow:hidden здесь и min-height:0 на детях — стандартный
     паттерн «шапка фиксирована, скроллится только внутренний список»: сам
     .rv-popup не скроллится, скроллится только .rv-popup__vehicles. */
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.rv-popup--light { background: #fff; border-color: #e2e6f0; }

.rv-popup__head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  flex-shrink: 0;
}

.rv-popup__abbr {
  width: 42px;
  height: 42px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
  font-size: 13px;
  color: #0a0d14;
  flex-shrink: 0;
}

.rv-popup__nm { font-weight: 800; font-size: 17px; }
.rv-popup__sub { color: var(--rv-muted); font-size: 12px; margin-top: 2px; }

.rv-popup__close {
  margin-left: auto;
  background: none;
  border: none;
  color: var(--rv-muted);
  cursor: pointer;
  font-size: 16px;
  padding: 4px;
  border-radius: 6px;
  transition: color 0.12s;
}
.rv-popup__close:hover { color: var(--rv-text); }

.rv-popup__body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  /* flex:1 + min-height:0 — тело растёт до max-height родителя, отдавая
     освободившееся место списку машин, но не выталкивает попап за экран
     (min-height:0 обязателен — без него flex-элемент не хочет сжиматься
     ниже контента, и внутренний скролл .rv-popup__vehicles не срабатывает). */
  flex: 1 1 auto;
  min-height: 0;
}

.rv-popup__stat {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  border-radius: 10px;
  background: rgba(255,255,255,.03);
  border: 1px solid var(--rv-line);
  flex-shrink: 0;
}
.rv-popup--light .rv-popup__stat { background: #f4f6fb; border-color: #e2e6f0; }

.rv-popup__stat-l { color: var(--rv-muted); font-size: 12px; }
.rv-popup__stat-v { font-weight: 700; font-size: 13px; }

/* 2026-09 (владелец: «в попапе нужен поиск») — фильтр по уже загруженному
   списку машин конкретного места (список маленький, серверный запрос не нужен). */
.rv-popup__filter {
  display: flex;
  align-items: center;
  gap: 6px;
  background: rgba(255,255,255,.03);
  border: 1px solid var(--rv-line);
  border-radius: 10px;
  padding: 7px 10px;
  margin-bottom: 8px;
  flex-shrink: 0;
}
.rv-popup--light .rv-popup__filter { background: #f4f6fb; border-color: #e2e6f0; }
.rv-popup__filter-ic { color: var(--rv-muted); font-size: 13px; flex-shrink: 0; }
.rv-popup__filter-input {
  flex: 1;
  min-width: 0;
  border: none;
  outline: none;
  background: transparent;
  color: var(--rv-text);
  font-size: 12.5px;
  font-family: inherit;
}
.rv-popup__filter-input::placeholder { color: var(--rv-muted2); }
.rv-popup__filter-clear {
  border: none;
  background: none;
  color: var(--rv-muted);
  cursor: pointer;
  font-size: 11px;
  flex-shrink: 0;
}
.rv-popup__filter-clear:hover { color: var(--rv-text); }
.rv-popup__filter-count {
  color: var(--rv-muted);
  font-size: 11.5px;
  margin: -2px 0 8px 2px;
  flex-shrink: 0;
}

.rv-popup__vehicles {
  display: grid;
  align-content: start;
  gap: 6px;
  /* 2026-09 (правка владельца, «10 машин без прокрутки»): было фиксированных
     260px (~5 строк) — вдвое мало. flex:1 (родитель .rv-popup__body — flex-
     column) отдаёт этому блоку всё место, оставшееся внутри .rv-popup
     max-height:90vh после шапки и строки «ТС всего»; на типичном
     ноутбучном/десктопном окне это ~550-650px (≈10-13 строк по ~44px),
     на мобильном 90vh даёт пропорционально меньше, но всё равно больше
     исходных 260px. min-height задаёт лишь запасной вариант на случай,
     если flex-родитель почему-то не растянулся (не должно случаться) —
     без него список выглядел бы куце даже при малом числе машин. Скролл
     остаётся для случаев, когда список не помещается целиком.
     Watch out: min-height:0 обязателен вместе с flex:1 — иначе flex-item
     не сжимается ниже своего контента и overflow-y:auto не срабатывает. */
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
}
.rv-popup__veh {
  display: grid;
  grid-template-columns: auto auto 1fr;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 10px;
  background: rgba(255,255,255,.03);
  border: 1px solid var(--rv-line);
  cursor: pointer;
  font-size: 12.5px;
  transition: border-color 0.12s;
}
.rv-popup__veh:hover { border-color: var(--rv-accent); }
.rv-popup--light .rv-popup__veh { background: #f4f6fb; }
.rv-popup__veh-ic { flex-shrink: 0; opacity: 0.9; }
.rv-popup__veh-nm {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rv-popup__footer { display: flex; justify-content: flex-end; }

/* ── Popup transition ───────────────────────────────────────────────────── */
.rv-popup-fade-enter-active,
.rv-popup-fade-leave-active { transition: opacity 0.18s ease; }
.rv-popup-fade-enter-from,
.rv-popup-fade-leave-to { opacity: 0; }

/* ── Loading ────────────────────────────────────────────────────────────── */
.rv-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 80px;
}

.rv-spinner {
  width: 28px;
  height: 28px;
  border: 3px solid var(--rv-line);
  border-top-color: var(--rv-accent);
  border-radius: 50%;
  animation: rv-spin 0.7s linear infinite;
}
@keyframes rv-spin { to { transform: rotate(360deg); } }

/* ── Empty state ────────────────────────────────────────────────────────── */
.rv-empty {
  color: var(--rv-muted);
  font-size: 13px;
  padding: 20px 0;
  text-align: center;
}
</style>
