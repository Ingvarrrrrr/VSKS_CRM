<template>
  <section>
    <v-card class="fleet-table-card" elevation="0">
      <v-card-text class="pa-0">
        <v-data-table
          v-resizable-columns="'vehicle-dashboard'"
          :items="vehicles"
          :headers="tableHeaders"
          :search="searchQuery"
          density="compact"
          :items-per-page="20"
          class="fleet-table clickable-rows"
          @click:row="(_: unknown, { item }: { item: AllVehicleRow }) => $emit('row-click', item.vehicle_id)"
        >
          <template #item.plate="{ item }">
            <LicensePlate :model-value="item.plate" />
          </template>
          <template #item.state="{ item }">
            <span class="fleet-state-chip" :class="`fleet-state-chip--${item.state}`">
              {{ stateLabels[item.state] || item.state }}
            </span>
          </template>
          <template #item.insurance_until="{ item }">
            <span :class="item.insurance_overdue ? 'text-red' : ''">
              {{ item.insurance_until || '—' }}
            </span>
          </template>
        </v-data-table>
      </v-card-text>
    </v-card>
  </section>
</template>

<script setup lang="ts">
import LicensePlate from '@/components/vehicles/LicensePlate.vue'
import type { AllVehicleRow } from '@/composables/fleet/dashboard/useFleetVehicles'

defineProps<{
  vehicles: AllVehicleRow[]
  tableHeaders: any[]
  searchQuery: string
  stateLabels: Record<string, string>
}>()

defineEmits<{
  (e: 'row-click', vehicleId: number): void
}>()
</script>

<style scoped></style>
