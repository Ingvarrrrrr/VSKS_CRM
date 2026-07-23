<template>
  <v-container fluid class="pa-4">
    <!-- Header -->
    <div class="d-flex align-center mb-4 flex-wrap" style="gap:12px">
      <div>
        <h1 class="text-h5 font-weight-bold">Отчёты</h1>
        <span class="text-body-2 text-medium-emphasis">{{ periodLabel }}</span>
      </div>
      <v-spacer />
      <v-select
        v-model="filterSubsidyId"
        :items="subsidyOptions"
        item-title="name" item-value="id"
        label="Субсидия"
        variant="outlined" density="compact" clearable hide-details
        style="max-width:220px"
        @update:model-value="load"
      />
      <v-select
        v-model="filterDepartment"
        :items="departmentOptions"
        label="Отдел"
        variant="outlined" density="compact" clearable hide-details
        style="max-width:200px"
        @update:model-value="load"
      />
      <v-btn-toggle v-model="period" mandatory density="compact" color="primary" @update:model-value="load">
        <v-btn value="week" size="small">Неделя</v-btn>
        <v-btn value="month" size="small">Месяц</v-btn>
        <v-btn value="year" size="small">Год</v-btn>
      </v-btn-toggle>
      <div class="d-flex align-center" style="gap:4px">
        <v-btn icon="mdi-chevron-left" variant="text" size="small" @click="navigate(-1)" />
        <v-btn variant="outlined" size="small" @click="goToday">Сегодня</v-btn>
        <v-btn icon="mdi-chevron-right" variant="text" size="small" @click="navigate(1)" />
      </div>
      <v-btn variant="tonal" color="primary" size="small" prepend-icon="mdi-refresh" :loading="loading" @click="load">
        Обновить
      </v-btn>
    </div>

    <div v-if="loading && !data" class="d-flex justify-center py-12">
      <v-progress-circular indeterminate color="primary" size="48" />
    </div>

    <template v-else-if="data">
      <!-- KPI Cards -->
      <v-row class="mb-4">
        <v-col cols="6" md="2">
          <v-card variant="outlined" class="pa-3 text-center">
            <div class="text-h5 font-weight-bold text-blue">{{ data.totals.planned_count }}</div>
            <div class="text-caption text-medium-emphasis">Запланировано</div>
            <div class="text-caption text-blue">{{ formatMoney(data.totals.planned_sum) }}</div>
          </v-card>
        </v-col>
        <v-col cols="6" md="2">
          <v-card variant="outlined" class="pa-3 text-center">
            <div class="text-h5 font-weight-bold text-teal">{{ data.totals.active_count }}</div>
            <div class="text-caption text-medium-emphasis">В работе</div>
            <div class="text-caption text-teal">{{ formatMoney(data.totals.active_sum) }}</div>
          </v-card>
        </v-col>
        <v-col cols="6" md="2">
          <v-card variant="outlined" class="pa-3 text-center">
            <div class="text-h5 font-weight-bold text-success">{{ data.totals.completed_count }}</div>
            <div class="text-caption text-medium-emphasis">Завершено</div>
            <div class="text-caption text-success">{{ formatMoney(data.totals.completed_sum) }}</div>
          </v-card>
        </v-col>
        <v-col cols="6" md="2">
          <v-card variant="outlined" class="pa-3 text-center">
            <div class="text-h5 font-weight-bold text-warning">{{ data.totals.upcoming_count }}</div>
            <div class="text-caption text-medium-emphasis">Предстоит</div>
          </v-card>
        </v-col>
        <v-col cols="6" md="2">
          <v-card variant="outlined" class="pa-3 text-center">
            <div class="text-h5 font-weight-bold text-error">{{ data.totals.overdue_count }}</div>
            <div class="text-caption text-medium-emphasis">Просрочено</div>
          </v-card>
        </v-col>
      </v-row>

      <!-- Sections -->
      <div ref="registryArea">
      <v-expansion-panels v-model="openPanels" multiple>
        <v-expansion-panel v-if="data.overdue.length > 0" value="overdue">
          <v-expansion-panel-title>
            <v-icon icon="mdi-alert-circle" color="error" class="mr-2" />
            Просроченные ({{ data.overdue.length }})
            <v-spacer />
            <RegistryExportButton
              title="Просроченные"
              :get-columns="() => REPORT_COLUMNS_OVERDUE"
              :get-rows="() => getReportRows('overdue')"
              :get-capture-el="() => registryArea"
              @click.stop
              @error="(m) => console.error(m)"
            />
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <v-table density="compact" hover>
              <thead><tr>
                <th>Название</th><th>Статус</th><th>Контрагент</th>
                <th class="text-right">Сумма</th><th>Срок</th><th>Исполнитель</th><th>Комментарий</th>
              </tr></thead>
              <tbody>
                <tr v-for="item in data.overdue" :key="item.id" style="cursor:pointer" @click="openItem(item.id)">
                  <td class="font-weight-medium">{{ item.subject || `#${item.purchase_number || item.id}` }}</td>
                  <td><v-chip :color="statusColor(item.status)" size="x-small" variant="flat">{{ STATUS_LABELS[item.status] }}</v-chip></td>
                  <td class="text-body-2">{{ item.contractor_name || '—' }}</td>
                  <td class="text-right text-body-2 font-weight-medium">{{ formatMoney(item.payment_amount || item.contract_price || item.planned_total_price) }}</td>
                  <td class="text-body-2">{{ formatDateRu(item.execution_term) || '—' }}</td>
                  <td class="text-body-2">{{ item.assigned_user_name || '—' }}</td>
                  <td class="text-body-2 text-truncate" style="max-width:180px">{{ item.task_comment || '' }}</td>
                </tr>
              </tbody>
            </v-table>
          </v-expansion-panel-text>
        </v-expansion-panel>

        <v-expansion-panel value="active">
          <v-expansion-panel-title>
            <v-icon icon="mdi-progress-wrench" color="teal" class="mr-2" />
            В работе ({{ data.active.length }})
            <v-spacer />
            <RegistryExportButton
              title="В работе"
              :get-columns="() => REPORT_COLUMNS_ACTIVE"
              :get-rows="() => getReportRows('active')"
              @click.stop
              @error="(m) => console.error(m)"
            />
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <v-table density="compact" hover>
              <thead><tr>
                <th>Название</th><th>Статус</th><th>Контрагент</th>
                <th class="text-right">Сумма</th><th>Срок</th><th>Исполнитель</th><th>Комментарий</th>
              </tr></thead>
              <tbody>
                <tr v-for="item in data.active" :key="item.id" style="cursor:pointer" @click="openItem(item.id)">
                  <td class="font-weight-medium">{{ item.subject || `#${item.purchase_number || item.id}` }}</td>
                  <td><v-chip :color="statusColor(item.status)" size="x-small" variant="flat">{{ STATUS_LABELS[item.status] }}</v-chip></td>
                  <td class="text-body-2">{{ item.contractor_name || '—' }}</td>
                  <td class="text-right text-body-2 font-weight-medium">{{ formatMoney(item.contract_price || item.planned_total_price) }}</td>
                  <td class="text-body-2">{{ formatDateRu(item.execution_term) || '—' }}</td>
                  <td class="text-body-2">{{ item.assigned_user_name || '—' }}</td>
                  <td class="text-body-2 text-truncate" style="max-width:180px">{{ item.task_comment || '' }}</td>
                </tr>
                <tr v-if="data.active.length === 0"><td colspan="7" class="text-center text-medium-emphasis pa-4">Нет данных</td></tr>
              </tbody>
            </v-table>
          </v-expansion-panel-text>
        </v-expansion-panel>

        <v-expansion-panel value="completed">
          <v-expansion-panel-title>
            <v-icon icon="mdi-check-circle" color="success" class="mr-2" />
            Завершено за период ({{ data.completed.length }})
            <v-spacer />
            <RegistryExportButton
              title="Завершено"
              :get-columns="() => REPORT_COLUMNS_COMPLETED"
              :get-rows="() => getReportRows('completed')"
              @click.stop
              @error="(m) => console.error(m)"
            />
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <v-table density="compact" hover>
              <thead><tr>
                <th>Название</th><th>Контрагент</th>
                <th class="text-right">Оплачено</th><th>Исполнитель</th><th>Комментарий</th>
              </tr></thead>
              <tbody>
                <tr v-for="item in data.completed" :key="item.id" style="cursor:pointer" @click="openItem(item.id)">
                  <td class="font-weight-medium">{{ item.subject || `#${item.purchase_number || item.id}` }}</td>
                  <td class="text-body-2">{{ item.contractor_name || '—' }}</td>
                  <td class="text-right text-body-2 font-weight-medium text-success">{{ formatMoney(item.payment_amount) }}</td>
                  <td class="text-body-2">{{ item.assigned_user_name || '—' }}</td>
                  <td class="text-body-2 text-truncate" style="max-width:180px">{{ item.task_comment || '' }}</td>
                </tr>
                <tr v-if="data.completed.length === 0"><td colspan="5" class="text-center text-medium-emphasis pa-4">Нет данных</td></tr>
              </tbody>
            </v-table>
          </v-expansion-panel-text>
        </v-expansion-panel>

        <v-expansion-panel value="planned">
          <v-expansion-panel-title>
            <v-icon icon="mdi-clock-outline" color="blue" class="mr-2" />
            Запланировано ({{ data.planned.length }})
            <v-spacer />
            <RegistryExportButton
              title="Запланировано"
              :get-columns="() => REPORT_COLUMNS_PLANNED"
              :get-rows="() => getReportRows('planned')"
              @click.stop
              @error="(m) => console.error(m)"
            />
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <v-table density="compact" hover>
              <thead><tr>
                <th>Название</th><th>Статус</th><th>Контрагент</th>
                <th class="text-right">НМЦД</th><th>Срок</th><th>Субсидия</th>
              </tr></thead>
              <tbody>
                <tr v-for="item in data.planned" :key="item.id" style="cursor:pointer" @click="openItem(item.id)">
                  <td class="font-weight-medium">{{ item.subject || `#${item.purchase_number || item.id}` }}</td>
                  <td><v-chip :color="statusColor(item.status)" size="x-small" variant="flat">{{ STATUS_LABELS[item.status] }}</v-chip></td>
                  <td class="text-body-2">{{ item.contractor_name || '—' }}</td>
                  <td class="text-right text-body-2 font-weight-medium">{{ formatMoney(item.planned_total_price) }}</td>
                  <td class="text-body-2">{{ formatDateRu(item.execution_term) || '—' }}</td>
                  <td class="text-body-2">{{ item.subsidy_name || '—' }}</td>
                </tr>
                <tr v-if="data.planned.length === 0"><td colspan="6" class="text-center text-medium-emphasis pa-4">Нет данных</td></tr>
              </tbody>
            </v-table>
          </v-expansion-panel-text>
        </v-expansion-panel>

        <v-expansion-panel v-if="data.upcoming.length > 0" value="upcoming">
          <v-expansion-panel-title>
            <v-icon icon="mdi-calendar-arrow-right" color="warning" class="mr-2" />
            Предстоит ({{ data.upcoming.length }})
            <v-spacer />
            <RegistryExportButton
              title="Предстоит"
              :get-columns="() => REPORT_COLUMNS_UPCOMING"
              :get-rows="() => getReportRows('upcoming')"
              @click.stop
              @error="(m) => console.error(m)"
            />
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <v-table density="compact" hover>
              <thead><tr>
                <th>Название</th><th>Статус</th><th>Контрагент</th>
                <th class="text-right">Сумма</th><th>Срок</th>
              </tr></thead>
              <tbody>
                <tr v-for="item in data.upcoming" :key="item.id" style="cursor:pointer" @click="openItem(item.id)">
                  <td class="font-weight-medium">{{ item.subject || `#${item.purchase_number || item.id}` }}</td>
                  <td><v-chip :color="statusColor(item.status)" size="x-small" variant="flat">{{ STATUS_LABELS[item.status] }}</v-chip></td>
                  <td class="text-body-2">{{ item.contractor_name || '—' }}</td>
                  <td class="text-right text-body-2 font-weight-medium">{{ formatMoney(item.contract_price || item.planned_total_price) }}</td>
                  <td class="text-body-2">{{ formatDateRu(item.execution_term) || '—' }}</td>
                </tr>
              </tbody>
            </v-table>
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>
      </div>
    </template>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch } from '@/api'
import RegistryExportButton from '@/components/RegistryExportButton.vue'

const router = useRouter()
const loading = ref(false)
const registryArea = ref<HTMLElement | null>(null)
const period = ref<'week' | 'month' | 'year'>('week')
const refDate = ref(new Date().toISOString().slice(0, 10))
const data = ref<any>(null)
const openPanels = ref(['overdue', 'active'])
const filterSubsidyId = ref<number | null>(null)
const filterDepartment = ref<string | null>(null)
const subsidyOptions = ref<{ id: number; name: string }[]>([])
const departmentOptions = ref<string[]>([])

const STATUS_LABELS: Record<string, string> = {
  planned: 'План', work_in_progress: 'Ведётся работа', in_progress: 'Ведётся работа',
  contracted: 'Договор', delivered: 'Поставл.', paid: 'Оплачена',
}

const periodLabel = computed(() => {
  if (!data.value) return ''
  const s = formatDateRu(data.value.start_date)
  const e = formatDateRu(data.value.end_date)
  const names: Record<string, string> = { week: 'Неделя', month: 'Месяц', year: 'Год' }
  return `${names[period.value]}: ${s} — ${e}`
})

function navigate(dir: number) {
  const d = new Date(refDate.value)
  if (period.value === 'week') d.setDate(d.getDate() + dir * 7)
  else if (period.value === 'month') d.setMonth(d.getMonth() + dir)
  else d.setFullYear(d.getFullYear() + dir)
  refDate.value = d.toISOString().slice(0, 10)
  load()
}

function goToday() {
  refDate.value = new Date().toISOString().slice(0, 10)
  load()
}

function openItem(id: number) {
  router.push(`/orders/${id}/edit`)
}

function statusColor(s: string): string {
  const map: Record<string, string> = {
    planned: 'grey', work_in_progress: 'teal', in_progress: 'teal',
    contracted: 'indigo', delivered: 'deep-purple', paid: 'success',
  }
  return map[s] || 'grey'
}

function formatDateRu(d?: string): string {
  if (!d) return ''
  const [y, m, day] = d.split('-')
  return `${day}.${m}.${y}`
}

function formatMoney(v?: number): string {
  if (!v) return '0 ₽'
  if (v >= 1_000_000) return (v / 1_000_000).toFixed(1) + ' млн ₽'
  if (v >= 1_000) return (v / 1_000).toFixed(0) + ' тыс ₽'
  return v.toLocaleString('ru-RU') + ' ₽'
}

async function load() {
  loading.value = true
  try {
    const params = new URLSearchParams({ period: period.value, ref_date: refDate.value })
    if (filterSubsidyId.value) params.set('subsidy_id', String(filterSubsidyId.value))
    if (filterDepartment.value) params.set('department', filterDepartment.value)
    data.value = await apiFetch<any>(`/reports/summary?${params}`)
  } finally {
    loading.value = false
  }
}

async function loadFilters() {
  try { subsidyOptions.value = await apiFetch<any[]>('/subsidies/') } catch { subsidyOptions.value = [] }
  try { departmentOptions.value = await apiFetch<string[]>('/users/dictionaries/departments') } catch { departmentOptions.value = [] }
}

onMounted(() => {
  load()
  loadFilters()
})

const REPORT_COLUMNS_OVERDUE = [
  { key: 'subject', title: 'Название' },
  { key: 'status', title: 'Статус' },
  { key: 'contractor_name', title: 'Контрагент' },
  { key: 'payment_amount', title: 'Сумма' },
  { key: 'execution_term', title: 'Срок' },
  { key: 'assigned_user_name', title: 'Исполнитель' },
  { key: 'task_comment', title: 'Комментарий' },
]
const REPORT_COLUMNS_ACTIVE = [
  { key: 'subject', title: 'Название' },
  { key: 'status', title: 'Статус' },
  { key: 'contractor_name', title: 'Контрагент' },
  { key: 'contract_price', title: 'Сумма' },
  { key: 'execution_term', title: 'Срок' },
  { key: 'assigned_user_name', title: 'Исполнитель' },
  { key: 'task_comment', title: 'Комментарий' },
]
const REPORT_COLUMNS_COMPLETED = [
  { key: 'subject', title: 'Название' },
  { key: 'contractor_name', title: 'Контрагент' },
  { key: 'payment_amount', title: 'Оплачено' },
  { key: 'assigned_user_name', title: 'Исполнитель' },
  { key: 'task_comment', title: 'Комментарий' },
]
const REPORT_COLUMNS_PLANNED = [
  { key: 'subject', title: 'Название' },
  { key: 'status', title: 'Статус' },
  { key: 'contractor_name', title: 'Контрагент' },
  { key: 'planned_total_price', title: 'НМЦД' },
  { key: 'execution_term', title: 'Срок' },
  { key: 'subsidy_name', title: 'Субсидия' },
]
const REPORT_COLUMNS_UPCOMING = [
  { key: 'subject', title: 'Название' },
  { key: 'status', title: 'Статус' },
  { key: 'contractor_name', title: 'Контрагент' },
  { key: 'contract_price', title: 'Сумма' },
  { key: 'execution_term', title: 'Срок' },
]
function getReportRows(section: 'overdue' | 'active' | 'completed' | 'planned' | 'upcoming') {
  return data.value?.[section] ?? []
}
</script>
