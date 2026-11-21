<template>
  <div class="d-flex flex-wrap align-center gap-2 mb-2 px-1 text-caption">
    <span class="text-medium-emphasis">Подсветка строк (нажмите на платёж, чтобы сматчить с 1 или несколькими закупками):</span>
    <span class="registry-legend-badge registry-legend-goods">Зелёный — Товары (сопоставлено)</span>
    <span class="registry-legend-badge registry-legend-services">Песочный — Услуги (сопоставлено)</span>
    <span class="registry-legend-badge registry-legend-unmatched">Белый — Не сопоставлено</span>
  </div>
</template>

<script setup lang="ts">
</script>

<style scoped>
.registry-legend-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 6px;
  font-weight: 600;
}
.registry-legend-goods {
  background-color: #dcfce7;
  color: #14532d;
  border: 1px solid #86efac;
}
.registry-legend-services {
  background-color: #f9ecc9;
  color: #78350f;
  border: 1px solid #fcd34d;
}
.registry-legend-unmatched {
  background-color: #ffffff;
  color: #4b5563;
  border: 1px solid #d1d5db;
}
</style>
