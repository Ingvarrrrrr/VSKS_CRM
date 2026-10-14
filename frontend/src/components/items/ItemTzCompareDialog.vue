<template>
  <!-- Окно сравнения ТЗ при импорте — план item-tz-description.md, Этап Б
       (владелец, 14.10.2026). Показывается ТОЛЬКО по строкам, где каталожное
       описание и описание из файла оба непусты и различаются (после
       схлопывания пробелов) — см. owner-side фильтр в useItemsImport.ts::
       maybeResolveTzCompare. Выбор по умолчанию — «из файла» (per строке).
       Presentational: parent (useItemsImport.ts) владеет rows/состоянием,
       этот компонент только рендерит и эмитит выбор. -->
  <v-dialog :model-value="modelValue" max-width="900" scrollable
    @update:model-value="(v: boolean) => emit('update:modelValue', v)">
    <v-card>
      <v-card-title class="pa-4 d-flex align-center">
        <v-icon icon="mdi-compare" class="mr-2" />
        Характеристики (ТЗ) отличаются от каталога
        <v-spacer />
        <v-chip size="small" color="primary" variant="tonal">{{ rows.length }}</v-chip>
      </v-card-title>
      <v-divider />
      <v-card-text class="pa-4">
        <v-alert type="info" variant="tonal" density="compact" class="mb-3">
          Каталог товаров общий для всех — загрузка файла меняет только эту заявку/закупку.
        </v-alert>
        <div class="d-flex ga-2 mb-3">
          <v-btn size="small" variant="tonal" @click="setAll('catalog')">Всё из каталога</v-btn>
          <v-btn size="small" variant="tonal" color="primary" @click="setAll('file')">Всё из файла</v-btn>
        </div>
        <div v-for="row in localRows" :key="row.idx" class="mb-4 pb-3" style="border-bottom:1px solid #e0e0e0">
          <div class="font-weight-medium mb-2">{{ row.itemName }}</div>
          <div class="d-flex flex-column flex-md-row ga-3">
            <div class="flex-grow-1" style="min-width:0">
              <div class="text-caption text-medium-emphasis mb-1">В каталоге</div>
              <v-textarea :model-value="row.catalogText" readonly density="compact" variant="outlined"
                hide-details rows="3" max-rows="8" auto-grow />
            </div>
            <div class="flex-grow-1" style="min-width:0">
              <div class="text-caption text-medium-emphasis mb-1">Из файла</div>
              <v-textarea :model-value="row.fileText" readonly density="compact" variant="outlined"
                hide-details rows="3" max-rows="8" auto-grow />
            </div>
          </div>
          <v-btn-toggle v-model="row.choice" mandatory density="compact" color="primary" class="mt-2">
            <v-btn value="catalog" size="small" style="text-transform:none;letter-spacing:0">оставить из каталога</v-btn>
            <v-btn value="file" size="small" style="text-transform:none;letter-spacing:0">взять из файла (только в эту заявку)</v-btn>
          </v-btn-toggle>
        </div>
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="emit('cancel')">Отмена</v-btn>
        <v-btn color="primary" variant="flat" @click="confirm">Продолжить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

export interface TzCompareRow {
  idx: number
  itemName: string
  catalogText: string
  fileText: string
  choice: 'catalog' | 'file'
}

const props = defineProps<{
  modelValue: boolean
  rows: TzCompareRow[]
}>()

const emit = defineEmits<{
  'update:modelValue': [v: boolean]
  confirm: [rows: TzCompareRow[]]
  cancel: []
}>()

// Локальная копия — правим choice без мутации пропа напрямую (Vue best practice).
const localRows = ref<TzCompareRow[]>(props.rows.map(r => ({ ...r })))
watch(() => props.rows, (v) => { localRows.value = v.map(r => ({ ...r })) })

function setAll(choice: 'catalog' | 'file') {
  for (const r of localRows.value) r.choice = choice
}

function confirm() {
  emit('confirm', localRows.value.map(r => ({ ...r })))
}
</script>
