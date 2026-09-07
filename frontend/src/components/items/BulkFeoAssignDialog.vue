<template>
  <!-- ISSUE-3 PART B: bulk-assign FEO level to selected items. Presentational —
       parent owns bulkFeoId/bulkPlannedSelection state and the apply/unallocated
       handlers; this child only renders the picker pair and emits actions.
       Extracted from PurchaseItemsEditor.vue. -->
  <v-dialog v-model="open" max-width="520">
    <v-card :loading="loading">
      <v-card-title class="text-subtitle-1">
        Назначить ФЭО для выбранных ({{ selectedCount }})
      </v-card-title>
      <v-card-text>
        <FeoTreeSelect
          v-model="categoryId"
          :nodes="feoNodes"
          :leaves="feoLeaves"
          :plan-positions="plannedItems"
          :node-amounts="nodeAmounts"
          :allow-unallocated="allowUnallocated"
          :root-label="subsidyName"
          @pick-unallocated="(parentId: number | null) => emit('pick-unallocated', parentId)"
        />
        <!-- F-PLAN: массовый выбор плановой позиции — компонент сам находит дочерние
             конечные элементы, если выбранный в дереве выше узел не лист. -->
        <FeoPlannedItemsSelect
          v-if="feoPlannedPerItem"
          v-model="plannedSelection"
          :category-id="categoryId"
          :nodes="feoNodes"
          :items="plannedItems"
          :prefill="plannedPrefill"
          :purchase-id="purchaseId"
          :exclude-purchase-id="purchaseId"
          class="mt-2"
          @planned-item-created="emit('planned-item-created')"
          @planned-item-deleted="emit('planned-item-deleted')"
        />
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="emit('cancel')">Отмена</v-btn>
        <v-btn color="primary" variant="flat" :disabled="categoryId == null" @click="emit('apply')">
          Применить
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

const open = defineModel<boolean>({ default: false })
const categoryId = defineModel<number | null>('categoryId', { default: null })
const plannedSelection = defineModel<FeoPlanSelection | null>('plannedSelection', { default: null })

defineProps<{
  loading?: boolean
  selectedCount: number
  feoNodes: FeoNode[]
  feoLeaves: FeoLeaf[]
  plannedItems: FeoPlanPosition[]
  nodeAmounts?: Record<number, { budget: number; free: number }> | null
  allowUnallocated?: boolean
  subsidyName?: string | null
  feoPlannedPerItem?: boolean
  purchaseId?: number | null
  plannedPrefill?: { name?: string | null; quantity?: number | null; unit?: string | null; amount?: number | null }
}>()

const emit = defineEmits<{
  'pick-unallocated': [parentId: number | null]
  apply: []
  cancel: []
  'planned-item-created': []
  'planned-item-deleted': []
}>()
</script>
