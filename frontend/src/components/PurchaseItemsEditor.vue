<template>
  <div class="purchase-items-editor">
    <!-- Header row -->
    <div class="d-flex align-center justify-space-between mb-2 flex-wrap ga-2">
      <span class="text-subtitle-1 font-weight-bold">
        {{ props.itemsTitle ?? (itemShape === 'purchase' ? 'Позиции закупки' : 'Позиции') }}
      </span>
      <div class="d-flex align-center ga-2 flex-wrap">
        <!-- View-mode toggle (hidden on mobile, which is forced to cards) -->
        <v-btn-toggle v-if="!mobile" v-model="viewMode" density="compact" mandatory variant="outlined">
          <v-tooltip text="Таблица" location="top">
            <template #activator="{ props: tip }">
              <v-btn v-bind="tip" value="table" size="small" icon="mdi-table" />
            </template>
          </v-tooltip>
          <v-tooltip text="Карточки" location="top">
            <template #activator="{ props: tip }">
              <v-btn v-bind="tip" value="cards" size="small" icon="mdi-view-grid" />
            </template>
          </v-tooltip>
        </v-btn-toggle>
        <!-- Владелец 2026-08-18: «сделать кнопку, чтобы разворачивались все позиции сразу» —
             видна только когда есть строки с раскрытием (stagesEnabled → ItemsTableStages,
             единственное представление с expand-row ТЗ/Договор/Поставка; у Flat/Cards
             раскрытия нет вовсе). -->
        <v-btn v-if="stagesEnabled && localItems.length > 0"
          variant="tonal" size="small"
          :prepend-icon="allExpanded ? 'mdi-unfold-less-horizontal' : 'mdi-unfold-more-horizontal'"
          @click="toggleExpandAll">
          {{ allExpanded ? 'Свернуть всё' : 'Развернуть всё' }}
        </v-btn>
        <v-btn v-if="selectedItemIdxs.length > 0 && !props.readonly"
          variant="tonal" prepend-icon="mdi-delete-sweep-outline" size="small" color="error"
          @click="removeSelectedItems">
          Удалить ({{ selectedItemIdxs.length }})
        </v-btn>
        <!-- ISSUE-3 PART B: bulk-assign FEO level to selected items -->
        <v-btn v-if="props.feoPerItem && selectedItemIdxs.length > 0 && !props.readonly"
          variant="tonal" prepend-icon="mdi-format-list-bulleted-type" size="small" color="primary"
          @click="openBulkFeoDialog">
          Назначить ФЭО для выбранных ({{ selectedItemIdxs.length }})
        </v-btn>
        <!-- Владелец 2026-08-06: «если делаются разные категории ФЭО... должна быть общая
             кнопка "Создать в плане закупок" — при нажатии на неё все позиции, которые не
             привязались к плановым, надо создать будут в соответствующих категориях, как
             плановые, которые для них выбраны». Видна в режиме «Разные плановые позиции
             для каждого товара» (feoPlannedPerItem) — ИЛИ allowPerItemPlan (Дефект 2,
             владелец 2026-08-20): заявка передаёт feoPlannedPerItem=false всегда (проп
             ещё управляет автозаполнением), но построчный выбор плановой позиции и эта
             кнопка должны быть доступны и там — см. allow-per-item-plan у ItemsTableFlat/
             ItemsCardsView/ItemsTableStages, тот же паттерн. Видна, когда есть хоть одна
             непривязанная к плановой позиция (с категорией или без — без категории кнопка
             ниже просто заблокирована с объяснением, а не спрятана молча).
             Владелец (2026-09-04, заявка №55): «согласующий может создавать плановые
             позиции, куда делась общая кнопка "создать плановые для всех позиций сразу"?» —
             у заявки readonly=true (состав закупки не его дело), но feoAttrsEditable=true
             (право wish.edit_feo + он в цепочке согласования) даёт ему ФЭО-распределение,
             а кнопка проверяла только !props.readonly и гасла. Условие теперь пускает по
             readonly ИЛИ feoAttrsEditable — тот же режим, что уже разрешён построчным
             FeoTreeSelect/FeoPlannedItemsSelect (см. комментарий у feoAttrsEditable в
             defineProps ниже). -->
        <v-tooltip :disabled="itemsMissingCategoryForPlan.length === 0" location="top" max-width="360">
          <template #activator="{ props: tip }">
            <span v-bind="tip">
              <v-btn v-if="(!props.readonly || props.feoAttrsEditable) && (props.feoPlannedPerItem || props.allowPerItemPlan) && (needPlanCount > 0 || itemsMissingCategoryForPlan.length > 0)"
                variant="tonal" prepend-icon="mdi-clipboard-plus-outline" size="small" color="primary"
                :class="{ 'plan-bulk-btn-blocked': itemsMissingCategoryForPlan.length > 0 }"
                @click="itemsMissingCategoryForPlan.length > 0 ? highlightMissingCategoryForPlan() : openCreatePlannedBulkDialog()">
                Создать в плане закупок ({{ needPlanCount }})
              </v-btn>
            </span>
          </template>
          У {{ itemsMissingCategoryForPlan.length }} {{ itemsMissingCategoryForPlan.length === 1 ? 'позиции' : 'позиций' }}
          не выбрана конечная категория ФЭО — заполните её, иначе для этих строк нельзя создать плановую позицию:
          {{ itemsMissingCategoryForPlan.slice(0, 5).map(r => `№${r.idx + 1} «${r.name}»`).join(', ') }}{{ itemsMissingCategoryForPlan.length > 5 ? `, …и ещё ${itemsMissingCategoryForPlan.length - 5}` : '' }}
        </v-tooltip>
        <v-btn
          v-if="selectedItemIdxs.length > 0 && hasUncatalogedSelected && !props.readonly"
          size="small" variant="tonal" color="teal"
          prepend-icon="mdi-database-plus"
          :loading="bulkAddCatalogLoading"
          @click="bulkAddToCatalog">
          Добавить в каталог ({{ uncatalogedSelectedCount }})
        </v-btn>
        <slot name="toolbar-actions" />
        <v-btn v-if="!props.readonly"
          variant="tonal" prepend-icon="mdi-plus" size="small"
          @click="addItem(true)">
          Добавить позицию
        </v-btn>
        <v-btn v-if="(props.supportsExcelImport || props.supportsSmartImport) && !props.readonly"
          variant="outlined" prepend-icon="mdi-file-upload-outline" size="small" color="success"
          @click="openSmartImportDialog">
          Импорт из файла
        </v-btn>
      </div>
    </div>

    <!-- Phase 27.1 D-01: Contract items toolbar (only when stagesEnabled) -->
    <div v-if="stagesEnabled && !props.readonly" class="d-flex ga-2 mb-2 flex-wrap">
      <v-btn
        variant="tonal" prepend-icon="mdi-content-copy" size="small" color="success"
        :loading="contractItemCopying"
        :disabled="localContractItems.length > 0 && localItems.length === 0"
        @click="handleCopyFromPurchase"
      >
        Скопировать из заявки
      </v-btn>
      <v-btn
        variant="tonal" prepend-icon="mdi-file-import" size="small" color="primary"
        @click="openContractImportDialog"
      >
        Импорт из файла/QR
      </v-btn>
    </div>

    <!-- Phase 27.1.2: НДС режим toggle (всегда виден над таблицей, не зависит от секции «Параметры договора») -->
    <!-- Мобильный фикс (владелец, 2026-09-04, «прокручиваемых вбок таблиц быть не должно»):
         border-variant v-btn-toggle держит intrinsic ширину кнопок и на узком экране обрезался
         за краем диалога («ОДИНАКОВЫЙ НА ВСЮ ЗАКУПКУ | ДЛЯ КАЖДОЙ ПОЗИЦ…» — правый край текста
         был не виден). .mobile-toggle-wrap (см. <style scoped> внизу файла) тянет тумблер на
         всю ширину и делит кнопки поровну с переносом текста внутри кнопки — вместо обрезки
         вбок текст уходит на вторую строку. Тот же фикс — у группировки ниже. Десктоп не тронут,
         класс навешивается только когда mobile. -->
    <div v-if="itemShape === 'purchase' && !props.readonly" class="d-flex ga-2 mb-2 align-center flex-wrap">
      <span class="text-caption text-medium-emphasis">НДС:</span>
      <v-btn-toggle
        :model-value="props.vatMode || 'uniform'"
        density="compact" rounded="lg" color="primary" border mandatory
        :class="{ 'mobile-toggle-wrap': mobile }"
        @update:model-value="(v: string) => emit('update:vatMode', v)"
      >
        <v-btn value="uniform" size="x-small">Одинаковый на всю закупку</v-btn>
        <v-btn value="per_item" size="x-small">Для каждой позиции</v-btn>
      </v-btn-toggle>
    </div>

    <!-- Группировка и фильтр позиций по категориям/видам товаров из каталога -->
    <div v-if="itemShape === 'purchase' && !stagesEnabled && localItems.length > 1"
      class="d-flex ga-2 mb-2 align-center flex-wrap">
      <span class="text-caption text-medium-emphasis">Группировка:</span>
      <v-btn-toggle v-model="itemsGroupBy" density="compact" rounded="lg" color="primary" border mandatory
        :class="{ 'mobile-toggle-wrap': mobile }">
        <v-btn value="none" size="x-small">Нет</v-btn>
        <v-btn value="category" size="x-small">По категориям</v-btn>
        <v-btn value="category_type" size="x-small">Категории + виды</v-btn>
      </v-btn-toggle>
      <v-select v-model="itemsFilterCats" :items="itemCategoryOptions" label="Фильтр: категория"
        multiple clearable chips closable-chips density="compact" variant="outlined" hide-details
        style="max-width:240px;min-width:170px" />
      <v-select v-model="itemsFilterTypes" :items="itemTypeOptions" label="Фильтр: вид"
        multiple clearable chips closable-chips density="compact" variant="outlined" hide-details
        style="max-width:240px;min-width:170px" />
      <template v-if="itemsFilterActive">
        <span class="text-caption text-medium-emphasis">Показано {{ visibleItemsCount }} из {{ localItems.length }}</span>
        <v-btn size="x-small" variant="text" color="primary"
          @click="itemsFilterCats = []; itemsFilterTypes = []">Сбросить</v-btn>
      </template>
    </div>

    <!-- Владелец 2026-08-18: «У меня в закупке имеются позиции, не привязанные к плановым.
         Это косяк, об этом надо сообщать!» — плашка над таблицей, исчезает сама, когда
         непривязанных нет (пока позиции ещё грузятся, localItems пуст — плашка не появляется). -->
    <!-- Владелец (2026-08-31): «одна позиция в ФЭО не привязана к плановой» и «одна позиция
         внутри закупки не привязана к плановой» — РАЗНЫЕ вещи, и раньше обе назывались
         одинаково. Здесь речь именно про позиции ЭТОГО документа: человек ещё в процессе
         привязки. Про непривязанные строки самого плана говорит отдельный блок «Не привязаны
         к плану — требуется действие» на экране субсидии (SubsidiesView.vue). -->
    <v-alert v-if="itemsMissingPlan.length > 0" type="warning" variant="tonal" density="compact" class="mb-2">
      {{ itemsMissingPlanWord === 'позиция' ? 'Позиция' : 'Позиции' }} этой закупки пока не
      {{ itemsMissingPlanWord === 'позиция' ? 'привязана' : 'привязаны' }} к плановой позиции:
      {{ itemsMissingPlanSummary }}. Пока привязки нет, {{ itemsMissingPlanWord === 'позиция' ? 'она не расходует' : 'они не расходуют' }}
      план и не {{ itemsMissingPlanWord === 'позиция' ? 'видна' : 'видны' }} в плане закупок — выберите плановую позицию в строке или создайте новую.
    </v-alert>

    <!-- Purchase shape table -->
    <template v-if="itemShape === 'purchase'">
      <!-- Phase 27.1.1: expand-row layout (3 sub-rows per position: ТЗ / Договор / Поставка) — Layer 3: extracted -->
      <template v-if="stagesEnabled">
        <ItemsTableStages
          :items="localItems"
          :readonly="props.readonly"
          :feo-attrs-editable="props.feoAttrsEditable"
          :tz-frozen="tzFrozen"
          :allowed-item-types="props.allowedItemTypes"
          :contractors="contractors"
          :contractor-lookup-loading="contractorLookupLoading"
          :selected-item-idxs="selectedItemIdxs"
          :all-items-selected="allItemsSelected"
          :total-nmck="internalTotalNmck"
          :unit-options="UNIT_OPTIONS"
          :vat-rate-options="VAT_RATE_OPTIONS"
          :feo-leaves="feoLeaves"
          :feo-nodes="feoNodes"
          :node-amounts="nodeAmounts"
          :feo-per-item="props.feoPerItem"
          :feo-planned-per-item="props.feoPlannedPerItem"
          :allow-per-item-plan="props.allowPerItemPlan"
          :default-feo-category-id="props.defaultFeoCategoryId"
          :planned-items="props.plannedItems"
          :planned-selection-for="plannedSelectionFor"
          :pending-by-planned-item="pendingByPlannedItem"
          :pending-items-by-planned-item="pendingItemsByPlannedItem"
          :purchase-id="props.purchaseId"
          :wish-id="props.wishId"
          :plan-for-item="planForItem"
          :plan-excess-for="planExcessFor"
          :category-residual-for="categoryResidualFor"
          :subsidy-id="props.subsidyId"
          :subsidy-name="props.subsidyName"
          :show-vat-columns-in-expand-row="showVatColumnsInExpandRow"
          :show-contractor-column="showContractorColumn"
          :is-advance="isAdvance"
          :expanded="expanded"
          :contract-items-total="contractItemsTotal"
          :purchase-planned-total="purchasePlannedTotal"
          :contract-savings="contractSavings"
          :contract-savings-percent="contractSavingsPercent"
          :summary-name="summaryName"
          :stage-totals="stageTotals"
          :is-delivered="isDelivered"
          :is-delivery-filled="isDeliveryFilled"
          :effective-vat-rate="effectiveVatRate"
          :vat-amount="vatAmount"
          :vat-amount-for-stage="vatAmountForStage"
          :total-with-vat="totalWithVat"
          :total-with-vat-for-stage="totalWithVatForStage"
          :get-contract-item-for="getContractItemFor"
          :contractor-name-by-id="contractorNameById"
          :contract-stage-contractor-name="contractStageContractorName"
          :delivery-stage-contractor-name="deliveryStageContractorName"
          :is-over-budget="isOverBudget"
          :over-budget-delta="overBudgetDelta"
          :is-feo-missing="isFeoMissing"
          :fmt-rub="fmtRub"
          :format-number="formatNumber"
          :parse-number="parseNumber"
          :contractor-filter="contractorFilter"
          @toggle-select-all="toggleSelectAll"
          @toggle-item-select="toggleItemSelect"
          @toggle-expand="toggleExpand"
          @confirm-match="confirmMatch"
          @open-repick-dialog="openRepickDialog"
          @remove-item="removeItem"
          @split-item="openSplitDialog"
          @open-product-picker="openProductPicker"
          @clear-item="clearItem"
          @open-quick-product-edit="openQuickProductEdit"
          @calc-item-total="calcItemTotal"
          @vat-rate-change="onVatRateChange"
          @items-changed="emit('items-changed')"
          @contractor-search-input="onContractorSearchInput"
          @item-contractor-select="onItemContractorSelect"
          @open-contractor-quick-create="openContractorQuickCreate"
          @item-feo-change="onItemFeoChange"
          @item-planned-change="onItemPlannedChange"
          @item-pick-unallocated="pickUnallocatedForItem"
          @item-type-change="onItemTypeChange"
          @update-contract-field="updateContractField"
          @contract-vat-change="onContractVatRateChange"
          @update-accepted-field="updateAcceptedField"
          @planned-item-created="emit('planned-item-created')"
          @planned-item-deleted="emit('planned-item-deleted')"
        />
      </template>


      <!-- Legacy flat table (when stagesEnabled is false) — Layer 3: extracted.
           View-mode: cards (mobile-forced or desktop toggle) vs compact table. -->
      <template v-else>
        <ItemsCardsView
          v-if="effectiveView === 'cards'"
          :items="localItems"
          :display-rows="itemsDisplayRows"
          :readonly="props.readonly"
          :feo-attrs-editable="props.feoAttrsEditable"
          :supports-split="true"
          :allowed-item-types="props.allowedItemTypes"
          :vat-mode="props.vatMode || 'uniform'"
          :feo-per-item="props.feoPerItem"
          :feo-planned-per-item="props.feoPlannedPerItem"
          :allow-per-item-plan="props.allowPerItemPlan"
          :default-feo-category-id="props.defaultFeoCategoryId"
          :planned-items="props.plannedItems"
          :planned-selection-for="plannedSelectionFor"
          :pending-by-planned-item="pendingByPlannedItem"
          :pending-items-by-planned-item="pendingItemsByPlannedItem"
          :purchase-id="props.purchaseId"
          :wish-id="props.wishId"
          :plan-for-item="planForItem"
          :plan-excess-for="planExcessFor"
          :category-residual-for="categoryResidualFor"
          :show-contractor-column="showContractorColumn"
          :show-needed-date="props.showNeededDate"
          :contractors="contractors"
          :contractor-lookup-loading="contractorLookupLoading"
          :selected-item-idxs="selectedItemIdxs"
          :all-items-selected="allItemsSelected"
          :total-nmck="internalTotalNmck"
          :feo-leaves="feoLeaves"
          :feo-nodes="feoNodes"
          :node-amounts="nodeAmounts"
          :subsidy-id="props.subsidyId"
          :subsidy-name="props.subsidyName"
          :unit-options="UNIT_OPTIONS"
          :vat-rate-options="VAT_RATE_OPTIONS"
          :is-over-budget="isOverBudget"
          :over-budget-delta="overBudgetDelta"
          :is-feo-missing="isFeoMissing"
          :fmt-rub="fmtRub"
          :format-number="formatNumber"
          :parse-number="parseNumber"
          :contractor-filter="contractorFilter"
          :product-photo-src="productPhotoSrc"
          @toggle-select-all="toggleSelectAll"
          @toggle-item-select="toggleItemSelect"
          @inline-match-pick="onInlineMatchPick"
          @inline-match-create-new="onInlineMatchCreateNew"
          @inline-match-clear="onInlineMatchClear"
          @open-quick-product-edit="openQuickProductEdit"
          @confirm-match="confirmMatch"
          @calc-item-total="calcItemTotal"
          @vat-rate-change="onVatRateChange"
          @remove-item="removeItem"
          @split-item="openSplitDialog"
          @contractor-search-input="onContractorSearchInput"
          @item-contractor-select="onItemContractorSelect"
          @open-contractor-quick-create="openContractorQuickCreate"
          @item-feo-change="onItemFeoChange"
          @item-planned-change="onItemPlannedChange"
          @item-pick-unallocated="pickUnallocatedForItem"
          @item-type-change="onItemTypeChange"
          @items-changed="emitUpdate"
          @planned-item-created="emit('planned-item-created')"
          @planned-item-deleted="emit('planned-item-deleted')"
        />
        <ItemsTableFlat
          v-else
          :items="localItems"
          :display-rows="itemsDisplayRows"
          :readonly="props.readonly"
          :feo-attrs-editable="props.feoAttrsEditable"
          :tz-frozen="tzFrozen"
          :allowed-item-types="props.allowedItemTypes"
          :vat-mode="props.vatMode || 'uniform'"
          :feo-per-item="props.feoPerItem"
          :feo-planned-per-item="props.feoPlannedPerItem"
          :allow-per-item-plan="props.allowPerItemPlan"
          :default-feo-category-id="props.defaultFeoCategoryId"
          :planned-items="props.plannedItems"
          :planned-selection-for="plannedSelectionFor"
          :pending-by-planned-item="pendingByPlannedItem"
          :pending-items-by-planned-item="pendingItemsByPlannedItem"
          :purchase-id="props.purchaseId"
          :wish-id="props.wishId"
          :plan-for-item="planForItem"
          :plan-excess-for="planExcessFor"
          :category-residual-for="categoryResidualFor"
          :show-contractor-column="showContractorColumn"
          :show-needed-date="props.showNeededDate"
          :contractors="contractors"
          :contractor-lookup-loading="contractorLookupLoading"
          :selected-item-idxs="selectedItemIdxs"
          :all-items-selected="allItemsSelected"
          :total-nmck="internalTotalNmck"
          :feo-leaves="feoLeaves"
          :feo-nodes="feoNodes"
          :node-amounts="nodeAmounts"
          :subsidy-id="props.subsidyId"
          :subsidy-name="props.subsidyName"
          :unit-options="UNIT_OPTIONS"
          :vat-rate-options="VAT_RATE_OPTIONS"
          :resize-style="resizeStyle"
          :on-resize-start="onResizeStart"
          :is-over-budget="isOverBudget"
          :over-budget-delta="overBudgetDelta"
          :is-feo-missing="isFeoMissing"
          :fmt-rub="fmtRub"
          :format-number="formatNumber"
          :parse-number="parseNumber"
          :contractor-filter="contractorFilter"
          :product-photo-src="productPhotoSrc"
          @toggle-select-all="toggleSelectAll"
          @toggle-item-select="toggleItemSelect"
          @inline-match-pick="onInlineMatchPick"
          @inline-match-create-new="onInlineMatchCreateNew"
          @inline-match-clear="onInlineMatchClear"
          @open-quick-product-edit="openQuickProductEdit"
          @confirm-match="confirmMatch"
          @calc-item-total="calcItemTotal"
          @vat-rate-change="onVatRateChange"
          @remove-item="removeItem"
          @split-item="openSplitDialog"
          @contractor-search-input="onContractorSearchInput"
          @item-contractor-select="onItemContractorSelect"
          @open-contractor-quick-create="openContractorQuickCreate"
          @item-feo-change="onItemFeoChange"
          @item-planned-change="onItemPlannedChange"
          @item-pick-unallocated="pickUnallocatedForItem"
          @item-type-change="onItemTypeChange"
          @items-changed="emitUpdate"
          @planned-item-created="emit('planned-item-created')"
          @planned-item-deleted="emit('planned-item-deleted')"
        />
      </template>
    </template>

    <!-- Wish shape — Layer 3: extracted. Card view applies here too (mobile-forced
         or desktop toggle); table otherwise. -->
    <template v-else>
      <ItemsCardsView
        v-if="effectiveView === 'cards'"
        :items="localItems"
        :readonly="props.readonly"
        :allowed-item-types="props.allowedItemTypes"
        :vat-mode="'uniform'"
        :feo-per-item="false"
        :show-contractor-column="false"
        :contractors="contractors"
        :contractor-lookup-loading="contractorLookupLoading"
        :selected-item-idxs="selectedItemIdxs"
        :all-items-selected="allItemsSelected"
        :total-nmck="internalTotalNmck"
        :feo-leaves="feoLeaves"
        :feo-nodes="feoNodes"
        :unit-options="UNIT_OPTIONS"
        :vat-rate-options="VAT_RATE_OPTIONS"
        :is-over-budget="isOverBudget"
        :over-budget-delta="overBudgetDelta"
        :is-feo-missing="isFeoMissing"
        :fmt-rub="fmtRub"
        :format-number="formatNumber"
        :parse-number="parseNumber"
        :contractor-filter="contractorFilter"
        :product-photo-src="productPhotoSrc"
        @toggle-select-all="toggleSelectAll"
        @toggle-item-select="toggleItemSelect"
        @inline-match-pick="onInlineMatchPick"
        @inline-match-create-new="onInlineMatchCreateNew"
        @inline-match-clear="onInlineMatchClear"
        @open-quick-product-edit="openQuickProductEdit"
        @confirm-match="confirmMatch"
        @calc-item-total="calcItemTotal"
        @vat-rate-change="onVatRateChange"
        @remove-item="removeItem"
        @contractor-search-input="onContractorSearchInput"
        @item-contractor-select="onItemContractorSelect"
        @open-contractor-quick-create="openContractorQuickCreate"
        @items-changed="emitUpdate"
      />
      <ItemsTableWish
        v-else
        :items="localItems"
        :readonly="props.readonly"
        :allowed-item-types="props.allowedItemTypes"
        :contractors="contractors"
        :selected-item-idxs="selectedItemIdxs"
        :all-items-selected="allItemsSelected"
        :total-nmck="internalTotalNmck"
        :unit-options="UNIT_OPTIONS"
        :format-number="formatNumber"
        :parse-number="parseNumber"
        :contractor-filter="contractorFilter"
        @toggle-select-all="toggleSelectAll"
        @toggle-item-select="toggleItemSelect"
        @inline-match-pick="onInlineMatchPick"
        @inline-match-create-new="onInlineMatchCreateNew"
        @inline-match-clear="onInlineMatchClear"
        @open-quick-product-edit="openQuickProductEdit"
        @calc-item-total="calcItemTotal"
        @remove-item="removeItem"
        @contractor-search-input="onContractorSearchInput"
        @item-contractor-select="onItemContractorSelect"
        @open-contractor-quick-create="openContractorQuickCreate"
      />
    </template>

    <!-- Bottom action buttons -->
    <div v-if="!props.readonly" class="d-flex gap-2 mt-3 flex-wrap">
      <v-btn variant="tonal" prepend-icon="mdi-plus" size="small" @click="addItem()">
        Добавить позицию
      </v-btn>
      <v-btn v-if="props.supportsFullProductDialog"
        variant="outlined" prepend-icon="mdi-package-variant-plus" size="small" color="primary"
        @click="openFullProduct(-1)">
        Добавить товар в каталог
      </v-btn>
    </div>

    <!-- ===== Product picker dialog (Layer 2: extracted) ===== -->
    <ProductPickerDialog
      v-model="productPickerDialog"
      :search="productPickerSearch"
      :results="productPickerResults"
      :supports-full-product-dialog="props.supportsFullProductDialog"
      :photo-src="productPhotoSrc"
      @update:search="(v: string) => productPickerSearch = v"
      @pick="selectFromPicker"
      @create-new="createProductFromPicker"
    />

    <!-- ===== Full product card dialog (Layer 2: extracted) ===== -->
    <FullProductDialog
      v-if="props.supportsFullProductDialog"
      v-model="fullProductDialog"
      :form="fullProductForm"
      :editing-id="fullProductEditingId"
      :saving="fullProductSaving"
      :supports-photo-upload="props.supportsPhotoUpload"
      :name-search="fullProductNameSearch"
      :name-suggestions="fullProductNameSuggestions"
      :is-duplicate="isFullProductDuplicate"
      :type-options="fullProductTypeOptions"
      :category-options="fullProductCategoryOptions"
      :avg-price="fullAvgPrice"
      :photo-preview="fullProductPhotoPreview"
      :photo-file-list="fullProductPhotoFileList"
      :has-photo-file="!!fullProductPhotoFile"
      @update:name-search="(v) => fullProductNameSearch = v"
      @photo-file-change="onFullPhotoFileChange"
      @save="saveFullProduct"
    />

    <!-- ===== Items import dialog (Excel 2-step + Smart import) — Layer 2: extracted ===== -->
    <ItemsImportWizard
      v-model="itemsImportDialog"
      :state="importWizardState"
      :import-preview-data="importPreviewData"
      :items-import-result="itemsImportResult"
      :items-import-loading="itemsImportLoading"
      :import-error="importError"
      :current-sheet-data="currentSheetData"
      :current-sheet-headers="currentSheetHeaders"
      :mapping-has-name="mappingHasName"
      :unmapped-count="unmappedCount"
      :target-fields="TARGET_FIELDS"
      :smart-import-preview="smartImportPreview"
      :smart-import-columns="smartImportColumns"
      :smart-import-result="smartImportResult"
      :smart-import-loading="smartImportLoading"
      :column-mapping-applied="columnMappingApplied"
      :crm-mapping-fields="CRM_MAPPING_FIELDS"
      :crm-field-select-items="crmFieldSelectItems"
      :is-mapped="isMapped"
      :is-ignored="isIgnored"
      :is-target-filled="isTargetFilled"
      :get-column-label="getColumnLabel"
      :get-samples="getSamples"
      @switch-mode="switchImportMode"
      @close="closeImportDialog"
      @import-preview="doImportPreview"
      @mapped-import="doMappedImport"
      @import-all-tables="doImportAllTables"
      @smart-preview="doSmartPreview"
      @smart-import="doSmartImport"
      @apply-column-mapping="applyColumnMapping"
      @download-debug-report="downloadDebugReport"
      @drop-to-target="onDropToTarget"
      @drop-to-unresolved="onDropToUnresolved"
      @drag-start="onDragStart"
      @unmap-target="unmapTarget"
      @ignore-column="ignoreColumn"
    />

    <!-- ===== Contractor quick-create dialog (Phase 26-X) — Layer 2: extracted ===== -->
    <ContractorQuickCreate
      v-model="contractorPickerDialog"
      :form="contractorPickerForm"
      :saving="contractorPickerSaving"
      @save="saveContractorQuickCreate"
    />

    <!-- ===== Product Match Review Dialog ===== -->
    <ProductMatchReviewDialog
      v-model="matchReviewShow"
      :rows="matchReviewRows"
      @confirm="onMatchConfirm"
      @cancel="onMatchCancel"
    />

    <!-- ===== Duplicate Merge Dialog ===== -->
    <DuplicateMergeDialog
      v-if="dupMergeShow"
      v-model="dupMergeShow"
      :groups="dupMergeGroups"
      @confirm="onDupMergeConfirm"
    />

    <!-- ===== P1-B: Single Product Repick Dialog ===== -->
    <SingleProductPickerDialog
      v-if="repickDialog.show"
      v-model="repickDialog.show"
      :item-name="repickDialog.itemName"
      @pick="onRepickPick"
    />

    <!-- ===== ISSUE-3 PART B: Bulk FEO assignment dialog — extracted ===== -->
    <BulkFeoAssignDialog
      v-model="bulkFeoDialog"
      v-model:category-id="bulkFeoId"
      v-model:planned-selection="bulkPlannedSelection"
      :loading="unallocatedLoading"
      :selected-count="selectedItemIdxs.length"
      :feo-nodes="feoNodes"
      :feo-leaves="feoLeaves"
      :planned-items="effectivePlannedItems"
      :node-amounts="nodeAmounts"
      :allow-unallocated="!!props.subsidyId"
      :subsidy-name="props.subsidyName"
      :feo-planned-per-item="props.feoPlannedPerItem"
      :purchase-id="props.purchaseId"
      :planned-prefill="bulkPlannedPrefill"
      @pick-unallocated="(parentId: number | null) => applyBulkUnallocated(parentId)"
      @apply="applyBulkFeo"
      @cancel="closeBulkFeoDialog"
      @planned-item-created="emit('planned-item-created')"
      @planned-item-deleted="emit('planned-item-deleted')"
    />

    <!-- ===== Общая кнопка «Создать в плане закупок» (владелец 2026-08-06) — создаёт плановые
         позиции (Ур.5 FeoPlannedItem) сразу для ВСЕХ позиций, у которых заполнена категория ФЭО,
         но нет привязки к плановой позиции, каждую в своей категории. Extracted. ===== -->
    <CreatePlannedBulkDialog
      v-model="createPlannedBulkDialog"
      :loading="createPlannedBulkLoading"
      :rows="needPlanRows"
      :no-category-count="noCategoryCount"
      :progress="createPlannedBulkProgress"
      :failures="createPlannedBulkFailures"
      @confirm="runCreatePlannedBulk"
      @cancel="closeCreatePlannedBulkDialog"
    />

    <!-- ===== Разбивка позиции по категориям ФЭО (владелец 2026-08-18): закупка
         в статусе «Заказано» с заморозкой ТЗ (добавлять НОВЫЕ позиции нельзя), но
         владельцу нужно разложить уже существующую позицию (напр. 66 огнетушителей)
         по нескольким категориям ФЭО/плановым позициям — количество и сумма НЕ
         меняются, меняется только распределение. См. POST
         /purchases/{pid}/items/{item_id}/split в backend/app/routers/purchases.py.
         Extracted. ===== -->
    <SplitItemDialog
      v-model="splitDialog.show"
      :saving="splitDialog.saving"
      :mobile="mobile"
      :dialog-width="splitDialogWidth"
      :item="splitItem"
      :parts="splitParts"
      :feo-nodes="feoNodes"
      :feo-leaves="feoLeaves"
      :planned-items="effectivePlannedItems"
      :node-amounts="nodeAmounts"
      :allow-unallocated="!!props.subsidyId"
      :subsidy-name="props.subsidyName"
      :show-planned-select="props.feoPlannedPerItem || props.allowPerItemPlan"
      :purchase-id="props.purchaseId"
      :part-amount="splitPartAmount"
      :planned-selection-for="splitPartPlannedSelection"
      :distributed="splitDistributed"
      :remaining="splitRemaining"
      :balanced="splitBalanced"
      :can-save="splitCanSave"
      @remove-part="removeSplitPart"
      @add-part="addSplitPart"
      @feo-change="onSplitPartFeoChange"
      @planned-change="onSplitPartPlannedChange"
      @planned-item-created="emit('planned-item-created')"
      @planned-item-deleted="emit('planned-item-deleted')"
      @save="saveSplit"
      @cancel="closeSplitDialog"
    />

  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, reactive, onMounted } from 'vue'
import { useDisplay } from 'vuetify'
import { apiFetch } from '@/api'
import FileDropZone from '@/components/FileDropZone.vue'
import ProductMatchReviewDialog from '@/components/ProductMatchReviewDialog.vue'
import DuplicateMergeDialog from '@/components/DuplicateMergeDialog.vue'
import SingleProductPickerDialog from '@/components/SingleProductPickerDialog.vue'
import ProductPickerDialog from '@/components/items/ProductPickerDialog.vue'
import FullProductDialog from '@/components/items/FullProductDialog.vue'
import ItemsImportWizard from '@/components/items/ItemsImportWizard.vue'
import ContractorQuickCreate from '@/components/items/ContractorQuickCreate.vue'
import ItemsTableFlat from '@/components/items/ItemsTableFlat.vue'
import ItemsCardsView from '@/components/items/ItemsCardsView.vue'
import ItemsTableWish from '@/components/items/ItemsTableWish.vue'
import ItemsTableStages from '@/components/items/ItemsTableStages.vue'
import BulkFeoAssignDialog from '@/components/items/BulkFeoAssignDialog.vue'
import CreatePlannedBulkDialog from '@/components/items/CreatePlannedBulkDialog.vue'
import SplitItemDialog from '@/components/items/SplitItemDialog.vue'
import type { ContractItem } from '@/types/contractItem'
import { copyFromPurchase as apiCopyFromPurchase } from '@/api/contractItems'
import { useResizableColumns } from '@/composables/useResizableColumns'
import { formatNumber, parseNumber, fmtRub } from '@/utils/numberFormat'
import { useFeoLeaves } from '@/composables/useFeoLeaves'
import { useFeoNodeAmounts } from '@/composables/useFeoNodeAmounts'
import type { FeoPlanPosition, FeoPlanSelection } from '@/composables/useFeoPlannedResiduals'
import { useItemMatching } from '@/composables/useItemMatching'
import { useItemsImport } from '@/composables/items/useItemsImport'
import { useItemsTable } from '@/composables/items/useItemsTable'
import { useItemsTotals } from '@/composables/items/useItemsTotals'
import { useItemsCatalog, productPhotoSrc } from '@/composables/items/useItemsCatalog'
import { useItemsContractors } from '@/composables/items/useItemsContractors'
import { useItemsSplit } from '@/composables/items/useItemsSplit'
import { useItemsFeo } from '@/composables/items/useItemsFeo'
import { useItemsBulkFeo } from '@/composables/items/useItemsBulkFeo'
import { useToast, type ToastType } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'
import { ACTIONS } from '@/constants/permissionActions'
import type { PriceFreshness } from '@/composables/usePriceFreshness'
import {
  VAT_RATE_OPTIONS,
  vatAmount,
  totalWithVat,
} from '@/composables/useVatCalc'

// ── Interfaces ───────────────────────────────────────────────────────────────

interface Contractor {
  id: number
  name: string
  inn?: string | null
  kpp?: string | null
  address?: string | null
}

interface EditorItem {
  _uid?: string | number    // BUG #3: stable row identity for :key (insertion order)
  product_id: number | null
  item_name: string
  item_type: string
  quantity: number | null
  unit: string
  unit_price: number | null
  total_price: number | null
  country_origin: string
  vat_rate?: string | null       // Fix 3/4/5: НДС ставка per-item
  match_confirmed?: boolean
  contractor_id?: number | null
  contractor_inn?: string | null
  contractor_name?: string | null
  receipt_id?: number | null  // Phase 26-BB
  // Purchase-only (undefined when itemShape === 'wish'):
  final_unit_price?: number | null
  final_total?: number | null
  feo_planned_item_id?: number | null
  feo_category_id?: number | null  // FCAT-F1: per-item привязка к leaf FeoCategory
  feo_node_id?: number | null      // UI-only: позиция каскада ФЭО (любой узел, не только лист)
  // F-PLAN2: true — сумма позиции НЕ расходует план элемента ФЭО (сверх плана);
  // категория (feo_category_id) при этом остаётся заполненной.
  over_plan?: boolean | null
  // Per-item delivery date (ISO 'YYYY-MM-DD' | null)
  needed_date?: string | null
  // Стадия «Приняли» (5-я стадия жизненного цикла позиции): автозаполняется на delivered,
  // правится вручную — см. «Поставка» подстрока в ItemsTableStages.vue.
  accepted_name?: string | null
  accepted_quantity?: number | null
  accepted_unit?: string | null
  // UI-local state (stripped by parent before save):
  _selectedProduct?: Product | null
  _photo_url?: string
  _description?: string
  _description_44fz?: string
  // Владелец, 2026-08-29: штамп даты/источника актуализации цены товара —
  // показывается под ценой за единицу в ItemsTableFlat/ItemsCardsView/
  // ItemsTableStages. UI-only, вырезается перед сохранением наравне с
  // _selectedProduct/_photo_url/_description (см. useItemMatching.applyCandidate).
  _price_meta?: {
    price_updated_at?: string | null
    price_source?: string | null
    price_source_ref?: string | null
    price_freshness?: PriceFreshness | null
  } | null
}

interface Product {
  id: number
  name: string
  description?: string
  product_type?: string
  category?: string
  price?: number | null
  avg_price?: number | null
  photo_url?: string | null
  photo_link?: string | null
  has_photo?: boolean
  contract_price?: number | null
  description_44fz?: string
  price_updated_at?: string | null
  price_source?: string | null
  price_source_ref?: string | null
  price_freshness?: PriceFreshness | null
}

// productPhotoSrc — composables/items/useItemsCatalog.ts

// ── Constants ────────────────────────────────────────────────────────────────

const UNIT_OPTIONS = ['шт.', 'усл.', 'компл.', 'уп.', 'м.', 'кг.', 'л.', 'п.м.', 'кв.м.', 'час.', 'мес.', 'год']
const COUNTRIES = ['РФ', 'Беларусь', 'Казахстан', 'Китай', 'Германия', 'США', 'Япония', 'Турция', 'Индия']

// Fix 3 + Fix 4/5: VAT options/helpers now from @/composables/useVatCalc
// (VAT_RATE_OPTIONS, parseVatRatePercent, vatAmount, totalWithVat,
// normalizeVatRate imported above). Phase 27.1.16 convention preserved:
// unit_price / total_price из чека ФФД ВКЛЮЧАЮТ НДС; vatAmount выделяет НДС
// из суммы С НДС: total * pct / (100 + pct).
// Per-stage VAT helpers + calcItemTotal — composables/items/useItemsTotals.ts

// Export COUNTRIES so template can use it if needed (not currently rendered but kept for completeness)
void COUNTRIES

// ── Props & Emits ────────────────────────────────────────────────────────────

const props = withDefaults(defineProps<{
  modelValue: EditorItem[]
  contractItems?: ContractItem[]        // Phase 27.1 D-04: contract_items for side-by-side
  showContractColumns?: boolean         // @deprecated — use unifiedStagesView (Phase 27.1.1)
  unifiedStagesView?: boolean           // Phase 27.1.1: expand-row 3-stage mode
  purchaseStatus?: string               // Phase 27.1.1: для определения isDelivered (D-01.1.1)
  itemShape: 'purchase' | 'wish'
  purchaseId?: number | null
  // Дефект 2 (владелец, 2026-08-20): «удалить случайно созданную плановую позицию
  // прямо из заявки» — та же роль, что purchaseId выше, для формы заявки, у которой
  // закупки ещё нет. Прокидывается дальше в ItemsTableStages/ItemsCardsView/
  // ItemsTableFlat → FeoPlannedItemsSelect::wishId (см. deletePlannedItem там и
  // backend/app/routers/feo_planned_items.py::delete_planned_item).
  wishId?: number | null
  allowedItemTypes?: string[]
  defaultItemType?: string
  defaultUnit?: string
  defaultCountry?: string
  supportsExcelImport?: boolean
  supportsSmartImport?: boolean
  supportsFullProductDialog?: boolean
  supportsPhotoUpload?: boolean
  readonly?: boolean
  // Владелец (2026-08-19): согласующий заявки из цепочки видит состав (название/
  // кол-во/цену/ед./страну) заблокированным через readonly=true — состав это
  // предмет закупки, менять его не его дело. Но перераспределить позиции по
  // категориям/плановым позициям ФЭО он должен мочь — это его специфика. Когда
  // readonly=true И feoAttrsEditable=true, кликабельны построчные FeoTreeSelect/
  // FeoPlannedItemsSelect (и кнопка «Создать в плане закупок» внутри последнего) —
  // см. feoReadonly в ItemsTableFlat/ItemsTableStages/ItemsCardsView.vue — а также
  // (владелец, заявка №55, 2026-09-04) общая кнопка «Создать в плане закупок» в
  // тулбаре выше (создаёт плановые сразу для всех непривязанных позиций разом —
  // раньше проверяла только !props.readonly и гасла у согласующего). Остальные
  // поля строки и add/remove-позиция по-прежнему не трогает.
  feoAttrsEditable?: boolean
  vatMode?: 'uniform' | 'per_item'          // Phase 26-U-3: НДС режим
  uniformVatRate?: string | null             // Phase 26-U-3: ставка для uniform режима
  formMode?: string                          // Phase 26-X: 'advance_report' → показывать колонку Контрагент
  contractors?: Contractor[]                 // Phase 26-JJ: shared contractors state from parent
  // F-PIF1/F-PIF2: per-item FEO selector props
  feoPerItem?: boolean
  level2Id?: number | null
  subsidyId?: number | null
  // Название субсидии — «ствол» дерева ФЭО (FeoTreeSelect rootLabel), опционально
  subsidyName?: string | null
  purchaseIdFeo?: number | null
  // ISSUE-3: header-selected deepest FEO level — used to default per-item values
  defaultFeoCategoryId?: number | null
  // F-PLAN: привязка позиций заявки к плановым позициям плана закупок (FeoPlannedItem).
  // ⚠️ Не задавать значение по умолчанию в withDefaults ниже — undefined (проп НЕ передан
  // вызывающей стороной, напр. CreateOrderView.vue) обязан отличаться от явного null,
  // иначе шапка-источник-истины перезапишет feo_planned_item_id закупки, у которой
  // своя, никак не связанная с заявками, привязка (см. fillItemsWithDefaultPlannedItem).
  defaultFeoPlannedItemId?: number | null
  // Разные плановые позиции для каждого товара (аналог feoPerItem, но для Ур.5 ФЭО)
  feoPlannedPerItem?: boolean
  // Владелец (сессия 2026-08-17): «Создать в плане закупок» внутри позиции должна быть
  // доступна и в режиме «одна категория ФЭО на всю закупку» (feoPerItem=false), не только
  // в per-item режиме — раньше построчная FeoPlannedItemsSelect не рендерилась вовсе
  // (была жёстко внутри `<tr v-if="feoPerItem">`). Это отдельный от feoPlannedPerItem флаг
  // намеренно: feoPlannedPerItem ещё управляет ГЕЙТОМ автозаполнения feo_planned_item_id
  // из шапки (fillItemsWithDefaultPlannedItem ниже) — смешивать нельзя, иначе шапочный
  // выбор перестанет каскадом проставляться на пустые позиции.
  allowPerItemPlan?: boolean
  // Плановые позиции плана закупок субсидии (единый источник /feo-categories/plan-positions) —
  // для per-item выбора в таблице (FeoPlannedItemsSelect dense-режим в каждой строке).
  plannedItems?: FeoPlanPosition[]
  // SN-UX: кастомный заголовок секции позиций
  itemsTitle?: string
  // Per-item delivery date column (only shown when explicitly enabled)
  showNeededDate?: boolean
  // Владелец (2026-09-03, «подсказка о превышении должна быть понятной»): размер
  // превышения плана категории над финансированием по ФЭО и id категории-виновника —
  // ОДИН И ТОТ ЖЕ канал, что уже питает плашку «Превышение плана ФЭО» на карточке
  // закупки (GET /api/purchases/{id}.feo_excess_amount/feo_excess_category_id, см.
  // app.routers.purchases._compute_purchase_feo_excess). НЕ гейтится правом
  // feo_budget.view_leaf — используется в categoryResidualFor ниже, чтобы у
  // пользователя без права показать в позиции только факт и размер превышения
  // статьи (без «занято»/финансирования, из которых можно вычислить бюджет).
  // CreateOrderView.vue прокидывает purchaseData.feo_excess_amount/_category_id;
  // WishesView.vue (у заявки закупки ещё нет) их не передаёт — там блок тихо не
  // рендерится для пользователя без права (нет придуманных чисел).
  feoExcessAmount?: number | null
  feoExcessCategoryId?: number | null
}>(), {
  contractItems: () => [],
  showContractColumns: false,
  unifiedStagesView: false,
  purchaseStatus: '',
  allowedItemTypes: () => ['товар', 'услуга', 'работа'],
  defaultItemType: 'товар',
  defaultUnit: 'шт.',
  defaultCountry: 'РФ',
  supportsExcelImport: true,
  supportsSmartImport: true,
  supportsFullProductDialog: true,
  supportsPhotoUpload: true,
  readonly: false,
  feoAttrsEditable: false,
  purchaseId: null,
  wishId: null,
  vatMode: 'uniform',
  uniformVatRate: null,
  formMode: 'default',
  feoPerItem: false,
  level2Id: null,
  subsidyId: null,
  subsidyName: null,
  purchaseIdFeo: null,
  defaultFeoCategoryId: null,
  // defaultFeoPlannedItemId — БЕЗ дефолта намеренно, см. комментарий у типа пропа.
  feoPlannedPerItem: false,
  allowPerItemPlan: false,
  plannedItems: () => [],
  itemsTitle: undefined,
  showNeededDate: false,
  feoExcessAmount: null,
  feoExcessCategoryId: null,
})

// Владелец (2026-09-03): «обычному пользователю не надо знать, сколько денег
// осталось в организации» — то же право, что гейтит денежные поля на
// GET /feo-categories/leaves (feoLeaves ниже) и /flat (feoNodes), см.
// categoryResidualFor. Считаем локально (authStore), а не ждём проп сверху — тот
// же паттерн, что canViewLeafBudget в CreateOrderView.vue.
const authStore = useAuthStore()
const canViewLeafBudget = computed(() => authStore.hasAction(ACTIONS.FEO_BUDGET_VIEW_LEAF!))

// Phase 27.1.1: stagesEnabled — either the new prop or backward-compat alias
const stagesEnabled = computed(() => props.unifiedStagesView || props.showContractColumns)

// ── F-PIF2: per-item FEO residuals (composable) ───────────────────────────────
// FCAT-F1: leaf FeoCategory loading + budget helpers via @/composables/useFeoLeaves.
// FeoLeaf type imported above.
const {
  feoLeaves,
  feoNodes,
  isOverBudget: feoIsOverBudget,
  overBudgetDelta: feoOverBudgetDelta,
} = useFeoLeaves({
  subsidyId: computed(() => props.subsidyId),
  excludePurchaseId: computed(() => props.purchaseIdFeo),
})

// Задача владельца 2026-08-06: остаток по КАЖДОМУ узлу дерева ФЭО (не только листу),
// считается один раз здесь (см. composables/useFeoNodeAmounts) и передаётся готовым
// объектом во все 3 таблицы позиций + bulk-диалог ниже — FeoTreeSelect рендерится в
// каждой строке, пересчитывать роллап внутри него нельзя (перф).
const { nodeAmounts } = useFeoNodeAmounts({
  subsidyId: computed(() => props.subsidyId),
})

// Thin row-wrappers so templates keep calling isOverBudget(item) / overBudgetDelta(item)
function isOverBudget(row: EditorItem): boolean {
  return feoIsOverBudget(row.feo_category_id, row.total_price)
}

function overBudgetDelta(row: EditorItem): number {
  return feoOverBudgetDelta(row.feo_category_id, row.total_price)
}

function isFeoMissing(row: EditorItem): boolean {
  return props.feoPerItem && !row.feo_category_id
}

// ISSUE-3 PART A: when per-item mode is turned ON (or the header's deepest level
// changes while in per-item mode), fill ONLY items whose feo_category_id is empty
// with the header-selected default. Never overwrite user-picked per-item values.
function fillEmptyItemsWithDefaultFeo(): boolean {
  if (!props.feoPerItem) return false
  if (props.defaultFeoCategoryId == null) return false
  let changed = false
  for (const it of localItems.value) {
    if (it.feo_category_id == null) {
      it.feo_category_id = props.defaultFeoCategoryId
      changed = true
    }
  }
  return changed
}

// F-PLAN: шапка — источник feo_planned_item_id по умолчанию, когда режим
// «разные плановые позиции для каждого товара» выключен (та же логика, что у
// fillEmptyItemsWithDefaultFeo выше: заполняем ТОЛЬКО пустые позиции). После
// перестановки блоков диалога заявки (позиции теперь выше «Категории ФЭО»)
// пользователь может успеть построчно выбрать плановую позицию ДО того, как
// заполнит шапку — раньше эта функция затирала такой построчный выбор значением
// из шапки у ВСЕХ позиций; теперь она не трогает уже заполненные строки.
// ⚠️ КРИТИЧЕСКИЙ GUARD: выполняется ТОЛЬКО если проп defaultFeoPlannedItemId
// передан явно вызывающей стороной. Если он undefined (CreateOrderView.vue НЕ
// передаёт этот проп и использует свою, не связанную с заявками привязку) —
// немедленный выход, чтобы не затереть feo_planned_item_id закупки.
function fillItemsWithDefaultPlannedItem(): boolean {
  if (props.defaultFeoPlannedItemId === undefined) return false
  if (props.feoPlannedPerItem) return false
  let changed = false
  for (const it of localItems.value) {
    if (it.feo_planned_item_id == null) {
      it.feo_planned_item_id = props.defaultFeoPlannedItemId
      changed = true
    }
  }
  return changed
}

watch(
  () => [props.feoPerItem, props.defaultFeoCategoryId, props.feoPlannedPerItem, props.defaultFeoPlannedItemId] as const,
  () => {
    // ОСТОРОЖНО: не использовать || между вызовами — короткое замыкание
    // пропустит вторую fill-функцию, если первая уже вернула true.
    const changedFeo = fillEmptyItemsWithDefaultFeo()
    const changedPlanned = fillItemsWithDefaultPlannedItem()
    if (changedFeo || changedPlanned) emitUpdate()
  }
)
// ─────────────────────────────────────────────────────────────────────────────

const emit = defineEmits<{
  'update:modelValue': [items: EditorItem[]]
  'update:contractItems': [items: ContractItem[]]  // Phase 27.1 D-04
  'update:vatMode': [mode: string]                 // Phase 27.1.2: inline toggle
  'item-added': [item: EditorItem]
  'item-removed': [idx: number]
  'product-created': [product: Product]
  'items-changed': []
  'reload-requested': []
  /** Плановая позиция создана диалогом FeoPlannedItemsSelect (внутри бы это ни было —
   *  массовый bulk-диалог или per-item пикер в таблице) — родитель должен перезагрузить
   *  props.plannedItems (см. FeoPlannedItemsSelect.vue, баг «кнопка ничего не делает»). */
  'planned-item-created': []
  /** Плановая позиция удалена корзинкой из строки списка (FeoPlannedItemsSelect,
   *  владелец, сессия 2026-08-19: «где эта корзиночка?») — родитель перезагружает
   *  props.plannedItems тем же обработчиком, что и на 'planned-item-created'. */
  'planned-item-deleted': []
}>()

// ── Local state ──────────────────────────────────────────────────────────────

const display = useDisplay()

// View-mode toggle (table | cards). On mobile the card layout is forced
// regardless of the toggle; on desktop the toggle drives the effective mode.
const viewMode = ref<'table' | 'cards'>('table')
const mobile = computed(() => display.mobile.value)
const effectiveView = computed<'table' | 'cards'>(() => mobile.value ? 'cards' : viewMode.value)

// Row identity, CRUD (add/remove/clear/confirm-match) and selection (composable)
// — see composables/items/useItemsTable.ts.
const {
  nextUid, ensureUid, normalizeItems, localItems, emitUpdate,
  addItem, removeItem, clearItem, confirmMatch,
  selectedItemIdxs, allItemsSelected, toggleSelectAll, toggleItemSelect, removeSelectedItems,
} = useItemsTable({ props, emit })
void ensureUid; void normalizeItems

// ── Phase 27.1 D-04: Contract items side-by-side ─────────────────────────────

const localContractItems = ref<ContractItem[]>([...(props.contractItems || [])])

// Perf: same self-emit guard for the contractItems echo loop (CreateOrderView full mode).
let _selfEmitContract = false
watch(
  () => props.contractItems,
  (v) => {
    if (_selfEmitContract) { _selfEmitContract = false; return }
    localContractItems.value = [...(v || [])]
  },
)

function emitContractItemsUpdate() {
  _selfEmitContract = true
  emit('update:contractItems', [...localContractItems.value])
}

// Import mode: when true, results of import dialog go to localContractItems instead of localItems
const contractItemImportMode = ref(false)

// contractItemsTotal/purchasePlannedTotal/contractSavings* — composables/items/useItemsTotals.ts

// Phase 27.1.10: dynamic resolution orphan source_item_id → actual PurchaseItem.id
// по item_name OR qty+unit_price match. Backend может ещё не успеть relink — UI решает сам.
const resolvedContractLinks = computed(() => {
  // Map: ContractItem.id → resolved PurchaseItem.id (или null)
  const out = new Map<number, number | null>()
  const piById = new Map<number, any>()
  const piByNormName = new Map<string, any>()
  const piByQtyPrice = new Map<string, any>()

  for (const pi of localItems.value) {
    const pid = (pi as any).id
    if (pid != null) piById.set(pid, pi)
    const norm = ((pi as any).item_name || '').trim().toLowerCase()
    if (norm) piByNormName.set(norm, pi)
    const qty = Number((pi as any).quantity || 0)
    const price = Number((pi as any).unit_price || 0)
    if (qty > 0 && price > 0) {
      piByQtyPrice.set(`${qty}|${price}`, pi)
    }
  }

  for (const ci of localContractItems.value) {
    const ciId = (ci as any).id
    if (ciId == null) continue

    const srcId = (ci as any).source_item_id

    // Case 1: existing valid link
    if (srcId != null && piById.has(srcId)) {
      out.set(ciId, srcId)
      continue
    }

    // Case 2: orphan — try resolve by name
    const ciName = ((ci as any).name || '').trim().toLowerCase()
    if (ciName && piByNormName.has(ciName)) {
      const matched = piByNormName.get(ciName)
      out.set(ciId, (matched as any).id ?? null)
      continue
    }

    // Case 3: orphan — try resolve by qty+price
    const ciQty = Number((ci as any).quantity || 0)
    const ciPrice = Number((ci as any).unit_price || 0)
    if (ciQty > 0 && ciPrice > 0 && piByQtyPrice.has(`${ciQty}|${ciPrice}`)) {
      const matched = piByQtyPrice.get(`${ciQty}|${ciPrice}`)
      out.set(ciId, (matched as any).id ?? null)
      continue
    }

    // Case 4: 1-to-1 unconditional fallback
    if (localItems.value.length === 1 && localContractItems.value.length === 1) {
      const onlyPi = localItems.value[0]
      out.set(ciId, (onlyPi as any).id ?? null)
      continue
    }

    // Case 5: substring match — name содержится в item_name или наоборот
    if (ciName) {
      let foundSubstr = false
      for (const pi of localItems.value) {
        const piName = ((pi as any).item_name || '').trim().toLowerCase()
        if (!piName) continue
        if (piName.includes(ciName) || ciName.includes(piName)) {
          const piId = (pi as any).id
          if (piId != null) {
            out.set(ciId, piId)
            foundSubstr = true
            break
          }
        }
      }
      if (foundSubstr) continue
    }

    out.set(ciId, null)
  }

  return out
})

function getContractItemFor(rowIdx: number): ContractItem | undefined {
  const pi = localItems.value[rowIdx]
  const pid = (pi as any)?.id
  if (pid == null) return localContractItems.value[rowIdx]

  // Direct match по source_item_id
  let linked = localContractItems.value.find(ci => (ci as any).source_item_id === pid)
  if (linked) return linked

  // Reverse lookup через resolved links — может быть orphan CI который должен связаться с этим PI
  for (const ci of localContractItems.value) {
    const ciId = (ci as any).id
    if (ciId == null) continue
    if (resolvedContractLinks.value.get(ciId) === pid) {
      return ci
    }
  }

  // Positional fallback
  return localContractItems.value[rowIdx]
}

function updateContractField(rowIdx: number, field: keyof ContractItem, value: unknown) {
  const ci = getContractItemFor(rowIdx)
  if (!ci) {
    // Create a new contract_item linked to this row
    const newCi: ContractItem = {
      id: 0,
      purchase_id: props.purchaseId || 0,
      source_item_id: (localItems.value[rowIdx] as any)?.id ?? null,
      contract_id: null,
      product_id: null,
      name: (localItems.value[rowIdx] as any)?.item_name || '',
      quantity: null,
      unit: null,
      unit_price: null,
      total: null,
      match_confirmed: true,
    }
    ;(newCi as any)[field] = value
    localContractItems.value.push(newCi)
  } else {
    ;(ci as any)[field] = value
    // Auto-recalc total = qty × unit_price
    if (field === 'quantity' || field === 'unit_price') {
      ci.total = Math.round(Number(ci.quantity || 0) * Number(ci.unit_price || 0) * 100) / 100
    }
  }
  emitContractItemsUpdate()
}

// Стадия «Поставка»/«Приняли» — то же по паттерну, что и updateContractField выше,
// но поля живут прямо на purchase_item (accepted_name/accepted_quantity/accepted_unit),
// не в отдельной сущности, поэтому просто мутируем localItems[idx] и синхронизируем наверх.
function updateAcceptedField(
  idx: number,
  field: 'accepted_name' | 'accepted_quantity' | 'accepted_unit',
  value: unknown,
) {
  const item = localItems.value[idx]
  if (!item) return
  ;(item as any)[field] = value
  emitUpdate()
}

// Layer 3: extracted from the inline Договор-VAT @update:model-value handler so
// the stages table template can call a named parent handler (logic unchanged).
function onContractVatRateChange(idx: number, v: any) {
  const ci = getContractItemFor(idx)
  if (!ci) return
  let rate: string | null
  if (v == null || v === '' || v === 'Без НДС') { rate = null }
  else { const s = String(v); rate = /^\d+(?:\.\d+)?$/.test(s.trim()) ? s.trim() + '%' : s }
  ;(ci as any).vat_rate = rate
  emitContractItemsUpdate()
}

const contractItemCopying = ref(false)

async function handleCopyFromPurchase() {
  if (!props.purchaseId) {
    showSnack('Сохраните закупку перед копированием позиций', 'warning')
    return
  }
  contractItemCopying.value = true
  try {
    const result = await apiCopyFromPurchase(props.purchaseId)
    localContractItems.value = result
    emit('update:contractItems', result)
    showSnack(`Скопировано ${result.length} позиций из заявки`)
  } catch (e: any) {
    const msg = e?.response?.data?.detail?.message || e?.detail || e?.message || 'Ошибка копирования'
    showSnack(msg, 'error')
  } finally {
    contractItemCopying.value = false
  }
}

function openContractImportDialog() {
  // D-02: reuse existing import dialog, routing output to localContractItems
  contractItemImportMode.value = true
  openSmartImportDialog()
}

function splitContractRow(rowIdx: number) {
  // D-05: split one contract row into 2 with same source_item_id
  const ci = getContractItemFor(rowIdx)
  if (!ci) return
  const half = Math.round(Number(ci.quantity || 0) / 2 * 1000) / 1000
  const halfTotal = Math.round(half * Number(ci.unit_price || 0) * 100) / 100
  const newCi: ContractItem = {
    ...ci,
    id: 0,
    quantity: half,
    total: halfTotal,
  }
  ci.quantity = half
  ci.total = halfTotal
  localContractItems.value.push(newCi)
  emitContractItemsUpdate()
}

// ── Phase 27.1.1: expand-row state + helpers ──────────────────────────────────

const expanded = ref<Record<number, boolean>>({})

function toggleExpand(idx: number) {
  expanded.value[idx] = !expanded.value[idx]
}

// Владелец 2026-08-18: «Развернуть всё / Свернуть всё» — один переключатель над
// таблицей. allExpanded=true только когда ВСЕ текущие строки раскрыты (пустой
// список позиций считается «не всё раскрыто», чтобы кнопка не пряталась в стейте
// «Свернуть всё» без единой строки).
const allExpanded = computed(() =>
  localItems.value.length > 0 && localItems.value.every((_, i) => !!expanded.value[i])
)

function toggleExpandAll() {
  const next: Record<number, boolean> = {}
  const shouldExpand = !allExpanded.value
  localItems.value.forEach((_, i) => { next[i] = shouldExpand })
  expanded.value = next
}

// Auto-expand для match_confirmed=false (D-01.1.2)
watch(localItems, (items) => {
  items.forEach((it, i) => {
    if (it.match_confirmed === false && it.product_id) expanded.value[i] = true
  })
}, { immediate: true })

function rematchContractItem(contractIdx: number, newSourceItemId: number | null) {
  const ci = localContractItems.value[contractIdx]
  if (!ci) return
  ci.source_item_id = newSourceItemId
  ci.match_confirmed = true
  emit('update:contractItems', [...localContractItems.value])
}

function summaryName(idx: number): string {
  return getContractItemFor(idx)?.name || localItems.value[idx]?.item_name || '—'
}

function stageTotals(idx: number) {
  const tz = Number(localItems.value[idx]?.total_price || 0)
  const dog = Number(getContractItemFor(idx)?.total || 0)
  const delivery = isDelivered(idx) ? dog : 0
  return { tz, dog, delivery }
}

function isDelivered(idx: number): boolean {
  void idx
  return props.purchaseStatus === 'delivered' || props.purchaseStatus === 'paid'
}

// Шаг 2 «план ≠ факт» (сессия 2026-08-06): с этих статусов закупка объявлена —
// поля кол-ва/цены ТЗ замораживаются на фронте (то же множество статусов, что
// TZ_FROZEN_STATUSES в backend/app/routers/purchases.py::patch_purchase_item).
// Итоговую цену по факту закупки вносят в подстроке «Договор» позиции.
const TZ_FROZEN_STATUSES = new Set(['work_in_progress', 'contracted', 'ordered', 'delivered', 'paid'])
const tzFrozen = computed(() => TZ_FROZEN_STATUSES.has(props.purchaseStatus || ''))

function isDeliveryFilled(idx: number): boolean {
  return isDelivered(idx) && !!getContractItemFor(idx)
}

const rematchOptions = computed(() => {
  const base = localItems.value.map((it, i) => ({
    title: `№${i + 1}: ${(it.item_name || '').slice(0, 50) || '(без имени)'}`,
    value: (it as any).id ?? i,
  }))
  // Phase 26-nnn: orphan-заглушки. source_item_id у ContractItem может
  // указывать на удалённую PurchaseItem (после dedup phase26-ww или
  // ручного удаления строки ТЗ). Без заглушки Vuetify autocomplete не
  // находит item в items[] и рендерит raw value (голый id типа "1281")
  // — выглядит как "номер БД вместо названия". Добавляем виртуальный
  // option для каждого orphan source_item_id чтобы #selection slot
  // получил selItem с осмысленным title.
  const baseValues = new Set(base.map(o => o.value))
  const orphanIds = new Set<number>()
  for (const ci of localContractItems.value) {
    const sid = (ci as any).source_item_id
    if (sid != null && !baseValues.has(sid)) orphanIds.add(sid)
  }
  const orphans = Array.from(orphanIds).map(id => {
    // Найти ContractItem с этим orphan source_item_id и попытаться отрезолвить через resolvedContractLinks
    const ci = localContractItems.value.find(c => (c as any).source_item_id === id)
    if (ci) {
      const ciId = (ci as any).id
      if (ciId != null) {
        const resolved = resolvedContractLinks.value.get(ciId)
        if (resolved != null) {
          const matchedPi = localItems.value.find(pi => (pi as any).id === resolved)
          if (matchedPi) {
            const idx = localItems.value.indexOf(matchedPi)
            return {
              title: `№${idx + 1}: ${((matchedPi as any).item_name || '').slice(0, 50) || '(без имени)'} (восстановлено)`,
              value: id,  // Keep orphan id чтобы autocomplete found match. При save — fix через rematchContractItem.
            }
          }
        }
      }
    }
    return {
      title: `№${id} (связь не найдена)`,
      value: id,
    }
  })
  return [...base, ...orphans]
})

function isOrphanLink(idx: number): boolean {
  const ci = getContractItemFor(idx)
  if (!ci || ci.source_item_id == null) return false
  return !localItems.value.some(it => (it as any).id === ci.source_item_id)
}

// ── Phase 27.1.14: per-stage contractor chip helpers ──────────────────────────

function contractorNameById(cid: number | null | undefined): string {
  if (cid == null) return ''
  const c = contractors.value?.find(c => c.id === cid)
  return c?.name || ''
}

function contractStageContractorName(idx: number): string {
  // Договор stage: из PurchaseItem.contractor_id (для авансовых из чека Phase 24 D-05)
  // FALLBACK: пусто (Purchase.contractor_id можно передать через props в будущем)
  const pi = localItems.value[idx] as any
  if (pi?.contractor_id) return contractorNameById(pi.contractor_id)
  return ''
}

function deliveryStageContractorName(idx: number): string {
  // Поставка stage: fallback на Договор-контрагента (DeliveryItem Phase 27 ещё не реализован)
  return contractStageContractorName(idx)
}

// Snackbar — единый механизм (useToast + ToastContainer, смонтирован в App.vue).
// По умолчанию уведомление НЕ исчезает само (duration=0): результат действия
// пользователя должен быть прочитан, а не пропасть за 3-4 секунды.
const toast = useToast()
function showSnack(
  text: string,
  color: ToastType = 'success',
  opts?: { actionText?: string; onAction?: () => void; duration?: number },
) {
  toast.addToast(text, color, opts)
}

// Catalog matching (composable) — shared by inline match, repick, import review
const { applyCandidate: applyMatchCandidate, clearBinding: clearMatchBinding } = useItemMatching()

// Product catalogue: load/search/filter, per-row matching (picker/inline/full
// product dialog), category/type grouping, bulk-add-to-catalog — composable,
// see composables/items/useItemsCatalog.ts.
const {
  loadProducts,
  itemsGroupBy, itemsFilterCats, itemsFilterTypes,
  itemCategoryOptions, itemTypeOptions, itemsFilterActive, itemsDisplayRows, visibleItemsCount,
  hasUncatalogedSelected, uncatalogedSelectedCount, bulkAddCatalogLoading, bulkAddToCatalog,
  onInlineMatchPick, onInlineMatchClear, onInlineMatchCreateNew,
  productPickerDialog, productPickerSearch, productPickerResults,
  openProductPicker, selectFromPicker, createProductFromPicker,
  fullProductDialog, fullProductSaving, fullProductEditingId,
  fullProductPhotoFile, fullProductPhotoFileList, fullProductPhotoPreview, fullProductForm,
  fullProductNameSearch, fullProductNameSuggestions, isFullProductDuplicate,
  fullProductTypeOptions, fullProductCategoryOptions, fullAvgPrice,
  onFullPhotoFileChange, openFullProduct,
  openQuickProductEdit, saveFullProduct,
} = useItemsCatalog({
  props, localItems, selectedItemIdxs, emitUpdate, emit, showSnack,
  applyMatchCandidate, clearMatchBinding, clearItem,
})

// Excel/Smart import + product-match review + duplicate-merge + P1-B repick
// dialog (composable) — see composables/items/useItemsImport.ts. Presentational
// half is components/items/ItemsImportWizard.vue.
const {
  itemsImportDialog, itemsImportLoading, itemsImportResult,
  importPreviewData, importError, TARGET_FIELDS,
  currentSheetData, currentSheetHeaders, mappingHasName, unmappedCount,
  isMapped, isIgnored, isTargetFilled, getColumnLabel, getSamples,
  onDragStart, onDropToTarget, onDropToUnresolved, unmapTarget, ignoreColumn,
  openSmartImportDialog, switchImportMode,
  closeImportDialog, doImportPreview, doMappedImport, doImportAllTables,
  smartImportPreview, smartImportColumns, smartImportResult,
  smartImportLoading, doSmartPreview, doSmartImport, downloadDebugReport,
  CRM_MAPPING_FIELDS, crmFieldSelectItems, columnMappingApplied, importWizardState,
  applyColumnMapping,
  matchReviewShow, matchReviewRows, onMatchConfirm, onMatchCancel,
  dupMergeShow, dupMergeGroups, onDupMergeConfirm,
  repickDialog, openRepickDialog, onRepickPick,
} = useItemsImport({
  props, localItems, localContractItems, contractItemImportMode,
  emitUpdate, emitContractItemsUpdate, emit, showSnack, nextUid, applyMatchCandidate,
})

// ── Contractors catalogue — composables/items/useItemsContractors.ts ────────
const {
  localContractors, contractors,
  contractorPickerDialog, contractorPickerSaving, contractorPickerForm,
  contractorPickerIdx, contractorPickerPrefillName, contractorPickerPrefillInn,
  contractorLookupLoading,
  loadContractors, contractorFilter, onItemContractorSelect,
  openContractorQuickCreate, saveContractorQuickCreate,
  tryLookupContractorByInn, onContractorSearchInput,
} = useItemsContractors({ props, localItems, emitUpdate, showSnack })

// showContractorColumn: advance_report → отдельная колонка всегда видна
const showContractorColumn = computed(() => props.formMode === 'advance_report')

// isAdvance: для авансовых закупок Договор/Поставка sub-rows показывают данные из ТЗ
const isAdvance = computed(() => props.formMode === 'advance_report')

// VAT-per-row helpers, item/stage totals and contract-vs-plan savings % —
// composables/items/useItemsTotals.ts. Phase 26-NN: showVatColumnsInExpandRow
// hides НДС columns in expand-row for advance reports with no vat_rate at all.
const {
  effectiveVatRate, vatAmountForStage, totalWithVatForStage, onVatRateChange, calcItemTotal,
  internalTotalNmck, contractItemsTotal, purchasePlannedTotal, contractSavings, contractSavingsPercent,
  showVatColumnsInExpandRow,
} = useItemsTotals({ localItems, localContractItems, getContractItemFor, isAdvance, emitUpdate })

// Phase 26-V: resizable columns
// Phase 26-V-fix (superseded below): «Тип» держал максимум «Услуга»+стрелка
// (6 букв) — 90px, ПОКА ФЭО-каскад рендерился внутри той же ячейки и
// растягивал её принудительно своим min-width. После выноса ФЭО в отдельную
// full-width подстроку (feo-attrs-row) 90px стало мало ДЛЯ САМОГО v-select:
// «Товар»/«Услуга» + встроенная стрелка v-select обрезались в «Т...». Поднято
// до 128 — замерено Playwright: оба варианта помещаются без многоточия.
// «Страна происхождения» ужата до 110 (текст в 2 строки заголовка), чтобы на
// типичной ширине (~1280px) «Ед. изм.» не уезжала за край без скролла.
// unit: жалоба владельца — 90px было мало для v-combobox с выпадающей стрелкой,
// самое длинное значение UNIT_OPTIONS («компл.») обрезалось в «ш..». Поднято
// до 120 — замерено в браузере (Playwright): input.scrollWidth === input.clientWidth
// (без обрезки) у «компл.» начинается с 116px ширины колонки, 120 даёт ~4px
// запас. «кв.м.» умещается с ещё большим запасом.
const { onResizeStart, resizeStyle } = useResizableColumns('purchase-items-editor', {
  name: 320, type: 128, qty: 90, unit: 120, price: 130, sum: 130,
  country: 110, contractor: 200, actions: 80,
})

onMounted(async () => {
  await loadProducts()
  await loadContractors()

  // Phase 27.1.10: auto-fix orphan source_item_id'ы при mount
  // — обновляем UI state синхронно с resolved map'ом + emit чтобы при ближайшем save в БД persist'илось правильно
  let changed = 0
  const orphans: any[] = []
  for (const ci of localContractItems.value) {
    const ciId = (ci as any).id
    if (ciId == null) continue
    const resolved = resolvedContractLinks.value.get(ciId)
    const current = (ci as any).source_item_id
    if (resolved != null && resolved !== current) {
      (ci as any).source_item_id = resolved
      changed++
    }
    // Phase 27.1.11: логируем unresolved orphans для отладки на проде
    if (current != null && resolved == null) {
      orphans.push({
        contract_item_id: ciId,
        contract_item_name: (ci as any).name,
        contract_item_qty: (ci as any).quantity,
        contract_item_price: (ci as any).unit_price,
        broken_source_item_id: current,
        available_pi_count: localItems.value.length,
      })
    }
  }
  if (changed > 0) {
    emit('update:contractItems', [...localContractItems.value])
    console.info(`[PurchaseItemsEditor] auto-resolved ${changed} orphan source_item_id(s)`)
  }
  if (orphans.length > 0) {
    console.warn('[PurchaseItemsEditor] unresolved orphans:', orphans)
  }
})

// ── Totals — composables/items/useItemsTotals.ts ──────────────────────────────

// ── Группировка/фильтр позиций, каталог, product-picker/full-product диалоги —
// composables/items/useItemsCatalog.ts

// ── Items CRUD (add/remove/clear/confirm-match) — composables/items/useItemsTable.ts
// calcItemTotal — composables/items/useItemsTotals.ts

// ── Разбивка позиции по категориям ФЭО — composables/items/useItemsSplit.ts ──
const {
  splitDialog, splitParts, splitItem, splitDialogWidth,
  splitDistributed, splitRemaining, splitBalanced, splitPartsValid, splitCanSave,
  openSplitDialog, closeSplitDialog, addSplitPart, removeSplitPart,
  onSplitPartFeoChange, splitPartPlannedSelection, onSplitPartPlannedChange, splitPartAmount,
  saveSplit,
} = useItemsSplit({ props, localItems, feoNodes, display, emit, showSnack })

// ── Selection — composables/items/useItemsTable.ts ────────────────────────────

// ── Разное ФЭО/план хелперы (per-item) — composables/items/useItemsFeo.ts ────
const {
  pickUnallocatedForItem, _injectUnallocatedNode, _propagateToSelected,
  onItemFeoChange, plannedSelectionFor, pendingByPlannedItem, pendingItemsByPlannedItem,
  plannedAggregateForCategory, categoryResidualFor, planForItem, planExcessFor,
  onItemPlannedChange, onItemTypeChange,
} = useItemsFeo({
  props, localItems, selectedItemIdxs, feoNodes, feoLeaves, canViewLeafBudget,
  emitUpdate, showSnack,
})

// ── ISSUE-3 PART B: bulk-assign FEO level to selected items + «Создать в плане
// закупок» (владелец 2026-08-06) — composables/items/useItemsBulkFeo.ts ──────
const {
  bulkFeoDialog, bulkFeoId, bulkPlannedSelection, unallocatedLoading,
  effectivePlannedItems, bulkPlannedPrefill,
  openBulkFeoDialog, closeBulkFeoDialog, applyBulkFeo, applyBulkUnallocated,
  itemsMissingPlan, itemsMissingPlanWord, itemsMissingPlanSummary,
  needPlanRows, needPlanCount, noCategoryCount, itemsMissingCategoryForPlan,
  createPlannedBulkDialog, createPlannedBulkLoading, createPlannedBulkProgress, createPlannedBulkFailures,
  openCreatePlannedBulkDialog, closeCreatePlannedBulkDialog,
  highlightMissingCategoryForPlan, runCreatePlannedBulk,
} = useItemsBulkFeo({
  props, localItems, selectedItemIdxs, feoNodes,
  injectUnallocatedNode: _injectUnallocatedNode,
  emitUpdate, emit, showSnack,
})

// import-no-clutter: bulk-add несвязанных позиций в каталог
// hasUncatalogedSelected..saveFullProduct — composables/items/useItemsCatalog.ts


// SN-UX: formatNumber / parseNumber now imported from @/utils/numberFormat

// F-PIF2/FCAT-F1: expose helpers for parent (CreateOrderView hard validation)
defineExpose({
  hasMissingFeoLinks() {
    if (!props.feoPerItem) return false
    return localItems.value.some(it => !it.feo_category_id)
  },
  missingFeoRowsCount() {
    if (!props.feoPerItem) return 0
    return localItems.value.filter(it => !it.feo_category_id).length
  },
  // Владелец (2026-09-04): «стрелка должна вести к полю» — родителю (CreateOrderView)
  // нужен _uid первой проблемной строки, чтобы guideArrowTo('item:'+uid) навёлся на
  // КОНКРЕТНУЮ позицию (id="item-row-<uid>" уже проставлен в ItemsTableFlat/
  // ItemsCardsView/ItemsTableStages), а не на весь блок позиций.
  firstMissingFeoRowUid() {
    if (!props.feoPerItem) return null
    return localItems.value.find(it => !it.feo_category_id)?._uid ?? null
  },
})
</script>

<style scoped>
/* Мобильный фикс (владелец, 2026-09-04, «прокручиваемых вбок таблиц быть не должно»):
   растягивает v-btn-toggle (НДС / группировка) на всю ширину контейнера и переносит
   текст кнопок на вторую строку вместо обрезки за правым краем экрана. Vuetify держит
   white-space:nowrap на внутреннем .v-btn__content с приоритетом выше inline-стиля
   родителя — нужен :deep() именно по этому классу. Применяется только через
   :class="{ 'mobile-toggle-wrap': mobile }", на десктоп не влияет. */
.mobile-toggle-wrap {
  width: 100%;
}
.mobile-toggle-wrap :deep(.v-btn) {
  flex: 1 1 0;
  height: auto !important;
  min-height: 32px;
  padding-top: 4px;
  padding-bottom: 4px;
}
.mobile-toggle-wrap :deep(.v-btn__content) {
  white-space: normal;
  text-align: center;
  line-height: 1.2;
}

/* Владелец 2026-08-18: карточки частей в диалоге разбивки позиции */
.split-part-block {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
}

/* Phase 26-V: resizable column handles */
.col-resize-handle {
  position: absolute;
  top: 0; right: 0; bottom: 0;
  width: 6px;
  cursor: col-resize;
  user-select: none;
}
.col-resize-handle:hover {
  background: rgba(var(--v-theme-primary), 0.3);
}
th { position: relative; }

/* ── Import column-mapping table (imap) ─────────────────── */
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
/* ──────────────────────────────────────────────────────── */
.purchase-items-editor {
  width: 100%;
}
</style>

<style>
/* Дефект 2 (владелец, 2026-08-20): «Создать в плане закупок» заблокирована, пока хоть у
   одной непривязанной позиции нет конечной категории ФЭО — визуально приглушена, но не
   :disabled (клик всё равно должен сработать и подсветить проблемную строку, а не молча
   ничего не делать; тот же приём, что .wish-btn-blocked в WishesView.vue). Глобальный
   (не scoped) стиль — id строки, к которой ведёт подсветка, живёт в дочернем компоненте
   (ItemsTableFlat/ItemsCardsView/ItemsTableStages), а не в этом шаблоне. */
.plan-bulk-btn-blocked {
  opacity: 0.55;
  filter: grayscale(0.35);
}
@keyframes plan-bulk-row-pulse-kf {
  0%   { box-shadow: 0 0 0 0 rgba(211, 47, 47, 0.6); outline: 2px solid rgba(211, 47, 47, 0.8); }
  40%  { box-shadow: 0 0 0 8px rgba(211, 47, 47, 0); outline: 2px solid rgba(211, 47, 47, 0.4); }
  60%  { box-shadow: 0 0 0 0 rgba(211, 47, 47, 0); outline: 2px solid rgba(211, 47, 47, 0.8); }
  100% { box-shadow: 0 0 0 0 rgba(211, 47, 47, 0); outline: 2px solid transparent; }
}
.plan-bulk-row-pulse {
  animation: plan-bulk-row-pulse-kf 1s ease-out 3;
  border-radius: 4px;
}
</style>
