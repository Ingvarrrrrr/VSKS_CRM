<template>
  <v-dialog :model-value="modelValue" max-width="480" @update:model-value="emit('update:modelValue', $event)">
    <v-card>
      <v-card-title class="text-h6 pt-4 px-6 d-flex align-center gap-2">
        <v-icon icon="mdi-alert-circle-outline" color="error" />
        Ошибка
      </v-card-title>
      <v-card-text class="px-6">
        <p class="mb-2">{{ message }}</p>
        <div v-if="code" class="text-caption text-medium-emphasis">Код: {{ code }}</div>
        <div v-if="correlationId" class="text-caption text-medium-emphasis">ID: {{ correlationId }}</div>
      </v-card-text>
      <v-card-actions class="px-6 pb-4">
        <v-btn size="small" variant="tonal" prepend-icon="mdi-content-copy"
          @click="emit('copy')">Скопировать</v-btn>
        <v-spacer />
        <v-btn variant="text" @click="emit('update:modelValue', false)">Закрыть</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
defineProps<{
  modelValue: boolean
  message: string
  code: string
  correlationId: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'copy'): void
}>()
</script>

<style scoped></style>
