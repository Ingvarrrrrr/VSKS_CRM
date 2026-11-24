<template>
  <div v-if="shouldShow" class="password-requirements-hint pa-2 rounded mb-3">
    <!-- Предупреждение о простом пароле или совпадении с логином -->
    <v-alert
      v-if="evalState.isCommon"
      type="warning"
      variant="tonal"
      density="compact"
      class="mb-2 text-caption"
      icon="mdi-alert-circle-outline"
    >
      Пароль слишком простой — легко угадывается. Придумайте более сложный пароль.
    </v-alert>
    <v-alert
      v-else-if="evalState.matchesIdentifier"
      type="warning"
      variant="tonal"
      density="compact"
      class="mb-2 text-caption"
      icon="mdi-alert-circle-outline"
    >
      Пароль не должен совпадать с логином или email.
    </v-alert>

    <div class="text-caption text-medium-emphasis mb-1 font-weight-medium">
      Требования к паролю:
    </div>

    <div class="d-flex flex-column gap-1 text-caption">
      <!-- 1. Длина -->
      <div class="d-flex align-center" :class="itemClass(evalState.hasMinLength)">
        <v-icon size="14" :color="iconColor(evalState.hasMinLength)" class="mr-1">
          {{ evalState.hasMinLength ? 'mdi-check-circle' : 'mdi-circle-outline' }}
        </v-icon>
        <span>
          Не менее {{ evalState.minLength }} символов
          <span class="text-medium-emphasis">(сейчас {{ evalState.currentLength }})</span>
        </span>
      </div>

      <!-- 2. Буквы -->
      <div class="d-flex align-center" :class="itemClass(evalState.hasLetter)">
        <v-icon size="14" :color="iconColor(evalState.hasLetter)" class="mr-1">
          {{ evalState.hasLetter ? 'mdi-check-circle' : 'mdi-circle-outline' }}
        </v-icon>
        <span>Буквы (латиница или кириллица)</span>
      </div>

      <!-- 3. Цифры -->
      <div class="d-flex align-center" :class="itemClass(evalState.hasDigit)">
        <v-icon size="14" :color="iconColor(evalState.hasDigit)" class="mr-1">
          {{ evalState.hasDigit ? 'mdi-check-circle' : 'mdi-circle-outline' }}
        </v-icon>
        <span>Цифры (0–9)</span>
      </div>

      <!-- 4. Спецсимволы инфо -->
      <div class="text-caption text-disabled mt-1">
        Можно использовать спецсимволы (!@#$%^&*_- и др.)
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { evaluatePassword } from '@/utils/passwordPolicy'

const props = withDefaults(
  defineProps<{
    password?: string
    identifiers?: (string | null | undefined)[]
    showWhenEmpty?: boolean
  }>(),
  {
    password: '',
    identifiers: () => [],
    showWhenEmpty: false,
  },
)

const shouldShow = computed(() => {
  if (props.showWhenEmpty) return true
  return Boolean(props.password && props.password.length > 0)
})

const evalState = computed(() => {
  return evaluatePassword(props.password, props.identifiers)
})

function iconColor(valid: boolean): string {
  if (valid) return 'success'
  if (props.password && props.password.length > 0) return 'grey'
  return 'grey-lighten-1'
}

function itemClass(valid: boolean): string {
  if (valid) return 'text-success font-weight-medium'
  return 'text-medium-emphasis'
}
</script>

<style scoped>
.password-requirements-hint {
  background: rgba(var(--v-theme-surface-variant), 0.35);
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.gap-1 {
  gap: 4px;
}
</style>
