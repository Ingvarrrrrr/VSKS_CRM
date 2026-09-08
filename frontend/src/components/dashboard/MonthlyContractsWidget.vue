<template>
  <div class="chart-card" style="height:100%;overflow:auto">
    <div class="chart-card-header">
      <v-icon icon="mdi-calendar-refresh" size="18" color="#6366F1" class="mr-2" />
      <span class="chart-card-title">Ежемесячные договоры — остаток к заказу</span>
      <span v-if="monthlyContractsRemaining.length > 0" class="ml-auto font-weight-bold" style="color:#6366F1">{{ formatCurrencyShort(totalMonthlyRemaining) }}</span>
    </div>
    <template v-if="monthlyContractsRemaining.length > 0">
      <div
        v-for="c in monthlyContractsRemaining" :key="c.id"
        class="pipeline-row"
      >
        <div class="pipeline-label">
          <span class="pipeline-dot" style="background:#6366F1" />
          {{ c.name }}
        </div>
        <div class="pipeline-bar-track">
          <div class="pipeline-bar-fill" :style="{ width: c.elapsedPct + '%', background: '#6366F1' }" />
        </div>
        <div class="pipeline-meta">
          <span class="pipeline-amount">{{ formatCurrencyShort(c.remaining) }} ост.</span>
          <span class="pipeline-pct" :style="{ color: chartMuted }">{{ c.elapsedPct }}%</span>
        </div>
      </div>
    </template>
    <div v-else class="chart-empty">
      <v-icon icon="mdi-calendar-refresh" size="48" color="grey-lighten-2" />
      <div class="text-caption text-medium-emphasis mt-2">Нет ежемесячных договоров</div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  monthlyContractsRemaining: any[]
  totalMonthlyRemaining: number
  chartMuted: string
  formatCurrencyShort: (v: number) => string
}>()
</script>
