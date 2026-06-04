<template>
  <div class="vehicle-trips-tab pa-4">

    <!-- Toolbar -->
    <div class="d-flex align-center justify-space-between mb-4 flex-wrap gap-3">
      <div class="text-subtitle-1 font-weight-medium">Путёвки</div>
      <v-btn
        color="primary"
        prepend-icon="mdi-clipboard-edit-outline"
        @click="openNewWaybillForm()"
      >
        Новый путевой лист
      </v-btn>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="text-center py-10">
      <v-progress-circular indeterminate size="40" color="primary" />
    </div>

    <!-- Table -->
    <v-data-table
      v-resizable-columns="'vehicle-trips'"
      v-else
      :headers="headers"
      :items="trips"
      :items-per-page="25"
      density="compact"
      class="elevation-0 border rounded"
      no-data-text="Путёвок нет"
    >
      <!-- Дата -->
      <template #item.date="{ item }">
        {{ formatDate(item.date) }}
      </template>

      <!-- Водитель -->
      <template #item.driver_full_name="{ item }">
        {{ item.driver_full_name || '—' }}
      </template>

      <!-- Маршрут -->
      <template #item.route="{ item }">
        <span v-if="item.route_from || item.route_to">
          {{ item.route_from || '?' }} → {{ item.route_to || '?' }}
        </span>
        <span v-else class="text-medium-emphasis">—</span>
      </template>

      <!-- Одометр -->
      <template #item.odometer="{ item }">
        <span v-if="item.odometer_start != null || item.odometer_finish != null">
          {{ item.odometer_start ?? '?' }} → {{ item.odometer_finish ?? '?' }}
        </span>
        <span v-else class="text-medium-emphasis">—</span>
      </template>

      <!-- Топливо -->
      <template #item.fuel="{ item }">
        <span v-if="item.fuel_remaining_start != null || item.fuel_remaining_finish != null">
          {{ item.fuel_remaining_start ?? '?' }} → {{ item.fuel_remaining_finish ?? '?' }} л
        </span>
        <span v-else class="text-medium-emphasis">—</span>
      </template>

      <!-- Заказчик -->
      <template #item.purpose="{ item }">
        {{ item.purpose || '—' }}
      </template>

      <!-- Actions -->
      <template #item.actions="{ item }">
        <div class="d-flex gap-1">
          <v-btn
            icon
            size="small"
            variant="text"
            color="primary"
            title="Скачать путёвку (.docx)"
            :loading="renderingId === item.id"
            @click="downloadDocx(item)"
          >
            <v-icon>mdi-file-word-outline</v-icon>
          </v-btn>
          <v-btn
            icon
            size="small"
            variant="text"
            color="secondary"
            title="Редактировать"
            @click="openEditDialog(item)"
          >
            <v-icon>mdi-pencil-outline</v-icon>
          </v-btn>
          <v-btn
            icon
            size="small"
            variant="text"
            color="error"
            title="Удалить"
            @click="confirmDelete(item)"
          >
            <v-icon>mdi-delete-outline</v-icon>
          </v-btn>
        </div>
      </template>
    </v-data-table>

    <!-- ─── Add / Edit Dialog ─── -->
    <v-dialog v-model="dialog" max-width="680" persistent>
      <v-card>
        <v-card-title class="d-flex align-center gap-2 pa-5 pb-3">
          <v-icon :icon="editingTrip ? 'mdi-pencil' : 'mdi-plus-circle-outline'" color="primary" />
          {{ editingTrip ? 'Редактировать путёвку' : 'Новая путёвка' }}
        </v-card-title>

        <v-card-text class="px-5 pt-0">
          <v-form ref="formRef" validate-on="submit lazy">
            <v-row dense>

              <!-- Дата -->
              <v-col cols="12" sm="6">
                <v-text-field
                  v-model="form.date"
                  label="Дата *"
                  type="date"
                  :rules="[v => !!v || 'Дата обязательна']"
                  density="compact"
                  variant="outlined"
                />
              </v-col>

              <!-- Водитель -->
              <v-col cols="12" sm="6">
                <v-autocomplete
                  v-model="selectedDriver"
                  :items="availableDrivers"
                  item-title="full_name"
                  item-value="id"
                  return-object
                  :custom-filter="driverFilter"
                  label="Водитель *"
                  density="compact"
                  variant="outlined"
                  :loading="loadingDrivers"
                  no-data-text="Водители не найдены"
                  clearable
                  :rules="[() => !!selectedDriver || 'Водитель обязателен']"
                >
                  <template #item="{ props, item }">
                    <v-list-item v-bind="props">
                      <template #append>
                        <v-chip
                          :color="item.raw.kind === 'user' ? 'primary' : 'secondary'"
                          size="x-small"
                          variant="tonal"
                          class="ml-2"
                        >
                          {{ item.raw.kind === 'user' ? 'Штатный' : 'Внешний' }}
                        </v-chip>
                      </template>
                      <template #subtitle>
                        <span v-if="item.raw.license_categories" class="text-caption">
                          Кат. {{ item.raw.license_categories }}
                        </span>
                      </template>
                    </v-list-item>
                  </template>
                </v-autocomplete>
              </v-col>

              <!-- Маршрут от -->
              <v-col cols="12" sm="6">
                <v-combobox
                  v-model="form.route_from"
                  :items="routeFromHistory"
                  label="Откуда"
                  density="compact"
                  variant="outlined"
                  clearable
                  hide-no-data
                  no-data-text=""
                />
              </v-col>

              <!-- Маршрут до -->
              <v-col cols="12" sm="6">
                <v-combobox
                  v-model="form.route_to"
                  :items="routeToHistory"
                  label="Куда"
                  density="compact"
                  variant="outlined"
                  clearable
                  hide-no-data
                  no-data-text=""
                />
              </v-col>

              <!-- Одометр старт -->
              <v-col cols="12" sm="6">
                <v-text-field
                  v-model.number="form.odometer_start"
                  label="Одометр старт (км)"
                  type="number"
                  min="0"
                  density="compact"
                  variant="outlined"
                />
              </v-col>

              <!-- Одометр финиш -->
              <v-col cols="12" sm="6">
                <v-text-field
                  v-model.number="form.odometer_finish"
                  label="Одометр финиш (км)"
                  type="number"
                  min="0"
                  density="compact"
                  variant="outlined"
                />
              </v-col>

              <!-- Топливо старт -->
              <v-col cols="12" sm="4">
                <v-text-field
                  v-model.number="form.fuel_remaining_start"
                  label="Топливо старт (л)"
                  type="number"
                  min="0"
                  step="0.1"
                  density="compact"
                  variant="outlined"
                />
              </v-col>

              <!-- Топливо финиш -->
              <v-col cols="12" sm="4">
                <v-text-field
                  v-model.number="form.fuel_remaining_finish"
                  label="Топливо финиш (л)"
                  type="number"
                  min="0"
                  step="0.1"
                  density="compact"
                  variant="outlined"
                />
              </v-col>

              <!-- Топливо выдано -->
              <v-col cols="12" sm="4">
                <v-text-field
                  v-model.number="form.fuel_issued_l"
                  label="Заправлено (л)"
                  type="number"
                  min="0"
                  step="0.1"
                  density="compact"
                  variant="outlined"
                />
              </v-col>

              <!-- Заказчик -->
              <v-col cols="12">
                <v-textarea
                  v-model="form.purpose"
                  label="Заказчик / цель поездки"
                  rows="2"
                  density="compact"
                  variant="outlined"
                  auto-grow
                />
              </v-col>

            </v-row>
          </v-form>

          <!-- Error -->
          <v-alert
            v-if="dialogError"
            type="error"
            variant="tonal"
            density="compact"
            class="mt-3"
            closable
            @click:close="dialogError = ''"
          >
            {{ dialogError }}
          </v-alert>
        </v-card-text>

        <v-card-actions class="px-5 pb-4 gap-2">
          <v-spacer />
          <v-btn variant="text" @click="closeDialog">Отмена</v-btn>
          <v-btn
            color="primary"
            variant="elevated"
            :loading="saving"
            @click="saveTrip"
          >
            {{ editingTrip ? 'Сохранить' : 'Создать' }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ─── Delete Confirm Dialog ─── -->
    <v-dialog v-model="deleteDialog" max-width="440">
      <v-card>
        <v-card-title class="d-flex align-center gap-2 pa-5 pb-2">
          <v-icon icon="mdi-delete-alert" color="error" />
          Удалить путёвку?
        </v-card-title>
        <v-card-text class="px-5">
          Путёвка от {{ formatDate(deletingTrip?.date) }} будет удалена без возможности восстановления.
        </v-card-text>
        <v-card-actions class="px-5 pb-4 gap-2">
          <v-spacer />
          <v-btn variant="text" @click="deleteDialog = false">Отмена</v-btn>
          <v-btn color="error" variant="elevated" :loading="deleting" @click="doDelete">
            Удалить
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ─── Snackbar ─── -->
    <v-snackbar
      v-model="snackbar.show"
      :color="snackbar.color"
      :timeout="snackbar.color === 'error' ? -1 : 4000"
      location="bottom right"
    >
      {{ snackbar.text }}
      <template #actions>
        <v-btn variant="text" @click="snackbar.show = false">Закрыть</v-btn>
      </template>
    </v-snackbar>

  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch } from '@/api'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  vehicleId: number
}>()

const router = useRouter()

function openNewWaybillForm() {
  router.push(`/fleet/waybills/new?vehicle_id=${props.vehicleId}`)
}

// ─── Types ───────────────────────────────────────────────────────────────────

interface Trip {
  id: number
  vehicle_id: number
  date: string | null
  driver_user_id: number | null
  driver_external_id: number | null
  driver_full_name: string | null
  route_from: string | null
  route_to: string | null
  purpose: string | null
  odometer_start: number | null
  odometer_finish: number | null
  fuel_remaining_start: number | null
  fuel_remaining_finish: number | null
  fuel_issued_l: number | null
  status: string | null
}

interface AvailableDriver {
  kind: 'user' | 'external'
  id: number
  full_name: string
  license_categories: string | null
  license_series: string | null
  license_number: string | null
}

// ─── State ───────────────────────────────────────────────────────────────────

const loading = ref(false)
const trips = ref<Trip[]>([])

const dialog = ref(false)
const saving = ref(false)
const editingTrip = ref<Trip | null>(null)
const formRef = ref<any>(null)
const dialogError = ref('')

const deleteDialog = ref(false)
const deleting = ref(false)
const deletingTrip = ref<Trip | null>(null)

const renderingId = ref<number | null>(null)

const loadingDrivers = ref(false)
const availableDrivers = ref<AvailableDriver[]>([])
const selectedDriver = ref<AvailableDriver | null>(null)

const snackbar = reactive({
  show: false,
  text: '',
  color: 'success' as string,
})

// ─── Form ────────────────────────────────────────────────────────────────────

const form = reactive({
  date: '',
  route_from: '',
  route_to: '',
  odometer_start: null as number | null,
  odometer_finish: null as number | null,
  fuel_remaining_start: null as number | null,
  fuel_remaining_finish: null as number | null,
  fuel_issued_l: null as number | null,
  purpose: '',
})

// ─── Table headers ────────────────────────────────────────────────────────────

const headers = [
  { title: 'Дата', key: 'date', width: 110 },
  { title: 'Водитель', key: 'driver_full_name', minWidth: 140 },
  { title: 'Маршрут', key: 'route', sortable: false, minWidth: 160 },
  { title: 'Одометр (км)', key: 'odometer', sortable: false, width: 150 },
  { title: 'Топливо (л)', key: 'fuel', sortable: false, width: 140 },
  { title: 'Заказчик', key: 'purpose', minWidth: 120 },
  { title: '', key: 'actions', sortable: false, width: 120, align: 'end' as const },
]

// ─── Route history (autocomplete suggestions) ─────────────────────────────────

const routeFromHistory = computed(() =>
  [...new Set(trips.value.map(t => t.route_from).filter(Boolean) as string[])]
)
const routeToHistory = computed(() =>
  [...new Set(trips.value.map(t => t.route_to).filter(Boolean) as string[])]
)

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatDate(d: string | null | undefined): string {
  if (!d) return '—'
  try {
    return new Date(d).toLocaleDateString('ru-RU')
  } catch {
    return d
  }
}

function driverFilter(value: string, query: string, item?: any): boolean {
  if (!query) return true
  const name = (item?.raw?.full_name ?? '').toLowerCase()
  return name.includes(query.toLowerCase())
}

function showSnack(text: string, color = 'success') {
  snackbar.text = text
  snackbar.color = color
  snackbar.show = true
}

// ─── Load trips ───────────────────────────────────────────────────────────────

async function loadTrips() {
  loading.value = true
  try {
    const data = await apiFetch(`/trips?vehicle_id=${props.vehicleId}`)
    trips.value = Array.isArray(data) ? data : (data?.items ?? [])
  } catch (e: any) {
    showSnack(e?.payload?.message ?? 'Ошибка загрузки путёвок', 'error')
  } finally {
    loading.value = false
  }
}

// ─── Load available drivers ───────────────────────────────────────────────────

async function loadAvailableDrivers() {
  loadingDrivers.value = true
  try {
    const data = await apiFetch('/drivers/available')
    availableDrivers.value = data?.items ?? []
  } catch {
    availableDrivers.value = []
  } finally {
    loadingDrivers.value = false
  }
}

// ─── Dialog open/close ────────────────────────────────────────────────────────

function openAddDialog() {
  editingTrip.value = null
  form.date = new Date().toISOString().slice(0, 10)
  form.route_from = ''
  form.route_to = ''
  form.odometer_start = null
  form.odometer_finish = null
  form.fuel_remaining_start = null
  form.fuel_remaining_finish = null
  form.fuel_issued_l = null
  form.purpose = ''
  selectedDriver.value = null
  dialogError.value = ''
  dialog.value = true
  loadAvailableDrivers()
}

function openEditDialog(trip: Trip) {
  editingTrip.value = trip
  form.date = trip.date ?? ''
  form.route_from = trip.route_from ?? ''
  form.route_to = trip.route_to ?? ''
  form.odometer_start = trip.odometer_start
  form.odometer_finish = trip.odometer_finish
  form.fuel_remaining_start = trip.fuel_remaining_start
  form.fuel_remaining_finish = trip.fuel_remaining_finish
  form.fuel_issued_l = trip.fuel_issued_l
  form.purpose = trip.purpose ?? ''
  dialogError.value = ''
  dialog.value = true
  loadAvailableDrivers().then(() => {
    // pre-select driver
    if (trip.driver_user_id) {
      selectedDriver.value = availableDrivers.value.find(
        d => d.kind === 'user' && d.id === trip.driver_user_id
      ) ?? null
    } else if (trip.driver_external_id) {
      selectedDriver.value = availableDrivers.value.find(
        d => d.kind === 'external' && d.id === trip.driver_external_id
      ) ?? null
    } else {
      selectedDriver.value = null
    }
  })
}

function closeDialog() {
  dialog.value = false
  editingTrip.value = null
  dialogError.value = ''
}

// ─── Save (create / edit) ─────────────────────────────────────────────────────

async function saveTrip() {
  const validation = await formRef.value?.validate()
  if (!validation?.valid) return

  if (!selectedDriver.value) {
    dialogError.value = 'Выберите водителя'
    return
  }

  saving.value = true
  dialogError.value = ''

  // XOR: exactly one of driver_user_id / driver_external_id
  const driver_user_id = selectedDriver.value.kind === 'user' ? selectedDriver.value.id : null
  const driver_external_id = selectedDriver.value.kind === 'external' ? selectedDriver.value.id : null

  const body = {
    vehicle_id: props.vehicleId,
    date: form.date,
    driver_user_id,
    driver_external_id,
    route_from: form.route_from || null,
    route_to: form.route_to || null,
    purpose: form.purpose || null,
    odometer_start: form.odometer_start,
    odometer_finish: form.odometer_finish,
    fuel_remaining_start: form.fuel_remaining_start,
    fuel_remaining_finish: form.fuel_remaining_finish,
    fuel_issued_l: form.fuel_issued_l,
  }

  try {
    if (editingTrip.value) {
      await apiFetch(`/trips/${editingTrip.value.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      showSnack('Путёвка обновлена')
    } else {
      await apiFetch('/trips', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      showSnack('Путёвка создана')
    }
    closeDialog()
    await loadTrips()
  } catch (e: any) {
    dialogError.value = e?.payload?.message ?? 'Ошибка сохранения'
  } finally {
    saving.value = false
  }
}

// ─── Delete ───────────────────────────────────────────────────────────────────

function confirmDelete(trip: Trip) {
  deletingTrip.value = trip
  deleteDialog.value = true
}

async function doDelete() {
  if (!deletingTrip.value) return
  deleting.value = true
  try {
    await apiFetch(`/trips/${deletingTrip.value.id}`, { method: 'DELETE' })
    deleteDialog.value = false
    showSnack('Путёвка удалена')
    await loadTrips()
  } catch (e: any) {
    showSnack(e?.payload?.message ?? 'Ошибка удаления', 'error')
  } finally {
    deleting.value = false
    deletingTrip.value = null
  }
}

// ─── Download docx ────────────────────────────────────────────────────────────

async function downloadDocx(trip: Trip) {
  renderingId.value = trip.id
  try {
    const token = localStorage.getItem('token') ?? ''
    const response = await fetch(`/api/trips/${trip.id}/render`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!response.ok) {
      let msg = 'Ошибка генерации путёвки'
      try {
        const json = await response.json()
        msg = json?.detail?.message ?? json?.message ?? msg
      } catch { /* ignore */ }
      showSnack(msg, 'error')
      return
    }
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const dateStr = trip.date?.replaceAll('-', '') ?? 'date'
    a.download = `trip_${trip.id}_${dateStr}.docx`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    showSnack('Путёвка скачана')
    // Refresh list to update status = 'rendered'
    await loadTrips()
  } catch (e: any) {
    showSnack(e?.message ?? 'Ошибка генерации', 'error')
  } finally {
    renderingId.value = null
  }
}

// ─── Init ─────────────────────────────────────────────────────────────────────

onMounted(() => {
  loadTrips()
})

watch(() => props.vehicleId, () => {
  loadTrips()
})
</script>
