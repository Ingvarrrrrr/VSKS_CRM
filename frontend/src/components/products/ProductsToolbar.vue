<template>
  <div class="d-flex align-center justify-space-between mb-6">
    <div>
      <h1 class="text-h5 font-weight-bold">Каталог товаров</h1>
      <span class="text-body-2 text-medium-emphasis">{{ productsCount }} позиций</span>
    </div>
    <div class="d-flex gap-2">
      <v-btn variant="outlined" prepend-icon="mdi-download-outline" @click="$emit('download-template')">Шаблон</v-btn>
      <v-btn variant="outlined" prepend-icon="mdi-upload-outline" color="secondary" @click="$emit('open-import')">Импорт Excel</v-btn>
      <v-btn variant="outlined" prepend-icon="mdi-image-sync" color="teal" @click="$emit('open-download-photos')">Скачать фото</v-btn>
      <v-btn variant="outlined" prepend-icon="mdi-content-duplicate" color="warning" :loading="deduplicating" @click="$emit('deduplicate')">Удалить дубликаты</v-btn>
      <v-btn color="primary" prepend-icon="mdi-plus" @click="$emit('create')">Добавить товар</v-btn>
      <v-btn variant="outlined" prepend-icon="mdi-table-column" @click="$emit('open-column-config')">Столбцы</v-btn>
      <v-btn-toggle v-if="!mobile" :model-value="viewMode" mandatory density="compact" variant="outlined" divided class="ml-1"
        @update:model-value="$emit('update:viewMode', $event)">
        <v-btn value="table" size="small" icon="mdi-table" />
        <v-btn value="cards" size="small" icon="mdi-view-grid" />
      </v-btn-toggle>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  productsCount: number
  deduplicating: boolean
  mobile: boolean
  viewMode: 'table' | 'cards'
}>()
defineEmits<{
  (e: 'download-template'): void
  (e: 'open-import'): void
  (e: 'open-download-photos'): void
  (e: 'deduplicate'): void
  (e: 'create'): void
  (e: 'open-column-config'): void
  (e: 'update:viewMode', value: 'table' | 'cards'): void
}>()
</script>
