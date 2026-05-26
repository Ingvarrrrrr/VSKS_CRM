<template>
  <div class="purchase-items-editor">
    <!-- Header row -->
    <div class="d-flex align-center justify-space-between mb-2 flex-wrap ga-2">
      <span class="text-subtitle-1 font-weight-bold">
        {{ itemShape === 'purchase' ? 'Позиции закупки' : 'Позиции' }}
      </span>
      <div class="d-flex align-center ga-2 flex-wrap">
        <v-btn v-if="selectedItemIdxs.length > 0 && !props.readonly"
          variant="tonal" prepend-icon="mdi-delete-sweep-outline" size="small" color="error"
          @click="removeSelectedItems">
          Удалить ({{ selectedItemIdxs.length }})
        </v-btn>
        <slot name="toolbar-actions" />
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

    <!-- Purchase shape table -->
    <template v-if="itemShape === 'purchase'">
      <!-- Phase 27.1.1: expand-row layout (3 sub-rows per position: ТЗ / Договор / Поставка) -->
      <template v-if="stagesEnabled">
        <v-table density="compact">
          <thead>
            <tr>
              <th style="width:36px"></th>
              <th style="width:36px;padding:0 4px;text-align:center">
                <v-checkbox :model-value="allItemsSelected" density="compact" hide-details :rules="[]"
                  :indeterminate="selectedItemIdxs.length > 0 && !allItemsSelected"
                  @update:model-value="toggleSelectAll" />
              </th>
              <th style="width:36px;text-align:center;color:#888;font-size:12px">№</th>
              <th>Наименование</th>
              <th style="min-width:280px">Суммы стадий</th>
              <th style="width:48px">Матч</th>
              <th style="width:80px"></th>
            </tr>
          </thead>
          <tbody>
            <template v-for="(item, idx) in localItems" :key="idx">
              <!-- Summary row -->
              <tr class="summary-row" style="cursor:pointer" @click="toggleExpand(idx)">
                <td style="width:36px;text-align:center">
                  <v-btn
                    :icon="expanded[idx] ? 'mdi-chevron-up' : 'mdi-chevron-down'"
                    size="small" variant="text" density="compact"
                    @click.stop="toggleExpand(idx)"
                  />
                </td>
                <td style="width:36px;padding:0 4px;text-align:center" @click.stop>
                  <v-checkbox :model-value="selectedItemIdxs.includes(idx)" density="compact" hide-details :rules="[]"
                    @update:model-value="(val: boolean | null) => toggleItemSelect(idx, val)" />
                </td>
                <td style="width:36px;text-align:center;color:#888;font-size:12px;font-weight:500">{{ idx + 1 }}</td>
                <td>
                  <div class="d-flex align-center gap-1">
                    <v-tooltip v-if="item._photo_url" location="right">
                      <template #activator="{ props: tip }">
                        <v-avatar v-bind="tip" size="28" rounded="sm" class="flex-shrink-0" style="overflow:hidden">
                          <img :src="item._photo_url" style="width:28px;height:28px;object-fit:cover;display:block" />
                        </v-avatar>
                      </template>
                      <img :src="item._photo_url" style="width:160px;height:160px;object-fit:cover;border-radius:8px;display:block" />
                    </v-tooltip>
                    <v-icon v-else size="20" class="flex-shrink-0 text-medium-emphasis">mdi-package-variant</v-icon>
                    <span class="text-body-2" style="max-width:300px;white-space:normal;line-height:1.3">{{ summaryName(idx) || '—' }}</span>
                  </div>
                </td>
                <td>
                  <div class="d-flex ga-1 flex-wrap align-center">
                    <v-chip size="x-small" color="info" variant="tonal">ТЗ: {{ stageTotals(idx).tz > 0 ? stageTotals(idx).tz.toLocaleString('ru-RU') + ' ₽' : '—' }}</v-chip>
                    <v-chip size="x-small" color="success" variant="tonal">Дог: {{ stageTotals(idx).dog > 0 ? stageTotals(idx).dog.toLocaleString('ru-RU') + ' ₽' : '—' }}</v-chip>
                    <v-chip size="x-small" color="purple" variant="tonal">Пост: {{ stageTotals(idx).delivery > 0 ? stageTotals(idx).delivery.toLocaleString('ru-RU') + ' ₽' : '—' }}</v-chip>
                  </div>
                </td>
                <td style="text-align:center">
                  <v-tooltip v-if="item.match_confirmed === false && item.product_id" text="Fuzzy-match — требует подтверждения" location="top">
                    <template #activator="{ props: tip }">
                      <v-icon v-bind="tip" color="warning" icon="mdi-alert" size="small" />
                    </template>
                  </v-tooltip>
                  <v-icon v-else-if="item.product_id" color="success" icon="mdi-check" size="small" />
                  <v-tooltip v-else-if="item.item_name" text="Позиция не привязана к каталогу — выберите товар или создайте новый" location="top">
                    <template #activator="{ props: tip }">
                      <v-icon v-bind="tip" color="warning" icon="mdi-alert" size="small" />
                    </template>
                  </v-tooltip>
                  <v-icon v-else color="grey" icon="mdi-minus" size="small" />
                </td>
                <td @click.stop>
                  <div class="d-flex">
                    <v-tooltip v-if="item.match_confirmed === false && item.product_id" text="Подтвердить матч" location="top">
                      <template #activator="{ props: tip }">
                        <v-btn v-bind="tip" icon="mdi-check-bold" size="x-small" variant="tonal"
                          color="warning" :disabled="props.readonly"
                          @click.stop="confirmMatch(idx)" />
                      </template>
                    </v-tooltip>
                    <!-- P1-B: кнопка перепривязки к каталогу -->
                    <v-tooltip text="Изменить привязку к каталогу" location="top">
                      <template #activator="{ props: tip }">
                        <v-btn v-bind="tip" icon="mdi-link-variant-plus" size="x-small" variant="text"
                          color="teal" :disabled="props.readonly"
                          @click.stop="openRepickDialog(idx)" />
                      </template>
                    </v-tooltip>
                    <v-btn icon="mdi-delete-outline" variant="text" size="small" color="error"
                      :disabled="props.readonly"
                      @click.stop="removeItem(idx)" />
                  </div>
                </td>
              </tr>
              <!-- Expanded sub-rows -->
              <tr v-if="expanded[idx]" class="stage-row-wrapper">
                <td colspan="7" style="padding:0 0 8px 48px">
                  <v-table density="compact" class="nested-stages-table">
                    <thead>
                      <tr>
                        <th style="width:90px">Стадия</th>
                        <th style="min-width:280px">Наименование</th>
                        <th style="min-width:90px">Кол-во</th>
                        <th style="min-width:80px">Ед.</th>
                        <th style="min-width:110px">Цена ед., ₽</th>
                        <th v-if="showVatColumnsInExpandRow" style="min-width:100px">НДС %</th>
                        <th v-if="showVatColumnsInExpandRow" style="min-width:110px">НДС сумма, ₽</th>
                        <th style="min-width:120px">{{ showVatColumnsInExpandRow ? 'Сумма с НДС, ₽' : 'Сумма, ₽' }}</th>
                        <th style="min-width:200px">Действия</th>
                      </tr>
                    </thead>
                    <tbody>
                      <!-- ТЗ sub-row -->
                      <tr class="stage-tz-row">
                        <td><v-chip color="info" size="x-small" variant="tonal">ТЗ</v-chip></td>
                        <td>
                          <div class="d-flex align-center gap-1">
                            <v-textarea
                              v-model="item.item_name"
                              density="compact" variant="outlined" hide-details clearable readonly
                              rows="1" auto-grow class="my-1 flex-grow-1" style="cursor:pointer;min-width:200px"
                              placeholder="Нажмите для выбора..."
                              :disabled="props.readonly"
                              @click="openProductPicker(idx)"
                              @click:clear.stop="clearItem(idx)"
                            />
                            <v-tooltip v-if="item.item_name" :text="item.product_id ? 'Редактировать товар в каталоге' : 'Создать товар в каталоге из этой позиции'" location="top">
                              <template #activator="{ props: tip }">
                                <v-btn v-bind="tip" icon="mdi-pencil-outline" size="x-small" variant="tonal"
                                  color="teal" class="flex-shrink-0" :disabled="props.readonly"
                                  @click.stop="openQuickProductEdit(item)" />
                              </template>
                            </v-tooltip>
                          </div>
                          <!-- Phase 27.1.1 fix: per-item contractor только для авансовых (advance_report). Inline contractor для обычных закупок убран — 1 контрагент на закупку. -->
                        </td>
                        <td>
                          <v-text-field v-model.number="item.quantity" type="number" density="compact"
                            variant="outlined" hide-details class="my-1" :disabled="props.readonly"
                            @update:model-value="calcItemTotal(idx)" />
                        </td>
                        <td>
                          <v-combobox v-model="item.unit" :items="UNIT_OPTIONS" density="compact" variant="outlined"
                            hide-details class="my-1" :disabled="props.readonly" />
                        </td>
                        <td>
                          <v-text-field v-model.number="item.unit_price" type="number" density="compact"
                            variant="outlined" hide-details class="my-1" :disabled="props.readonly"
                            @update:model-value="calcItemTotal(idx)" />
                        </td>
                        <!-- Fix 4/5: НДС % column -->
                        <td v-if="showVatColumnsInExpandRow">
                          <v-combobox v-model="item.vat_rate"
                            :items="VAT_RATE_OPTIONS"
                            item-title="title" item-value="value"
                            density="compact" variant="outlined" hide-details class="my-1"
                            style="min-width:90px" :disabled="props.readonly"
                            placeholder="НДС %"
                            @update:model-value="onVatRateChange(idx, $event)"
                          />
                        </td>
                        <!-- Fix 4/5: НДС сумма column -->
                        <td v-if="showVatColumnsInExpandRow" class="text-caption">{{ fmtRub(vatAmount(item)) }}</td>
                        <!-- Fix 4/5: Сумма с НДС column -->
                        <td class="text-caption font-weight-medium">{{ fmtRub(totalWithVat(item)) }}</td>
                        <td>
                          <div class="d-flex align-center ga-1 flex-wrap">
                            <!-- Тип -->
                            <v-select v-model="item.item_type"
                              :items="props.allowedItemTypes.map(t => ({ value: t, title: t.charAt(0).toUpperCase() + t.slice(1) }))"
                              item-title="title" item-value="value" density="compact" variant="outlined"
                              hide-details style="min-width:100px" class="my-1" :disabled="props.readonly" />
                            <!-- F-PIF2: ФЭО позиция per-item (показывается только в режиме feoPerItem) -->
                            <template v-if="props.feoPerItem">
                              <v-autocomplete
                                v-model="item.feo_planned_item_id"
                                :items="feoResiduals"
                                item-title="name"
                                item-value="feo_item_id"
                                label="ФЭО позиция"
                                variant="outlined"
                                density="compact"
                                clearable
                                hide-details
                                class="my-1"
                                style="min-width:200px"
                                :class="{ 'feo-over-budget': isOverBudget(item) }"
                                :disabled="props.readonly"
                                @update:model-value="emit('items-changed')"
                              >
                                <template #item="{ props: itemProps, item: feoItem }">
                                  <v-list-item v-bind="itemProps" :title="feoItem.raw.name">
                                    <template #subtitle>
                                      План: {{ fmtRub(feoItem.raw.planned_amount) }} • Использовано: {{ fmtRub(feoItem.raw.used_amount) }} • Остаток: {{ fmtRub(feoItem.raw.residual) }}
                                    </template>
                                  </v-list-item>
                                </template>
                              </v-autocomplete>
                              <div v-if="isOverBudget(item)" class="text-caption text-warning my-1 d-flex align-center ga-1">
                                <v-icon icon="mdi-alert-outline" size="14" />
                                Превышение: {{ fmtRub(overBudgetDelta(item)) }}
                              </div>
                            </template>
                            <!-- Страна -->
                            <v-text-field v-model="item.country_origin" density="compact"
                              variant="outlined" hide-details class="my-1" placeholder="Россия"
                              style="min-width:120px" :disabled="props.readonly" />
                            <!-- Контрагент (advance_report column mode) -->
                            <template v-if="showContractorColumn">
                              <v-autocomplete
                                :model-value="item.contractor_id ? contractors.find(c => c.id === item.contractor_id) || null : null"
                                :items="contractors" item-title="name" item-value="id" return-object
                                variant="outlined" density="compact" clearable auto-select-first hide-details
                                class="my-1" style="min-width:180px"
                                :custom-filter="contractorFilter" :loading="contractorLookupLoading[idx] === true"
                                placeholder="Поставщик..." :disabled="props.readonly"
                                @update:search="(s: string) => onContractorSearchInput(idx, s)"
                                @update:model-value="(v: Contractor | null) => onItemContractorSelect(idx, v)"
                              >
                                <template #append-inner>
                                  <v-btn icon="mdi-account-plus" size="x-small" variant="text" color="teal"
                                    :disabled="props.readonly" @click.stop="openContractorQuickCreate(idx)" />
                                </template>
                              </v-autocomplete>
                            </template>
                            <!-- ТЗ contractor chip (non-advance mode, if contractor set from Phase 24 D-05) -->
                            <v-chip
                              v-if="!showContractorColumn && item.contractor_id && contractorNameById(item.contractor_id)"
                              size="x-small" color="info" variant="tonal"
                              prepend-icon="mdi-store" class="text-truncate" style="max-width:160px"
                            >
                              {{ contractorNameById(item.contractor_id) }}
                            </v-chip>
                          </div>
                        </td>
                      </tr>
                      <!-- Договор sub-row -->
                      <tr class="stage-contract-row">
                        <td><v-chip color="success" size="x-small" variant="tonal">Договор</v-chip></td>
                        <td>
                          <v-textarea
                            :model-value="getContractItemFor(idx)?.name ?? (isAdvance ? (localItems[idx] as any)?.item_name ?? '' : '')"
                            density="compact" variant="outlined" hide-details placeholder="Наименование по договору"
                            rows="1" auto-grow class="my-1 flex-grow-1" style="min-width:200px"
                            :disabled="props.readonly"
                            @update:model-value="(v: string) => updateContractField(idx, 'name', v)"
                          />
                        </td>
                        <td>
                          <v-text-field
                            :model-value="getContractItemFor(idx)?.quantity ?? (isAdvance ? (localItems[idx] as any)?.quantity ?? '' : '')"
                            type="number" density="compact" variant="outlined" hide-details
                            :disabled="props.readonly"
                            @update:model-value="(v: string) => updateContractField(idx, 'quantity', Number(v))"
                          />
                        </td>
                        <td>
                          <v-text-field
                            :model-value="getContractItemFor(idx)?.unit ?? (isAdvance ? (localItems[idx] as any)?.unit ?? '' : '')"
                            density="compact" variant="outlined" hide-details
                            :disabled="props.readonly"
                            @update:model-value="(v: string) => updateContractField(idx, 'unit', v)"
                          />
                        </td>
                        <td>
                          <v-text-field
                            :model-value="getContractItemFor(idx)?.unit_price ?? (isAdvance ? (localItems[idx] as any)?.unit_price ?? '' : '')"
                            type="number" density="compact" variant="outlined" hide-details
                            :disabled="props.readonly"
                            @update:model-value="(v: string) => updateContractField(idx, 'unit_price', Number(v))"
                          />
                        </td>
                        <!-- Fix 4/5: НДС % column (Договор) -->
                        <td v-if="showVatColumnsInExpandRow">
                          <v-combobox
                            :model-value="getContractItemFor(idx)?.vat_rate ?? localItems[idx]?.vat_rate ?? null"
                            :items="VAT_RATE_OPTIONS"
                            item-title="title" item-value="value"
                            density="compact" variant="outlined" hide-details class="my-1"
                            style="min-width:90px" :disabled="props.readonly"
                            placeholder="НДС %"
                            @update:model-value="(v: any) => {
                              const ci = getContractItemFor(idx)
                              if (!ci) return
                              let rate: string | null
                              if (v == null || v === '' || v === 'Без НДС') { rate = null }
                              else { const s = String(v); rate = /^\d+(?:\.\d+)?$/.test(s.trim()) ? s.trim() + '%' : s }
                              ;(ci as any).vat_rate = rate
                              emitContractItemsUpdate()
                            }"
                          />
                        </td>
                        <!-- Fix 4/5: НДС сумма column (Договор) -->
                        <td v-if="showVatColumnsInExpandRow" class="text-caption">{{ fmtRub(vatAmountForStage(idx, 'contract')) }}</td>
                        <!-- Fix 4/5: Сумма с НДС column (Договор) -->
                        <td class="text-caption font-weight-medium">{{ fmtRub(totalWithVatForStage(idx, 'contract')) }}</td>
                        <td>
                          <div class="d-flex align-center ga-1 flex-wrap" style="font-size:11px">
                            <v-chip
                              v-if="contractStageContractorName(idx)"
                              size="x-small" color="success" variant="tonal"
                              prepend-icon="mdi-store"
                              class="text-truncate" style="max-width:180px"
                            >
                              {{ contractStageContractorName(idx) }}
                            </v-chip>
                            <span v-else class="text-medium-emphasis text-caption">—</span>
                          </div>
                        </td>
                      </tr>
                      <!-- Поставка sub-row (D-01.1.1) -->
                      <tr class="stage-delivery-row" :class="{ 'stage-delivery-empty': !isDeliveryFilled(idx) }">
                        <td><v-chip color="purple" size="x-small" variant="tonal">Поставка</v-chip></td>
                        <template v-if="isDelivered(idx) && getContractItemFor(idx)">
                          <!-- delivered/paid: копия Договор, readonly textarea (унифицировано с ТЗ/Договор) -->
                          <td>
                            <v-textarea
                              :model-value="getContractItemFor(idx)?.name || '—'"
                              density="compact" variant="outlined" hide-details readonly
                              rows="1" auto-grow class="my-1" style="min-width:200px"
                              bg-color="grey-lighten-4"
                            />
                          </td>
                          <td class="text-caption text-grey-darken-1">{{ getContractItemFor(idx)?.quantity ?? '—' }}</td>
                          <td class="text-caption text-grey-darken-1">{{ getContractItemFor(idx)?.unit ?? '—' }}</td>
                          <td class="text-caption text-grey-darken-1">{{ getContractItemFor(idx)?.unit_price ?? '—' }}</td>
                          <!-- Fix 4/5: НДС % readonly (Поставка) -->
                          <td v-if="showVatColumnsInExpandRow" class="text-caption text-grey-darken-1">{{ effectiveVatRate(idx, 'delivery') ?? '—' }}</td>
                          <!-- Fix 4/5: НДС сумма readonly (Поставка) -->
                          <td v-if="showVatColumnsInExpandRow" class="text-caption text-grey-darken-1">{{ fmtRub(vatAmountForStage(idx, 'delivery')) }}</td>
                          <!-- Fix 4/5: Сумма с НДС readonly (Поставка) -->
                          <td class="text-caption text-grey-darken-1 font-weight-medium">
                            {{ fmtRub(totalWithVatForStage(idx, 'delivery')) }}
                          </td>
                          <td>
                            <div class="d-flex align-center ga-1 flex-wrap">
                              <v-chip
                                v-if="deliveryStageContractorName(idx)"
                                size="x-small" color="purple" variant="tonal"
                                prepend-icon="mdi-truck-delivery" class="text-truncate" style="max-width:140px"
                              >
                                {{ deliveryStageContractorName(idx) }}
                              </v-chip>
                              <v-tooltip location="top" text="Появится в Phase 27 (delivery_items). Будет создавать «Поставка 1» + «Поставка 2» для частичных поставок.">
                                <template #activator="{ props: tp }">
                                  <v-btn v-bind="tp" icon="mdi-arrow-split-vertical" size="x-small" variant="text"
                                    color="grey" disabled />
                                </template>
                              </v-tooltip>
                            </div>
                          </td>
                        </template>
                        <template v-else-if="isAdvance">
                          <!-- advance: показываем данные из ТЗ вместо заглушки -->
                          <td>
                            <v-textarea
                              :model-value="(localItems[idx] as any)?.item_name ?? ''"
                              density="compact" variant="outlined" hide-details readonly
                              rows="1" auto-grow class="my-1" style="min-width:200px"
                              bg-color="grey-lighten-4"
                            />
                          </td>
                          <td class="text-caption text-grey-darken-1">{{ (localItems[idx] as any)?.quantity ?? '—' }}</td>
                          <td class="text-caption text-grey-darken-1">{{ (localItems[idx] as any)?.unit ?? '—' }}</td>
                          <td class="text-caption text-grey-darken-1">{{ (localItems[idx] as any)?.unit_price ?? '—' }}</td>
                          <td v-if="showVatColumnsInExpandRow" class="text-caption text-grey-darken-1">{{ (localItems[idx] as any)?.vat_rate ?? '—' }}</td>
                          <td v-if="showVatColumnsInExpandRow" class="text-caption text-grey-darken-1">{{ fmtRub(vatAmount((localItems[idx] as any) ?? {})) }}</td>
                          <td class="text-caption text-grey-darken-1 font-weight-medium">{{ fmtRub(Number((localItems[idx] as any)?.total_price ?? 0)) }}</td>
                          <td></td>
                        </template>
                        <template v-else>
                          <td colspan="9" class="text-caption text-grey-lighten-1 text-center py-1">
                            Поставок ещё нет — появятся в Phase 27 (delivery_items)
                          </td>
                        </template>
                      </tr>
                    </tbody>
                  </v-table>
                </td>
              </tr>
            </template>
            <tr v-if="!localItems.length">
              <td colspan="7" class="text-center text-medium-emphasis py-4">
                Нет позиций. Нажмите «Добавить позицию».
              </td>
            </tr>
          </tbody>
          <tfoot v-if="localItems.length">
            <tr>
              <td colspan="3" class="text-right pr-3 py-2 text-caption font-weight-bold">НМЦД итого:</td>
              <td colspan="4" class="py-2 font-weight-bold text-blue-darken-2">
                {{ internalTotalNmck.toLocaleString('ru-RU') }} ₽
              </td>
            </tr>
          </tfoot>
        </v-table>

        <!-- Savings badge under the expand-row table -->
        <div v-if="contractItemsTotal > 0" class="mt-3 d-flex ga-2 flex-wrap align-center">
          <v-chip color="primary" variant="tonal" size="small">
            Сумма позиций договора: {{ contractItemsTotal.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }} ₽
          </v-chip>
          <v-chip color="info" variant="tonal" size="small">
            НМЦД заявки: {{ purchasePlannedTotal.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }} ₽
          </v-chip>
          <v-chip
            v-if="contractSavings != null"
            :color="Number(contractSavings) >= 0 ? 'success' : 'error'"
            variant="tonal" size="small"
          >
            Экономия: {{ contractSavings.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }} ₽ ({{ contractSavingsPercent }}%)
          </v-chip>
        </div>
      </template>

      <!-- Legacy flat table (when stagesEnabled is false, i.e. pre-Phase 27.1.1) -->
      <template v-else>
        <div class="overflow-x-auto">
          <v-table density="compact">
            <thead>
              <tr>
                <th style="width:36px;padding:0 4px;text-align:center">
                  <v-checkbox :model-value="allItemsSelected" density="compact" hide-details :rules="[]"
                    :indeterminate="selectedItemIdxs.length > 0 && !allItemsSelected"
                    @update:model-value="toggleSelectAll" />
                </th>
                <th style="width:36px;text-align:center;color:#888;font-size:12px">№</th>
                <th :style="resizeStyle('name')">Наименование<span class="col-resize-handle" @mousedown="onResizeStart($event, 'name')">&nbsp;</span></th>
                <th :style="resizeStyle('type')">Тип<span class="col-resize-handle" @mousedown="onResizeStart($event, 'type')">&nbsp;</span></th>
                <th :style="resizeStyle('qty')">Кол-во<span class="col-resize-handle" @mousedown="onResizeStart($event, 'qty')">&nbsp;</span></th>
                <th :style="resizeStyle('unit')">Ед. изм.<span class="col-resize-handle" @mousedown="onResizeStart($event, 'unit')">&nbsp;</span></th>
                <th :style="resizeStyle('price')">Цена ед., ₽<span class="col-resize-handle" @mousedown="onResizeStart($event, 'price')">&nbsp;</span></th>
                <th :style="resizeStyle('sum')">Сумма, ₽<span class="col-resize-handle" @mousedown="onResizeStart($event, 'sum')">&nbsp;</span></th>
                <th :style="resizeStyle('country')">Страна происхождения<span class="col-resize-handle" @mousedown="onResizeStart($event, 'country')">&nbsp;</span></th>
                <th v-if="props.vatMode === 'per_item'" style="min-width:130px">НДС</th>
                <th v-if="showContractorColumn" :style="resizeStyle('contractor')">Контрагент<span class="col-resize-handle" @mousedown="onResizeStart($event, 'contractor')">&nbsp;</span></th>
                <th :style="resizeStyle('actions')"><span class="col-resize-handle" @mousedown="onResizeStart($event, 'actions')">&nbsp;</span></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(item, idx) in localItems" :key="idx">
                <td style="width:36px;padding:0 4px;text-align:center">
                  <v-checkbox :model-value="selectedItemIdxs.includes(idx)" density="compact" hide-details :rules="[]"
                    @update:model-value="(val: boolean | null) => toggleItemSelect(idx, val)" />
                </td>
                <td style="width:36px;text-align:center;color:#888;font-size:12px;font-weight:500">{{ idx + 1 }}</td>
                <td style="min-width:420px">
                  <div class="d-flex align-center gap-1">
                    <v-tooltip v-if="item._photo_url" location="right">
                      <template #activator="{ props: tip }">
                        <v-avatar v-bind="tip" size="36" rounded="sm" class="flex-shrink-0" style="cursor:pointer;overflow:hidden">
                          <img :src="item._photo_url" style="width:36px;height:36px;object-fit:cover;display:block" />
                        </v-avatar>
                      </template>
                      <img :src="item._photo_url" style="width:200px;height:200px;object-fit:cover;border-radius:8px;display:block" />
                    </v-tooltip>
                    <v-icon v-else size="28" class="flex-shrink-0 text-medium-emphasis">mdi-package-variant</v-icon>
                    <v-tooltip v-if="item.item_name && !item.product_id" text="Позиция не привязана к каталогу" location="top">
                      <template #activator="{ props: tip }">
                        <v-icon v-bind="tip" size="18" color="warning" class="flex-shrink-0">mdi-alert</v-icon>
                      </template>
                    </v-tooltip>
                    <v-textarea
                      v-model="item.item_name" density="compact" variant="outlined" hide-details clearable readonly
                      rows="1" auto-grow class="my-1" style="cursor:pointer;min-width:280px"
                      placeholder="Нажмите для выбора..." :disabled="props.readonly"
                      @click="openProductPicker(idx)" @click:clear.stop="clearItem(idx)"
                    />
                    <v-tooltip v-if="item.item_name" :text="item.product_id ? 'Редактировать товар в каталоге' : 'Создать товар в каталоге из этой позиции'" location="top">
                      <template #activator="{ props: tip }">
                        <v-btn v-bind="tip" icon="mdi-pencil-outline" size="x-small" variant="tonal"
                          color="teal" class="flex-shrink-0 ml-1" :disabled="props.readonly"
                          @click.stop="openQuickProductEdit(item)" />
                      </template>
                    </v-tooltip>
                    <v-tooltip v-if="item.match_confirmed === false && item.product_id" text="Подтвердить, что товар из каталога определён правильно" location="top">
                      <template #activator="{ props: tip }">
                        <v-btn v-bind="tip" icon="mdi-check-bold" size="x-small" variant="tonal"
                          color="warning" class="flex-shrink-0 ml-1" :disabled="props.readonly"
                          @click.stop="confirmMatch(idx)" />
                      </template>
                    </v-tooltip>
                  </div>
                  <!-- Phase 27.1.2: inline contractor убран для не-advance из flat layout. Per-item contractor только в advance_report mode (колонка showContractorColumn справа). -->
                </td>
                <td>
                  <v-select v-model="item.item_type"
                    :items="props.allowedItemTypes.map(t => ({ value: t, title: t.charAt(0).toUpperCase() + t.slice(1) }))"
                    item-title="title" item-value="value" density="compact" variant="outlined"
                    hide-details class="my-1" :disabled="props.readonly" />
                </td>
                <td>
                  <v-text-field v-model.number="item.quantity" type="number" density="compact"
                    variant="outlined" hide-details class="my-1" :disabled="props.readonly"
                    @update:model-value="calcItemTotal(idx)" />
                </td>
                <td>
                  <v-combobox v-model="item.unit" :items="UNIT_OPTIONS" density="compact" variant="outlined"
                    hide-details class="my-1" :disabled="props.readonly" />
                </td>
                <td>
                  <v-text-field v-model.number="item.unit_price" type="number" density="compact"
                    variant="outlined" hide-details class="my-1" :disabled="props.readonly"
                    @update:model-value="calcItemTotal(idx)" />
                </td>
                <td>
                  <v-text-field :model-value="item.total_price ?? ''" readonly density="compact"
                    variant="outlined" hide-details bg-color="grey-lighten-4" class="my-1" />
                </td>
                <td>
                  <v-text-field v-model="item.country_origin" density="compact"
                    variant="outlined" hide-details class="my-1" placeholder="Россия" :disabled="props.readonly" />
                </td>
                <td v-if="props.vatMode === 'per_item'">
                  <v-combobox v-model="item.vat_rate"
                    :items="VAT_RATE_OPTIONS"
                    item-title="title" item-value="value"
                    density="compact" variant="outlined" hide-details class="my-1"
                    style="min-width:100px" :disabled="props.readonly"
                    placeholder="НДС %"
                    @update:model-value="onVatRateChange(idx, $event)" />
                </td>
                <td v-if="showContractorColumn" :style="resizeStyle('contractor')">
                  <v-autocomplete
                    :model-value="item.contractor_id ? contractors.find(c => c.id === item.contractor_id) || null : null"
                    :items="contractors" item-title="name" item-value="id" return-object
                    variant="outlined" density="compact" clearable auto-select-first hide-details
                    class="my-1" :custom-filter="contractorFilter" :loading="contractorLookupLoading[idx] === true"
                    :menu-props="{ maxWidth: 500 }" placeholder="Поставщик. Поиск по названию или ИНН..."
                    :disabled="props.readonly"
                    @update:search="(s: string) => onContractorSearchInput(idx, s)"
                    @update:model-value="(v: Contractor | null) => onItemContractorSelect(idx, v)"
                  >
                    <template #item="{ item: i, props: itemProps }">
                      <v-list-item v-bind="itemProps" :title="undefined">
                        <template #title><span style="white-space:normal;word-break:break-word;line-height:1.4">{{ i.raw.name }}</span></template>
                        <template #subtitle><span v-if="i.raw.inn" class="text-caption">ИНН: {{ i.raw.inn }}</span></template>
                      </v-list-item>
                    </template>
                    <template #append-inner>
                      <v-btn icon="mdi-account-plus" size="x-small" variant="text" color="teal"
                        title="Добавить контрагента" :disabled="props.readonly"
                        @click.stop="openContractorQuickCreate(idx)" />
                    </template>
                    <template #no-data>
                      <v-list-item>
                        <v-alert type="info" density="compact" variant="tonal" class="text-caption ma-0">Введите ИНН (10 или 12 цифр) — данные подтянутся из ФНС автоматически.</v-alert>
                      </v-list-item>
                    </template>
                  </v-autocomplete>
                  <div v-if="item.receipt_id" class="text-caption text-medium-emphasis mt-1 d-flex align-center gap-1">
                    <v-icon size="12">mdi-receipt</v-icon>
                    <span>из чека #{{ item.receipt_id }}</span>
                  </div>
                </td>
                <td>
                  <v-btn icon="mdi-delete-outline" variant="text" size="small" color="error"
                    :disabled="props.readonly" @click="removeItem(idx)" />
                </td>
              </tr>
              <tr v-if="!localItems.length">
                <td :colspan="showContractorColumn ? 11 : 10" class="text-center text-medium-emphasis py-4">
                  Нет позиций. Нажмите «Добавить позицию».
                </td>
              </tr>
            </tbody>
            <tfoot v-if="localItems.length">
              <tr>
                <td colspan="7" class="text-right pr-3 py-2 text-caption font-weight-bold">НМЦД итого:</td>
                <td class="py-2 font-weight-bold text-blue-darken-2">
                  {{ internalTotalNmck.toLocaleString('ru-RU') }} ₽
                </td>
                <td :colspan="showContractorColumn ? 3 : 2"></td>
              </tr>
            </tfoot>
          </v-table>
        </div>
      </template>
    </template>

    <!-- Wish shape table -->
    <template v-else>
      <div class="overflow-x-auto">
        <v-table density="compact">
          <thead>
            <tr>
              <th style="width:36px;padding:0 4px;text-align:center">
                <v-checkbox :model-value="allItemsSelected" density="compact" hide-details :rules="[]"
                  :indeterminate="selectedItemIdxs.length > 0 && !allItemsSelected"
                  @update:model-value="toggleSelectAll" />
              </th>
              <th style="width:36px;text-align:center;color:#888;font-size:12px">№</th>
              <th style="min-width:380px">Наименование</th>
              <th style="min-width:150px">Тип</th>
              <th style="min-width:120px">Кол-во</th>
              <th style="min-width:120px">Ед. изм.</th>
              <th style="min-width:140px">Цена ед., ₽</th>
              <th style="min-width:140px">Сумма, ₽</th>
              <th style="width:48px"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(item, idx) in localItems" :key="idx">
              <td style="width:36px;padding:0 4px;text-align:center">
                <v-checkbox :model-value="selectedItemIdxs.includes(idx)" density="compact" hide-details :rules="[]"
                  @update:model-value="(val: boolean | null) => toggleItemSelect(idx, val)" />
              </td>
              <td style="width:36px;text-align:center;color:#888;font-size:12px;font-weight:500">{{ idx + 1 }}</td>
              <td style="min-width:380px">
                <div class="d-flex align-center gap-1">
                  <v-tooltip v-if="item._photo_url" location="right">
                    <template #activator="{ props: tip }">
                      <v-avatar v-bind="tip" size="36" rounded="sm" class="flex-shrink-0" style="cursor:pointer;overflow:hidden">
                        <img :src="item._photo_url" style="width:36px;height:36px;object-fit:cover;display:block" />
                      </v-avatar>
                    </template>
                    <img :src="item._photo_url" style="width:200px;height:200px;object-fit:cover;border-radius:8px;display:block" />
                  </v-tooltip>
                  <v-icon v-else size="28" class="flex-shrink-0 text-medium-emphasis">mdi-package-variant</v-icon>

                  <v-tooltip v-if="item.item_name && !item.product_id"
                    text="Позиция не привязана к каталогу" location="top">
                    <template #activator="{ props: tip }">
                      <v-icon v-bind="tip" size="18" color="warning" class="flex-shrink-0">mdi-alert</v-icon>
                    </template>
                  </v-tooltip>

                  <v-textarea
                    v-model="item.item_name"
                    density="compact"
                    variant="outlined"
                    hide-details
                    clearable
                    readonly
                    rows="1"
                    auto-grow
                    class="my-1"
                    style="cursor:pointer;min-width:240px"
                    placeholder="Нажмите для выбора..."
                    :disabled="props.readonly"
                    @click="openProductPicker(idx)"
                    @click:clear.stop="clearItem(idx)"
                  />
                  <v-tooltip v-if="item.item_name" :text="item.product_id ? 'Редактировать товар в каталоге' : 'Создать товар в каталоге из этой позиции'" location="top">
                    <template #activator="{ props: tip }">
                      <v-btn v-bind="tip" icon="mdi-pencil-outline" size="x-small" variant="tonal"
                        color="teal" class="flex-shrink-0 ml-1" :disabled="props.readonly"
                        @click.stop="openQuickProductEdit(item)" />
                    </template>
                  </v-tooltip>
                </div>
                <!-- Phase 26-X: inline contractor picker in wish table -->
                <v-autocomplete
                  :model-value="item.contractor_id ? contractors.find(c => c.id === item.contractor_id) || null : null"
                  :items="contractors"
                  :custom-filter="contractorFilter"
                  item-title="name"
                  item-value="id"
                  return-object
                  density="compact"
                  variant="outlined"
                  hide-details
                  clearable
                  class="mt-1"
                  style="min-width:180px"
                  placeholder="Контрагент (магазин)..."
                  prepend-inner-icon="mdi-store"
                  no-data-text="Не найден"
                  :disabled="props.readonly"
                  @update:model-value="(v: Contractor | null) => onItemContractorSelect(idx, v)"
                  @update:search="(s: string) => onContractorSearchInput(idx, s)"
                >
                  <template #no-data>
                    <v-list-item>
                      <v-alert type="warning" density="compact" variant="tonal" class="text-caption ma-0">
                        Контрагент не найден в БД.
                      </v-alert>
                      <v-btn size="x-small" color="primary" variant="tonal" class="mt-1" prepend-icon="mdi-plus"
                        @click.stop="openContractorQuickCreate(idx)">
                        Создать нового
                      </v-btn>
                    </v-list-item>
                  </template>
                </v-autocomplete>
              </td>
              <td>
                <v-select v-model="item.item_type"
                  :items="props.allowedItemTypes.map(t => ({ value: t, title: t.charAt(0).toUpperCase() + t.slice(1) }))"
                  item-title="title" item-value="value" density="compact" variant="outlined"
                  hide-details class="my-1" :disabled="props.readonly" />
              </td>
              <td>
                <v-text-field v-model.number="item.quantity" type="number" density="compact"
                  variant="outlined" hide-details class="my-1" :disabled="props.readonly"
                  @update:model-value="calcItemTotal(idx)" />
              </td>
              <td>
                <v-combobox v-model="item.unit" :items="UNIT_OPTIONS" density="compact" variant="outlined"
                  hide-details class="my-1" :disabled="props.readonly" />
              </td>
              <td>
                <v-text-field v-model.number="item.unit_price" type="number" density="compact"
                  variant="outlined" hide-details class="my-1" :disabled="props.readonly"
                  @update:model-value="calcItemTotal(idx)" />
              </td>
              <td>
                <v-text-field :model-value="item.total_price ?? ''" readonly density="compact"
                  variant="outlined" hide-details bg-color="grey-lighten-4" class="my-1" />
              </td>
              <td>
                <v-btn icon="mdi-delete-outline" variant="text" size="small" color="error"
                  :disabled="props.readonly"
                  @click="removeItem(idx)" />
              </td>
            </tr>
            <tr v-if="!localItems.length">
              <td colspan="9" class="text-center text-medium-emphasis py-4">
                Нет позиций. Нажмите «Добавить позицию».
              </td>
            </tr>
          </tbody>
          <tfoot v-if="localItems.length">
            <tr>
              <td colspan="6" class="text-right pr-3 py-2 text-caption font-weight-bold">НМЦД итого:</td>
              <td class="py-2 font-weight-bold text-blue-darken-2">
                {{ internalTotalNmck.toLocaleString('ru-RU') }} ₽
              </td>
              <td colspan="2"></td>
            </tr>
          </tfoot>
        </v-table>
      </div>
    </template>

    <!-- Bottom action buttons -->
    <div v-if="!props.readonly" class="d-flex gap-2 mt-3 flex-wrap">
      <v-btn variant="tonal" prepend-icon="mdi-plus" size="small" @click="addItem">
        Добавить позицию
      </v-btn>
      <v-btn v-if="props.supportsFullProductDialog"
        variant="outlined" prepend-icon="mdi-package-variant-plus" size="small" color="primary"
        @click="openFullProduct(-1)">
        Добавить товар в каталог
      </v-btn>
    </div>

    <!-- ===== Product picker dialog ===== -->
    <v-dialog v-model="productPickerDialog" max-width="720" :fullscreen="display.smAndDown" scrollable>
      <v-card>
        <v-card-title class="text-h6 pt-4 px-4 px-sm-6 d-flex align-center justify-space-between">
          <span>Выбрать товар из каталога</span>
          <v-btn icon="mdi-close" variant="text" size="small" @click="productPickerDialog = false" />
        </v-card-title>
        <v-card-text class="px-4 pb-2">
          <v-text-field
            v-model="productPickerSearch"
            prepend-inner-icon="mdi-magnify"
            label="Поиск"
            placeholder="Наименование, описание или тип"
            variant="outlined" density="compact" clearable hide-details autofocus
            class="mb-3"
          />
          <div v-if="!productPickerResults.length" class="text-center text-medium-emphasis py-8">
            <v-icon icon="mdi-package-variant-closed" size="40" class="mb-2" />
            <div>Ничего не найдено</div>
            <v-btn class="mt-3" variant="tonal" color="primary" prepend-icon="mdi-plus"
              @click="createProductFromPicker">
              Добавить в каталог{{ productPickerSearch.length <= 30 ? ': «' + productPickerSearch + '»' : '' }}
            </v-btn>
          </div>
          <v-table v-else density="compact" hover>
            <thead>
              <tr>
                <th style="width:48px"></th>
                <th>Наименование</th>
                <th style="width:110px">Тип</th>
                <th style="width:130px;text-align:right">Цена, ₽</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in productPickerResults" :key="p.id"
                style="cursor:pointer" @click="selectFromPicker(p)">
                <td>
                  <v-avatar size="36" rounded="sm" class="my-1" style="overflow:hidden">
                    <img v-if="productPhotoSrc(p)" :src="productPhotoSrc(p)!" style="width:36px;height:36px;object-fit:cover;display:block" @error="($event.target as HTMLImageElement).style.display='none'" />
                    <v-icon v-else icon="mdi-package-variant" color="grey" size="20" />
                  </v-avatar>
                </td>
                <td>
                  <div class="font-weight-medium">{{ p.name }}</div>
                  <div v-if="p.description" class="text-caption text-medium-emphasis"
                    style="max-width:340px;white-space:normal;line-height:1.3">
                    {{ p.description.slice(0, 90) }}{{ p.description.length > 90 ? '…' : '' }}
                  </div>
                </td>
                <td>
                  <v-chip v-if="p.product_type" size="x-small" variant="tonal">{{ p.product_type }}</v-chip>
                </td>
                <td style="text-align:right" class="font-weight-medium text-blue-darken-2">
                  {{ p.price ? Number(p.price).toLocaleString('ru-RU') + ' ₽' : '—' }}
                </td>
              </tr>
            </tbody>
          </v-table>
        </v-card-text>
        <v-card-actions class="px-4 pb-3 d-flex flex-wrap" style="gap:6px">
          <v-btn v-if="props.supportsFullProductDialog"
            variant="tonal" color="teal" size="small" prepend-icon="mdi-plus"
            @click="createProductFromPicker" class="flex-grow-0">
            Новый товар
          </v-btn>
          <span class="text-caption text-medium-emphasis">{{ productPickerResults.length }} позиций</span>
          <v-spacer />
          <v-btn variant="text" size="small" @click="productPickerDialog = false">Отмена</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ===== Full product card dialog ===== -->
    <v-dialog v-if="props.supportsFullProductDialog" v-model="fullProductDialog" max-width="700" :fullscreen="display.smAndDown" scrollable>
      <v-card>
        <v-card-title class="text-h6 pt-4 px-4 px-sm-6">
          {{ fullProductEditingId ? 'Редактировать товар / услугу' : 'Добавить товар / услугу в каталог' }}
        </v-card-title>
        <v-card-text class="px-4 px-sm-6">
          <v-row dense>
            <v-col cols="12">
              <v-combobox
                v-model="fullProductForm.name"
                v-model:search="fullProductNameSearch"
                :items="fullProductNameSuggestions"
                no-filter
                label="Наименование *"
                variant="outlined" density="compact"
                autofocus
                :rules="[(v: string) => !!v || 'Обязательное поле']"
                :hint="isFullProductDuplicate ? '⚠ Товар с таким названием уже есть в каталоге' : ''"
                :persistent-hint="isFullProductDuplicate"
              >
                <template #item="{ item: listItem, props: itemProps }">
                  <v-list-item v-bind="itemProps" :title="listItem.raw">
                    <template #append>
                      <v-chip size="x-small" color="warning" variant="tonal">уже есть</v-chip>
                    </template>
                  </v-list-item>
                </template>
              </v-combobox>
            </v-col>
            <v-col cols="12" md="4">
              <v-select v-model="fullProductForm.item_kind"
                :items="[{ title: 'Товар', value: 'товар' }, { title: 'Услуга', value: 'услуга' }]"
                label="Товар / Услуга" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12" md="4">
              <v-combobox v-model="fullProductForm.product_type"
                :items="fullProductTypeOptions"
                label="Тип товара" variant="outlined" density="compact" clearable
                hint="Напр.: Ноутбук, Тренажёр" persistent-hint />
            </v-col>
            <v-col cols="12" md="4">
              <v-combobox v-model="fullProductForm.category"
                :items="fullProductCategoryOptions"
                label="Категория *"
                :rules="[v => (!!v && String(v).trim().length > 0) || 'Категория обязательна']"
                required
                variant="outlined" density="compact"
                hint="Выберите или введите новую (обязательное поле)" persistent-hint />
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field v-model.number="fullProductForm.price" label="Цена за ед., ₽" type="number"
                variant="outlined" density="compact"
                :readonly="fullAvgPrice !== null"
                :hint="fullAvgPrice !== null ? 'Среднее из ссылок — ' + fullAvgPrice.toLocaleString('ru-RU') + ' ₽' : 'Можно задать вручную или через ссылки'"
                persistent-hint />
            </v-col>
            <v-col cols="12" md="6">
              <v-switch v-model="fullProductForm.is_active" label="Активен" color="success" density="compact" hide-details class="mt-1" />
            </v-col>
            <v-col cols="12">
              <v-textarea v-model="fullProductForm.description" label="Описание" variant="outlined"
                density="compact" rows="2" auto-grow />
            </v-col>
            <v-col v-if="props.supportsPhotoUpload" cols="12">
              <div class="text-subtitle-2 mb-2">Фото товара</div>
              <div v-if="fullProductPhotoPreview" class="mb-3">
                <img :src="fullProductPhotoPreview" style="max-width:100%;max-height:140px;object-fit:contain;display:block;border-radius:4px;border:1px solid #e0e0e0;background:#f5f5f5" />
              </div>
              <v-file-input
                v-model="fullProductPhotoFileList"
                label="Загрузить фото с компьютера"
                accept="image/jpeg,image/jpg,image/png,image/webp,image/gif"
                variant="outlined" density="compact" prepend-icon="mdi-camera" show-size clearable
                @update:model-value="onFullPhotoFileChange"
              />
              <v-text-field v-model="fullProductForm.photo_link" label="Или ссылка на фото" variant="outlined"
                density="compact" prepend-inner-icon="mdi-image-outline" class="mt-2"
                :disabled="!!fullProductPhotoFile" />
            </v-col>
            <v-col cols="12">
              <div class="text-subtitle-2 mb-2">
                Ссылки для сравнения цен
                <span v-if="fullAvgPrice !== null" class="text-caption font-weight-bold text-blue-darken-2 ml-2">
                  ср. {{ fullAvgPrice.toLocaleString('ru-RU') }} ₽
                </span>
              </div>
              <div v-for="(link, i) in fullProductForm.priceLinks" :key="i" class="d-flex gap-2 mb-2 align-center">
                <v-text-field v-model="link.url" :label="'Ссылка ' + (i + 1)" variant="outlined" density="compact"
                  hide-details prepend-inner-icon="mdi-link" class="flex-grow-1" />
                <v-text-field v-model.number="link.price" label="Цена, ₽" type="number"
                  variant="outlined" density="compact" hide-details style="max-width:140px" />
                <v-btn v-if="link.url" icon="mdi-open-in-new" variant="text" size="x-small" color="primary"
                  :href="link.url" target="_blank" />
                <v-btn icon="mdi-minus-circle" variant="text" size="x-small" color="error"
                  @click="fullProductForm.priceLinks.splice(i, 1)" />
              </div>
              <v-btn prepend-icon="mdi-plus" variant="tonal" size="small" color="primary"
                @click="fullProductForm.priceLinks.push({ url: '', price: null })">
                Добавить ссылку
              </v-btn>
            </v-col>
          </v-row>
        </v-card-text>
        <v-card-actions class="px-4 pb-4 d-flex flex-wrap" style="gap:8px">
          <v-spacer />
          <v-btn variant="text" @click="fullProductDialog = false">Отмена</v-btn>
          <v-btn color="primary" :loading="fullProductSaving"
            :disabled="!fullProductForm.category || !String(fullProductForm.category).trim()"
            @click="saveFullProduct">
            {{ fullProductEditingId ? 'Сохранить' : 'Добавить в каталог' }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ===== Items import dialog (Excel 2-step + Smart import) ===== -->
    <v-dialog v-model="itemsImportDialog" max-width="1400" scrollable>
      <v-card>
        <v-card-title class="pa-4 d-flex align-center">
          <v-icon :icon="isSmartMode ? 'mdi-brain' : 'mdi-package-variant-plus'" class="mr-2" />
          {{ isSmartMode ? 'Умный импорт позиций' : 'Импорт товаров из файла' }}
          <v-spacer />
          <v-chip v-if="importStep > 1 && !isSmartMode" size="small" color="primary" variant="tonal" class="ml-2">
            Шаг {{ importStep }} / 3
          </v-chip>
        </v-card-title>
        <v-divider />
        <v-card-text class="pa-4 pb-0">
          <v-btn-toggle :model-value="isSmartMode" @update:model-value="switchImportMode" density="compact" mandatory color="primary" class="mb-2">
            <v-btn :value="true" prepend-icon="mdi-brain">Авто (умный)</v-btn>
            <v-btn :value="false" prepend-icon="mdi-tune-vertical">Вручную (выбор листа и колонок)</v-btn>
          </v-btn-toggle>
          <div class="text-caption text-medium-emphasis mb-2">
            Если автоматический режим не распознал позиции (например, mojibake-кодировка или скан PDF без OCR) — переключитесь в ручной режим.
          </div>
        </v-card-text>
        <v-card-text class="pa-4">
          <!-- Excel import: Step 1 - Upload file -->
          <template v-if="!isSmartMode && importStep === 1">
            <v-alert type="info" variant="tonal" density="compact" class="mb-3" icon="mdi-information-outline">
              <div class="text-body-2">
                <strong>Поддерживаемые форматы:</strong> Excel (.xlsx, .xls), Word (.docx), PDF<br>
                <strong>Название листа:</strong> любое — система прочитает первый лист (или предложит выбрать)<br>
                <strong>Заголовки столбцов:</strong> определяются автоматически по ключевым словам
                (наименование, количество, цена, сумма и т.д.). Могут быть в любой строке.<br>
                <strong>На следующем шаге</strong> вы увидите распознанные столбцы и укажете соответствие полей.
              </div>
            </v-alert>
            <FileDropZone v-model="itemsImportFile"
              accept=".xlsx,.xls,.pdf,.docx,.doc,.html,.htm"
              hint="Excel, PDF, Word, HTML — перетащите или нажмите"
              class="mb-2" />
          </template>

          <!-- Excel import: Step 2 - Column mapping -->
          <template v-if="!isSmartMode && importStep === 2 && importPreviewData">
            <v-alert v-if="currentSheetData" type="info" variant="tonal" density="compact" class="mb-3" icon="mdi-file-table-outline">
              <strong>Лист:</strong> {{ currentSheetData.name }} ({{ currentSheetData.total_rows }} строк данных)
            </v-alert>
            <v-select
              v-if="importPreviewData.sheets.length > 1"
              v-model="importSelectedSheet"
              :items="importPreviewData.sheets.map((s: any) => ({ title: `${s.name} (${s.total_rows} строк)`, value: s.name }))"
              label="Сменить лист" variant="outlined" density="compact" class="mb-3"
            />

            <!-- COLUMN TABLE: headers on top, cards below -->
            <div class="imap-grid">
              <div v-for="target in TARGET_FIELDS" :key="target.value"
                class="imap-col"
                :class="{
                  'imap-col--over': dragOverTarget === target.value,
                  'imap-col--filled': isTargetFilled(target.value),
                  'imap-col--required': target.required && !isTargetFilled(target.value),
                }"
                @dragover.prevent="dragOverTarget = target.value"
                @dragleave="dragOverTarget = null"
                @drop.prevent="onDropToTarget(target.value, $event)">
                <div class="imap-col-hdr">{{ target.title }}<span v-if="target.required" style="color:#e53935">*</span></div>
                <div class="imap-col-body">
                  <div v-if="isTargetFilled(target.value)"
                    class="imap-card"
                    draggable="true"
                    @dragstart="onDragStart(dragMapping[target.value] as number, $event)">
                    <div class="imap-card-row">
                      <span class="imap-card-name">{{ getColumnLabel(dragMapping[target.value] as number) }}</span>
                      <button class="imap-card-x" @click.stop="unmapTarget(target.value)">×</button>
                    </div>
                    <div class="imap-card-samples">{{ getSamples(dragMapping[target.value] as number).join(', ') || '—' }}</div>
                  </div>
                  <div v-else class="imap-col-empty">—</div>
                </div>
              </div>
            </div>

            <!-- NOT RESOLVED section -->
            <div class="imap-unresolved mt-3"
              :class="{ 'imap-unresolved--over': dragOverTarget === '_unresolved' }"
              @dragover.prevent="dragOverTarget = '_unresolved'"
              @dragleave="dragOverTarget = null"
              @drop.prevent="onDropToUnresolved($event)">
              <span class="imap-unresolved-label">Не определилось</span>
              <div class="d-flex gap-2 flex-wrap mt-1">
                <template v-for="(_, colIdx) in currentSheetHeaders" :key="colIdx">
                  <div v-if="!isMapped(colIdx) && !isIgnored(colIdx)"
                    class="imap-card imap-card--free"
                    draggable="true"
                    @dragstart="onDragStart(colIdx, $event)">
                    <div class="imap-card-row">
                      <span class="imap-card-name">{{ getColumnLabel(colIdx) }}</span>
                      <button class="imap-card-x imap-card-x--grey" title="Убрать" @click.stop="ignoreColumn(colIdx)">×</button>
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
          <template v-if="!isSmartMode && importStep === 3">
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
          <template v-if="isSmartMode">
            <v-alert type="info" variant="tonal" density="compact" class="mb-3" icon="mdi-information-outline">
              <div class="text-body-2">
                <strong>Умный импорт</strong> — автоматически распознаёт наименования, количество и цены из файла.<br>
                Поддерживаются Excel, Word, PDF, HTML, <strong>JPG/PNG/WEBP</strong> (фото чека с QR ФНС или текстом).<br>
                <span class="text-medium-emphasis">Для фото чека: лучший результат даёт QR-код ФНС (приложение «Проверка чека»). OCR-распознавание текста менее точно.</span>
              </div>
            </v-alert>
            <div class="mb-4">
              <v-file-input
                v-model="smartImportFileList"
                label="Выберите файл для умного импорта"
                accept=".xlsx,.xls,.pdf,.docx,.doc,.html,.htm,.jpg,.jpeg,.png,.webp,.heic"
                variant="outlined" density="compact" prepend-icon="mdi-file-document-outline"
                show-size clearable
                @update:model-value="onSmartFileChange"
              />
            </div>

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
                prepend-icon="mdi-tune" @click="showMappingPanel = !showMappingPanel">
                {{ showMappingPanel ? 'Скрыть' : 'Настроить' }} маппинг столбцов
              </v-btn>
              <v-chip v-if="columnMappingApplied" color="success" variant="tonal" size="small" class="mb-3">
                Маппинг применён
              </v-chip>

              <div v-if="showMappingPanel" class="mb-3 pa-3" style="border:1px solid #e0e0e0;border-radius:8px">
                <div class="text-caption font-weight-bold mb-2">Сопоставление столбцов файла → полей CRM</div>
                <v-row dense>
                  <v-col v-for="(label, field) in CRM_MAPPING_FIELDS" :key="field" cols="12" md="4">
                    <v-select
                      v-model="columnFieldMapping[field]"
                      :items="crmFieldSelectItems"
                      :label="label"
                      item-title="title" item-value="value"
                      variant="outlined" density="compact" hide-details class="mb-2"
                    />
                  </v-col>
                </v-row>
                <v-btn color="primary" size="small" variant="flat" @click="applyColumnMapping">
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

            <v-alert v-if="smartImportResult" type="success" density="compact" class="mb-2">
              Добавлено позиций: <strong>{{ smartImportResult.added }}</strong>
            </v-alert>
          </template>

        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-btn v-if="!isSmartMode && importStep > 1 && importStep < 3" variant="text" @click="importStep--">
            <v-icon icon="mdi-arrow-left" class="mr-1" /> Назад
          </v-btn>
          <v-spacer />
          <v-btn variant="text" @click="closeImportDialog">Закрыть</v-btn>

          <!-- Excel import buttons -->
          <template v-if="!isSmartMode">
            <v-btn v-if="importStep === 1" color="primary" variant="flat"
              :loading="itemsImportLoading"
              :disabled="!itemsImportFile"
              @click="doImportPreview">
              Далее
            </v-btn>
            <v-btn v-if="importStep === 2 && (importPreviewData?.sheets?.length ?? 0) > 1"
              color="success" variant="tonal"
              :loading="itemsImportLoading"
              prepend-icon="mdi-table-multiple"
              @click="doImportAllTables">
              Импортировать ВСЕ таблицы ({{ importPreviewData?.sheets?.length }})
            </v-btn>
            <v-btn v-if="importStep === 2" color="success" variant="flat"
              :loading="itemsImportLoading"
              :disabled="!mappingHasName"
              @click="doMappedImport">
              Импортировать
            </v-btn>
            <v-btn v-if="importStep === 3" color="primary" variant="flat"
              @click="closeImportDialog">
              Готово
            </v-btn>
          </template>

          <!-- Smart import buttons -->
          <template v-if="isSmartMode">
            <v-btn v-if="!smartImportPreview" color="primary" variant="flat"
              :loading="smartImportLoading"
              :disabled="!smartImportFile"
              @click="doSmartPreview">
              Распознать
            </v-btn>
            <v-btn v-if="smartImportPreview && smartImportPreview.length && !smartImportResult"
              color="success" variant="flat"
              :loading="smartImportLoading"
              @click="doSmartImport">
              Добавить позиции
            </v-btn>
          </template>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ===== Contractor quick-create dialog (Phase 26-X) ===== -->
    <v-dialog v-model="contractorPickerDialog" max-width="480" persistent>
      <v-card>
        <v-card-title class="text-h6 pt-4 px-4 d-flex align-center justify-space-between">
          <span><v-icon icon="mdi-store-plus" class="mr-2" />Новый контрагент</span>
          <v-btn icon="mdi-close" variant="text" size="small" @click="contractorPickerDialog = false" />
        </v-card-title>
        <v-card-text class="px-4 pb-2">
          <v-alert type="info" density="compact" variant="tonal" class="mb-3 text-caption">
            Контрагент не найден в БД. Заполните минимальные данные для создания.
          </v-alert>
          <v-text-field
            v-model="contractorPickerForm.name"
            label="Наименование *"
            variant="outlined" density="compact"
            :rules="[v => !!v || 'Обязательное поле']"
            class="mb-2"
          />
          <v-text-field
            v-model="contractorPickerForm.inn"
            label="ИНН"
            variant="outlined" density="compact" class="mb-2"
          />
          <v-text-field
            v-model="contractorPickerForm.kpp"
            label="КПП"
            variant="outlined" density="compact" class="mb-2"
          />
          <v-text-field
            v-model="contractorPickerForm.address"
            label="Адрес"
            variant="outlined" density="compact"
          />
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="contractorPickerDialog = false">Отмена</v-btn>
          <v-btn color="primary" :loading="contractorPickerSaving"
            :disabled="!contractorPickerForm.name.trim()"
            @click="saveContractorQuickCreate">
            Создать
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

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

    <!-- ===== Snackbar ===== -->
    <v-snackbar v-model="snack.show" :color="snack.color" :timeout="snack.color === 'error' ? -1 : 3500" location="bottom right" multi-line>
      {{ snack.text }}
      <template #actions>
        <v-btn variant="text" size="small" @click="snack.show = false">OK</v-btn>
      </template>
    </v-snackbar>
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
import type { ContractItem } from '@/types/contractItem'
import { copyFromPurchase as apiCopyFromPurchase } from '@/api/contractItems'
import { useResizableColumns } from '@/composables/useResizableColumns'

// ── Interfaces ───────────────────────────────────────────────────────────────

interface Contractor {
  id: number
  name: string
  inn?: string | null
  kpp?: string | null
  address?: string | null
}

interface EditorItem {
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
  // UI-local state (stripped by parent before save):
  _selectedProduct?: Product | null
  _photo_url?: string
  _description?: string
  _description_44fz?: string
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
const COUNTRIES = ['Российская Федерация', 'Беларусь', 'Казахстан', 'Китай', 'Германия', 'США', 'Япония', 'Турция', 'Индия']

// Fix 3 + Fix 4/5: VAT options (5/10/22/Без НДС/custom)
const VAT_RATE_OPTIONS = [
  { title: '5%', value: '5%' },
  { title: '10%', value: '10%' },
  { title: '22%', value: '22%' },
  { title: 'Без НДС', value: null },
]

function parseVatRatePercent(rate: string | null | undefined): number {
  if (!rate || rate === 'Без НДС') return 0
  const m = String(rate).match(/^(\d+(?:\.\d+)?)\s*%?$/)
  return m ? parseFloat(m[1]) : 0
}

// Phase 27.1.16: формулы НДС переопределены — unit_price / total_price из чека ФФД ВКЛЮЧАЮТ НДС.
// vatAmount = выделение НДС из суммы С НДС: total * pct / (100 + pct).
// Пример: total=392 ₽ с НДС 22% → vatAmount = 392 * 22 / 122 = 70,69 ₽.
// totalWithVat возвращает total_price напрямую (он уже с НДС).
function vatAmount(item: EditorItem | ContractItem): number {
  const total = Number((item as any).total_price ?? (item as any).total ?? 0)
  const pct = parseVatRatePercent((item as any).vat_rate)
  if (pct <= 0) return 0
  return Number((total * pct / (100 + pct)).toFixed(2))
}

function totalWithVat(item: EditorItem | ContractItem): number {
  // total_price УЖЕ с НДС (стандарт: цена из чека/договора включает НДС)
  return Number((item as any).total_price ?? (item as any).total ?? 0)
}

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

function fmtRub(n: number | null | undefined): string {
  if (n == null || isNaN(Number(n))) return '—'
  return Number(n).toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' ₽'
}

function onVatRateChange(idx: number, v: any) {
  const item = localItems.value[idx]
  if (!item) return
  if (v == null || v === '' || v === 'Без НДС') {
    item.vat_rate = null
  } else {
    const s = String(v)
    // Normalize: if user typed just a number without %, add %
    item.vat_rate = /^\d+(?:\.\d+)?$/.test(s.trim()) ? s.trim() + '%' : s
  }
  calcItemTotal(idx)
}

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
  allowedItemTypes?: string[]
  defaultItemType?: string
  defaultUnit?: string
  defaultCountry?: string
  supportsExcelImport?: boolean
  supportsSmartImport?: boolean
  supportsFullProductDialog?: boolean
  supportsPhotoUpload?: boolean
  readonly?: boolean
  vatMode?: 'uniform' | 'per_item'          // Phase 26-U-3: НДС режим
  uniformVatRate?: string | null             // Phase 26-U-3: ставка для uniform режима
  formMode?: string                          // Phase 26-X: 'advance_report' → показывать колонку Контрагент
  contractors?: Contractor[]                 // Phase 26-JJ: shared contractors state from parent
  // F-PIF1/F-PIF2: per-item FEO selector props
  feoPerItem?: boolean
  level2Id?: number | null
  subsidyId?: number | null
  purchaseIdFeo?: number | null
}>(), {
  contractItems: () => [],
  showContractColumns: false,
  unifiedStagesView: false,
  purchaseStatus: '',
  allowedItemTypes: () => ['товар', 'услуга', 'работа'],
  defaultItemType: 'товар',
  defaultUnit: 'шт.',
  defaultCountry: 'Россия',
  supportsExcelImport: true,
  supportsSmartImport: true,
  supportsFullProductDialog: true,
  supportsPhotoUpload: true,
  readonly: false,
  purchaseId: null,
  vatMode: 'uniform',
  uniformVatRate: null,
  formMode: 'default',
  feoPerItem: false,
  level2Id: null,
  subsidyId: null,
  purchaseIdFeo: null,
})

// Phase 27.1.1: stagesEnabled — either the new prop or backward-compat alias
const stagesEnabled = computed(() => props.unifiedStagesView || props.showContractColumns)

// ── F-PIF2: per-item FEO residuals ───────────────────────────────────────────
interface FeoResidual {
  feo_item_id: number
  name: string
  category_id: number
  planned_amount: number
  used_amount: number
  residual: number
}
const feoResiduals = ref<FeoResidual[]>([])

watch(
  () => [props.subsidyId, props.purchaseIdFeo, props.level2Id] as const,
  async ([subsidyId, purchaseIdFeo, level2Id]) => {
    if (!subsidyId) { feoResiduals.value = []; return }
    try {
      const qs = purchaseIdFeo != null ? `&exclude_purchase_id=${purchaseIdFeo}` : ''
      const all = await apiFetch<FeoResidual[]>(`/feo-planned-items/residuals?subsidy_id=${subsidyId}${qs}`)
      feoResiduals.value = level2Id != null ? all.filter(x => x.category_id === level2Id) : all
    } catch {
      feoResiduals.value = []
    }
  },
  { immediate: true },
)

function getFeoResidual(itemId: number | undefined | null): FeoResidual | null {
  if (!itemId) return null
  return feoResiduals.value.find(r => r.feo_item_id === itemId) ?? null
}

function isOverBudget(row: EditorItem): boolean {
  if (!row.feo_planned_item_id) return false
  const r = getFeoResidual(row.feo_planned_item_id)
  if (!r) return false
  return (r.used_amount + Number(row.total_price || 0)) > r.planned_amount
}

function overBudgetDelta(row: EditorItem): number {
  const r = getFeoResidual(row.feo_planned_item_id)
  if (!r) return 0
  return (r.used_amount + Number(row.total_price || 0)) - r.planned_amount
}
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
}>()

// ── Local state ──────────────────────────────────────────────────────────────

const display = useDisplay()
const localItems = ref<EditorItem[]>([...props.modelValue])

// Duplicate merge dialog state
const dupMergeShow = ref(false)
const dupMergeGroups = ref<DupGroup[]>([])
// Pending items waiting for user decision in DuplicateMergeDialog
let _pendingMergeItems: EditorItem[] = []

watch(
  () => props.modelValue,
  (v) => { localItems.value = [...v] },
  { deep: true }
)

function emitUpdate() {
  emit('update:modelValue', [...localItems.value])
  emit('items-changed')
}

// ── Phase 27.1 D-04: Contract items side-by-side ─────────────────────────────

const localContractItems = ref<ContractItem[]>([...(props.contractItems || [])])

watch(
  () => props.contractItems,
  (v) => { localContractItems.value = [...(v || [])] },
  { deep: true },
)

function emitContractItemsUpdate() {
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

// Snackbar
const snack = reactive({ show: false, text: '', color: 'success' })
function showSnack(text: string, color = 'success') {
  snack.text = text; snack.color = color; snack.show = true
}

// Products catalogue
const products = ref<Product[]>([])

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
const { onResizeStart, resizeStyle } = useResizableColumns('purchase-items-editor', {
  name: 320, type: 120, qty: 90, unit: 90, price: 130, sum: 130,
  country: 150, contractor: 200, actions: 80,
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

// ── Items CRUD ────────────────────────────────────────────────────────────────

function addItem() {
  const newItem: EditorItem = {
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
    newItem.feo_planned_item_id = null
  }
  localItems.value.push(newItem)
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
    item.item_name = ''
    item.product_id = null
    item._selectedProduct = null
    item._photo_url = undefined
    item._description = undefined
    item._description_44fz = undefined
  } else if (typeof val === 'string') {
    item.item_name = val
    item.product_id = null
    item._selectedProduct = val
    item._photo_url = undefined
    item._description = undefined
    item._description_44fz = undefined
  } else {
    item.item_name = val.name || ''
    item.product_id = val.id
    item._selectedProduct = val
    item._photo_url = productPhotoSrc(val)
    item._description = val.description || undefined
    item._description_44fz = val.description_44fz || undefined
    if (val.product_type && !item.item_type) item.item_type = val.product_type
    if (!item.unit_price) {
      const bestPrice = val.contract_price ?? val.price
      if (bestPrice) {
        item.unit_price = Number(bestPrice)
        calcItemTotal(idx)
      }
    }
  }
  // Any explicit user action on the product field counts as confirmation.
  ;(item as any).match_confirmed = true
  emitUpdate()
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
  { value: 'item_name',   title: 'Наименование', required: true },
  { value: 'unit_price',  title: 'Цена за ед.',  required: false },
  { value: 'quantity',    title: 'Количество',    required: false },
  { value: 'unit',        title: 'Ед. изм.',      required: false },
  { value: 'total_price', title: 'Сумма',         required: false },
  { value: 'description', title: 'Описание',      required: false },
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
    item_name:   ['наименован', 'назван', 'описание выполн', 'описание оказ', 'товара', 'товар', 'предмет', 'name', 'продукц', 'описан'],
    description: ['характерист', 'тз', 'спецификац', 'specification'],
    quantity:    ['кол-во', 'количеств', 'объем', 'qty', 'кол.', 'кол '],
    unit_price:  ['цена (тариф)', 'цена', 'price', 'за единиц', 'за ед', 'тариф'],
    total_price: ['всего', 'сумм', 'итого', 'total', 'стоимость'],
    unit:        ['ед. изм', 'единиц', 'ед.изм', 'изм', 'unit', 'ед.'],
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
    item.feo_planned_item_id = null
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
        item_name: 'col_item_name',
        description: 'col_description',
        quantity: 'col_quantity',
        unit_price: 'col_unit_price',
        total_price: 'col_total_price',
        unit: 'col_unit',
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
      // Wish / no-pid context — build rows client-side
      const sheet = importPreviewData.value?.sheets?.find((s: any) => s.name === importSelectedSheet.value)
        ?? importPreviewData.value?.sheets?.[0]
      if (!sheet) { showSnack('Нет данных превью', 'error'); return }
      const headerOffset = sheet.header_row_offset ?? 0
      const dataRows = (sheet.sample as any[][]).slice(headerOffset + 1)
      const newItems: EditorItem[] = dataRows
        .filter(row => {
          const nameIdx = dragMapping.value['item_name']
          return nameIdx !== null && nameIdx !== undefined && String(row[nameIdx] ?? '').trim()
        })
        .map(row => buildEditorItemFromRow(row, dragMapping.value))
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
const smartImportPreview = ref<any[] | null>(null)
const smartImportColumns = ref<string[] | null>(null)
const smartImportResult = ref<{ added: number; matched_catalog: number; unmatched: number } | null>(null)

// ── Product match review dialog ───────────────────────────────────────────────
interface MatchCandidate {
  product_id: number
  name: string
  price: number | null
  score: number
  description?: string | null
  photo_url?: string | null
  item_type?: string | null
  category?: string | null
}
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
  item.product_id = candidate.product_id
  item.item_name = candidate.name
  item._description = candidate.description ?? undefined
  item._photo_url = candidate.photo_url ?? undefined
  if (candidate.item_type) item.item_type = candidate.item_type
  ;(item as any).match_confirmed = true
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
    }
    if (props.itemShape === 'purchase') {
      item.final_unit_price = null
      item.final_total = null
      item.feo_planned_item_id = null
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
    const resp = await fetch(`/api/purchases/${props.purchaseId}/items/import-smart?confirm=true`, {
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
</script>

<style scoped>
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
/* Phase 27.1.1: expand-row layout */
.summary-row:hover {
  background: rgba(0, 0, 0, 0.02);
}
.stage-row-wrapper td {
  background: #fafafa;
}
.nested-stages-table {
  border: 1px solid #e0e0e0;
  border-radius: 4px;
}
.nested-stages-table :deep(.v-text-field input),
.nested-stages-table :deep(.v-combobox input),
.nested-stages-table :deep(.v-text-field .v-field__input),
.nested-stages-table :deep(.v-combobox .v-field__input) {
  font-size: 12px !important;
  padding-top: 4px !important;
  padding-bottom: 4px !important;
  min-height: 32px !important;
}
.nested-stages-table :deep(.v-field) {
  --v-field-padding-start: 8px;
  --v-field-padding-end: 8px;
}
.stage-tz-row td {
  background: rgba(25, 118, 210, 0.04);
}
.stage-contract-row td {
  background: rgba(46, 125, 50, 0.04);
}
.stage-delivery-row td {
  background: rgba(156, 39, 176, 0.04);
}
.stage-delivery-empty td {
  opacity: 0.6;
}
/* F-PIF2: soft-warning при превышении FEO плана */
.feo-over-budget :deep(.v-field) {
  background: rgba(255, 193, 7, 0.08);
  border-color: rgba(255, 193, 7, 0.5);
}
</style>
