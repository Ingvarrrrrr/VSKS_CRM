<!-- Общая подпись «пересчитываю…» со спиннером — рядом с ЛЮБЫМ переключателем,
     который запускает пересчёт карточек денег (ФОТ: KpiPayrollViewToggle.vue
     и «Целиком/Товары и услуги» в KpiCardsWidget.vue/SubsidyKpiCards.vue).
     Один компонент на все три места (Правило №6 — состояние читает общий
     singleton useKpiRecalc.ts, не копия). Сам переключатель НЕ блокируется —
     это просьба владельца (23.10.2026): просто индикатор рядом, кнопки
     остаются активными. -->
<template>
  <span v-if="recalc.recalculating.value" class="kpi-recalc-badge text-caption text-medium-emphasis">
    <v-progress-circular indeterminate size="14" width="2" color="teal" />
    пересчитываю…
  </span>
</template>

<script setup lang="ts">
import { useKpiRecalc } from '@/composables/useKpiRecalc'

const recalc = useKpiRecalc()
</script>

<style scoped>
.kpi-recalc-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
</style>
