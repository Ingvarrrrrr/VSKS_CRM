<template>
  <!-- 2. Транспортное средство -->
  <v-card class="wbf-card" flat border>
    <div class="wbf-card-header">
      <v-icon color="success" size="18">mdi-car</v-icon>
      <span>Транспортное средство</span>
    </div>
    <v-autocomplete
      v-model="form.vehicle_id"
      label="Транспортное средство *"
      :items="vehicles"
      :item-title="(v: Vehicle) => `${v.plate} · ${v.brand_model} (${v.year})`"
      item-value="id"
      variant="outlined"
      density="compact"
      prepend-inner-icon="mdi-car"
      :readonly="formReadonly"
      clearable
      @update:model-value="$emit('select')"
    />
    <!-- Phase 30.2: "Не выбран ТС" chip if no vehicle selected on new form -->
    <v-chip
      v-if="isNew && !form.vehicle_id"
      color="warning"
      variant="tonal"
      size="small"
      prepend-icon="mdi-alert-outline"
      class="mt-2"
    >
      Не выбран ТС — сохранение недоступно
    </v-chip>
    <div v-if="selectedVehicle" class="wbf-veh-preview">
      <div class="wbf-veh-preview-icon">
        <v-icon color="primary">mdi-car-side</v-icon>
      </div>
      <div class="wbf-veh-info">
        <div class="wbf-veh-main">
          <LicensePlate :model-value="selectedVehicle.plate" size="sm" />
          <span class="wbf-veh-model">{{ selectedVehicle.brand_model }}, {{ selectedVehicle.year }}</span>
        </div>
        <div class="wbf-veh-sub">
          VIN: {{ selectedVehicle.vin || '—' }} · Пробег: {{ (selectedVehicle.current_mileage_km || 0).toLocaleString('ru-RU') }} км
        </div>
        <!-- Phase 30.2: fuel norms display -->
        <div v-if="selectedVehicle.fuel_norm_summer || selectedVehicle.fuel_norm_winter" class="wbf-veh-sub">
          Норма расхода: {{ selectedVehicle.fuel_norm_summer ?? '—' }} л/100км (лето) · {{ selectedVehicle.fuel_norm_winter ?? '—' }} л/100км (зима)
        </div>
      </div>
    </div>
  </v-card>
</template>

<script setup lang="ts">
import LicensePlate from '@/components/vehicles/LicensePlate.vue'
import type { Vehicle, WaybillForm } from '@/composables/fleet/waybill/waybillFormTypes'

defineProps<{
  form: WaybillForm
  vehicles: Vehicle[]
  formReadonly: boolean
  isNew: boolean
  selectedVehicle: Vehicle | undefined
}>()
defineEmits<{
  (e: 'select'): void
}>()
</script>

<style scoped></style>
