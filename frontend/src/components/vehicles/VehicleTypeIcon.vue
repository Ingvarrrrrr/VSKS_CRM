<template>
  <img
    v-if="useImg"
    :src="imgSrc"
    :alt="type"
    class="vti vti--img"
    :style="{ width: size + 'px', height: 'auto' }"
  />
  <v-icon
    v-else
    :icon="mdiIcon"
    :size="size"
    class="vti vti--mdi"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  type?: string | null
  /** Base width in px. Height scales automatically. Default 60 */
  size?: number
}>(), {
  type: 'other',
  size: 60,
})

// Типы, у которых есть нарезанный PNG в /public/vehicle-icons/
const IMG_TYPES = new Set([
  'car_light', 'minivan', 'truck_van', 'truck_board', 'truck_metal',
  'bus', 'other',
])

// Для остальных — MDI иконка (Vuetify icon set)
const MDI_MAP: Record<string, string> = {
  truck_tank:  'mdi-tanker-truck',
  special:     'mdi-tractor-variant',
  quadbike:    'mdi-atv',
  snowmobile:  'mdi-snowmobile',
  boat:        'mdi-sail-boat',
  boat_motor:  'mdi-rowing',
  trailer:     'mdi-truck-trailer',
}

const useImg = computed(() => IMG_TYPES.has(props.type || 'other'))
const imgSrc = computed(() => `/vehicle-icons/${props.type || 'other'}.png`)
const mdiIcon = computed(() => MDI_MAP[props.type || ''] || 'mdi-car')
</script>

<style scoped>
.vti--img {
  display: block;
  object-fit: contain;
}
/* В тёмной теме PNG силуэты (чёрные) нечитаемы — инвертируем */
.v-theme--dark .vti--img {
  filter: invert(1) brightness(0.95);
}
</style>
