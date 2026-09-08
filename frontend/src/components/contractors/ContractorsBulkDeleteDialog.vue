<template>
  <v-dialog :model-value="modelValue" max-width="440" persistent @update:model-value="$emit('update:modelValue', $event)">
    <v-card class="dialog-card">
      <v-card-title class="dialog-title">
        <v-icon icon="mdi-alert-circle-outline" color="error" class="mr-2" />
        Удалить контрагентов?
      </v-card-title>
      <v-divider />
      <v-card-text class="pt-4">
        <p class="mb-3">
          Вы собираетесь удалить <strong>{{ count }}</strong> контрагентов.
          Это действие <strong>нельзя отменить</strong>.
        </p>
        <p v-if="count > 5" class="text-caption text-medium-emphasis mb-3">
          Для подтверждения введите количество удаляемых записей:
        </p>
        <v-text-field
          v-if="count > 5"
          :model-value="confirmCount"
          :placeholder="`Введите ${count}`"
          variant="outlined"
          density="compact"
          hide-details
          autofocus
          @update:model-value="$emit('update:confirmCount', $event)"
        />
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="$emit('cancel')">Отмена</v-btn>
        <v-btn
          color="error"
          :loading="saving"
          :disabled="count > 5 && confirmCount !== String(count)"
          @click="$emit('confirm')"
        >Удалить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
defineProps<{
  modelValue: boolean
  count: number
  confirmCount: string
  saving: boolean
}>()
defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'update:confirmCount', value: string): void
  (e: 'cancel'): void
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
