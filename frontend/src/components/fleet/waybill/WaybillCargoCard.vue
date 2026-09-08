<template>
  <!-- 6. Груз и пассажиры -->
  <v-card class="wbf-card" flat border>
    <div class="wbf-card-header">
      <v-icon size="18">mdi-package-variant</v-icon>
      <span>Груз и пассажиры</span>
    </div>
    <div class="wbf-grid-2">
      <v-textarea
        v-model="form.cargo_description"
        label="Описание груза"
        variant="outlined"
        density="compact"
        rows="2"
        auto-grow
        hide-details
        :readonly="formReadonly"
        @change="$emit('dirty')"
      />
      <div class="wbf-grid-col">
        <v-text-field
          v-model.number="form.cargo_weight_t"
          label="Вес груза (т)"
          type="number"
          variant="outlined"
          density="compact"
          hide-details
          :readonly="formReadonly"
          @change="$emit('dirty')"
        />
        <v-text-field
          v-model.number="form.passengers_count"
          label="Кол-во пассажиров"
          type="number"
          variant="outlined"
          density="compact"
          hide-details
          :readonly="formReadonly"
          @change="$emit('dirty')"
        />
      </div>
    </div>
  </v-card>
</template>

<script setup lang="ts">
import type { WaybillForm } from '@/composables/fleet/waybill/waybillFormTypes'

defineProps<{
  form: WaybillForm
  formReadonly: boolean
}>()
defineEmits<{
  (e: 'dirty'): void
}>()
</script>

<style scoped></style>
