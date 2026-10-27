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
      <!-- «Похожие товары» (владелец, 27.10.2026) — ручная проверка карточек,
           возможно, одного товара у разных магазинов. Видна только тому, кто
           может редактировать каталог — тот же признак canEditCatalog
           (ProductsView.vue, ACTIONS.PRODUCTS_EDIT_CATALOG), что у блока
           «Предложения правок» рядом. -->
      <v-btn v-if="canEditCatalog" variant="outlined" prepend-icon="mdi-shape-outline" color="indigo" @click="$emit('open-similar-products')">Похожие товары</v-btn>
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
  // total_capped с бэкенда (ПРАВИЛО №6, product_search.py::count_products) —
  // владелец 26.10.2026 решил: счётчик всегда точный, потолок убран, поле
  // всегда false. Оставлено в пропсах для совместимости с вызывающим кодом,
  // в шаблоне больше не используется (раньше показывало «10 000+»).
  productsCountCapped?: boolean
  deduplicating: boolean
  mobile: boolean
  viewMode: 'table' | 'cards'
  canEditCatalog: boolean
}>()
defineEmits<{
  (e: 'download-template'): void
  (e: 'open-import'): void
  (e: 'open-download-photos'): void
  (e: 'deduplicate'): void
  (e: 'create'): void
  (e: 'open-column-config'): void
  (e: 'update:viewMode', value: 'table' | 'cards'): void
  (e: 'open-similar-products'): void
}>()
</script>
