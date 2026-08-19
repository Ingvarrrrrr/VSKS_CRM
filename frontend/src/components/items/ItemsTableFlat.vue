<template>
  <!-- Presentational legacy flat items table (wish/simple editor + purchase
       non-stages mode). Holds NO business state — all data comes in via props,
       all mutations leave via emits. The parent owns localItems and every
       handler. Extracted from PurchaseItemsEditor.vue (Layer 3). -->
  <div class="overflow-x-auto">
    <v-table density="compact" class="items-flat-table">
      <thead>
        <tr>
          <th style="width:36px;padding:0 4px;text-align:center">
            <v-checkbox :model-value="allItemsSelected" density="compact" hide-details :rules="[]"
              :indeterminate="selectedItemIdxs.length > 0 && !allItemsSelected"
              @update:model-value="(v: boolean | null) => emit('toggle-select-all', v)" />
          </th>
          <th style="width:36px;text-align:center;color:#888;font-size:12px">№</th>
          <th :style="resizeStyle('name')">Наименование<span class="col-resize-handle" @mousedown="onResizeStart($event, 'name')">&nbsp;</span></th>
          <th :style="resizeStyle('type')">Тип<span class="col-resize-handle" @mousedown="onResizeStart($event, 'type')">&nbsp;</span></th>
          <th :style="resizeStyle('qty')">Кол-во<span class="col-resize-handle" @mousedown="onResizeStart($event, 'qty')">&nbsp;</span></th>
          <th :style="resizeStyle('unit')">Ед. изм.<span class="col-resize-handle" @mousedown="onResizeStart($event, 'unit')">&nbsp;</span></th>
          <th :style="resizeStyle('price')">Цена ед., ₽<span class="col-resize-handle" @mousedown="onResizeStart($event, 'price')">&nbsp;</span></th>
          <th :style="resizeStyle('sum')">Сумма, ₽<span class="col-resize-handle" @mousedown="onResizeStart($event, 'sum')">&nbsp;</span></th>
          <th :style="resizeStyle('country')">Страна происхождения<span class="col-resize-handle" @mousedown="onResizeStart($event, 'country')">&nbsp;</span></th>
          <th v-if="vatMode === 'per_item'" style="min-width:130px">НДС</th>
          <th v-if="showNeededDate" style="min-width:150px">Дата поставки</th>
          <th v-if="showContractorColumn" :style="resizeStyle('contractor')">Контрагент<span class="col-resize-handle" @mousedown="onResizeStart($event, 'contractor')">&nbsp;</span></th>
          <th :style="resizeStyle('actions')"><span class="col-resize-handle" @mousedown="onResizeStart($event, 'actions')">&nbsp;</span></th>
        </tr>
      </thead>
      <tbody>
        <!-- Perf: for large lists (> VIRT_THRESHOLD) apply content-visibility:auto so
             the browser skips layout/paint of offscreen rows. Small lists behave
             EXACTLY as before (no class, no style). contain-intrinsic-size reserves
             approximate row height so the scrollbar stays stable. -->
        <template v-for="(row, rPos) in bodyRows" :key="row.header != null ? `gh-${rPos}` : (items[row.idx!]?._uid ?? row.idx)">
        <tr v-if="row.header != null" class="items-group-header" :class="row.level === 2 ? 'items-group-header--type' : ''">
          <td :colspan="totalColCount" :class="row.level === 2 ? 'pl-8' : 'pl-3'" class="py-1">
            <v-icon size="14" class="mr-1">{{ row.level === 2 ? 'mdi-shape-outline' : 'mdi-folder-outline' }}</v-icon>
            <span class="font-weight-bold" style="font-size:12px">{{ row.header }}</span>
            <span class="text-medium-emphasis ml-2" style="font-size:11px">{{ row.count }} поз. · {{ fmtRub(row.sum || 0) }}</span>
          </td>
        </tr>
        <template v-else>
        <template v-for="{ item, idx } in [{ item: items[row.idx!], idx: row.idx! }]" :key="item._uid ?? idx">
        <tr :class="{ 'cv-row': virtualize }">
          <td style="width:36px;padding:0 4px;text-align:center">
            <v-checkbox :model-value="selectedItemIdxs.includes(idx)" density="compact" hide-details :rules="[]"
              @update:model-value="(val: boolean | null) => emit('toggle-item-select', idx, val)" />
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
              <!-- BUG #5: inline catalog matching dropdown (no dialog dive) -->
              <InlineProductMatch
                class="my-1 flex-grow-1 name-match-grow"
                style="min-width:280px"
                :item-name="item.item_name"
                :product-id="item.product_id"
                :match-confirmed="item.match_confirmed"
                :disabled="readonly"
                @pick="(c: MatchCandidate) => emit('inline-match-pick', idx, c)"
                @create-new="emit('inline-match-create-new', idx)"
                @clear="emit('inline-match-clear', idx)"
              />
              <v-tooltip v-if="item.item_name" :text="item.product_id ? 'Редактировать товар в каталоге' : 'Создать товар в каталоге из этой позиции'" location="top">
                <template #activator="{ props: tip }">
                  <v-btn v-bind="tip" icon="mdi-pencil-outline" size="x-small" variant="tonal"
                    color="teal" class="flex-shrink-0 ml-1" :disabled="readonly"
                    @click.stop="emit('open-quick-product-edit', item)" />
                </template>
              </v-tooltip>
              <v-tooltip v-if="item.match_confirmed === false && item.product_id" text="Подтвердить, что товар из каталога определён правильно" location="top">
                <template #activator="{ props: tip }">
                  <v-btn v-bind="tip" icon="mdi-check-bold" size="x-small" variant="tonal"
                    color="warning" class="flex-shrink-0 ml-1" :disabled="readonly"
                    @click.stop="emit('confirm-match', idx)" />
                </template>
              </v-tooltip>
            </div>
            <!-- Phase 27.1.2: inline contractor убран для не-advance из flat layout. Per-item contractor только в advance_report mode (колонка showContractorColumn справа). -->
          </td>
          <td>
            <v-select v-model="item.item_type"
              :items="allowedItemTypes.map(t => ({ value: t, title: t.charAt(0).toUpperCase() + t.slice(1) }))"
              item-title="title" item-value="value" density="compact" variant="outlined"
              hide-details class="my-1" :disabled="readonly"
              @update:model-value="(v: string) => emit('item-type-change', idx, v)" />
          </td>
          <td>
            <v-tooltip :disabled="!tzFrozen || readonly" :text="tzFrozenTooltip" location="top" max-width="280">
              <template #activator="{ props: tip }">
                <v-text-field v-bind="tip" v-model.number="item.quantity" type="number" density="compact"
                  variant="outlined" hide-details class="my-1" :class="{ 'tz-over-plan': planExcessFor?.(item)?.qtyOver }"
                  :disabled="tzDisabled"
                  @update:model-value="emit('calc-item-total', idx)" />
              </template>
            </v-tooltip>
            <div v-if="planForItem?.(item)?.planned_quantity != null" class="text-caption plan-hint"
              :class="planExcessFor?.(item)?.qtyOver ? 'text-error font-weight-bold' : 'text-medium-emphasis'">
              план: {{ formatNumber(planForItem!(item)!.planned_quantity) }}{{ planForItem!(item)!.unit ? ' ' + planForItem!(item)!.unit : '' }}
            </div>
          </td>
          <td>
            <v-combobox v-model="item.unit" :items="unitOptions" density="compact" variant="outlined"
              hide-details class="my-1" :disabled="readonly" />
          </td>
          <td>
            <v-tooltip :disabled="!tzFrozen || readonly" :text="tzFrozenTooltip" location="top" max-width="280">
              <template #activator="{ props: tip }">
                <v-text-field
                  v-bind="tip"
                  :model-value="formatNumber(item.unit_price)"
                  density="compact" variant="outlined" hide-details class="my-1"
                  :class="{ 'tz-over-plan': planExcessFor?.(item)?.priceOver }"
                  :disabled="tzDisabled"
                  @update:model-value="(v: string) => { item.unit_price = parseNumber(v) as any; emit('calc-item-total', idx) }"
                />
              </template>
            </v-tooltip>
            <div v-if="planForItem?.(item)?.unit_price != null" class="text-caption plan-hint"
              :class="planExcessFor?.(item)?.priceOver ? 'text-error font-weight-bold' : 'text-medium-emphasis'">
              план: {{ formatNumber(planForItem!(item)!.unit_price) }} ₽
            </div>
          </td>
          <td>
            <v-text-field :model-value="formatNumber(item.total_price)" readonly density="compact"
              variant="outlined" hide-details bg-color="grey-lighten-4" class="my-1"
              :class="{ 'tz-over-plan': planExcessFor?.(item)?.totalOver }" />
            <div v-if="planForItem?.(item)?.planned_amount != null" class="text-caption plan-hint"
              :class="planExcessFor?.(item)?.totalOver ? 'text-error font-weight-bold' : 'text-medium-emphasis'">
              план: {{ formatNumber(planForItem!(item)!.planned_amount) }} ₽
            </div>
          </td>
          <td>
            <v-text-field v-model="item.country_origin" density="compact"
              variant="outlined" hide-details class="my-1" placeholder="РФ" :disabled="readonly" />
          </td>
          <td v-if="vatMode === 'per_item'">
            <v-combobox v-model="item.vat_rate"
              :items="vatRateOptions"
              item-title="title" item-value="value"
              density="compact" variant="outlined" hide-details class="my-1"
              style="min-width:100px" :disabled="readonly"
              placeholder="НДС %"
              @update:model-value="emit('vat-rate-change', idx, $event)" />
          </td>
          <td v-if="showNeededDate">
            <v-text-field
              :model-value="item.needed_date ?? ''"
              type="date" density="compact" variant="outlined" hide-details class="my-1"
              :disabled="readonly"
              @update:model-value="(e: string) => { item.needed_date = e || null; emit('items-changed') }"
            />
          </td>
          <td v-if="showContractorColumn" :style="resizeStyle('contractor')">
            <v-autocomplete
              :model-value="item.contractor_id ? contractors.find(c => c.id === item.contractor_id) || null : null"
              :items="contractors" item-title="name" item-value="id" return-object
              variant="outlined" density="compact" clearable auto-select-first hide-details
              class="my-1" :custom-filter="contractorFilter" :loading="contractorLookupLoading[idx] === true"
              :menu-props="{ maxWidth: 500 }" placeholder="Поставщик. Поиск по названию или ИНН..."
              :disabled="readonly"
              @update:search="(s: string) => emit('contractor-search-input', idx, s)"
              @update:model-value="(v: Contractor | null) => emit('item-contractor-select', idx, v)"
            >
              <template #item="{ item: i, props: itemProps }">
                <v-list-item v-bind="itemProps" :title="undefined">
                  <template #title><span style="white-space:normal;word-break:break-word;line-height:1.4">{{ i.raw.name }}</span></template>
                  <template #subtitle><span v-if="i.raw.inn" class="text-caption">ИНН: {{ i.raw.inn }}</span></template>
                </v-list-item>
              </template>
              <template #append-inner>
                <v-btn icon="mdi-account-plus" size="x-small" variant="text" color="teal"
                  title="Добавить контрагента" :disabled="readonly"
                  @click.stop="emit('open-contractor-quick-create', idx)" />
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
            <div class="d-flex">
              <!-- Владелец 2026-08-18: разбивка позиции по разным категориям ФЭО
                   (напр. 66 огнетушителей → 41 по одной категории, 25 по другой).
                   Доступно от 2 единиц количества, недоступно в readonly. -->
              <v-tooltip v-if="!readonly && (item.quantity ?? 0) >= 2" text="Разбить по категориям ФЭО" location="top">
                <template #activator="{ props: tip }">
                  <v-btn v-bind="tip" icon="mdi-call-split" variant="text" size="small" color="primary"
                    data-testid="split-item-btn"
                    @click="emit('split-item', idx)" />
                </template>
              </v-tooltip>
              <v-btn icon="mdi-delete-outline" variant="text" size="small" color="error"
                :disabled="readonly" @click="emit('remove-item', idx)" />
            </div>
          </td>
        </tr>
        <!-- ФЭО-подстрока на всю ширину таблицы: путь категории ФЭО обычно длинный
             («Родитель › Подкатегория › Конечная категория (уточнение)») и не помещается
             в узкую 90px колонку «Тип» — раньше рендерился внутри неё и переносился по
             одному слову, растягивая строку на ~700-1000px по вертикали («лапша»).
             Вынесено из узкой колонки по аналогии с ItemsTableStages.vue (stage-attrs-row). -->
        <tr v-if="feoPerItem || allowPerItemPlan" class="feo-attrs-row" :class="{ 'cv-row': virtualize }">
          <td></td>
          <td></td>
          <td :colspan="totalColCount - 2">
            <div class="d-flex align-start ga-4 flex-wrap py-1">
              <template v-if="feoPerItem">
                <FeoTreeSelect
                  :model-value="item.feo_node_id ?? item.feo_category_id"
                  :nodes="feoNodes"
                  :leaves="feoLeaves"
                  :plan-positions="plannedItems || []"
                  :node-amounts="nodeAmounts"
                  :readonly="feoReadonly"
                  :error="isFeoMissing(item)"
                  label="Категория ФЭО"
                  required
                  :allow-unallocated="!!subsidyId"
                  :root-label="subsidyName"
                  style="flex:2 1 520px;min-width:320px"
                  @update:model-value="(v: number | null) => emit('item-feo-change', idx, v)"
                  @pick-unallocated="(parentId: number | null) => emit('item-pick-unallocated', idx, parentId)"
                />
                <div v-if="isOverBudget(item)" class="text-caption text-warning mt-2 d-flex align-center ga-1" style="white-space:nowrap">
                  <v-icon icon="mdi-alert-outline" size="14" />
                  Превышение: {{ fmtRub(overBudgetDelta(item)) }}
                </div>
              </template>
              <!-- F-PLAN: выбор плановой позиции плана закупок (Ур.5 ФЭО) для этой позиции.
                   category-id — узел каскада (лист или промежуточный), НЕ только feo_category_id;
                   владелец 2026-08-17: в общем режиме (без своей категории у строки) падает на
                   defaultFeoCategoryId — категорию, выбранную один раз в шапке заявки/закупки. -->
              <FeoPlannedItemsSelect
                v-if="feoPlannedPerItem || allowPerItemPlan"
                :model-value="plannedSelectionFor ? plannedSelectionFor(item) : null"
                :category-id="item.feo_node_id ?? item.feo_category_id ?? defaultFeoCategoryId ?? null"
                :nodes="feoNodes" :items="plannedItems || []"
                :amount="item.total_price" :readonly="feoReadonly" dense
                :pending-by-planned-item="pendingByPlannedItem"
                :purchase-id="purchaseId"
                style="flex:1 1 320px;min-width:260px"
                :prefill="{ name: item.item_name, quantity: item.quantity, unit: item.unit, amount: item.total_price }"
                @update:model-value="(v) => emit('item-planned-change', idx, v)"
                @planned-item-created="emit('planned-item-created')"
                @planned-item-deleted="emit('planned-item-deleted')" />
            </div>
          </td>
        </tr>
        </template>
        </template>
        </template>
        <tr v-if="!items.length">
          <td :colspan="totalColCount" class="text-center text-medium-emphasis py-4">
            Нет позиций. Нажмите «Добавить позицию».
          </td>
        </tr>
      </tbody>
      <tfoot v-if="items.length">
        <tr>
          <td colspan="7" class="text-right pr-3 py-2 text-caption font-weight-bold">НМЦД итого:</td>
          <td class="py-2 font-weight-bold text-blue-darken-2">
            {{ totalNmck.toLocaleString('ru-RU') }} ₽
          </td>
          <td :colspan="totalColCount - 8"></td>
        </tr>
      </tfoot>
    </v-table>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import InlineProductMatch from '@/components/items/InlineProductMatch.vue'
import FeoTreeSelect from '@/components/items/FeoTreeSelect.vue'
import FeoPlannedItemsSelect from '@/components/items/FeoPlannedItemsSelect.vue'
import type { MatchCandidate } from '@/composables/useItemMatching'
import type { FeoPlanSelection, FeoPlanPosition } from '@/composables/useFeoPlannedResiduals'
import type { Contractor, ProductLike, ItemsDisplayRow } from '@/components/items/types'
import type { FeoNode } from '@/composables/useFeoLeaves'

// EditorItem is structurally identical to the parent's; kept loose here since the
// parent owns the canonical definition and passes its own objects through.
type EditorItem = any

// Perf: only enable content-visibility virtualization above this row count so
// small lists render identically to before.
const VIRT_THRESHOLD = 40

const props = defineProps<{
  items: EditorItem[]
  readonly: boolean
  // Владелец (2026-08-19): согласующий заявки видит состав заблокированным
  // (readonly=true), но должен иметь возможность перераспределить категорию/
  // плановую позицию ФЭО построчно — см. одноимённый проп в PurchaseItemsEditor.vue.
  // Действует ТОЛЬКО на FeoTreeSelect/FeoPlannedItemsSelect ниже (см. feoReadonly),
  // остальные поля строки остаются readonly как есть.
  feoAttrsEditable?: boolean
  // Шаг 2 «план ≠ факт» (сессия 2026-08-06): закупка объявлена (статус «Ведётся
  // работа» и далее) — кол-во/цена ТЗ заморожены. Считается в родителе
  // (PurchaseItemsEditor.vue::tzFrozen) по purchaseStatus.
  tzFrozen?: boolean
  allowedItemTypes: string[]
  vatMode: 'uniform' | 'per_item'
  feoPerItem: boolean
  // F-PLAN: разные плановые позиции плана закупок (Ур.5 ФЭО) для каждого товара
  feoPlannedPerItem?: boolean
  // Владелец (сессия 2026-08-17): показать построчный пикер/кнопку «Создать в плане
  // закупок» ДАЖЕ когда feoPerItem=false (общая категория ФЭО на всю закупку) — см.
  // комментарий у одноимённого пропа в PurchaseItemsEditor.vue.
  allowPerItemPlan?: boolean
  // Фолбэк категории для построчного FeoPlannedItemsSelect, когда у самой позиции
  // своей feo_node_id/feo_category_id нет (обычный случай в общем режиме — категория
  // выбирается один раз в шапке, а не на каждой строке).
  defaultFeoCategoryId?: number | null
  plannedItems?: any[]
  // F-PLAN2: производный выбор { kind, id } | null для FeoPlannedItemsSelect по
  // фактическим полям позиции (feo_planned_item_id / feo_category_id / over_plan) —
  // см. plannedSelectionFor() в PurchaseItemsEditor.vue (общая логика для всех 3 таблиц).
  plannedSelectionFor?: (item: EditorItem) => FeoPlanSelection | null
  // Жалоба владельца (сессия 2026-08-19): «выбрано»/«остаток» не учитывали переключатели,
  // включённые ПРЯМО СЕЙЧАС в этой форме — только серверные числа. Карта
  // feo_planned_item_id → сумма позиций ЭТОЙ формы (см. pendingByPlannedItem в
  // PurchaseItemsEditor.vue), прокидывается как есть в FeoPlannedItemsSelect.
  pendingByPlannedItem?: Record<number, number> | null
  // Владелец (сессия 2026-08-19): «где эта корзиночка?» — корзинка построчного удаления
  // плановой позиции (FeoPlannedItemsSelect) нужна знать, «откуда удаляют», см. одноимённый
  // проп в FeoPlannedItemsSelect.vue / PurchaseItemsEditor.vue.
  purchaseId?: number | null
  // Шаг 5 «ТЗ не дороже и не больше плана» (владелец, 2026-08-07): найти плановую
  // строку позиции (для подписи «план: N шт / N ₽») и проверить превышение
  // (для подсветки) — обе считаются один раз в родителе (см. planForItem/
  // planExcessFor в PurchaseItemsEditor.vue), тот же источник, что и
  // plannedSelectionFor выше.
  planForItem?: (item: EditorItem) => FeoPlanPosition | null
  planExcessFor?: (item: EditorItem) => { plan: FeoPlanPosition; qtyOver: boolean; priceOver: boolean; totalOver: boolean } | null
  showContractorColumn: boolean
  showNeededDate?: boolean
  contractors: Contractor[]
  contractorLookupLoading: Record<number, boolean>
  selectedItemIdxs: number[]
  allItemsSelected: boolean
  totalNmck: number
  feoLeaves: any[]
  feoNodes: FeoNode[]
  // Задача владельца 2026-08-06: остаток по каждому узлу дерева ФЭО — считается один
  // раз в родителе (см. composables/useFeoNodeAmounts), прокидывается в FeoTreeSelect.
  nodeAmounts?: Record<number, { budget: number; free: number }> | null
  subsidyId?: number | null
  subsidyName?: string | null
  unitOptions: string[]
  vatRateOptions: any[]
  // Pure helper / computed-bound function props supplied by the parent:
  resizeStyle: (key: string) => Record<string, string>
  onResizeStart: (e: MouseEvent, key: string) => void
  isOverBudget: (item: EditorItem) => boolean
  overBudgetDelta: (item: EditorItem) => number
  isFeoMissing: (item: EditorItem) => boolean
  fmtRub: (v: number) => string
  formatNumber: (v: number | null | undefined) => string
  parseNumber: (v: string) => number | null
  contractorFilter: (value: string, query: string, item?: any) => boolean
  productPhotoSrc?: (p: ProductLike | null | undefined) => string | undefined
  // Optional grouped/filtered render order (see ItemsDisplayRow). When absent,
  // rows render in natural items[] order exactly as before.
  displayRows?: ItemsDisplayRow[] | null
}>()

const virtualize = computed(() => props.items.length > VIRT_THRESHOLD)

// Шаг 2 «план ≠ факт»: кол-во/цена ТЗ недоступны для правки, если закупка уже
// объявлена (см. ItemsTableStages.vue — тот же паттерн).
const tzDisabled = computed(() => props.readonly || !!props.tzFrozen)
const tzFrozenTooltip = 'Закупка объявлена — кол-во и цена ТЗ зафиксированы. Итоговую цену по результатам закупки внесите в договоре закупки.'
// См. feoAttrsEditable выше — построчные ФЭО-контролы остаются кликабельными
// даже при readonly=true, если родитель явно это разрешил.
const feoReadonly = computed(() => props.readonly && !props.feoAttrsEditable)

const bodyRows = computed<ItemsDisplayRow[]>(() =>
  props.displayRows ?? props.items.map((_, i) => ({ idx: i }))
)

const totalColCount = computed(() =>
  10 + (props.vatMode === 'per_item' ? 1 : 0) + (props.showNeededDate ? 1 : 0) + (props.showContractorColumn ? 1 : 0)
)

const emit = defineEmits<{
  'toggle-select-all': [val: boolean | null]
  'toggle-item-select': [idx: number, val: boolean | null]
  'inline-match-pick': [idx: number, candidate: MatchCandidate]
  'inline-match-create-new': [idx: number]
  'inline-match-clear': [idx: number]
  'open-quick-product-edit': [item: EditorItem]
  'confirm-match': [idx: number]
  'calc-item-total': [idx: number]
  'vat-rate-change': [idx: number, v: any]
  'remove-item': [idx: number]
  'split-item': [idx: number]
  'contractor-search-input': [idx: number, search: string]
  'item-contractor-select': [idx: number, val: Contractor | null]
  'open-contractor-quick-create': [idx: number]
  'item-feo-change': [idx: number, val: number | null]
  'item-planned-change': [idx: number, val: FeoPlanSelection | null]
  'item-pick-unallocated': [idx: number, parentId: number | null]
  'item-type-change': [idx: number, val: string]
  'items-changed': []
  'planned-item-created': []
  'planned-item-deleted': []
}>()
</script>

<style scoped>
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

/* F-PIF2: soft-warning при превышении FEO плана */
.feo-over-budget :deep(.v-field) {
  background: rgba(255, 193, 7, 0.08);
  border-color: rgba(255, 193, 7, 0.5);
}
.feo-missing :deep(.v-field) {
  background: rgba(244, 67, 54, 0.06);
  border-color: rgba(244, 67, 54, 0.5);
}

/* Шаг 5 «ТЗ не дороже и не больше плана» (владелец, 2026-08-07): подсветка
   ДО отправки — зеркалит backend-гейт assert_tz_not_over_plan, чтобы 409
   не был первым, что видит пользователь. */
.tz-over-plan :deep(.v-field) {
  background: rgba(244, 67, 54, 0.08);
  border-color: rgb(244, 67, 54);
}
.plan-hint {
  line-height: 1.3;
  margin-top: 2px;
}

/* Perf: content-visibility virtualization for large lists (> VIRT_THRESHOLD).
   Browser skips layout/paint of offscreen rows; contain-intrinsic-size reserves
   an approximate row height so scroll position / scrollbar stay stable. Applied
   only via the cv-row class which is toggled on when items.length > threshold. */
.cv-row {
  content-visibility: auto;
  contain-intrinsic-size: auto 88px;
}

/* ФЭО-подстрока (полная ширина, под строкой позиции) — визуально примыкает к
   родительской строке, без собственной верхней границы/фона. */
.feo-attrs-row td {
  border-top: none;
  padding-top: 0;
}

/* Группировка позиций по категориям/видам: строки-заголовки групп */
.items-group-header td {
  background: rgba(var(--v-theme-primary), 0.06);
  border-top: 1px solid rgba(var(--v-theme-primary), 0.2);
}
.items-group-header--type td {
  background: rgba(var(--v-theme-primary), 0.03);
  border-top: 1px dashed rgba(var(--v-theme-primary), 0.15);
}

/* SN-UX: шрифт 12px во всех inline-полях flat-таблицы позиций */
.items-flat-table :deep(.v-field__input) { font-size: 12px !important; }
.items-flat-table :deep(.v-field__field) { font-size: 12px; }
.items-flat-table :deep(.v-select__selection) { font-size: 12px; }
.items-flat-table :deep(.v-autocomplete .v-field__input) { font-size: 12px !important; }
.items-flat-table :deep(.v-textarea .v-field__input) { font-size: 12px !important; }
</style>
