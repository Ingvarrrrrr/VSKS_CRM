<template>
  <!-- 5. Спидометр и топливо -->
  <v-card class="wbf-card" flat border>
    <div class="wbf-card-header">
      <v-icon color="warning" size="18">mdi-speedometer</v-icon>
      <span>Спидометр и топливо</span>
    </div>
    <div class="wbf-section-label">Показания спидометра</div>
    <div class="wbf-grid-2">
      <OdometerField
        v-model="form.odometer_start"
        label="При выезде"
        :readonly="formReadonly"
      />
      <OdometerField
        v-model="form.odometer_finish"
        label="При возврате"
        :previous-value="form.odometer_start"
        :readonly="form.status === 'created' || form.status === 'tech_inspect' || form.status === 'med_inspect'"
      />
    </div>
    <div v-if="actualMileage" class="wbf-mileage-computed">
      Пробег за смену:
      <span class="wbf-mono">{{ actualMileage.toLocaleString('ru-RU') }} км</span>
    </div>
    <div class="wbf-section-label wbf-mt">Топливо</div>
    <FuelReadout
      v-model:fuel-start="form.fuel_remaining_start"
      v-model:fuel-issued="form.fuel_issued_l"
      v-model:fuel-end="form.fuel_remaining_finish"
      :mileage-km="actualMileage"
      :norm-per-100km="selectedVehicle?.fuel_norm_summer"
      :readonly="formReadonly"
    />
  </v-card>
</template>

<script setup lang="ts">
import OdometerField from '@/components/fleet/OdometerField.vue'
import FuelReadout from '@/components/fleet/FuelReadout.vue'
import type { Vehicle, WaybillForm } from '@/composables/fleet/waybill/waybillFormTypes'

defineProps<{
  form: WaybillForm
  formReadonly: boolean
  selectedVehicle: Vehicle | undefined
  actualMileage: number | undefined
}>()
</script>

<style scoped></style>
