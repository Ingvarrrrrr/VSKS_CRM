<template>
  <v-dialog v-model="show" max-width="460">
    <v-card>
      <v-card-title class="text-h6 pt-4 px-6">Массовое изменение ({{ count }})</v-card-title>
      <v-card-text class="px-6">
        <v-combobox
          v-model="category" :items="categoryOptions"
          label="Новая категория" variant="outlined" density="compact"
          clearable hide-details class="mb-3"
        />
        <v-combobox
          v-model="type" :items="typeOptions"
          label="Новый вид (тип)" variant="outlined" density="compact"
          clearable hide-details
        />
        <div class="text-caption text-medium-emphasis mt-2">Пустое поле — значение не меняется.</div>
      </v-card-text>
      <v-card-actions class="px-6 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="show = false">Отмена</v-btn>
        <v-btn color="primary" :loading="editing" @click="$emit('confirm')">Применить к {{ count }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
defineProps<{
  count: number
  editing: boolean
  categoryOptions: string[]
  typeOptions: string[]
}>()
defineEmits<{ (e: 'confirm'): void }>()

const show = defineModel<boolean>('modelValue', { required: true })
const category = defineModel<string | null>('category', { required: true })
const type = defineModel<string | null>('type', { required: true })
</script>
