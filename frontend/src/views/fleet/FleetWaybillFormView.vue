<template>
  <div
    class="wbf-page"
    :class="{ 'print-a5': isLightVehicle, 'print-a4': !isLightVehicle }"
  >
    <!-- ═══ STICKY TOPBAR ═══ -->
    <div class="wbf-topbar no-print">
      <div class="wbf-crumbs">
        <router-link to="/fleet">Автопарк</router-link>
        <span class="sep">/</span>
        <router-link to="/fleet/waybills">Путевые листы</router-link>
        <span class="sep">/</span>
        <span class="current">{{ isNew ? 'Новый' : `№ ${form.number}` }}</span>
      </div>
      <div class="wbf-topbar-center">
        <h1 class="wbf-title">{{ isNew ? 'Новый путевой лист' : `Путевой лист № ${form.number}` }}</h1>
        <StatusPill :variant="statusVariant(form.status)" :dot="form.status === 'in_progress'">
          {{ statusLabel(form.status) }}
        </StatusPill>
      </div>
      <div class="wbf-topbar-actions">
        <v-btn variant="outlined" size="small" prepend-icon="mdi-arrow-left" @click="$router.back()">
          Назад
        </v-btn>
        <v-btn variant="outlined" size="small" prepend-icon="mdi-content-save-outline" :loading="saving" :disabled="isNew && !form.vehicle_id" @click="saveDraft">
          Сохранить черновик
        </v-btn>
        <v-btn
          v-if="form.id"
          variant="outlined"
          size="small"
          prepend-icon="mdi-download"
          :loading="downloadingDocx"
          @click="downloadDocx"
        >
          Скачать .docx
        </v-btn>
        <!-- Phase 30.2: печать A5 (легковой) / A4 (грузовой), двусторонняя по длинной стороне -->
        <v-btn
          v-if="form.id"
          variant="outlined"
          size="small"
          prepend-icon="mdi-printer"
          @click="onPrint"
        >
          Распечатать
        </v-btn>
        <v-btn
          color="primary"
          size="small"
          :loading="saving"
          :disabled="isNew && !form.vehicle_id"
          @click="handlePrimaryAction"
        >
          {{ primaryActionLabel }}
        </v-btn>
      </div>
    </div>

    <!-- Stage stepper -->
    <div class="wbf-stepper-wrap no-print">
      <StageStepper :current-stage="(form.status as any) || 'created'" />
    </div>

    <!-- Loading state -->
    <div v-if="loading" class="wbf-loading no-print">
      <v-progress-circular indeterminate color="primary" />
    </div>

    <!-- ═══ FORM ═══ -->
    <div v-else class="wbf-layout wbf-print-area">

      <!-- ── MAIN column ── -->
      <div class="wbf-main">

        <!-- 1. Шапка ПЛ -->
        <v-card class="wbf-card" flat border>
          <div class="wbf-card-header">
            <v-icon color="primary" size="18">mdi-file-document-outline</v-icon>
            <span>Шапка путевого листа</span>
          </div>
          <div class="wbf-grid-3">
            <v-text-field
              :model-value="form.number"
              label="Номер п/л"
              readonly
              variant="outlined"
              density="compact"
              hide-details
              class="font-mono"
              :placeholder="isNew ? 'Будет присвоен' : ''"
            />
            <v-text-field
              v-model="form.date_start"
              label="Начало действия *"
              type="datetime-local"
              variant="outlined"
              density="compact"
              hide-details
              :readonly="formReadonly"
              @change="scheduleAutosave"
            />
            <v-text-field
              v-model="form.date_end"
              label="Конец действия *"
              type="datetime-local"
              variant="outlined"
              density="compact"
              hide-details
              :readonly="formReadonly"
              @change="scheduleAutosave"
            />
            <v-select
              v-model="form.waybill_type"
              label="Тип путевого"
              :items="waybillTypes"
              item-title="label"
              item-value="value"
              variant="outlined"
              density="compact"
              hide-details
              :readonly="formReadonly"
              @update:model-value="scheduleAutosave"
            />
          </div>
        </v-card>

        <!-- 2. Транспортное средство -->
        <v-card class="wbf-card" flat border>
          <div class="wbf-card-header">
            <v-icon color="success" size="18">mdi-car</v-icon>
            <span>Транспортное средство</span>
          </div>
          <v-autocomplete
            v-model="form.vehicle_id"
            label="Транспортное средство *"
            :items="vehicles"
            :item-title="v => `${v.plate} · ${v.brand_model} (${v.year})`"
            item-value="id"
            variant="outlined"
            density="compact"
            prepend-inner-icon="mdi-car"
            :readonly="formReadonly"
            clearable
            @update:model-value="onVehicleSelect"
          />
          <!-- Phase 30.2: "Не выбран ТС" chip if no vehicle selected on new form -->
          <v-chip
            v-if="isNew && !form.vehicle_id"
            color="warning"
            variant="tonal"
            size="small"
            prepend-icon="mdi-alert-outline"
            class="mt-2"
          >
            Не выбран ТС — сохранение недоступно
          </v-chip>
          <div v-if="selectedVehicle" class="wbf-veh-preview">
            <div class="wbf-veh-preview-icon">
              <v-icon color="primary">mdi-car-side</v-icon>
            </div>
            <div class="wbf-veh-info">
              <div class="wbf-veh-main">
                <LicensePlate :model-value="selectedVehicle.plate" size="sm" />
                <span class="wbf-veh-model">{{ selectedVehicle.brand_model }}, {{ selectedVehicle.year }}</span>
              </div>
              <div class="wbf-veh-sub">
                VIN: {{ selectedVehicle.vin || '—' }} · Пробег: {{ (selectedVehicle.current_mileage_km || 0).toLocaleString('ru-RU') }} км
              </div>
              <!-- Phase 30.2: fuel norms display -->
              <div v-if="selectedVehicle.fuel_norm_summer || selectedVehicle.fuel_norm_winter" class="wbf-veh-sub">
                Норма расхода: {{ selectedVehicle.fuel_norm_summer ?? '—' }} л/100км (лето) · {{ selectedVehicle.fuel_norm_winter ?? '—' }} л/100км (зима)
              </div>
            </div>
          </div>
        </v-card>

        <!-- 3. Водитель -->
        <v-card class="wbf-card" flat border>
          <div class="wbf-card-header">
            <v-icon color="purple" size="18">mdi-account</v-icon>
            <span>Водитель</span>
          </div>
          <v-autocomplete
            v-model="form.driver_user_id"
            label="Водитель *"
            :items="drivers"
            :item-title="u => u.full_name + (u.license_categories ? ` · кат. ${u.license_categories}` : '')"
            item-value="id"
            variant="outlined"
            density="compact"
            prepend-inner-icon="mdi-account"
            :readonly="formReadonly"
            clearable
            @update:model-value="scheduleAutosave"
          />
          <div v-if="selectedDriver" class="wbf-driver-preview">
            <GradientAvatar :full-name="selectedDriver.full_name" size="md" />
            <div class="wbf-driver-info">
              <div class="wbf-driver-name">{{ selectedDriver.full_name }}</div>
              <div class="wbf-driver-sub">
                Категории: {{ selectedDriver.license_categories || '—' }} ·
                Удостоверение: {{ selectedDriver.license_number || '—' }} ·
                Стаж: {{ selectedDriver.experience_years ?? '?' }} лет
              </div>
              <div v-if="selectedDriver.driver_tab_number" class="wbf-driver-sub">
                Таб. номер: {{ selectedDriver.driver_tab_number }}
              </div>
            </div>
          </div>
        </v-card>

        <!-- 4. Маршрут и задание -->
        <v-card class="wbf-card" flat border>
          <div class="wbf-card-header">
            <v-icon color="info" size="18">mdi-map-marker-path</v-icon>
            <span>Маршрут и задание</span>
          </div>
          <v-textarea
            v-model="form.purpose"
            label="Цель поездки *"
            variant="outlined"
            density="compact"
            rows="2"
            auto-grow
            :readonly="formReadonly"
            @change="scheduleAutosave"
          />
          <div class="wbf-section-label">Точки маршрута</div>
          <RouteStopsEditor
            v-model="form.route_stops"
            :readonly="formReadonly"
          />
          <div class="wbf-grid-3 wbf-mt">
            <v-text-field
              v-model.number="form.planned_mileage_km"
              label="Плановый пробег (км)"
              type="number"
              variant="outlined"
              density="compact"
              hide-details
              :readonly="formReadonly"
              @change="scheduleAutosave"
            />
            <v-text-field
              v-model="form.planned_duration"
              label="Время в пути (план)"
              variant="outlined"
              density="compact"
              hide-details
              :readonly="formReadonly"
              placeholder="напр. 11 ч."
              @change="scheduleAutosave"
            />
            <v-text-field
              v-model="form.work_hours_norm"
              label="Норма часов"
              variant="outlined"
              density="compact"
              hide-details
              :readonly="formReadonly"
              placeholder="напр. 11 / 12"
              @change="scheduleAutosave"
            />
          </div>
        </v-card>

        <!-- 5. Спидометр и топливо -->
        <v-card class="wbf-card" flat border>
          <div class="wbf-card-header">
            <v-icon color="warning" size="18">mdi-speedometer</v-icon>
            <span>Спидометр и топливо</span>
          </div>
          <div class="wbf-section-label">Показания спидометра</div>
          <div class="wbf-grid-2">
            <OdometerField
              v-model="form.odometer_start"
              label="При выезде"
              :readonly="formReadonly"
            />
            <OdometerField
              v-model="form.odometer_finish"
              label="При возврате"
              :previous-value="form.odometer_start"
              :readonly="form.status === 'created' || form.status === 'tech_inspect' || form.status === 'med_inspect'"
            />
          </div>
          <div v-if="actualMileage" class="wbf-mileage-computed">
            Пробег за смену:
            <span class="wbf-mono">{{ actualMileage.toLocaleString('ru-RU') }} км</span>
          </div>
          <div class="wbf-section-label wbf-mt">Топливо</div>
          <FuelReadout
            v-model:fuel-start="form.fuel_remaining_start"
            v-model:fuel-issued="form.fuel_issued_l"
            v-model:fuel-end="form.fuel_remaining_finish"
            :mileage-km="actualMileage"
            :norm-per-100km="selectedVehicle?.fuel_norm_summer"
            :readonly="formReadonly"
          />
        </v-card>

        <!-- 6. Груз и пассажиры -->
        <v-card class="wbf-card" flat border>
          <div class="wbf-card-header">
            <v-icon size="18">mdi-package-variant</v-icon>
            <span>Груз и пассажиры</span>
          </div>
          <div class="wbf-grid-2">
            <v-textarea
              v-model="form.cargo_description"
              label="Описание груза"
              variant="outlined"
              density="compact"
              rows="2"
              auto-grow
              hide-details
              :readonly="formReadonly"
              @change="scheduleAutosave"
            />
            <div class="wbf-grid-col">
              <v-text-field
                v-model.number="form.cargo_weight_t"
                label="Вес груза (т)"
                type="number"
                variant="outlined"
                density="compact"
                hide-details
                :readonly="formReadonly"
                @change="scheduleAutosave"
              />
              <v-text-field
                v-model.number="form.passengers_count"
                label="Кол-во пассажиров"
                type="number"
                variant="outlined"
                density="compact"
                hide-details
                :readonly="formReadonly"
                @change="scheduleAutosave"
              />
            </div>
          </div>
        </v-card>

        <!-- 7. Предрейсовые осмотры -->
        <v-card class="wbf-card" flat border>
          <div class="wbf-card-header">
            <v-icon color="success" size="18">mdi-clipboard-check-outline</v-icon>
            <span>Предрейсовые осмотры</span>
          </div>
          <div class="wbf-inspections">
            <InspectionBlock
              kind="mechanic"
              phase="pre"
              v-model:inspector-id="form.pre_mechanic_id"
              v-model:inspected-at="form.pre_mechanic_at"
              v-model:result="form.pre_mechanic_result"
              :users="mechanicUsers"
              :readonly="preInspectReadonly"
            />
            <InspectionBlock
              kind="doctor"
              phase="pre"
              v-model:inspector-id="form.pre_doctor_id"
              v-model:inspected-at="form.pre_doctor_at"
              v-model:result="form.pre_doctor_result"
              :users="doctorUsers"
              :readonly="preInspectReadonly"
            />
          </div>
        </v-card>

        <!-- 8. Послерейсовые осмотры -->
        <v-card class="wbf-card" flat border>
          <div class="wbf-card-header">
            <v-icon color="error" size="18">mdi-clipboard-alert-outline</v-icon>
            <span>Послерейсовые осмотры</span>
          </div>
          <div class="wbf-inspections">
            <InspectionBlock
              kind="mechanic"
              phase="post"
              v-model:inspector-id="form.post_mechanic_id"
              v-model:inspected-at="form.post_mechanic_at"
              v-model:result="form.post_mechanic_result"
              :users="mechanicUsers"
              :readonly="postInspectReadonly"
            />
            <InspectionBlock
              kind="doctor"
              phase="post"
              v-model:inspector-id="form.post_doctor_id"
              v-model:inspected-at="form.post_doctor_at"
              v-model:result="form.post_doctor_result"
              :users="doctorUsers"
              :readonly="postInspectReadonly"
            />
          </div>
        </v-card>

        <!-- 9. Подпись водителя -->
        <v-card class="wbf-card" flat border>
          <div class="wbf-card-header">
            <v-icon color="primary" size="18">mdi-draw</v-icon>
            <span>Подпись водителя</span>
          </div>
          <div class="wbf-signature-wrap">
            <SignaturePad
              v-model="form.driver_signature"
              :readonly="form.status === 'closed' || form.status === 'on_review'"
              :width="480"
              :height="140"
            />
          </div>
          <div class="wbf-mt">
            <v-btn
              v-if="form.id && form.status === 'in_progress'"
              color="primary"
              :loading="signingLoading"
              prepend-icon="mdi-send"
              @click="driverSign"
            >
              Сдать путевой
            </v-btn>
          </div>
        </v-card>

        <!-- Workflow action buttons -->
        <div class="wbf-workflow-actions">
          <template v-if="form.id">
            <v-btn
              v-if="form.status === 'created'"
              color="warning"
              prepend-icon="mdi-wrench"
              :loading="actionLoading"
              @click="submitTechInspect"
            >
              Передать механику
            </v-btn>
            <v-btn
              v-if="form.status === 'tech_inspect'"
              color="success"
              prepend-icon="mdi-check"
              :loading="actionLoading"
              @click="confirmTechInspect"
            >
              Подтвердить тех. осмотр
            </v-btn>
            <v-btn
              v-if="form.status === 'med_inspect'"
              color="success"
              prepend-icon="mdi-medical-bag"
              :loading="actionLoading"
              @click="confirmMedInspect"
            >
              Подтвердить медосмотр
            </v-btn>
            <v-btn
              v-if="form.status === 'on_review'"
              color="primary"
              prepend-icon="mdi-archive-check"
              :loading="actionLoading"
              @click="closeWaybill"
            >
              Закрыть путевой лист
            </v-btn>
          </template>
        </div>
      </div>

      <!-- ── ASIDE column ── -->
      <div class="wbf-aside no-print">
        <div class="wbf-aside-sticky">
          <WaybillSummaryAside :waybill="asideWaybill" />
        </div>
      </div>

    </div><!-- /wbf-layout -->

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiFetch } from '@/api'

import StageStepper from '@/components/fleet/StageStepper.vue'
import StatusPill from '@/components/fleet/StatusPill.vue'
import GradientAvatar from '@/components/fleet/GradientAvatar.vue'
import InspectionBlock from '@/components/fleet/InspectionBlock.vue'
import OdometerField from '@/components/fleet/OdometerField.vue'
import FuelReadout from '@/components/fleet/FuelReadout.vue'
import RouteStopsEditor from '@/components/fleet/RouteStopsEditor.vue'
import SignaturePad from '@/components/fleet/SignaturePad.vue'
import WaybillSummaryAside from '@/components/fleet/WaybillSummaryAside.vue'
import LicensePlate from '@/components/vehicles/LicensePlate.vue'
import type { RouteStop } from '@/components/fleet/RouteStopsEditor.vue'
import { useToast } from '@/composables/useToast'

// ─── Types ────────────────────────────────────────────────────────────────────
interface Vehicle {
  id: number
  plate: string
  brand_model: string
  brand?: string
  model?: string
  year?: number
  vin?: string
  current_mileage_km?: number
  fuel_norm_summer?: number
  fuel_norm_winter?: number
  type?: string
}

interface Driver {
  id: number
  full_name: string
  license_categories?: string
  license_number?: string
  experience_years?: number
  driver_tab_number?: string
}

interface UserOption {
  id: number
  fullName: string
  role?: string
}

interface WaybillForm {
  id?: number
  number: string
  status: string
  date_start: string
  date_end: string
  waybill_type: string
  vehicle_id?: number
  driver_user_id?: number
  purpose: string
  route_stops: RouteStop[]
  planned_mileage_km?: number
  planned_duration?: string
  work_hours_norm?: string
  odometer_start?: number
  odometer_finish?: number
  fuel_remaining_start?: number
  fuel_issued_l?: number
  fuel_remaining_finish?: number
  cargo_description?: string
  cargo_weight_t?: number
  passengers_count?: number
  // Pre inspections
  pre_mechanic_id?: number
  pre_mechanic_at?: string
  pre_mechanic_result?: string
  pre_doctor_id?: number
  pre_doctor_at?: string
  pre_doctor_result?: string
  // Post inspections
  post_mechanic_id?: number
  post_mechanic_at?: string
  post_mechanic_result?: string
  post_doctor_id?: number
  post_doctor_at?: string
  post_doctor_result?: string
  // Signature
  driver_signature?: string
  // Aside helpers
  tech_inspect_ok?: boolean
  med_inspect_ok?: boolean
  fill_percent?: number
  planned_duration_h?: number
  status_history?: any[]
  related_docs?: any[]
}

// ─── Routing ──────────────────────────────────────────────────────────────────
const route = useRoute()
const router = useRouter()
const idParam = route.params.id as string
const isNew = idParam === 'new'
const queryVehicleId = isNew ? (Number(route.query.vehicle_id) || null) : null

// ─── State ────────────────────────────────────────────────────────────────────
const loading = ref(!isNew)
const saving = ref(false)
const actionLoading = ref(false)
const signingLoading = ref(false)
const downloadingDocx = ref(false)
const toast = useToast()
function showError(msg: string) {
  toast.error(msg)
}
function showSuccess(msg: string) {
  toast.success(msg)
}

const form = ref<WaybillForm>({
  number: '',
  status: 'created',
  date_start: '',
  date_end: '',
  waybill_type: 'passenger',
  purpose: '',
  route_stops: [
    { ord: 1, kind: 'start', name: '', description: '' },
    { ord: 2, kind: 'end',   name: '', description: '' },
  ],
})

const vehicles = ref<Vehicle[]>([])
const drivers  = ref<Driver[]>([])
const allUsers = ref<UserOption[]>([])

const waybillTypes = [
  { label: 'Легковой (Форма № 3)',  value: 'passenger' },
  { label: 'Грузовой (Форма № 4)', value: 'truck' },
  { label: 'Автобус (Форма № 6)',  value: 'bus' },
]

// ─── Computed ─────────────────────────────────────────────────────────────────
const selectedVehicle = computed(() =>
  vehicles.value.find(v => v.id === form.value.vehicle_id)
)
const selectedDriver = computed(() =>
  drivers.value.find(d => d.id === form.value.driver_user_id)
)
const mechanicUsers = computed(() => allUsers.value)
const doctorUsers   = computed(() => allUsers.value)

const actualMileage = computed<number | undefined>(() => {
  const s = form.value.odometer_start
  const f = form.value.odometer_finish
  if (s !== undefined && f !== undefined && f >= s) return f - s
  return undefined
})

const formReadonly = computed(() =>
  form.value.status === 'closed' || form.value.status === 'on_review'
)
const preInspectReadonly = computed(() =>
  ['in_progress', 'closing', 'on_review', 'closed'].includes(form.value.status)
)
const postInspectReadonly = computed(() =>
  ['closed'].includes(form.value.status)
)

const primaryActionLabel = computed(() => {
  if (isNew || form.value.status === 'created') return 'Передать в работу'
  if (form.value.status === 'tech_inspect')     return 'Подтвердить тех. осмотр'
  if (form.value.status === 'med_inspect')      return 'Подтвердить медосмотр'
  if (form.value.status === 'in_progress')      return 'Сдать путевой'
  if (form.value.status === 'on_review')        return 'Закрыть'
  return 'Сохранить'
})

const asideWaybill = computed(() => ({
  id: form.value.id ?? 0,
  number: form.value.number || 'Новый',
  date: form.value.date_start,
  valid_from: form.value.date_start,
  valid_to: form.value.date_end,
  fill_percent: form.value.fill_percent,
  planned_mileage_km: form.value.planned_mileage_km,
  planned_duration_h: form.value.planned_duration_h,
  tech_inspect_ok: form.value.tech_inspect_ok,
  med_inspect_ok: form.value.med_inspect_ok,
  status_history: form.value.status_history,
  related_docs: form.value.related_docs,
}))

// ─── Status helpers ───────────────────────────────────────────────────────────
function statusLabel(s: string): string {
  const map: Record<string, string> = {
    created:      'Создан',
    tech_inspect: 'Тех. осмотр',
    med_inspect:  'Медосмотр',
    in_progress:  'В работе',
    closing:      'Закрытие',
    on_review:    'На проверке',
    closed:       'Закрыт',
    overdue:      'Просрочен',
  }
  return map[s] ?? s
}

function statusVariant(s: string): 'ok' | 'warn' | 'alert' | 'info' | 'muted' {
  const map: Record<string, 'ok' | 'warn' | 'alert' | 'info' | 'muted'> = {
    created:      'info',
    tech_inspect: 'warn',
    med_inspect:  'warn',
    in_progress:  'ok',
    closing:      'warn',
    on_review:    'warn',
    closed:       'muted',
    overdue:      'alert',
  }
  return map[s] ?? 'muted'
}

// ─── Data loading ─────────────────────────────────────────────────────────────
function mapServerToForm(data: any): Partial<WaybillForm> {
  return {
    id: data.id,
    number: data.number,
    status: data.status,
    date_start: data.date_start ?? data.valid_from ?? '',
    date_end: data.date_end ?? data.valid_to ?? '',
    waybill_type: data.waybill_type ?? 'passenger',
    vehicle_id: data.vehicle_id,
    driver_user_id: data.driver_user_id,
    purpose: data.purpose ?? '',
    route_stops: data.route_stops?.length
      ? data.route_stops
      : [
          { ord: 1, kind: 'start', name: '', description: '' },
          { ord: 2, kind: 'end',   name: '', description: '' },
        ],
    planned_mileage_km: data.planned_mileage_km,
    planned_duration: data.planned_duration,
    work_hours_norm: data.work_hours_norm,
    odometer_start: data.odometer_start,
    odometer_finish: data.odometer_finish,
    fuel_remaining_start: data.fuel_remaining_start,
    fuel_issued_l: data.fuel_issued_l,
    fuel_remaining_finish: data.fuel_remaining_finish,
    cargo_description: data.cargo_description,
    cargo_weight_t: data.cargo_weight_t,
    passengers_count: data.passengers_count,
    pre_mechanic_id: data.pre_mechanic_id,
    pre_mechanic_at: data.pre_mechanic_at,
    pre_mechanic_result: data.pre_mechanic_result,
    pre_doctor_id: data.pre_doctor_id,
    pre_doctor_at: data.pre_doctor_at,
    pre_doctor_result: data.pre_doctor_result,
    post_mechanic_id: data.post_mechanic_id,
    post_mechanic_at: data.post_mechanic_at,
    post_mechanic_result: data.post_mechanic_result,
    post_doctor_id: data.post_doctor_id,
    post_doctor_at: data.post_doctor_at,
    post_doctor_result: data.post_doctor_result,
    driver_signature: data.driver_signature,
    tech_inspect_ok: data.tech_inspect_ok,
    med_inspect_ok: data.med_inspect_ok,
    fill_percent: data.fill_percent,
    planned_duration_h: data.planned_duration_h,
    status_history: data.status_history,
    related_docs: data.related_docs,
  }
}

async function loadWaybill() {
  loading.value = true
  try {
    const data = await apiFetch<any>(`/trips/${idParam}`)
    Object.assign(form.value, mapServerToForm(data))
  } catch (e) {
    console.error('[wbf] load error', e)
  } finally {
    loading.value = false
  }
}

async function loadVehicles() {
  try {
    // GET /api/vehicles отдаёт { items, total } (пагинация), а не голый массив —
    // найдено при проверке консоли на этой странице (2026-09-03): vehicles.value
    // становился объектом, и .find() валился с "is not a function", ломая
    // выбор ТС и подстановку в шапку путевого листа.
    const data = await apiFetch<Vehicle[] | { items: Vehicle[] }>('/vehicles/')
    vehicles.value = Array.isArray(data) ? data : (data?.items ?? [])
  } catch (e) {
    console.warn('[wbf] vehicles error', e)
  }
}

async function loadDrivers() {
  try {
    const data = await apiFetch<Driver[]>('/users/?can_drive=true&limit=200')
    drivers.value = data
  } catch (e) {
    console.warn('[wbf] drivers error', e)
  }
}

async function loadUsers() {
  try {
    const data = await apiFetch<any[]>('/users/')
    allUsers.value = data.map(u => ({
      id: u.id,
      fullName: u.full_name ?? u.fullName ?? `User #${u.id}`,
      role: u.role,
    }))
  } catch (e) {
    console.warn('[wbf] users error', e)
  }
}

// ─── Auto-populate for new waybill from vehicle ───────────────────────────────
async function autoPopulateFromVehicle(vehicleId: number) {
  try {
    const veh = await apiFetch<Vehicle>(`/vehicles/${vehicleId}`)
    // ensure vehicle is in the autocomplete list
    if (!vehicles.value.find(v => v.id === veh.id)) {
      vehicles.value = [veh, ...vehicles.value]
    }
    form.value.vehicle_id = veh.id

    // date_start = now in datetime-local format
    const now = new Date()
    const pad = (n: number) => String(n).padStart(2, '0')
    form.value.date_start = `${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`

    // waybill_type by vehicle.type
    const lightTypes = ['car_light', 'suv', 'minivan']
    if (lightTypes.includes(veh.type || '')) {
      form.value.waybill_type = 'passenger'
    } else if ((veh.type || '').startsWith('truck')) {
      form.value.waybill_type = 'truck'
    }

    // odometer_start from vehicle
    if (veh.current_mileage_km != null && !form.value.odometer_start) {
      form.value.odometer_start = veh.current_mileage_km
    }

    // fuel_remaining_start from last closed trip
    try {
      const fuelData = await apiFetch<{
        fuel_remaining_l: number | null
        from_waybill_number: string | null
        from_date: string | null
      }>(`/trips/last-fuel?vehicle_id=${vehicleId}`)
      if (fuelData.fuel_remaining_l != null) {
        form.value.fuel_remaining_start = fuelData.fuel_remaining_l
      }
    } catch (e) {
      console.warn('[wbf] last-fuel fetch error', e)
    }
  } catch (e) {
    console.warn('[wbf] auto-populate vehicle error', e)
  }
}

onMounted(async () => {
  await Promise.all([loadVehicles(), loadDrivers(), loadUsers()])
  if (!isNew) {
    await loadWaybill()
  } else {
    // Phase 30.3: auto-set текущий пользователь как водителя, если can_drive=true
    try {
      const me = await apiFetch<any>('/users/me')
      if (me?.can_drive && me?.id) {
        if (!drivers.value.find(d => d.id === me.id)) {
          drivers.value = [{ id: me.id, full_name: me.full_name || me.username || `User #${me.id}` }, ...drivers.value]
        }
        if (!form.value.driver_id) form.value.driver_id = me.id
      }
    } catch (e) {
      console.warn('[wbf] me fetch error', e)
    }
    if (queryVehicleId) {
      await autoPopulateFromVehicle(queryVehicleId)
    }
  }
})

// ─── Vehicle select ───────────────────────────────────────────────────────────
function onVehicleSelect() {
  if (selectedVehicle.value && !form.value.odometer_start) {
    form.value.odometer_start = selectedVehicle.value.current_mileage_km
  }
  scheduleAutosave()
}

// ─── Autosave ─────────────────────────────────────────────────────────────────
let autosaveTimer: ReturnType<typeof setTimeout> | null = null
function scheduleAutosave() {
  if (autosaveTimer) clearTimeout(autosaveTimer)
  autosaveTimer = setTimeout(() => { autosave() }, 1500)
}

async function autosave() {
  if (!form.value.id) return // new, not yet created
  try {
    await apiFetch(`/trips/${form.value.id}`, {
      method: 'PATCH',
      body: buildPayload() as any,
    })
  } catch (e) {
    console.warn('[wbf] autosave error', e)
  }
}

function buildPayload(): Record<string, unknown> {
  return {
    date_start: form.value.date_start || undefined,
    date_end: form.value.date_end || undefined,
    waybill_type: form.value.waybill_type,
    vehicle_id: form.value.vehicle_id,
    driver_user_id: form.value.driver_user_id,
    purpose: form.value.purpose,
    planned_mileage_km: form.value.planned_mileage_km,
    planned_duration: form.value.planned_duration,
    work_hours_norm: form.value.work_hours_norm,
    odometer_start: form.value.odometer_start,
    odometer_finish: form.value.odometer_finish,
    fuel_remaining_start: form.value.fuel_remaining_start,
    fuel_issued_l: form.value.fuel_issued_l,
    fuel_remaining_finish: form.value.fuel_remaining_finish,
    cargo_description: form.value.cargo_description,
    cargo_weight_t: form.value.cargo_weight_t,
    passengers_count: form.value.passengers_count,
    pre_mechanic_id: form.value.pre_mechanic_id,
    pre_mechanic_at: form.value.pre_mechanic_at,
    pre_mechanic_result: form.value.pre_mechanic_result,
    pre_doctor_id: form.value.pre_doctor_id,
    pre_doctor_at: form.value.pre_doctor_at,
    pre_doctor_result: form.value.pre_doctor_result,
    post_mechanic_id: form.value.post_mechanic_id,
    post_mechanic_at: form.value.post_mechanic_at,
    post_mechanic_result: form.value.post_mechanic_result,
    post_doctor_id: form.value.post_doctor_id,
    post_doctor_at: form.value.post_doctor_at,
    post_doctor_result: form.value.post_doctor_result,
  }
}

// ─── Save draft ───────────────────────────────────────────────────────────────
async function saveDraft() {
  if (!form.value.vehicle_id) {
    showError('Выберите транспортное средство для путевого листа')
    return
  }
  saving.value = true
  try {
    if (!form.value.id) {
      // Create
      const data = await apiFetch<any>('/trips/', {
        method: 'POST',
        body: buildPayload() as any,
      })
      Object.assign(form.value, mapServerToForm(data))
      router.replace(`/fleet/waybills/${form.value.id}`)
    } else {
      // Update
      await apiFetch(`/trips/${form.value.id}`, {
        method: 'PATCH',
        body: buildPayload() as any,
      })
    }
  } catch (e: any) {
    console.error('[wbf] save error', e)
    const code = e?.payload?.code || e?.detail?.code
    const msg = e?.payload?.message || e?.detail?.message
    if (code === 'VEHICLE_REQUIRED') {
      showError('Выберите транспортное средство для путевого листа')
    } else if (code === 'DRIVER_REQUIRED' || code === 'DRIVER_NOT_ELIGIBLE') {
      showError(msg || 'Укажите водителя с правом управления ТС')
    } else if (msg) {
      showError(msg)
    } else {
      showError('Ошибка сохранения путевого листа')
    }
  } finally {
    saving.value = false
  }
}

// ─── Primary action button ────────────────────────────────────────────────────
async function handlePrimaryAction() {
  const s = form.value.status
  if (!form.value.id || s === 'created') {
    await saveDraft()
    return
  }
  if (s === 'tech_inspect')  { await confirmTechInspect(); return }
  if (s === 'med_inspect')   { await confirmMedInspect();  return }
  if (s === 'in_progress')   { await driverSign();         return }
  if (s === 'on_review')     { await closeWaybill();       return }
  await saveDraft()
}

// ─── Workflow actions ─────────────────────────────────────────────────────────
async function submitTechInspect() {
  if (!form.value.id) return
  actionLoading.value = true
  try {
    const data = await apiFetch<any>(`/trips/${form.value.id}/tech-inspect`, {
      method: 'POST',
      body: {
        mechanic_id: form.value.pre_mechanic_id,
        inspected_at: form.value.pre_mechanic_at,
        result: form.value.pre_mechanic_result,
      } as any,
    })
    if (data?.status) form.value.status = data.status
  } catch (e) {
    console.error('[wbf] tech-inspect error', e)
  } finally {
    actionLoading.value = false
  }
}

async function confirmTechInspect() {
  await submitTechInspect()
}

async function confirmMedInspect() {
  if (!form.value.id) return
  actionLoading.value = true
  try {
    const data = await apiFetch<any>(`/trips/${form.value.id}/med-inspect`, {
      method: 'POST',
      body: {
        doctor_id: form.value.pre_doctor_id,
        inspected_at: form.value.pre_doctor_at,
        result: form.value.pre_doctor_result,
      } as any,
    })
    if (data?.status) form.value.status = data.status
  } catch (e) {
    console.error('[wbf] med-inspect error', e)
  } finally {
    actionLoading.value = false
  }
}

async function driverSign() {
  if (!form.value.id) return
  signingLoading.value = true
  try {
    const data = await apiFetch<any>(`/trips/${form.value.id}/driver-sign`, {
      method: 'POST',
      body: {
        signature: form.value.driver_signature,
        signed_at: new Date().toISOString(),
      } as any,
    })
    if (data?.status) form.value.status = data.status
  } catch (e) {
    console.error('[wbf] driver-sign error', e)
  } finally {
    signingLoading.value = false
  }
}

async function closeWaybill() {
  if (!form.value.id) return
  actionLoading.value = true
  try {
    const data = await apiFetch<any>(`/trips/${form.value.id}/close`, { method: 'POST', body: {} as any })
    if (data?.status) form.value.status = data.status
  } catch (e) {
    console.error('[wbf] close error', e)
  } finally {
    actionLoading.value = false
  }
}

// ─── Download .docx ───────────────────────────────────────────────────────────
async function downloadDocx() {
  if (!form.value.id) return
  downloadingDocx.value = true
  try {
    const token = localStorage.getItem('auth_token')
    const res = await fetch(`/api/trips/${form.value.id}/waybill.docx`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `Путевой_лист_${form.value.number || form.value.id}.docx`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    console.error('[wbf] docx download error', e)
  } finally {
    downloadingDocx.value = false
  }
}

// Watch route_stops + odometer for autosave
watch([() => form.value.odometer_start, () => form.value.odometer_finish,
       () => form.value.fuel_remaining_start, () => form.value.fuel_issued_l,
       () => form.value.fuel_remaining_finish], scheduleAutosave)

// ─── Phase 30.2: Print ────────────────────────────────────────────────────────
// Легковой/автобус → A5 landscape; грузовой (truck) → A4 landscape
const isLightVehicle = computed(() => {
  const t = form.value.waybill_type || ''
  return t !== 'truck' // passenger, bus → A5; truck → A4
})

function onPrint() {
  document.documentElement.dataset.printFormat = isLightVehicle.value ? 'a5' : 'a4'
  window.print()
}
</script>

<style scoped>
/* ─── Page layout ─── */
.wbf-page {
  --panel:   var(--v-theme-surface, #141823);
  --line:    rgba(var(--v-border-color), var(--v-border-opacity, 0.12));
  --text:    var(--v-theme-on-surface, #e9edf5);
  --muted:   #8a93a8;
  --accent:  #6aa6ff;
  --ok:      #22c997;
  --warn:    #f6b34a;
  --alert:   #ff5b6a;
  min-height: 100vh;
  background: var(--v-theme-background, #0a0d14);
}

/* ─── Sticky topbar ─── */
.wbf-topbar {
  position: sticky;
  top: 0;
  z-index: 20;
  background: rgba(var(--v-theme-surface), 0.95);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid var(--line);
  padding: 10px 28px;
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 20px;
}
.wbf-crumbs {
  font-size: 12px;
  color: var(--muted);
  white-space: nowrap;
}
.wbf-crumbs a { color: var(--accent); text-decoration: none; }
.wbf-crumbs a:hover { text-decoration: underline; }
.wbf-crumbs .sep { margin: 0 5px; opacity: 0.5; }
.wbf-crumbs .current { color: var(--text); }
.wbf-topbar-center {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.wbf-title {
  font-size: 18px;
  font-weight: 700;
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.wbf-topbar-actions { display: flex; gap: 8px; flex-shrink: 0; }

/* Mobile: 3-колоночный grid (крошки / заголовок / кнопки) на 390px не
   помещается и вылезает за экран горизонтально — владелец пожаловался,
   что «всё съехало». Складываем topbar в столбец и даём кнопкам
   переноситься на новую строку вместо overflow. */
@media (max-width: 640px) {
  .wbf-topbar {
    grid-template-columns: 1fr;
    padding: 10px 16px;
    gap: 8px;
  }
  .wbf-crumbs { white-space: normal; }
  .wbf-topbar-center { flex-wrap: wrap; }
  .wbf-title {
    white-space: normal;
    overflow: visible;
    text-overflow: unset;
    font-size: 16px;
  }
  .wbf-topbar-actions { flex-wrap: wrap; }
}

/* Stage stepper */
.wbf-stepper-wrap {
  padding: 6px 28px;
  border-bottom: 1px solid var(--line);
  background: var(--panel);
}
@media (max-width: 640px) {
  .wbf-stepper-wrap { padding: 6px 12px; }
}

/* Loading */
.wbf-loading {
  display: flex;
  justify-content: center;
  padding: 80px;
}

/* ─── 2-col layout ─── */
.wbf-layout {
  display: grid;
  grid-template-columns: 1.6fr 1fr;
  gap: 20px;
  padding: 20px 28px 60px;
  align-items: start;
}
@media (max-width: 1024px) {
  .wbf-layout {
    grid-template-columns: 1fr;
    padding: 12px 16px 60px;
  }
  .wbf-aside-sticky {
    position: static !important;
    top: auto !important;
  }
  .wbf-grid-3 {
    grid-template-columns: 1fr 1fr;
  }
}

/* Main column */
.wbf-main { display: grid; gap: 16px; }

/* Cards */
.wbf-card { padding: 16px 18px; }
.wbf-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 700;
  margin-bottom: 14px;
}

.wbf-grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.wbf-grid-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; }
.wbf-grid-col { display: grid; gap: 12px; }
.wbf-mt { margin-top: 12px; }
.wbf-section-label {
  font-size: 11.5px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  color: var(--muted);
  margin-bottom: 8px;
  margin-top: 12px;
}
.wbf-section-label:first-child { margin-top: 0; }

.font-mono { font-family: 'JetBrains Mono', monospace !important; }

/* Vehicle preview */
.wbf-veh-preview {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  background: rgba(255,255,255,0.02);
  border: 1px solid var(--line);
  border-radius: 10px;
  margin-top: 10px;
}
.wbf-veh-preview-icon {
  width: 44px; height: 28px;
  background: rgba(106,166,255,0.08);
  border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.wbf-veh-info { flex: 1; min-width: 0; }
.wbf-veh-main { display: flex; align-items: center; gap: 10px; }
.wbf-veh-model { font-size: 13px; font-weight: 600; }
.wbf-veh-sub { font-size: 11.5px; color: var(--muted); margin-top: 3px; }

/* Driver preview */
.wbf-driver-preview {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  background: rgba(255,255,255,0.02);
  border: 1px solid var(--line);
  border-radius: 10px;
  margin-top: 10px;
}
.wbf-driver-info { flex: 1; min-width: 0; }
.wbf-driver-name { font-size: 14px; font-weight: 700; }
.wbf-driver-sub  { font-size: 11.5px; color: var(--muted); margin-top: 2px; }

/* Odometer computed */
.wbf-mileage-computed {
  font-size: 12.5px;
  color: var(--muted);
  margin-top: 8px;
}
.wbf-mono { font-family: 'JetBrains Mono', monospace; font-weight: 700; color: var(--ok); }

/* Inspections */
.wbf-inspections { display: grid; gap: 12px; }

/* Signature */
.wbf-signature-wrap {
  display: flex;
  justify-content: center;
  padding: 8px 0;
}

/* Workflow actions */
.wbf-workflow-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  padding: 12px 0;
}

/* Aside */
.wbf-aside-sticky {
  position: sticky;
  top: 80px;
}

/* ─── Phase 30.2: Print styles ────────────────────────────────────────────── */
/* Эти правила должны действовать ТОЛЬКО при печати (window.print()) — раньше
   были объявлены без @media print и ломали экранную вёрстку целиком:
   .no-print гасил topbar/stepper/aside на экране, а .wbf-print-area делал
   .wbf-layout position:absolute поверх сайдбара. Баг найден при жалобе
   владельца «всё съехало» на /fleet/waybills/new (2026-09-03). */
@media print {
  /* Скрыть всё UI-«обёрточное», показать только форму */
  .no-print { display: none !important; }

  /* Wrapper */
  .wbf-print-area {
    position: absolute;
    left: 0; top: 0;
    width: 100%;
  }

  /* Убрать тени, оставить рамки */
  .wbf-print-area .v-card {
    box-shadow: none !important;
    border: 1px solid #000 !important;
    page-break-inside: avoid;
  }

  /* Сжать отступы */
  .wbf-print-area .v-card { margin-bottom: 6mm; padding: 4mm; }
  .wbf-print-area .v-text-field { margin-bottom: 3px; }
  .wbf-print-area .v-input__details { display: none; }

  /* Послерейсовые осмотры начинаются с новой страницы (оборотная сторона) */
  .wbf-section-posttrip { page-break-before: always; }
}

/* Light theme */
.v-theme--light .wbf-topbar { background: rgba(255,255,255,0.95); }
.v-theme--light .wbf-stepper-wrap { background: #fff; }
</style>

<!-- Phase 30.2: global @page rules (non-scoped — @page cannot be scoped) -->
<style>
/* ── A5 landscape — легковой/автобус (по умолчанию) ── */
@media print {
  @page {
    size: A5 landscape;
    margin: 8mm;
  }

  /* Скрыть navigation drawer, app-bar и всё вне формы */
  .v-navigation-drawer,
  .v-app-bar,
  .v-overlay,
  .wbf-topbar,
  .wbf-stepper-wrap,
  .wbf-aside,
  .no-print {
    display: none !important;
  }

  body {
    background: #fff !important;
    color: #000 !important;
  }

  .wbf-print-area {
    position: static !important;
    width: 100%;
    font-size: 10pt;
    color: #000;
    background: #fff;
  }

  /* Двусторонняя с разворотом по длинному краю */
  @page :left  { margin: 8mm 10mm 8mm 8mm; }
  @page :right { margin: 8mm 8mm 8mm 10mm; }

  .wbf-layout {
    grid-template-columns: 1fr !important;
    gap: 0 !important;
    padding: 0 !important;
  }
}

/* ── A4 landscape — грузовой ── */
html[data-print-format=a4] {
  @media print {
    @page {
      size: A4 landscape;
      margin: 10mm;
    }
    @page :left  { margin: 10mm 12mm 10mm 10mm; }
    @page :right { margin: 10mm 10mm 10mm 12mm; }
  }
}
.print-a4 {
  @media print {
    @page {
      size: A4 landscape;
      margin: 10mm;
    }
  }
}
</style>
