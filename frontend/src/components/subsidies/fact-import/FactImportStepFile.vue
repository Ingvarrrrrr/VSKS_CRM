<template>
  <v-alert type="info" variant="tonal" density="compact" class="mb-3" icon="mdi-information-outline">
    Загрузите файл учёта закупок (Excel) — тот же, по которому ведётся субсидия.
    План в GALA этот шаг не меняет, он только привязывает уже совершённые
    закупки к плановым позициям.
    <div class="mt-2 d-flex flex-wrap ga-2">
      <v-btn size="small" variant="text" color="primary" prepend-icon="mdi-download-outline" @click="downloadTemplate('single')">
        Шаблон: статус одной колонкой
      </v-btn>
      <v-btn size="small" variant="text" color="primary" prepend-icon="mdi-download-outline" @click="downloadTemplate('stages')">
        Шаблон: статусы по колонкам Да/Нет (как GoodsService)
      </v-btn>
    </div>
    <div class="text-caption text-medium-emphasis mt-1">
      Загрузка понимает оба формата — какой шаблон ни скачайте, система сама распознает его при загрузке файла.
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

const { factImport, loadSheets, loadPreview, downloadTemplate, resetForSourceChange } = useFactImport()
const fileList = ref<File[]>([])

async function onFilePicked(files: File | File[] | null) {
  const file = Array.isArray(files) ? (files[0] ?? null) : (files ?? null)
  factImport.file = file
  factImport.sheets = []
  factImport.selectedSheet = null
  // Багфикс 20.10.2026: новый файл — старый mapping/preview от предыдущего
  // файла не имеет смысла для его заголовков (иначе карточки на шаге 2
  // сдвинуты, см. useFactImport.ts::resetForSourceChange).
  resetForSourceChange()
  if (file) await loadSheets()
}

async function onSheetChange(name: string) {
  factImport.selectedSheet = name
  // Багфикс 20.10.2026: смена листа — ПЕРЕД новым предпросмотром сбрасываем
  // mapping, иначе loadPreview() видит непустой mapping (построенный по
  // ПЕРВОМУ листу в loadSheets()) и накладывает его индексы на заголовки
  // другого листа.
  resetForSourceChange()
  await loadPreview()
}
</script>
