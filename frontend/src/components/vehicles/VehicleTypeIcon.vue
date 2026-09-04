<template>
  <span class="vti-box" :style="{ width: size + 'px', height: size + 'px' }">
    <img
      v-if="useImg"
      :src="imgSrc"
      :alt="type"
      class="vti vti--img"
    />
    <v-icon
      v-else
      :icon="mdiIcon"
      :size="size"
      class="vti vti--mdi"
    />
  </span>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useBodyTypeIconOverrides } from '@/composables/useBodyTypeIconOverrides'

const props = withDefaults(defineProps<{
  type?: string | null
  /**
   * Значение поля «Кузов» (Vehicle.body_type). Если задано и найдено в
   * справочнике bodyTypeIcon.ts — побеждает `type` (кузов описывает силуэт
   * точнее). Необязательный проп: старые вызовы без него ведут себя как раньше.
   */
  bodyType?: string | null
  /** Сторона квадратной области под иконку (px). Default 60 */
  size?: number
}>(), {
  type: 'other',
  bodyType: null,
  size: 60,
})

// Типы, у которых есть нарезанный PNG в /public/vehicle-icons/.
// Источник (2026-09): 23 силуэта, сгенерированных ИИ (легально чистый контент) —
// заменили прежние 9 PNG, нарезанные из iStock-изображения с водяным знаком
// (юридически сомнительный источник). Нарезка ИИ-сетки была со сдвигом по сетке
// 4×7 (часть плиток содержала обрывок соседней иконки и/или обрезанный по краю
// силуэт) — каждый файл здесь пересобран вручную: обрезки соседей убраны, а у
// грузовиков (pickup/truck_metal/truck_tank/bus), обрезанных по краю плитки,
// недостающий хвост силуэта склеен из соседней плитки по общей линии колёс.
//
// 2026-09: добавлены ещё 7 силуэтов (wagon/microbus/moped/sedan/hatchback/
// ambulance/fire_truck) из второго ИИ-набора — используются в основном через
// сопоставление по «Кузову» (см. bodyTypeIcon.ts), но доступны и по `type`.
const IMG_TYPES = new Set([
  'car_light', 'suv', 'pickup', 'minivan', 'truck_van', 'truck_tank',
  'truck_metal', 'bus', 'quadbike', 'snowmobile', 'trailer', 'other',
  'wagon', 'microbus', 'moped', 'sedan', 'hatchback', 'ambulance', 'fire_truck',
])

// Для типов без силуэта в ИИ-наборе — MDI-иконка (Vuetify icon set)
const MDI_MAP: Record<string, string> = {
  truck_board: 'mdi-truck-flatbed',    // бортовой (открытый) грузовик — точного силуэта в наборе нет
  special:     'mdi-tractor-variant',  // спецтехника — в наборе нет
  boat:        'mdi-sail-boat',        // лодка — в наборе нет
  boat_motor:  'mdi-rowing',           // лодка с мотором — в наборе нет
}

// Кузов (body_type) — приоритетнее типа, когда сопоставление найдено.
// resolveIcon учитывает переопределение организации (редактор значков кузова,
// см. OrgSettingsView.vue → VehicleBodyIconsDialog.vue), а при его отсутствии
// откатывается на хардкод-дефолт из bodyTypeIcon.ts — как и раньше.
const { resolveIcon, loadOverrides } = useBodyTypeIconOverrides()
onMounted(() => { loadOverrides() })
const bodyIcon = computed(() => resolveIcon(props.bodyType))

const useImg = computed(() => {
  if (bodyIcon.value) return bodyIcon.value.kind === 'img'
  return IMG_TYPES.has(props.type || 'other')
})
const imgSrc = computed(() => {
  if (bodyIcon.value?.kind === 'img') return `/vehicle-icons/${bodyIcon.value.file}.png`
  return `/vehicle-icons/${props.type || 'other'}.png`
})
const mdiIcon = computed(() => {
  if (bodyIcon.value?.kind === 'mdi') return bodyIcon.value.icon
  return MDI_MAP[props.type || ''] || 'mdi-car'
})
</script>

<style scoped>
/* Фиксированная квадратная область под иконку — у исходных PNG разное
   соотношение сторон (легковая машина широкая и низкая, грузовик — выше),
   поэтому центрируем силуэт внутри одинакового «слота», а не растягиваем
   по ширине с произвольной высотой (иначе иконки скачут по высоте в сетках). */
.vti-box {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.vti--img {
  display: block;
  max-width: 100%;
  max-height: 100%;
  width: auto;
  height: auto;
  object-fit: contain;
}
/* В тёмной теме PNG силуэты (чёрные) нечитаемы — инвертируем */
.v-theme--dark .vti--img {
  filter: invert(1) brightness(0.95);
}
</style>
