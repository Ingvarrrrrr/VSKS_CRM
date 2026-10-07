<template>
  <!-- Контрагент -->
  <div v-if="ctx.selectedSubsidy.value?.contractor_name" class="detail-contractor mt-2 mb-3">
    <v-icon icon="mdi-account-tie" size="16" color="teal" class="mr-1" />
    <span class="text-body-2 font-weight-medium">{{ ctx.selectedSubsidy.value?.contractor_name }}</span>
    <span v-if="ctx.selectedSubsidy.value?.contractor_inn" class="text-caption text-medium-emphasis ml-2">ИНН {{ ctx.selectedSubsidy.value?.contractor_inn }}</span>
    <v-btn
      icon="mdi-pencil-outline" size="x-small" variant="text" color="teal" class="ml-2"
      title="Реквизиты контрагента для этой субсидии"
      @click="ctx.openContractorOverride(ctx.selectedSubsidy.value!)"
    />
  </div>

  <div class="detail-feo-header">
    <span class="chart-card-title">Направления ФЭО</span>
    <div class="d-flex align-center ml-4" style="gap:6px" title="Группировка позиций «из заявок» при раскрытии направления">
      <span class="text-caption text-medium-emphasis">Позиции:</span>
      <v-btn-toggle v-model="ctx.feoItemsGroupBy.value" density="compact" mandatory variant="outlined" color="teal" style="height:26px" :disabled="ctx.plannedBase.value === 'purchases'">
        <v-btn size="x-small" value="none">Нет</v-btn>
        <v-btn size="x-small" value="category">По категориям</v-btn>
        <v-btn size="x-small" value="category_type">Категории + виды</v-btn>
      </v-btn-toggle>
    </div>
    <!-- Раздел C (план ancient-prancing-music.md, 2026-09-21): «целиком / товары-
         услуги» — общий pref useKpiPrefs.ts (localStorage-singleton, тот же
         паттерн, что и feoItemsGroupBy выше), общий с KpiCardsWidget.vue/
         SubsidyKpiCards.vue (другой агент) — состояние одно на все три места,
         второй переключатель здесь просто второй ВИЗУАЛЬНЫЙ экземпляр того же
         pref, не отдельное состояние. ⚠️ useKpiPrefs.ts на момент написания
         этого файла ещё не существовал (пишет другой агент параллельно) —
         импорт по согласованному пути, npx vue-tsc --noEmit перепроверить,
         когда файл появится. -->
    <div class="d-flex align-center ml-3" style="gap:6px" title="Показывать суммы категорий целиком или разбитыми на товары/услуги">
      <span class="text-caption text-medium-emphasis">Суммы:</span>
      <v-btn-toggle v-model="kpiPrefs.kpiTypeSplit.value" density="compact" mandatory variant="outlined" color="teal" style="height:26px">
        <v-btn size="x-small" value="total">Целиком</v-btn>
        <v-btn size="x-small" value="split">Товары и услуги</v-btn>
      </v-btn-toggle>
    </div>
    <!-- Поиск по субсидии в дереве ФЭО (владелец, 2026-09-15): «ОУ-2 огнетушитель не
         помню где находится... задолбался искать» — общий поиск по БД не привязан к
         текущей субсидии и не показывает путь. Ищет по названиям направлений/
         категорий (клиент, ctx.feoCategories уже загружены целиком) И по названиям
         плановых позиций (GET /feo-categories/plan-positions, тот же эндпоинт, что
         уже использует FeoPlannedItemsSelect.vue — см. useFeoTreeSearch.ts).
         Простое вхождение слов, порядок/регистр не важны. -->
    <div class="feo-search-wrap ml-2">
      <v-text-field
        v-model="ctx.feoSearchQuery.value"
        density="compact" variant="outlined" hide-details clearable
        placeholder="Поиск по субсидии…"
        prepend-inner-icon="mdi-magnify"
        @keydown.esc="ctx.feoSearchQuery.value = ''"
      />
      <div v-if="(ctx.feoSearchQuery.value || '').trim()" class="feo-search-dropdown">
        <div v-if="ctx.feoSearchLoading.value" class="feo-search-dropdown__empty">
          <v-progress-circular indeterminate size="16" width="2" color="teal" class="mr-2" />
          Загрузка плановых позиций…
        </div>
        <template v-else>
          <div v-if="!ctx.feoSearchResults.value.length" class="feo-search-dropdown__empty">
            Ничего не найдено
          </div>
          <div
            v-for="r in ctx.feoSearchResults.value" :key="r.key"
            class="feo-search-dropdown__item"
            @click="ctx.goToFeoSearchResult(r)"
          >
            <v-icon
              :icon="r.kind === 'planned_item' ? 'mdi-cube-outline' : 'mdi-folder-outline'"
              size="16" color="teal" class="mr-2"
            />
            <div class="feo-search-dropdown__text">
              <div class="feo-search-dropdown__name">{{ r.name }}</div>
              <div v-if="r.path" class="feo-search-dropdown__path">{{ r.path }}</div>
            </div>
          </div>
        </template>
      </div>
    </div>
    <div class="d-flex align-center ml-auto feo-toolbar-actions" style="gap:8px">
      <!-- Отмена/повтор дерева плана (владелец, п.4 волны 4, 2026-09-13): создание/
           правка/удаление/перенос плановых позиций + перенос категорий, глубина 5.
           Подпись в title называет КОНКРЕТНОЕ действие — «человек должен понимать,
           ЧТО именно отменится» (не просто «отменить»). Ctrl+Z/Ctrl+Y — тот же
           стек, хоткей навешан в SubsidiesView.vue (useFeoUndoStack.ts). -->
      <v-btn
        icon="mdi-undo" size="small" variant="text" color="blue-grey"
        :disabled="!ctx.canUndoFeo.value"
        :title="ctx.canUndoFeo.value ? `Отменить: ${ctx.feoUndoLabel.value} (Ctrl+Z)` : 'Отменить нечего'"
        @click="ctx.performFeoUndo()"
      />
      <v-btn
        icon="mdi-redo" size="small" variant="text" color="blue-grey"
        :disabled="!ctx.canRedoFeo.value"
        :title="ctx.canRedoFeo.value ? `Повторить: ${ctx.feoRedoLabel.value} (Ctrl+Y)` : 'Повторять нечего'"
        @click="ctx.performFeoRedo()"
      />
      <!-- «Создать закупку на основе плана» (владелец, лист 2 №7, 2026-09-20):
           режим выбора плановых позиций дерева ФЭО → полноэкранный подбор
           товара → создаётся ЗАЯВКА. Состояние/галочки — usePlanToRequest.ts
           (переиспользует selectedPlannedItemIds из useFeoLevel5Api, Правило №6),
           подсветка дерева — FeoTreeTable.vue (тот же синглтон). -->
      <template v-if="!planToRequest.active.value">
        <v-btn size="small" variant="tonal" color="deep-purple" prepend-icon="mdi-cart-plus"
          @click="planToRequest.startSelectMode(ctx.selectedId.value!)">
          Создать закупку на основе плана
        </v-btn>
      </template>
      <template v-else>
        <!-- «Вся смета» (владелец, задача 1) — toggle выбрать всё/снять всё по
             всей субсидии, тот же общий Set выбора, что и построчные/категорийные
             чекбоксы (usePlanToRequest.ts::selectWholeSmeta, Правило №6).
             Подпись и tooltip (правка 2026-09-21: владелец спросил, что значит
             «остаток») — RESIDUAL_SELECTION_TOOLTIP, единственный источник
             текста, второй не заводим. -->
        <v-tooltip location="top" open-delay="200">
          <template #activator="{ props: wholeSmetaTooltipProps }">
            <v-btn v-bind="wholeSmetaTooltipProps" size="small" variant="outlined" color="deep-purple"
              :prepend-icon="wholeSmetaAllSelected ? 'mdi-checkbox-multiple-blank-outline' : 'mdi-checkbox-multiple-marked-outline'"
              :loading="planToRequest.residualsLoading.value"
              @click="planToRequest.selectWholeSmeta(ctx.feoCategories.value, !wholeSmetaAllSelected)">
              {{ wholeSmetaAllSelected ? 'Снять всё' : 'Вся смета' }}
              <!-- Счётчик (владелец, задача 1б) — тот же источник, что и подпись
                   «выбрано k из N» на чекбоксах категорий
                   (usePlanToRequest.ts::wholeSmetaSelection().total, Правило №6). -->
              <span v-if="wholeSmetaSelectionState.total" class="ml-1">({{ wholeSmetaSelectionState.total }}{{ wholeSmetaAllSelected ? '' : ' незакупленных' }})</span>
            </v-btn>
          </template>
          <span>{{ RESIDUAL_SELECTION_TOOLTIP }}</span>
        </v-tooltip>
        <v-btn size="small" variant="flat" color="deep-purple"
          prepend-icon="mdi-check-bold"
          :disabled="planToRequest.selectedCount.value === 0"
          @click="planToRequest.openConfirmDialog(ctx.selectedId.value!, ctx.feoCategories.value, () => ctx.loadFeo(ctx.selectedId.value!))">
          Подтвердить выбор для создания закупки ({{ planToRequest.selectedCount.value }})
        </v-btn>
        <v-btn size="small" variant="text" color="grey-darken-1" @click="planToRequest.cancelSelectMode()">
          Отмена
        </v-btn>
      </template>
      <!-- «Что ещё заказать» (владелец, 04.10.2026, план .planning/quick/
           2026-10-04-sheet-ideas/PLAN.md, Волна B) — плановые позиции
           субсидии с остатком «без договоров», сгруппированные по «нужности».
           Состояние/данные — usePlanToOrderDialog.ts (Правило №6). Третий
           аргумент — итог карточки «Можно перераспределить» (not_committed_likely
           + not_committed_nice ЭТОЙ субсидии), чтобы итог окна совпадал с
           карточкой (приёмка 04.10.2026, субсидия «ХО» id 75 — расхождение). -->
      <v-btn size="small" variant="outlined" color="deep-purple" prepend-icon="mdi-cart-outline"
        @click="planToOrder.openPlanToOrderDialog(
          ctx.selectedId.value!,
          ctx.selectedSubsidy.value?.name,
          (ctx.selectedSubsidy.value?.not_committed_likely ?? 0) + (ctx.selectedSubsidy.value?.not_committed_nice ?? 0),
        )">
        Что ещё заказать
      </v-btn>
      <!-- «Свернуть категории-дубли» (владелец, задача 3) — categoryCollapse.ts,
           счётчик считается лениво при открытии субсидии (watch на ctx.selectedId
           ниже), кнопка скрыта при 0 кандидатов. -->
      <v-btn v-if="feoCollapse.candidatesCount.value > 0" size="small" variant="outlined" color="blue-grey-darken-1"
        prepend-icon="mdi-arrow-collapse-up"
        @click="feoCollapse.openBulkDialog(ctx.selectedId.value!)">
        Свернуть категории-дубли ({{ feoCollapse.candidatesCount.value }})
      </v-btn>
      <v-btn size="small" variant="outlined" color="success" prepend-icon="mdi-file-excel-outline" @click="openExportVersionsDialog">Выгрузить ФЭО</v-btn>
      <template v-if="ctx.canEditFeo.value">
        <v-tooltip location="bottom" max-width="320">
          <template #activator="{ props: feoTemplateTooltipProps }">
            <v-btn v-bind="feoTemplateTooltipProps" size="small" variant="outlined" prepend-icon="mdi-download-outline"
              @click="ctx.downloadFeoTemplate(ctx.selectedSubsidy.value?.id, ctx.selectedSubsidy.value?.name)">Шаблон</v-btn>
          </template>
          <!-- Решение владельца 05.10.2026: субсидию, у которой часть закупок
               уже прошла, грузят ОДНИМ файлом — необязательный блок «Факт». -->
          Если часть закупок уже прошла — заполните блок «Факт»: после загрузки плана система предложит загрузить их.
        </v-tooltip>
        <v-btn size="small" variant="outlined" color="secondary" prepend-icon="mdi-upload-outline" @click="feoImport.show = true">Импорт</v-btn>
        <v-btn size="small" variant="outlined" color="secondary" prepend-icon="mdi-upload-outline" @click="feoImport.show = true">Импорт</v-btn>
        <!-- «Импорт факта» (план breezy-mixing-lovelace.md, Часть 2) — уже
             совершённые закупки из таблиц ведения субсидии. Та же видимость,
             что у «Импорт» выше (ctx.canEditFeo). Журнал прогонов — пункт
             меню рядом с запуском нового импорта, не отдельная кнопка. -->
        <v-menu>
          <template #activator="{ props: factImportMenuProps }">
            <v-btn size="small" variant="outlined" color="deep-orange" prepend-icon="mdi-file-swap-outline"
              append-icon="mdi-chevron-down" v-bind="factImportMenuProps">
              Импорт факта
            </v-btn>
          </template>
          <v-list density="compact">
            <v-list-item prepend-icon="mdi-upload-outline" @click="openFactImport">
              <v-list-item-title>Новый импорт факта</v-list-item-title>
            </v-list-item>
            <v-list-item prepend-icon="mdi-history" @click="openFactImportRuns">
              <v-list-item-title>Журнал импорта факта</v-list-item-title>
            </v-list-item>
          </v-list>
        </v-menu>
      </template>
      <!-- 12-04: Version history -->
      <v-btn size="small" variant="text" color="blue-grey" prepend-icon="mdi-history" @click="openVersionHistory">
        История
      </v-btn>
      <!-- «Приравнять ФЭО к плану по всем статьям» (владелец 07.10.2026,
           решение №4, план .planning/quick/2026-10-07-dnr-feo-cards/PLAN.md
           шаг 3-5) — тот же гейт canSaveVersion, что у одиночного «Приравнять»
           в FeoTreeRow.vue (org_admin и выше). Подтверждение — отдельный
           диалог AlignBudgetAllDialog.vue (Правило №5, новая логика). -->
      <v-btn
        v-if="canSaveVersion"
        size="small"
        variant="outlined"
        color="blue-grey"
        prepend-icon="mdi-equal-box"
        title="ФЭО каждой статьи субсидии станет равным её полной плановой сумме"
        @click="ctx.selectedId.value && alignAllDialog?.open(ctx.selectedId.value)"
      >
        Приравнять ФЭО к плану по всем статьям
      </v-btn>
      <!-- 12-05: Save version -->
      <v-btn
        v-if="canSaveVersion"
        size="small"
        variant="text"
        color="success"
        prepend-icon="mdi-content-save"
        @click="openSaveVersionDialog"
      >
        Сохранить редакцию
      </v-btn>
      <!-- 12-04: Export dropdown -->
      <v-menu>
        <template #activator="{ props: menuProps }">
          <v-btn size="small" variant="outlined" color="teal" prepend-icon="mdi-export" append-icon="mdi-chevron-down" v-bind="menuProps">
            Экспорт
          </v-btn>
        </template>
        <v-list density="compact">
          <v-list-item prepend-icon="mdi-microsoft-excel" @click="exportPlanGraphExcel">
            <v-list-item-title>Excel (.xlsx)</v-list-item-title>
          </v-list-item>
          <v-list-item prepend-icon="mdi-microsoft-word" @click="exportPlanGraphDocx">
            <v-list-item-title>Word (шаблон)</v-list-item-title>
          </v-list-item>
          <v-list-item prepend-icon="mdi-file-pdf-box" @click="exportFeoPdf">
            <v-list-item-title>PDF (как на экране)</v-list-item-title>
          </v-list-item>
          <v-divider />
          <v-list-item prepend-icon="mdi-upload-outline">
            <v-list-item-title>
              <label style="cursor:pointer">
                Загрузить шаблон .docx
                <input type="file" accept=".docx" style="display:none"
                  @change="(e: any) => { if (e.target.files[0]) uploadTemplate(e.target.files[0]) }" />
              </label>
            </v-list-item-title>
          </v-list-item>
        </v-list>
      </v-menu>
      <v-btn v-if="ctx.canEditFeo.value" size="small" variant="tonal" color="primary" prepend-icon="mdi-plus" @click="ctx.openAddFeoDialog(null)">Добавить</v-btn>
    </div>
  </div>

  <!-- «Закуплено полностью» — легенда + переключатель «Скрыть закупленные
       полностью» (владелец, 30.09.2026, п.4-5): один флажок на всё дерево ФЭО
       и панель Ур.5 (useFeoHideFullyPurchased.ts, module-level singleton,
       Правило №6 — второй Set не заводим), запоминается в localStorage,
       по умолчанию выключен. Штриховка/чип читают
       usePlanToRequest.ts::isPlannedItemFullyTaken/isCategoryPlanFullyTaken/
       isCategoryFullyPurchased — те же формулы, что уже использует режим
       «Создать закупку на основе плана», второй расчёт остатка не заводим. -->
  <div class="feo-fully-purchased-legend">
    <span class="feo-fully-purchased-legend-swatch" />
    <span>— закуплено полностью (остаток по согласованным закупкам = 0)</span>
    <span class="feo-partially-purchased-legend-swatch ml-2" />
    <span>— закуплено частично</span>
    <v-switch
      v-model="hideFullyPurchased.hideFullyPurchased.value"
      density="compact" hide-details color="success" class="ml-4" style="flex:0 0 auto"
      :label="hideFullyPurchased.hideFullyPurchased.value ? 'скрыты' : 'скрыть закупленные полностью'"
    />
  </div>

  <!-- Подсказка режима выбора (владелец, лист 2 №7) — одной строкой под тулбаром,
       пока активен режим создания заявки из плана. -->
  <div v-if="planToRequest.active.value" class="plan-to-request-hint">
    <v-icon icon="mdi-cursor-default-click-outline" size="14" class="mr-1" />
    Отметьте плановые позиции галочками (построчно, категорией целиком или «Вся смета») — из них соберётся заявка
    <span v-if="planToRequest.residualsLoading.value" class="ml-2 text-medium-emphasis">(загрузка остатков…)</span>
  </div>

  <PlanToRequestDialog />
  <PlanToOrderDialog />
  <FeoCollapseCandidatesDialog />
  <FeoCollapseConfirmDialog />
  <FactImportWizard />
  <FactImportRunsPanel />
  <AlignBudgetAllDialog ref="alignAllDialog" />
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useToast, type ToastType } from '@/composables/useToast'
import { useRegistryExport } from '@/composables/useRegistryExport'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { usePlanGraphVersions } from '@/composables/subsidies/usePlanGraphVersions'
import { useFeoImport } from '@/composables/subsidies/useFeoImport'
import { usePlanToRequest, RESIDUAL_SELECTION_TOOLTIP } from '@/composables/subsidies/usePlanToRequest'
import { useFeoCategoryCollapse } from '@/composables/subsidies/useFeoCategoryCollapse'
import PlanToRequestDialog from '@/components/subsidies/PlanToRequestDialog.vue'
import FeoCollapseCandidatesDialog from '@/components/subsidies/FeoCollapseCandidatesDialog.vue'
import FeoCollapseConfirmDialog from '@/components/subsidies/FeoCollapseConfirmDialog.vue'
// Раздел C — см. докстринг у переключателя «Суммы» в шаблоне выше.
import { useKpiPrefs } from '@/composables/useKpiPrefs'
// «Закуплено полностью» (владелец, 30.09.2026) — см. докстринг у легенды/
// переключателя в шаблоне выше.
import { useFeoHideFullyPurchased } from '@/composables/subsidies/useFeoHideFullyPurchased'
// «Импорт факта» (план breezy-mixing-lovelace.md, Часть 2) — см. докстринг у
// кнопки-меню в шаблоне выше.
import { useFactImport } from '@/composables/subsidies/useFactImport'
import FactImportWizard from '@/components/subsidies/fact-import/FactImportWizard.vue'
import FactImportRunsPanel from '@/components/subsidies/fact-import/FactImportRunsPanel.vue'
// «Что ещё заказать» (владелец, 04.10.2026) — см. докстринг кнопки в шаблоне
// выше и usePlanToOrderDialog.ts.
import { usePlanToOrderDialog } from '@/composables/subsidies/usePlanToOrderDialog'
import PlanToOrderDialog from '@/components/subsidies/PlanToOrderDialog.vue'
// «Приравнять ФЭО к плану по всем статьям» (владелец 07.10.2026) — см.
// докстринг кнопки/компонента выше.
import AlignBudgetAllDialog from '@/components/subsidies/AlignBudgetAllDialog.vue'

const ctx = useSubsidyDetailCtx()
const alignAllDialog = ref<InstanceType<typeof AlignBudgetAllDialog> | null>(null)
const planToRequest = usePlanToRequest()
const feoCollapse = useFeoCategoryCollapse()
const kpiPrefs = useKpiPrefs()
const hideFullyPurchased = useFeoHideFullyPurchased()
const planToOrder = usePlanToOrderDialog()

// Остатки плановых позиций (planned_item_consumption/category_plan_links) —
// нужны ВСЕГДА, не только в режиме «Создать закупку на основе плана»
// (usePlanToRequest.ts::ensureResidualsLoaded, Правило №6 — второй GET не
// заводим): штриховка «закуплено полностью» в FeoTreeRow.vue/
// FeoLevel5Panel.vue читает тот же feoResiduals.
watch(() => ctx.selectedId.value, (id) => { planToRequest.ensureResidualsLoaded(id) }, { immediate: true })

// N кандидатов на сворачивание — считается лениво при открытии субсидии
// (задача 3), не на каждый рендер тулбара.
watch(() => ctx.selectedId.value, (id) => {
  if (id != null) void feoCollapse.ensureCandidates(id)
}, { immediate: true })

// Очистка выбора при смене субсидии, пока активен режим «Создать закупку на
// основе плана» (владелец, правка 2026-09-20, задача 1а): без этого
// selectedPlannedItemIds оставался глобальным Set с id прошлой субсидии, и
// чекбоксы категорий новой субсидии могли показывать indeterminate по
// случайному совпадению id. immediate НЕ ставим — на монтаже planToRequest.active
// всегда false (режим ещё не запущен), первый вызов watcher срабатывает уже на
// РЕАЛЬНУЮ смену субсидии. clearSelection переиспользует startSelectMode
// целиком (тот же сброс Set + перезагрузка остатков под новую субсидию,
// Правило №6, второй сброс не пишем).
watch(() => ctx.selectedId.value, (id, prevId) => {
  if (id != null && id !== prevId && planToRequest.active.value) {
    planToRequest.clearSelection(id)
  }
})

// Состояние кнопки «Вся смета»/«Снять всё» (задача 1) — тот же источник, что и
// чекбоксы категорий (usePlanToRequest.ts::wholeSmetaSelection, Правило №6).
// Единственный вызов на рендер (не два computed'а, дублирующих фильтр) — оба
// места шаблона (state и подпись счётчика) читают этот же computed.
const wholeSmetaSelectionState = computed(() => planToRequest.wholeSmetaSelection(ctx.feoCategories.value))
const wholeSmetaAllSelected = computed(() => wholeSmetaSelectionState.value.all)

const toast = useToast()
function showSnack(text: string, color: ToastType = 'success') {
  toast.addToast(text, color)
}

// Тот же гейт, что и в SubsidyEditDialog.vue (canSaveVersion) — вычисляется
// независимо здесь же (см. комментарий там же: используется в нескольких
// местах вне диалога, которые остаются вне общего ctx — простая проверка роли
// из localStorage, не формула, дублирование не нарушает Правило №6).
const userRoleRaw = localStorage.getItem('user_role') || ''
const canSaveVersion = computed(() => ['superadmin', 'org_admin', 'admin', 'account_owner'].includes(userRoleRaw))

const { openVersionHistory, openExportVersionsDialog, openSaveVersionDialog } = usePlanGraphVersions(ctx)
const { feoImport } = useFeoImport(ctx)
const { openWizard: openFactImportWizard, loadRuns: loadFactImportRuns, factImport: factImportState } = useFactImport()

function openFactImport() {
  if (ctx.selectedId.value != null) openFactImportWizard(ctx.selectedId.value)
}
function openFactImportRuns() {
  factImportState.subsidyId = ctx.selectedId.value ?? null
  factImportState.runsPanelShow = true
  void loadFactImportRuns()
}

const { exportScreenshotPdf: _exportFeoScreenshotPdf } = useRegistryExport()

function exportPlanGraphExcel() {
  const token = localStorage.getItem('auth_token') || ''
  const url = `/api/subsidies/${ctx.selectedId.value}/plan-graph/export`
  fetch(url, { headers: { Authorization: `Bearer ${token}` } })
    .then(r => r.blob())
    .then(blob => {
      const bUrl = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = bUrl
      a.click()
      URL.revokeObjectURL(bUrl)
    })
}

async function exportPlanGraphDocx() {
  const token = localStorage.getItem('auth_token') || ''
  const url = `/api/subsidies/${ctx.selectedId.value}/plan-graph/export-docx`
  const r = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
  if (!r.ok) {
    const err = await r.json().catch(() => ({}))
    showSnack(err.message || 'Шаблон не загружен', 'error')
    return
  }
  const blob = await r.blob()
  const bUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = bUrl
  a.click()
  URL.revokeObjectURL(bUrl)
}

async function exportFeoPdf() {
  if (!ctx.feoTableArea.value) { showSnack('Таблица ФЭО не готова', 'error'); return }
  try {
    const name = `ФЭО_${ctx.selectedSubsidy.value?.name ?? ''}`.trim()
    await _exportFeoScreenshotPdf(ctx.feoTableArea.value, name, undefined, {
      // Колонка «Действия» нефункциональна в PDF и съедает место — скрыть.
      hideSelectors: ['.feo-th-actions', '.feo-td-actions'],
      // С table-layout:fixed «Наименование» ужимается в столбик; auto + перенос по словам.
      extraCss: '.feo-table{table-layout:auto!important;width:100%!important}'
        + '.feo-th-name,.feo-td-name{min-width:280px!important;white-space:normal!important}'
        + '.feo-name{word-break:normal!important;overflow-wrap:anywhere!important}',
    })
  } catch (e: any) {
    showSnack(e?.message ?? 'Ошибка экспорта PDF', 'error')
  }
}

async function uploadTemplate(file: File) {
  const fd = new FormData()
  fd.append('file', file)
  const token = localStorage.getItem('auth_token') || ''
  const r = await fetch(`/api/subsidies/${ctx.selectedId.value}/plan-graph/template`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: fd,
  })
  const data = await r.json()
  if (r.ok) {
    showSnack('Шаблон загружен')
  } else {
    showSnack(data.message || 'Ошибка загрузки', 'error')
  }
}
</script>

<style scoped>
.plan-to-request-hint {
  display: flex;
  align-items: center;
  margin: 2px 0 6px;
  padding: 4px 8px;
  font-size: 12px;
  color: #5b21b6;
  background: rgba(124, 58, 237, 0.08);
  border: 1px solid rgba(124, 58, 237, 0.25);
  border-radius: 6px;
}
</style>
