<template>
  <!-- ── Import FEO dialog ── -->
  <v-dialog v-model="feoImport.show" max-width="1400" persistent :fullscreen="mobile">
    <v-card class="dialog-card">
      <v-card-title class="dialog-title">
        <v-icon icon="mdi-upload" color="primary" class="mr-2" />
        Импорт категорий ФЭО из Excel
        <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="closeFeoImport" />
      </v-card-title>
      <v-divider />
      <v-card-text class="pt-4">

        <!-- Step 1: File upload -->
        <template v-if="feoImport.step === 1">
          <v-alert type="info" variant="tonal" density="compact" class="mb-4" icon="mdi-information-outline">
            <div class="text-body-2">
              <strong>Поддерживаемые форматы:</strong> Excel (.xlsx, .xls), Word (.docx), PDF<br>
              <strong>Название листа:</strong> любое — система прочитает первый лист (или предложит выбрать)<br>
              <strong>Заголовки столбцов:</strong> система автоматически найдёт строку с заголовками по ключевым словам
              (субсидия, направление, уровень, количество и т.д.). Заголовки могут быть в любой строке — не обязательно в первой.<br>
              <strong>На следующем шаге</strong> вы увидите распознанные столбцы и сможете вручную указать,
              какой столбец соответствует какому полю.
            </div>
          </v-alert>
          <v-file-input
            v-model="feoImport.fileList"
            label="Выберите файл (Excel, PDF или Word)"
            accept=".xlsx,.xls,.pdf,.docx,.doc"
            variant="outlined" density="compact"
            prepend-icon="mdi-file-upload"
            show-size
            hint="Перетащите файл сюда или нажмите для выбора"
            persistent-hint
            @update:model-value="feoImport.file = Array.isArray($event) ? ($event[0] ?? null) : ($event ?? null)"
          />
        </template>

        <!-- Step 2: Column mapping — вынесен в FeoImportMappingStep.vue (файл мастера
             целиком превышал 600 строк) -->
        <template v-if="feoImport.step === 2 && feoImport.previewData">
          <FeoImportMappingStep />
        </template>

        <!-- Step 3: Dry-run preview (прогноз перед записью) -->
        <template v-if="feoImport.step === 3">
          <v-alert type="info" variant="tonal" density="compact" class="mb-3" icon="mdi-clipboard-text-search-outline">
            Это <strong>прогноз</strong> — данные ещё не записаны в базу. Проверьте результат и нажмите «Импортировать».
          </v-alert>
          <div v-if="feoImport.dryResult" class="d-flex flex-wrap gap-2 mb-3">
            <v-chip color="success" variant="flat"
              :disabled="!feoImport.dryResult.created_details?.length"
              @click="feoToggleResultPanel('dry_created')">
              <v-icon icon="mdi-plus-circle" start size="16" />Будет создано: {{ feoImport.dryResult.created ?? 0 }}
              <v-icon v-if="feoImport.dryResult.created_details?.length" end size="16"
                :icon="feoResultPanels.includes('dry_created') ? 'mdi-chevron-up' : 'mdi-chevron-down'" />
            </v-chip>
            <v-chip color="warning" variant="flat"
              :disabled="!feoImport.dryResult.updated_details?.length"
              @click="feoToggleResultPanel('dry_updated')">
              <v-icon icon="mdi-pencil" start size="16" />Будет обновлено: {{ feoImport.dryResult.updated ?? 0 }}
              <v-icon v-if="feoImport.dryResult.updated_details?.length" end size="16"
                :icon="feoResultPanels.includes('dry_updated') ? 'mdi-chevron-up' : 'mdi-chevron-down'" />
            </v-chip>
            <v-chip color="grey" variant="flat"
              :disabled="!feoImport.dryResult.skipped_details?.length"
              @click="feoToggleResultPanel('dry_skipped')">
              <v-icon icon="mdi-debug-step-over" start size="16" />Будет пропущено: {{ feoImport.dryResult.skipped }}
              <v-icon v-if="feoImport.dryResult.skipped_details?.length" end size="16"
                :icon="feoResultPanels.includes('dry_skipped') ? 'mdi-chevron-up' : 'mdi-chevron-down'" />
            </v-chip>
          </div>
          <!-- Предупреждения dry-run -->
          <template v-if="feoImport.dryResult?.warnings?.length">
            <div class="text-subtitle-2 mb-1 text-warning">Предупреждения ({{ feoImport.dryResult.warnings.length }}):</div>
            <v-expansion-panels v-model="feoResultPanels" multiple class="mb-3">
              <v-expansion-panel
                v-for="kind in [...new Set(feoImport.dryResult.warnings.map(w => w.kind))]"
                :key="'dw_' + kind"
                :value="'dw_' + kind">
                <v-expansion-panel-title>
                  <v-icon icon="mdi-alert-outline" size="18" color="warning" class="mr-2" />
                  {{ feoWarnKindLabel(kind) }} ({{ feoImport.dryResult.warnings.filter(w => w.kind === kind).length }})
                </v-expansion-panel-title>
                <v-expansion-panel-text>
                  <v-list density="compact" max-height="280" class="overflow-y-auto">
                    <v-list-item
                      v-for="(w, wi) in feoImport.dryResult.warnings.filter(x => x.kind === kind)"
                      :key="wi"
                      :title="w.name"
                      :subtitle="feoWarnSubtitle(w)" />
                  </v-list>
                </v-expansion-panel-text>
              </v-expansion-panel>
            </v-expansion-panels>
          </template>
          <!-- Ошибки dry-run — красным, блокируют импорт -->
          <div v-if="feoImport.dryResult?.errors?.length" class="mt-2">
            <div class="text-subtitle-2 mb-1 text-error">Ошибки ({{ feoImport.dryResult.errors.length }}) — исправьте файл перед импортом:</div>
            <v-list density="compact" class="bg-error-lighten-5 rounded">
              <v-list-item v-for="(e, i) in feoImport.dryResult.errors" :key="i"
                :subtitle="`Стр. ${e.row}: ${e.name} — ${e.message}`" />
            </v-list>
          </div>
          <!-- Детали по категориям (сворачиваемые) -->
          <v-expansion-panels v-if="feoImport.dryResult" v-model="feoResultPanels" multiple class="mb-3">
            <v-expansion-panel v-if="feoImport.dryResult.created_details?.length" value="dry_created">
              <v-expansion-panel-title>
                <v-icon icon="mdi-plus-circle" size="18" color="success" class="mr-2" />
                Будет создано ({{ feoImport.dryResult.created_details.length }})
              </v-expansion-panel-title>
              <v-expansion-panel-text>
                <v-list density="compact" max-height="320" class="overflow-y-auto">
                  <v-list-item v-for="(d, i) in feoImport.dryResult.created_details" :key="i"
                    :title="d.name" :subtitle="`Стр. ${d.row} — ${d.reason}`" />
                </v-list>
              </v-expansion-panel-text>
            </v-expansion-panel>
            <v-expansion-panel v-if="feoImport.dryResult.updated_details?.length" value="dry_updated">
              <v-expansion-panel-title>
                <v-icon icon="mdi-pencil" size="18" color="warning" class="mr-2" />
                Будет обновлено ({{ feoImport.dryResult.updated_details.length }})
              </v-expansion-panel-title>
              <v-expansion-panel-text>
                <v-list density="compact" max-height="320" class="overflow-y-auto">
                  <v-list-item v-for="(d, i) in feoImport.dryResult.updated_details" :key="i"
                    :title="d.name" :subtitle="`Стр. ${d.row} — ${d.reason}`" />
                </v-list>
              </v-expansion-panel-text>
            </v-expansion-panel>
            <v-expansion-panel v-if="feoImport.dryResult.skipped_details?.length" value="dry_skipped">
              <v-expansion-panel-title>
                <v-icon icon="mdi-debug-step-over" size="18" color="grey" class="mr-2" />
                Будет пропущено ({{ feoImport.dryResult.skipped_details.length }})
              </v-expansion-panel-title>
              <v-expansion-panel-text>
                <v-list density="compact" max-height="320" class="overflow-y-auto">
                  <v-list-item v-for="(d, i) in feoImport.dryResult.skipped_details" :key="i"
                    :title="d.name" :subtitle="`Стр. ${d.row} — ${d.reason}`" />
                </v-list>
              </v-expansion-panel-text>
            </v-expansion-panel>
            <v-expansion-panel v-if="feoImport.dryResult.deleted_details?.length" value="dry_deleted">
              <v-expansion-panel-title>
                <v-icon icon="mdi-delete-outline" size="18" color="error" class="mr-2" />
                Будет удалено как пустое ({{ feoImport.dryResult.deleted_details.length }})
              </v-expansion-panel-title>
              <v-expansion-panel-text>
                <v-list density="compact" max-height="240" class="overflow-y-auto">
                  <v-list-item v-for="(d, i) in feoImport.dryResult.deleted_details" :key="i"
                    :title="d.path" :subtitle="d.reason" />
                </v-list>
              </v-expansion-panel-text>
            </v-expansion-panel>
          </v-expansion-panels>
          <!-- Останется вне новой разбивки — узлы, ждущие решения человека -->
          <template v-if="feoUnmatchedNeedsMapping.length">
            <div class="text-subtitle-2 mb-1 text-error">
              Останется вне новой разбивки ({{ feoUnmatchedNeedsMapping.length }}):
            </div>
            <v-list density="compact" class="bg-error-lighten-5 rounded mb-3">
              <v-list-item v-for="n in feoUnmatchedNeedsMapping" :key="n.id"
                :title="n.path" :subtitle="feoLoadSummary(n.load)" />
            </v-list>
          </template>
          <v-alert v-if="feoImport.dryResult?.remap_aborted_reason" type="warning" variant="tonal"
            icon="mdi-alert" class="mb-3">
            {{ feoImport.dryResult.remap_aborted_reason }}
          </v-alert>
        </template>

        <!-- Step 4: Remap unmatched nodes (условный — только если есть needs_mapping) -->
        <template v-if="feoImport.step === 4">
          <v-alert type="info" variant="tonal" density="compact" class="mb-3" icon="mdi-source-branch">
            <div class="text-body-2">
              Направления, которых в файле нет вообще, дерево не трогает.<br>
              Узел, которому не выбрали цель, останется в дереве как есть — ничего не теряется.<br>
              Удалённое исчезает из текущего дерева, но остаётся в предыдущей редакции плана закупок —
              она доступна в Истории и выгружается из неё.
            </div>
          </v-alert>

          <v-btn v-if="feoHasSuggestions" size="small" variant="tonal" color="primary" class="mb-3"
            prepend-icon="mdi-auto-fix" @click="feoAcceptAllSuggestions">
            Принять все подсказки
          </v-btn>

          <v-table density="comfortable" class="feo-remap-table">
            <thead>
              <tr>
                <th style="width:26%">Старый узел</th>
                <th style="width:28%">Что на нём висит</th>
                <th style="width:46%">Куда перенести</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="n in feoUnmatchedNeedsMapping" :key="n.id">
                <td>{{ n.path }}</td>
                <td>
                  <div>{{ feoLoadSummary(n.load) }}</div>
                  <div v-if="n.blocking_purchases?.length" class="text-caption text-medium-emphasis mt-1">
                    <div v-for="bp in n.blocking_purchases" :key="bp.id" class="d-flex align-center" style="gap:4px">
                      <span class="flex-shrink-0">{{ bp.purchase_number != null ? `№${bp.purchase_number}` : `Закупка #${bp.id}` }}</span>
                      <span v-if="bp.subject" class="text-truncate" style="min-width:0">{{ bp.subject }}</span>
                      <span class="flex-shrink-0">{{ bp.status_label }}</span>
                    </div>
                  </div>
                </td>
                <td class="py-2">
                  <div v-if="n.suggestion" class="text-caption mb-1">
                    Похоже на: «{{ n.suggestion }}»<span v-if="n.suggestion_reason"> ({{ n.suggestion_reason }})</span>
                    <v-btn size="x-small" variant="text" color="primary" class="ml-1"
                      @click="feoImport.remap[n.id] = n.suggestion">Принять</v-btn>
                  </div>
                  <v-autocomplete
                    v-model="feoImport.remap[n.id]"
                    :items="feoImport.dryResult?.new_paths || []"
                    clearable density="compact" variant="outlined" hide-details
                    placeholder="Оставить как есть" />
                </td>
              </tr>
            </tbody>
          </v-table>
        </template>

        <!-- Step 5: Result (после реального импорта) -->
        <template v-if="feoImport.step === 5">
          <div v-if="feoImport.result" class="d-flex flex-wrap gap-2 mb-3">
            <v-chip color="success" variant="flat"
              :disabled="!feoImport.result.created_details?.length"
              @click="feoToggleResultPanel('created')">
              <v-icon icon="mdi-plus-circle" start size="16" />Создано: {{ feoImport.result.created ?? 0 }}
              <v-icon v-if="feoImport.result.created_details?.length" end size="16"
                :icon="feoResultPanels.includes('created') ? 'mdi-chevron-up' : 'mdi-chevron-down'" />
            </v-chip>
            <v-chip color="warning" variant="flat"
              :disabled="!feoImport.result.updated_details?.length"
              @click="feoToggleResultPanel('updated')">
              <v-icon icon="mdi-pencil" start size="16" />Обновлено: {{ feoImport.result.updated ?? 0 }}
              <v-icon v-if="feoImport.result.updated_details?.length" end size="16"
                :icon="feoResultPanels.includes('updated') ? 'mdi-chevron-up' : 'mdi-chevron-down'" />
            </v-chip>
            <v-chip color="grey" variant="flat"
              :disabled="!feoImport.result.skipped_details?.length"
              @click="feoToggleResultPanel('skipped')">
              <v-icon icon="mdi-debug-step-over" start size="16" />Пропущено: {{ feoImport.result.skipped }}
              <v-icon v-if="feoImport.result.skipped_details?.length" end size="16"
                :icon="feoResultPanels.includes('skipped') ? 'mdi-chevron-up' : 'mdi-chevron-down'" />
            </v-chip>
          </div>
          <v-expansion-panels v-if="feoImport.result" v-model="feoResultPanels" multiple class="mb-3">
            <v-expansion-panel v-if="feoImport.result.created_details?.length" value="created">
              <v-expansion-panel-title>
                <v-icon icon="mdi-plus-circle" size="18" color="success" class="mr-2" />
                Созданные позиции ({{ feoImport.result.created_details.length }})
              </v-expansion-panel-title>
              <v-expansion-panel-text>
                <v-list density="compact" max-height="320" class="overflow-y-auto">
                  <v-list-item v-for="(d, i) in feoImport.result.created_details" :key="i"
                    :title="d.name" :subtitle="`Стр. ${d.row} — ${d.reason}`" />
                </v-list>
              </v-expansion-panel-text>
            </v-expansion-panel>
            <v-expansion-panel v-if="feoImport.result.updated_details?.length" value="updated">
              <v-expansion-panel-title>
                <v-icon icon="mdi-pencil" size="18" color="warning" class="mr-2" />
                Обновлённые позиции ({{ feoImport.result.updated_details.length }})
              </v-expansion-panel-title>
              <v-expansion-panel-text>
                <v-list density="compact" max-height="320" class="overflow-y-auto">
                  <v-list-item v-for="(d, i) in feoImport.result.updated_details" :key="i"
                    :title="d.name" :subtitle="`Стр. ${d.row} — ${d.reason}`" />
                </v-list>
              </v-expansion-panel-text>
            </v-expansion-panel>
            <v-expansion-panel v-if="feoImport.result.skipped_details?.length" value="skipped">
              <v-expansion-panel-title>
                <v-icon icon="mdi-debug-step-over" size="18" color="grey" class="mr-2" />
                Пропущенные позиции ({{ feoImport.result.skipped_details.length }})
              </v-expansion-panel-title>
              <v-expansion-panel-text>
                <v-list density="compact" max-height="320" class="overflow-y-auto">
                  <v-list-item v-for="(d, i) in feoImport.result.skipped_details" :key="i"
                    :title="d.name" :subtitle="`Стр. ${d.row} — ${d.reason}`" />
                </v-list>
              </v-expansion-panel-text>
            </v-expansion-panel>
          </v-expansion-panels>
          <!-- Итоги переезда/удаления узлов -->
          <div v-if="feoImport.result?.relinked_count || feoImport.result?.deleted_count" class="text-body-2 mb-2">
            <div v-if="feoImport.result?.relinked_count">Перенесено ссылок: {{ feoImport.result.relinked_count }}</div>
            <div v-if="feoImport.result?.deleted_count">Удалено узлов: {{ feoImport.result.deleted_count }}</div>
          </div>
          <v-alert v-if="feoImport.result?.version_created" type="info" variant="tonal" density="compact"
            icon="mdi-history" class="mb-3">
            Создана предыдущая редакция плана закупок (доступна в истории для выгрузки)
          </v-alert>
          <v-expansion-panels v-if="feoImport.result?.deleted_details?.length || feoImport.result?.remap_applied?.length"
            v-model="feoResultPanels" multiple class="mb-3">
            <v-expansion-panel v-if="feoImport.result?.deleted_details?.length" value="result_deleted">
              <v-expansion-panel-title>
                <v-icon icon="mdi-delete-outline" size="18" color="error" class="mr-2" />
                Удалённые узлы ({{ feoImport.result.deleted_details.length }})
              </v-expansion-panel-title>
              <v-expansion-panel-text>
                <v-list density="compact" max-height="240" class="overflow-y-auto">
                  <v-list-item v-for="(d, i) in feoImport.result.deleted_details" :key="i"
                    :title="d.path" :subtitle="d.reason" />
                </v-list>
              </v-expansion-panel-text>
            </v-expansion-panel>
            <v-expansion-panel v-if="feoImport.result?.remap_applied?.length" value="result_remap">
              <v-expansion-panel-title>
                <v-icon icon="mdi-swap-horizontal" size="18" color="primary" class="mr-2" />
                Перенесённые узлы ({{ feoImport.result.remap_applied.length }})
              </v-expansion-panel-title>
              <v-expansion-panel-text>
                <v-list density="compact" max-height="280" class="overflow-y-auto">
                  <v-list-item v-for="(r, i) in feoImport.result.remap_applied" :key="i"
                    :title="`${r.old_path} → ${r.new_path}`" />
                </v-list>
              </v-expansion-panel-text>
            </v-expansion-panel>
          </v-expansion-panels>
          <!-- Предупреждения итогового импорта (те же kinds, но факт, не прогноз) -->
          <template v-if="feoImport.result?.warnings?.length">
            <div class="text-subtitle-2 mb-1 text-warning">Предупреждения ({{ feoImport.result.warnings.length }}):</div>
            <v-expansion-panels v-model="feoResultPanels" multiple class="mb-3">
              <v-expansion-panel
                v-for="kind in [...new Set(feoImport.result.warnings.map(w => w.kind))]"
                :key="'rw_' + kind"
                :value="'rw_' + kind">
                <v-expansion-panel-title>
                  <v-icon icon="mdi-alert-outline" size="18" color="warning" class="mr-2" />
                  {{ feoWarnKindLabel(kind) }} ({{ feoImport.result.warnings!.filter(w => w.kind === kind).length }})
                </v-expansion-panel-title>
                <v-expansion-panel-text>
                  <v-list density="compact" max-height="280" class="overflow-y-auto">
                    <v-list-item
                      v-for="(w, wi) in feoImport.result.warnings!.filter(x => x.kind === kind)"
                      :key="wi"
                      :title="w.name"
                      :subtitle="feoWarnSubtitle(w)" />
                  </v-list>
                </v-expansion-panel-text>
              </v-expansion-panel>
            </v-expansion-panels>
          </template>
          <div v-if="feoImport.result?.errors?.length" class="mt-2">
            <div class="text-subtitle-2 mb-1 text-error">Ошибки ({{ feoImport.result.errors.length }}):</div>
            <v-list density="compact" class="bg-error-lighten-5 rounded">
              <v-list-item v-for="(e, i) in feoImport.result.errors" :key="i"
                :subtitle="`Стр. ${e.row}: ${e.name} — ${e.message}`" />
            </v-list>
          </div>
        </template>

      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-btn v-if="feoImport.step === 2" variant="text" @click="feoImport.step = 1">
          <v-icon icon="mdi-arrow-left" class="mr-1" /> Назад
        </v-btn>
        <v-btn v-if="feoImport.step === 3" variant="text" @click="feoImport.step = 2">
          <v-icon icon="mdi-arrow-left" class="mr-1" /> Назад к сопоставлению
        </v-btn>
        <v-btn v-if="feoImport.step === 4" variant="text" @click="feoImport.step = 3">
          <v-icon icon="mdi-arrow-left" class="mr-1" /> Назад
        </v-btn>
        <v-spacer />
        <v-btn variant="text" @click="closeFeoImport">{{ feoImport.step === 5 ? 'Закрыть' : 'Отмена' }}</v-btn>
        <v-btn v-if="feoImport.step === 1" color="primary" :loading="feoImport.loading"
          :disabled="!feoImport.file" @click="doFeoImport">Далее</v-btn>
        <!-- Шаг 2: запускает dry-run → шаг 3 (Проверка) -->
        <v-btn v-if="feoImport.step === 2" color="primary" variant="flat"
          :loading="feoImport.loading" :disabled="!feoMappingValid"
          @click="doFeoMappedImport(true)">Проверить</v-btn>
        <!-- Шаг 3: если есть несопоставленные узлы — на шаг 4 (Сопоставление), иначе сразу реальный импорт → шаг 5 -->
        <v-btn v-if="feoImport.step === 3 && feoUnmatchedNeedsMapping.length" color="primary" variant="flat"
          :disabled="!!(feoImport.dryResult?.errors?.length)"
          @click="feoImport.step = 4">Сопоставить ({{ feoUnmatchedNeedsMapping.length }})</v-btn>
        <v-btn v-if="feoImport.step === 3 && !feoUnmatchedNeedsMapping.length" color="success" variant="flat"
          :loading="feoImport.loading"
          :disabled="!!(feoImport.dryResult?.errors?.length)"
          @click="doFeoMappedImport(false)">Импортировать<template v-if="feoImport.dryResult?.deleted_count">, удалить {{ feoImport.dryResult.deleted_count }}</template></v-btn>
        <!-- Шаг 4: пересчитать прогноз с текущим remap или перейти к реальному импорту → шаг 5 -->
        <v-btn v-if="feoImport.step === 4" variant="tonal" :loading="feoImport.loading"
          @click="doFeoMappedImport(true, true)">
          <v-icon icon="mdi-refresh" class="mr-1" /> Пересчитать
        </v-btn>
        <v-btn v-if="feoImport.step === 4" color="success" variant="flat"
          :loading="feoImport.loading"
          :disabled="!!(feoImport.dryResult?.errors?.length)"
          @click="doFeoMappedImport(false)">{{ feoStep4MainLabel }}</v-btn>
        <v-btn v-if="feoImport.step === 5" color="primary" variant="flat"
          @click="closeFeoImport">Готово</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
// Мастер импорта категорий ФЭО из Excel/Word/PDF — вынесен из SubsidiesView.vue.
// Состояние/логика — в useFeoImport.ts (singleton, тот же паттерн, что и
// useSubsidyApprovers.ts/usePlanGraphVersions.ts/usePlannedItems.ts): кнопка
// «Импорт» в тулбаре дерева ФЭО (SubsidiesView.vue) продолжает открывать этот
// диалог напрямую через `feoImport.show = true` — тот же реактивный объект,
// импортированный из useFeoImport.ts.
import { useDisplay } from 'vuetify'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { useFeoImport } from '@/composables/subsidies/useFeoImport'
import FeoImportMappingStep from './FeoImportMappingStep.vue'

const { mobile } = useDisplay()
const {
  feoImport, feoResultPanels, feoToggleResultPanel,
  feoUnmatchedNeedsMapping, feoHasSuggestions, feoAcceptAllSuggestions,
  feoStep4MainLabel, feoLoadSummary, feoMappingValid,
  feoWarnKindLabel, feoWarnSubtitle,
  doFeoImport, doFeoMappedImport, closeFeoImport,
} = useFeoImport(useSubsidyDetailCtx())
</script>
