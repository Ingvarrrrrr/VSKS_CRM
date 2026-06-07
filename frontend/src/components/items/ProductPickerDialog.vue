<template>
  <!-- Presentational product picker. Parent owns search state, results list and
       all business logic; this child renders the dialog and emits user intents.
       Extracted from PurchaseItemsEditor.vue (Layer 2). -->
  <v-dialog :model-value="modelValue" max-width="1600" width="95vw" scrollable
    @update:model-value="(v: boolean) => emit('update:modelValue', v)">
    <v-card class="d-flex flex-column" style="height: calc(100vh - 48px)">
      <v-card-title class="text-h6 pt-4 px-4 px-sm-6 d-flex align-center justify-space-between">
        <span>Выбрать товар из каталога</span>
        <v-btn icon="mdi-close" variant="text" size="small" @click="emit('update:modelValue', false)" />
      </v-card-title>
      <v-card-text class="px-4 pb-2 flex-grow-1" style="overflow-y:auto">
        <v-text-field
          :model-value="search"
          prepend-inner-icon="mdi-magnify"
          label="Поиск"
          placeholder="Наименование, описание или тип"
          variant="outlined" density="compact" clearable hide-details autofocus
          class="mb-3"
          @update:model-value="(v: string) => emit('update:search', v ?? '')"
        />
        <div v-if="!results.length" class="text-center text-medium-emphasis py-8">
          <v-icon icon="mdi-package-variant-closed" size="40" class="mb-2" />
          <div>Ничего не найдено</div>
          <v-btn class="mt-3" variant="tonal" color="primary" prepend-icon="mdi-plus"
            @click="emit('create-new')">
            Добавить в каталог{{ search.length <= 30 ? ': «' + search + '»' : '' }}
          </v-btn>
        </div>
        <v-table v-else density="compact" hover>
          <thead>
            <tr>
              <th style="width:48px"></th>
              <th>Наименование</th>
              <th style="width:110px">Тип</th>
              <th style="width:130px;text-align:right">Цена, ₽</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in results" :key="p.id"
              style="cursor:pointer" @click="emit('pick', p)">
              <td>
                <v-avatar size="36" rounded="sm" class="my-1" style="overflow:hidden">
                  <img v-if="photoSrc(p)" :src="photoSrc(p)!" style="width:36px;height:36px;object-fit:cover;display:block" @error="($event.target as HTMLImageElement).style.display='none'" />
                  <v-icon v-else icon="mdi-package-variant" color="grey" size="20" />
                </v-avatar>
              </td>
              <td>
                <div class="font-weight-medium">{{ p.name }}</div>
                <div v-if="p.description" class="text-caption text-medium-emphasis"
                  style="max-width:340px;white-space:normal;line-height:1.3">
                  {{ p.description.slice(0, 90) }}{{ p.description.length > 90 ? '…' : '' }}
                </div>
              </td>
              <td>
                <v-chip v-if="p.product_type" size="x-small" variant="tonal">{{ p.product_type }}</v-chip>
              </td>
              <td style="text-align:right" class="font-weight-medium text-blue-darken-2">
                {{ p.price ? Number(p.price).toLocaleString('ru-RU') + ' ₽' : '—' }}
              </td>
            </tr>
          </tbody>
        </v-table>
      </v-card-text>
      <v-card-actions class="px-4 pb-3 d-flex flex-wrap" style="gap:6px">
        <v-btn v-if="supportsFullProductDialog"
          variant="tonal" color="teal" size="small" prepend-icon="mdi-plus"
          class="flex-grow-0" @click="emit('create-new')">
          Новый товар
        </v-btn>
        <span class="text-caption text-medium-emphasis">{{ results.length }} позиций</span>
        <v-spacer />
        <v-btn variant="text" size="small" @click="emit('update:modelValue', false)">Отмена</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import type { ProductLike } from '@/components/items/types'

defineProps<{
  modelValue: boolean
  search: string
  results: ProductLike[]
  supportsFullProductDialog?: boolean
  /** Resolves the row photo src (parent's productPhotoSrc helper). */
  photoSrc: (p: ProductLike | null | undefined) => string | undefined
}>()

const emit = defineEmits<{
  'update:modelValue': [v: boolean]
  'update:search': [v: string]
  pick: [product: ProductLike]
  'create-new': []
}>()
</script>
