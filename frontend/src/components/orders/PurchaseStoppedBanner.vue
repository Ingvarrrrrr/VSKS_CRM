<template>
  <div class="purchase-stopped-banner">
    <v-icon icon="mdi-alert-octagon" size="18" class="mr-1" />
    <span class="purchase-stopped-banner__title">ЗАКУПКА ОСТАНОВЛЕНА</span>
    <span class="purchase-stopped-banner__meta">{{ line }}</span>
  </div>
</template>

<script setup lang="ts">
// Владелец, 2026-08-13: «остановка закупки» — крупный алерт на всю ширину.
// Владелец, 2026-09-15: «поставить кнопку остановить/возобновить и в списке,
// и в самой закупке» — раньше эта разметка+CSS были СКОПИРОВАНЫ трижды
// (OrdersTable.vue×2, OrdersCards.vue), теперь единственная точка (ПРАВИЛО №6),
// используется там же и в PurchaseHeader.vue (карточка закупки).
import { computed } from 'vue'
import { stoppedPurchaseLine } from '@/composables/orders/ordersLabels'

const props = defineProps<{
  stoppedByName?: string | null
  stoppedAt?: string | null
  stoppedReason?: string | null
}>()

const line = computed(() => stoppedPurchaseLine({
  stopped_by_name: props.stoppedByName,
  stopped_at: props.stoppedAt,
  stopped_reason: props.stoppedReason,
}))
</script>

<style scoped>
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
