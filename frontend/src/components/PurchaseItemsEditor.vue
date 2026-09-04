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
    <div v-if="itemShape === 'purchase' && !props.readonly" class="d-flex ga-2 mb-2 align-center flex-wrap">
      <span class="text-caption text-medium-emphasis">НДС:</span>
      <v-btn-toggle
        :model-value="props.vatMode || 'uniform'"
        density="compact" rounded="lg" color="primary" border mandatory
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
      <v-btn-toggle v-model="itemsGroupBy" density="compact" rounded="lg" color="primary" border mandatory>
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

    <!-- ===== ISSUE-3 PART B: Bulk FEO assignment dialog ===== -->
    <v-dialog v-model="bulkFeoDialog" max-width="520">
      <v-card :loading="unallocatedLoading">
        <v-card-title class="text-subtitle-1">
          Назначить ФЭО для выбранных ({{ selectedItemIdxs.length }})
        </v-card-title>
        <v-card-text>
          <FeoTreeSelect
            v-model="bulkFeoId"
            :nodes="feoNodes"
            :leaves="feoLeaves"
            :plan-positions="effectivePlannedItems"
            :node-amounts="nodeAmounts"
            :allow-unallocated="!!props.subsidyId"
            :root-label="props.subsidyName"
            @pick-unallocated="(parentId: number | null) => applyBulkUnallocated(parentId)"
          />
          <!-- F-PLAN: массовый выбор плановой позиции — компонент сам находит дочерние
               конечные элементы, если выбранный в дереве выше узел не лист. -->
          <FeoPlannedItemsSelect
            v-if="props.feoPlannedPerItem"
            v-model="bulkPlannedSelection"
            :category-id="bulkFeoId"
            :nodes="feoNodes"
            :items="effectivePlannedItems"
            :prefill="bulkPlannedPrefill"
            :purchase-id="props.purchaseId"
            :exclude-purchase-id="props.purchaseId"
            class="mt-2"
            @planned-item-created="emit('planned-item-created')"
            @planned-item-deleted="emit('planned-item-deleted')"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="closeBulkFeoDialog">Отмена</v-btn>
          <v-btn color="primary" variant="flat" :disabled="bulkFeoId == null" @click="applyBulkFeo">
            Применить
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ===== Общая кнопка «Создать в плане закупок» (владелец 2026-08-06) — создаёт плановые
         позиции (Ур.5 FeoPlannedItem) сразу для ВСЕХ позиций, у которых заполнена категория ФЭО,
         но нет привязки к плановой позиции, каждую в своей категории. ===== -->
    <v-dialog v-model="createPlannedBulkDialog" max-width="640" :persistent="createPlannedBulkLoading">
      <v-card>
        <v-card-title class="text-subtitle-1">
          Создать в плане закупок ({{ needPlanRows.length }})
        </v-card-title>
        <v-card-text>
          <div v-if="noCategoryCount > 0" class="text-caption mb-2" style="color:#EF4444">
            У {{ noCategoryCount }} {{ noCategoryCount === 1 ? 'позиции' : 'позиций' }} не выбрана категория ФЭО — для них плановые позиции не создаются.
          </div>
          <!-- Дефект 2 (владелец, 2026-08-20): решение владельца — каждая строка получает
               СВОЮ плановую позицию, одноимённые не объединяются. Честно предупреждаем,
               если в категории уже есть плановая с тем же именем — это НЕ блокирует
               создание и НЕ меняет поведение, только предупреждает, чтобы не было сюрприза. -->
          <div v-if="needPlanRows.some(r => r.duplicateOf)" class="text-caption mb-2" style="color:#B45309">
            У части позиций (отмечены ниже) в этой категории уже есть плановая позиция с таким же названием — будет создана ОТДЕЛЬНАЯ, не объединяются.
          </div>
          <v-table density="compact">
            <thead>
              <tr>
                <th>Наименование</th>
                <th>Кол-во</th>
                <th>Сумма</th>
                <th>Категория ФЭО</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in needPlanRows" :key="row.uid">
                <td>
                  {{ row.name }}
                  <v-tooltip v-if="row.duplicateOf" location="top" :text="`Уже есть: «${row.duplicateOf.name}» — будет создана отдельная позиция`">
                    <template #activator="{ props: tip }">
                      <v-icon v-bind="tip" icon="mdi-alert-outline" size="16" color="warning" class="ml-1" />
                    </template>
                  </v-tooltip>
                </td>
                <td>{{ row.quantity ?? '—' }} {{ row.unit }}</td>
                <td>{{ fmtRub(row.amount) }}</td>
                <td>{{ row.categoryName }}</td>
              </tr>
            </tbody>
          </v-table>
          <div v-if="createPlannedBulkLoading || createPlannedBulkProgress.total > 0" class="mt-3 d-flex align-center ga-2">
            <v-progress-circular v-if="createPlannedBulkLoading" indeterminate size="18" width="2" color="primary" />
            <span class="text-caption">Создано {{ createPlannedBulkProgress.done }} из {{ createPlannedBulkProgress.total }}</span>
          </div>
          <div v-if="createPlannedBulkFailures.length" class="mt-2 text-caption" style="color:#EF4444">
            <div>Не удалось создать/привязать:</div>
            <div v-for="(f, i) in createPlannedBulkFailures" :key="i">{{ f }}</div>
          </div>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" :disabled="createPlannedBulkLoading" @click="closeCreatePlannedBulkDialog">Отмена</v-btn>
          <v-btn color="primary" variant="flat" :loading="createPlannedBulkLoading" :disabled="needPlanRows.length === 0" @click="runCreatePlannedBulk">
            Создать
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ===== Разбивка позиции по категориям ФЭО (владелец 2026-08-18): закупка
         в статусе «Заказано» с заморозкой ТЗ (добавлять НОВЫЕ позиции нельзя), но
         владельцу нужно разложить уже существующую позицию (напр. 66 огнетушителей)
         по нескольким категориям ФЭО/плановым позициям — количество и сумма НЕ
         меняются, меняется только распределение. См. POST
         /purchases/{pid}/items/{item_id}/split в backend/app/routers/purchases.py. ===== -->
    <v-dialog v-model="splitDialog.show" :max-width="splitDialogWidth" :fullscreen="mobile" :persistent="splitDialog.saving">
      <v-card v-if="splitItem">
        <v-card-title class="text-subtitle-1">
          Разбить позицию «{{ splitItem.item_name || '—' }}»
        </v-card-title>
        <v-card-text>
          <div class="text-caption text-medium-emphasis mb-3">
            Исходное количество: {{ formatNumber(splitItem.quantity) }} {{ splitItem.unit }}
            &nbsp;·&nbsp; цена за единицу: {{ fmtRub(splitItem.unit_price || 0) }}
            &nbsp;·&nbsp; сумма: {{ fmtRub(splitItem.total_price || 0) }}
          </div>

          <div v-for="(part, i) in splitParts" :key="i" class="split-part-block mb-4 pa-3">
            <div class="d-flex align-center justify-space-between mb-2">
              <span class="text-caption font-weight-bold">Часть {{ i + 1 }}</span>
              <v-btn v-if="splitParts.length > 2" icon="mdi-close" size="x-small" variant="text" color="error"
                title="Удалить часть" @click="removeSplitPart(i)" />
            </div>
            <v-row dense>
              <v-col cols="12" sm="4">
                <v-text-field
                  :model-value="formatNumber(part.quantity)"
                  label="Кол-во" density="compact" variant="outlined" hide-details
                  @update:model-value="(v: string) => { part.quantity = parseNumber(v) }"
                />
              </v-col>
              <v-col cols="12" sm="8" class="d-flex align-center">
                <span class="text-caption text-medium-emphasis">
                  Сумма части: {{ splitPartAmount(i) != null ? fmtRub(splitPartAmount(i)!) : '—' }}
                </span>
              </v-col>
              <v-col cols="12">
                <FeoTreeSelect
                  :model-value="part.feo_node_id"
                  :nodes="feoNodes"
                  :leaves="feoLeaves"
                  :plan-positions="effectivePlannedItems"
                  :node-amounts="nodeAmounts"
                  :allow-unallocated="!!props.subsidyId"
                  :root-label="props.subsidyName"
                  label="Категория ФЭО"
                  @update:model-value="(v: number | null) => onSplitPartFeoChange(i, v)"
                />
              </v-col>
              <v-col v-if="props.feoPlannedPerItem || props.allowPerItemPlan" cols="12">
                <FeoPlannedItemsSelect
                  :model-value="splitPartPlannedSelection(i)"
                  :category-id="part.feo_node_id ?? part.feo_category_id"
                  :nodes="feoNodes"
                  :items="effectivePlannedItems"
                  :amount="splitPartAmount(i)"
                  :purchase-id="props.purchaseId"
                  :exclude-purchase-id="props.purchaseId"
                  dense
                  @update:model-value="(v) => onSplitPartPlannedChange(i, v)"
                  @planned-item-created="emit('planned-item-created')"
                  @planned-item-deleted="emit('planned-item-deleted')"
                />
              </v-col>
            </v-row>
          </div>

          <v-btn variant="tonal" prepend-icon="mdi-plus" size="small" @click="addSplitPart">Добавить часть</v-btn>

          <div class="mt-4">
            <span class="text-body-2 font-weight-bold" :class="splitBalanced ? 'text-success' : 'text-error'">
              Распределено {{ formatNumber(splitDistributed) }} из {{ formatNumber(splitItem.quantity) }}
              <template v-if="!splitBalanced">, остаток {{ formatNumber(splitRemaining) }}</template>
            </span>
          </div>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" :disabled="splitDialog.saving" @click="closeSplitDialog">Отмена</v-btn>
          <v-btn color="primary" variant="flat" :loading="splitDialog.saving" :disabled="!splitCanSave" @click="saveSplit">
            Разбить
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, reactive, onMounted } from 'vue'
import { useDisplay } from 'vuetify'
import { apiFetch } from '@/api'
import FileDropZone from '@/components/FileDropZone.vue'
import ProductMatchReviewDialog from '@/components/ProductMatchReviewDialog.vue'
import DuplicateMergeDialog from '@/components/DuplicateMergeDialog.vue'
import type { DupGroup, ResolvedGroup } from '@/components/DuplicateMergeDialog.vue'
import SingleProductPickerDialog from '@/components/SingleProductPickerDialog.vue'
import ProductPickerDialog from '@/components/items/ProductPickerDialog.vue'
import FullProductDialog from '@/components/items/FullProductDialog.vue'
import ItemsImportWizard from '@/components/items/ItemsImportWizard.vue'
import ContractorQuickCreate from '@/components/items/ContractorQuickCreate.vue'
import ItemsTableFlat from '@/components/items/ItemsTableFlat.vue'
import ItemsCardsView from '@/components/items/ItemsCardsView.vue'
import ItemsTableWish from '@/components/items/ItemsTableWish.vue'
import ItemsTableStages from '@/components/items/ItemsTableStages.vue'
import FeoTreeSelect from '@/components/items/FeoTreeSelect.vue'
import FeoPlannedItemsSelect from '@/components/items/FeoPlannedItemsSelect.vue'
import type { ContractItem } from '@/types/contractItem'
import type { ItemsDisplayRow } from '@/components/items/types'
import { copyFromPurchase as apiCopyFromPurchase } from '@/api/contractItems'
import { useResizableColumns } from '@/composables/useResizableColumns'
import { formatNumber, parseNumber, fmtRub } from '@/utils/numberFormat'
import { useFeoLeaves } from '@/composables/useFeoLeaves'
import { useFeoNodeAmounts } from '@/composables/useFeoNodeAmounts'
import type { FeoPlanPosition, FeoPlanSelection } from '@/composables/useFeoPlannedResiduals'
import { useItemMatching, type MatchCandidate } from '@/composables/useItemMatching'
import { useToast, type ToastType } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'
import type { PriceFreshness } from '@/composables/usePriceFreshness'
import {
  VAT_RATE_OPTIONS,
  parseVatRatePercent,
  vatAmount,
  totalWithVat,
  normalizeVatRate,
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

// Phase 17.1-08: prefer the bytea-backed /api/products/{id}/photo endpoint
// when the backend has a cached copy; fall back to external photo_url/link.
function productPhotoSrc(p: Pick<Product, 'id' | 'has_photo' | 'photo_url' | 'photo_link'> | null | undefined): string | undefined {
  if (!p) return undefined
  if (p.has_photo) return `/api/products/${p.id}/photo`
  return p.photo_url || p.photo_link || undefined
}

interface PriceLink {
  url: string
  price: number | null
}

// ── Constants ────────────────────────────────────────────────────────────────

const UNIT_OPTIONS = ['шт.', 'усл.', 'компл.', 'уп.', 'м.', 'кг.', 'л.', 'п.м.', 'кв.м.', 'час.', 'мес.', 'год']
const COUNTRIES = ['РФ', 'Беларусь', 'Казахстан', 'Китай', 'Германия', 'США', 'Япония', 'Турция', 'Индия']

// Fix 3 + Fix 4/5: VAT options/helpers now from @/composables/useVatCalc
// (VAT_RATE_OPTIONS, parseVatRatePercent, vatAmount, totalWithVat,
// normalizeVatRate imported above). Phase 27.1.16 convention preserved:
// unit_price / total_price из чека ФФД ВКЛЮЧАЮТ НДС; vatAmount выделяет НДС
// из суммы С НДС: total * pct / (100 + pct).

// Phase 27.1.17: per-stage helpers с fallback vat_rate на PurchaseItem
function effectiveVatRate(idx: number, stage: 'contract' | 'delivery'): string | null {
  const ci = getContractItemFor(idx)
  return ci?.vat_rate ?? localItems.value[idx]?.vat_rate ?? null
}

function vatAmountForStage(idx: number, stage: 'tz' | 'contract' | 'delivery'): number {
  let rate: string | null = null
  let total = 0
  if (stage === 'tz') {
    const pi = localItems.value[idx]
    rate = pi?.vat_rate ?? null
    total = Number((pi as any)?.total_price ?? 0)
  } else if (stage === 'contract') {
    rate = effectiveVatRate(idx, 'contract')
    total = Number(getContractItemFor(idx)?.total ?? 0)
  } else {
    rate = effectiveVatRate(idx, 'delivery')
    total = Number(getContractItemFor(idx)?.total ?? 0)
  }
  if (!rate) return 0
  const pct = parseVatRatePercent(rate)
  if (pct <= 0) return 0
  return Number((total * pct / (100 + pct)).toFixed(2))
}

function totalWithVatForStage(idx: number, stage: 'contract' | 'delivery'): number {
  return Number(getContractItemFor(idx)?.total ?? 0)
}

// fmtRub now imported from @/utils/numberFormat

function onVatRateChange(idx: number, v: any) {
  const item = localItems.value[idx]
  if (!item) return
  item.vat_rate = normalizeVatRate(v)
  calcItemTotal(idx)
}

// Export COUNTRIES so template can use it if needed (not currently rendered but kept for completeness)
void COUNTRIES

// BUG #3: stable, monotonically-increasing row identity. Used as :key so that
// rows keep insertion order and do NOT re-order/re-render when item_name changes
// (e.g. via inline catalog matching).
let _uidCounter = 0
function nextUid(): string {
  _uidCounter += 1
  return `it-${Date.now().toString(36)}-${_uidCounter}`
}
function ensureUid<T extends { _uid?: string | number }>(item: T): T {
  if (item._uid == null) item._uid = nextUid()
  return item
}

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
const canViewLeafBudget = computed(() => authStore.hasAction('feo_budget.view_leaf'))

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

// BUG #3: assign stable _uid to every incoming item missing one (in-place so the
// parent's objects keep identity), preserving insertion order.
function normalizeItems(items: EditorItem[]): EditorItem[] {
  return items.map(it => ensureUid(it))
}
const localItems = ref<EditorItem[]>(normalizeItems([...props.modelValue]))

// Duplicate merge dialog state
const dupMergeShow = ref(false)
const dupMergeGroups = ref<DupGroup[]>([])
// Pending items waiting for user decision in DuplicateMergeDialog
let _pendingMergeItems: EditorItem[] = []

// Perf: self-emit guard breaks the emit→parent-writeback→watch-rebuild echo loop.
// Shallow watch (no deep) — we only need to react when the parent SWAPS the array
// reference (load/reset). Local nested-field edits mutate localItems[idx] objects
// directly and call emitUpdate() explicitly, so deep traversal is unnecessary.
let _selfEmit = false
watch(
  () => props.modelValue,
  (v) => {
    // Skip rebuild when the incoming value is the array we just emitted.
    if (_selfEmit) { _selfEmit = false; return }
    localItems.value = normalizeItems([...v])
  }
)

function emitUpdate() {
  _selfEmit = true
  emit('update:modelValue', [...localItems.value])
  emit('items-changed')
}

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

const contractItemsTotal = computed(() =>
  localContractItems.value.reduce((s, ci) => s + Number(ci.total || 0), 0),
)

const purchasePlannedTotal = computed(() =>
  localItems.value.reduce((s, it) => s + Number(it.total_price || 0), 0),
)

const contractSavings = computed(() => {
  const tz = purchasePlannedTotal.value
  const ci = contractItemsTotal.value
  if (!tz || !ci) return null
  return tz - ci
})

const contractSavingsPercent = computed(() => {
  const tz = purchasePlannedTotal.value
  const sv = contractSavings.value
  if (!tz || sv == null) return null
  return ((sv / tz) * 100).toFixed(1)
})

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

// Products catalogue
const products = ref<Product[]>([])

// Catalog matching (composable) — shared by inline match, repick, import review
const { applyCandidate: applyMatchCandidate, clearBinding: clearMatchBinding } = useItemMatching()

// ── Contractors catalogue ────────────────────────────────────────────────────

// Phase 26-JJ: localContractors holds hydrated-per-id + live-search results.
// contractors computed merges props.contractors (parent shared state) with local — no duplicates.
const localContractors = ref<Contractor[]>([])
const contractors = computed<Contractor[]>(() => {
  if (!props.contractors) return localContractors.value
  const seen = new Set(props.contractors.map((c: Contractor) => c.id))
  return [...props.contractors, ...localContractors.value.filter((c: Contractor) => !seen.has(c.id))]
})
const contractorPickerDialog = ref(false)
const contractorPickerSaving = ref(false)
const contractorPickerForm = reactive({
  name: '',
  inn: '',
  kpp: '',
  address: '',
})
const contractorPickerIdx = ref(-1)
const contractorPickerPrefillName = ref('')
const contractorPickerPrefillInn = ref('')

// Per-row loading state для INN lookup
const contractorLookupLoading = ref<Record<number, boolean>>({})

// showContractorColumn: advance_report → отдельная колонка всегда видна
const showContractorColumn = computed(() => props.formMode === 'advance_report')

// isAdvance: для авансовых закупок Договор/Поставка sub-rows показывают данные из ТЗ
const isAdvance = computed(() => props.formMode === 'advance_report')

// Phase 26-NN: для авансовых отчётов, если ни у одной позиции нет vat_rate
// (чек от ИП на УСН или НДС не извлёкся) — скрываем НДС-колонки в expand-row.
// Для не-авансовых — колонки НДС всегда видны.
const showVatColumnsInExpandRow = computed(() => {
  if (!isAdvance.value) return true
  return (localItems.value || []).some((it: any) =>
    it?.vat_rate && String(it.vat_rate).trim() !== ''
  )
})

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

// Phase 26-JJ: NO bulk load. Hydrate only known contractor_id from current items.
// If props.contractors is provided — parent already manages the list.
async function loadContractors() {
  if (props.contractors) return  // shared state from parent — parent will hydrate
  const ids = Array.from(new Set(
    (props.modelValue || [])
      .map((it: any) => it.contractor_id)
      .filter((id: any) => typeof id === 'number' && id > 0)
  )) as number[]
  if (!ids.length) return
  const fetched = await Promise.all(
    ids.map((id: number) => apiFetch<Contractor>(`/contractors/${id}`).catch(() => null as any))
  )
  for (const c of fetched) {
    if (c && c.id && !localContractors.value.some((x: Contractor) => x.id === c.id)) {
      localContractors.value.push(c)
    }
  }
}

function contractorFilter(_value: string, query: string, item?: any): boolean {
  if (!query.trim()) return true
  const q = query.toLowerCase().trim()
  const name = (item?.raw?.name || '').toLowerCase()
  const inn = (item?.raw?.inn || '').toLowerCase()
  return name.includes(q) || inn.includes(q)
}

function onItemContractorSelect(idx: number, val: Contractor | null) {
  const item = localItems.value[idx]
  if (!item) return
  if (!val) {
    item.contractor_id = null
    item.contractor_name = null
    item.contractor_inn = null
  } else {
    item.contractor_id = val.id
    item.contractor_name = val.name
    item.contractor_inn = val.inn || null
  }
  emitUpdate()
}

function openContractorQuickCreate(idx: number, prefillName?: string, prefillInn?: string) {
  contractorPickerIdx.value = idx
  contractorPickerPrefillName.value = prefillName || ''
  contractorPickerPrefillInn.value = prefillInn || ''
  Object.assign(contractorPickerForm, {
    name: prefillName || '',
    inn: prefillInn || '',
    kpp: '',
    address: '',
  })
  contractorPickerDialog.value = true
}

async function saveContractorQuickCreate() {
  if (!contractorPickerForm.name.trim()) return
  contractorPickerSaving.value = true
  try {
    const saved = await apiFetch<Contractor>('/contractors/', {
      method: 'POST',
      body: {
        name: contractorPickerForm.name.trim(),
        inn: contractorPickerForm.inn.trim() || null,
        kpp: contractorPickerForm.kpp.trim() || null,
        address: contractorPickerForm.address.trim() || null,
      },
    })
    // Phase 26-JJ: loadContractors теперь не делает bulk load — добавляем нового контрагента напрямую
    if (saved && saved.id && !localContractors.value.some((c: Contractor) => c.id === saved.id)) {
      localContractors.value.push(saved)
    }
    if (contractorPickerIdx.value >= 0) {
      onItemContractorSelect(contractorPickerIdx.value, saved)
    }
    contractorPickerDialog.value = false
    showSnack(`Контрагент «${saved.name}» создан`)
  } catch (e: any) {
    const msg = e?.payload?.message || e?.detail || e?.message || 'Ошибка создания контрагента'
    showSnack(typeof msg === 'string' ? msg : JSON.stringify(msg), 'error')
  } finally {
    contractorPickerSaving.value = false
  }
}

// Lookup contractor by INN from the local list
async function tryLookupContractorByInn(inn: string): Promise<Contractor | null> {
  if (!inn || inn.length < 10) return null
  const found = contractors.value.find(c => c.inn === inn)
  if (found) return found
  try {
    const res = await apiFetch<Contractor>(`/contractors/lookup-inn/${inn}`)
    return res || null
  } catch {
    return null
  }
}

// Phase 26-JJ: live server-search + INN lookup
let _innLookupTimer: ReturnType<typeof setTimeout> | null = null
let _searchTimer: ReturnType<typeof setTimeout> | null = null
async function onContractorSearchInput(idx: number, search: string) {
  if (_innLookupTimer) { clearTimeout(_innLookupTimer); _innLookupTimer = null }
  if (_searchTimer) { clearTimeout(_searchTimer); _searchTimer = null }

  const q = (search || '').trim()
  if (!q) return

  // Цифровой ИНН (10/12) — отдельный путь через lookup-inn
  if (/^\d{10}$|^\d{12}$/.test(q)) {
    if (contractors.value.some((c: Contractor) => c.inn === q)) return
    _innLookupTimer = window.setTimeout(async () => {
      contractorLookupLoading.value[idx] = true
      try {
        const found = await apiFetch<Contractor>(`/contractors/lookup-inn/${q}`)
        if (found && found.id) {
          if (!localContractors.value.some((c: Contractor) => c.id === found.id)) {
            localContractors.value.push(found)
          }
          const item = localItems.value[idx]
          if (item && !item.contractor_id) {
            onItemContractorSelect(idx, found)
          }
        }
      } catch {
        // ФНС не нашёл / network — молча игнорируем
      } finally {
        contractorLookupLoading.value[idx] = false
      }
    }, 600) as unknown as number
    return
  }

  // Текстовый поиск — server-side через /contractors/?search=...
  if (q.length < 2) return
  _searchTimer = window.setTimeout(async () => {
    contractorLookupLoading.value[idx] = true
    try {
      const results = await apiFetch<Contractor[]>(`/contractors/?search=${encodeURIComponent(q)}&limit=50`)
      if (Array.isArray(results)) {
        for (const c of results) {
          if (c.id && !localContractors.value.some((x: Contractor) => x.id === c.id)) {
            localContractors.value.push(c)
          }
        }
      }
    } catch {
      // network — молча игнорируем
    } finally {
      contractorLookupLoading.value[idx] = false
    }
  }, 300) as unknown as number
}

onMounted(async () => {
  try {
    products.value = await apiFetch<Product[]>('/products/')
  } catch (e) {
    console.warn('[PurchaseItemsEditor] Could not load products:', e)
  }
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

// ── Totals ───────────────────────────────────────────────────────────────────

const internalTotalNmck = computed(() =>
  localItems.value.reduce((s, i) => s + (i.total_price || 0), 0)
)

// ── Группировка/фильтр позиций по категории и виду товара из каталога ────────
// Категория/вид берутся у сматченного товара (product_id → products); позиции
// без товара попадают в «Без категории»/«Без вида». Строки данных ссылаются на
// ОРИГИНАЛЬНЫЙ индекс в localItems, поэтому все idx-события работают как раньше.
const NO_CATEGORY = 'Без категории'
const NO_TYPE = 'Без вида'
const itemsGroupBy = ref<'none' | 'category' | 'category_type'>('none')
const itemsFilterCats = ref<string[]>([])
const itemsFilterTypes = ref<string[]>([])

const productById = computed(() => {
  const m = new Map<number, Product>()
  for (const p of products.value) m.set(p.id, p)
  return m
})
function itemCategoryOf(it: EditorItem): string {
  const p = it.product_id != null ? productById.value.get(it.product_id) : undefined
  return (p?.category || '').trim() || ((it as any)._category || '').trim() || NO_CATEGORY
}
function itemTypeOf(it: EditorItem): string {
  const p = it.product_id != null ? productById.value.get(it.product_id) : undefined
  return (p?.product_type || '').trim() || ((it as any)._product_type || '').trim() || NO_TYPE
}
const itemCategoryOptions = computed(() => {
  const s = new Set(localItems.value.map(itemCategoryOf))
  return [...s].sort((a, b) => a.localeCompare(b, 'ru'))
})
const itemTypeOptions = computed(() => {
  const cats = itemsFilterCats.value
  const s = new Set(
    localItems.value
      .filter(it => !cats.length || cats.includes(itemCategoryOf(it)))
      .map(itemTypeOf)
  )
  return [...s].sort((a, b) => a.localeCompare(b, 'ru'))
})
const itemsFilterActive = computed(() =>
  itemsFilterCats.value.length > 0 || itemsFilterTypes.value.length > 0
)

const itemsDisplayRows = computed<ItemsDisplayRow[] | null>(() => {
  // null → дети рендерят natural order без каких-либо изменений (быстрый путь)
  if (itemsGroupBy.value === 'none' && !itemsFilterActive.value) return null
  const rows = localItems.value
    .map((item, idx) => ({
      idx,
      cat: itemCategoryOf(item),
      type: itemTypeOf(item),
      sum: Number(item.total_price || 0),
    }))
    .filter(r =>
      (!itemsFilterCats.value.length || itemsFilterCats.value.includes(r.cat)) &&
      (!itemsFilterTypes.value.length || itemsFilterTypes.value.includes(r.type))
    )
  if (itemsGroupBy.value === 'none') return rows.map(r => ({ idx: r.idx }))
  rows.sort((a, b) =>
    a.cat.localeCompare(b.cat, 'ru') ||
    a.type.localeCompare(b.type, 'ru') ||
    a.idx - b.idx
  )
  const out: ItemsDisplayRow[] = []
  let curCat: string | null = null
  let curType: string | null = null
  for (const r of rows) {
    if (r.cat !== curCat) {
      curCat = r.cat
      curType = null
      const grp = rows.filter(x => x.cat === r.cat)
      out.push({ header: r.cat, level: 1, count: grp.length, sum: grp.reduce((s, x) => s + x.sum, 0) })
    }
    if (itemsGroupBy.value === 'category_type' && r.type !== curType) {
      curType = r.type
      const grp = rows.filter(x => x.cat === r.cat && x.type === r.type)
      out.push({ header: r.type, level: 2, count: grp.length, sum: grp.reduce((s, x) => s + x.sum, 0) })
    }
    out.push({ idx: r.idx })
  }
  return out
})
const visibleItemsCount = computed(() =>
  itemsDisplayRows.value == null
    ? localItems.value.length
    : itemsDisplayRows.value.filter(r => r.idx != null).length
)

// ── Items CRUD ────────────────────────────────────────────────────────────────

function addItem(atStart = false) {
  const newItem: EditorItem = {
    _uid: nextUid(),
    product_id: null,
    item_name: '',
    item_type: props.defaultItemType,
    quantity: null,
    unit: props.defaultUnit,
    unit_price: null,
    total_price: null,
    country_origin: props.defaultCountry,
    _selectedProduct: null,
    _photo_url: undefined,
    _description: undefined,
    _description_44fz: undefined,
  }
  if (props.itemShape === 'purchase') {
    newItem.final_unit_price = null
    newItem.final_total = null
    // F-PLAN: новая строка сразу наследует шапочную плановую позицию, если задана
    newItem.feo_planned_item_id = props.defaultFeoPlannedItemId ?? null
    newItem.over_plan = false
    // ISSUE-3 PART A: inherit header-selected deepest FEO level by default
    if (props.feoPerItem && newItem.feo_category_id == null && props.defaultFeoCategoryId != null) {
      newItem.feo_category_id = props.defaultFeoCategoryId
    }
  }
  if (atStart) {
    // Кнопка в шапке: новая строка сверху, чтобы была видна без прокрутки длинного списка
    localItems.value.unshift(newItem)
    selectedItemIdxs.value = selectedItemIdxs.value.map(i => i + 1)
  } else {
    localItems.value.push(newItem)
  }
  emit('item-added', newItem)
  emitUpdate()
}

function removeItem(idx: number) {
  localItems.value.splice(idx, 1)
  selectedItemIdxs.value = selectedItemIdxs.value
    .filter(i => i !== idx)
    .map(i => (i > idx ? i - 1 : i))
  emit('item-removed', idx)
  emitUpdate()
}

function clearItem(idx: number) {
  localItems.value[idx].item_name = ''
  localItems.value[idx].product_id = null
  localItems.value[idx]._selectedProduct = null
  localItems.value[idx]._photo_url = undefined
  localItems.value[idx]._description = undefined
  localItems.value[idx]._description_44fz = undefined
  localItems.value[idx]._price_meta = null
  emitUpdate()
}

function confirmMatch(idx: number) {
  const item = localItems.value[idx]
  if (item) {
    item.match_confirmed = true
    emitUpdate()
  }
}

function calcItemTotal(idx: number) {
  const item = localItems.value[idx]
  if (item.quantity != null && item.unit_price != null) {
    item.total_price = Math.round(item.quantity * item.unit_price * 100) / 100
  } else {
    item.total_price = null
  }
  emitUpdate()
}

// ── Разбивка позиции по категориям ФЭО (владелец 2026-08-18) ────────────────
// Закупка «Заказано» (statuses с tzFrozen=true) запрещает ДОБАВЛЕНИЕ новых
// позиций, но не запрещает разложить уже существующую позицию по нескольким
// категориям/плановым позициям — количество и сумма не меняются, только
// распределение. POST /purchases/{pid}/items/{item_id}/split (backend, не
// трогаем): Σ quantity частей ДОЛЖНА точно совпасть с quantity исходной
// позиции, иначе backend вернёт 409 с числами — здесь этот же инвариант
// проверяется на лету, чтобы 409 не был первым, что видит пользователь.
interface SplitPart {
  quantity: number | null
  // UI-only: узел дерева ФЭО (может быть промежуточным, не только листом) —
  // тот же паттерн, что item.feo_node_id/feo_category_id у обычной позиции
  // (см. onItemFeoChange выше).
  feo_node_id: number | null
  feo_category_id: number | null
  feo_planned_item_id: number | null
}

const splitDialog = reactive({
  show: false,
  idx: null as number | null,
  saving: false,
})
const splitParts = ref<SplitPart[]>([])

const splitItem = computed<EditorItem | null>(() =>
  splitDialog.idx != null ? (localItems.value[splitDialog.idx] ?? null) : null
)

// Тот же приём адаптивной ширины диалога, что и reqItemEditDialogWidth в
// SubsidiesView.vue (сессия 2026-08-18): 720 планшет/маленький ноутбук, 900
// обычный десктоп, 1100 крупный монитор. mobile (уже объявлен выше) держит
// :fullscreen, как у остальных диалогов этого файла.
const splitDialogWidth = computed(() => {
  if (display.smAndDown.value) return 720
  if (display.mdAndDown.value) return 900
  return 1100
})

const splitDistributed = computed(() =>
  splitParts.value.reduce((s, p) => s + (Number(p.quantity) || 0), 0)
)
const splitRemaining = computed(() => {
  const total = Number(splitItem.value?.quantity ?? 0)
  // Округление до 4 знаков — в БД parts.quantity Numeric(15,4), сравнение «в лоб»
  // float'ов иначе почти никогда не даст точный 0.
  return Math.round((total - splitDistributed.value) * 10000) / 10000
})
const splitBalanced = computed(() => splitParts.value.length >= 2 && Math.abs(splitRemaining.value) < 0.0001)
// Backend требует quantity части > 0 (см. split_purchase_item) — проверяем на
// лету, чтобы не отправлять заведомо отклоняемый запрос (часть с пустым/нулевым
// кол-вом при «сходящемся» остатке технически возможна, если другая часть
// компенсирует разницу).
const splitPartsValid = computed(() => splitParts.value.every(p => Number(p.quantity) > 0))
const splitCanSave = computed(() => splitBalanced.value && splitPartsValid.value)

function openSplitDialog(idx: number) {
  const item = localItems.value[idx]
  if (!item) return
  splitDialog.idx = idx
  splitParts.value = [
    {
      quantity: null,
      feo_node_id: item.feo_node_id ?? item.feo_category_id ?? null,
      feo_category_id: item.feo_category_id ?? null,
      feo_planned_item_id: null,
    },
    { quantity: null, feo_node_id: null, feo_category_id: null, feo_planned_item_id: null },
  ]
  splitDialog.show = true
}

// ⚠️ БАГ (найден живым тестом на локалке, сессия 2026-08-18): guard
// `splitDialog.saving` защищает от закрытия ПОЛЬЗОВАТЕЛЕМ (кнопка «Отмена»/
// клик вне диалога) во время сохранения — но saveSplit() ниже вызывает эту же
// функцию ПОСЛЕ успешного запроса, ДО того как finally сбросит saving в false,
// поэтому guard молча блокировал автозакрытие: сеть отвечала 200, снэкбар
// «Позиция разбита на части» показывался, а диалог оставался открытым с
// прежними значениями частей. Поэтому здесь guard не проверяется — вызывающая
// сторона (saveSplit) сама решает, когда звать forceClose; пользовательский
// путь (кнопка «Отмена») защищён отдельно через :disabled на этой кнопке и
// :persistent на v-dialog (см. template), а не через эту функцию.
function closeSplitDialog() {
  splitDialog.show = false
  splitDialog.idx = null
  splitParts.value = []
}

function addSplitPart() {
  splitParts.value.push({ quantity: null, feo_node_id: null, feo_category_id: null, feo_planned_item_id: null })
}

function removeSplitPart(i: number) {
  if (splitParts.value.length <= 2) return
  splitParts.value.splice(i, 1)
}

// Тот же паттерн, что onItemFeoChange: клик по нелистовому узлу дерева только
// углубляет навигацию (feo_category_id остаётся null), клик по листу — фиксирует
// категорию части. Смена категории части сбрасывает её плановую позицию (Ур.5),
// если та принадлежала другой категории — иначе backend отклонит part с 409.
function onSplitPartFeoChange(i: number, nodeId: number | null) {
  const part = splitParts.value[i]
  if (!part) return
  const isLeaf = nodeId != null && (feoNodes.value.find(n => n.id === nodeId)?.is_leaf ?? false)
  const newCategoryId = isLeaf ? nodeId : null
  if (part.feo_category_id !== newCategoryId) part.feo_planned_item_id = null
  part.feo_node_id = nodeId
  part.feo_category_id = newCategoryId
}

function splitPartPlannedSelection(i: number): FeoPlanSelection | null {
  const part = splitParts.value[i]
  if (!part || part.feo_planned_item_id == null) return null
  return { kind: 'planned_item', id: part.feo_planned_item_id }
}

// feo_planned_item_id (POST /split) — id конкретной FeoPlannedItem (Ур.5), НЕ
// id категории/плановой строки уровня категории. FeoPlannedItemsSelect может
// эмитить kind='plan_position'|'feo_article' (план на уровне самой категории,
// без отдельной Ур.5 записи) — такие значения split-эндпоинту не передаём.
function onSplitPartPlannedChange(i: number, val: FeoPlanSelection | null) {
  const part = splitParts.value[i]
  if (!part) return
  part.feo_planned_item_id = val && val.kind === 'planned_item' ? val.id : null
}

function splitPartAmount(i: number): number | null {
  const part = splitParts.value[i]
  const unitPrice = splitItem.value?.unit_price
  if (!part || part.quantity == null || unitPrice == null) return null
  return Math.round(Number(part.quantity) * Number(unitPrice) * 100) / 100
}

async function saveSplit() {
  const item = splitItem.value
  if (!item || props.purchaseId == null) return
  const itemId = (item as any).id
  if (itemId == null) {
    showSnack('Позиция ещё не сохранена — сохраните закупку и повторите', 'warning')
    return
  }
  if (!splitCanSave.value) return
  splitDialog.saving = true
  try {
    await apiFetch(`/purchases/${props.purchaseId}/items/${itemId}/split`, {
      method: 'POST',
      body: JSON.stringify({
        parts: splitParts.value.map(p => ({
          quantity: p.quantity,
          feo_category_id: p.feo_category_id,
          feo_planned_item_id: p.feo_planned_item_id,
        })),
      }),
    })
    showSnack('Позиция разбита на части', 'success')
    closeSplitDialog()
    // Тот же приём, что у bulkAddToCatalog/runCreatePlannedBulk выше: сервер
    // пересчитал/создал позиции — перезагружаем их у родителя, а не пытаемся
    // угадать результат локально.
    emit('reload-requested')
  } catch (e: any) {
    showSnack(e?.payload?.message ?? e?.detail ?? e?.message ?? 'Ошибка разбивки позиции', 'error')
  } finally {
    splitDialog.saving = false
  }
}

// ── Selection ────────────────────────────────────────────────────────────────

const selectedItemIdxs = ref<number[]>([])
const allItemsSelected = computed(() =>
  localItems.value.length > 0 && selectedItemIdxs.value.length === localItems.value.length
)

function toggleSelectAll(val: boolean | null) {
  selectedItemIdxs.value = val ? localItems.value.map((_, i) => i) : []
}

function toggleItemSelect(idx: number, val: boolean | null) {
  if (val) {
    if (!selectedItemIdxs.value.includes(idx)) selectedItemIdxs.value.push(idx)
  } else {
    selectedItemIdxs.value = selectedItemIdxs.value.filter(i => i !== idx)
  }
}

function removeSelectedItems() {
  const toRemove = new Set(selectedItemIdxs.value)
  localItems.value = localItems.value.filter((_, i) => !toRemove.has(i))
  selectedItemIdxs.value = []
  emitUpdate()
}

// ── ISSUE-3 PART B: bulk-assign FEO level to selected items ───────────────────
const bulkFeoDialog = ref(false)
const bulkFeoId = ref<number | null>(null)
// F-PLAN: массово назначаемая плановая позиция (единый источник plan-positions) для bulk-диалога.
const bulkPlannedSelection = ref<FeoPlanSelection | null>(null)
const unallocatedLoading = ref(false)

// F-PLAN: список плановых позиций для bulk-диалога — то же, что приходит в проп.
const effectivePlannedItems = computed(() => props.plannedItems || [])

// Предзаполнение диалога «Создать в плане закупок» для bulk-выбора — имя первой
// выбранной позиции, сумма — Σ total_price ВСЕХ выбранных (агрегат по группе, не
// одна позиция, как в построчных редакторах).
const bulkPlannedPrefill = computed(() => {
  const rows = selectedItemIdxs.value.map(idx => localItems.value[idx]).filter((r): r is EditorItem => !!r)
  const first = rows.find(r => (r.item_name || '').trim())
  const amount = rows.reduce((sum, r) => sum + (Number(r.total_price) || 0), 0)
  return {
    name: first?.item_name ?? null,
    quantity: first?.quantity ?? null,
    unit: first?.unit ?? null,
    amount,
  }
})

function openBulkFeoDialog() {
  bulkFeoId.value = null
  bulkPlannedSelection.value = null
  bulkFeoDialog.value = true
}

function closeBulkFeoDialog() {
  bulkFeoDialog.value = false
  bulkFeoId.value = null
  bulkPlannedSelection.value = null
}

function applyBulkFeo() {
  if (bulkFeoId.value == null) return
  // Same rule as onItemFeoChange: feo_node_id всегда получает выбранный узел
  // (лист или промежуточная папка), feo_category_id — только когда узел лист.
  // Раньше здесь писался только feo_category_id, и поле позиции (которое
  // читает feo_node_id ?? feo_category_id) продолжало показывать старый путь.
  const isLeaf = feoNodes.value.find(n => n.id === bulkFeoId.value)?.is_leaf ?? false
  const planned = bulkPlannedSelection.value
  for (const idx of selectedItemIdxs.value) {
    const item = localItems.value[idx]
    if (item) {
      item.feo_node_id = bulkFeoId.value
      item.feo_category_id = isLeaf ? bulkFeoId.value : null
      // F-PLAN: массовое назначение плановой позиции — только когда выбрана явно в диалоге.
      if (planned) {
        if (planned.kind === 'planned_item') {
          item.feo_planned_item_id = planned.id
        } else {
          item.feo_planned_item_id = null
          item.feo_category_id = planned.id
        }
        item.over_plan = false
      }
    }
  }
  bulkFeoDialog.value = false
  bulkFeoId.value = null
  bulkPlannedSelection.value = null
  selectedItemIdxs.value = []
  emitUpdate()
}

async function applyBulkUnallocated(parentId: number | null) {
  if (!props.subsidyId) return
  unallocatedLoading.value = true
  try {
    const body: Record<string, unknown> = { subsidy_id: props.subsidyId }
    if (parentId != null) body.parent_id = parentId
    const cat = await apiFetch<{ id: number; name: string; parent_id: number | null }>('/feo-categories/unallocated', {
      method: 'POST',
      body: JSON.stringify(body),
    })
    // Добавить в feoNodes если отсутствует, пометив родителя не-листом.
    _injectUnallocatedNode(cat)
    for (const idx of selectedItemIdxs.value) {
      const item = localItems.value[idx]
      if (item) {
        item.feo_node_id = cat.id
        item.feo_category_id = cat.id
      }
    }
    bulkFeoDialog.value = false
    bulkFeoId.value = null
    selectedItemIdxs.value = []
    emitUpdate()
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.message || 'Ошибка получения категории «Не определена»', 'error')
  } finally {
    unallocatedLoading.value = false
  }
}

// ── Владелец 2026-08-06: общая кнопка «Создать в плане закупок» ───────────────
// «Если делаются разные категории ФЭО, то ... должна быть общая кнопка, которая
// "Создать в плане закупок" — при нажатии на неё все позиции, которые не привязались
// к плановым, надо создать будут в соответствующих категориях, как плановые, которые
// для них выбраны». Категория позиции — тот же эффективный узел, что используют
// per-item FeoPlannedItemsSelect в таблицах (item.feo_node_id ?? item.feo_category_id,
// см. ItemsTableFlat.vue/ItemsCardsView.vue/ItemsTableStages.vue).
interface PlanCreateRow {
  idx: number
  uid: string | number
  name: string
  quantity: number | null
  unit: string
  amount: number | null
  categoryId: number
  categoryName: string
  // Дефект 2 (владелец, 2026-08-20): решение владельца — каждой строке своя ОТДЕЛЬНАЯ
  // плановая позиция, одноимённые НЕ объединяются (см. runCreatePlannedBulk). Это поле
  // чисто информационное — честно предупредить в предпросмотре, что в этой категории
  // уже есть плановая позиция с таким же именем, НЕ блокирует и НЕ меняет создание.
  duplicateOf: { id: number; name: string } | null
}

// Этап 1 (владелец, 2026-09-02): «сейчас на закупке без per-item категорий
// кнопка "Создать в плане закупок" гаснет, и расхождение нечем исправить» —
// когда режим «разные категории ФЭО для каждого товара» (feoPerItem) ВЫКЛЮЧЕН,
// эффективная категория позиции обязана быть категорией шапки (defaultFeoCategoryId),
// а не собственным feo_category_id позиции (в этом режиме позиции вообще не
// должны иметь свою категорию — см. backend _item_feo_mismatch reason="header",
// который как раз и алярмит расхождение, если она вдруг есть). Когда feoPerItem
// ВКЛЮЧЁН — прежнее поведение (своя категория позиции).
function _effectiveFeoCategoryId(it: EditorItem): number | null {
  if (!props.feoPerItem) return props.defaultFeoCategoryId ?? null
  return it.feo_node_id ?? it.feo_category_id ?? null
}

// Кандидаты — непустое наименование, ещё нет привязки к плановой позиции (Ур.5).
const _unlinkedCandidates = computed(() =>
  localItems.value
    .map((it, idx) => ({ it, idx }))
    .filter(({ it }) => (it.item_name || '').trim() && it.feo_planned_item_id == null)
)

// Владелец 2026-08-18: «У меня в закупке имеются позиции, не привязанные к
// плановым. Это косяк, об этом надо сообщать!» — те же строки, что и
// _unlinkedCandidates (непустое имя, feo_planned_item_id == null), НО без
// over_plan=true: такие позиции сознательно заведены сверх плана (согласуется
// отдельно, см. EditorItem.over_plan / F-PLAN2) и привязки к плановой позиции
// не требуют — не считаем их «косяком». Гейт по subsidyId: без субсидии у
// закупки нет плана вовсе, предупреждение всегда было бы включено — бесполезный шум.
const itemsMissingPlan = computed(() => {
  if (props.itemShape !== 'purchase' || !props.subsidyId) return []
  return _unlinkedCandidates.value.filter(({ it }) => !it.over_plan).map(({ it }) => it)
})

function _pluralRu(n: number, [one, few, many]: [string, string, string]): string {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return one
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few
  return many
}

const itemsMissingPlanWord = computed(() => _pluralRu(itemsMissingPlan.value.length, ['позиция', 'позиции', 'позиций']))

const itemsMissingPlanSummary = computed(() => {
  const names = itemsMissingPlan.value.map(it => (it.item_name || '').trim() || '—')
  const shown = names.slice(0, 3)
  const restCount = names.length - shown.length
  return shown.join(', ') + (restCount > 0 ? ` и ещё ${restCount}` : '')
})

const needPlanRows = computed((): PlanCreateRow[] =>
  _unlinkedCandidates.value
    .map(({ it, idx }) => {
      const categoryId = _effectiveFeoCategoryId(it)
      if (categoryId == null) return null
      const categoryName = feoNodes.value.find(n => n.id === categoryId)?.name ?? `#${categoryId}`
      const name = (it.item_name || '').trim()
      // Дефект 2 (владелец, 2026-08-20): ЧЕСТНОЕ предупреждение — в этой категории уже
      // есть плановая позиция с таким же именем. Информационное, НЕ дедуп: runCreatePlannedBulk
      // ниже больше не привязывает к ней и не пропускает создание — каждая строка получает
      // свою отдельную плановую позицию (allow_duplicate_name), одноимённые не объединяются.
      const dup = (effectivePlannedItems.value || []).find(p =>
        p.kind === 'planned_item'
        && p.category_id === categoryId
        && _normalizePlanName(p.name) === _normalizePlanName(name)
      )
      return {
        idx,
        uid: it._uid ?? idx,
        name,
        quantity: it.quantity ?? null,
        unit: it.unit || '',
        amount: it.total_price ?? null,
        categoryId,
        categoryName,
        duplicateOf: dup ? { id: dup.id, name: dup.name } : null,
      } as PlanCreateRow
    })
    .filter((r): r is PlanCreateRow => r != null)
)

const needPlanCount = computed(() => needPlanRows.value.length)

const noCategoryCount = computed(() =>
  _unlinkedCandidates.value.filter(({ it }) => _effectiveFeoCategoryId(it) == null).length
)

// Дефект 2 (владелец, 2026-08-20): пункт 3 задачи — кнопка «Создать в плане закупок»
// заблокирована, пока хоть у одной непривязанной позиции нет конечной категории ФЭО
// (иначе клик по кнопке частично создаёт план и молча пропускает остальное — путаница).
// Список нужен и для тултипа-объяснения, и для перехода/подсветки первой строки.
const itemsMissingCategoryForPlan = computed(() =>
  _unlinkedCandidates.value
    .filter(({ it }) => _effectiveFeoCategoryId(it) == null)
    .map(({ it, idx }) => ({ idx, uid: it._uid ?? idx, name: (it.item_name || '').trim() || 'без названия' }))
)

const createPlannedBulkDialog = ref(false)
const createPlannedBulkLoading = ref(false)
const createPlannedBulkProgress = reactive({ done: 0, total: 0 })
const createPlannedBulkFailures = ref<string[]>([])

function openCreatePlannedBulkDialog() {
  createPlannedBulkFailures.value = []
  createPlannedBulkProgress.done = 0
  createPlannedBulkProgress.total = 0
  createPlannedBulkDialog.value = true
}

function closeCreatePlannedBulkDialog() {
  if (createPlannedBulkLoading.value) return
  createPlannedBulkDialog.value = false
}

// Дефект 2, п.3 (владелец, 2026-08-20): клик по заблокированной кнопке «Создать в плане
// закупок» не молчит — прокручивает к первой позиции без категории ФЭО и подсвечивает её
// строку (тот же приём, что highlightMissingFeoCategory/highlightMissingDateItems в
// WishesView.vue: pulse-класс + scrollIntoView, только здесь без общего arrow-оверлея —
// компонент переиспользуется вне WishesView, ссылаться на её рефы нельзя). item-row-*
// id проставлен на строку/карточку каждой позиции в ItemsTableFlat/ItemsCardsView/
// ItemsTableStages (см. соответствующие файлы).
function highlightMissingCategoryForPlan() {
  const first = itemsMissingCategoryForPlan.value[0]
  if (!first) return
  const el = document.getElementById(`item-row-${first.uid}`)
  if (!el) return
  el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  el.classList.add('plan-bulk-row-pulse')
  setTimeout(() => el.classList.remove('plan-bulk-row-pulse'), 3000)
}

// Дедуп — строго точное совпадение имени после нормализации (trim + схлопывание
// пробелов + lower), НИКАКОГО fuzzy (правило проекта — fuzzy ложно сливал разные
// SKU, см. Lessons: feedback_dedup_exact_only).
function _normalizePlanName(s: string | null | undefined): string {
  return (s || '').trim().replace(/\s+/g, ' ').toLowerCase()
}

// Дефект 2 (владелец, 2026-08-20): решение владельца — «каждой строке своя отдельная
// плановая позиция, одноимённые НЕ объединять». Раньше здесь был дедуп (внутри прогона
// И против props.plannedItems) — 2 позиции заявки с одинаковым названием («Футболка
// поло», 10 шт и 15 шт с разной печатью) схлопывались в одну плановую и роняли остаток
// плана. Теперь КАЖДАЯ строка — отдельный POST с allow_duplicate_name:true (backend
// feo_planned_items.py::create_planned_item, тот же флаг, что снимает интерактивный
// 409 planned_item_duplicate_name у одиночного создания) — дедуп по имени внутри
// категории сознательно пропускается, needPlanRows.duplicateOf выше только предупреждает
// об этом в предпросмотре, не меняя поведение.
async function runCreatePlannedBulk() {
  const rows = needPlanRows.value
  if (!rows.length) return
  createPlannedBulkLoading.value = true
  createPlannedBulkFailures.value = []
  createPlannedBulkProgress.done = 0
  createPlannedBulkProgress.total = rows.length
  let anyChanged = false
  for (const row of rows) {
    const item = localItems.value[row.idx]
    if (!item) { createPlannedBulkProgress.done += 1; continue }
    try {
      const created = await apiFetch<{ id: number }>('/feo-planned-items/', {
        method: 'POST',
        body: JSON.stringify({
          feo_category_id: row.categoryId,
          name: row.name,
          quantity: row.quantity,
          unit: row.unit || null,
          amount: row.amount,
          allow_duplicate_name: true,
        }),
      })
      item.feo_planned_item_id = created.id
      item.over_plan = false
      anyChanged = true
    } catch (e: any) {
      const status = e?.status
      const msg = e?.payload?.message || e?.message || 'неизвестная ошибка'
      createPlannedBulkFailures.value.push(`«${row.name}»${status ? ` (HTTP ${status})` : ''}: ${msg}`)
    } finally {
      createPlannedBulkProgress.done += 1
    }
  }
  if (anyChanged) {
    emitUpdate()
    emit('planned-item-created')
  }
  createPlannedBulkLoading.value = false
  const failCount = createPlannedBulkFailures.value.length
  // Дефект 2, п.4 (владелец): ОДИН тост на весь прогон, не по одному на позицию.
  if (failCount === 0) {
    createPlannedBulkDialog.value = false
    showSnack(`Плановые позиции созданы: ${rows.length}`)
  } else {
    showSnack(
      `Готово ${rows.length - failCount} из ${rows.length}. Не удалось: ${createPlannedBulkFailures.value.join('; ')}`,
      'error'
    )
    // Диалог не закрываем — пусть видно, что не получилось; успевшие позиции уже привязаны.
  }
}

async function pickUnallocatedForItem(idx: number, parentId: number | null) {
  if (!props.subsidyId) return
  try {
    const body: Record<string, unknown> = { subsidy_id: props.subsidyId }
    if (parentId != null) body.parent_id = parentId
    const cat = await apiFetch<{ id: number; name: string; parent_id: number | null }>('/feo-categories/unallocated', {
      method: 'POST',
      body: JSON.stringify(body),
    })
    _injectUnallocatedNode(cat)
    _propagateToSelected(idx, it => {
      it.feo_node_id = cat.id
      it.feo_category_id = cat.id
    })
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.message || 'Ошибка получения категории «Не определена»', 'error')
  }
}

/**
 * Добавляет новый узел «Не определена» в feoNodes, если его там ещё нет.
 * Если у узла есть parent_id — помечает родителя not-leaf (у него появился ребёнок).
 */
function _injectUnallocatedNode(cat: { id: number; name: string; parent_id?: number | null }) {
  const existing = feoNodes.value.find(n => n.id === cat.id)
  if (!existing) {
    const parentNode = cat.parent_id != null ? feoNodes.value.find(n => n.id === cat.parent_id) : null
    const newNode = { id: cat.id, name: cat.name, parent_id: cat.parent_id ?? null, level: parentNode ? parentNode.level + 1 : 1, is_leaf: true } as any
    const updated = [...feoNodes.value, newNode]
    // Если у нового узла есть родитель — снимаем с него is_leaf
    if (cat.parent_id != null) {
      const parentIdx = updated.findIndex(n => n.id === cat.parent_id)
      if (parentIdx !== -1) updated[parentIdx] = { ...updated[parentIdx], is_leaf: false }
    }
    feoNodes.value = updated
  }
}

// Inline-пропагация на выбранные: при мультивыборе изменение ФЭО/Тип в одной
// позиции применяется ко всем выбранным. Если строка не входит в выделение
// (или выделена одна) — меняется только она.
function _propagateToSelected(idx: number, apply: (it: any) => void) {
  const sel = selectedItemIdxs.value
  const targets = sel.length > 1 && sel.includes(idx) ? sel : [idx]
  for (const i of targets) {
    const it = localItems.value[i]
    if (it) apply(it)
  }
  emitUpdate()
}

function onItemFeoChange(idx: number, nodeId: number | null) {
  // FeoCascadeSelect эмитит выбранный УЗЕЛ на каждом уровне (а не только лист).
  // feo_node_id — позиция каскада (любой узел); пропагируем её на все выбранные
  // строки, чтобы смена ЛЮБОГО уровня в одной позиции отражалась во всех сразу.
  // feo_category_id (сохраняемый лист) выставляем только когда узел — лист.
  const isLeaf = nodeId != null && (feoNodes.value.find(n => n.id === nodeId)?.is_leaf ?? false)
  const newCategoryId = isLeaf ? nodeId : null
  _propagateToSelected(idx, it => {
    // F-PLAN: смена категории ФЭО делает привязанную плановую позицию (Ур.5)
    // невалидной — она принадлежит другой категории и «расходовала» бы её план.
    // Сбрасываем feo_planned_item_id, если он ссылается на позицию из старой категории.
    // ⚠️ id-коллизия: feo_planned_item_id живёт в пространстве id FeoPlannedItem —
    // сравнивать только со строками kind='planned_item', иначе можно случайно
    // «попасть» в id категории (kind='plan_position'/'feo_article') с тем же числом.
    if (it.feo_planned_item_id != null) {
      const plannedCategoryId = (props.plannedItems || [])
        .find(p => p.kind === 'planned_item' && p.id === it.feo_planned_item_id)?.category_id
      if (plannedCategoryId !== newCategoryId) it.feo_planned_item_id = null
    }
    it.feo_node_id = nodeId
    it.feo_category_id = newCategoryId
  })
}

// F-PLAN2: производный выбор для FeoPlannedItemsSelect по фактическим полям позиции —
// { kind:'planned_item', id: feo_planned_item_id } если задан; иначе, если категория
// позиции сама является плановой позицией/статьёй ФЭО с планом (kind='plan_position'
// | 'feo_article'), — её собственный ключ; иначе null.
function plannedSelectionFor(item: EditorItem): FeoPlanSelection | null {
  if (item.feo_planned_item_id != null) return { kind: 'planned_item', id: item.feo_planned_item_id }
  if (item.feo_category_id != null) {
    const row = (props.plannedItems || [])
      .find(p => p.category_id === item.feo_category_id && (p.kind === 'plan_position' || p.kind === 'feo_article'))
    if (row) return { kind: row.kind, id: item.feo_category_id }
  }
  return null
}

// Жалоба владельца (сессия 2026-08-19): «включаю переключатель — должно стать выбрано
// 1 500, остаток 0... а сейчас включаю-выключаю, там по-прежнему план 1 500, выбрано 0».
// row.consumed/row.residual в FeoPlanPosition приходят С СЕРВЕРА
// (/feo-categories/plan-positions, exclude_purchase_id — своя закупка НЕ учтена, это
// осознанно и трогать НЕЛЬЗЯ, см. комментарий в useFeoPlannedResiduals.ts), но выбор,
// сделанный ПРЯМО СЕЙЧАС в этой форме (переключатель включён/выключен на строке),
// в них не отражён вовсе — карта ниже суммирует «занято сейчас в этой форме» по
// каждой плановой позиции и передаётся в FeoPlannedItemsSelect (проп
// pendingByPlannedItem), который добавляет её поверх серверных чисел. Строки с
// over_plan===true НЕ считаем — они сознательно сверх плана и не расходуют его (тот
// же признак, что и в pendingByPlannedItem-соседях: plannedSelectionFor/EditorItem.
// over_plan). Сумма строки — total_price, тот же источник, что и totalNmck/прочие
// суммы в этом файле. Реактивность: computed от localItems — переключение
// switch(row) меняет it.feo_planned_item_id внутри localItems (см. item-planned-change
// хендлеры ниже), карта пересчитывается сама.
const pendingByPlannedItem = computed((): Record<number, number> => {
  const map: Record<number, number> = {}
  for (const it of localItems.value) {
    const pid = (it as any).feo_planned_item_id
    if (pid == null) continue
    if ((it as any).over_plan === true) continue
    map[pid] = (map[pid] || 0) + Number((it as any).total_price || 0)
  }
  return map
})

// Расшифровка «Кто расходует план» (владелец, 2026-08-20): диалог
// FeoPlannedItemsSelect.vue::openConsumers должен показать, ЧТО именно даёт число
// pendingByPlannedItem, а не только саму сумму — иначе «выбрано Y» в строке списка
// нечем объяснить (боевой случай: 14 футболок, план 15 793,40, «выбрано 11 281» —
// потому что на ту же плановую позицию ссылается ЕЩЁ ОДНА строка ЭТОЙ ЖЕ формы на
// 10 шт, ещё не сохранённая на сервер). Та же фильтрация (pid != null, !over_plan),
// но список позиций {name, quantity, unit, amount} вместо суммы.
const pendingItemsByPlannedItem = computed((): Record<number, { name: string; quantity: number | null; unit: string | null; amount: number }[]> => {
  const map: Record<number, { name: string; quantity: number | null; unit: string | null; amount: number }[]> = {}
  for (const it of localItems.value) {
    const pid = (it as any).feo_planned_item_id
    if (pid == null) continue
    if ((it as any).over_plan === true) continue
    if (!map[pid]) map[pid] = []
    map[pid].push({
      name: (it as any).item_name || 'без названия',
      quantity: (it as any).quantity ?? null,
      unit: (it as any).unit ?? null,
      amount: Number((it as any).total_price || 0),
    })
  }
  return map
})

// Шаг 5 «ТЗ не дороже и не больше плана» (владелец, 2026-08-07, план
// zany-fluttering-mountain.md): фронт-зеркало backend-гейта
// assert_tz_not_over_plan (app/services/feo_plan.py) — подсвечивает
// превышение ДО отправки, чтобы 409 не был первым, что видит пользователь.
// Источник плана — та же строка, что выбрана для FeoPlannedItemsSelect
// (plannedSelectionFor): planned_quantity / unit_price (цена за единицу) /
// planned_amount (итоговая плановая сумма) — те же поля, что читает бэкенд
// из FeoPlannedItem.quantity/amount либо FeoCategory.planned_quantity/
// planned_amount (см. FeoPlanPosition в useFeoPlannedResiduals.ts).
// Фолбэк для МИГРИРОВАННЫХ категорий-листьев (2026-08-12, зеркалит backend-фолбэк
// в assert_tz_not_over_plan / app/services/feo_plan.py): план переехал из
// planned_quantity/planned_amount самой категории в отдельные плановые позиции
// (kind='planned_item') внутри неё. У такой категории оба поля плана категории
// = null, поэтому /feo-categories/plan-positions НЕ эмитит для неё строку
// 'plan_position'/'feo_article', plannedSelectionFor(item) возвращает null
// (строки для выбора нет), и без этого фолбэка planForItem/planExcessFor тоже
// всегда возвращали null — предупреждение «ТЗ превышает план» тихо переставало
// работать. Складываем ровно те поля, которые читает planExcessFor
// (planned_quantity / unit_price / planned_amount) плюс остальные, требуемые
// типом FeoPlanPosition, из активных 'planned_item' той же категории: сумма
// плана Σ planned_amount, количество Σ planned_quantity, цена за единицу =
// сумма/количество при количестве > 0.
function plannedAggregateForCategory(categoryId: number): FeoPlanPosition | null {
  const rows = (props.plannedItems || []).filter(
    p => p.kind === 'planned_item' && p.category_id === categoryId
  )
  if (!rows.length) return null
  const plannedAmount = rows.reduce((s, r) => s + (r.planned_amount ?? 0), 0)
  const consumed = rows.reduce((s, r) => s + (r.consumed ?? 0), 0)
  const consumedQty = rows.reduce((s, r) => s + (r.consumed_quantity ?? 0), 0)
  const residual = rows.reduce((s, r) => s + (r.residual ?? 0), 0)
  const residualQty = rows.reduce((s, r) => s + (r.residual_quantity ?? 0), 0)
  return {
    id: categoryId,
    name: rows[0].name,
    path: rows[0].path,
    category_id: categoryId,
    kind: 'plan_position',
    // Владелец (2026-08-26, заявка №45/Минтруд_2026): этот агрегат складывает
    // НЕСВЯЗАННЫЕ FeoPlannedItem внутри статьи (разные товары/цены/единицы) —
    // planned_quantity/unit_price делением суммы на суммарное количество были бы
    // ВЫДУМАННОЙ величиной (баг «план: 98 000,01 ₽» — цена, которой не существует,
    // «Ты самостоятельно неправильно вычислил стоимость за единицу продукции путём
    // деления уже запланированного на количество»). planned_amount — РЕАЛЬНАЯ сумма
    // (Σ planned_amount уже существующих плановых позиций статьи), её оставляем и
    // подписываем «Уже запланировано по статье» (см. categoryResidualFor ниже и
    // ItemsTableFlat.vue/ItemsTableStages.vue/ItemsCardsView.vue). planned_quantity/
    // unit_price = null убирают выдуманные подписи «план: N шт»/«план: N ₽» под
    // количеством/ценой ЭТОГО фолбэка (guard `!= null` в шаблонах таблиц) — то, что
    // не задано по-настоящему, не показываем.
    planned_quantity: null,
    unit: rows[0].unit,
    planned_amount: plannedAmount,
    unit_price: null,
    consumed,
    consumed_quantity: consumedQty,
    residual,
    residual_quantity: residualQty,
    key: `plan_position:${categoryId}`,
  }
}

// Владелец (2026-08-26): «Остаток на статье» под суммой позиции — ТОЛЬКО когда
// planForItem вернулся из фолбэка plannedAggregateForCategory (нет ни конкретной
// выбранной плановой позиции, ни собственной строки категории 'plan_position'/
// 'feo_article' с сервера — см. planForItem выше). Для настоящей плановой позиции
// (kind='planned_item' выбран построчно) старые подписи/проверка превышения не
// трогаются (регресс запрещён владельцем).
//
// «Финансирование по ФЭО» статьи — поле FeoCategory.budget, уже загруженное для
// формы через useFeoLeaves (см. feoLeaves ниже, GET /feo-categories/leaves,
// budget = «собственная (ручная) сумма финансирования узла», единственное
// доступное на клиенте число для этого понятия — ответ /feo-categories/plan-positions
// его не отдаёт вовсе, там только planned_quantity/planned_amount конечных
// категорий и Ур.5 FeoPlannedItem). Если категория не входит в feoLeaves (например,
// план стоит не на листе, а на направлении/подкатегории) — feoBudget = null,
// остаток статьи не считаем (не выдумываем число).
interface CategoryResidualInfo {
  /** true — у текущего пользователя есть feo_budget.view_leaf, ниже заполнены
   *  «занято»/финансирование/остаток. false — их НЕЛЬЗЯ показывать (владелец,
   *  2026-09-03: «обычному пользователю не надо знать, сколько денег осталось в
   *  организации»); заполнено только excessAmount, из него одного бюджет не
   *  вычислить. */
  canViewBudget: boolean
  /** «Занято по статье» (владелец, сессия 2026-08-31) = Σ planned_amount плановых
   *  позиций статьи + unlinkedActual (см. ниже). Раньше — только плановые позиции;
   *  переименовано вслед за подписью «Уже запланировано по статье» → «Занято по статье»,
   *  т.к. теперь включает и непривязанные фактические позиции. null, если canViewBudget=false. */
  alreadyPlanned: number | null
  /** Из alreadyPlanned выше — часть, НЕ привязанная ни к одной плановой позиции
   *  (backend unlinked_actual_amount: позиции закупок статьи с feo_planned_item_id
   *  IS NULL, из плана закупок и дальше). Показывается отдельной строкой, только
   *  когда > 0 — владелец: «на это необходимо указывать» (стоит привязать к плану).
   *  null, если canViewBudget=false. */
  unlinkedActual: number | null
  /** FeoCategory.budget («финансирование по ФЭО») либо null, если для категории его
   *  нет ИЛИ canViewBudget=false. */
  feoBudget: number | null
  /** feoBudget − alreadyPlanned, либо null если feoBudget неизвестен. */
  residualBeforeItem: number | null
  /** feoBudget − alreadyPlanned − сумма ЭТОЙ позиции, либо null если feoBudget неизвестен. */
  residualWithItem: number | null
  /** true — у позиции уже введена (посчитана) ненулевая сумма. */
  hasItemTotal: boolean
  /** Размер превышения СТАТЬИ ЭТОЙ КОНКРЕТНОЙ ПОЗИЦИЕЙ (не состояние статьи целиком!) —
   *  заполнен ТОЛЬКО когда canViewBudget=false. Владелец (2026-09-03, повторно):
   *  «пользователь без права видит текущее состояние статьи, без прав видит только
   *  на сколько превысило статью его хотелка» — раньше здесь лежал сырой
   *  props.feoExcessAmount (перебор ВСЕЙ статьи, чужой вклад включительно), одна и
   *  та же цифра показывалась на КАЖДОЙ позиции, попавшей в эту категорию, — утечка
   *  состояния статьи. Теперь — min(сумма_этой_позиции, props.feoExcessAmount):
   *  если статья была перебрана ещё ДО этой позиции хотя бы на её сумму — показана
   *  вся сумма позиции («она целиком не поместилась»); если статья была перебрана
   *  меньше — показана только непоместившаяся часть; если перебора не было вовсе
   *  (или он весь пришёлся на других) — excessAmount=null, строка не рисуется.
   *  Источник сырого числа — props.feoExcessAmount/feoExcessCategoryId (канал
   *  app.routers.purchases._compute_purchase_feo_excess, НЕ гейтится правом
   *  feo_budget.view_leaf — превышение категории само по себе не бюджетная цифра,
   *  что и позволяет клиповать его на фронте суммой позиции без похода на бэкенд).
   *  ⚠️ Неизбежное следствие (озвучено владельцем): когда позиция ПОМЕСТИЛАСЬ НЕ
   *  ЦЕЛИКОМ (excessAmount < сумма позиции), пользователь МОЖЕТ обратным счётом
   *  получить «свободно было = сумма позиции − excessAmount» — это цена самого
   *  требования «показать, на сколько вылезла позиция», а не отдельная дыра;
   *  когда позиция не превышает статью, excessAmount=null и никакого числа не
   *  утекает вовсе. null — превышения (для этой позиции) нет либо данных о нём
   *  нет (напр. форма заявки без покупки, WishesView.vue). */
  excessAmount: number | null
}

function categoryResidualFor(item: EditorItem): CategoryResidualInfo | null {
  if (item.feo_planned_item_id != null) return null
  if (item.feo_category_id == null) return null
  const sel = plannedSelectionFor(item)
  if (sel) {
    const row = (props.plannedItems || []).find(p => p.key === `${sel.kind}:${sel.id}`)
    if (row) return null // настоящая строка категории 'plan_position'/'feo_article' с сервера — старые подписи
  }
  const agg = plannedAggregateForCategory(item.feo_category_id)
  if (!agg) return null
  const itemTotal = Number(item.total_price) || 0
  const hasItemTotal = itemTotal > 0

  if (!canViewLeafBudget.value) {
    // Владелец (2026-09-03, повторно — «ты еунля, с чего пользователь без права
    // видит текущее состояние статьи, без прав видит только на сколько превысило
    // статью его хотелка»): без feo_budget.view_leaf нельзя показывать ни «занято»,
    // ни состояние статьи целиком — ТОЛЬКО то, на сколько СВОЯ сумма ЭТОЙ позиции
    // не поместилась в статью. Сырой перебор статьи (props.feoExcessAmount, из
    // независимого от права канала — см. CategoryResidualInfo.excessAmount выше)
    // клипуется суммой позиции: min(itemTotal, rawExcess). Пустая позиция (сумма
    // 0) строки не даёт вовсе.
    const rawExcess =
      props.feoExcessCategoryId != null && props.feoExcessCategoryId === item.feo_category_id
        ? props.feoExcessAmount ?? null
        : null
    const excessAmount =
      rawExcess != null && rawExcess > 0.005 && hasItemTotal ? Math.min(itemTotal, rawExcess) : null
    if (excessAmount == null || excessAmount <= 0.005) return null
    return {
      canViewBudget: false,
      alreadyPlanned: null,
      unlinkedActual: null,
      feoBudget: null,
      residualBeforeItem: null,
      residualWithItem: null,
      hasItemTotal,
      excessAmount,
    }
  }

  // unlinked_actual_amount — свойство КАТЕГОРИИ целиком (не отдельной плановой позиции),
  // бэкенд повторяет одно и то же число на каждой строке /plan-positions этой категории —
  // берём с любой одной строки (первая, попавшаяся в agg.category_id), а НЕ суммируем по
  // всем 'planned_item' строкам категории (иначе задвоили бы его столько раз, сколько
  // плановых позиций в статье — см. комментарий у поля в useFeoPlannedResiduals.ts).
  const unlinkedRow = (props.plannedItems || []).find(p => p.category_id === item.feo_category_id)
  const unlinkedActual = unlinkedRow?.unlinked_actual_amount ?? 0
  const alreadyPlanned = (agg.planned_amount ?? 0) + unlinkedActual
  const feoBudget = feoLeaves.value.find(l => l.id === item.feo_category_id)?.budget ?? null
  const residualBeforeItem = feoBudget != null ? feoBudget - alreadyPlanned : null
  const residualWithItem = residualBeforeItem != null ? residualBeforeItem - itemTotal : null
  return {
    canViewBudget: true,
    alreadyPlanned, unlinkedActual, feoBudget, residualBeforeItem, residualWithItem,
    hasItemTotal, excessAmount: null,
  }
}

function planForItem(item: EditorItem): FeoPlanPosition | null {
  const sel = plannedSelectionFor(item)
  if (sel) {
    const row = (props.plannedItems || []).find(p => p.key === `${sel.kind}:${sel.id}`)
    if (row) return row
  }
  // sel === null (нет агрегатной строки категории) ИЛИ позиция не привязана к
  // конкретной plannedItem (feo_planned_item_id не задан) — пробуем агрегат
  // по 'planned_item' той же категории (см. plannedAggregateForCategory выше).
  if (item.feo_planned_item_id == null && item.feo_category_id != null) {
    return plannedAggregateForCategory(item.feo_category_id)
  }
  return null
}

interface TzPlanExcess {
  plan: FeoPlanPosition
  qtyOver: boolean
  priceOver: boolean
  totalOver: boolean
}

function planExcessFor(item: EditorItem): TzPlanExcess | null {
  // over_plan=true — позиция сознательно сверх плана (согласуется отдельно,
  // через превышение ФЭО категории) — не подсвечиваем как нарушение.
  if (item.over_plan) return null
  const plan = planForItem(item)
  if (!plan) return null
  const qty = Number(item.quantity) || 0
  const price = Number(item.unit_price) || 0
  const total = item.total_price != null ? Number(item.total_price) : qty * price
  // Владелец (2026-09-02, «Логистические услуги»): для kind='planned_item' без
  // unit_price количество ОРИЕНТИРОВОЧНОЕ и НЕ ограничивает закупку (см.
  // assert_tz_not_over_plan / feo_plan.py — planned_qty там сознательно остаётся
  // None в этой ветке). У 'plan_position'/'feo_article' (FeoCategory) такой
  // семантики нет — там planned_quantity всегда жёсткий предел. Без этого условия
  // фронт подсвечивал бы «превышение по количеству», которого бэкенд не блокирует —
  // тот же класс бага, что был с ценой за единицу.
  const qtyLimited = plan.kind !== 'planned_item' || plan.unit_price != null
  const qtyOver = qtyLimited && plan.planned_quantity != null && qty > plan.planned_quantity
  const priceOver = plan.unit_price != null && price > plan.unit_price
  const totalOver = plan.planned_amount != null && total > plan.planned_amount
  if (!qtyOver && !priceOver && !totalOver) return null
  return { plan, qtyOver, priceOver, totalOver }
}

function onItemPlannedChange(idx: number, val: FeoPlanSelection | null) {
  _propagateToSelected(idx, it => {
    if (!val) {
      it.feo_planned_item_id = null
      return
    }
    if (val.kind === 'planned_item') {
      it.feo_planned_item_id = val.id
      it.over_plan = false
    } else {
      it.feo_planned_item_id = null
      it.feo_category_id = val.id
      it.over_plan = false
    }
  })
}

function onItemTypeChange(idx: number, val: string) {
  _propagateToSelected(idx, it => { it.item_type = val })
}

// import-no-clutter: bulk-add несвязанных позиций в каталог
const hasUncatalogedSelected = computed(() =>
  selectedItemIdxs.value.some(idx => !localItems.value[idx]?.product_id)
)
const uncatalogedSelectedCount = computed(() =>
  selectedItemIdxs.value.filter(idx => !localItems.value[idx]?.product_id).length
)

async function bulkAddToCatalog() {
  const uncatItems = selectedItemIdxs.value
    .map(idx => localItems.value[idx])
    .filter(it => it && !it.product_id && it.id)  // только сохранённые в БД (имеют id)
  if (!uncatItems.length) {
    showSnack('Выберите сохранённые позиции без привязки к каталогу', 'warning')
    return
  }
  bulkAddCatalogLoading.value = true
  try {
    const res = await apiFetch<{ created: number; linked: number; errors: string[] }>(
      '/products/bulk-from-purchase-items',
      { method: 'POST', body: JSON.stringify({ purchase_item_ids: uncatItems.map(it => it.id) }) }
    )
    showSnack(`Добавлено в каталог: ${res.created + res.linked}`, 'success')
    emit('reload-requested')
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.message || 'Ошибка добавления в каталог', 'error')
  } finally {
    bulkAddCatalogLoading.value = false
  }
}

// ── Product selection ────────────────────────────────────────────────────────

const productFilter = (_value: string, query: string, item?: any): boolean => {
  if (!query.trim()) return true
  const q = query.toLowerCase().trim()
  const name = (item?.raw?.name || '').toLowerCase()
  const desc = (item?.raw?.description || '').toLowerCase()
  const type = (item?.raw?.product_type || '').toLowerCase()
  return name.includes(q) || desc.includes(q) || type.includes(q)
}

// Keep productFilter available but it's not used directly in this component's template
void productFilter

function productItemsFor(search?: string): Product[] {
  const q = (search || '').toLowerCase().trim()
  if (!q) return products.value
  return products.value.filter(p => {
    const name = (p.name || '').toLowerCase()
    const desc = (p.description || '').toLowerCase()
    const type = (p.product_type || '').toLowerCase()
    return name.includes(q) || desc.includes(q) || type.includes(q)
  })
}

const hasProducts = computed(() => products.value.length > 0)
void hasProducts

function onItemProductSelect(idx: number, val: any) {
  const item = localItems.value[idx]
  if (!val) {
    clearMatchBinding(item)
    item._description_44fz = undefined
    ;(item as any).match_confirmed = true
    emitUpdate()
    return
  }
  if (typeof val === 'string') {
    item.item_name = val
    item.product_id = null
    item._selectedProduct = val
    item._photo_url = undefined
    item._description = undefined
    item._description_44fz = undefined
    item._price_meta = null
    ;(item as any).match_confirmed = true
    emitUpdate()
    return
  }
  // Catalog Product object → apply via shared matching logic.
  applyMatchCandidate(item as any, {
    product_id: val.id,
    name: val.name || '',
    price: val.price ?? null,
    score: 1,
    description: val.description ?? null,
    photo_url: productPhotoSrc(val) ?? null,
    item_type: val.product_type ?? null,
    contract_price: val.contract_price ?? null,
    price_updated_at: val.price_updated_at ?? null,
    price_source: val.price_source ?? null,
    price_source_ref: val.price_source_ref ?? null,
    price_freshness: val.price_freshness ?? null,
  })
  item._description_44fz = val.description_44fz || undefined
  emitUpdate()
}

// ── BUG #5: inline per-row catalog matching ──────────────────────────────────
// InlineProductMatch emits a chosen candidate; apply it without opening a dialog.
function onInlineMatchPick(idx: number, candidate: MatchCandidate) {
  const item = localItems.value[idx]
  if (!item) return
  applyMatchCandidate(item as any, candidate)
  emitUpdate()
}

function onInlineMatchClear(idx: number) {
  clearItem(idx)
}

// Fall back to the full product dialog for "create new" from inline match.
function onInlineMatchCreateNew(idx: number) {
  const row = idx >= 0 ? localItems.value[idx] : null
  const prefillName = row?.item_name || ''
  const price = row && row.unit_price != null && Number(row.unit_price) > 0 ? Number(row.unit_price) : undefined
  openFullProduct(idx, prefillName, undefined, price)
}

// ── Product picker dialog ────────────────────────────────────────────────────

const productPickerDialog = ref(false)
const productPickerSearch = ref('')
const productPickerIdx = ref(-1)

const productPickerResults = computed(() => productItemsFor(productPickerSearch.value))

function openProductPicker(idx: number) {
  productPickerIdx.value = idx
  productPickerSearch.value = localItems.value[idx]?.item_name || ''
  productPickerDialog.value = true
}

function selectFromPicker(prod: Product) {
  productPickerDialog.value = false
  onItemProductSelect(productPickerIdx.value, prod)
}

function createProductFromPicker() {
  productPickerDialog.value = false
  const idx = productPickerIdx.value
  const row = idx >= 0 ? localItems.value[idx] : null
  const price = row && row.unit_price != null && Number(row.unit_price) > 0 ? Number(row.unit_price) : undefined
  openFullProduct(idx, productPickerSearch.value, undefined, price)
}

// ── Full product dialog ───────────────────────────────────────────────────────

const fullProductDialog = ref(false)
const fullProductSaving = ref(false)
const fullProductIdx = ref(-1)
const fullProductEditingId = ref<number | null>(null)
const fullProductPhotoFile = ref<File | null>(null)
const fullProductPhotoFileList = ref<File[]>([])
const fullProductPhotoPreview = ref<string | null>(null)
const fullProductForm = reactive({
  name: '' as string,
  category: '',
  product_type: '',
  item_kind: 'товар' as string,
  price: null as number | null,
  description: '',
  photo_url: '',
  photo_link: '',
  is_active: true,
  priceLinks: [] as PriceLink[],
})

const fullProductNameSearch = ref('')
const fullProductNameSuggestions = computed(() => {
  const q = (fullProductNameSearch.value || '').toLowerCase().trim()
  if (q.length < 2) return []
  return products.value
    .filter(p => p.name.toLowerCase().includes(q))
    .map(p => p.name)
    .slice(0, 15)
})

const isFullProductDuplicate = computed(() => {
  const q = (typeof fullProductForm.name === 'string' ? fullProductForm.name : '').toLowerCase().trim()
  if (!q) return false
  return products.value.some(p => p.name.toLowerCase().trim() === q)
})

const fullProductTypeOptions = computed(() => {
  const types = products.value.map(p => p.product_type).filter(Boolean) as string[]
  return [...new Set(types)].sort()
})

const fullProductCategoryOptions = computed(() => {
  const cats = products.value.map(p => p.category).filter(Boolean) as string[]
  return [...new Set(cats)].sort()
})

const fullAvgPrice = computed<number | null>(() => {
  const prices = fullProductForm.priceLinks
    .map(l => l.price)
    .filter((p): p is number => p !== null && !isNaN(Number(p)) && Number(p) > 0)
  if (!prices.length) return null
  return Math.round(prices.reduce((s, p) => s + p, 0) / prices.length * 100) / 100
})

watch(fullAvgPrice, v => { if (v !== null) fullProductForm.price = v })

function onFullPhotoFileChange(files: File[] | File | null) {
  const fileArr = Array.isArray(files) ? files : (files ? [files] : [])
  const f = fileArr[0] ?? null
  fullProductPhotoFile.value = f
  fullProductPhotoPreview.value = f ? URL.createObjectURL(f) : null
}

function resetFullProductForm(prefill?: string) {
  Object.assign(fullProductForm, {
    name: prefill || '',
    category: '',
    product_type: '',
    item_kind: 'товар',
    price: null,
    description: '',
    photo_url: '',
    photo_link: '',
    is_active: true,
    priceLinks: [],
  })
  fullProductPhotoFile.value = null
  fullProductPhotoFileList.value = []
  fullProductPhotoPreview.value = null
}

function openFullProduct(idx: number, prefill?: string, productId?: number | null, prefillPrice?: number) {
  fullProductIdx.value = idx
  fullProductEditingId.value = null
  resetFullProductForm(prefill)
  if (!productId && prefillPrice != null && Number.isFinite(prefillPrice) && prefillPrice > 0) {
    fullProductForm.price = prefillPrice
  }
  fullProductDialog.value = true

  if (productId) {
    // Try cache first, then refetch fresh data so any backend-only fields are loaded
    const cached = products.value.find(p => p.id === productId)
    if (cached) populateFullProductFromProduct(cached)
    apiFetch<Product>(`/products/${productId}`)
      .then(p => populateFullProductFromProduct(p))
      .catch(() => { /* keep cached/prefill values */ })
  }
}

function populateFullProductFromProduct(p: Product) {
  fullProductEditingId.value = p.id
  Object.assign(fullProductForm, {
    name: p.name || '',
    category: p.category || '',
    product_type: p.product_type || '',
    item_kind: (p as any).item_kind || 'товар',
    price: p.price != null ? Number(p.price) : null,
    description: p.description || '',
    photo_url: p.photo_url || '',
    photo_link: p.photo_link || '',
    is_active: (p as any).is_active !== false,
    priceLinks: Array.isArray((p as any).price_links)
      ? (p as any).price_links.map((l: any) => ({ url: l.url || '', price: l.price ?? null }))
      : [],
  })
  fullProductPhotoPreview.value = productPhotoSrc(p) || null
}

function openQuickProductEdit(item: EditorItem) {
  const idx = localItems.value.indexOf(item)
  const price = !item.product_id && item.unit_price != null && Number(item.unit_price) > 0 ? Number(item.unit_price) : undefined
  openFullProduct(idx, item.item_name, item.product_id || undefined, price)
}

async function saveFullProduct() {
  const nameStr = typeof fullProductForm.name === 'string' ? fullProductForm.name : (fullProductForm.name as any)?.name || ''
  if (!nameStr.trim()) return
  fullProductSaving.value = true
  try {
    const body: any = {
      name: nameStr,
      category: (fullProductForm.category || '').trim(),
      product_type: fullProductForm.product_type || null,
      item_kind: fullProductForm.item_kind || 'товар',
      price: fullAvgPrice.value ?? fullProductForm.price ?? null,
      description: fullProductForm.description || null,
      photo_link: fullProductForm.photo_link || null,
      is_active: fullProductForm.is_active,
      price_links: fullProductForm.priceLinks.filter(l => l.url),
    }
    const isEdit = fullProductEditingId.value != null
    let saved: Product
    if (isEdit) {
      saved = await apiFetch<Product>(`/products/${fullProductEditingId.value}`, { method: 'PUT', body })
    } else {
      try {
        saved = await apiFetch<Product>('/products/', { method: 'POST', body })
      } catch (err: any) {
        // Backend detected a near-duplicate name → ask the user.
        // FastAPI's HTTPException(detail={...}) is wrapped by api.ts: the original
        // dict ends up at err.payload.message (apiFetch puts parsed.detail there).
        const detail = err?.payload?.message
        const existing = (err?.status === 409 && typeof detail === 'object' && detail?.code === 'duplicate_product')
          ? detail.existing : null
        if (existing) {
          const msg = `Похожий товар уже есть в каталоге:\n«${existing.name}»\n\nИспользовать его (ОК) или всё равно создать новый (Отмена)?`
          if (confirm(msg)) {
            saved = existing
          } else {
            saved = await apiFetch<Product>('/products/?force=true', { method: 'POST', body })
          }
        } else {
          throw err
        }
      }
    }
    // Upload photo if selected (works for both create and edit)
    if (fullProductPhotoFile.value) {
      const fd = new FormData()
      fd.append('file', fullProductPhotoFile.value)
      const token = localStorage.getItem('auth_token')
      const res = await fetch(`/api/products/${saved.id}/photo`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: fd,
      })
      if (res.ok) Object.assign(saved, await res.json())
    }
    products.value = await apiFetch<Product[]>('/products/')
    if (fullProductIdx.value >= 0) {
      onItemProductSelect(fullProductIdx.value, saved)
      // 27.4-14: моментальная запись привязки в БД (без ожидания общего «Сохранить»),
      // иначе после F5 product_id вернётся в null.
      const linkItem = localItems.value[fullProductIdx.value]
      if (props.purchaseId && (linkItem as any)?.id && saved.id) {
        try {
          await apiFetch(`/purchases/${props.purchaseId}/items/${(linkItem as any).id}/set-product`,
            { method: 'POST', body: { product_id: saved.id } })
        } catch (e) { console.warn('Failed to persist product_id link', e) }
      }
    }
    emit('product-created', saved)
    showSnack(isEdit ? `Товар "${saved.name}" обновлён` : `Товар "${saved.name}" добавлен в каталог`)
    fullProductDialog.value = false
    fullProductPhotoFile.value = null
    fullProductPhotoFileList.value = []
    fullProductPhotoPreview.value = null
  } catch {
    showSnack('Ошибка при добавлении товара', 'error')
  } finally {
    fullProductSaving.value = false
  }
}

// ── Excel import ──────────────────────────────────────────────────────────────

const itemsImportDialog = ref(false)
const isSmartMode = ref(false)
const itemsImportFile = ref<File | null>(null)
const itemsImportLoading = ref(false)
const itemsImportResult = ref<Record<string, any> | null>(null)
const importStep = ref(1)
const importPreviewData = ref<any>(null)
const importSelectedSheet = ref('')
const dragMapping = ref<Record<string, number | null>>({})
const ignoredColumns = ref<number[]>([])
const dragOverTarget = ref<string | null>(null)
const importError = ref('')

const TARGET_FIELDS = [
  { value: 'item_name',     title: 'Наименование',    required: true },
  { value: 'unit_price',    title: 'Цена за ед.',     required: false },
  { value: 'quantity',      title: 'Количество',      required: false },
  { value: 'unit',          title: 'Ед. изм.',        required: false },
  { value: 'total_price',   title: 'Сумма',           required: false },
  { value: 'description',   title: 'Описание',        required: false },
  { value: 'row_num',       title: '№',               required: false, hint: 'Номер строки в исходном документе' },
  { value: 'vat_rate',      title: 'Ставка НДС',      required: false },
  { value: 'vat_amount',    title: 'Сумма НДС',       required: false },
  { value: 'total_with_vat', title: 'Стоимость с НДС', required: false },
  { value: 'category',      title: 'Категория товара', required: false, hint: 'Для группировки/фильтрации; при конфликте главнее категория из каталога' },
  { value: 'product_type',  title: 'Вид товара',      required: false, hint: 'Вид внутри категории; при конфликте главнее вид из каталога' },
]

const currentSheetData = computed(() => {
  if (!importPreviewData.value) return null
  const sheets = importPreviewData.value.sheets
  return sheets.find((s: any) => s.name === importSelectedSheet.value) || sheets[0]
})

const currentSheetHeaders = computed(() => currentSheetData.value?.headers || [])

const mappingHasName = computed(() =>
  dragMapping.value['item_name'] !== null && dragMapping.value['item_name'] !== undefined
)

function isMapped(idx: number): boolean {
  return Object.values(dragMapping.value).includes(idx)
}

function isIgnored(idx: number): boolean {
  return ignoredColumns.value.includes(idx)
}

function isTargetFilled(field: string): boolean {
  return dragMapping.value[field] !== null && dragMapping.value[field] !== undefined
}

function getColumnLabel(idx: number): string {
  return (currentSheetHeaders.value[idx] as string) || `Столбец ${idx + 1}`
}

const unmappedCount = computed(() =>
  currentSheetHeaders.value.filter((_: any, i: number) => !isMapped(i) && !isIgnored(i)).length
)

function getSamples(idx: number): string[] {
  const sample = currentSheetData.value?.sample || []
  return (sample as any[][]).slice(0, 1)
    .map((row: any[]) => String(row[idx] ?? '').trim())
    .filter(Boolean)
}

function onDragStart(idx: number, e: DragEvent) {
  e.dataTransfer!.effectAllowed = 'move'
  e.dataTransfer!.setData('text/plain', String(idx))
}

function onDropToTarget(field: string, e: DragEvent) {
  const idx = parseInt(e.dataTransfer!.getData('text/plain'))
  for (const f of Object.keys(dragMapping.value)) {
    if (dragMapping.value[f] === idx) dragMapping.value[f] = null
  }
  dragMapping.value[field] = idx
  dragOverTarget.value = null
}

function onDropToUnresolved(e: DragEvent) {
  const idx = parseInt(e.dataTransfer!.getData('text/plain'))
  for (const f of Object.keys(dragMapping.value)) {
    if (dragMapping.value[f] === idx) dragMapping.value[f] = null
  }
  dragOverTarget.value = null
}

function unmapTarget(field: string) {
  dragMapping.value[field] = null
}

function ignoreColumn(idx: number) {
  for (const f of Object.keys(dragMapping.value)) {
    if (dragMapping.value[f] === idx) dragMapping.value[f] = null
  }
  if (!ignoredColumns.value.includes(idx)) ignoredColumns.value.push(idx)
}

function autoDetectMapping(headers: string[]): Record<string, number | null> {
  const mapping: Record<string, number | null> = {}
  TARGET_FIELDS.forEach(f => { mapping[f.value] = null })

  // УПД numeric-label detection (Постановление Правительства РФ № 1137):
  // Если хедеры — это сабметки УПД '1а','1б','2','2а','3','4','5','9' — мапим позиционно.
  const normalizedHeaders = headers.map(h => h.trim().toLowerCase().replace(/\s/g, ''))
  const UPD_LABELS = ['1а', '1б', '2', '2а', '3', '4', '5', '9']
  const updMatches = UPD_LABELS.filter(l => normalizedHeaders.includes(l)).length
  if (updMatches >= 4) {
    const idx = (label: string) => normalizedHeaders.indexOf(label)
    if (idx('1б') >= 0) mapping.item_name = idx('1б')
    if (idx('3')  >= 0) mapping.quantity  = idx('3')
    if (idx('4')  >= 0) mapping.unit_price = idx('4')
    // Prefer "с налогом — всего" (col 9), fallback на "без налога" (col 5)
    if      (idx('9') >= 0) mapping.total_price = idx('9')
    else if (idx('5') >= 0) mapping.total_price = idx('5')
    if      (idx('2а') >= 0) mapping.unit = idx('2а')
    else if (idx('2')  >= 0) mapping.unit = idx('2')
    return mapping
  }

  // Keyword fallback. Учитываем УПД headers ("Наименование товара (описание выполненных работ...)",
  // "Цена (тариф) за единицу", "Стоимость... с налогом - всего") + общие случаи.
  const used = new Set<number>()

  // First pass: total_price priority — "с налогом" over plain "стоимость"
  for (let i = 0; i < headers.length; i++) {
    const h = headers[i].toLowerCase()
    if (h.includes('с налогом') && (h.includes('всего') || h.includes('итог'))) {
      mapping.total_price = i; used.add(i); break
    }
  }

  const keywords: Record<string, string[]> = {
    item_name:      ['наименован', 'назван', 'описание выполн', 'описание оказ', 'товара', 'товар', 'предмет', 'name', 'продукц', 'описан', 'маршрут', 'направлени', 'рейс', 'билет', 'услуга', 'работа'],
    description:    ['характерист', 'тз', 'спецификац', 'specification'],
    quantity:       ['кол-во', 'количеств', 'объем', 'qty', 'кол.', 'кол '],
    unit_price:     ['цена (тариф)', 'цена', 'price', 'за единиц', 'за ед', 'тариф', 'стоимость', 'сумма билет', 'цена билет'],
    total_price:    ['всего', 'сумм', 'итого', 'total', 'стоимость'],
    unit:           ['ед. изм', 'единиц', 'ед.изм', 'изм', 'unit', 'ед.'],
    row_num:        ['№', 'n', 'no', '#', 'пп', 'п/п'],
    vat_rate:       ['ставка ндс', 'налоговая ставка', '% ндс', 'ндс %', 'vat rate'],
    vat_amount:     ['сумма ндс', 'налог', 'vat amount'],
    total_with_vat: ['с ндс', 'с учётом ндс', 'с налогом всего', 'итого с ндс', 'total with vat', 'к оплате', 'сумма с налогом'],
    category:       ['категор', 'category'],
    product_type:   ['вид товара'],
  }
  for (const [field, kws] of Object.entries(keywords)) {
    if (mapping[field] !== null) continue  // already set (e.g. total_price by с налогом)
    for (let i = 0; i < headers.length; i++) {
      if (used.has(i)) continue
      const h = headers[i].toLowerCase()
      if (kws.some(kw => h.includes(kw))) {
        mapping[field] = i; used.add(i); break
      }
    }
  }
  return mapping
}

watch(importSelectedSheet, (newSheet) => {
  if (!importPreviewData.value) return
  const sheet = importPreviewData.value.sheets.find((s: any) => s.name === newSheet)
  if (sheet) {
    dragMapping.value = autoDetectMapping(sheet.headers)
    ignoredColumns.value = []
  }
})

function openImportDialog() {
  isSmartMode.value = false
  itemsImportDialog.value = true
}

function openSmartImportDialog() {
  isSmartMode.value = true
  smartImportPreview.value = null
  smartImportResult.value = null
  smartImportFile.value = null
  smartImportFileList.value = []
  itemsImportDialog.value = true
}

function switchImportMode(smart: boolean) {
  isSmartMode.value = smart
  // Reset state on mode switch
  smartImportFile.value = null
  smartImportFileList.value = []
  smartImportPreview.value = null
  smartImportColumns.value = null
  smartImportResult.value = null
  importStep.value = 1
  importPreviewData.value = null
  itemsImportFile.value = null
  importError.value = ''
  columnMappingApplied.value = false
}

function closeImportDialog() {
  itemsImportDialog.value = false
  importStep.value = 1
  itemsImportFile.value = null
  importPreviewData.value = null
  dragMapping.value = {}
  ignoredColumns.value = []
  itemsImportResult.value = null
  importError.value = ''
  isSmartMode.value = false
}

async function doImportPreview() {
  if (!itemsImportFile.value) return
  itemsImportLoading.value = true
  try {
    const token = localStorage.getItem('auth_token')
    const fd = new FormData()
    fd.append('file', itemsImportFile.value)
    const resp = await fetch('/api/purchases/items/import-preview', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` } as HeadersInit,
      body: fd,
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}))
      throw new Error(err.detail || `Ошибка ${resp.status}`)
    }
    const data = await resp.json()
    importPreviewData.value = data
    importSelectedSheet.value = data.sheets[0]?.name || ''
    dragMapping.value = autoDetectMapping(data.sheets[0]?.headers || [])
    ignoredColumns.value = []
    importStep.value = 2
  } catch (e: any) {
    showSnack(e.message || 'Ошибка чтения файла', 'error')
  } finally {
    itemsImportLoading.value = false
  }
}

function buildEditorItemFromRow(row: any[], mapping: Record<string, number | null>): EditorItem {
  function getVal(field: string): any {
    const idx = mapping[field]
    if (idx === null || idx === undefined) return null
    return row[idx] ?? null
  }
  const unitPrice = getVal('unit_price') !== null ? Number(getVal('unit_price')) : null
  const quantity = getVal('quantity') !== null ? Number(getVal('quantity')) : null
  const totalPrice = getVal('total_price') !== null
    ? Number(getVal('total_price'))
    : (unitPrice !== null && quantity !== null ? Math.round(unitPrice * quantity * 100) / 100 : null)

  const item: EditorItem = {
    product_id: null,
    item_name: String(getVal('item_name') ?? '').trim(),
    item_type: props.defaultItemType,
    quantity,
    unit: String(getVal('unit') ?? props.defaultUnit).trim() || props.defaultUnit,
    unit_price: unitPrice,
    total_price: totalPrice,
    country_origin: props.defaultCountry,
    _selectedProduct: null,
    _photo_url: undefined,
    _description: String(getVal('description') ?? '').trim() || undefined,
    _description_44fz: undefined,
  }
  if (props.itemShape === 'purchase') {
    item.final_unit_price = null
    item.final_total = null
    // F-PLAN: импортированные строки сразу наследуют шапочную плановую позицию
    item.feo_planned_item_id = props.defaultFeoPlannedItemId ?? null
  }
  return item
}

async function doMappedImport() {
  if (!itemsImportFile.value) return
  itemsImportLoading.value = true
  itemsImportResult.value = null
  importError.value = ''
  try {
    if (props.purchaseId) {
      // Purchase context — call pid-bound endpoint
      const token = localStorage.getItem('auth_token')
      const fd = new FormData()
      fd.append('file', itemsImportFile.value)
      const params = new URLSearchParams()
      if (importSelectedSheet.value) params.set('sheet_name', importSelectedSheet.value)
      const headerRowOffset = currentSheetData.value?.header_row_offset ?? 0
      if (headerRowOffset > 0) params.set('header_row_offset', String(headerRowOffset))
      const paramMap: Record<string, string> = {
        item_name:     'col_item_name',
        description:   'col_description',
        quantity:      'col_quantity',
        unit_price:    'col_unit_price',
        total_price:   'col_total_price',
        unit:          'col_unit',
        row_num:       'col_row_num',
        vat_rate:      'col_vat_rate',
        vat_amount:    'col_vat_amount',
        total_with_vat: 'col_total_with_vat',
        category:      'col_category',
        product_type:  'col_product_type',
      }
      for (const [field, colIdx] of Object.entries(dragMapping.value)) {
        if (colIdx !== null && colIdx !== undefined && paramMap[field]) {
          params.set(paramMap[field], String(colIdx))
        }
      }
      const resp = await fetch(`/api/purchases/${props.purchaseId}/items/import-mapped?${params}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` } as HeadersInit,
        body: fd,
      })
      if (!resp.ok) {
        const errText = await resp.text().catch(() => '')
        let detail = `Ошибка ${resp.status}`
        try { detail = JSON.parse(errText).detail || detail } catch { /* */ }
        throw new Error(detail)
      }
      const data = await resp.json()
      itemsImportResult.value = data
      importStep.value = 3
      if (data.added > 0) {
        showSnack(`Импортировано ${data.added} позиций`)
        emit('reload-requested')
      } else {
        importError.value = 'Не удалось импортировать ни одной позиции. Проверьте маппинг столбцов.'
        if (data.debug) {
          const d = data.debug
          showSnack(
            `Импортировано 0 позиций. Обработано строк: ${d.rows_processed}. ` +
            `Пустое наименование: ${d.skipped_empty_name}. ` +
            `Отброшено как «итого/подпись»: ${d.skipped_junk_row}. ` +
            `Первые строки данных: ${JSON.stringify(d.first_3_rows_sample)}`,
            'warning'
          )
        }
      }
    } else {
      // Wish / no-pid context — вызов backend import-mapped-nopid
      const sheet = importPreviewData.value?.sheets?.find((s: any) => s.name === importSelectedSheet.value)
        ?? importPreviewData.value?.sheets?.[0]
      if (!sheet) { showSnack('Нет данных превью', 'error'); return }
      const fdNoPid = new FormData()
      fdNoPid.append('file', itemsImportFile.value as File)
      const paramsNoPid = new URLSearchParams()
      if (importSelectedSheet.value) paramsNoPid.set('sheet_name', importSelectedSheet.value)
      const headerOffset = sheet.header_row_offset ?? 0
      if (headerOffset > 0) paramsNoPid.set('header_row_offset', String(headerOffset))
      const paramMapNoPid: Record<string, string> = {
        item_name:     'col_item_name',
        description:   'col_description',
        quantity:      'col_quantity',
        unit_price:    'col_unit_price',
        total_price:   'col_total_price',
        unit:          'col_unit',
        row_num:       'col_row_num',
        vat_rate:      'col_vat_rate',
        vat_amount:    'col_vat_amount',
        total_with_vat: 'col_total_with_vat',
        category:      'col_category',
        product_type:  'col_product_type',
      }
      for (const [field, colIdx] of Object.entries(dragMapping.value)) {
        if (colIdx !== null && colIdx !== undefined && paramMapNoPid[field]) {
          paramsNoPid.set(paramMapNoPid[field], String(colIdx))
        }
      }
      const token = localStorage.getItem('auth_token') || ''
      const respNoPid = await fetch(`/api/purchases/items/import-mapped-nopid?${paramsNoPid}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` } as HeadersInit,
        body: fdNoPid,
      })
      if (!respNoPid.ok) {
        const errText = await respNoPid.text().catch(() => '')
        let detail = `Ошибка ${respNoPid.status}`
        try { detail = JSON.parse(errText).detail || detail } catch { /* */ }
        throw new Error(detail)
      }
      const dataNoPid = await respNoPid.json()
      const backendItems: any[] = dataNoPid.items || []
      const newItems: EditorItem[] = backendItems.map((bi) => ({
        _uid: nextUid(),
        product_id: bi.product_id ?? null,
        item_name: bi.item_name || '',
        item_type: bi.item_type || 'товар',
        quantity: bi.quantity ?? 1,
        unit: bi.unit || 'шт',
        unit_price: bi.unit_price ?? 0,
        total_price: bi.total_price ?? 0,
        country_origin: 'РФ',
        _description: bi.description || '',
        _category: bi.category || '',
        _product_type: bi.product_type || '',
      } as EditorItem))
      localItems.value = [...localItems.value, ...newItems]
      emitUpdate()
      itemsImportResult.value = { imported: newItems.length, added: newItems.length }
      importStep.value = 3
      showSnack(`Добавлено позиций: ${newItems.length}`)
    }
  } catch (e: any) {
    importError.value = e?.message ?? 'Ошибка импорта'
    importStep.value = 3
    showSnack('Ошибка импорта', 'error')
  } finally {
    itemsImportLoading.value = false
  }
}

async function doImportAllTables() {
  if (!importPreviewData.value?.sheets?.length) return
  if (!props.purchaseId) {
    showSnack('Множественный импорт доступен только для существующей закупки', 'warning')
    return
  }
  itemsImportLoading.value = true
  let totalAdded = 0
  let totalErrors: any[] = []
  try {
    for (const sheet of importPreviewData.value.sheets) {
      const detected = autoDetectMapping(sheet.headers)
      // Skip tables where we couldn't find item_name column
      if (detected['item_name'] === null || detected['item_name'] === undefined) {
        totalErrors.push({ sheet: sheet.name, reason: 'не найден столбец Наименование' })
        continue
      }
      const params = new URLSearchParams()
      if (sheet.name) params.set('sheet_name', sheet.name)
      params.set('header_row_offset', String(sheet.header_row_offset ?? 0))
      params.set('col_item_name', String(detected['item_name']))
      if (detected['quantity'] !== null) params.set('col_quantity', String(detected['quantity']))
      if (detected['unit_price'] !== null) params.set('col_unit_price', String(detected['unit_price']))
      if (detected['total_price'] !== null) params.set('col_total_price', String(detected['total_price']))
      if (detected['unit'] !== null) params.set('col_unit', String(detected['unit']))
      const fd = new FormData()
      fd.append('file', itemsImportFile.value as File)
      const token = localStorage.getItem('auth_token')
      try {
        const resp = await fetch(`/api/purchases/${props.purchaseId}/items/import-mapped?${params.toString()}`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` } as HeadersInit,
          body: fd,
        })
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}))
          totalErrors.push({ sheet: sheet.name, reason: err.detail || `HTTP ${resp.status}` })
          continue
        }
        const r = await resp.json()
        totalAdded += (r.added || 0)
      } catch (e: any) {
        totalErrors.push({ sheet: sheet.name, reason: e.message || 'network error' })
      }
    }
    if (totalAdded > 0) {
      showSnack(`Импортировано ${totalAdded} позиций из ${importPreviewData.value.sheets.length} таблиц${totalErrors.length ? ` (с ошибками в ${totalErrors.length})` : ''}`)
      emit('reload-requested')
      itemsImportDialog.value = false
    } else {
      const summary = totalErrors.length
        ? `Все таблицы пропущены. Причины: ${totalErrors.map(e => `${e.sheet}: ${e.reason}`).join('; ')}`
        : 'Ни одной позиции не импортировано'
      showSnack(summary, 'warning')
    }
  } finally {
    itemsImportLoading.value = false
  }
}

// ── Smart import ──────────────────────────────────────────────────────────────

const smartImportFile = ref<File | null>(null)
const smartImportFileList = ref<File[]>([])
const smartImportLoading = ref(false)
const smartImportSkipCatalog = ref(false)   // import-no-clutter: тогл «не добавлять в каталог»
const bulkAddCatalogLoading = ref(false)    // import-no-clutter: loading для bulk-add кнопки
const smartImportPreview = ref<any[] | null>(null)
const smartImportColumns = ref<string[] | null>(null)
const smartImportResult = ref<{ added: number; matched_catalog: number; unmatched: number } | null>(null)

// ── Product match review dialog ───────────────────────────────────────────────
// MatchCandidate now imported from @/composables/useItemMatching
interface ResolvedRow {
  query: string
  product_id: number | null
  create_new: boolean
  chosen_candidate?: MatchCandidate | null
}
interface MatchRow { query: string; status: 'auto' | 'suggest' | 'create'; candidates: MatchCandidate[]; _choice?: number | '__create__' | null }
const matchReviewShow = ref(false)
const matchReviewRows = ref<MatchRow[]>([])

// ── P1-B: Single product repick dialog ───────────────────────────────────────
const repickDialog = ref<{ show: boolean; itemIdx: number; itemName: string }>({
  show: false,
  itemIdx: -1,
  itemName: '',
})

function openRepickDialog(idx: number) {
  repickDialog.value = {
    show: true,
    itemIdx: idx,
    itemName: localItems.value[idx]?.item_name || '',
  }
}

function onRepickPick(candidate: MatchCandidate) {
  const idx = repickDialog.value.itemIdx
  if (idx < 0) return
  const item = localItems.value[idx]
  if (!item) return
  applyMatchCandidate(item as any, candidate)
  repickDialog.value.show = false
  emitUpdate()
  showSnack(`Товар перепривязан: ${candidate.name}`, 'success')
}

const CRM_MAPPING_FIELDS: Record<string, string> = {
  item_name: 'Наименование',
  quantity: 'Кол-во',
  unit: 'Ед. изм.',
  unit_price: 'Цена за ед.',
  total_price: 'Сумма',
}

const crmFieldSelectItems = [
  { title: 'Наименование', value: 'item_name' },
  { title: 'Кол-во', value: 'quantity' },
  { title: 'Ед. изм.', value: 'unit' },
  { title: 'Цена за ед.', value: 'unit_price' },
  { title: 'Сумма', value: 'total_price' },
  { title: '— игнорировать', value: '_ignore' },
]

const showMappingPanel = ref(false)
const columnFieldMapping = ref<Record<string, string>>({})
const columnMappingApplied = ref(false)

// Layer 2: reactive proxy bundling the mutable UI state the ItemsImportWizard
// child needs to two-way bind. Getters/setters delegate to the existing refs so
// ALL business logic and state ownership stay in this parent (no duplication).
const importWizardState = reactive({
  get isSmartMode() { return isSmartMode.value },
  set isSmartMode(v: boolean) { isSmartMode.value = v },
  get itemsImportFile() { return itemsImportFile.value },
  set itemsImportFile(v: File | null) { itemsImportFile.value = v },
  get importStep() { return importStep.value },
  set importStep(v: number) { importStep.value = v },
  get importSelectedSheet() { return importSelectedSheet.value },
  set importSelectedSheet(v: string) { importSelectedSheet.value = v },
  get dragMapping() { return dragMapping.value },
  set dragMapping(v: Record<string, number | null>) { dragMapping.value = v },
  get dragOverTarget() { return dragOverTarget.value },
  set dragOverTarget(v: string | null) { dragOverTarget.value = v },
  get smartImportFile() { return smartImportFile.value },
  set smartImportFile(v: File | null) { smartImportFile.value = v },
  get smartImportSkipCatalog() { return smartImportSkipCatalog.value },
  set smartImportSkipCatalog(v: boolean) { smartImportSkipCatalog.value = v },
  get showMappingPanel() { return showMappingPanel.value },
  set showMappingPanel(v: boolean) { showMappingPanel.value = v },
  get columnFieldMapping() { return columnFieldMapping.value },
  set columnFieldMapping(v: Record<string, string>) { columnFieldMapping.value = v },
})

watch(smartImportPreview, (v) => {
  if (v) {
    columnFieldMapping.value = Object.fromEntries(Object.keys(CRM_MAPPING_FIELDS).map(f => [f, f]))
    columnMappingApplied.value = false
    showMappingPanel.value = false
  }
})

function onSmartFileChange(files: File[] | File | null) {
  const fileArr = Array.isArray(files) ? files : (files ? [files] : [])
  smartImportFile.value = fileArr[0] ?? null
  smartImportPreview.value = null
  smartImportResult.value = null
}

function applyColumnMapping() {
  if (!smartImportPreview.value) return
  const mapping = columnFieldMapping.value
  smartImportPreview.value = smartImportPreview.value.map(row => {
    const newRow: any = { ...row }
    for (const [field, src] of Object.entries(mapping)) {
      newRow[field] = src === '_ignore' ? null : (row[src as keyof typeof row] ?? null)
    }
    return newRow
  })
  columnMappingApplied.value = true
  showMappingPanel.value = false
}

async function doSmartPreview() {
  if (!smartImportFile.value) return

  if (!props.purchaseId) {
    // 27.4-26b: Wish / no-pid context — XLSX через нативный smart парсер (без sample-обрезки).
    // PDF/DOCX/HTML остаются на старом preview-flow (sample 5 строк → требует UI mapping).
    const fileName = (smartImportFile.value?.name || '').toLowerCase()
    const isXlsx = fileName.endsWith('.xlsx') || fileName.endsWith('.xls')
    smartImportLoading.value = true
    smartImportPreview.value = null
    smartImportResult.value = null
    try {
      const token = localStorage.getItem('auth_token')
      const fd = new FormData()
      fd.append('file', smartImportFile.value)
      const endpoint = isXlsx
        ? '/api/purchases/items/import-smart-nopid'
        : '/api/purchases/items/import-preview'
      const resp = await fetch(endpoint, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` } as HeadersInit,
        body: fd,
      })
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}))
        throw new Error(err.detail || err.message || `Ошибка ${resp.status}`)
      }
      const data = await resp.json()
      if (isXlsx) {
        // /import-smart-nopid возвращает уже распарсенные позиции — без sample-slice
        smartImportPreview.value = data.preview || []
        smartImportColumns.value = ['item_name', 'quantity', 'unit', 'unit_price', 'total_price']
        if (!smartImportPreview.value.length) showSnack('Позиции не распознаны', 'warning')
      } else {
        // legacy path для PDF/DOCX/HTML — sample 5 строк
        const firstSheet = data.sheets?.[0]
        if (!firstSheet) { showSnack('Позиции не распознаны', 'warning'); return }
        const detectedMapping = autoDetectMapping(firstSheet.headers || [])
        const headerOffset = firstSheet.header_row_offset ?? 0
        const dataRows = (firstSheet.sample as any[][]).slice(headerOffset + 1)
        const preview = dataRows
          .filter(row => {
            const nameIdx = detectedMapping['item_name']
            return nameIdx !== null && nameIdx !== undefined && String(row[nameIdx] ?? '').trim()
          })
          .map(row => {
            const item: Record<string, any> = {}
            for (const [field, idx] of Object.entries(detectedMapping)) {
              if (idx !== null && idx !== undefined) item[field] = row[idx]
            }
            return item
          })
        smartImportPreview.value = preview
        smartImportColumns.value = Object.keys(detectedMapping).filter(k => detectedMapping[k] !== null)
        if (!preview.length) showSnack('Позиции не распознаны', 'warning')
      }
    } catch (e: any) {
      showSnack(e.message || 'Ошибка распознавания', 'error')
    } finally {
      smartImportLoading.value = false
    }
    return
  }

  // Purchase context with pid
  smartImportLoading.value = true
  smartImportPreview.value = null
  smartImportResult.value = null
  try {
    const token = localStorage.getItem('auth_token')
    const fd = new FormData()
    fd.append('file', smartImportFile.value)
    const resp = await fetch(`/api/purchases/${props.purchaseId}/items/import-smart?confirm=false`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` } as HeadersInit,
      body: fd,
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}))
      throw new Error(err.detail || err.message || `Ошибка ${resp.status}`)
    }
    const data = await resp.json()
    // QR ФНС: чек сразу создан на сервере (без preview), закрываем диалог
    if (data.source === 'qr_fns') {
      showSnack(data.message || 'Чек импортирован по QR ФНС', 'success')
      emit('reload-requested')
      itemsImportDialog.value = false
      return
    }
    smartImportPreview.value = data.preview || []
    smartImportColumns.value = data.columns_found || []
    if (data.warning) showSnack(data.warning, 'warning')
    if (!smartImportPreview.value.length) showSnack('Позиции не распознаны', 'warning')
  } catch (e: any) {
    showSnack(e.message || 'Ошибка распознавания', 'error')
  } finally {
    smartImportLoading.value = false
  }
}

// ── Product match review helpers ─────────────────────────────────────────────

/** Commit items built from preview rows after product matching.
 *  resolved[i].product_id   — matched catalog id (or null → create_new)
 *  resolved[i].create_new   — true when backend should create a new catalog entry
 *  Lines 3042–3098 of the original doSmartImport are refactored into this helper
 *  so that both "confirmed via dialog" and "bypass" paths share the same commit logic.
 */
function commitPreviewItems(resolved: ResolvedRow[]) {
  if (!smartImportPreview.value?.length) return
  const previewRows = smartImportPreview.value

  // Phase 27.1 D-02: contract items branch
  if (contractItemImportMode.value) {
    const newContractItems: ContractItem[] = previewRows.map((row, i) => ({
      id: 0,
      purchase_id: props.purchaseId || 0,
      source_item_id: null,
      contract_id: null,
      product_id: resolved[i]?.product_id ?? null,
      name: row.item_name || row.name || '',
      quantity: row.quantity ?? null,
      unit: row.unit ?? null,
      unit_price: row.unit_price ?? null,
      total: row.total_price ?? row.total ?? null,
      match_confirmed: resolved[i]?.product_id != null,
    }))
    localContractItems.value = newContractItems
    contractItemImportMode.value = false
    emitContractItemsUpdate()
    smartImportResult.value = { added: newContractItems.length, matched_catalog: resolved.filter(r => r.product_id != null).length, unmatched: resolved.filter(r => r.create_new).length }
    showSnack(`${newContractItems.length} позиций договора импортированы.`, 'info')
    itemsImportDialog.value = false
    return
  }

  // Normal items branch
  const newItems: EditorItem[] = previewRows.map((row, i) => {
    const res = resolved[i]
    const cand = res?.chosen_candidate ?? null
    // P0-B: если привязан к каталогу — берём имя/описание/фото из кандидата
    const hasCatalog = res?.product_id != null && cand != null
    const item: EditorItem = {
      _uid: nextUid(),
      product_id: res?.product_id ?? null,
      // item_name: из каталога если привязан, иначе из xlsx
      item_name: hasCatalog ? (cand!.name || row.item_name || '') : (row.item_name || ''),
      // item_type: из каталога если есть, иначе из xlsx или дефолт
      item_type: hasCatalog && cand!.item_type ? cand!.item_type : (row.item_type || props.defaultItemType),
      // qty/unit_price/total_price ВСЕГДА из xlsx
      quantity: row.quantity ?? null,
      unit: row.unit || props.defaultUnit,
      unit_price: row.unit_price ?? null,
      total_price: row.total_price ?? null,
      country_origin: props.defaultCountry,
      _selectedProduct: null,
      _photo_url: hasCatalog ? (cand!.photo_url ?? undefined) : undefined,
      _description: hasCatalog ? (cand!.description ?? undefined) : undefined,
      _description_44fz: undefined,
      _price_meta: hasCatalog ? {
        price_updated_at: cand!.price_updated_at ?? null,
        price_source: cand!.price_source ?? null,
        price_source_ref: cand!.price_source_ref ?? null,
        price_freshness: cand!.price_freshness ?? null,
      } : null,
    }
    if (props.itemShape === 'purchase') {
      item.final_unit_price = null
      item.final_total = null
      // F-PLAN: импортированные строки сразу наследуют шапочную плановую позицию
      item.feo_planned_item_id = props.defaultFeoPlannedItemId ?? null
    }
    return item
  })
  // ── Detect duplicates by product_id ──────────────────────────────────────
  const productGroups = new Map<number, EditorItem[]>()
  for (const item of newItems) {
    if (item.product_id != null) {
      const pid = item.product_id
      if (!productGroups.has(pid)) productGroups.set(pid, [])
      productGroups.get(pid)!.push(item)
    }
  }
  const dupGroups: DupGroup[] = []
  for (const [pid, groupItems] of productGroups.entries()) {
    if (groupItems.length > 1) {
      dupGroups.push({
        product_id: pid,
        name: groupItems[0].item_name || `ID ${pid}`,
        items: groupItems.map(it => ({
          quantity: it.quantity ?? null,
          unit_price: it.unit_price ?? null,
          total_price: it.total_price ?? null,
        })),
        _choice: 'merge',
      })
    }
  }

  if (dupGroups.length > 0) {
    // Show dialog — commit will happen in onDupMergeConfirm
    _pendingMergeItems = newItems
    dupMergeGroups.value = dupGroups
    dupMergeShow.value = true
    // Store resolved count info for later snack
    ;(window as any).__pendingImportMatchedCount = resolved.filter(r => r.product_id != null).length
    itemsImportDialog.value = false
    return
  }

  // No duplicates — commit immediately
  localItems.value.push(...newItems)
  emitUpdate()
  const matchedCount = resolved.filter(r => r.product_id != null).length
  smartImportResult.value = { added: newItems.length, matched_catalog: matchedCount, unmatched: newItems.length - matchedCount }
  showSnack(`${newItems.length} позиций добавлены в список.`, 'info')
  itemsImportDialog.value = false
}

/** Handler for DuplicateMergeDialog @confirm */
function onDupMergeConfirm(resolvedGroups: ResolvedGroup[]) {
  const mergeMap = new Map<number, ResolvedGroup>()
  for (const rg of resolvedGroups) {
    mergeMap.set(rg.product_id, rg)
  }

  // Build final items: for groups with choice=merge keep only merged item, else keep all
  const seenMerged = new Set<number>()
  const finalItems: EditorItem[] = []

  for (const item of _pendingMergeItems) {
    const pid = item.product_id
    if (pid == null) {
      finalItems.push(item)
      continue
    }
    const rg = mergeMap.get(pid)
    if (!rg || rg.choice === 'keep') {
      finalItems.push(item)
      continue
    }
    // merge choice — push merged item once
    if (!seenMerged.has(pid)) {
      seenMerged.add(pid)
      const mi = rg.mergedItem!
      finalItems.push({
        ...item,
        quantity: mi.quantity,
        unit_price: mi.unit_price,
        total_price: mi.total_price,
      })
    }
    // subsequent items in the same group are dropped
  }

  localItems.value.push(...finalItems)
  emitUpdate()
  const matchedCount = (window as any).__pendingImportMatchedCount ?? 0
  delete (window as any).__pendingImportMatchedCount
  smartImportResult.value = { added: finalItems.length, matched_catalog: matchedCount, unmatched: finalItems.length - matchedCount }
  showSnack(`${finalItems.length} позиций добавлены в список.`, 'info')
  _pendingMergeItems = []
}

/** Handler for ProductMatchReviewDialog @confirm event */
function onMatchConfirm(resolved: ResolvedRow[]) {
  matchReviewShow.value = false
  commitPreviewItems(resolved)
}

/** Handler for ProductMatchReviewDialog @cancel event */
function onMatchCancel() {
  matchReviewShow.value = false
  // Do not commit anything — leave import dialog open so user sees the preview
}

async function doSmartImport() {
  if (!smartImportPreview.value?.length) return

  // If user applied custom column mapping OR no purchaseId, run product matching first
  if (columnMappingApplied.value || !props.purchaseId) {
    // TODO: contract items mode currently bypasses product matching (needs separate design)
    if (contractItemImportMode.value) {
      const bypassResolved = smartImportPreview.value.map(row => ({
        query: row.item_name || row.name || '',
        product_id: null as number | null,
        create_new: true,
      }))
      commitPreviewItems(bypassResolved)
      return
    }

    // «Не добавлять в каталог» (напр. авансовые платежи): позиции должны быть
    // один-в-один как в чеке. Сопоставление с каталогом не нужно — коммитим как есть,
    // без привязки и без диалога.
    if (smartImportSkipCatalog.value) {
      const skipResolved = smartImportPreview.value.map(row => ({
        query: row.item_name || '',
        product_id: null as number | null,
        create_new: false,
      }))
      commitPreviewItems(skipResolved)
      return
    }

    // Call /api/products/match to get suggestions, then show review dialog
    const queries: string[] = smartImportPreview.value.map(row => row.item_name || '')
    smartImportLoading.value = true
    try {
      const matchData = await apiFetch<{
        results: Array<{ query: string; status: 'auto' | 'suggest' | 'create'; candidates: MatchCandidate[] }>
      }>('/products/match', { method: 'POST', body: { queries } })
      matchReviewRows.value = matchData.results.map(r => ({ ...r, _choice: undefined }))
      matchReviewShow.value = true
    } catch (e: any) {
      // If match endpoint not available yet, fall back to direct commit without matching
      // TODO: remove fallback once /api/products/match is stable
      showSnack('Сопоставление с каталогом недоступно, позиции добавлены без привязки', 'warning')
      const fallbackResolved = smartImportPreview.value.map(row => ({
        query: row.item_name || '',
        product_id: null as number | null,
        create_new: true,
      }))
      commitPreviewItems(fallbackResolved)
    } finally {
      smartImportLoading.value = false
    }
    return
  }

  if (!smartImportFile.value || !props.purchaseId) return
  smartImportLoading.value = true
  try {
    const token = localStorage.getItem('auth_token')
    const fd = new FormData()
    fd.append('file', smartImportFile.value)
    const resp = await fetch(`/api/purchases/${props.purchaseId}/items/import-smart?confirm=true&skip_catalog=${smartImportSkipCatalog.value}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` } as HeadersInit,
      body: fd,
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}))
      throw new Error(err.detail || err.message || `Ошибка ${resp.status}`)
    }
    smartImportResult.value = await resp.json()
    if (smartImportResult.value!.added > 0) {
      showSnack(`Импортировано ${smartImportResult.value!.added} позиций`)
      emit('reload-requested')
    }
  } catch (e: any) {
    showSnack(e.message || 'Ошибка импорта', 'error')
  } finally {
    smartImportLoading.value = false
  }
}

// import-pdf-debug C3: скачать debug-отчёт для несработавшего файла
async function downloadDebugReport() {
  if (!smartImportFile.value) return
  const fd = new FormData()
  fd.append('file', smartImportFile.value)
  try {
    const token = localStorage.getItem('auth_token') || ''
    const res = await fetch('/api/purchases/items/import-pdf-debug', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` } as HeadersInit,
      body: fd,
    })
    const data = await res.json()
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `import-debug-${smartImportFile.value.name}.json`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    showSnack('Не удалось получить debug-отчёт', 'error')
  }
}

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
})
</script>

<style scoped>
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
