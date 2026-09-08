<!-- Ответственный за ТС. -->
<template>
  <v-card class="vp-box mb-4">
    <v-card-title class="vp-box__title">
      <v-icon icon="mdi-account-hard-hat" size="small" class="mr-2" />
      Ответственный за ТС
    </v-card-title>
    <v-card-text>
      <div class="vp-resp-card" v-if="vehicle.assigned_org_name || vehicle.owner_org_name">
        <div class="vp-resp-avatar">
          {{ respInitials }}
        </div>
        <div>
          <div class="vp-resp-name">{{ vehicle.assigned_org_name || vehicle.owner_org_name }}</div>
          <div class="vp-resp-role">
            <span v-if="vehicle.assigned_org_name">Эксплуатант</span>
            <span v-else>Владелец</span>
          </div>
        </div>
      </div>
      <div v-else class="text-medium-emphasis text-body-2">не назначен</div>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
import type { Vehicle } from '@/composables/fleet/vehicleDetailTypes'

defineProps<{
  vehicle: Vehicle
  respInitials: string
}>()
</script>
