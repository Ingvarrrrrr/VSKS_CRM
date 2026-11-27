<template>
  <div class="spreadsheet-source-input">
    <div class="d-flex align-center justify-space-between mb-3">
      <v-btn-toggle
        :model-value="sourceMode"
        @update:model-value="$emit('update:sourceMode', $event)"
        mandatory
        density="compact"
        color="primary"
        variant="outlined"
        class="mb-0"
      >
        <v-btn value="file" prepend-icon="mdi-file-excel-outline" size="small">Файл Excel</v-btn>
        <v-btn value="url" prepend-icon="mdi-link-variant" size="small">Ссылка (Google / Яндекс)</v-btn>
      </v-btn-toggle>
    </div>

    <!-- File mode -->
    <v-file-input
      v-if="sourceMode === 'file'"
      :model-value="fileList"
      @update:model-value="$emit('update:fileList', $event)"
      :label="fileLabel"
      :accept="accept"
      variant="outlined"
      density="compact"
      clearable
      prepend-icon="mdi-file-excel"
      class="mb-3"
    />

    <!-- URL mode -->
    <div v-else class="mb-3">
      <div class="d-flex ga-2 align-start">
        <v-text-field
          :model-value="sourceUrl"
          @update:model-value="$emit('update:sourceUrl', $event)"
          label="Ссылка на таблицу (Google Sheets / Яндекс Диск)"
          placeholder="https://docs.google.com/spreadsheets/d/... или https://disk.yandex.ru/..."
          variant="outlined"
          density="compact"
          clearable
          prepend-inner-icon="mdi-link"
          class="flex-grow-1"
          @keyup.enter="$emit('load-sheets', true)"
        />
        <v-btn
          color="primary"
          variant="tonal"
          size="small"
          height="40"
          :loading="loading"
          :disabled="!sourceUrl"
          prepend-icon="mdi-download-network-outline"
          @click="$emit('load-sheets', true)"
        >
          Загрузить листы
        </v-btn>
      </div>
      <div class="text-caption text-medium-emphasis mt-1">
        Откройте доступ «Все, у кого есть ссылка — Читатель» (Google) или публичную ссылку (Яндекс Диск / Яндекс Таблицы).
      </div>
    </div>

    <!-- Header row selection (optional, shown after workbook is loaded when showHeaderRow=true) -->
    <v-row v-if="showHeaderRow" dense class="align-center">
      <v-col cols="12" sm="6">
        <v-text-field
          :model-value="headerRow ?? ''"
          @update:model-value="(val) => $emit('update:headerRow', val ? Number(val) : null)"
          type="number"
          min="1"
          max="50"
          clearable
          density="compact"
          variant="outlined"
          label="Строка с названиями колонок"
          placeholder="Авто"
          :hint="headerRowHint"
          persistent-hint
        />
      </v-col>
    </v-row>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  sourceMode: 'file' | 'url'
  fileList: File[] | File | null
  sourceUrl: string
  headerRow: number | null
  detectedHeaderRow: number | null
  loading?: boolean
  fileLabel?: string
  accept?: string
  showHeaderRow?: boolean
}>(), {
  showHeaderRow: true,
})

defineEmits<{
  (e: 'update:sourceMode', val: 'file' | 'url'): void
  (e: 'update:fileList', val: File[] | File | null): void
  (e: 'update:sourceUrl', val: string): void
  (e: 'update:headerRow', val: number | null): void
  (e: 'load-sheets', forceRefresh: boolean): void
}>()

const headerRowHint = computed(() => {
  if (props.detectedHeaderRow) {
    return `Автоматически определена строка ${props.detectedHeaderRow}. Укажите вручную (например, 3), если шапка ниже.`
  }
  return 'Оставьте пустым для автоопределения или укажите номер строки (например, 3)'
})
</script>
