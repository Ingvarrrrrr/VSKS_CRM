<template>
  <v-card class="fine-leaders-widget h-100 d-flex flex-column" elevation="0" rounded="0" style="background:transparent;border:none">
    <!-- Header -->
    <v-card-title class="d-flex align-center ga-2 pb-1 flex-wrap px-5 pt-5">
      <span class="pod-trophy">{{ kindIcon }}</span>
      <span class="text-subtitle-1 font-weight-bold">{{ title || kindDefaultTitle }}</span>
      <v-spacer />
      <!-- Period selector -->
      <v-select
        v-model="selectedPeriod"
        :items="PERIODS"
        item-title="label"
        item-value="days"
        density="compact"
        variant="outlined"
        hide-details
        style="max-width:160px;font-size:12px"
        @update:model-value="fetchLeaders"
      />
    </v-card-title>

    <!-- Loading -->
    <div v-if="loading" class="d-flex justify-center align-center py-10 flex-grow-1">
      <v-progress-circular indeterminate color="warning" size="32" />
    </div>

    <!-- Empty state -->
    <div
      v-else-if="leaders.length === 0"
      class="d-flex flex-column align-center justify-center py-10 text-medium-emphasis flex-grow-1"
    >
      <v-icon icon="mdi-check-circle-outline" color="success" size="44" class="mb-2" />
      <span class="text-body-2">Штрафов пока нет</span>
    </div>

    <!-- Content -->
    <v-card-text v-else class="pa-5 pt-4 d-flex flex-column ga-3 flex-grow-1">

      <!-- Podium: top 3 in 2-1-3 order -->
      <div v-if="top3.length > 0" class="podium-row">

        <!-- 2nd place (left) -->
        <div class="podium-card podium-card--second podium-card--clickable" style="min-height:80px" @click="top3[1] && onLeaderClick(top3[1])">
          <div class="podium-rank podium-rank--second">2</div>
          <div v-if="top3[1]" class="podium-body">
            <LicensePlate v-if="isVehicles" :model-value="displayName(top3[1])" size="sm" class="podium-plate" />
            <div v-else class="podium-name">{{ displayName(top3[1]) }}</div>
            <div v-if="displaySub(top3[1])" class="podium-sub">{{ displaySub(top3[1]) }}</div>
            <div class="podium-fines">{{ top3[1].fines_count }} шт.</div>
            <div class="podium-amount podium-amount--second">{{ fmtRub(top3[1].fines_total) }}</div>
            <span v-if="top3[1].unpaid_count > 0" class="pod-badge pod-badge--unpaid">
              {{ top3[1].unpaid_count }} не оплачено
            </span>
            <span v-else class="pod-badge pod-badge--paid">✓ оплачено</span>
          </div>
          <div v-else class="podium-body podium-body--empty">—</div>
        </div>

        <!-- 1st place (center, tallest) -->
        <div class="podium-card podium-card--first podium-card--clickable" style="min-height:108px" @click="top3[0] && onLeaderClick(top3[0])">
          <div class="podium-rank podium-rank--first">1</div>
          <div class="podium-body">
            <LicensePlate v-if="isVehicles" :model-value="displayName(top3[0])" class="podium-plate" />
            <div v-else class="podium-name podium-name--first">{{ displayName(top3[0]) }}</div>
            <div v-if="displaySub(top3[0])" class="podium-sub">{{ displaySub(top3[0]) }}</div>
            <div class="podium-fines">{{ top3[0].fines_count }} шт.</div>
            <div class="podium-amount podium-amount--first">{{ fmtRub(top3[0].fines_total) }}</div>
            <span v-if="top3[0].unpaid_count > 0" class="pod-badge pod-badge--unpaid">
              {{ top3[0].unpaid_count }} не оплачено
            </span>
            <span v-else class="pod-badge pod-badge--paid">✓ оплачено</span>
          </div>
        </div>

        <!-- 3rd place (right) -->
        <div class="podium-card podium-card--third podium-card--clickable" style="min-height:64px" @click="top3[2] && onLeaderClick(top3[2])">
          <div class="podium-rank podium-rank--third">3</div>
          <div v-if="top3[2]" class="podium-body">
            <LicensePlate v-if="isVehicles" :model-value="displayName(top3[2])" size="sm" class="podium-plate" />
            <div v-else class="podium-name">{{ displayName(top3[2]) }}</div>
            <div v-if="displaySub(top3[2])" class="podium-sub">{{ displaySub(top3[2]) }}</div>
            <div class="podium-fines">{{ top3[2].fines_count }} шт.</div>
            <div class="podium-amount podium-amount--third">{{ fmtRub(top3[2].fines_total) }}</div>
            <span v-if="top3[2].unpaid_count > 0" class="pod-badge pod-badge--unpaid">
              {{ top3[2].unpaid_count }} не оплачено
            </span>
            <span v-else class="pod-badge pod-badge--paid">✓ оплачено</span>
          </div>
          <div v-else class="podium-body podium-body--empty">—</div>
        </div>

      </div>

      <!-- Podium base decoration -->
      <div v-if="top3.length > 0" class="pod-base">
        <div class="pod-base__b pod-base__b--second"></div>
        <div class="pod-base__b pod-base__b--first"></div>
        <div class="pod-base__b pod-base__b--third"></div>
      </div>

      <!-- Rest (4-10) -->
      <div v-if="rest.length > 0" class="others-section">
        <div class="others-title">Остальные</div>
        <div
          v-for="(leader, idx) in rest"
          :key="leaderKey(leader)"
          class="other-row other-row--clickable"
          @click="onLeaderClick(leader)"
        >
          <span class="other-row__num">{{ idx + 4 }}.</span>
          <div class="other-row__av" :style="{ background: avatarGradient(displayName(leader)) }">
            {{ initials(displayName(leader)) }}
          </div>
          <div class="other-row__info">
            <LicensePlate v-if="isVehicles" :model-value="displayName(leader)" size="sm" />
            <div v-else class="other-row__nm">{{ displayName(leader) }}</div>
            <div v-if="displaySub(leader)" class="other-row__sb">{{ displaySub(leader) }}</div>
          </div>
          <span class="other-row__cnt">{{ leader.fines_count }} шт.</span>
          <span class="other-row__sum">{{ fmtRub(leader.fines_total) }}</span>
          <span
            v-if="leader.unpaid_count > 0"
            class="other-row__badge other-row__badge--unpaid"
          >{{ leader.unpaid_count }}</span>
          <span
            v-else
            class="other-row__badge other-row__badge--paid"
          >✓</span>
        </div>
      </div>

    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { apiFetch } from '@/api'
import LicensePlate from '@/components/vehicles/LicensePlate.vue'

// ── Props ─────────────────────────────────────────────────────────────────
const props = withDefaults(defineProps<{
  kind?: 'drivers' | 'vehicles' | 'filials'
  title?: string
}>(), {
  kind: 'drivers',
  title: '',
})

// ── Types ──────────────────────────────────────────────────────────────────

// drivers kind
interface FineLeaderDriver {
  driver_key: string
  driver_name: string | null
  driver_kind: 'user' | 'external' | 'unmatched'
  driver_id: number | null
  fines_count: number
  fines_total: number
  unpaid_count: number
  unpaid_total: number
}

// vehicles / filials kind
interface FineLeaderEntity {
  entity_key: string
  entity_name: string | null
  entity_sub: string | null
  entity_id: number | null
  fines_count: number
  fines_total: number
  unpaid_count: number
  unpaid_total: number
}

type FineLeaderItem = FineLeaderDriver | FineLeaderEntity

// ── Constants ──────────────────────────────────────────────────────────────

const PERIODS = [
  { label: 'Всё время', days: null },
  { label: 'Год', days: 365 },
  { label: '6 мес.', days: 180 },
  { label: 'Месяц', days: 30 },
]

const AVATAR_PALETTES: [string, string][] = [
  ['#6aa6ff', '#8b5cf6'],
  ['#22c997', '#5dd0ff'],
  ['#f6b34a', '#ff8a4a'],
  ['#ff5b6a', '#ff3b8b'],
  ['#8b5cf6', '#5dd0ff'],
]

// ── State ──────────────────────────────────────────────────────────────────

const selectedPeriod = ref<number | null>(null)
const leaders = ref<FineLeaderItem[]>([])
const loading = ref(false)

const emit = defineEmits<{
  (e: 'leader-click', payload: { key: string; name: string | null; kind: string; id: number | null }): void
}>()

// ── Computed ───────────────────────────────────────────────────────────────

const kindIcon = computed(() => {
  if (props.kind === 'vehicles') return '🚗'
  if (props.kind === 'filials') return '🏢'
  return '🏆'
})

const kindDefaultTitle = computed(() => {
  if (props.kind === 'vehicles') return 'Топ ТС по штрафам'
  if (props.kind === 'filials') return 'Топ филиалов по штрафам'
  return 'Рекордсмены по штрафам'
})

const top3 = computed(() => leaders.value.slice(0, 3))
const rest = computed(() => leaders.value.slice(3))
const isVehicles = computed(() => props.kind === 'vehicles')

// ── Helpers ────────────────────────────────────────────────────────────────

function isDriver(item: FineLeaderItem): item is FineLeaderDriver {
  return 'driver_key' in item
}

function displayName(item: FineLeaderItem): string {
  if (isDriver(item)) return item.driver_name || '— Не определён —'
  return (item as FineLeaderEntity).entity_name || '—'
}

function displaySub(item: FineLeaderItem): string | null {
  if (isDriver(item)) return null
  return (item as FineLeaderEntity).entity_sub || null
}

function leaderKey(item: FineLeaderItem): string {
  if (isDriver(item)) return item.driver_key
  return (item as FineLeaderEntity).entity_key
}

function fmtRub(val: number): string {
  return val.toLocaleString('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 })
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (!parts.length) return '?'
  if (parts.length === 1) return parts[0][0].toUpperCase()
  return (parts[0][0] + parts[1][0]).toUpperCase()
}

function avatarGradient(name: string): string {
  const hash = name.split('').reduce((a, c) => a + c.charCodeAt(0), 0)
  const [c1, c2] = AVATAR_PALETTES[hash % AVATAR_PALETTES.length]
  return `linear-gradient(135deg, ${c1}, ${c2})`
}

// ── Navigation ─────────────────────────────────────────────────────────────

// Виджет только сообщает о клике. Что делать дальше (drill на месте или
// навигация-фильтр) решает родитель — слушает @leader-click. Сам виджет
// никуда НЕ перекидывает.
function onLeaderClick(item: FineLeaderItem): void {
  if (props.kind === 'drivers') {
    const d = item as FineLeaderDriver
    emit('leader-click', { key: d.driver_key, name: d.driver_name, kind: d.driver_kind, id: d.driver_id })
    return
  }
  if (props.kind === 'vehicles') {
    const v = item as FineLeaderEntity
    emit('leader-click', { key: v.entity_key, name: v.entity_name, kind: 'vehicle', id: v.entity_id })
    return
  }
  if (props.kind === 'filials') {
    const f = item as FineLeaderEntity
    emit('leader-click', { key: f.entity_key, name: f.entity_name, kind: 'filial', id: f.entity_id })
    return
  }
}

// ── API ────────────────────────────────────────────────────────────────────

async function fetchLeaders(): Promise<void> {
  loading.value = true
  try {
    const params = new URLSearchParams({ kind: props.kind, limit: '10' })
    if (selectedPeriod.value != null) {
      params.set('period_days', String(selectedPeriod.value))
    }
    leaders.value = await apiFetch<FineLeaderItem[]>(`/vehicles-dashboard/fine-leaders?${params}`)
  } catch (e) {
    console.error('[FineLeaders]', e)
    leaders.value = []
  } finally {
    loading.value = false
  }
}

onMounted(fetchLeaders)
</script>

<style scoped>
.fine-leaders-widget {
  min-height: 260px;
}

.pod-trophy {
  font-size: 20px;
  margin-right: 2px;
}

/* Podium layout: 2-1-3 */
.podium-row {
  display: grid;
  grid-template-columns: 1fr 1.1fr 1fr;
  gap: 12px;
  align-items: flex-end;
  max-width: 780px;
  margin: 0 auto;
  position: relative;
  padding-top: 14px;
}

.podium-card {
  position: relative;
  border-radius: 16px;
  padding: 16px 12px;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  border: 1px solid transparent;
  transition: transform 0.2s ease;
  min-width: 0;
}
.podium-card:hover { transform: translateY(-4px); }

/* 1st — gold */
.podium-card--first {
  background: linear-gradient(180deg, rgba(251,191,36,.18), rgba(251,191,36,.05));
  border-color: rgba(251,191,36,.45);
  box-shadow: 0 0 40px -10px rgba(251,191,36,.35);
  transform: translateY(-12px);
}
.podium-card--first:hover { transform: translateY(-16px); }

/* 2nd — silver */
.podium-card--second {
  background: linear-gradient(180deg, rgba(203,213,225,.14), rgba(203,213,225,.03));
  border-color: rgba(203,213,225,.35);
}

/* 3rd — bronze */
.podium-card--third {
  background: linear-gradient(180deg, rgba(205,127,50,.14), rgba(205,127,50,.03));
  border-color: rgba(205,127,50,.35);
}

/* Rank badges */
.podium-rank {
  width: 36px; height: 36px;
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-weight: 900;
  font-size: 16px;
  color: #1a1d23;
  position: absolute;
  top: -18px;
  left: 50%;
  transform: translateX(-50%);
  border: 3px solid rgba(0,0,0,.3);
  z-index: 2;
}

.podium-rank--first {
  background: linear-gradient(135deg, #FFD700, #FFC107);
  color: #1a1d23;
  width: 44px; height: 44px;
  font-size: 20px;
  top: -22px;
}
.podium-rank--second {
  background: linear-gradient(135deg, #E0E0E0, #9E9E9E);
  color: #1a1d23;
}
.podium-rank--third {
  background: linear-gradient(135deg, #CD7F32, #8B5A2B);
  color: #fff;
}

.podium-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  margin-top: 20px;
  width: 100%;
}
.podium-body--empty { color: rgba(255,255,255,.3); margin-top: 20px; }

.podium-name {
  font-size: 12px;
  font-weight: 700;
  line-height: 1.2;
  max-width: 110px;
  text-align: center;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  color: var(--text, #e9edf5);
}
.podium-name--first { font-size: 13px; }

/* Гос-номер вместо текста для kind="vehicles" */
.podium-plate { margin: 2px auto 0; }

.podium-sub {
  font-size: 10px;
  color: var(--muted, #8a93a8);
  margin-top: 1px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 110px;
}

.podium-fines {
  font-size: 11px;
  color: var(--muted, #8a93a8);
  margin-top: 2px;
}

/* Mobile: подиум помещается в 375px без обрезания 3-й карточки */
@media (max-width: 599px) {
  .podium-row { gap: 6px; padding-top: 16px; }
  .podium-card { padding: 12px 5px; }
  .podium-rank { width: 30px; height: 30px; font-size: 14px; top: -15px; }
  .podium-rank--first { width: 36px; height: 36px; font-size: 17px; top: -18px; }
  .podium-name { max-width: 100%; font-size: 11px; }
  .podium-name--first { font-size: 12px; }
  .podium-sub { max-width: 100%; }
  .podium-amount { font-size: 12px; }
  .podium-amount--first { font-size: 16px; }
  .pod-badge { padding: 2px 6px; font-size: 9px; white-space: normal; }

  .other-row { grid-template-columns: 16px 30px 1fr auto auto auto; gap: 6px; padding: 8px 8px; }
  .other-row__av { width: 30px; height: 30px; }
  .other-row__nm { font-size: 12px; word-break: break-word; line-height: 1.15; }
  .other-row__cnt { font-size: 11px; }
  .other-row__sum { font-size: 12px; }
}

.podium-amount {
  font-size: 14px;
  font-weight: 900;
  margin: 4px 0;
}
.podium-amount--first  { font-size: 20px; color: #FFC107; }
.podium-amount--second { color: #9E9E9E; }
.podium-amount--third  { color: #CD7F32; }

/* Badges */
.pod-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 9px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.2px;
  margin-top: 4px;
}
.pod-badge--unpaid {
  background: rgba(255,91,106,.12);
  color: #ff5b6a;
  border: 1px solid rgba(255,91,106,.25);
}
.pod-badge--paid {
  background: rgba(34,201,151,.12);
  color: #22c997;
  border: 1px solid rgba(34,201,151,.25);
}

/* Podium base */
.pod-base {
  display: grid;
  grid-template-columns: 1fr 1.1fr 1fr;
  gap: 12px;
  max-width: 780px;
  margin: 6px auto 0;
  height: 6px;
}
.pod-base__b { border-radius: 0 0 8px 8px; opacity: 0.35; }
.pod-base__b--first  {
  background: linear-gradient(180deg, #FFD700, #FFC107);
  height: 14px;
  margin-top: -8px;
  opacity: 0.5;
}
.pod-base__b--second { background: linear-gradient(180deg, #E0E0E0, #9E9E9E); }
.pod-base__b--third  { background: linear-gradient(180deg, #CD7F32, #8B5A2B); }

/* Others section */
.others-section {
  border-top: 1px solid var(--line, #222838);
  padding-top: 16px;
  margin-top: 4px;
}
.others-title {
  font-size: 11px;
  letter-spacing: 0.4px;
  text-transform: uppercase;
  color: var(--muted, #8a93a8);
  font-weight: 700;
  margin-bottom: 10px;
}

.other-row {
  display: grid;
  grid-template-columns: 24px 34px 1fr auto auto auto;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border: 1px solid var(--line, #222838);
  border-radius: 10px;
  background: rgba(255,255,255,.02);
  margin-bottom: 7px;
}
.other-row:last-child { margin-bottom: 0; }

.other-row__num {
  color: var(--muted, #8a93a8);
  font-weight: 700;
  font-size: 12px;
  text-align: center;
}
.other-row__av {
  width: 34px; height: 34px;
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-weight: 700;
  color: #fff;
  font-size: 11px;
}
.other-row__info { min-width: 0; }
.other-row__nm { font-weight: 600; font-size: 13px; }
.other-row__sb { font-size: 11px; color: var(--muted, #8a93a8); }
.other-row__cnt { color: var(--muted, #8a93a8); font-size: 12px; font-weight: 600; white-space: nowrap; }
.other-row__sum { font-weight: 800; font-size: 13px; white-space: nowrap; }

.other-row__badge {
  width: 24px; height: 24px;
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-weight: 800; font-size: 11px;
  flex-shrink: 0;
}
.other-row__badge--unpaid {
  background: rgba(255,91,106,.15);
  color: #ff5b6a;
  border: 1px solid rgba(255,91,106,.3);
}
.other-row__badge--paid {
  background: rgba(34,201,151,.12);
  color: #22c997;
  border: 1px solid rgba(34,201,151,.3);
}

/* Light theme */
.v-theme--light .podium-name { color: #1a1d23; }
.v-theme--light .podium-fines { color: #6b7280; }
.v-theme--light .podium-sub { color: #6b7280; }
.v-theme--light .others-section { border-color: #e2e6f0; }
.v-theme--light .other-row { border-color: #e2e6f0; background: rgba(0,0,0,.02); }

/* Clickable leaders */
.podium-card--clickable { cursor: pointer; transition: transform 0.15s, filter 0.15s, box-shadow 0.15s; }
.podium-card--clickable:hover { filter: brightness(1.12); box-shadow: 0 4px 20px rgba(106,166,255,.18); }
.podium-card--first.podium-card--clickable:hover { transform: translateY(-16px); }
.podium-card--second.podium-card--clickable:hover { transform: translateY(-6px); }
.podium-card--third.podium-card--clickable:hover  { transform: translateY(-6px); }
.podium-card--clickable:active { filter: brightness(0.95); }
.other-row--clickable { cursor: pointer; transition: background 0.15s, box-shadow 0.15s; }
.other-row--clickable:hover { background: rgba(106, 166, 255, 0.12) !important; box-shadow: 0 2px 8px rgba(106,166,255,.1); }
</style>
