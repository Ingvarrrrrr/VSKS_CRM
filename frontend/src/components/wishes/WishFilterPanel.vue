<template>
  <!-- ── FILTER PANEL (общий для всех табов) ── -->
  <v-card variant="outlined" class="mb-4">
    <v-card-text class="py-3">
      <div class="d-flex flex-wrap align-center" style="gap:12px">
        <v-autocomplete
          v-if="ctx.isSaas.value"
          v-model="filters.accountId"
          :items="accountOptions"
          item-title="name"
          item-value="id"
          label="Аккаунт"
          variant="outlined"
          density="compact"
          clearable
          hide-details
          style="min-width:200px;max-width:260px"
        />
        <v-autocomplete
          v-if="ctx.isSaas.value"
          v-model="filters.orgId"
          :items="orgOptionsFiltered"
          item-title="name"
          item-value="id"
          label="Организация"
          variant="outlined"
          density="compact"
          clearable
          hide-details
          style="min-width:200px;max-width:260px"
        />
        <v-autocomplete
          v-model="filters.subsidyId"
          :items="ctx.subsidies.value"
          item-title="name"
          item-value="id"
          label="Субсидия"
          variant="outlined"
          density="compact"
          clearable
          hide-details
          style="min-width:220px;max-width:280px"
        />
        <v-autocomplete
          v-model="filters.creatorId"
          :items="ctx.users.value"
          item-title="full_name"
          item-value="id"
          label="От кого"
          variant="outlined"
          density="compact"
          clearable
          hide-details
          style="min-width:200px;max-width:240px"
        />
        <v-autocomplete
          v-model="filters.assignedToId"
          :items="ctx.users.value"
          item-title="full_name"
          item-value="id"
          label="Кому"
          variant="outlined"
          density="compact"
          clearable
          hide-details
          style="min-width:200px;max-width:240px"
        />
        <v-text-field
          v-model="filters.createdFrom"
          type="date"
          label="Создано с"
          variant="outlined"
          density="compact"
          clearable
          hide-details
          style="min-width:150px;max-width:180px"
        />
        <v-text-field
          v-model="filters.createdTo"
          type="date"
          label="Создано по"
          variant="outlined"
          density="compact"
          clearable
          hide-details
          style="min-width:150px;max-width:180px"
        />
        <v-text-field
          v-model="filters.deadlineFrom"
          type="date"
          label="Срок с"
          variant="outlined"
          density="compact"
          clearable
          hide-details
          style="min-width:150px;max-width:180px"
        />
        <v-text-field
          v-model="filters.deadlineTo"
          type="date"
          label="Срок по"
          variant="outlined"
          density="compact"
          clearable
          hide-details
          style="min-width:150px;max-width:180px"
        />
        <v-btn variant="tonal" size="small" prepend-icon="mdi-filter-off" @click="resetFilters">
          Очистить фильтры
        </v-btn>
      </div>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
// WishFilterPanel.vue — общая панель фильтров для трёх вкладок заявок («Мои» /
// «На согласование мне» / «Заявки сотрудников»). Дословный перенос шаблона из
// WishesView.vue (см. useWishFilters.ts для состояния/buildFilterParams).
import { useWishesContext } from '@/composables/wishes/useWishesContext'
import type { WishFiltersState } from '@/composables/wishes/useWishFilters'

defineProps<{
  filters: WishFiltersState
  accountOptions: { id: number; name: string }[]
  orgOptionsFiltered: { id: number; name: string }[]
  resetFilters: () => void
}>()

const ctx = useWishesContext()
</script>
