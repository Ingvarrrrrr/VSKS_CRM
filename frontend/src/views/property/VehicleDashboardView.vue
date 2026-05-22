<template>
  <div class="fleet-dash" :class="{ 'fleet-dash--light': !isDark }" :style="dashboardAccentStyle">
    <!-- ── Topbar ── -->
    <div class="fleet-topbar">
      <div class="fleet-crumbs">
        Автопарк <span class="fleet-crumbs__sep">/</span>
        <b>Все ТС</b>
      </div>
      <div class="fleet-search">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>
        </svg>
        <input
          v-model="searchQuery"
          placeholder="Поиск по госномеру, VIN, марке, ответственному…"
          class="fleet-search__input"
        />
      </div>
      <div class="fleet-topbar__actions">

        <button class="fleet-btn" @click="onExport">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <path d="M7 10l5 5 5-5"/><path d="M12 15V3"/>
          </svg>
          Экспорт
        </button>
        <button class="fleet-btn" @click="goToTripPicker">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
          </svg>
          Путевой лист
        </button>
        <button class="fleet-btn" @click="router.push('/m/driver')" title="Мобильный кабинет водителя">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="5" y="2" width="14" height="20" rx="2"/><line x1="12" y1="18" x2="12" y2="18"/>
          </svg>
          Кабинет водителя
        </button>
        <button class="fleet-btn fleet-btn--primary" @click="router.push('/property/vehicles/new')">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 5v14M5 12h14"/>
          </svg>
          Добавить ТС
        </button>
      </div>
    </div>

    <!-- ── Filter bar: Тип ТС + Регион ── -->
    <div class="fleet-filterbar">
      <div class="fleet-filterbar__item">
        <label class="fleet-filterbar__label">Тип ТС</label>
        <select multiple v-model="selectedTypes" class="fleet-filterbar__select" size="1">
          <option v-for="t in VEHICLE_TYPE_OPTIONS" :key="t.value" :value="t.value">{{ t.label }}</option>
        </select>
        <div class="fleet-filterbar__chips" v-if="selectedTypes.length">
          <span
            v-for="t in selectedTypes"
            :key="t"
            class="fleet-filterbar__chip"
            @click="selectedTypes = selectedTypes.filter(x => x !== t)"
          >{{ VEHICLE_TYPE_LABELS[t] || t }} ×</span>
        </div>
      </div>
      <div class="fleet-filterbar__item">
        <label class="fleet-filterbar__label">Регион</label>
        <select multiple v-model="selectedRegions" class="fleet-filterbar__select" size="1">
          <option v-for="reg in availableRegions" :key="reg" :value="reg">{{ reg }}</option>
        </select>
        <div class="fleet-filterbar__chips" v-if="selectedRegions.length">
          <span
            v-for="reg in selectedRegions"
            :key="reg"
            class="fleet-filterbar__chip"
            @click="selectedRegions = selectedRegions.filter(x => x !== reg)"
          >{{ reg }} ×</span>
        </div>
      </div>
      <button
        v-if="selectedTypes.length || selectedRegions.length"
        class="fleet-btn"
        style="align-self:flex-end"
        @click="selectedTypes = []; selectedRegions = []"
      >Сбросить</button>
    </div>

    <!-- ── KPI Cards ── -->
    <section class="fleet-kpis">
      <!-- Total -->
      <div class="fleet-kpi fleet-kpi--clickable" @click="resetAllFilters">
        <div class="fleet-kpi__label">Всего в реестре</div>
        <div class="fleet-kpi__value">{{ kpi.total_vehicles }}</div>
        <div class="fleet-kpi__sub">авто, спецтехника, квадроциклы, прицепы</div>
        <div class="fleet-kpi__bar">
          <i style="width:100%;background:linear-gradient(90deg,#6aa6ff,#8b5cf6)"></i>
        </div>
      </div>
      <!-- Working -->
      <div class="fleet-kpi fleet-kpi--clickable" @click="applyKpiFilter('working')">
        <div class="fleet-kpi__label">В рабочем</div>
        <div class="fleet-kpi__value">{{ filterCounts.working }}</div>
        <div class="fleet-kpi__trend fleet-kpi__trend--ok">+2 за неделю</div>
        <div class="fleet-kpi__sub">{{ workingPct }}% парка</div>
        <div class="fleet-kpi__bar">
          <i :style="`width:${workingPct}%;background:linear-gradient(90deg,#22c997,#5dd0ff)`"></i>
        </div>
      </div>
      <!-- In repair -->
      <div class="fleet-kpi fleet-kpi--clickable" @click="applyKpiFilter('in_repair')">
        <div class="fleet-kpi__label">В ремонте</div>
        <div class="fleet-kpi__value">{{ filterCounts.in_repair }}</div>
        <div class="fleet-kpi__trend fleet-kpi__trend--warn">−1</div>
        <div class="fleet-kpi__sub">включая неисправные</div>
        <div class="fleet-kpi__bar">
          <i :style="`width:${repairPct}%;background:linear-gradient(90deg,#f6b34a,#ff8a4a)`"></i>
        </div>
      </div>
      <!-- Not running -->
      <div class="fleet-kpi fleet-kpi--clickable" @click="applyKpiFilter('not_running')">
        <div class="fleet-kpi__label">Не на ходу / списать</div>
        <div class="fleet-kpi__value">{{ filterCounts.not_running }}</div>
        <div class="fleet-kpi__trend fleet-kpi__trend--alert">+3</div>
        <div class="fleet-kpi__sub">требует решения по эксплуатации</div>
        <div class="fleet-kpi__bar">
          <i :style="`width:${notRunningPct}%;background:linear-gradient(90deg,#ff5b6a,#ff3b8b)`"></i>
        </div>
      </div>
      <!-- Docs -->
      <div class="fleet-kpi fleet-kpi--clickable" @click="applyKpiFilter('docs_expiring')">
        <div class="fleet-kpi__label">Документы — истекли/истекают</div>
        <div class="fleet-kpi__value">{{ maintenanceWarnings.length }}</div>
        <div class="fleet-kpi__trend fleet-kpi__trend--alert">+2</div>
        <div class="fleet-kpi__sub">ОСАГО, ТО, СТС</div>
        <div class="fleet-kpi__bar">
          <i :style="`width:${docsPct}%;background:linear-gradient(90deg,#ff5b6a,#ff3b8b)`"></i>
        </div>
      </div>
    </section>

    <!-- ── Two-column: Regions + Driver reports ── -->
    <section class="fleet-two-col">
      <!-- Regions -->
      <div class="fleet-panel">
        <h3 class="fleet-panel__title">
          География эксплуатации
          <small>распределение по штабам и регионам</small>
        </h3>
        <!-- Geography tiles grid -->
        <div class="fleet-reg-tiles" v-if="regionItems.length">
          <div
            class="fleet-reg-tile"
            v-for="reg in visibleRegionItems"
            :key="reg.region"
            :class="{ 'fleet-reg-tile--active': selectedRegions.includes(reg.region) }"
            :title="`${reg.region} — всего ${reg.count}\nРабочих: ${regSegments(reg).working}\nВ ремонте: ${regSegments(reg).inRepair}${regSegments(reg).broken ? '\nНе на ходу: ' + regSegments(reg).broken : ''}`"
            @click="applyRegionFilter(reg.region)"
          >
            <!-- Header: region name -->
            <div class="fleet-reg-tile__nm">{{ reg.region }}</div>
            <!-- Center: total count -->
            <div class="fleet-reg-tile__cnt">{{ reg.count }}</div>
            <!-- Footer: status dots -->
            <div class="fleet-reg-tile__dots">
              <!-- Working: green -->
              <template v-if="regSegments(reg).working > 0">
                <span
                  v-for="n in Math.min(regSegments(reg).working, REG_DOT_MAX)"
                  :key="'w' + n"
                  class="fleet-reg-tile__dot fleet-reg-tile__dot--working"
                ></span>
                <span v-if="regSegments(reg).working > REG_DOT_MAX" class="fleet-reg-tile__dot-more">+{{ regSegments(reg).working - REG_DOT_MAX }}</span>
              </template>
              <!-- In repair: yellow -->
              <template v-if="regSegments(reg).inRepair > 0">
                <span
                  v-for="n in Math.min(regSegments(reg).inRepair, REG_DOT_MAX)"
                  :key="'r' + n"
                  class="fleet-reg-tile__dot fleet-reg-tile__dot--repair"
                ></span>
                <span v-if="regSegments(reg).inRepair > REG_DOT_MAX" class="fleet-reg-tile__dot-more">+{{ regSegments(reg).inRepair - REG_DOT_MAX }}</span>
              </template>
              <!-- Broken / не на ходу: red -->
              <template v-if="regSegments(reg).broken > 0">
                <span
                  v-for="n in Math.min(regSegments(reg).broken, REG_DOT_MAX)"
                  :key="'b' + n"
                  class="fleet-reg-tile__dot fleet-reg-tile__dot--broken"
                ></span>
                <span v-if="regSegments(reg).broken > REG_DOT_MAX" class="fleet-reg-tile__dot-more">+{{ regSegments(reg).broken - REG_DOT_MAX }}</span>
              </template>
              <!-- Other statuses: grey -->
              <template v-if="regSegments(reg).other > 0">
                <span
                  v-for="n in Math.min(regSegments(reg).other, REG_DOT_MAX)"
                  :key="'o' + n"
                  class="fleet-reg-tile__dot fleet-reg-tile__dot--other"
                ></span>
                <span v-if="regSegments(reg).other > REG_DOT_MAX" class="fleet-reg-tile__dot-more">+{{ regSegments(reg).other - REG_DOT_MAX }}</span>
              </template>
            </div>
          </div>
        </div>
        <!-- Show more / collapse -->
        <div v-if="regionItems.length > REG_TILES_LIMIT" class="fleet-reg-tiles__more">
          <button class="fleet-chip" @click="showAllRegions = !showAllRegions">
            {{ showAllRegions ? 'Свернуть' : `Показать ещё ${regionItems.length - REG_TILES_LIMIT}` }}
          </button>
        </div>
        <div class="fleet-empty" v-if="!regionItems.length">
          <v-progress-circular v-if="loadingRegions" indeterminate color="#6aa6ff" size="24" />
          <span v-else>Нет данных о регионах</span>
        </div>
      </div>

      <!-- Driver reports -->
      <div class="fleet-panel">
        <h3 class="fleet-panel__title">
          Свежие отчёты водителей
          <small>с мобильного приложения</small>
        </h3>
        <ul class="fleet-feed" v-if="driverReports.length">
          <li v-for="(item, i) in driverReports" :key="i" class="fleet-feed__item">
            <div class="fleet-feed__ic" :class="`fleet-feed__ic--${item.ic}`">
              {{ IC_ICONS[item.ic] }}
            </div>
            <div class="fleet-feed__body">
              <b>{{ item.plate }}</b> · {{ item.title }}
              <small>{{ item.author ? item.author + ' · ' : '' }}{{ fmtTs(item.timestamp) }}</small>
            </div>
          </li>
        </ul>
        <div class="fleet-empty fleet-empty--feed" v-else-if="!loadingReports">
          Отчётов пока нет. Скоро будет мобильное приложение для водителей.
        </div>
        <div class="fleet-empty" v-else>
          <v-progress-circular indeterminate color="#6aa6ff" size="24" />
        </div>
      </div>
    </section>

    <!-- ── Filter chips + view toggle ── -->
    <div class="fleet-filters">
      <button
        class="fleet-chip"
        :class="{ 'fleet-chip--active': activeFilter === 'all' }"
        @click="activeFilter = 'all'"
      >
        Все <span class="fleet-chip__count">{{ filterCounts.all }}</span>
      </button>
      <button
        class="fleet-chip"
        :class="{ 'fleet-chip--active': activeFilter === 'working' }"
        @click="activeFilter = 'working'"
      >
        <i class="fleet-chip__dot fleet-chip__dot--ok"></i>
        Рабочие {{ filterCounts.working }}
      </button>
      <button
        class="fleet-chip"
        :class="{ 'fleet-chip--active': activeFilter === 'in_repair' }"
        @click="activeFilter = 'in_repair'"
      >
        <i class="fleet-chip__dot fleet-chip__dot--warn"></i>
        В ремонте {{ filterCounts.in_repair }}
      </button>
      <button
        class="fleet-chip"
        :class="{ 'fleet-chip--active': activeFilter === 'not_running' }"
        @click="activeFilter = 'not_running'"
      >
        <i class="fleet-chip__dot fleet-chip__dot--alert"></i>
        Не на ходу {{ filterCounts.not_running }}
      </button>
      <button
        class="fleet-chip"
        :class="{ 'fleet-chip--active': activeFilter === 'no_report' }"
        @click="activeFilter = 'no_report'"
      >
        <i class="fleet-chip__dot fleet-chip__dot--info"></i>
        Без отчёта 30+ дн.
      </button>
      <button
        class="fleet-chip"
        :class="{ 'fleet-chip--active': activeFilter === 'disposal' }"
        @click="activeFilter = 'disposal'"
      >
        <i class="fleet-chip__dot fleet-chip__dot--muted"></i>
        На списание {{ filterCounts.for_disposal }}
      </button>
      <button
        class="fleet-chip"
        :class="{ 'fleet-chip--active': activeFilter === 'docs_expiring' }"
        @click="activeFilter = 'docs_expiring'"
      >
        <i class="fleet-chip__dot fleet-chip__dot--alert"></i>
        Документы {{ maintenanceWarnings.length }}
      </button>

      <div class="fleet-filters__spacer"></div>

      <div class="fleet-view-toggle">
        <button
          :class="{ active: viewMode === 'cards' }"
          @click="viewMode = 'cards'"
        >Карточки</button>
        <button
          :class="{ active: viewMode === 'table' }"
          @click="viewMode = 'table'"
        >Таблица</button>
        <button
          :class="{ active: viewMode === 'regions' }"
          @click="viewMode = 'regions'"
        >По регионам</button>
      </div>
    </div>

    <!-- ── Cards view ── -->
    <section class="fleet-grid" v-if="viewMode === 'cards'">
      <VehicleCard
        v-for="v in filteredVehicles"
        :key="v.vehicle_id"
        :vehicle="toCardData(v)"
        @detail="router.push(`/property/vehicles/${v.vehicle_id}`)"
        @action="onCardAction"
      />
      <div v-if="loadingAll" class="fleet-loading-overlay">
        <v-progress-circular indeterminate color="#6aa6ff" size="36" />
      </div>
      <div v-if="!loadingAll && filteredVehicles.length === 0" class="fleet-empty fleet-empty--full">
        Нет транспортных средств
      </div>
    </section>

    <!-- ── Table view (existing functionality) ── -->
    <section v-else-if="viewMode === 'table'">
      <v-card class="fleet-table-card" elevation="0">
        <v-card-text class="pa-0">
          <v-data-table
            :items="filteredVehicles"
            :headers="tableHeaders"
            :search="searchQuery"
            density="compact"
            :items-per-page="20"
            class="fleet-table clickable-rows"
            @click:row="(_: unknown, { item }: { item: AllVehicleRow }) => router.push(`/property/vehicles/${item.vehicle_id}`)"
          >
            <template #item.plate="{ item }">
              <LicensePlate :model-value="item.plate" />
            </template>
            <template #item.state="{ item }">
              <span class="fleet-state-chip" :class="`fleet-state-chip--${item.state}`">
                {{ STATE_LABELS[item.state] || item.state }}
              </span>
            </template>
            <template #item.insurance_until="{ item }">
              <span :class="item.insurance_overdue ? 'text-red' : ''">
                {{ item.insurance_until || '—' }}
              </span>
            </template>
          </v-data-table>
        </v-card-text>
      </v-card>
    </section>

    <!-- ── Regions view ── -->
    <section v-else-if="viewMode === 'regions'">
      <div v-for="region in regionGroups" :key="region.name" class="fleet-region-group">
        <div class="fleet-region-group__header">
          <span class="fleet-region-group__name">{{ region.name }}</span>
          <span class="fleet-region-group__count">{{ region.vehicles.length }} ТС</span>
        </div>
        <div class="fleet-grid fleet-grid--compact">
          <VehicleCard
            v-for="v in region.vehicles"
            :key="v.vehicle_id"
            :vehicle="toCardData(v)"
            @detail="router.push(`/property/vehicles/${v.vehicle_id}`)"
            @action="onCardAction"
          />
        </div>
      </div>
    </section>

    <!-- ── Fine Leaders Widget ── -->
    <section class="fleet-fine-leaders-section">
      <FineLeadersPodiumWidget />
    </section>

    <!-- Phase 29.3-drill-inline: клик KPI/региона → activeFilter/selectedRegions inline -->
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useTheme } from 'vuetify'
import { apiFetch } from '@/api'
import VehicleCard from '@/components/vehicles/VehicleCard.vue'
import LicensePlate from '@/components/vehicles/LicensePlate.vue'
import FineLeadersPodiumWidget from '@/components/vehicles/FineLeadersPodiumWidget.vue'

const router = useRouter()
const theme = useTheme()
const isDark = computed(() => theme.global.current.value.dark)

// ── Vehicle type options ─────────────────────────────────────────────────────
const VEHICLE_TYPE_LABELS: Record<string, string> = {
  car_light: 'Легковой',
  suv: 'Внедорожник',
  pickup: 'Пикап',
  minivan: 'Минивэн',
  truck_van: 'Грузовой фургон',
  truck_board: 'Грузовой бортовой',
  truck_tank: 'Грузовой цистерна',
  truck_metal: 'Грузовой металловоз',
  bus: 'Автобус',
  special: 'Спецтехника',
  quadbike: 'Квадроцикл',
  snowmobile: 'Снегоход',
  boat: 'Лодка',
  boat_motor: 'Лодка с мотором',
  trailer: 'Прицеп',
  other: 'Другое',
}
const VEHICLE_TYPE_OPTIONS = Object.entries(VEHICLE_TYPE_LABELS).map(([value, label]) => ({ value, label }))

// ── Design constants ─────────────────────────────────────────────────────────
const IC_ICONS: Record<string, string> = {
  ok: '✓', warn: '⚠', alert: '!', info: 'i',
}

const STATE_LABELS: Record<string, string> = {
  working: 'Работает', broken: 'Сломан', in_repair: 'В ремонте',
  needs_repair: 'Треб. ремонта', destroyed: 'Уничтожен', utilized: 'Утилизирован',
}

// ── State ────────────────────────────────────────────────────────────────────
const viewMode = ref<'cards' | 'table' | 'regions'>('cards')
const searchQuery = ref('')
const activeFilter = ref<string>('all')
const selectedTypes = ref<string[]>([])
const selectedRegions = ref<string[]>([])

// ── Inline drill filter ───────────────────────────────────────────────────────
// Phase 29.3-drill-inline: клик KPI/региона → активирует chip-фильтр и скроллит к карточкам
function applyKpiFilter(stateCode: string) {
  activeFilter.value = stateCode
  nextTick(() => {
    document.querySelector('.fleet-filters')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
}
function applyRegionFilter(reg: string) {
  if (!selectedRegions.value.includes(reg)) {
    selectedRegions.value = [reg]
  } else {
    selectedRegions.value = []
  }
  nextTick(() => {
    document.querySelector('.fleet-filters')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
}
function applyRegionAndState(region: string, state: 'working' | 'in_repair' | 'not_running') {
  selectedRegions.value = [region]
  activeFilter.value = state
  nextTick(() => {
    document.querySelector('.fleet-chips-row, .fleet-card-grid, .fleet-filters')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
}
function resetAllFilters() {
  activeFilter.value = 'all'
  selectedTypes.value = []
  selectedRegions.value = []
  searchQuery.value = ''
  nextTick(() => {
    document.querySelector('.fleet-card-grid, .fleet-filters')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
}

// ── KPI ──────────────────────────────────────────────────────────────────────
interface KpiData {
  total_vehicles: number
  fuel_total_cost: number
  repairs_total_cost: number
  total_mileage_km: number
}

const kpi = ref<KpiData>({ total_vehicles: 0, fuel_total_cost: 0, repairs_total_cost: 0, total_mileage_km: 0 })

async function fetchKpi() {
  try {
    kpi.value = await apiFetch<KpiData>('/vehicles-dashboard/kpi')
  } catch (e) {
    console.error('[VehicleDash] kpi', e)
  }
}

// ── Filter counts ─────────────────────────────────────────────────────────────
interface FilterCounts {
  all: number
  working: number
  in_repair: number
  not_running: number
  no_report_30d: number
  for_disposal: number
  mock_demo?: boolean
}

const filterCounts = ref<FilterCounts>({
  all: 0, working: 0, in_repair: 0, not_running: 0, no_report_30d: 0, for_disposal: 0,
})

async function fetchFilterCounts() {
  try {
    filterCounts.value = await apiFetch<FilterCounts>('/vehicles-dashboard/filter-counts')
  } catch (e) {
    console.error('[VehicleDash] filter-counts', e)
  }
}

// ── KPI % helpers ─────────────────────────────────────────────────────────────
const total = computed(() => filterCounts.value.all || 1)
const workingPct = computed(() => Math.round(filterCounts.value.working / total.value * 100))
const repairPct = computed(() => Math.round(filterCounts.value.in_repair / total.value * 100))
const notRunningPct = computed(() => Math.round(filterCounts.value.not_running / total.value * 100))
const docsPct = computed(() => {
  const n = maintenanceWarnings.value.length
  return Math.round(Math.min(n / total.value * 100, 100))
})

// ── Maintenance warnings ──────────────────────────────────────────────────────
interface MaintenanceWarning {
  vehicle_id: number
  warning_type: string
  days_left: number | null
  km_left: number | null
}

const maintenanceWarnings = ref<MaintenanceWarning[]>([])

async function fetchWarnings() {
  try {
    maintenanceWarnings.value = await apiFetch<MaintenanceWarning[]>('/vehicles-dashboard/maintenance-warning')
  } catch (e) {
    console.error('[VehicleDash] warnings', e)
  }
}

// ── Regions ───────────────────────────────────────────────────────────────────
interface RegionItem {
  region: string
  count: number
  shtab_label: string
  by_state: Record<string, number>
}

const regionItems = ref<RegionItem[]>([])
const loadingRegions = ref(false)

const availableRegions = computed(() => regionItems.value.map(r => r.region).filter(Boolean))

const MAX_REG_COUNT = computed(() => Math.max(...regionItems.value.map(r => r.count), 1))

// Tiles constants
const REG_TILES_LIMIT = 12   // show first N tiles before "show more"
const REG_DOT_MAX = 4        // max dots per status before "+N" overflow label

const showAllRegions = ref(false)

// Sorted by count desc, capped if not showAll
const visibleRegionItems = computed(() => {
  const sorted = [...regionItems.value].sort((a, b) => b.count - a.count)
  return showAllRegions.value ? sorted : sorted.slice(0, REG_TILES_LIMIT)
})

function regSegments(reg: RegionItem) {
  const bs = reg.by_state || {}
  const working = bs['working'] || 0
  const inRepair = (bs['in_repair'] || 0) + (bs['needs_repair'] || 0)
  const broken = (bs['broken'] || 0) + (bs['destroyed'] || 0) + (bs['not_running'] || 0)
  const other = (bs['utilized'] || 0) + (bs['transferred'] || 0) + (bs['decommissioned'] || 0)
  const max = MAX_REG_COUNT.value
  const total = reg.count
  const total_w = Math.round((total / max) * 96)
  const working_w = Math.round((working / max) * 96)
  const in_repair_w = Math.round((inRepair / max) * 96)
  const broken_w = Math.round((broken / max) * 96)
  // pct values are relative to total bar width (100%)
  const working_pct = total > 0 ? Math.round((working / total) * 100) : 0
  const in_repair_pct = total > 0 ? Math.round((inRepair / total) * 100) : 0
  const broken_pct = total > 0 ? 100 - working_pct - in_repair_pct : 0
  return { working, inRepair, broken, other, total_w, working_w, in_repair_w, broken_w, working_pct, in_repair_pct, broken_pct }
}

async function fetchRegions() {
  loadingRegions.value = true
  try {
    const data = await apiFetch<{ items: RegionItem[]; mock_demo: boolean }>('/vehicles-dashboard/by-region')
    regionItems.value = data.items || []
  } catch (e) {
    console.error('[VehicleDash] regions', e)
  } finally {
    loadingRegions.value = false
  }
}

// ── Driver reports ────────────────────────────────────────────────────────────
interface ReportItem {
  vehicle_id: number
  plate: string
  type: string
  ic: string
  title: string
  author: string
  timestamp: string
}

const driverReports = ref<ReportItem[]>([])
const loadingReports = ref(false)

async function fetchDriverReports() {
  loadingReports.value = true
  try {
    const data = await apiFetch<ReportItem[]>('/vehicles-dashboard/driver-reports?limit=8')
    driverReports.value = Array.isArray(data) ? data : []
  } catch (e) {
    console.error('[VehicleDash] driver-reports', e)
    driverReports.value = []
  } finally {
    loadingReports.value = false
  }
}

// ── All vehicles table data ───────────────────────────────────────────────────
interface AllVehicleRow {
  vehicle_id: number
  plate: string
  brand_model: string
  state: string
  owner_org_name: string
  owner_org_color?: string | null
  assigned_org_color?: string | null
  fuel_cost: number
  repair_cost: number
  mileage_km: number
  insurance_overdue: boolean
  insurance_until: string | null
  // extra fields from detailed endpoint (may be absent)
  assigned_text?: string
  responsible_name?: string
  last_report_at?: string
  vin?: string
  type?: string
  year?: number
  color?: string
  odometer_km?: number
  akb_ok?: boolean | null
  tires_ok?: boolean | null
  mirrors_ok?: boolean | null
  has_radio?: boolean | null
  first_aid_kit_ok?: boolean | null
  fire_ext_ok?: boolean | null
  spare_wheel_ok?: boolean | null
  paint_ok?: boolean | null
  technical_state_note?: string
  sts_number?: string
  last_maintenance_at?: string
}

const allVehicles = ref<AllVehicleRow[]>([])
const loadingAll = ref(false)

async function fetchAllVehicles() {
  loadingAll.value = true
  try {
    const data = await apiFetch<AllVehicleRow[]>('/vehicles-dashboard/all-vehicles-summary')
    allVehicles.value = Array.isArray(data) ? data : []
  } catch (e) {
    console.error('[VehicleDash] all-vehicles', e)
  } finally {
    loadingAll.value = false
  }
}

// ── Filtering ─────────────────────────────────────────────────────────────────
const filteredVehicles = computed(() => {
  let list = allVehicles.value

  // Search by plate/brand_model/vin/responsible
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase().trim()
    list = list.filter(v => {
      const hay = `${v.plate} ${v.brand_model} ${v.vin || ''} ${v.responsible_name || ''}`.toLowerCase()
      return hay.includes(q)
    })
  }

  // Filter chip
  if (activeFilter.value === 'working') {
    list = list.filter(v => v.state === 'working')
  } else if (activeFilter.value === 'in_repair') {
    list = list.filter(v => ['in_repair', 'broken', 'needs_repair'].includes(v.state))
  } else if (activeFilter.value === 'not_running') {
    list = list.filter(v => ['destroyed', 'utilized'].includes(v.state))
  } else if (activeFilter.value === 'no_report') {
    const cutoff = Date.now() - 30 * 24 * 60 * 60 * 1000
    list = list.filter(v => {
      if (!v.last_report_at) return true
      return new Date(v.last_report_at).getTime() < cutoff
    })
  } else if (activeFilter.value === 'disposal') {
    list = list.filter(v => v.state === 'destroyed' || v.state === 'utilized')
  } else if (activeFilter.value === 'docs_expiring') {
    const warnIds = new Set(maintenanceWarnings.value.map(m => m.vehicle_id))
    list = list.filter(v => warnIds.has(v.vehicle_id))
  }

  // Type filter (multi)
  if (selectedTypes.value.length) {
    list = list.filter(v => v.type && selectedTypes.value.includes(v.type))
  }

  // Region filter (multi) — match against assigned_text with trim,
  // consistent with backend by_region which uses coalesce(assigned_text, 'Не указан')
  if (selectedRegions.value.length) {
    list = list.filter(v => {
      const vRegion = (v.assigned_text || '').trim() || 'Не указан'
      return selectedRegions.value.includes(vRegion)
    })
  }

  return list
})

// ── Region groups (for regions view) ─────────────────────────────────────────
const regionGroups = computed(() => {
  const map: Record<string, { name: string; vehicles: AllVehicleRow[] }> = {}
  for (const v of filteredVehicles.value) {
    const key = v.assigned_text || v.owner_org_name || 'Не указан'
    if (!map[key]) map[key] = { name: key, vehicles: [] }
    map[key].vehicles.push(v)
  }
  return Object.values(map).sort((a, b) => b.vehicles.length - a.vehicles.length)
})

// ── Table headers ─────────────────────────────────────────────────────────────
const tableHeaders = [
  { title: 'Гос.№', key: 'plate', width: 130 },
  { title: 'Марка/Модель', key: 'brand_model' },
  { title: 'Состояние', key: 'state', width: 140 },
  { title: 'Владелец', key: 'owner_org_name' },
  { title: 'Пробег км', key: 'mileage_km', align: 'end' as const, width: 100 },
  { title: 'ОСАГО', key: 'insurance_until', width: 130 },
]

// ── Card data adapter ─────────────────────────────────────────────────────────
function toCardData(v: AllVehicleRow) {
  const [brand, ...rest] = (v.brand_model || '').split(' ')
  return {
    id: v.vehicle_id,
    plate: v.plate,
    brand: brand || '',
    model: rest.join(' '),
    year: v.year,
    color: v.color,
    type: v.type,
    state: v.state,
    vin: v.vin,
    owner_org_name: v.owner_org_name,
    owner_org_color: v.owner_org_color,
    assigned_org_color: v.assigned_org_color,
    assigned_text: v.assigned_text,
    responsible_name: v.responsible_name,
    last_report_at: v.last_report_at,
    insurance_until: v.insurance_until || undefined,
    sts_number: v.sts_number,
    odometer_km: v.odometer_km || v.mileage_km,
    last_maintenance_at: v.last_maintenance_at,
    technical_state_note: v.technical_state_note,
    akb_ok: v.akb_ok,
    tires_ok: v.tires_ok,
    mirrors_ok: v.mirrors_ok,
    has_radio: v.has_radio,
    first_aid_kit_ok: v.first_aid_kit_ok,
    fire_ext_ok: v.fire_ext_ok,
    spare_wheel_ok: v.spare_wheel_ok,
    paint_ok: v.paint_ok,
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function fmtTs(ts: string): string {
  if (!ts) return ''
  try {
    return new Date(ts).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit' })
  } catch {
    return ts
  }
}

async function onExport() {
  const token = localStorage.getItem('auth_token') || localStorage.getItem('access_token') || ''
  const params = new URLSearchParams()
  if (activeFilter.value && activeFilter.value !== 'all' && activeFilter.value !== 'docs_expiring') {
    params.set('state', activeFilter.value)
  }
  if (selectedTypes.value.length === 1) params.set('type', selectedTypes.value[0])
  const url = `/api/vehicles/export/excel${params.toString() ? '?' + params.toString() : ''}`
  try {
    const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const blob = await res.blob()
    const dlUrl = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = dlUrl
    a.download = `vehicles_${new Date().toISOString().slice(0, 10)}.xlsx`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(dlUrl)
  } catch (e) {
    console.error('[VehicleDash] export failed:', e)
    alert('Ошибка экспорта')
  }
}

function goToTripPicker() {
  // Переход в список ТС с фильтром «Рабочие» — юзер кликает машину → карточка → вкладка «Путёвки»
  router.push({ path: '/property/vehicles', query: { state: 'working', pick_for: 'trip' } })
}

function onCardAction(payload: { type: string; vehicle: ReturnType<typeof toCardData> }) {
  if (payload.type === 'card' || payload.type === 'detail') {
    router.push(`/property/vehicles/${payload.vehicle.id}`)
  }
}

// ── Orgs list (for accent color) ─────────────────────────────────────────────
interface OrgItem { id: number; name: string; is_active: boolean; color?: string | null }
const orgsList = ref<OrgItem[]>([])
const selectedOwners = ref<number[]>([])

async function fetchOrgs() {
  try {
    const data = await apiFetch<OrgItem[]>('/auth/my-orgs')
    orgsList.value = Array.isArray(data) ? data : []
  } catch (e) {
    console.error('[VehicleDash] my-orgs', e)
  }
}

const activeOrgColor = computed<string | null>(() => {
  if (selectedOwners.value?.length === 1) {
    const o = orgsList.value.find(x => x.id === selectedOwners.value[0])
    if (o?.color) return o.color
  }
  return orgsList.value[0]?.color || null
})

const dashboardAccentStyle = computed(() => activeOrgColor.value ? {
  '--org-accent': activeOrgColor.value,
  '--org-accent-soft': activeOrgColor.value + '22',
} : {})

// ── Init ──────────────────────────────────────────────────────────────────────
onMounted(() => {
  fetchKpi()
  fetchFilterCounts()
  fetchWarnings()
  fetchRegions()
  fetchDriverReports()
  fetchAllVehicles()
  fetchOrgs()
})
</script>

<style scoped>
/* ─── Fleet design tokens (scoped) ─── */
.fleet-dash {
  --bg: #0a0d14;
  --bg-2: #0f131c;
  --panel: #141823;
  --panel-2: #1a1f2c;
  --line: #222838;
  --line-2: #2b3245;
  --text: #e9edf5;
  --muted: #8a93a8;
  --muted-2: #5d6478;
  --accent: #6aa6ff;
  --accent-2: #8b5cf6;
  --ok: #22c997;
  --warn: #f6b34a;
  --alert: #ff5b6a;
  --info: #5dd0ff;

  padding: 22px 28px 140px;
  min-height: 100vh;
  background: radial-gradient(1200px 600px at 80% -10%, rgba(106,166,255,.06), transparent 60%),
              radial-gradient(900px 500px at -10% 110%, rgba(139,92,246,.06), transparent 60%),
              var(--bg);
  color: var(--text);
  font-family: 'Inter', system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
  font-size: 14px;
  box-sizing: border-box;
}

/* Phase 29.2: light theme overrides */
.fleet-dash.fleet-dash--light {
  --bg: #f4f6fb;
  --bg-2: #ffffff;
  --panel: #ffffff;
  --panel-2: #f1f4fa;
  --line: #e2e6f0;
  --line-2: #cdd3e1;
  --text: #0f172a;
  --muted: #6b7280;
  --muted-2: #94a3b8;
  --accent: #2563eb;
  --accent-2: #7c3aed;
  --ok: #059669;
  --warn: #d97706;
  --alert: #dc2626;
  --info: #0284c7;
  background: radial-gradient(1200px 600px at 80% -10%, rgba(37,99,235,.05), transparent 60%),
              radial-gradient(900px 500px at -10% 110%, rgba(124,58,237,.05), transparent 60%),
              var(--bg);
}

.fleet-dash.fleet-dash--light .fleet-kpi {
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06);
}

.fleet-dash.fleet-dash--light .fleet-btn--primary {
  background: linear-gradient(180deg, #3b82f6, #2563eb);
  border-color: #1d4ed8;
  color: #fff;
  box-shadow: 0 8px 22px -10px rgba(37,99,235,.4);
}

.fleet-dash.fleet-dash--light .fleet-kpi__bar {
  background: rgba(15, 23, 42, .06);
}

*, *::before, *::after { box-sizing: border-box; }

/* ─── Topbar ─── */
.fleet-topbar {
  display: flex;
  align-items: center;
  gap: 18px;
  justify-content: space-between;
  margin-bottom: 22px;
  flex-wrap: wrap;
  border-bottom: 2px solid var(--org-accent, var(--line));
  padding-bottom: 18px;
}

.fleet-crumbs {
  color: var(--muted);
  font-size: 13px;
  white-space: nowrap;
}

.fleet-crumbs__sep { opacity: .5; margin: 0 4px; }
.fleet-crumbs b { color: var(--text); font-weight: 600; }

.fleet-search {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--panel);
  border: 1px solid var(--line);
  padding: 8px 12px;
  border-radius: 10px;
  flex: 1;
  max-width: 380px;
}

.fleet-search svg { color: var(--muted); flex-shrink: 0; }

.fleet-search__input {
  background: transparent;
  border: 0;
  outline: 0;
  color: var(--text);
  width: 100%;
  font-size: 13px;
  font-family: inherit;
}

.fleet-search__input::placeholder { color: var(--muted); }

.fleet-topbar__actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.fleet-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 9px 14px;
  border-radius: 10px;
  border: 1px solid var(--line-2);
  background: var(--panel);
  color: var(--text);
  font-weight: 600;
  font-size: 13px;
  cursor: pointer;
  transition: background .12s;
  font-family: inherit;
}

.fleet-btn:hover { background: var(--panel-2); }

.fleet-btn--primary {
  background: linear-gradient(180deg, #5a96ff, #4a85f0);
  border-color: #3a74dc;
  color: #fff;
  box-shadow: 0 8px 22px -10px rgba(106,166,255,.6);
}

.fleet-btn--primary:hover { background: linear-gradient(180deg, #6aa6ff, #5a96ff); }

/* ─── KPIs ─── */
.fleet-kpis {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 14px;
  margin-bottom: 22px;
}

.fleet-kpi {
  background: linear-gradient(180deg, var(--panel), var(--bg-2));
  border: 1px solid var(--line);
  border-left: 4px solid var(--org-accent, transparent);
  border-radius: 14px;
  padding: 16px 16px 14px;
  position: relative;
  overflow: hidden;
}

.fleet-kpi__label {
  color: var(--muted);
  font-size: 12px;
  letter-spacing: .3px;
  text-transform: uppercase;
  font-weight: 600;
}

.fleet-kpi__value {
  font-size: 26px;
  font-weight: 800;
  margin-top: 6px;
  letter-spacing: -.4px;
  color: var(--text);
}

.fleet-kpi__sub {
  margin-top: 4px;
  font-size: 12px;
  color: var(--muted);
}

.fleet-kpi__trend {
  position: absolute;
  top: 14px;
  right: 14px;
  font-size: 12px;
  padding: 3px 8px;
  border-radius: 999px;
  font-weight: 600;
}

.fleet-kpi__trend--ok { background: rgba(34,201,151,.12); color: var(--ok); }
.fleet-kpi__trend--warn { background: rgba(246,179,74,.12); color: var(--warn); }
.fleet-kpi__trend--alert { background: rgba(255,91,106,.12); color: var(--alert); }

.fleet-kpi__bar {
  height: 6px;
  border-radius: 999px;
  background: rgba(255,255,255,.05);
  margin-top: 12px;
  overflow: hidden;
}

.fleet-kpi__bar i {
  display: block;
  height: 100%;
  border-radius: 999px;
  transition: width .4s ease;
}

/* ─── Two-column ─── */
.fleet-two-col {
  display: grid;
  grid-template-columns: 1.2fr 1fr;
  gap: 16px;
  margin-bottom: 22px;
}

.fleet-panel {
  background: linear-gradient(180deg, var(--panel), var(--bg-2));
  border: 1px solid var(--line);
  border-radius: 16px;
  padding: 18px;
}

.fleet-panel__title {
  margin: 0 0 14px;
  font-size: 14px;
  letter-spacing: .2px;
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text);
  font-weight: 600;
}

.fleet-panel__title small {
  color: var(--muted);
  font-weight: 500;
  font-size: 12px;
  margin-left: auto;
}

/* ─── Geography — tile grid ─────────────────────────────────────────────── */
.fleet-reg-tiles {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
}
@media (min-width: 768px) {
  .fleet-reg-tiles { grid-template-columns: repeat(3, 1fr); }
}
@media (min-width: 1100px) {
  .fleet-reg-tiles { grid-template-columns: repeat(4, 1fr); }
}

.fleet-reg-tile {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  padding: 12px 10px 10px;
  border-radius: 10px;
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgba(var(--v-theme-on-surface), 0.10);
  cursor: pointer;
  transition: border-color 0.18s, box-shadow 0.18s, transform 0.12s;
  min-height: 90px;
  user-select: none;
}
.fleet-reg-tile:hover {
  border-color: rgba(var(--v-theme-primary, 106 166 255), 0.55);
  box-shadow: 0 4px 14px rgba(var(--v-theme-primary, 106 166 255), 0.18);
  transform: translateY(-2px);
}
.fleet-reg-tile--active {
  border-color: rgb(var(--v-theme-primary, 106 166 255));
  box-shadow: 0 0 0 2px rgba(var(--v-theme-primary, 106 166 255), 0.35);
}

.fleet-reg-tile__nm {
  font-size: 11px;
  font-weight: 500;
  line-height: 1.2;
  color: rgba(var(--v-theme-on-surface), 0.75);
  text-align: center;
  width: 100%;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.fleet-reg-tile__cnt {
  font-size: 30px;
  font-weight: 700;
  line-height: 1;
  color: rgb(var(--v-theme-on-surface));
  letter-spacing: -1px;
}

.fleet-reg-tile__dots {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 3px;
  min-height: 14px;
  width: 100%;
}

.fleet-reg-tile__dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.fleet-reg-tile__dot--working { background: #4caf50; }
.fleet-reg-tile__dot--repair  { background: #ff9800; }
.fleet-reg-tile__dot--broken  { background: #f44336; }
.fleet-reg-tile__dot--other   { background: #9e9e9e; }

.fleet-reg-tile__dot-more {
  font-size: 10px;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), 0.55);
  line-height: 1;
}

.fleet-reg-tiles__more {
  display: flex;
  justify-content: center;
  margin-top: 10px;
}

/* Feed */
.fleet-feed {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 260px;
  overflow-y: auto;
}

.fleet-feed::-webkit-scrollbar { width: 6px; }
.fleet-feed::-webkit-scrollbar-thumb { background: var(--line-2); border-radius: 3px; }

.fleet-feed__item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: rgba(255,255,255,.02);
}

.fleet-feed__ic {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 30px;
  font-weight: 700;
  font-size: 14px;
}

.fleet-feed__ic--ok { background: rgba(34,201,151,.12); color: var(--ok); }
.fleet-feed__ic--warn { background: rgba(246,179,74,.12); color: var(--warn); }
.fleet-feed__ic--alert { background: rgba(255,91,106,.12); color: var(--alert); }
.fleet-feed__ic--info { background: rgba(93,208,255,.12); color: var(--info); }

.fleet-feed__body { font-size: 13px; line-height: 1.4; color: var(--text); }

.fleet-feed__body b { font-weight: 700; }

.fleet-feed__body small {
  display: block;
  color: var(--muted);
  margin-top: 3px;
  font-size: 11.5px;
}

/* ─── Filters / chips ─── */
.fleet-filters {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.fleet-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 7px 12px;
  border: 1px solid var(--line-2);
  border-radius: 999px;
  background: var(--panel);
  color: var(--muted);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: color .12s, border-color .12s, background .12s;
  font-family: inherit;
}

.fleet-chip:hover { color: var(--text); }

.fleet-chip--active {
  background: rgba(106,166,255,.12);
  border-color: rgba(106,166,255,.4);
  color: #cfe1ff;
}

.fleet-chip__count { color: var(--muted); font-weight: 600; }
.fleet-chip--active .fleet-chip__count { color: rgba(207,225,255,.6); }

.fleet-chip__dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  display: inline-block;
}

.fleet-chip__dot--ok { background: var(--ok); }
.fleet-chip__dot--warn { background: var(--warn); }
.fleet-chip__dot--alert { background: var(--alert); }
.fleet-chip__dot--info { background: var(--info); }
.fleet-chip__dot--muted { background: #6c7388; }

.fleet-filters__spacer { flex: 1; }

.fleet-view-toggle {
  display: flex;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 10px;
  overflow: hidden;
}

.fleet-view-toggle button {
  background: transparent;
  border: 0;
  color: var(--muted);
  padding: 8px 12px;
  cursor: pointer;
  font-weight: 600;
  font-size: 12px;
  transition: background .12s, color .12s;
  font-family: inherit;
}

.fleet-view-toggle button.active {
  background: var(--panel-2);
  color: var(--text);
}

/* ─── Cards grid ─── */
.fleet-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 16px;
  position: relative;
}

.fleet-grid--compact { margin-top: 12px; }

/* ─── Table ─── */
.fleet-table-card {
  background: var(--panel) !important;
  border: 1px solid var(--line) !important;
  border-radius: 14px !important;
}

.fleet-table :deep(th) { font-size: 12px !important; }
.fleet-table :deep(td) { font-size: 12px !important; }
.fleet-table :deep(tr) { cursor: pointer; }

.fleet-state-chip {
  display: inline-flex;
  align-items: center;
  padding: 3px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
}

.fleet-state-chip--working { background: rgba(34,201,151,.12); color: var(--ok); }
.fleet-state-chip--in_repair { background: rgba(246,179,74,.12); color: var(--warn); }
.fleet-state-chip--broken,
.fleet-state-chip--needs_repair { background: rgba(255,91,106,.12); color: var(--alert); }
.fleet-state-chip--destroyed,
.fleet-state-chip--utilized { background: rgba(255,255,255,.06); color: var(--muted); }

/* ─── Region groups view ─── */
.fleet-region-group {
  margin-bottom: 28px;
}

.fleet-region-group__header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--line);
}

.fleet-region-group__name {
  font-weight: 700;
  font-size: 15px;
  color: var(--text);
}

.fleet-region-group__count {
  font-size: 12px;
  color: var(--muted);
  background: rgba(255,255,255,.04);
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid var(--line);
}

/* ─── Misc ─── */
.fleet-empty {
  color: var(--muted);
  font-size: 13px;
  padding: 20px 0;
  text-align: center;
}

.fleet-empty--feed {
  padding: 12px;
  font-style: italic;
}

.fleet-empty--full {
  grid-column: 1 / -1;
  padding: 40px;
}

.fleet-loading-overlay {
  grid-column: 1 / -1;
  display: flex;
  justify-content: center;
  padding: 40px;
}

.text-red { color: var(--alert); }

.clickable-rows :deep(tr) { cursor: pointer; }
.clickable-rows :deep(tr:hover td) { background: rgba(106,166,255,.04); }

/* ─── Filter bar ─── */
.fleet-filterbar {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 18px;
  flex-wrap: wrap;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 14px 16px;
}

.fleet-filterbar__item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 160px;
}

.fleet-filterbar__label {
  font-size: 11px;
  font-weight: 600;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: .3px;
}

.fleet-filterbar__select {
  background: var(--bg-2);
  border: 1px solid var(--line-2);
  border-radius: 8px;
  color: var(--text);
  padding: 6px 10px;
  font-size: 13px;
  font-family: inherit;
  cursor: pointer;
  min-width: 160px;
}

.fleet-filterbar__select option { background: var(--panel); }

.fleet-filterbar__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.fleet-filterbar__chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: 999px;
  background: rgba(106,166,255,.14);
  border: 1px solid rgba(106,166,255,.3);
  color: #cfe1ff;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: background .1s;
}

.fleet-filterbar__chip:hover { background: rgba(255,91,106,.2); border-color: rgba(255,91,106,.4); color: #ffaab2; }

/* ─── Clickable KPI & region ─── */
.fleet-kpi--clickable { cursor: pointer; transition: border-color .14s, transform .14s; }
.fleet-kpi--clickable:hover { border-color: rgba(106,166,255,.4); transform: translateY(-1px); }

/* ─── Fine Leaders section ─── */
.fleet-fine-leaders-section {
  margin-top: 20px;
  max-width: 520px;
}

/* ─── Responsive ─── */
@media (max-width: 1100px) {
  .fleet-kpis { grid-template-columns: repeat(2, 1fr); }
  .fleet-two-col { grid-template-columns: 1fr; }
}

@media (max-width: 640px) {
  .fleet-topbar { gap: 10px; }
  .fleet-search { max-width: 100%; }
  .fleet-kpis { grid-template-columns: 1fr 1fr; }
  .fleet-fine-leaders-section { max-width: 100%; }
}
</style>
