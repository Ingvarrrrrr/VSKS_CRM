<template>
  <div class="regions-view" :class="{ 'regions-view--light': !isDark }">

    <!-- ── Topbar ── -->
    <div class="rv-topbar">
      <div>
        <div class="rv-crumbs">
          <router-link to="/fleet">Автопарк</router-link>
          <span class="rv-crumbs__sep">/</span>
          <b>Регионы и филиалы</b>
        </div>
        <h1 class="rv-h1">География парка</h1>
        <p class="rv-lead">
          Распределение
          <b>{{ totalVehicles }}</b> единиц техники по
          <b>{{ orgs.length }}</b> филиалам и регионам · клик по филиалу — его машины и ответственные
        </p>
      </div>
    </div>

    <!-- ── KPI strip ── -->
    <div class="rv-kpi-row">
      <KpiCard label="Всего ТС" :value="totalVehicles" variant="default" />
      <KpiCard label="Филиалов" :value="orgs.length" variant="info" />
      <KpiCard label="В работе" :value="totalWorking" variant="ok" />
      <KpiCard label="В ремонте" :value="totalRepair" variant="warn" />
      <KpiCard label="Сломано" :value="totalBroken" variant="alert" />
    </div>

    <!-- ── Map + Top list ── -->
    <section class="rv-map-row">
      <!-- Map -->
      <div class="rv-panel rv-map-box">
        <div class="rv-panel__head">
          <span>Карта филиалов</span>
          <small>размер кружка ∝ количеству ТС</small>
        </div>
        <div v-if="loadingOrgs" class="rv-loading">
          <div class="rv-spinner"></div>
        </div>
        <RussiaMapSvg
          v-else
          :pins="mapPins"
          :connections="mapConnections"
          @pin-click="onPinClick"
        />
      </div>

      <!-- Top-8 orgs list -->
      <div class="rv-panel rv-top-list">
        <div class="rv-panel__head">
          <span>Топ филиалов</span>
          <small>по количеству ТС</small>
        </div>
        <div v-if="loadingOrgs" class="rv-loading">
          <div class="rv-spinner"></div>
        </div>
        <template v-else>
          <div
            v-for="(org, idx) in topOrgs"
            :key="org.id"
            class="rv-reg-row"
            @click="goToOrg(org.id)"
          >
            <div class="rv-reg-row__ic" :style="{ background: orgBadgeBg(org, idx), color: orgBadgeColor(org, idx) }">
              {{ orgAbbr(org.name) }}
            </div>
            <div class="rv-reg-row__info">
              <div class="rv-reg-row__nm">{{ org.name }}</div>
              <div class="rv-reg-row__ds">{{ org.region || 'регион не указан' }}</div>
            </div>
            <div class="rv-reg-row__cnt">
              {{ orgVehicleCount(org) }}
              <small>ТС</small>
            </div>
          </div>
          <div v-if="!topOrgs.length" class="rv-empty">Нет данных</div>
        </template>
      </div>
    </section>

    <!-- ── Region cards grid ── -->
    <h2 class="rv-section-title">
      Карточки филиалов
      <span class="rv-section-title__sub">— основные данные, ответственные, состояние парка</span>
    </h2>
    <section class="rv-cards-grid">
      <div v-if="loadingOrgs" class="rv-loading" style="grid-column:1/-1">
        <div class="rv-spinner"></div>
      </div>
      <article
        v-else
        v-for="org in sortedOrgs"
        :key="org.id"
        class="rv-card"
        :class="cardColorClass(org)"
      >
        <div class="rv-card__head">
          <div class="rv-card__flag" :class="cardColorClass(org)">
            {{ orgAbbr(org.name) }}
          </div>
          <div class="rv-card__title">
            <div class="rv-card__nm">{{ org.name }}</div>
            <div class="rv-card__ds">{{ org.region || 'регион не указан' }}</div>
          </div>
          <div class="rv-card__big">
            {{ orgVehicleCount(org) }}
            <small>единиц</small>
          </div>
        </div>

        <!-- Status chips -->
        <div class="rv-card__chips">
          <span class="rv-chip rv-chip--ok">
            {{ orgByState(org, 'working') }} в работе
          </span>
          <span class="rv-chip rv-chip--warn">
            {{ orgByState(org, 'in_repair') + orgByState(org, 'needs_repair') }} в ремонте
          </span>
          <span class="rv-chip rv-chip--alert">
            {{ orgByState(org, 'broken') }} сломано
          </span>
        </div>

        <!-- Head avatar + details button -->
        <div class="rv-card__footer">
          <GradientAvatar
            v-if="org.head_user_name"
            :fullName="org.head_user_name"
            size="sm"
          />
          <div v-if="org.head_user_name" class="rv-card__head-name">
            <div class="rv-card__head-nm">{{ org.head_user_name }}</div>
            <div class="rv-card__head-ro">ст. ответственный</div>
          </div>
          <button class="rv-btn rv-btn--sm" style="margin-left:auto" @click.stop="goToOrg(org.id)">
            Подробнее →
          </button>
        </div>
      </article>
    </section>

    <!-- ── Transfer log ── -->
    <section class="rv-panel rv-transfers" style="margin-top:22px">
      <div class="rv-panel__head">
        <span>Журнал передач между филиалами</span>
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
          <LicensePlate :modelValue="tx.plate" size="sm" />
          <div class="rv-tx__from">
            <div class="rv-tx__nm">{{ tx.from_org_name || tx.from_assigned_text || '—' }}</div>
            <div class="rv-tx__ds">{{ tx.from_type || 'филиал' }}</div>
          </div>
          <div class="rv-tx__arr">→</div>
          <div class="rv-tx__to">
            <div class="rv-tx__nm">{{ tx.to_org_name || tx.to_assigned_text || '—' }}</div>
            <div class="rv-tx__ds">{{ tx.to_type || 'филиал' }}</div>
          </div>
          <div class="rv-tx__detail">
            <span>{{ tx.brand_model || '' }}</span>
            <span v-if="tx.basis" class="rv-tx__basis"> · {{ tx.basis }}</span>
          </div>
          <div class="rv-tx__when">{{ formatDate(tx.changed_at) }}</div>
        </div>
      </div>
    </section>

    <!-- ── Pin popup ── -->
    <teleport to="body">
      <transition name="rv-popup-fade">
        <div v-if="selectedPin" class="rv-popup-overlay" @click.self="selectedPin = null">
          <div class="rv-popup" :class="{ 'rv-popup--light': !isDark }">
            <div class="rv-popup__head">
              <div class="rv-popup__abbr" :style="{ background: selectedPin.color }">{{ orgAbbr(selectedPin.name || '') }}</div>
              <div>
                <div class="rv-popup__nm">{{ selectedPin.name }}</div>
                <div class="rv-popup__sub">{{ selectedPin.sub }}</div>
              </div>
              <button class="rv-popup__close" @click="selectedPin = null">✕</button>
            </div>
            <div class="rv-popup__body">
              <div class="rv-popup__stat">
                <span class="rv-popup__stat-l">ТС всего</span>
                <span class="rv-popup__stat-v">{{ selectedPin.count }}</span>
              </div>
              <div v-if="selectedPinOrg">
                <div class="rv-popup__stat">
                  <span class="rv-popup__stat-l">Регион</span>
                  <span class="rv-popup__stat-v">{{ selectedPinOrg.region || '—' }}</span>
                </div>
                <div v-if="selectedPinOrg.head_user_name" class="rv-popup__stat">
                  <span class="rv-popup__stat-l">Ответственный</span>
                  <span class="rv-popup__stat-v">{{ selectedPinOrg.head_user_name }}</span>
                </div>
              </div>
            </div>
            <div class="rv-popup__footer">
              <button class="rv-btn rv-btn--primary" @click="goToOrg(selectedPinOrgId)">
                Перейти к филиалу →
              </button>
            </div>
          </div>
        </div>
      </transition>
    </teleport>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useTheme } from 'vuetify'
import { apiFetch } from '@/api'

import RussiaMapSvg from '@/components/fleet/RussiaMapSvg.vue'
import { type MapPin, type MapConnection, DEFAULT_PINS } from '@/components/fleet/russiaMapPins'
import KpiCard from '@/components/fleet/KpiCard.vue'
import GradientAvatar from '@/components/fleet/GradientAvatar.vue'
import LicensePlate from '@/components/vehicles/LicensePlate.vue'

// ─── Theme ───────────────────────────────────────────────────────────────────

const theme  = useTheme()
const isDark = computed(() => theme.global.current.value.dark)
const router = useRouter()

// ─── Types ───────────────────────────────────────────────────────────────────

interface OrgFull {
  id: number
  name: string
  region: string | null
  lat: number | null
  lon: number | null
  color: string | null
  head_user_id: number | null
  head_user_name?: string | null
}

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
  from_type?: string | null
  to_type?: string | null
  basis: string | null
  doc_number: string | null
  changed_at: string
  changed_by_user_id: number | null
}

// ─── State ───────────────────────────────────────────────────────────────────

const orgs              = ref<OrgFull[]>([])
const regionData        = ref<RegionItem[]>([])
const transfers         = ref<TransferRow[]>([])
const loadingOrgs       = ref(false)
const loadingTransfers  = ref(false)
const selectedPin       = ref<MapPin | null>(null)

// ─── Computed helpers ────────────────────────────────────────────────────────

// Map org id → regionData item by matching name/shtab_label
function regionForOrg(org: OrgFull): RegionItem | undefined {
  return regionData.value.find(r =>
    r.shtab_label === org.name ||
    r.region === org.name ||
    (org.region && r.region === org.region)
  )
}

function orgVehicleCount(org: OrgFull): number {
  return regionForOrg(org)?.count ?? 0
}

function orgByState(org: OrgFull, state: string): number {
  return regionForOrg(org)?.by_state?.[state] ?? 0
}

const sortedOrgs = computed(() =>
  [...orgs.value].sort((a, b) => orgVehicleCount(b) - orgVehicleCount(a))
)

const topOrgs = computed(() => sortedOrgs.value.slice(0, 8))

const totalVehicles = computed(() => regionData.value.reduce((s, r) => s + r.count, 0))
const totalWorking  = computed(() => regionData.value.reduce((s, r) => s + (r.by_state?.working || 0), 0))
const totalRepair   = computed(() => regionData.value.reduce((s, r) => s + (r.by_state?.in_repair || 0) + (r.by_state?.needs_repair || 0), 0))
const totalBroken   = computed(() => regionData.value.reduce((s, r) => s + (r.by_state?.broken || 0), 0))

// ─── Map pins ────────────────────────────────────────────────────────────────

// Russia bounding box for lat/lon → SVG coordinate mapping
// SVG viewBox: 0 0 600 360
// Russia approx: lon 27..190, lat 70..42 (top-left = west-north)
const LON_MIN = 27, LON_MAX = 190
const LAT_MIN = 42, LAT_MAX = 72

function lonToX(lon: number): number {
  return Math.round(((lon - LON_MIN) / (LON_MAX - LON_MIN)) * 560 + 20)
}

function latToY(lat: number): number {
  // Lat increases upward, SVG Y increases downward
  return Math.round(((LAT_MAX - lat) / (LAT_MAX - LAT_MIN)) * 300 + 30)
}

const PIN_MIN_R = 5
const PIN_MAX_R = 22

const maxOrgCount = computed(() => Math.max(...orgs.value.map(o => orgVehicleCount(o)), 1))

function pinRadius(count: number): number {
  const pct = count / maxOrgCount.value
  return Math.round(PIN_MIN_R + pct * (PIN_MAX_R - PIN_MIN_R))
}

const ORG_COLORS = ['#6aa6ff', '#f6b34a', '#22c997', '#8b5cf6', '#5dd0ff', '#ff5b6a']

function pinColor(org: OrgFull, idx: number): string {
  if (org.color) return org.color
  return ORG_COLORS[idx % ORG_COLORS.length]
}

const mapPins = computed<MapPin[]>(() => {
  const geoOrgs = orgs.value.filter(o => o.lat != null && o.lon != null)
  if (!geoOrgs.length) return DEFAULT_PINS

  return geoOrgs.map((org, idx) => {
    const count = orgVehicleCount(org)
    return {
      id:     org.id,
      name:   org.name,
      sub:    `${count} ТС`,
      x:      lonToX(org.lon!),
      y:      latToY(org.lat!),
      radius: pinRadius(count),
      count,
      color:  pinColor(org, idx),
    }
  })
})

// Connections: recent transfers draw lines between orgs
const mapConnections = computed<MapConnection[]>(() => {
  if (!transfers.value.length || mapPins.value === DEFAULT_PINS) return []
  const pinMap = new Map(mapPins.value.map(p => [p.id as number, p]))
  const seen   = new Set<string>()
  const lines: MapConnection[] = []

  for (const tx of transfers.value.slice(0, 15)) {
    const from = tx.from_owner_org_id ? pinMap.get(tx.from_owner_org_id) : null
    const to   = tx.to_owner_org_id   ? pinMap.get(tx.to_owner_org_id)   : null
    if (!from || !to) continue
    const key = [from.id, to.id].sort().join('-')
    if (seen.has(key)) continue
    seen.add(key)
    lines.push({ from: { x: from.x, y: from.y }, to: { x: to.x, y: to.y } })
  }
  return lines
})

// ─── Pin click → popup ───────────────────────────────────────────────────────

const selectedPinOrg = computed(() =>
  selectedPin.value ? orgs.value.find(o => o.id === selectedPin.value?.id) ?? null : null
)

const selectedPinOrgId = computed(() =>
  (selectedPin.value?.id as number | null) ?? null
)

function onPinClick(pin: MapPin) {
  selectedPin.value = pin
}

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
type CardColor = typeof CARD_COLORS[number]

function orgAbbr(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean)
  if (words.length === 1) return words[0].slice(0, 3).toUpperCase()
  return words.slice(0, 3).map(w => w[0]).join('').toUpperCase()
}

function orgBadgeBg(org: OrgFull, idx: number): string {
  return BADGE_PALETTES[idx % BADGE_PALETTES.length].bg
}

function orgBadgeColor(org: OrgFull, idx: number): string {
  return BADGE_PALETTES[idx % BADGE_PALETTES.length].color
}

function cardColorClass(org: OrgFull): string {
  const idx = sortedOrgs.value.findIndex(o => o.id === org.id)
  return `rv-card--${CARD_COLORS[idx % CARD_COLORS.length]}`
}

// ─── Navigation ──────────────────────────────────────────────────────────────

function goToOrg(id: number | null) {
  if (!id) return
  selectedPin.value = null
  router.push({ path: '/fleet/vehicles', query: { owner_org_id: id } })
}

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

async function fetchOrgs() {
  loadingOrgs.value = true
  try {
    const [orgData, regionResp] = await Promise.all([
      apiFetch<{ items: OrgFull[] }>('/organizations/?limit=500'),
      apiFetch<{ items: RegionItem[]; mock_demo?: boolean }>('/vehicles-dashboard/by-region'),
    ])
    orgs.value       = Array.isArray(orgData.items) ? orgData.items : []
    regionData.value = Array.isArray(regionResp.items) ? regionResp.items : []
  } catch (e) {
    console.error('[FleetRegions] fetchOrgs', e)
  } finally {
    loadingOrgs.value = false
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
  fetchOrgs()
  fetchTransfers()
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

.rv-reg-row__nm { font-weight: 700; font-size: 13.5px; }
.rv-reg-row__ds { color: var(--rv-muted); font-size: 11.5px; margin-top: 2px; }

.rv-reg-row__cnt {
  text-align: right;
  font-weight: 800;
  font-size: 18px;
  letter-spacing: -0.3px;
  font-family: 'JetBrains Mono', monospace;
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

.rv-card__head {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  margin-bottom: 14px;
  position: relative;
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

.rv-card__title { flex: 1; }
.rv-card__nm { font-weight: 800; font-size: 17px; }
.rv-card__ds { color: var(--rv-muted); font-size: 12.5px; margin-top: 2px; }

.rv-card__big {
  position: absolute;
  top: 0;
  right: 0;
  font-size: 32px;
  font-weight: 800;
  letter-spacing: -0.6px;
  color: var(--rv-text);
  line-height: 1;
  font-family: 'JetBrains Mono', monospace;
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
}
.rv-popup--light { background: #fff; border-color: #e2e6f0; }

.rv-popup__head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
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

.rv-popup__body { display: grid; gap: 8px; margin-bottom: 16px; }

.rv-popup__stat {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  border-radius: 10px;
  background: rgba(255,255,255,.03);
  border: 1px solid var(--rv-line);
}
.rv-popup--light .rv-popup__stat { background: #f4f6fb; border-color: #e2e6f0; }

.rv-popup__stat-l { color: var(--rv-muted); font-size: 12px; }
.rv-popup__stat-v { font-weight: 700; font-size: 13px; }

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
