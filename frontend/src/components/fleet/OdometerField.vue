<template>
  <div class="odometer-field">
    <v-text-field
      :model-value="modelValue"
      :label="label"
      :readonly="readonly"
      :error-messages="errorMsg"
      type="number"
      variant="outlined"
      density="compact"
      hide-spin-buttons
      prepend-inner-icon="mdi-speedometer"
      @update:model-value="onInput"
    >
      <template #append-inner>
        <span class="odometer-field__unit">км</span>
      </template>
    </v-text-field>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  modelValue?: number
  label: string
  previousValue?: number
  readonly?: boolean
}>(), {
  readonly: false,
})

const emit = defineEmits<{
  (e: 'update:modelValue', v: number | undefined): void
}>()

const errorMsg = computed<string[]>(() => {
  if (
    props.modelValue !== undefined &&
    props.previousValue !== undefined &&
    props.modelValue < props.previousValue
  ) {
    const prev = props.previousValue.toLocaleString('ru-RU')
    return [`Пробег не может уменьшаться. Предыдущее значение: ${prev} км`]
  }
  return []
})

function onInput(v: string | number | null | undefined) {
  if (v === '' || v === null || v === undefined) {
    emit('update:modelValue', undefined)
    return
  }
  const n = Number(v)
  emit('update:modelValue', isNaN(n) ? undefined : n)
}
</script>

<style scoped>
.odometer-field {
  width: 100%;
}

.odometer-field__unit {
  font-size: 12px;
  color: var(--muted, #8a93a8);
  font-weight: 500;
  user-select: none;
}
</style>
