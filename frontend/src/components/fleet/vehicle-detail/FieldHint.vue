<!--
  Иконка-подсказка "откуда берётся значение" для поля карточки ТС.
  Единственный источник текста — реестр полей (useVehicleFields.getFieldSourceHint,
  backend/app/services/vehicle_fields.py, §4). Ничего не грузит сама — реестр
  загружается один раз в useVehicleFields.loadFields() при монтировании карточки.
-->
<template>
  <v-tooltip v-if="hint" :text="hint" location="top" max-width="320">
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
  fieldKey: string
}>()

const { getFieldSourceHint } = useVehicleFields()
const hint = computed(() => getFieldSourceHint(props.fieldKey))
</script>
