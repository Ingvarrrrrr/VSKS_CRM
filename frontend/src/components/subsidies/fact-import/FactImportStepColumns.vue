<template>
  <v-alert type="info" variant="tonal" density="compact" class="mb-3">
    Колонки подобраны автоматически — проверьте и перетащите карточки, если
    что-то распознано неверно.
  </v-alert>
  <ImportMappingGrid
    :headers="headers"
    :sample-rows="sampleRows"
    :target-fields="FACT_IMPORT_TARGET_FIELDS"
    :model-value="factImport.mapping"
    @update:model-value="onMappingChange"
  />
  <v-alert v-if="!mappingValid" type="warning" density="compact" icon="mdi-alert" class="mt-3">
    Сопоставьте столбец «Наименование плановой позиции» — без него строки не сопоставятся с планом.
  </v-alert>
</template>

<script setup lang="ts">
// Тонкая обёртка над общим ImportMappingGrid.vue (ПРАВИЛО №6 — тот же
// компонент, что и мастер ФЭО/импорт товаров), см. FeoImportMappingStep.vue.
import { computed } from 'vue'
import ImportMappingGrid from '@/components/common/ImportMappingGrid.vue'
import { useFactImport, FACT_IMPORT_TARGET_FIELDS } from '@/composables/subsidies/useFactImport'

const { factImport, mappingValid, queuePreviewRefresh } = useFactImport()

// preview.columns несёт заголовки + образцы (по строкам предпросмотра у нас
// нет «сырых» ячеек — используем названия строк как подсказку образца,
// за отсутствием отдельного сэмпла с бэкенда на этом шаге).
const headers = computed(() => (factImport.preview?.columns || []).map(c => c.header))
const sampleRows = computed(() => [] as any[][])

// 🔵 правка 3: тот же debounce (queuePreviewRefresh) — перетаскивание
// нескольких карточек подряд не шлёт файл на каждое перетаскивание.
function onMappingChange(v: Record<string, number | null>) {
  factImport.mapping = v
  factImport.groupsDirty = false
  queuePreviewRefresh()
}
</script>
