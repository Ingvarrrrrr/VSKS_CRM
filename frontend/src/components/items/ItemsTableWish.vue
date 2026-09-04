<template>
  <!-- Presentational wish-shape items table. Holds NO business state — props in,
       events out. Parent owns localItems and every handler. Uses InlineProductMatch
       per row + an always-visible inline contractor picker.
       Extracted from PurchaseItemsEditor.vue (Layer 3). -->
  <div class="overflow-x-auto">
    <v-table density="compact">
      <thead>
        <tr>
          <th style="width:36px;padding:0 4px;text-align:center">
            <v-checkbox :model-value="allItemsSelected" density="compact" hide-details :rules="[]"
              :indeterminate="selectedItemIdxs.length > 0 && !allItemsSelected"
              @update:model-value="(v: boolean | null) => emit('toggle-select-all', v)" />
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
        <!-- Perf: content-visibility:auto for large lists (> VIRT_THRESHOLD) skips
             layout/paint of offscreen rows. Small lists render identically (no class). -->
        <tr v-for="(item, idx) in items" :key="item._uid ?? idx"
          :class="{ 'cv-row': virtualize }">
          <td style="width:36px;padding:0 4px;text-align:center">
            <v-checkbox :model-value="selectedItemIdxs.includes(idx)" density="compact" hide-details :rules="[]"
              @update:model-value="(val: boolean | null) => emit('toggle-item-select', idx, val)" />
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

              <!-- BUG #5: inline catalog matching dropdown (no dialog dive) -->
              <InlineProductMatch
                class="my-1 flex-grow-1"
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
              :disabled="readonly"
              @update:model-value="(v: Contractor | null) => emit('item-contractor-select', idx, v)"
              @update:search="(s: string) => emit('contractor-search-input', idx, s)"
            >
              <template #no-data>
                <v-list-item>
                  <v-alert type="warning" density="compact" variant="tonal" class="text-caption ma-0">
                    Контрагент не найден в БД.
                  </v-alert>
                  <v-btn size="x-small" color="primary" variant="tonal" class="mt-1" prepend-icon="mdi-plus"
                    @click.stop="emit('open-contractor-quick-create', idx)">
                    Создать нового
                  </v-btn>
                </v-list-item>
              </template>
            </v-autocomplete>
          </td>
          <td>
            <v-select v-model="item.item_type"
              :items="allowedItemTypes.map(t => ({ value: t, title: t.charAt(0).toUpperCase() + t.slice(1) }))"
              item-title="title" item-value="value" density="compact" variant="outlined"
              hide-details class="my-1" :disabled="readonly" />
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
            <PriceFreshnessStamp :price-meta="item._price_meta" />
          </td>
          <td>
            <v-text-field :model-value="formatNumber(item.total_price)" readonly density="compact"
              variant="outlined" hide-details bg-color="grey-lighten-4" class="my-1" />
          </td>
          <td>
            <v-btn icon="mdi-delete-outline" variant="text" size="small" color="error"
              :disabled="readonly"
              @click="emit('remove-item', idx)" />
          </td>
        </tr>
        <tr v-if="!items.length">
          <td colspan="9" class="text-center text-medium-emphasis py-4">
            Нет позиций. Нажмите «Добавить позицию».
          </td>
        </tr>
      </tbody>
      <tfoot v-if="items.length">
        <tr>
          <td colspan="6" class="text-right pr-3 py-2 text-caption font-weight-bold">НМЦД итого:</td>
          <td class="py-2 font-weight-bold text-blue-darken-2">
            {{ totalNmck.toLocaleString('ru-RU') }} ₽
          </td>
          <td colspan="2"></td>
        </tr>
      </tfoot>
    </v-table>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import InlineProductMatch from '@/components/items/InlineProductMatch.vue'
import PriceFreshnessStamp from '@/components/items/PriceFreshnessStamp.vue'
import type { MatchCandidate } from '@/composables/useItemMatching'
import type { Contractor } from '@/components/items/types'

type EditorItem = any

// Perf: only enable content-visibility virtualization above this row count so
// small lists render identically to before.
const VIRT_THRESHOLD = 40

const props = defineProps<{
  items: EditorItem[]
  readonly: boolean
  allowedItemTypes: string[]
  contractors: Contractor[]
  selectedItemIdxs: number[]
  allItemsSelected: boolean
  totalNmck: number
  unitOptions: string[]
  formatNumber: (v: number | null | undefined) => string
  parseNumber: (v: string) => number | null
  contractorFilter: (value: string, query: string, item?: any) => boolean
}>()

const virtualize = computed(() => props.items.length > VIRT_THRESHOLD)

const emit = defineEmits<{
  'toggle-select-all': [val: boolean | null]
  'toggle-item-select': [idx: number, val: boolean | null]
  'inline-match-pick': [idx: number, candidate: MatchCandidate]
  'inline-match-create-new': [idx: number]
  'inline-match-clear': [idx: number]
  'open-quick-product-edit': [item: EditorItem]
  'calc-item-total': [idx: number]
  'remove-item': [idx: number]
  'contractor-search-input': [idx: number, search: string]
  'item-contractor-select': [idx: number, val: Contractor | null]
  'open-contractor-quick-create': [idx: number]
}>()
</script>

<style scoped>
/* Perf: content-visibility virtualization for large wish lists (> VIRT_THRESHOLD).
   Browser skips layout/paint of offscreen rows; contain-intrinsic-size reserves an
   approximate row height so scroll/scrollbar stay stable. Toggled via cv-row class. */
.cv-row {
  content-visibility: auto;
  contain-intrinsic-size: auto 88px;
}
</style>
