<template>
  <div class="chart-card" style="height:100%;overflow:auto">
    <div class="chart-card-header">
      <v-icon icon="mdi-chart-box" size="18" color="#8B5CF6" class="mr-2" />
      <span class="chart-card-title">Структура закупок — Товары / Услуги</span>
    </div>
    <template v-if="pipelineByType.some((s: any) => s.total > 0)">
      <div class="pipeline-row">
        <div class="pipeline-label"><span class="pipeline-dot" style="background:#9CA3AF" />Бюджет</div>
        <div class="pipeline-bar-track" style="margin-bottom:3px">
          <div class="pipeline-bar-fill" style="width:100%; background:#F59E0B; opacity:0.35" />
        </div>
        <div class="pipeline-meta">{{ formatCurrencyShort(totalBudget) }}</div>
      </div>
      <div v-for="stage in pipelineByType" :key="stage.status" class="pipeline-row">
        <div class="pipeline-label">
          <span class="pipeline-dot" :style="{ background: stage.color }" />
          {{ stage.label }}
        </div>
        <div style="flex:1; min-width:0">
          <div class="pipeline-bar-track" style="margin-bottom:3px">
            <div class="pipeline-bar-fill" :style="{ width: Math.min(stage.goodsPct, 100) + '%', background: '#F59E0B' }" />
          </div>
          <div class="pipeline-bar-track">
            <div class="pipeline-bar-fill" :style="{ width: Math.min(stage.servicesPct, 100) + '%', background: '#3B82F6' }" />
          </div>
        </div>
        <div class="pipeline-meta" style="flex-direction:column; align-items:flex-end; gap:2px">
          <span style="color:#F59E0B; font-size:11px">{{ formatCurrencyShort(stage.goods) }}</span>
          <span style="color:#3B82F6; font-size:11px">{{ formatCurrencyShort(stage.services) }}</span>
        </div>
      </div>
      <div class="d-flex gap-4 mt-2" style="font-size:11px; color:var(--crm-text-muted)">
        <span><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#F59E0B;margin-right:4px"></span>Товары</span>
        <span><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#3B82F6;margin-right:4px"></span>Услуги / Работы</span>
      </div>
    </template>
    <div v-else class="chart-empty">
      <v-icon icon="mdi-chart-box" size="48" color="grey-lighten-2" />
      <div class="text-caption text-medium-emphasis mt-2">Нет данных о закупках</div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  pipelineByType: any[]
  totalBudget: number
  formatCurrencyShort: (v: number) => string
}>()
</script>
