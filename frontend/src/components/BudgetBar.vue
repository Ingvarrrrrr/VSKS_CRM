<template>
  <div
    v-if="max > 0"
    class="budget-bar"
    :aria-label="`Бюджет: ${subsidy.name}. НМЦД ${fmtRub(subsidy.planned)}, в договоре ${fmtRub(subsidy.contracted)}, оплачено ${fmtRub(subsidy.paid)}, лимит ${fmtRub(subsidy.budget)}`"
  >
    <!-- Header row -->
    <div class="bb-head">
      <span class="bb-name">{{ subsidy.name }}</span>
      <span class="bb-amounts" :style="{ color: overrun ? '#ef4444' : '#fb923c' }">
        {{ fmtRub(subsidy.planned) }} / {{ fmtRub(subsidy.budget) }}
      </span>
    </div>

    <!-- Bar -->
    <div class="bb-bar">
      <!-- Layer 1: planned -->
      <div
        class="bb-planned"
        :style="{
          width: scale(subsidy.planned),
          background: overrun
            ? 'repeating-linear-gradient(135deg, rgba(239,68,68,0.25) 0px 5px, rgba(239,68,68,0.08) 5px 10px)'
            : 'rgba(251,146,60,0.15)',
          borderRight: overrun ? '2px solid #ef4444' : '2px solid #fb923c',
        }"
      />

      <!-- Layer 2: contracted -->
      <div
        class="bb-contracted"
        :style="{ width: scale(subsidy.contracted) }"
      />

      <!-- Layer 3: paid -->
      <div
        class="bb-paid"
        :style="{ width: scale(subsidy.paid) }"
      />

      <!-- Layer 4: limit marker -->
      <div
        v-if="subsidy.budget > 0"
        class="bb-limit"
        :style="{ left: limitPos }"
      >
        <span class="bb-limit-label">ЛИМИТ</span>
      </div>
    </div>

    <!-- Legend -->
    <div class="bb-legend">
      <span>▨ НМЦД {{ fmtRub(subsidy.planned) }}</span>
      <span>━ В договоре {{ fmtRub(subsidy.contracted) }}</span>
      <span>▬ Оплачено {{ fmtRub(subsidy.paid) }}</span>
      <v-tooltip v-if="showWarn" location="top">
        <template #activator="{ props: tooltipProps }">
          <v-chip
            v-bind="tooltipProps"
            color="warning"
            size="x-small"
            class="bb-warn-chip"
          >
            ⚠
          </v-chip>
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

const props = defineProps<{
  subsidy: SubsidyBudgetData
}>()

const max = computed(() =>
  Math.max(props.subsidy.budget, props.subsidy.planned, props.subsidy.contracted, 1)
)

function scale(v: number): string {
  return `${Math.min((v / max.value) * 100, 100)}%`
}

const overrun = computed(
  () => props.subsidy.planned > props.subsidy.budget && props.subsidy.budget > 0
)

const limitPos = computed(() =>
  props.subsidy.budget > 0 ? `${(props.subsidy.budget / max.value) * 100}%` : '0%'
)

const showWarn = computed(() => props.subsidy.paid > props.subsidy.contracted)

function fmtRub(n: number): string {
  if (n >= 1_000_000) return `${(n / 1e6).toFixed(2)} М ₽`
  if (n >= 1_000) return `${Math.round(n / 1000)} к ₽`
  return `${Math.round(n)} ₽`
}
</script>

<style scoped>
.budget-bar {
  width: 100%;
  font-family: var(--font-ui, 'Inter Tight', sans-serif);
}

.bb-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 6px;
}

.bb-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--gala-sand-100, #f0ece4);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 65%;
}

.bb-amounts {
  font-family: var(--font-mono, 'JetBrains Mono', monospace);
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}

/* Bar container */
.bb-bar {
  position: relative;
  height: 44px;
  border-radius: 3px;
  overflow: hidden;
  background: var(--bb-bg, #0a0908);
}

/* Layer 1 — planned */
.bb-planned {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  transition: width 0.3s ease;
}

/* Layer 2 — contracted */
.bb-contracted {
  position: absolute;
  top: 6px;
  bottom: 6px;
  left: 0;
  background: rgba(251, 146, 60, 0.65);
  border-radius: 0 2px 2px 0;
  transition: width 0.3s ease;
}

/* Layer 3 — paid */
.bb-paid {
  position: absolute;
  top: 14px;
  bottom: 14px;
  left: 0;
  background: var(--gala-sand-100, #f0ece4);
  border-radius: 0 2px 2px 0;
  transition: width 0.3s ease;
}

/* Layer 4 — limit marker */
.bb-limit {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 1.5px;
  background: rgba(255, 255, 255, 0.45);
}

.bb-limit-label {
  position: absolute;
  top: -12px;
  left: 4px;
  font-family: var(--font-mono, 'JetBrains Mono', monospace);
  font-size: 8px;
  color: rgba(255, 255, 255, 0.5);
  white-space: nowrap;
  pointer-events: none;
}

/* Legend */
.bb-legend {
  display: flex;
  gap: 16px;
  align-items: center;
  margin-top: 8px;
  font-family: var(--font-mono, 'JetBrains Mono', monospace);
  font-size: 10px;
  color: var(--gala-sand-500, #9a9080);
  flex-wrap: wrap;
}

.bb-warn-chip {
  cursor: default;
  margin-left: 2px;
}

/* Light theme support */
:deep(.v-theme--light) .bb-bar,
.v-theme--light .bb-bar {
  --bb-bg: #e8e5e0;
}

:deep(.v-theme--light) .bb-paid,
.v-theme--light .bb-paid {
  background: rgba(20, 18, 16, 0.85);
}

:deep(.v-theme--light) .bb-name {
  color: var(--gala-sand-800, #3d3830);
}

/* Dark theme default */
:deep(.v-theme--dark) .bb-bar,
.v-theme--dark .bb-bar {
  --bb-bg: #0a0908;
}
</style>
