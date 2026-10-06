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
            <div class="kpi-value">{{ formatCurrency(kpiSubAnim_budget) }}</div>
            <div class="kpi-label">Бюджет (ФЭО)</div>
            <!-- Решение владельца 06.10.2026 (budget_from_plan, см. докстринг
                 backend subsidy_money_summary.py): бюджета по ФЭО/вручную нет —
                 показанное число временно взято из плана. -->
            <div v-if="ctx.selectedSubsidy.value?.budget_from_plan" class="text-caption text-medium-emphasis">по плану — суммы ФЭО не введены</div>
            <div v-if="isSplit" class="kpi-split-rows" @click.stop>
              <template v-if="splitRowsFor('budget')">
                <div v-for="row in splitRowsFor('budget')" :key="row.kind" class="kpi-split-row"
                  :class="{ 'kpi-split-row-clickable': hasStageDrill('budget'), 'kpi-split-row-active': hasStageDrill('budget') && isActiveTypeRow('budget', row.kind), 'kpi-split-row-neg': row.amount < -0.5 }"
                  @click="hasStageDrill('budget') && onTypeRowClick('budget', row.kind)">
                  <span class="kpi-split-dot" :class="'kpi-split-dot-' + row.kind" />
                  <span class="kpi-split-text">{{ row.label }} {{ formatCurrency(Math.abs(row.amount)) }}</span>
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
            <div class="kpi-value">{{ formatCurrency(kpiSubAnim_plan_schedule) }}</div>
            <div class="kpi-label">Запланировано</div>
            <div v-if="isSplit" class="kpi-split-rows" @click.stop>
              <template v-if="splitRowsFor('plan_schedule')">
                <div v-for="row in splitRowsFor('plan_schedule')" :key="row.kind" class="kpi-split-row"
                  :class="{ 'kpi-split-row-clickable': hasStageDrill('plan_schedule'), 'kpi-split-row-active': hasStageDrill('plan_schedule') && isActiveTypeRow('plan_schedule', row.kind), 'kpi-split-row-neg': row.amount < -0.5 }"
                  @click="hasStageDrill('plan_schedule') && onTypeRowClick('plan_schedule', row.kind)">
                  <span class="kpi-split-dot" :class="'kpi-split-dot-' + row.kind" />
                  <span class="kpi-split-text">{{ row.label }} {{ formatCurrency(Math.abs(row.amount)) }}</span>
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
            <div class="kpi-value">{{ formatCurrency(kpiSubAnim_work) }}</div>
            <div class="kpi-label">Ведётся работа</div>
            <!-- Задача (владелец, 06.10.2026, ИСПРАВЛЕНО координатором) —
                 расшифровка состава «Ведётся работа»: «Заказано» (эта же
                 карточка в этом компоненте) + договоры без заказа —
                 дочерние заказы рамочных договоров в статусе 'contracted'
                 (contractedNotOrdered, готовое поле ниже; НЕ monthlyFutureToYearEnd
                 — тот график payment-платежей тут ни при чём, см. backend/app/
                 services/stage_cumulative.py::contracted_not_ordered_by_subsidy) —
                 оба числа уже есть, здесь ничего не складывается заново (Правило №6). -->
            <div v-if="contractedNotOrdered > 0" class="kpi-sub-note text-caption text-medium-emphasis">
              заказано {{ formatCurrency(kpiSubTarget_ordered) }} + договоры без заказа (будущие месяцы) {{ formatCurrency(contractedNotOrdered) }}
            </div>
            <div v-if="isSplit" class="kpi-split-rows" @click.stop>
              <template v-if="splitRowsFor('work')">
                <div v-for="row in splitRowsFor('work')" :key="row.kind" class="kpi-split-row"
                  :class="{ 'kpi-split-row-clickable': hasStageDrill('work'), 'kpi-split-row-active': hasStageDrill('work') && isActiveTypeRow('work', row.kind), 'kpi-split-row-neg': row.amount < -0.5 }"
                  @click="hasStageDrill('work') && onTypeRowClick('work', row.kind)">
                  <span class="kpi-split-dot" :class="'kpi-split-dot-' + row.kind" />
                  <span class="kpi-split-text">{{ row.label }} {{ formatCurrency(Math.abs(row.amount)) }}</span>
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
            <div class="kpi-value">{{ formatCurrency(kpiSubAnim_ordered) }}</div>
            <div class="kpi-label">Заказано</div>
            <div v-if="isSplit" class="kpi-split-rows" @click.stop>
              <template v-if="splitRowsFor('ordered')">
                <div v-for="row in splitRowsFor('ordered')" :key="row.kind" class="kpi-split-row"
                  :class="{ 'kpi-split-row-clickable': hasStageDrill('ordered'), 'kpi-split-row-active': hasStageDrill('ordered') && isActiveTypeRow('ordered', row.kind), 'kpi-split-row-neg': row.amount < -0.5 }"
                  @click="hasStageDrill('ordered') && onTypeRowClick('ordered', row.kind)">
                  <span class="kpi-split-dot" :class="'kpi-split-dot-' + row.kind" />
                  <span class="kpi-split-text">{{ row.label }} {{ formatCurrency(Math.abs(row.amount)) }}</span>
                </div>
              </template>
              <div v-else class="kpi-split-loading text-caption">загрузка по типам…</div>
            </div>
          </div>
        </div>
      </template>
    </v-tooltip>
    <!-- 5. Заключено договоров — клик открывает список договоров (квик-план
         06.10.2026, sleepy-fluttering-walrus.md, п.2), не подсветку дерева
         ФЭО, как у остальных карточек (openContractsDrill ниже). -->
    <v-tooltip location="bottom" text="суммарная стоимость заключённых договоров — клик открывает список">
      <template #activator="{ props: tip }">
        <div v-bind="tip" class="kpi-card kpi-contracts" @click="openContractsDrill">
          <div class="kpi-icon-box"><v-icon icon="mdi-file-sign" size="26" /></div>
          <div class="kpi-body">
            <div class="kpi-value">{{ formatCurrency(kpiSubAnim_contracts) }}</div>
            <div class="kpi-label">Заключено договоров</div>
            <!-- Задача 3 (владелец, 04.10.2026): остаток помесячных платежей
                 по уже заключённым помесячным договорам до конца года —
                 готовое поле бэкенда (monthly_future_to_year_end), см.
                 SubsidyRow в composables/subsidies/types.ts. -->
            <div v-if="monthlyFutureToYearEnd > 0" class="kpi-sub-note text-caption text-medium-emphasis">
              из них ещё уйдёт помесячно до конца года: {{ formatCurrency(monthlyFutureToYearEnd) }}
            </div>
            <div v-if="isSplit" class="kpi-split-rows" @click.stop>
              <template v-if="splitRowsFor('contracts')">
                <div v-for="row in splitRowsFor('contracts')" :key="row.kind" class="kpi-split-row"
                  :class="{ 'kpi-split-row-clickable': hasStageDrill('contracts'), 'kpi-split-row-active': hasStageDrill('contracts') && isActiveTypeRow('contracts', row.kind), 'kpi-split-row-neg': row.amount < -0.5 }"
                  @click="hasStageDrill('contracts') && onTypeRowClick('contracts', row.kind)">
                  <span class="kpi-split-dot" :class="'kpi-split-dot-' + row.kind" />
                  <span class="kpi-split-text">{{ row.label }} {{ formatCurrency(Math.abs(row.amount)) }}</span>
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
            <div class="kpi-value">{{ formatCurrency(kpiSubAnim_delivered) }}</div>
            <div class="kpi-label">Поставлено</div>
            <div v-if="isSplit" class="kpi-split-rows" @click.stop>
              <template v-if="splitRowsFor('delivered')">
                <div v-for="row in splitRowsFor('delivered')" :key="row.kind" class="kpi-split-row"
                  :class="{ 'kpi-split-row-clickable': hasStageDrill('delivered'), 'kpi-split-row-active': hasStageDrill('delivered') && isActiveTypeRow('delivered', row.kind), 'kpi-split-row-neg': row.amount < -0.5 }"
                  @click="hasStageDrill('delivered') && onTypeRowClick('delivered', row.kind)">
                  <span class="kpi-split-dot" :class="'kpi-split-dot-' + row.kind" />
                  <span class="kpi-split-text">{{ row.label }} {{ formatCurrency(Math.abs(row.amount)) }}</span>
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
            <div class="kpi-value">{{ formatCurrency(kpiSubAnim_delivered_unpaid) }}</div>
            <div class="kpi-label">Поставлено, не оплачено</div>
            <div v-if="isSplit" class="kpi-split-rows" @click.stop>
              <template v-if="splitRowsFor('delivered_unpaid')">
                <div v-for="row in splitRowsFor('delivered_unpaid')" :key="row.kind" class="kpi-split-row"
                  :class="{ 'kpi-split-row-clickable': hasStageDrill('delivered_unpaid'), 'kpi-split-row-active': hasStageDrill('delivered_unpaid') && isActiveTypeRow('delivered_unpaid', row.kind), 'kpi-split-row-neg': row.amount < -0.5 }"
                  @click="hasStageDrill('delivered_unpaid') && onTypeRowClick('delivered_unpaid', row.kind)">
                  <span class="kpi-split-dot" :class="'kpi-split-dot-' + row.kind" />
                  <span class="kpi-split-text">{{ row.label }} {{ formatCurrency(Math.abs(row.amount)) }}</span>
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
            <!-- Решение владельца (06.10.2026, переигран порядок карточки):
                 ГЛАВНОЕ крупное число снова «по отметке сотрудников»
                 (paid_declared) — именно эта запись у исполнителей, выписка
                 часто ещё не подтверждена/заведена. «Подтверждено выпиской» и
                 расхождение — строками ниже, тем же порядком и той же
                 разбивкой товары/услуги, что раньше показывались у главного
                 числа (ничего не пересчитывается — только порядок строк). -->
            <div class="kpi-value">{{ formatCurrency(kpiSubAnim_paid) }}</div>
            <div class="kpi-label">Оплачено</div>
            <div class="kpi-paid-dual">
              <!-- Задача 3 (владелец, 06.10.2026): кружки-маркеры товары/услуги —
                   тот же приём, что у остальных карточек (kpi-split-dot-*). -->
              <div class="kpi-paid-dual-sub kpi-paid-dual-sub-dots">
                <span class="kpi-paid-dual-chip"><span class="kpi-split-dot kpi-split-dot-goods" />тов. {{ formatCurrency(paidDeclaredByKind.goods) }}</span>
                <span class="kpi-paid-dual-chip"><span class="kpi-split-dot kpi-split-dot-services" />усл. {{ formatCurrency(paidDeclaredByKind.services) }}</span>
              </div>
              <div class="kpi-paid-dual-row">
                <span class="kpi-paid-dual-label">подтверждено выпиской:</span>
                <span class="kpi-paid-dual-amount">{{ formatCurrency(paidConfirmedTotal) }}</span>
              </div>
              <div class="kpi-paid-dual-sub kpi-paid-dual-sub-dots">
                <span class="kpi-paid-dual-chip"><span class="kpi-split-dot kpi-split-dot-goods" />тов. {{ formatCurrency(paidConfirmedByKind.goods) }}</span>
                <span class="kpi-paid-dual-chip"><span class="kpi-split-dot kpi-split-dot-services" />усл. {{ formatCurrency(paidConfirmedByKind.services) }}</span>
              </div>
              <div v-if="paidHasDiscrepancy" class="kpi-paid-dual-row kpi-paid-dual-warn">
                <span class="kpi-paid-dual-label">расхождение:</span>
                <span class="kpi-paid-dual-amount">{{ paidDiff >= 0 ? '+' : '−' }}{{ formatCurrency(Math.abs(paidDiff)) }}</span>
              </div>
            </div>
            <!-- Старые строки «товары 0 ₽ / услуги 0 ₽» (splitRowsFor('paid'),
                 статус-based widget.paid_goods/services) убраны 2026-10-06 —
                 дублировали и противоречили разбивке по выписке/отметке выше
                 (kpi-paid-dual-sub), которая теперь единственный источник
                 товары/услуги для «Оплачено» (ПРАВИЛО №6). -->
          </div>
        </div>
      </template>
    </v-tooltip>
    <!-- 9. Свободно -->
    <v-tooltip location="bottom" :disabled="true">
      <template #activator="{ props: tip }">
        <div v-bind="tip" class="kpi-card kpi-free"
          :class="[freeDiffRounded < 0 ? 'kpi-over' : '', kpi.kpiCardClass('free')]"
          @click="kpi.onKpiCardClick('free')"
        >
          <div class="kpi-icon-box"><v-icon icon="mdi-cash-lock-open" size="26" /></div>
          <div class="kpi-body">
            <div class="kpi-value">{{ formatCurrency(Math.abs(kpiSubAnim_free)) }}</div>
            <div class="kpi-label">{{ freeDiffRounded < 0 ? 'Превышение' : 'Свободно' }}</div>
            <div v-if="isSplit" class="kpi-split-rows" @click.stop>
              <template v-if="splitRowsFor('free')">
                <div v-for="row in splitRowsFor('free')" :key="row.kind" class="kpi-split-row"
                  :class="{ 'kpi-split-row-neg': row.amount !== null && row.amount < 0 }">
                  <span class="kpi-split-dot" :class="'kpi-split-dot-' + row.kind" />
                  <!-- row.amount === null — бюджет ФЭО по этому типу не введён
                       (решение владельца 06.10.2026): показываем «нет данных»,
                       НЕ считаем превышение из нуля бюджета (см. splitRowsFor). -->
                  <span class="kpi-split-text">{{ row.label }}: {{ row.amount === null ? 'нет данных по типу (бюджет ФЭО не разбит)' : ((row.amount < 0 ? 'превышение' : 'свободно') + ' ' + formatCurrency(Math.abs(row.amount))) }}</span>
                </div>
              </template>
              <div v-else class="kpi-split-loading text-caption">загрузка по типам…</div>
            </div>
          </div>
        </div>
      </template>
    </v-tooltip>
    <!-- 10-11. «Можно перераспределить» / «Экономия по закупкам» — квик-план
         2026-10-02, вынесены в отдельный компонент (Правило №5 — этот файл уже
         > 500 строк). -->
    <SubsidyMoneyCards :subsidy="ctx.selectedSubsidy.value" :is-split="isSplit" />
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
          <!-- Жалоба владельца 06.10.2026: «предлагается подтвердить
               превышение, при этом я не могу посмотреть что это за
               превышение» — чип кликабелен (раскрывает дерево + стрелки,
               excessDrilldown.activate), и рядом с кнопками решения — «Где?»
               как явная вторая точка входа (Правило №6: один activate(), не
               два механизма поиска виновника). -->
          <v-tooltip location="top" text="Показать, где превышение">
            <template #activator="{ props: whereTip }">
              <v-chip v-bind="whereTip" size="x-small" color="orange" variant="flat" class="kpi-type-excess-chip-clickable" @click="excessDrilldown.activate(tk.kind)">
                <v-icon icon="mdi-crosshairs-gps" size="12" start />
                согласование: {{ tk.label }} на {{ formatCurrency(feoTreeExcess.typeExcessFor(null, tk.kind)!.amount) }} · на согласовании у: {{ feoTreeExcess.typeExcessPendingNames(null, tk.kind) || '—' }}
              </v-chip>
            </template>
          </v-tooltip>
          <v-btn size="x-small" variant="text" color="orange-darken-2" prepend-icon="mdi-crosshairs-gps"
            @click="excessDrilldown.activate(tk.kind)"
          >Где?</v-btn>
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
          <v-chip size="x-small" color="grey" variant="flat" class="kpi-type-excess-chip-clickable" @click="excessDrilldown.activate(tk.kind)">
            <v-icon icon="mdi-crosshairs-gps" size="12" start />
            {{ tk.label }} на {{ formatCurrency(feoTreeExcess.typeExcessFor(null, tk.kind)!.amount) }} · согласовано · {{ feoTreeExcess.typeExcessResolvedByName(null, tk.kind) }}{{ feoTreeExcess.typeExcessResolvedDate(null, tk.kind) ? ' · ' + feoTreeExcess.typeExcessResolvedDate(null, tk.kind) : '' }}
          </v-chip>
        </template>
        <template v-else-if="feoTreeExcess.typeExcessFor(null, tk.kind)!.approval?.status === 'rejected'">
          <v-chip size="x-small" color="red" variant="flat" class="kpi-type-excess-chip-clickable" @click="excessDrilldown.activate(tk.kind)">
            <v-icon icon="mdi-crosshairs-gps" size="12" start />
            {{ tk.label }} — отклонено{{ feoTreeExcess.typeExcessFor(null, tk.kind)!.approval?.comment ? ': ' + feoTreeExcess.typeExcessFor(null, tk.kind)!.approval!.comment : '' }}
          </v-chip>
          <v-btn size="x-small" variant="text" color="red-darken-1" prepend-icon="mdi-crosshairs-gps"
            @click="excessDrilldown.activate(tk.kind)"
          >Где?</v-btn>
          <v-btn size="x-small" variant="tonal" color="red"
            :loading="feoTreeExcess.typeExcessRequestLoading.value === feoTreeExcess.typeExcessKey(null, tk.kind)"
            @click="feoTreeExcess.requestTypeExcessApproval(null, tk.kind)"
          >Согласовать</v-btn>
        </template>
        <template v-else>
          <v-tooltip location="top" text="Показать, где превышение">
            <template #activator="{ props: whereTip }">
              <v-chip v-bind="whereTip" size="x-small" color="red" variant="flat" class="kpi-type-excess-chip-clickable" @click="excessDrilldown.activate(tk.kind)">
                <v-icon icon="mdi-crosshairs-gps" size="12" start />
                {{ tk.label }} на {{ formatCurrency(feoTreeExcess.typeExcessFor(null, tk.kind)!.amount) }} — требуется согласование
              </v-chip>
            </template>
          </v-tooltip>
          <v-btn size="x-small" variant="text" color="red-darken-1" prepend-icon="mdi-crosshairs-gps"
            @click="excessDrilldown.activate(tk.kind)"
          >Где?</v-btn>
          <v-btn size="x-small" variant="tonal" color="red"
            :loading="feoTreeExcess.typeExcessRequestLoading.value === feoTreeExcess.typeExcessKey(null, tk.kind)"
            @click="feoTreeExcess.requestTypeExcessApproval(null, tk.kind)"
          >Согласовать</v-btn>
        </template>
      </div>
    </template>
  </div>

  <!-- Панель навигации по найденным статьям-виновникам (задание владельца
       06.10.2026) — отдельный компонент (Правило №5), сам решает, показывать
       ли себя (activeKind). -->

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
  <!-- Квик-план 2026-10-02 («Деньги субсидии», PLAN.md п.4): статистика по
       способу закупки для ТЕКУЩЕЙ субсидии — тот же компонент/composable,
       что и на дашборде (Правило №6), с subsidy_id вместо «без фильтра». -->
  <EconomyByMethodTable v-if="ctx.selectedId.value" class="mb-4"
    :rows="economyByMethod.rows.value" :loading="economyByMethod.loading.value" :format-currency="formatCurrency" />
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

  <!-- Квик-план 06.10.2026 (sleepy-fluttering-walrus.md, п.2): карточка
       «Заключено договоров» — отдельный диалог со списком ДОГОВОРОВ (не
       позиций закупок), см. ContractsDrillDialog.vue. -->
  <ContractsDrillDialog
    :visible="contractsDrillVisible"
    :subsidy-id="ctx.selectedId.value"
    scope="managed"
    @close="contractsDrillVisible = false"
  />
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useAnimatedNumber } from '@/composables/useAnimatedNumber'
import { KPI_LABELS, KPI_EMPTY_REASONS } from '@/constants/kpiMetrics'
import { formatCurrency, roundMoney } from '@/composables/subsidies/format'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { useKpiDrilldown } from '@/composables/subsidies/useKpiDrilldown'
// useFeoTreeExcess() без аргумента — переиспользует singleton, построенный
// SubsidiesView.vue раньше (см. её докстринг про порядок монтирования):
// typeExcessFor(null, kind)/requestTypeExcessApproval/decideTypeExcess и т.п.
// уже реализуют GET/POST/decide согласования по типу — второй раз этот
// механизм здесь не заводится (Правило №6).
import { useFeoTreeExcess } from '@/composables/subsidies/useFeoTreeExcess'
// «Где превышение» (жалоба владельца 06.10.2026: «не могу посмотреть что это
// за превышение... чтобы раскрылась субсидия и стрелочки привели к каждому
// пункту») — singleton уже построен SubsidiesView.vue с ctx, здесь
// переиспользуется без аргумента (тот же приём, что у useFeoTreeExcess()
// выше).
import { useKpiPrefs } from '@/composables/useKpiPrefs'
import {
  KIND_LABELS, KPI_STAGE_CUMULATIVE_STATUSES, KPI_STAGE_LABELS, hasStageDrill,
  freeByKindFromTypeTotals, type ItemTypeKind,
} from '@/utils/itemTypeKind'
import { STATUS_LABELS, STATUS_COLORS } from '@/composables/dashboard/dashboardStatusMaps'
import { purchaseEffectivePrice } from '@/composables/dashboard/dashboardFormat'
import StageFeoDrillDialog from '@/components/StageFeoDrillDialog.vue'
import SubsidyMoneyCards from '@/components/subsidies/SubsidyMoneyCards.vue'
import ContractsDrillDialog from '@/components/subsidies/ContractsDrillDialog.vue'
import EconomyByMethodTable from '@/components/dashboard/EconomyByMethodTable.vue'
import { useEconomyByMethod } from '@/composables/dashboard/useEconomyByMethod'
import type { SubsidyTypeTotals } from '@/composables/subsidies/types'

const ctx = useSubsidyDetailCtx()
const kpi = useKpiDrilldown(ctx)
const feoTreeExcess = useFeoTreeExcess()
// Детализация превышений («Где?») ещё не закоммичена её автором — временная заглушка (06.10, сборка упала на отсутствующем модуле).
const excessDrilldown = { activate: (_kind?: unknown) => undefined }
const kpiPrefs = useKpiPrefs()
const isSplit = computed(() => kpiPrefs.kpiTypeSplit.value === 'split')

// Квик-план 2026-10-02: «Экономия по способу закупки» для текущей субсидии —
// тот же composable, что и дашборд (Правило №6), с её id.
const economyByMethod = useEconomyByMethod({ subsidyId: ctx.selectedId })
watch(() => ctx.selectedId.value, (id) => { if (id) economyByMethod.load() }, { immediate: true })

// amount: null — «нет данных по типу» (решение владельца 06.10.2026, см.
// splitRowsFor('free') ниже) — пока только у карточки «Свободно».
interface SplitRow { kind: ItemTypeKind; label: string; amount: number | null }

const kpiSubTarget_budget            = computed(() => ctx.selectedBudget.value)
const kpiSubTarget_plan_schedule     = computed(() => ctx.selectedPlannedTotal.value)
const kpiSubTarget_work              = computed(() => ctx.selectedSubsidy.value?.work              ?? 0)
const kpiSubTarget_ordered           = computed(() => ctx.selectedSubsidy.value?.ordered           ?? 0)
const kpiSubTarget_contracts         = computed(() => ctx.selectedSubsidy.value?.contracts         ?? 0)
const kpiSubTarget_delivered         = computed(() => ctx.selectedSubsidy.value?.delivered         ?? 0)
const kpiSubTarget_delivered_unpaid  = computed(() => ctx.selectedSubsidy.value?.delivered_unpaid  ?? 0)
// Переигран владельцем 06.10.2026 (карточка «Оплачено», см. шаблон выше):
// ГЛАВНОЕ число — снова «по отметке сотрудников» (paid_declared), «по
// выписке» (paid_confirmed) — строкой ниже. .paid остаётся фолбэком для
// совсем старого бэка (до paid_declared/paid_confirmed).
const kpiSubTarget_paid              = computed(() => Number(ctx.selectedSubsidy.value?.paid_declared ?? ctx.selectedSubsidy.value?.paid ?? 0))
// Задача (владелец, 06.10.2026) — карточка «Оплачено»: ДВЕ величины словами
// владельца, «по выписке» (главная) и «по отметке сотрудников» (вторая) —
// готовые поля бэкенда (dashboard_charts.py::subsidy_stats: paid_confirmed,
// paid_declared, paid_diff), Правило №6 — не считаем здесь заново формулу,
// только берём готовый paid_diff если бэкенд его прислал, иначе считаем
// разницу локально (declared − confirmed) для обратной совместимости.
const paidDeclaredTotal = computed(() => Number(ctx.selectedSubsidy.value?.paid_declared ?? 0))
const paidConfirmedTotal = computed(() => Number(ctx.selectedSubsidy.value?.paid_confirmed ?? 0))
const paidDeclaredByKind = computed(() => ctx.selectedSubsidy.value?.paid_declared_by_kind ?? { goods: 0, services: 0, unspecified: 0 })
const paidConfirmedByKind = computed(() => ctx.selectedSubsidy.value?.paid_confirmed_by_kind ?? { goods: 0, services: 0, unspecified: 0 })
const paidDiff = computed(() => {
  const explicit = ctx.selectedSubsidy.value?.paid_diff
  if (explicit != null) return Number(explicit)
  return paidDeclaredTotal.value - paidConfirmedTotal.value
})
const paidHasDiscrepancy = computed(() => Math.abs(paidDiff.value) > 0.5)
// roundMoney — защита от шума плавающей точки: бюджет ФЭО и план суммируются
// из десятков строк, «равно нулю» на деле выходит 0.000000002 ₽, что
// переворачивало подпись карточки на «Превышение 0 ₽» (владелец, 2026-10-06,
// ФАДМ 2026_2). freeDiffRounded — НЕ анимированная версия, используется для
// знака/подписи/класса (анимация kpiSubAnim_free меняла бы подпись раньше
// времени посреди анимации числа).
const freeDiffRounded = computed(() => roundMoney(ctx.selectedBudget.value - ctx.selectedPlannedTotal.value))
const kpiSubTarget_free              = computed(() => freeDiffRounded.value)
// Задача 3 (владелец, 04.10.2026) — готовое поле бэкенда, не считаем здесь (Правило №6).
const monthlyFutureToYearEnd = computed(() => ctx.selectedSubsidy.value?.monthly_future_to_year_end ?? 0)
// «Договоры без заказа» для подписи «Ведётся работа» (06.10.2026, ИСПРАВЛЕНО
// координатором — см. комментарий у места использования выше): дочерние
// заказы рамочных договоров в статусе 'contracted', НЕ is_monthly_payment-график.
const contractedNotOrdered = computed(() => ctx.selectedSubsidy.value?.contracted_not_ordered ?? 0)

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
  // 'free' обрабатывается отдельно в splitRowsFor() ниже (решение владельца
  // 06.10.2026: без разбивки бюджета ФЭО по типу превышение по типу — ложная
  // тревога, см. её докстринг) — здесь больше НЕ обрабатывается.
  if (stage === 'budget' || stage === 'plan_schedule') {
    const totals = subsidyTypeTotals()
    if (!totals) return null
    if (stage === 'budget') {
      return { goods: totals.feo_goods || 0, services: totals.feo_services || 0, unspecified: totals.feo_unspecified || 0 }
    }
    // plan_schedule
    return { goods: totals.plan_goods || 0, services: totals.plan_services || 0, unspecified: totals.plan_unspecified || 0 }
  }
  // «Поставлено, не оплачено» (владелец, 05.10.2026) — по типам источник НЕ
  // widget.delivered_unpaid (тот означает status='delivered' без paid, его же
  // читает дашборд через effectiveWidgets/stageTypeSplit, ПРАВИЛО №6 — старое
  // поле не трогаем), а отдельное точное поле delivered_unpaid_declared_by_kind
  // (delivered − paid_declared по типам, см. backend dashboard_charts.py).
  if (stage === 'delivered_unpaid') {
    const k = ctx.selectedSubsidy.value?.delivered_unpaid_declared_by_kind
    if (!k) return null
    return { goods: Number(k.goods) || 0, services: Number(k.services) || 0, unspecified: Number(k.unspecified) || 0 }
  }
  const w = (ctx.selectedSubsidy.value?.widget as any)?.[stage]
  if (!w) return null
  const g = w[`${stage}_goods`]
  if (g === undefined) return null
  return { goods: Number(g) || 0, services: Number(w[`${stage}_services`]) || 0, unspecified: Number(w[`${stage}_unspecified`]) || 0 }
}

function splitRowsFor(stage: SplitStageKey): SplitRow[] | null {
  if (stage === 'free') {
    // Решение владельца (06.10.2026, жалоба «превышение без типа 20 093 275,58
    // ложная тревога»): «Свободно» по типу = «Бюджет (ФЭО) по типу» − «Запланировано
    // по типу». Бюджет по типу нередко НЕ разбит (суммы ФЭО заданы на статьях
    // целиком, без распределения на товары/услуги) — тогда feo_goods/feo_services
    // стоят 0, а «план по типу» (из плановых позиций, у которых тип ЕСТЬ) —
    // не 0, и вычитание давало огромное ложное «превышение». Теперь — row.amount
    // = null («нет данных»), когда у ЭТОЙ конкретной корзины (товары/услуги)
    // бюджет по типу не введён (feo_<kind> <= 0); посчитанное число — только
    // когда бюджет по типу у этой корзины реально есть (частичная разбивка —
    // считаем превышение только для разбитой части, см. задание владельца).
    // «без типа» НИКОГДА не помечается превышением — у «без типа» нет
    // самостоятельного бюджета-по-типу, который можно было бы сравнить с
    // планом (см. docstring type_totals.py: feo_unspecified — остаток, не
    // отдельно заданная величина), поэтому строка для unspecified не строится.
    const totals = subsidyTypeTotals()
    if (!totals) return null
    const free = freeByKindFromTypeTotals(totals, roundMoney)
    return [
      { kind: 'goods', label: KIND_LABELS.goods, amount: free.goods },
      { kind: 'services', label: KIND_LABELS.services, amount: free.services },
    ]
  }
  const raw = rawSplitFor(stage)
  if (!raw) return null
  const rows: SplitRow[] = [
    { kind: 'goods', label: KIND_LABELS.goods, amount: raw.goods },
    { kind: 'services', label: KIND_LABELS.services, amount: raw.services },
  ]
  if (Math.abs(raw.unspecified) > 0.5) {
    // «Запланировано»: «без типа» — нейтральная подпись (решение владельца
    // 06.10.2026), не алармирующее «без типа» — сюда попадают и статьи без
    // плановых позиций, и позиции без указанного типа, это не ошибка.
    const label = stage === 'plan_schedule'
      ? 'без разбивки (статьи без плановых позиций или позиции без типа)'
      : KIND_LABELS.unspecified
    rows.push({ kind: 'unspecified', label, amount: raw.unspecified })
  }
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

// ── «Заключено договоров» — список договоров (квик-план 06.10.2026) ─────────
const contractsDrillVisible = ref(false)
function openContractsDrill() {
  if (!ctx.selectedId.value) return
  contractsDrillVisible.value = true
}

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
/* Задача 3 (04.10.2026): подпись «из них ещё уйдёт помесячно...» у карточки
   «Заключено договоров» — переносится на мобильной ширине, не вылезает. */
.kpi-sub-note {
  margin-top: 4px;
  line-height: 1.3;
  white-space: normal;
  word-break: break-word;
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
/* Карточка «Оплачено» (05.10.2026) — «подтверждено выпиской» / «по отметке
   сотрудников», каждая со своей строкой товары/услуги. */
.kpi-paid-dual {
  margin-top: 4px;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.kpi-paid-dual-row {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 2px 6px;
  font-size: 11.5px;
  line-height: 1.3;
  min-width: 0;
}
.kpi-paid-dual-label {
  opacity: 0.75;
}
.kpi-paid-dual-amount {
  font-weight: 600;
  white-space: nowrap;
  margin-left: auto;
}
.kpi-paid-dual-warn .kpi-paid-dual-amount {
  color: #fb923c;
}
.kpi-paid-dual-sub {
  font-size: 10.5px;
  opacity: 0.6;
  margin-bottom: 3px;
}
/* Задача 3 (06.10.2026): кружки-маркеры перед «товары»/«услуги» — в одну
   строку (card шире, высота карточки расти не должна). */
.kpi-paid-dual-sub-dots {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}
.kpi-paid-dual-chip {
  display: flex;
  align-items: center;
  gap: 4px;
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
/* Задание владельца 06.10.2026 («где превышение») — чип сам кликабелен,
   не только отдельная кнопка «Где?» рядом с решением. */
.kpi-type-excess-chip-clickable {
  cursor: pointer;
}
</style>
