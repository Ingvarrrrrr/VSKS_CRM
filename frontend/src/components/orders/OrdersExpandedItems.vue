<template>
  <div class="pa-3">
    <PurchaseStoppedBanner
      v-if="item.stopped_at"
      class="mb-3"
      :stopped-by-name="item.stopped_by_name"
      :stopped-at="item.stopped_at"
      :stopped-reason="item.stopped_reason"
    />
    <v-table density="compact" class="rounded border expand-items-table">
      <colgroup>
        <col style="width: auto">
        <col style="width: 140px">
        <col style="width: 110px">
        <col style="width: 80px">
        <col style="width: 160px">
        <col style="width: 160px">
      </colgroup>
      <thead>
        <tr class="bg-grey-lighten-4">
          <th>Наименование позиции</th>
          <th>Тип</th>
          <th class="text-right">Кол-во</th>
          <th>Ед.</th>
          <th class="text-right">Цена ед., ₽</th>
          <th class="text-right">Сумма, ₽</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="itm in item.items" :key="itm.id">
          <td>{{ itm.item_name }}</td>
          <td>{{ itm.item_type || '—' }}</td>
          <td class="text-right">{{ itm.quantity ?? '—' }}</td>
          <td>{{ itm.unit || '—' }}</td>
          <td class="text-right">{{ itm.unit_price ? Number(itm.unit_price).toLocaleString('ru-RU') : '—' }}</td>
          <td class="text-right">{{ itm.total_price ? Number(itm.total_price).toLocaleString('ru-RU') : '—' }}</td>
        </tr>
        <tr v-if="!item.items?.length">
          <td colspan="6" class="text-center text-medium-emphasis text-caption py-2">Нет позиций</td>
        </tr>
      </tbody>
    </v-table>
  </div>
</template>

<script setup lang="ts">
import type { Purchase } from '@/composables/orders/ordersTypes'
import PurchaseStoppedBanner from '@/components/orders/PurchaseStoppedBanner.vue'

defineProps<{
  item: Purchase
}>()
</script>

<style scoped>
.expand-items-table :deep(table) { table-layout: fixed; }
.expand-items-table :deep(td),
.expand-items-table :deep(th) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.expand-items-table :deep(td:first-child) {
  white-space: normal;
  word-break: break-word;
}
</style>
