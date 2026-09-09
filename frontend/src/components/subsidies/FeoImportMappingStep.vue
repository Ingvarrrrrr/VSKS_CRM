<template>
  <!-- Step 2: Column mapping — вынесен из FeoImportWizard.vue отдельным
       подкомпонентом (файл мастера целиком превышал 600 строк, см. задание
       волны 5a-2). Состояние — тот же singleton useFeoImport.ts, что и у
       родителя (FeoImportWizard.vue) — не копия. Сама сетка сопоставления —
       общий ImportMappingGrid.vue (план dreamy-booping-piglet.md, задача B,
       п.5): drag&drop, подсветка обязательных полей и «Не определилось»
       теперь живут в одном месте для мастера ФЭО и мастера импорта товаров,
       поведение этого шага не менялось — только рендер сетки вынесен. -->
  <v-alert v-if="feoCurrentSheet" type="info" variant="tonal" density="compact" class="mb-3" icon="mdi-file-table-outline">
    <strong>Лист:</strong> {{ feoCurrentSheet.name }} ({{ feoCurrentSheet.total_rows }} строк данных)
  </v-alert>
  <v-select
    v-if="feoImport.previewData.sheets.length > 1"
    v-model="feoImport.selectedSheet"
    :items="feoImport.previewData.sheets.map((s: any) => ({ title: `${s.name} (${s.total_rows} строк)`, value: s.name }))"
    label="Сменить лист" variant="outlined" density="compact" class="mb-3"
    @update:model-value="feoAutoMap(feoCurrentSheet?.headers || [])"
  />
  <v-select
    v-model="feoImportTargetSubsidy"
    :items="allSubsidies"
    item-title="name" item-value="id"
    label="Субсидия назначения (для строк без столбца «Субсидия»)"
    variant="outlined" density="compact" clearable class="mb-3"
    hint="Если в файле колонка «Субсидия» пустая — все строки будут отнесены к выбранной субсидии"
    persistent-hint />

  <ImportMappingGrid
    :headers="feoCurrentHeaders"
    :sample-rows="feoCurrentSheet?.sample || []"
    :target-fields="feoTargetFields"
    :model-value="feoDragMapping"
    :ignored-columns="feoIgnoredCols"
    @update:model-value="v => feoDragMapping = v"
    @update:ignored-columns="v => feoIgnoredCols = v"
  />

  <v-alert v-if="!feoMappingValid" type="warning" density="compact" icon="mdi-alert" class="mt-3">
    Укажите столбцы «Субсидия» и «Уровень 2 / Направление»
  </v-alert>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import ImportMappingGrid from '@/components/common/ImportMappingGrid.vue'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { useFeoImport } from '@/composables/subsidies/useFeoImport'

const {
  feoImport, feoImportTargetSubsidy, FEO_TARGET_FIELDS, feoDragMapping, feoIgnoredCols,
  feoCurrentSheet, feoCurrentHeaders, feoMappingValid, feoAutoMap, allSubsidies,
} = useFeoImport(useSubsidyDetailCtx())

// ImportMappingGrid ожидает {key,label,required,hint}; FEO_TARGET_FIELDS хранит
// {value,title,required} — маппинг имён полей, поведение автоподбора и
// валидации не тронуто (живёт в useFeoImport.ts).
const feoTargetFields = computed(() =>
  FEO_TARGET_FIELDS.map((f: any) => ({ key: f.value, label: f.title, required: f.required }))
)
</script>
