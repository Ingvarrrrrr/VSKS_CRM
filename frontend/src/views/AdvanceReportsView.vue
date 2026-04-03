<template>
  <v-container fluid class="pa-6">
    <div class="d-flex align-center justify-space-between mb-6">
      <div>
        <h1 class="text-h5 font-weight-bold">Авансовые отчёты</h1>
        <span class="text-body-2 text-medium-emphasis">{{ filteredItems.length }} записей</span>
      </div>
      <v-btn color="primary" prepend-icon="mdi-plus" to="/advance-reports/create">Добавить</v-btn>
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

    <v-card variant="outlined">
      <v-data-table
        :headers="headers"
        :items="filteredItems"
        :loading="loading"
        :search="search"
        density="compact"
        hover
        items-per-page="25"
        :items-per-page-options="[25, 50, 100, -1]"
        @click:row="(_e: any, { item }: any) => $router.push(`/advance-reports/${item.id}/edit`)"
        style="cursor:pointer"
      >
        <template #item.index="{ index }">
          <span class="text-medium-emphasis text-caption">{{ index + 1 }}</span>
        </template>

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

        <template #no-data>
          <div class="text-center py-10">
            <v-icon icon="mdi-cash-register" size="48" color="grey-lighten-1" class="mb-3" />
            <div class="text-medium-emphasis">Авансовые отчёты не найдены</div>
            <v-btn color="primary" class="mt-3" to="/advance-reports/create">Создать первый</v-btn>
          </div>
        </template>
      </v-data-table>
    </v-card>

    <v-snackbar v-model="snack.show" :color="snack.color" :timeout="3000" location="bottom right">
      {{ snack.text }}
    </v-snackbar>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive } from 'vue'
import { apiFetch } from '@/api'

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
  purchase_method?: string
  purchase_contract_type?: string
}
const FRAMEWORK_TYPES = new Set(['framework_cumulative', 'framework_with_amount'])

interface Subsidy { id: number; name: string }

const items = ref<Purchase[]>([])
const subsidies = ref<Subsidy[]>([])
const loading = ref(false)
const filterStatus = ref<string>('')
const filterSubsidyId = ref<number | null>(null)
const search = ref('')

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

const headers = [
  { title: '№', key: 'index', width: 55, sortable: false },
  { title: 'Наименование', key: 'item_name', minWidth: 240 },
  { title: 'Статус', key: 'status', width: 130 },
  { title: 'Сумма', key: 'nmck', width: 130, align: 'end' as const },
  { title: 'Дата', key: 'delivery_date', width: 140 },
]

const filteredItems = computed(() => {
  let r = items.value
  if (filterStatus.value) r = r.filter(p => p.status === filterStatus.value)
  if (filterSubsidyId.value) r = r.filter(p => p.subsidy_id === filterSubsidyId.value)
  return r
})

async function load() {
  loading.value = true
  try {
    items.value = await apiFetch<Purchase[]>('/purchases/?purchase_method=advance')
    subsidies.value = await apiFetch<Subsidy[]>('/subsidies/')
  } catch {
    snack.text = 'Ошибка загрузки'; snack.color = 'error'; snack.show = true
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>
