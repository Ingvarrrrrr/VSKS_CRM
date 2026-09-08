<template>
  <div class="chart-card" style="height:100%;overflow:auto">
    <div class="chart-card-header">
      <template v-if="donutView === 'breakdown'">
        <v-btn icon="mdi-arrow-left" variant="text" size="x-small" class="mr-1" @click="donutView = 'donut'" />
        <v-icon size="18" class="mr-2"
          :icon="['mdi-cash-check','mdi-file-sign','mdi-clock-outline','mdi-cash-remove'][drillDownSegment ?? 0]"
          :color="['success','primary','warning','grey'][drillDownSegment ?? 0]" />
        <span class="chart-card-title">{{ segmentLabels[drillDownSegment ?? 0] }}</span>
      </template>
      <template v-else>
        <v-icon icon="mdi-chart-donut" size="18" color="#3B82F6" class="mr-2" />
        <span class="chart-card-title">Структура бюджета</span>
        <span class="text-caption text-medium-emphasis ml-2">(нажмите на сегмент)</span>
      </template>
    </div>
    <Transition name="chart-fade" mode="out-in">
      <div v-if="donutView === 'donut'" key="donut">
        <apexchart v-if="donutReady" type="donut" height="270" :options="donutOptions" :series="donutSeries" />
        <div v-else class="chart-empty">
          <v-icon icon="mdi-chart-donut" size="48" color="grey-lighten-2" />
          <div class="text-caption text-medium-emphasis mt-2">Нет данных о бюджете</div>
        </div>
      </div>
      <div v-else key="breakdown">
        <apexchart type="bar" height="270" :options="breakdownBarOptions" :series="breakdownBarSeries" />
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  donutReady: boolean
  donutOptions: any
  donutSeries: number[]
  drillDownSegment: number | null
  breakdownBarOptions: any
  breakdownBarSeries: any[]
  segmentLabels: string[]
}>()

const donutView = defineModel<'donut' | 'breakdown'>('donutView', { required: true })
</script>
