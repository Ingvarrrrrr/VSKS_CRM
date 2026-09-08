<!-- Hero-плашка карточки ТС: фото/силуэт, основные данные, статус-пилюля. -->
<template>
  <div class="vp-hero mb-4">
    <!-- Photo / silhouette / placeholder — приоритет: реальное фото → силуэт по кузову (bodyType, живьём до сохранения) → заглушка-камера.
         «Тип ТС» — характеристика из ПТС, на картинку не влияет (запрос владельца, 2026-09). -->
    <div
      class="vp-hero__photo"
      :class="{ 'vp-hero__photo--clickable': true }"
      role="button"
      :title="photoUrl ? 'Открыть фото' : 'Перейти к фотографиям'"
      @click="$emit('open-photos')"
    >
      <img
        v-if="photoUrl"
        :src="photoUrl"
        alt="Фото ТС"
        class="vp-hero__photo-img"
      />
      <VehicleTypeIcon
        v-else-if="hasSilhouette"
        :body-type="bodyType"
        :size="52"
      />
      <v-icon v-else icon="mdi-camera" size="36" class="vp-hero__photo-icon" />
    </div>

    <!-- Info block -->
    <div class="vp-hero__info">
      <div class="vp-hero__title">
        {{ [vehicle.brand, vehicle.model].filter(Boolean).join(' ') || 'ТС' }}
        <span class="vp-hero__year" v-if="vehicle.year_of_manufacture">· {{ vehicle.year_of_manufacture }}</span>
      </div>
      <div class="vp-hero__meta">
        <template v-if="vehicle.color">{{ vehicle.color }}</template>
        <template v-if="vehicle.owner_org_name"> · {{ vehicle.owner_org_name }}</template>
        <template v-if="vehicle.vin"> · VIN: <span class="vp-hero__mono">{{ vehicle.vin }}</span></template>
      </div>
      <div class="d-flex align-center gap-2 flex-wrap mt-2">
        <LicensePlate :model-value="vehicle.plate" size="lg" />
        <v-chip
          v-if="vehicle.type"
          size="small"
          variant="flat"
          class="vp-chip-glass"
          prepend-icon="mdi-car-info"
        >{{ TYPE_LABEL[vehicle.type] ?? vehicle.type }}</v-chip>
        <v-chip
          v-if="vehicle.insurance_until"
          size="small"
          variant="flat"
          :class="isInsuranceExpiringSoon ? 'vp-chip-warn' : 'vp-chip-glass'"
          prepend-icon="mdi-shield-check"
        >ОСАГО до {{ formatDate(vehicle.insurance_until) }}</v-chip>
        <v-chip
          v-if="vehicle.next_to_km && vehicle.current_odometer_km"
          size="small"
          variant="flat"
          :class="isToSoon ? 'vp-chip-warn' : 'vp-chip-glass'"
          prepend-icon="mdi-wrench"
        >ТО через {{ (vehicle.next_to_km - vehicle.current_odometer_km).toLocaleString('ru-RU') }} км</v-chip>
      </div>
    </div>

    <!-- Status pill (right) -->
    <div class="vp-hero__status">
      <div class="vp-status-pill" :class="`vp-status-pill--${vehicle.state ?? 'unknown'}`">
        <span class="vp-status-pill__dot"></span>
        {{ STATE_LABEL[vehicle.state ?? ''] ?? vehicle.state ?? 'Неизвестно' }}
      </div>
      <div class="vp-hero__status-sub">
        Состояние<br>
        <span v-if="vehicle.updated_at" class="vp-hero__status-date">{{ formatDate(vehicle.updated_at) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import VehicleTypeIcon from '@/components/vehicles/VehicleTypeIcon.vue'
import LicensePlate from '@/components/vehicles/LicensePlate.vue'
import { TYPE_LABEL, STATE_LABEL } from '@/composables/fleet/useVehicleFieldOptions'
import type { Vehicle } from '@/composables/fleet/vehicleDetailTypes'

defineProps<{
  vehicle: Vehicle
  photoUrl: string | null
  hasSilhouette: boolean
  bodyType: string | null
  isInsuranceExpiringSoon: boolean
  isToSoon: boolean
  formatDate: (d?: string | null) => string
}>()

defineEmits<{
  (e: 'open-photos'): void
}>()
</script>
