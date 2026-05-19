<template>
  <v-container fluid class="pa-4">
    <!-- Filter bar -->
    <v-row class="mb-4" align="center" dense>
      <v-col cols="12" sm="4" md="3">
        <v-select
          v-model="filterField"
          :items="fieldOptions"
          item-title="label"
          item-value="key"
          label="Поле"
          clearable
          density="compact"
          hide-details
          variant="outlined"
          @update:model-value="resetAndLoad"
        />
      </v-col>
      <v-col cols="12" sm="4" md="3">
        <v-text-field
          v-model="filterDateFrom"
          label="Дата с"
          type="date"
          density="compact"
          hide-details
          variant="outlined"
          @update:model-value="resetAndLoad"
        />
      </v-col>
      <v-col cols="12" sm="4" md="3">
        <v-text-field
          v-model="filterDateTo"
          label="Дата по"
          type="date"
          density="compact"
          hide-details
          variant="outlined"
          @update:model-value="resetAndLoad"
        />
      </v-col>
      <v-col cols="auto">
        <v-btn
          variant="text"
          density="compact"
          @click="clearFilters"
        >
          Сбросить
        </v-btn>
      </v-col>
    </v-row>

    <!-- Loading -->
    <div v-if="loading" class="text-center py-8">
      <v-progress-circular indeterminate color="primary" />
    </div>

    <!-- Empty -->
    <v-alert
      v-else-if="!loading && !items.length"
      type="info"
      variant="tonal"
      class="mb-4"
    >
      История изменений пуста
    </v-alert>

    <!-- Timeline -->
    <v-timeline v-else density="compact" side="end" class="history-timeline">
      <v-timeline-item
        v-for="item in items"
        :key="item.id"
        dot-color="primary"
        size="small"
      >
        <template #opposite>
          <div class="text-caption text-medium-emphasis text-no-wrap">
            {{ formatDate(item.changed_at) }}
          </div>
        </template>

        <v-card variant="outlined" class="mb-2">
          <v-card-text class="pa-3">
            <!-- Field + user -->
            <div class="d-flex flex-wrap align-center gap-2 mb-2">
              <v-chip size="small" color="primary" variant="tonal">
                {{ FIELD_LABELS[item.field_key] ?? item.field_key }}
              </v-chip>
              <span v-if="item.changed_by_user" class="text-caption text-medium-emphasis">
                {{ item.changed_by_user.full_name }}
              </span>
              <span v-else-if="item.changed_by_user_id" class="text-caption text-medium-emphasis">
                пользователь #{{ item.changed_by_user_id }}
              </span>
            </div>

            <!-- Old → New -->
            <div class="d-flex flex-wrap align-center gap-1">
              <v-chip
                size="small"
                color="error"
                variant="tonal"
                class="text-decoration-line-through"
              >
                <template #default>
                  <v-tooltip v-if="isLong(item.old_value)" location="bottom">
                    <template #activator="{ props: tip }">
                      <span v-bind="tip">было: {{ truncate(item.old_value) }}</span>
                    </template>
                    {{ item.old_value }}
                  </v-tooltip>
                  <span v-else>было: {{ item.old_value ?? '—' }}</span>
                </template>
              </v-chip>

              <v-icon size="14" color="grey">mdi-arrow-right</v-icon>

              <v-chip size="small" color="success" variant="tonal">
                <template #default>
                  <v-tooltip v-if="isLong(item.new_value)" location="bottom">
                    <template #activator="{ props: tip }">
                      <span v-bind="tip">стало: {{ truncate(item.new_value) }}</span>
                    </template>
                    {{ item.new_value }}
                  </v-tooltip>
                  <span v-else>стало: {{ item.new_value ?? '—' }}</span>
                </template>
              </v-chip>
            </div>

            <!-- Comment -->
            <div v-if="item.comment" class="text-caption text-medium-emphasis mt-2">
              «{{ item.comment }}»
            </div>
          </v-card-text>
        </v-card>
      </v-timeline-item>
    </v-timeline>

    <!-- Pagination -->
    <div v-if="totalPages > 1" class="d-flex justify-center mt-4">
      <v-pagination
        v-model="page"
        :length="totalPages"
        :total-visible="7"
        @update:model-value="loadHistory"
      />
    </div>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { apiFetch } from '@/api'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  vehicleId: number
}>()

// ─── Field label mapping ──────────────────────────────────────────────────────

const FIELD_LABELS: Record<string, string> = {
  plate: 'Гос. номер',
  brand: 'Марка',
  model: 'Модель',
  color: 'Цвет',
  vin: 'VIN',
  type: 'Тип ТС',
  state: 'Состояние',
  fuel_type: 'Тип топлива',
  fuel_norm_summer: 'Норма топлива (лето)',
  fuel_norm_winter: 'Норма топлива (зима)',
  registered_at: 'Дата регистрации',
  insurance_until: 'Страховка до',
  next_to_km: 'ТО через (км)',
  owner_org_id: 'Организация-владелец',
  assigned_org_id: 'Организация-эксплуатант',
  assigned_text: 'Закреплено за',
  has_tracker: 'GPS-трекер',
  akb_ok: 'АКБ в норме',
  has_radio: 'Радиостанция',
  mirrors_ok: 'Зеркала ОК',
  has_keys: 'Ключи',
  has_first_aid_kit: 'Аптечка',
  has_spare_wheel: 'Запаска',
  has_extinguisher: 'Огнетушитель',
}

// ─── Types ───────────────────────────────────────────────────────────────────

interface HistoryUser {
  id: number
  full_name: string
}

interface FieldHistoryItem {
  id: number
  vehicle_id: number
  field_key: string
  old_value: string | null
  new_value: string | null
  changed_at: string
  changed_by_user_id: number | null
  changed_by_user?: HistoryUser | null
  comment: string | null
}

// ─── State ───────────────────────────────────────────────────────────────────

const items = ref<FieldHistoryItem[]>([])
const loading = ref(false)
const page = ref(1)
const totalItems = ref(0)
const PAGE_SIZE = 50

const filterField = ref<string | null>(null)
const filterDateFrom = ref<string>('')
const filterDateTo = ref<string>('')

// ─── Computed ────────────────────────────────────────────────────────────────

const totalPages = computed(() => Math.ceil(totalItems.value / PAGE_SIZE))

const fieldOptions = computed(() => [
  { key: null, label: 'Все поля' },
  ...Object.entries(FIELD_LABELS).map(([key, label]) => ({ key, label })),
])

// ─── Load ─────────────────────────────────────────────────────────────────────

async function loadHistory() {
  loading.value = true
  try {
    const params = new URLSearchParams()
    params.set('limit', String(PAGE_SIZE))
    params.set('offset', String((page.value - 1) * PAGE_SIZE))
    if (filterField.value) params.set('field_key', filterField.value)
    if (filterDateFrom.value) params.set('date_from', filterDateFrom.value)
    if (filterDateTo.value) params.set('date_to', filterDateTo.value)

    const data = await apiFetch<FieldHistoryItem[] | { items: FieldHistoryItem[]; total: number }>(
      `/vehicles/${props.vehicleId}/field-history?${params.toString()}`
    )

    if (Array.isArray(data)) {
      items.value = data
      // Backend returns plain array without total — use array length for pagination hint
      totalItems.value = data.length < PAGE_SIZE ? (page.value - 1) * PAGE_SIZE + data.length : page.value * PAGE_SIZE + 1
    } else {
      items.value = data.items ?? []
      totalItems.value = data.total ?? 0
    }
  } catch (e) {
    console.error('VehicleHistoryTab fetch error', e)
    items.value = []
    totalItems.value = 0
  } finally {
    loading.value = false
  }
}

function resetAndLoad() {
  page.value = 1
  loadHistory()
}

function clearFilters() {
  filterField.value = null
  filterDateFrom.value = ''
  filterDateTo.value = ''
  resetAndLoad()
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const TRUNCATE_LEN = 40

function isLong(val: string | null | undefined): boolean {
  return !!val && val.length > TRUNCATE_LEN
}

function truncate(val: string | null | undefined): string {
  if (!val) return '—'
  return val.length > TRUNCATE_LEN ? val.slice(0, TRUNCATE_LEN) + '…' : val
}

function formatDate(s: string): string {
  try {
    return new Date(s).toLocaleString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return s
  }
}

// ─── Init ─────────────────────────────────────────────────────────────────────

onMounted(() => {
  loadHistory()
})
</script>

<style scoped>
.history-timeline {
  max-width: 900px;
}
.gap-1 {
  gap: 4px;
}
.gap-2 {
  gap: 8px;
}
</style>
