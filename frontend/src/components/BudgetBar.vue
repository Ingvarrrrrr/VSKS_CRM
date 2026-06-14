<template>
  <div
    v-if="max > 0"
    class="budget-bar"
    :aria-label="`Бюджет: ${subsidy.name}. НМЦД ${fmtRub(subsidy.planned)}, в договоре ${fmtRub(subsidy.contracted)}, оплачено ${fmtRub(subsidy.paid)}, лимит ${fmtRub(subsidy.budget)}`"
  >
    <div class="bb-head">
      <span class="bb-name">{{ subsidy.name }}</span>
      <span class="bb-amounts" :style="{ color: overrun ? '#ef4444' : '#fb923c' }">
        {{ fmtRub(filled) }} / {{ fmtRub(subsidy.budget) }}
      </span>
    </div>

    <div class="bb-bar">
      <div class="bb-seg bb-seg-paid" :style="{ width: pct(segPaid) }" />
      <div class="bb-seg bb-seg-contracted" :style="{ width: pct(segContracted) }" />
      <div
        class="bb-seg"
        :class="overrun ? 'bb-seg-overrun' : 'bb-seg-planned'"
        :style="{ width: pct(segPlanned) }"
      />
      <div v-if="subsidy.budget > 0" class="bb-limit" :style="{ left: limitPos }">
        <span class="bb-limit-label">ЛИМИТ</span>
      </div>
    </div>

    <div class="bb-legend">
      <span class="bb-leg"><i class="bb-dot bb-dot-paid" />Оплачено {{ fmtRub(subsidy.paid) }}</span>
      <span class="bb-leg"><i class="bb-dot bb-dot-contracted" />В договоре {{ fmtRub(subsidy.contracted) }}</span>
      <span class="bb-leg"><i class="bb-dot bb-dot-planned" />Запланировано {{ fmtRub(subsidy.planned) }}</span>
      <span class="bb-leg"><i class="bb-dot bb-dot-free" />Свободно {{ fmtRub(freeAmount) }}</span>
      <v-tooltip v-if="showWarn" location="top">
        <template #activator="{ props: tooltipProps }">
          <v-chip v-bind="tooltipProps" color="warning" size="x-small" class="bb-warn-chip">⚠</v-chip>
        </template>
        <span>Оплачено превышает сумму договоров</span>
      </v-tooltip>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface SubsidyBudgetData {
  id: number | string
  name: string
  budget: number
  planned: number
  contracted: number
  paid: number
}

const props = defineProps<{ subsidy: SubsidyBudgetData }>()

const paid = computed(() => Math.max(props.subsidy.paid || 0, 0))
const contracted = computed(() => Math.max(props.subsidy.contracted || 0, 0))
const planned = computed(() => Math.max(props.subsidy.planned || 0, 0))

const t2 = computed(() => Math.max(contracted.value, paid.value))
const filled = computed(() => Math.max(planned.value, t2.value))

const segPaid = computed(() => paid.value)
const segContracted = computed(() => t2.value - paid.value)
const segPlanned = computed(() => filled.value - t2.value)

const max = computed(() =>
  Math.max(props.subsidy.budget, planned.value, contracted.value, paid.value, 1)
)

const freeAmount = computed(() => Math.max(props.subsidy.budget - filled.value, 0))
const overrun = computed(() => filled.value > props.subsidy.budget && props.subsidy.budget > 0)
const limitPos = computed(() =>
  props.subsidy.budget > 0 ? `${(props.subsidy.budget / max.value) * 100}%` : '0%'
)
const showWarn = computed(() => props.subsidy.paid > props.subsidy.contracted)

function pct(v: number): string {
  return `${(v / max.value) * 100}%`
}

function fmtRub(n: number): string {
  if (n >= 1_000_000) return `${(n / 1e6).toFixed(2)} М ₽`
  if (n >= 1_000) return `${Math.round(n / 1000)} к ₽`
  return `${Math.round(n)} ₽`
}
</script>

<style scoped>
.budget-bar { width: 100%; font-family: var(--font-ui, 'Inter Tight', sans-serif); }
.bb-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px; }
.bb-name { font-size: 13px; font-weight: 600; color: var(--gala-sand-100, #f0ece4); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 60%; }
.bb-amounts { font-family: var(--font-mono, 'JetBrains Mono', monospace); font-size: 12px; font-weight: 600; white-space: nowrap; }

.bb-bar { position: relative; height: 28px; border-radius: 4px; overflow: hidden; background: var(--bb-bg, #1a1714); display: flex; }
.bb-seg { height: 100%; transition: width 0.3s ease; }
.bb-seg-paid { background: #22c55e; }
.bb-seg-contracted { background: #fb923c; }
.bb-seg-planned { background: #fcd34d; }
.bb-seg-overrun { background: repeating-linear-gradient(135deg, #ef4444 0 6px, rgba(239,68,68,0.55) 6px 12px); }

.bb-limit { position: absolute; top: 0; bottom: 0; width: 2px; background: rgba(255,255,255,0.75); }
.bb-limit-label { position: absolute; top: -11px; left: 3px; font-family: var(--font-mono, 'JetBrains Mono', monospace); font-size: 8px; color: rgba(255,255,255,0.6); white-space: nowrap; pointer-events: none; }

.bb-legend { display: flex; gap: 14px; align-items: center; margin-top: 8px; font-family: var(--font-mono, 'JetBrains Mono', monospace); font-size: 10px; color: var(--gala-sand-500, #9a9080); flex-wrap: wrap; }
.bb-leg { display: inline-flex; align-items: center; gap: 5px; }
.bb-dot { width: 9px; height: 9px; border-radius: 2px; display: inline-block; flex-shrink: 0; }
.bb-dot-paid { background: #22c55e; }
.bb-dot-contracted { background: #fb923c; }
.bb-dot-planned { background: #fcd34d; }
.bb-dot-free { background: #4a443c; }
.bb-warn-chip { cursor: default; margin-left: 2px; }

.v-theme--light .bb-bar { --bb-bg: #d8d2c8; }
.v-theme--light .bb-name { color: #2d2922; }
.v-theme--light .bb-legend { color: #4a4339; }
.v-theme--light .bb-dot-free { background: #a8a195; }
.v-theme--light .bb-limit-label { color: rgba(0,0,0,0.55); }
:deep(.v-theme--dark) .bb-bar, .v-theme--dark .bb-bar { --bb-bg: #1a1714; }
.bb-limit-label { color: var(--gala-sand-400, #b5ab98); }
</style>
