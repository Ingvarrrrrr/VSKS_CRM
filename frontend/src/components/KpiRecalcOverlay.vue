<!-- Общий визуальный индикатор «карточки пересчитываются» (владелец,
     23.10.2026, доп. задача к payroll_view) — полупрозрачный слой + полоска
     v-progress-linear сверху блока, числа под слоем приглушены. Один
     компонент на дашборд (KpiCardsWidget.vue) и карточку субсидии
     (SubsidyKpiCards.vue) — Правило №6, не заводить два оверлея с одинаковой
     разметкой. Сам НЕ знает про useKpiRecalc.ts — активность приходит
     пропом, чтобы компонент оставался чистой вёрсткой (переиспользуем и
     тест можно писать на источник флага отдельно). Содержимое — через
     <slot>, карточки внутри во время пересчёта невидимо для кликов
     (pointer-events:none), сам переключатель вне этого слота и остаётся
     активным. -->
<template>
  <div class="kpi-recalc-wrap">
    <v-progress-linear
      v-if="active"
      indeterminate
      color="teal"
      height="3"
      class="kpi-recalc-bar"
    />
    <div class="kpi-recalc-dim" :class="{ 'kpi-recalc-dim-active': active }">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ active: boolean }>()
</script>

<style scoped>
.kpi-recalc-wrap {
  position: relative;
}
.kpi-recalc-bar {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  z-index: 2;
  border-radius: 4px 4px 0 0;
}
.kpi-recalc-dim {
  transition: opacity 0.15s;
}
.kpi-recalc-dim-active {
  opacity: 0.45;
  pointer-events: none;
}
</style>
