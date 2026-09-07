<template>
  <div class="summary-bar">
    <div class="summary-item">
      <span class="summary-label">Субсидий</span>
      <span class="summary-value">{{ filteredSubsidies.length }}</span>
    </div>
    <div class="summary-sep" />
    <div class="summary-item summary-item--link" @click="ctx.router.push('/dashboard')">
      <span class="summary-label">Бюджет ФЭО (итого)</span>
      <span class="summary-value">{{ formatCurrency(totals.budget) }}</span>
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
      <span class="summary-label">Оплачено</span>
      <span class="summary-value" style="color:var(--color-paid)">{{ formatCurrency(totals.paid) }}</span>
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
const { filteredSubsidies, totals } = useSubsidyList(ctx)
</script>
