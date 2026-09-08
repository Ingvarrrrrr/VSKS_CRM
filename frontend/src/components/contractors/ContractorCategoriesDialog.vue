<template>
  <v-dialog :model-value="modelValue" max-width="480" scrollable :fullscreen="mobile" @update:model-value="$emit('update:modelValue', $event)">
    <v-card>
      <v-card-title class="dialog-title">
        <v-icon icon="mdi-tag-multiple-outline" color="teal" class="mr-2" />
        Категории товаров: {{ contractor?.name }}
        <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="$emit('update:modelValue', false)" />
      </v-card-title>
      <v-divider />
      <v-card-text class="pt-4">
        <v-chip
          v-for="cat in contractor?.product_categories ?? []"
          :key="cat"
          color="teal"
          variant="tonal"
          class="mr-2 mb-2"
        >{{ cat }}</v-chip>
        <div v-if="!contractor?.product_categories?.length" class="text-center text-medium-emphasis pa-4">
          Категории не указаны (нет закупок с товарами из каталога)
        </div>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import type { ContractorWithStats } from '@/composables/contractors/contractorsTypes'

defineProps<{
  modelValue: boolean
  contractor: ContractorWithStats | null
  mobile: boolean
}>()
defineEmits<{
  (e: 'update:modelValue', value: boolean): void
}>()
</script>

<style scoped>
.dialog-title {
  display: flex;
  align-items: center;
  font-size: 16px !important;
  font-weight: 600 !important;
  padding: 16px 20px !important;
}
</style>
