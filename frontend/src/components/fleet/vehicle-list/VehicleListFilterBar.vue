<template>
  <v-card class="mb-4" variant="outlined">
    <v-card-text class="py-3">
      <div class="d-flex align-center gap-4 flex-wrap">
        <v-select
          :model-value="filterStates"
          :items="stateOptions"
          item-title="label"
          item-value="value"
          label="Состояние"
          variant="outlined"
          density="compact"
          multiple
          chips
          closable-chips
          clearable
          hide-details
          style="min-width:200px"
          @update:model-value="emit('update:filterStates', $event)"
        />
        <v-select
          :model-value="filterTypes"
          :items="typeOptions"
          item-title="label"
          item-value="value"
          label="Тип ТС"
          variant="outlined"
          density="compact"
          multiple
          chips
          closable-chips
          clearable
          hide-details
          style="min-width:200px"
          @update:model-value="emit('update:filterTypes', $event)"
        />
        <v-select
          :model-value="filterFuelTypes"
          :items="fuelTypeOptions"
          item-title="label"
          item-value="value"
          label="Топливо"
          variant="outlined"
          density="compact"
          multiple
          chips
          closable-chips
          clearable
          hide-details
          style="min-width:180px"
          @update:model-value="emit('update:filterFuelTypes', $event)"
        />
        <v-autocomplete
          :model-value="filterOwnerOrgIds"
          :items="orgsList"
          item-title="name"
          item-value="id"
          label="Владелец"
          variant="outlined"
          density="compact"
          multiple
          chips
          closable-chips
          clearable
          hide-details
          style="min-width:220px"
          @update:model-value="emit('update:filterOwnerOrgIds', $event)"
        />
        <v-autocomplete
          :model-value="filterAssignedOrgIds"
          :items="orgsList"
          item-title="name"
          item-value="id"
          label="Эксплуатант"
          variant="outlined"
          density="compact"
          multiple
          chips
          closable-chips
          clearable
          hide-details
          style="min-width:220px"
          @update:model-value="emit('update:filterAssignedOrgIds', $event)"
        />
        <v-text-field
          :model-value="filterSearch"
          prepend-inner-icon="mdi-magnify"
          label="Поиск (гос.№, марка, VIN)"
          variant="outlined"
          density="compact"
          clearable
          hide-details
          style="min-width:220px"
          @update:model-value="emit('update:filterSearch', $event)"
        />
        <v-btn
          size="small" variant="tonal" color="primary"
          prepend-icon="mdi-bookmark-plus-outline"
          @click="emit('save-preset')">
          Сохранить фильтр
        </v-btn>
        <v-btn variant="tonal" prepend-icon="mdi-view-column" size="small" @click="emit('open-columns')">Колонки</v-btn>
        <v-tooltip text="Сбросить настройки колонок" location="top">
          <template #activator="{ props: tooltipProps }">
            <v-btn v-bind="tooltipProps" variant="text" size="small" icon="mdi-restore" @click="emit('reset-columns')" />
          </template>
        </v-tooltip>
        <v-chip
          v-if="activeFiltersCount > 0"
          color="deep-orange" variant="tonal" size="small"
          prepend-icon="mdi-filter-multiple"
          class="ml-1"
          closable
          @click:close="emit('clear-all')">
          Фильтры {{ activeFiltersCount }}
        </v-chip>
      </div>

      <!-- Saved presets -->
      <div v-if="savedFilterPresets.length" class="d-flex align-center gap-2 flex-wrap mt-2">
        <span class="text-caption text-medium-emphasis">Пресеты:</span>
        <v-chip
          v-for="preset in savedFilterPresets" :key="preset.name"
          size="small" variant="tonal" color="primary"
          class="vlist-fb-preset-chip"
          @click="emit('apply-preset', preset)">
          {{ preset.name }}
          <v-icon icon="mdi-close" size="12" class="ml-1" @click.stop="emit('remove-preset', preset.name)" />
        </v-chip>
      </div>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
import type { FilterPreset, OrgItem } from '@/composables/fleet/vehicle-list/vehicleListTypes'

defineProps<{
  filterStates: string[]
  filterTypes: string[]
  filterFuelTypes: string[]
  filterOwnerOrgIds: number[]
  filterAssignedOrgIds: number[]
  filterSearch: string
  stateOptions: { value: string; label: string }[]
  typeOptions: { value: string; label: string }[]
  fuelTypeOptions: { value: string; label: string }[]
  orgsList: OrgItem[]
  activeFiltersCount: number
  savedFilterPresets: FilterPreset[]
}>()

const emit = defineEmits<{
  (e: 'update:filterStates', value: string[]): void
  (e: 'update:filterTypes', value: string[]): void
  (e: 'update:filterFuelTypes', value: string[]): void
  (e: 'update:filterOwnerOrgIds', value: number[]): void
  (e: 'update:filterAssignedOrgIds', value: number[]): void
  (e: 'update:filterSearch', value: string): void
  (e: 'save-preset'): void
  (e: 'open-columns'): void
  (e: 'reset-columns'): void
  (e: 'clear-all'): void
  (e: 'apply-preset', preset: FilterPreset): void
  (e: 'remove-preset', name: string): void
}>()
</script>

<style scoped>
.vlist-fb-preset-chip {
  cursor: pointer;
}
</style>
