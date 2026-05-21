<template>
  <article class="fleet-card" @click="emit('click', vehicle)">
    <!-- Hero: icon + status -->
    <div class="fleet-card__hero">
      <div class="fleet-card__veh-icon">
        <!-- Грузовик: truck_van / truck_board / truck_tank / truck_metal -->
        <svg viewBox="0 0 90 50" fill="none" v-if="isTruck">
          <rect x="4" y="14" width="50" height="22" rx="2" :fill="vehicleColor" opacity=".85"/>
          <rect x="54" y="20" width="24" height="16" rx="2" :fill="vehicleColor"/>
          <rect x="58" y="22" width="16" height="7" rx="1" fill="currentColor"/>
          <circle cx="14" cy="40" r="5" fill="currentColor"/><circle cx="14" cy="40" r="2" :fill="vehicleColor"/>
          <circle cx="30" cy="40" r="5" fill="currentColor"/><circle cx="30" cy="40" r="2" :fill="vehicleColor"/>
          <circle cx="46" cy="40" r="5" fill="currentColor"/><circle cx="46" cy="40" r="2" :fill="vehicleColor"/>
          <circle cx="66" cy="40" r="5" fill="currentColor"/><circle cx="66" cy="40" r="2" :fill="vehicleColor"/>
        </svg>
        <!-- Минивэн -->
        <svg viewBox="0 0 90 50" fill="none" v-else-if="vehicleType === 'minivan'">
          <rect x="8" y="14" width="74" height="24" rx="3" :fill="vehicleColor" opacity=".85"/>
          <rect x="14" y="18" width="14" height="9" rx="1" fill="currentColor"/>
          <rect x="32" y="18" width="14" height="9" rx="1" fill="currentColor"/>
          <rect x="50" y="18" width="14" height="9" rx="1" fill="currentColor"/>
          <rect x="66" y="18" width="10" height="9" rx="1" fill="currentColor"/>
          <circle cx="22" cy="40" r="5" fill="currentColor"/><circle cx="22" cy="40" r="2" :fill="vehicleColor"/>
          <circle cx="66" cy="40" r="5" fill="currentColor"/><circle cx="66" cy="40" r="2" :fill="vehicleColor"/>
          <path d="M8 38 Q8 44 22 44 L66 44 Q82 44 82 38" :fill="vehicleColor" opacity=".3"/>
        </svg>
        <!-- Автобус: bus -->
        <svg viewBox="0 0 90 50" fill="none" v-else-if="vehicleType === 'bus'">
          <rect x="4" y="10" width="82" height="28" rx="3" :fill="vehicleColor" opacity=".9"/>
          <rect x="8" y="14" width="10" height="8" rx="1" fill="currentColor"/>
          <rect x="22" y="14" width="10" height="8" rx="1" fill="currentColor"/>
          <rect x="36" y="14" width="10" height="8" rx="1" fill="currentColor"/>
          <rect x="50" y="14" width="10" height="8" rx="1" fill="currentColor"/>
          <rect x="64" y="14" width="10" height="8" rx="1" fill="currentColor"/>
          <rect x="78" y="14" width="6" height="8" rx="1" fill="currentColor"/>
          <circle cx="18" cy="40" r="5" fill="currentColor"/><circle cx="18" cy="40" r="2" :fill="vehicleColor"/>
          <circle cx="70" cy="40" r="5" fill="currentColor"/><circle cx="70" cy="40" r="2" :fill="vehicleColor"/>
        </svg>
        <!-- Квадроцикл -->
        <svg viewBox="0 0 90 50" fill="none" v-else-if="vehicleType === 'quadbike'">
          <rect x="28" y="16" width="34" height="14" rx="4" :fill="vehicleColor" opacity=".9"/>
          <path d="M22 24 L28 20 L28 28 Z" :fill="vehicleColor" opacity=".7"/>
          <path d="M62 20 L68 24 L62 28 Z" :fill="vehicleColor" opacity=".7"/>
          <rect x="34" y="12" width="22" height="8" rx="3" :fill="vehicleColor" opacity=".6"/>
          <circle cx="18" cy="34" r="8" fill="currentColor" stroke-width="2" :stroke="vehicleColor"/>
          <circle cx="18" cy="34" r="3" :fill="vehicleColor"/>
          <circle cx="72" cy="34" r="8" fill="currentColor" stroke-width="2" :stroke="vehicleColor"/>
          <circle cx="72" cy="34" r="3" :fill="vehicleColor"/>
        </svg>
        <!-- Снегоход -->
        <svg viewBox="0 0 90 50" fill="none" v-else-if="vehicleType === 'snowmobile'">
          <rect x="10" y="20" width="60" height="12" rx="6" :fill="vehicleColor" opacity=".85"/>
          <path d="M16 20 L26 10 L50 10 L60 20" :fill="vehicleColor" opacity=".7"/>
          <rect x="14" y="12" width="18" height="6" rx="2" fill="currentColor"/>
          <rect x="4" y="34" width="60" height="6" rx="3" :fill="vehicleColor" opacity=".5"/>
          <circle cx="68" cy="30" r="8" fill="currentColor" stroke-width="2" :stroke="vehicleColor"/>
          <circle cx="68" cy="30" r="3" :fill="vehicleColor"/>
        </svg>
        <!-- Лодка / моторная лодка -->
        <svg viewBox="0 0 90 50" fill="none" v-else-if="vehicleType === 'boat' || vehicleType === 'boat_motor'">
          <path d="M10 30 Q10 22 20 22 L70 22 Q80 22 80 30 L75 38 Q45 42 15 38 Z" :fill="vehicleColor" opacity=".85"/>
          <path d="M30 22 L35 10 L55 10 L60 22" :fill="vehicleColor" opacity=".5"/>
          <rect x="34" y="10" width="22" height="5" rx="2" fill="currentColor" opacity=".8"/>
          <template v-if="vehicleType === 'boat_motor'">
            <rect x="74" y="24" width="6" height="12" rx="2" :fill="vehicleColor" opacity=".9"/>
            <path d="M72 36 Q78 40 84 36" :stroke="vehicleColor" stroke-width="2" fill="none" opacity=".8"/>
          </template>
        </svg>
        <!-- Прицеп -->
        <svg viewBox="0 0 90 50" fill="none" v-else-if="vehicleType === 'trailer'">
          <rect x="12" y="16" width="66" height="22" rx="2" :fill="vehicleColor" opacity=".8"/>
          <line x1="8" y1="27" x2="12" y2="27" :stroke="vehicleColor" stroke-width="3"/>
          <circle cx="30" cy="40" r="6" fill="currentColor" stroke-width="2" :stroke="vehicleColor"/>
          <circle cx="30" cy="40" r="2" :fill="vehicleColor"/>
          <circle cx="62" cy="40" r="6" fill="currentColor" stroke-width="2" :stroke="vehicleColor"/>
          <circle cx="62" cy="40" r="2" :fill="vehicleColor"/>
          <rect x="18" y="20" width="10" height="6" rx="1" fill="currentColor" opacity=".6"/>
          <rect x="34" y="20" width="10" height="6" rx="1" fill="currentColor" opacity=".6"/>
          <rect x="50" y="20" width="10" height="6" rx="1" fill="currentColor" opacity=".6"/>
        </svg>
        <!-- Спецтехника -->
        <svg viewBox="0 0 90 50" fill="none" v-else-if="vehicleType === 'special'">
          <rect x="4" y="16" width="50" height="22" rx="2" :fill="vehicleColor" opacity=".85"/>
          <rect x="54" y="20" width="24" height="16" rx="2" :fill="vehicleColor"/>
          <rect x="58" y="22" width="16" height="7" rx="1" fill="currentColor"/>
          <rect x="26" y="10" width="12" height="8" rx="1" :fill="vehicleColor" opacity=".7"/>
          <line x1="32" y1="10" x2="32" y2="6" :stroke="vehicleColor" stroke-width="2"/>
          <circle cx="14" cy="40" r="6" fill="currentColor" stroke-width="2" :stroke="vehicleColor"/>
          <circle cx="14" cy="40" r="2" :fill="vehicleColor"/>
          <circle cx="40" cy="40" r="6" fill="currentColor" stroke-width="2" :stroke="vehicleColor"/>
          <circle cx="40" cy="40" r="2" :fill="vehicleColor"/>
          <circle cx="66" cy="40" r="5" fill="currentColor"/><circle cx="66" cy="40" r="2" :fill="vehicleColor"/>
        </svg>
        <!-- Легковой car_light (SUV-style) и default -->
        <svg viewBox="0 0 90 50" fill="none" v-else>
          <path d="M8 36 L14 28 Q22 20 38 20 L52 20 Q64 20 72 28 L82 32 L82 36 Z" :fill="vehicleColor" opacity=".9"/>
          <path d="M20 28 Q26 22 38 22 L41 22 L41 28 Z" fill="currentColor"/>
          <path d="M43 22 L52 22 Q62 22 68 28 L43 28 Z" fill="currentColor"/>
          <circle cx="24" cy="38" r="5" fill="currentColor"/><circle cx="24" cy="38" r="2" :fill="vehicleColor"/>
          <circle cx="64" cy="38" r="5" fill="currentColor"/><circle cx="64" cy="38" r="2" :fill="vehicleColor"/>
        </svg>
      </div>
      <div class="fleet-status" :class="statusClass">
        <span class="fleet-status__pulse"></span>
        {{ statusLabel }}
      </div>
    </div>

    <!-- Title block -->
    <div class="fleet-card__title">
      <LicensePlate :model-value="vehicle.plate" size="sm" />
      <div class="fleet-card__model">{{ modelYear }}</div>
      <div class="fleet-card__meta">{{ metaLine }}</div>
    </div>

    <!-- Responsible row -->
    <div class="fleet-card__resp" v-if="vehicle.responsible_name || vehicle.assigned_text">
      <div class="fleet-card__av" :style="{ background: avatarGradient }">{{ avatarInitials }}</div>
      <div>
        <div class="fleet-card__resp-name">{{ vehicle.responsible_name || 'Не закреплён' }}</div>
        <div class="fleet-card__resp-role">{{ vehicle.assigned_text || vehicle.assigned_org_name || '' }}</div>
      </div>
      <div class="fleet-card__resp-right" v-if="vehicle.last_report_at">
        <b>{{ fmtDate(vehicle.last_report_at) }}</b>последний отчёт
      </div>
    </div>

    <!-- Documents pills -->
    <div class="fleet-card__docs" v-if="vehicle.insurance_until || vehicle.sts_number">
      <span class="fleet-doc-pill" :class="insuranceClass" v-if="vehicle.insurance_until">
        ОСАГО до <b>{{ fmtDate(vehicle.insurance_until) }}</b>
      </span>
      <span class="fleet-doc-pill fleet-doc-pill--muted" v-if="vehicle.sts_number">
        СТС <b>{{ vehicle.sts_number }}</b>
      </span>
    </div>

    <!-- 4×2 Checklist -->
    <div class="fleet-card__check">
      <div class="fleet-check-item" :class="checkState(vehicle.akb_ok)">
        <span class="fleet-check-item__l">АКБ</span>
        <span class="fleet-check-item__v">{{ checkMark(vehicle.akb_ok) }}</span>
      </div>
      <div class="fleet-check-item" :class="checkState(vehicle.tires_ok)">
        <span class="fleet-check-item__l">Резина</span>
        <span class="fleet-check-item__v">{{ checkMark(vehicle.tires_ok) }}</span>
      </div>
      <div class="fleet-check-item" :class="checkState(vehicle.mirrors_ok)">
        <span class="fleet-check-item__l">Зеркала</span>
        <span class="fleet-check-item__v">{{ checkMark(vehicle.mirrors_ok) }}</span>
      </div>
      <div class="fleet-check-item" :class="checkState(vehicle.has_radio)">
        <span class="fleet-check-item__l">Радио</span>
        <span class="fleet-check-item__v">{{ checkMark(vehicle.has_radio) }}</span>
      </div>
      <div class="fleet-check-item" :class="checkState(vehicle.first_aid_kit_ok)">
        <span class="fleet-check-item__l">Аптечка</span>
        <span class="fleet-check-item__v">{{ checkMark(vehicle.first_aid_kit_ok) }}</span>
      </div>
      <div class="fleet-check-item" :class="checkState(vehicle.fire_ext_ok)">
        <span class="fleet-check-item__l">Огнет.</span>
        <span class="fleet-check-item__v">{{ checkMark(vehicle.fire_ext_ok) }}</span>
      </div>
      <div class="fleet-check-item" :class="checkState(vehicle.spare_wheel_ok)">
        <span class="fleet-check-item__l">Запаска</span>
        <span class="fleet-check-item__v">{{ checkMark(vehicle.spare_wheel_ok) }}</span>
      </div>
      <div class="fleet-check-item" :class="checkState(vehicle.paint_ok)">
        <span class="fleet-check-item__l">ЛКП</span>
        <span class="fleet-check-item__v">{{ checkMark(vehicle.paint_ok) }}</span>
      </div>
    </div>

    <!-- Stats row -->
    <div class="fleet-card__stats">
      <div class="fleet-stat">
        <div class="fleet-stat__label">Пробег</div>
        <div class="fleet-stat__value">{{ vehicle.odometer_km ? vehicle.odometer_km.toLocaleString('ru-RU') + ' км' : '— км' }}</div>
      </div>
      <div class="fleet-stat">
        <div class="fleet-stat__label">Последнее ТО</div>
        <div class="fleet-stat__value">{{ vehicle.last_maintenance_at ? fmtDate(vehicle.last_maintenance_at) : 'не отмечено' }}</div>
      </div>
      <div class="fleet-stat">
        <div class="fleet-stat__label">VIN</div>
        <div class="fleet-stat__value fleet-stat__value--mono">{{ vehicle.vin || '—' }}</div>
      </div>
    </div>

    <!-- Notes -->
    <div class="fleet-card__notes" v-if="vehicle.technical_state_note">
      <b>Тех. состояние:</b> {{ vehicle.technical_state_note }}
    </div>

    <!-- Actions -->
    <div class="fleet-card__actions">
      <button class="fleet-action" @click.stop="emit('action', { type: 'card', vehicle })">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg>
        Карточка
      </button>
      <button class="fleet-action" @click.stop="emit('action', { type: 'history', vehicle })">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 7v6l4 2"/></svg>
        История
      </button>
      <button class="fleet-action" @click.stop="emit('action', { type: 'maintenance', vehicle })">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7h18M6 7v13h12V7"/></svg>
        ТО
      </button>
      <button class="fleet-action" @click.stop="emit('detail', vehicle)">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 11.5a8.4 8.4 0 1 1-16.8 0 8.4 8.4 0 0 1 16.8 0z"/><path d="M22 22l-3-3"/></svg>
        Подробно
      </button>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import LicensePlate from '@/components/vehicles/LicensePlate.vue'

interface VehicleCardData {
  id?: number
  plate: string
  brand?: string
  model?: string
  year?: number
  color?: string
  type?: string
  state?: string
  vin?: string
  owner_org_name?: string
  assigned_org_name?: string
  assigned_text?: string
  responsible_name?: string
  last_report_at?: string
  insurance_until?: string
  sts_number?: string
  odometer_km?: number
  last_maintenance_at?: string
  technical_state_note?: string
  // Checklist booleans
  akb_ok?: boolean | null
  tires_ok?: boolean | null
  mirrors_ok?: boolean | null
  has_radio?: boolean | null
  first_aid_kit_ok?: boolean | null
  fire_ext_ok?: boolean | null
  spare_wheel_ok?: boolean | null
  paint_ok?: boolean | null
}

const props = defineProps<{ vehicle: VehicleCardData }>()
const emit = defineEmits<{
  (e: 'click', v: VehicleCardData): void
  (e: 'detail', v: VehicleCardData): void
  (e: 'action', payload: { type: string; vehicle: VehicleCardData }): void
}>()

// ── Vehicle type helpers ─────────────────────────────────────────────────────
const TRUCK_TYPES = ['truck_van', 'truck_board', 'truck_tank', 'truck_metal']

const vehicleType = computed(() => props.vehicle.type || '')
const isTruck = computed(() => TRUCK_TYPES.includes(vehicleType.value))

const vehicleColor = computed(() => {
  switch (props.vehicle.state) {
    case 'working': return '#22c997'
    case 'in_repair':
    case 'needs_repair': return '#f6b34a'
    case 'broken':
    case 'destroyed':
    case 'utilized': return '#ff5b6a'
    default: return '#6aa6ff'
  }
})

// ── Status ───────────────────────────────────────────────────────────────────
const STATUS_MAP: Record<string, { label: string; cls: string }> = {
  working: { label: 'Рабочее', cls: 'fleet-status--ok' },
  in_repair: { label: 'В ремонте', cls: 'fleet-status--warn' },
  broken: { label: 'Не на ходу', cls: 'fleet-status--alert' },
  needs_repair: { label: 'Замечания', cls: 'fleet-status--warn' },
  destroyed: { label: 'Списан', cls: 'fleet-status--muted' },
  utilized: { label: 'Утилизирован', cls: 'fleet-status--muted' },
}

const statusLabel = computed(() => STATUS_MAP[props.vehicle.state || '']?.label || 'Неизвестно')
const statusClass = computed(() => STATUS_MAP[props.vehicle.state || '']?.cls || 'fleet-status--muted')

// ── Display helpers ──────────────────────────────────────────────────────────
const modelYear = computed(() => {
  const parts = [props.vehicle.brand, props.vehicle.model].filter(Boolean)
  const base = parts.join(' ')
  return props.vehicle.year ? `${base} · ${props.vehicle.year}` : base
})

const metaLine = computed(() => {
  const parts = [
    props.vehicle.type,
    props.vehicle.color,
    props.vehicle.owner_org_name,
    props.vehicle.assigned_text,
  ].filter(Boolean)
  return parts.join(' · ')
})

const avatarInitials = computed(() => {
  const name = props.vehicle.responsible_name || ''
  const parts = name.trim().split(/\s+/)
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
  if (parts[0]) return parts[0].slice(0, 2).toUpperCase()
  return '—'
})

const GRADIENTS = [
  'linear-gradient(135deg,#22c997,#5dd0ff)',
  'linear-gradient(135deg,#6aa6ff,#8b5cf6)',
  'linear-gradient(135deg,#f6b34a,#ff8a4a)',
  'linear-gradient(135deg,#8b5cf6,#5dd0ff)',
  'linear-gradient(135deg,#ff5b6a,#ff8a4a)',
]
const avatarGradient = computed(() => {
  const idx = (props.vehicle.id || 0) % GRADIENTS.length
  return GRADIENTS[idx]
})

function fmtDate(value: string): string {
  if (!value) return '—'
  try {
    const d = new Date(value)
    return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit' })
  } catch {
    return value
  }
}

const insuranceClass = computed(() => {
  if (!props.vehicle.insurance_until) return 'fleet-doc-pill--muted'
  const d = new Date(props.vehicle.insurance_until)
  const today = new Date()
  const diff = (d.getTime() - today.getTime()) / 86400000
  if (diff < 0) return 'fleet-doc-pill--alert'
  if (diff < 60) return 'fleet-doc-pill--warn'
  return 'fleet-doc-pill--ok'
})

// ── Checklist helpers ────────────────────────────────────────────────────────
function checkMark(val: boolean | null | undefined): string {
  if (val === true) return '✓'
  if (val === false) return '✕'
  return '—'
}
function checkState(val: boolean | null | undefined): string {
  if (val === true) return 'fleet-check-item--ok'
  if (val === false) return 'fleet-check-item--alert'
  return 'fleet-check-item--muted'
}
</script>

<style scoped>
/* Design tokens — dark theme */
.v-theme--dark .fleet-card {
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
  --ok: #22c997;
  --warn: #f6b34a;
  --alert: #ff5b6a;
  --info: #5dd0ff;
  --icon-bg-top: #1a2030;
  --icon-bg-bot: #11151f;
  --card-icon-detail: #0a0d14;
  --avatar-text: #0a0d14;
  --avatar-bg: linear-gradient(135deg, #6366f1, #8b5cf6);
  --success-bg: rgba(34,201,151,.08); --success-fg: #a8efd2;
  --warning-bg: rgba(246,179,74,.08); --warning-fg: #fcd998;
  --error-bg: rgba(255,91,106,.08); --error-fg: #ffaab2;
}

/* Design tokens — light theme */
.v-theme--light .fleet-card {
  --bg: #ffffff;
  --bg-2: #f5f7fa;
  --panel: #ffffff;
  --panel-2: #f1f4fa;
  --line: #e0e3e8;
  --line-2: #cdd3e1;
  --text: #1a1d23;
  --muted: #6b7280;
  --muted-2: #94a3b8;
  --accent: #2563eb;
  --ok: #059669;
  --warn: #d97706;
  --alert: #dc2626;
  --info: #0284c7;
  --icon-bg-top: #e8eaf0;
  --icon-bg-bot: #d8dce4;
  --card-icon-detail: #1a1d23;
  --avatar-text: #ffffff;
  --avatar-bg: linear-gradient(135deg, #6366f1, #8b5cf6);
  --success-bg: #d1fae5; --success-fg: #047857;
  --warning-bg: #fef3c7; --warning-fg: #92400e;
  --error-bg: #fee2e2; --error-fg: #b91c1c;
}

/* Fallback tokens for when no theme class is present (dark default) */
.fleet-card {
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
  --ok: #22c997;
  --warn: #f6b34a;
  --alert: #ff5b6a;
  --info: #5dd0ff;
  --icon-bg-top: #1a2030;
  --icon-bg-bot: #11151f;
  --card-icon-detail: #0a0d14;
  --avatar-text: #0a0d14;
  --avatar-bg: linear-gradient(135deg, #6366f1, #8b5cf6);
  --success-bg: rgba(34,201,151,.08); --success-fg: #a8efd2;
  --warning-bg: rgba(246,179,74,.08); --warning-fg: #fcd998;
  --error-bg: rgba(255,91,106,.08); --error-fg: #ffaab2;

  position: relative;
  background: linear-gradient(180deg, var(--panel), var(--bg-2));
  border: 1px solid var(--line);
  border-radius: 18px;
  overflow: hidden;
  transition: transform .15s ease, border-color .15s ease;
  cursor: pointer;
  color: var(--text);
  font-family: 'Inter', system-ui, -apple-system, sans-serif;
  font-size: 13px;
}

.fleet-card:hover {
  transform: translateY(-2px);
  border-color: var(--line-2);
}

/* Hero */
.fleet-card__hero {
  position: relative;
  padding: 16px 16px 0;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.fleet-card__veh-icon {
  width: 96px;
  height: 60px;
  border-radius: 12px;
  background: radial-gradient(120px 60px at 30% 30%, rgba(106,166,255,.25), transparent 70%),
              linear-gradient(180deg, var(--icon-bg-top), var(--icon-bg-bot));
  border: 1px solid var(--line);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--card-icon-detail);
}

.fleet-card__veh-icon svg {
  width: 78px;
  height: 42px;
}

/* Status pill */
.fleet-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .3px;
  text-transform: uppercase;
}

.fleet-status__pulse {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  display: inline-block;
}

.fleet-status--ok {
  color: var(--ok);
  background: rgba(34,201,151,.1);
  border: 1px solid rgba(34,201,151,.25);
}
.fleet-status--ok .fleet-status__pulse { background: var(--ok); }

.fleet-status--warn {
  color: var(--warn);
  background: rgba(246,179,74,.1);
  border: 1px solid rgba(246,179,74,.25);
}
.fleet-status--warn .fleet-status__pulse { background: var(--warn); }

.fleet-status--alert {
  color: var(--alert);
  background: rgba(255,91,106,.1);
  border: 1px solid rgba(255,91,106,.25);
}
.fleet-status--alert .fleet-status__pulse { background: var(--alert); }

.fleet-status--muted {
  color: var(--muted);
  background: rgba(255,255,255,.04);
  border: 1px solid var(--line-2);
}
.fleet-status--muted .fleet-status__pulse { background: var(--muted); }

/* Title */
.fleet-card__title {
  padding: 14px 16px 6px;
}


.fleet-card__model {
  margin-top: 10px;
  font-weight: 700;
  font-size: 16px;
  color: var(--text);
}

.fleet-card__meta {
  margin-top: 2px;
  color: var(--muted);
  font-size: 12.5px;
}

/* Responsible */
.fleet-card__resp {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 12px 16px 0;
  padding: 10px 12px;
  background: rgba(255,255,255,.02);
  border: 1px solid var(--line);
  border-radius: 12px;
}

.fleet-card__av {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  color: var(--avatar-text);
  font-size: 12px;
  flex-shrink: 0;
}

.fleet-card__resp-name {
  font-weight: 600;
  font-size: 13px;
  color: var(--text);
}

.fleet-card__resp-role {
  color: var(--muted);
  font-size: 12px;
}

.fleet-card__resp-right {
  margin-left: auto;
  text-align: right;
  font-size: 12px;
  color: var(--muted);
}

.fleet-card__resp-right b {
  color: var(--text);
  font-weight: 600;
  display: block;
}

/* Documents */
.fleet-card__docs {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 16px 0;
  flex-wrap: wrap;
}

.fleet-doc-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 9px;
  border-radius: 999px;
  background: rgba(255,255,255,.03);
  border: 1px solid var(--line);
  font-weight: 600;
  font-size: 11.5px;
  color: var(--muted);
}

.fleet-doc-pill b { color: var(--text); font-weight: 700; }

.fleet-doc-pill--ok {
  background: var(--success-bg);
  border-color: rgba(34,201,151,.25);
  color: var(--success-fg);
}
.fleet-doc-pill--ok b { color: var(--ok); }

.fleet-doc-pill--warn {
  background: var(--warning-bg);
  border-color: rgba(246,179,74,.25);
  color: var(--warning-fg);
}
.fleet-doc-pill--warn b { color: var(--warn); }

.fleet-doc-pill--alert {
  background: var(--error-bg);
  border-color: rgba(255,91,106,.25);
  color: var(--error-fg);
}
.fleet-doc-pill--alert b { color: var(--alert); }

.fleet-doc-pill--muted {
  color: var(--muted);
}

/* Checklist */
.fleet-card__check {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  padding: 12px 16px 0;
}

.fleet-check-item {
  background: rgba(255,255,255,.02);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 8px 9px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.fleet-check-item__l {
  font-size: 11px;
  color: var(--muted);
  font-weight: 600;
}

.fleet-check-item__v {
  font-weight: 800;
  font-size: 13px;
  width: 20px;
  height: 20px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.fleet-check-item--ok .fleet-check-item__v {
  background: rgba(34,201,151,.18);
  color: var(--ok);
}

.fleet-check-item--alert .fleet-check-item__v {
  background: rgba(255,91,106,.18);
  color: var(--alert);
}

.fleet-check-item--muted .fleet-check-item__v {
  background: rgba(255,255,255,.06);
  color: var(--muted-2);
}

/* Stats */
.fleet-card__stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  padding: 14px 16px 0;
  gap: 6px;
}

.fleet-stat__label {
  font-size: 11px;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: .4px;
  font-weight: 600;
}

.fleet-stat__value {
  font-weight: 700;
  margin-top: 4px;
  font-size: 13.5px;
  color: var(--text);
}

.fleet-stat__value--mono {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 11.5px;
}

/* Notes */
.fleet-card__notes {
  padding: 10px 16px 0;
  color: var(--muted);
  font-size: 12px;
  font-style: italic;
  line-height: 1.4;
}

.fleet-card__notes b {
  color: var(--text);
  font-style: normal;
}

/* Actions */
.fleet-card__actions {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 6px;
  padding: 14px;
  margin-top: 14px;
  border-top: 1px solid var(--line);
}

.fleet-action {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 9px 6px;
  border-radius: 10px;
  background: transparent;
  border: 1px solid transparent;
  color: var(--muted);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: color .12s, background .12s, border-color .12s;
}

.fleet-action:hover {
  color: var(--text);
  background: rgba(255,255,255,.03);
  border-color: var(--line);
}

.fleet-action svg {
  width: 16px;
  height: 16px;
}
</style>
