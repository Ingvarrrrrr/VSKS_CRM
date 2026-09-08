<!--
  Подпись поля карточки ТС: "<текст> + FieldHint + FieldHistoryPopover".
  Подпись поля берётся из реестра (GET /api/vehicle-fields →
  useVehicleFields.getFieldLabel), проп `label` — только запасной вариант на
  случай, если реестр ещё не загрузился или в нём нет такого ключа. Реестр —
  единственный источник правды (backend/app/services/vehicle_fields.py),
  второй копии подписей на фронте не держим.
-->
<template>
  <div class="text-caption text-medium-emphasis mb-1 d-flex align-center">
    <span>{{ effectiveLabel }}</span>
    <FieldHint :field-key="fieldKey" />
    <FieldHistoryPopover
      :vehicle-id="vehicleId"
      :field-key="fieldKey"
      :field-label="effectiveLabel"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useVehicleFields } from '@/composables/useVehicleFields'
import FieldHistoryPopover from '@/components/vehicles/FieldHistoryPopover.vue'
import FieldHint from './FieldHint.vue'

const props = defineProps<{
  label: string
  fieldKey: string
  vehicleId: number
}>()

const { getFieldLabel } = useVehicleFields()
const effectiveLabel = computed(() => getFieldLabel(props.fieldKey) ?? props.label)
</script>
