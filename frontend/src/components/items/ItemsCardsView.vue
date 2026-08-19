<template>
  <!-- Presentational large-card view — editable drop-in alternative to
       ItemsTableFlat for the flat/simple (wish + purchase non-stages) shape.
       Holds NO business state: all data comes in via props, all mutations leave
       via emits with the SAME names/payloads as ItemsTableFlat so the parent's
       handlers work unchanged. Used on mobile (forced) and via the desktop toggle. -->
  <div class="items-cards-view">
    <!-- Select-all header strip (mirrors the table's header checkbox) -->
    <div v-if="items.length" class="d-flex align-center ga-2 mb-2 px-1">
      <v-checkbox :model-value="allItemsSelected" density="compact" hide-details :rules="[]"
        :indeterminate="selectedItemIdxs.length > 0 && !allItemsSelected"
        :disabled="readonly"
        @update:model-value="(v: boolean | null) => emit('toggle-select-all', v)" />
      <span class="text-caption text-medium-emphasis">Выбрать все</span>
    </div>

    <template v-for="(row, rPos) in bodyRows" :key="row.header != null ? `gh-${rPos}` : (items[row.idx!]?._uid ?? row.idx)">
    <div v-if="row.header != null" class="items-group-header-card d-flex align-center ga-1 px-2 py-1 mb-2"
      :class="row.level === 2 ? 'items-group-header-card--type ml-4' : ''">
      <v-icon size="14">{{ row.level === 2 ? 'mdi-shape-outline' : 'mdi-folder-outline' }}</v-icon>
      <span class="font-weight-bold" style="font-size:12px">{{ row.header }}</span>
      <span class="text-medium-emphasis" style="font-size:11px">{{ row.count }} поз. · {{ fmtRub(row.sum || 0) }}</span>
    </div>
    <template v-else>
    <v-card
      v-for="{ item, idx } in [{ item: items[row.idx!], idx: row.idx! }]"
      :key="item._uid ?? idx"
      variant="outlined"
      class="mb-3 item-card"
      :class="{ 'cv-card': virtualize }"
    >
      <!-- Split (top-right, absolute, next to delete) — владелец 2026-08-18:
           разбивка позиции по разным категориям ФЭО. Только для закупок
           (supportsSplit), не для заявок (wish), от 2 единиц количества. -->
      <v-tooltip v-if="supportsSplit && !readonly && (item.quantity ?? 0) >= 2" text="Разбить по категориям ФЭО" location="top">
        <template #activator="{ props: tip }">
          <v-btn v-bind="tip" icon="mdi-call-split" variant="text" size="small" color="primary"
            class="item-card-split" data-testid="split-item-btn" @click="emit('split-item', idx)" />
        </template>
      </v-tooltip>
      <!-- Delete (top-right, absolute) -->
      <v-btn v-if="!readonly" icon="mdi-delete-outline" variant="text" size="small" color="error"
        class="item-card-delete" @click="emit('remove-item', idx)" />

      <v-row no-gutters>
        <!-- LEFT: big photo + № + select -->
        <v-col cols="12" sm="4" md="3" class="pa-3 d-flex flex-column align-center">
          <div class="d-flex align-center justify-space-between w-100 mb-2">
            <v-chip size="x-small" variant="tonal" color="grey">№ {{ idx + 1 }}</v-chip>
            <v-checkbox :model-value="selectedItemIdxs.includes(idx)" density="compact" hide-details :rules="[]"
              :disabled="readonly"
              @update:model-value="(val: boolean | null) => emit('toggle-item-select', idx, val)" />
          </div>
          <v-img :src="item._photo_url" height="200" width="100%" :cover="false" rounded="lg" class="item-card-photo">
            <template #error>
              <div class="d-flex align-center justify-center fill-height bg-grey-lighten-4">
                <v-icon size="64" class="text-medium-emphasis">mdi-package-variant</v-icon>
              </div>
            </template>
            <template #placeholder>
              <div class="d-flex align-center justify-center fill-height bg-grey-lighten-4">
                <v-icon size="64" class="text-medium-emphasis">mdi-package-variant</v-icon>
              </div>
            </template>
          </v-img>
        </v-col>

        <!-- RIGHT: editable fields -->
        <v-col cols="12" sm="8" md="9" class="pa-3">
          <v-row dense>
            <!-- Name: InlineProductMatch + edit-product + confirm-match -->
            <v-col cols="12">
              <div class="d-flex align-center gap-1 pr-10">
                <InlineProductMatch
                  class="flex-grow-1"
                  style="min-width:240px"
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
            </v-col>

            <!-- Тип (+ ФЭО позиция under it, like the flat table) -->
            <v-col cols="12" sm="6">
              <v-select v-model="item.item_type"
                :items="allowedItemTypes.map(t => ({ value: t, title: t.charAt(0).toUpperCase() + t.slice(1) }))"
                item-title="title" item-value="value" density="compact" variant="outlined"
                :label="feoPerItem ? 'Тип / ФЭО *' : 'Тип'"
                hide-details :disabled="readonly"
                @update:model-value="(v: string) => emit('item-type-change', idx, v)" />
              <template v-if="feoPerItem">
                <FeoTreeSelect
                  :model-value="item.feo_node_id ?? item.feo_category_id"
                  :nodes="feoNodes"
                  :leaves="feoLeaves"
                  :plan-positions="plannedItems || []"
                  :node-amounts="nodeAmounts"
                  :readonly="feoReadonly"
                  :error="isFeoMissing(item)"
                  class="mt-2"
                  :allow-unallocated="!!subsidyId"
                  :root-label="subsidyName"
                  @update:model-value="(v: number | null) => emit('item-feo-change', idx, v)"
                  @pick-unallocated="(parentId: number | null) => emit('item-pick-unallocated', idx, parentId)"
                />
                <div v-if="isOverBudget(item)" class="text-caption text-warning d-flex align-center ga-1 mt-1">
                  <v-icon icon="mdi-alert-outline" size="12" />
                  <span style="font-size:11px">Превышение: {{ fmtRub(overBudgetDelta(item)) }}</span>
                </div>
              </template>
              <!-- F-PLAN: выбор плановой позиции плана закупок (Ур.5 ФЭО) для этой позиции.
                   category-id — узел каскада (лист или промежуточный), НЕ только feo_category_id;
                   владелец 2026-08-17: в общем режиме падает на defaultFeoCategoryId — категорию,
                   выбранную один раз в шапке заявки/закупки. -->
              <FeoPlannedItemsSelect
                v-if="feoPlannedPerItem || allowPerItemPlan"
                :model-value="plannedSelectionFor ? plannedSelectionFor(item) : null"
                :category-id="item.feo_node_id ?? item.feo_category_id ?? defaultFeoCategoryId ?? null"
                :nodes="feoNodes" :items="plannedItems || []"
                :amount="item.total_price" :readonly="feoReadonly" dense class="mt-1"
                :prefill="{ name: item.item_name, quantity: item.quantity, unit: item.unit, amount: item.total_price }"
                @update:model-value="(v) => emit('item-planned-change', idx, v)"
                @planned-item-created="emit('planned-item-created')" />
            </v-col>

            <!-- Кол-во -->
            <v-col cols="6" sm="3">
              <v-text-field v-model.number="item.quantity" type="number" density="compact"
                variant="outlined" label="Кол-во" hide-details :disabled="readonly"
                @update:model-value="emit('calc-item-total', idx)" />
            </v-col>

            <!-- Ед. изм. -->
            <v-col cols="6" sm="3">
              <v-combobox v-model="item.unit" :items="unitOptions" density="compact" variant="outlined"
                label="Ед. изм." hide-details :disabled="readonly" />
            </v-col>

            <!-- Цена ед. -->
            <v-col cols="6" sm="4">
              <v-text-field
                :model-value="formatNumber(item.unit_price)"
                density="compact" variant="outlined" label="Цена ед., ₽" hide-details
                :disabled="readonly"
                @update:model-value="(v: string) => { item.unit_price = parseNumber(v) as any; emit('calc-item-total', idx) }"
              />
            </v-col>

            <!-- Сумма (readonly) -->
            <v-col cols="6" sm="4">
              <v-text-field :model-value="formatNumber(item.total_price)" readonly density="compact"
                variant="outlined" label="Сумма, ₽" hide-details bg-color="grey-lighten-4" />
            </v-col>

            <!-- Страна -->
            <v-col cols="12" sm="4">
              <v-text-field v-model="item.country_origin" density="compact"
                variant="outlined" label="Страна происхождения" hide-details placeholder="РФ" :disabled="readonly" />
            </v-col>

            <!-- Дата поставки (per-item, только при showNeededDate) -->
            <v-col v-if="showNeededDate" cols="12" sm="4">
              <v-text-field
                :model-value="item.needed_date ?? ''"
                type="date" density="compact" variant="outlined" label="Дата поставки" hide-details
                :disabled="readonly"
                @update:model-value="(e: string) => { item.needed_date = e || null; emit('items-changed') }"
              />
            </v-col>

            <!-- НДС (per_item only) -->
            <v-col v-if="vatMode === 'per_item'" cols="6" sm="4">
              <v-combobox v-model="item.vat_rate"
                :items="vatRateOptions"
                item-title="title" item-value="value"
                density="compact" variant="outlined" hide-details
                label="НДС" placeholder="НДС %" :disabled="readonly"
                @update:model-value="emit('vat-rate-change', idx, $event)" />
            </v-col>

            <!-- Контрагент (advance_report mode only) -->
            <v-col v-if="showContractorColumn" cols="12">
              <v-autocomplete
                :model-value="item.contractor_id ? contractors.find(c => c.id === item.contractor_id) || null : null"
                :items="contractors" item-title="name" item-value="id" return-object
                variant="outlined" density="compact" clearable auto-select-first hide-details
                label="Контрагент" :custom-filter="contractorFilter" :loading="contractorLookupLoading[idx] === true"
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
            </v-col>
          </v-row>
        </v-col>
      </v-row>
    </v-card>
    </template>
    </template>

    <div v-if="!items.length" class="text-center text-medium-emphasis py-6">
      Нет позиций. Нажмите «Добавить позицию».
    </div>

    <div v-if="items.length" class="d-flex justify-end pa-2 text-caption font-weight-bold">
      <span>НМЦД итого:&nbsp;</span>
      <span class="text-blue-darken-2">{{ totalNmck.toLocaleString('ru-RU') }} ₽</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import InlineProductMatch from '@/components/items/InlineProductMatch.vue'
import FeoTreeSelect from '@/components/items/FeoTreeSelect.vue'
import FeoPlannedItemsSelect from '@/components/items/FeoPlannedItemsSelect.vue'
import type { MatchCandidate } from '@/composables/useItemMatching'
import type { Contractor, ProductLike, ItemsDisplayRow } from '@/components/items/types'
import type { FeoNode } from '@/composables/useFeoLeaves'
import type { FeoPlanSelection } from '@/composables/useFeoPlannedResiduals'

// EditorItem is structurally identical to the parent's; kept loose here since the
// parent owns the canonical definition and passes its own objects through.
type EditorItem = any

// Perf: only enable content-visibility virtualization above this row count so
// small lists render identically to before. Mirrors ItemsTableFlat's threshold.
const VIRT_THRESHOLD = 40

const props = defineProps<{
  items: EditorItem[]
  readonly: boolean
  // Владелец (2026-08-19): согласующий заявки — состав заблокирован, но построчная
  // категория/плановая позиция ФЭО остаётся редактируемой. См. одноимённый проп в
  // PurchaseItemsEditor.vue и feoReadonly ниже.
  feoAttrsEditable?: boolean
  allowedItemTypes: string[]
  vatMode: 'uniform' | 'per_item'
  feoPerItem: boolean
  // F-PLAN: разные плановые позиции плана закупок (Ур.5 ФЭО) для каждого товара
  feoPlannedPerItem?: boolean
  // Владелец (сессия 2026-08-17): показать построчный пикер/кнопку «Создать в плане
  // закупок» ДАЖЕ когда feoPerItem=false — см. PurchaseItemsEditor.vue.
  allowPerItemPlan?: boolean
  // Фолбэк категории для построчного FeoPlannedItemsSelect, когда у самой позиции
  // своей feo_node_id/feo_category_id нет (обычный случай в общем режиме).
  defaultFeoCategoryId?: number | null
  plannedItems?: any[]
  // F-PLAN2: производный выбор { kind, id } | null для FeoPlannedItemsSelect по
  // фактическим полям позиции — см. plannedSelectionFor() в PurchaseItemsEditor.vue.
  plannedSelectionFor?: (item: EditorItem) => FeoPlanSelection | null
  // Владелец 2026-08-18: показать кнопку «Разбить» на карточке — только у закупок
  // (POST /purchases/{pid}/items/{item_id}/split не существует для заявок/wish-позиций).
  supportsSplit?: boolean
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
  isOverBudget: (item: EditorItem) => boolean
  overBudgetDelta: (item: EditorItem) => number
  isFeoMissing: (item: EditorItem) => boolean
  fmtRub: (v: number) => string
  formatNumber: (v: number | null | undefined) => string
  parseNumber: (v: string) => number | null
  contractorFilter: (value: string, query: string, item?: any) => boolean
  productPhotoSrc?: (p: ProductLike | null | undefined) => string | undefined
  // Optional grouped/filtered render order (see ItemsDisplayRow). When absent,
  // cards render in natural items[] order exactly as before.
  displayRows?: ItemsDisplayRow[] | null
}>()

const virtualize = computed(() => props.items.length > VIRT_THRESHOLD)
// См. feoAttrsEditable в defineProps выше — построчные ФЭО-контролы остаются
// кликабельными даже при readonly=true, если родитель явно это разрешил.
const feoReadonly = computed(() => props.readonly && !props.feoAttrsEditable)

const bodyRows = computed<ItemsDisplayRow[]>(() =>
  props.displayRows ?? props.items.map((_, i) => ({ idx: i }))
)

// Identical contract to ItemsTableFlat — same emit names & payload shapes so the
// parent handlers are wired unchanged.
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
}>()
</script>

<style scoped>
.item-card { position: relative; }
.item-card-delete {
  position: absolute;
  top: 4px;
  right: 4px;
  z-index: 2;
}
.item-card-split {
  position: absolute;
  top: 4px;
  right: 44px;
  z-index: 2;
}
.item-card-photo { background: rgb(var(--v-theme-surface)); }

/* F-PIF2: soft-warning при превышении FEO плана */
.feo-over-budget :deep(.v-field) {
  background: rgba(255, 193, 7, 0.08);
  border-color: rgba(255, 193, 7, 0.5);
}
.feo-missing :deep(.v-field) {
  background: rgba(244, 67, 54, 0.06);
  border-color: rgba(244, 67, 54, 0.5);
}

/* Perf: content-visibility virtualization for large lists (> VIRT_THRESHOLD),
   mirroring ItemsTableFlat. Browser skips layout/paint of offscreen cards;
   contain-intrinsic-size reserves an approximate card height so scroll stays
   stable. Applied only when items.length > threshold. */
.cv-card {
  content-visibility: auto;
  contain-intrinsic-size: auto 240px;
}

/* Группировка позиций по категориям/видам: полоски-заголовки групп */
.items-group-header-card {
  background: rgba(var(--v-theme-primary), 0.06);
  border-left: 3px solid rgba(var(--v-theme-primary), 0.5);
  border-radius: 4px;
}
.items-group-header-card--type {
  background: rgba(var(--v-theme-primary), 0.03);
  border-left-style: dashed;
}
</style>
