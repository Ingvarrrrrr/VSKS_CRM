<template>
  <!-- Раздел C (план ancient-prancing-music.md, 21.09): общий с дашбордом
       переключатель «целиком / товары-услуги» — тот же useKpiPrefs.ts. -->
  <div class="kpi-toggle-row">
    <v-btn-toggle v-model="kpiPrefs.kpiTypeSplit.value" mandatory density="compact" color="primary">
      <v-btn value="total" size="small">Целиком</v-btn>
      <v-btn value="split" size="small">Товары и услуги</v-btn>
    </v-btn-toggle>
  </div>

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
            <div v-if="isSplit" class="kpi-split-rows" @click.stop>
              <template v-if="splitRowsFor('budget')">
                <div v-for="row in splitRowsFor('budget')" :key="row.kind" class="kpi-split-row"
                  :class="{ 'kpi-split-row-clickable': hasStageDrill('budget'), 'kpi-split-row-active': hasStageDrill('budget') && isActiveTypeRow('budget', row.kind), 'kpi-split-row-neg': row.amount < -0.5 }"
                  @click="hasStageDrill('budget') && onTypeRowClick('budget', row.kind)">
                  <span class="kpi-split-dot" :class="'kpi-split-dot-' + row.kind" />
                  <span class="kpi-split-text">{{ row.label }} {{ formatCurrencyRound(Math.abs(row.amount)) }}</span>
                </div>
              </template>
              <div v-else class="kpi-split-loading text-caption">загрузка по типам…</div>
            </div>
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
            <div v-if="isSplit" class="kpi-split-rows" @click.stop>
              <template v-if="splitRowsFor('plan_schedule')">
                <div v-for="row in splitRowsFor('plan_schedule')" :key="row.kind" class="kpi-split-row"
                  :class="{ 'kpi-split-row-clickable': hasStageDrill('plan_schedule'), 'kpi-split-row-active': hasStageDrill('plan_schedule') && isActiveTypeRow('plan_schedule', row.kind), 'kpi-split-row-neg': row.amount < -0.5 }"
                  @click="hasStageDrill('plan_schedule') && onTypeRowClick('plan_schedule', row.kind)">
                  <span class="kpi-split-dot" :class="'kpi-split-dot-' + row.kind" />
                  <span class="kpi-split-text">{{ row.label }} {{ formatCurrencyRound(Math.abs(row.amount)) }}</span>
                </div>
              </template>
              <div v-else class="kpi-split-loading text-caption">загрузка по типам…</div>
            </div>
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
            <div v-if="isSplit" class="kpi-split-rows" @click.stop>
              <template v-if="splitRowsFor('work')">
                <div v-for="row in splitRowsFor('work')" :key="row.kind" class="kpi-split-row"
                  :class="{ 'kpi-split-row-clickable': hasStageDrill('work'), 'kpi-split-row-active': hasStageDrill('work') && isActiveTypeRow('work', row.kind), 'kpi-split-row-neg': row.amount < -0.5 }"
                  @click="hasStageDrill('work') && onTypeRowClick('work', row.kind)">
                  <span class="kpi-split-dot" :class="'kpi-split-dot-' + row.kind" />
                  <span class="kpi-split-text">{{ row.label }} {{ formatCurrencyRound(Math.abs(row.amount)) }}</span>
                </div>
              </template>
              <div v-else class="kpi-split-loading text-caption">загрузка по типам…</div>
            </div>
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
            <div v-if="isSplit" class="kpi-split-rows" @click.stop>
              <template v-if="splitRowsFor('ordered')">
                <div v-for="row in splitRowsFor('ordered')" :key="row.kind" class="kpi-split-row"
                  :class="{ 'kpi-split-row-clickable': hasStageDrill('ordered'), 'kpi-split-row-active': hasStageDrill('ordered') && isActiveTypeRow('ordered', row.kind), 'kpi-split-row-neg': row.amount < -0.5 }"
                  @click="hasStageDrill('ordered') && onTypeRowClick('ordered', row.kind)">
                  <span class="kpi-split-dot" :class="'kpi-split-dot-' + row.kind" />
                  <span class="kpi-split-text">{{ row.label }} {{ formatCurrencyRound(Math.abs(row.amount)) }}</span>
                </div>
              </template>
              <div v-else class="kpi-split-loading text-caption">загрузка по типам…</div>
            </div>
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
            <div v-if="isSplit" class="kpi-split-rows" @click.stop>
              <template v-if="splitRowsFor('contracts')">
                <div v-for="row in splitRowsFor('contracts')" :key="row.kind" class="kpi-split-row"
                  :class="{ 'kpi-split-row-clickable': hasStageDrill('contracts'), 'kpi-split-row-active': hasStageDrill('contracts') && isActiveTypeRow('contracts', row.kind), 'kpi-split-row-neg': row.amount < -0.5 }"
                  @click="hasStageDrill('contracts') && onTypeRowClick('contracts', row.kind)">
                  <span class="kpi-split-dot" :class="'kpi-split-dot-' + row.kind" />
                  <span class="kpi-split-text">{{ row.label }} {{ formatCurrencyRound(Math.abs(row.amount)) }}</span>
                </div>
              </template>
              <div v-else class="kpi-split-loading text-caption">загрузка по типам…</div>
            </div>
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
            <div v-if="isSplit" class="kpi-split-rows" @click.stop>
              <template v-if="splitRowsFor('delivered')">
                <div v-for="row in splitRowsFor('delivered')" :key="row.kind" class="kpi-split-row"
                  :class="{ 'kpi-split-row-clickable': hasStageDrill('delivered'), 'kpi-split-row-active': hasStageDrill('delivered') && isActiveTypeRow('delivered', row.kind), 'kpi-split-row-neg': row.amount < -0.5 }"
                  @click="hasStageDrill('delivered') && onTypeRowClick('delivered', row.kind)">
                  <span class="kpi-split-dot" :class="'kpi-split-dot-' + row.kind" />
                  <span class="kpi-split-text">{{ row.label }} {{ formatCurrencyRound(Math.abs(row.amount)) }}</span>
                </div>
              </template>
              <div v-else class="kpi-split-loading text-caption">загрузка по типам…</div>
            </div>
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
            <div v-if="isSplit" class="kpi-split-rows" @click.stop>
              <template v-if="splitRowsFor('delivered_unpaid')">
                <div v-for="row in splitRowsFor('delivered_unpaid')" :key="row.kind" class="kpi-split-row"
                  :class="{ 'kpi-split-row-clickable': hasStageDrill('delivered_unpaid'), 'kpi-split-row-active': hasStageDrill('delivered_unpaid') && isActiveTypeRow('delivered_unpaid', row.kind), 'kpi-split-row-neg': row.amount < -0.5 }"
                  @click="hasStageDrill('delivered_unpaid') && onTypeRowClick('delivered_unpaid', row.kind)">
                  <span class="kpi-split-dot" :class="'kpi-split-dot-' + row.kind" />
                  <span class="kpi-split-text">{{ row.label }} {{ formatCurrencyRound(Math.abs(row.amount)) }}</span>
                </div>
              </template>
              <div v-else class="kpi-split-loading text-caption">загрузка по типам…</div>
            </div>
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
            <div v-if="isSplit" class="kpi-split-rows" @click.stop>
              <template v-if="splitRowsFor('paid')">
                <div v-for="row in splitRowsFor('paid')" :key="row.kind" class="kpi-split-row"
                  :class="{ 'kpi-split-row-clickable': hasStageDrill('paid'), 'kpi-split-row-active': hasStageDrill('paid') && isActiveTypeRow('paid', row.kind), 'kpi-split-row-neg': row.amount < -0.5 }"
                  @click="hasStageDrill('paid') && onTypeRowClick('paid', row.kind)">
                  <span class="kpi-split-dot" :class="'kpi-split-dot-' + row.kind" />
                  <span class="kpi-split-text">{{ row.label }} {{ formatCurrencyRound(Math.abs(row.amount)) }}</span>
                </div>
              </template>
              <div v-else class="kpi-split-loading text-caption">загрузка по типам…</div>
            </div>
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
            <div v-if="isSplit" class="kpi-split-rows" @click.stop>
              <template v-if="splitRowsFor('free')">
                <div v-for="row in splitRowsFor('free')" :key="row.kind" class="kpi-split-row"
                  :class="{ 'kpi-split-row-clickable': hasStageDrill('free'), 'kpi-split-row-active': hasStageDrill('free') && isActiveTypeRow('free', row.kind), 'kpi-split-row-neg': row.amount < -0.5 }"
                  @click="hasStageDrill('free') && onTypeRowClick('free', row.kind)">
                  <span class="kpi-split-dot" :class="'kpi-split-dot-' + row.kind" />
                  <span class="kpi-split-text">{{ row.label }} {{ formatCurrencyRound(Math.abs(row.amount)) }}</span>
                </div>
              </template>
              <div v-else class="kpi-split-loading text-caption">загрузка по типам…</div>
            </div>
          </div>
        </div>
      </template>
    </v-tooltip>
  </div>

  <!-- Раздел E1 (план ancient-prancing-music.md, 21.09): два новых контроля
       превышения ПО ТИПУ на уровне субсидии целиком (независимые от «план над
       ФЭО»/«ТЗ над плановой позицией») — величины/approval/действия из
       composables/subsidies/useFeoTreeExcess.ts::typeExcessFor(null, kind) и
       компании (тот же источник и та же логика, что и FeoTreeRow.vue на
       уровне категории — node=null здесь означает уровень субсидии, см. её
       докстринг). Правило №6 — не дублировать GET/POST/decide/карту согласований. -->
  <div v-if="isSplit" class="kpi-type-excess-block">
    <template v-for="tk in feoTreeExcess.typeExcessKindDefs" :key="tk.kind">
      <div v-if="feoTreeExcess.typeExcessFor(null, tk.kind)" class="kpi-type-excess-row">
        <template v-if="feoTreeExcess.typeExcessFor(null, tk.kind)!.approval?.status === 'pending'">
          <v-chip size="x-small" color="orange" variant="flat">
            согласование: {{ tk.label }} на {{ formatCurrency(feoTreeExcess.typeExcessFor(null, tk.kind)!.amount) }} · на согласовании у: {{ feoTreeExcess.typeExcessPendingNames(null, tk.kind) || '—' }}
          </v-chip>
          <template v-if="feoTreeExcess.typeExcessMyPendingStep(null, tk.kind) && feoTreeExcess.typeExcessFor(null, tk.kind)!.approval?.can_decide">
            <v-btn size="x-small" variant="tonal" color="success"
              :loading="feoTreeExcess.typeExcessDecideLoading.value === feoTreeExcess.typeExcessKey(null, tk.kind)"
              @click="feoTreeExcess.decideTypeExcess(null, tk.kind, 'approved')"
            >Одобрить</v-btn>
            <v-btn size="x-small" variant="tonal" color="error"
              :loading="feoTreeExcess.typeExcessDecideLoading.value === feoTreeExcess.typeExcessKey(null, tk.kind)"
              @click="feoTreeExcess.decideTypeExcess(null, tk.kind, 'rejected')"
            >Отклонить</v-btn>
          </template>
          <div v-else-if="feoTreeExcess.typeExcessMyPendingStep(null, tk.kind) && !feoTreeExcess.typeExcessFor(null, tk.kind)!.approval?.can_decide" class="text-caption text-medium-emphasis" style="width:100%">
            Решение по превышению принимают только уполномоченные (владелец/финансист). Обратитесь к ним — согласовывать может не любой назначенный.
          </div>
        </template>
        <template v-else-if="feoTreeExcess.typeExcessFor(null, tk.kind)!.approved">
          <v-chip size="x-small" color="grey" variant="flat">
            {{ tk.label }} на {{ formatCurrency(feoTreeExcess.typeExcessFor(null, tk.kind)!.amount) }} · согласовано · {{ feoTreeExcess.typeExcessResolvedByName(null, tk.kind) }}{{ feoTreeExcess.typeExcessResolvedDate(null, tk.kind) ? ' · ' + feoTreeExcess.typeExcessResolvedDate(null, tk.kind) : '' }}
          </v-chip>
        </template>
        <template v-else-if="feoTreeExcess.typeExcessFor(null, tk.kind)!.approval?.status === 'rejected'">
          <v-chip size="x-small" color="red" variant="flat">
            {{ tk.label }} — отклонено{{ feoTreeExcess.typeExcessFor(null, tk.kind)!.approval?.comment ? ': ' + feoTreeExcess.typeExcessFor(null, tk.kind)!.approval!.comment : '' }}
          </v-chip>
          <v-btn size="x-small" variant="tonal" color="red"
            :loading="feoTreeExcess.typeExcessRequestLoading.value === feoTreeExcess.typeExcessKey(null, tk.kind)"
            @click="feoTreeExcess.requestTypeExcessApproval(null, tk.kind)"
          >Согласовать</v-btn>
        </template>
        <template v-else>
          <v-chip size="x-small" color="red" variant="flat">
            {{ tk.label }} на {{ formatCurrency(feoTreeExcess.typeExcessFor(null, tk.kind)!.amount) }} — требуется согласование
          </v-chip>
          <v-btn size="x-small" variant="tonal" color="red"
            :loading="feoTreeExcess.typeExcessRequestLoading.value === feoTreeExcess.typeExcessKey(null, tk.kind)"
            @click="feoTreeExcess.requestTypeExcessApproval(null, tk.kind)"
          >Согласовать</v-btn>
        </template>
      </div>
    </template>
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

  <!-- Раздел C1: та же расшифровка по клику, что и на дашборде — один диалог,
       для карточки субсидии всегда одна субсидия в scope (managed, subsidy_ids
       = [текущая] всегда, не условно — владелец: «карточка субсидии — scope=
       managed&subsidy_ids=<текущая>»). Позиции диалог грузит сам через
       GET /dashboard/type-drill — allPurchases/subsidies здесь больше не нужны
       в режиме typeKind (единственный режим этого экрана). -->
  <StageFeoDrillDialog
    :visible="stageDrillVisible"
    :title="stageDrillTitle"
    :stage-statuses="stageDrillStatuses"
    :all-purchases="[]"
    :subsidy-ids="drillSubsidyIds"
    :subsidies="drillSubsidies"
    :effective-price="purchaseEffectivePrice"
    :status-label-map="STATUS_LABELS"
    :status-color-map="STATUS_COLORS"
    :type-kind="stageDrillTypeKind"
    :stage-key="stageDrillStageKey"
    scope="managed"
    :type-drill-subsidy-ids="drillSubsidyIds"
    @close="stageDrillVisible = false"
    @row-click="(id) => { stageDrillVisible = false; ctx.router.push(`/orders/${id}/edit`) }"
  />
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useAnimatedNumber } from '@/composables/useAnimatedNumber'
import { KPI_LABELS, KPI_EMPTY_REASONS } from '@/constants/kpiMetrics'
import { formatCurrency, formatCurrencyRound } from '@/composables/subsidies/format'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { useKpiDrilldown } from '@/composables/subsidies/useKpiDrilldown'
// useFeoTreeExcess() без аргумента — переиспользует singleton, построенный
// SubsidiesView.vue раньше (см. её докстринг про порядок монтирования):
// typeExcessFor(null, kind)/requestTypeExcessApproval/decideTypeExcess и т.п.
// уже реализуют GET/POST/decide согласования по типу — второй раз этот
// механизм здесь не заводится (Правило №6).
import { useFeoTreeExcess } from '@/composables/subsidies/useFeoTreeExcess'
import { useKpiPrefs } from '@/composables/useKpiPrefs'
import {
  KIND_LABELS, KPI_STAGE_CUMULATIVE_STATUSES, KPI_STAGE_LABELS, hasStageDrill, type ItemTypeKind,
} from '@/utils/itemTypeKind'
import { STATUS_LABELS, STATUS_COLORS } from '@/composables/dashboard/dashboardStatusMaps'
import { purchaseEffectivePrice } from '@/composables/dashboard/dashboardFormat'
import StageFeoDrillDialog from '@/components/StageFeoDrillDialog.vue'
import type { SubsidyTypeTotals } from '@/composables/subsidies/types'

const ctx = useSubsidyDetailCtx()
const kpi = useKpiDrilldown(ctx)
const feoTreeExcess = useFeoTreeExcess()
const kpiPrefs = useKpiPrefs()
const isSplit = computed(() => kpiPrefs.kpiTypeSplit.value === 'split')

interface SplitRow { kind: ItemTypeKind; label: string; amount: number }

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

// ── Раздел C/E1: товары/услуги по карточкам ──────────────────────────────────
// «Бюджет (ФЭО)»/«Запланировано»/«Свободно» — из subsidy_type_totals, который
// GET /feo-categories/plan-tree (compute_subsidy_type_summary) отдаёт ВСЕГДА
// (без флага) вместе с обычным деревом — ctx.planTreeByCat уже содержит его
// под строковым ключом 'subsidy_type_totals' (useFeoTreeState.splitPlanTree
// вычленяет только 'unassigned', остальные ключи проходят как есть; тип
// PlanTreeEntry не объявляет этот строковый ключ, тот же каст использует
// useFeoTreeExcess.ts для subsidy_type_excess — см. её докстринг). Остальные
// 6 карточек (work/ordered/contracts/delivered/delivered_unpaid/paid) — из
// ctx.selectedSubsidy.value.widget[stage] (SubsidiesView.vue догружает
// ?type_split=true в /dashboard/charts?scope=managed при включении
// переключателя — второй запрос здесь не заводится, Правило №6).
type SplitStageKey = 'budget' | 'plan_schedule' | 'work' | 'ordered' | 'contracts' | 'delivered' | 'delivered_unpaid' | 'paid' | 'free'

function subsidyTypeTotals(): SubsidyTypeTotals | null {
  return (ctx.planTreeByCat.value as any)?.subsidy_type_totals ?? null
}

function rawSplitFor(stage: SplitStageKey): { goods: number; services: number; unspecified: number } | null {
  if (stage === 'budget' || stage === 'plan_schedule' || stage === 'free') {
    const totals = subsidyTypeTotals()
    if (!totals) return null
    if (stage === 'budget') {
      return { goods: totals.feo_goods || 0, services: totals.feo_services || 0, unspecified: totals.feo_unspecified || 0 }
    }
    if (stage === 'plan_schedule') {
      return { goods: totals.plan_goods || 0, services: totals.plan_services || 0, unspecified: totals.plan_unspecified || 0 }
    }
    // free = ФЭО по типу − план по типу (тот же смысл, что и общая карточка).
    return {
      goods: (totals.feo_goods || 0) - (totals.plan_goods || 0),
      services: (totals.feo_services || 0) - (totals.plan_services || 0),
      unspecified: (totals.feo_unspecified || 0) - (totals.plan_unspecified || 0),
    }
  }
  const w = (ctx.selectedSubsidy.value?.widget as any)?.[stage]
  if (!w) return null
  const g = w[`${stage}_goods`]
  if (g === undefined) return null
  return { goods: Number(g) || 0, services: Number(w[`${stage}_services`]) || 0, unspecified: Number(w[`${stage}_unspecified`]) || 0 }
}

function splitRowsFor(stage: SplitStageKey): SplitRow[] | null {
  const raw = rawSplitFor(stage)
  if (!raw) return null
  const rows: SplitRow[] = [
    { kind: 'goods', label: KIND_LABELS.goods, amount: raw.goods },
    { kind: 'services', label: KIND_LABELS.services, amount: raw.services },
  ]
  if (Math.abs(raw.unspecified) > 0.5) rows.push({ kind: 'unspecified', label: KIND_LABELS.unspecified, amount: raw.unspecified })
  return rows
}

function isActiveTypeRow(stage: string, kind: ItemTypeKind): boolean {
  const f = kpiPrefs.activeTypeFilter.value
  return !!f && f.stage === stage && f.kind === kind
}

// ── Расшифровка по клику (StageFeoDrillDialog, режим typeKind) ──────────────
// Позиции больше НЕ грузятся этим компонентом (правка после приёмки 21.09) —
// диалог сам зовёт GET /dashboard/type-drill?scope=managed&subsidy_ids=
// <текущая> (тот же расчёт, что и card.split, Правило №6); здесь только
// состояние «что открыть» (заголовок/тип/ключ этапа).
const stageDrillVisible = ref(false)
const stageDrillTitle = ref('')
const stageDrillStatuses = ref<string[]>([])
const stageDrillTypeKind = ref<ItemTypeKind | null>(null)
const stageDrillStageKey = ref<string | null>(null)

const drillSubsidyIds = computed(() => ctx.selectedId.value ? [ctx.selectedId.value] : [])
const drillSubsidies = computed(() => ctx.selectedSubsidy.value ? [ctx.selectedSubsidy.value] : [])

watch(() => ctx.selectedId.value, () => {
  stageDrillVisible.value = false
  stageDrillTypeKind.value = null
  stageDrillStageKey.value = null
})

function onTypeRowClick(stage: SplitStageKey, kind: ItemTypeKind) {
  if (!hasStageDrill(stage)) return  // budget/free — нет списка закупок; шаблон уже не вешает click (см. hasStageDrill выше)
  const active = kpiPrefs.toggleTypeFilter(stage, kind)
  if (!active) {
    stageDrillVisible.value = false
    stageDrillTypeKind.value = null
    stageDrillStageKey.value = null
    return
  }
  const statuses = KPI_STAGE_CUMULATIVE_STATUSES[stage]
  if (!statuses) return
  stageDrillTypeKind.value = kind
  stageDrillStageKey.value = stage
  stageDrillTitle.value = `${KPI_STAGE_LABELS[stage] || stage} · ${KIND_LABELS[kind]}`
  stageDrillStatuses.value = statuses
  stageDrillVisible.value = true
}

</script>

<style scoped>
.kpi-toggle-row {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 8px;
}
.kpi-split-rows {
  margin-top: 4px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.kpi-split-row {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11.5px;
  line-height: 1.3;
  padding: 1px 4px;
  border-radius: 4px;
  cursor: default;
  opacity: 0.85;
  transition: background 0.15s, opacity 0.15s;
}
.kpi-split-row-clickable {
  cursor: pointer;
}
.kpi-split-row-clickable:hover {
  opacity: 1;
  background: rgba(0, 0, 0, 0.05);
}
.kpi-split-row-active {
  opacity: 1;
  background: rgba(251, 146, 60, 0.16);
  outline: 1px solid rgba(251, 146, 60, 0.5);
}
.kpi-split-row-neg {
  color: #EF4444;
}
.kpi-split-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex: none;
}
.kpi-split-dot-goods { background: #3B82F6; }
.kpi-split-dot-services { background: #A855F7; }
.kpi-split-dot-unspecified { background: #94A3B8; }
.kpi-split-loading {
  opacity: 0.6;
}
.kpi-type-excess-block {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 8px 0 12px;
}
.kpi-type-excess-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 2px;
  font-size: 12.5px;
  padding: 4px 8px;
  border-radius: 6px;
  background: rgba(251, 191, 36, 0.1);
}
.kpi-type-excess-text {
  margin-right: 4px;
}
</style>
