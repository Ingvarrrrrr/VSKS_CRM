<!-- Квик-план 2026-10-02 («Деньги субсидии», PLAN.md п.5), дополнено 06.10.2026
     (sleepy-fluttering-walrus.md, п.1): карточки для вкладки «Субсидии» —
     «Можно перераспределить» (теперь 4 строки: не запланировано / хотелось бы
     можно отказаться / скорее всего понадобится / договоры без заказа (будущие
     месяцы) + красные строки превышения плана по направлениям ФЭО) и
     «Экономия по закупкам». Вынесены в отдельный компонент (Правило №5 —
     SubsidyKpiCards.vue уже > 500 строк, новые карточки туда не дописываются,
     только один вызов). Поля ВСЕ приходят готовыми с бэкенда (redistributable/
     redistributable_by_kind/redistributable_unplanned/not_committed_nice/
     not_committed_likely/contracted_not_ordered/over_plan_categories/
     committed_missing_fact_items/economy_total/economy_no_planned_price_items —
     см. SubsidyRow в composables/subsidies/types.ts) — фронт ничего не считает
     (Правило №6). Рендерится внутри того же `.detail-kpis` контейнера родителя,
     чтобы глобальные стили `.subsidies-page .detail-kpis .kpi-card`
     (styles/subsidies.css) применились без копирования CSS (scoped-стили
     родителя дочерний компонент не достают — урок
     feedback_split_view_css_before_after_screenshots.md). -->
<template>
  <v-tooltip location="bottom" :disabled="true">
    <template #activator="{ props: tip }">
      <div v-bind="tip" class="kpi-card kpi-redistributable" :class="{ 'kpi-over': (redistributable ?? 0) < 0 }"
        title="Бюджет минус законтрактовано: деньги, ещё не связанные договором. Разовый договор занимает деньги с момента заключения, рамочный — только суммой заказов"
      >
        <div class="kpi-icon-box"><v-icon icon="mdi-swap-horizontal" size="26" /></div>
        <!-- Задача (владелец, 06.10.2026, доп.): карточка растягивала ряд (4
             строки расшифровки + товары/услуги + возможная красная строка
             перерасхода). На компьютере — 2 колонки внутри kpi-body (левая:
             сумма+подпись+4 строки, правая: товары/услуги+перерасход+кнопка),
             см. .kpi-redistributable-grid в subsidies.css рядом с .kpi-paid
             (span 2 по сетке карточек). На мобильном сбрасывается в 1 колонку. -->
        <div class="kpi-body kpi-redistributable-grid">
          <div class="kpi-redistributable-col-main">
            <!-- redistributable == null → feo_entered=false на бэке (budget<=0,
                 см. backend/app/services/subsidy_money_summary.py) — решение
                 владельца 07.10.2026, план .planning/quick/2026-10-07-dnr-feo-
                 cards/PLAN.md шаг 1: «ФЭО не введено», не обезличенное «—». -->
            <div class="kpi-value" :class="{ 'text-medium-emphasis': redistributable == null }">{{ redistributable != null ? formatCurrency(redistributable) : 'ФЭО не введено' }}</div>
            <div class="kpi-label">Можно перераспределить</div>
            <!-- Задача 1 (владелец, 04.10.2026 → доп. 06.10.2026, исправлено
                 координатором): раньше одна строка «не запланировано X
                 (Свободно) + в плане без договоров Y» — теперь четыре строки с
                 разбивкой «в плане без договоров» по статусу плановой позиции
                 (not_committed_likely/_nice, см. SubsidyRow в composables/
                 subsidies/types.ts) + «договоры без заказа» (contracted_not_ordered,
                 готовое поле бэкенда — дочерние заказы рамочных договоров в
                 статусе 'contracted', см. app.services.stage_cumulative).
                 «хотелось бы» показываем даже при 0 ₽, чтобы категория была видна. -->
            <div v-if="redistributable != null" class="kpi-sub-note kpi-redistributable-notes text-caption text-medium-emphasis">
              <div class="kpi-redistributable-note-row">не запланировано: {{ formatCurrency(redistributableUnplanned) }}</div>
              <div class="kpi-redistributable-note-row">хотелось бы, можно отказаться: {{ formatCurrency(notCommittedNice) }}</div>
              <div class="kpi-redistributable-note-row">скорее всего понадобится: {{ formatCurrency(notCommittedLikely) }}</div>
              <div class="kpi-redistributable-note-row">договоры без заказа (будущие месяцы): {{ formatCurrency(contractedNotOrdered) }}</div>
            </div>
          </div>
          <div class="kpi-redistributable-col-side">
            <!-- Клик по «Товары»/«Услуги» открывает RedistributableDrillDialog
                 (доп. задача 06.10.2026) — тот же приём, что type-drill строк
                 в SubsidyKpiCards.vue (kpi-split-row-clickable, см. CSS ниже —
                 scoped-стили родителя сюда не доходят, дублируем класс). -->
            <div v-if="isSplit" class="kpi-split-rows" @click.stop>
              <template v-if="splitRows.length">
                <div v-for="row in splitRows" :key="row.kind" class="kpi-split-row"
                  :class="{ 'kpi-split-row-neg': row.amount < -0.5, 'kpi-split-row-clickable': row.kind === 'goods' || row.kind === 'services' }"
                  @click="(row.kind === 'goods' || row.kind === 'services') && openDrill(row.kind)"
                >
                  <span class="kpi-split-dot" :class="'kpi-split-dot-' + row.kind" />
                  <span class="kpi-split-text">{{ row.label }} {{ formatCurrency(Math.abs(row.amount)) }}</span>
                </div>
              </template>
              <div v-else class="kpi-split-loading text-caption">нет данных по типам</div>
            </div>
            <div v-if="committedMissingFactItems > 0" class="kpi-sub-note text-caption" style="color:#B45309">
              {{ committedMissingFactItems }} позиций в договоре без суммы договора — учтены по плановой цене
            </div>
            <!-- Задача (владелец, 06.10.2026): по каждому направлению ФЭО,
                 законтрактованному сверх плана, — отдельная красная строка (без
                 кнопок, только сигнал), готовое поле бэкенда over_plan_categories
                 (см. SubsidyRow в composables/subsidies/types.ts, Правило №6). -->
            <div v-if="overPlanCategories.length" class="kpi-sub-note kpi-over-plan-notes text-caption">
              <div v-for="cat in overPlanCategories" :key="cat.category_id" class="kpi-over-plan-row">
                по «{{ cat.name || 'направлению ФЭО' }}» законтрактовано сверх плана на {{ formatCurrency(cat.excess_amount) }}
              </div>
            </div>
            <!-- «Где взять деньги» (план .planning/quick/2026-10-05-funding-sources/
                 PLAN.md, п.2г) — отрицательное «Можно перераспределить» =
                 превышение бюджета субсидии целиком (нет единой корневой
                 ФЭО-категории, поэтому category_id не передаём — бэкенд
                 трактует запрос без category_id/planned_item_id как уровень
                 субсидии, target.kind='subsidy'). -->
            <v-btn v-if="(redistributable ?? 0) < 0 && props.subsidy?.id" size="x-small" variant="text" color="deep-purple"
              prepend-icon="mdi-cash-sync" class="mt-1" @click.stop="funding.openFundingSources({ subsidyId: props.subsidy!.id, amount: -(redistributable ?? 0) })"
            >Где взять деньги</v-btn>
          </div>
        </div>
      </div>
    </template>
  </v-tooltip>

  <RedistributableDrillDialog
    :visible="drillVisible" :subsidy-id="props.subsidy?.id ?? null" :kind="drillKind"
    @close="drillVisible = false"
  />

  <!-- «Остаток субсидии» (владелец, 06.10.2026) = бюджет ФЭО − оплачено. Пока
       поступление на счёт = бюджету ФЭО (ввода поступлений нет), поэтому это
       же число читается и как «остаток на счёте». Крупно — по отметке
       сотрудников (balance_by_marks), строкой ниже — то же по выписке
       (balance_by_statement). Готовые поля бэкенда (subsidy_money_summary.py,
       ПРАВИЛО №6) — фронт не считает. -->
  <v-tooltip location="bottom" :disabled="true">
    <template #activator="{ props: tip }">
      <div v-bind="tip" class="kpi-card kpi-balance" :class="{ 'kpi-over': (balanceByMarks ?? 0) < 0 }"
        title="Бюджет ФЭО минус оплаченное. Пока поступление на счёт = бюджету ФЭО (ввод поступлений появится позже)"
      >
        <div class="kpi-icon-box"><v-icon icon="mdi-bank-outline" size="26" /></div>
        <div class="kpi-body">
          <div class="kpi-value" :class="balanceByMarks != null && balanceByMarks < 0 ? 'text-error' : ''">
            {{ balanceByMarks != null ? formatCurrency(balanceByMarks) : 'бюджет не введён' }}
          </div>
          <div class="kpi-label">Остаток субсидии</div>
          <!-- Решение владельца 06.10.2026 (budget_from_plan, см. докстринг
               backend subsidy_money_summary.py): бюджета по ФЭО/вручную нет —
               остаток временно считается от плана. -->
          <div v-if="props.subsidy?.budget_from_plan" class="text-caption text-medium-emphasis">по плану — суммы ФЭО не введены</div>
          <div v-if="balanceByMarks != null" class="kpi-sub-note kpi-balance-notes text-caption text-medium-emphasis">
            <div class="kpi-balance-note-row">по отметке: {{ formatCurrency(balanceByMarks) }}</div>
            <div class="kpi-balance-note-row" :class="{ 'text-error': (balanceByStatement ?? 0) < 0 }">
              подтверждено выпиской: {{ balanceByStatement != null ? formatCurrency(balanceByStatement) : '—' }}
            </div>
            <div class="kpi-balance-note-row kpi-balance-hint">бюджет ФЭО − оплачено; пока поступление = бюджету ФЭО</div>
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
          <div class="kpi-value" :class="economyTotal == null ? '' : (economyTotal < 0 ? 'text-error' : 'text-success')">{{ economyTotal != null ? formatCurrency(Math.abs(economyTotal)) : '—' }}</div>
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
import { computed, ref } from 'vue'
import { formatCurrency } from '@/composables/subsidies/format'
import { KIND_LABELS, type ItemTypeKind } from '@/utils/itemTypeKind'
import { formatEconomyUnmeasuredText } from '@/utils/economyUnmeasured'
import type { SubsidyRow } from '@/composables/subsidies/types'
import { useFundingSources } from '@/composables/subsidies/useFundingSources'
import RedistributableDrillDialog from '@/components/subsidies/RedistributableDrillDialog.vue'

const props = defineProps<{
  subsidy: SubsidyRow | null
  isSplit: boolean
}>()

const funding = useFundingSources()

// Расшифровка «Товары»/«Услуги» по клику (доп. задача 06.10.2026) —
// RedistributableDrillDialog сам зовёт GET /dashboard/redistributable-drill
// (Правило №6 — этот компонент ничего не считает, только открывает диалог).
const drillVisible = ref(false)
const drillKind = ref<'goods' | 'services'>('goods')
function openDrill(kind: 'goods' | 'services') {
  drillKind.value = kind
  drillVisible.value = true
}

interface SplitRow { kind: ItemTypeKind; label: string; amount: number }

const redistributable = computed(() => props.subsidy?.redistributable ?? null)
// Задача (владелец, 04.10.2026): «не запланировано» — redistributable_unplanned
// с бэка (free, если бюджет задан, иначе 0.0), а не prop free, который фронт
// раньше считал сам от РАСЧЁТНОЙ оценки бюджета (ctx.selectedBudget) — из-за
// этого три строки карточки не сходились в сумму с «Можно перераспределить»
// у субсидии без введённого бюджета. Одна точка расчёта — Правило №6.
const redistributableUnplanned = computed(() => props.subsidy?.redistributable_unplanned ?? 0)
// Задача 1 (владелец, 04.10.2026): разбивка «в плане без договоров» по
// статусу плановой позиции — готовые поля бэкенда, ничего не считаем.
const notCommittedLikely = computed(() => props.subsidy?.not_committed_likely ?? 0)
const notCommittedNice = computed(() => props.subsidy?.not_committed_nice ?? 0)
const committedMissingFactItems = computed(() => props.subsidy?.committed_missing_fact_items ?? 0)
// Задача (владелец, 06.10.2026) — готовые поля бэкенда, фронт не считает (Правило №6).
const contractedNotOrdered = computed(() => props.subsidy?.contracted_not_ordered ?? 0)
const overPlanCategories = computed(() => props.subsidy?.over_plan_categories ?? [])
// null-безопасно (02.10.2026, приёмка): нет данных (поле не пришло или
// бэкенд явно вернул null) — показываем «—», а не 0 ₽ (0 — это РЕАЛЬНОЕ
// отсутствие экономии, другое сообщение владельцу).
// «Остаток субсидии» — готовые поля бэкенда (dashboard_charts.py: бюджет ФЭО − оплачено).
// Раньше шаблон ссылался на эти имена, но они не были объявлены → всегда «бюджет не введён».
const balanceByMarks = computed<number | null>(() => props.subsidy?.balance_by_marks ?? null)
const balanceByStatement = computed<number | null>(() => props.subsidy?.balance_by_statement ?? null)
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
/* Задача 1 (04.10.2026): три строки вместо одной — каждая переносится
   отдельно на мобильной ширине (~400px), не растягивает карточку в одну
   длинную строку. */
.kpi-redistributable-notes {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.kpi-redistributable-note-row {
  white-space: normal;
  word-break: break-word;
}
/* scoped-стиль родителя (SubsidyKpiCards.vue:534) до дочернего компонента не
   доходит (урок feedback_split_view_css_before_after_screenshots.md) —
   повторяем здесь тот же класс/цвет для минусовых строк разбивки по типам. */
.kpi-split-row-neg {
  color: #EF4444;
}
/* Задача (06.10.2026): красные строки превышения плана по направлениям ФЭО —
   без кнопок, только сигнал (ПРАВИЛО механика/сигнализация — не глушить). */
.kpi-over-plan-notes {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.kpi-over-plan-row {
  color: #EF4444;
  white-space: normal;
  word-break: break-word;
}
/* Задача (06.10.2026, доп.): 2 колонки внутри карточки на компьютере — левая
   сумма+подпись+4 строки, правая товары/услуги+перерасход+кнопка. Высота
   карточки перестаёт расти с ростом числа строк расшифровки (растягивала ряд
   карточек, см. .kpi-redistributable в styles/subsidies.css — span 2 по
   колонкам сетки, тот же приём, что .kpi-paid). На мобильном (≤600px) —
   обратно в одну колонку (правило в styles/subsidies.css). */
.kpi-redistributable-grid {
  display: flex;
  gap: 20px;
  align-items: flex-start;
}
.kpi-redistributable-col-main {
  flex: 1 1 50%;
  min-width: 0;
}
.kpi-redistributable-col-side {
  flex: 1 1 50%;
  min-width: 0;
  border-left: 1px solid rgba(0, 0, 0, 0.08);
  padding-left: 16px;
}
@media (max-width: 600px) {
  .kpi-redistributable-grid {
    flex-direction: column;
    gap: 0;
  }
  .kpi-redistributable-col-side {
    border-left: none;
    padding-left: 0;
    margin-top: 6px;
  }
}
/* scoped-стиль родителя SubsidyKpiCards.vue (.kpi-split-row-clickable, и ВСЯ
   разметка строк товары/услуги — kpi-split-rows/kpi-split-row/kpi-split-dot/
   kpi-split-text/kpi-split-loading) НЕ доходит до дочернего компонента (урок
   feedback_split_view_css_before_after_screenshots.md) — координатор поймал
   это по скриншоту (товары/услуги рисовались крупным шрифтом без кружков,
   т.к. в этом файле были только .kpi-split-row-neg/-clickable, а базовые
   правила размера/кружков — только в SubsidyKpiCards.vue). Повторяем ВСЮ
   группу правил здесь, байт-в-байт как в SubsidyKpiCards.vue (её же классы,
   нужен визуально идентичный результат на соседних карточках). */
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
.kpi-split-row-clickable {
  cursor: pointer;
}
.kpi-split-row-clickable:hover {
  opacity: 1;
  background: rgba(0, 0, 0, 0.05);
}
</style>
