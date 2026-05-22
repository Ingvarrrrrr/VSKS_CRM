<template>
  <div class="driver-home">
    <!-- Greeting -->
    <div class="driver-home__greeting pa-4 pb-0">
      <div class="text-h5 font-weight-black">{{ greeting }}, {{ userName }}!</div>
      <div class="text-body-2 mt-1" style="opacity: 0.6">{{ todayStr }}</div>
    </div>

    <!-- Vehicle selector (if no vehicle selected) -->
    <div v-if="!selectedVehicleId" class="pa-4">
      <v-card variant="outlined" class="rounded-xl pa-4">
        <div class="text-subtitle-2 mb-3 text-medium-emphasis">Выберите ТС</div>
        <v-autocomplete
          v-model="selectedVehicleId"
          :items="vehicleOptions"
          item-title="label"
          item-value="id"
          label="Транспортное средство"
          variant="outlined"
          density="comfortable"
          hide-details
          rounded="lg"
          prepend-inner-icon="mdi-car"
          @update:model-value="onVehicleSelect"
        />
      </v-card>
    </div>

    <!-- Vehicle card -->
    <div v-if="vehicle" class="pa-4 pt-3">
      <v-card class="driver-home__car-card rounded-xl" variant="outlined">
        <!-- Status badge -->
        <div class="driver-home__car-card__badge">
          <StatusPill :variant="vehicleStatusVariant" :dot="true" :label="vehicleStatusLabel" />
        </div>

        <!-- Silhouette -->
        <div class="driver-home__silhouette">
          <VehicleTypeIcon :type="vehicle.vehicle_type" :size="130" />
        </div>

        <!-- Plate + model -->
        <div class="pa-3 pt-2">
          <LicensePlate :model-value="vehicle.license_plate || ''" size="md" />
          <div class="text-subtitle-1 font-weight-bold mt-2">
            {{ vehicleTitle }}
          </div>
          <div class="text-caption mt-1" style="opacity: 0.6">
            {{ vehicleSubtitle }}
          </div>

          <!-- Info strips -->
          <v-row class="mt-3" dense>
            <v-col v-for="strip in infoStrips" :key="strip.label" cols="6">
              <div class="driver-home__strip rounded-lg pa-2">
                <div class="driver-home__strip__label text-caption font-weight-bold">
                  {{ strip.label }}
                </div>
                <div class="driver-home__strip__value text-body-2 font-weight-bold mt-1">
                  {{ strip.value }}
                </div>
              </div>
            </v-col>
          </v-row>
        </div>
      </v-card>
    </div>

    <!-- Loading skeleton for vehicle -->
    <div v-else-if="loadingVehicle && selectedVehicleId" class="pa-4 pt-3">
      <v-skeleton-loader type="card" class="rounded-xl" />
    </div>

    <!-- Quick actions -->
    <div class="pa-4 pt-0">
      <v-row dense>
        <v-col cols="6">
          <v-card
            class="driver-home__quick-btn rounded-xl pa-3"
            variant="outlined"
            @click="openOdometerDialog"
            :disabled="!vehicle"
          >
            <div class="driver-home__quick-btn__icon driver-home__quick-btn__icon--ok mb-2">
              <v-icon icon="mdi-speedometer" size="18" />
            </div>
            <div class="text-body-2 font-weight-bold">Обновить пробег</div>
            <div class="text-caption mt-1" style="opacity: 0.5">
              {{ vehicle?.current_odometer_km ? `${vehicle.current_odometer_km.toLocaleString('ru-RU')} км` : 'нет данных' }}
            </div>
          </v-card>
        </v-col>
        <v-col cols="6">
          <v-card
            class="driver-home__quick-btn rounded-xl pa-3"
            variant="outlined"
            :to="{ name: 'm-driver-checklist' }"
            :disabled="!vehicle"
          >
            <div class="driver-home__quick-btn__icon mb-2">
              <v-icon icon="mdi-clipboard-check-outline" size="18" />
            </div>
            <div class="text-body-2 font-weight-bold">Чек-лист</div>
            <div class="text-caption mt-1" style="opacity: 0.5">провести осмотр</div>
          </v-card>
        </v-col>
        <v-col cols="6">
          <v-card
            class="driver-home__quick-btn driver-home__quick-btn--alert rounded-xl pa-3"
            variant="outlined"
            :to="{ name: 'm-driver-incident' }"
            :disabled="!vehicle"
          >
            <div class="driver-home__quick-btn__icon driver-home__quick-btn__icon--alert mb-2">
              <v-icon icon="mdi-alert-circle-outline" size="18" />
            </div>
            <div class="text-body-2 font-weight-bold">Неисправность</div>
            <div class="text-caption mt-1" style="opacity: 0.5">сообщить срочно</div>
          </v-card>
        </v-col>
        <v-col cols="6">
          <v-card
            class="driver-home__quick-btn driver-home__quick-btn--warn rounded-xl pa-3"
            variant="outlined"
            :disabled="!vehicle"
          >
            <div class="driver-home__quick-btn__icon driver-home__quick-btn__icon--warn mb-2">
              <v-icon icon="mdi-wrench-clock" size="18" />
            </div>
            <div class="text-body-2 font-weight-bold">Запросить ТО</div>
            <div class="text-caption mt-1" style="opacity: 0.5">
              {{ nextServiceHint }}
            </div>
          </v-card>
        </v-col>
        <v-col cols="12">
          <v-card
            class="driver-home__quick-btn driver-home__quick-btn--waybill rounded-xl pa-3"
            variant="outlined"
            @click="openWaybill"
            :loading="loadingWaybill"
          >
            <div class="d-flex align-center ga-3">
              <div class="driver-home__quick-btn__icon driver-home__quick-btn__icon--waybill">
                <v-icon icon="mdi-clipboard-list-outline" size="20" />
              </div>
              <div>
                <div class="text-body-2 font-weight-bold">Путевой лист</div>
                <div class="text-caption mt-0_5" style="opacity: 0.5">
                  {{ activeWaybillId ? `Активный № ${activeWaybillId}` : 'нет активных' }}
                </div>
              </div>
              <v-spacer />
              <v-chip
                v-if="activeWaybillId"
                size="x-small"
                color="success"
                variant="tonal"
              >В работе</v-chip>
              <v-chip
                v-else
                size="x-small"
                color="default"
                variant="tonal"
              >Нет</v-chip>
            </div>
          </v-card>
        </v-col>
      </v-row>
    </div>

    <!-- Documents section -->
    <div v-if="vehicle" class="pa-4 pt-0">
      <div class="d-flex align-center justify-space-between mb-2">
        <div class="text-caption font-weight-bold text-uppercase" style="letter-spacing: 0.4px; opacity: 0.5">
          Документы и сроки
        </div>
      </div>
      <div class="d-flex flex-column gap-2">
        <v-card
          v-for="doc in documents"
          :key="doc.key"
          variant="outlined"
          class="rounded-xl pa-3 d-flex align-center"
          style="gap: 12px"
        >
          <div class="driver-home__doc-dot" :class="`driver-home__doc-dot--${doc.variant}`"></div>
          <div style="flex: 1">
            <div class="text-body-2 font-weight-semibold">{{ doc.name }}</div>
            <div class="text-caption mt-0_5" style="opacity: 0.55">{{ doc.desc }}</div>
          </div>
          <div class="text-caption font-weight-bold" :class="docRightClass(doc.variant)">{{ doc.right }}</div>
        </v-card>
      </div>
    </div>

    <!-- Activity feed -->
    <div v-if="vehicle && (recentItems.length > 0 || loadingFeed)" class="pa-4 pt-0">
      <div class="text-caption font-weight-bold text-uppercase mb-2" style="letter-spacing: 0.4px; opacity: 0.5">
        Последние отчёты
      </div>
      <v-skeleton-loader v-if="loadingFeed" type="list-item-two-line@3" />
      <div v-else class="d-flex flex-column gap-2">
        <v-card
          v-for="item in recentItems"
          :key="item.key"
          variant="outlined"
          class="rounded-xl pa-3 d-flex align-start"
          style="gap: 10px"
        >
          <div class="driver-home__feed-icon rounded-lg d-flex align-center justify-center flex-shrink-0"
               :class="`driver-home__feed-icon--${item.variant}`">
            <v-icon :icon="item.icon" size="14" />
          </div>
          <div style="flex: 1">
            <div class="text-body-2">{{ item.text }}</div>
            <div class="text-caption mt-0_5" style="opacity: 0.5">{{ item.sub }}</div>
          </div>
        </v-card>
      </div>
    </div>

    <!-- Bottom padding for safe area -->
    <div style="height: 24px" />

    <!-- Odometer update dialog -->
    <v-dialog v-model="odometerDialog" max-width="400" :fullscreen="false">
      <v-card class="rounded-xl">
        <v-card-title class="text-h6 pa-4">Обновить пробег</v-card-title>
        <v-card-text class="pa-4 pt-0">
          <v-text-field
            v-model.number="newOdometer"
            type="number"
            label="Текущий пробег, км"
            variant="outlined"
            density="comfortable"
            suffix="км"
            :hint="vehicle ? `Последнее значение: ${vehicle.current_odometer_km?.toLocaleString('ru-RU') ?? '—'} км` : ''"
            persistent-hint
            rounded="lg"
          />
        </v-card-text>
        <v-card-actions class="pa-4 pt-0 gap-2">
          <v-btn variant="outlined" rounded="lg" @click="odometerDialog = false">Отмена</v-btn>
          <v-btn
            color="primary"
            variant="flat"
            rounded="lg"
            :loading="savingOdometer"
            @click="saveOdometer"
          >
            Сохранить
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Snackbar -->
    <v-snackbar v-model="snack.show" :color="snack.color" :timeout="3000" rounded="lg">
      {{ snack.text }}
      <template #actions>
        <v-btn variant="text" size="small" @click="snack.show = false">Закрыть</v-btn>
      </template>
    </v-snackbar>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import LicensePlate from '@/components/vehicles/LicensePlate.vue'
import VehicleTypeIcon from '@/components/vehicles/VehicleTypeIcon.vue'
import StatusPill from '@/components/fleet/StatusPill.vue'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
const router = useRouter()

// ---- State ----
const selectedVehicleId = ref<number | null>(
  localStorage.getItem('driver_selected_vehicle_id')
    ? parseInt(localStorage.getItem('driver_selected_vehicle_id')!)
    : null
)
const vehicle = ref<any>(null)
const vehicleOptions = ref<{ id: number; label: string }[]>([])
const loadingVehicle = ref(false)
const loadingFeed = ref(false)
const recentItems = ref<any[]>([])

const odometerDialog = ref(false)
const newOdometer = ref<number | null>(null)
const savingOdometer = ref(false)

const snack = ref({ show: false, text: '', color: 'success' })

// ---- Active waybill ----
const activeWaybillId = ref<number | null>(null)
const loadingWaybill = ref(false)
const ACTIVE_WB_STATUSES = ['created', 'tech_inspect', 'med_inspect', 'in_progress', 'closing', 'on_review']

// ---- Computed ----
const userName = computed(() => {
  const u = authStore.user as any
  if (!u) return ''
  if (u.last_name && u.first_name) return `${u.last_name} ${u.first_name[0]}.`
  if (u.last_name) return u.last_name
  if (u.full_name) return u.full_name
  return u.username || 'Водитель'
})

const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return 'Доброй ночи'
  if (h < 12) return 'Доброе утро'
  if (h < 17) return 'Добрый день'
  if (h < 22) return 'Добрый вечер'
  return 'Доброй ночи'
})

const todayStr = computed(() => {
  return new Date().toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'long',
    weekday: 'long',
  })
})

const vehicleTitle = computed(() => {
  if (!vehicle.value) return ''
  const parts = []
  if (vehicle.value.brand) parts.push(vehicle.value.brand)
  if (vehicle.value.model) parts.push(vehicle.value.model)
  if (vehicle.value.year) parts.push(`· ${vehicle.value.year}`)
  return parts.join(' ')
})

const vehicleSubtitle = computed(() => {
  if (!vehicle.value) return ''
  const parts = []
  if (vehicle.value.vehicle_type_display || vehicle.value.vehicle_type) {
    parts.push(vehicle.value.vehicle_type_display || vehicle.value.vehicle_type)
  }
  if (vehicle.value.color) parts.push(vehicle.value.color)
  if (vehicle.value.current_station_name) parts.push(vehicle.value.current_station_name)
  return parts.join(' · ')
})

const vehicleStatusVariant = computed<'ok' | 'warn' | 'alert' | 'muted'>(() => {
  const s = vehicle.value?.operational_status
  if (!s) return 'muted'
  if (s === 'operational') return 'ok'
  if (s === 'under_repair' || s === 'maintenance') return 'warn'
  if (s === 'decommissioned' || s === 'accident') return 'alert'
  return 'muted'
})

const vehicleStatusLabel = computed(() => {
  const s = vehicle.value?.operational_status
  if (!s) return 'Неизвестно'
  const map: Record<string, string> = {
    operational: 'Рабочее',
    under_repair: 'В ремонте',
    maintenance: 'ТО',
    decommissioned: 'Списано',
    accident: 'ДТП',
    reserve: 'В резерве',
  }
  return map[s] || s
})

const infoStrips = computed(() => {
  if (!vehicle.value) return []
  const v = vehicle.value
  return [
    {
      label: 'Пробег',
      value: v.current_odometer_km
        ? `${v.current_odometer_km.toLocaleString('ru-RU')} км`
        : '—',
    },
    {
      label: 'Последнее ТО',
      value: v.last_service_odometer_km
        ? `${v.last_service_odometer_km.toLocaleString('ru-RU')} км`
        : (v.last_service_date ? fmtDate(v.last_service_date) : '—'),
    },
    {
      label: 'ПТС',
      value: v.pts_number || '—',
    },
    {
      label: 'СТС',
      value: v.sts_number || '—',
    },
  ]
})

const nextServiceHint = computed(() => {
  const v = vehicle.value
  if (!v) return 'нет данных'
  const interval = v.service_interval_km || 10000
  const odometer = v.current_odometer_km || 0
  const lastService = v.last_service_odometer_km || 0
  const nextAt = lastService + interval
  const remaining = nextAt - odometer
  if (remaining <= 0) return 'требуется ТО!'
  return `ещё ~${remaining.toLocaleString('ru-RU')} км`
})

const documents = computed(() => {
  const v = vehicle.value
  if (!v) return []
  const today = new Date()
  const items: any[] = []

  if (v.insurance_policy_end) {
    const exp = new Date(v.insurance_policy_end)
    const days = Math.round((exp.getTime() - today.getTime()) / 86400000)
    items.push({
      key: 'osago',
      name: 'ОСАГО',
      desc: `действует до ${fmtDate(v.insurance_policy_end)}`,
      right: days > 0 ? `${days} дн.` : 'истёк',
      variant: days > 30 ? 'ok' : days > 0 ? 'warn' : 'alert',
    })
  }

  if (v.tech_inspection_until) {
    const exp = new Date(v.tech_inspection_until)
    const days = Math.round((exp.getTime() - today.getTime()) / 86400000)
    items.push({
      key: 'tech',
      name: 'Техосмотр',
      desc: days > 0 ? `до ${fmtDate(v.tech_inspection_until)}` : 'требуется оформление',
      right: days > 0 ? `${days} дн.` : 'просрочен',
      variant: days > 30 ? 'ok' : days > 0 ? 'warn' : 'alert',
    })
  }

  if (v.pts_number) {
    items.push({ key: 'pts', name: 'ПТС', desc: v.pts_number, right: 'OK', variant: 'ok' })
  }
  if (v.sts_number) {
    items.push({ key: 'sts', name: 'СТС', desc: v.sts_number, right: 'OK', variant: 'ok' })
  }

  return items
})

// ---- Methods ----
function fmtDate(s: string): string {
  if (!s) return '—'
  return new Date(s).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit' })
}

function docRightClass(variant: string) {
  if (variant === 'ok') return 'text-success'
  if (variant === 'warn') return 'text-warning'
  if (variant === 'alert') return 'text-error'
  return ''
}

function openOdometerDialog() {
  newOdometer.value = vehicle.value?.current_odometer_km ?? null
  odometerDialog.value = true
}

async function loadVehicles() {
  try {
    const token = localStorage.getItem('auth_token')
    const res = await fetch('/api/vehicles/?limit=50', {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) return
    const data = await res.json()
    const list = data.items ?? data.results ?? data ?? []
    vehicleOptions.value = list.map((v: any) => ({
      id: v.id,
      label: `${v.license_plate || '—'} — ${v.brand || ''} ${v.model || ''}`.trim(),
    }))
  } catch {
    // ignore
  }
}

async function loadVehicle(id: number) {
  loadingVehicle.value = true
  try {
    const token = localStorage.getItem('auth_token')
    const res = await fetch(`/api/vehicles/${id}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) return
    vehicle.value = await res.json()
    await loadFeed(id)
  } catch {
    vehicle.value = null
  } finally {
    loadingVehicle.value = false
  }
}

async function loadFeed(vehicleId: number) {
  loadingFeed.value = true
  try {
    const token = localStorage.getItem('auth_token')
    const [clRes, incRes] = await Promise.all([
      fetch(`/api/checklists/?vehicle_id=${vehicleId}&limit=5`, {
        headers: { Authorization: `Bearer ${token}` },
      }),
      fetch(`/api/incidents/?vehicle_id=${vehicleId}&limit=5`, {
        headers: { Authorization: `Bearer ${token}` },
      }),
    ])

    const items: any[] = []

    if (clRes.ok) {
      const clData = await clRes.json()
      const clList = clData.items ?? clData.results ?? clData ?? []
      for (const c of clList.slice(0, 3)) {
        const hasIssues = c.overall_state !== 'operational'
        items.push({
          key: `cl-${c.id}`,
          icon: hasIssues ? 'mdi-alert' : 'mdi-check',
          variant: hasIssues ? 'warn' : 'ok',
          text: hasIssues
            ? `Чек-лист: замечания (${c.overall_state})`
            : 'Чек-лист пройден — все системы ОК',
          sub: fmtDate(c.created_at) + ' · отправлено',
        })
      }
    }

    if (incRes.ok) {
      const incData = await incRes.json()
      const incList = incData.items ?? incData.results ?? incData ?? []
      for (const i of incList.slice(0, 3)) {
        items.push({
          key: `inc-${i.id}`,
          icon: 'mdi-alert-circle',
          variant: i.severity === 'high' || i.severity === 'critical' ? 'alert' : 'warn',
          text: `Инцидент: ${i.incident_type || i.affected_system || 'неизвестно'}`,
          sub: fmtDate(i.created_at) + ' · принято',
        })
      }
    }

    // Sort by newest first (approximate by key order)
    recentItems.value = items.slice(0, 5)
  } catch {
    recentItems.value = []
  } finally {
    loadingFeed.value = false
  }
}

function onVehicleSelect(id: number) {
  if (!id) return
  localStorage.setItem('driver_selected_vehicle_id', String(id))
  loadVehicle(id)
}

async function loadActiveWaybill() {
  loadingWaybill.value = true
  try {
    const token = localStorage.getItem('auth_token')
    const res = await fetch('/api/trips/?limit=10&ordering=-id', {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) return
    const data = await res.json()
    const list: any[] = data.items ?? data.results ?? data ?? []
    const active = list.find((w: any) => ACTIVE_WB_STATUSES.includes(w.status))
    activeWaybillId.value = active?.id ?? null
  } catch {
    activeWaybillId.value = null
  } finally {
    loadingWaybill.value = false
  }
}

function openWaybill() {
  if (activeWaybillId.value) {
    router.push({ name: 'm-driver-waybill', params: { id: String(activeWaybillId.value) } })
  } else {
    snack.value = { show: true, text: 'Активных путевых листов нет. Обратитесь к диспетчеру.', color: 'info' }
  }
}

async function saveOdometer() {
  if (!vehicle.value || newOdometer.value == null) return
  if (newOdometer.value < (vehicle.value.current_odometer_km || 0)) {
    snack.value = { show: true, text: 'Пробег не может быть меньше текущего', color: 'error' }
    return
  }
  savingOdometer.value = true
  try {
    const token = localStorage.getItem('auth_token')
    const res = await fetch(`/api/vehicles/${vehicle.value.id}`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ current_odometer_km: newOdometer.value }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => null)
      throw new Error(err?.detail || `HTTP ${res.status}`)
    }
    vehicle.value.current_odometer_km = newOdometer.value
    odometerDialog.value = false
    snack.value = { show: true, text: 'Пробег обновлён', color: 'success' }
  } catch (e: any) {
    snack.value = { show: true, text: `Ошибка: ${e.message}`, color: 'error' }
  } finally {
    savingOdometer.value = false
  }
}

// ---- Lifecycle ----
onMounted(async () => {
  await loadVehicles()
  if (selectedVehicleId.value) {
    await loadVehicle(selectedVehicleId.value)
  }
  loadActiveWaybill()
})

watch(selectedVehicleId, (id) => {
  if (id) {
    localStorage.setItem('driver_selected_vehicle_id', String(id))
  }
})
</script>

<style scoped>
.driver-home {
  max-width: 480px;
  margin: 0 auto;
  padding-bottom: env(safe-area-inset-bottom, 0);
}

.driver-home__car-card {
  position: relative;
  overflow: hidden;
}

.driver-home__car-card__badge {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 1;
}

.driver-home__silhouette {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  border-radius: 12px;
  margin: 12px 12px 0;
  background: rgba(var(--v-theme-surface-variant), 0.5);
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  min-height: 90px;
}

.driver-home__strip {
  background: rgba(var(--v-theme-surface-variant), 0.4);
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.driver-home__strip__label {
  text-transform: uppercase;
  letter-spacing: 0.4px;
  opacity: 0.55;
}

.driver-home__quick-btn {
  cursor: pointer;
  transition: border-color 0.15s;
}

.driver-home__quick-btn:hover {
  border-color: rgba(var(--v-theme-primary), 0.5);
}

.driver-home__quick-btn__icon {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgb(var(--v-theme-primary));
}

.driver-home__quick-btn__icon--ok {
  background: rgba(34, 201, 151, 0.12);
  color: #22c997;
}

.driver-home__quick-btn__icon--warn {
  background: rgba(246, 179, 74, 0.12);
  color: #f6b34a;
}

.driver-home__quick-btn__icon--alert {
  background: rgba(255, 91, 106, 0.12);
  color: #ff5b6a;
}

.driver-home__doc-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.driver-home__doc-dot--ok { background: #22c997; }
.driver-home__doc-dot--warn { background: #f6b34a; }
.driver-home__doc-dot--alert { background: #ff5b6a; }
.driver-home__doc-dot--muted { background: #8a93a8; }

.driver-home__feed-icon {
  width: 30px;
  height: 30px;
}

.driver-home__feed-icon--ok {
  background: rgba(34, 201, 151, 0.15);
  color: #22c997;
}

.driver-home__feed-icon--warn {
  background: rgba(246, 179, 74, 0.15);
  color: #f6b34a;
}

.driver-home__feed-icon--alert {
  background: rgba(255, 91, 106, 0.15);
  color: #ff5b6a;
}

.driver-home__feed-icon--info {
  background: rgba(93, 208, 255, 0.15);
  color: #5dd0ff;
}

.driver-home__quick-btn--waybill {
  border-color: rgba(var(--v-theme-primary), 0.25);
}
.driver-home__quick-btn--waybill:hover {
  border-color: rgba(var(--v-theme-primary), 0.5);
  background: rgba(var(--v-theme-primary), 0.04);
}
.driver-home__quick-btn__icon--waybill {
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgb(var(--v-theme-primary));
}

.gap-2 {
  gap: 8px;
}

.mt-0_5 {
  margin-top: 2px;
}
</style>
