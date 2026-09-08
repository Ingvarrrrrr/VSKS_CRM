<template>
  <v-dialog :model-value="im.contractorImportDialog.value" max-width="1000" persistent scrollable :fullscreen="mobile" @update:model-value="im.contractorImportDialog.value = $event">
    <v-card>
      <v-card-title class="d-flex align-center pa-4">
        <span>Импорт контрагентов — шаг {{ im.contractorImportStep.value }} из 2</span>
        <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="im.closeContractorImport()" />
      </v-card-title>
      <v-divider />
      <v-card-text style="min-height:300px">

        <!-- Step 1 -->
        <template v-if="im.contractorImportStep.value === 1">
          <v-alert type="info" variant="tonal" density="compact" class="mb-3" icon="mdi-information-outline">
            <div class="text-body-2">
              <strong>Форматы:</strong> Excel (.xlsx, .xls), Word (.docx), PDF<br>
              <strong>Заголовки:</strong> определяются автоматически по ключевым словам — могут быть в любой строке<br>
              <strong>Лист:</strong> любое название — система прочитает первый или предложит выбрать
            </div>
          </v-alert>
          <FileDropZone v-model="im.contractorImportFile.value"
            accept=".xlsx,.xls,.docx,.doc,.pdf"
            hint=".xlsx, .xls, .docx, .doc, .pdf — перетащите или нажмите"
            class="mb-4" />
          <v-alert v-if="im.contractorImportError.value" type="error" density="compact" class="mt-2">{{ im.contractorImportError.value }}</v-alert>
        </template>

        <!-- Step 2: mapping -->
        <template v-if="im.contractorImportStep.value === 2 && im.contractorImportPreview.value">
          <p class="text-caption text-medium-emphasis mb-2">
            Перетащите столбцы из файла в нужные поля. Всего строк: {{ im.contractorImportPreview.value.total_rows }}
          </p>
          <!-- TARGET ZONES (imap-grid) -->
          <div class="imap-grid mb-4">
            <div v-for="target in im.CONTRACTOR_TARGET_FIELDS" :key="target.value"
              class="imap-col"
              :class="{
                'imap-col--over': im.contractorDragOverTarget.value === target.value,
                'imap-col--filled': im.contractorIsTargetFilled(target.value),
                'imap-col--required': target.required && !im.contractorIsTargetFilled(target.value),
              }"
              @dragover.prevent="im.contractorDragOverTarget.value = target.value"
              @dragleave="im.contractorDragOverTarget.value = null"
              @drop.prevent="im.contractorOnDropToTarget(target.value, $event)">
              <div class="imap-col-hdr">{{ target.title }}<span v-if="target.required" style="color:#e53935">*</span></div>
              <div class="imap-col-body">
                <div v-if="im.contractorIsTargetFilled(target.value)"
                  class="imap-card" draggable="true"
                  @dragstart="im.contractorOnDragStart(im.contractorDragMapping.value[target.value] as number, $event)">
                  <div class="imap-card-row">
                    <span class="imap-card-name">{{ im.contractorGetLabel(im.contractorDragMapping.value[target.value] as number) }}</span>
                    <button class="imap-card-x" @click.stop="im.contractorUnmapTarget(target.value)">×</button>
                  </div>
                  <div class="imap-card-samples">{{ im.contractorGetSamples(im.contractorDragMapping.value[target.value] as number).join(', ') || '—' }}</div>
                </div>
                <div v-else class="imap-col-empty">—</div>
              </div>
            </div>
          </div>
          <!-- UNRESOLVED -->
          <div class="imap-unresolved"
            :class="{'imap-unresolved--over': im.contractorDragOverTarget.value === '_unresolved'}"
            @dragover.prevent="im.contractorDragOverTarget.value = '_unresolved'"
            @dragleave="im.contractorDragOverTarget.value = null"
            @drop.prevent="im.contractorOnDropToUnresolved($event)">
            <span class="imap-unresolved-label">Не определилось</span>
            <div class="d-flex gap-2 flex-wrap mt-1">
              <template v-for="(h, idx) in im.contractorImportPreview.value.headers" :key="idx">
                <div v-if="!im.contractorIsMapped(idx) && !im.contractorIsIgnored(idx)"
                  class="imap-card imap-card--free" draggable="true"
                  @dragstart="im.contractorOnDragStart(idx, $event)">
                  <div class="imap-card-row">
                    <span class="imap-card-name">{{ h || `Столбец ${idx+1}` }}</span>
                    <button class="imap-card-x imap-card-x--grey" @click.stop="im.contractorIgnoreCol(idx)">×</button>
                  </div>
                  <div class="imap-card-samples">{{ im.contractorGetSamples(idx).join(', ') || '—' }}</div>
                </div>
              </template>
            </div>
          </div>
          <v-alert v-if="!im.contractorIsTargetFilled('name')" type="warning" density="compact" class="mt-3">
            Укажите хотя бы столбец «Наименование»
          </v-alert>
        </template>

        <!-- Step 3: result -->
        <template v-if="im.contractorImportStep.value === 3 && im.contractorImportResult.value">
          <v-alert type="success" class="mb-3">
            Добавлено: <strong>{{ im.contractorImportResult.value.created }}</strong>
            <template v-if="im.contractorImportResult.value.updated">, дополнено: <strong>{{ im.contractorImportResult.value.updated }}</strong></template>
            <template v-if="im.contractorImportResult.value.skipped">, пропущено пустых: {{ im.contractorImportResult.value.skipped }}</template>
          </v-alert>
          <v-alert v-if="im.contractorImportResult.value.update_details?.length" type="info" variant="tonal" density="compact" class="mb-3">
            <div class="text-subtitle-2 mb-1">Дополненные контрагенты:</div>
            <div v-for="(d, i) in im.contractorImportResult.value.update_details.slice(0, 20)" :key="i" class="text-caption">{{ d }}</div>
            <div v-if="im.contractorImportResult.value.update_details.length > 20" class="text-caption text-medium-emphasis">...и ещё {{ im.contractorImportResult.value.update_details.length - 20 }}</div>
          </v-alert>
          <v-alert v-if="im.contractorImportResult.value.errors?.length" type="error" variant="tonal" density="compact" class="mb-3">
            <div class="text-subtitle-2 mb-1">Ошибки:</div>
            <div v-for="(e, i) in im.contractorImportResult.value.errors.slice(0, 10)" :key="i" class="text-caption">{{ e }}</div>
          </v-alert>
        </template>
      </v-card-text>
      <v-divider />
      <v-card-actions class="pa-4">
        <v-spacer />
        <v-btn variant="text" @click="im.closeContractorImport()">{{ im.contractorImportStep.value === 3 ? 'Закрыть' : 'Отмена' }}</v-btn>
        <v-btn v-if="im.contractorImportStep.value === 1" color="primary" :loading="im.contractorImportLoading.value"
          :disabled="!im.contractorImportFile.value" @click="im.doContractorImportPreview()">
          Далее →
        </v-btn>
        <v-btn v-if="im.contractorImportStep.value === 2" color="success" :loading="im.contractorImportLoading.value"
          :disabled="!im.contractorIsTargetFilled('name')" @click="im.doContractorImportMapped()">
          Импортировать
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import FileDropZone from '@/components/FileDropZone.vue'
import type { ContractorsImportApi } from '@/composables/contractors/useContractorsImport'

defineProps<{
  im: ContractorsImportApi
  mobile: boolean
}>()
</script>

<style scoped>
/* ── imap drag-and-drop (contractor import) ── */
.imap-grid { display:flex; gap:4px; overflow-x:auto; padding-bottom:4px; flex-wrap:wrap; }
.imap-col { flex:1; min-width:100px; border:1px dashed #ccc; border-radius:6px; background:#fafafa; transition:border-color .15s,background .15s; }
.imap-col--over { border-color:#1976D2; background:rgba(25,118,210,.04); }
.imap-col--filled { border-style:solid; border-color:#43A047; background:#f6fff6; }
.imap-col--required { border-color:#ef9a9a; background:#fff8f8; }
.imap-col-hdr { font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:.3px; color:#555; padding:5px 7px 3px; border-bottom:1px solid #e8e8e8; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.imap-col-body { padding:5px; min-height:58px; }
.imap-col-empty { font-size:10px; color:#ccc; text-align:center; margin-top:10px; font-style:italic; }
.imap-card { border-radius:4px; background:#fff; border:1px solid #e0e0e0; padding:4px 6px; cursor:grab; user-select:none; transition:border-color .15s,box-shadow .15s; }
.imap-card:hover { border-color:#1976D2; box-shadow:0 1px 5px rgba(25,118,210,.15); }
.imap-card-row { display:flex; align-items:center; justify-content:space-between; gap:2px; }
.imap-card-name { font-size:11px; font-weight:600; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; flex:1; }
.imap-card-x { font-size:14px; line-height:1; background:none; border:none; cursor:pointer; color:#aaa; padding:0 2px; flex-shrink:0; }
.imap-card-x:hover { color:#e53935; }
.imap-card-x--grey { color:#bbb; }
.imap-card-samples { font-size:10px; color:#999; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; margin-top:2px; line-height:1.3; }
.imap-card--free { background:#fafafa; }
.imap-unresolved { border:1px dashed #ccc; border-radius:6px; padding:6px 10px; min-height:44px; transition:border-color .15s,background .15s; }
.imap-unresolved--over { border-color:#1976D2; background:rgba(25,118,210,.04); }
.imap-unresolved-label { font-size:10px; font-weight:700; text-transform:uppercase; color:#aaa; letter-spacing:.3px; }
</style>
