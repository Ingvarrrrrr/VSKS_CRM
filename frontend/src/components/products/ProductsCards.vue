<template>
  <div>
    <!-- Bulk action bar (cards mode) -->
    <ProductsBulkActionBar
      v-if="selectedIds.length"
      :selected-count="selectedIds.length"
      :total-count="totalCount"
      :is-superadmin="isSuperadmin"
      toolbar-class="px-2 rounded mb-3"
      @clear="$emit('update:selectedIds', [])"
      @select-all="$emit('select-all')"
      @bulk-edit="$emit('bulk-edit')"
      @toggle-active="active => $emit('toggle-active', active)"
      @bulk-delete="$emit('bulk-delete')"
      @delete-all="$emit('delete-all')"
    />

    <v-row v-if="items.length" dense>
      <v-col
        v-for="p in items"
        :key="p.id"
        cols="12" sm="6" md="4" lg="3"
      >
        <v-card
          hover
          variant="outlined"
          class="d-flex flex-column h-100"
          style="cursor:pointer"
          @click="$emit('edit', p)"
        >
          <!-- Photo -->
          <v-img
            :src="cardPhotoSrc(p)"
            height="180"
            :cover="false"
            class="bg-grey-lighten-4 flex-shrink-0"
          >
            <template #error>
              <div class="d-flex align-center justify-center fill-height">
                <v-icon size="64" class="text-medium-emphasis">mdi-package-variant</v-icon>
              </div>
            </template>
            <template #placeholder>
              <div class="d-flex align-center justify-center fill-height">
                <v-icon size="64" class="text-medium-emphasis">mdi-package-variant</v-icon>
              </div>
            </template>
          </v-img>

          <v-card-text class="flex-grow-1 pb-1">
            <div class="font-weight-bold text-body-2 mb-1" style="line-height:1.3">{{ p.name }}</div>
            <div class="d-flex flex-wrap gap-1 mb-1">
              <v-chip v-if="p.product_type" size="x-small" variant="tonal" :color="typeColor(p.product_type)">
                {{ p.product_type }}
              </v-chip>
              <v-chip v-if="p.category" size="x-small" variant="tonal" color="grey">
                {{ p.category }}
              </v-chip>
              <v-chip size="x-small" :color="p.is_active ? 'success' : 'grey'" variant="tonal">
                {{ p.is_active ? 'Активен' : 'Неактивен' }}
              </v-chip>
            </div>
            <div v-if="p.price" class="font-weight-medium text-blue-darken-2 text-body-2">
              {{ Number(p.price).toLocaleString('ru-RU') }} ₽
            </div>
            <div v-if="p.description" class="text-caption text-medium-emphasis mt-1" style="line-height:1.3">
              {{ p.description.slice(0, 80) }}{{ p.description.length > 80 ? '…' : '' }}
            </div>
          </v-card-text>

          <v-card-actions @click.stop class="pt-0">
            <v-spacer />
            <v-btn icon="mdi-pencil-outline" variant="text" size="small" @click.stop="$emit('edit', p)" />
            <v-btn icon="mdi-delete-outline" variant="text" size="small" color="error" @click.stop="$emit('delete', p)" />
          </v-card-actions>
        </v-card>
      </v-col>
    </v-row>

    <!-- Empty state -->
    <div v-else class="text-center py-10">
      <v-icon icon="mdi-package-variant-closed" size="48" color="grey-lighten-1" class="mb-3" />
      <div class="text-medium-emphasis">Товары не найдены</div>
    </div>

    <!-- Pagination -->
    <v-pagination
      v-if="totalPages > 1"
      :model-value="page"
      :length="totalPages"
      density="compact"
      :total-visible="7"
      class="d-flex justify-center mt-4"
      @update:model-value="$emit('update:page', $event)"
    />
  </div>
</template>

<script setup lang="ts">
import { typeColor } from '@/composables/products/productsTypes'
import type { Product } from '@/composables/products/productsTypes'
import ProductsBulkActionBar from './ProductsBulkActionBar.vue'

defineProps<{
  items: Product[]
  totalCount: number
  page: number
  totalPages: number
  selectedIds: number[]
  isSuperadmin: boolean
  cardPhotoSrc: (p: Product) => string | undefined
}>()

defineEmits<{
  (e: 'update:selectedIds', ids: number[]): void
  (e: 'update:page', page: number): void
  (e: 'select-all'): void
  (e: 'edit', item: Product): void
  (e: 'delete', item: Product): void
  (e: 'bulk-edit'): void
  (e: 'toggle-active', active: boolean): void
  (e: 'bulk-delete'): void
  (e: 'delete-all'): void
}>()
</script>
