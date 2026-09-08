<template>
  <div class="rv-kpi-row">
    <KpiCard label="Всего ТС" :value="totalVehicles" variant="default" />
    <KpiCard label="Мест нахождения" :value="locationsCount" variant="info" />
    <KpiCard label="В работе" :value="totalWorking" variant="ok" />
    <KpiCard label="В ремонте" :value="totalRepair" variant="warn" />
    <KpiCard label="Сломано" :value="totalBroken" variant="alert" />
  </div>
</template>

<script setup lang="ts">
import KpiCard from '@/components/fleet/KpiCard.vue'

defineProps<{
  totalVehicles: number
  locationsCount: number
  totalWorking: number
  totalRepair: number
  totalBroken: number
}>()
</script>

<style scoped></style>
