<template>
  <section>
    <div v-for="region in regionGroups" :key="region.name" class="fleet-region-group">
      <div class="fleet-region-group__header">
        <span class="fleet-region-group__name">{{ region.name }}</span>
        <span class="fleet-region-group__count">{{ region.vehicles.length }} ТС</span>
      </div>
      <div class="fleet-grid fleet-grid--compact">
        <VehicleCard
          v-for="v in region.vehicles"
          :key="v.vehicle_id"
          :vehicle="toCardData(v)"
          @detail="$emit('detail', v.vehicle_id)"
          @action="$emit('action', $event)"
        />
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import VehicleCard from '@/components/vehicles/VehicleCard.vue'
import type { AllVehicleRow, VehicleCardData } from '@/composables/fleet/dashboard/useFleetVehicles'

defineProps<{
  regionGroups: { name: string; vehicles: AllVehicleRow[] }[]
  toCardData: (v: AllVehicleRow) => VehicleCardData
}>()

defineEmits<{
  (e: 'detail', vehicleId: number): void
  // vehicle: 'any' — см. пояснение в FleetVehicleGrid.vue (VehicleCard.vue
  // re-эмитит через свой локальный тип с опциональным id).
  (e: 'action', payload: { type: string; vehicle: any }): void
}>()
</script>

<style scoped></style>
