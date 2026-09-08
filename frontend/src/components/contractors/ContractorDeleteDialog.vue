<template>
  <v-dialog :model-value="modelValue" max-width="420" @update:model-value="$emit('update:modelValue', $event)">
    <v-card class="dialog-card">
      <v-card-title class="dialog-title">
        <v-icon icon="mdi-alert-circle-outline" color="error" class="mr-2" />
        Удалить контрагента?
      </v-card-title>
      <v-divider />
      <v-card-text class="pt-4">
        Удалить <strong>{{ target?.name }}</strong>? Действие нельзя отменить.
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="$emit('update:modelValue', false)">Отмена</v-btn>
        <v-btn color="error" :loading="saving" @click="$emit('confirm')">Удалить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import type { ContractorWithStats } from '@/composables/contractors/contractorsTypes'

defineProps<{
  modelValue: boolean
  target: ContractorWithStats | null
  saving: boolean
}>()
defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'confirm'): void
}>()
</script>

<style scoped>
.dialog-card { }
.dialog-title {
  display: flex;
  align-items: center;
  font-size: 16px !important;
  font-weight: 600 !important;
  padding: 16px 20px !important;
}
</style>
