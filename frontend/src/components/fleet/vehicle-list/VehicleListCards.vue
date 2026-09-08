<template>
  <div>
    <v-progress-linear v-if="loading" indeterminate color="primary" class="mb-3" />
    <div v-if="!loading && (!items || items.length === 0)" class="text-center py-10">
      <v-icon icon="mdi-car-off" size="48" color="grey-lighten-1" class="mb-3" />
      <div class="text-medium-emphasis">ТС не найдены</div>
    </div>
    <v-row dense>
      <v-col
        v-for="v in (Array.isArray(items) ? items : [])"
        :key="v.id"
        cols="12" sm="6" lg="4"
      >
        <v-card variant="outlined" class="h-100 d-flex flex-column" hover
          @click="router.push(`/property/vehicles/${v.id}`)">
          <v-card-item class="pb-1">
            <v-card-title class="text-body-2 font-weight-bold">
              <LicensePlate :model-value="v.plate" :readonly="true" size="sm" />
            </v-card-title>
            <template #append>
              <v-chip size="x-small" variant="tonal" :color="stateColor(v.state)">
                {{ stateLabel(v.state) }}
              </v-chip>
            </template>
          </v-card-item>
          <v-card-text class="py-1 flex-grow-1">
            <div class="text-body-2 font-weight-medium mb-1">
              {{ [v.brand, v.model].filter(Boolean).join(' ') || '—' }}
              <span v-if="v.color" class="text-caption text-medium-emphasis"> · {{ v.color }}</span>
            </div>
            <div class="d-flex flex-wrap gap-x-3 gap-y-1 text-caption text-medium-emphasis">
              <span v-if="v.type">
                <v-chip size="x-small" variant="tonal" :color="typeColor(v.type)">{{ typeLabel(v.type) }}</v-chip>
              </span>
              <span v-if="v.owner_org_name">Владелец: <strong>{{ v.owner_org_name }}</strong></span>
              <span v-if="v.assigned_org_name || v.assigned_text">
                Экспл.: <strong>{{ v.assigned_org_name || v.assigned_text }}</strong>
              </span>
            </div>
            <div class="d-flex flex-wrap gap-x-3 gap-y-1 text-caption mt-1">
              <span v-if="v.insurance_until">
                ОСАГО:
                <span :class="insuranceClass(v)">{{ formatDate(v.insurance_until) }}</span>
                <v-icon v-if="isInsuranceExpiring(v)" icon="mdi-alert-circle" size="x-small" color="warning" class="ml-1" />
              </span>
              <span v-if="v.current_odometer_km != null">Пробег: <strong>{{ v.current_odometer_km.toLocaleString('ru-RU') }} км</strong></span>
              <span v-if="v.fuel_type" class="text-caption">{{ fuelTypeLabel(v.fuel_type) }}</span>
            </div>
          </v-card-text>
          <v-divider />
          <v-card-actions class="py-1" @click.stop>
            <v-spacer />
            <v-tooltip text="Открыть карточку" location="top">
              <template #activator="{ props: tip }">
                <v-btn v-bind="tip" icon="mdi-open-in-new" size="x-small" variant="text" color="primary"
                  :to="`/property/vehicles/${v.id}`" @click.stop />
              </template>
            </v-tooltip>
          </v-card-actions>
        </v-card>
      </v-col>
    </v-row>
    <!-- Server-side pagination for cards: reuse same page/itemsPerPage -->
    <div class="d-flex justify-center align-center pa-3 gap-2 mt-2">
      <v-btn icon="mdi-chevron-left" variant="text" size="small" :disabled="page <= 1" @click="emit('update:page', page - 1)" />
      <span class="text-body-2">Стр. {{ page }} из {{ Math.max(1, Math.ceil(total / itemsPerPage)) }}</span>
      <v-btn icon="mdi-chevron-right" variant="text" size="small" :disabled="page >= Math.ceil(total / itemsPerPage)" @click="emit('update:page', page + 1)" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import LicensePlate from '@/components/vehicles/LicensePlate.vue'
import type { VehicleListItem } from '@/composables/fleet/vehicle-list/vehicleListTypes'
import {
  typeLabel, typeColor, stateLabel, stateColor, fuelTypeLabel,
  formatDate, isInsuranceExpiring, insuranceClass,
} from '@/composables/fleet/vehicle-list/vehicleListLookups'

defineProps<{
  items: VehicleListItem[]
  loading: boolean
  total: number
  page: number
  itemsPerPage: number
}>()

const emit = defineEmits<{
  (e: 'update:page', value: number): void
}>()

const router = useRouter()
</script>

<style scoped></style>
