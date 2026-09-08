<template>
  <div class="chart-card" style="height:100%;overflow:auto">
    <div class="chart-card-header">
      <v-icon icon="mdi-calendar-clock" size="18" color="primary" class="mr-2" />
      <span class="chart-card-title">Финансовый план</span>
      <v-spacer />
      <v-tooltip text="Кликни по бару чтобы увидеть закупки этой группы" location="top">
        <template #activator="{ props: tip }">
          <v-icon v-bind="tip" icon="mdi-cursor-default-click" size="14" class="ml-1" color="grey" />
        </template>
      </v-tooltip>
      <v-btn-toggle v-model="finplanGranularity" mandatory size="x-small" density="compact" class="ml-2">
        <v-btn value="month">По месяцам</v-btn>
        <v-btn value="quarter">По кварталам</v-btn>
      </v-btn-toggle>
      <v-btn size="x-small" variant="tonal" color="success" prepend-icon="mdi-microsoft-excel" @click="$emit('export-xlsx')" class="ml-2">
        Excel
      </v-btn>
    </div>

    <!-- No-deadline banner -->
    <v-alert
      v-if="finplanNoDeadlineCount > 0"
      type="warning" variant="tonal" density="compact" class="mx-3 mt-2"
      :text="`${finplanNoDeadlineCount} закупок без срока исполнения — данные некорректны`"
    >
      <template #append>
        <v-btn size="x-small" variant="tonal" color="warning" @click="$emit('open-drilldown', '', 'no_deadline')">
          Показать
        </v-btn>
      </template>
    </v-alert>

    <!-- KPI текущего месяца -->
    <div v-if="finplanCurrentMonthKpi" class="d-flex gap-3 px-3 py-2">
      <v-card variant="tonal" color="warning" class="pa-2 flex-1 text-center" density="compact">
        <div class="text-caption text-medium-emphasis">План</div>
        <div class="text-body-2 font-weight-bold">{{ formatCurrencyShort(finplanCurrentMonthKpi.plan) }}</div>
      </v-card>
      <v-card variant="tonal" color="error" class="pa-2 flex-1 text-center" density="compact" style="cursor:pointer" @click="$emit('open-drilldown', finplanCurrentMonthKpi.period, 'overdue')">
        <div class="text-caption text-medium-emphasis">Накопл. долг</div>
        <div class="text-body-2 font-weight-bold">{{ formatCurrencyShort(finplanCurrentMonthKpi.overdue) }}</div>
      </v-card>
      <v-card variant="tonal" color="primary" class="pa-2 flex-1 text-center" density="compact">
        <div class="text-caption text-medium-emphasis">Итого к оплате</div>
        <div class="text-body-2 font-weight-bold">{{ formatCurrencyShort(finplanCurrentMonthKpi.plan + finplanCurrentMonthKpi.overdue) }}</div>
      </v-card>
    </div>

    <apexchart
      v-if="finplanSeries.length"
      type="bar" height="300"
      :options="finplanOptions" :series="finplanSeries"
    />
    <div v-else class="chart-empty">
      <v-icon icon="mdi-calendar-clock" size="48" color="grey-lighten-2" />
      <div class="text-caption text-medium-emphasis mt-2">Нет данных по ожидаемым выплатам</div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  finplanNoDeadlineCount: number
  finplanCurrentMonthKpi: { period: string; plan: number; overdue: number } | null
  finplanSeries: any[]
  finplanOptions: any
  formatCurrencyShort: (v: number) => string
}>()

defineEmits<{
  (e: 'open-drilldown', period: string, category: 'plan' | 'committed' | 'overdue' | 'no_deadline'): void
  (e: 'export-xlsx'): void
}>()

const finplanGranularity = defineModel<'month' | 'quarter'>('finplanGranularity', { required: true })
</script>
