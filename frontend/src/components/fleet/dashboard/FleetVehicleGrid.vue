<template>
  <section class="fleet-grid">
    <VehicleCard
      v-for="v in vehicles"
      :key="v.vehicle_id"
      :vehicle="toCardData(v)"
      @detail="$emit('detail', v.vehicle_id)"
      @action="$emit('action', $event)"
    />
    <div v-if="loading" class="fleet-loading-overlay">
      <v-progress-circular indeterminate color="#6aa6ff" size="36" />
    </div>
    <div v-if="!loading && vehicles.length === 0" class="fleet-empty fleet-empty--full">
      Нет транспортных средств
    </div>
  </section>
</template>

<script setup lang="ts">
import VehicleCard from '@/components/vehicles/VehicleCard.vue'
import type { AllVehicleRow, VehicleCardData } from '@/composables/fleet/dashboard/useFleetVehicles'

defineProps<{
  vehicles: AllVehicleRow[]
  loading: boolean
  toCardData: (v: AllVehicleRow) => VehicleCardData
}>()

defineEmits<{
  (e: 'detail', vehicleId: number): void
  // vehicle: 'any' — VehicleCard.vue re-emits через СВОЙ локальный интерфейс
  // VehicleCardData (id опционален там), отличный от нашего строгого типа
  // (id обязателен); строгая типизация тут дала бы ложный конфликт типов.
  (e: 'action', payload: { type: string; vehicle: any }): void
}>()
</script>

<style scoped></style>
