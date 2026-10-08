<template>
  <div class="poruchenie-checkbox">
    <v-checkbox
      :model-value="modelValue"
      @update:model-value="(v: boolean | null) => emit('update:modelValue', !!v)"
      density="compact"
      hide-details
      color="primary"
      :error="!!errorMessage"
    >
      <template #label>
        <span class="poruchenie-label">
          Организация поручает обработку персональных данных своих сотрудников и
          контрагентов на
          <a :href="poruchenieHref" target="_blank" rel="noopener noreferrer" @click.stop>условиях поручения</a>
          и отвечает за получение их согласия
        </span>
      </template>
    </v-checkbox>
    <div v-if="errorMessage" class="poruchenie-error text-error">{{ errorMessage }}</div>
  </div>
</template>

<script lang="ts">
// Реэкспорт версии именно этого документа (ПРАВИЛО №6, см. legal/CONTRACT.md) —
// RegisterView.vue шлёт её серверу только как проверку «фронт прислал что-то»;
// фактическую версию сервер всё равно считает сам (PORUCHENIE_VERSION в
// backend/app/services/legal_generated.py).
export { PORUCHENIE_VERSION } from '@/legal/documents.generated'
</script>

<script setup lang="ts">
defineProps<{
  modelValue: boolean
  errorMessage?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const poruchenieHref = '/legal/poruchenie'
</script>

<style scoped>
.poruchenie-checkbox {
  display: flex;
  flex-direction: column;
}
.poruchenie-label {
  font-size: 13px;
  line-height: 1.5;
  color: rgba(var(--v-theme-on-surface), 0.8);
}
.poruchenie-label a {
  color: rgb(var(--v-theme-primary));
  text-decoration: underline;
}
.poruchenie-label a:hover {
  text-decoration: none;
}
.poruchenie-error {
  font-size: 12px;
  margin-left: 34px;
  margin-top: -4px;
}
</style>
