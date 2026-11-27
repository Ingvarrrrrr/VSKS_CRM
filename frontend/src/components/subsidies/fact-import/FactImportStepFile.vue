<template>
  <v-alert type="info" variant="tonal" density="compact" class="mb-3" icon="mdi-information-outline">
    Загрузите файл учёта закупок (Excel) — тот же, по которому ведётся субсидия.
    План в GALA этот шаг не меняет, он только привязывает уже совершённые
    закупки к плановым позициям.
    <div class="mt-2 d-flex flex-wrap ga-2">
      <v-btn size="small" variant="text" color="primary" prepend-icon="mdi-download-outline" @click="downloadUnifiedTemplate(factImport.subsidyId)">
        Скачать единый шаблон (.xlsx)
      </v-btn>
    </div>
    <div class="text-caption text-medium-emphasis mt-1">
      Используйте единый шаблон для одновременного заполнения плана и факта.
    </div>
  </v-alert>

  <SpreadsheetSourceInput
    v-model:sourceMode="factImport.sourceMode"
    v-model:fileList="fileList"
    v-model:sourceUrl="factImport.sourceUrl"
    v-model:headerRow="factImport.headerRow"
    :detectedHeaderRow="factImport.detectedHeaderRow"
    :loading="factImport.loading"
    fileLabel="Файл Excel (.xlsx, .xls)"
    accept=".xlsx,.xls"
    @load-sheets="onLoadSheets"
    @update:sourceMode="onSourceModeChange"
    @update:fileList="onFilePicked"
    @update:headerRow="onHeaderRowChange"
  />

  <v-select
    v-if="factImport.sheets.length > 1"
    :model-value="factImport.selectedSheet"
    :items="factImport.sheets.map(s => ({ title: `${s.name} (${s.rows} строк)`, value: s.name }))"
    label="Лист" variant="outlined" density="compact" class="mt-2"
    @update:model-value="onSheetChange"
  />

  <v-alert v-if="factImport.preview?.warnings?.length" type="warning" variant="tonal" density="compact" class="mt-3">
    <div v-for="(w, i) in factImport.preview.warnings" :key="i">{{ w }}</div>
  </v-alert>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useFactImport } from '@/composables/subsidies/useFactImport'
import SpreadsheetSourceInput from '@/components/common/SpreadsheetSourceInput.vue'

const { factImport, loadSheets, loadPreview, downloadUnifiedTemplate, resetForSourceChange } = useFactImport()
const fileList = ref<File[] | File | null>(null)

function onSourceModeChange() {
  resetForSourceChange()
  factImport.sheets = []
  factImport.selectedSheet = null
}

async function onFilePicked(files: File | File[] | null) {
  const file = Array.isArray(files) ? (files[0] ?? null) : (files ?? null)
  factImport.file = file
  factImport.sheets = []
  factImport.selectedSheet = null
  resetForSourceChange()
  if (file) await loadSheets()
}

async function onLoadSheets(forceRefresh = false) {
  resetForSourceChange()
  await loadSheets(forceRefresh)
}

async function onHeaderRowChange() {
  resetForSourceChange()
  if (factImport.sourceMode === 'url' && factImport.sourceUrl) {
    await loadSheets(true)
  } else if (factImport.sourceMode === 'file' && factImport.file) {
    await loadPreview()
  }
}

async function onSheetChange(name: string) {
  factImport.selectedSheet = name
  resetForSourceChange()
  await loadPreview()
}
</script>
