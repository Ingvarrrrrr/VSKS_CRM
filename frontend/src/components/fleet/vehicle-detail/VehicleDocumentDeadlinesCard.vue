<!-- Документы и сроки — ОСАГО/техосмотр/ПТС/СТС кратким статусом. -->
<template>
  <v-card class="vp-box mb-4">
    <v-card-title class="vp-box__title">
      <v-icon icon="mdi-file-document-outline" size="small" class="mr-2" />
      Документы и сроки
    </v-card-title>
    <v-card-text class="px-3 py-2">
      <div class="vp-docs">
        <!-- ОСАГО -->
        <div class="vp-doc-row">
          <span class="vp-doc-dot" :class="docDotClass(vehicle.insurance_until)"></span>
          <div class="vp-doc-info">
            <div class="vp-doc-name">ОСАГО</div>
            <div class="vp-doc-sub">
              <span v-if="vehicle.insurance_until">до {{ formatDate(vehicle.insurance_until) }}</span>
              <span v-else>не указано</span>
            </div>
          </div>
          <div class="vp-doc-right">
            <b v-if="vehicle.insurance_until">{{ daysLeft(vehicle.insurance_until) }}</b>
            <b v-else style="opacity:.45">—</b>
          </div>
        </div>
        <!-- Техосмотр -->
        <div class="vp-doc-row">
          <span class="vp-doc-dot" :class="docDotClass(vehicle.tech_inspection_until)"></span>
          <div class="vp-doc-info">
            <div class="vp-doc-name">Техосмотр</div>
            <div class="vp-doc-sub">
              <span v-if="vehicle.tech_inspection_until">до {{ formatDate(vehicle.tech_inspection_until) }}</span>
              <span v-else>отсутствует</span>
            </div>
          </div>
          <div class="vp-doc-right">
            <b v-if="vehicle.tech_inspection_until">{{ daysLeft(vehicle.tech_inspection_until) }}</b>
            <b v-else class="vp-doc-alert">нет</b>
          </div>
        </div>
        <!-- ПТС -->
        <div class="vp-doc-row">
          <span class="vp-doc-dot" :class="vehicle.pts_number ? 'vp-dot--ok' : 'vp-dot--alert'"></span>
          <div class="vp-doc-info">
            <div class="vp-doc-name">ПТС</div>
            <div class="vp-doc-sub">
              <span v-if="vehicle.pts_number" class="vp-mono-sm">{{ vehicle.pts_number }}</span>
              <span v-else>не указан</span>
            </div>
          </div>
          <div class="vp-doc-right"><b v-if="vehicle.pts_number">OK</b><b v-else class="vp-doc-alert">—</b></div>
        </div>
        <!-- СТС -->
        <div class="vp-doc-row">
          <span class="vp-doc-dot" :class="vehicle.sts_number ? 'vp-dot--ok' : 'vp-dot--alert'"></span>
          <div class="vp-doc-info">
            <div class="vp-doc-name">СТС</div>
            <div class="vp-doc-sub">
              <span v-if="vehicle.sts_number" class="vp-mono-sm">{{ vehicle.sts_number }}</span>
              <span v-else>не указан</span>
            </div>
          </div>
          <div class="vp-doc-right"><b v-if="vehicle.sts_number">OK</b><b v-else class="vp-doc-alert">—</b></div>
        </div>
      </div>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
import type { Vehicle } from '@/composables/fleet/vehicleDetailTypes'

defineProps<{
  vehicle: Vehicle
  formatDate: (d?: string | null) => string
  daysLeft: (d?: string | null) => string
  docDotClass: (d?: string | null) => string
}>()
</script>
