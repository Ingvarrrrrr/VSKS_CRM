<template>
  <div v-if="analyticsLoading" class="d-flex justify-center py-12">
    <v-progress-circular indeterminate color="primary" size="48" />
  </div>
  <template v-else-if="analyticsData">
    <!-- KPI row -->
    <v-row class="mb-4">
      <v-col cols="6" md="3">
        <v-card variant="outlined" class="pa-4 text-center table-row-hover" style="cursor:pointer" @click="router.push('/orders?overdue=1')">
          <div class="text-h4 font-weight-bold text-error">{{ analyticsData.overdue_count }}</div>
          <div class="text-body-2 text-medium-emphasis mt-1">Просрочено</div>
          <v-icon icon="mdi-alert-circle" color="error" class="mt-1" />
        </v-card>
      </v-col>
      <v-col cols="6" md="3">
        <v-card variant="outlined" class="pa-4 text-center table-row-hover" style="cursor:pointer" @click="router.push('/orders?due_soon=1')">
          <div class="text-h4 font-weight-bold text-warning">{{ analyticsData.upcoming_deadlines.length }}</div>
          <div class="text-body-2 text-medium-emphasis mt-1">Срок до 30 дней</div>
          <v-icon icon="mdi-clock-alert" color="warning" class="mt-1" />
        </v-card>
      </v-col>
      <v-col cols="6" md="3">
        <v-card variant="outlined" class="pa-4 text-center table-row-hover" style="cursor:pointer" @click="router.push('/orders?status=paid')">
          <div class="text-h4 font-weight-bold text-success">{{ analyticsTotalPaid }}</div>
          <div class="text-body-2 text-medium-emphasis mt-1">Оплачено за год</div>
          <v-icon icon="mdi-cash-check" color="success" class="mt-1" />
        </v-card>
      </v-col>
      <v-col cols="6" md="3">
        <v-card variant="outlined" class="pa-4 text-center table-row-hover" style="cursor:pointer" @click="router.push('/orders')">
          <div class="text-h4 font-weight-bold text-primary">{{ analyticsTotalPurchases }}</div>
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
          <div v-for="item in analyticsData.funnel" :key="item.status" class="mb-3" style="cursor:pointer" @click="router.push(`/orders?status=${item.status}`)">
            <div class="d-flex justify-space-between mb-1">
              <span class="text-body-2">{{ A_STATUS_LABELS[item.status] || item.status }}</span>
              <span class="text-body-2 font-weight-medium">{{ item.count }} шт{{ item.total ? ' · ' + formatCurrencyShort(item.total) : '' }}</span>
            </div>
            <v-progress-linear
              :model-value="analyticsFunnelPct(item.total)"
              :color="A_STATUS_COLORS[item.status] || 'grey'"
              rounded height="14" bg-color="grey-lighten-3"
            />
          </div>
        </v-card>
      </v-col>

      <!-- Purchase method distribution -->
      <v-col cols="12" md="3">
        <v-card variant="outlined" class="pa-4" style="height:100%">
          <div class="text-subtitle-1 font-weight-bold mb-3">Способы закупки</div>
          <div v-for="(cnt, method) in analyticsData.method_distribution" :key="method" class="mb-3" style="cursor:pointer" @click="router.push(`/orders?method=${method}`)">
            <div class="d-flex justify-space-between mb-1">
              <span class="text-body-2">{{ A_METHOD_LABELS[method] || method }}</span>
              <span class="text-body-2 font-weight-medium">{{ cnt }}</span>
            </div>
            <v-progress-linear
              :model-value="analyticsTotalPurchases > 0 ? (cnt / analyticsTotalPurchases) * 100 : 0"
              :color="A_METHOD_COLORS[method] || 'blue-grey'"
              rounded height="14" bg-color="grey-lighten-3"
            />
          </div>
        </v-card>
      </v-col>

      <!-- Upcoming deadlines -->
      <v-col cols="12" md="3">
        <v-card variant="outlined" class="pa-4" style="height:100%">
          <div class="text-subtitle-1 font-weight-bold mb-3">
            Ближайшие сроки
            <v-chip size="x-small" color="warning" variant="tonal" class="ml-1">{{ analyticsData.upcoming_deadlines.length }}</v-chip>
          </div>
          <div v-if="analyticsData.upcoming_deadlines.length === 0" class="text-caption text-medium-emphasis">
            Нет сроков в ближайшие 30 дней
          </div>
          <div v-for="d in analyticsData.upcoming_deadlines" :key="d.id" class="analytics-deadline-item">
            <div class="d-flex align-center justify-space-between">
              <router-link :to="`/orders/${d.id}`" class="text-body-2 analytics-deadline-link">
                {{ d.name || `Закупка #${d.purchase_number || d.id}` }}
              </router-link>
              <v-chip :color="analyticsDeadlineColor(d.execution_term)" size="x-small" variant="tonal">
                {{ analyticsFormatDate(d.execution_term) }}
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
              <tr v-for="pf in analyticsData.plan_fact" :key="pf.subsidy">
                <td class="text-body-2">{{ pf.subsidy }}</td>
                <td class="text-right text-body-2">{{ formatCurrencyShort(pf.plan) }}</td>
                <td class="text-right text-body-2">{{ formatCurrencyShort(pf.contracted) }}</td>
                <td class="text-right text-body-2 text-success">{{ formatCurrencyShort(pf.paid) }}</td>
                <td style="min-width:150px">
                  <v-progress-linear
                    v-if="pf.plan > 0"
                    :model-value="Math.min((pf.contracted / pf.plan) * 100, 100)"
                    color="blue" height="12" rounded bg-color="grey-lighten-3"
                    :title="`Законтрактовано: ${Math.round((pf.contracted / pf.plan)*100)}%`"
                  />
                </td>
              </tr>
              <tr v-if="analyticsData.plan_fact.length === 0">
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
          <div class="text-subtitle-1 font-weight-bold mb-3">Ежемесячные оплаты</div>
          <div v-if="analyticsData.monthly_payments.length === 0" class="text-caption text-medium-emphasis text-center py-4">
            Нет данных об оплатах
          </div>
          <div v-else class="analytics-monthly-chart">
            <div v-for="m in analyticsData.monthly_payments" :key="`${m.year}-${m.month}`" class="analytics-bar-col">
              <div class="analytics-bar-label">{{ formatCurrencyShort(m.total) }}</div>
              <div class="analytics-bar-wrap">
                <div class="analytics-bar-fill" :style="{ height: analyticsBarHeight(m.total) + '%' }" />
              </div>
              <div class="analytics-bar-x">{{ A_MONTH_NAMES[m.month - 1].slice(0,3) }}<br/>{{ m.year }}</div>
            </div>
          </div>
        </v-card>
      </v-col>

      <v-col cols="12" md="5">
        <v-card variant="outlined" class="pa-4">
          <div class="text-subtitle-1 font-weight-bold mb-3">Топ контрагентов по сумме</div>
          <div v-for="(c, i) in analyticsData.top_contractors" :key="c.name" class="mb-2">
            <div class="d-flex justify-space-between mb-1">
              <span class="text-body-2 text-truncate" style="max-width:200px" :title="c.name">
                {{ i + 1 }}. {{ c.name }}
              </span>
              <span class="text-body-2 font-weight-medium ml-2 flex-shrink-0">{{ formatCurrencyShort(c.total) }}</span>
            </div>
            <v-progress-linear
              :model-value="analyticsTopPct(c.total)"
              color="indigo" rounded height="10" bg-color="grey-lighten-3"
            />
          </div>
          <div v-if="analyticsData.top_contractors.length === 0" class="text-caption text-medium-emphasis text-center py-4">
            Нет данных
          </div>
        </v-card>
      </v-col>
    </v-row>
  </template>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import type { AnalyticsData } from '@/composables/dashboard/useAnalyticsTab'

defineProps<{
  analyticsLoading: boolean
  analyticsData: AnalyticsData | null
  analyticsTotalPurchases: number
  analyticsTotalPaid: string
  analyticsFunnelPct: (count: number) => number
  analyticsTopPct: (total: number) => number
  analyticsBarHeight: (total: number) => number
  analyticsFormatDate: (d: string) => string
  analyticsDeadlineColor: (d: string) => string
  formatCurrencyShort: (v: number) => string
  A_STATUS_LABELS: Record<string, string>
  A_STATUS_COLORS: Record<string, string>
  A_METHOD_LABELS: Record<string, string>
  A_METHOD_COLORS: Record<string, string>
  A_MONTH_NAMES: string[]
}>()

const router = useRouter()
</script>
