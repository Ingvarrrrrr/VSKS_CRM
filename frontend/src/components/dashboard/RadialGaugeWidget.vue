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
defineProps<{
  radialOptions: any
  totalUsagePct: number
  totalPaid: number
  totalBudget: number
  formatCurrencyShort: (v: number) => string
}>()
</script>
