<template>
  <div class="filters-bar mb-4">
    <v-text-field
      :model-value="search"
      prepend-inner-icon="mdi-magnify"
      label="Поиск по названию или ИНН"
      variant="outlined"
      density="compact"
      hide-details
      style="max-width: 320px"
      clearable
      @update:model-value="$emit('update:search', $event); $emit('search-input')"
      @click:clear="$emit('update:search', ''); $emit('search-input')"
    />
    <v-autocomplete
      :model-value="filterCategory"
      :items="categories"
      label="Категория товаров"
      variant="outlined"
      density="compact"
      hide-details
      clearable
      style="max-width: 260px"
      @update:model-value="$emit('update:filterCategory', $event)"
    />
    <v-btn
      v-if="filterCategory || search"
      variant="text"
      size="small"
      color="grey"
      @click="$emit('clear')"
    >Сбросить</v-btn>
    <span class="search-count">{{ count }} из {{ total }}</span>
    <v-btn-toggle
      v-if="!mobile"
      :model-value="viewMode"
      mandatory
      density="compact"
      variant="outlined"
      divided
      class="ml-1"
      @update:model-value="$emit('update:viewMode', $event)"
    >
      <v-btn value="table" size="small" icon="mdi-table" />
      <v-btn value="cards" size="small" icon="mdi-view-grid" />
    </v-btn-toggle>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  search: string
  filterCategory: string | null
  categories: string[]
  count: number
  total: number
  mobile: boolean
  viewMode: string
}>()
defineEmits<{
  (e: 'update:search', value: string): void
  (e: 'update:filterCategory', value: string | null): void
  (e: 'update:viewMode', value: string): void
  (e: 'search-input'): void
  (e: 'clear'): void
}>()
</script>
