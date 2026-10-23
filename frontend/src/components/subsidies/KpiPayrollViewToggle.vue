<!-- KpiPayrollViewToggle.vue — переключатель «Всё / Только закупки / Только
     ФОТ» (владелец, план payroll_view, 23.10.2026), общий singleton-pref
     (useKpiPrefs.ts::payrollView) с дашбордом и карточкой субсидии — тот же
     паттерн, что и соседний переключатель «Целиком / Товары и услуги»
     (kpiTypeSplit). Показывается ТОЛЬКО тем, у кого payrollVisible=true (ответ
     /dashboard/charts) — иначе показывать переключатель нечему (нет права
     «Видеть ФОТ» ни по одной субсидии в scope). -->
<template>
  <div
    v-if="kpiPrefs.payrollVisible.value"
    class="d-flex align-center ml-3"
    style="gap:6px"
    title="Показывать все числа карточек, числа без ФОТ, или только ФОТ"
  >
    <span class="text-caption text-medium-emphasis">ФОТ:</span>
    <v-btn-toggle v-model="kpiPrefs.payrollView.value" density="compact" mandatory variant="outlined" color="teal" style="height:26px">
      <v-btn size="x-small" value="all">Всё</v-btn>
      <v-btn size="x-small" value="exclude">Только закупки</v-btn>
      <v-btn size="x-small" value="only">Только ФОТ</v-btn>
    </v-btn-toggle>
    <!-- Задача владельца (23.10.2026, доп.): индикатор «карточки
         пересчитываются», пока не пришёл новый ответ /dashboard/charts —
         общий компонент/флаг (Правило №6, useKpiRecalc.ts), переключатель
         не блокируется. -->
    <KpiRecalcBadge />
  </div>
</template>

<script setup lang="ts">
import { useKpiPrefs } from '@/composables/useKpiPrefs'
import KpiRecalcBadge from '@/components/KpiRecalcBadge.vue'

const kpiPrefs = useKpiPrefs()
</script>
