<template>
  <v-alert type="info" variant="tonal" density="compact" class="mb-3" icon="mdi-information-outline">
    Загрузите файл учёта закупок (Excel) — тот же, по которому ведётся субсидия.
    План в GALA этот шаг не меняет, он только привязывает уже совершённые
    закупки к плановым позициям.
    <div class="mt-2">
      <v-btn size="small" variant="text" color="primary" prepend-icon="mdi-download-outline" @click="downloadTemplate">
        Скачать шаблон
      </v-btn>
    </div>
  </v-alert>
  <v-file-input
    v-model="fileList"
    label="Файл Excel (.xlsx, .xls)"
    accept=".xlsx,.xls"
    variant="outlined" density="compact"
    prepend-icon="mdi-file-excel"
    show-size
    :loading="factImport.loading"
    @update:model-value="onFilePicked"
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

const { factImport, loadSheets, loadPreview, downloadTemplate } = useFactImport()
const fileList = ref<File[]>([])

async function onFilePicked(files: File | File[] | null) {
  const file = Array.isArray(files) ? (files[0] ?? null) : (files ?? null)
  factImport.file = file
  factImport.sheets = []
  factImport.selectedSheet = null
  factImport.preview = null
  if (file) await loadSheets()
}

async function onSheetChange(name: string) {
  factImport.selectedSheet = name
  await loadPreview()
}
</script>
