<template>
  <v-dialog v-model="migrateDialog" max-width="480">
    <v-card>
      <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">Мигрировать из закупок</v-card-title>
      <v-card-text class="px-4">
        <p class="text-body-2 mb-3">
          Создаст записи реестра из всех закупок с заполненным номером договора. Уже существующие номера пропускаются.
        </p>
        <v-alert v-if="migrateResult" :type="migrateResult.created > 0 ? 'success' : 'info'" variant="tonal" density="compact">
          Создано: <strong>{{ migrateResult.created }}</strong>,
          пропущено: <strong>{{ migrateResult.skipped }}</strong>
        </v-alert>
      </v-card-text>
      <v-card-actions class="px-4 pb-3">
        <v-spacer />
        <v-btn variant="text" @click="migrateDialog = false">Закрыть</v-btn>
        <v-btn v-if="!migrateResult" color="primary" variant="tonal" :loading="migrating" @click="onMigrate">
          Запустить
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
const migrateDialog = defineModel<boolean>({ required: true })

defineProps<{
  migrating: boolean
  migrateResult: { created: number; skipped: number } | null
  onMigrate: () => void
}>()
</script>
