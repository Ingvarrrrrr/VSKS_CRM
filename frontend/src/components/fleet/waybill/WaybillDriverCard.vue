<template>
  <!-- 3. Водитель -->
  <v-card class="wbf-card" flat border>
    <div class="wbf-card-header">
      <v-icon color="purple" size="18">mdi-account</v-icon>
      <span>Водитель</span>
    </div>
    <v-autocomplete
      v-model="form.driver_user_id"
      label="Водитель *"
      :items="drivers"
      :item-title="(u: Driver) => u.full_name + (u.license_categories ? ` · кат. ${u.license_categories}` : '')"
      item-value="id"
      variant="outlined"
      density="compact"
      prepend-inner-icon="mdi-account"
      :readonly="formReadonly"
      clearable
      @update:model-value="$emit('dirty')"
    />
    <div v-if="selectedDriver" class="wbf-driver-preview">
      <GradientAvatar :full-name="selectedDriver.full_name" size="md" />
      <div class="wbf-driver-info">
        <div class="wbf-driver-name">{{ selectedDriver.full_name }}</div>
        <div class="wbf-driver-sub">
          Категории: {{ selectedDriver.license_categories || '—' }} ·
          Удостоверение: {{ selectedDriver.license_number || '—' }} ·
          Стаж: {{ selectedDriver.experience_years ?? '?' }} лет
        </div>
        <div v-if="selectedDriver.driver_tab_number" class="wbf-driver-sub">
          Таб. номер: {{ selectedDriver.driver_tab_number }}
        </div>
      </div>
    </div>
  </v-card>
</template>

<script setup lang="ts">
import GradientAvatar from '@/components/fleet/GradientAvatar.vue'
import type { Driver, WaybillForm } from '@/composables/fleet/waybill/waybillFormTypes'

defineProps<{
  form: WaybillForm
  drivers: Driver[]
  formReadonly: boolean
  selectedDriver: Driver | undefined
}>()
defineEmits<{
  (e: 'dirty'): void
}>()
</script>

<style scoped></style>
