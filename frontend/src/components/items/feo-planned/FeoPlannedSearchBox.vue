<template>
  <!-- Поиск по ВСЕМ плановым позициям субсидии (владелец, 2026-09-16, дефект 1/3):
       v-autocomplete — и поле ввода, и выпадающий список одновременно (жалоба:
       «тыкаю в поле — список, но НЕТ поля для ввода»), без v-model на постоянное
       значение (это поиск-действие, не хранимый выбор — после клика по варианту
       поле очищается, см. onSelect). -->
  <v-autocomplete
    :model-value="null"
    :search="searchText"
    @update:search="onUpdateSearch"
    :items="rows"
    item-title="name"
    item-value="key"
    :loading="loading"
    :disabled="readonly"
    density="compact"
    variant="outlined"
    clearable
    hide-no-data
    hide-details
    no-filter
    placeholder="Поиск по всем плановым позициям субсидии…"
    prepend-inner-icon="mdi-magnify"
    class="feo-planned-search-box mb-2"
    :menu-props="{ maxHeight: 360 }"
    @update:model-value="onSelectKey"
  >
    <template #item="{ item, props: itemProps }">
      <v-list-item v-bind="itemProps" :title="undefined">
        <div class="d-flex align-center ga-2 flex-wrap">
          <span class="text-body-2">{{ item.raw.name }}</span>
          <v-chip v-if="item.raw.score >= 0.999" size="x-small" color="success" variant="tonal">точное совпадение</v-chip>
          <v-chip v-else-if="item.raw.score >= 0.6" size="x-small" color="amber" variant="tonal">похоже, {{ Math.round(item.raw.score * 100) }}%</v-chip>
          <v-chip v-if="item.raw.crossCategory" size="x-small" color="warning" variant="tonal">другая категория</v-chip>
        </div>
        <div class="text-caption text-medium-emphasis">
          <template v-if="item.raw.crossCategory">{{ item.raw.path }} — выбор перенесёт позицию в эту категорию · </template>
          остаток {{ fmt(item.raw.residual) }}
        </div>
      </v-list-item>
    </template>
  </v-autocomplete>
</template>

<script setup lang="ts">
import type { FeoPlannedSearchRow } from '@/composables/items/feoPlanned/useFeoPlannedSearch'

const searchText = defineModel<string>('searchText', { default: '' })

const props = defineProps<{
  rows: FeoPlannedSearchRow[]
  loading?: boolean
  readonly?: boolean
  fmt: (v: number | null | undefined) => string
}>()

const emit = defineEmits<{
  select: [row: FeoPlannedSearchRow]
}>()

function onUpdateSearch(v: string) {
  searchText.value = v
}

function onSelectKey(key: string | null) {
  if (!key) return
  const row = props.rows.find(r => r.key === key)
  if (row) emit('select', row)
}
</script>

<style scoped>
.feo-planned-search-box :deep(.v-field__input) {
  min-height: 36px;
  padding-top: 4px;
  padding-bottom: 4px;
}
</style>
