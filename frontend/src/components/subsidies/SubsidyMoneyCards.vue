<!-- Квик-план 2026-10-02 («Деньги субсидии», PLAN.md п.5): две новые карточки
     для вкладки «Субсидии» — «Можно перераспределить» и «Экономия по
     закупкам». Вынесены в отдельный компонент (Правило №5 — SubsidyKpiCards.vue
     уже > 500 строк, новые карточки туда не дописываются, только один вызов).
     Поля ВСЕ приходят готовыми с бэкенда (redistributable/redistributable_by_kind/
     planned_not_committed/committed_missing_fact_items/economy_total/
     economy_no_planned_price_items — см. SubsidyRow в composables/subsidies/types.ts) —
     фронт ничего не считает (Правило №6). Рендерится внутри того же
     `.detail-kpis` контейнера родителя, чтобы глобальные стили
     `.subsidies-page .detail-kpis .kpi-card` (styles/subsidies.css) применились
     без копирования CSS (scoped-стили родителя дочерний компонент не достают —
     урок feedback_split_view_css_before_after_screenshots.md). -->
<template>
  <v-tooltip location="bottom" :disabled="true">
    <template #activator="{ props: tip }">
      <div v-bind="tip" class="kpi-card kpi-redistributable" :class="{ 'kpi-over': (redistributable ?? 0) < 0 }"
        title="Бюджет минус законтрактовано: деньги, ещё не связанные договором. Разовый договор занимает деньги с момента заключения, рамочный — только суммой заказов"
      >
        <div class="kpi-icon-box"><v-icon icon="mdi-swap-horizontal" size="26" /></div>
        <div class="kpi-body">
          <div class="kpi-value">{{ redistributable != null ? formatCurrencyRound(redistributable) : '—' }}</div>
          <div class="kpi-label">Можно перераспределить</div>
          <div v-if="redistributable != null" class="kpi-sub-note text-caption text-medium-emphasis">
            не запланировано {{ formatCurrencyRound(free) }} (Свободно) + в плане без договоров {{ formatCurrencyRound(plannedNotCommitted) }}
          </div>
          <div v-if="isSplit" class="kpi-split-rows" @click.stop>
            <template v-if="splitRows.length">
              <div v-for="row in splitRows" :key="row.kind" class="kpi-split-row" :class="{ 'kpi-split-row-neg': row.amount < -0.5 }">
                <span class="kpi-split-dot" :class="'kpi-split-dot-' + row.kind" />
                <span class="kpi-split-text">{{ row.label }} {{ formatCurrencyRound(Math.abs(row.amount)) }}</span>
              </div>
            </template>
            <div v-else class="kpi-split-loading text-caption">нет данных по типам</div>
          </div>
          <div v-if="committedMissingFactItems > 0" class="kpi-sub-note text-caption" style="color:#B45309">
            {{ committedMissingFactItems }} позиций в договоре без суммы договора — учтены по плановой цене
          </div>
        </div>
      </div>
    </template>
  </v-tooltip>

  <v-tooltip location="bottom" :disabled="true">
    <template #activator="{ props: tip }">
      <div v-bind="tip" class="kpi-card kpi-economy" :class="{ 'kpi-over': (economyTotal ?? 0) < 0, 'kpi-unmeasured': economyTotal == null }"
        title="Плановая позиция минус договор по законтрактованным закупкам; минус — согласованная переплата"
      >
        <div class="kpi-icon-box"><v-icon :icon="(economyTotal ?? 0) < 0 ? 'mdi-cash-minus' : 'mdi-cash-plus'" size="26" /></div>
        <div class="kpi-body">
          <div class="kpi-value" :class="economyTotal == null ? '' : (economyTotal < 0 ? 'text-error' : 'text-success')">{{ economyTotal != null ? formatCurrencyRound(Math.abs(economyTotal)) : '—' }}</div>
          <div class="kpi-label">{{ (economyTotal ?? 0) < 0 ? 'Переплата по закупкам' : 'Экономия по закупкам' }}</div>
          <div v-if="economyUnmeasuredText" class="kpi-sub-note text-caption" style="color:#B45309">
            {{ economyUnmeasuredText }}
          </div>
        </div>
      </div>
    </template>
  </v-tooltip>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { formatCurrencyRound } from '@/composables/subsidies/format'
import { KIND_LABELS, type ItemTypeKind } from '@/utils/itemTypeKind'
import { formatEconomyUnmeasuredText } from '@/utils/economyUnmeasured'
import type { SubsidyRow } from '@/composables/subsidies/types'

const props = defineProps<{
  subsidy: SubsidyRow | null
  free: number
  isSplit: boolean
}>()

interface SplitRow { kind: ItemTypeKind; label: string; amount: number }

const redistributable = computed(() => props.subsidy?.redistributable ?? null)
const plannedNotCommitted = computed(() => props.subsidy?.planned_not_committed ?? 0)
const committedMissingFactItems = computed(() => props.subsidy?.committed_missing_fact_items ?? 0)
// null-безопасно (02.10.2026, приёмка): нет данных (поле не пришло или
// бэкенд явно вернул null) — показываем «—», а не 0 ₽ (0 — это РЕАЛЬНОЕ
// отсутствие экономии, другое сообщение владельцу).
const economyTotal = computed<number | null>(() => props.subsidy?.economy_total ?? null)
const economyNoPlannedPriceItems = computed(() => props.subsidy?.economy_no_planned_price_items ?? 0)
const economyUnmeasuredText = computed(() =>
  formatEconomyUnmeasuredText(economyNoPlannedPriceItems.value, props.subsidy?.economy_unmeasured_by_reason)
)

const splitRows = computed<SplitRow[]>(() => {
  const k = props.subsidy?.redistributable_by_kind
  if (!k) return []
  const rows: SplitRow[] = [
    { kind: 'goods', label: KIND_LABELS.goods, amount: k.goods },
    { kind: 'services', label: KIND_LABELS.services, amount: k.services },
  ]
  if (Math.abs(k.unspecified || 0) > 0.5) rows.push({ kind: 'unspecified', label: KIND_LABELS.unspecified, amount: k.unspecified })
  return rows
})
</script>

<style scoped>
.kpi-sub-note {
  margin-top: 4px;
  line-height: 1.3;
}
/* scoped-стиль родителя (SubsidyKpiCards.vue:534) до дочернего компонента не
   доходит (урок feedback_split_view_css_before_after_screenshots.md) —
   повторяем здесь тот же класс/цвет для минусовых строк разбивки по типам. */
.kpi-split-row-neg {
  color: #EF4444;
}
</style>
