<template>
  <!-- Stale parsed alert: записи где parsed_contract_number совпадает с номером субсидии -->
  <v-alert
    v-if="hasStaleParsed"
    type="warning"
    variant="tonal"
    closable
    density="compact"
    class="mb-3"
    @click:close="emit('dismiss-stale')"
  >
    В реестре есть записи где номер субсидии попал в колонку «Договор (авто)».
    Откройте импорт → нажмите «Перепарсить» для исправления.
  </v-alert>

  <!-- Filters -->
  <v-card class="mb-4" variant="outlined" rounded="lg">
    <v-card-text class="py-2 px-3">
      <div class="d-flex align-center gap-1 mb-2">
        <v-icon size="16" color="grey">mdi-filter</v-icon>
        <span class="text-caption font-weight-medium text-medium-emphasis">ФИЛЬТРЫ</span>
        <v-spacer />
        <!-- Import badge -->
        <v-chip
          v-if="importId"
          size="small"
          color="blue"
          variant="tonal"
          closable
          @click:close="emit('clear-import')"
        >Фильтр: Импорт #{{ importId }}</v-chip>
        <v-chip
          v-if="activeFilterCount > 0"
          size="small"
          color="primary"
          variant="tonal"
          prepend-icon="mdi-filter-check"
        >Фильтры {{ activeFilterCount }}</v-chip>
        <v-btn v-if="hasFilters" variant="text" size="x-small" color="error" prepend-icon="mdi-filter-remove" @click="emit('clear-filters')">
          Сбросить
        </v-btn>
      </div>
      <div class="d-flex flex-wrap gap-2 align-end">
        <v-text-field
          v-model="searchQuery"
          prepend-inner-icon="mdi-magnify"
          label="Поиск по любому полю"
          variant="outlined"
          density="compact"
          hide-details
          clearable
          style="min-width:220px; max-width:340px"
        />
        <v-select
          v-model="filterSubsidyId"
          :items="subsidiesList"
          item-title="name"
          item-value="id"
          label="Субсидия"
          variant="outlined"
          density="compact"
          hide-details
          clearable
          style="min-width:180px; max-width:260px"
        />
        <v-text-field
          v-model="fDateFrom"
          label="Дата от"
          type="date"
          variant="outlined"
          density="compact"
          hide-details
          clearable
          style="min-width:145px; max-width:145px"
        />
        <v-text-field
          v-model="fDateTo"
          label="Дата до"
          type="date"
          variant="outlined"
          density="compact"
          hide-details
          clearable
          style="min-width:145px; max-width:145px"
        />
        <v-select
          v-model="fStatus"
          :items="statusOptions"
          item-title="label"
          item-value="value"
          label="Статус"
          variant="outlined"
          density="compact"
          hide-details
          clearable
          style="min-width:160px; max-width:200px"
        />
        <v-select
          v-model="fMatched"
          :items="yesNoOptions"
          item-title="label"
          item-value="value"
          label="Сматчено"
          variant="outlined"
          density="compact"
          hide-details
          clearable
          style="min-width:160px; max-width:200px"
        />
        <v-select
          v-model="fConfirmed"
          :items="yesNoOptions"
          item-title="label"
          item-value="value"
          label="Подтверждено"
          variant="outlined"
          density="compact"
          hide-details
          clearable
          style="min-width:165px; max-width:200px"
        />
        <v-text-field
          v-model="fInn"
          label="ИНН получателя"
          variant="outlined"
          density="compact"
          hide-details
          clearable
          style="min-width:160px; max-width:200px"
          @keyup.enter="emit('apply')"
        />
        <v-select
          v-model="fDisposition"
          :items="dispositionOptions"
          item-title="label"
          item-value="value"
          label="Разнесение"
          variant="outlined"
          density="compact"
          hide-details
          clearable
          style="min-width:190px; max-width:230px"
        />
        <v-btn color="primary" variant="elevated" @click="emit('apply')" :loading="loading">
          Применить
        </v-btn>
        <v-chip color="primary" variant="tonal" prepend-icon="mdi-cash-multiple" size="small" class="ml-2">
          Сумма: {{ formatMoney(filteredSum) }}
        </v-chip>
      </div>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
import { formatMoney } from '@/composables/payments/paymentsFormat'
import { statusOptions, yesNoOptions, dispositionOptions, type SubsidyItem } from '@/composables/payments/usePaymentsFilters'

const searchQuery = defineModel<string>('searchQuery', { required: true })
const filterSubsidyId = defineModel<number | null>('filterSubsidyId', { required: true })
const fDateFrom = defineModel<string>('fDateFrom', { required: true })
const fDateTo = defineModel<string>('fDateTo', { required: true })
const fStatus = defineModel<string | null>('fStatus', { required: true })
const fMatched = defineModel<string | null>('fMatched', { required: true })
const fConfirmed = defineModel<string | null>('fConfirmed', { required: true })
const fInn = defineModel<string>('fInn', { required: true })
const fDisposition = defineModel<string | null>('fDisposition', { required: true })

defineProps<{
  hasStaleParsed: boolean
  importId: number | null
  activeFilterCount: number
  hasFilters: boolean
  loading: boolean
  filteredSum: number
  subsidiesList: SubsidyItem[]
}>()

const emit = defineEmits<{
  'dismiss-stale': []
  'clear-import': []
  'clear-filters': []
  apply: []
}>()
</script>
