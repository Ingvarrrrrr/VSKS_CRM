<template>
  <!-- Разбивка позиции по категориям ФЭО (владелец 2026-08-18): закупка в статусе
       «Заказано» с заморозкой ТЗ (добавлять НОВЫЕ позиции нельзя), но владельцу
       нужно разложить уже существующую позицию (напр. 66 огнетушителей) по нескольким
       категориям ФЭО/плановым позициям — количество и сумма НЕ меняются, меняется
       только распределение. См. POST /purchases/{pid}/items/{item_id}/split.
       Presentational — parent owns `parts` (mutated in place, same as
       ItemsTableFlat/ItemsTableStages row mutation) and the save/derived-totals
       logic. Extracted from PurchaseItemsEditor.vue. -->
  <v-dialog v-model="open" :max-width="dialogWidth" :fullscreen="mobile" :persistent="saving">
    <v-card v-if="item">
      <v-card-title class="text-subtitle-1">
        Разбить позицию «{{ item.item_name || '—' }}»
      </v-card-title>
      <v-card-text>
        <div class="text-caption text-medium-emphasis mb-3">
          Исходное количество: {{ formatNumber(item.quantity) }} {{ item.unit }}
          &nbsp;·&nbsp; цена за единицу: {{ fmtRub(item.unit_price || 0) }}
          &nbsp;·&nbsp; сумма: {{ fmtRub(item.total_price || 0) }}
        </div>

        <div v-for="(part, i) in parts" :key="i" class="split-part-block mb-4 pa-3">
          <div class="d-flex align-center justify-space-between mb-2">
            <span class="text-caption font-weight-bold">Часть {{ i + 1 }}</span>
            <v-btn v-if="parts.length > 2" icon="mdi-close" size="x-small" variant="text" color="error"
              title="Удалить часть" @click="emit('remove-part', i)" />
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
                Сумма части: {{ partAmount(i) != null ? fmtRub(partAmount(i)!) : '—' }}
              </span>
            </v-col>
            <v-col cols="12">
              <FeoTreeSelect
                :model-value="part.feo_node_id"
                :nodes="feoNodes"
                :leaves="feoLeaves"
                :plan-positions="plannedItems"
                :node-amounts="nodeAmounts"
                :allow-unallocated="allowUnallocated"
                :root-label="subsidyName"
                label="Категория ФЭО"
                @update:model-value="(v: number | null) => emit('feo-change', i, v)"
              />
            </v-col>
            <v-col v-if="showPlannedSelect" cols="12">
              <FeoPlannedItemsSelect
                :model-value="plannedSelectionFor(i)"
                :category-id="part.feo_node_id ?? part.feo_category_id"
                :nodes="feoNodes"
                :items="plannedItems"
                :amount="partAmount(i)"
                :purchase-id="purchaseId"
                :exclude-purchase-id="purchaseId"
                dense
                @update:model-value="(v) => emit('planned-change', i, v)"
                @planned-item-created="emit('planned-item-created')"
                @planned-item-deleted="emit('planned-item-deleted')"
              />
            </v-col>
          </v-row>
        </div>

        <v-btn variant="tonal" prepend-icon="mdi-plus" size="small" @click="emit('add-part')">Добавить часть</v-btn>

        <div class="mt-4">
          <span class="text-body-2 font-weight-bold" :class="balanced ? 'text-success' : 'text-error'">
            Распределено {{ formatNumber(distributed) }} из {{ formatNumber(item.quantity) }}
            <template v-if="!balanced">, остаток {{ formatNumber(remaining) }}</template>
          </span>
        </div>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" :disabled="saving" @click="emit('cancel')">Отмена</v-btn>
        <v-btn color="primary" variant="flat" :loading="saving" :disabled="!canSave" @click="emit('save')">
          Разбить
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import FeoTreeSelect from '@/components/items/FeoTreeSelect.vue'
import FeoPlannedItemsSelect from '@/components/items/FeoPlannedItemsSelect.vue'
import type { FeoNode, FeoLeaf } from '@/composables/useFeoLeaves'
import type { FeoPlanPosition, FeoPlanSelection } from '@/composables/useFeoPlannedResiduals'
import { formatNumber, parseNumber, fmtRub } from '@/utils/numberFormat'

// EditorItem/SplitPart are structurally identical to the parent's; kept loose
// here (same convention as ItemsTableFlat.vue) since the parent owns the real
// shape and this dialog only reads/mutates the fields it renders.
type EditorItem = any
type SplitPart = any

const open = defineModel<boolean>({ default: false })

defineProps<{
  saving?: boolean
  mobile?: boolean
  dialogWidth: string | number
  item: EditorItem | null
  parts: SplitPart[]
  feoNodes: FeoNode[]
  feoLeaves: FeoLeaf[]
  plannedItems: FeoPlanPosition[]
  nodeAmounts?: Record<number, { budget: number; free: number }> | null
  allowUnallocated?: boolean
  subsidyName?: string | null
  showPlannedSelect?: boolean
  purchaseId?: number | null
  partAmount: (i: number) => number | null
  plannedSelectionFor: (i: number) => FeoPlanSelection | null
  distributed: number
  remaining: number
  balanced: boolean
  canSave: boolean
}>()

const emit = defineEmits<{
  'remove-part': [i: number]
  'add-part': []
  'feo-change': [i: number, nodeId: number | null]
  'planned-change': [i: number, val: FeoPlanSelection | null]
  'planned-item-created': []
  'planned-item-deleted': []
  save: []
  cancel: []
}>()
</script>
