<template>
  <!-- KPI mini-cards for selected subsidy -->
  <div class="detail-kpis">
    <!-- 1. Бюджет (ФЭО) -->
    <v-tooltip location="bottom" :disabled="true">
      <template #activator="{ props: tip }">
        <div v-bind="tip" class="kpi-card kpi-budget" :class="kpi.kpiCardClass('budget')" title="Живой расчёт по дереву ФЭО: ручное финансирование категорий, без него — факт, иначе план. Совпадает с ИТОГО дерева ниже" @click="kpi.onKpiCardClick('budget')">
          <div class="kpi-icon-box"><v-icon icon="mdi-wallet" size="26" /></div>
          <div class="kpi-body">
            <div class="kpi-value">{{ formatCurrencyRound(kpiSubAnim_budget) }}</div>
            <div class="kpi-label">Бюджет (ФЭО)</div>
          </div>
        </div>
      </template>
    </v-tooltip>
    <!-- 2. Запланировано -->
    <v-tooltip location="bottom" :disabled="true">
      <template #activator="{ props: tip }">
        <div v-bind="tip" class="kpi-card kpi-plan_schedule" :class="kpi.kpiCardClass('plan_schedule')" title="Плановая сумма дерева ФЭО: ручные позиции (импорт/создание в ФЭО) + заявки в плане закупок" @click="kpi.onKpiCardClick('plan_schedule')">
          <div class="kpi-icon-box"><v-icon icon="mdi-calendar-clock" size="26" /></div>
          <div class="kpi-body">
            <div class="kpi-value">{{ formatCurrencyRound(kpiSubAnim_plan_schedule) }}</div>
            <div class="kpi-label">Запланировано</div>
          </div>
        </div>
      </template>
    </v-tooltip>
    <!-- 3. Ведётся работа -->
    <v-tooltip location="bottom" text="включает заказанные, поставленные и оплаченные">
      <template #activator="{ props: tip }">
        <div v-bind="tip" class="kpi-card kpi-work" :class="kpi.kpiCardClass('work')" @click="kpi.onKpiCardClick('work')">
          <div class="kpi-icon-box"><v-icon icon="mdi-progress-wrench" size="26" /></div>
          <div class="kpi-body">
            <div class="kpi-value">{{ formatCurrencyRound(kpiSubAnim_work) }}</div>
            <div class="kpi-label">Ведётся работа</div>
          </div>
        </div>
      </template>
    </v-tooltip>
    <!-- 4. Заказано -->
    <v-tooltip location="bottom" text="включает поставленные и оплаченные">
      <template #activator="{ props: tip }">
        <div v-bind="tip" class="kpi-card kpi-ordered" :class="kpi.kpiCardClass('ordered')" @click="kpi.onKpiCardClick('ordered')">
          <div class="kpi-icon-box"><v-icon icon="mdi-cart-check" size="26" /></div>
          <div class="kpi-body">
            <div class="kpi-value">{{ formatCurrencyRound(kpiSubAnim_ordered) }}</div>
            <div class="kpi-label">Заказано</div>
          </div>
        </div>
      </template>
    </v-tooltip>
    <!-- 5. Заключено договоров -->
    <v-tooltip location="bottom" text="суммарная стоимость заключённых договоров">
      <template #activator="{ props: tip }">
        <div v-bind="tip" class="kpi-card kpi-contracts" :class="kpi.kpiCardClass('contracts')" @click="kpi.onKpiCardClick('contracts')">
          <div class="kpi-icon-box"><v-icon icon="mdi-file-sign" size="26" /></div>
          <div class="kpi-body">
            <div class="kpi-value">{{ formatCurrencyRound(kpiSubAnim_contracts) }}</div>
            <div class="kpi-label">Заключено договоров</div>
          </div>
        </div>
      </template>
    </v-tooltip>
    <!-- 6. Поставлено -->
    <v-tooltip location="bottom" text="включает оплаченные">
      <template #activator="{ props: tip }">
        <div v-bind="tip" class="kpi-card kpi-delivered" :class="kpi.kpiCardClass('delivered')" @click="kpi.onKpiCardClick('delivered')">
          <div class="kpi-icon-box"><v-icon icon="mdi-truck-check" size="26" /></div>
          <div class="kpi-body">
            <div class="kpi-value">{{ formatCurrencyRound(kpiSubAnim_delivered) }}</div>
            <div class="kpi-label">Поставлено</div>
          </div>
        </div>
      </template>
    </v-tooltip>
    <!-- 7. Поставлено, не оплачено -->
    <v-tooltip location="bottom" text="поставлено, но оплата ещё не прошла">
      <template #activator="{ props: tip }">
        <div v-bind="tip" class="kpi-card kpi-delivered_unpaid" :class="kpi.kpiCardClass('delivered_unpaid')" @click="kpi.onKpiCardClick('delivered_unpaid')">
          <div class="kpi-icon-box"><v-icon icon="mdi-truck-alert" size="26" /></div>
          <div class="kpi-body">
            <div class="kpi-value">{{ formatCurrencyRound(kpiSubAnim_delivered_unpaid) }}</div>
            <div class="kpi-label">Поставлено, не оплачено</div>
          </div>
        </div>
      </template>
    </v-tooltip>
    <!-- 8. Оплачено -->
    <v-tooltip location="bottom" :disabled="true">
      <template #activator="{ props: tip }">
        <div v-bind="tip" class="kpi-card kpi-paid" :class="kpi.kpiCardClass('paid')" @click="kpi.onKpiCardClick('paid')">
          <div class="kpi-icon-box"><v-icon icon="mdi-cash-check" size="26" /></div>
          <div class="kpi-body">
            <div class="kpi-value">{{ formatCurrencyRound(kpiSubAnim_paid) }}</div>
            <div class="kpi-label">Оплачено</div>
          </div>
        </div>
      </template>
    </v-tooltip>
    <!-- 9. Свободно -->
    <v-tooltip location="bottom" :disabled="true">
      <template #activator="{ props: tip }">
        <div v-bind="tip" class="kpi-card kpi-free"
          :class="[ctx.selectedBudget.value - ctx.selectedPlannedTotal.value < 0 ? 'kpi-over' : '', kpi.kpiCardClass('free')]"
          @click="kpi.onKpiCardClick('free')"
        >
          <div class="kpi-icon-box"><v-icon icon="mdi-cash-lock-open" size="26" /></div>
          <div class="kpi-body">
            <div class="kpi-value">{{ formatCurrencyRound(Math.abs(kpiSubAnim_free)) }}</div>
            <div class="kpi-label">{{ ctx.selectedBudget.value - ctx.selectedPlannedTotal.value < 0 ? 'Превышение' : 'Свободно' }}</div>
          </div>
        </div>
      </template>
    </v-tooltip>
  </div>
  <!-- Владелец (2026-08-30): предупреждение «сумма заказанного приближается
       к потолку субсидии» — потолок = calculate_budget_from_categories
       (тот же источник, что и жёсткий гейт PLAN_OVER_SUBSIDY_CEILING),
       заказано = разовые/авансовые/рамочные закупки в статусах Заказано+
       И ежемесячные платежи ВЕСЬ график целиком (см. app/services/feo_plan.py). -->
  <v-alert
    v-if="ctx.selectedSubsidy.value?.ceiling_exceeded || ctx.selectedSubsidy.value?.ceiling_near_warning"
    :type="ctx.selectedSubsidy.value?.ceiling_exceeded ? 'error' : 'warning'"
    density="compact"
    variant="tonal"
    class="mb-3"
    icon="mdi-alert-octagon-outline"
  >
    {{ ctx.selectedSubsidy.value?.ceiling_exceeded ? 'Потолок субсидии превышен: ' : 'Приближение к потолку субсидии: ' }}
    заказано {{ formatCurrency(ctx.selectedSubsidy.value?.ceiling_committed_total || 0) }}
    из потолка {{ formatCurrency(ctx.selectedSubsidy.value?.ceiling_total || 0) }}
    — это {{ ctx.selectedSubsidy.value?.ceiling_committed_percent }}%
    (порог предупреждения {{ ctx.selectedSubsidy.value?.ceiling_warn_percent }}%).
  </v-alert>
  <!-- Подсказка активной KPI-метрики -->
  <div v-if="kpi.activeKpi.value" class="feo-kpi-banner">
    <v-icon icon="mdi-filter-variant" size="16" color="#fb923c" />
    <span v-if="!ctx.plannedItemsLoaded.value">загрузка состава…</span>
    <span v-else-if="kpi.kpiHasMatches.value">{{ KPI_LABELS[kpi.activeKpi.value!] }}</span>
    <span v-else>в дереве ФЭО нечего подсвечивать: {{ KPI_EMPTY_REASONS[kpi.activeKpi.value!] }}</span>
    <v-btn size="x-small" variant="text" color="primary" class="ml-auto" @click="kpi.resetKpi">Сбросить</v-btn>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useAnimatedNumber } from '@/composables/useAnimatedNumber'
import { KPI_LABELS, KPI_EMPTY_REASONS } from '@/constants/kpiMetrics'
import { formatCurrency, formatCurrencyRound } from '@/composables/subsidies/format'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { useKpiDrilldown } from '@/composables/subsidies/useKpiDrilldown'

const ctx = useSubsidyDetailCtx()
const kpi = useKpiDrilldown(ctx)

const kpiSubTarget_budget            = computed(() => ctx.selectedBudget.value)
const kpiSubTarget_plan_schedule     = computed(() => ctx.selectedPlannedTotal.value)
const kpiSubTarget_work              = computed(() => ctx.selectedSubsidy.value?.work              ?? 0)
const kpiSubTarget_ordered           = computed(() => ctx.selectedSubsidy.value?.ordered           ?? 0)
const kpiSubTarget_contracts         = computed(() => ctx.selectedSubsidy.value?.contracts         ?? 0)
const kpiSubTarget_delivered         = computed(() => ctx.selectedSubsidy.value?.delivered         ?? 0)
const kpiSubTarget_delivered_unpaid  = computed(() => ctx.selectedSubsidy.value?.delivered_unpaid  ?? 0)
const kpiSubTarget_paid              = computed(() => ctx.selectedSubsidy.value?.paid              ?? 0)
const kpiSubTarget_free              = computed(() => ctx.selectedBudget.value - ctx.selectedPlannedTotal.value)

const kpiSubAnim_budget            = useAnimatedNumber(kpiSubTarget_budget,           800)
const kpiSubAnim_plan_schedule     = useAnimatedNumber(kpiSubTarget_plan_schedule,    800)
const kpiSubAnim_work              = useAnimatedNumber(kpiSubTarget_work,             800)
const kpiSubAnim_ordered           = useAnimatedNumber(kpiSubTarget_ordered,          800)
const kpiSubAnim_contracts         = useAnimatedNumber(kpiSubTarget_contracts,        800)
const kpiSubAnim_delivered         = useAnimatedNumber(kpiSubTarget_delivered,        800)
const kpiSubAnim_delivered_unpaid  = useAnimatedNumber(kpiSubTarget_delivered_unpaid, 800)
const kpiSubAnim_paid              = useAnimatedNumber(kpiSubTarget_paid,             800)
const kpiSubAnim_free              = useAnimatedNumber(kpiSubTarget_free,             800)
</script>
