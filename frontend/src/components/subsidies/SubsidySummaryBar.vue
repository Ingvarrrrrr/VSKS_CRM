<template>
  <div class="summary-bar">
    <div class="summary-item">
      <span class="summary-label">Субсидий</span>
      <span class="summary-value">{{ nonSandboxSubsidies.length }}</span>
    </div>
    <div class="summary-sep" />
    <div class="summary-item summary-item--link" @click="ctx.router.push('/dashboard')">
      <span class="summary-label">Бюджет ФЭО (итого)</span>
      <span class="summary-value">{{ formatCurrency(totals.budget) }}</span>
      <!-- Задача 4 (владелец, 07.10.2026, план .planning/quick/2026-10-07-dnr-
           feo-cards/PLAN.md) — та же подпись-приём, что у «Оплачено» выше
           («из них подтверждено выпиской»): budgetMissingCount — готовое поле
           useSubsidyList.ts (ПРАВИЛО №6, второй счётчик здесь не считается). -->
      <span v-if="budgetMissingCount > 0" class="summary-sub">без {{ budgetMissingCount }} {{ subsidiesWord(budgetMissingCount) }} без ФЭО</span>
    </div>
    <div class="summary-sep" />
    <div class="summary-item summary-item--link" @click="ctx.router.push('/orders')">
      <span class="summary-label">Запланировано</span>
      <span class="summary-value" style="color:var(--color-planned)">{{ formatCurrency(totals.planned) }}</span>
    </div>
    <div class="summary-sep" />
    <div class="summary-item summary-item--link" @click="ctx.router.push('/orders?status=work_in_progress')">
      <span class="summary-label">Заказано</span>
      <span class="summary-value" style="color:#3B82F6">{{ formatCurrency(totals.ordered) }}</span>
    </div>
    <div class="summary-sep" />
    <div class="summary-item summary-item--link" @click="ctx.router.push('/orders?status=paid')">
      <span class="summary-label">Оплачено (по отметке)</span>
      <span class="summary-value" style="color:var(--color-paid)">{{ formatCurrency(totals.paid) }}</span>
      <span class="summary-sub">из них подтверждено выпиской: {{ formatCurrency(totals.paid_confirmed) }}</span>
    </div>
    <div class="summary-sep" />
    <div class="summary-item summary-item--link" @click="ctx.router.push('/dashboard')">
      <span class="summary-label">Свободно</span>
      <span class="summary-value" :style="{ color: totals.budget - totals.planned < 0 ? '#EF4444' : '#3B82F6' }">
        {{ formatCurrency(totals.budget - totals.planned) }}
      </span>
    </div>
    <div class="summary-sep" />
    <div class="summary-item summary-item--link" @click="ctx.router.push('/orders?status=work_in_progress')">
      <span class="summary-label">Ведётся работа</span>
      <span class="summary-value" style="color:#6366F1">{{ formatCurrency(totals.work) }}</span>
    </div>
    <div class="summary-sep" />
    <div class="summary-item summary-item--link" @click="ctx.router.push('/contracts')">
      <span class="summary-label">Заключено договоров</span>
      <span class="summary-value" style="color:#0284C7">{{ formatCurrency(totals.contracts) }}</span>
    </div>
    <div class="summary-sep" />
    <div class="summary-item summary-item--link" @click="ctx.router.push('/orders?status=delivered')">
      <span class="summary-label">Поставлено</span>
      <span class="summary-value" style="color:#14B8A6">{{ formatCurrency(totals.delivered) }}</span>
    </div>
    <div class="summary-sep" />
    <div class="summary-item">
      <span class="summary-label">Поставлено не оплачено</span>
      <span class="summary-value" style="color:#EF4444">{{ formatCurrency(totals.delivered_unpaid) }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { formatCurrency } from '@/composables/subsidies/format'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { useSubsidyList } from '@/composables/subsidies/useSubsidyList'

const ctx = useSubsidyDetailCtx()
// useSubsidyList() без ctx — переиспользует singleton SubsidiesView.vue, см.
// докстринг в SubsidyListHeader.vue (владелец, 29.09: переключатель вид не
// работал до F5, т.к. этот вызов с другим ctx пересобирал отдельный API).
// Счётчик «Субсидий» — без копий для экспериментов (is_sandbox), как и
// денежные итоги (totals уже исключает их, ПРАВИЛО №6: один источник —
// nonSandboxSubsidies из useSubsidyList.ts, не второй .filter() здесь).
const { nonSandboxSubsidies, totals, budgetMissingCount } = useSubsidyList()

function subsidiesWord(n: number): string {
  const mod100 = Math.abs(n) % 100
  const mod10 = mod100 % 10
  if (mod100 >= 11 && mod100 <= 14) return 'субсидий'
  if (mod10 === 1) return 'субсидии'
  if (mod10 >= 2 && mod10 <= 4) return 'субсидий'
  return 'субсидий'
}
</script>
