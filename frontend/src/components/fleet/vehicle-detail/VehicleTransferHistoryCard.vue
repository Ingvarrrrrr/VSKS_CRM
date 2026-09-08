<!-- История передач ТС между владельцами/эксплуатантами. -->
<template>
  <v-card class="vp-box mb-4">
    <v-card-title class="vp-box__title">
      <v-icon icon="mdi-swap-horizontal" size="small" class="mr-2" />
      История передач
      <BlockHint block-key="transfer_history" />
    </v-card-title>
    <v-card-text>
      <div v-if="loading" class="text-center py-4">
        <v-progress-circular indeterminate size="28" color="primary" />
      </div>
      <div v-else-if="items.length === 0" class="text-medium-emphasis text-body-2">
        История пуста — передачи не фиксировались
      </div>
      <v-timeline v-else density="compact" side="end">
        <v-timeline-item
          v-for="item in items"
          :key="item.id"
          :dot-color="item.from_owner_org_id !== item.to_owner_org_id ? 'orange' : 'blue'"
          size="small"
        >
          <div class="text-body-2 font-weight-medium">
            {{ formatDate(item.changed_at) }}
            <template v-if="item.from_owner_org_id !== item.to_owner_org_id">— смена владельца</template>
            <template v-else>— смена эксплуатанта</template>
          </div>
          <div class="text-body-2 text-medium-emphasis">
            <template v-if="item.from_assigned_org_id || item.to_assigned_org_id">
              {{ item.from_assigned_text || '—' }} → {{ item.to_assigned_text || '—' }}
            </template>
          </div>
          <div v-if="item.basis" class="text-caption text-medium-emphasis">
            {{ item.basis }}<template v-if="item.doc_number"> № {{ item.doc_number }}</template>
            <template v-if="item.doc_date"> от {{ formatDate(item.doc_date) }}</template>
          </div>
          <div v-if="item.comment" class="text-caption text-medium-emphasis">{{ item.comment }}</div>
        </v-timeline-item>
      </v-timeline>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
import BlockHint from './BlockHint.vue'
import type { TransferHistoryItem } from '@/composables/fleet/vehicleDetailTypes'

defineProps<{
  items: TransferHistoryItem[]
  loading: boolean
  formatDate: (d?: string | null) => string
}>()
</script>
