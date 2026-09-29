<template>
  <!-- Сводка «план · выбрано · остаток · не хватает» одной плановой позиции —
       вынесена из FeoPlannedItemRow.vue (владелец, 30.09.2026: «в подходящих
       не видно, сколько запланировано и сколько выбрано»), чтобы строка
       списка (FeoPlannedItemRow.vue) И карточка кандидата подсказки
       (FeoPlannedMatchSuggestions.vue) показывали РОВНО ОДНУ и ту же разметку
       (Правило №6 — второй копии этого блока не заводим). -->
  <span class="feo-tree-residual">
    план {{ plannedLabel }} ·
    <span
      v-if="row.kind === 'planned_item' && showConsumersLink"
      class="feo-planned-consumed-link"
      role="button"
      tabindex="0"
      title="Кто расходует план — показать построчно"
      @click.stop="emit('open-consumers')"
      @keydown.enter.stop.prevent="emit('open-consumers')"
    >выбрано {{ consumedLabel }}<v-icon size="12" icon="mdi-magnify" class="ml-1" /></span>
    <span v-else>выбрано {{ consumedLabel }}</span> ·
    <span :class="residualDisplay.cssClass">{{ residualDisplay.text }}</span>
    <span v-if="shortfallLabel" class="feo-planned-shortfall-note"> — не хватает {{ shortfallLabel }}</span>
  </span>
</template>

<script setup lang="ts">
import type { FeoPlanPosition } from '@/composables/useFeoPlannedResiduals'
import type { PlanResidualDisplay } from '@/utils/numberFormat'

defineProps<{
  row: Pick<FeoPlanPosition, 'kind'>
  plannedLabel: string
  consumedLabel: string
  residualDisplay: PlanResidualDisplay
  /** Текст «не хватает N» (уже отформатированный, без тире/приставки) — null,
   *  когда остатка достаточно (см. isShort в useFeoPlannedRows.ts/feoPlanRowSummary). */
  shortfallLabel?: string | null
  /** FeoPlannedItemRow.vue показывает «показать построчно» (открывает
   *  FeoPlannedConsumersDialog.vue) — карточка подсказки (FeoPlannedMatchSuggestions.vue)
   *  этот диалог не открывает, там просто «выбрано N» без ссылки. */
  showConsumersLink?: boolean
}>()

const emit = defineEmits<{
  'open-consumers': []
}>()
</script>

<style scoped src="../feoTreeRails.css"></style>
