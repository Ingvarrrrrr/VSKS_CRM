<template>
  <div>
    <!-- Filters -->
    <v-card class="mb-4" variant="outlined">
      <v-card-text class="py-3">
        <div class="d-flex align-center gap-4 flex-wrap">
          <v-select
            v-model="filters.subsidyId"
            :items="subsidies"
            item-title="name"
            item-value="id"
            label="Субсидия"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            style="min-width:220px"
          />
          <v-select
            v-model="filters.status"
            :items="statusItems"
            item-title="label"
            item-value="value"
            label="Статус"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            style="min-width:170px"
          />
          <v-text-field
            v-model="filters.search"
            prepend-inner-icon="mdi-magnify"
            label="Поиск"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            style="min-width:200px"
          />
          <v-select
            v-model="filters.types"
            :items="orderTypeOptions"
            item-title="label"
            item-value="value"
            label="Тип договора"
            variant="outlined"
            density="compact"
            multiple
            chips
            closable-chips
            clearable
            hide-details
            style="min-width:220px"
          />
          <v-autocomplete
            v-model="filters.contractorIds"
            :items="contractorsForFilter"
            item-title="name"
            item-value="id"
            label="Контрагент"
            variant="outlined"
            density="compact"
            multiple
            chips
            closable-chips
            clearable
            hide-details
            style="min-width:220px"
          />
          <v-text-field
            v-model="filters.product"
            label="Поиск товара"
            prepend-inner-icon="mdi-magnify"
            variant="outlined" density="compact" hide-details clearable
            placeholder="Название товара..."
            style="min-width:200px; max-width:240px"
          />
          <!-- Phase 32: period filter -->
          <v-text-field
            v-model="filters.periodFrom"
            label="Период с"
            type="date"
            variant="outlined" density="compact" hide-details clearable
            style="min-width:160px; max-width:180px"
          />
          <v-text-field
            v-model="filters.periodTo"
            label="Период по"
            type="date"
            variant="outlined" density="compact" hide-details clearable
            style="min-width:160px; max-width:180px"
          />
          <v-btn
            size="small" variant="tonal" color="primary"
            prepend-icon="mdi-bookmark-plus-outline"
            @click="emit('save-preset')">
            Сохранить фильтр
          </v-btn>
          <v-btn variant="tonal" prepend-icon="mdi-view-column" size="small" @click="emit('open-columns')">Колонки</v-btn>
          <!-- Phase 31-06: filter by unseen changes -->
          <v-checkbox
            v-model="filters.onlyUnseen"
            label="Только с чужими правками"
            density="compact"
            hide-details
            color="#fb923c"
            class="ml-1"
            style="min-width:fit-content"
          />
          <v-btn-toggle v-if="!mobile" :model-value="viewMode" @update:model-value="v => emit('update:viewMode', v)" mandatory density="compact" variant="outlined" divided class="ml-1">
            <v-btn value="table" size="small" icon="mdi-table" />
            <v-btn value="cards" size="small" icon="mdi-view-grid" />
          </v-btn-toggle>
          <v-chip
            v-if="activeFilterCount > 0 || filters.periodFrom || filters.periodTo"
            color="deep-orange" variant="tonal" size="small"
            prepend-icon="mdi-filter-multiple"
            class="ml-1"
            closable
            @click:close="emit('clear-filters')"
          >
            Фильтры {{ activeFilterCount + (filters.periodFrom || filters.periodTo ? 1 : 0) }}
          </v-chip>
          <v-chip color="primary" variant="tonal" prepend-icon="mdi-cash-multiple" size="small" class="ml-2">
            Сумма: {{ formatMoney(filteredSum) }}
          </v-chip>
        </div>
        <!-- Saved filter preset chips -->
        <div v-if="savedFilterPresets.length" class="d-flex align-center gap-2 flex-wrap mt-2">
          <span class="text-caption text-medium-emphasis">Пресеты:</span>
          <v-chip
            v-for="p in savedFilterPresets" :key="p.name"
            size="small" variant="tonal" color="primary"
            class="cursor-pointer"
            @click="emit('apply-preset', p)">
            {{ p.name }}
            <v-icon icon="mdi-close" size="12" class="ml-1" @click.stop="emit('remove-preset', p.name)" />
          </v-chip>
        </div>
      </v-card-text>
    </v-card>

    <!-- Status tab chips -->
    <v-chip-group v-model="filters.status" class="mb-4">
      <v-chip value="" variant="outlined" filter>Все</v-chip>
      <v-chip
        v-for="s in statusItems"
        :key="s.value"
        :value="s.value"
        :color="s.color"
        filter
        variant="outlined"
      >
        {{ s.label }}
      </v-chip>
    </v-chip-group>

    <!-- FEO category filter badge -->
    <v-chip v-if="filters.feoCategoryId" color="teal" variant="tonal" closable class="mb-3" prepend-icon="mdi-filter"
      @click:close="filters.feoCategoryId = null; filters.feoCategoryName = ''; filters.feoCategoryIds = new Set()">
      ФЭО: {{ filters.feoCategoryName }}
    </v-chip>

    <!-- Wish filter badge: все закупки, созданные из одной заявки -->
    <v-chip v-if="filters.wishId" color="deep-orange" variant="tonal" closable class="mb-3" prepend-icon="mdi-filter"
      @click:close="filters.wishId = null">
      Закупки из заявки #{{ filters.wishId }} ({{ ordersFromWishCount }})
    </v-chip>
  </div>
</template>

<script setup lang="ts">
import { formatMoney } from '@/utils/formatMoney'
import type { OrdersFiltersState } from '@/composables/orders/useOrdersFilters'
import type { FilterPreset, Subsidy } from '@/composables/orders/ordersTypes'

defineProps<{
  filters: OrdersFiltersState
  subsidies: Subsidy[]
  statusItems: { value: string; label: string; color: string }[]
  orderTypeOptions: { label: string; value: string }[]
  contractorsForFilter: any[]
  mobile: boolean
  viewMode: 'table' | 'cards'
  activeFilterCount: number
  filteredSum: number
  savedFilterPresets: FilterPreset[]
  ordersFromWishCount: number
}>()

const emit = defineEmits<{
  'save-preset': []
  'open-columns': []
  'apply-preset': [p: FilterPreset]
  'remove-preset': [name: string]
  'clear-filters': []
  'update:viewMode': [v: 'table' | 'cards']
}>()
</script>
