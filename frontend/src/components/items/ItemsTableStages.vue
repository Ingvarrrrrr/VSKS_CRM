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
          <th style="min-width:280px">Суммы стадий</th>
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
                    <th v-if="feoPerItem" style="min-width:240px">ФЭО позиция *</th>
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
                          :disabled="readonly"
                          @click="emit('open-product-picker', idx)"
                          @click:clear.stop="emit('clear-item', idx)"
                        />
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
                    <!-- F-PIF2/FCAT-F1: ФЭО позиция — отдельная колонка в expand-row table -->
                    <td v-if="feoPerItem">
                      <v-autocomplete
                        v-model="item.feo_category_id"
                        :items="feoLeaves"
                        item-title="path"
                        item-value="id"
                        label="ФЭО позиция"
                        variant="outlined"
                        density="compact"
                        clearable
                        hide-details
                        class="my-1"
                        style="min-width:200px"
                        :class="{ 'feo-over-budget': isOverBudget(item), 'feo-missing': isFeoMissing(item) }"
                        :error="isFeoMissing(item)"
                        :error-messages="isFeoMissing(item) ? 'Обязательно' : ''"
                        :disabled="readonly"
                        @update:model-value="emit('items-changed')"
                      >
                        <template #item="{ props: itemProps, item: feoItem }">
                          <v-list-item v-bind="itemProps" :title="feoItem.raw.name">
                            <template #subtitle>
                              <div style="font-size:11px;color:#666">{{ feoItem.raw.path }}</div>
                              <div>План: {{ fmtRub(feoItem.raw.budget) }} • Ост.: {{ fmtRub(feoItem.raw.residual) }}</div>
                            </template>
                          </v-list-item>
                        </template>
                        <template #selection="{ item: feoItem }">
                          <span style="font-size:12px">{{ feoItem.raw.name }}</span>
                        </template>
                      </v-autocomplete>
                      <div v-if="isOverBudget(item)" class="text-caption text-warning my-1 d-flex align-center ga-1">
                        <v-icon icon="mdi-alert-outline" size="14" />
                        Превышение: {{ fmtRub(overBudgetDelta(item)) }}
                      </div>
                    </td>
                    <td>
                      <div class="d-flex align-center ga-1 flex-wrap">
                        <!-- Тип -->
                        <v-select v-model="item.item_type"
                          :items="allowedItemTypes.map(t => ({ value: t, title: t.charAt(0).toUpperCase() + t.slice(1) }))"
                          item-title="title" item-value="value" density="compact" variant="outlined"
                          hide-details style="min-width:100px" class="my-1" :disabled="readonly" />
                        <!-- Страна -->
                        <v-text-field v-model="item.country_origin" density="compact"
                          variant="outlined" hide-details class="my-1" placeholder="РФ"
                          style="min-width:120px" :disabled="readonly" />
                        <!-- Контрагент (advance_report column mode) -->
                        <template v-if="showContractorColumn">
                          <v-autocomplete
                            :model-value="item.contractor_id ? contractors.find(c => c.id === item.contractor_id) || null : null"
                            :items="contractors" item-title="name" item-value="id" return-object
                            variant="outlined" density="compact" clearable auto-select-first hide-details
                            class="my-1" style="min-width:180px"
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
                        :model-value="getContractItemFor(idx)?.name ?? (isAdvance ? (items[idx] as any)?.item_name ?? '' : '')"
                        density="compact" variant="outlined" hide-details placeholder="Наименование по договору"
                        rows="1" auto-grow class="my-1 flex-grow-1" style="min-width:200px"
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
                          :model-value="(items[idx] as any)?.item_name ?? ''"
                          density="compact" variant="outlined" hide-details readonly
                          rows="1" auto-grow class="my-1" style="min-width:200px"
                          bg-color="grey-lighten-4"
                        />
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
        <tr v-if="!items.length">
          <td colspan="7" class="text-center text-medium-emphasis py-4">
            Нет позиций. Нажмите «Добавить позицию».
          </td>
        </tr>
      </tbody>
      <tfoot v-if="items.length">
        <tr>
          <td colspan="3" class="text-right pr-3 py-2 text-caption font-weight-bold">НМЦД итого:</td>
          <td colspan="4" class="py-2 font-weight-bold text-blue-darken-2">
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
import type { Contractor } from '@/components/items/types'

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
  feoPerItem?: boolean
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
  'items-changed': []
  'contractor-search-input': [idx: number, search: string]
  'item-contractor-select': [idx: number, val: Contractor | null]
  'open-contractor-quick-create': [idx: number]
  'update-contract-field': [idx: number, field: string, val: unknown]
  'contract-vat-change': [idx: number, val: any]
}>()
</script>

<style scoped>
/* Phase 27.1.1: expand-row layout (moved from PurchaseItemsEditor.vue during Layer 3 extraction) */
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
/* F-PIF2: hard-error при отсутствии FEO позиции в режиме feoPerItem */
.feo-missing :deep(.v-field) {
  background: rgba(244, 67, 54, 0.06);
  border-color: rgba(244, 67, 54, 0.5);
}
</style>
