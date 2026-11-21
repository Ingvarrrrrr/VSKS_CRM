<template>
  <v-card variant="outlined" class="mb-4 pa-4 rounded-lg">
    <div class="d-flex align-center justify-space-between mb-3">
      <div class="d-flex align-center ga-2">
        <v-icon color="indigo">mdi-key-chain</v-icon>
        <span class="text-subtitle-2 font-weight-bold">Ключи площадок (ЭТП)</span>
      </div>
      <div class="text-caption text-medium-emphasis">
        Для отправки закупок от имени этой организации
      </div>
    </div>

    <v-divider class="mb-4" />

    <!-- Росэлторг.Бизнес -->
    <div class="mb-3">
      <div class="d-flex align-center justify-space-between mb-1">
        <span class="text-caption font-weight-medium">Росэлторг.Бизнес</span>
        <v-chip
          v-if="hasRoseltorg"
          size="x-small"
          color="success"
          variant="tonal"
          prepend-icon="mdi-check-circle"
        >
          Ключ сохранён
        </v-chip>
        <v-chip v-else size="x-small" color="grey" variant="tonal">
          Не задан
        </v-chip>
      </div>
      <v-text-field
        v-model="roseltorgToken"
        type="password"
        label="Токен интеграции Росэлторг"
        variant="outlined"
        density="compact"
        placeholder="••••••••••••••••"
        persistent-placeholder
        hint="Токен из кабинета Росэлторг.ID → Внешние интеграции"
        persistent-hint
        autocomplete="new-password"
      />
    </div>

    <!-- Фабрикант -->
    <div>
      <div class="d-flex align-center justify-space-between mb-1">
        <span class="text-caption font-weight-medium">Фабрикант</span>
        <v-chip
          v-if="hasFabrikant"
          size="x-small"
          color="success"
          variant="tonal"
          prepend-icon="mdi-check-circle"
        >
          Ключи сохранены
        </v-chip>
        <v-chip v-else size="x-small" color="grey" variant="tonal">
          Не заданы
        </v-chip>
      </div>
      <v-row dense>
        <v-col cols="12" sm="6">
          <v-text-field
            v-model="fabrikantLogin"
            label="Логин Фабрикант"
            variant="outlined"
            density="compact"
            autocomplete="off"
          />
        </v-col>
        <v-col cols="12" sm="6">
          <v-text-field
            v-model="fabrikantPassword"
            type="password"
            label="Пароль Фабрикант"
            variant="outlined"
            density="compact"
            placeholder="••••••••••••••••"
            persistent-placeholder
            autocomplete="new-password"
          />
        </v-col>
      </v-row>
    </div>
  </v-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const roseltorgToken = defineModel<string>('roseltorgToken', { default: '' })
const fabrikantLogin = defineModel<string>('fabrikantLogin', { default: '' })
const fabrikantPassword = defineModel<string>('fabrikantPassword', { default: '' })

const props = withDefaults(defineProps<{
  hasRoseltorgToken?: boolean
  hasFabrikantCredentials?: boolean
}>(), {
  hasRoseltorgToken: false,
  hasFabrikantCredentials: false,
})

const hasRoseltorg = computed(() => props.hasRoseltorgToken || !!roseltorgToken.value?.trim())
const hasFabrikant = computed(() => props.hasFabrikantCredentials || (!!fabrikantLogin.value?.trim() && !!fabrikantPassword.value?.trim()))
</script>
