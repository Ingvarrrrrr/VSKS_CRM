<template>
  <v-card class="mb-4" variant="outlined" rounded="lg">
    <v-card-text class="py-2 px-3">
      <div class="d-flex align-center gap-1 mb-2">
        <v-icon size="16" color="grey">mdi-filter</v-icon>
        <span class="text-caption font-weight-medium text-medium-emphasis">ФИЛЬТРЫ (мульти-выбор)</span>
        <v-spacer />
        <v-chip color="primary" variant="tonal" prepend-icon="mdi-cash-multiple" size="small" class="mr-2">
          Сумма: {{ formatMoneyUtil(filteredSum) }}
        </v-chip>
        <v-btn v-if="hasFilters" variant="text" size="x-small" color="error" prepend-icon="mdi-filter-remove" @click="emit('clear-filters')">
          Сбросить все
        </v-btn>
        <v-chip
          v-if="cfgActiveFilterCount > 0"
          color="info" variant="tonal" size="small"
          prepend-icon="mdi-filter-check"
          class="ml-1"
        >
          Фильтры {{ cfgActiveFilterCount }}
          <v-btn
            icon="mdi-close"
            size="x-small"
            variant="text"
            class="ml-1"
            @click="emit('clear-column-filters')"
          />
        </v-chip>
      </div>
      <div class="d-flex flex-wrap gap-2">

        <!-- Поиск по договорам (номер, контрагент, ИНН, субсидия, предмет, примечания) -->
        <v-text-field
          v-model="search"
          label="Поиск"
          prepend-inner-icon="mdi-magnify"
          variant="outlined" density="compact" hide-details clearable
          style="min-width:220px; max-width:300px"
          placeholder="Номер, контрагент, ИНН, предмет..."
        />

        <!-- Субсидия -->
        <v-autocomplete
          v-model="fSubsidy"
          :items="usedSubsidies"
          item-title="name" item-value="id"
          label="Субсидия" multiple chips closable-chips
          variant="outlined" density="compact" hide-details clearable
          style="min-width:200px; max-width:280px"
        />

        <!-- Тип документа -->
        <v-autocomplete
          v-model="fType"
          :items="usedContractTypes"
          item-title="label" item-value="value"
          label="Тип документа" multiple chips closable-chips
          variant="outlined" density="compact" hide-details clearable
          style="min-width:200px; max-width:300px"
        />

        <!-- Способ закупки -->
        <v-autocomplete
          v-model="fMethod"
          :items="usedPurchaseMethods"
          item-title="label" item-value="value"
          label="Способ закупки" multiple chips closable-chips
          variant="outlined" density="compact" hide-details clearable
          style="min-width:180px; max-width:240px"
        />

        <!-- Контрагент -->
        <v-autocomplete
          v-model="fContractor"
          :items="usedContractors"
          item-title="name" item-value="id"
          label="Контрагент" multiple chips closable-chips
          variant="outlined" density="compact" hide-details clearable
          style="min-width:200px; max-width:300px"
        />

        <!-- Поиск по товару -->
        <v-text-field
          v-model="fProduct"
          label="Поиск товара"
          prepend-inner-icon="mdi-magnify"
          variant="outlined" density="compact" hide-details clearable
          style="min-width:200px; max-width:280px"
          placeholder="Название товара..."
        />

        <!-- Дата от/до -->
        <v-text-field
          v-model="fDateFrom"
          label="Дата от" type="date"
          variant="outlined" density="compact" hide-details clearable
          style="min-width:145px; max-width:145px"
        />
        <v-text-field
          v-model="fDateTo"
          label="Дата до" type="date"
          variant="outlined" density="compact" hide-details clearable
          style="min-width:145px; max-width:145px"
        />

      </div>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
import { formatMoney as formatMoneyUtil } from '@/utils/formatMoney'
import type { Subsidy, Contractor } from '@/composables/contracts/contractsTypes'

const search = defineModel<string>('search', { required: true })
const fSubsidy = defineModel<number[]>('fSubsidy', { required: true })
const fType = defineModel<string[]>('fType', { required: true })
const fMethod = defineModel<string[]>('fMethod', { required: true })
const fContractor = defineModel<number[]>('fContractor', { required: true })
const fProduct = defineModel<string>('fProduct', { required: true })
const fDateFrom = defineModel<string>('fDateFrom', { required: true })
const fDateTo = defineModel<string>('fDateTo', { required: true })

defineProps<{
  usedSubsidies: Subsidy[]
  usedContractTypes: { value: string; label: string }[]
  usedPurchaseMethods: { value: string; label: string }[]
  usedContractors: Contractor[]
  filteredSum: number
  hasFilters: boolean
  cfgActiveFilterCount: number
}>()

const emit = defineEmits<{
  'clear-filters': []
  'clear-column-filters': []
}>()
</script>
