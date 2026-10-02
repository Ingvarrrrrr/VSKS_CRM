<template>
  <span v-if="hasChange" class="rev-cell" :class="{ 'rev-cell--up': delta > 0, 'rev-cell--down': delta < 0 }">
    <span class="rev-cell-before">{{ formatCurrency(before || 0) }}</span>
    <v-icon icon="mdi-arrow-right-thin" size="12" class="rev-cell-arrow" />
    <span class="rev-cell-after">{{ formatCurrency(after || 0) }}</span>
    <span class="rev-cell-delta">{{ delta > 0 ? '+' : '' }}{{ formatCurrency(delta) }}</span>
  </span>
  <span v-else-if="showUnchanged && before != null" class="rev-cell rev-cell--same text-medium-emphasis">
    {{ formatCurrency(before || 0) }}
  </span>
</template>

<script setup lang="ts">
// Пара «Было | Станет» у числовой ячейки дерева ФЭО под корректировкой —
// волна 3B, требование владельца п.1: изменившиеся «станет» выделены цветом
// с разницей, неизменившиеся бледные. Один источник вёрстки такой пары
// (Правило №6) — FeoTreeRow.vue вставляет этот компонент в каждую числовую
// ячейку с overlay вместо собственной разметки «было/стало».
import { computed } from 'vue'
import { formatCurrency } from '@/composables/subsidies/format'

const props = withDefaults(defineProps<{
  before: number | null
  after: number | null
  // Показывать бледное «было» даже когда ничего не изменилось (по умолчанию
  // true — п.1 владельца: пара видна ВСЕГДА, не только у изменённых строк).
  showUnchanged?: boolean
}>(), { showUnchanged: true })

const delta = computed(() => Number(props.after ?? 0) - Number(props.before ?? 0))
const hasChange = computed(() => Math.abs(delta.value) > 0.005)
</script>

<style scoped>
.rev-cell { display: inline-flex; align-items: center; gap: 3px; font-size: 12px; flex-wrap: wrap; justify-content: flex-end; }
.rev-cell-before { color: var(--crm-text-faint); text-decoration: line-through; text-decoration-color: var(--crm-text-faint); }
.rev-cell-arrow { color: var(--crm-text-faint); flex-shrink: 0; }
.rev-cell-after { font-weight: 700; }
.rev-cell--up .rev-cell-after { color: #16a34a; }
.rev-cell--down .rev-cell-after { color: #dc2626; }
.rev-cell-delta {
  font-size: 10px; font-weight: 600; border-radius: 6px; padding: 0 4px;
  margin-left: 2px;
}
.rev-cell--up .rev-cell-delta { color: #16a34a; background: rgba(22,163,74,0.12); }
.rev-cell--down .rev-cell-delta { color: #dc2626; background: rgba(220,38,38,0.12); }
.rev-cell--same { font-size: 12px; }
</style>
