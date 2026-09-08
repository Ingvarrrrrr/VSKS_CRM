<template>
  <v-dialog v-model="show" max-width="420">
    <v-card>
      <v-card-title class="text-h6 pt-4 px-6">Удалить товары?</v-card-title>
      <v-card-text class="px-6">
        Будет удалено <strong>{{ count }}</strong> товаров из каталога.
        Позиции в закупках, где эти товары были выбраны, сохранятся, но ссылка на карточку товара будет очищена.
      </v-card-text>
      <v-card-actions class="px-6 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="show = false">Отмена</v-btn>
        <v-btn color="error" :loading="deleting" @click="$emit('confirm')">Удалить {{ count }} товаров</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
defineProps<{
  count: number
  deleting: boolean
}>()
defineEmits<{ (e: 'confirm'): void }>()

const show = defineModel<boolean>('modelValue', { required: true })
</script>
