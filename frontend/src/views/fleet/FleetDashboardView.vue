<template>
  <div class="fleet-dash" :class="isDark ? 'fleet-dash--dark' : 'fleet-dash--light'">

    <!-- Topbar -->
    <div class="fleet-dash__topbar">
      <div class="fleet-dash__crumbs">
        <router-link to="/fleet" class="fleet-dash__crumb-root">Автопарк</router-link>
        <span class="fleet-dash__crumb-sep">/</span>
        <span class="fleet-dash__crumb-active">Дашборд</span>
      </div>
      <div class="fleet-dash__actions">
        <button class="fd-btn" @click="exportXlsx">
          <v-icon size="15" icon="mdi-file-excel-outline" />
          Экспорт XLSX
        </button>
        <button class="fd-btn" @click="goWaybill">
          <v-icon size="15" icon="mdi-file-document-outline" />
          Путевой лист
        </button>
        <button class="fd-btn fd-btn--primary" @click="addVehicle">
          <v-icon size="15" icon="mdi-plus" />
          Добавить ТС
        </button>
      </div>
    </div>

    <!-- KPI row -->
    <div class="fleet-dash__kpis">
      <KpiCard
        label="Всего в реестре"
        :value="kpiLoading ? '…' : String(kpi.total)"
        :sub="kpiLoading ? '' : 'авто, спецтехника, прицепы'"
        :bar-pct="100"
        variant="default"
        :clickable="true"
        :active="selectedFilter === 'all'"
        @click="filterAndScroll('all')"
      />
      <KpiCard
        label="В рабочем"
        :value="kpiLoading ? '…' : String(kpi.working)"
        :sub="kpiLoading ? '' : workingPct + '% парка'"
        :trend="kpiLoading ? undefined : '+' + kpi.working_delta + ' за неделю'"
        trend-type="ok"
        :bar-pct="workingPct"
        variant="ok"
        :clickable="true"
        :active="selectedFilter === 'working'"
        @click="filterAndScroll('working')"
      />
      <KpiCard
        label="В ремонте"
        :value="kpiLoading ? '…' : String(kpi.in_repair)"
        :sub="kpiLoading ? '' : repairPct + '% парка'"
        :bar-pct="repairPct"
        variant="warn"
        :clickable="true"
        :active="selectedFilter === 'in_repair'"
        @click="filterAndScroll('in_repair')"
      />
      <KpiCard
        label="Не на ходу"
        :value="kpiLoading ? '…' : String(kpi.broken)"
        :sub="kpiLoading ? '' : brokenPct + '% парка'"
        :bar-pct="brokenPct"
        variant="alert"
        :clickable="true"
        :active="selectedFilter === 'broken'"
        @click="filterAndScroll('broken')"
      />
      <KpiCard
        label="Документы истекают"
        :value="kpiLoading ? '…' : String(kpi.docs_expiring)"
        :sub="kpiLoading ? '' : 'в течение 30 дней'"
        :bar-pct="null"
        variant="warn"
        :clickable="true"
        :active="selectedFilter === 'docs_expiring'"
        @click="filterAndScroll('docs_expiring')"
      />
    </div>

    <!-- Two columns: Geography + Fines -->
    <div class="fleet-dash__two-col">

      <!-- LEFT: Geography stacked bars -->
      <div class="fd-panel">
        <div class="fd-panel__head">
          <span class="fd-panel__title">
            <v-icon size="16" icon="mdi-map-marker-multiple-outline" class="mr-1" />
            География эксплуатации
          </span>
          <span class="fd-panel__sub">{{ regions.length }} регионов</span>
        </div>
        <div v-if="regionLoading" class="fd-panel__loading">
          <v-progress-circular indeterminate size="28" color="primary" />
        </div>
        <div v-else-if="regions.length === 0" class="fd-panel__empty">
          Нет данных
        </div>
        <div v-else class="fd-panel__regions">
          <!-- Phase 29.3-R3: верхняя строка «ВСЕГО» — сумма всех регионов (clickable segments, без региона) -->
          <div class="fd-row-total">
            <StackedRegionBar
              region="ВСЕГО"
              shtab=""
              :count="allRegionsTotalCount"
              :max-count="allRegionsTotalCount"
              :working="allRegionsBy.working"
              :in-repair="allRegionsBy.in_repair"
              :broken="allRegionsBy.broken"
              :needs-repair="allRegionsBy.needs_repair"
              :destroyed="allRegionsBy.destroyed"
              :utilized="allRegionsBy.utilized"
              @segment-click="onTotalSegmentClick"
            />
          </div>

          <!-- Top-5 регионов -->
          <div
            v-for="row in regionRows"
            :key="row.region"
            class="fd-region-row"
            :class="{ 'fd-region-row--active': selectedRegion === row.region }"
            @click="selectedRegion = (selectedRegion === row.region ? '' : row.region); selectedFilter = ''"
          >
            <StackedRegionBar
              :region="row.region"
              :shtab="row.shtab_label"
              :count="row.count"
              :max-count="regionMax"
              :working="row.by_state.working || 0"
              :in-repair="row.by_state.in_repair || 0"
              :broken="row.by_state.broken || 0"
              :needs-repair="row.by_state.needs_repair || 0"
              :destroyed="row.by_state.destroyed || 0"
              :utilized="row.by_state.utilized || 0"
              @segment-click="onRegionSegmentClick"
            />
          </div>

          <!-- 6-я строка «Прочее» — collapsible, persistent -->
          <template v-if="otherRegions.length">
            <div
              class="fd-other-header"
              :class="{ 'fd-other-header--expanded': showOtherRegions }"
              @click="showOtherRegions = !showOtherRegions"
            >
              <span class="fd-other-caret">{{ showOtherRegions ? '▼' : '▶' }}</span>
              <StackedRegionBar
                :region="`Прочее (${otherRegions.length})`"
                :shtab="''"
                :count="otherRegionsTotalCount"
                :max-count="regionMax"
                :working="otherRegionsBy.working"
                :in-repair="otherRegionsBy.in_repair"
                :broken="otherRegionsBy.broken"
                :needs-repair="otherRegionsBy.needs_repair"
                :destroyed="otherRegionsBy.destroyed"
                :utilized="otherRegionsBy.utilized"
                style="flex:1"
              />
            </div>

            <div v-show="showOtherRegions" class="fd-other-nested">
              <div
                v-for="row in otherRegions"
                :key="row.region"
                class="fd-region-row"
                :class="{ 'fd-region-row--active': selectedRegion === row.region }"
                @click="selectedRegion = (selectedRegion === row.region ? '' : row.region); selectedFilter = ''"
              >
                <StackedRegionBar
                  :region="row.region"
                  :shtab="row.shtab_label"
                  :count="row.count"
                  :max-count="regionMax"
                  :working="row.by_state.working || 0"
                  :in-repair="row.by_state.in_repair || 0"
                  :broken="row.by_state.broken || 0"
                  :needs-repair="row.by_state.needs_repair || 0"
                  :destroyed="row.by_state.destroyed || 0"
                  :utilized="row.by_state.utilized || 0"
                  @segment-click="onRegionSegmentClick"
                />
              </div>
            </div>
          </template>
        </div>
        <div class="fd-panel__legend">
          <span class="fleg fleg--working">Рабочих</span>
          <span class="fleg fleg--repair">В ремонте</span>
          <span class="fleg fleg--broken">Не на ходу</span>
        </div>
      </div>

      <!-- RIGHT: Fine leaders podium -->
      <div class="fd-panel fd-panel--fines">
        <FineLeadersPodiumWidget @leader-click="onLeaderClick" />
      </div>
    </div>

    <!-- Phase 29.3-R3 (pt9): drill-секция штрафов выбранного водителя -->
    <DriverFinesDrill
      v-if="selectedDriver"
      :driver="selectedDriver"
      @close="selectedDriver = null"
    />

    <!-- Bottom: Vehicle cards grid -->
    <div ref="cardsSection" class="fd-panel fd-panel--cards">
      <div class="fd-panel__head">
        <span class="fd-panel__title">
          <v-icon size="16" icon="mdi-car-multiple" class="mr-1" />
          Карточки ТС
          <span v-if="selectedFilter" class="fd-filter-badge" @click="selectedFilter = ''">
            {{ filterLabel }} &times;
          </span>
          <span v-if="selectedRegion" class="fd-filter-badge fd-filter-badge--region" @click="selectedRegion = ''">
            {{ selectedRegion }} &times;
          </span>
        </span>
        <router-link to="/fleet/vehicles" class="fd-panel__link">
          Все ТС
          <v-icon size="14" icon="mdi-arrow-right" />
        </router-link>
      </div>
      <div v-if="cardsLoading" class="fd-panel__loading">
        <v-progress-circular indeterminate size="28" color="primary" />
      </div>
      <div v-else-if="visibleCards.length === 0" class="fd-panel__empty">
        Нет транспортных средств
      </div>
      <div v-else class="fd-cards-grid">
        <VehicleCard
          v-for="v in visibleCards"
          :key="v.id"
          :vehicle="v"
        />
      </div>
    </div>

    <!-- Footer stat -->
    <div class="fleet-dash__footer">
      <span v-if="!kpiLoading">
        <b>{{ kpi.working }}</b> ТС в работе &nbsp;·&nbsp;
        <b>{{ kpi.total - kpi.working }}</b> в ремонте/неподвижны &nbsp;·&nbsp;
        Обновлено: {{ nowStr }}
      </span>
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useTheme } from 'vuetify'
import { apiFetch } from '@/api'

import KpiCard from '@/components/fleet/KpiCard.vue'
import StackedRegionBar from '@/components/fleet/StackedRegionBar.vue'
import FineLeadersPodiumWidget from '@/components/vehicles/FineLeadersPodiumWidget.vue'
import DriverFinesDrill from '@/components/fleet/DriverFinesDrill.vue'
import VehicleCard from '@/components/vehicles/VehicleCard.vue'

// ─── Types ───────────────────────────────────────────────────────────────────

interface KpiData {
  total: number
  working: number
  in_repair: number
  broken: number
  docs_expiring: number
  working_delta: number
}

interface RegionRow {
  region: string
  count: number
  shtab_label?: string
  by_state: {
    working?: number
    in_repair?: number
    broken?: number
    needs_repair?: number
    destroyed?: number
    utilized?: number
  }
}

// ─── State ───────────────────────────────────────────────────────────────────

const router   = useRouter()
const theme    = useTheme()
const isDark   = computed(() => theme.global.name.value === 'dark')

const kpiLoading    = ref(true)
const regionLoading = ref(true)
const cardsLoading  = ref(true)

const kpi     = ref<KpiData>({ total: 0, working: 0, in_repair: 0, broken: 0, docs_expiring: 0, working_delta: 0 })
const regions = ref<RegionRow[]>([])
const cards   = ref<any[]>([])

const selectedFilter = ref('')
// Phase 29.3-R3 (pt8): region drill on-page
const selectedRegion = ref('')
// Phase 29.3-R3 (pt9): drill штрафов конкретного водителя
const selectedDriver = ref<{ driver_key: string; driver_name: string | null; driver_kind: string } | null>(null)

function onLeaderClick(payload: { key: string; name: string | null; kind: string; id: number | null }) {
  // Dashboard only shows drivers podium (default kind), map to old shape for DriverFinesDrill
  selectedDriver.value = {
    driver_key: payload.key,
    driver_name: payload.name,
    driver_kind: payload.kind,
  }
}
const cardsSection   = ref<HTMLElement | null>(null)
const nowStr = new Date().toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })

// ─── Computed ─────────────────────────────────────────────────────────────────

const workingPct = computed(() =>
  kpi.value.total > 0 ? Math.round((kpi.value.working / kpi.value.total) * 100) : 0
)
const repairPct = computed(() =>
  kpi.value.total > 0 ? Math.round((kpi.value.in_repair / kpi.value.total) * 100) : 0
)
const brokenPct = computed(() =>
  kpi.value.total > 0 ? Math.round((kpi.value.broken / kpi.value.total) * 100) : 0
)

// Phase 29.3-R3: фильтрация регионов с пустым именем (assigned_text=null/empty) —
// они идут в строку «ВСЕГО» / агрегат, но не как отдельная анонимная строка
const regionRowsSorted = computed(() =>
  [...regions.value]
    .filter(r => r.region && r.region.trim().length > 0)
    .sort((a, b) => b.count - a.count)
)

// Phase 29.3-R3: top-5 + 6-я строка «Прочее» (collapsible, persistent — не сворачивается auto)
const REG_TOP_LIMIT = 5
const showOtherRegions = ref(false)

const regionRows = computed(() => regionRowsSorted.value.slice(0, REG_TOP_LIMIT))
const otherRegions = computed(() => regionRowsSorted.value.slice(REG_TOP_LIMIT))
const otherRegionsTotalCount = computed(() => otherRegions.value.reduce((sum, r) => sum + r.count, 0))

// Phase 29.3-R3: первая строка «ВСЕГО» — сумма всех регионов (включая безымянные, для total)
const allRegionsTotalCount = computed(() => regions.value.reduce((sum, r) => sum + r.count, 0))
const allRegionsBy = computed(() => {
  const acc: Record<string, number> = { working: 0, in_repair: 0, broken: 0, needs_repair: 0, destroyed: 0, utilized: 0 }
  for (const r of regions.value) {
    for (const k of Object.keys(acc)) acc[k] += (r.by_state as any)[k] || 0
  }
  return acc
})
const otherRegionsBy = computed(() => {
  const acc: Record<string, number> = { working: 0, in_repair: 0, broken: 0, needs_repair: 0, destroyed: 0, utilized: 0 }
  for (const r of otherRegions.value) {
    for (const k of Object.keys(acc)) acc[k] += (r.by_state as any)[k] || 0
  }
  return acc
})

const regionMax = computed(() =>
  regionRowsSorted.value.length > 0 ? regionRowsSorted.value[0].count : 1
)

const filterLabel = computed(() => {
  const map: Record<string, string> = {
    all: 'Все ТС',
    working: 'В рабочем',
    in_repair: 'В ремонте',
    broken: 'Не на ходу',
    docs_expiring: 'Документы истекают',
  }
  return map[selectedFilter.value] ?? selectedFilter.value
})

// Phase 29.3-R3: фильтр «В ремонте» включает state IN (in_repair, broken, needs_repair)
const STATE_FILTER_MAP: Record<string, string[]> = {
  in_repair: ['in_repair', 'broken', 'needs_repair'],
  broken: ['broken', 'destroyed', 'utilized', 'not_running'],
  working: ['working'],
}

// Phase 29.3-R3 (pt7): «Документы истекают» — id'ы ТС с просрочкой ОСАГО/СТС/ПТС в течение 30 дней
const docsExpiringIds = ref<Set<number>>(new Set())

const visibleCards = computed(() => {
  let list = cards.value as any[]

  // Region filter (drill from geography) — нормализованное сравнение (trim+lower)
  if (selectedRegion.value) {
    const reg = selectedRegion.value.trim().toLowerCase()
    list = list.filter((v: any) => (v.assigned_text || '').trim().toLowerCase() === reg)
  }

  // State / docs_expiring filter
  // Phase 29.3-R3 (Д-1): без drill показываем превью 9 карточек, при drill — все подходящие
  const isDrillActive = !!selectedRegion.value || !!selectedFilter.value
  const previewLimit = isDrillActive ? Infinity : 9

  if (!selectedFilter.value || selectedFilter.value === 'all') {
    return previewLimit === Infinity ? list : list.slice(0, previewLimit as number)
  }
  if (selectedFilter.value === 'docs_expiring') {
    return list.filter((v: any) => docsExpiringIds.value.has(v.vehicle_id))
  }
  const allowed = STATE_FILTER_MAP[selectedFilter.value] || [selectedFilter.value]
  return list.filter((v: any) => allowed.includes(v.state))
})

// ─── Methods ──────────────────────────────────────────────────────────────────

async function loadKpi() {
  kpiLoading.value = true
  try {
    // /kpi возвращает {total_vehicles, fuel_total_cost, repairs_total_cost, total_mileage_km}
    // /filter-counts возвращает {all, working, in_repair, not_running, ...}
    // /maintenance-warning возвращает массив с истекающими доками
    const [kpiData, counts, warnings] = await Promise.all([
      apiFetch<any>('/vehicles-dashboard/kpi').catch(() => ({})),
      apiFetch<any>('/vehicles-dashboard/filter-counts').catch(() => ({})),
      apiFetch<any[]>('/vehicles-dashboard/maintenance-warning').catch(() => []),
    ])
    kpi.value = {
      total: counts.all || kpiData.total_vehicles || 0,
      working: counts.working || 0,
      in_repair: counts.in_repair || 0,
      broken: counts.not_running || 0,
      docs_expiring: Array.isArray(warnings) ? warnings.length : 0,
      working_delta: 0,
    }
    // Phase 29.3-R3 (pt7): сохраняем id'ы ТС с истекающими доками для drill on-page
    if (Array.isArray(warnings)) {
      docsExpiringIds.value = new Set(warnings.map((w: any) => w.vehicle_id).filter(Boolean))
    }
  } catch (e) {
    console.error('[FleetDash] KPI', e)
  } finally {
    kpiLoading.value = false
  }
}

async function loadRegions() {
  regionLoading.value = true
  try {
    // API возвращает { items: [...] } а не плоский массив
    const resp = await apiFetch<{ items: RegionRow[] } | RegionRow[]>('/vehicles-dashboard/by-region')
    regions.value = Array.isArray(resp) ? resp : (resp?.items || [])
  } catch (e) {
    console.error('[FleetDash] Regions', e)
    regions.value = []
  } finally {
    regionLoading.value = false
  }
}

async function loadCards() {
  cardsLoading.value = true
  try {
    // Phase 29.3-R3 (Д-1/Д-5): источник cards = /api/vehicles?limit=500 (полная модель)
    // + frontend dedup по VIN→plate (та же логика что в backend /all-vehicles-summary).
    // Раньше limit=30 терял ТС с id>30; /all-vehicles-summary терял поля
    // (vin/year/color/insurance_until/responsible_name/sts_number и др.).
    const resp = await apiFetch<{ items: any[]; total: number } | any[]>('/vehicles?limit=500')
    const allVehicles: any[] = Array.isArray(resp) ? resp : ((resp as any)?.items || [])

    // Dedup keys: vin (нормализованный) → plate (нормализованный) → id.
    // Приоритет non-working state (in_repair/broken/needs_repair > working > unknown).
    const STATE_RANK: Record<string, number> = {
      broken: 4, destroyed: 4, utilized: 4, needs_repair: 3, in_repair: 3,
      working: 1, unknown: 0, '': 0,
    }
    const rank = (s: any) => STATE_RANK[s || ''] ?? 2
    const norm = (s?: string | null) => (s || '').toString().toUpperCase().replace(/\s+/g, '').trim()
    const dedup = new Map<string, any>()
    for (const v of allVehicles) {
      let k = ''
      if (v.vin && String(v.vin).trim()) k = 'vin:' + norm(v.vin)
      else if (v.plate && String(v.plate).trim()) k = 'plate:' + norm(v.plate)
      else k = `__id_${v.id}`
      const prev = dedup.get(k)
      if (!prev) dedup.set(k, v)
      else {
        const curR = rank(v.state), prevR = rank(prev.state)
        const curHasRegion = !!(v.assigned_text && String(v.assigned_text).trim())
        const prevHasRegion = !!(prev.assigned_text && String(prev.assigned_text).trim())
        if (curR > prevR || (curR === prevR && curHasRegion && !prevHasRegion)) dedup.set(k, v)
      }
    }
    cards.value = Array.from(dedup.values())
  } catch (e) {
    console.error('[FleetDash] Cards', e)
    cards.value = []
  } finally {
    cardsLoading.value = false
  }
}

function filterAndScroll(state: string) {
  // Phase 29.3-R3: убран scroll-zoom на виджеты — пользователь сам решает куда смотреть.
  selectedFilter.value = state
}

// Phase 29.3-R3 (pt8): клик по сегменту региона = drill on-page, не navigate
function onRegionSegmentClick({ region, state }: { region: string; state: string }) {
  selectedRegion.value = (region || '').trim()
  selectedFilter.value = state
}

// Phase 29.3-R3 (pt10): клик по сегменту строки «ВСЕГО» — фильтр по state без региона
function onTotalSegmentClick({ state }: { region: string; state: string }) {
  selectedRegion.value = ''
  selectedFilter.value = state
}

function exportXlsx() {
  router.push('/fleet/vehicles?export=xlsx')
}

function goWaybill() {
  router.push('/fleet/waybills/new')
}

function addVehicle() {
  router.push('/fleet/vehicles/new')
}

// ─── Lifecycle ────────────────────────────────────────────────────────────────

onMounted(() => {
  loadKpi()
  loadRegions()
  loadCards()
})
</script>

<style scoped>
/* ── CSS tokens (dark by default) ─────────────────────────────────────────── */
.fleet-dash {
  --bg:      #0a0d14;
  --bg-2:    #0f131c;
  --panel:   #141823;
  --panel-2: #1a1f2c;
  --line:    #222838;
  --line-2:  #2b3245;
  --text:    #e9edf5;
  --muted:   #8a93a8;
  --muted-2: #5d6478;
  --accent:  #6aa6ff;
  --ok:      #22c997;
  --warn:    #f6b34a;
  --alert:   #ff5b6a;
  --info:    #5dd0ff;

  padding: 24px 28px 64px;
  min-height: 100vh;
  color: var(--text);
  font-family: 'Inter', system-ui, -apple-system, sans-serif;
  font-size: 14px;
}

.fleet-dash--light {
  --bg:      #f5f7fb;
  --bg-2:    #edf0f7;
  --panel:   #ffffff;
  --panel-2: #f1f4fa;
  --line:    #e2e6f0;
  --line-2:  #d0d6e8;
  --text:    #1a1d23;
  --muted:   #6b7280;
  --muted-2: #9ca3af;
}

/* ── Topbar ────────────────────────────────────────────────────────────────── */
.fleet-dash__topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 22px;
  flex-wrap: wrap;
  gap: 12px;
}

.fleet-dash__crumbs {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}
.fleet-dash__crumb-root {
  color: var(--muted);
  text-decoration: none;
  font-weight: 500;
}
.fleet-dash__crumb-root:hover { color: var(--text); }
.fleet-dash__crumb-sep { color: var(--muted-2); }
.fleet-dash__crumb-active { font-weight: 700; color: var(--text); }

.fleet-dash__actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.fd-btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 9px 15px;
  border-radius: 10px;
  border: 1px solid var(--line-2);
  background: var(--panel);
  color: var(--text);
  font-weight: 600;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}
.fd-btn:hover { background: var(--panel-2); }
.fd-btn--primary {
  background: linear-gradient(180deg, #5a96ff, #4a85f0);
  border-color: #3a74dc;
  color: #fff;
  box-shadow: 0 6px 18px -8px rgba(106, 166, 255, 0.55);
}
.fd-btn--primary:hover { filter: brightness(1.08); }

/* ── KPI row ───────────────────────────────────────────────────────────────── */
.fleet-dash__kpis {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 14px;
  margin-bottom: 22px;
}

@media (max-width: 1200px) {
  .fleet-dash__kpis { grid-template-columns: repeat(3, 1fr); }
}
@media (max-width: 768px) {
  .fleet-dash__kpis { grid-template-columns: repeat(2, 1fr); }
}

/* ── Two-col layout ────────────────────────────────────────────────────────── */
.fleet-dash__two-col {
  display: grid;
  grid-template-columns: 1.2fr 1fr;
  gap: 20px;
  margin-bottom: 22px;
}
@media (max-width: 900px) {
  .fleet-dash__two-col { grid-template-columns: 1fr; }
}

/* ── Panel box ─────────────────────────────────────────────────────────────── */
.fd-panel {
  background: linear-gradient(180deg, var(--panel), var(--bg-2));
  border: 1px solid var(--line);
  border-radius: 16px;
  padding: 18px 20px;
}
.fd-panel--fines {
  padding: 0;
  overflow: hidden;
}

.fd-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}
.fd-panel__title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text);
  display: flex;
  align-items: center;
  gap: 6px;
}
.fd-panel__sub {
  font-size: 12px;
  color: var(--muted);
  font-weight: 500;
}
.fd-panel__link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 600;
  color: var(--accent);
  text-decoration: none;
}
.fd-panel__link:hover { opacity: 0.8; }

.fd-panel__loading,
.fd-panel__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 120px;
  color: var(--muted);
  font-size: 13px;
}

/* ── Regions ───────────────────────────────────────────────────────────────── */
.fd-panel__regions {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.fd-panel__legend {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid var(--line);
}

.fleg {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  font-weight: 600;
  color: var(--muted);
}
.fleg::before {
  content: '';
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 3px;
}
.fleg--working::before { background: linear-gradient(90deg, #22c997, #5dd0ff); }
.fleg--repair::before  { background: linear-gradient(90deg, #f6b34a, #ff8a4a); }
.fleg--broken::before  { background: linear-gradient(90deg, #ff5b6a, #ff3b8b); }

/* ── Cards section ─────────────────────────────────────────────────────────── */
.fd-panel--cards {
  margin-bottom: 16px;
}

.fd-filter-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: 8px;
  padding: 2px 10px;
  border-radius: 999px;
  background: rgba(106, 166, 255, 0.15);
  border: 1px solid rgba(106, 166, 255, 0.35);
  color: #cfe1ff;
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.15s;
}
.fd-filter-badge:hover { background: rgba(106, 166, 255, 0.25); }

.fd-cards-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}
@media (max-width: 1100px) {
  .fd-cards-grid { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 680px) {
  .fd-cards-grid { grid-template-columns: 1fr; }
}

/* ── Footer ────────────────────────────────────────────────────────────────── */
.fleet-dash__footer {
  text-align: center;
  font-size: 12px;
  color: var(--muted);
  padding: 10px 0;
}
.fleet-dash__footer b { color: var(--text); font-weight: 700; }

/* Phase 29.3-R3 (pt8): clickable region rows */
.fd-region-row {
  cursor: pointer;
  border-radius: 8px;
  padding: 2px 4px;
  margin: 0 -4px;
  transition: background 0.15s, box-shadow 0.15s;
}
.fd-region-row:hover {
  background: rgba(106, 166, 255, 0.08);
}
.fd-region-row--active {
  background: rgba(106, 166, 255, 0.18);
  box-shadow: inset 3px 0 0 var(--accent, #6aa6ff);
}

.fd-filter-badge--region {
  background: rgba(34, 201, 151, 0.18);
  color: #22c997;
  border: 1px solid rgba(34, 201, 151, 0.3);
}

/* Phase 29.3-R3: верхняя строка «ВСЕГО» */
.fd-row-total {
  padding: 4px 0 8px 0;
  border-bottom: 1px solid rgba(106, 166, 255, 0.18);
  margin-bottom: 4px;
  font-weight: 700;
}
.fd-row-total :deep(.srb-region) {
  font-weight: 700;
  color: var(--text, #e9edf5);
  letter-spacing: 0.4px;
}

/* Phase 29.3-R3: «Прочее» header + nested */
.fd-other-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
  padding: 2px 0;
  cursor: pointer;
  user-select: none;
}
.fd-other-caret {
  display: inline-block;
  width: 14px;
  text-align: center;
  font-size: 11px;
  color: var(--accent, #6aa6ff);
  flex-shrink: 0;
}
.fd-other-header:hover .fd-other-caret { color: #8ab8ff; }
.fd-other-nested {
  margin-left: 22px;
  padding-left: 8px;
  border-left: 2px solid rgba(106, 166, 255, 0.15);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
</style>
