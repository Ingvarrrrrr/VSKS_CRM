<template>
  <div class="incident">
    <div class="incident__header pa-4 pb-2">
      <div class="text-h6 font-weight-bold">Рапорт о ЧП</div>
    </div>

    <div class="incident__body pa-4 pt-0">

      <!-- Severity -->
      <div class="incident__field-label mt-2">Срочность</div>
      <div class="incident__severity mt-2">
        <button
          v-for="opt in severityOptions"
          :key="opt.value"
          class="incident__sev"
          :class="[
            form.severity === opt.value ? `incident__sev--active incident__sev--${opt.color}` : ''
          ]"
          @click="form.severity = opt.value"
        >{{ opt.label }}</button>
      </div>

      <!-- Affected system -->
      <div class="incident__field-label mt-4">Что сломалось</div>
      <div class="incident__systems mt-2">
        <button
          v-for="sys in systemOptions"
          :key="sys.value"
          class="incident__sysb rounded-xl"
          :class="form.affectedSystem === sys.value ? 'incident__sysb--active' : ''"
          @click="form.affectedSystem = sys.value"
        >
          <v-icon :icon="sys.icon" size="20" />
          <span>{{ sys.label }}</span>
        </button>
      </div>

      <!-- Description -->
      <div class="incident__field-label mt-4">Описание проблемы</div>
      <v-textarea
        v-model="form.description"
        variant="outlined"
        rounded="lg"
        density="comfortable"
        rows="3"
        placeholder="Например: при торможении слышен скрежет"
        class="mt-2"
        hide-details
      />

      <!-- Operational status -->
      <div class="incident__field-label mt-4">Машина сейчас на ходу?</div>
      <div class="incident__toggle mt-2">
        <button
          v-for="opt in operationalOptions"
          :key="opt.value"
          class="incident__toggle__opt"
          :class="[
            { 'incident__toggle__opt--active': form.isOperational === opt.value },
            `incident__toggle__opt--${opt.color}`
          ]"
          @click="form.isOperational = opt.value"
        >{{ opt.label }}</button>
      </div>

      <!-- Location -->
      <div class="incident__field-label mt-4">Где находится ТС</div>
      <v-text-field
        v-model="form.location"
        variant="outlined"
        density="comfortable"
        rounded="lg"
        placeholder="Адрес или описание местоположения"
        prepend-inner-icon="mdi-map-marker-outline"
        class="mt-2"
        hide-details
      />

      <!-- Photos -->
      <div class="incident__field-label mt-4">Фото проблемы</div>
      <div class="incident__photo-grid mt-2">
        <div
          v-for="n in 4"
          :key="n"
          class="incident__photo-cell rounded-xl"
        >
          <img
            v-if="photoPreviews[n - 1]"
            :src="photoPreviews[n - 1]"
            class="incident__photo-img rounded-xl"
            alt="фото"
          />
          <div v-else class="incident__photo-placeholder" @click="triggerPhotoInput(n - 1)">
            <v-icon icon="mdi-camera-outline" size="20" color="medium-emphasis" />
          </div>
        </div>
      </div>
      <!-- Hidden file inputs -->
      <input
        v-for="n in 4"
        :key="`fi-${n}`"
        :ref="(el) => { if (el) fileInputs[n - 1] = el as HTMLInputElement }"
        type="file"
        accept="image/*"
        capture="environment"
        style="display: none"
        @change="(e) => onPhotoChange(e, n - 1)"
      />

      <!-- Recipient -->
      <div class="incident__field-label mt-4">Кому отправить</div>
      <div class="incident__recipient rounded-xl pa-3 d-flex align-center mt-2" style="gap: 12px">
        <div class="incident__recipient__avatar d-flex align-center justify-center font-weight-bold text-body-2">
          {{ recipientInitials }}
        </div>
        <div style="flex: 1">
          <div class="text-body-2 font-weight-bold">{{ recipientName }}</div>
          <div class="text-caption mt-0_5 text-medium-emphasis">{{ recipientRole }}</div>
        </div>
        <div class="text-caption font-weight-bold text-success">+ механик</div>
      </div>

      <!-- Bottom padding -->
      <div style="height: 100px" />
    </div>

    <!-- Sticky bottom -->
    <div class="incident__bottom pa-4 pt-2">
      <div class="d-flex gap-2">
        <v-btn
          variant="outlined"
          rounded="lg"
          size="large"
          style="flex: 1"
          @click="$router.push({ name: 'm-driver-home' })"
        >
          Черновик
        </v-btn>
        <v-btn
          color="error"
          variant="flat"
          rounded="lg"
          size="large"
          style="flex: 2"
          :loading="submitting"
          @click="submitIncident"
        >
          Отправить рапорт
        </v-btn>
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

const router = useRouter()

// ---- State ----
const submitting = ref(false)
const snack = ref({ show: false, text: '', color: 'success', timeout: 3000 })

const fileInputs = ref<HTMLInputElement[]>([])
const photoFiles = ref<File[]>([])
const photoPreviews = ref<string[]>([])

const vehicle = ref<any>(null)

const form = reactive({
  severity: 'medium' as string,
  affectedSystem: '' as string,
  description: '' as string,
  isOperational: 'operational' as string,
  location: '' as string,
})

// ---- Options ----
const severityOptions = [
  { value: 'low', label: 'Низкая', color: 'ok' },
  { value: 'medium', label: 'Средняя', color: 'warn' },
  { value: 'high', label: 'Срочно', color: 'alert' },
]

const systemOptions = [
  { value: 'engine', label: 'Двигатель', icon: 'mdi-engine-outline' },
  { value: 'brakes', label: 'Тормоза', icon: 'mdi-car-brake-alert' },
  { value: 'battery', label: 'АКБ', icon: 'mdi-car-battery' },
  { value: 'tires', label: 'Шины', icon: 'mdi-tire' },
  { value: 'electrics', label: 'Электрика', icon: 'mdi-lightning-bolt-outline' },
  { value: 'other', label: 'Другое', icon: 'mdi-dots-horizontal-circle-outline' },
]

const operationalOptions = [
  { value: 'operational', label: 'На ходу', color: 'ok' },
  { value: 'stopped', label: 'Стоит', color: 'alert' },
  { value: 'in_transit', label: 'В пути', color: 'warn' },
]

// ---- Computed ----
const recipientName = computed(() => {
  if (vehicle.value?.responsible_person_name) return vehicle.value.responsible_person_name
  return 'Диспетчер'
})

const recipientRole = computed(() => {
  if (vehicle.value?.current_station_name) return `ответственный · ${vehicle.value.current_station_name}`
  return 'ответственный'
})

const recipientInitials = computed(() => {
  const name = recipientName.value
  const parts = name.split(' ')
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`
  if (parts.length === 1 && parts[0].length >= 2) return parts[0].slice(0, 2)
  return 'Д'
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
      // Pre-fill location from current station
      if (!form.location && vehicle.value.current_station_name) {
        form.location = vehicle.value.current_station_name
      }
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

async function submitIncident() {
  if (!form.affectedSystem) {
    snack.value = { show: true, text: 'Выберите систему (что сломалось)', color: 'error', timeout: -1 }
    return
  }
  if (!form.description.trim()) {
    snack.value = { show: true, text: 'Заполните описание проблемы', color: 'error', timeout: -1 }
    return
  }

  const vehicleId = vehicle.value?.id
    || parseInt(localStorage.getItem('driver_selected_vehicle_id') || '0')
  if (!vehicleId) {
    snack.value = { show: true, text: 'Нет выбранного ТС', color: 'error', timeout: -1 }
    return
  }

  submitting.value = true
  try {
    const token = localStorage.getItem('auth_token')

    const body = {
      vehicle_id: vehicleId,
      incident_type: 'breakdown',
      severity: form.severity,
      affected_system: form.affectedSystem,
      is_operational: form.isOperational === 'operational',
      location: form.location || '',
      description: form.description,
      photos: [],
    }

    const res = await fetch('/api/incidents/', {
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

    snack.value = { show: true, text: 'Рапорт отправлен', color: 'success', timeout: 3000 }
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
.incident {
  max-width: 480px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  min-height: calc(100vh - 112px);
  padding-bottom: env(safe-area-inset-bottom, 0);
}

.incident__body {
  flex: 1;
  overflow-y: auto;
}

.incident__bottom {
  position: sticky;
  bottom: 0;
  background: rgb(var(--v-theme-background));
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.incident__field-label {
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  opacity: 0.55;
}

/* Severity */
.incident__severity {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
}

.incident__sev {
  padding: 12px 6px;
  border-radius: 12px;
  text-align: center;
  font-size: 13px;
  font-weight: 700;
  color: rgba(var(--v-theme-on-surface), 0.5);
  background: rgba(var(--v-theme-surface-variant), 0.4);
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  cursor: pointer;
  font-family: inherit;
  transition: all 0.15s;
}

.incident__sev--active.incident__sev--ok {
  background: rgba(34, 201, 151, 0.12);
  color: #22c997;
  border-color: rgba(34, 201, 151, 0.35);
}

.incident__sev--active.incident__sev--warn {
  background: rgba(246, 179, 74, 0.12);
  color: #f6b34a;
  border-color: rgba(246, 179, 74, 0.35);
}

.incident__sev--active.incident__sev--alert {
  background: rgba(255, 91, 106, 0.12);
  color: #ff5b6a;
  border-color: rgba(255, 91, 106, 0.35);
}

/* Systems grid */
.incident__systems {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.incident__sysb {
  padding: 12px 6px 10px;
  text-align: center;
  font-size: 11.5px;
  font-weight: 700;
  color: rgba(var(--v-theme-on-surface), 0.5);
  background: rgba(var(--v-theme-surface-variant), 0.4);
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.15s;
}

.incident__sysb--active {
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgb(var(--v-theme-primary));
  border-color: rgba(var(--v-theme-primary), 0.35);
}

/* Toggle */
.incident__toggle {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
}

.incident__toggle__opt {
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

.incident__toggle__opt--active.incident__toggle__opt--ok {
  background: rgba(34, 201, 151, 0.12);
  color: #22c997;
  border-color: rgba(34, 201, 151, 0.35);
}

.incident__toggle__opt--active.incident__toggle__opt--warn {
  background: rgba(246, 179, 74, 0.12);
  color: #f6b34a;
  border-color: rgba(246, 179, 74, 0.35);
}

.incident__toggle__opt--active.incident__toggle__opt--alert {
  background: rgba(255, 91, 106, 0.12);
  color: #ff5b6a;
  border-color: rgba(255, 91, 106, 0.35);
}

/* Photo grid */
.incident__photo-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}

.incident__photo-cell {
  aspect-ratio: 1;
  overflow: hidden;
}

.incident__photo-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.incident__photo-placeholder {
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

.incident__photo-placeholder:hover {
  background: rgba(255, 91, 106, 0.08);
}

/* Recipient */
.incident__recipient {
  background: rgba(var(--v-theme-surface-variant), 0.4);
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.incident__recipient__avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: linear-gradient(135deg, #6aa6ff, #8b5cf6);
  color: #0a0d14;
  flex-shrink: 0;
}

.gap-2 { gap: 8px; }
.mt-0_5 { margin-top: 2px; }
</style>
