<template>
  <!-- ── Edit mode banner ── -->
  <div v-if="isEditing" class="edit-mode-banner">
    <v-icon icon="mdi-cursor-move" size="18" class="mr-2" />
    Режим редактирования — перетаскивайте и изменяйте размер виджетов
    <v-btn size="small" variant="tonal" color="white" class="ml-4" @click="$emit('toggle-editing')">Готово</v-btn>
  </div>

  <!-- ── Budget Overflow Alert (outside grid) ── -->
  <div v-if="overrunSubsidies.length > 0" class="budget-overrun-banner">
    <v-icon icon="mdi-alert" size="28" color="white" class="mr-3 flex-shrink-0" />
    <div class="overrun-content">
      <div class="overrun-title">Превышение бюджета субсидий!</div>
      <div v-for="s in overrunSubsidies" :key="s.id" class="overrun-row">
        <strong>{{ s.name }}</strong>:
        бюджет {{ formatCurrency(s.budget) }},
        НМЦД {{ formatCurrency(s.planned) }}
        <span v-if="s.contracted > s.budget">
          · законтрактовано {{ formatCurrency(s.contracted) }}
        </span>
        → <strong>перерасход {{ formatCurrency(Math.max(s.planned, s.contracted) - s.budget) }}</strong>
      </div>
      <div class="overrun-hint">Уменьшите НМЦД закупок или увеличьте размер субсидии</div>
    </div>
  </div>

  <!-- ── Ceiling warning banner (владелец, 2026-08-30) ── -->
  <div v-if="subsidiesNearCeiling.length > 0" class="ceiling-warning-banner"
    :class="{ 'ceiling-warning-banner--critical': subsidiesNearCeiling.some(s => s.ceiling_exceeded) }"
  >
    <v-icon icon="mdi-gauge-full" size="28" color="white" class="mr-3 flex-shrink-0" />
    <div class="overrun-content">
      <div class="overrun-title">Субсидии у потолка финансирования</div>
      <div v-for="s in subsidiesNearCeiling" :key="s.subsidy_id" class="overrun-row">
        <strong>{{ s.name }}</strong>:
        заказано {{ formatCurrency(s.ceiling_committed_total) }} из потолка {{ formatCurrency(s.ceiling_total) }}
        — <strong>{{ s.ceiling_committed_percent }}%</strong>
        (порог {{ s.ceiling_warn_percent }}%)
        <span v-if="s.ceiling_exceeded"> — потолок превышен!</span>
      </div>
      <div class="overrun-hint">
        В сумму заказанного входят разовые/авансовые/рамочные закупки в статусе «Заказано» и далее,
        плюс ежемесячные платежи — весь график целиком.
        <router-link to="/subsidies" class="ceiling-warning-link">Открыть субсидии →</router-link>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  isEditing: boolean
  overrunSubsidies: any[]
  subsidiesNearCeiling: any[]
  formatCurrency: (v: number) => string
}>()

defineEmits<{
  (e: 'toggle-editing'): void
}>()
</script>
