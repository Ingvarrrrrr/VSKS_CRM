<template>
  <!-- Задача 2026-09-22: строка файла называет товар/услугу/работу,
       отличную от значения уже сопоставленного товара в каталоге —
       решение по КАЖДОЙ строке принимает человек, тот же стиль блока, что и
       у FeoBudgetConflictGroup/FeoCategorySumConflictGroup в
       FeoImportWizard.vue (шаг 3, предпросмотр). Вынесено отдельным
       компонентом (Правило №5) — FeoImportWizard.vue и так превышал 600
       строк. Состояние — тот же singleton useFeoImport.ts, что и у соседних
       блоков (не копия), см. useFeoImport() ниже. -->
  <v-alert v-if="feoItemTypeConflicts.length" type="warning" variant="tonal" density="compact"
    class="mb-3" icon="mdi-swap-horizontal-bold">
    <div class="text-body-2 mb-2">
      Товар/услуга расходятся с каталогом ({{ feoItemTypeConflicts.length }}) — решите по каждой строке
      или для всех сразу.
    </div>
    <div class="d-flex flex-wrap gap-2 mb-2">
      <v-btn size="small" variant="tonal" @click="feoSetAllItemTypeResolutions('file')">Все из файла</v-btn>
      <v-btn size="small" variant="tonal" @click="feoSetAllItemTypeResolutions('catalog')">Все из каталога</v-btn>
    </div>
    <v-table density="compact" class="feo-itemtype-table">
      <thead>
        <tr>
          <th>№</th>
          <th>Позиция</th>
          <th>В файле</th>
          <th>В каталоге</th>
          <th>Решение</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="c in feoItemTypeConflicts" :key="c.row">
          <td>{{ c.row }}</td>
          <td><span class="feo-wrap-text">{{ c.item_name }}</span></td>
          <td>в файле: {{ c.file_type }}</td>
          <td>в каталоге: {{ c.catalog_type ?? '—' }}<span v-if="c.product_name"> ({{ c.product_name }})</span></td>
          <td>
            <v-btn-toggle
              :model-value="feoItemTypeResolutionFor(c.row)"
              density="compact" variant="outlined" divided
              @update:model-value="(v: 'file' | 'catalog' | null) => feoSetItemTypeResolution(c.row, v)">
              <v-btn value="file" size="x-small">Оставить из файла (обновит каталог)</v-btn>
              <v-btn value="catalog" size="x-small">Оставить из каталога</v-btn>
            </v-btn-toggle>
          </td>
        </tr>
      </tbody>
    </v-table>
    <div class="text-caption text-medium-emphasis mt-2">
      Без выбора возьмём значение из файла, каталог не изменится.
    </div>
  </v-alert>
</template>

<script setup lang="ts">
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { useFeoImport } from '@/composables/subsidies/useFeoImport'

const {
  feoItemTypeConflicts, feoItemTypeResolutionFor, feoSetItemTypeResolution, feoSetAllItemTypeResolutions,
} = useFeoImport(useSubsidyDetailCtx())
</script>

<style scoped>
/* feo-wrap-text — тот же приём переноса длинного текста, что и в
   FeoImportWizard.vue (scoped CSS родителя не достаёт до этого компонента —
   см. её докстринг у .feo-wrap-text, тот же инцидент, свой класс здесь же). */
.feo-wrap-text {
  display: block;
  white-space: normal;
  word-break: break-word;
  line-height: 1.35;
}
.feo-itemtype-table :deep(td),
.feo-itemtype-table :deep(th) {
  white-space: normal;
  vertical-align: middle;
}
</style>
