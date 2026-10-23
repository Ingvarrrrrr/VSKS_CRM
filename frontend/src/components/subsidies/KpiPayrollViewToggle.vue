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
    <!-- Индикатор «пересчитываю…» (Правило №6, useKpiRecalc.ts) умышленно НЕ
         рисуется здесь: везде, где стоит этот переключатель (KpiCardsWidget.vue,
         SubsidyKpiCards.vue), рядом уже есть KpiRecalcBadge у соседнего
         переключателя «Целиком / Товары и услуги» — тот же общий
         singleton-флаг, второй экземпляр подряд дублировал надпись
         «пересчитываю…» (правка 23.10.2026, 2-й заход). Свой badge здесь
         к тому же гасило бы payrollVisible — индикатор мигал бы только у
         части пользователей. -->
  </div>
</template>

<script setup lang="ts">
import { useKpiPrefs } from '@/composables/useKpiPrefs'

const kpiPrefs = useKpiPrefs()
</script>
