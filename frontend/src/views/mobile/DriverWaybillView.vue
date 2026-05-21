<template>
  <div class="dwv">
    <!-- Loading -->
    <div v-if="loading" class="dwv__loading">
      <v-progress-circular indeterminate color="primary" size="40" />
      <p>Загрузка путевого листа…</p>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="dwv__error">
      <v-icon icon="mdi-alert-circle-outline" size="48" color="error" />
      <p>{{ error }}</p>
      <v-btn variant="outlined" size="small" @click="loadWaybill">Повторить</v-btn>
    </div>

    <!-- Content -->
    <template v-else-if="waybill">
      <!-- App header -->
      <div class="dwv__header">
        <button class="dwv__back" @click="router.back()">‹</button>
        <div class="dwv__header-title">{{ screenTitle }}</div>
        <div class="dwv__header-r">⋯</div>
      </div>

      <!-- ==================== SCREEN 1: Получение ==================== -->
      <template v-if="currentScreen === 1">
        <div class="dwv__body">
          <!-- Notification banner -->
          <div class="dwv__notif">
            <div class="dwv__notif-ic">📋</div>
            <div class="dwv__notif-t">
              <b>Новый путевой лист от диспетчера</b>
              <span>{{ waybill.dispatcher_name ?? 'Диспетчер' }}</span>
            </div>
          </div>

          <!-- Hero card -->
          <div class="dwv__hero">
            <div class="dwv__hero-num">№ {{ waybill.number ?? waybill.id }}</div>
            <div class="dwv__hero-tit">{{ heroRoute }}</div>
            <div class="dwv__hero-row">
              <span>Дата выезда</span><b>{{ fmt(waybill.date_start) }}</b>
            </div>
            <div class="dwv__hero-row">
              <span>Возврат</span><b>{{ fmt(waybill.date_end) }}</b>
            </div>
            <div class="dwv__hero-row">
              <span>Пробег план.</span>
              <b>{{ waybill.planned_mileage_km != null ? waybill.planned_mileage_km + ' км' : '—' }}</b>
            </div>
            <div class="dwv__hero-row">
              <span>Топлива в баке</span>
              <b>
                {{ waybill.fuel_remaining_start != null ? waybill.fuel_remaining_start + ' л' : '—' }}
                {{ waybill.vehicle?.fuel_norm ? '/ ' + waybill.vehicle.fuel_norm + ' л' : '' }}
              </b>
            </div>
          </div>

          <!-- Vehicle card -->
          <div class="dwv__card" v-if="waybill.vehicle">
            <div class="dwv__card-title">Транспорт</div>
            <div class="dwv__veh">
              <div class="dwv__veh-icon">
                <VehicleTypeIcon :type="waybill.vehicle.vehicle_type" :size="56" />
              </div>
              <div class="dwv__veh-info">
                <LicensePlate :modelValue="waybill.vehicle.license_plate ?? ''" />
                <div class="dwv__veh-mod">
                  {{ waybill.vehicle.brand_model }}
                  {{ waybill.vehicle.year ? '· ' + waybill.vehicle.year + ' г.' : '' }}
                </div>
              </div>
            </div>
          </div>

          <!-- Route stops (readonly) -->
          <div class="dwv__card" v-if="waybill.route_stops?.length">
            <div class="dwv__card-title">Маршрут</div>
            <RouteStopsEditor :modelValue="waybill.route_stops" :readonly="true" />
          </div>

          <!-- Cargo -->
          <div class="dwv__card" v-if="waybill.cargo_description || waybill.cargo_weight_t">
            <div class="dwv__card-title">Груз</div>
            <div class="dwv__cargo-desc">
              {{ waybill.cargo_description }}
              <b v-if="waybill.cargo_weight_t"> · {{ waybill.cargo_weight_t }} т</b>
            </div>
          </div>
        </div>

        <!-- Sticky bottom: reject / accept -->
        <div class="dwv__stb">
          <button class="dwv__btn dwv__btn--out" style="flex:0 0 90px" @click="rejectWaybill">
            Отказ
          </button>
          <button class="dwv__btn" @click="acceptWaybill" :disabled="accepting">
            {{ accepting ? 'Принятие…' : 'Принять' }}
          </button>
        </div>
      </template>

      <!-- ==================== SCREEN 2: В дороге ==================== -->
      <template v-else-if="currentScreen === 2">
        <div class="dwv__body">
          <!-- Progress stepper -->
          <div class="dwv__card">
            <StageStepper :currentStage="waybill.status" />
          </div>

          <!-- Current status banner -->
          <div class="dwv__banner-active">
            <div>
              <div class="dwv__banner-label">Следующий пункт</div>
              <div class="dwv__banner-val">{{ nextStopName }}</div>
            </div>
            <StatusPill variant="ok" :dot="true">В пути</StatusPill>
          </div>

          <!-- Odometer readings per stop -->
          <div class="dwv__card">
            <div class="dwv__card-title">
              Показания на пунктах
              <span class="dwv__card-sub">{{ filledReadings }} из {{ waybill.route_stops?.length ?? 0 }}</span>
            </div>

            <div
              v-for="(stop, idx) in waybill.route_stops"
              :key="stop.id ?? idx"
              class="dwv__odo-stop"
            >
              <div class="dwv__odo-label">
                {{ stop.name }}
                <span v-if="stop.planned_time"> · {{ fmtTime(stop.planned_time) }}</span>
              </div>
              <div v-if="stopReading(stop)" class="dwv__odo-filled">
                {{ stopReading(stop)!.mileage_km.toLocaleString('ru-RU') }} км ✓
              </div>
              <div v-else class="dwv__odo-input">
                <OdometerField
                  v-model="pendingOdometer[stop.id ?? idx]"
                  label="Пробег"
                  :previousValue="lastOdometerValue"
                  @update:modelValue="(v) => onOdometerInput(stop, idx, v)"
                />
              </div>
            </div>
          </div>

          <!-- Fuel refills -->
          <div class="dwv__card">
            <div class="dwv__card-title">
              Заправки
              <span class="dwv__card-add" @click="openFuelDialog">+</span>
            </div>

            <div v-if="!waybill.fuel_refills?.length" class="dwv__empty-sub">Нет заправок</div>

            <div
              v-for="(refill, ri) in waybill.fuel_refills"
              :key="ri"
              class="dwv__refill-row"
            >
              <div>
                <div class="dwv__refill-name">{{ refill.station_name ?? 'АЗС' }}</div>
                <div class="dwv__refill-date">{{ fmtDateTime(refill.created_at) }}</div>
              </div>
              <div class="dwv__refill-right">
                <div class="dwv__refill-liters">{{ refill.liters }} л</div>
                <div class="dwv__refill-amount">
                  {{ refill.amount_rub != null ? refill.amount_rub.toLocaleString('ru-RU') + ' ₽' : '' }}
                </div>
              </div>
            </div>

            <button class="dwv__btn dwv__btn--out dwv__btn--sm" @click="openFuelDialog">
              + Прикрепить чек
            </button>
          </div>

          <!-- Photos (MVP placeholder) -->
          <div class="dwv__card">
            <div class="dwv__card-title">Фото с маршрута</div>
            <div class="dwv__photo-row">
              <div
                v-for="ph in routePhotos"
                :key="ph"
                class="dwv__photo-cell dwv__photo-cell--done"
              >✓</div>
              <label class="dwv__photo-cell dwv__photo-cell--add">
                <input
                  type="file"
                  accept="image/*"
                  capture="environment"
                  style="display:none"
                  @change="onPhotoAdd"
                />
                +
              </label>
            </div>
            <div class="dwv__photo-hint">Спидометр, чек с заправки, путевая документация</div>
          </div>

          <!-- Incidents -->
          <div class="dwv__card">
            <div class="dwv__card-title">Происшествия за смену</div>
            <div class="dwv__empty-sub">Нет инцидентов</div>
            <button class="dwv__btn dwv__btn--out dwv__btn--sm" @click="reportIncident">
              + Сообщить о происшествии
            </button>
          </div>

          <!-- Offline banner -->
          <div class="dwv__offline-banner">
            <v-icon icon="mdi-wifi-off" size="16" />
            <span>Связь не нужна — данные сохранятся и синхронизируются позже</span>
          </div>
        </div>

        <!-- Sticky bottom -->
        <div class="dwv__stb">
          <button class="dwv__btn" @click="saveProgress" :disabled="saving">
            {{ saving ? 'Сохранение…' : 'Зафиксировать показания' }}
          </button>
        </div>
      </template>

      <!-- ==================== SCREEN 3: Закрытие ==================== -->
      <template v-else-if="currentScreen === 3">
        <div class="dwv__body">
          <!-- Progress stepper -->
          <div class="dwv__card">
            <StageStepper :currentStage="waybill.status" />
          </div>

          <!-- Summary card -->
          <div class="dwv__banner-close">
            <div class="dwv__banner-label">Путевой лист № {{ waybill.number ?? waybill.id }}</div>
            <div class="dwv__banner-val">{{ heroRoute }}</div>
          </div>

          <!-- Stats grid 2×2 -->
          <div class="dwv__stats-grid">
            <div class="dwv__stat">
              <div class="dwv__stat-l">Пробег</div>
              <div class="dwv__stat-v">
                {{ waybill.actual_mileage_km != null ? waybill.actual_mileage_km : '—' }}
                <span class="dwv__stat-unit">км</span>
              </div>
              <div class="dwv__stat-s">по плану {{ waybill.planned_mileage_km ?? '—' }}</div>
            </div>
            <div class="dwv__stat">
              <div class="dwv__stat-l">Топливо</div>
              <div class="dwv__stat-v">
                {{ fuelConsumed != null ? fuelConsumed : '—' }}
                <span class="dwv__stat-unit">л</span>
              </div>
              <div class="dwv__stat-s">{{ fuelPer100 != null ? fuelPer100 + ' л/100км' : '' }}</div>
            </div>
            <div class="dwv__stat">
              <div class="dwv__stat-l">Длительность</div>
              <div class="dwv__stat-v">{{ tripDuration }}</div>
              <div class="dwv__stat-s">с перерывами</div>
            </div>
            <div class="dwv__stat">
              <div class="dwv__stat-l">Затраты</div>
              <div class="dwv__stat-v">
                {{ totalFuelCost != null ? totalFuelCost.toLocaleString('ru-RU') : '—' }}
                <span class="dwv__stat-unit">₽</span>
              </div>
              <div class="dwv__stat-s">{{ waybill.fuel_refills?.length ?? 0 }} заправок</div>
            </div>
          </div>

          <!-- Final odometer -->
          <div class="dwv__card">
            <div class="dwv__card-title">Спидометр при возврате</div>
            <OdometerField
              v-model="form.odometer_finish"
              label="Финальный пробег"
              :previousValue="waybill.odometer_start ?? undefined"
            />
            <div class="dwv__field-group">
              <div class="dwv__field-label">Остаток топлива в баке (л)</div>
              <v-text-field
                v-model.number="form.fuel_remaining_finish"
                type="number"
                variant="outlined"
                density="compact"
                hide-spin-buttons
                placeholder="0"
                prepend-inner-icon="mdi-gas-station"
              />
            </div>
          </div>

          <!-- Post-trip checklist -->
          <div class="dwv__card">
            <div class="dwv__card-title">
              Послерейсовый осмотр
              <StatusPill :variant="allChecksDone ? 'ok' : 'warn'" style="margin-left:8px">
                {{ allChecksDone ? 'все ок' : 'требует проверки' }}
              </StatusPill>
            </div>

            <div
              v-for="item in checklist"
              :key="item.key"
              class="dwv__chk-row"
            >
              <div class="dwv__chk-pills">
                <button
                  v-for="opt in checklistOpts"
                  :key="opt.value"
                  class="dwv__chk-pill"
                  :class="['dwv__chk-pill--' + opt.value, { 'dwv__chk-pill--active': item.state === opt.value }]"
                  @click="item.state = opt.value"
                >{{ opt.label }}</button>
              </div>
              <div class="dwv__chk-text">
                <div>{{ item.label }}</div>
                <div class="dwv__chk-hint">{{ item.hint }}</div>
              </div>
            </div>
          </div>

          <!-- Driver signature -->
          <div class="dwv__card">
            <div class="dwv__card-title">
              Подпись водителя
              <StatusPill v-if="form.signature" variant="ok" style="margin-left:8px">
                подписан
              </StatusPill>
            </div>
            <div class="dwv__sig-wrap">
              <SignaturePad v-model="form.signature" :width="sigPadWidth" :height="100" />
            </div>
          </div>
        </div>

        <!-- Sticky bottom -->
        <div class="dwv__stb">
          <button
            class="dwv__btn dwv__btn--out"
            style="flex:0 0 110px"
            @click="saveProgress"
            :disabled="saving"
          >
            Сохранить
          </button>
          <button
            class="dwv__btn dwv__btn--ok"
            @click="closeWaybill"
            :disabled="closing || !form.signature || form.odometer_finish == null"
          >
            {{ closing ? 'Закрытие…' : 'Закрыть лист' }}
          </button>
        </div>
      </template>

      <!-- ==================== SCREEN 4: Закрыт/Просрочен (readonly) ==================== -->
      <template v-else>
        <div class="dwv__body">
          <div class="dwv__closed-banner">
            <v-icon
              icon="mdi-check-circle"
              size="56"
              :color="waybill.status === 'overdue' ? '#f6b34a' : '#22c997'"
            />
            <div class="dwv__closed-title">
              Путевой лист {{ waybill.status === 'overdue' ? 'просрочен' : 'закрыт' }}
            </div>
            <StatusPill :variant="waybill.status === 'overdue' ? 'warn' : 'ok'">
              {{ statusLabel(waybill.status) }}
            </StatusPill>
          </div>

          <div class="dwv__card">
            <div class="dwv__card-title">Сводка</div>
            <div class="dwv__hero-row"><span>Маршрут</span><b>{{ heroRoute }}</b></div>
            <div class="dwv__hero-row"><span>Дата</span><b>{{ fmt(waybill.date_start) }}</b></div>
            <div class="dwv__hero-row">
              <span>Пробег факт.</span><b>{{ waybill.actual_mileage_km ?? '—' }} км</b>
            </div>
            <div class="dwv__hero-row">
              <span>Пробег план.</span><b>{{ waybill.planned_mileage_km ?? '—' }} км</b>
            </div>
          </div>

          <div class="dwv__stb-inline">
            <a
              class="dwv__btn"
              :href="`/api/trips/${waybill.id}/waybill.docx`"
              target="_blank"
              download
            >Скачать .docx</a>
          </div>
        </div>
      </template>
    </template>

    <!-- ==================== Fuel refill dialog ==================== -->
    <v-dialog v-model="fuelDialog" max-width="440" :persistent="savingFuel">
      <v-card class="dwv__dialog">
        <v-card-title>Заправка</v-card-title>
        <v-card-text>
          <v-text-field
            v-model="fuelForm.station_name"
            label="АЗС / название"
            variant="outlined"
            density="compact"
            class="mb-3"
          />
          <div class="dwv__fuel-row">
            <v-text-field
              v-model.number="fuelForm.liters"
              label="Литры"
              type="number"
              variant="outlined"
              density="compact"
              hide-spin-buttons
            />
            <v-text-field
              v-model.number="fuelForm.amount_rub"
              label="Сумма, ₽"
              type="number"
              variant="outlined"
              density="compact"
              hide-spin-buttons
            />
          </div>
          <div class="dwv__field-label" style="margin-bottom:6px">Фото чека</div>
          <v-file-input
            v-model="fuelForm.receiptFile"
            label="Прикрепить фото"
            accept="image/*"
            capture="environment"
            variant="outlined"
            density="compact"
            prepend-icon="mdi-camera"
          />
          <div v-if="fuelError" class="dwv__fuel-error">{{ fuelError }}</div>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn text @click="fuelDialog = false">Отмена</v-btn>
          <v-btn color="primary" :loading="savingFuel" @click="submitFuel">Сохранить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiFetch } from '@/api'
import StageStepper from '@/components/fleet/StageStepper.vue'
import SignaturePad from '@/components/fleet/SignaturePad.vue'
import RouteStopsEditor from '@/components/fleet/RouteStopsEditor.vue'
import OdometerField from '@/components/fleet/OdometerField.vue'
import StatusPill from '@/components/fleet/StatusPill.vue'
import LicensePlate from '@/components/vehicles/LicensePlate.vue'
import VehicleTypeIcon from '@/components/vehicles/VehicleTypeIcon.vue'

// ─── Types ───────────────────────────────────────────────────────────────────

interface RouteStop {
  id?: number | null
  ord: number
  kind: string
  name: string
  description?: string | null
  planned_time?: string | null
}

interface OdometerReading {
  id?: number
  mileage_km: number
  location?: string | null
  recorded_at?: string | null
}

interface FuelRefill {
  id?: number
  station_name?: string | null
  liters: number
  amount_rub?: number | null
  created_at?: string | null
}

interface Vehicle {
  id?: number
  license_plate?: string | null
  brand_model?: string | null
  year?: number | null
  vehicle_type?: string | null
  fuel_norm?: number | null
}

interface Waybill {
  id: number
  number?: string | null
  status: string
  date_start?: string | null
  date_end?: string | null
  planned_mileage_km?: number | null
  actual_mileage_km?: number | null
  odometer_start?: number | null
  odometer_finish?: number | null
  fuel_remaining_start?: number | null
  fuel_remaining_finish?: number | null
  cargo_description?: string | null
  cargo_weight_t?: number | null
  route_from?: string | null
  route_to?: string | null
  dispatcher_name?: string | null
  vehicle?: Vehicle | null
  route_stops?: RouteStop[]
  odometer_readings?: OdometerReading[]
  fuel_refills?: FuelRefill[]
}

interface ChecklistItem {
  key: string
  label: string
  hint: string
  state: 'ok' | 'issue' | 'missing'
}

// ─── State ───────────────────────────────────────────────────────────────────

const route  = useRoute()
const router = useRouter()

const waybill   = ref<Waybill | null>(null)
const loading   = ref(true)
const error     = ref('')
const accepting = ref(false)
const saving    = ref(false)
const closing   = ref(false)

// Screen 2 — pending odometer values (key = stop.id or index)
const pendingOdometer = reactive<Record<string | number, number | undefined>>({})

// Screen 3 — form values
const form = reactive({
  odometer_finish:      undefined as number | undefined,
  fuel_remaining_finish: undefined as number | undefined,
  signature:            undefined as string | null | undefined,
})

// Screen 3 — post-trip checklist
const checklist = reactive<ChecklistItem[]>([
  { key: 'body',   label: 'Кузов и стёкла',            hint: 'Без новых повреждений',         state: 'ok'      },
  { key: 'wheels', label: 'Колёса и шины',             hint: 'Давление в норме',              state: 'ok'      },
  { key: 'lights', label: 'Световые приборы',          hint: 'Все работают',                  state: 'ok'      },
  { key: 'leaks',  label: 'Утечки масла / охлаждения', hint: 'Требуется визуальная проверка', state: 'missing' },
])

const checklistOpts: { value: 'ok' | 'issue' | 'missing'; label: string }[] = [
  { value: 'ok',      label: 'ОК'           },
  { value: 'issue',   label: 'Замечание'    },
  { value: 'missing', label: 'Не проверено' },
]

// Fuel dialog
const fuelDialog  = ref(false)
const savingFuel  = ref(false)
const fuelError   = ref('')
const fuelForm = reactive({
  station_name: '',
  liters:       undefined as number | undefined,
  amount_rub:   undefined as number | undefined,
  receiptFile:  undefined as File | undefined,
})

// MVP photo grid placeholder (count of "added" photos)
const routePhotos = ref<number[]>([1, 2, 3])

// ─── Computed ─────────────────────────────────────────────────────────────────

/**
 * Determine which screen to show based on waybill.status + driver acceptance flag.
 *  1 = Получение   (created / tech_inspect / med_inspect — unless driver accepted)
 *  2 = В дороге    (in_progress; or pre-inspect if accepted)
 *  3 = Закрытие    (closing / on_review)
 *  4 = Readonly    (closed / overdue)
 */
const currentScreen = computed<1 | 2 | 3 | 4>(() => {
  if (!waybill.value) return 1
  const s = waybill.value.status
  if (['created', 'tech_inspect', 'med_inspect'].includes(s)) {
    const accepted = localStorage.getItem(`waybill_${waybill.value.id}_accepted`)
    return accepted ? 2 : 1
  }
  if (s === 'in_progress') return 2
  if (s === 'closing' || s === 'on_review') return 3
  return 4
})

const screenTitle = computed(() => {
  switch (currentScreen.value) {
    case 1:  return 'Путевой лист'
    case 2:  return `№ ${waybill.value?.number ?? waybill.value?.id}`
    case 3:  return 'Закрытие листа'
    default: return 'Путевой лист'
  }
})

const heroRoute = computed(() => {
  if (!waybill.value) return ''
  const stops = waybill.value.route_stops
  if (stops?.length) {
    const first = stops[0]?.name ?? waybill.value.route_from ?? ''
    const last  = stops[stops.length - 1]?.name ?? waybill.value.route_to ?? ''
    if (stops.length <= 2) return first && last ? `${first} → ${last}` : first || last
    const mid = stops.slice(1, -1).map(s => s.name).join(' → ')
    return `${first} → ${mid} → ${last}`
  }
  const from = waybill.value.route_from ?? ''
  const to   = waybill.value.route_to   ?? ''
  return from && to ? `${from} → ${to}` : from || to || '—'
})

const nextStopName = computed(() => {
  if (!waybill.value?.route_stops?.length) return '—'
  const readings = waybill.value.odometer_readings ?? []
  for (const stop of waybill.value.route_stops) {
    if (!readings.some(r => r.location === stop.name)) return stop.name
  }
  return waybill.value.route_stops[waybill.value.route_stops.length - 1]?.name ?? '—'
})

const filledReadings = computed(() => {
  const readings = waybill.value?.odometer_readings ?? []
  const stops    = waybill.value?.route_stops ?? []
  return stops.filter(stop => readings.some(r => r.location === stop.name)).length
})

const lastOdometerValue = computed<number | undefined>(() => {
  const readings = waybill.value?.odometer_readings ?? []
  if (!readings.length) return waybill.value?.odometer_start ?? undefined
  return readings[readings.length - 1]?.mileage_km
})

const fuelConsumed = computed<number | null>(() => {
  if (!waybill.value) return null
  const start  = waybill.value.fuel_remaining_start ?? 0
  const issued = (waybill.value.fuel_refills ?? []).reduce((s, r) => s + (r.liters ?? 0), 0)
  const finish = form.fuel_remaining_finish ?? waybill.value.fuel_remaining_finish
  if (finish == null) return null
  return Math.max(0, start + issued - finish)
})

const fuelPer100 = computed<string | null>(() => {
  const consumed = fuelConsumed.value
  const km = waybill.value?.actual_mileage_km
  if (!consumed || !km || km === 0) return null
  return (consumed / km * 100).toFixed(1)
})

const tripDuration = computed<string>(() => {
  const wb = waybill.value
  if (!wb?.date_start || !wb.date_end) return '—'
  const start = new Date(wb.date_start)
  const end   = new Date(wb.date_end)
  const mins  = Math.max(0, Math.round((end.getTime() - start.getTime()) / 60000))
  return `${Math.floor(mins / 60)}ч ${mins % 60}м`
})

const totalFuelCost = computed<number | null>(() => {
  const refills = waybill.value?.fuel_refills ?? []
  if (!refills.length) return null
  return refills.reduce((s, r) => s + (r.amount_rub ?? 0), 0)
})

const allChecksDone = computed(() => checklist.every(c => c.state === 'ok'))

const sigPadWidth = computed(() => Math.min(typeof window !== 'undefined' ? window.innerWidth - 64 : 320, 400))

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fmt(dt?: string | null): string {
  if (!dt) return '—'
  try {
    return new Date(dt).toLocaleString('ru-RU', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  } catch { return dt }
}

function fmtTime(dt?: string | null): string {
  if (!dt) return ''
  try {
    return new Date(dt).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
  } catch { return dt }
}

function fmtDateTime(dt?: string | null): string {
  if (!dt) return ''
  try {
    return new Date(dt).toLocaleString('ru-RU', {
      day: '2-digit', month: '2-digit',
      hour: '2-digit', minute: '2-digit',
    })
  } catch { return dt }
}

function statusLabel(s: string): string {
  const MAP: Record<string, string> = {
    created: 'Создан', tech_inspect: 'Тех.осмотр', med_inspect: 'Медосмотр',
    in_progress: 'В пути', closing: 'Закрытие', on_review: 'На проверке',
    closed: 'Закрыт', overdue: 'Просрочен',
  }
  return MAP[s] ?? s
}

function stopReading(stop: RouteStop): OdometerReading | undefined {
  return (waybill.value?.odometer_readings ?? []).find(r => r.location === stop.name)
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload  = () => resolve(reader.result as string)
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

// ─── Data loading ─────────────────────────────────────────────────────────────

async function loadWaybill() {
  loading.value = true
  error.value   = ''
  try {
    const id = route.params.id as string
    const wb = await apiFetch<Waybill>(`/trips/${id}`)
    waybill.value = wb
    // Pre-fill Screen 3 form from existing backend values
    if (wb.odometer_finish != null)        form.odometer_finish       = wb.odometer_finish
    if (wb.fuel_remaining_finish != null)  form.fuel_remaining_finish  = wb.fuel_remaining_finish
  } catch (e: any) {
    error.value = e?.message ?? 'Ошибка загрузки'
  } finally {
    loading.value = false
  }
}

// ─── Screen 1 actions ─────────────────────────────────────────────────────────

function rejectWaybill() {
  router.back()
}

async function acceptWaybill() {
  if (!waybill.value) return
  accepting.value = true
  try {
    // Set localStorage flag → currentScreen computed re-evaluates to 2
    localStorage.setItem(`waybill_${waybill.value.id}_accepted`, 'true')
    // Force Vue reactivity cycle to pick up the new computed value
    const snapshot = waybill.value
    waybill.value  = null
    await new Promise<void>(r => setTimeout(r, 0))
    waybill.value  = snapshot
  } finally {
    accepting.value = false
  }
}

// ─── Screen 2 actions ─────────────────────────────────────────────────────────

async function onOdometerInput(stop: RouteStop, idx: number, val: number | undefined) {
  if (val == null || !waybill.value) return
  const key = stop.id ?? idx
  pendingOdometer[key] = val
  try {
    const reading = await apiFetch<OdometerReading>(`/trips/${waybill.value.id}/odometer-readings`, {
      method: 'POST',
      body: JSON.stringify({
        mileage_km:  val,
        location:    stop.name,
        recorded_at: new Date().toISOString(),
      }),
    })
    if (!waybill.value.odometer_readings) waybill.value.odometer_readings = []
    waybill.value.odometer_readings.push(reading)
    delete pendingOdometer[key]
  } catch (e: any) {
    // Keep pendingOdometer[key] so the input remains editable
    console.error('[odometer] save failed', e?.message)
  }
}

function reportIncident() {
  if (!waybill.value) return
  router.push(`/m/driver/incident?trip_id=${waybill.value.id}`)
}

function onPhotoAdd(_e: Event) {
  // Photo grid is a visual MVP placeholder; no dedicated API endpoint
  routePhotos.value.push(routePhotos.value.length + 1)
}

async function saveProgress() {
  if (!waybill.value) return
  saving.value = true
  try {
    const body: Record<string, unknown> = {}
    if (form.odometer_finish != null)       body.odometer_finish       = form.odometer_finish
    if (form.fuel_remaining_finish != null) body.fuel_remaining_finish  = form.fuel_remaining_finish
    if (Object.keys(body).length) {
      await apiFetch(`/trips/${waybill.value.id}`, { method: 'PATCH', body: JSON.stringify(body) })
    }
  } catch (e: any) {
    console.error('[save] failed', e?.message)
  } finally {
    saving.value = false
  }
}

// ─── Fuel dialog ──────────────────────────────────────────────────────────────

function openFuelDialog() {
  fuelForm.station_name = ''
  fuelForm.liters       = undefined
  fuelForm.amount_rub   = undefined
  fuelForm.receiptFile  = undefined
  fuelError.value       = ''
  fuelDialog.value      = true
}

async function submitFuel() {
  if (!waybill.value) return
  if (!fuelForm.liters) { fuelError.value = 'Укажите количество литров'; return }
  savingFuel.value = true
  fuelError.value  = ''
  try {
    let receiptData: string | undefined
    if (fuelForm.receiptFile) {
      receiptData = await fileToBase64(fuelForm.receiptFile)
    }
    const refill = await apiFetch<FuelRefill>(`/trips/${waybill.value.id}/fuel-refills`, {
      method: 'POST',
      body: JSON.stringify({
        station_name: fuelForm.station_name || undefined,
        liters:       fuelForm.liters,
        amount_rub:   fuelForm.amount_rub   ?? undefined,
        ...(receiptData ? { receipt_photo_data: receiptData } : {}),
      }),
    })
    if (!waybill.value.fuel_refills) waybill.value.fuel_refills = []
    waybill.value.fuel_refills.push(refill)
    fuelDialog.value = false
  } catch (e: any) {
    fuelError.value = e?.message ?? 'Ошибка сохранения'
  } finally {
    savingFuel.value = false
  }
}

// ─── Screen 3 actions ─────────────────────────────────────────────────────────

async function closeWaybill() {
  if (!waybill.value || !form.signature) return
  closing.value = true
  try {
    // 1. Persist final odometer / fuel
    await saveProgress()

    // 2. Post-trip checklist (non-blocking — backend may not have this endpoint yet)
    try {
      await apiFetch('/checklists/', {
        method: 'POST',
        body: JSON.stringify({
          type:       'post_trip',
          waybill_id: waybill.value.id,
          items:      checklist.map(c => ({ key: c.key, label: c.label, state: c.state })),
        }),
      })
    } catch (e: any) {
      console.warn('[checklist] post failed (non-blocking)', e?.message)
    }

    // 3. Driver sign → status becomes on_review
    await apiFetch(`/trips/${waybill.value.id}/driver-sign`, {
      method: 'POST',
      body: JSON.stringify({ signature_data: form.signature }),
    })

    await loadWaybill()
  } catch (e: any) {
    console.error('[close] failed', e?.message)
  } finally {
    closing.value = false
  }
}

// ─── Lifecycle ────────────────────────────────────────────────────────────────

onMounted(() => { loadWaybill() })
</script>

<style scoped>
/* ── Root ──────────────────────────────────────────────────────────────────── */
.dwv {
  display: flex;
  flex-direction: column;
  min-height: 100dvh;
  max-width: 480px;
  margin: 0 auto;
  background: var(--bg, #0a0d14);
  color: var(--text, #e9edf5);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

/* ── Loading / error ───────────────────────────────────────────────────────── */
.dwv__loading,
.dwv__error {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 40px 24px;
  text-align: center;
  color: var(--muted, #8a93a8);
}

/* ── App header ────────────────────────────────────────────────────────────── */
.dwv__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 18px 8px;
  background: var(--bg, #0a0d14);
  position: sticky;
  top: 0;
  z-index: 10;
  border-bottom: 1px solid var(--line, #222838);
}

.dwv__back {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: none;
  background: var(--panel-2, #1a1f2c);
  color: var(--text, #e9edf5);
  font-size: 22px;
  cursor: pointer;
  display: grid;
  place-items: center;
  line-height: 1;
}

.dwv__header-title { font-size: 15px; font-weight: 600; }

.dwv__header-r {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--panel-2, #1a1f2c);
  display: grid;
  place-items: center;
  color: var(--muted, #8a93a8);
  font-size: 18px;
}

/* ── Scrollable body ───────────────────────────────────────────────────────── */
.dwv__body {
  flex: 1;
  overflow-y: auto;
  padding: 12px 16px 100px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  -webkit-overflow-scrolling: touch;
}
.dwv__body::-webkit-scrollbar { display: none; }

/* ── Generic card ──────────────────────────────────────────────────────────── */
.dwv__card {
  background: var(--panel, #141823);
  border: 1px solid var(--line, #222838);
  border-radius: 16px;
  padding: 14px;
}

.dwv__card-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 10px;
  display: flex;
  align-items: center;
}

.dwv__card-sub {
  font-size: 10px;
  color: var(--muted, #8a93a8);
  font-weight: 400;
  margin-left: auto;
}

.dwv__card-add {
  margin-left: auto;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--panel-2, #1a1f2c);
  display: grid;
  place-items: center;
  font-size: 16px;
  cursor: pointer;
  color: var(--accent, #6aa6ff);
  font-weight: 700;
  user-select: none;
}

/* ── Notification banner ───────────────────────────────────────────────────── */
.dwv__notif {
  background: rgba(106, 166, 255, 0.1);
  border: 1px solid rgba(106, 166, 255, 0.3);
  border-radius: 12px;
  padding: 10px 12px;
  display: flex;
  gap: 10px;
  align-items: center;
}
.dwv__notif-ic {
  width: 34px; height: 34px;
  border-radius: 50%;
  background: var(--accent, #6aa6ff);
  display: grid;
  place-items: center;
  font-size: 16px;
  flex: none;
}
.dwv__notif-t { font-size: 11px; line-height: 1.4; }
.dwv__notif-t b { display: block; font-weight: 600; margin-bottom: 2px; }
.dwv__notif-t span { color: var(--muted, #8a93a8); }

/* ── Hero card ─────────────────────────────────────────────────────────────── */
.dwv__hero {
  background: linear-gradient(135deg, rgba(106,166,255,.12), rgba(139,92,246,.06));
  border: 1px solid rgba(106, 166, 255, 0.3);
  border-radius: 18px;
  padding: 16px;
  position: relative;
  overflow: hidden;
}
.dwv__hero::before {
  content: 'НОВОЕ';
  position: absolute; top: 14px; right: 14px;
  background: var(--accent, #6aa6ff);
  color: #fff; font-size: 9px; font-weight: 700;
  padding: 3px 8px; border-radius: 6px; letter-spacing: .5px;
}
.dwv__hero-num {
  color: var(--accent, #6aa6ff);
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px; font-weight: 700; margin-bottom: 4px;
}
.dwv__hero-tit {
  font-size: 16px; font-weight: 700; margin-bottom: 12px;
  line-height: 1.3; padding-right: 56px;
}
.dwv__hero-row {
  display: flex; justify-content: space-between;
  font-size: 11px; color: var(--muted, #8a93a8); padding: 3px 0;
}
.dwv__hero-row b { color: var(--text, #e9edf5); font-weight: 500; }

/* ── Vehicle card ──────────────────────────────────────────────────────────── */
.dwv__veh { display: flex; align-items: center; gap: 12px; }
.dwv__veh-icon {
  width: 78px; height: 50px;
  background: var(--panel-2, #1a1f2c);
  border-radius: 10px; display: grid; place-items: center; flex: none;
}
.dwv__veh-mod { color: var(--muted, #8a93a8); font-size: 11px; margin-top: 4px; }

/* ── Cargo ─────────────────────────────────────────────────────────────────── */
.dwv__cargo-desc { font-size: 12px; line-height: 1.5; color: var(--muted, #8a93a8); }
.dwv__cargo-desc b { color: var(--text, #e9edf5); }

/* ── Screen 2: active status banner ───────────────────────────────────────── */
.dwv__banner-active {
  background: linear-gradient(135deg, rgba(34,201,151,.1), rgba(93,208,255,.04));
  border: 1px solid rgba(34, 201, 151, 0.3);
  border-radius: 16px; padding: 14px;
  display: flex; justify-content: space-between; align-items: center;
}
.dwv__banner-label { font-size: 11px; color: var(--muted, #8a93a8); margin-bottom: 4px; }
.dwv__banner-val   { font-size: 14px; font-weight: 600; }

/* ── Screen 3: closing summary banner ─────────────────────────────────────── */
.dwv__banner-close {
  background: linear-gradient(135deg, rgba(246,179,74,.08), rgba(255,91,106,.03));
  border: 1px solid rgba(246, 179, 74, 0.2);
  border-radius: 16px; padding: 14px;
}

/* ── Stats grid 2×2 ────────────────────────────────────────────────────────── */
.dwv__stats-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.dwv__stat { background: var(--bg-2, #0f131c); border-radius: 10px; padding: 10px; }
.dwv__stat-l { font-size: 9px; color: var(--muted, #8a93a8); text-transform: uppercase; letter-spacing: .5px; }
.dwv__stat-v { font-family: 'JetBrains Mono', monospace; font-size: 17px; font-weight: 700; margin-top: 3px; }
.dwv__stat-unit { font-size: 11px; font-weight: 400; color: var(--muted, #8a93a8); margin-left: 2px; }
.dwv__stat-s { font-size: 10px; color: var(--muted, #8a93a8); margin-top: 2px; }

/* ── Odometer stops ────────────────────────────────────────────────────────── */
.dwv__odo-stop   { margin-bottom: 10px; }
.dwv__odo-label  { font-size: 10px; color: var(--muted, #8a93a8); text-transform: uppercase; letter-spacing: .4px; margin-bottom: 4px; }
.dwv__odo-filled {
  padding: 10px 12px;
  background: var(--bg-2, #0f131c);
  border: 1px solid var(--ok, #22c997);
  border-radius: 10px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 14px; font-weight: 600; color: var(--ok, #22c997);
}

/* ── Fuel refills ──────────────────────────────────────────────────────────── */
.dwv__refill-row {
  display: flex; justify-content: space-between; align-items: flex-start;
  padding: 8px 0; border-bottom: 1px solid var(--line, #222838); font-size: 12px;
}
.dwv__refill-row:last-of-type { border-bottom: none; }
.dwv__refill-name   { font-weight: 500; }
.dwv__refill-date   { font-size: 10px; color: var(--muted, #8a93a8); margin-top: 2px; }
.dwv__refill-right  { text-align: right; }
.dwv__refill-liters { font-family: 'JetBrains Mono', monospace; font-weight: 600; }
.dwv__refill-amount { font-size: 10px; color: var(--muted, #8a93a8); margin-top: 2px; }

/* ── Fuel dialog ───────────────────────────────────────────────────────────── */
.dwv__fuel-row   { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 12px; }
.dwv__fuel-error { font-size: 12px; color: var(--alert, #ff5b6a); margin-top: 4px; }
.dwv__dialog     { background: var(--panel, #141823) !important; }

/* ── Photo row ─────────────────────────────────────────────────────────────── */
.dwv__photo-row  { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 6px; }
.dwv__photo-cell { width: 60px; height: 60px; border-radius: 10px; display: grid; place-items: center; font-size: 18px; flex: none; }
.dwv__photo-cell--done { background: linear-gradient(135deg, #2b3245, #3a4258); color: var(--ok, #22c997); }
.dwv__photo-cell--add  { background: var(--panel-2, #1a1f2c); border: 1px dashed var(--line-2, #2b3245); color: var(--muted, #8a93a8); cursor: pointer; }
.dwv__photo-hint { font-size: 10px; color: var(--muted, #8a93a8); margin-top: 8px; }

/* ── Post-trip checklist ───────────────────────────────────────────────────── */
.dwv__chk-row {
  display: flex; align-items: flex-start; gap: 10px;
  padding: 8px 0; border-bottom: 1px solid var(--line, #222838);
}
.dwv__chk-row:last-child { border-bottom: none; }

.dwv__chk-pills { display: flex; flex-direction: column; gap: 4px; flex: none; }

.dwv__chk-pill {
  padding: 3px 8px; border-radius: 8px;
  border: 1px solid var(--line-2, #2b3245);
  background: transparent; color: var(--muted, #8a93a8);
  font-size: 10px; font-weight: 600; cursor: pointer; font-family: inherit;
  transition: background .15s, color .15s, border-color .15s;
  white-space: nowrap;
}
.dwv__chk-pill--ok.dwv__chk-pill--active      { background: rgba(34,201,151,.2);  border-color: #22c997; color: #22c997; }
.dwv__chk-pill--issue.dwv__chk-pill--active    { background: rgba(246,179,74,.2);  border-color: #f6b34a; color: #f6b34a; }
.dwv__chk-pill--missing.dwv__chk-pill--active  { background: rgba(138,147,168,.15); border-color: var(--muted, #8a93a8); color: var(--muted, #8a93a8); }

.dwv__chk-text { font-size: 12px; flex: 1; }
.dwv__chk-hint { font-size: 10px; color: var(--muted, #8a93a8); margin-top: 2px; }

/* ── Signature ─────────────────────────────────────────────────────────────── */
.dwv__sig-wrap { width: 100%; overflow-x: auto; }

/* ── Offline banner ────────────────────────────────────────────────────────── */
.dwv__offline-banner {
  background: rgba(93, 208, 255, 0.06);
  border: 1px solid rgba(93, 208, 255, 0.15);
  border-radius: 10px; padding: 10px 14px;
  display: flex; align-items: center; gap: 8px;
  font-size: 11px; color: var(--muted, #8a93a8);
}

/* ── Closed screen ─────────────────────────────────────────────────────────── */
.dwv__closed-banner {
  display: flex; flex-direction: column; align-items: center;
  gap: 10px; padding: 32px 16px; text-align: center;
}
.dwv__closed-title { font-size: 18px; font-weight: 700; }
.dwv__stb-inline   { padding: 8px 0; }

/* ── Field helpers ─────────────────────────────────────────────────────────── */
.dwv__field-group { margin-top: 10px; }
.dwv__field-label { font-size: 10px; color: var(--muted, #8a93a8); text-transform: uppercase; letter-spacing: .4px; margin-bottom: 4px; display: block; }

/* ── Empty sub-text ────────────────────────────────────────────────────────── */
.dwv__empty-sub { font-size: 11px; color: var(--muted, #8a93a8); margin-bottom: 8px; }

/* ── Sticky bottom ─────────────────────────────────────────────────────────── */
.dwv__stb {
  position: sticky; bottom: 0; left: 0; right: 0;
  padding: 10px 16px 20px;
  border-top: 1px solid var(--line, #222838);
  background: var(--bg-2, #0f131c);
  display: flex; gap: 8px; z-index: 10;
}

.dwv__btn {
  flex: 1;
  padding: 13px 16px; border-radius: 14px; border: none;
  background: linear-gradient(135deg, var(--accent, #6aa6ff), #8b5cf6);
  color: #fff; font-size: 14px; font-weight: 700;
  cursor: pointer; text-align: center; font-family: inherit;
  text-decoration: none;
  display: inline-flex; align-items: center; justify-content: center;
  transition: opacity .15s;
}
.dwv__btn:disabled { opacity: .5; cursor: not-allowed; }

.dwv__btn--out {
  background: transparent;
  border: 1px solid var(--line-2, #2b3245);
  color: var(--text, #e9edf5);
}
.dwv__btn--ok  { background: linear-gradient(135deg, #22c997, #5dd0ff); }
.dwv__btn--sm  { margin-top: 10px; padding: 10px; font-size: 12px; }

/* ── Light theme overrides ─────────────────────────────────────────────────── */
@media (prefers-color-scheme: light) {
  .dwv           { background: var(--bg, #f5f7fa); color: var(--text, #1a1f2c); }
  .dwv__header   { background: var(--bg, #f5f7fa); border-bottom-color: #e0e3ea; }
  .dwv__card     { background: #fff; border-color: #e0e3ea; }
  .dwv__back,
  .dwv__header-r { background: #eef0f5; color: #1a1f2c; }
  .dwv__stat     { background: #eef0f5; }
  .dwv__stb      { background: #f5f7fa; border-top-color: #e0e3ea; }
}
</style>
