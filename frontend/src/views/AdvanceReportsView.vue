<template>
  <v-container fluid class="pa-6">
    <div class="d-flex align-center justify-space-between mb-6">
      <div>
        <h1 class="text-h5 font-weight-bold">Авансовые отчёты</h1>
        <span class="text-body-2 text-medium-emphasis">{{ enrichedItems.length }} записей</span>
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
          <v-autocomplete
            v-model="filterContractorIds"
            :items="usedContractors"
            item-title="name"
            item-value="id"
            label="Контрагент"
            variant="outlined"
            density="compact"
            multiple
            chips
            closable-chips
            clearable
            hide-details
            style="min-width:220px"
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
          <v-btn size="small" variant="tonal" @click="clearFilters">Сбросить</v-btn>
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
        v-model="selected"
        v-model:expanded="expandedRows"
        :headers="headers"
        :items="filteredItems"
        :loading="loading"
        :search="search"
        show-select
        show-expand
        :single-expand="false"
        density="compact"
        hover
        items-per-page="25"
        :items-per-page-options="[25, 50, 100, -1]"
        item-value="id"
      >
        <template #item.index="{ index }">
          <span class="text-medium-emphasis text-caption">{{ index + 1 }}</span>
        </template>

        <template #item.displayName="{ item }">
          <span>{{ item.displayName }}</span>
        </template>

        <template #item.contractor_name="{ item }">
          <v-chip v-if="(item as any).reimbursement_user_name" size="x-small" color="purple" variant="tonal" prepend-icon="mdi-account">
            {{ (item as any).reimbursement_user_name }}
          </v-chip>
          <v-chip v-else-if="(item as any).multi_contractor_label === 'Множественный контрагент'" size="x-small" color="orange" variant="tonal" prepend-icon="mdi-domain-switch">
            {{ (item as any).multi_contractor_label }}
          </v-chip>
          <span v-else class="text-caption">{{ (item as any).multi_contractor_label || item.contractor_name || '—' }}</span>
        </template>

        <template #item.reimbursement_user_name="{ item }">
          <span class="text-caption">{{ item.reimbursement_user_name || '—' }}</span>
        </template>

        <template #item.subsidy_name="{ item }">
          <span class="text-caption">{{ item.subsidy_name || '—' }}</span>
        </template>

        <template #item.status="{ item }">
          <v-chip :color="statusColor(item.status)" size="x-small" variant="tonal">
            {{ statusLabel(item.status, item) }}
          </v-chip>
        </template>

        <template #item.nmck="{ item }">
          {{ formatMoney(item.total_nmck ?? item.planned_total_price) }}
        </template>

        <template #item.executionDate="{ item }">
          {{ item.executionDate ? new Date(item.executionDate).toLocaleDateString('ru-RU') : '—' }}
        </template>

        <!-- Expanded row: состав (items + receipts info) -->
        <template #expanded-row="{ columns, item }">
          <tr>
            <td :colspan="columns.length" class="pa-0">
              <div class="pa-3 bg-grey-lighten-5">
                <div class="text-caption font-weight-medium text-medium-emphasis mb-2">
                  Состав авансового отчёта #{{ item.purchase_number || item.id }}
                </div>
                <div v-if="!item.items || !item.items.length" class="text-caption text-medium-emphasis">
                  Нет позиций
                </div>
                <v-table v-else density="compact">
                  <thead>
                    <tr>
                      <th>Наименование</th>
                      <th class="text-right">Кол-во</th>
                      <th class="text-right">Цена ед.</th>
                      <th class="text-right">Сумма</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(pi, ii) in item.items" :key="ii">
                      <td class="text-caption">{{ pi.item_name || '—' }}</td>
                      <td class="text-right text-caption">{{ pi.quantity ?? '—' }}</td>
                      <td class="text-right text-caption">{{ pi.unit_price ? formatMoney(pi.unit_price) : '—' }}</td>
                      <td class="text-right text-caption">{{ pi.total_price ? formatMoney(pi.total_price) : '—' }}</td>
                    </tr>
                    <tr class="font-weight-bold">
                      <td colspan="3" class="text-right text-caption">Итого:</td>
                      <td class="text-right text-caption">{{ formatMoney((item.items as any[]).reduce((s: number, i: any) => s + (Number(i.total_price) || 0), 0)) }}</td>
                    </tr>
                  </tbody>
                </v-table>
                <div v-if="item.last_receipt_date" class="text-caption text-medium-emphasis mt-2">
                  Последний чек: {{ new Date(item.last_receipt_date).toLocaleDateString('ru-RU') }}
                </div>
              </div>
            </td>
          </tr>
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
  subsidy_name?: string
  total_nmck?: number
  planned_total_price?: number
  delivery_date?: string
  acceptance_doc_date?: string
  last_receipt_date?: string
  purchase_method?: string
  purchase_contract_type?: string
  contractor_id?: number
  contractor_name?: string
  contractor_inn?: string
  reimbursement_user_id?: number | null
  reimbursement_user_name?: string | null
  multi_contractor_label?: string | null
  items?: any[]
}

interface Subsidy { id: number; name: string }
interface Contractor { id: number; name: string; inn?: string }

const FRAMEWORK_TYPES = new Set(['framework_cumulative', 'framework_with_amount'])

const items = ref<Purchase[]>([])
const subsidies = ref<Subsidy[]>([])
const contractors = ref<Contractor[]>([])
const loading = ref(false)
const filterStatus = ref<string>('')
const filterSubsidyId = ref<number | null>(null)
const filterContractorIds = ref<number[]>([])
const search = ref('')
const selected = ref<number[]>([])
const expandedRows = ref<number[]>([])

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

function pickDate(...dates: (string | undefined | null)[]): string | null {
  for (const d of dates) {
    if (d) return d
  }
  return null
}

const headers = [
  { title: '', key: 'data-table-select', width: 40 },
  { title: '', key: 'data-table-expand', width: 40 },
  { title: '№', key: 'index', width: 55, sortable: false },
  { title: 'Наименование', key: 'displayName', minWidth: 240 },
  { title: 'Контрагент', key: 'contractor_name', minWidth: 200 },
  { title: 'Кому возмещать', key: 'reimbursement_user_name', minWidth: 180 },
  { title: 'Субсидия', key: 'subsidy_name', width: 160 },
  { title: 'Сумма', key: 'nmck', width: 130, align: 'end' as const },
  { title: 'Дата исполнения', key: 'executionDate', width: 140 },
  { title: 'Статус', key: 'status', width: 130 },
]

// Дедуп по имени контрагента — у авансовых contractor_id часто пуст, есть только contractor_name.
const usedContractors = computed(() => {
  const byName = new Map<string, any>()
  for (const p of items.value) {
    const name = p.contractor_name
    if (!name || byName.has(name)) continue
    const real = contractors.value.find(c =>
      (p.contractor_id && c.id === p.contractor_id) ||
      (p.contractor_inn && c.inn === p.contractor_inn) ||
      c.name === name
    )
    byName.set(name, real || { id: -byName.size - 1, name, inn: p.contractor_inn || '' })
  }
  return Array.from(byName.values())
})

const enrichedItems = computed(() => items.value.map(p => ({
  ...p,
  displayName: p.subject || p.item_name || '—',
  executionDate: pickDate(p.last_receipt_date, p.acceptance_doc_date, p.delivery_date),
})))

const filteredItems = computed(() => {
  let r = enrichedItems.value
  if (filterStatus.value) r = r.filter(p => p.status === filterStatus.value)
  if (filterSubsidyId.value) r = r.filter(p => p.subsidy_id === filterSubsidyId.value)
  if (filterContractorIds.value.length) {
    const allowedNames = new Set(
      usedContractors.value
        .filter((c: any) => filterContractorIds.value.includes(c.id))
        .map((c: any) => c.name)
    )
    r = r.filter(p => !!p.contractor_name && allowedNames.has(p.contractor_name))
  }
  return r
})

function clearFilters() {
  filterStatus.value = ''
  filterSubsidyId.value = null
  filterContractorIds.value = []
  search.value = ''
}

async function load() {
  loading.value = true
  try {
    const [purchasesData, subsidiesData, contractorsData] = await Promise.all([
      apiFetch<Purchase[]>('/purchases/?purchase_method=advance'),
      apiFetch<Subsidy[]>('/subsidies/'),
      apiFetch<Contractor[]>('/contractors/'),
    ])
    items.value = purchasesData
    subsidies.value = subsidiesData
    contractors.value = contractorsData
  } catch {
    snack.text = 'Ошибка загрузки'; snack.color = 'error'; snack.show = true
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>
