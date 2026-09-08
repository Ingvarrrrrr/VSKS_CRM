<!-- Пропуска (Autoblock §2) — 5 пар «номер + дата истечения». -->
<template>
  <v-card v-if="isGroupVisible('passes')" class="vp-box mb-4">
    <v-card-title class="vp-box__title">
      <v-icon icon="mdi-badge-account-horizontal-outline" size="small" class="mr-2" />
      Пропуска
      <BlockHint block-key="vehicle_passes" />
    </v-card-title>
    <v-card-text>
      <v-row dense>
        <template v-for="p in passFieldDefs" :key="p.key">
          <v-col v-if="isFieldVisible(p.key)" cols="12" sm="6">
            <FieldLabel :label="p.label" :field-key="p.key" :vehicle-id="vehicleId" />
            <v-select v-model="(form as any)[p.key]" :items="passStatusOptions" variant="outlined" density="compact" hide-details clearable />
          </v-col>
          <v-col v-if="isFieldVisible(p.untilKey)" cols="12" sm="6">
            <FieldLabel label="Действует до" :field-key="p.untilKey" :vehicle-id="vehicleId" />
            <v-text-field v-model="(form as any)[p.untilKey]" type="date" variant="outlined" density="compact" hide-details />
          </v-col>
        </template>
      </v-row>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
import FieldLabel from './FieldLabel.vue'
import BlockHint from './BlockHint.vue'
import type { VehicleForm } from '@/composables/fleet/vehicleDetailTypes'

defineProps<{
  form: VehicleForm
  vehicleId: number
  isFieldVisible: (key: string) => boolean
  isGroupVisible: (key: string) => boolean
  passFieldDefs: { key: string; untilKey: string; label: string }[]
  passStatusOptions: string[]
}>()
</script>
