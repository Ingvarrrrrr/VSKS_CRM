<!-- Квик-план 2026-10-02 («Деньги субсидии», PLAN.md п.4): таблица «Экономия
     по способу закупки» — одна карточка переиспользуется и дашбордом (без
     subsidy_id), и карточкой субсидии (с subsidy_id), см. useEconomyByMethod.ts.
     Все числа приходят готовыми с бэкенда (Правило №6) — здесь только
     отрисовка и форматирование. -->
<template>
  <v-card variant="outlined" class="pa-4">
    <div class="d-flex align-center mb-3">
      <div class="text-subtitle-1 font-weight-bold">Экономия по способу закупки</div>
      <v-progress-circular v-if="loading" indeterminate size="18" width="2" color="primary" class="ml-2" />
    </div>
    <v-table density="compact">
      <thead>
        <tr>
          <th>Способ</th>
          <th class="text-right">Закупок</th>
          <th class="text-right">План</th>
          <th class="text-right">Договор</th>
          <th class="text-right">Экономия ₽</th>
          <th class="text-right">Экономия %</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="row.method + '_' + (row.competitive_form || '')" :class="{ 'economy-row--total': row.is_total }">
          <td class="text-body-2">{{ row.label }}</td>
          <td class="text-right text-body-2">{{ row.purchases }}</td>
          <!-- ИСПРАВЛЕНО 02.10.2026 (приёмка ФАДМ_2026 — «—» вместо 0 ₽, когда
               у группы нет ни одной измеренной закупки; нейтральный цвет, не
               зелёный/красный — см. purchase_economy.py docstring). -->
          <td class="text-right text-body-2">{{ row.plan != null ? formatCurrency(row.plan) : '—' }}</td>
          <td class="text-right text-body-2">{{ row.fact != null ? formatCurrency(row.fact) : '—' }}</td>
          <td class="text-right text-body-2" :class="row.economy == null ? 'text-medium-emphasis' : (row.economy < 0 ? 'text-error' : 'text-success')">
            <template v-if="row.economy == null">—</template>
            <template v-else>
              {{ row.economy < 0 ? '−' : '' }}{{ formatCurrency(Math.abs(row.economy)) }}
              <span v-if="row.economy < 0" class="text-caption">(переплата)</span>
            </template>
          </td>
          <td class="text-right text-body-2" :class="row.economy == null ? 'text-medium-emphasis' : (row.economy < 0 ? 'text-error' : 'text-success')">
            {{ row.economy_pct != null ? `${formatPercent(row.economy_pct)}%` : '—' }}
          </td>
        </tr>
        <tr v-if="!loading && rows.length === 0">
          <td colspan="6" class="text-center text-medium-emphasis text-caption pa-4">Нет данных</td>
        </tr>
      </tbody>
    </v-table>
    <div v-if="unmeasuredText" class="text-caption text-medium-emphasis mt-2">
      {{ unmeasuredText }}
    </div>
  </v-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { EconomyByMethodRow } from '@/composables/dashboard/useEconomyByMethod'
import { formatEconomyUnmeasuredText, type EconomyUnmeasuredByReason } from '@/utils/economyUnmeasured'

// Приёмка 04.10.2026: «Экономия %» отдавала сырое число (1.9223908221607067%)
// — округляем до 1 знака, тот же ru-RU toLocaleString, что formatCurrency
// (frontend/src/composables/subsidies/format.ts) — отдельного форматтера
// процентов в проекте нет (grep не нашёл), поэтому берём ту же конвенцию
// (запятая как разделитель, см. ceiling_committed_percent в SubsidyKpiCards.vue —
// там бэкенд уже округляет сам; здесь округляем на фронте, т.к. бэкенд отдаёт
// сырое деление).
function formatPercent(v: number): string {
  return v.toLocaleString('ru-RU', { maximumFractionDigits: 1 })
}

const props = defineProps<{
  rows: EconomyByMethodRow[]
  loading: boolean
  formatCurrency: (v: number) => string
}>()

const totalNoPlannedPriceItems = computed(() =>
  props.rows.reduce((s, r) => s + (r.no_planned_price_items || 0), 0)
)

// ИСПРАВЛЕНО 02.10.2026: разбивка по причине — складываем по всем строкам
// таблицы (способам закупки), та же семантика, что и экономия/план/факт
// (Σ по группам), только для unmeasured_by_reason.
const unmeasuredByReasonTotal = computed<EconomyUnmeasuredByReason>(() => {
  const acc: EconomyUnmeasuredByReason = { unlinked: 0, no_plan_price: 0, monthly: 0, no_fact: 0 }
  for (const r of props.rows) {
    const by = r.unmeasured_by_reason
    if (!by) continue
    acc.unlinked += by.unlinked || 0
    acc.no_plan_price += by.no_plan_price || 0
    acc.monthly += by.monthly || 0
    acc.no_fact += by.no_fact || 0
  }
  return acc
})

const unmeasuredText = computed(() =>
  formatEconomyUnmeasuredText(totalNoPlannedPriceItems.value, unmeasuredByReasonTotal.value)
)
</script>

<style scoped>
/* Строка-итог «Конкурентная — всего» (только когда у конкурентных закупок
   ≥ 2 разных competitive_form, см. purchase_economy.py) — выделяется жирным,
   чтобы не читалась как ещё один рядовой способ закупки. */
.economy-row--total td { font-weight: 700; }
</style>
