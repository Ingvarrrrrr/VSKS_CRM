<template>
  <!-- Split purchase kanban dialog -->
  <v-dialog v-model="open" max-width="1200" scrollable :fullscreen="mobile">
    <v-card>
      <v-card-title class="pa-4 pb-2">
        <v-icon class="mr-2" color="primary">mdi-call-split</v-icon>
        Разбить закупку на несколько
        <span class="text-caption text-medium-emphasis ml-3">
          · Перетащите позиции по колонкам, затем «Разбить на N закупок»
        </span>
      </v-card-title>
      <v-card-text class="pa-4">
        <PurchaseSplitKanban
          v-if="open && items.length && purchaseId"
          :purchase-id="purchaseId"
          :items="items"
          @split="$emit('split', $event)"
          @cancel="open = false"
          @error="(m: string) => $emit('error', m)"
        />
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { useDisplay } from 'vuetify'
import PurchaseSplitKanban from '@/components/PurchaseSplitKanban.vue'

const open = defineModel<boolean>({ default: false })

defineProps<{
  purchaseId: number | null
  items: any[]
}>()

defineEmits<{
  (e: 'split', result: { purchase_ids: number[]; count: number; source_purchase_id: number }): void
  (e: 'error', message: string): void
}>()

const { mobile } = useDisplay()
</script>
