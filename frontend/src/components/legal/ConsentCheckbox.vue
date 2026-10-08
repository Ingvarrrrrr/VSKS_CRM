<template>
  <div class="consent-checkbox">
    <v-checkbox
      :model-value="modelValue"
      @update:model-value="(v: boolean | null) => emit('update:modelValue', !!v)"
      density="compact"
      hide-details
      color="primary"
      :error="!!errorMessage"
    >
      <template #label>
        <span class="consent-label">
          Я даю
          <a :href="consentHref" target="_blank" rel="noopener noreferrer" @click.stop>согласие</a>
          на обработку персональных данных и подтверждаю, что ознакомлен с
          <a :href="privacyHref" target="_blank" rel="noopener noreferrer" @click.stop>политикой обработки персональных данных</a>
        </span>
      </template>
    </v-checkbox>
    <div v-if="errorMessage" class="consent-error text-error">{{ errorMessage }}</div>
  </div>
</template>

<script lang="ts">
// Реэкспорт версии именно согласия на обработку ПДн (privacy+consent) —
// единственный источник (ПРАВИЛО №6), см. legal/CONTRACT.md. RegisterView.vue
// шлёт её серверу только как проверку «фронт прислал что-то»; фактическую
// версию сервер всё равно считает сам (PD_CONSENT_VERSION в
// backend/app/services/legal_generated.py).
export { PD_CONSENT_VERSION } from '@/legal/documents.generated'
</script>

<script setup lang="ts">
defineProps<{
  modelValue: boolean
  errorMessage?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const consentHref = '/legal/consent'
const privacyHref = '/legal/privacy'
</script>

<style scoped>
.consent-checkbox {
  display: flex;
  flex-direction: column;
}
.consent-label {
  font-size: 13px;
  line-height: 1.5;
  color: rgba(var(--v-theme-on-surface), 0.8);
}
.consent-label a {
  color: rgb(var(--v-theme-primary));
  text-decoration: underline;
}
.consent-label a:hover {
  text-decoration: none;
}
.consent-error {
  font-size: 12px;
  margin-left: 34px;
  margin-top: -4px;
}
</style>
