<template>
  <v-dialog :model-value="modelValue" max-width="380" @update:model-value="emit('update:modelValue', $event)">
    <v-card>
      <v-card-title class="pa-4">Сохранить фильтр</v-card-title>
      <v-card-text class="pa-4 pt-0">
        <v-text-field
          :model-value="name"
          label="Название пресета"
          variant="outlined" density="compact" autofocus
          @update:model-value="emit('update:name', $event)"
          @keyup.enter="emit('confirm')"
        />
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="emit('update:modelValue', false)">Отмена</v-btn>
        <v-btn color="primary" variant="flat"
          :disabled="!name.trim()"
          @click="emit('confirm')">
          Сохранить
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
defineProps<{
  modelValue: boolean
  name: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'update:name', value: string): void
  (e: 'confirm'): void
}>()
</script>

<style scoped></style>
