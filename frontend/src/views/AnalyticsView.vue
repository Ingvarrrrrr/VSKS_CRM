<template>
  <v-container fluid class="pa-6">
    <div class="d-flex align-center mb-6">
      <div>
        <h1 class="text-h5 font-weight-bold">Аналитика</h1>
        <span class="text-body-2 text-medium-emphasis">Сводная статистика по закупкам</span>
      </div>
      <v-spacer />
      <v-btn variant="outlined" prepend-icon="mdi-refresh" :loading="loading" @click="load">
        Обновить
      </v-btn>
    </div>

    <div v-if="loading" class="d-flex justify-center py-12">
      <v-progress-circular indeterminate color="primary" size="48" />
    </div>

    <template v-else-if="data">
      <!-- KPI row -->
      <v-row class="mb-4">
        <v-col cols="6" md="3">
          <v-card variant="outlined" class="pa-4 text-center">
            <div class="text-h4 font-weight-bold text-error">{{ data.overdue_count }}</div>
            <div class="text-body-2 text-medium-emphasis mt-1">Просрочено</div>
            <v-icon icon="mdi-alert-circle" color="error" class="mt-1" />
          </v-card>
        </v-col>
        <v-col cols="6" md="3">
          <v-card variant="outlined" class="pa-4 text-center">
            <div class="text-h4 font-weight-bold text-warning">{{ data.upcoming_deadlines.length }}</div>
            <div class="text-body-2 text-medium-emphasis mt-1">Срок до 30 дней</div>
            <v-icon icon="mdi-clock-alert" color="warning" class="mt-1" />
          </v-card>
        </v-col>
        <v-col cols="6" md="3">
          <v-card variant="outlined" class="pa-4 text-center">
            <div class="text-h4 font-weight-bold text-success">{{ totalPaid }}</div>
            <div class="text-body-2 text-medium-emphasis mt-1">Оплачено за год</div>
            <v-icon icon="mdi-cash-check" color="success" class="mt-1" />
          </v-card>
        </v-col>
        <v-col cols="6" md="3">
          <v-card variant="outlined" class="pa-4 text-center">
            <div class="text-h4 font-weight-bold text-primary">{{ totalPurchases }}</div>
            <div class="text-body-2 text-medium-emphasis mt-1">Всего закупок</div>
            <v-icon icon="mdi-clipboard-list" color="primary" class="mt-1" />
          </v-card>
        </v-col>
      </v-row>

      <v-row>
        <!-- Purchase funnel -->
        <v-col cols="12" md="6">
          <v-card variant="outlined" class="pa-4">
            <div class="text-subtitle-1 font-weight-bold mb-3">Воронка закупок</div>
            <div v-for="item in data.funnel" :key="item.status" class="mb-2">
              <div class="d-flex justify-space-between mb-1">
                <span class="text-body-2">{{ STATUS_LABELS[item.status] || item.status }}</span>
                <span class="text-body-2 font-weight-medium">{{ item.count }}</span>
              </div>
              <v-progress-linear
                :model-value="funnelPct(item.count)"
                :color="STATUS_COLORS[item.status] || 'grey'"
                rounded height="20"
                bg-color="grey-lighten-3"
              >
                <template v-slot:default>
                  <span v-if="item.total" class="text-caption text-white font-weight-bold">
                    {{ formatMoney(item.total) }}
                  </span>
                </template>
              </v-progress-linear>
            </div>
          </v-card>
        </v-col>

        <!-- Purchase method distribution -->
        <v-col cols="12" md="3">
          <v-card variant="outlined" class="pa-4" style="height:100%">
            <div class="text-subtitle-1 font-weight-bold mb-3">Способы закупки</div>
            <div v-for="(cnt, method) in data.method_distribution" :key="method" class="mb-3">
              <div class="d-flex justify-space-between mb-1">
                <span class="text-body-2">{{ METHOD_LABELS[method] || method }}</span>
                <span class="text-body-2 font-weight-medium">{{ cnt }}</span>
              </div>
              <v-progress-linear
                :model-value="(cnt / totalPurchases) * 100"
                :color="METHOD_COLORS[method] || 'blue-grey'"
                rounded height="14"
                bg-color="grey-lighten-3"
              />
            </div>
          </v-card>
        </v-col>

        <!-- Upcoming deadlines -->
        <v-col cols="12" md="3">
          <v-card variant="outlined" class="pa-4" style="height:100%">
            <div class="text-subtitle-1 font-weight-bold mb-3">
              Ближайшие сроки
              <v-chip size="x-small" color="warning" variant="tonal" class="ml-1">{{ data.upcoming_deadlines.length }}</v-chip>
            </div>
            <div v-if="data.upcoming_deadlines.length === 0" class="text-caption text-medium-emphasis">
              Нет сроков в ближайшие 30 дней
            </div>
            <div v-for="d in data.upcoming_deadlines" :key="d.id" class="deadline-item">
              <div class="d-flex align-center justify-space-between">
                <router-link :to="`/orders/${d.id}`" class="text-body-2 deadline-link">
                  {{ d.name || `Закупка #${d.purchase_number || d.id}` }}
                </router-link>
                <v-chip :color="deadlineColor(d.execution_term)" size="x-small" variant="tonal">
                  {{ formatDate(d.execution_term) }}
                </v-chip>
              </div>
            </div>
          </v-card>
        </v-col>
      </v-row>

      <!-- Plan vs Fact -->
      <v-row class="mt-4">
        <v-col cols="12">
          <v-card variant="outlined" class="pa-4">
            <div class="text-subtitle-1 font-weight-bold mb-3">План / Факт по субсидиям</div>
            <v-table density="compact">
              <thead>
                <tr>
                  <th>Субсидия</th>
                  <th class="text-right">НМЦД (план)</th>
                  <th class="text-right">Законтрактовано</th>
                  <th class="text-right">Оплачено</th>
                  <th>Исполнение</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="pf in data.plan_fact" :key="pf.subsidy">
                  <td class="text-body-2">{{ pf.subsidy }}</td>
                  <td class="text-right text-body-2">{{ formatMoney(pf.plan) }}</td>
                  <td class="text-right text-body-2">{{ formatMoney(pf.contracted) }}</td>
                  <td class="text-right text-body-2 text-success">{{ formatMoney(pf.paid) }}</td>
                  <td style="min-width:150px">
                    <v-progress-linear
                      v-if="pf.plan > 0"
                      :model-value="Math.min((pf.contracted / pf.plan) * 100, 100)"
                      color="blue" height="12" rounded bg-color="grey-lighten-3"
                      :title="`Законтрактовано: ${Math.round((pf.contracted / pf.plan)*100)}%`"
                    />
                  </td>
                </tr>
                <tr v-if="data.plan_fact.length === 0">
                  <td colspan="5" class="text-center text-medium-emphasis text-caption pa-4">Нет данных</td>
                </tr>
              </tbody>
            </v-table>
          </v-card>
        </v-col>
      </v-row>

      <!-- Monthly paid + Top contractors -->
      <v-row class="mt-4">
        <v-col cols="12" md="7">
          <v-card variant="outlined" class="pa-4">
            <div class="text-subtitle-1 font-weight-bold mb-3">Ежемесячные оплаты (12 мес.)</div>
            <div v-if="data.monthly_paid.length === 0" class="text-caption text-medium-emphasis text-center py-4">
              Нет данных об оплатах
            </div>
            <div v-else class="monthly-chart">
              <div v-for="m in data.monthly_paid" :key="`${m.year}-${m.month}`" class="bar-col">
                <div class="bar-label">{{ formatMoney(m.total) }}</div>
                <div class="bar-wrap">
                  <div
                    class="bar-fill"
                    :style="{ height: barHeight(m.total) + '%' }"
                    :title="`${MONTH_NAMES[m.month - 1]} ${m.year}: ${formatMoney(m.total)}`"
                  />
                </div>
                <div class="bar-x">{{ MONTH_NAMES[m.month - 1].slice(0,3) }}<br/>{{ m.year }}</div>
              </div>
            </div>
          </v-card>
        </v-col>

        <v-col cols="12" md="5">
          <v-card variant="outlined" class="pa-4">
            <div class="text-subtitle-1 font-weight-bold mb-3">Топ контрагентов по сумме</div>
            <div v-for="(c, i) in data.top_contractors" :key="c.name" class="mb-2">
              <div class="d-flex justify-space-between mb-1">
                <span class="text-body-2 text-truncate" style="max-width:200px" :title="c.name">
                  {{ i + 1 }}. {{ c.name }}
                </span>
                <span class="text-body-2 font-weight-medium ml-2 flex-shrink-0">{{ formatMoney(c.total) }}</span>
              </div>
              <v-progress-linear
                :model-value="topContractorPct(c.total)"
                color="indigo" rounded height="10" bg-color="grey-lighten-3"
              />
            </div>
            <div v-if="data.top_contractors.length === 0" class="text-caption text-medium-emphasis text-center py-4">
              Нет данных
            </div>
          </v-card>
        </v-col>
      </v-row>
    </template>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { apiFetch } from '@/api'

interface FunnelItem { status: string; count: number; total: number }
interface MonthItem { year: number; month: number; total: number }
interface ContractorItem { name: string; total: number }
interface DeadlineItem { id: number; name: string; purchase_number?: number; execution_term: string; status: string }
interface PlanFactItem { subsidy: string; plan: number; contracted: number; paid: number }
interface AnalyticsData {
  funnel: FunnelItem[]
  monthly_paid: MonthItem[]
  top_contractors: ContractorItem[]
  overdue_count: number
  upcoming_deadlines: DeadlineItem[]
  method_distribution: Record<string, number>
  plan_fact: PlanFactItem[]
}

const STATUS_LABELS: Record<string, string> = {
  planned: 'Планирование', confirmed: 'Подтверждена', in_progress: 'В работе',
  contracted: 'Законтрактована', delivered: 'Поставлена', paid: 'Оплачена',
}
const STATUS_COLORS: Record<string, string> = {
  planned: 'orange', confirmed: 'blue', in_progress: 'teal',
  contracted: 'indigo', delivered: 'deep-purple', paid: 'green',
}
const METHOD_LABELS: Record<string, string> = {
  single: 'Единственный поставщик', competitive: 'Конкурсная процедура',
  quote_request: 'Запрос котировок', unknown: 'Не указано',
}
const METHOD_COLORS: Record<string, string> = {
  single: 'blue', competitive: 'teal', quote_request: 'purple', unknown: 'grey',
}
const MONTH_NAMES = ['Янв','Фев','Мар','Апр','Май','Июн','Июл','Авг','Сен','Окт','Ноя','Дек']

const data = ref<AnalyticsData | null>(null)
const loading = ref(false)

const totalPurchases = computed(() =>
  data.value ? data.value.funnel.reduce((s, i) => s + i.count, 0) : 0
)
const totalPaid = computed(() => {
  if (!data.value) return '—'
  const total = data.value.monthly_paid.reduce((s, i) => s + i.total, 0)
  return formatMoney(total)
})

const maxFunnelCount = computed(() =>
  data.value ? Math.max(...data.value.funnel.map(i => i.count), 1) : 1
)
const funnelPct = (count: number) => (count / maxFunnelCount.value) * 100

const maxContractor = computed(() =>
  data.value && data.value.top_contractors.length ? data.value.top_contractors[0].total : 1
)
const topContractorPct = (total: number) => (total / maxContractor.value) * 100

const maxMonthly = computed(() =>
  data.value && data.value.monthly_paid.length ? Math.max(...data.value.monthly_paid.map(m => m.total)) : 1
)
const barHeight = (total: number) => Math.max((total / maxMonthly.value) * 100, 4)

function formatMoney(v?: number): string {
  if (!v) return '0 ₽'
  if (v >= 1_000_000_000) return (v / 1_000_000_000).toFixed(1) + ' млрд ₽'
  if (v >= 1_000_000) return (v / 1_000_000).toFixed(1) + ' млн ₽'
  if (v >= 1_000) return (v / 1_000).toFixed(0) + ' тыс ₽'
  return v.toLocaleString('ru-RU') + ' ₽'
}

function formatDate(d: string): string {
  if (!d) return ''
  const [y, m, day] = d.split('-')
  return `${day}.${m}.${y}`
}

function deadlineColor(d: string): string {
  const diff = (new Date(d).getTime() - Date.now()) / 86400000
  if (diff <= 7) return 'error'
  if (diff <= 14) return 'warning'
  return 'success'
}

async function load() {
  loading.value = true
  try {
    data.value = await apiFetch<AnalyticsData>('/dashboard/analytics')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.deadline-item { padding: 6px 0; border-bottom: 1px solid var(--crm-border); }
.deadline-item:last-child { border-bottom: none; }
.deadline-link { text-decoration: none; color: inherit; }
.deadline-link:hover { text-decoration: underline; }
.monthly-chart {
  display: flex; align-items: flex-end; gap: 6px;
  height: 160px; padding: 0 4px;
}
.bar-col {
  flex: 1; display: flex; flex-direction: column; align-items: center;
}
.bar-label {
  font-size: 9px; color: var(--crm-text-muted); text-align: center; min-height: 24px;
  display: flex; align-items: flex-end; justify-content: center; margin-bottom: 2px;
  transform: rotate(-30deg); transform-origin: bottom right;
}
.bar-wrap {
  flex: 1; width: 100%; display: flex; align-items: flex-end;
  min-height: 100px;
}
.bar-fill {
  width: 100%; background: linear-gradient(180deg, #6366f1 0%, #4338ca 100%);
  border-radius: 4px 4px 0 0; min-height: 4px;
  transition: height 0.5s ease;
}
.bar-x { font-size: 9px; text-align: center; color: var(--crm-text-faint); margin-top: 4px; line-height: 1.2; }
</style>
