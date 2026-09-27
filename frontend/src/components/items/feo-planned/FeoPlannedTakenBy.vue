<template>
  <!-- Владелец (сессия 2026-09-27, жалоба РЕЕ-2026-00771/РЕЕ-2026-00913): плановая
       позиция может быть УЖЕ целиком занята другой закупкой, а подсказка
       «100% ПРИВЯЗАТЬ»/строка списка молча об этом не говорили — превышение
       вылезало ТОЛЬКО после нажатия «Привязать». Общий компонент (ПРАВИЛО №5/№6) —
       используется и в FeoPlannedMatchSuggestions.vue (под кандидатом подсказки), и
       в FeoPlannedItemRow.vue (в строке списка), чтобы текст/ссылки/форматирование
       денег не разъезжались между двумя местами. -->
  <div v-if="linkedPurchases && linkedPurchases.length" class="feo-taken-by" :class="{ 'feo-taken-by--short': short }">
    <span>{{ short ? 'занято:' : 'Уже занято закупками:' }}</span>
    <template v-for="(p, idx) in linkedPurchases" :key="p.id">
      <router-link
        v-if="p.registry_number"
        :to="`/orders/${p.id}`"
        target="_blank"
        class="feo-taken-by-link"
        @click.stop
      >{{ p.registry_number }}</router-link>
      <span v-else>закупка #{{ p.id }}</span>
      <span v-if="!short"> — {{ fmt(p.amount) }}</span><span v-if="idx < linkedPurchases.length - 1">, </span>
    </template>
    <template v-if="!short">
      <span v-if="shortfall != null && shortfall > 0" class="feo-taken-by-note feo-taken-by-note--error">
        — не хватает {{ fmt(shortfall) }}. Если это та же покупка — это дубль, сначала разберитесь с той закупкой
      </span>
      <span v-else class="feo-taken-by-note feo-taken-by-note--warning">
        — если это та же покупка, это дубль, сначала разберитесь с той закупкой
      </span>
    </template>
  </div>
</template>

<script setup lang="ts">
import { formatMoney } from '@/utils/formatMoney'

defineProps<{
  linkedPurchases?: { id: number; registry_number: string | null; amount: number }[]
  /** Компактный вид — одна строка «· занято: РЕЕ-... » для FeoPlannedItemRow.vue,
   *  без остатка/предупреждения (там оно уже есть в residualDisplay). */
  short?: boolean
  /** Не хватает N ₽ на новую позицию сверх уже занятого — красный текст вместо
   *  оранжевого. Передаётся только в развёрнутом (не short) виде. */
  shortfall?: number | null
}>()

function fmt(v: number | null | undefined): string {
  return formatMoney(v)
}
</script>

<style scoped>
.feo-taken-by {
  font-size: 12px;
  color: rgb(var(--v-theme-warning));
  margin-top: 2px;
  margin-bottom: 4px;
}
.feo-taken-by--short {
  display: inline;
  margin: 0;
  font-size: inherit;
  color: inherit;
  opacity: 0.85;
}
.feo-taken-by-link {
  color: rgb(var(--v-theme-primary));
  text-decoration: underline;
}
.feo-taken-by-note--error {
  color: rgb(var(--v-theme-error));
  font-weight: 500;
}
.feo-taken-by-note--warning {
  color: rgb(var(--v-theme-warning));
}
</style>
