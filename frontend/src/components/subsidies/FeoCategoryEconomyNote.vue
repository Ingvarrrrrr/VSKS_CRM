<template>
  <div v-if="note" class="feo-order-economy-note text-medium-emphasis">
    <a href="#" style="color:inherit;text-decoration:underline dotted" @click.prevent="toggle">
      план из файла {{ formatCurrency(note.planFromFile) }} · экономия по заказам {{ formatCurrency(note.economy) }}
    </a>
    <div v-if="expanded" class="feo-order-economy-breakdown">
      <template v-if="loading">
        <span class="text-caption">загрузка позиций…</span>
      </template>
      <template v-else-if="savedItems.length">
        <div v-for="it in savedItems" :key="it.id" class="text-caption">
          «{{ it.name }}» — план {{ formatCurrency(it.amount ?? 0) }}, заказано
          {{ formatCurrency((it.amount ?? 0) - (it.savings ?? 0)) }}, экономия {{ formatCurrency(it.savings ?? 0) }}
        </div>
      </template>
      <template v-else>
        <span class="text-caption">нет своих позиций с экономией в этой категории (возможно, экономия — у подкатегорий)</span>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
// Правка 12.10.2026 (план lazy-swimming-hollerith.md, п.4б): «план из файла ·
// экономия по заказам» у строки категории дерева ФЭО — владелец жаловался,
// что замещение плана заказом (правило «заказ замещает план», 05.08) меняет
// плановую сумму категории МОЛЧА (847 805,82 вместо 863 979,59 без единого
// слова «почему»). Данные узла — ГОТОВЫЕ plan_manual/plan из
// compute_feo_plan_tree (ctx.feoOrderEconomyNoteFor, useFeoTreeAmounts.ts) —
// вторая формула замещения здесь не считается (ПРАВИЛО №6). Расшифровка по
// позициям (клик) — уже существующие per-item savings/closed из GET
// /feo-planned-items/comparison (ctx.comparisonData, та же замещающая
// формула на уровне ОДНОЙ позиции, ПРАВИЛО №6 — второй запрос/формулу не
// заводим), лениво подгружается кликом через ctx.refreshComparison, как и
// раскрытие Ур.5-панели (FeoLevel5Panel.vue).
import { computed, ref } from 'vue'
import type { FeoNode } from '@/composables/subsidies/types'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { formatCurrency } from '@/composables/subsidies/format'

const props = defineProps<{ node: FeoNode }>()
const ctx = useSubsidyDetailCtx()

const note = computed(() => ctx.feoOrderEconomyNoteFor(props.node))
const expanded = ref(false)
const loading = ref(false)

const savedItems = computed(() => {
  const data = ctx.comparisonData.value[props.node.id]
  if (!data) return []
  return data.planned.filter(p => p.closed && (p.savings ?? 0) > 0.005)
})

async function toggle() {
  expanded.value = !expanded.value
  if (expanded.value && !ctx.comparisonData.value[props.node.id]) {
    loading.value = true
    try {
      await ctx.refreshComparison(props.node.id)
    } finally {
      loading.value = false
    }
  }
}
</script>

<style scoped>
.feo-order-economy-note {
  font-size: 10px;
  line-height: 1.4;
  margin-top: 2px;
}
.feo-order-economy-breakdown {
  margin-top: 2px;
  padding: 4px 6px;
  background: rgba(34, 197, 94, 0.06);
  border: 1px solid rgba(34, 197, 94, 0.25);
  border-radius: 4px;
}
</style>
