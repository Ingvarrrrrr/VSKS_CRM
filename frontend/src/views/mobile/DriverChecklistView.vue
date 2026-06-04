<template>
  <div class="checklist">
    <!-- Header: progress bar -->
    <div class="checklist__header pa-4 pb-0">
      <div class="d-flex align-center justify-space-between mb-2">
        <div class="text-h6 font-weight-bold">Чек-лист осмотра</div>
        <div class="text-caption font-weight-bold text-medium-emphasis">{{ progressPct }}%</div>
      </div>
      <v-progress-linear
        :model-value="progressPct"
        color="primary"
        rounded
        height="6"
        class="mb-3"
      />
      <!-- Compact vehicle row -->
      <div v-if="vehicle" class="d-flex align-center gap-3 mb-1">
        <div class="checklist__veh-thumb rounded-lg d-flex align-center justify-center">
          <VehicleTypeIcon :type="vehicle.vehicle_type" :size="40" />
        </div>
        <div>
          <LicensePlate :model-value="vehicle.license_plate || ''" size="sm" />
          <div class="text-caption mt-1 text-medium-emphasis">
            {{ [vehicle.brand, vehicle.model].filter(Boolean).join(' ') }}
            {{ vehicle.current_station_name ? '· ' + vehicle.current_station_name : '' }}
          </div>
        </div>
      </div>
      <div v-else class="text-caption text-medium-emphasis mb-1">Нет выбранного ТС</div>
    </div>

    <!-- Single scrollable form: all sections visible -->
    <div class="checklist__body pa-4">

      <!-- Текущий пробег -->
      <div class="checklist__section">
        <div class="checklist__field-label">Текущий пробег, км</div>
        <v-text-field
          v-model.number="form.odometer"
          type="number"
          variant="outlined"
          density="comfortable"
          suffix="км"
          rounded="lg"
          hide-details="auto"
          placeholder="Введите пробег"
          class="mt-2"
        >
          <template #append-inner>
            <v-btn
              v-if="vehicle?.current_odometer_km"
              size="x-small"
              variant="text"
              color="primary"
              class="text-caption"
              @click="form.odometer = vehicle.current_odometer_km"
            >Авто</v-btn>
          </template>
        </v-text-field>
        <div v-if="vehicle?.current_odometer_km" class="text-caption mt-2 text-medium-emphasis">
          Последнее значение: {{ vehicle.current_odometer_km.toLocaleString('ru-RU') }} км
        </div>
      </div>

      <!-- Уровень топлива (сегментированный) -->
      <div class="checklist__section">
        <div class="checklist__field-label">Уровень топлива</div>
        <div class="checklist__seg mt-2">
          <button
            v-for="opt in fuelOptions"
            :key="opt.value"
            class="checklist__seg__opt"
            :class="{ 'checklist__seg__opt--active': form.fuelLevel === opt.value }"
            @click="form.fuelLevel = opt.value"
          >{{ opt.label }}</button>
        </div>
      </div>

      <!-- Общее тех. состояние -->
      <div class="checklist__section">
        <div class="checklist__field-label">Общее тех. состояние</div>
        <div class="checklist__toggle mt-2">
          <button
            v-for="opt in stateOptions"
            :key="opt.value"
            class="checklist__toggle__opt"
            :class="[
              { 'checklist__toggle__opt--active': form.overallState === opt.value },
              `checklist__toggle__opt--${opt.color}`
            ]"
            @click="form.overallState = opt.value"
          >{{ opt.label }}</button>
        </div>
      </div>

      <!-- Комплектность -->
      <div class="checklist__section">
        <div class="checklist__field-label">Комплектность · нажми статус</div>
        <div class="d-flex flex-column gap-2 mt-2">
          <div
            v-for="item in checkItems"
            :key="item.key"
            class="checklist__item rounded-xl pa-3 d-flex align-center"
            style="gap: 10px"
          >
            <div class="text-body-2 font-weight-semibold" style="flex: 1">{{ item.label }}</div>
            <div class="d-flex gap-1">
              <button
                v-for="pip in pips"
                :key="pip.value"
                class="checklist__pip rounded-lg"
                :class="[
                  form.items[item.key] === pip.value
                    ? `checklist__pip--${pip.color}`
                    : ''
                ]"
                @click="form.items[item.key] = pip.value"
              >{{ pip.label }}</button>
            </div>
          </div>
        </div>
      </div>

      <!-- Состояние ЛКП -->
      <div class="checklist__section">
        <div class="checklist__field-label">Состояние ЛКП</div>
        <div class="checklist__toggle mt-2">
          <button
            v-for="opt in paintOptions"
            :key="opt.value"
            class="checklist__toggle__opt"
            :class="[
              { 'checklist__toggle__opt--active': form.paintCondition === opt.value },
              `checklist__toggle__opt--${opt.color}`
            ]"
            @click="form.paintCondition = opt.value"
          >{{ opt.label }}</button>
        </div>
      </div>

      <!-- Фото -->
      <div class="checklist__section">
        <div class="checklist__field-label">Фото (до 5)</div>
        <div class="checklist__photo-grid mt-2">
          <div
            v-for="n in 5"
            :key="n"
            class="checklist__photo-cell rounded-xl"
          >
            <img
              v-if="photoPreviews[n - 1]"
              :src="photoPreviews[n - 1]"
              class="checklist__photo-img rounded-xl"
              alt="фото"
            />
            <div v-else class="checklist__photo-placeholder" @click="triggerPhotoInput(n - 1)">
              <v-icon icon="mdi-camera-plus-outline" size="20" color="medium-emphasis" />
            </div>
          </div>
        </div>
        <!-- Hidden file inputs (5 slots) -->
        <input
          v-for="n in 5"
          :key="`fi-${n}`"
          :ref="(el) => { if (el) fileInputs[n - 1] = el as HTMLInputElement }"
          type="file"
          accept="image/*"
          capture="environment"
          style="display: none"
          @change="(e) => onPhotoChange(e, n - 1)"
        />
      </div>

      <!-- Замечания -->
      <div class="checklist__section">
        <div class="checklist__field-label">Замечания</div>
        <v-textarea
          v-model="form.notes"
          variant="outlined"
          rounded="lg"
          density="comfortable"
          rows="3"
          placeholder="Свободный комментарий..."
          class="mt-2"
          hide-details
        />
      </div>
    </div>

    <!-- Bottom sticky buttons -->
    <div class="checklist__bottom pa-4 pt-2">
      <div class="d-flex gap-2">
        <v-btn
          variant="outlined"
          rounded="lg"
          size="large"
          style="flex: 1"
          @click="router.push({ name: 'm-driver-home' })"
        >Отмена</v-btn>
        <v-btn
          color="primary"
          variant="flat"
          rounded="lg"
          size="large"
          style="flex: 2"
          :loading="submitting"
          @click="submitChecklist"
        >Отправить</v-btn>
      </div>
    </div>

    <!-- Snackbar -->
    <v-snackbar v-model="snack.show" :color="snack.color" rounded="lg" :timeout="snack.timeout ?? 3000">
      {{ snack.text }}
      <template #actions>
        <v-btn variant="text" size="small" @click="snack.show = false">Закрыть</v-btn>
      </template>
    </v-snackbar>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import LicensePlate from '@/components/vehicles/LicensePlate.vue'
import VehicleTypeIcon from '@/components/vehicles/VehicleTypeIcon.vue'

const router = useRouter()

// ---- State ----
const vehicle = ref<any>(null)
const submitting = ref(false)

const snack = ref({ show: false, text: '', color: 'success', timeout: 3000 })

const fileInputs = ref<HTMLInputElement[]>([])
const photoFiles = ref<File[]>([])
const photoPreviews = ref<string[]>([])

const form = reactive({
  odometer: null as number | null,
  fuelLevel: '' as string,
  overallState: '' as string,
  paintCondition: '' as string,
  notes: '',
  items: {} as Record<string, string>,
})

// ---- Options ----
const fuelOptions = [
  { value: '1/4', label: '¼' },
  { value: '1/2', label: '½' },
  { value: '3/4', label: '¾' },
  { value: 'full', label: 'Full' },
]

const stateOptions = [
  { value: 'operational', label: 'Рабочее', color: 'ok' },
  { value: 'issues', label: 'С замечаниями', color: 'warn' },
  { value: 'not_operational', label: 'Не на ходу', color: 'alert' },
]

const paintOptions = [
  { value: 'good', label: 'Хорошее', color: 'ok' },
  { value: 'satisfactory', label: 'Незнач. поврежд.', color: 'warn' },
  { value: 'poor', label: 'Сильные', color: 'alert' },
]

const pips = [
  { value: 'ok', label: '✓', color: 'ok' },
  { value: 'unknown', label: '?', color: 'warn' },
  { value: 'fail', label: '✕', color: 'alert' },
]

const checkItems = [
  { key: 'battery', label: 'АКБ' },
  { key: 'tires', label: 'Авторезина (летняя)' },
  { key: 'mirrors', label: 'Зеркала' },
  { key: 'radio', label: 'Радиостанция' },
  { key: 'first_aid', label: 'Аптечка' },
  { key: 'fire_ext', label: 'Огнетушитель' },
  { key: 'spare_wheel', label: 'Запасное колесо' },
  { key: 'tools', label: 'Полный набор ключей' },
  { key: 'branding', label: 'Брендирование' },
]

// Init default item statuses
checkItems.forEach((item) => {
  form.items[item.key] = 'ok'
})

// ---- Progress ----
const progressPct = computed<number>(() => {
  let filled = 0
  const total = 5
  if (form.odometer != null) filled++
  if (form.fuelLevel) filled++
  if (form.overallState) filled++
  if (checkItems.every((ci) => form.items[ci.key])) filled++
  if (form.paintCondition) filled++
  return Math.round((filled / total) * 100)
})

// ---- Methods ----
async function loadVehicle() {
  const id = localStorage.getItem('driver_selected_vehicle_id')
  if (!id) return
  try {
    const token = localStorage.getItem('auth_token')
    const res = await fetch(`/api/vehicles/${id}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (res.ok) {
      vehicle.value = await res.json()
      form.odometer = vehicle.value.current_odometer_km ?? null
    }
  } catch {
    // ignore
  }
}

function triggerPhotoInput(index: number) {
  fileInputs.value[index]?.click()
}

function onPhotoChange(event: Event, index: number) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  photoFiles.value[index] = file
  const reader = new FileReader()
  reader.onload = (e) => {
    photoPreviews.value[index] = e.target?.result as string
  }
  reader.readAsDataURL(file)
}

async function submitChecklist() {
  const vehicleId = vehicle.value?.id
    || parseInt(localStorage.getItem('driver_selected_vehicle_id') || '0')
  if (!vehicleId) {
    snack.value = { show: true, text: 'Нет выбранного ТС', color: 'error', timeout: -1 }
    return
  }

  submitting.value = true
  try {
    const token = localStorage.getItem('auth_token')

    // Build items array
    const itemsArr = checkItems.map((ci) => ({
      key: ci.key,
      status: form.items[ci.key] || 'unknown',
    }))

    const body = {
      vehicle_id: vehicleId,
      type: 'pre_trip',
      overall_state: form.overallState || 'operational',
      fuel_level: form.fuelLevel || '1/2',
      paint_condition: form.paintCondition || 'good',
      notes: form.notes || '',
      odometer_km: form.odometer,
      items: itemsArr,
    }

    const res = await fetch('/api/checklists/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(body),
    })

    if (!res.ok) {
      const err = await res.json().catch(() => null)
      throw new Error(err?.detail || `HTTP ${res.status}`)
    }

    snack.value = { show: true, text: 'Чек-лист отправлен', color: 'success', timeout: 3000 }
    setTimeout(() => router.push({ name: 'm-driver-home' }), 1200)
  } catch (e: any) {
    snack.value = { show: true, text: `Ошибка: ${e.message}`, color: 'error', timeout: -1 }
  } finally {
    submitting.value = false
  }
}

// ---- Lifecycle ----
onMounted(loadVehicle)
</script>

<style scoped>
.checklist {
  max-width: 480px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  min-height: calc(100vh - 112px); /* header 56 + nav 56 */
  padding-bottom: env(safe-area-inset-bottom, 0);
}

.checklist__body {
  flex: 1;
}

.checklist__section {
  margin-bottom: 18px;
}

.checklist__bottom {
  position: sticky;
  bottom: 0;
  background: rgb(var(--v-theme-background));
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.checklist__veh-thumb {
  width: 50px;
  height: 36px;
  background: rgba(var(--v-theme-surface-variant), 0.5);
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  overflow: hidden;
}

.checklist__field-label {
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  opacity: 0.55;
}

/* Segmented control */
.checklist__seg {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 6px;
  background: rgba(var(--v-theme-surface-variant), 0.4);
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 14px;
  padding: 4px;
}

.checklist__seg__opt {
  padding: 10px 4px;
  border-radius: 10px;
  text-align: center;
  font-size: 13px;
  font-weight: 700;
  color: rgba(var(--v-theme-on-surface), 0.5);
  background: transparent;
  border: none;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.15s;
}

.checklist__seg__opt--active {
  background: rgba(var(--v-theme-primary), 0.18);
  color: rgb(var(--v-theme-primary));
  box-shadow: inset 0 0 0 1px rgba(var(--v-theme-primary), 0.35);
}

/* Toggle buttons */
.checklist__toggle {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
}

.checklist__toggle__opt {
  padding: 11px 4px;
  border-radius: 10px;
  text-align: center;
  font-size: 12px;
  font-weight: 700;
  color: rgba(var(--v-theme-on-surface), 0.5);
  background: rgba(var(--v-theme-surface-variant), 0.4);
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  cursor: pointer;
  font-family: inherit;
  transition: all 0.15s;
}

.checklist__toggle__opt--active.checklist__toggle__opt--ok {
  background: rgba(34, 201, 151, 0.12);
  color: #22c997;
  border-color: rgba(34, 201, 151, 0.35);
}

.checklist__toggle__opt--active.checklist__toggle__opt--warn {
  background: rgba(246, 179, 74, 0.12);
  color: #f6b34a;
  border-color: rgba(246, 179, 74, 0.35);
}

.checklist__toggle__opt--active.checklist__toggle__opt--alert {
  background: rgba(255, 91, 106, 0.12);
  color: #ff5b6a;
  border-color: rgba(255, 91, 106, 0.35);
}

/* Checklist items */
.checklist__item {
  background: rgba(var(--v-theme-surface-variant), 0.3);
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

/* 3-state pips */
.checklist__pip {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 700;
  color: rgba(var(--v-theme-on-surface), 0.4);
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  background: rgba(var(--v-theme-surface-variant), 0.3);
  cursor: pointer;
  font-family: inherit;
  transition: all 0.15s;
}

.checklist__pip--ok {
  background: rgba(34, 201, 151, 0.2);
  color: #22c997;
  border-color: rgba(34, 201, 151, 0.4);
}

.checklist__pip--warn {
  background: rgba(246, 179, 74, 0.2);
  color: #f6b34a;
  border-color: rgba(246, 179, 74, 0.4);
}

.checklist__pip--alert {
  background: rgba(255, 91, 106, 0.2);
  color: #ff5b6a;
  border-color: rgba(255, 91, 106, 0.4);
}

/* Photo grid */
.checklist__photo-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 8px;
}

.checklist__photo-cell {
  aspect-ratio: 1;
  overflow: hidden;
}

.checklist__photo-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.checklist__photo-placeholder {
  width: 100%;
  height: 100%;
  border: 1.5px dashed rgba(var(--v-border-color), calc(var(--v-border-opacity) * 2));
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  background: rgba(var(--v-theme-surface-variant), 0.3);
  transition: background 0.15s;
}

.checklist__photo-placeholder:hover {
  background: rgba(var(--v-theme-primary), 0.08);
}

.gap-1 { gap: 4px; }
.gap-2 { gap: 8px; }
.gap-3 { gap: 12px; }
</style>
