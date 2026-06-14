<template>
  <!-- Presentational Excel 2-step + Smart import dialog (the stepper UI).
       The parent keeps ALL parse/match/commit logic (doImportPreview,
       doMappedImport, doSmartPreview, doSmartImport, autoDetectMapping,
       commitPreviewItems, etc.) and owns every piece of state; this child only
       renders the stepper and emits user intents. State that the child needs to
       mutate (file inputs, drag mapping, toggles) is passed as a reactive
       `state` object and mutated in place, mirroring the v-model style used by
       the parent's refs. Extracted from PurchaseItemsEditor.vue (Layer 2). -->
  <v-dialog :model-value="modelValue" max-width="1400" scrollable :fullscreen="mobile"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)">
    <v-card>
      <v-card-title class="pa-4 d-flex align-center">
        <v-icon :icon="state.isSmartMode ? 'mdi-brain' : 'mdi-package-variant-plus'" class="mr-2" />
        {{ state.isSmartMode ? 'Умный импорт позиций' : 'Импорт товаров из файла' }}
        <v-spacer />
        <v-chip v-if="state.importStep > 1 && !state.isSmartMode" size="small" color="primary" variant="tonal" class="ml-2">
          Шаг {{ state.importStep }} / 3
        </v-chip>
      </v-card-title>
      <v-divider />
      <v-card-text class="pa-4 pb-0">
        <v-btn-toggle :model-value="state.isSmartMode" density="compact" mandatory color="primary" class="mb-2"
          @update:model-value="(v: boolean) => emit('switch-mode', v)">
          <v-btn :value="true" prepend-icon="mdi-brain">Авто (умный)</v-btn>
          <v-btn :value="false" prepend-icon="mdi-tune-vertical">Вручную (выбор листа и колонок)</v-btn>
        </v-btn-toggle>
        <div class="text-caption text-medium-emphasis mb-2">
          Если автоматический режим не распознал позиции (например, mojibake-кодировка или скан PDF без OCR) — переключитесь в ручной режим.
        </div>
      </v-card-text>
      <v-card-text class="pa-4">
        <!-- Excel import: Step 1 - Upload file -->
        <template v-if="!state.isSmartMode && state.importStep === 1">
          <v-alert type="info" variant="tonal" density="compact" class="mb-3" icon="mdi-information-outline">
            <div class="text-body-2">
              <strong>Поддерживаемые форматы:</strong> Excel (.xlsx, .xls), Word (.docx), PDF<br>
              <strong>Название листа:</strong> любое — система прочитает первый лист (или предложит выбрать)<br>
              <strong>Заголовки столбцов:</strong> определяются автоматически по ключевым словам
              (наименование, количество, цена, сумма и т.д.). Могут быть в любой строке.<br>
              <strong>На следующем шаге</strong> вы увидите распознанные столбцы и укажете соответствие полей.
            </div>
          </v-alert>
          <FileDropZone v-model="state.itemsImportFile"
            accept=".xlsx,.xls,.pdf,.docx,.doc,.html,.htm"
            hint="Excel, PDF, Word, HTML — перетащите или нажмите"
            class="mb-2" />
        </template>

        <!-- Excel import: Step 2 - Column mapping -->
        <template v-if="!state.isSmartMode && state.importStep === 2 && importPreviewData">
          <v-alert v-if="currentSheetData" type="info" variant="tonal" density="compact" class="mb-3" icon="mdi-file-table-outline">
            <strong>Лист:</strong> {{ currentSheetData.name }} ({{ currentSheetData.total_rows }} строк данных)
          </v-alert>
          <v-select
            v-if="importPreviewData.sheets.length > 1"
            v-model="state.importSelectedSheet"
            :items="importPreviewData.sheets.map((s: any) => ({ title: `${s.name} (${s.total_rows} строк)`, value: s.name }))"
            label="Сменить лист" variant="outlined" density="compact" class="mb-3"
          />

          <!-- COLUMN TABLE: headers on top, cards below -->
          <div class="imap-grid">
            <div v-for="target in targetFields" :key="target.value"
              class="imap-col"
              :class="{
                'imap-col--over': state.dragOverTarget === target.value,
                'imap-col--filled': isTargetFilled(target.value),
                'imap-col--required': target.required && !isTargetFilled(target.value),
              }"
              @dragover.prevent="state.dragOverTarget = target.value"
              @dragleave="state.dragOverTarget = null"
              @drop.prevent="emit('drop-to-target', target.value, $event)">
              <div class="imap-col-hdr">{{ target.title }}<span v-if="target.required" style="color:#e53935">*</span></div>
              <div class="imap-col-body">
                <div v-if="isTargetFilled(target.value)"
                  class="imap-card"
                  draggable="true"
                  @dragstart="emit('drag-start', state.dragMapping[target.value] as number, $event)">
                  <div class="imap-card-row">
                    <span class="imap-card-name">{{ getColumnLabel(state.dragMapping[target.value] as number) }}</span>
                    <button class="imap-card-x" @click.stop="emit('unmap-target', target.value)">×</button>
                  </div>
                  <div class="imap-card-samples">{{ getSamples(state.dragMapping[target.value] as number).join(', ') || '—' }}</div>
                </div>
                <div v-else class="imap-col-empty">—</div>
              </div>
            </div>
          </div>

          <!-- NOT RESOLVED section -->
          <div class="imap-unresolved mt-3"
            :class="{ 'imap-unresolved--over': state.dragOverTarget === '_unresolved' }"
            @dragover.prevent="state.dragOverTarget = '_unresolved'"
            @dragleave="state.dragOverTarget = null"
            @drop.prevent="emit('drop-to-unresolved', $event)">
            <span class="imap-unresolved-label">Не определилось</span>
            <div class="d-flex gap-2 flex-wrap mt-1">
              <template v-for="(_, colIdx) in currentSheetHeaders" :key="colIdx">
                <div v-if="!isMapped(colIdx) && !isIgnored(colIdx)"
                  class="imap-card imap-card--free"
                  draggable="true"
                  @dragstart="emit('drag-start', colIdx, $event)">
                  <div class="imap-card-row">
                    <span class="imap-card-name">{{ getColumnLabel(colIdx) }}</span>
                    <button class="imap-card-x imap-card-x--grey" title="Убрать" @click.stop="emit('ignore-column', colIdx)">×</button>
                  </div>
                  <div class="imap-card-samples">{{ getSamples(colIdx).join(', ') || '—' }}</div>
                </div>
              </template>
              <span v-if="unmappedCount === 0" style="font-size:11px;color:#888;align-self:center">все распределены ✓</span>
            </div>
          </div>

          <v-alert v-if="!mappingHasName" type="warning" density="compact" icon="mdi-alert" class="mt-3">
            Укажите столбец «Наименование»
          </v-alert>
        </template>

        <!-- Excel import: Step 3 - Result -->
        <template v-if="!state.isSmartMode && state.importStep === 3">
          <v-alert v-if="itemsImportResult" type="success" density="compact" class="mb-2">
            <div>Добавлено позиций: <strong>{{ (itemsImportResult as any).added ?? (itemsImportResult as any).imported }}</strong></div>
            <div v-if="(itemsImportResult as any).matched_catalog">Из каталога: {{ (itemsImportResult as any).matched_catalog }}</div>
            <div v-if="(itemsImportResult as any).new_in_catalog">Новых в каталоге: {{ (itemsImportResult as any).new_in_catalog }}</div>
          </v-alert>
          <v-alert v-if="importError" type="error" density="compact">
            {{ importError }}
          </v-alert>
        </template>

        <!-- Smart import section -->
        <template v-if="state.isSmartMode">
          <v-alert type="info" variant="tonal" density="compact" class="mb-3" icon="mdi-information-outline">
            <div class="text-body-2">
              <strong>Умный импорт</strong> — автоматически распознаёт наименования, количество и цены из файла.<br>
              Поддерживаются Excel, Word, PDF, HTML, <strong>JPG/PNG/WEBP</strong> (фото чека с QR ФНС или текстом).<br>
              <span class="text-medium-emphasis">Для фото чека: лучший результат даёт QR-код ФНС (приложение «Проверка чека»). OCR-распознавание текста менее точно.</span>
            </div>
          </v-alert>
          <FileDropZone v-model="state.smartImportFile"
            accept=".xlsx,.xls,.pdf,.docx,.doc,.html,.htm,.jpg,.jpeg,.png,.webp,.heic"
            hint="Excel, PDF, Word, HTML, фото чека — перетащите или нажмите"
            class="mb-4" />

          <!-- import-no-clutter: тогл «не добавлять в каталог» -->
          <v-switch
            v-model="state.smartImportSkipCatalog"
            label="Не добавлять в каталог при импорте"
            hint="Позиции попадут только в эту закупку, без сопоставления с каталогом — один-в-один как в чеке. Идеально для авансовых платежей, билетов, актов."
            persistent-hint
            density="compact"
            color="primary"
            hide-details="auto"
            class="mb-3"
          />

          <!-- Preview table -->
          <template v-if="smartImportPreview && smartImportPreview.length">
            <div class="text-subtitle-2 mb-2">
              Распознано позиций: <strong>{{ smartImportPreview.length }}</strong>
              <span v-if="smartImportColumns?.length" class="ml-2 text-caption text-medium-emphasis">
                (столбцы: {{ smartImportColumns.join(', ') }})
              </span>
            </div>

            <!-- Column mapping panel toggle -->
            <v-btn v-if="!columnMappingApplied" variant="tonal" size="small" class="mb-3"
              prepend-icon="mdi-tune" @click="state.showMappingPanel = !state.showMappingPanel">
              {{ state.showMappingPanel ? 'Скрыть' : 'Настроить' }} маппинг столбцов
            </v-btn>
            <v-chip v-if="columnMappingApplied" color="success" variant="tonal" size="small" class="mb-3">
              Маппинг применён
            </v-chip>

            <div v-if="state.showMappingPanel" class="mb-3 pa-3" style="border:1px solid #e0e0e0;border-radius:8px">
              <div class="text-caption font-weight-bold mb-2">Сопоставление столбцов файла → полей CRM</div>
              <v-row dense>
                <v-col v-for="(label, field) in crmMappingFields" :key="field" cols="12" md="4">
                  <v-select
                    v-model="state.columnFieldMapping[field]"
                    :items="crmFieldSelectItems"
                    :label="label"
                    item-title="title" item-value="value"
                    variant="outlined" density="compact" hide-details class="mb-2"
                  />
                </v-col>
              </v-row>
              <v-btn color="primary" size="small" variant="flat" @click="emit('apply-column-mapping')">
                Применить маппинг
              </v-btn>
            </div>

            <v-table density="compact" class="mb-3">
              <thead>
                <tr>
                  <th>Наименование</th>
                  <th>Тип</th>
                  <th>Кол-во</th>
                  <th>Ед.</th>
                  <th>Цена ед.</th>
                  <th>Сумма</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, ri) in smartImportPreview.slice(0, 10)" :key="ri">
                  <td>{{ row.item_name || '—' }}</td>
                  <td>{{ row.item_type || '—' }}</td>
                  <td>{{ row.quantity ?? '—' }}</td>
                  <td>{{ row.unit || '—' }}</td>
                  <td>{{ row.unit_price ?? '—' }}</td>
                  <td>{{ row.total_price ?? '—' }}</td>
                </tr>
              </tbody>
            </v-table>
            <div v-if="smartImportPreview.length > 10" class="text-caption text-medium-emphasis mb-2">
              + ещё {{ smartImportPreview.length - 10 }} строк
            </div>
          </template>

          <!-- import-pdf-debug C3: alert при пустом результате -->
          <v-alert
            v-if="state.smartImportFile && smartImportPreview !== null && smartImportPreview.length === 0 && !smartImportLoading"
            type="warning" variant="tonal" class="mb-3">
            <div>Не удалось автоматически распознать таблицу в этом файле.</div>
            <div class="mt-2 d-flex ga-2 flex-wrap">
              <v-btn size="small" variant="tonal" @click="emit('switch-mode', false)">
                Переключиться на Ручной режим
              </v-btn>
              <v-btn size="small" variant="tonal" color="info" @click="emit('download-debug-report')">
                Скачать debug-отчёт
              </v-btn>
            </div>
          </v-alert>

          <v-alert v-if="smartImportResult" type="success" density="compact" class="mb-2">
            Добавлено позиций: <strong>{{ smartImportResult.added }}</strong>
          </v-alert>
        </template>

      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-btn v-if="!state.isSmartMode && state.importStep > 1 && state.importStep < 3" variant="text" @click="state.importStep--">
          <v-icon icon="mdi-arrow-left" class="mr-1" /> Назад
        </v-btn>
        <v-spacer />
        <v-btn variant="text" @click="emit('close')">Закрыть</v-btn>

        <!-- Excel import buttons -->
        <template v-if="!state.isSmartMode">
          <v-btn v-if="state.importStep === 1" color="primary" variant="flat"
            :loading="itemsImportLoading"
            :disabled="!state.itemsImportFile"
            @click="emit('import-preview')">
            Далее
          </v-btn>
          <v-btn v-if="state.importStep === 2 && (importPreviewData?.sheets?.length ?? 0) > 1"
            color="success" variant="tonal"
            :loading="itemsImportLoading"
            prepend-icon="mdi-table-multiple"
            @click="emit('import-all-tables')">
            Импортировать ВСЕ таблицы ({{ importPreviewData?.sheets?.length }})
          </v-btn>
          <v-btn v-if="state.importStep === 2" color="success" variant="flat"
            :loading="itemsImportLoading"
            :disabled="!mappingHasName"
            @click="emit('mapped-import')">
            Импортировать
          </v-btn>
          <v-btn v-if="state.importStep === 3" color="primary" variant="flat"
            @click="emit('close')">
            Готово
          </v-btn>
        </template>

        <!-- Smart import buttons -->
        <template v-if="state.isSmartMode">
          <v-btn v-if="!smartImportPreview" color="primary" variant="flat"
            :loading="smartImportLoading"
            :disabled="!state.smartImportFile"
            @click="emit('smart-preview')">
            Распознать
          </v-btn>
          <v-btn v-if="smartImportPreview && smartImportPreview.length && !smartImportResult"
            color="success" variant="flat"
            :loading="smartImportLoading"
            @click="emit('smart-import')">
            Добавить позиции
          </v-btn>
        </template>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import FileDropZone from '@/components/FileDropZone.vue'
import { useDisplay } from 'vuetify'

const { mobile } = useDisplay()

interface TargetField { value: string; title: string; required?: boolean; hint?: string }
interface CrmFieldSelectItem { title: string; value: string }

/** Mutable UI state owned by the parent; passed by reference so v-model bindings
 *  (file inputs, step counter, drag mapping, toggles) mutate the parent's refs.
 *  Kept as a single object to avoid 15+ individual v-model props. */
interface WizardState {
  isSmartMode: boolean
  itemsImportFile: File | null
  importStep: number
  importSelectedSheet: string
  dragMapping: Record<string, number | null>
  dragOverTarget: string | null
  smartImportFile: File | null
  smartImportSkipCatalog: boolean
  showMappingPanel: boolean
  columnFieldMapping: Record<string, string>
}

defineProps<{
  modelValue: boolean
  state: WizardState
  // Parent-owned data / computed values (read-only here):
  importPreviewData: any
  itemsImportResult: Record<string, any> | null
  itemsImportLoading: boolean
  importError: string
  currentSheetData: any
  currentSheetHeaders: any[]
  mappingHasName: boolean
  unmappedCount: number
  targetFields: TargetField[]
  smartImportPreview: any[] | null
  smartImportColumns: string[] | null
  smartImportResult: { added: number; matched_catalog: number; unmatched: number } | null
  smartImportLoading: boolean
  columnMappingApplied: boolean
  crmMappingFields: Record<string, string>
  crmFieldSelectItems: CrmFieldSelectItem[]
  // Pure helper functions passed in from the parent (no business state here):
  isMapped: (idx: number) => boolean
  isIgnored: (idx: number) => boolean
  isTargetFilled: (field: string) => boolean
  getColumnLabel: (idx: number) => string
  getSamples: (idx: number) => string[]
}>()

const emit = defineEmits<{
  'update:modelValue': [v: boolean]
  'switch-mode': [smart: boolean]
  close: []
  'import-preview': []
  'mapped-import': []
  'import-all-tables': []
  'smart-preview': []
  'smart-import': []
  'apply-column-mapping': []
  'download-debug-report': []
  'drop-to-target': [field: string, e: DragEvent]
  'drop-to-unresolved': [e: DragEvent]
  'drag-start': [idx: number, e: DragEvent]
  'unmap-target': [field: string]
  'ignore-column': [idx: number]
}>()
</script>

<style scoped>
/* ── Import column-mapping table (imap) — moved with the dialog (Layer 2) ─── */
.imap-grid {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  padding-bottom: 4px;
}
.imap-col {
  flex: 1;
  min-width: 130px;
  border: 1px dashed #ccc;
  border-radius: 6px;
  background: #fafafa;
  transition: border-color 0.15s, background 0.15s;
}
.imap-col--over {
  border-color: #1976D2;
  background: rgba(25, 118, 210, 0.04);
}
.imap-col--filled {
  border-style: solid;
  border-color: #43A047;
  background: #f6fff6;
}
.imap-col--required {
  border-color: #ef9a9a;
  background: #fff8f8;
}
.imap-col-hdr {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  color: #555;
  padding: 5px 7px 3px;
  border-bottom: 1px solid #e8e8e8;
  white-space: normal;
  word-break: break-word;
}
.imap-col-body {
  padding: 5px;
  min-height: 58px;
}
.imap-col-empty {
  font-size: 10px;
  color: #ccc;
  text-align: center;
  margin-top: 10px;
  font-style: italic;
}
.imap-card {
  border-radius: 4px;
  background: #fff;
  border: 1px solid #e0e0e0;
  padding: 4px 6px;
  cursor: grab;
  user-select: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.imap-card:hover {
  border-color: #1976D2;
  box-shadow: 0 1px 5px rgba(25, 118, 210, 0.15);
}
.imap-card-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 2px;
}
.imap-card-name {
  font-size: 11px;
  font-weight: 600;
  white-space: normal;
  word-break: break-word;
  flex: 1;
}
.imap-card-x {
  font-size: 14px;
  line-height: 1;
  background: none;
  border: none;
  cursor: pointer;
  color: #aaa;
  padding: 0 2px;
  flex-shrink: 0;
}
.imap-card-x:hover { color: #e53935; }
.imap-card-x--grey { color: #bbb; }
.imap-card-samples {
  font-size: 10px;
  color: #999;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 2px;
  line-height: 1.3;
}
.imap-card--free {
  background: #fafafa;
}
.imap-unresolved {
  border: 1px dashed #ccc;
  border-radius: 6px;
  padding: 6px 10px;
  min-height: 44px;
  transition: border-color 0.15s, background 0.15s;
}
.imap-unresolved--over {
  border-color: #1976D2;
  background: rgba(25, 118, 210, 0.04);
}
.imap-unresolved-label {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  color: #aaa;
  letter-spacing: 0.3px;
}
</style>
