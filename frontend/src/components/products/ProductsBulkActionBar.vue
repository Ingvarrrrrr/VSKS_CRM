<template>
  <v-toolbar color="primary" density="compact" :class="toolbarClass">
    <span class="text-body-2 ml-2 font-weight-medium">Выбрано: {{ selectedCount }}</span>
    <v-btn variant="text" size="small" prepend-icon="mdi-close-circle" color="white" class="ml-2"
      @click="$emit('clear')">Снять</v-btn>
    <v-btn v-if="selectedCount < totalCount" variant="text" size="small" prepend-icon="mdi-select-all" color="white" class="ml-1"
      @click="$emit('select-all')">Выбрать все ({{ totalCount }})</v-btn>
    <v-spacer />
    <v-btn variant="tonal" size="small" prepend-icon="mdi-tag-multiple" color="white" class="mr-2"
      @click="$emit('bulk-edit')">Категория / вид</v-btn>
    <v-btn variant="tonal" size="small" prepend-icon="mdi-eye-check" color="white" class="mr-2"
      @click="$emit('toggle-active', true)">Активировать</v-btn>
    <v-btn variant="tonal" size="small" prepend-icon="mdi-eye-off" color="white" class="mr-2"
      @click="$emit('toggle-active', false)">Деактивировать</v-btn>
    <v-btn variant="flat" size="small" prepend-icon="mdi-delete" color="error"
      @click="$emit('bulk-delete')">Удалить выбранные</v-btn>
    <v-btn v-if="isSuperadmin" variant="flat" size="small" prepend-icon="mdi-delete-sweep" color="error" class="ml-2"
      @click="$emit('delete-all')">Удалить ВСЕ</v-btn>
  </v-toolbar>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  selectedCount: number
  totalCount: number
  isSuperadmin: boolean
  toolbarClass?: string
}>(), {
  toolbarClass: 'px-2 rounded-t',
})
defineEmits<{
  (e: 'clear'): void
  (e: 'select-all'): void
  (e: 'bulk-edit'): void
  (e: 'toggle-active', active: boolean): void
  (e: 'bulk-delete'): void
  (e: 'delete-all'): void
}>()
</script>
