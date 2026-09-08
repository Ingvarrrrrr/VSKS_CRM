<!--
  То же самое, что FieldHint, но для целых НЕ-полевых блоков карточки
  (история передач/изменений, штрафы, путевые листы, ремонты, заправки,
  пропуска) — подсказка берётся из RELATED_BLOCKS
  (backend/app/services/vehicle_fields.get_related_blocks(), §4) через
  useVehicleFields.getRelatedBlockHint(blockKey).
-->
<template>
  <v-tooltip v-if="hint" :text="hint" location="top" max-width="340">
    <template #activator="{ props: activatorProps }">
      <v-icon
        v-bind="activatorProps"
        icon="mdi-help-circle-outline"
        size="16"
        color="primary"
        class="ml-1 field-hint-icon"
      />
    </template>
  </v-tooltip>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useVehicleFields } from '@/composables/useVehicleFields'

const props = defineProps<{
  blockKey: string
}>()

const { getRelatedBlockHint } = useVehicleFields()
const hint = computed(() => getRelatedBlockHint(props.blockKey))
</script>
