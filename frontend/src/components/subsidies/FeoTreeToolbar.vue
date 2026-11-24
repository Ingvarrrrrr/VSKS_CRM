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

  <!-- Липкая панель (владелец, 19.10.2026): шапка ФЭО (заголовок/переключатели/
       поиск/кнопки + легенда стадий + строка «убрать номера строк» + подсказка
       режима выбора) остаётся вверху экрана, пока на экране дерево — иначе
       колесо докручивает .feo-table-wrap до конца, прокрутка переходит на
       страницу, и панель уезжает вместе с деревом. Контрагент (.detail-contractor
       выше) сознательно ВНЕ обёртки — требование владельца. Высота панели
       переменная (1-3 строки) → меряется ResizeObserver'ом (см. скрипт) и
       пишется в CSS-переменную --feo-toolbar-h на <html>, которую читает
       .feo-table-wrap (FeoTreeTable.vue/subsidies.css), чтобы высота таблицы
       всегда была «экран минус шапка приложения минус эта панель минус нижняя
       строка». Только десктоп (≥960px, см. стиль ниже) — на мобильном
       оставляем прежнее поведение. -->
  <div ref="stickyToolbarRef" class="feo-sticky-toolbar">
  <div class="detail-feo-header">
    <span class="chart-card-title">Направления ФЭО</span>
    <div class="d-flex align-center ml-4" style="gap:6px" title="Группировка позиций «из заявок» при раскрытии направления">
      <span class="text-caption text-medium-emphasis">Позиции:</span>
      <v-btn-toggle v-model="ctx.feoItemsGroupBy.value" density="compact" mandatory variant="outlined" color="teal" style="height:26px" :disabled="ctx.plannedBase.value === 'purchases'">
        <v-btn size="x-small" value="none">Нет</v-btn>
        <v-btn size="x-small" value="category">По категориям</v-btn>
        <v-btn size="x-small" value="category_type">Категории + виды</v-btn>
        <!-- «По категориям — вся субсидия» (владелец, 28.10.2026): весь
             бензоинструмент (и любая другая категория товара) со ВСЕХ статей
             ФЭО одним списком — заменяет дерево на SubsidyCategoryPanel.vue
             (см. её докстринг и SubsidiesView.vue). -->
        <v-btn size="x-small" value="category_subsidy" title="Вся субсидия одним списком по категориям товара, независимо от статьи ФЭО">Вся субсидия</v-btn>
      </v-btn-toggle>
    </div>
    <!-- Фильтр «Все / Товары / Услуги» (владелец, 28.10.2026) — работает и в
         этом режиме, и в обычном дереве (FeoLevel5Panel.vue читает тот же
         ctx.feoItemTypeFilter, ПРАВИЛО №6, второй фильтр не заводим). -->
    <div class="d-flex align-center ml-3" style="gap:6px" title="Показывать все позиции или только товары/услуги">
      <span class="text-caption text-medium-emphasis">Тип:</span>
      <v-btn-toggle v-model="ctx.feoItemTypeFilter.value" density="compact" mandatory variant="outlined" color="teal" style="height:26px">
        <v-btn size="x-small" value="all">Все</v-btn>
        <v-btn size="x-small" value="goods">Товары</v-btn>
        <v-btn size="x-small" value="services">Услуги</v-btn>
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
    <!-- Компактный фильтр по цвету заливки -->
    <v-chip
      v-if="cellMarks.activeColorFilter.value?.feo_item || cellMarks.activeColorFilter.value?.feo_category"
      size="x-small"
      color="purple"
      variant="tonal"
      closable
      class="ml-2"
      prepend-icon="mdi-palette"
      @click:close="clearFeoColorFilters"
    >
      🎨 Фильтр цвета: {{ cellMarks.activeColorFilter.value?.feo_item || cellMarks.activeColorFilter.value?.feo_category }}
    </v-chip>
    <!-- Переключатель «Всё / Только закупки / Только ФОТ» (владелец, план
         payroll_view, 23.10.2026) — перенесён в SubsidyKpiCards.vue рядом с
         «Целиком», чтобы не было двух мест с одним переключателем (правка
         23.10.2026, 2-й заход). -->
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
        @focus="ctx.onFeoSearchFocus()"
        @keydown.esc="ctx.clearFeoSearch()"
        @click:clear="ctx.clearFeoSearch()"
      />
      <!-- feoSearchOpen — отдельный флаг открытости (владелец, 2026-10-13): после
           выбора варианта запрос остаётся в поле, но список закрывается; снова
           открывается при вводе/фокусе (useFeoTreeSearch.ts). -->
      <div v-if="ctx.feoSearchOpen.value" class="feo-search-dropdown">
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
            @mousedown.prevent
            @click="ctx.goToFeoSearchResult(r)"
          >
            <v-icon
              :icon="r.kind === 'planned_item' ? 'mdi-cube-outline' : 'mdi-folder-outline'"
              size="16" color="teal" class="mr-2"
            />
            <!-- Название и путь — ЦЕЛИКОМ, с переносом строк, без многоточий
                 (владелец, п.1): прежние white-space:nowrap + text-overflow:ellipsis
                 в styles/subsidies.css обрезали оба текста. -->
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
      <!-- «Ещё» (владелец, 20.10.2026, правка того же дня): редкие действия
           дерева ФЭО собраны в одно плоское меню с подзаголовками групп —
           «Выгрузить ФЭО»/«Импорт ФЭО»/«Импорт факта»/«Экспорт» перестали быть
           отдельными кнопками/вложенными меню на панели, их пункты перенесены
           сюда без изменения видимости/действия (см. комментарии у пунктов
           ниже и в docstring'ах composables выше), логика не продублирована. -->
      <FeoToolbarMoreMenu
        :can-save-version="canSaveVersion"
        @clear-source-rows="clearSourceRowsConfirming = true"
        @snack="showSnack"
      />
      <v-btn v-if="ctx.canEditFeo.value" size="small" variant="tonal" color="primary" prepend-icon="mdi-plus" @click="ctx.openAddFeoDialog(null)">Добавить</v-btn>
    </div>
  </div>

  <!-- Легенда шкалы стадий закупки (владелец, 16.10.2026, заменяет легенду
       «закуплено полностью/частично» — штриховка/«пузырьки» убраны, строка
       теперь закрашена отрезками по стадии, см. @/utils/planStageBackground.ts)
       + переключатель «Скрыть закупленные полностью» (владелец, 30.09.2026,
       п.4-5, смысл не меняется): один флажок на всё дерево ФЭО и панель Ур.5
       (useFeoHideFullyPurchased.ts, module-level singleton, Правило №6 —
       второй Set не заводим), запоминается в localStorage, по умолчанию
       выключен. «Закуплено» (закрашено целиком) определяют те же формулы
       usePlanToRequest.ts::isPlannedItemFullyTaken/isCategoryPlanFullyTaken/
       isCategoryFullyPurchased, что и режим «Создать закупку на основе
       плана» — второй расчёт остатка не заводим. -->
  <div class="feo-fully-purchased-legend">
    <span v-for="st in planStageLegend" :key="st.key" class="d-flex align-center" style="gap:4px">
      <span class="feo-stage-legend-swatch" :style="{ background: st.color }" />
      <span>{{ st.label }}</span>
    </span>
    <v-switch
      v-model="hideFullyPurchased.hideFullyPurchased.value"
      density="compact" hide-details color="success" class="ml-4" style="flex:0 0 auto"
      :label="hideFullyPurchased.hideFullyPurchased.value ? 'скрыты' : 'скрыть закупленные полностью'"
    />
    <!-- Общий переключатель РАСКРЫТИЯ комментариев ФЭО (перенесён из FeoTreeRow.vue
         2026-10-20, владелец — должен быть виден всегда, не только при наличии
         строк дерева). Один на всю субсидию, рисуется один раз в панели над
         деревом, не в первой строке таблицы. -->
    <span class="d-flex align-center" style="gap:6px"
      title="разворачивает/сворачивает сразу все ветки; иконка комментария видна всегда">
      <v-icon icon="mdi-comment-text-multiple-outline" size="14" color="grey-darken-1" class="ml-4" />
      <span class="text-caption text-medium-emphasis">Комментарии:</span>
      <v-switch
        :model-value="feoComments.isVisibleCached(ctx.selectedId.value)"
        density="compact" hide-details color="teal" style="flex:0 0 auto"
        :label="feoComments.isVisibleCached(ctx.selectedId.value) ? 'все развёрнуты' : 'все свёрнуты'"
        @update:model-value="onToggleCommentsVisible"
      />
    </span>
  </div>

  <!-- «Убрать номера строк файла» (владелец, 12.10.2026, план
       lazy-swimming-hollerith.md п.4г) — обнуляет подписи «строка N файла»
       у ВСЕХ плановых позиций субсидии (FeoLevel5Panel.vue). Подтверждение —
       на странице (раскрывающаяся плашка), не browser confirm(). Видна
       только администратору организации и выше — тот же canSaveVersion,
       что и у «Приравнять ФЭО к плану»/«Сохранить редакцию» выше (ПРАВИЛО
       №6, второй гейт роли не заводим). -->
  <div v-if="canSaveVersion && clearSourceRowsConfirming" class="feo-clear-source-rows-bar">
    <span class="text-caption text-medium-emphasis">
      У всех плановых позиций субсидии исчезнут подписи «строка N файла» (закупки,
      привязанные к частям объединённых позиций, не затрагиваются). Продолжить?
    </span>
    <v-btn size="x-small" variant="flat" color="error" class="ml-2" :loading="clearSourceRowsLoading"
      @click="confirmClearSourceRows"
    >Да, убрать</v-btn>
    <v-btn size="x-small" variant="text" class="ml-1" :disabled="clearSourceRowsLoading"
      @click="clearSourceRowsConfirming = false"
    >Отмена</v-btn>
  </div>

  <!-- Подсказка режима выбора (владелец, лист 2 №7) — одной строкой под тулбаром,
       пока активен режим создания заявки из плана. -->
  <div v-if="planToRequest.active.value" class="plan-to-request-hint">
    <v-icon icon="mdi-cursor-default-click-outline" size="14" class="mr-1" />
    Отметьте плановые позиции галочками (построчно, категорией целиком или «Вся смета») — из них соберётся заявка
    <span v-if="planToRequest.residualsLoading.value" class="ml-2 text-medium-emphasis">(загрузка остатков…)</span>
  </div>
  </div>

  <PlanToRequestDialog />
  <PlanToOrderDialog />
  <FeoCollapseCandidatesDialog />
  <FeoCollapseConfirmDialog />
</template>

<script setup lang="ts">
import { computed, ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { apiFetch } from '@/api'
import { useToast, type ToastType } from '@/composables/useToast'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { usePlanToRequest, RESIDUAL_SELECTION_TOOLTIP } from '@/composables/subsidies/usePlanToRequest'
import { useFeoCategoryCollapse } from '@/composables/subsidies/useFeoCategoryCollapse'
import PlanToRequestDialog from '@/components/subsidies/PlanToRequestDialog.vue'
import FeoCollapseCandidatesDialog from '@/components/subsidies/FeoCollapseCandidatesDialog.vue'
import FeoCollapseConfirmDialog from '@/components/subsidies/FeoCollapseConfirmDialog.vue'
import { useKpiPrefs } from '@/composables/useKpiPrefs'
import { useFeoHideFullyPurchased } from '@/composables/subsidies/useFeoHideFullyPurchased'
import { usePlanToOrderDialog } from '@/composables/subsidies/usePlanToOrderDialog'
import PlanToOrderDialog from '@/components/subsidies/PlanToOrderDialog.vue'
import { STAGE_ORDER, PLAN_STAGE_META } from '@/constants/planStageScale'
import { useFeoComments } from '@/composables/subsidies/useFeoComments'
import FeoToolbarMoreMenu from '@/components/subsidies/FeoToolbarMoreMenu.vue'
import { useCellMarks } from '@/composables/useCellMarks'

const ctx = useSubsidyDetailCtx()
const cellMarks = useCellMarks()
const feoComments = useFeoComments()
const planToRequest = usePlanToRequest()
const feoCollapse = useFeoCategoryCollapse()
const kpiPrefs = useKpiPrefs()
const hideFullyPurchased = useFeoHideFullyPurchased()

function clearFeoColorFilters() {
  cellMarks.setColorFilter('feo_item', null)
  cellMarks.setColorFilter('feo_category', null)
}

const planStageLegend = computed(() => STAGE_ORDER.map((key) => PLAN_STAGE_META[key]))
const planToOrder = usePlanToOrderDialog()

// Остатки плановых позиций (planned_item_consumption/category_plan_links) —
// нужны ВСЕГДА, не только в режиме «Создать закупку на основе плана»
// (usePlanToRequest.ts::ensureResidualsLoaded, Правило №6 — второй GET не
// заводим): штриховка «закуплено полностью» в FeoTreeRow.vue/
// FeoLevel5Panel.vue читает тот же feoResiduals.
watch(() => ctx.selectedId.value, (id) => {
  planToRequest.ensureResidualsLoaded(id)
  planToRequest.consumePendingAppend(id)
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

// Переключатель «Комментарии к плану ФЭО: все развёрнуты/свёрнуты» — перенесён
// из FeoTreeRow.vue (onToggleCommentsVisible, 2026-10-20), логика без изменений.
async function onToggleCommentsVisible(val: boolean | null) {
  const subsidyId = ctx.selectedId.value
  if (subsidyId == null) return
  const next = !!val
  try {
    await feoComments.setVisibility(subsidyId, next)
    feoComments.broadcastExpandAll(subsidyId, next)
  } catch (e: any) {
    toast.addToast(e?.payload?.message || e?.detail || e?.message || 'Не удалось изменить видимость комментариев', 'error')
  }
}

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

// «Убрать номера строк файла» (12.10.2026, план lazy-swimming-hollerith.md
// п.4г) — подтверждение на странице (раскрывающаяся плашка), не browser
// confirm(). После успеха — страница ФЭО перечитывается заново (ctx.loadFeo),
// чтобы подписи «строка N файла» у FeoLevel5Panel.vue пропали без ручного
// обновления каждой открытой панели по отдельности.
const clearSourceRowsConfirming = ref(false)
const clearSourceRowsLoading = ref(false)
async function confirmClearSourceRows() {
  const subsidyId = ctx.selectedId.value
  if (subsidyId == null) return
  clearSourceRowsLoading.value = true
  try {
    const res = await apiFetch<{ cleared_items: number; cleared_parts: number }>(
      `/feo-planned-items/clear-source-rows?subsidy_id=${subsidyId}`,
      { method: 'POST' },
    )
    showSnack(`Номера строк файла убраны у ${res.cleared_items} позиций`, 'success')
    clearSourceRowsConfirming.value = false
    await ctx.loadFeo(subsidyId)
  } catch (e: any) {
    showSnack(e?.payload?.detail || e?.message || 'Не удалось убрать номера строк файла', 'error')
  } finally {
    clearSourceRowsLoading.value = false
  }
}

// Липкая панель (владелец, 19.10.2026) — см. докстринг в <template> выше.
// Высота панели (1-3 строки в зависимости от ширины/режима) пишется в
// CSS-переменную на <html>, а не на локальный предок: FeoTreeTable.vue —
// отдельный компонент (scoped CSS соседа её не видит), а subsidies.css —
// глобальный, но переменная на документе читается отовсюду одинаково просто.
const stickyToolbarRef = ref<HTMLElement | null>(null)
let toolbarResizeObserver: ResizeObserver | null = null
function applyToolbarHeightVar(px: number) {
  document.documentElement.style.setProperty('--feo-toolbar-h', `${Math.ceil(px)}px`)
}
onMounted(() => {
  const el = stickyToolbarRef.value
  if (!el || typeof ResizeObserver === 'undefined') return
  applyToolbarHeightVar(el.getBoundingClientRect().height)
  toolbarResizeObserver = new ResizeObserver(() => {
    // Доработка 20.10.2026 (владелец нашёл регресс — заголовки .feo-th
    // прятались под панелью): ResizeObserverEntry.contentRect исключает
    // padding/border (у .feo-sticky-toolbar — padding-bottom:6px +
    // border-bottom:1px = 7px), а следующий элемент (.feo-table-wrap) в
    // обычном потоке начинается ровно от border-box панели. Меряем
    // getBoundingClientRect().height самого элемента (border-box) — то же
    // число, что реально занимает панель в документе.
    applyToolbarHeightVar(el.getBoundingClientRect().height)
  })
  toolbarResizeObserver.observe(el)
})
onBeforeUnmount(() => {
  toolbarResizeObserver?.disconnect()
  toolbarResizeObserver = null
})

</script>

<style scoped>
/* Липкая панель — только десктоп (владелец, 19.10.2026): ниже 960px оставляем
   прежнее поведение (панель прокручивается вместе со страницей, на узком
   экране места и так мало). top — высота шапки приложения (App.vue:
   .v-app-bar height: calc(48px + var(--gala-safe-top))), z-index выше таблицы
   (её sticky thead — z-index:3, .feo-th-actions — 5), но ниже дропдауна
   поиска (.feo-search-dropdown — z-index:1300, см. subsidies.css) и диалогов. */
@media (min-width: 960px) {
  .feo-sticky-toolbar {
    position: sticky;
    top: calc(48px + var(--gala-safe-top, 0px));
    z-index: 6;
    background: var(--crm-surface);
    padding-bottom: 6px;
    margin-bottom: 6px;
    border-bottom: 1px solid var(--crm-border);
    box-shadow: 0 2px 6px var(--crm-shadow);
  }
}
.feo-clear-source-rows-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 2px;
  margin: 2px 0;
}
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
