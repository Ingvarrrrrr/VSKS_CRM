<template>
  <v-dialog v-model="show" max-width="480">
    <v-card>
      <v-card-title class="text-h6 pt-4 px-6 text-error">Удалить ВСЕ товары?</v-card-title>
      <v-card-text class="px-6">
        Будут удалены <strong>все {{ totalCount }}</strong> товаров из каталога.
        Это действие необратимо. Для подтверждения введите слово <strong>УДАЛИТЬ</strong>.
      </v-card-text>
      <v-text-field v-model="confirmText" label="Введите УДАЛИТЬ" variant="outlined" density="compact" class="mx-6" hide-details />
      <v-card-actions class="px-6 pb-4 pt-3">
        <v-spacer />
        <v-btn variant="text" @click="show = false; confirmText = ''">Отмена</v-btn>
        <v-btn color="error" :loading="deleting" :disabled="confirmText !== 'УДАЛИТЬ'" @click="$emit('confirm')">Удалить все</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
defineProps<{
  totalCount: number
  deleting: boolean
}>()
defineEmits<{ (e: 'confirm'): void }>()

const show = defineModel<boolean>('modelValue', { required: true })
const confirmText = defineModel<string>('confirmText', { required: true })
</script>
