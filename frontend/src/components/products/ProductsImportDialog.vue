<template>
  <v-dialog v-model="wizard.importDialog.show" max-width="900" persistent :fullscreen="mobile">
    <v-card>
      <v-card-title class="text-h6 pt-4 px-6">
        Импорт товаров из Excel
        <div class="text-caption text-medium-emphasis font-weight-regular mt-1">
          Шаг {{ wizard.importDialog.step }} из 4
        </div>
      </v-card-title>
      <v-card-text class="px-6 pidlg-body">
        <v-alert v-if="wizard.importDialog.error" type="error" variant="tonal" density="compact" class="mb-3">
          {{ wizard.importDialog.error }}
        </v-alert>

        <!-- Step 1: файл + выбор листа + строка заголовка -->
        <template v-if="wizard.importDialog.step === 1">
          <v-alert type="info" variant="tonal" density="compact" class="mb-3" icon="mdi-information-outline">
            <div class="text-body-2">
              Колонки НЕ подбираются автоматически — на шаге 2 нужно будет
              сопоставить их вручную (подсказка предложена, но её надо
              проверить и подтвердить).<br>
              <strong>Обязательная колонка:</strong> «Наименование».
            </div>
          </v-alert>
          <v-file-input
            v-model="wizard.importDialog.fileList"
            label="Файл Excel (.xlsx, .xls)"
            accept=".xlsx,.xls"
            variant="outlined" density="compact"
            prepend-icon="mdi-file-excel"
            show-size
            :loading="wizard.importDialog.loading"
            @update:model-value="onFilePicked"
          />

          <template v-if="wizard.hasPreview">
            <v-select
              v-if="wizard.importDialog.sheets.length > 1"
              :model-value="wizard.importDialog.selectedSheet"
              :items="wizard.importDialog.sheets.map(s => ({ title: `${s.name} (${s.total_rows} строк)`, value: s.name }))"
              label="Лист" variant="outlined" density="compact" class="mb-2"
              @update:model-value="v => wizard.selectSheet(v)"
            />
            <v-alert type="info" variant="tonal" density="compact" class="mb-2 pidlg-header-alert" icon="mdi-table-row">
              Строка заголовка: <strong>{{ wizard.importDialog.headerRowOffset + 1 }}</strong>,
              строк данных: <strong>{{ wizard.importDialog.totalRowsInSheet }}</strong>
              <div class="d-flex ga-2 mt-2">
                <v-btn size="x-small" variant="tonal" prepend-icon="mdi-arrow-down-bold"
                  :disabled="!wizard.importDialog.sample.length" @click="wizard.shiftHeaderRowDown()">
                  Заголовок ниже
                </v-btn>
                <v-btn size="x-small" variant="text" prepend-icon="mdi-restore"
                  :disabled="wizard.importDialog.headerRowOffset === wizard.importDialog.detectedHeaderRowOffset"
                  @click="wizard.resetHeaderRow()">
                  Сбросить
                </v-btn>
              </div>
            </v-alert>
            <div class="pidlg-sample-wrap">
              <v-table density="compact" class="text-caption pidlg-sample-table">
                <thead>
                  <tr><th v-for="(h, i) in wizard.importDialog.headers" :key="i">{{ h }}</th></tr>
                </thead>
                <tbody>
                  <tr v-for="(row, ri) in wizard.importDialog.sample.slice(0, 3)" :key="ri">
                    <td v-for="(cell, ci) in row" :key="ci">{{ cell }}</td>
                  </tr>
                </tbody>
              </v-table>
            </div>
          </template>
        </template>

        <!-- Step 2: маппинг колонок -->
        <template v-else-if="wizard.importDialog.step === 2">
          <p class="text-body-2 text-medium-emphasis mb-3">
            Проверьте и подтвердите, какая колонка файла — какое поле товара.
            Перетащите карточку колонки в нужное поле. Красная рамка —
            обязательное поле «Наименование» ещё не заполнено.
          </p>
          <ImportMappingGrid
            :headers="wizard.importDialog.headers"
            :sample-rows="wizard.importDialog.sample"
            :target-fields="targetFields"
            :model-value="wizard.importDialog.mapping"
            :approximate-fields="wizard.importDialog.fuzzyFields"
            @update:model-value="v => wizard.importDialog.mapping = v"
          />
          <v-alert v-if="wizard.importDialog.fuzzyFields.length" type="warning" variant="tonal" density="compact" icon="mdi-flag-outline" class="mt-3">
            Поля с пометкой «предположительно» подобраны по части заголовка, а не по точному совпадению — проверьте их перед тем, как идти дальше.
          </v-alert>
          <v-alert v-if="!wizard.mappingValid" type="warning" density="compact" icon="mdi-alert" class="mt-3">
            Сопоставьте столбец «Наименование» — без него импорт невозможен.
          </v-alert>
        </template>

        <!-- Step 3: предпросмотр (dry_run) -->
        <template v-else-if="wizard.importDialog.step === 3">
          <v-alert type="info" variant="tonal" density="compact" class="mb-3">
            Ничего ещё не сохранено — это пробный подсчёт по вашему маппингу.
          </v-alert>
          <div class="d-flex flex-wrap ga-2 mb-3">
            <v-chip color="success" variant="tonal">Создастся: {{ wizard.importDialog.dryResult?.created ?? 0 }}</v-chip>
            <v-chip color="primary" variant="tonal">Обновится: {{ wizard.importDialog.dryResult?.updated ?? 0 }}</v-chip>
            <v-chip color="warning" variant="tonal">Пропустится: {{ wizard.importDialog.dryResult?.skipped ?? 0 }}</v-chip>
            <v-chip v-if="wizard.importDialog.dryResult?.errors?.length" color="error" variant="tonal">
              Ошибок: {{ wizard.importDialog.dryResult.errors.length }}
            </v-chip>
          </div>
          <div class="text-caption text-medium-emphasis mb-1">
            Пропуски и ошибки показаны первыми:
          </div>
          <div class="pidlg-rows-wrap">
            <v-table density="compact" class="text-caption">
              <thead>
                <tr><th>Стр.</th><th>Действие</th><th>Наименование</th><th>Причина</th></tr>
              </thead>
              <tbody>
                <tr v-for="r in wizard.sortedDryRows" :key="r.row">
                  <td>{{ r.row }}</td>
                  <td>
                    <v-chip size="x-small" :color="rowActionColor(r.action)" variant="tonal">{{ rowActionLabel(r.action) }}</v-chip>
                  </td>
                  <td>{{ r.name || '—' }}</td>
                  <td>{{ r.reason || '—' }}</td>
                </tr>
              </tbody>
            </v-table>
          </div>
        </template>

        <!-- Step 4: импорт -->
        <template v-else>
          <template v-if="!wizard.importDialog.result">
            <v-alert type="warning" variant="tonal" density="compact" class="mb-3" icon="mdi-alert-circle-outline">
              Сейчас будет записано в базу: создано <strong>{{ wizard.importDialog.dryResult?.created ?? 0 }}</strong>,
              обновлено <strong>{{ wizard.importDialog.dryResult?.updated ?? 0 }}</strong>.
              Действие необратимо без ручного удаления. Проверьте шаг 2 и 3, если сомневаетесь.
            </v-alert>
          </template>
          <v-alert v-else type="success" variant="tonal" class="mb-3">
            Импорт завершён. Создано: <strong>{{ wizard.importDialog.result.created }}</strong>,
            обновлено: <strong>{{ wizard.importDialog.result.updated }}</strong>,
            пропущено: <strong>{{ wizard.importDialog.result.skipped }}</strong>.
          </v-alert>
        </template>
      </v-card-text>
      <v-card-actions class="px-6 pb-4">
        <v-btn v-if="wizard.importDialog.step > 1 && !wizard.importDialog.result" variant="text"
          @click="wizard.importDialog.step -= 1">Назад</v-btn>
        <v-spacer />
        <v-btn variant="text" @click="wizard.closeImportDialog()">
          {{ wizard.importDialog.result ? 'Закрыть' : 'Отмена' }}
        </v-btn>
        <v-btn v-if="wizard.importDialog.step === 1" color="primary" :loading="wizard.importDialog.loading"
          :disabled="!wizard.hasPreview" @click="wizard.goToMapping()">Далее</v-btn>
        <v-btn v-else-if="wizard.importDialog.step === 2" color="primary" :loading="wizard.importDialog.loading"
          :disabled="!wizard.mappingValid" @click="wizard.doPreviewDryRun()">Далее</v-btn>
        <v-btn v-else-if="wizard.importDialog.step === 3" color="primary"
          @click="wizard.goToImportStep()">Далее</v-btn>
        <v-btn v-else-if="!wizard.importDialog.result" color="error" :loading="wizard.importDialog.loading"
          @click="wizard.doConfirmImport()">Импортировать</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import ImportMappingGrid from '@/components/common/ImportMappingGrid.vue'
import { PRODUCTS_IMPORT_TARGET_FIELDS, type useProductsImport } from '@/composables/products/useProductsImport'

const targetFields = PRODUCTS_IMPORT_TARGET_FIELDS

const props = defineProps<{
  wizard: ReturnType<typeof useProductsImport>
  mobile: boolean
}>()
const { wizard } = props

async function onFilePicked(files: File | File[] | null) {
  wizard.importDialog.file = Array.isArray(files) ? (files[0] ?? null) : (files ?? null)
  wizard.importDialog.sheets = []
  wizard.importDialog.dryResult = null
  wizard.importDialog.result = null
  if (wizard.importDialog.file) await wizard.doImportPreview()
}

const ROW_ACTION_LABELS: Record<string, string> = {
  created: 'создать', updated: 'обновить', skipped: 'пропуск', error: 'ошибка',
}
const ROW_ACTION_COLORS: Record<string, string> = {
  created: 'success', updated: 'primary', skipped: 'warning', error: 'error',
}
function rowActionLabel(a: string) { return ROW_ACTION_LABELS[a] || a }
function rowActionColor(a: string) { return ROW_ACTION_COLORS[a] || 'grey' }
</script>

<style scoped>
.pidlg-body {
  max-height: 65vh;
  overflow-y: auto;
}
.pidlg-header-alert :deep(.v-alert__content) {
  width: 100%;
}
.pidlg-sample-wrap,
.pidlg-rows-wrap {
  max-height: 320px;
  overflow: auto;
  border: 1px solid #eee;
  border-radius: 6px;
}
.pidlg-sample-table th,
.pidlg-sample-table td {
  white-space: nowrap;
}
</style>
