<template>
  <div class="vehicle-fines-tab pa-4">

    <!-- Toolbar -->
    <div class="d-flex align-center justify-space-between mb-4 flex-wrap gap-3">
      <div class="text-subtitle-1 font-weight-medium">Штрафы</div>
      <v-btn
        color="primary"
        prepend-icon="mdi-plus"
        variant="tonal"
        @click="openAddDialog"
      >
        Добавить штраф
      </v-btn>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="text-center py-10">
      <v-progress-circular indeterminate size="40" color="primary" />
    </div>

    <!-- Empty state -->
    <v-alert
      v-else-if="fines.length === 0"
      type="info"
      variant="tonal"
      text="Штрафов нет"
    />

    <!-- Table -->
    <v-data-table
      v-resizable-columns="'vehicle-fines'"
      v-else
      :headers="headers"
      :items="fines"
      :items-per-page="25"
      density="compact"
      class="elevation-0 border rounded"
      no-data-text="Штрафов нет"
    >
      <!-- Дата -->
      <template #item.issued_at="{ item }">
        {{ formatDateTime(item.issued_at) }}
      </template>

      <!-- Сумма -->
      <template #item.amount="{ item }">
        {{ fmtRub(Number(item.amount)) }}
      </template>

      <!-- № постановления -->
      <template #item.doc_number="{ item }">
        {{ item.doc_number || '—' }}
      </template>

      <!-- Нарушение -->
      <template #item.violation_type="{ item }">
        <span class="text-truncate" style="max-width:180px;display:inline-block">
          {{ item.violation_type || '—' }}
        </span>
      </template>

      <!-- Место -->
      <template #item.location="{ item }">
        <span class="text-truncate" style="max-width:160px;display:inline-block">
          {{ item.location || '—' }}
        </span>
      </template>

      <!-- Водитель -->
      <template #item.driver_name="{ item }">
        <span v-if="item.driver_name" class="text-body-2">{{ item.driver_name }}</span>
        <span v-else class="text-medium-emphasis text-caption">не определён</span>
      </template>

      <!-- Статус -->
      <template #item.status="{ item }">
        <v-chip
          :color="STATUS_COLOR[item.status] ?? 'grey'"
          size="x-small"
          variant="tonal"
        >
          {{ STATUS_LABEL[item.status] ?? item.status }}
        </v-chip>
      </template>

      <!-- Действия -->
      <template #item.actions="{ item }">
        <div class="d-flex align-center ga-1">
          <v-tooltip v-if="item.status === 'unpaid'" text="Отметить оплаченным" location="top">
            <template #activator="{ props }">
              <v-btn
                v-bind="props"
                icon="mdi-check"
                size="x-small"
                variant="tonal"
                color="success"
                :loading="paying === item.id"
                @click="markPaid(item)"
              />
            </template>
          </v-tooltip>
          <v-tooltip text="Пересчитать матч водителя" location="top">
            <template #activator="{ props }">
              <v-btn
                v-bind="props"
                icon="mdi-refresh"
                size="x-small"
                variant="text"
                :loading="rematching === item.id"
                @click="rematchFine(item)"
              />
            </template>
          </v-tooltip>
          <v-tooltip text="Удалить" location="top">
            <template #activator="{ props }">
              <v-btn
                v-bind="props"
                icon="mdi-delete-outline"
                size="x-small"
                variant="text"
                color="error"
                @click="confirmDelete(item)"
              />
            </template>
          </v-tooltip>
        </div>
      </template>
    </v-data-table>

    <!-- ── Add Fine Dialog ── -->
    <v-dialog v-model="addDialog" max-width="520" persistent>
      <v-card rounded="lg">
        <v-card-title class="d-flex align-center ga-2 pa-4 pb-2">
          <v-icon icon="mdi-alert-octagon-outline" color="warning" />
          Добавить штраф
        </v-card-title>
        <v-divider />
        <v-card-text class="pa-4">
          <v-row dense>
            <v-col cols="12" sm="6">
              <v-text-field
                v-model="form.issued_at"
                label="Дата и время штрафа"
                type="datetime-local"
                density="compact"
                variant="outlined"
                :rules="[v => !!v || 'Обязательное поле']"
              />
            </v-col>
            <v-col cols="12" sm="6">
              <v-text-field
                v-model.number="form.amount"
                label="Сумма (₽)"
                type="number"
                min="0"
                step="0.01"
                density="compact"
                variant="outlined"
                :rules="[v => (v != null && v > 0) || 'Введите сумму > 0']"
              />
            </v-col>
            <v-col cols="12" sm="6">
              <v-text-field
                v-model="form.doc_number"
                label="№ постановления"
                density="compact"
                variant="outlined"
              />
            </v-col>
            <v-col cols="12" sm="6">
              <v-text-field
                v-model="form.violation_type"
                label="Тип нарушения"
                density="compact"
                variant="outlined"
                placeholder="превышение скорости 20-40 км/ч"
              />
            </v-col>
            <v-col cols="12">
              <v-text-field
                v-model="form.location"
                label="Место нарушения"
                density="compact"
                variant="outlined"
              />
            </v-col>
            <v-col cols="12">
              <v-textarea
                v-model="form.comment"
                label="Комментарий"
                rows="2"
                density="compact"
                variant="outlined"
              />
            </v-col>
          </v-row>

          <!-- Matched driver preview (after save) -->
          <v-alert
            v-if="lastMatchedDriver"
            type="success"
            variant="tonal"
            density="compact"
            class="mt-2"
          >
            Водитель по путёвке: <strong>{{ lastMatchedDriver }}</strong>
          </v-alert>
          <v-alert
            v-if="saveError"
            type="error"
            variant="tonal"
            density="compact"
            class="mt-2"
          >
            {{ saveError }}
          </v-alert>
        </v-card-text>
        <v-divider />
        <v-card-actions class="pa-3">
          <v-spacer />
          <v-btn variant="text" @click="closeAddDialog">Отмена</v-btn>
          <v-btn
            color="primary"
            variant="flat"
            :loading="saving"
            :disabled="!form.issued_at || !(form.amount > 0)"
            @click="saveFine"
          >
            Сохранить
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Delete confirm ── -->
    <v-dialog v-model="deleteDialog" max-width="400">
      <v-card rounded="lg">
        <v-card-title class="pa-4 pb-2">Удалить штраф?</v-card-title>
        <v-card-text>
          Штраф на сумму <strong>{{ fmtRub(Number(deleteTarget?.amount ?? 0)) }}</strong>
          от {{ deleteTarget ? formatDateTime(deleteTarget.issued_at) : '' }} будет удалён.
        </v-card-text>
        <v-card-actions class="pa-3">
          <v-spacer />
          <v-btn variant="text" @click="deleteDialog = false">Отмена</v-btn>
          <v-btn color="error" variant="flat" :loading="deleting" @click="doDelete">Удалить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Snackbar -->
    <v-snackbar v-model="snackbar.show" :color="snackbar.color" timeout="4000">
      {{ snackbar.text }}
      <template #actions>
        <v-btn variant="text" @click="snackbar.show = false">Закрыть</v-btn>
      </template>
    </v-snackbar>

  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { apiFetch } from '@/api'

const props = defineProps<{ vehicleId: number }>()

interface VehicleFine {
  id: number
  vehicle_id: number
  issued_at: string
  amount: string | number
  doc_number: string | null
  violation_type: string | null
  location: string | null
  status: string
  paid_at: string | null
  comment: string | null
  driver_name: string | null
  driver_kind: string
  matched_trip_id: number | null
}

const STATUS_COLOR: Record<string, string> = {
  unpaid: 'error',
  paid: 'success',
  disputed: 'warning',
}
const STATUS_LABEL: Record<string, string> = {
  unpaid: 'Не оплачен',
  paid: 'Оплачен',
  disputed: 'Оспаривается',
}

const headers = [
  { title: 'Дата', key: 'issued_at', sortable: true, width: '150px' },
  { title: 'Сумма', key: 'amount', sortable: true, width: '110px' },
  { title: '№ постановления', key: 'doc_number', sortable: false },
  { title: 'Нарушение', key: 'violation_type', sortable: false },
  { title: 'Место', key: 'location', sortable: false },
  { title: 'Водитель', key: 'driver_name', sortable: false },
  { title: 'Статус', key: 'status', sortable: false, width: '120px' },
  { title: '', key: 'actions', sortable: false, width: '110px' },
]

const fines = ref<VehicleFine[]>([])
const loading = ref(false)
const paying = ref<number | null>(null)
const rematching = ref<number | null>(null)
const deleting = ref(false)

// Add dialog
const addDialog = ref(false)
const saving = ref(false)
const saveError = ref<string | null>(null)
const lastMatchedDriver = ref<string | null>(null)
const form = ref({
  issued_at: '',
  amount: 0,
  doc_number: '',
  violation_type: '',
  location: '',
  comment: '',
})

// Delete dialog
const deleteDialog = ref(false)
const deleteTarget = ref<VehicleFine | null>(null)

const snackbar = ref({ show: false, text: '', color: 'success' })

function showSnack(text: string, color = 'success') {
  snackbar.value = { show: true, text, color }
}

function formatDateTime(val: string): string {
  if (!val) return '—'
  const d = new Date(val)
  return d.toLocaleString('ru-RU', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

function fmtRub(val: number): string {
  return val.toLocaleString('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 })
}

async function fetchFines(): Promise<void> {
  loading.value = true
  try {
    fines.value = await apiFetch<VehicleFine[]>(`/vehicle-fines/?vehicle_id=${props.vehicleId}`)
  } catch (e) {
    console.error('[VehicleFinesTab] fetchFines', e)
    showSnack('Ошибка загрузки штрафов', 'error')
  } finally {
    loading.value = false
  }
}

function openAddDialog() {
  form.value = { issued_at: '', amount: 0, doc_number: '', violation_type: '', location: '', comment: '' }
  saveError.value = null
  lastMatchedDriver.value = null
  addDialog.value = true
}

function closeAddDialog() {
  addDialog.value = false
}

async function saveFine(): Promise<void> {
  saveError.value = null
  lastMatchedDriver.value = null
  saving.value = true
  try {
    const payload = {
      vehicle_id: props.vehicleId,
      issued_at: new Date(form.value.issued_at).toISOString(),
      amount: form.value.amount,
      doc_number: form.value.doc_number || null,
      violation_type: form.value.violation_type || null,
      location: form.value.location || null,
      comment: form.value.comment || null,
    }
    let created: VehicleFine
    try {
      created = await apiFetch<VehicleFine>('/vehicle-fines/', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
    } catch (apiErr: any) {
      const msg = apiErr?.payload?.message || apiErr?.message || 'HTTP error'
      saveError.value = typeof msg === 'string' ? msg : JSON.stringify(msg)
      return
    }
    if (created.driver_name) {
      lastMatchedDriver.value = created.driver_name
    }
    await fetchFines()
    showSnack('Штраф добавлен')
    if (!created.driver_name) {
      // No match — close after short delay so user sees empty state
      setTimeout(() => { addDialog.value = false }, 300)
    }
  } catch (e) {
    saveError.value = e instanceof Error ? e.message : 'Ошибка сохранения'
  } finally {
    saving.value = false
  }
}

async function markPaid(fine: VehicleFine): Promise<void> {
  paying.value = fine.id
  try {
    await apiFetch(`/vehicle-fines/${fine.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ status: 'paid' }),
    })
    await fetchFines()
    showSnack('Штраф отмечен оплаченным')
  } catch (e) {
    showSnack(e instanceof Error ? e.message : 'Ошибка', 'error')
  } finally {
    paying.value = null
  }
}

async function rematchFine(fine: VehicleFine): Promise<void> {
  rematching.value = fine.id
  try {
    const updated = await apiFetch<VehicleFine>(`/vehicle-fines/${fine.id}/rematch`, {
      method: 'POST',
    })
    await fetchFines()
    showSnack(updated.driver_name
      ? `Водитель найден: ${updated.driver_name}`
      : 'Путёвка на эту дату не найдена')
  } catch (e) {
    showSnack(e instanceof Error ? e.message : 'Ошибка пересчёта', 'error')
  } finally {
    rematching.value = null
  }
}

function confirmDelete(fine: VehicleFine) {
  deleteTarget.value = fine
  deleteDialog.value = true
}

async function doDelete(): Promise<void> {
  if (!deleteTarget.value) return
  deleting.value = true
  try {
    await apiFetch(`/vehicle-fines/${deleteTarget.value.id}`, {
      method: 'DELETE',
    })
    deleteDialog.value = false
    await fetchFines()
    showSnack('Штраф удалён')
  } catch (e) {
    showSnack(e instanceof Error ? e.message : 'Ошибка удаления', 'error')
  } finally {
    deleting.value = false
  }
}

onMounted(fetchFines)
</script>

<style scoped>
.vehicle-fines-tab {
  min-height: 200px;
}
</style>
