<template>
  <v-dialog v-model="show" max-width="700" scrollable :fullscreen="mobile">
    <v-card>
      <v-card-title class="text-h6 pt-4 px-5 d-flex align-center gap-2">
        <v-icon :icon="'mdi-cart-outline'" :color="statusColors[statusDrillStatus] || 'grey'" />
        {{ statusLabels[statusDrillStatus] || statusDrillStatus }}<span v-if="statusDrillStatuses.length > 1" class="text-medium-emphasis">&nbsp;(и далее)</span>
        <v-chip size="x-small" variant="tonal" class="ml-1">{{ statusDrillPurchases.length }} шт.</v-chip>
      </v-card-title>
      <v-card-text class="pa-0">
        <v-table density="compact">
          <thead>
            <tr>
              <th class="px-4">№</th>
              <th class="px-4">Предмет закупки</th>
              <th class="text-right px-4">Сумма</th>
              <th class="px-4">Субсидия</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in statusDrillPurchases" :key="p.id"
              style="cursor:pointer" @click="$router.push(`/orders/${p.id}/edit`); show = false">
              <td class="px-4 text-medium-emphasis">{{ p.purchase_number || p.id }}</td>
              <td class="px-4 py-2" style="max-width:280px;white-space:normal;font-size:13px">{{ p.subject || p.item_name || '—' }}</td>
              <td class="text-right px-4 font-weight-medium text-primary">{{ formatCurrency(purchaseEffectivePrice(p)) }}</td>
              <td class="px-4 text-caption text-medium-emphasis">{{ p.subsidy_name || '—' }}</td>
            </tr>
            <tr v-if="statusDrillPurchases.length === 0">
              <td colspan="4" class="text-center py-6 text-medium-emphasis">Нет закупок</td>
            </tr>
          </tbody>
        </v-table>
      </v-card-text>
      <v-card-actions class="px-5 pb-4">
        <v-btn
          v-if="statusDrillPurchases.length > 0"
          color="success" variant="tonal" prepend-icon="mdi-microsoft-excel"
          @click="$emit('export-xlsx')"
        >Скачать Excel</v-btn>
        <v-spacer /><v-btn @click="show = false">Закрыть</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
defineProps<{
  mobile: boolean
  statusDrillStatus: string
  statusDrillStatuses: string[]
  statusDrillPurchases: any[]
  statusLabels: Record<string, string>
  statusColors: Record<string, string>
  formatCurrency: (v: number) => string
  purchaseEffectivePrice: (p: any) => number
}>()

defineEmits<{
  (e: 'export-xlsx'): void
}>()

const show = defineModel<boolean>({ required: true })
</script>
