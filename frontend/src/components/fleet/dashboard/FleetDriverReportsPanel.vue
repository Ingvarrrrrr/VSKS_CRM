<template>
  <div class="fleet-panel">
    <h3 class="fleet-panel__title">
      Свежие отчёты водителей
      <small>с мобильного приложения</small>
    </h3>
    <ul class="fleet-feed" v-if="driverReports.length">
      <li v-for="(item, i) in driverReports" :key="i" class="fleet-feed__item">
        <div class="fleet-feed__ic" :class="`fleet-feed__ic--${item.ic}`">
          {{ icIcons[item.ic] }}
        </div>
        <div class="fleet-feed__body">
          <b>{{ item.plate }}</b> · {{ item.title }}
          <small>{{ item.author ? item.author + ' · ' : '' }}{{ fmtTs(item.timestamp) }}</small>
        </div>
      </li>
    </ul>
    <div class="fleet-empty fleet-empty--feed" v-else-if="!loadingReports">
      Отчётов пока нет. Скоро будет мобильное приложение для водителей.
    </div>
    <div class="fleet-empty" v-else>
      <v-progress-circular indeterminate color="#6aa6ff" size="24" />
    </div>
  </div>
</template>

<script setup lang="ts">
import type { ReportItem } from '@/composables/fleet/dashboard/useDriverReports'
import { fmtTs, IC_ICONS } from '@/composables/fleet/dashboard/fleetDashboardShared'

defineProps<{
  driverReports: ReportItem[]
  loadingReports: boolean
}>()

const icIcons = IC_ICONS
</script>

<style scoped></style>
