<!-- История пробега (sparkline), Slice 2. -->
<template>
  <v-card class="vp-box mb-4">
    <v-card-title class="vp-box__title">
      <v-icon icon="mdi-chart-line" size="small" class="mr-2" />
      История пробега
      <span class="vp-box-sub ml-auto">последние {{ sparkPoints.length }} записей</span>
    </v-card-title>
    <v-card-text>
      <div v-if="sparkPoints.length < 2" class="text-medium-emphasis text-body-2 py-2 text-center">
        Недостаточно данных для графика (нужно минимум 2 записи)
      </div>
      <template v-else>
        <div class="vp-spark-wrap">
          <svg class="vp-spark" viewBox="0 0 600 96" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <linearGradient id="vp-spark-grad" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stop-color="#6aa6ff" stop-opacity="0.5"/>
                <stop offset="100%" stop-color="#6aa6ff" stop-opacity="0"/>
              </linearGradient>
            </defs>
            <path :d="sparkAreaPath" fill="url(#vp-spark-grad)" />
            <polyline :points="sparkPolyline" stroke="#6aa6ff" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round" />
            <circle v-if="sparkLastPoint" :cx="sparkLastPoint.x" :cy="sparkLastPoint.y" r="4" fill="#6aa6ff" stroke="white" stroke-width="2" />
          </svg>
          <div class="vp-spark-axis">
            <span v-for="(lbl, i) in sparkAxisLabels" :key="i">{{ lbl }}</span>
          </div>
        </div>
        <div v-if="sparkStats" class="vp-spark-footer">
          <div>
            <span class="vp-spark-big">+{{ sparkStats.totalKm.toLocaleString('ru-RU') }} км</span>
            <span class="vp-spark-sub">за период</span>
          </div>
          <div>
            <span class="vp-spark-med">~{{ sparkStats.avgPerMonth.toLocaleString('ru-RU') }} км/мес</span>
            <span class="vp-spark-sub">средний</span>
          </div>
          <div>
            <span class="vp-spark-med vp-spark-ok">+{{ sparkStats.lastDelta.toLocaleString('ru-RU') }} км</span>
            <span class="vp-spark-sub">последний интервал</span>
          </div>
        </div>
      </template>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
import type { OdometerRow } from '@/composables/fleet/vehicleDetailTypes'

defineProps<{
  sparkPoints: OdometerRow[]
  sparkPolyline: string
  sparkAreaPath: string
  sparkLastPoint: { x: number; y: number } | null
  sparkAxisLabels: string[]
  sparkStats: { totalKm: number; avgPerMonth: number; lastDelta: number } | null
}>()
</script>
