<template>
  <div class="chart-card" style="height:100%;overflow:auto">
    <div class="chart-card-header">
      <v-icon icon="mdi-clipboard-list-outline" size="18" color="#14B8A6" class="mr-2" />
      <span class="chart-card-title">Последние закупки</span>
      <span class="chart-link ml-auto" style="cursor:pointer" @click="goToOrders">Все →</span>
    </div>
    <div v-if="loadingPurchases" class="chart-empty">
      <v-progress-circular indeterminate size="32" color="primary" />
    </div>
    <div v-else-if="recentPurchases.length === 0" class="chart-empty">
      <v-icon icon="mdi-cart-off" size="48" color="grey-lighten-2" />
      <div class="text-caption text-medium-emphasis mt-2">Нет закупок</div>
    </div>
    <div v-else class="purchase-list">
      <div
        v-for="p in recentPurchases" :key="p.id"
        class="purchase-row"
        @click="$router.push(`/orders/${p.id}/edit`)"
      >
        <div class="purchase-num">
          <v-icon icon="mdi-package-variant" size="16" :color="statusColorHex(p.status)" />
        </div>
        <div class="purchase-main">
          <div class="purchase-name">{{ p.subject || p.items?.[0]?.item_name || p.item_name || 'Без названия' }}</div>
          <div class="purchase-meta">
            {{ p.registry_number || p.order_number || '—' }}
            <span v-if="p.contractor_name"> · {{ p.contractor_name }}</span>
          </div>
        </div>
        <div class="purchase-right">
          <div class="purchase-amount">{{ formatCurrencyShort(purchaseEffectivePrice(p)) }}</div>
          <v-chip size="x-small" :color="statusColor(p.status)" variant="flat" class="mt-1">
            {{ statusLabel(p.status) }}
          </v-chip>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'

const props = defineProps<{
  loadingPurchases: boolean
  recentPurchases: any[]
  selectedSubsidyIds: number[]
  formatCurrencyShort: (v: number) => string
  statusColorHex: (s: string) => string
  statusColor: (s: string) => string
  statusLabel: (s: string) => string
  purchaseEffectivePrice: (p: any) => number
}>()

const router = useRouter()

function goToOrders() {
  const ids = props.selectedSubsidyIds
  if (ids.length === 1) {
    router.push(`/orders?subsidy_id=${ids[0]}`)
  } else {
    router.push('/orders')
  }
}
</script>
