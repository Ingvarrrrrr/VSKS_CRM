<template>
  <div class="rv-panel rv-top-list">
    <div class="rv-panel__head">
      <span>Топ мест нахождения</span>
      <small>по количеству ТС</small>
    </div>
    <div v-if="loading" class="rv-loading">
      <div class="rv-spinner"></div>
    </div>
    <template v-else>
      <div
        v-for="(loc, idx) in topLocations"
        :key="loc.region"
        class="rv-reg-row"
        @click="$emit('select', loc.region)"
      >
        <div class="rv-reg-row__ic" :style="{ background: locationBadgeBg(idx), color: locationBadgeColor(idx) }">
          {{ locationAbbr(loc.region) }}
        </div>
        <div class="rv-reg-row__info">
          <div class="rv-reg-row__nm" :title="loc.region">{{ loc.region }}</div>
          <div v-if="locationSubtitle(loc.region)" class="rv-reg-row__ds">{{ locationSubtitle(loc.region) }}</div>
        </div>
        <div class="rv-reg-row__cnt">
          {{ loc.count }}
          <small>ТС</small>
        </div>
      </div>
      <div v-if="!topLocations.length" class="rv-empty">Нет данных</div>
    </template>
  </div>
</template>

<script setup lang="ts">
import type { RegionItem } from '@/composables/fleet/regions/useRegionsData'
import { useLocationDisplay } from '@/composables/fleet/regions/useLocationDisplay'

defineProps<{
  loading: boolean
  topLocations: RegionItem[]
}>()

defineEmits<{
  (e: 'select', region: string): void
}>()

const { locationAbbr, locationBadgeBg, locationBadgeColor, locationSubtitle } = useLocationDisplay()
</script>

<style scoped></style>
