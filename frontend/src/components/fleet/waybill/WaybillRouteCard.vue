<template>
  <!-- 4. Маршрут и задание -->
  <v-card class="wbf-card" flat border>
    <div class="wbf-card-header">
      <v-icon color="info" size="18">mdi-map-marker-path</v-icon>
      <span>Маршрут и задание</span>
    </div>
    <v-textarea
      v-model="form.purpose"
      label="Цель поездки *"
      variant="outlined"
      density="compact"
      rows="2"
      auto-grow
      :readonly="formReadonly"
      @change="$emit('dirty')"
    />
    <div class="wbf-section-label">Точки маршрута</div>
    <RouteStopsEditor
      v-model="form.route_stops"
      :readonly="formReadonly"
    />
    <div class="wbf-grid-3 wbf-mt">
      <v-text-field
        v-model.number="form.planned_mileage_km"
        label="Плановый пробег (км)"
        type="number"
        variant="outlined"
        density="compact"
        hide-details
        :readonly="formReadonly"
        @change="$emit('dirty')"
      />
      <v-text-field
        v-model="form.planned_duration"
        label="Время в пути (план)"
        variant="outlined"
        density="compact"
        hide-details
        :readonly="formReadonly"
        placeholder="напр. 11 ч."
        @change="$emit('dirty')"
      />
      <v-text-field
        v-model="form.work_hours_norm"
        label="Норма часов"
        variant="outlined"
        density="compact"
        hide-details
        :readonly="formReadonly"
        placeholder="напр. 11 / 12"
        @change="$emit('dirty')"
      />
    </div>
  </v-card>
</template>

<script setup lang="ts">
import RouteStopsEditor from '@/components/fleet/RouteStopsEditor.vue'
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
