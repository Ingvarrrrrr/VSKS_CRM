<template>
  <article class="fleet-card fleet-card--clickable" @click="goToCard" :style="orgAccentStyle">
    <!-- Hero: icon + status -->
    <div class="fleet-card__hero">
      <div class="fleet-card__veh-icon">
        <VehicleTypeIcon :type="vehicleType" :size="60" :style="{ color: vehicleColor }" />
      </div>
      <div class="fleet-card__hero-right">
        <div class="fleet-status" :class="statusClass">
          <span class="fleet-status__pulse"></span>
          {{ statusLabel }}
        </div>
        <span class="fleet-category-badge" :data-cat="category">
          {{ CATEGORY_LABEL[category] }}
        </span>
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
      <button class="fleet-action fleet-action--primary" @click.stop="createWaybill">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 11h6M9 15h6M9 7h6M5 4h14a1 1 0 0 1 1 1v15a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z"/></svg>
        Сформировать путевой лист
      </button>
      <button class="fleet-action" @click.stop="openHistoryDialog">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 7v6l4 2"/></svg>
        История
      </button>
      <button class="fleet-action" @click.stop="openMaintenanceDialog">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7h18M6 7v13h12V7"/></svg>
        ТО
      </button>
    </div>

    <!-- ─── Диалог: История перемещений ─── -->
    <v-dialog v-model="historyDialog" max-width="900" scrollable @click.stop>
      <v-card>
        <v-card-title class="d-flex align-center">
          <v-icon class="mr-2">mdi-history</v-icon>
          История перемещений · {{ vehicle.plate }}
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" @click="historyDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text style="max-height: 70vh">
          <div v-if="historyLoading" class="d-flex justify-center pa-6">
            <v-progress-circular indeterminate color="primary" />
          </div>
          <v-alert v-else-if="historyError" type="error" variant="tonal" :text="historyError" />
          <v-alert v-else-if="historyItems.length === 0" type="info" variant="tonal" text="История перемещений пуста" />
          <v-table v-else density="compact">
            <thead>
              <tr>
                <th>Дата</th>
                <th>Что менялось</th>
                <th>Откуда → Куда</th>
                <th>Основание</th>
                <th>Документ</th>
                <th>Комментарий</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in historyItems" :key="row.id">
                <td class="text-no-wrap">{{ fmtDateTime(row.changed_at) }}</td>
                <td>
                  <v-chip v-if="row.from_owner_org_id !== row.to_owner_org_id" size="x-small" color="warning" variant="tonal">
                    Собственник
                  </v-chip>
                  <v-chip v-else size="x-small" color="info" variant="tonal">
                    Эксплуатант
                  </v-chip>
                </td>
                <td>{{ row.from_assigned_text || '—' }} → {{ row.to_assigned_text || '—' }}</td>
                <td>{{ row.basis || '—' }}</td>
                <td>
                  <template v-if="row.doc_number">№ {{ row.doc_number }}</template>
                  <template v-if="row.doc_date"> от {{ fmtDate(row.doc_date) }}</template>
                  <template v-if="!row.doc_number && !row.doc_date">—</template>
                </td>
                <td>{{ row.comment || '—' }}</td>
              </tr>
            </tbody>
          </v-table>
        </v-card-text>
      </v-card>
    </v-dialog>

    <!-- ─── Диалог: История ТО ─── -->
    <v-dialog v-model="maintenanceDialog" max-width="900" scrollable @click.stop>
      <v-card>
        <v-card-title class="d-flex align-center">
          <v-icon class="mr-2">mdi-wrench</v-icon>
          История ТО · {{ vehicle.plate }}
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" @click="maintenanceDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text style="max-height: 70vh">
          <div v-if="maintenanceLoading" class="d-flex justify-center pa-6">
            <v-progress-circular indeterminate color="primary" />
          </div>
          <v-alert v-else-if="maintenanceError" type="error" variant="tonal" :text="maintenanceError" />
          <v-alert v-else-if="maintenanceItems.length === 0" type="info" variant="tonal" text="Записи о ТО/ремонтах отсутствуют" />
          <v-table v-else density="compact">
            <thead>
              <tr>
                <th>Дата</th>
                <th>Статус</th>
                <th>Описание</th>
                <th class="text-right">Пробег, км</th>
                <th class="text-right">Стоимость, ₽</th>
                <th>Исполнитель</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in maintenanceItems" :key="row.id">
                <td class="text-no-wrap">{{ fmtDate(row.date) }}</td>
                <td>
                  <v-chip size="x-small" :color="repairStatusColor(row.status)" variant="tonal">
                    {{ repairStatusLabel(row.status) }}
                  </v-chip>
                </td>
                <td style="min-width: 220px">{{ row.description || '—' }}</td>
                <td class="text-right">{{ row.mileage_at_repair?.toLocaleString('ru-RU') || '—' }}</td>
                <td class="text-right">{{ row.cost_amount ? Number(row.cost_amount).toLocaleString('ru-RU') : '—' }}</td>
                <td>{{ row.performed_by_name || '—' }}</td>
              </tr>
            </tbody>
          </v-table>
        </v-card-text>
      </v-card>
    </v-dialog>
  </article>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch } from '@/api'
import LicensePlate from '@/components/vehicles/LicensePlate.vue'
import VehicleTypeIcon from '@/components/vehicles/VehicleTypeIcon.vue'
import { vehicleCategory, CATEGORY_LABEL } from '@/utils/vehicleCategory'

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
  owner_org_color?: string | null
  assigned_org_name?: string
  assigned_org_color?: string | null
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

const router = useRouter()

function goToCard() {
  if (props.vehicle.id) router.push(`/fleet/vehicles/${props.vehicle.id}`)
}
function createWaybill() {
  if (props.vehicle.id) router.push(`/fleet/waybills/new?vehicle_id=${props.vehicle.id}`)
}

// ── Диалог «История перемещений» ─────────────────────────────────────────────
interface TransferHistoryRow {
  id: number
  changed_at: string
  from_owner_org_id?: number | null
  to_owner_org_id?: number | null
  from_owner_org_name?: string | null
  to_owner_org_name?: string | null
  from_assigned_org_id?: number | null
  to_assigned_org_id?: number | null
  from_assigned_org_name?: string | null
  to_assigned_org_name?: string | null
  from_assigned_text?: string | null
  to_assigned_text?: string | null
  basis?: string | null
  doc_number?: string | null
  doc_date?: string | null
  comment?: string | null
}
const historyDialog = ref(false)
const historyLoading = ref(false)
const historyError = ref<string | null>(null)
const historyItems = ref<TransferHistoryRow[]>([])

async function openHistoryDialog() {
  if (!props.vehicle.id) return
  historyDialog.value = true
  historyLoading.value = true
  historyError.value = null
  historyItems.value = []
  try {
    const data = await apiFetch<TransferHistoryRow[]>(`/vehicles/${props.vehicle.id}/transfer-history`)
    historyItems.value = data || []
  } catch (e: any) {
    historyError.value = e?.payload?.message || e?.message || 'Не удалось загрузить историю перемещений'
  } finally {
    historyLoading.value = false
  }
}

// ── Диалог «История ТО» ──────────────────────────────────────────────────────
interface RepairRow {
  id: number
  date: string
  description?: string | null
  status: string
  mileage_at_repair?: number | null
  cost_amount?: number | string | null
  performed_by_name?: string | null
}
const maintenanceDialog = ref(false)
const maintenanceLoading = ref(false)
const maintenanceError = ref<string | null>(null)
const maintenanceItems = ref<RepairRow[]>([])

async function openMaintenanceDialog() {
  if (!props.vehicle.id) return
  maintenanceDialog.value = true
  maintenanceLoading.value = true
  maintenanceError.value = null
  maintenanceItems.value = []
  try {
    const data = await apiFetch<RepairRow[]>(`/vehicle-repairs?vehicle_id=${props.vehicle.id}`)
    maintenanceItems.value = data || []
  } catch (e: any) {
    maintenanceError.value = e?.payload?.message || e?.message || 'Не удалось загрузить историю ТО'
  } finally {
    maintenanceLoading.value = false
  }
}

const REPAIR_STATUS_LABEL: Record<string, string> = {
  planned: 'Запланирован',
  in_progress: 'В работе',
  done: 'Выполнен',
  cancelled: 'Отменён',
}
const REPAIR_STATUS_COLOR: Record<string, string> = {
  planned: 'info',
  in_progress: 'warning',
  done: 'success',
  cancelled: 'grey',
}
function repairStatusLabel(s: string): string {
  return REPAIR_STATUS_LABEL[s] || s
}
function repairStatusColor(s: string): string {
  return REPAIR_STATUS_COLOR[s] || 'grey'
}

function fmtDateTime(value: string): string {
  if (!value) return '—'
  try {
    const d = new Date(value)
    return d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' })
  } catch {
    return value
  }
}

// ── Vehicle type helpers ─────────────────────────────────────────────────────
const vehicleType = computed(() => props.vehicle.type || '')
const category = computed(() => vehicleCategory(props.vehicle.type))

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

const orgColor = computed<string | null>(() =>
  props.vehicle.assigned_org_color || props.vehicle.owner_org_color || null
)

const orgAccentStyle = computed(() =>
  orgColor.value ? { '--org-accent': orgColor.value } : {}
)

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
  border-left: 4px solid var(--org-accent, var(--line));
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

.fleet-card--clickable {
  cursor: pointer;
}

.fleet-card--clickable:hover {
  transform: translateY(-3px);
  box-shadow: 0 8px 24px rgba(0,0,0,0.18);
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

.fleet-card__hero-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
}

/* Category badge */
.fleet-category-badge {
  display: inline-flex;
  align-items: center;
  padding: 3px 8px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .3px;
  text-transform: uppercase;
  background: rgba(255,255,255,.06);
  border: 1px solid var(--line-2);
  color: var(--muted);
}
.fleet-category-badge[data-cat="light"]     { background: rgba(106,166,255,.12); border-color: rgba(106,166,255,.3); color: #6aa6ff; }
.fleet-category-badge[data-cat="truck"]     { background: rgba(146,100,60,.15);  border-color: rgba(146,100,60,.35);  color: #c8956a; }
.fleet-category-badge[data-cat="passenger"] { background: rgba(93,208,255,.12);  border-color: rgba(93,208,255,.3);  color: #5dd0ff; }
.fleet-category-badge[data-cat="special"]   { background: rgba(246,179,74,.12);  border-color: rgba(246,179,74,.3);  color: #f6b34a; }
.fleet-category-badge[data-cat="other"]     { background: rgba(255,255,255,.04); border-color: var(--line);          color: var(--muted-2); }

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
  /* auto-fill: при узкой карточке (<~280px) items перенесутся в 2+ строк вместо обрезания */
  grid-template-columns: repeat(auto-fill, minmax(72px, 1fr));
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
  gap: 4px;
  /* не позволяем flex/grid растягивать или обрезать item */
  min-width: 0;
  overflow: hidden;
}

.fleet-check-item__l {
  font-size: 11px;
  color: var(--muted);
  font-weight: 600;
  /* обрезаем только текст label, но не весь chip */
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
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
  grid-template-columns: 2fr 1fr 1fr;
  gap: 6px;
  padding: 14px;
  margin-top: 14px;
  border-top: 1px solid var(--line);
}

.fleet-action--primary {
  flex-direction: row !important;
  gap: 8px !important;
  background: linear-gradient(135deg, #14b8a6, #0891b2) !important;
  color: #fff !important;
  border-color: transparent !important;
  font-size: 12px !important;
}
.fleet-action--primary:hover {
  background: linear-gradient(135deg, #0d9488, #0e7490) !important;
  color: #fff !important;
}
.fleet-action--primary svg {
  width: 18px;
  height: 18px;
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
