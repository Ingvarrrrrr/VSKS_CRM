<template>
  <v-icon
    size="16"
    color="grey"
    class="ml-1 cursor-pointer field-history-icon"
    title="История изменений"
    @click="openHistory"
  >mdi-information-outline</v-icon>
</template>

<script setup lang="ts">
import { useGalaContextMenu } from '@/composables/useGalaContextMenu'

const props = defineProps<{
  vehicleId: number
  fieldKey: string
  fieldLabel: string
}>()

const { openCellHistory } = useGalaContextMenu()

function openHistory(e: MouseEvent) {
  openCellHistory(
    {
      entityType: 'vehicle',
      entityId: props.vehicleId,
      fieldName: props.fieldKey,
      fieldLabel: props.fieldLabel,
    },
    { x: e.clientX, y: e.clientY }
  )
}
</script>

<style scoped>
.field-history-icon {
  opacity: 0.55;
  transition: opacity 0.15s;
  vertical-align: middle;
}
.field-history-icon:hover {
  opacity: 1;
}
</style>
