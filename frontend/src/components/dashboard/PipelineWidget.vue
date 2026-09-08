<template>
  <div class="chart-card" style="height:100%;overflow:auto">
    <div class="chart-card-header">
      <v-icon icon="mdi-stairs-up" size="18" color="#F59E0B" class="mr-2" />
      <span class="chart-card-title">Закупки по этапам</span>
      <v-chip
        size="x-small"
        :color="selectedSubsidyIds.length === 0 ? 'grey' : 'primary'"
        variant="tonal"
        class="ml-2"
        :title="selectedSubsidyIds.length === 0 ? 'Показаны закупки по всем субсидиям' : 'Применён фильтр субсидий'"
      >
        {{ selectedSubsidyIds.length === 0
          ? 'Все субсидии'
          : selectedSubsidyIds.length === 1
            ? (allSubsidies.find((s: any) => s.id === selectedSubsidyIds[0])?.name || '1 субсидия')
            : `${selectedSubsidyIds.length} субсидий` }}
      </v-chip>
      <span class="text-caption text-medium-emphasis ml-2">(нажмите для детализации)</span>
    </div>
    <div v-if="totalBudget > 0 || pipelineStages.some((s: any) => s.amount > 0)" class="pipeline-wrap">
      <div class="pipeline-row">
        <div class="pipeline-label">
          <span class="pipeline-dot" style="background:#9CA3AF" />
          Бюджет
        </div>
        <div class="pipeline-bar-track">
          <div class="pipeline-bar-fill" style="width:100%; background:#9CA3AF; opacity:0.35" />
        </div>
        <div class="pipeline-meta">
          <span class="pipeline-amount">{{ formatCurrencyShort(totalBudget) }}</span>
          <span class="pipeline-pct" :style="{ color: chartMuted }">100%</span>
        </div>
      </div>
      <template v-for="stage in pipelineStages" :key="stage.status">
        <div
          class="pipeline-row"
          @click="$emit('stage-click', stage.status)"
        >
          <div class="pipeline-label">
            <span class="pipeline-dot" :style="{ background: stage.color }" />
            {{ stage.label }}
          </div>
          <div class="pipeline-bar-track">
            <div
              class="pipeline-bar-fill"
              :style="{ width: Math.min(stage.pct, 100) + '%', background: stage.color }"
            />
          </div>
          <div class="pipeline-meta">
            <span class="pipeline-amount">{{ formatCurrencyShort(stage.amount) }}</span>
            <span class="pipeline-pct" :style="{ color: stage.pct > 100 ? '#EF4444' : chartMuted }">
              {{ stage.pct }}%
            </span>
          </div>
        </div>
        <!-- Между «Поставлено» и «Оплачено» — красная метрика «Поставлено, не оплачено» -->
        <div
          v-if="stage.status === 'delivered' && deliveredNotPaid.amount > 0"
          class="pipeline-row"
          style="background: rgba(239,68,68,0.06); border-radius:6px; margin: 4px 0"
          @click="$emit('delivered-not-paid-click')"
        >
          <div class="pipeline-label">
            <span class="pipeline-dot" style="background:#EF4444" />
            Поставлено, не оплачено
          </div>
          <div class="pipeline-bar-track">
            <div class="pipeline-bar-fill" :style="{ width: Math.min(deliveredNotPaid.pct, 100) + '%', background: '#EF4444' }" />
          </div>
          <div class="pipeline-meta">
            <span class="pipeline-amount" style="color:#EF4444">{{ formatCurrencyShort(deliveredNotPaid.amount) }}</span>
            <span class="pipeline-pct" :style="{ color: chartMuted }">{{ deliveredNotPaid.pct }}%</span>
          </div>
        </div>
      </template>
      <div v-if="wishesAmountForPie > 0" class="pipeline-wishes-hint">
        <v-icon icon="mdi-star-circle-outline" size="14" color="warning" class="mr-1" />
        Желания: {{ formatCurrencyShort(wishesAmountForPie) }}
        ({{ Math.round(wishesAmountForPie / (totalBudget || 1) * 100) }}% бюджета)
      </div>
    </div>
    <div v-else class="chart-empty">
      <v-icon icon="mdi-cart-outline" size="48" color="grey-lighten-2" />
      <div class="text-caption text-medium-emphasis mt-2">Нет данных о закупках</div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  selectedSubsidyIds: number[]
  allSubsidies: any[]
  totalBudget: number
  pipelineStages: any[]
  deliveredNotPaid: { amount: number; pct: number }
  wishesAmountForPie: number
  chartMuted: string
  formatCurrencyShort: (v: number) => string
}>()

defineEmits<{
  (e: 'stage-click', status: string): void
  (e: 'delivered-not-paid-click'): void
}>()
</script>
