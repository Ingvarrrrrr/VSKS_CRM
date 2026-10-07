<template>
  <div v-for="rn in rows" :key="rn" :data-row-anchor="rn"
    class="figrl-row d-flex align-center ga-2 mb-1"
    :class="{ 'row-jump-flash': highlightedRow === rn, 'figrl-row--skipped': isSkipped(rn) }">
    <span class="text-caption figrl-row-num">Стр. {{ rn }}</span>
    <div class="figrl-row-body text-caption">
      <span class="figrl-row-title">{{ rowLabel(rn) }}</span>
      <v-chip size="x-small" variant="tonal" class="figrl-status-chip">{{ rowStatusLabel(rn) }}</v-chip>
      <template v-if="!isSkipped(rn)">
        <span class="text-medium-emphasis">· договор {{ fmt(rowContract(rn)) }} · оплачено {{ fmt(rowPaid(rn)) }}</span>
      </template>
      <template v-else>
        <span class="text-medium-emphasis">
          · пропущена<template v-if="rowSkipReason(rn)"> — {{ rowSkipReason(rn) }}</template>
        </span>
      </template>
    </div>
    <v-select
      density="compact" variant="outlined" hide-details style="max-width:200px" class="figrl-move"
      :items="otherGroupOptions" label="Перенести в…"
      @update:model-value="v => v && move(rn, v)"
    />
  </div>
</template>

<script setup lang="ts">
// FactImportGroupRowsList — «Строки группы» на карточке шага 4 мастера
// «Импорт факта» (ПРАВИЛО №5: вынесена из FactImportStepGroups.vue, чтобы
// тот не разрастался добавлением деталей по строке). Чек-лист владельца
// 07.10.2026, п.5: раньше здесь был только номер строки — непонятно, что
// внутри карточки. Теперь на строку: «Стр. N · <плановая позиция> · статус
// · договор · оплачено», пропущенные — серым, с причиной (skip_reason.text,
// ОДИН источник с preview.py, ПРАВИЛО №6). Данные строки берутся из
// visibleRows (уже загруженный предпросмотр) — второго запроса не шлём.
import { computed } from 'vue'
import { useFactImport } from '@/composables/subsidies/useFactImport'
import { purchaseStatusLabel } from '@/constants/purchaseStatus'
import { formatMoney } from '@/utils/formatMoney'

const props = defineProps<{
  rows: number[]
  groupKey: string
  highlightedRow: number | null
}>()

const { visibleRows, visibleGroups, moveRowToGroup, queuePreviewRefresh } = useFactImport()

function rowData(rn: number) {
  return visibleRows.value.find(r => r.row === rn) ?? null
}
function rowLabel(rn: number): string {
  const r = rowData(rn)
  return r?.match.planned_item_name || r?.name || '(без имени)'
}
function rowStatusLabel(rn: number): string {
  return purchaseStatusLabel(rowData(rn)?.status) || 'План закупок'
}
function rowContract(rn: number): number | null {
  const r = rowData(rn)
  if (!r) return null
  return r.fact.amount ?? r.contracted ?? null
}
function rowPaid(rn: number): number | null {
  return rowData(rn)?.paid ?? null
}
function isSkipped(rn: number): boolean {
  return !!rowData(rn)?.skip
}
function rowSkipReason(rn: number): string | null {
  return rowData(rn)?.skip_reason?.text ?? null
}
function fmt(v: number | null | undefined): string {
  if (v == null) return '—'
  return formatMoney(v)
}

const otherGroupOptions = computed(() => {
  const items = visibleGroups.value
    .filter(g => g.key !== props.groupKey)
    .map(g => ({ title: g.supplier || g.category_path || g.key, value: g.key }))
  items.push({ title: '— выделить в отдельную закупку —', value: 'new' })
  return items
})

function move(row: number, targetKey: string) {
  moveRowToGroup(row, targetKey)
  queuePreviewRefresh()
}
</script>

<style scoped>
.figrl-row-num { flex-shrink: 0; }
.figrl-row-body {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}
.figrl-row-title {
  white-space: normal;
  overflow-wrap: anywhere;
  min-width: 0;
}
.figrl-status-chip { flex-shrink: 0; }
.figrl-row--skipped { opacity: 0.6; }
.figrl-move { flex-shrink: 0; }
</style>
