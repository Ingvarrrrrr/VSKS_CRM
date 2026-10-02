<template>
  <div v-if="overlay?.active.value && overlay.preview.value" class="rev-totals">
    <v-icon icon="mdi-file-compare" size="16" color="#7c3aed" class="mr-1" />
    <span class="rev-totals-label">Итоги субсидии с учётом корректировки:</span>
    <span v-for="key in totalsKeys" :key="key" class="rev-totals-pair">
      <span class="rev-totals-key">{{ totalsLabels[key] }}</span>
      <span class="rev-totals-before">{{ formatCurrency(beforeTotals[key] || 0) }}</span>
      <v-icon icon="mdi-arrow-right-thin" size="12" />
      <span class="rev-totals-after" :class="valueClass(key)">{{ formatCurrency(afterTotals[key] || 0) }}</span>
      <span v-if="deltaFor(key)" class="rev-totals-delta" :class="deltaClass(key)">{{ deltaFor(key)! > 0 ? '+' : '' }}{{ formatCurrency(deltaFor(key)!) }}</span>
    </span>
    <v-progress-circular v-if="overlay.loading.value" indeterminate size="14" width="2" color="#7c3aed" class="ml-2" />
  </div>
</template>

<script setup lang="ts">
// Шапка «итогов субсидии» парами «было → станет» над деревом ФЭО —
// требование владельца п.1 (волна 3B). Источник чисел — ТОТ ЖЕ preview, что
// и RevisionCellBadge.vue в ячейках дерева (Правило №6), просто срез totals
// вместо totals по одному узлу.
import { computed } from 'vue'
import { formatCurrency } from '@/composables/subsidies/format'
import { useRevisionOverlay } from '@/composables/subsidies/useRevisionOverlay'

const overlay = useRevisionOverlay()

// Приёмка 02.10, п.7: subsidy_money_summary реально отдаёт МНОГО ключей
// (committed_by_kind, planned_not_committed, planned_not_committed_by_kind,
// redistributable_by_kind, committed_missing_fact_items, plan_floor_added —
// см. скриншот приёмки) — totalsKeys брал ВСЕ Object.keys(afterTotals), а не
// только эти пять, поэтому словарь totalsLabels ниже существовал, но не
// применялся как фильтр. Белый список — ТОЛЬКО 5 цифр владельца, в этом
// порядке (budget/planned/committed/free/redistributable), остальные ключи
// (служебные разрезы «...by_kind», «...missing_fact_items» и т.п.) здесь не
// показываются вовсе.
const TOTALS_ORDER = ['budget', 'planned', 'committed', 'free', 'redistributable'] as const
const totalsLabels: Record<string, string> = {
  budget: 'Бюджет',
  planned: 'Запланировано',
  committed: 'Законтрактовано',
  free: 'Свободно',
  redistributable: 'Можно перераспределить',
}

const beforeTotals = computed(() => overlay?.preview.value?.before?.totals || {})
const afterTotals = computed(() => overlay?.preview.value?.after?.totals || {})
const totalsKeys = computed(() => TOTALS_ORDER.filter((k) => k in afterTotals.value || k in beforeTotals.value))

function deltaFor(key: string): number | null {
  const d = Number(afterTotals.value[key] || 0) - Number(beforeTotals.value[key] || 0)
  return Math.abs(d) < 0.005 ? null : d
}
function deltaClass(key: string) {
  const d = deltaFor(key)
  if (d == null) return 'text-medium-emphasis'
  return d > 0 ? 'rev-up' : 'rev-down'
}
// «Свободно» — красным, если отрицательно (приёмка 02.10, п.7), НЕЗАВИСИМО от
// направления дельты (строка могла быть отрицательной и ДО корректировки).
function valueClass(key: string) {
  if (key === 'free' && Number(afterTotals.value[key] ?? beforeTotals.value[key] ?? 0) < 0) return 'rev-down'
  return deltaClass(key)
}
</script>

<style scoped>
.rev-totals {
  display: flex; align-items: center; flex-wrap: wrap; gap: 10px;
  font-size: 12px; background: rgba(124,58,237,0.06); border: 1px solid rgba(124,58,237,0.25);
  border-radius: 8px; padding: 6px 12px; margin-bottom: 10px;
}
.rev-totals-label { font-weight: 600; color: #6d28d9; }
.rev-totals-pair { display: inline-flex; align-items: center; gap: 4px; }
.rev-totals-key { color: var(--crm-text-muted); margin-right: 2px; }
.rev-totals-before { color: var(--crm-text-faint); text-decoration: line-through; }
.rev-totals-delta { font-weight: 700; margin-left: 2px; }
.rev-up { color: #16a34a; font-weight: 700; }
.rev-down { color: #dc2626; font-weight: 700; }
</style>
