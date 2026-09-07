<template>
  <div>
    <v-row dense>
      <v-col v-for="item in pagedCards" :key="item.id" cols="12" sm="6" lg="4">
        <v-card variant="outlined" class="h-100 d-flex flex-column" hover @click="router.push(`/orders/${item.id}/edit`)">
          <!-- Владелец, 2026-08-13: остановка закупки — крупный алерт на всю ширину карточки -->
          <div v-if="item.stopped_at" class="purchase-stopped-banner ma-2 mb-0">
            <v-icon icon="mdi-alert-octagon" size="18" class="mr-1" />
            <span class="purchase-stopped-banner__title">ЗАКУПКА ОСТАНОВЛЕНА</span>
            <span class="purchase-stopped-banner__meta">{{ stoppedPurchaseLine(item) }}</span>
          </div>
          <v-card-item class="pb-1">
            <template #prepend>
              <v-checkbox-btn :model-value="isOrderSelected(item)" density="compact" @click.stop @update:model-value="toggleOrderSelected(item)" />
            </template>
            <v-card-title class="text-body-2 d-flex align-center ga-2">
              <span class="font-weight-bold">{{ item.registry_number || ('#' + item.id) }}</span>
              <v-chip :color="STATUS_COLOR[item.status] || 'grey'" size="x-small" variant="tonal">{{ statusLabelFor(item) }}</v-chip>
            </v-card-title>
          </v-card-item>
          <v-card-text class="py-1 flex-grow-1">
            <div class="text-body-2 font-weight-medium mb-1" style="overflow-wrap:anywhere">{{ item.subject || item.item_name || '—' }}</div>
            <div class="d-flex flex-wrap ga-1 mb-2">
              <v-chip :color="purchaseTypeColor(item)" size="x-small" variant="tonal">{{ purchaseTypeLabel(item) }}</v-chip>
              <v-chip v-if="item.approval_status" :color="APPROVAL_STATUS_COLOR[item.approval_status]" size="x-small" variant="tonal">{{ APPROVAL_STATUS_LABEL[item.approval_status] }}</v-chip>
              <v-chip v-if="item.feo_excess" size="x-small" :color="feoExcessChip(item).color" variant="flat"
                :title="feoExcessChip(item).title"
              >
                <v-icon icon="mdi-alert-decagram" size="12" class="mr-1" />{{ feoExcessChip(item).text }}
              </v-chip>
              <v-chip v-if="item.feo_mismatch" size="x-small" color="amber-darken-3" variant="flat"
                :title="(item.feo_mismatch_items || []).map((mi: any) => mi.message).join(' | ')"
              >
                <v-icon icon="mdi-alert" size="12" class="mr-1" />Расхождение ФЭО
              </v-chip>
            </div>
            <div class="text-caption text-medium-emphasis">Контрагент</div>
            <div class="text-body-2 mb-1" style="overflow-wrap:anywhere">{{ item.contractor_name || '—' }}</div>
            <div class="text-caption text-medium-emphasis">Субсидия</div>
            <div class="text-body-2 mb-1">{{ item.subsidy_name || '—' }}</div>
            <div class="d-flex justify-space-between mt-2">
              <div>
                <div class="text-caption text-medium-emphasis">Сумма</div>
                <div class="text-body-1 font-weight-bold">{{ formatMoney(effectivePrice(item)) }}</div>
              </div>
              <div class="text-right">
                <div class="text-caption text-medium-emphasis">Договор</div>
                <div class="text-body-2">{{ item.contract_date ? formatDate(item.contract_date) : '—' }}</div>
              </div>
            </div>
          </v-card-text>
          <v-divider />
          <v-card-actions class="py-1" @click.stop>
            <v-btn v-if="nextStatus(item.status)" size="x-small" :color="STATUS_COLOR[nextStatus(item.status)!]" variant="tonal" :loading="transitioning === item.id" @click.stop="emit('transition', item)">→ {{ statusLabelFor(item, nextStatus(item.status)!) }}</v-btn>
            <v-spacer />
            <!-- Phase 32: file badge -->
            <v-chip
              v-if="(item.files_count ?? 0) > 0"
              size="x-small" variant="tonal" color="teal"
              prepend-icon="mdi-paperclip"
              class="cursor-pointer"
              @click.stop="emit('open-files', item)"
            >{{ item.files_count }}</v-chip>
            <v-btn v-if="isAdmin" icon="mdi-delete" variant="text" size="small" color="error" @click.stop="emit('delete-one', item)" />
          </v-card-actions>
        </v-card>
      </v-col>
    </v-row>
    <div v-if="!pagedCards.length" class="text-center py-10">
      <v-icon icon="mdi-clipboard-text-outline" size="48" color="grey-lighten-1" class="mb-3" />
      <div class="text-medium-emphasis">Закупки не найдены</div>
    </div>
    <div v-if="cardsTotalPages > 1" class="d-flex justify-center mt-4">
      <v-pagination :model-value="cardsPage" @update:model-value="v => emit('update:cardsPage', v)" :length="cardsTotalPages" density="compact" total-visible="7" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { formatMoney } from '@/utils/formatMoney'
import {
  STATUS_COLOR, APPROVAL_STATUS_COLOR, APPROVAL_STATUS_LABEL,
  effectivePrice, formatDate, statusLabelFor, purchaseTypeLabel, purchaseTypeColor,
  feoExcessChip, stoppedPurchaseLine, nextStatus,
} from '@/composables/orders/ordersLabels'
import type { Purchase } from '@/composables/orders/ordersTypes'

defineProps<{
  pagedCards: any[]
  cardsPage: number
  cardsTotalPages: number
  isOrderSelected: (item: any) => boolean
  toggleOrderSelected: (item: any) => void
  isAdmin: boolean
  transitioning: number | null
}>()

const emit = defineEmits<{
  'update:cardsPage': [v: number]
  transition: [item: Purchase]
  'delete-one': [item: Purchase]
  'open-files': [item: Purchase]
}>()

const router = useRouter()
</script>

<style scoped>
/* Владелец, 2026-08-13: «остановка закупки» — крупный алерт в красной рамке, а
   не мелкий чип (тот же приём, что и wish-stopped-banner в WishesView.vue). */
.purchase-stopped-banner {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  column-gap: 10px;
  row-gap: 2px;
  width: 100%;
  border: 2px solid #d32f2f;
  background: #fdecea;
  color: #b71c1c;
  border-radius: 6px;
  padding: 6px 10px;
  margin-bottom: 6px;
}
.purchase-stopped-banner__title {
  font-weight: 800;
  font-size: 0.92rem;
  letter-spacing: 0.02em;
}
.purchase-stopped-banner__meta {
  font-size: 0.78rem;
  font-weight: 500;
  opacity: 0.9;
}
</style>
