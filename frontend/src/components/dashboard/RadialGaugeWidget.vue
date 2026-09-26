<template>
  <div class="chart-card chart-card--compact" style="height:100%;overflow:auto">
    <div class="chart-card-header">
      <v-icon icon="mdi-gauge" size="18" color="#22C55E" class="mr-2" />
      <span class="chart-card-title">Освоение</span>
    </div>
    <apexchart type="radialBar" height="180" :options="radialOptions" :series="[totalUsagePct]" :key="'gauge-' + totalUsagePct" />
    <div class="radial-footer">
      <span class="text-caption text-medium-emphasis">
        {{ formatCurrencyShort(totalPaid) }} из {{ formatCurrencyShort(totalBudget) }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { defineAsyncComponent } from 'vue'

// vue3-apexcharts больше не регистрируется глобально (main.ts) — тяжёлая
// библиотека тянется динамически только там, где реально есть <apexchart>.
const apexchart = defineAsyncComponent(() => import('vue3-apexcharts').then(m => m.default))

defineProps<{
  radialOptions: any
  totalUsagePct: number
  totalPaid: number
  totalBudget: number
  formatCurrencyShort: (v: number) => string
}>()
</script>
