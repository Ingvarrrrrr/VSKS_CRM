<template>
  <!-- Владелец (сессия 2026-09-27, жалоба РЕЕ-2026-00771/РЕЕ-2026-00913): плановая
       позиция может быть УЖЕ целиком занята другой закупкой, а подсказка
       «100% ПРИВЯЗАТЬ»/строка списка молча об этом не говорили — превышение
       вылезало ТОЛЬКО после нажатия «Привязать». Общий компонент (ПРАВИЛО №5/№6) —
       используется и в FeoPlannedMatchSuggestions.vue (под кандидатом подсказки), и
       в FeoPlannedItemRow.vue (в строке списка), чтобы текст/ссылки/форматирование
       денег не разъезжались между двумя местами. -->
  <div
    v-if="(linkedPurchases && linkedPurchases.length) || (linkedWishes && linkedWishes.length)"
    class="feo-taken-by"
    :class="{ 'feo-taken-by--short': short }"
  >
    <template v-if="linkedPurchases && linkedPurchases.length">
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
        <span v-if="p.status_label"> ({{ p.status_label }}<template v-if="p.wish_id">, из заявки №{{ p.wish_id }}</template>)</span>
        <span v-if="!short"> — {{ fmt(p.amount) }}</span><span v-if="idx < linkedPurchases.length - 1">, </span>
      </template>
      <template v-if="!short">
        <span v-if="shortfall != null && shortfall > 0" class="feo-taken-by-note feo-taken-by-note--error">
          — не хватает {{ fmt(shortfall) }}. Если это та же покупка — это дубль, сначала разберитесь с той закупкой
        </span>
        <!-- Владелец (30.09.2026): остатка ХВАТАЕТ на новую позицию (shortfall
             известен и <= 0) — тревожное «это дубль, разберитесь» неуместно,
             спокойная нейтральная подпись вместо него. Не путать с shortfall
             == null (сумма новой позиции ещё неизвестна) — там достаточность
             не проверена, оставляем прежнее предупреждение (ветка else ниже). -->
        <span v-else-if="shortfall != null" class="feo-taken-by-note feo-taken-by-note--ok">
          — остаток хватает
        </span>
        <span v-else class="feo-taken-by-note feo-taken-by-note--warning">
          — если это та же покупка, это дубль, сначала разберитесь с той закупкой
        </span>
      </template>
    </template>
    <!-- Владелец (2026-09-29): «про то, что это дубликат, ничего не написано» —
         НЕзакрытые заявки (draft/submitted/approved), у которых та же плановая
         позиция ещё не стала закупкой — план не резервируют, но заявку стоит
         увидеть ДО согласования этой (см. backend OPEN_WISH_STATUSES). -->
    <template v-if="linkedWishes && linkedWishes.length">
      <span v-if="linkedPurchases && linkedPurchases.length"> · </span>
      <span>{{ short ? 'также в заявке' : 'Также фигурирует в заявке' }}</span>
      <template v-for="(w, idx) in linkedWishes" :key="'w-' + w.id">
        <router-link :to="`/wishes?open=${w.id}`" target="_blank" class="feo-taken-by-link" @click.stop>№{{ w.id }}</router-link>
        <span> ({{ w.status_label || w.status }})</span><span v-if="idx < linkedWishes.length - 1">, </span>
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
import { formatMoney } from '@/utils/formatMoney'

defineProps<{
  linkedPurchases?: { id: number; registry_number: string | null; amount: number; status?: string; status_label?: string; wish_id?: number | null }[]
  /** Владелец (2026-09-29): другие незакрытые заявки на ту же плановую позицию —
   *  см. backend planned_item_consumption.linked_wishes/category_plan_links.linked_wishes. */
  linkedWishes?: { id: number; status: string; status_label?: string; quantity: number | null }[]
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
.feo-taken-by-note--ok {
  color: rgb(var(--v-theme-success));
}
</style>
