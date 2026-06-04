<template>
  <div>
    <!-- Toolbar -->
    <div class="d-flex align-center mb-3">
      <v-btn
        color="primary"
        variant="flat"
        prepend-icon="mdi-plus"
        size="small"
        @click="openAddDialog"
      >
        Добавить заправку
      </v-btn>
      <v-spacer />
      <!-- Seasonal norm hint -->
      <v-chip
        v-if="seasonalNorm !== null"
        :color="isWinter ? 'blue-lighten-2' : 'green-lighten-2'"
        variant="tonal"
        size="small"
        :prepend-icon="isWinter ? 'mdi-snowflake' : 'mdi-white-balance-sunny'"
      >
        Норма: {{ seasonalNorm }} л/100км ({{ isWinter ? 'зимняя' : 'летняя' }})
      </v-chip>
    </div>

    <!-- Table -->
    <v-data-table
      v-resizable-columns="'vehicle-fuel-log'"
      :headers="headers"
      :items="logs"
      :loading="loading"
      density="compact"
      no-data-text="Записей о заправках нет"
      items-per-page="25"
    >
      <!-- Date -->
      <template #item.date="{ item }">
        {{ fmtDate(item.date) }}
      </template>

      <!-- Odometer -->
      <template #item.odometer_km="{ item }">
        <span v-if="item.odometer_km">{{ item.odometer_km.toLocaleString('ru') }} км</span>
        <span v-else class="text-medium-emphasis">—</span>
      </template>

      <!-- Delta km -->
      <template #item.delta_km="{ item }">
        <span v-if="item.delta_km > 0" class="text-medium-emphasis">
          +{{ item.delta_km.toLocaleString('ru') }} км
        </span>
        <span v-else class="text-disabled">—</span>
      </template>

      <!-- Liters -->
      <template #item.liters="{ item }">
        <span v-if="item.liters !== null && item.liters !== undefined">{{ item.liters }} л</span>
        <span v-else class="text-disabled">—</span>
      </template>

      <!-- Price per liter -->
      <template #item.price_per_liter="{ item }">
        <span v-if="item.price_per_liter !== null && item.price_per_liter !== undefined">
          {{ item.price_per_liter }} ₽
        </span>
        <span v-else class="text-disabled">—</span>
      </template>

      <!-- Total amount -->
      <template #item.total_amount="{ item }">
        <span v-if="computedTotal(item) !== null" class="font-weight-medium">
          {{ computedTotal(item)!.toLocaleString('ru', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }} ₽
        </span>
        <span v-else class="text-disabled">—</span>
      </template>

      <!-- Norm l/100km (seasonal) -->
      <template #item.norm_l_100="{ item }">
        <span v-if="getNorm(item) !== null" class="text-medium-emphasis">
          {{ getNorm(item) }} л/100
        </span>
        <span v-else class="text-disabled">—</span>
      </template>

      <!-- Actual consumption -->
      <template #item.fuel_used_l="{ item }">
        <span v-if="item.fuel_used_l > 0">{{ item.fuel_used_l }} л</span>
        <span v-else class="text-disabled">—</span>
      </template>

      <!-- Station -->
      <template #item.station_name="{ item }">
        <span v-if="item.station_name">{{ item.station_name }}</span>
        <span v-else class="text-disabled">—</span>
      </template>

      <!-- Receipt -->
      <template #item.receipt_attachment_id="{ item }">
        <v-btn
          v-if="item.receipt_attachment_id"
          icon="mdi-receipt"
          size="x-small"
          variant="text"
          color="primary"
          :href="`/api/vehicle-attachments/${item.receipt_attachment_id}/download`"
          target="_blank"
        />
        <span v-else class="text-disabled">—</span>
      </template>

      <!-- Actions -->
      <template #item.actions="{ item }">
        <v-btn
          icon="mdi-delete-outline"
          size="x-small"
          variant="text"
          color="error"
          @click="confirmDelete(item)"
        />
      </template>
    </v-data-table>

    <!-- Add dialog -->
    <v-dialog v-model="addDialog" max-width="560" persistent>
      <v-card>
        <v-card-title class="pa-5 pb-2 d-flex align-center">
          <v-icon icon="mdi-gas-station" class="mr-2" color="primary" />
          Добавить заправку
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="closeAddDialog" />
        </v-card-title>

        <v-card-text class="pa-5 pt-2">
          <v-row dense>
            <!-- Date -->
            <v-col cols="12" sm="6">
              <v-text-field
                v-model="form.date"
                label="Дата *"
                type="date"
                variant="outlined"
                density="compact"
                :rules="[v => !!v || 'Обязательно']"
                hide-details="auto"
              />
            </v-col>

            <!-- Odometer -->
            <v-col cols="12" sm="6">
              <v-text-field
                v-model.number="form.odometer_km"
                label="Одометр (км)"
                type="number"
                variant="outlined"
                density="compact"
                hint="Создаст запись пробега"
                hide-details="auto"
              />
            </v-col>

            <!-- Liters -->
            <v-col cols="12" sm="4">
              <v-text-field
                v-model.number="form.liters"
                label="Литры"
                type="number"
                step="0.01"
                variant="outlined"
                density="compact"
                hide-details="auto"
                @input="recalcTotal"
              />
            </v-col>

            <!-- Price per liter -->
            <v-col cols="12" sm="4">
              <v-text-field
                v-model.number="form.price_per_liter"
                label="Цена/л (₽)"
                type="number"
                step="0.01"
                variant="outlined"
                density="compact"
                hide-details="auto"
                :loading="loadingPrice"
                @focus="fetchLatestPrice"
                @input="recalcTotal"
              />
            </v-col>

            <!-- Total amount -->
            <v-col cols="12" sm="4">
              <v-text-field
                v-model.number="form.total_amount"
                label="Сумма (₽)"
                type="number"
                step="0.01"
                variant="outlined"
                density="compact"
                hide-details="auto"
                hint="Авто: литры × цена"
              />
            </v-col>

            <!-- Fuel type -->
            <v-col cols="12" sm="6">
              <v-select
                v-model="form.fuel_type"
                label="Тип топлива"
                :items="fuelTypes"
                variant="outlined"
                density="compact"
                clearable
                hide-details
              />
            </v-col>

            <!-- Station -->
            <v-col cols="12" sm="6">
              <v-text-field
                v-model="form.station_name"
                label="Станция / АЗС"
                variant="outlined"
                density="compact"
                hide-details
              />
            </v-col>

            <!-- Receipt upload -->
            <v-col cols="12">
              <div class="text-caption mb-1 text-medium-emphasis">Чек (фото/скан)</div>
              <FileDropZone
                v-model="form.receiptFile"
                accept="image/*,.pdf"
                hint="Фото чека — перетащите или нажмите"
              />
            </v-col>

            <!-- Note -->
            <v-col cols="12">
              <v-text-field
                v-model="form.note"
                label="Заметка"
                variant="outlined"
                density="compact"
                hide-details
              />
            </v-col>
          </v-row>

          <!-- Error block -->
          <div v-if="addError.show" class="mt-3 pa-3 border rounded bg-red-lighten-5">
            <div class="d-flex align-center mb-1">
              <span class="text-caption font-weight-bold text-error">Ошибка</span>
              <v-spacer />
              <v-btn size="x-small" variant="text" prepend-icon="mdi-content-copy" @click="copyAddError">
                Скопировать
              </v-btn>
            </div>
            <div class="text-body-2">{{ addError.message }}</div>
            <div v-if="addError.code" class="text-caption text-medium-emphasis mt-1">Код: {{ addError.code }}</div>
            <div v-if="addError.correlationId" class="text-caption text-medium-emphasis">ID: {{ addError.correlationId }}</div>
          </div>
        </v-card-text>

        <v-card-actions class="pa-5 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="closeAddDialog">Отмена</v-btn>
          <v-btn
            color="primary"
            variant="flat"
            :loading="saving"
            :disabled="!form.date"
            @click="saveLog"
          >
            Сохранить
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Delete confirm dialog -->
    <v-dialog v-model="deleteDialog" max-width="400">
      <v-card>
        <v-card-title class="pa-5 pb-2">Удалить запись?</v-card-title>
        <v-card-text class="pa-5 pt-0 text-body-2">
          Запись о заправке от {{ deleteTarget ? fmtDate(deleteTarget.date) : '' }} будет удалена.
        </v-card-text>
        <v-card-actions class="pa-5 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="deleteDialog = false">Отмена</v-btn>
          <v-btn color="error" variant="flat" :loading="deleting" @click="doDelete">Удалить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Snackbar -->
    <v-snackbar
      v-model="snack.show"
      :color="snack.color"
      timeout="-1"
      location="bottom right"
    >
      {{ snack.text }}
      <template #actions>
        <v-btn variant="text" @click="snack.show = false">Закрыть</v-btn>
      </template>
    </v-snackbar>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { apiFetch } from '@/api'
import FileDropZone from '@/components/FileDropZone.vue'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  vehicleId: number
}>()

// ─── Types ───────────────────────────────────────────────────────────────────

interface FuelLogOut {
  id: number
  vehicle_id: number
  date: string
  liters: number | null
  price_per_liter: number | null
  total_amount: number | null
  price_total: number | null
  fuel_type: string | null
  receipt_attachment_id: number | null
  note: string | null
  source: string
  delta_km: number
  fuel_used_l: number
  // Extended on list (station_name comes from station field if backend returns it)
  station_name?: string | null
  odometer_km?: number | null
}

interface LatestPriceOut {
  price_per_liter: number | null
  source: string
}

// ─── Table headers ────────────────────────────────────────────────────────────

const headers = [
  { title: 'Дата', key: 'date', width: 100 },
  { title: 'Одометр', key: 'odometer_km', width: 110 },
  { title: 'Δкм', key: 'delta_km', width: 90 },
  { title: 'Литры', key: 'liters', width: 80 },
  { title: 'Цена/л', key: 'price_per_liter', width: 80 },
  { title: 'Сумма', key: 'total_amount', width: 100 },
  { title: 'Норма л/100', key: 'norm_l_100', width: 110 },
  { title: 'Расход (расч.)', key: 'fuel_used_l', width: 120 },
  { title: 'Станция', key: 'station_name', width: 140 },
  { title: 'Чек', key: 'receipt_attachment_id', width: 60, sortable: false },
  { title: '', key: 'actions', width: 50, sortable: false },
]

// ─── Seasonal norm ────────────────────────────────────────────────────────────

const currentMonth = new Date().getMonth() + 1  // 1-12
const isWinter = computed(() => currentMonth < 5 || currentMonth > 9)

// We'll fetch the norm from vehicle data; for the hint display we expose a reactive
const seasonalNorm = ref<number | null>(null)

function getNorm(item: FuelLogOut): number | null {
  // Use backend-computed fuel_used_l relative to delta_km to show actual norm
  if (item.delta_km > 0 && item.fuel_used_l > 0) {
    return Math.round((item.fuel_used_l / item.delta_km) * 100 * 10) / 10
  }
  return null
}

// ─── State ────────────────────────────────────────────────────────────────────

const logs = ref<FuelLogOut[]>([])
const loading = ref(false)

const addDialog = ref(false)
const saving = ref(false)
const loadingPrice = ref(false)
const priceFetched = ref(false)

const deleteDialog = ref(false)
const deleteTarget = ref<FuelLogOut | null>(null)
const deleting = ref(false)

const fuelTypes = ['АИ-92', 'АИ-95', 'АИ-98', 'ДТ', 'Газ (LPG)', 'Газ (CNG)']

interface FormState {
  date: string
  odometer_km: number | null
  liters: number | null
  price_per_liter: number | null
  total_amount: number | null
  fuel_type: string | null
  station_name: string
  note: string
  receiptFile: File | null
}

const form = reactive<FormState>({
  date: new Date().toISOString().slice(0, 10),
  odometer_km: null,
  liters: null,
  price_per_liter: null,
  total_amount: null,
  fuel_type: null,
  station_name: '',
  note: '',
  receiptFile: null,
})

const addError = reactive({
  show: false,
  message: '',
  code: '',
  correlationId: '',
})

const snack = reactive({
  show: false,
  text: '',
  color: 'success' as string,
})

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fmtDate(d: string): string {
  if (!d) return '—'
  const [y, m, day] = d.split('-')
  return `${day}.${m}.${y}`
}

function computedTotal(item: FuelLogOut): number | null {
  if (item.price_total !== null && item.price_total !== undefined) return item.price_total
  if (item.total_amount !== null && item.total_amount !== undefined) return item.total_amount
  if (item.liters !== null && item.price_per_liter !== null &&
      item.liters !== undefined && item.price_per_liter !== undefined) {
    return Math.round(item.liters * item.price_per_liter * 100) / 100
  }
  return null
}

function showSnack(text: string, color = 'success') {
  snack.text = text
  snack.color = color
  snack.show = true
}

function showAddError(err: unknown) {
  const e = err as Record<string, any>
  const payload = e?.payload ?? e?.detail ?? e
  addError.message = payload?.message ?? payload?.detail ?? String(err)
  addError.code = payload?.code ?? ''
  addError.correlationId = payload?.correlation_id ?? ''
  addError.show = true
}

function copyAddError() {
  const text = [
    addError.message,
    addError.code ? `Код: ${addError.code}` : '',
    addError.correlationId ? `ID: ${addError.correlationId}` : '',
  ].filter(Boolean).join('\n')
  navigator.clipboard.writeText(text).catch(() => {})
}

function recalcTotal() {
  if (form.liters !== null && form.price_per_liter !== null &&
      form.liters !== undefined && form.price_per_liter !== undefined) {
    form.total_amount = Math.round(form.liters * form.price_per_liter * 100) / 100
  }
}

// ─── API ──────────────────────────────────────────────────────────────────────

async function fetchLogs() {
  loading.value = true
  try {
    const data = await apiFetch<FuelLogOut[]>(
      `/api/fuel-logs/?vehicle_id=${props.vehicleId}`
    )
    logs.value = data
    // Set seasonal norm hint from first log with fuel_used_l if available
    const normLog = data.find(l => l.delta_km > 0 && l.fuel_used_l > 0)
    if (normLog) {
      seasonalNorm.value = Math.round((normLog.fuel_used_l / normLog.delta_km) * 100 * 10) / 10
    }
  } catch (err: unknown) {
    const e = err as Record<string, any>
    const payload = e?.payload ?? e?.detail ?? e
    showSnack(payload?.message ?? 'Ошибка загрузки заправок', 'error')
  } finally {
    loading.value = false
  }
}

async function fetchLatestPrice() {
  if (priceFetched.value || form.price_per_liter !== null) return
  loadingPrice.value = true
  try {
    const data = await apiFetch<LatestPriceOut>(
      `/api/fuel-logs/latest-price/${props.vehicleId}`
    )
    if (data.price_per_liter !== null) {
      form.price_per_liter = data.price_per_liter
      recalcTotal()
      priceFetched.value = true
    }
  } catch {
    // silent — price hint is optional
  } finally {
    loadingPrice.value = false
  }
}

async function uploadReceipt(file: File): Promise<number | null> {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('vehicle_id', String(props.vehicleId))
  fd.append('kind', 'other')
  fd.append('name', `Чек ${form.date}`)
  try {
    const res = await apiFetch<{ id: number }>('/vehicle-attachments/upload', {
      method: 'POST',
      body: fd,
    })
    return res.id
  } catch {
    return null
  }
}

async function saveLog() {
  if (!form.date) return
  saving.value = true
  addError.show = false
  try {
    let receiptId: number | null = null
    if (form.receiptFile) {
      receiptId = await uploadReceipt(form.receiptFile)
    }

    const body: Record<string, unknown> = {
      vehicle_id: props.vehicleId,
      date: form.date,
    }
    if (form.liters !== null) body.liters = form.liters
    if (form.price_per_liter !== null) body.price_per_liter = form.price_per_liter
    if (form.total_amount !== null) body.total_amount = form.total_amount
    if (form.fuel_type) body.fuel_type = form.fuel_type
    if (form.note) body.note = form.note
    if (form.odometer_km !== null) body.odometer_km = form.odometer_km
    if (receiptId !== null) body.receipt_attachment_id = receiptId

    await apiFetch('/fuel-logs/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })

    showSnack('Заправка добавлена')
    closeAddDialog()
    await fetchLogs()
  } catch (err: unknown) {
    showAddError(err)
  } finally {
    saving.value = false
  }
}

function openAddDialog() {
  form.date = new Date().toISOString().slice(0, 10)
  form.odometer_km = null
  form.liters = null
  form.price_per_liter = null
  form.total_amount = null
  form.fuel_type = null
  form.station_name = ''
  form.note = ''
  form.receiptFile = null
  addError.show = false
  priceFetched.value = false
  addDialog.value = true
}

function closeAddDialog() {
  addDialog.value = false
}

function confirmDelete(item: FuelLogOut) {
  deleteTarget.value = item
  deleteDialog.value = true
}

async function doDelete() {
  if (!deleteTarget.value) return
  deleting.value = true
  try {
    await apiFetch(`/fuel-logs/${deleteTarget.value.id}`, { method: 'DELETE' })
    showSnack('Запись удалена')
    deleteDialog.value = false
    deleteTarget.value = null
    await fetchLogs()
  } catch (err: unknown) {
    const e = err as Record<string, any>
    const payload = e?.payload ?? e?.detail ?? e
    showSnack(payload?.message ?? 'Ошибка удаления', 'error')
  } finally {
    deleting.value = false
  }
}

// ─── Init ─────────────────────────────────────────────────────────────────────

onMounted(fetchLogs)
</script>
