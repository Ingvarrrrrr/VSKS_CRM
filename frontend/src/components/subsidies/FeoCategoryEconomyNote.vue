<template>
  <div v-if="note" class="feo-order-economy-note text-medium-emphasis">
    <a href="#" style="color:inherit;text-decoration:underline dotted" @click.prevent="dialogVisible = true">
      план из файла {{ formatCurrency(note.planFromFile) }}
      <template v-if="note.overspend > 0.005"> · перерасход по заказам +{{ formatCurrency(note.overspend) }}</template>
      <template v-if="note.economy > 0.005"> · экономия по заказам {{ formatCurrency(note.economy) }}</template>
    </a>

    <!-- Правка 13.10.2026 (замечание координатора) — клик открывает ТОТ ЖЕ
         компонент окна, что и подпись «Запланировано» (SubsidyKpiCards.vue),
         с фильтром по этой категории (её поддерево) — один компонент окна,
         одна точка данных (app.services.feo_order_diff, ПРАВИЛО №6), а не
         отдельная inline-расшифровка по comparisonData/savings, как раньше. -->
    <OrderSubstitutionDialog
      :visible="dialogVisible"
      :subsidy-id="ctx.selectedId.value"
      :category-id="node.id"
      @close="dialogVisible = false"
      @open-purchase="(id) => { dialogVisible = false; ctx.router.push(`/orders/${id}/edit`) }"
    />
  </div>
</template>

<script setup lang="ts">
// Правка 12.10.2026 (план lazy-swimming-hollerith.md, п.4б): «план из файла ·
// экономия по заказам» у строки категории дерева ФЭО — владелец жаловался,
// что замещение плана заказом (правило «заказ замещает план», 05.08) меняет
// плановую сумму категории МОЛЧА (847 805,82 вместо 863 979,59 без единого
// слова «почему»). Данные узла — ГОТОВЫЕ plan_manual/plan из
// compute_feo_plan_tree (ctx.feoOrderEconomyNoteFor, useFeoTreeAmounts.ts) —
// вторая формула замещения здесь не считается (ПРАВИЛО №6).
//
// Правка 13.10.2026 (замечание координатора) — клик по подписи открывает
// OrderSubstitutionDialog (тот же компонент, что у карточки «Запланировано»,
// SubsidyKpiCards.vue) с category-id=node.id — ОДИН компонент окна для обоих
// входов, расшифровка по позициям ТЕПЕРЬ строится по той же точке, что
// суммирует order_overspend/order_economy узла (app.services.feo_order_diff,
// GET /feo-categories/order-substitution-rows), а не по отдельному
// GET /feo-planned-items/comparison (старая inline-расшифровка убрана —
// её savings-числа были per-item, но НЕ гарантированно совпадали с суммой
// подписи после правки «по позициям, не по категории», см. commit 71742e15).
import { computed, ref } from 'vue'
import type { FeoNode } from '@/composables/subsidies/types'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { formatCurrency } from '@/composables/subsidies/format'
import OrderSubstitutionDialog from '@/components/subsidies/OrderSubstitutionDialog.vue'

const props = defineProps<{ node: FeoNode }>()
const ctx = useSubsidyDetailCtx()

const note = computed(() => ctx.feoOrderEconomyNoteFor(props.node))
const dialogVisible = ref(false)
</script>

<style scoped>
.feo-order-economy-note {
  font-size: 10px;
  line-height: 1.4;
  margin-top: 2px;
}
</style>
