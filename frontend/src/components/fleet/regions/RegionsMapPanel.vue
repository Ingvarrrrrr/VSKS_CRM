<template>
  <div class="rv-panel rv-map-box">
    <div class="rv-panel__head">
      <span>Карта по месту нахождения</span>
      <small>размер кружка ∝ количеству ТС</small>
    </div>
    <div v-if="loading" class="rv-loading">
      <div class="rv-spinner"></div>
    </div>
    <RussiaMapSvg
      v-else-if="mapPins.length"
      :pins="mapPins"
      :search-active="searchActive"
      :matched-ids="matchedIds"
      @pin-click="$emit('pin-click', $event)"
    />
    <div v-else class="rv-empty">
      Нет координат для отображения — известные города/регионы не заполнены
      в «Месте нахождения» ни у одной машины
    </div>
  </div>
</template>

<script setup lang="ts">
import RussiaMapSvg from '@/components/fleet/RussiaMapSvg.vue'
import type { MapPin } from '@/components/fleet/russiaMapPins'

defineProps<{
  loading: boolean
  mapPins: MapPin[]
  searchActive: boolean
  matchedIds: (string | number)[]
}>()

defineEmits<{
  (e: 'pin-click', pin: MapPin): void
}>()
</script>

<style scoped></style>
