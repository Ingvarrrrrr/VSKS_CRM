<!-- Полоса бюджета субсидии/заявки. Два режима (владелец 08.10.2026, план
     binary-crunching-island.md, раздел 2):
     - legacy (без пропа `ordered`) — как было: Оплачено/В договоре/
       Запланировано поверх БЮДЖЕТА. Используется в SummaryTableWidget.vue и
       PurchaseContractParamsSection.vue (их пропы не трогаем).
     - с `ordered` — плитка субсидии (SubsidyCardsGrid.vue передаёт то же
       число, что показано в мини-карточке «Заказано», Правило №6, второй
       расчёт не заводим): Оплачено ⊂ Заказано ⊂ Запланировано + Свободно.
     В обоих режимах ширина штриховки превышения — ТОЛЬКО (заполнено − бюджет),
     не весь последний сегмент (жалоба владельца: штриховка ~1/4 полосы при
     превышении 4 тыс. из 15,9 млн) — рисуется отдельным слоем-оверлеем поверх
     сегментов, начинается точно на отметке ЛИМИТ, минимальная видимая ширина
     3px (чтобы не потерялась при маленьком превышении на большом бюджете). -->
<template>
  <div
    v-if="max > 0"
    class="budget-bar"
    :aria-label="ariaLabel"
  >
    <div class="bb-head">
      <span v-if="!hideName" class="bb-name">{{ subsidy.name }}</span>
      <span class="bb-amounts" :style="{ color: overrun ? '#ef4444' : '#fb923c' }"
        :title="headAmountsTitle"
      >
        {{ fmtRub(filled) }} / {{ fmtRub(subsidy.budget) }}
      </span>
    </div>

    <div class="bb-bar">
      <template v-if="hasOrdered">
        <div class="bb-seg bb-seg-paid" :style="{ width: pct(segPaid) }" :title="segTitle('Оплачено', paid)" />
        <div class="bb-seg bb-seg-ordered" :style="{ width: pct(segOrderedNotPaid) }" :title="segTitle('Заказано, не оплачено', segOrderedNotPaid)" />
        <div class="bb-seg bb-seg-planned" :style="{ width: pct(segPlannedNotOrdered) }" :title="segTitle('Запланировано, не заказано', segPlannedNotOrdered)" />
        <div v-if="freeAmount > 0" class="bb-seg bb-seg-free" :style="{ width: pct(freeAmount) }" :title="segTitle('Свободно', freeAmount)" />
      </template>
      <template v-else>
        <div class="bb-seg bb-seg-paid" :style="{ width: pct(segPaid) }" :title="segTitle('Оплачено', paid)" />
        <div class="bb-seg bb-seg-contracted" :style="{ width: pct(segContracted) }" :title="segTitle('В договоре', segContracted)" />
        <div class="bb-seg bb-seg-planned" :style="{ width: pct(segPlanned) }" :title="segTitle('Запланировано', segPlanned)" />
      </template>

      <!-- Штриховка превышения — отдельный слой, НЕ весь последний сегмент:
           ширина = заполнено − бюджет, минимум 3px, начинается на отметке ЛИМИТ. -->
      <div
        v-if="overrun"
        class="bb-overrun-overlay"
        :style="{ left: limitPos, width: overrunWidth }"
        :title="`Превышение бюджета на ${fmtFull(overrunAmount)}`"
      />

      <div v-if="subsidy.budget > 0" class="bb-limit" :style="{ left: limitPos }">
        <span class="bb-limit-label">ЛИМИТ</span>
      </div>
    </div>

    <div v-if="!hideLegend" class="bb-legend">
      <template v-if="hasOrdered">
        <span class="bb-leg" :class="{ 'bb-leg--zero': paid <= 0 }"><i class="bb-dot bb-dot-paid" />Оплачено {{ fmtRub(subsidy.paid) }}</span>
        <span class="bb-leg" :class="{ 'bb-leg--zero': ordered <= 0 }"><i class="bb-dot bb-dot-ordered" />Заказано {{ fmtRub(subsidy.ordered || 0) }}</span>
        <span class="bb-leg" :class="{ 'bb-leg--zero': planned <= 0 }"><i class="bb-dot bb-dot-planned" />Запланировано {{ fmtRub(subsidy.planned) }}</span>
        <span class="bb-leg"><i class="bb-dot bb-dot-free" />Свободно {{ fmtRub(freeAmount) }}</span>
      </template>
      <template v-else>
        <span class="bb-leg" :class="{ 'bb-leg--zero': paid <= 0 }"><i class="bb-dot bb-dot-paid" />Оплачено {{ fmtRub(subsidy.paid) }}</span>
        <span class="bb-leg" :class="{ 'bb-leg--zero': contracted <= 0 }"><i class="bb-dot bb-dot-contracted" />В договоре {{ fmtRub(subsidy.contracted) }}</span>
        <span class="bb-leg" :class="{ 'bb-leg--zero': planned <= 0 }"><i class="bb-dot bb-dot-planned" />Запланировано {{ fmtRub(subsidy.planned) }}</span>
        <span class="bb-leg"><i class="bb-dot bb-dot-free" />Свободно {{ fmtRub(freeAmount) }}</span>
      </template>
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
  // Необязательное поле — «Заказано» (закупки в статусе contracted/заказано,
  // не включая оплаченные отдельно). Передаётся только там, где источник
  // отдаёт настоящее «Заказано» (SubsidyCardsGrid.vue ← s.ordered), а не
  // total_confirmed. Без него компонент работает как раньше (legacy-режим).
  ordered?: number
}

const props = defineProps<{ subsidy: SubsidyBudgetData; hideLegend?: boolean; hideName?: boolean }>()

const hasOrdered = computed(() => typeof props.subsidy.ordered === 'number')

const paid = computed(() => Math.max(props.subsidy.paid || 0, 0))
const contracted = computed(() => Math.max(props.subsidy.contracted || 0, 0))
const ordered = computed(() => Math.max(props.subsidy.ordered || 0, 0))
const planned = computed(() => Math.max(props.subsidy.planned || 0, 0))

// ── legacy режим (без ordered) — как было, не трогаем шкалу/сегменты ──
const t2 = computed(() => Math.max(contracted.value, paid.value))
const filledLegacy = computed(() => Math.max(planned.value, t2.value))
const segContracted = computed(() => t2.value - paid.value)
const segPlanned = computed(() => filledLegacy.value - t2.value)

// ── режим с ordered — шкала = max(бюджет, план), сегменты накопительно,
// без задвоения: Оплачено ⊂ Заказано ⊂ Запланировано (раздел 2 плана) ──
const tOrd = computed(() => Math.max(ordered.value, paid.value))
const filledOrdered = computed(() => Math.max(planned.value, tOrd.value))
const segOrderedNotPaid = computed(() => tOrd.value - paid.value)
const segPlannedNotOrdered = computed(() => filledOrdered.value - tOrd.value)

const segPaid = computed(() => paid.value)
const filled = computed(() => (hasOrdered.value ? filledOrdered.value : filledLegacy.value))

const max = computed(() =>
  hasOrdered.value
    ? Math.max(props.subsidy.budget, planned.value, 1)
    : Math.max(props.subsidy.budget, planned.value, contracted.value, paid.value, 1)
)

const freeAmount = computed(() => Math.max(props.subsidy.budget - filled.value, 0))
const overrun = computed(() => filled.value > props.subsidy.budget && props.subsidy.budget > 0)
const overrunAmount = computed(() => (overrun.value ? filled.value - props.subsidy.budget : 0))
const limitPos = computed(() =>
  props.subsidy.budget > 0 ? `${(props.subsidy.budget / max.value) * 100}%` : '0%'
)
// Минимум 3px — иначе маленькое превышение на большом бюджете визуально пропадает.
const overrunWidth = computed(() => `max(${pct(overrunAmount.value)}, 3px)`)
const showWarn = computed(() => props.subsidy.paid > props.subsidy.contracted)

const ariaLabel = computed(() => {
  const base = `Бюджет: ${props.subsidy.name}. НМЦД ${fmtRub(props.subsidy.planned)}, `
    + `${hasOrdered.value ? 'заказано ' + fmtRub(props.subsidy.ordered || 0) : 'в договоре ' + fmtRub(props.subsidy.contracted)}, `
    + `оплачено ${fmtRub(props.subsidy.paid)}, лимит ${fmtRub(props.subsidy.budget)}`
  return base
})
const headAmountsTitle = computed(() => {
  const basisLabel = hasOrdered.value
    ? `запланировано ${fmtFull(props.subsidy.planned)}, заказано ${fmtFull(props.subsidy.ordered || 0)}`
    : `запланировано ${fmtFull(props.subsidy.planned)}, в договоре ${fmtFull(props.subsidy.contracted)}`
  return `Занято ${fmtFull(filled.value)} из бюджета ${fmtFull(props.subsidy.budget)} (занято = наибольшее из: ${basisLabel}, оплачено ${fmtFull(props.subsidy.paid)})`
})

function segTitle(label: string, amount: number): string {
  return `${label}: ${fmtFull(amount)}`
}

function pct(v: number): string {
  return `${(v / max.value) * 100}%`
}

function fmtRub(n: number): string {
  if (n >= 1_000_000) return `${(n / 1e6).toFixed(1)} млн ₽`
  if (n >= 1_000) return `${Math.round(n / 1000)} тыс ₽`
  return `${Math.round(n)} ₽`
}

function fmtFull(n: number): string {
  return `${Math.round(n || 0).toLocaleString('ru-RU')} ₽`
}
</script>

<style scoped>
.budget-bar { width: 100%; font-family: var(--font-ui, 'Inter Tight', sans-serif); }
.bb-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px; }
.bb-name { font-size: 13px; font-weight: 600; color: var(--gala-sand-100, #f0ece4); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 60%; }
.bb-amounts { font-family: var(--font-mono, 'JetBrains Mono', monospace); font-size: 12px; font-weight: 600; white-space: nowrap; margin-left: auto; }

.bb-bar { position: relative; height: 28px; border-radius: 4px; overflow: hidden; background: var(--bb-bg, #1a1714); display: flex; }
.bb-seg { height: 100%; transition: width 0.3s ease; }
.bb-seg-paid { background: #22c55e; }
.bb-seg-contracted { background: #fb923c; }
.bb-seg-ordered { background: #3b82f6; }
.bb-seg-planned { background: #fcd34d; }
.bb-seg-free { background: transparent; }

/* Оверлей превышения — абсолютный слой поверх сегментов, не сам сегмент
   (иначе ширина штриховки = весь сегмент «запланировано», старая ошибка). */
.bb-overrun-overlay {
  position: absolute; top: 0; bottom: 0;
  background: repeating-linear-gradient(135deg, #ef4444 0 6px, rgba(239,68,68,0.55) 6px 12px);
  pointer-events: auto;
}

.bb-limit { position: absolute; top: 0; bottom: 0; width: 2px; background: rgba(255,255,255,0.75); }
.bb-limit-label { position: absolute; top: -11px; left: 3px; font-family: var(--font-mono, 'JetBrains Mono', monospace); font-size: 8px; color: rgba(255,255,255,0.6); white-space: nowrap; pointer-events: none; }

.bb-legend { display: flex; gap: 14px; align-items: center; margin-top: 8px; font-family: var(--font-mono, 'JetBrains Mono', monospace); font-size: 10px; color: var(--gala-sand-500, #9a9080); flex-wrap: wrap; }
.bb-leg { display: inline-flex; align-items: center; gap: 5px; }
.bb-leg--zero { opacity: 0.45; }
.bb-dot { width: 9px; height: 9px; border-radius: 2px; display: inline-block; flex-shrink: 0; }
.bb-dot-paid { background: #22c55e; }
.bb-dot-contracted { background: #fb923c; }
.bb-dot-ordered { background: #3b82f6; }
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
