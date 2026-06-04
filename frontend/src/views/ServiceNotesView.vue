<template>
  <v-container fluid class="pa-6">
    <div class="d-flex align-center justify-space-between mb-6">
      <div>
        <h1 class="text-h5 font-weight-bold">Служебные записки на выдачу</h1>
        <span class="text-body-2 text-medium-emphasis">{{ filteredItems.length }} записей</span>
      </div>
      <div class="d-flex gap-2">
        <v-btn variant="tonal" prepend-icon="mdi-view-column" size="small" @click="showColumnPicker = true">Колонки</v-btn>
        <v-btn color="primary" prepend-icon="mdi-plus" to="/service-notes/create">Добавить</v-btn>
      </div>
    </div>

    <v-card class="mb-4" variant="outlined">
      <v-card-text class="py-3">
        <div class="d-flex align-center gap-4 flex-wrap">
          <v-select
            v-model="filterSubsidyId"
            :items="subsidies"
            item-title="name"
            item-value="id"
            label="Субсидия"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            style="min-width:220px"
          />
          <v-select
            v-model="filterStatus"
            :items="statusItems"
            item-title="label"
            item-value="value"
            label="Статус"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            style="min-width:170px"
          />
          <v-text-field
            v-model="search"
            prepend-inner-icon="mdi-magnify"
            label="Поиск"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            style="min-width:200px"
          />
          <v-autocomplete
            v-model="filterCreatorId"
            :items="users"
            item-title="full_name"
            item-value="id"
            label="От кого"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            style="min-width:200px;max-width:240px"
          />
          <v-autocomplete
            v-model="filterAssignedUserId"
            :items="users"
            item-title="full_name"
            item-value="id"
            label="Кому"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            style="min-width:200px;max-width:240px"
          />
          <v-text-field
            v-model="filterServiceNoteFrom"
            type="date"
            label="Дата СЗ с"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            style="min-width:150px;max-width:180px"
          />
          <v-text-field
            v-model="filterServiceNoteTo"
            type="date"
            label="Дата СЗ по"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            style="min-width:150px;max-width:180px"
          />
        </div>
      </v-card-text>
    </v-card>

    <v-chip-group v-model="filterStatus" class="mb-4">
      <v-chip value="" variant="outlined" filter>Все</v-chip>
      <v-chip
        v-for="s in statusItems"
        :key="s.value"
        :value="s.value"
        :color="s.color"
        filter
        variant="outlined"
      >
        {{ s.label }}
      </v-chip>
    </v-chip-group>

    <v-data-table
        v-resizable-columns="'service-notes'"
        :headers="visibleHeaders"
        :items="filteredItems"
        :loading="loading"
        :search="search"
        density="compact"
        hover
        items-per-page="25"
        :items-per-page-options="[25, 50, 100, -1]"
      >
        <template #item.status="{ item }">
          <v-chip :color="statusColor(item.status)" size="x-small" variant="tonal">
            {{ statusLabel(item.status, item) }}
          </v-chip>
        </template>

        <template #item.nmck="{ item }">
          {{ formatMoney(item.total_nmck ?? item.planned_total_price) }}
        </template>

        <template #item.delivery_date="{ item }">
          {{ item.delivery_date ? new Date(item.delivery_date).toLocaleDateString('ru-RU') : '—' }}
        </template>

        <template #item.creator_name="{ item }">
          {{ resolveUserName(item.service_note_by) }}
        </template>

        <template #item.assigned_user_name="{ item }">
          {{ resolveUserName(item.assigned_user_id) }}
        </template>

        <template #item.subject="{ item }">
          <span :title="item.subject || ''">{{ truncate(item.subject, 40) }}</span>
        </template>

        <template #item.service_note_at="{ item }">
          {{ item.service_note_at ? new Date(item.service_note_at).toLocaleDateString('ru-RU') : '—' }}
        </template>

        <template #item.actions="{ item }">
          <v-btn icon="mdi-pencil" variant="text" size="small"
            :to="`/service-notes/${item.id}/edit`" />
        </template>

        <template #no-data>
          <div class="text-center py-10">
            <v-icon icon="mdi-file-account-outline" size="48" color="grey-lighten-1" class="mb-3" />
            <div class="text-medium-emphasis">Служебные записки не найдены</div>
            <v-btn color="primary" class="mt-3" to="/service-notes/create">Создать первую</v-btn>
          </div>
        </template>
      </v-data-table>

    <v-snackbar v-model="snack.show" :color="snack.color" :timeout="3000" location="bottom right">
      {{ snack.text }}
    </v-snackbar>

    <ColumnConfigDialog
      v-model="showColumnPicker"
      :all-columns="allColumns"
      :state="colState"
      :show-width="true"
      :toggle-visible="toggleVisible"
      :set-position="setPosition"
      :set-width="setWidth"
      :reset="resetColumns"
    />
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive } from 'vue'
import { apiFetch } from '@/api'
import { useColumnConfig, type ColumnDef } from '@/composables/useColumnConfig'
import ColumnConfigDialog from '@/components/ColumnConfigDialog.vue'

interface Purchase {
  id: number
  purchase_number?: number
  status: string
  item_name?: string
  subject?: string
  subsidy_id?: number
  total_nmck?: number
  planned_total_price?: number
  delivery_date?: string
  registry_number?: string
  purchase_basis?: string
  purchase_contract_type?: string
  assigned_user_id?: number | null
  service_note_by?: number | null
  service_note_at?: string | null
  service_note_text?: string | null
}
const FRAMEWORK_TYPES = new Set(['framework_cumulative', 'framework_with_amount'])

interface Subsidy { id: number; name: string }
interface User { id: number; full_name: string }

const items = ref<Purchase[]>([])
const subsidies = ref<Subsidy[]>([])
const users = ref<User[]>([])
const loading = ref(false)
const filterStatus = ref<string>('')
const filterSubsidyId = ref<number | null>(null)
const filterCreatorId = ref<number | null>(null)
const filterAssignedUserId = ref<number | null>(null)
const filterServiceNoteFrom = ref('')
const filterServiceNoteTo = ref('')
const search = ref('')

// Build user lookup map for O(1) name resolution
const userMap = computed<Map<number, string>>(() => {
  const m = new Map<number, string>()
  for (const u of users.value) m.set(u.id, u.full_name)
  return m
})

function resolveUserName(id?: number | null): string {
  if (!id) return '—'
  return userMap.value.get(id) || `#${id}`
}

function truncate(str: string | undefined | null, len: number): string {
  if (!str) return '—'
  return str.length > len ? str.slice(0, len) + '…' : str
}

const snack = reactive({ show: false, text: '', color: 'success' })

const STATUS_LABEL: Record<string, string> = {
  wishes: 'Желания', plan_schedule: 'План-график',
  confirmed: 'Подтверждено', work_in_progress: 'В работе',
  contracted: 'Договор', delivered: 'Поставлено', paid: 'Оплачено',
}
const STATUS_COLOR: Record<string, string> = {
  wishes: 'amber', plan_schedule: 'orange',
  confirmed: 'blue', work_in_progress: 'teal',
  contracted: 'indigo', delivered: 'deep-purple', paid: 'green',
}
const statusItems = Object.entries(STATUS_LABEL).map(([value, label]) => ({
  value, label, color: STATUS_COLOR[value],
}))

const statusLabel = (s: string, item?: Purchase) => {
  if (s === 'contracted' && item && FRAMEWORK_TYPES.has(item.purchase_contract_type || '')) return 'Заказ'
  return STATUS_LABEL[s] || s
}
const statusColor = (s: string) => STATUS_COLOR[s] || 'grey'
const formatMoney = (v?: number | null) => v ? Number(v).toLocaleString('ru-RU') + ' ₽' : '—'

const allColumns: ColumnDef[] = [
  { title: '#', key: 'purchase_number', width: 70 },
  { title: 'Наименование', key: 'item_name' },
  { title: 'Предмет', key: 'subject', width: 200 },
  { title: 'Статус', key: 'status', width: 130 },
  { title: 'НМЦД', key: 'nmck', width: 130, align: 'end' },
  { title: 'Срок поставки', key: 'delivery_date', width: 140 },
  { title: 'От кого', key: 'creator_name', width: 180 },
  { title: 'Кому', key: 'assigned_user_name', width: 180 },
  { title: 'Дата СЗ', key: 'service_note_at', width: 120 },
  { title: 'Действия', key: 'actions', width: 80, sortable: false },
]

const { state: colState, visibleHeaders, toggleVisible, setPosition, setWidth, reset: resetColumns } = useColumnConfig('service_notes', allColumns)
const showColumnPicker = ref(false)

const filteredItems = computed(() => {
  let r = items.value
  if (filterStatus.value) r = r.filter(p => p.status === filterStatus.value)
  if (filterSubsidyId.value) r = r.filter(p => p.subsidy_id === filterSubsidyId.value)
  if (filterCreatorId.value) r = r.filter(p => p.service_note_by === filterCreatorId.value)
  if (filterAssignedUserId.value) r = r.filter(p => p.assigned_user_id === filterAssignedUserId.value)
  if (filterServiceNoteFrom.value) {
    const from = new Date(filterServiceNoteFrom.value).getTime()
    r = r.filter(p => p.service_note_at ? new Date(p.service_note_at).getTime() >= from : false)
  }
  if (filterServiceNoteTo.value) {
    const to = new Date(filterServiceNoteTo.value).getTime() + 86400000 // inclusive
    r = r.filter(p => p.service_note_at ? new Date(p.service_note_at).getTime() <= to : false)
  }
  return r
})

async function load() {
  loading.value = true
  try {
    ;[items.value, subsidies.value, users.value] = await Promise.all([
      apiFetch<Purchase[]>('/purchases/?purchase_basis=service_note'),
      apiFetch<Subsidy[]>('/subsidies/'),
      apiFetch<User[]>('/users/'),
    ])
  } catch {
    snack.text = 'Ошибка загрузки'; snack.color = 'error'; snack.show = true
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>
