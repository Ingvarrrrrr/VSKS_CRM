<!-- Документы для редактирования (свёрнуто) — ПТС/СТС/страховка/техосмотр/расход. -->
<template>
  <v-card class="vp-box mb-4">
    <v-card-title class="vp-box__title">
      <v-icon icon="mdi-pencil-outline" size="small" class="mr-2" />
      Редактировать документы
    </v-card-title>
    <v-card-text>
      <v-row dense>
        <v-col v-if="isFieldVisible('pts_number')" cols="6">
          <FieldLabel label="ПТС" field-key="pts_number" :vehicle-id="vehicleId" />
          <v-text-field v-model="form.pts_number" variant="outlined" density="compact" hide-details />
        </v-col>
        <v-col v-if="isFieldVisible('pts_kind')" cols="6">
          <FieldLabel label="Вид ПТС" field-key="pts_kind" :vehicle-id="vehicleId" />
          <v-select v-model="form.pts_kind" :items="ptsKindOptions" item-title="title" item-value="value" variant="outlined" density="compact" hide-details clearable />
        </v-col>
        <v-col v-if="isFieldVisible('sts_number')" cols="6">
          <FieldLabel label="СТС" field-key="sts_number" :vehicle-id="vehicleId" />
          <v-text-field v-model="form.sts_number" variant="outlined" density="compact" hide-details />
        </v-col>
        <v-col v-if="isFieldVisible('sts_issued_at')" cols="6">
          <FieldLabel label="СТС — дата выдачи" field-key="sts_issued_at" :vehicle-id="vehicleId" />
          <v-text-field v-model="form.sts_issued_at" type="date" variant="outlined" density="compact" hide-details />
        </v-col>
        <v-col v-if="isFieldVisible('insurance_company')" cols="6">
          <FieldLabel label="Страховая компания" field-key="insurance_company" :vehicle-id="vehicleId" />
          <v-text-field v-model="form.insurance_company" variant="outlined" density="compact" hide-details />
        </v-col>
        <v-col v-if="isFieldVisible('insurance_policy_number')" cols="6">
          <FieldLabel label="Номер страхового договора" field-key="insurance_policy_number" :vehicle-id="vehicleId" />
          <v-text-field v-model="form.insurance_policy_number" variant="outlined" density="compact" hide-details />
        </v-col>
        <v-col v-if="isFieldVisible('insurance_until')" cols="6">
          <FieldLabel label="ОСАГО до" field-key="insurance_until" :vehicle-id="vehicleId" />
          <v-text-field v-model="form.insurance_until" type="date" variant="outlined" density="compact" hide-details />
        </v-col>
        <v-col v-if="isFieldVisible('tech_inspection_status')" cols="6">
          <FieldLabel label="Обязательный техосмотр" field-key="tech_inspection_status" :vehicle-id="vehicleId" />
          <v-select v-model="form.tech_inspection_status" :items="techInspectionStatusOptions" variant="outlined" density="compact" hide-details clearable />
        </v-col>
        <v-col v-if="isFieldVisible('tech_inspection_last_date')" cols="6">
          <FieldLabel label="Дата последнего техосмотра" field-key="tech_inspection_last_date" :vehicle-id="vehicleId" />
          <v-text-field v-model="form.tech_inspection_last_date" type="date" variant="outlined" density="compact" hide-details />
        </v-col>
        <v-col v-if="isFieldVisible('tech_inspection_until')" cols="6">
          <FieldLabel label="Техосмотр до" field-key="tech_inspection_until" :vehicle-id="vehicleId" />
          <v-text-field v-model="form.tech_inspection_until" type="date" variant="outlined" density="compact" hide-details />
        </v-col>
        <v-col v-if="isFieldVisible('fuel_type')" cols="6">
          <FieldLabel label="Тип топлива" field-key="fuel_type" :vehicle-id="vehicleId" />
          <v-select v-model="form.fuel_type" :items="fuelTypeSelectItems" item-title="title" item-value="value" variant="outlined" density="compact" hide-details clearable />
        </v-col>
        <v-col v-if="isFieldVisible('current_odometer_km')" cols="6">
          <div class="text-caption text-medium-emphasis mb-1 d-flex align-center flex-wrap">
            <span>Текущий пробег, км</span>
            <FieldHint field-key="current_odometer_km" />
            <v-chip size="x-small" variant="tonal" color="grey" class="ml-2">не редактируется</v-chip>
            <v-btn
              size="x-small"
              variant="text"
              color="primary"
              class="ml-1 px-1"
              prepend-icon="mdi-arrow-right-circle-outline"
              @click="$emit('open-odometer')"
            >Внести пробег</v-btn>
          </div>
          <v-text-field :model-value="currentOdometerKm ?? '—'" variant="outlined" density="compact" hide-details readonly class="text-medium-emphasis" />
        </v-col>
        <v-col v-if="isFieldVisible('last_to_mileage_km')" cols="6">
          <FieldLabel label="Последнее ТО, км" field-key="last_to_mileage_km" :vehicle-id="vehicleId" />
          <v-text-field v-model.number="form.last_to_mileage_km" type="number" variant="outlined" density="compact" hide-details />
        </v-col>
        <v-col v-if="isFieldVisible('last_to_date')" cols="6">
          <FieldLabel label="Дата последнего ТО" field-key="last_to_date" :vehicle-id="vehicleId" />
          <v-text-field v-model="form.last_to_date" type="date" variant="outlined" density="compact" hide-details />
        </v-col>
        <v-col v-if="isFieldVisible('next_to_km')" cols="6">
          <FieldLabel label="Следующее ТО, км" field-key="next_to_km" :vehicle-id="vehicleId" />
          <v-text-field v-model.number="form.next_to_km" type="number" variant="outlined" density="compact" hide-details />
        </v-col>
        <v-col v-if="isFieldVisible('engine_power_hp')" cols="6">
          <FieldLabel label="Мощность, л.с." field-key="engine_power_hp" :vehicle-id="vehicleId" />
          <v-text-field v-model.number="form.engine_power_hp" type="number" variant="outlined" density="compact" hide-details />
        </v-col>
        <v-col v-if="isFieldVisible('engine_volume_l')" cols="6">
          <FieldLabel label="Объём двигателя, л" field-key="engine_volume_l" :vehicle-id="vehicleId" />
          <v-text-field v-model.number="form.engine_volume_l" type="number" step="0.1" variant="outlined" density="compact" hide-details />
        </v-col>
        <v-col v-if="isFieldVisible('fuel_norm_summer')" cols="6">
          <FieldLabel label="Норма расхода (лето)" field-key="fuel_norm_summer" :vehicle-id="vehicleId" />
          <v-text-field v-model.number="form.fuel_norm_summer" type="number" step="0.1" suffix="л/100км" variant="outlined" density="compact" hide-details />
        </v-col>
        <v-col v-if="isFieldVisible('fuel_norm_winter')" cols="6">
          <FieldLabel label="Норма расхода (зима)" field-key="fuel_norm_winter" :vehicle-id="vehicleId" />
          <v-text-field v-model.number="form.fuel_norm_winter" type="number" step="0.1" suffix="л/100км" variant="outlined" density="compact" hide-details />
        </v-col>
      </v-row>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
import FieldLabel from './FieldLabel.vue'
import FieldHint from './FieldHint.vue'
import type { VehicleForm } from '@/composables/fleet/vehicleDetailTypes'

defineProps<{
  form: VehicleForm
  vehicleId: number
  isFieldVisible: (key: string) => boolean
  ptsKindOptions: { value: string; title: string }[]
  techInspectionStatusOptions: string[]
  fuelTypeSelectItems: { value: string; title: string }[]
  currentOdometerKm: number | null
}>()

defineEmits<{
  (e: 'open-odometer'): void
}>()
</script>
