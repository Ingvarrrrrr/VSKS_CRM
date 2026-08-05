<template>
  <!-- Presentational purchase-shape STAGES table (expand-row: ТЗ / Договор / Поставка).
       Holds NO business state — props in, events out. Parent owns localItems,
       localContractItems, expanded, every helper and every computed. The ТЗ sub-row
       mutates shared `item.*` objects directly via v-model (same pattern as Flat/Wish);
       contract (Договор) and delivery (Поставка) data is read via getContractItemFor()
       and written back via update-contract-field / contract-vat-change emits, so no
       contract-item state lives in this child.
       Extracted from PurchaseItemsEditor.vue (Layer 3). -->
  <div>
    <v-table density="compact">
      <thead>
        <tr>
          <th style="width:36px"></th>
          <th style="width:36px;padding:0 4px;text-align:center">
            <v-checkbox :model-value="allItemsSelected" density="compact" hide-details :rules="[]"
              :indeterminate="selectedItemIdxs.length > 0 && !allItemsSelected"
              @update:model-value="(v: boolean | null) => emit('toggle-select-all', v)" />
          </th>
          <th style="width:36px;text-align:center;color:#888;font-size:12px">№</th>
          <th>Наименование</th>
          <th style="width:90px">Кол-во</th>
          <th style="width:110px">Цена, ₽</th>
          <th style="width:120px">Сумма, ₽</th>
          <th style="min-width:220px">Суммы стадий</th>
          <th style="width:48px">Матч</th>
          <th style="width:80px"></th>
        </tr>
      </thead>
      <tbody>
        <template v-for="(item, idx) in items" :key="item._uid ?? idx">
          <!-- Summary row -->
          <tr class="summary-row" style="cursor:pointer" @click="emit('toggle-expand', idx)">
            <td style="width:36px;text-align:center">
              <v-btn
                :icon="expanded[idx] ? 'mdi-chevron-up' : 'mdi-chevron-down'"
                size="small" variant="text" density="compact"
                @click.stop="emit('toggle-expand', idx)"
              />
            </td>
            <td style="width:36px;padding:0 4px;text-align:center" @click.stop>
              <v-checkbox :model-value="selectedItemIdxs.includes(idx)" density="compact" hide-details :rules="[]"
                @update:model-value="(val: boolean | null) => emit('toggle-item-select', idx, val)" />
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
                <span class="text-body-2" style="white-space:normal;line-height:1.3;word-break:break-word">{{ summaryName(idx) || '—' }}</span>
              </div>
            </td>
            <td @click.stop>
              <v-text-field v-model.number="item.quantity" type="number" density="compact"
                variant="outlined" hide-details class="my-1 summary-num-input" :disabled="readonly"
                @update:model-value="emit('calc-item-total', idx)" />
            </td>
            <td @click.stop>
              <v-text-field
                :model-value="formatNumber(item.unit_price)"
                density="compact" variant="outlined" hide-details class="my-1 summary-num-input"
                :disabled="readonly"
                @update:model-value="(v: string) => { item.unit_price = parseNumber(v) as any; emit('calc-item-total', idx) }"
              />
            </td>
            <td class="font-weight-medium" style="font-size:12px;white-space:nowrap">{{ fmtRub(totalWithVat(item)) }}</td>
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
                      color="warning" :disabled="readonly"
                      @click.stop="emit('confirm-match', idx)" />
                  </template>
                </v-tooltip>
                <!-- P1-B: кнопка перепривязки к каталогу -->
                <v-tooltip text="Изменить привязку к каталогу" location="top">
                  <template #activator="{ props: tip }">
                    <v-btn v-bind="tip" icon="mdi-link-variant-plus" size="x-small" variant="text"
                      color="teal" :disabled="readonly"
                      @click.stop="emit('open-repick-dialog', idx)" />
                  </template>
                </v-tooltip>
                <v-btn icon="mdi-delete-outline" variant="text" size="small" color="error"
                  :disabled="readonly"
                  @click.stop="emit('remove-item', idx)" />
              </div>
            </td>
          </tr>
          <!-- Expanded sub-rows -->
          <tr v-if="expanded[idx]" class="stage-row-wrapper">
            <td colspan="10" style="padding:0 0 8px 48px">
              <v-table density="compact" class="nested-stages-table">
                <thead>
                  <tr>
                    <th style="width:90px">Стадия</th>
                    <th style="min-width:220px">Наименование</th>
                    <th style="width:90px">Кол-во</th>
                    <th style="width:80px">Ед.</th>
                    <th style="min-width:110px">Цена ед., ₽</th>
                    <th v-if="showVatColumnsInExpandRow" style="width:90px">НДС %</th>
                    <th v-if="showVatColumnsInExpandRow" style="min-width:100px">НДС сумма, ₽</th>
                    <th style="min-width:110px">{{ showVatColumnsInExpandRow ? 'Сумма с НДС, ₽' : 'Сумма, ₽' }}</th>
                    <th style="min-width:180px">Контрагент</th>
                  </tr>
                </thead>
                <tbody>
                  <!-- ТЗ sub-row -->
                  <tr class="stage-tz-row">
                    <td><v-chip color="info" size="x-small" variant="tonal">ТЗ</v-chip></td>
                    <td>
                      <div class="d-flex align-center gap-1">
                        <div
                          class="feo-name-display flex-grow-1"
                          :class="{ 'is-empty': !item.item_name, 'is-readonly': readonly }"
                          :title="item.item_name || ''"
                          @click="!readonly && emit('open-product-picker', idx)"
                        >{{ item.item_name || 'Нажмите для выбора...' }}</div>
                        <v-btn v-if="item.item_name && !readonly" icon="mdi-close" size="x-small" variant="text"
                          class="flex-shrink-0" @click.stop="emit('clear-item', idx)" />
                        <v-tooltip v-if="item.item_name" :text="item.product_id ? 'Редактировать товар в каталоге' : 'Создать товар в каталоге из этой позиции'" location="top">
                          <template #activator="{ props: tip }">
                            <v-btn v-bind="tip" icon="mdi-pencil-outline" size="x-small" variant="tonal"
                              color="teal" class="flex-shrink-0" :disabled="readonly"
                              @click.stop="emit('open-quick-product-edit', item)" />
                          </template>
                        </v-tooltip>
                      </div>
                      <!-- Phase 27.1.1 fix: per-item contractor только для авансовых (advance_report). Inline contractor для обычных закупок убран — 1 контрагент на закупку. -->
                    </td>
                    <td>
                      <v-text-field v-model.number="item.quantity" type="number" density="compact"
                        variant="outlined" hide-details class="my-1" :disabled="readonly"
                        @update:model-value="emit('calc-item-total', idx)" />
                    </td>
                    <td>
                      <v-combobox v-model="item.unit" :items="unitOptions" density="compact" variant="outlined"
                        hide-details class="my-1" :disabled="readonly" />
                    </td>
                    <td>
                      <v-text-field
                        :model-value="formatNumber(item.unit_price)"
                        density="compact" variant="outlined" hide-details class="my-1"
                        :disabled="readonly"
                        @update:model-value="(v: string) => { item.unit_price = parseNumber(v) as any; emit('calc-item-total', idx) }"
                      />
                    </td>
                    <!-- Fix 4/5: НДС % column -->
                    <td v-if="showVatColumnsInExpandRow">
                      <v-combobox v-model="item.vat_rate"
                        :items="vatRateOptions"
                        item-title="title" item-value="value"
                        density="compact" variant="outlined" hide-details class="my-1"
                        style="min-width:90px" :disabled="readonly"
                        placeholder="НДС %"
                        @update:model-value="emit('vat-rate-change', idx, $event)"
                      />
                    </td>
                    <!-- Fix 4/5: НДС сумма column -->
                    <td v-if="showVatColumnsInExpandRow" class="text-caption">{{ fmtRub(vatAmount(item)) }}</td>
                    <!-- Fix 4/5: Сумма с НДС column -->
                    <td class="text-caption font-weight-medium">{{ fmtRub(totalWithVat(item)) }}</td>
                    <!-- Контрагент column -->
                    <td>
                      <!-- Контрагент (advance_report column mode) -->
                      <template v-if="showContractorColumn">
                        <v-autocomplete
                          :model-value="item.contractor_id ? contractors.find(c => c.id === item.contractor_id) || null : null"
                          :items="contractors" item-title="name" item-value="id" return-object
                          variant="outlined" density="compact" clearable auto-select-first hide-details
                          class="my-1" style="min-width:160px"
                          :custom-filter="contractorFilter" :loading="contractorLookupLoading[idx] === true"
                          placeholder="Поставщик..." :disabled="readonly"
                          @update:search="(s: string) => emit('contractor-search-input', idx, s)"
                          @update:model-value="(v: Contractor | null) => emit('item-contractor-select', idx, v)"
                        >
                          <template #append-inner>
                            <v-btn icon="mdi-account-plus" size="x-small" variant="text" color="teal"
                              :disabled="readonly" @click.stop="emit('open-contractor-quick-create', idx)" />
                          </template>
                        </v-autocomplete>
                      </template>
                      <!-- ТЗ contractor chip (non-advance mode, if contractor set from Phase 24 D-05) -->
                      <v-chip
                        v-else-if="item.contractor_id && contractorNameById(item.contractor_id)"
                        size="x-small" color="info" variant="tonal"
                        prepend-icon="mdi-store" style="max-width:170px;white-space:normal;height:auto"
                        :title="contractorNameById(item.contractor_id)"
                      >
                        {{ contractorNameById(item.contractor_id) }}
                      </v-chip>
                      <span v-else class="text-medium-emphasis text-caption">—</span>
                    </td>
                  </tr>
                  <!-- ТЗ attributes row (full width): ФЭО каскад + Тип + Страна.
                       Вынесено из узких колонок, чтобы числовая таблица влезала без горизонтального скролла. -->
                  <tr class="stage-tz-row stage-attrs-row">
                    <td></td>
                    <td :colspan="(showVatColumnsInExpandRow ? 9 : 7) - 1">
                      <div class="d-flex align-start ga-4 flex-wrap py-1">
                        <!-- ФЭО позиция — горизонтальный каскад по уровням -->
                        <div v-if="feoPerItem" class="d-flex align-start ga-2 flex-wrap" style="flex:1 1 460px;min-width:300px">
                          <FeoTreeSelect
                            :model-value="item.feo_node_id ?? item.feo_category_id"
                            :nodes="feoNodes"
                            :leaves="feoLeaves"
                            :readonly="readonly"
                            :error="isFeoMissing(item)"
                            horizontal
                            label="ФЭО позиция"
                            required
                            :allow-unallocated="!!subsidyId"
                            :root-label="subsidyName"
                            style="flex:1 1 auto;min-width:240px"
                            @update:model-value="(v: number | null) => emit('item-feo-change', idx, v)"
                            @pick-unallocated="(parentId: number | null) => emit('item-pick-unallocated', idx, parentId)"
                          />
                          <div v-if="isOverBudget(item)" class="text-caption text-warning mt-2 d-flex align-center ga-1" style="white-space:nowrap">
                            <v-icon icon="mdi-alert-outline" size="14" />
                            Превышение: {{ fmtRub(overBudgetDelta(item)) }}
                          </div>
                          <!-- F-PLAN: выбор плановой позиции план-графика (Ур.5 ФЭО) для этой позиции.
                               category-id — узел каскада (лист или промежуточный), НЕ только feo_category_id:
                               компонент сам находит дочерние конечные элементы под промежуточным узлом. -->
                          <FeoPlannedItemsSelect
                            v-if="feoPlannedPerItem"
                            :model-value="plannedSelectionFor ? plannedSelectionFor(item) : null"
                            :out-of-plan="!!item.over_plan"
                            :category-id="item.feo_node_id ?? item.feo_category_id ?? null"
                            :nodes="feoNodes" :items="plannedItems || []"
                            :amount="item.total_price" :readonly="readonly" dense class="mt-1"
                            @update:model-value="(v) => emit('item-planned-change', idx, v)"
                            @update:out-of-plan="(v) => emit('item-out-of-plan-change', idx, v)" />
                        </div>
                        <!-- Тип -->
                        <v-select v-model="item.item_type"
                          :items="allowedItemTypes.map(t => ({ value: t, title: t.charAt(0).toUpperCase() + t.slice(1) }))"
                          item-title="title" item-value="value" density="compact" variant="outlined"
                          label="Тип" hide-details style="min-width:140px;max-width:180px" class="my-1" :disabled="readonly"
                          @update:model-value="(v: string) => emit('item-type-change', idx, v)" />
                        <!-- Страна -->
                        <v-text-field v-model="item.country_origin" density="compact"
                          variant="outlined" hide-details class="my-1" label="Страна" placeholder="РФ"
                          style="min-width:120px;max-width:160px" :disabled="readonly" />
                      </div>
                    </td>
                  </tr>
                  <!-- Договор sub-row -->
                  <tr class="stage-contract-row">
                    <td><v-chip color="success" size="x-small" variant="tonal">Договор</v-chip></td>
                    <td>
                      <v-textarea
                        :model-value="getContractItemFor(idx)?.name ?? (isAdvance ? (items[idx] as any)?.item_name ?? '' : '')"
                        density="compact" variant="outlined" hide-details placeholder="Наименование по договору"
                        rows="2" :max-rows="6" auto-grow class="my-1 flex-grow-1" style="min-width:260px"
                        :disabled="readonly"
                        @update:model-value="(v: string) => emit('update-contract-field', idx, 'name', v)"
                      />
                    </td>
                    <td>
                      <v-text-field
                        :model-value="getContractItemFor(idx)?.quantity ?? (isAdvance ? (items[idx] as any)?.quantity ?? '' : '')"
                        type="number" density="compact" variant="outlined" hide-details
                        :disabled="readonly"
                        @update:model-value="(v: string) => emit('update-contract-field', idx, 'quantity', Number(v))"
                      />
                    </td>
                    <td>
                      <v-text-field
                        :model-value="getContractItemFor(idx)?.unit ?? (isAdvance ? (items[idx] as any)?.unit ?? '' : '')"
                        density="compact" variant="outlined" hide-details
                        :disabled="readonly"
                        @update:model-value="(v: string) => emit('update-contract-field', idx, 'unit', v)"
                      />
                    </td>
                    <td>
                      <v-text-field
                        :model-value="getContractItemFor(idx)?.unit_price ?? (isAdvance ? (items[idx] as any)?.unit_price ?? '' : '')"
                        type="number" density="compact" variant="outlined" hide-details
                        :disabled="readonly"
                        @update:model-value="(v: string) => emit('update-contract-field', idx, 'unit_price', Number(v))"
                      />
                    </td>
                    <!-- Fix 4/5: НДС % column (Договор) -->
                    <td v-if="showVatColumnsInExpandRow">
                      <v-combobox
                        :model-value="getContractItemFor(idx)?.vat_rate ?? items[idx]?.vat_rate ?? null"
                        :items="vatRateOptions"
                        item-title="title" item-value="value"
                        density="compact" variant="outlined" hide-details class="my-1"
                        style="min-width:90px" :disabled="readonly"
                        placeholder="НДС %"
                        @update:model-value="(v: any) => emit('contract-vat-change', idx, v)"
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
                          style="max-width:260px;white-space:normal;height:auto"
                          :title="contractStageContractorName(idx)"
                        >
                          {{ contractStageContractorName(idx) }}
                        </v-chip>
                        <span v-else class="text-medium-emphasis text-caption">—</span>
                      </div>
                    </td>
                  </tr>
                  <!-- Поставка sub-row (D-01.1.1) — «Приняли»: редактируется на delivered/paid -->
                  <tr class="stage-delivery-row" :class="{ 'stage-delivery-empty': !isDeliveryFilled(idx) }">
                    <td><v-chip color="purple" size="x-small" variant="tonal">Поставка</v-chip></td>
                    <template v-if="isDelivered(idx)">
                      <!-- delivered/paid: редактируемые accepted_name/accepted_quantity/accepted_unit
                           (та же стадия «Приняли», что и в /comparison stages). Автозаполняется на
                           переходе в delivered из договора/ТЗ, дальше правится вручную. -->
                      <td>
                        <v-textarea
                          :model-value="(items[idx] as any)?.accepted_name ?? ''"
                          density="compact" variant="outlined" hide-details placeholder="Наименование по приёмке"
                          rows="2" :max-rows="6" auto-grow class="my-1 flex-grow-1" style="min-width:260px"
                          :disabled="readonly"
                          @update:model-value="(v: string) => emit('update-accepted-field', idx, 'accepted_name', v)"
                        />
                      </td>
                      <td>
                        <v-text-field
                          :model-value="(items[idx] as any)?.accepted_quantity ?? ''"
                          type="number" density="compact" variant="outlined" hide-details
                          :disabled="readonly"
                          @update:model-value="(v: string) => emit('update-accepted-field', idx, 'accepted_quantity', v === '' ? null : Number(v))"
                        />
                      </td>
                      <td>
                        <v-combobox
                          :model-value="(items[idx] as any)?.accepted_unit ?? ''"
                          :items="unitOptions" density="compact" variant="outlined" hide-details
                          :disabled="readonly"
                          @update:model-value="(v: string) => emit('update-accepted-field', idx, 'accepted_unit', v)"
                        />
                      </td>
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
                            prepend-icon="mdi-truck-delivery" style="max-width:260px;white-space:normal;height:auto"
                            :title="deliveryStageContractorName(idx)"
                          >
                            {{ deliveryStageContractorName(idx) }}
                          </v-chip>
                          <span v-else class="text-medium-emphasis text-caption">—</span>
                        </div>
                      </td>
                    </template>
                    <template v-else-if="isAdvance">
                      <!-- advance, ещё не delivered: показываем данные из ТЗ вместо заглушки -->
                      <td>
                        <div
                          class="feo-name-display is-static"
                          :title="(items[idx] as any)?.item_name || ''"
                        >{{ (items[idx] as any)?.item_name || '—' }}</div>
                      </td>
                      <td class="text-caption text-grey-darken-1">{{ (items[idx] as any)?.quantity ?? '—' }}</td>
                      <td class="text-caption text-grey-darken-1">{{ (items[idx] as any)?.unit ?? '—' }}</td>
                      <td class="text-caption text-grey-darken-1">{{ (items[idx] as any)?.unit_price ?? '—' }}</td>
                      <td v-if="showVatColumnsInExpandRow" class="text-caption text-grey-darken-1">{{ (items[idx] as any)?.vat_rate ?? '—' }}</td>
                      <td v-if="showVatColumnsInExpandRow" class="text-caption text-grey-darken-1">{{ fmtRub(vatAmount((items[idx] as any) ?? {})) }}</td>
                      <td class="text-caption text-grey-darken-1 font-weight-medium">{{ fmtRub(Number((items[idx] as any)?.total_price ?? 0)) }}</td>
                      <td></td>
                    </template>
                    <template v-else>
                      <td :colspan="(showVatColumnsInExpandRow ? 9 : 7) - 1" class="text-caption text-grey-lighten-1 text-center py-1">
                        Появится после перевода закупки в статус «Поставлено»
                      </td>
                    </template>
                  </tr>
                </tbody>
              </v-table>
            </td>
          </tr>
        </template>
        <tr v-if="!items.length">
          <td colspan="10" class="text-center text-medium-emphasis py-4">
            Нет позиций. Нажмите «Добавить позицию».
          </td>
        </tr>
      </tbody>
      <tfoot v-if="items.length">
        <tr>
          <td colspan="3" class="text-right pr-3 py-2 text-caption font-weight-bold">НМЦД итого:</td>
          <td colspan="7" class="py-2 font-weight-bold text-blue-darken-2">
            {{ totalNmck.toLocaleString('ru-RU') }} ₽
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
  </div>
</template>

<script setup lang="ts">
import FeoTreeSelect from '@/components/items/FeoTreeSelect.vue'
import FeoPlannedItemsSelect from '@/components/items/FeoPlannedItemsSelect.vue'
import type { Contractor } from '@/components/items/types'
import type { FeoNode } from '@/composables/useFeoLeaves'
import type { FeoPlanSelection } from '@/composables/useFeoPlannedResiduals'

type EditorItem = any
type StageTotals = { tz: number; dog: number; delivery: number }

defineProps<{
  items: EditorItem[]
  readonly: boolean
  allowedItemTypes: string[]
  contractors: Contractor[]
  contractorLookupLoading: Record<number, boolean>
  selectedItemIdxs: number[]
  allItemsSelected: boolean
  totalNmck: number
  unitOptions: string[]
  vatRateOptions: any[]
  feoLeaves: any[]
  feoNodes: FeoNode[]
  feoPerItem?: boolean
  // F-PLAN: разные плановые позиции план-графика (Ур.5 ФЭО) для каждого товара
  feoPlannedPerItem?: boolean
  plannedItems?: any[]
  // F-PLAN2: производный выбор { kind, id } | null для FeoPlannedItemsSelect по
  // фактическим полям позиции — см. plannedSelectionFor() в PurchaseItemsEditor.vue.
  plannedSelectionFor?: (item: EditorItem) => FeoPlanSelection | null
  subsidyId?: number | null
  subsidyName?: string | null
  // mode flags (computed in parent)
  showVatColumnsInExpandRow: boolean
  showContractorColumn: boolean
  isAdvance: boolean
  // expand state (parent-owned)
  expanded: Record<number, boolean>
  // savings badge computeds
  contractItemsTotal: number
  purchasePlannedTotal: number
  contractSavings: number | null
  contractSavingsPercent: number | string
  // function props — parent helpers (read-only computations)
  summaryName: (idx: number) => string
  stageTotals: (idx: number) => StageTotals
  isDelivered: (idx: number) => boolean
  isDeliveryFilled: (idx: number) => boolean
  effectiveVatRate: (idx: number, stage: 'contract' | 'delivery') => string | null
  vatAmount: (row: EditorItem) => number
  vatAmountForStage: (idx: number, stage: 'tz' | 'contract' | 'delivery') => number
  totalWithVat: (row: EditorItem) => number
  totalWithVatForStage: (idx: number, stage: 'contract' | 'delivery') => number
  getContractItemFor: (idx: number) => any
  contractorNameById: (cid: number | null | undefined) => string
  contractStageContractorName: (idx: number) => string
  deliveryStageContractorName: (idx: number) => string
  isOverBudget: (row: EditorItem) => boolean
  overBudgetDelta: (row: EditorItem) => number
  isFeoMissing: (row: EditorItem) => boolean
  fmtRub: (v: number | null | undefined) => string
  formatNumber: (v: number | null | undefined) => string
  parseNumber: (v: string) => number | null
  contractorFilter: (value: string, query: string, item?: any) => boolean
}>()

const emit = defineEmits<{
  'toggle-select-all': [val: boolean | null]
  'toggle-item-select': [idx: number, val: boolean | null]
  'toggle-expand': [idx: number]
  'confirm-match': [idx: number]
  'open-repick-dialog': [idx: number]
  'remove-item': [idx: number]
  'open-product-picker': [idx: number]
  'clear-item': [idx: number]
  'open-quick-product-edit': [item: EditorItem]
  'calc-item-total': [idx: number]
  'vat-rate-change': [idx: number, val: any]
  'item-feo-change': [idx: number, val: number | null]
  'item-planned-change': [idx: number, val: FeoPlanSelection | null]
  'item-out-of-plan-change': [idx: number, val: boolean]
  'item-pick-unallocated': [idx: number, parentId: number | null]
  'item-type-change': [idx: number, val: string]
  'items-changed': []
  'contractor-search-input': [idx: number, search: string]
  'item-contractor-select': [idx: number, val: Contractor | null]
  'open-contractor-quick-create': [idx: number]
  'update-contract-field': [idx: number, field: string, val: unknown]
  'contract-vat-change': [idx: number, val: any]
  'update-accepted-field': [idx: number, field: 'accepted_name' | 'accepted_quantity' | 'accepted_unit', val: unknown]
}>()
</script>

<style scoped>
/* ISSUE-4: full-name display field (replaces clipping readonly v-textarea) */
.feo-name-display {
  border: 1px solid rgba(0, 0, 0, 0.23);
  border-radius: 4px;
  padding: 6px 10px;
  min-width: 260px;
  cursor: pointer;
  white-space: normal;
  word-break: break-word;
  line-height: 1.3;
  font-size: 12px;
  min-height: 32px;
}
.feo-name-display.is-empty {
  color: rgba(0, 0, 0, 0.45);
}
.feo-name-display.is-readonly,
.feo-name-display.is-static {
  cursor: default;
}
.feo-name-display.is-static {
  background: #f5f5f5;
}

/* Phase 27.1.1: expand-row layout (moved from PurchaseItemsEditor.vue during Layer 3 extraction) */
.summary-row:hover {
  background: rgba(0, 0, 0, 0.02);
}
.summary-num-input :deep(.v-text-field input),
.summary-num-input :deep(.v-field__input) {
  font-size: 12px !important;
  padding-top: 4px !important;
  padding-bottom: 4px !important;
  min-height: 32px !important;
}
.summary-num-input :deep(.v-field) {
  --v-field-padding-start: 8px;
  --v-field-padding-end: 8px;
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
/* F-PIF2: hard-error при отсутствии FEO позиции в режиме feoPerItem */
.feo-missing :deep(.v-field) {
  background: rgba(244, 67, 54, 0.06);
  border-color: rgba(244, 67, 54, 0.5);
}
</style>
