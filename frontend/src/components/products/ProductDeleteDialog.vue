<template>
  <v-dialog v-model="show" max-width="400">
    <v-card>
      <v-card-title class="text-h6 pt-4 px-6">Удалить товар?</v-card-title>
      <v-card-text class="px-6">
        <strong>{{ target?.name }}</strong> будет удалён из каталога.
      </v-card-text>
      <v-card-actions class="px-6 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="show = false">Отмена</v-btn>
        <v-btn color="error" :loading="deleting" @click="$emit('confirm')">Удалить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import type { Product } from '@/composables/products/productsTypes'

defineProps<{
  target: Product | null
  deleting: boolean
}>()
defineEmits<{ (e: 'confirm'): void }>()

const show = defineModel<boolean>('modelValue', { required: true })
</script>
