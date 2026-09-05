<template>
  <div class="slm-view" :class="{ 'slm-view--light': !isDark }">
    <div class="slm-topbar">
      <div>
        <div class="slm-crumbs">
          <router-link to="/fleet">Автопарк</router-link>
          <span class="slm-crumbs__sep">/</span>
          <b>Где люди</b>
        </div>
        <h1 class="slm-h1">Сотрудники на смене</h1>
        <p class="slm-lead">
          <b>{{ onShift.length }}</b> человек на смене ·
          обновляется автоматически каждые {{ POLL_SECONDS }} сек ·
          последнее обновление: {{ lastRefreshLabel }}
        </p>
      </div>
      <div class="d-flex ga-2">
        <v-btn variant="tonal" size="small" color="primary" prepend-icon="mdi-map-marker-radius" @click="requestDialogOpen = true">
          Запросить местоположение
        </v-btn>
        <v-btn variant="tonal" size="small" :loading="loading" @click="load">Обновить сейчас</v-btn>
      </div>
    </div>

    <div class="slm-kpi-row">
      <div class="slm-kpi slm-kpi--ok"><b>{{ freshCount }}</b><span>на связи (&lt;5 мин)</span></div>
      <div class="slm-kpi slm-kpi--warn"><b>{{ staleCount }}</b><span>задержка (5–30 мин)</span></div>
      <div class="slm-kpi slm-kpi--alert"><b>{{ oldCount }}</b><span>давно нет данных</span></div>
      <div class="slm-kpi"><b>{{ noDataCount }}</b><span>ещё нет точек</span></div>
    </div>

    <section class="slm-map-row">
      <div class="slm-panel slm-map-box">
        <div class="slm-panel__head"><span>Карта</span><small>цвет метки = свежесть данных</small></div>
        <div v-if="loading && !onShift.length" class="slm-loading"><div class="slm-spinner"></div></div>
        <RussiaMapSvg
          v-else-if="mapPins.length"
          :pins="mapPins"
          @pin-click="onPinClick"
        />
        <div v-else class="slm-empty">
          {{ onShift.length ? 'У сотрудников на смене пока нет ни одной переданной точки' : 'Сейчас никто не на смене' }}
        </div>
      </div>

      <div class="slm-panel slm-list-box">
        <div class="slm-panel__head"><span>Список</span><small>клик — карточка сотрудника</small></div>
        <div v-if="loading && !onShift.length" class="slm-loading"><div class="slm-spinner"></div></div>
        <div v-else-if="!onShift.length" class="slm-empty">Сейчас никто не на смене</div>
        <div v-else class="slm-staff-list">
          <div v-for="u in onShift" :key="u.user_id" class="slm-staff-row" @click="openCard(u)">
            <span class="slm-staff-row__dot" :class="`slm-dot--${staleness(u.last_point?.recorded_at)}`"></span>
            <div class="slm-staff-row__info">
              <div class="slm-staff-row__nm">
                {{ u.full_name }}
                <v-icon v-if="u.via_request" size="13" icon="mdi-message-reply-text" color="orange" title="Разовый ответ на запрос, не активная смена" />
              </div>
              <div class="slm-staff-row__ds">{{ u.org_name || '—' }} · {{ sourceLabel(u.last_point?.source) }}</div>
            </div>
            <div class="slm-staff-row__time">{{ formatRelativeTime(u.last_point?.recorded_at) }}</div>
          </div>
        </div>
      </div>
    </section>

    <!-- Карточка сотрудника -->
    <teleport to="body">
      <transition name="slm-popup-fade">
        <div v-if="selectedUser" class="slm-popup-overlay" @click.self="selectedUser = null">
          <div class="slm-popup" :class="{ 'slm-popup--light': !isDark }">
            <div class="slm-popup__head">
              <div class="slm-popup__abbr" :style="{ background: stalenessColor(selectedUser.last_point?.recorded_at) }">
                {{ initials(selectedUser.full_name) }}
              </div>
              <div>
                <div class="slm-popup__nm">{{ selectedUser.full_name }}</div>
                <div class="slm-popup__sub">{{ selectedUser.org_name || '—' }}</div>
              </div>
              <button class="slm-popup__close" @click="selectedUser = null">✕</button>
            </div>
            <div class="slm-popup__body">
              <div v-if="selectedUser.shift_started_at" class="slm-popup__row"><span>На смене с</span><b>{{ fmtAbs(selectedUser.shift_started_at) }}</b></div>
              <div v-else class="slm-popup__row"><span>Смена</span><b>не активна — разовый ответ на запрос</b></div>
              <div class="slm-popup__row" v-if="selectedUser.last_point">
                <span>Источник</span><b>{{ sourceLabel(selectedUser.last_point.source) }}</b>
              </div>
              <div class="slm-popup__row" v-if="selectedUser.last_point">
                <span>Получено</span><b>{{ formatRelativeTime(selectedUser.last_point.recorded_at) }}</b>
              </div>
              <div class="slm-popup__row" v-if="selectedUser.last_point">
                <span>Координаты</span><b>{{ selectedUser.last_point.lat.toFixed(5) }}, {{ selectedUser.last_point.lon.toFixed(5) }}</b>
              </div>
              <div class="slm-popup__row" v-if="selectedUser.last_point">
                <span>Точность</span><b>{{ selectedUser.last_point.accuracy_m != null ? `±${Math.round(selectedUser.last_point.accuracy_m)} м` : 'неизвестна' }}</b>
              </div>
              <div v-else class="slm-popup__row"><span>Точек пока нет</span></div>
              <v-btn class="mt-3" block color="primary" variant="flat" @click="openTrack">Трек за период</v-btn>
            </div>
          </div>
        </div>
      </transition>
    </teleport>

    <StaffTrackDialog
      v-model="trackDialogOpen"
      :user-id="selectedUser?.user_id ?? null"
      :user-name="selectedUser?.full_name ?? ''"
    />

    <RequestLocationDialog v-model="requestDialogOpen" @requested="load" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useTheme } from 'vuetify'
import { apiFetch } from '@/api'
import { useToast } from '@/composables/useToast'
import { formatRelativeTime, stalenessLevel } from '@/utils/relativeTime'
import RussiaMapSvg from '@/components/fleet/RussiaMapSvg.vue'
import { projectLatLonToSvg, type MapPin } from '@/components/fleet/russiaMapPins'
import StaffTrackDialog from '@/components/staff/StaffTrackDialog.vue'
import RequestLocationDialog from '@/components/staff/RequestLocationDialog.vue'

interface LastPoint {
  id: number
  lat: number
  lon: number
  accuracy_m: number | null
  recorded_at: string
  received_at: string
  source: string
}
interface OnShiftUser {
  user_id: number
  full_name: string
  org_id: number | null
  org_name: string | null
  shift_started_at: string | null
  last_point: LastPoint | null
  via_request: boolean
}

// Источник точки — «приложение (смена)» через мобильный/браузер во время
// активной смены, или разовый ответ на запрос: через push (экран
// подтверждения в самом приложении, source='webapp') или через мессенджер
// (2026-09; push теперь основной канал запроса, поэтому 'webapp' — самый
// частый источник разового ответа, см. staff_location_requests.py::respond).
const SOURCE_LABELS: Record<string, string> = {
  browser: 'приложение (смена)',
  webapp: 'ответ на запрос · push',
  telegram: 'ответ на запрос · Telegram',
  max: 'ответ на запрос · MAX',
}
function sourceLabel(source: string | undefined | null): string {
  if (!source) return '—'
  return SOURCE_LABELS[source] || source
}

const theme = useTheme()
const isDark = computed(() => theme.global.current.value.dark)
const toast = useToast()

const POLL_SECONDS = 25
const onShift = ref<OnShiftUser[]>([])
const loading = ref(false)
const lastRefresh = ref<Date | null>(null)
const selectedUser = ref<OnShiftUser | null>(null)
const trackDialogOpen = ref(false)
const requestDialogOpen = ref(false)
let pollTimer: ReturnType<typeof setInterval> | null = null

const lastRefreshLabel = computed(() => lastRefresh.value ? formatRelativeTime(lastRefresh.value) : '—')

function staleness(iso: string | undefined | null): 'fresh' | 'stale' | 'old' | 'none' {
  return stalenessLevel(iso ?? null)
}

const STALE_COLORS: Record<string, string> = {
  fresh: '#22c997',
  stale: '#f6b34a',
  old: '#8a93a8',
  none: '#5d6478',
}
function stalenessColor(iso: string | undefined | null): string {
  return STALE_COLORS[staleness(iso)]
}

const freshCount = computed(() => onShift.value.filter(u => staleness(u.last_point?.recorded_at) === 'fresh').length)
const staleCount = computed(() => onShift.value.filter(u => staleness(u.last_point?.recorded_at) === 'stale').length)
const oldCount = computed(() => onShift.value.filter(u => u.last_point && staleness(u.last_point.recorded_at) === 'old').length)
const noDataCount = computed(() => onShift.value.filter(u => !u.last_point).length)

function initials(name: string): string {
  const parts = (name || '').trim().split(/\s+/).filter(Boolean)
  if (!parts.length) return '?'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[1][0]).toUpperCase()
}

const mapPins = computed<MapPin[]>(() =>
  onShift.value
    .filter(u => u.last_point)
    .map(u => {
      const { x, y } = projectLatLonToSvg(u.last_point!.lat, u.last_point!.lon)
      const lvl = staleness(u.last_point!.recorded_at)
      return {
        id: u.user_id,
        name: (u.full_name || '').split(/\s+/)[0] || u.full_name,
        x, y,
        radius: 14,
        count: 0,
        glyph: initials(u.full_name),
        color: STALE_COLORS[lvl],
        shape: 'person',
        hint: `${u.full_name} — ${formatRelativeTime(u.last_point!.recorded_at)}`,
      } as MapPin
    })
)

function onPinClick(pin: MapPin) {
  const u = onShift.value.find(x => x.user_id === pin.id)
  if (u) openCard(u)
}

function openCard(u: OnShiftUser) {
  selectedUser.value = u
}

function openTrack() {
  trackDialogOpen.value = true
}

function fmtAbs(iso: string): string {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  return d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

async function load() {
  loading.value = true
  try {
    const data = await apiFetch<OnShiftUser[]>('/staff-location/on-shift')
    onShift.value = Array.isArray(data) ? data : []
    lastRefresh.value = new Date()
  } catch (e: any) {
    toast.error(`Не удалось загрузить список: ${e?.payload?.message || e?.message || 'ошибка сети'}`)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  load()
  pollTimer = setInterval(load, POLL_SECONDS * 1000)
})
onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.slm-view {
  --sv-bg: #0a0d14; --sv-panel: #141823; --sv-bg2: #0f131c; --sv-line: #222838;
  --sv-line2: #2b3245; --sv-text: #e9edf5; --sv-muted: #8a93a8; --sv-accent: #6aa6ff;
  padding: 22px 28px 60px; color: var(--sv-text); font-family: 'Inter', system-ui, sans-serif;
  font-size: 14px; min-height: 100vh;
}
.slm-view--light {
  --sv-bg: #f4f6fb; --sv-panel: #ffffff; --sv-bg2: #eef1f7; --sv-line: #e2e6f0;
  --sv-line2: #d0d5e0; --sv-text: #1a1d23; --sv-muted: #6b7280; --sv-accent: #2563eb;
}
.slm-topbar { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; margin-bottom: 18px; }
.slm-crumbs { color: var(--sv-muted); font-size: 13px; margin-bottom: 4px; }
.slm-crumbs a { color: var(--sv-muted); text-decoration: none; }
.slm-crumbs__sep { opacity: 0.5; margin: 0 4px; }
.slm-crumbs b { color: var(--sv-text); font-weight: 600; }
.slm-h1 { margin: 0 0 4px; font-size: 24px; font-weight: 800; letter-spacing: -0.4px; }
.slm-lead { color: var(--sv-muted); margin: 0; font-size: 13px; }

.slm-kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 22px; }
@media (max-width: 700px) { .slm-kpi-row { grid-template-columns: repeat(2, 1fr); } }
.slm-kpi {
  background: linear-gradient(180deg, var(--sv-panel), var(--sv-bg2));
  border: 1px solid var(--sv-line); border-radius: 14px; padding: 14px 16px;
  display: flex; flex-direction: column; gap: 4px;
}
.slm-kpi b { font-size: 26px; font-weight: 800; font-family: 'JetBrains Mono', monospace; }
.slm-kpi span { font-size: 11.5px; color: var(--sv-muted); }
.slm-kpi--ok b { color: #22c997; }
.slm-kpi--warn b { color: #f6b34a; }
.slm-kpi--alert b { color: #ff5b6a; }

.slm-map-row { display: grid; grid-template-columns: 1.4fr 1fr; gap: 18px; }
@media (max-width: 960px) { .slm-map-row { grid-template-columns: 1fr; } }
.slm-panel {
  background: linear-gradient(180deg, var(--sv-panel), var(--sv-bg2));
  border: 1px solid var(--sv-line); border-radius: 16px; padding: 18px;
}
.slm-panel__head { display: flex; align-items: baseline; gap: 10px; margin-bottom: 14px; font-size: 14px; font-weight: 600; }
.slm-panel__head small { color: var(--sv-muted); font-weight: 400; font-size: 12px; margin-left: auto; }
.slm-map-box { position: relative; overflow: hidden; }
.slm-list-box { max-height: 560px; overflow-y: auto; }

.slm-loading, .slm-empty { padding: 40px 10px; text-align: center; color: var(--sv-muted); }
.slm-spinner { width: 28px; height: 28px; border: 3px solid var(--sv-line2); border-top-color: var(--sv-accent); border-radius: 50%; margin: 0 auto; animation: slm-spin 0.8s linear infinite; }
@keyframes slm-spin { to { transform: rotate(360deg); } }

.slm-staff-list { display: flex; flex-direction: column; }
.slm-staff-row {
  display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 10px;
  padding: 10px 4px; border-bottom: 1px solid var(--sv-line); cursor: pointer;
}
.slm-staff-row:last-child { border-bottom: none; }
.slm-staff-row:hover { background: rgba(255,255,255,.03); }
.slm-view--light .slm-staff-row:hover { background: rgba(0,0,0,.03); }
.slm-staff-row__dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.slm-dot--fresh { background: #22c997; }
.slm-dot--stale { background: #f6b34a; }
.slm-dot--old { background: #8a93a8; }
.slm-dot--none { background: #5d6478; }
.slm-staff-row__nm { font-weight: 700; font-size: 13.5px; }
.slm-staff-row__ds { color: var(--sv-muted); font-size: 11.5px; }
.slm-staff-row__time { font-size: 12px; color: var(--sv-muted); white-space: nowrap; }

/* Popup — тот же приём, что FleetRegionsView.vue */
.slm-popup-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,.5); z-index: 2000;
  display: flex; align-items: center; justify-content: center; padding: 16px;
}
.slm-popup {
  background: var(--sv-panel); color: var(--sv-text); border-radius: 16px; width: 100%; max-width: 380px;
  border: 1px solid var(--sv-line2); overflow: hidden;
}
.slm-popup--light { background: #fff; }
.slm-popup__head { display: flex; align-items: center; gap: 12px; padding: 16px; border-bottom: 1px solid var(--sv-line); }
.slm-popup__abbr { width: 42px; height: 42px; border-radius: 12px; display: flex; align-items: center; justify-content: center; font-weight: 800; color: #0a0d14; flex-shrink: 0; }
.slm-popup__nm { font-weight: 800; font-size: 15px; }
.slm-popup__sub { color: var(--sv-muted); font-size: 12px; }
.slm-popup__close { margin-left: auto; background: none; border: none; color: var(--sv-muted); font-size: 16px; cursor: pointer; }
.slm-popup__body { padding: 16px; }
.slm-popup__row { display: flex; justify-content: space-between; font-size: 13px; padding: 6px 0; border-bottom: 1px solid var(--sv-line); }
.slm-popup__row:last-of-type { border-bottom: none; }
.slm-popup-fade-enter-active, .slm-popup-fade-leave-active { transition: opacity 0.2s; }
.slm-popup-fade-enter-from, .slm-popup-fade-leave-to { opacity: 0; }
</style>
