<template>
  <div class="vehicle-odometer-tab">
    <!-- Error banners -->
    <v-alert
      v-if="loadError"
      type="error"
      variant="tonal"
      closable
      class="mb-3"
      @click:close="loadError = ''"
    >{{ loadError }}</v-alert>

    <!-- Main table -->
    <v-data-table
      v-resizable-columns="'vehicle-odometer'"
      :headers="headers"
      :items="rows"
      :loading="loading"
      density="compact"
      :items-per-page="50"
      sort-by="date"
      :sort-desc="true"
      class="odometer-table"
    >
      <!-- Date column: inline-edit -->
      <template #item.date="{ item }">
        <div v-if="editingId === item.id && editingField === 'date'" class="inline-edit-cell">
          <v-text-field
            v-model="editBuffer.date"
            type="date"
            density="compact"
            hide-details
            variant="underlined"
            style="min-width:130px"
            autofocus
            @blur="saveEdit(item)"
            @keydown.tab.prevent="nextField(item, 'date')"
            @keydown.esc="cancelEdit"
          />
        </div>
        <span
          v-else
          class="editable-cell"
          @click="startEdit(item, 'date')"
        >{{ formatDate(item.date) }}</span>
      </template>

      <!-- odometer_km column: inline-edit -->
      <template #item.odometer_km="{ item }">
        <div v-if="editingId === item.id && editingField === 'odometer_km'" class="inline-edit-cell">
          <v-text-field
            v-model.number="editBuffer.odometer_km"
            type="number"
            density="compact"
            hide-details
            variant="underlined"
            style="min-width:100px"
            autofocus
            :error="!!cellError"
            :error-messages="cellError ? [cellError] : []"
            @blur="saveEdit(item)"
            @keydown.tab.prevent="nextField(item, 'odometer_km')"
            @keydown.esc="cancelEdit"
          />
        </div>
        <span
          v-else
          class="editable-cell"
          @click="startEdit(item, 'odometer_km')"
        >{{ item.odometer_km.toLocaleString('ru-RU') }}</span>
      </template>

      <!-- delta_km — readonly -->
      <template #item.delta_km="{ item }">
        <span class="text-medium-emphasis">
          {{ item.delta_km > 0 ? '+' + item.delta_km.toLocaleString('ru-RU') : '—' }}
        </span>
      </template>

      <!-- fuel_used_l — readonly -->
      <template #item.fuel_used_l="{ item }">
        <span class="text-medium-emphasis">
          {{ item.fuel_used_l > 0 ? item.fuel_used_l.toLocaleString('ru-RU', { maximumFractionDigits: 1 }) + ' л' : '—' }}
        </span>
      </template>

      <!-- source column: inline-edit -->
      <template #item.source="{ item }">
        <div v-if="editingId === item.id && editingField === 'source'" class="inline-edit-cell">
          <v-select
            v-model="editBuffer.source"
            :items="sourceOptions"
            density="compact"
            hide-details
            variant="underlined"
            style="min-width:110px"
            autofocus
            @blur="saveEdit(item)"
            @keydown.tab.prevent="nextField(item, 'source')"
            @keydown.esc="cancelEdit"
          />
        </div>
        <span
          v-else
          class="editable-cell"
          @click="startEdit(item, 'source')"
        >{{ sourceLabel(item.source) }}</span>
      </template>

      <!-- note column: inline-edit -->
      <template #item.note="{ item }">
        <div v-if="editingId === item.id && editingField === 'note'" class="inline-edit-cell">
          <v-text-field
            v-model="editBuffer.note"
            density="compact"
            hide-details
            variant="underlined"
            style="min-width:180px"
            autofocus
            @blur="saveEdit(item)"
            @keydown.tab.prevent="nextField(item, 'note')"
            @keydown.esc="cancelEdit"
          />
        </div>
        <span
          v-else
          class="editable-cell text-medium-emphasis"
          @click="startEdit(item, 'note')"
        >{{ item.note || '—' }}</span>
      </template>

      <!-- Actions -->
      <template #item.actions="{ item }">
        <v-btn
          icon="mdi-delete-outline"
          size="x-small"
          variant="text"
          color="error"
          :loading="deletingId === item.id"
          @click="confirmDelete(item)"
        />
      </template>

      <!-- Bottom: add row -->
      <template #bottom>
        <v-divider />
        <div class="add-row pa-2">
          <div class="d-flex align-center gap-2 flex-wrap">
            <span class="text-caption text-medium-emphasis" style="min-width:80px">+ Новая запись</span>

            <v-text-field
              v-model="newRow.date"
              type="date"
              label="Дата"
              density="compact"
              hide-details
              variant="outlined"
              style="max-width:150px"
            />
            <v-text-field
              v-model.number="newRow.odometer_km"
              type="number"
              label="Одометр (км)"
              density="compact"
              hide-details
              variant="outlined"
              style="max-width:140px"
              :error="!!newRowErrors.odometer_km"
              :error-messages="newRowErrors.odometer_km ? [newRowErrors.odometer_km] : []"
            />
            <v-text-field
              v-model="newRow.note"
              label="Заметка"
              density="compact"
              hide-details
              variant="outlined"
              style="max-width:200px"
            />
            <v-select
              v-model="newRow.source"
              :items="sourceOptions"
              label="Источник"
              density="compact"
              hide-details
              variant="outlined"
              style="max-width:130px"
            />
            <v-btn
              color="primary"
              size="small"
              variant="tonal"
              prepend-icon="mdi-plus"
              :loading="saving"
              @click="addRow"
            >Добавить</v-btn>

            <!-- Duplicate date error (409) -->
            <span v-if="newRowErrors.date" class="text-error text-caption">{{ newRowErrors.date }}</span>
          </div>
        </div>
      </template>
    </v-data-table>

    <!-- Delete confirmation dialog -->
    <v-dialog v-model="deleteDialog" max-width="380">
      <v-card>
        <v-card-title>Удалить запись?</v-card-title>
        <v-card-text v-if="deleteTarget">
          Запись от {{ formatDate(deleteTarget.date) }}, {{ deleteTarget.odometer_km.toLocaleString('ru-RU') }} км будет удалена.
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="deleteDialog = false">Отмена</v-btn>
          <v-btn color="error" variant="tonal" :loading="deletingId !== null" @click="doDelete">Удалить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { apiFetch } from '@/api'
import { useToast } from '@/composables/useToast'

// ── Props ─────────────────────────────────────────────────────────────────────
const props = defineProps<{
  vehicleId: number
}>()

// ── Types ─────────────────────────────────────────────────────────────────────
interface OdometerRow {
  id: number
  vehicle_id: number
  date: string
  odometer_km: number
  delta_km: number
  fuel_used_l: number
  note: string | null
  source: string
  entered_by_id: number | null
}

type EditableField = 'date' | 'odometer_km' | 'source' | 'note'

const FIELD_ORDER: EditableField[] = ['date', 'odometer_km', 'source', 'note']

// ── Table headers ─────────────────────────────────────────────────────────────
const headers = [
  { title: 'Дата', key: 'date', sortable: true, width: 140 },
  { title: 'Одометр (км)', key: 'odometer_km', sortable: true, width: 140 },
  { title: 'Δ (км)', key: 'delta_km', sortable: false, width: 100 },
  { title: 'Топливо (л)', key: 'fuel_used_l', sortable: false, width: 110 },
  { title: 'Источник', key: 'source', sortable: false, width: 130 },
  { title: 'Заметка', key: 'note', sortable: false },
  { title: '', key: 'actions', sortable: false, width: 48, align: 'center' as const },
]

// ── Source options ────────────────────────────────────────────────────────────
const sourceOptions = [
  { title: 'Ручной ввод', value: 'manual' },
  { title: 'Путёвка', value: 'trip' },
  { title: 'Заправка', value: 'fuel' },
  { title: 'ТО', value: 'maintenance' },
]

function sourceLabel(val: string): string {
  return sourceOptions.find(o => o.value === val)?.title ?? val
}

// ── Data ──────────────────────────────────────────────────────────────────────
const rows = ref<OdometerRow[]>([])
const loading = ref(false)
const loadError = ref('')
const saving = ref(false)

// ── Inline-edit state ─────────────────────────────────────────────────────────
const editingId = ref<number | null>(null)
const editingField = ref<EditableField | null>(null)
const editBuffer = reactive<Partial<OdometerRow>>({})
const cellError = ref('')

// ── New row state ─────────────────────────────────────────────────────────────
const today = new Date().toISOString().slice(0, 10)
const newRow = reactive({ date: today, odometer_km: null as number | null, note: '', source: 'manual' })
const newRowErrors = reactive({ date: '', odometer_km: '' })

// ── Delete state ──────────────────────────────────────────────────────────────
const deleteDialog = ref(false)
const deleteTarget = ref<OdometerRow | null>(null)
const deletingId = ref<number | null>(null)

// ── Snackbar ── единый механизм (useToast + ToastContainer, смонтирован в App.vue).
const toast = useToast()

function showError(msg: string) {
  toast.error(msg)
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function formatDate(d: string): string {
  if (!d) return '—'
  const [y, m, day] = d.split('-')
  return `${day}.${m}.${y}`
}

function extractErrorMessage(e: unknown): string {
  return (e as any)?.payload?.message ?? (e as any)?.message ?? 'Неизвестная ошибка'
}

function extractErrorCode(e: unknown): string | null {
  return (e as any)?.payload?.code ?? null
}

// ── Load data ─────────────────────────────────────────────────────────────────
async function fetchRows() {
  loading.value = true
  loadError.value = ''
  try {
    rows.value = await apiFetch<OdometerRow[]>('/vehicle-odometer/?vehicle_id=' + props.vehicleId)
  } catch (e) {
    loadError.value = extractErrorMessage(e)
  } finally {
    loading.value = false
  }
}

onMounted(fetchRows)

// ── Inline-edit logic ─────────────────────────────────────────────────────────
function startEdit(item: OdometerRow, field: EditableField) {
  editingId.value = item.id
  editingField.value = field
  cellError.value = ''
  editBuffer.date = item.date
  editBuffer.odometer_km = item.odometer_km
  editBuffer.source = item.source
  editBuffer.note = item.note ?? ''
}

function cancelEdit() {
  editingId.value = null
  editingField.value = null
  cellError.value = ''
}

async function saveEdit(item: OdometerRow) {
  if (editingId.value !== item.id) return

  const field = editingField.value!
  const payload: Record<string, unknown> = {}

  if (field === 'date') payload.date = editBuffer.date
  else if (field === 'odometer_km') payload.odometer_km = Number(editBuffer.odometer_km)
  else if (field === 'source') payload.source = editBuffer.source
  else if (field === 'note') payload.note = editBuffer.note || null

  // No change — cancel silently
  const currentVal = item[field]
  const newVal = payload[field]
  if (String(currentVal ?? '') === String(newVal ?? '')) {
    cancelEdit()
    return
  }

  cellError.value = ''
  try {
    const updated = await apiFetch<OdometerRow>(`/vehicle-odometer/${item.id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    })
    const idx = rows.value.findIndex(r => r.id === item.id)
    if (idx !== -1) rows.value[idx] = updated
    cancelEdit()
  } catch (e) {
    const code = extractErrorCode(e)
    if (code === 'DUPLICATE_ODOMETER_DATE') {
      // Show inline red text for 409
      cellError.value = 'Запись на эту дату уже существует'
    } else if (code === 'NON_MONOTONIC_ODOMETER') {
      const lastKm = (e as any)?.payload?.details?.last_km ?? '?'
      cellError.value = `Одометр не может уменьшаться (последнее значение: ${lastKm} км)`
    } else {
      showError(extractErrorMessage(e))
      cancelEdit()
    }
  }
}

function nextField(item: OdometerRow, currentField: EditableField) {
  const idx = FIELD_ORDER.indexOf(currentField)
  const next = FIELD_ORDER[idx + 1]
  if (next) {
    // Save current first, then move to next field
    saveEdit(item).then(() => {
      if (!cellError.value) startEdit(item, next)
    })
  } else {
    saveEdit(item)
  }
}

// ── Add new row ───────────────────────────────────────────────────────────────
async function addRow() {
  newRowErrors.date = ''
  newRowErrors.odometer_km = ''

  if (!newRow.date) { newRowErrors.date = 'Укажите дату'; return }
  if (newRow.odometer_km === null || newRow.odometer_km < 0) {
    newRowErrors.odometer_km = 'Укажите показание одометра'
    return
  }

  saving.value = true
  try {
    const payload = {
      vehicle_id: props.vehicleId,
      date: newRow.date,
      odometer_km: newRow.odometer_km,
      note: newRow.note || null,
      source: newRow.source,
    }
    const created = await apiFetch<OdometerRow>('/vehicle-odometer/', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    rows.value.unshift(created)
    // Reset form
    newRow.date = today
    newRow.odometer_km = null
    newRow.note = ''
    newRow.source = 'manual'
  } catch (e) {
    const code = extractErrorCode(e)
    if (code === 'DUPLICATE_ODOMETER_DATE') {
      newRowErrors.date = 'Запись на эту дату уже существует'
    } else if (code === 'NON_MONOTONIC_ODOMETER') {
      const lastKm = (e as any)?.payload?.details?.last_km ?? '?'
      newRowErrors.odometer_km = `Одометр не может уменьшаться (последнее значение: ${lastKm} км)`
    } else {
      showError(extractErrorMessage(e))
    }
  } finally {
    saving.value = false
  }
}

// ── Delete ────────────────────────────────────────────────────────────────────
function confirmDelete(item: OdometerRow) {
  deleteTarget.value = item
  deleteDialog.value = true
}

async function doDelete() {
  if (!deleteTarget.value) return
  deletingId.value = deleteTarget.value.id
  try {
    await apiFetch(`/vehicle-odometer/${deleteTarget.value.id}`, { method: 'DELETE' })
    rows.value = rows.value.filter(r => r.id !== deleteTarget.value!.id)
    deleteDialog.value = false
    deleteTarget.value = null
  } catch (e) {
    showError(extractErrorMessage(e))
  } finally {
    deletingId.value = null
  }
}
</script>

<style scoped>
.editable-cell {
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 4px;
  transition: background 0.15s;
  display: inline-block;
  min-width: 40px;
}
.editable-cell:hover {
  background: rgba(var(--v-theme-primary), 0.08);
}
.inline-edit-cell {
  padding: 2px 0;
}
.add-row {
  background: rgba(var(--v-theme-surface), 1);
}
.odometer-table :deep(tbody tr:hover td) {
  background: rgba(var(--v-theme-primary), 0.03);
}
</style>
