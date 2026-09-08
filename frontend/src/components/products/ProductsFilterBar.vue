<template>
  <v-card class="mb-4" variant="outlined">
    <v-card-text class="py-3">
      <div class="d-flex gap-3 flex-wrap align-center">
        <v-text-field
          v-model="search"
          prepend-inner-icon="mdi-magnify"
          label="Поиск по наименованию / описанию"
          variant="outlined" density="compact" clearable hide-details
          style="min-width:240px"
        />
        <v-autocomplete
          v-model="filterType"
          :items="typeOptions"
          label="Тип" variant="outlined" density="compact"
          multiple chips closable-chips clearable hide-details style="min-width:180px"
        />
        <v-autocomplete
          v-model="filterCategory"
          :items="categoryOptions"
          label="Категория" variant="outlined" density="compact"
          multiple chips closable-chips clearable hide-details style="min-width:180px"
        />
        <v-select
          v-model="filterActive"
          :items="[{title:'Активные',value:true},{title:'Неактивные',value:false}]"
          label="Статус" variant="outlined" density="compact"
          clearable hide-details style="min-width:140px"
        />
        <v-text-field
          v-model.number="filterPriceMin"
          label="Цена от, ₽" type="number"
          variant="outlined" density="compact" clearable hide-details
          style="min-width:120px;max-width:140px"
        />
        <v-text-field
          v-model.number="filterPriceMax"
          label="Цена до, ₽" type="number"
          variant="outlined" density="compact" clearable hide-details
          style="min-width:120px;max-width:140px"
        />
        <v-switch
          v-model="filterStaleOnly"
          color="warning" density="compact" hide-details
          class="flex-shrink-0"
        >
          <template #label>
            <span class="text-body-2">Только требующие актуализации</span>
            <v-chip v-if="staleProductsCount" size="x-small" color="warning" variant="tonal" class="ml-2">{{ staleProductsCount }}</v-chip>
          </template>
        </v-switch>
        <v-btn
          v-if="filterType.length || filterCategory.length || filterActive !== null || filterPriceMin || filterPriceMax || filterStaleOnly"
          variant="text" size="small" prepend-icon="mdi-filter-off" color="grey-darken-1"
          @click="$emit('reset')"
        >Сбросить</v-btn>
      </div>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
defineProps<{
  typeOptions: string[]
  categoryOptions: string[]
  staleProductsCount: number
}>()
defineEmits<{ (e: 'reset'): void }>()

const search = defineModel<string>('search', { required: true })
const filterType = defineModel<string[]>('filterType', { required: true })
const filterCategory = defineModel<string[]>('filterCategory', { required: true })
const filterActive = defineModel<boolean | null>('filterActive', { required: true })
const filterPriceMin = defineModel<number | null>('filterPriceMin', { required: true })
const filterPriceMax = defineModel<number | null>('filterPriceMax', { required: true })
const filterStaleOnly = defineModel<boolean>('filterStaleOnly', { required: true })
</script>
