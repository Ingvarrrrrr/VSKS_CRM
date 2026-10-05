<template>
  <div class="orders-stage-kpis">
    <div v-for="card in cards" :key="card.key" class="orders-stage-kpi"
      :class="{ 'orders-stage-kpi-active': active === card.key }"
      @click="emit('stage-click', card.key)">
      <div class="orders-stage-kpi-value">{{ formatMoney(card.value) }}</div>
      <div class="orders-stage-kpi-label">{{ card.label }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
// OrdersStageKpiCards.vue — 4 карточки этапов над реестром «Закупки»
// (решение владельца 05.10.2026): «Заключён договор / Заказано / Поставлено /
// Оплачено», накопительно — суммы приходят из useOrdersStageKpis (ТОТ ЖЕ
// бэк-источник, что карточка субсидии/дашборд, Правило №6). formatMoney —
// единый форматтер (копейки: «4 777 721,20»), не toLocaleString по месту.
import { computed } from 'vue'
import { formatMoney } from '@/utils/formatMoney'

const props = defineProps<{
  contracts: number
  ordered: number
  delivered: number
  paid: number
  active?: string | null
}>()

const emit = defineEmits<{ 'stage-click': [key: string] }>()

const cards = computed(() => [
  { key: 'contracts', label: 'Заключён договор', value: props.contracts },
  { key: 'ordered',   label: 'Заказано',          value: props.ordered },
  { key: 'delivered', label: 'Поставлено',        value: props.delivered },
  { key: 'paid',       label: 'Оплачено',          value: props.paid },
])
</script>

<style scoped>
.orders-stage-kpis {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}
.orders-stage-kpi {
  flex: 1 1 180px;
  min-width: 160px;
  background: #fff;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 10px;
  padding: 10px 14px;
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.orders-stage-kpi:hover {
  border-color: #fb923c;
  box-shadow: 0 1px 6px rgba(251, 146, 60, 0.18);
}
.orders-stage-kpi-active {
  border-color: #fb923c;
  background: rgba(251, 146, 60, 0.07);
}
.orders-stage-kpi-value {
  font-size: 18px;
  font-weight: 700;
  line-height: 1.2;
}
.orders-stage-kpi-label {
  font-size: 12.5px;
  opacity: 0.7;
  margin-top: 2px;
}
</style>
