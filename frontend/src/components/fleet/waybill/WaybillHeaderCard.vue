<template>
  <!-- 1. Шапка ПЛ -->
  <v-card class="wbf-card" flat border>
    <div class="wbf-card-header">
      <v-icon color="primary" size="18">mdi-file-document-outline</v-icon>
      <span>Шапка путевого листа</span>
    </div>
    <div class="wbf-grid-3">
      <v-text-field
        :model-value="form.number"
        label="Номер п/л"
        readonly
        variant="outlined"
        density="compact"
        hide-details
        class="font-mono"
        :placeholder="isNew ? 'Будет присвоен' : ''"
      />
      <v-text-field
        v-model="form.date_start"
        label="Начало действия *"
        type="datetime-local"
        variant="outlined"
        density="compact"
        hide-details
        :readonly="formReadonly"
        @change="$emit('dirty')"
      />
      <v-text-field
        v-model="form.date_end"
        label="Конец действия *"
        type="datetime-local"
        variant="outlined"
        density="compact"
        hide-details
        :readonly="formReadonly"
        @change="$emit('dirty')"
      />
      <v-select
        v-model="form.waybill_type"
        label="Тип путевого"
        :items="waybillTypes"
        item-title="label"
        item-value="value"
        variant="outlined"
        density="compact"
        hide-details
        :readonly="formReadonly"
        @update:model-value="$emit('dirty')"
      />
    </div>
  </v-card>
</template>

<script setup lang="ts">
import { waybillTypes, type WaybillForm } from '@/composables/fleet/waybill/waybillFormTypes'

defineProps<{
  form: WaybillForm
  isNew: boolean
  formReadonly: boolean
}>()
defineEmits<{
  (e: 'dirty'): void
}>()
</script>

<style scoped></style>
