<template>
  <v-container fluid class="pa-6 fleet-fines-view">

    <!-- Header -->
    <div class="fines-header mb-4">
      <div class="fines-crumbs">
        <span class="fines-crumbs__link">Автопарк</span>
        <span class="fines-crumbs__sep">/</span>
        <span class="fines-crumbs__current">Штрафы и нарушения</span>
      </div>
      <div class="d-flex align-start justify-space-between mt-1 flex-wrap gap-2">
        <div>
          <h1 class="fines-title">Штрафы</h1>
          <p class="fines-lead">
            Авто-импорт из ГИБДД API
            <span class="fines-lead__dot">·</span>
            последнее обновление: сегодня
          </p>
        </div>
        <v-btn
          color="primary"
          prepend-icon="mdi-plus"
          variant="flat"
          rounded="lg"
          class="mt-1"
        >
          Добавить штраф
        </v-btn>
      </div>
    </div>

    <!-- KPI strip -->
    <div class="kpi-strip mb-5">
      <KpiCard
        label="Всего штрафов"
        :value="summary.total_count"
        sub="за всё время"
        variant="default"
        :loading="summaryLoading"
      />
      <KpiCard
        label="Не оплачено"
        :value="summary.unpaid_count"
        :sub="summary.unpaid_amount ? fmtRub(summary.unpaid_amount) : '—'"
        variant="alert"
        :loading="summaryLoading"
      />
      <KpiCard
        label="Оплачено"
        :value="summary.total_count - summary.unpaid_count"
        :sub="paidAmount > 0 ? fmtRub(paidAmount) : '—'"
        variant="ok"
        :loading="summaryLoading"
      />
      <KpiCard
        label="Общая сумма"
        :value="summary.total_amount ? fmtRub(summary.total_amount) : '—'"
        sub="за всё время"
        variant="info"
        :loading="summaryLoading"
      />
      <KpiCard
        label="Скоро срок"
        value="0"
        sub="осталось до 50% < 7 дн."
        variant="warn"
      />
    </div>

    <!-- Podiums row: Топ водителей / ТС / Филиалов -->
    <div class="fines-podiums-row mb-5">
      <div class="fines-podium-cell">
        <FineLeadersPodiumWidget kind="drivers" title="Топ водителей" @leader-click="onLeaderClick" />
      </div>
      <div class="fines-podium-cell">
        <FineLeadersPodiumWidget kind="vehicles" title="Топ ТС" @leader-click="onLeaderClick" />
      </div>
      <div class="fines-podium-cell">
        <FineLeadersPodiumWidget kind="filials" title="Топ филиалов" @leader-click="onLeaderClick" />
      </div>
    </div>

    <!-- Two-column analytics -->
    <div class="fines-two-col mb-5">

      <!-- By violation type -->
      <div class="fines-panel">
        <div class="fines-panel__head">
          <span class="fines-panel__icon">📊</span>
          <span class="fines-panel__title">По типам нарушений</span>
          <span class="fines-panel__small ml-auto">за всё время</span>
        </div>
        <div v-if="finesLoading" class="d-flex justify-center py-6">
          <v-progress-circular indeterminate size="28" color="primary" />
        </div>
        <div v-else-if="byType.length === 0" class="text-center text-medium-emphasis py-6">
          Нет данных
        </div>
        <div v-else class="bytype-list">
          <div
            v-for="item in byType"
            :key="item.type"
            class="bytype-row"
            :class="`bytype-row--${item.variant}`"
          >
            <div class="bytype-row__ic">{{ item.icon }}</div>
            <div class="bytype-row__info">
              <div class="bytype-row__nm">{{ item.type || 'Не указан' }}</div>
            </div>
            <div class="bytype-row__cnt">
              <b>{{ item.count }} шт</b>
              <small>{{ fmtRub(item.total) }}</small>
            </div>
          </div>
        </div>
      </div>

      <!-- By org/station -->
      <div class="fines-panel">
        <div class="fines-panel__head">
          <span class="fines-panel__icon">🏢</span>
          <span class="fines-panel__title">По филиалам</span>
          <span class="fines-panel__small ml-auto">сумма штрафов в ₽</span>
        </div>
        <div v-if="finesLoading" class="d-flex justify-center py-6">
          <v-progress-circular indeterminate size="28" color="primary" />
        </div>
        <div v-else-if="byOrg.length === 0" class="text-center text-medium-emphasis py-6">
          Нет данных
        </div>
        <div v-else class="byorg-list">
          <div
            v-for="item in byOrg"
            :key="item.name"
            class="byorg-bar"
          >
            <div class="byorg-bar__nm">{{ item.name }}</div>
            <div class="byorg-bar__track">
              <i :style="{ width: `${item.pct}%` }"></i>
            </div>
            <div class="byorg-bar__sum">{{ fmtRub(item.total) }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Detailed table -->
    <div class="fines-table-wrap">
      <!-- Table header / filters -->
      <div class="fines-table-head">
        <div class="d-flex align-center gap-2">
          <h3 class="fines-table-head__title">Журнал штрафов</h3>
          <span class="fines-table-head__count">{{ filteredFines.length }}</span>
        </div>
        <div class="d-flex align-center gap-3 flex-wrap mt-2">
          <!-- Status filter -->
          <div class="d-flex align-center gap-1">
            <button
              v-for="s in STATUS_FILTERS"
              :key="s.value"
              class="filter-chip"
              :class="{ 'filter-chip--active': statusFilter === s.value }"
              @click="statusFilter = s.value"
            >
              {{ s.label }}
            </button>
          </div>
          <!-- Period filter -->
          <div class="d-flex align-center gap-1">
            <button
              v-for="p in PERIOD_FILTERS"
              :key="p.value"
              class="filter-chip"
              :class="{ 'filter-chip--active': periodFilter === p.value }"
              @click="periodFilter = p.value"
            >
              {{ p.label }}
            </button>
          </div>
          <!-- Search -->
          <input
            v-model="search"
            class="fines-search"
            placeholder="Поиск по номеру ТС или нарушению..."
          />
        </div>
      </div>

      <!-- Loading -->
      <div v-if="finesLoading" class="d-flex justify-center py-10">
        <v-progress-circular indeterminate size="40" color="primary" />
      </div>

      <!-- Empty state -->
      <div v-else-if="filteredFines.length === 0" class="text-center text-medium-emphasis py-10">
        <v-icon icon="mdi-check-circle-outline" color="success" size="48" class="mb-3" />
        <div>Штрафов не найдено</div>
      </div>

      <!-- Table -->
      <div v-else class="fines-table-scroll">
        <table class="fines-table">
          <thead>
            <tr>
              <th>Дата</th>
              <th>ТС</th>
              <th>Водитель</th>
              <th>Нарушение</th>
              <th>Сумма</th>
              <th>Статус</th>
              <th>Место</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="fine in filteredFines" :key="fine.id">
              <!-- Дата -->
              <td>
                <span class="fine-date">{{ formatDate(fine.issued_at) }}</span>
                <span class="fine-time">{{ formatTime(fine.issued_at) }}</span>
              </td>
              <!-- ТС -->
              <td>
                <div class="fine-vehicle">
                  <LicensePlate
                    v-if="fine.vehicle_plate"
                    :model-value="fine.vehicle_plate"
                    size="sm"
                  />
                  <span v-else class="text-medium-emphasis">—</span>
                  <span v-if="fine.vehicle_model" class="fine-vehicle__model">{{ fine.vehicle_model }}</span>
                </div>
              </td>
              <!-- Водитель -->
              <td>
                <div v-if="fine.driver_name" class="fine-driver">
                  <GradientAvatar :full-name="fine.driver_name" size="sm" />
                  <span class="fine-driver__name">{{ fine.driver_name }}</span>
                </div>
                <span v-else class="text-medium-emphasis text-caption">не определён</span>
              </td>
              <!-- Нарушение -->
              <td>
                <span class="fine-violation">{{ fine.violation_type || '—' }}</span>
              </td>
              <!-- Сумма -->
              <td>
                <span class="fine-amount">{{ fmtRub(Number(fine.amount)) }}</span>
              </td>
              <!-- Статус -->
              <td>
                <StatusPill
                  :variant="fine.status === 'paid' ? 'ok' : 'alert'"
                  :dot="fine.status === 'unpaid'"
                >
                  {{ fine.status === 'paid' ? 'Оплачен' : 'Не оплачен' }}
                </StatusPill>
              </td>
              <!-- Место -->
              <td>
                <span class="fine-location">{{ fine.location || '—' }}</span>
              </td>
              <!-- Actions -->
              <td>
                <div class="d-flex align-center gap-1">
                  <v-tooltip v-if="fine.status === 'unpaid'" text="Отметить оплаченным" location="top">
                    <template #activator="{ props: tp }">
                      <v-btn
                        v-bind="tp"
                        icon="mdi-check"
                        size="x-small"
                        variant="tonal"
                        color="success"
                        :loading="paying === fine.id"
                        @click="markPaid(fine)"
                      />
                    </template>
                  </v-tooltip>
                  <v-tooltip text="Редактировать" location="top">
                    <template #activator="{ props: tp }">
                      <v-btn
                        v-bind="tp"
                        icon="mdi-pencil-outline"
                        size="x-small"
                        variant="text"
                        color="primary"
                      />
                    </template>
                  </v-tooltip>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="fines-table-foot">
        <span>Показано {{ filteredFines.length }} из {{ allFines.length }}</span>
        <span>Авто-импорт штрафов из <b>ГИБДД API</b> · последнее обновление: сегодня</span>
      </div>
    </div>

    <!-- Snackbar -->
    <v-snackbar v-model="snackbar.show" :color="snackbar.color" :timeout="-1">
      {{ snackbar.text }}
      <template #actions>
        <v-btn variant="text" @click="snackbar.show = false">Закрыть</v-btn>
      </template>
    </v-snackbar>

  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch } from '@/api'
import KpiCard from '@/components/fleet/KpiCard.vue'
import StatusPill from '@/components/fleet/StatusPill.vue'
import GradientAvatar from '@/components/fleet/GradientAvatar.vue'
import LicensePlate from '@/components/vehicles/LicensePlate.vue'
import FineLeadersPodiumWidget from '@/components/vehicles/FineLeadersPodiumWidget.vue'

const router = useRouter()

// ── Types ─────────────────────────────────────────────────────────────────

interface FinesSummary {
  total_count: number
  total_amount: number
  unpaid_count: number
  unpaid_amount: number
}

interface VehicleFine {
  id: number
  vehicle_id: number
  issued_at: string
  amount: string | number
  doc_number: string | null
  violation_type: string | null
  location: string | null
  status: string
  paid_at: string | null
  comment: string | null
  driver_name: string | null
  driver_kind: string
  matched_trip_id: number | null
  // enriched on client (from vehicle data in list endpoint if available)
  vehicle_plate?: string | null
  vehicle_model?: string | null
}

// ── Constants ─────────────────────────────────────────────────────────────

const STATUS_FILTERS = [
  { label: 'Все', value: '' },
  { label: 'Оплачено', value: 'paid' },
  { label: 'Не оплачено', value: 'unpaid' },
]

const PERIOD_FILTERS = [
  { label: 'Всё время', value: '' },
  { label: 'Месяц', value: '30' },
  { label: 'Квартал', value: '90' },
  { label: 'Год', value: '365' },
]

const TYPE_ICONS: Record<string, { icon: string; variant: string }> = {
  'превышение': { icon: '!', variant: 'alert' },
  'скорост':    { icon: '!', variant: 'alert' },
  'парковк':    { icon: '⚠', variant: 'warn' },
  'стоянк':     { icon: '⚠', variant: 'warn' },
  'полос':      { icon: 'i', variant: 'info' },
  'светофор':   { icon: '⚠', variant: 'warn' },
  'стоп-лин':   { icon: '⚠', variant: 'warn' },
  'ремень':     { icon: '!', variant: 'alert' },
}

// ── State ─────────────────────────────────────────────────────────────────

const summaryLoading = ref(false)
const finesLoading = ref(false)
const paying = ref<number | null>(null)

const summary = ref<FinesSummary>({
  total_count: 0,
  total_amount: 0,
  unpaid_count: 0,
  unpaid_amount: 0,
})
const allFines = ref<VehicleFine[]>([])

const statusFilter = ref('')
const periodFilter = ref('')
const search = ref('')

const snackbar = ref({ show: false, text: '', color: 'success' })

// ── Computed ──────────────────────────────────────────────────────────────

const paidAmount = computed(() =>
  (summary.value.total_amount ?? 0) - (summary.value.unpaid_amount ?? 0)
)

const filteredFines = computed(() => {
  let list = allFines.value

  if (statusFilter.value) {
    list = list.filter(f => f.status === statusFilter.value)
  }

  if (periodFilter.value) {
    const days = Number(periodFilter.value)
    const cutoff = new Date()
    cutoff.setDate(cutoff.getDate() - days)
    list = list.filter(f => new Date(f.issued_at) >= cutoff)
  }

  if (search.value.trim()) {
    const q = search.value.trim().toLowerCase()
    list = list.filter(f =>
      (f.vehicle_plate ?? '').toLowerCase().includes(q) ||
      (f.violation_type ?? '').toLowerCase().includes(q) ||
      (f.driver_name ?? '').toLowerCase().includes(q)
    )
  }

  return list
})

// Client-side aggregation: GROUP BY violation_type
const byType = computed(() => {
  const map = new Map<string, { count: number; total: number }>()
  for (const f of allFines.value) {
    const key = f.violation_type || 'Не указан'
    const prev = map.get(key) ?? { count: 0, total: 0 }
    map.set(key, { count: prev.count + 1, total: prev.total + Number(f.amount) })
  }
  return Array.from(map.entries())
    .sort((a, b) => b[1].count - a[1].count)
    .slice(0, 6)
    .map(([type, stats]) => {
      const typeLow = type.toLowerCase()
      const meta = Object.entries(TYPE_ICONS).find(([k]) => typeLow.includes(k))
      return {
        type,
        count: stats.count,
        total: stats.total,
        icon: meta ? meta[1].icon : '!',
        variant: meta ? meta[1].variant : 'alert',
      }
    })
})

// Client-side aggregation: GROUP BY owner_org_name (using driver_kind/name as fallback)
const byOrg = computed(() => {
  const map = new Map<string, number>()
  for (const f of allFines.value) {
    // vehicle_model may carry org info in future; for now use first word of location or 'Прочее'
    const key = extractOrg(f)
    map.set(key, (map.get(key) ?? 0) + Number(f.amount))
  }
  const entries = Array.from(map.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
  const maxVal = entries[0]?.[1] ?? 1
  return entries.map(([name, total]) => ({
    name,
    total,
    pct: Math.round((total / maxVal) * 100),
  }))
})

function extractOrg(f: VehicleFine): string {
  // Heuristic: use first part of location until comma/hyphen or 'Прочее'
  if (f.location) {
    const parts = f.location.split(/[,·\-]/)
    const candidate = parts[parts.length - 1].trim()
    if (candidate.length > 1 && candidate.length < 30) return candidate
  }
  return 'Прочее'
}

// ── API ───────────────────────────────────────────────────────────────────

async function fetchSummary(): Promise<void> {
  summaryLoading.value = true
  try {
    summary.value = await apiFetch<FinesSummary>('/vehicles-dashboard/fines-summary')
  } catch (e) {
    console.error('[FleetFines] fetchSummary', e)
  } finally {
    summaryLoading.value = false
  }
}

async function fetchFines(): Promise<void> {
  finesLoading.value = true
  try {
    allFines.value = await apiFetch<VehicleFine[]>('/vehicle-fines/')
  } catch (e) {
    console.error('[FleetFines] fetchFines', e)
    showSnack('Ошибка загрузки штрафов', 'error')
  } finally {
    finesLoading.value = false
  }
}

async function markPaid(fine: VehicleFine): Promise<void> {
  paying.value = fine.id
  try {
    await apiFetch(`/vehicle-fines/${fine.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ status: 'paid' }),
    })
    await Promise.all([fetchFines(), fetchSummary()])
    showSnack('Штраф отмечен оплаченным')
  } catch (e) {
    const msg = (e as any)?.payload?.message || (e instanceof Error ? e.message : 'Ошибка')
    showSnack(typeof msg === 'string' ? msg : JSON.stringify(msg), 'error')
  } finally {
    paying.value = null
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────

function showSnack(text: string, color = 'success') {
  snackbar.value = { show: true, text, color }
}

function fmtRub(val: number): string {
  return val.toLocaleString('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 })
}

function formatDate(val: string): string {
  if (!val) return '—'
  return new Date(val).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

function formatTime(val: string): string {
  if (!val) return ''
  return new Date(val).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
}

// ── Leader click handler ──────────────────────────────────────────────────

function onLeaderClick(payload: { key: string; name: string | null; kind: string; id: number | null }): void {
  const { kind, id } = payload
  if (kind === 'user' && id) {
    router.push(`/staff/${id}`)
  } else if (kind === 'external' && id) {
    router.push(`/staff?external=${id}`)
  } else if (kind === 'vehicle' && id) {
    router.push(`/fleet/vehicles/${id}`)
  } else if (kind === 'filial' && id) {
    router.push(`/fleet/regions?org_id=${id}`)
  }
}

// ── Init ──────────────────────────────────────────────────────────────────

onMounted(() => {
  fetchSummary()
  fetchFines()
})
</script>

<style scoped>
/* ── Layout ── */
.fleet-fines-view {
  min-height: 100vh;
}

/* ── Header ── */
.fines-crumbs {
  font-size: 13px;
  color: var(--muted, #8a93a8);
}
.fines-crumbs__link { cursor: pointer; }
.fines-crumbs__link:hover { color: var(--accent, #6aa6ff); }
.fines-crumbs__sep { margin: 0 6px; opacity: 0.5; }
.fines-crumbs__current { color: var(--text, #e9edf5); font-weight: 600; }

.fines-title {
  margin: 0 0 2px;
  font-size: 26px;
  font-weight: 800;
  letter-spacing: -0.4px;
}

.fines-lead {
  margin: 0;
  font-size: 13px;
  color: var(--muted, #8a93a8);
}
.fines-lead__dot { margin: 0 5px; }

/* ── KPI strip ── */
.kpi-strip {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 14px;
}
@media (max-width: 1100px) {
  .kpi-strip { grid-template-columns: repeat(2, 1fr); }
}

/* ── Podiums row (3 columns) ── */
.fines-podiums-row {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 16px;
}
@media (max-width: 1100px) {
  .fines-podiums-row { grid-template-columns: 1fr; }
}
.fines-podium-cell {
  background: linear-gradient(180deg, var(--panel, #141823), var(--bg-2, #0f131c));
  border: 1px solid var(--line, #222838);
  border-radius: 18px;
  overflow: hidden;
}

/* ── Two-column ── */
.fines-two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
}
@media (max-width: 900px) {
  .fines-two-col { grid-template-columns: 1fr; }
}

.fines-panel {
  background: linear-gradient(180deg, var(--panel, #141823), var(--bg-2, #0f131c));
  border: 1px solid var(--line, #222838);
  border-radius: 16px;
  padding: 18px;
}

.fines-panel__head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
  font-size: 14px;
  font-weight: 700;
  color: var(--text, #e9edf5);
}
.fines-panel__icon { font-size: 16px; }
.fines-panel__title { font-weight: 700; }
.fines-panel__small { color: var(--muted, #8a93a8); font-size: 12px; font-weight: 500; }

/* By type */
.bytype-list { display: grid; gap: 0; }
.bytype-row {
  display: grid;
  grid-template-columns: 34px 1fr auto;
  gap: 12px;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid var(--line, #222838);
}
.bytype-row:last-child { border: 0; }
.bytype-row__ic {
  width: 34px; height: 34px;
  border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  font-weight: 800; font-size: 14px;
}
.bytype-row--alert .bytype-row__ic { background: rgba(255,91,106,.1); color: #ff5b6a; }
.bytype-row--warn .bytype-row__ic  { background: rgba(246,179,74,.1);  color: #f6b34a; }
.bytype-row--info .bytype-row__ic  { background: rgba(93,208,255,.1);  color: #5dd0ff; }
.bytype-row--ok .bytype-row__ic    { background: rgba(34,201,151,.1);  color: #22c997; }
.bytype-row__nm { font-weight: 600; font-size: 13px; }
.bytype-row__cnt { text-align: right; }
.bytype-row__cnt b { display: block; font-weight: 800; font-size: 14px; }
.bytype-row__cnt small { color: var(--muted, #8a93a8); font-size: 11px; }

/* By org bars */
.byorg-list { display: grid; gap: 10px; }
.byorg-bar {
  display: grid;
  grid-template-columns: 110px 1fr auto;
  align-items: center;
  gap: 12px;
}
.byorg-bar__nm { font-size: 13px; font-weight: 600; }
.byorg-bar__track {
  height: 22px;
  background: rgba(255,255,255,.04);
  border-radius: 6px;
  overflow: hidden;
  border: 1px solid var(--line, #222838);
}
.byorg-bar__track i {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, #ff5b6a, #ff8a4a);
  border-radius: 6px;
}
.byorg-bar__sum { font-weight: 800; font-size: 13px; color: #ff5b6a; }

/* ── Table ── */
.fines-table-wrap {
  background: linear-gradient(180deg, var(--panel, #141823), var(--bg-2, #0f131c));
  border: 1px solid var(--line, #222838);
  border-radius: 16px;
  overflow: hidden;
}

.fines-table-head {
  padding: 16px 20px;
  border-bottom: 1px solid var(--line, #222838);
}
.fines-table-head__title {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: var(--text, #e9edf5);
}
.fines-table-head__count {
  background: rgba(106,166,255,.15);
  color: #6aa6ff;
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 999px;
}

.fines-table-scroll { overflow-x: auto; }

.fines-table {
  width: 100%;
  border-collapse: collapse;
}
.fines-table thead th {
  text-align: left;
  padding: 11px 18px;
  font-size: 11px;
  letter-spacing: 0.4px;
  text-transform: uppercase;
  color: var(--muted, #8a93a8);
  font-weight: 700;
  border-bottom: 1px solid var(--line, #222838);
  background: rgba(255,255,255,.02);
  white-space: nowrap;
}
.fines-table tbody td {
  padding: 13px 18px;
  border-bottom: 1px solid var(--line, #222838);
  font-size: 13px;
  vertical-align: middle;
  color: var(--text, #e9edf5);
}
.fines-table tbody tr:hover { background: rgba(255,255,255,.02); }
.fines-table tbody tr:last-child td { border-bottom: 0; }

.fine-date { display: block; font-weight: 600; font-size: 13px; }
.fine-time { display: block; font-size: 11px; color: var(--muted, #8a93a8); margin-top: 1px; }

.fine-vehicle { display: flex; flex-direction: column; gap: 4px; }
.fine-vehicle__model { font-size: 11px; color: var(--muted, #8a93a8); }

.fine-driver { display: flex; align-items: center; gap: 8px; }
.fine-driver__name { font-weight: 600; font-size: 13px; }

.fine-violation { max-width: 180px; display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fine-location  { max-width: 160px; display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fine-amount { font-weight: 800; font-size: 14px; }

.fines-table-foot {
  padding: 12px 20px;
  color: var(--muted, #8a93a8);
  font-size: 12px;
  border-top: 1px solid var(--line, #222838);
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 6px;
}
.fines-table-foot b { color: var(--text, #e9edf5); }

/* ── Filters ── */
.filter-chip {
  display: inline-flex;
  align-items: center;
  padding: 5px 12px;
  border-radius: 999px;
  border: 1px solid var(--line-2, #2b3245);
  background: transparent;
  color: var(--muted, #8a93a8);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
  font-family: inherit;
}
.filter-chip:hover { color: var(--text, #e9edf5); border-color: var(--accent, #6aa6ff); }
.filter-chip--active {
  background: rgba(106,166,255,.15);
  border-color: rgba(106,166,255,.4);
  color: #6aa6ff;
}

.fines-search {
  padding: 6px 14px;
  border-radius: 10px;
  border: 1px solid var(--line-2, #2b3245);
  background: var(--bg-2, #0f131c);
  color: var(--text, #e9edf5);
  font-size: 13px;
  font-family: inherit;
  min-width: 240px;
  outline: none;
  transition: border-color 0.15s;
}
.fines-search:focus { border-color: var(--accent, #6aa6ff); }
.fines-search::placeholder { color: var(--muted, #8a93a8); }

/* Light theme */
.v-theme--light .fines-panel,
.v-theme--light .fines-table-wrap,
.v-theme--light .fines-podium-cell {
  background: #ffffff;
  border-color: #e2e6f0;
  color: #1a1d23;
}
.v-theme--light .fines-title,
.v-theme--light .fines-table-head__title { color: #1a1d23; }
.v-theme--light .fines-crumbs { color: #6b7280; }
.v-theme--light .fines-lead { color: #6b7280; }
.v-theme--light .fines-table thead th { color: #6b7280; background: #f9fafb; border-color: #e2e6f0; }
.v-theme--light .fines-table tbody td { color: #1a1d23; border-color: #e2e6f0; }
.v-theme--light .fines-table tbody tr:hover { background: #f9fafb; }
.v-theme--light .fines-table-foot { color: #6b7280; border-color: #e2e6f0; }
.v-theme--light .fines-table-foot b { color: #1a1d23; }
.v-theme--light .fines-table-head { border-color: #e2e6f0; }
.v-theme--light .filter-chip { border-color: #d1d5db; color: #6b7280; }
.v-theme--light .filter-chip:hover { color: #1a1d23; border-color: #6aa6ff; }
.v-theme--light .fines-search { background: #f9fafb; border-color: #d1d5db; color: #1a1d23; }
.v-theme--light .bytype-row { border-color: #e2e6f0; }
.v-theme--light .byorg-bar__track { background: rgba(0,0,0,.04); border-color: #e2e6f0; }
</style>
