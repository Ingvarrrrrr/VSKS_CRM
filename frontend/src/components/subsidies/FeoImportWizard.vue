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
            :hint="`Перетащите файл сюда или нажмите для выбора. Максимум ${MAX_UPLOAD_SIZE_MB} МБ.`"
            persistent-hint
            :rules="[(files: File[] | File | null) => checkUploadSize(Array.isArray(files) ? files[0] : files) || true]"
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
          <!-- Баг владельца 23.09: после смены решения (радио-кнопки ниже)
               предупреждения и счётчики создано/обновлено/пропущено — от
               СТАРОГО прогноза, пока не придёт свежий dry-run (см.
               feoScheduleRecompute в useFeoImport.ts). Индикатор + приглушение
               блока — чтобы не читать устаревшие цифры (правило проекта: долгая
               операция не оставляет мёртвый экран). -->
          <v-progress-linear v-if="feoImport.recomputing" indeterminate color="primary" height="3" class="mb-3" />
          <v-alert v-if="feoImport.recomputeError" type="error" variant="tonal" density="compact" class="mb-3" icon="mdi-alert-circle">
            Не удалось пересчитать прогноз: {{ feoImport.recomputeError }}. Показаны прежние (устаревшие) цифры.
            <v-btn size="small" variant="text" color="error" class="ml-2" @click="feoRecomputeNow">Повторить</v-btn>
          </v-alert>
          <!-- D (баг 2026-09-09): куда реально идёт импорт — колонка «Субсидия»
               файла на это НЕ влияет, побеждает всегда открытая карточка. -->
          <v-alert v-if="feoImportTargetSubsidyName" type="success" variant="tonal" density="compact"
            class="mb-3" icon="mdi-target">
            Импорт в субсидию: <strong>{{ feoImportTargetSubsidyName }}</strong>
          </v-alert>
          <!-- Предупреждение «субсидия из файла проигнорирована» — заметно, не
               мелким пунктом в общем списке ниже. -->
          <v-alert
            v-if="feoImport.dryResult?.warnings?.some(w => w.kind === 'subsidy_name_ignored')"
            type="warning" variant="tonal" density="compact" class="mb-3" icon="mdi-alert">
            <div v-for="(w, wi) in feoImport.dryResult!.warnings!.filter(x => x.kind === 'subsidy_name_ignored')" :key="wi">
              {{ w.message }}
            </div>
          </v-alert>
          <!-- Волна 4, п.23 (владелец): полное совпадение имени Ур.5 внутри
               одной категории — предложить решение, а не решать самовольно.
               По умолчанию «оставить как есть» (пять «чайников» могли быть
               заведены намеренно — пять разных закупок); «объединить» —
               суммы/количества складываются, цена — от деления, деньги не
               меняются ни на рубль. Решение — по КАЖДОЙ группе отдельно. -->
          <v-alert v-if="feoDuplicateGroups.length" type="warning" variant="tonal" density="compact"
            class="mb-3" icon="mdi-content-duplicate">
            <div class="text-body-2 mb-2">
              В файле {{ feoDuplicateGroups.length }}
              {{ feoPluralRu(feoDuplicateGroups.length, ['группа', 'группы', 'групп']) }} строк с одинаковым
              (без учёта регистра и пробелов) названием в одной категории — решите по каждой.
            </div>
            <v-card v-for="g in feoDuplicateGroups" :key="g.key" variant="outlined" class="mb-2 pa-3">
              <div class="text-subtitle-2">
                «{{ g.name }}» <span class="text-medium-emphasis">— {{ g.category_path }}</span>
              </div>
              <v-list density="compact" class="my-1">
                <v-list-item v-for="r in g.rows" :key="r.row" :lines="false" class="px-0">
                  <template #title>
                    <span class="feo-wrap-text">
                      Стр. {{ r.row }}<template v-if="r.qty != null">, кол-во {{ r.qty }}{{ r.unit ? ' ' + r.unit : '' }}</template>
                      — {{ formatCurrency(r.amount ?? 0) }}
                    </span>
                  </template>
                </v-list-item>
              </v-list>
              <v-radio-group
                :model-value="feoResolutionFor(g.key)"
                @update:model-value="(v: 'merge' | 'keep' | null) => feoSetResolution(g.key, v ?? 'keep')"
                inline hide-details density="compact" class="mt-1">
                <v-radio label="Оставить как есть" value="keep" />
                <v-radio value="merge">
                  <template #label>
                    <span>
                      Объединить в одну (сумма {{ formatCurrency(g.merged_preview.amount ?? 0) }},
                      кол-во {{ g.merged_preview.qty != null ? g.merged_preview.qty + (g.merged_preview.unit ? ' ' + g.merged_preview.unit : '') : 'не задано' }},
                      цена {{ g.merged_preview.price != null ? formatCurrency(g.merged_preview.price) + ' за ед.' : 'не задана (количество не у всех строк указано)' }})
                    </span>
                  </template>
                </v-radio>
              </v-radio-group>
            </v-card>
          </v-alert>
          <!-- Владелец (2026-09-15, опрос): одна КАТЕГОРИЯ (строка-заголовок
               без «Плановой позиции»), чья Сумма по ФЭО объявлена в файле
               НЕСКОЛЬКИМИ строками с РАЗНЫМИ суммами — не брать молча
               последнюю, решение принимает человек по каждой такой
               категории. Тот же стиль карточек, что и у дублей Ур.5 выше. -->
          <v-alert v-if="feoBudgetConflictGroups.length" type="warning" variant="tonal" density="compact"
            class="mb-3" icon="mdi-cash-sync">
            <div class="text-body-2 mb-2">
              В файле {{ feoBudgetConflictGroups.length }}
              {{ feoPluralRu(feoBudgetConflictGroups.length, ['категория', 'категории', 'категорий']) }},
              для которых Сумма по ФЭО задана несколькими строками с РАЗНЫМИ суммами — решите по каждой.
            </div>
            <v-card v-for="g in feoBudgetConflictGroups" :key="g.key" variant="outlined" class="mb-2 pa-3">
              <div class="text-subtitle-2">
                «{{ g.name }}» <span class="text-medium-emphasis">— {{ g.category_path }}</span>
              </div>
              <!-- Владелец 2026-09-22 (дословно): «Там 4 суммы — должно
                   предлагать 4 суммы на выбор. Было бы 3 — три. Это
                   динамическое поле» — ОДИН список радио-кнопок по
                   g.options.rows (по строке файла на кнопку, а не фиксированные
                   «первая/последняя» рядом со списком строк — Правило №6,
                   тот список и три радио были дублем одного и того же). -->
              <v-radio-group
                :model-value="feoBudgetResolutionFor(g)"
                @update:model-value="(v: string | null) => feoSetBudgetResolution(g.key, v ?? 'last')"
                hide-details density="compact" class="mt-1">
                <v-radio v-for="r in g.options.rows" :key="r.value" :value="r.value">
                  <template #label>
                    <span class="feo-wrap-text">Стр. {{ r.row }} — {{ formatCurrency(r.amount ?? 0) }}</span>
                  </template>
                </v-radio>
                <v-radio value="sum">
                  <template #label>
                    <span>Сложить ({{ formatCurrency(g.options.sum.amount ?? 0) }})</span>
                  </template>
                </v-radio>
              </v-radio-group>
            </v-card>
          </v-alert>
          <!-- Владелец (2026-09-16, дословно): категория, у которой в файле
               заполнены И собственная сумма (строка-заголовок), И
               собственные позиции с суммой по ФЭО — сейчас молча побеждает
               собственная сумма категории (compute_budget_map), это
               остаётся поведением по умолчанию («Взять сумму категории»),
               но при переносе даём выбрать явно. Тот же стиль карточек, что
               и у конфликтов сумм выше. -->
          <v-alert v-if="feoCategorySumConflictGroups.length" type="warning" variant="tonal" density="compact"
            class="mb-3" icon="mdi-scale-balance">
            <div class="text-body-2 mb-2">
              В файле {{ feoCategorySumConflictGroups.length }}
              {{ feoPluralRu(feoCategorySumConflictGroups.length, ['категория', 'категории', 'категорий']) }},
              для которых заданы И собственная сумма по ФЭО, И сумма вложенных позиций — решите по каждой.
            </div>
            <v-card v-for="g in feoCategorySumConflictGroups" :key="g.key" variant="outlined" class="mb-2 pa-3">
              <div class="text-subtitle-2">
                «{{ g.name }}» <span class="text-medium-emphasis">— {{ g.category_path }}</span>
              </div>
              <v-radio-group
                :model-value="feoCatSumResolutionFor(g.key)"
                @update:model-value="(v: 'own' | 'items' | null) => feoSetCatSumResolution(g.key, v ?? 'own')"
                hide-details density="compact" class="mt-1">
                <v-radio value="own">
                  <template #label>
                    <span>Взять сумму категории ({{ formatCurrency(g.own_amount ?? 0) }})</span>
                  </template>
                </v-radio>
                <v-radio value="items">
                  <template #label>
                    <span>Взять сумму позиций ({{ formatCurrency(g.items_amount ?? 0) }}, позиций: {{ g.items_count }})</span>
                  </template>
                </v-radio>
              </v-radio-group>
            </v-card>
          </v-alert>
          <!-- Задача 2026-09-22: товар/услуга/работа из файла расходится со
               значением уже сопоставленного товара в каталоге — отдельный
               компонент (Правило №5), тот же singleton useFeoImport.ts. -->
          <FeoImportItemTypeConflicts />
          <!-- Счётчики/предупреждения/детали ниже — приглушаются, пока прогноз
               устарел (feoImport.resultStale, см. докстринг выше). Сами решения
               (радио-кнопки/переключатели выше) остаются кликабельными —
               дебаунс их не блокирует, серия кликов схлопывается в один запрос. -->
          <div :class="{ 'feo-stale-block': feoImport.resultStale }">
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
            <v-chip v-if="feoImport.dryResult.comments_created" color="info" variant="flat">
              <v-icon icon="mdi-comment-text-outline" start size="16" />Будет создано комментариев: {{ feoImport.dryResult.comments_created }}
            </v-chip>
          </div>
          <!-- Предупреждения dry-run -->
          <template v-if="feoImport.dryResult?.warnings?.length">
            <div class="text-subtitle-2 mb-1 text-warning">Предупреждения ({{ feoImport.dryResult.warnings.length }}):</div>
            <v-expansion-panels v-model="feoResultPanels" multiple class="mb-3">
              <v-expansion-panel
                v-for="kind in feoWarnKinds(feoImport.dryResult.warnings.filter(w => w.kind !== 'subsidy_name_ignored'))"
                :key="'dw_' + kind"
                :value="'dw_' + kind">
                <v-expansion-panel-title>
                  <v-icon
                    :icon="feoWarnKindIsAlert(kind) ? 'mdi-account-alert' : 'mdi-alert-outline'"
                    size="18" :color="feoWarnKindIsAlert(kind) ? 'error' : 'warning'" class="mr-2" />
                  {{ feoWarnKindLabel(kind) }} ({{ feoImport.dryResult.warnings.filter(w => w.kind === kind).length }})
                </v-expansion-panel-title>
                <v-expansion-panel-text>
                  <v-list density="compact" max-height="280" class="overflow-y-auto">
                    <v-list-item
                      v-for="(w, wi) in feoImport.dryResult.warnings.filter(x => x.kind === kind)"
                      :key="wi" :lines="false">
                      <template v-if="w.name" #title><span class="feo-wrap-text">{{ w.name }}</span></template>
                      <template #subtitle><span class="feo-wrap-text">{{ feoWarnSubtitle(w) }}</span></template>
                    </v-list-item>
                  </v-list>
                </v-expansion-panel-text>
              </v-expansion-panel>
            </v-expansion-panels>
          </template>
          <!-- Ошибки dry-run — красным, блокируют импорт -->
          <div v-if="feoImport.dryResult?.errors?.length" class="mt-2">
            <div class="text-subtitle-2 mb-1 text-error">Ошибки ({{ feoImport.dryResult.errors.length }}) — исправьте файл перед импортом:</div>
            <v-list density="compact" class="bg-error-lighten-5 rounded">
              <v-list-item v-for="(e, i) in feoImport.dryResult.errors" :key="i" :lines="false">
                <template #subtitle><span class="feo-wrap-text">Стр. {{ e.row }}: {{ e.name }} — {{ e.message }}</span></template>
              </v-list-item>
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
                  <v-list-item v-for="(d, i) in feoImport.dryResult.created_details" :key="i" :lines="false">
                    <template #title><span class="feo-wrap-text">{{ d.name }}</span></template>
                    <template #subtitle><span class="feo-wrap-text">Стр. {{ d.row }} — {{ d.reason }}</span></template>
                  </v-list-item>
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
                  <v-list-item v-for="(d, i) in feoImport.dryResult.updated_details" :key="i" :lines="false">
                    <template #title><span class="feo-wrap-text">{{ d.name }}</span></template>
                    <template #subtitle><span class="feo-wrap-text">Стр. {{ d.row }} — {{ d.reason }}</span></template>
                  </v-list-item>
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
                  <v-list-item v-for="(d, i) in feoImport.dryResult.skipped_details" :key="i" :lines="false">
                    <template #title><span class="feo-wrap-text">{{ d.name }}</span></template>
                    <template #subtitle><span class="feo-wrap-text">Стр. {{ d.row }} — {{ d.reason }}</span></template>
                  </v-list-item>
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
                  <v-list-item v-for="(d, i) in feoImport.dryResult.deleted_details" :key="i" :lines="false">
                    <template #title><span class="feo-wrap-text">{{ d.path }}</span></template>
                    <template #subtitle><span class="feo-wrap-text">{{ d.reason }}</span></template>
                  </v-list-item>
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
              <v-list-item v-for="n in feoUnmatchedNeedsMapping" :key="n.id" :lines="false">
                <template #title><span class="feo-wrap-text">{{ n.path }}</span></template>
                <template #subtitle><span class="feo-wrap-text">{{ feoLoadSummary(n.load) }}</span></template>
              </v-list-item>
            </v-list>
          </template>
          <v-alert v-if="feoImport.dryResult?.remap_aborted_reason" type="warning" variant="tonal"
            icon="mdi-alert" class="mb-3">
            {{ feoImport.dryResult.remap_aborted_reason }}
          </v-alert>
          </div>
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
          <v-alert v-if="feoImportTargetSubsidyName" type="success" variant="tonal" density="compact"
            class="mb-3" icon="mdi-target">
            Импорт в субсидию: <strong>{{ feoImportTargetSubsidyName }}</strong>
          </v-alert>
          <v-alert
            v-if="feoImport.result?.warnings?.some(w => w.kind === 'subsidy_name_ignored')"
            type="warning" variant="tonal" density="compact" class="mb-3" icon="mdi-alert">
            <div v-for="(w, wi) in feoImport.result!.warnings!.filter(x => x.kind === 'subsidy_name_ignored')" :key="wi">
              {{ w.message }}
            </div>
          </v-alert>
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
                  <v-list-item v-for="(d, i) in feoImport.result.created_details" :key="i" :lines="false">
                    <template #title><span class="feo-wrap-text">{{ d.name }}</span></template>
                    <template #subtitle><span class="feo-wrap-text">Стр. {{ d.row }} — {{ d.reason }}</span></template>
                  </v-list-item>
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
                  <v-list-item v-for="(d, i) in feoImport.result.updated_details" :key="i" :lines="false">
                    <template #title><span class="feo-wrap-text">{{ d.name }}</span></template>
                    <template #subtitle><span class="feo-wrap-text">Стр. {{ d.row }} — {{ d.reason }}</span></template>
                  </v-list-item>
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
                  <v-list-item v-for="(d, i) in feoImport.result.skipped_details" :key="i" :lines="false">
                    <template #title><span class="feo-wrap-text">{{ d.name }}</span></template>
                    <template #subtitle><span class="feo-wrap-text">Стр. {{ d.row }} — {{ d.reason }}</span></template>
                  </v-list-item>
                </v-list>
              </v-expansion-panel-text>
            </v-expansion-panel>
          </v-expansion-panels>
          <!-- Итоги переезда/удаления узлов -->
          <div v-if="feoImport.result?.relinked_count || feoImport.result?.deleted_count || feoImport.result?.comments_created"
            class="text-body-2 mb-2">
            <div v-if="feoImport.result?.relinked_count">Перенесено ссылок: {{ feoImport.result.relinked_count }}</div>
            <div v-if="feoImport.result?.deleted_count">Удалено узлов: {{ feoImport.result.deleted_count }}</div>
            <div v-if="feoImport.result?.comments_created">Создано комментариев: {{ feoImport.result.comments_created }}</div>
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
                  <v-list-item v-for="(d, i) in feoImport.result.deleted_details" :key="i" :lines="false">
                    <template #title><span class="feo-wrap-text">{{ d.path }}</span></template>
                    <template #subtitle><span class="feo-wrap-text">{{ d.reason }}</span></template>
                  </v-list-item>
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
                  <v-list-item v-for="(r, i) in feoImport.result.remap_applied" :key="i" :lines="false">
                    <template #title><span class="feo-wrap-text">{{ r.old_path }} → {{ r.new_path }}</span></template>
                  </v-list-item>
                </v-list>
              </v-expansion-panel-text>
            </v-expansion-panel>
          </v-expansion-panels>
          <!-- Предупреждения итогового импорта (те же kinds, но факт, не прогноз) -->
          <template v-if="feoImport.result?.warnings?.length">
            <div class="text-subtitle-2 mb-1 text-warning">Предупреждения ({{ feoImport.result.warnings.length }}):</div>
            <v-expansion-panels v-model="feoResultPanels" multiple class="mb-3">
              <v-expansion-panel
                v-for="kind in feoWarnKinds(feoImport.result.warnings.filter(w => w.kind !== 'subsidy_name_ignored'))"
                :key="'rw_' + kind"
                :value="'rw_' + kind">
                <v-expansion-panel-title>
                  <v-icon
                    :icon="feoWarnKindIsAlert(kind) ? 'mdi-account-alert' : 'mdi-alert-outline'"
                    size="18" :color="feoWarnKindIsAlert(kind) ? 'error' : 'warning'" class="mr-2" />
                  {{ feoWarnKindLabel(kind) }} ({{ feoImport.result.warnings!.filter(w => w.kind === kind).length }})
                </v-expansion-panel-title>
                <v-expansion-panel-text>
                  <v-list density="compact" max-height="280" class="overflow-y-auto">
                    <v-list-item
                      v-for="(w, wi) in feoImport.result.warnings!.filter(x => x.kind === kind)"
                      :key="wi" :lines="false">
                      <template v-if="w.name" #title><span class="feo-wrap-text">{{ w.name }}</span></template>
                      <template #subtitle><span class="feo-wrap-text">{{ feoWarnSubtitle(w) }}</span></template>
                    </v-list-item>
                  </v-list>
                </v-expansion-panel-text>
              </v-expansion-panel>
            </v-expansion-panels>
          </template>
          <div v-if="feoImport.result?.errors?.length" class="mt-2">
            <div class="text-subtitle-2 mb-1 text-error">Ошибки ({{ feoImport.result.errors.length }}):</div>
            <v-list density="compact" class="bg-error-lighten-5 rounded">
              <v-list-item v-for="(e, i) in feoImport.result.errors" :key="i" :lines="false">
                <template #subtitle><span class="feo-wrap-text">Стр. {{ e.row }}: {{ e.name }} — {{ e.message }}</span></template>
              </v-list-item>
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
        <!-- Шаг 3: если есть несопоставленные узлы — на шаг 4 (Сопоставление), иначе сразу реальный импорт → шаг 5.
             Пока прогноз устарел/пересчитывается (feoImport.resultStale/recomputing) — обе кнопки заблокированы,
             человек не должен импортировать по цифрам, которые ещё не отражают его выбор (баг 23.09). -->
        <v-btn v-if="feoImport.step === 3 && feoUnmatchedNeedsMapping.length" color="primary" variant="flat"
          :disabled="!!(feoImport.dryResult?.errors?.length) || feoImport.resultStale"
          @click="feoImport.step = 4">Сопоставить ({{ feoUnmatchedNeedsMapping.length }})</v-btn>
        <v-btn v-if="feoImport.step === 3 && !feoUnmatchedNeedsMapping.length" color="success" variant="flat"
          :loading="feoImport.loading"
          :disabled="!!(feoImport.dryResult?.errors?.length) || feoImport.resultStale"
          @click="doFeoMappedImport(false)">Импортировать<template v-if="feoImport.dryResult?.deleted_count">, удалить {{ feoImport.dryResult.deleted_count }}</template></v-btn>
        <!-- Шаг 4: пересчитать прогноз с текущим remap или перейти к реальному импорту → шаг 5.
             feoRecomputeNow — тот же канал, что и автопересчёт после радио-кнопок на шаге 3
             (feoScheduleRecompute в useFeoImport.ts), просто без ожидания дебаунса. -->
        <v-btn v-if="feoImport.step === 4" variant="tonal" :loading="feoImport.recomputing"
          @click="feoRecomputeNow">
          <v-icon icon="mdi-refresh" class="mr-1" /> Пересчитать
        </v-btn>
        <v-btn v-if="feoImport.step === 4" color="success" variant="flat"
          :loading="feoImport.loading"
          :disabled="!!(feoImport.dryResult?.errors?.length) || feoImport.resultStale"
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
import { formatCurrency } from '@/composables/subsidies/format'
import { MAX_UPLOAD_SIZE_MB, checkUploadSize } from '@/constants/uploadLimits'
import FeoImportMappingStep from './FeoImportMappingStep.vue'
import FeoImportItemTypeConflicts from './FeoImportItemTypeConflicts.vue'

const { mobile } = useDisplay()
const {
  feoImport, feoImportTargetSubsidyName, feoResultPanels, feoToggleResultPanel,
  feoDuplicateGroups, feoResolutionFor, feoSetResolution,
  feoBudgetConflictGroups, feoBudgetResolutionFor, feoSetBudgetResolution,
  feoCategorySumConflictGroups, feoCatSumResolutionFor, feoSetCatSumResolution,
  feoUnmatchedNeedsMapping, feoHasSuggestions, feoAcceptAllSuggestions,
  feoStep4MainLabel, feoLoadSummary, feoPluralRu, feoMappingValid,
  feoWarnKindLabel, feoWarnSubtitle, feoWarnKindIsAlert, feoWarnKinds,
  doFeoImport, doFeoMappedImport, closeFeoImport, feoRecomputeNow,
} = useFeoImport(useSubsidyDetailCtx())
</script>

<style scoped>
/* .dialog-card/.dialog-title — было в <style scoped> SubsidiesView.vue, пока
   диалог был её частью; вынесено вместе с диалогом (волна 5c) — иначе scoped CSS
   другого файла эти классы не достаёт (проверено на ContractorEditDialog.vue —
   тот же паттерн: каждый диалог держит эти два правила у себя). */
.dialog-card {}
.dialog-title {
  display: flex; align-items: center;
  font-size: 16px !important; font-weight: 600 !important;
  padding: 16px 20px !important;
}
/* Владелец (волна 3, п.1): длинные предупреждения/пояснения в мастере импорта
   («Проверка» шаг 3 и «Результат» шаг 5) обрезались Vuetify-шним
   white-space:nowrap + text-overflow:ellipsis на .v-list-item-title/-subtitle —
   владелец видел «...» вместо полного текста. Раньше эти v-list-item задавали
   текст через props :title/:subtitle (обычный текст), а не через собственную
   разметку — CSS-правило на .v-list-item-title в scoped-стиле ЭТОГО файла не
   достало бы до div'а, который рендерит сам Vuetify внутри v-list-item (тот же
   инцидент со scoped CSS родителя, не достающим до потомков дочернего
   компонента). Поэтому текст теперь идёт через #title/#subtitle слоты
   собственным <span> — тот же приём, что уже работает в проекте (см.
   InlineProductMatch.vue #title, ItemsTableFlat.vue:227, ContractorPicker.vue:27):
   стиль объявлен прямо на span, который целиком наш, а не Vuetify-шний div —
   .feo-wrap-text применяется здесь же, как обычный scoped-класс. */
.feo-wrap-text {
  display: block;
  white-space: normal;
  word-break: break-word;
  line-height: 1.35;
}
.dialog-card :deep(.v-list-item) {
  min-height: unset;
}
/* Баг владельца 23.09: счётчики создано/обновлено/пропущено и предупреждения
   визуально приглушаются, пока прогноз устарел (см. feoImport.resultStale) —
   человек не должен принять их за актуальные, пока идёт автопересчёт. */
.feo-stale-block {
  opacity: .5;
  transition: opacity .15s ease;
}
</style>
