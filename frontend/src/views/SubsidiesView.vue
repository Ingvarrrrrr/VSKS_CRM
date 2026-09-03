<template>
  <div class="subsidies-page">

    <!-- ── Header ── -->
    <div class="page-header">
      <div class="page-header-left">
        <v-icon icon="mdi-cash-multiple" size="32" color="#3B82F6" class="mr-3" />
        <div>
          <div class="page-title">Субсидии</div>
          <div class="page-subtitle">Управление субсидиями и распределение бюджета · {{ selectedYear }}</div>
        </div>
      </div>
      <div class="page-header-right">
        <v-chip-group v-if="availableYears.length" v-model="selectedYear" mandatory class="year-chips mr-3">
          <v-chip
            v-for="year in availableYears" :key="year" :value="year"
            filter variant="elevated" color="primary" size="small"
          >{{ year }}</v-chip>
        </v-chip-group>
        <v-btn-toggle v-if="!mobile" v-model="viewMode" mandatory density="comfortable" variant="outlined" divided class="mr-2">
          <v-btn value="table" size="small" icon="mdi-table" title="Таблица" />
          <v-btn value="cards" size="small" icon="mdi-view-grid" title="Карточки" />
        </v-btn-toggle>
        <RegistryExportButton
          title="Реестр субсидий"
          :get-columns="getSubsidyExportColumns"
          :get-rows="getSubsidyExportRows"
          :get-capture-el="() => registryArea"
          class="mr-2"
          @error="(m) => showSnack(m, 'error')"
        />
        <v-btn color="primary" prepend-icon="mdi-plus" @click="showAddDialog = true">
          Добавить
        </v-btn>
      </div>
    </div>

    <!-- ── Loading ── -->
    <div v-if="loading" class="d-flex justify-center py-16">
      <v-progress-circular indeterminate color="primary" size="52" />
    </div>

    <template v-else>
      <!-- ── Empty ── -->
      <div v-if="filteredSubsidies.length === 0" class="empty-state">
        <v-icon icon="mdi-cash-off" size="64" color="grey-lighten-2" />
        <div class="text-h6 text-medium-emphasis mt-3">Нет субсидий за {{ selectedYear }} год</div>
        <v-btn class="mt-4" variant="tonal" color="primary" prepend-icon="mdi-plus" @click="showAddDialog = true">
          Добавить субсидию
        </v-btn>
      </div>

      <template v-else>
       <div ref="registryArea">
        <!-- ── Table view ── -->
        <v-data-table
          v-if="effectiveView === 'table'"
          :headers="subsidyTableHeaders"
          :items="filteredSubsidies"
          density="compact"
          :items-per-page="25"
          hover
          class="subsidy-main-table mb-3"
        >
          <template #item.feo_budget_total="{ item }">
            {{ formatCurrencyShort(item.feo_budget_total || item.budget) }}
          </template>
          <template #item.planned="{ item }">
            <span style="color:#F59E0B">{{ formatCurrencyShort(item.planned) }}</span>
          </template>
          <template #item.ordered="{ item }">
            <span style="color:#3B82F6">{{ formatCurrencyShort(item.ordered) }}</span>
          </template>
          <template #item.paid="{ item }">
            <span style="color:var(--color-paid)">{{ formatCurrencyShort(item.paid) }}</span>
          </template>
          <template #item.contractor_name="{ item }">
            <span v-if="item.contractor_name" class="d-flex align-center">
              <v-icon icon="mdi-account-tie" size="13" class="mr-1" color="teal" />
              {{ item.contractor_name }}
            </span>
            <span v-else class="text-medium-emphasis">—</span>
          </template>
          <template #item.feo_filled="{ item }">
            <v-icon
              :icon="item.feo_filled ? 'mdi-check-circle' : 'mdi-circle-outline'"
              :color="item.feo_filled ? 'success' : 'grey-lighten-1'"
              size="18"
            />
          </template>
          <template #item.ceiling_committed_percent="{ item }">
            <v-chip
              v-if="item.ceiling_exceeded || item.ceiling_near_warning"
              size="x-small"
              :color="item.ceiling_exceeded ? 'error' : 'warning'"
              variant="flat"
              :title="`Заказано ${formatCurrency(item.ceiling_committed_total || 0)} из потолка ${formatCurrency(item.ceiling_total || 0)} — ${item.ceiling_committed_percent}% (порог предупреждения ${item.ceiling_warn_percent}%)`"
            >{{ item.ceiling_committed_percent }}%</v-chip>
            <span v-else class="text-medium-emphasis">—</span>
          </template>
          <template #item.name="{ item }">
            <span class="font-weight-medium cursor-pointer" @click="toggleSelect(item.id)">{{ item.name }}</span>
            <v-chip v-if="item.status === 'draft'" size="x-small" color="warning" variant="flat" class="ml-2">Черновик</v-chip>
          </template>
          <template #item.actions="{ item }">
            <div class="d-flex align-center justify-end" style="gap:2px">
              <v-btn
                v-if="canApproveSubsidy(item)"
                icon="mdi-check-decagram" size="x-small" variant="text" color="success"
                title="Утвердить черновик субсидии"
                :loading="approvingSubsidyId === item.id"
                @click.stop="approveSubsidy(item)"
              />
              <v-btn icon="mdi-account-group" size="x-small" variant="text" color="deep-purple" title="Участники (соредакторы)" @click.stop="openMembersDialog(item)" />
              <v-btn
                icon="mdi-file-document-multiple-outline"
                size="x-small" variant="text"
                :color="contractTemplates[item.id] ? 'indigo' : 'grey-lighten-1'"
                :title="contractTemplates[item.id] ? 'Шаблоны документов (договоры, СЗ, ТЗ, Фабрикант) — есть свои' : 'Шаблоны документов (договоры, СЗ, ТЗ, Фабрикант)'"
                @click.stop="openTemplateDialog(item)"
              />
              <v-btn icon="mdi-account-multiple" size="x-small" variant="text" color="teal" title="Согласующие" @click.stop="openApproversDialog(item)" />
              <v-btn icon="mdi-history" size="x-small" variant="text" color="blue-grey" title="История бюджета" @click.stop="openHistoryDialog(item)" />
              <v-btn icon="mdi-pencil" size="x-small" variant="text" color="primary" @click.stop="startEdit(item)" />
              <v-btn icon="mdi-delete" size="x-small" variant="text" color="error" @click.stop="confirmDelete(item)" />
            </div>
          </template>
        </v-data-table>

        <!-- ── Cards grid ── -->
        <div v-else class="subsidies-grid">
          <div
            v-for="(s, idx) in subPaged" :key="s.id"
            class="subsidy-card"
            :class="{ 'subsidy-card--active': selectedId === s.id, 'subsidy-card--drag-over': cardDragOverIdx === idx, 'subsidy-card--dragging': cardDragIdx === idx }"
            draggable="true"
            @click="toggleSelect(s.id)"
            @dragstart="onCardDragStart($event, idx)"
            @dragover.prevent="onCardDragOver(idx)"
            @dragleave="cardDragOverIdx = -1"
            @drop.prevent="onCardDrop(idx)"
            @dragend="cardDragIdx = -1; cardDragOverIdx = -1"
          >
            <div class="sc-title-band">
              <div v-fit-text class="sc-name" :title="s.name">{{ s.name }}</div>
              <v-chip v-if="s.status === 'draft'" size="x-small" color="warning" variant="flat" class="ml-2">Черновик</v-chip>
              <div class="sc-actions">
                <v-btn
                  v-if="canApproveSubsidy(s)"
                  icon="mdi-check-decagram" size="x-small" variant="text" color="success"
                  title="Утвердить черновик субсидии"
                  :loading="approvingSubsidyId === s.id"
                  @click.stop="approveSubsidy(s)"
                />
                <v-btn icon="mdi-account-group" size="x-small" variant="text" color="deep-purple" title="Участники (соредакторы)" @click.stop="openMembersDialog(s)" />
                <v-btn
                  icon="mdi-file-document-multiple-outline"
                  size="x-small" variant="text"
                  :color="contractTemplates[s.id] ? 'indigo' : 'grey-lighten-1'"
                  :title="contractTemplates[s.id] ? 'Шаблоны документов (договоры, СЗ, ТЗ, Фабрикант) — есть свои' : 'Шаблоны документов (договоры, СЗ, ТЗ, Фабрикант)'"
                  @click.stop="openTemplateDialog(s)"
                />
                <v-btn icon="mdi-account-multiple" size="x-small" variant="text" color="teal" title="Согласующие" @click.stop="openApproversDialog(s)" />
                <v-btn icon="mdi-history" size="x-small" variant="text" color="blue-grey" title="История бюджета" @click.stop="openHistoryDialog(s)" />
                <v-btn icon="mdi-pencil" size="x-small" variant="text" color="primary" @click.stop="startEdit(s)" />
                <v-btn icon="mdi-delete" size="x-small" variant="text" color="error" @click.stop="confirmDelete(s)" />
              </div>
            </div>

            <div class="sc-budget">{{ formatCurrencyShort(s.feo_budget_total || s.budget) }}</div>
            <div class="sc-budget-label">{{ (s.feo_budget_total || 0) > 0 ? 'Бюджет ФЭО (расчёт)' : 'Бюджет' }}</div>

            <div class="sc-mini-row">
              <div class="sc-mini" title="Запланировано (план ФЭО + заявки) — то же, что «Запланировано» на шкале ниже">
                <div class="sc-mini-label">Запланировано</div>
                <div class="sc-mini-val" style="color:#F59E0B">{{ formatCurrencyShort(s.planned) }}</div>
              </div>
              <div class="sc-mini" title="Закупки в статусе «Заказано» — заказ размещён, поставка не завершена">
                <div class="sc-mini-label">Заказано</div>
                <div class="sc-mini-val" style="color:#3B82F6">{{ formatCurrencyShort(s.ordered) }}</div>
              </div>
              <div class="sc-mini" title="Закупки в статусе «Оплачено» — фактически оплаченные суммы">
                <div class="sc-mini-label">Оплачено</div>
                <div class="sc-mini-val" style="color:var(--color-paid)">{{ formatCurrencyShort(s.paid) }}</div>
              </div>
            </div>

            <v-progress-linear
              :model-value="pct(s.planned, s.feo_budget_total || s.budget)"
              :color="progressColor(pct(s.planned, s.feo_budget_total || s.budget))"
              height="6" rounded class="mt-3"
            />
            <BudgetBar
              class="mt-3"
              hide-legend
              hide-name
              :subsidy="{
                id: s.id,
                name: s.name,
                budget: s.feo_budget_total || s.budget,
                planned: s.planned,
                contracted: s.contracted,
                paid: s.paid,
              }"
            />
            <v-chip
              v-if="Math.abs(cardDelta(s)) > 0.01"
              :color="cardDelta(s) > 0 ? '#fb923c' : '#ef4444'"
              size="small"
              class="mt-1 sc-delta-chip"
              prepend-icon="mdi-alert"
              :title="cardDelta(s) > 0
                ? `Бюджет ${Math.round(s.feo_budget_total || s.budget || 0).toLocaleString('ru-RU')} ₽ − запланировано (план ФЭО + заявки) ${Math.round(s.planned || 0).toLocaleString('ru-RU')} ₽ = можно допланировать ${Math.round(cardDelta(s)).toLocaleString('ru-RU')} ₽`
                : `Запланировано (план ФЭО + заявки) ${Math.round(s.planned || 0).toLocaleString('ru-RU')} ₽ — больше бюджета ${Math.round(s.feo_budget_total || s.budget || 0).toLocaleString('ru-RU')} ₽ на ${Math.round(-cardDelta(s)).toLocaleString('ru-RU')} ₽`"
            >ФЭО {{ cardDelta(s) > 0 ? '>' : '<' }} план: {{ cardDelta(s) > 0 ? 'допланировать' : 'урезать' }} {{ formatCurrencyShort(Math.abs(cardDelta(s))) }}</v-chip>
            <v-chip
              v-else-if="(s.feo_budget_total || s.budget || 0) > 0 && (s.planned || 0) > 0"
              color="success"
              size="small"
              class="mt-1 sc-delta-chip"
              prepend-icon="mdi-check"
              :title="`Бюджет ФЭО и запланировано (план ФЭО + заявки) совпадают: ${Math.round(s.planned).toLocaleString('ru-RU')} ₽`"
            >ФЭО = план</v-chip>
            <v-chip
              v-if="s.ceiling_exceeded || s.ceiling_near_warning"
              :color="s.ceiling_exceeded ? '#ef4444' : '#f59e0b'"
              size="small"
              class="mt-1 sc-delta-chip"
              prepend-icon="mdi-alert-octagon"
              :title="`Заказано ${formatCurrencyShort(s.ceiling_committed_total || 0)} из потолка ${formatCurrencyShort(s.ceiling_total || 0)} — ${s.ceiling_committed_percent}% (порог предупреждения ${s.ceiling_warn_percent}%)`"
            >{{ s.ceiling_exceeded ? 'Потолок превышен' : 'Близко к потолку' }}: {{ s.ceiling_committed_percent }}%</v-chip>
            <div v-if="s.contractor_name" class="sc-contractor">
              <v-icon icon="mdi-account-tie" size="13" class="mr-1" />
              <span>{{ s.contractor_name }}</span>
            </div>
            <div class="sc-footer">
              <div class="sc-pct">{{ pct(s.planned, s.feo_budget_total || s.budget) }}% запланировано</div>
              <div class="sc-feo-badge" :class="s.feo_filled ? 'sc-feo-badge--ok' : 'sc-feo-badge--no'">
                <v-icon :icon="s.feo_filled ? 'mdi-check-circle' : 'mdi-circle-outline'" size="14" class="mr-1" />
                ФЭО
              </div>
            </div>
          </div>
        </div>
       </div>
        <!-- cards pagination -->
        <div v-if="subTotalPages > 1" class="d-flex justify-center mt-3">
          <v-pagination v-model="subPage" :length="subTotalPages" density="comfortable" />
        </div>

        <!-- ── Summary bar ── -->
        <div class="summary-bar">
          <div class="summary-item">
            <span class="summary-label">Субсидий</span>
            <span class="summary-value">{{ filteredSubsidies.length }}</span>
          </div>
          <div class="summary-sep" />
          <div class="summary-item summary-item--link" @click="router.push('/dashboard')">
            <span class="summary-label">Бюджет ФЭО (итого)</span>
            <span class="summary-value">{{ formatCurrency(totals.budget) }}</span>
          </div>
          <div class="summary-sep" />
          <div class="summary-item summary-item--link" @click="router.push('/orders')">
            <span class="summary-label">Запланировано</span>
            <span class="summary-value" style="color:var(--color-planned)">{{ formatCurrency(totals.planned) }}</span>
          </div>
          <div class="summary-sep" />
          <div class="summary-item summary-item--link" @click="router.push('/orders?status=work_in_progress')">
            <span class="summary-label">Заказано</span>
            <span class="summary-value" style="color:#3B82F6">{{ formatCurrency(totals.ordered) }}</span>
          </div>
          <div class="summary-sep" />
          <div class="summary-item summary-item--link" @click="router.push('/orders?status=paid')">
            <span class="summary-label">Оплачено</span>
            <span class="summary-value" style="color:var(--color-paid)">{{ formatCurrency(totals.paid) }}</span>
          </div>
          <div class="summary-sep" />
          <div class="summary-item summary-item--link" @click="router.push('/dashboard')">
            <span class="summary-label">Свободно</span>
            <span class="summary-value" :style="{ color: totals.budget - totals.planned < 0 ? '#EF4444' : '#3B82F6' }">
              {{ formatCurrency(totals.budget - totals.planned) }}
            </span>
          </div>
          <div class="summary-sep" />
          <div class="summary-item summary-item--link" @click="router.push('/orders?status=work_in_progress')">
            <span class="summary-label">Ведётся работа</span>
            <span class="summary-value" style="color:#6366F1">{{ formatCurrency(totals.work) }}</span>
          </div>
          <div class="summary-sep" />
          <div class="summary-item summary-item--link" @click="router.push('/contracts')">
            <span class="summary-label">Заключено договоров</span>
            <span class="summary-value" style="color:#0284C7">{{ formatCurrency(totals.contracts) }}</span>
          </div>
          <div class="summary-sep" />
          <div class="summary-item summary-item--link" @click="router.push('/orders?status=delivered')">
            <span class="summary-label">Поставлено</span>
            <span class="summary-value" style="color:#14B8A6">{{ formatCurrency(totals.delivered) }}</span>
          </div>
          <div class="summary-sep" />
          <div class="summary-item">
            <span class="summary-label">Поставлено не оплачено</span>
            <span class="summary-value" style="color:#EF4444">{{ formatCurrency(totals.delivered_unpaid) }}</span>
          </div>
        </div>

        <!-- ── Detail panel ── -->
        <div v-if="selectedSubsidy" class="detail-panel">
          <div class="detail-header">
            <v-icon icon="mdi-folder-open-outline" size="20" color="#3B82F6" class="mr-2" />
            <span class="detail-title">{{ selectedSubsidy.name }} — направления ФЭО</span>
            <v-chip v-if="selectedSubsidy.status === 'draft'" size="x-small" color="warning" variant="flat" class="ml-2">Черновик</v-chip>
            <v-btn
              v-if="canApproveSubsidy(selectedSubsidy)"
              size="small" variant="tonal" color="success" prepend-icon="mdi-check-decagram"
              class="ml-3"
              :loading="approvingSubsidyId === selectedSubsidy.id"
              @click="approveSubsidy(selectedSubsidy)"
            >Утвердить</v-btn>
            <v-btn icon="mdi-close" size="x-small" variant="text" class="ml-auto" @click="selectedId = null" />
          </div>

          <!-- KPI mini-cards for selected subsidy -->
          <div class="detail-kpis">
            <!-- 1. Бюджет (ФЭО) -->
            <v-tooltip location="bottom" :disabled="true">
              <template #activator="{ props: tip }">
                <div v-bind="tip" class="kpi-card kpi-budget" :class="kpiCardClass('budget')" title="Живой расчёт по дереву ФЭО: ручное финансирование категорий, без него — факт, иначе план. Совпадает с ИТОГО дерева ниже" @click="onKpiCardClick('budget')">
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
                <div v-bind="tip" class="kpi-card kpi-plan_schedule" :class="kpiCardClass('plan_schedule')" title="Плановая сумма дерева ФЭО: ручные позиции (импорт/создание в ФЭО) + заявки в плане закупок" @click="onKpiCardClick('plan_schedule')">
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
                <div v-bind="tip" class="kpi-card kpi-work" :class="kpiCardClass('work')" @click="onKpiCardClick('work')">
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
                <div v-bind="tip" class="kpi-card kpi-ordered" :class="kpiCardClass('ordered')" @click="onKpiCardClick('ordered')">
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
                <div v-bind="tip" class="kpi-card kpi-contracts" :class="kpiCardClass('contracts')" @click="onKpiCardClick('contracts')">
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
                <div v-bind="tip" class="kpi-card kpi-delivered" :class="kpiCardClass('delivered')" @click="onKpiCardClick('delivered')">
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
                <div v-bind="tip" class="kpi-card kpi-delivered_unpaid" :class="kpiCardClass('delivered_unpaid')" @click="onKpiCardClick('delivered_unpaid')">
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
                <div v-bind="tip" class="kpi-card kpi-paid" :class="kpiCardClass('paid')" @click="onKpiCardClick('paid')">
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
                  :class="[selectedBudget - selectedPlannedTotal < 0 ? 'kpi-over' : '', kpiCardClass('free')]"
                  @click="onKpiCardClick('free')"
                >
                  <div class="kpi-icon-box"><v-icon icon="mdi-cash-lock-open" size="26" /></div>
                  <div class="kpi-body">
                    <div class="kpi-value">{{ formatCurrencyRound(Math.abs(kpiSubAnim_free)) }}</div>
                    <div class="kpi-label">{{ selectedBudget - selectedPlannedTotal < 0 ? 'Превышение' : 'Свободно' }}</div>
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
            v-if="selectedSubsidy.ceiling_exceeded || selectedSubsidy.ceiling_near_warning"
            :type="selectedSubsidy.ceiling_exceeded ? 'error' : 'warning'"
            density="compact"
            variant="tonal"
            class="mb-3"
            icon="mdi-alert-octagon-outline"
          >
            {{ selectedSubsidy.ceiling_exceeded ? 'Потолок субсидии превышен: ' : 'Приближение к потолку субсидии: ' }}
            заказано {{ formatCurrency(selectedSubsidy.ceiling_committed_total || 0) }}
            из потолка {{ formatCurrency(selectedSubsidy.ceiling_total || 0) }}
            — это {{ selectedSubsidy.ceiling_committed_percent }}%
            (порог предупреждения {{ selectedSubsidy.ceiling_warn_percent }}%).
          </v-alert>
          <!-- Подсказка активной KPI-метрики -->
          <div v-if="activeKpi" class="feo-kpi-banner">
            <v-icon icon="mdi-filter-variant" size="16" color="#fb923c" />
            <span v-if="!plannedItemsLoaded">загрузка состава…</span>
            <span v-else-if="kpiHasMatches">{{ KPI_LABELS[activeKpi] }}</span>
            <span v-else>в дереве ФЭО нечего подсвечивать: {{ KPI_EMPTY_REASONS[activeKpi] }}</span>
            <v-btn size="x-small" variant="text" color="primary" class="ml-auto" @click="resetKpi">Сбросить</v-btn>
          </div>
          <!-- Контрагент -->
          <div v-if="selectedSubsidy.contractor_name" class="detail-contractor mt-2 mb-3">
            <v-icon icon="mdi-account-tie" size="16" color="teal" class="mr-1" />
            <span class="text-body-2 font-weight-medium">{{ selectedSubsidy.contractor_name }}</span>
            <span v-if="selectedSubsidy.contractor_inn" class="text-caption text-medium-emphasis ml-2">ИНН {{ selectedSubsidy.contractor_inn }}</span>
            <v-btn
              icon="mdi-pencil-outline" size="x-small" variant="text" color="teal" class="ml-2"
              title="Реквизиты контрагента для этой субсидии"
              @click="openContractorOverride(selectedSubsidy)"
            />
          </div>

          <!-- FEO categories -->
          <div v-if="loadingFeo" class="d-flex justify-center py-8">
            <v-progress-circular indeterminate color="primary" />
          </div>

          <div v-else>
            <div class="detail-feo-header">
              <span class="chart-card-title">Направления ФЭО</span>
              <div class="d-flex align-center ml-4" style="gap:6px" title="Группировка позиций «из заявок» при раскрытии направления">
                <span class="text-caption text-medium-emphasis">Позиции:</span>
                <v-btn-toggle v-model="feoItemsGroupBy" density="compact" mandatory variant="outlined" color="teal" style="height:26px" :disabled="plannedBase === 'purchases'">
                  <v-btn size="x-small" value="none">Нет</v-btn>
                  <v-btn size="x-small" value="category">По категориям</v-btn>
                  <v-btn size="x-small" value="category_type">Категории + виды</v-btn>
                </v-btn-toggle>
              </div>
              <div class="d-flex align-center ml-auto" style="gap:8px">
                <v-btn size="small" variant="outlined" color="success" prepend-icon="mdi-file-excel-outline" @click="openExportVersionsDialog">Выгрузить ФЭО</v-btn>
                <template v-if="canEditFeo">
                  <v-btn size="small" variant="outlined" prepend-icon="mdi-download-outline" @click="downloadFeoTemplate">Шаблон</v-btn>
                  <v-btn size="small" variant="outlined" color="secondary" prepend-icon="mdi-upload-outline" @click="feoImport.show = true">Импорт</v-btn>
                </template>
                <!-- 12-04: Version history -->
                <v-btn size="small" variant="text" color="blue-grey" prepend-icon="mdi-history" @click="openVersionHistory">
                  История
                </v-btn>
                <!-- 12-05: Save version -->
                <v-btn
                  v-if="canSaveVersion"
                  size="small"
                  variant="text"
                  color="success"
                  prepend-icon="mdi-content-save"
                  @click="openSaveVersionDialog"
                >
                  Сохранить редакцию
                </v-btn>
                <!-- 12-04: Export dropdown -->
                <v-menu>
                  <template #activator="{ props: menuProps }">
                    <v-btn size="small" variant="outlined" color="teal" prepend-icon="mdi-export" append-icon="mdi-chevron-down" v-bind="menuProps">
                      Экспорт
                    </v-btn>
                  </template>
                  <v-list density="compact">
                    <v-list-item prepend-icon="mdi-microsoft-excel" @click="exportPlanGraphExcel">
                      <v-list-item-title>Excel (.xlsx)</v-list-item-title>
                    </v-list-item>
                    <v-list-item prepend-icon="mdi-microsoft-word" @click="exportPlanGraphDocx">
                      <v-list-item-title>Word (шаблон)</v-list-item-title>
                    </v-list-item>
                    <v-list-item prepend-icon="mdi-file-pdf-box" @click="exportFeoPdf">
                      <v-list-item-title>PDF (как на экране)</v-list-item-title>
                    </v-list-item>
                    <v-divider />
                    <v-list-item prepend-icon="mdi-upload-outline">
                      <v-list-item-title>
                        <label style="cursor:pointer">
                          Загрузить шаблон .docx
                          <input type="file" accept=".docx" style="display:none"
                            @change="(e: any) => { if (e.target.files[0]) uploadTemplate(e.target.files[0]) }" />
                        </label>
                      </v-list-item-title>
                    </v-list-item>
                  </v-list>
                </v-menu>
                <v-btn v-if="canEditFeo" size="small" variant="tonal" color="primary" prepend-icon="mdi-plus" @click="feoForm.parentId = null; showAddFeoDialog = true">Добавить</v-btn>
              </div>
            </div>

            <div v-if="feoCategories.length === 0" class="feo-empty">
              <v-icon icon="mdi-folder-off" size="40" color="grey-lighten-2" />
              <div class="text-caption text-medium-emphasis mt-2">Нет категорий ФЭО</div>
            </div>

            <!-- FEO table with D&D, inline edit, total row -->
            <div v-else ref="feoTableArea" class="feo-table-wrap">
              <table class="feo-table">
                <thead>
                  <tr>
                    <th class="feo-th feo-th-name" :style="feoResize.resizeStyle('name')">
                      Наименование
                      <span class="col-resize-handle" @mousedown="feoResize.onResizeStart($event, 'name')"></span>
                    </th>
                    <th class="feo-th feo-th-num" :style="feoResize.resizeStyle('budget')">
                      <div>Количество и<br>финансирование по ФЭО</div>
                      <span class="col-resize-handle" @mousedown="feoResize.onResizeStart($event, 'budget')"></span>
                    </th>
                    <th class="feo-th feo-th-num" :style="feoResize.resizeStyle('qty')">
                      <div>ПЛАНОВОЕ<br>КОЛ-ВО</div>
                      <div class="feo-residual-toggle">
                        <span
                          :class="plannedQtyBase === 'all' ? 'feo-residual-opt feo-residual-opt--active' : 'feo-residual-opt'"
                          title="Ручной план ФЭО + позиции заявок в плане закупок"
                          @click.stop="plannedQtyBase = 'all'"
                        >все</span>
                        <span
                          :class="plannedQtyBase === 'manual' ? 'feo-residual-opt feo-residual-opt--active' : 'feo-residual-opt'"
                          title="Только ручной план ФЭО"
                          @click.stop="plannedQtyBase = 'manual'"
                        >ручные</span>
                        <span
                          :class="plannedQtyBase === 'requests' ? 'feo-residual-opt feo-residual-opt--active' : 'feo-residual-opt'"
                          title="Только позиции заявок со статусом «План закупок» и дальше"
                          @click.stop="plannedQtyBase = 'requests'"
                        >из заявок</span>
                        <span
                          :class="plannedQtyBase === 'purchases' ? 'feo-residual-opt feo-residual-opt--active' : 'feo-residual-opt'"
                          title="Ручной план ФЭО + позиции закупок без слияния; при раскрытии направления — папки по закупкам"
                          @click.stop="plannedQtyBase = 'purchases'"
                        >по закупкам</span>
                      </div>
                      <span class="col-resize-handle" @mousedown="feoResize.onResizeStart($event, 'qty')"></span>
                    </th>
                    <th class="feo-th feo-th-num" :style="feoResize.resizeStyle('planned')">
                      <div>ПЛАНОВАЯ<br>СУММА</div>
                      <div class="feo-residual-toggle">
                        <span
                          :class="plannedSumBase === 'all' ? 'feo-residual-opt feo-residual-opt--active' : 'feo-residual-opt'"
                          title="Ручной план ФЭО + позиции заявок в плане закупок"
                          @click.stop="plannedSumBase = 'all'"
                        >все</span>
                        <span
                          :class="plannedSumBase === 'manual' ? 'feo-residual-opt feo-residual-opt--active' : 'feo-residual-opt'"
                          title="Только ручной план: кол-во × стоимость за ед."
                          @click.stop="plannedSumBase = 'manual'"
                        >ручные</span>
                        <span
                          :class="plannedSumBase === 'requests' ? 'feo-residual-opt feo-residual-opt--active' : 'feo-residual-opt'"
                          title="Только позиции заявок со статусом «План закупок» и дальше"
                          @click.stop="plannedSumBase = 'requests'"
                        >из заявок</span>
                        <span
                          :class="plannedSumBase === 'purchases' ? 'feo-residual-opt feo-residual-opt--active' : 'feo-residual-opt'"
                          title="Ручной план ФЭО + позиции закупок без слияния; при раскрытии направления — папки по закупкам"
                          @click.stop="plannedSumBase = 'purchases'"
                        >по закупкам</span>
                      </div>
                      <span class="col-resize-handle" @mousedown="feoResize.onResizeStart($event, 'planned')"></span>
                    </th>
                    <th class="feo-th feo-th-num" :style="feoResize.resizeStyle('spent')"
                      title="Сумма всех позиций закупок этой категории во всех статусах плана закупок (включая «План закупок»), в отличие от договорного факта"
                    >
                      В плане-графике
                      <span class="col-resize-handle" @mousedown="feoResize.onResizeStart($event, 'spent')"></span>
                    </th>
                    <th class="feo-th feo-th-num" :style="feoResize.resizeStyle('residual')">
                      <div>ОСТАТОК</div>
                      <div class="feo-residual-toggle">
                        <span
                          :class="residualBase === 'plan' ? 'feo-residual-opt feo-residual-opt--active' : 'feo-residual-opt'"
                          title="Остаток = Плановая сумма − В плане-графике"
                          @click.stop="residualBase = 'plan'"
                        >от плановой</span>
                        <span
                          :class="residualBase === 'feo' ? 'feo-residual-opt feo-residual-opt--active' : 'feo-residual-opt'"
                          title="Остаток = Финансирование по ФЭО − В плане-графике"
                          @click.stop="residualBase = 'feo'"
                        >от ФЭО</span>
                      </div>
                      <span class="col-resize-handle" @mousedown="feoResize.onResizeStart($event, 'residual')"></span>
                    </th>
                    <th class="feo-th feo-th-actions"></th>
                  </tr>
                </thead>
                <tbody>
                  <template v-for="node in visibleFeoNodes" :key="node.id">
                    <tr
                      v-if="isNodeVisible(node) && !(plannedBase === 'requests' && isManualPosLeaf(node))"
                      class="feo-tr"
                      :data-feo-node-id="node.id"
                      :class="[
                        `feo-tr--l${node.level}`,
                        dragOverId === node.id ? 'feo-drop-target' : '',
                        dragNodeId === node.id ? 'feo-dragging' : '',
                        kpiNodeClass(node),
                      ]"
                      :draggable="canEditFeo"
                      @dragstart="canEditFeo && onDragStart($event, node)"
                      @dragover.prevent="canEditFeo && onDragOver($event, node)"
                      @dragleave="onDragLeave"
                      @drop="canEditFeo && onDrop($event, node)"
                      @dragend="onDragEnd"
                    >
                      <!-- Наименование -->
                      <td class="feo-td feo-td-name" :style="{ paddingLeft: `${node.depth * 20 + 8}px` }">
                        <div class="feo-name-inner">
                          <!-- Лист ФЭО: клик по папке/шеврону раскрывает ЕДИНУЮ панель «Плановые
                               позиции» (expandedItemPanels/toggleItemPanel) — единственный источник
                               детализации листа с 2026-08-07 (устранение тройного рендера одной и
                               той же позиции, см. ШАГ 1 плана дедупликации дерева ФЭО). Раньше здесь
                               был отдельный toggleReqItems (hasReqItems), дававший второй независимый
                               список тех же позиций закупок — убран целиком. -->
                          <span class="feo-tree-chevron" @click="node.hasChildren ? toggleExpand(node.id) : toggleItemPanel(node)">
                            <v-icon
                              v-if="node.hasChildren"
                              size="15"
                              :icon="expandedIds.includes(node.id) ? 'mdi-chevron-down' : 'mdi-chevron-right'"
                              color="grey"
                              class="mr-1 cursor-pointer"
                            />
                            <v-icon
                              v-else
                              size="15"
                              :icon="expandedItemPanels.has(node.id) ? 'mdi-chevron-down' : 'mdi-chevron-right'"
                              color="grey"
                              class="mr-1 cursor-pointer"
                            />
                          </span>
                          <v-icon
                            size="16"
                            class="mr-1 flex-shrink-0 cursor-pointer"
                            :icon="node.hasChildren
                              ? (expandedIds.includes(node.id) ? 'mdi-folder-open' : 'mdi-folder')
                              : (expandedItemPanels.has(node.id) ? 'mdi-folder-open' : 'mdi-folder')"
                            :color="node.level === 1 ? '#3B82F6' : node.level === 2 ? '#F59E0B' : '#22C55E'"
                            @click="node.hasChildren ? toggleExpand(node.id) : toggleItemPanel(node)"
                          />
                          <span class="feo-name" :class="`feo-name--l${node.level}`">{{ node.name }}</span>
                          <span v-if="node.code" class="feo-code ml-2">{{ node.code }}</span>
                          <span v-if="node.appendix" class="feo-appendix ml-1">{{ node.appendix }}</span>
                        </div>
                        <v-tooltip v-if="node.description" location="bottom" open-delay="150" :max-width="420">
                          <template #activator="{ props: tooltipProps }">
                            <div v-bind="tooltipProps" class="feo-plan-note text-caption text-medium-emphasis text-truncate" style="max-width:100%">{{ node.description }}</div>
                          </template>
                          <span style="white-space:pre-line">{{ node.description }}</span>
                        </v-tooltip>
                      </td>

                      <!-- Финансирование по ФЭО (inline edit) -->
                      <!-- vertical-align:top (жалоба владельца 2026-08-17, разбор превышения): .feo-td
                           по умолчанию vertical-align:middle — когда «Плановая сумма» справа выросла
                           расшифровкой «из-за: …» на несколько строк, соседние числовые колонки
                           центрировались по всей высоте строки и визуально ЗАЛЕЗАЛИ на середину текста
                           расшифровки. top — сироты не всплывают в середину. -->
                      <td class="feo-td feo-td-num" style="vertical-align:top">
                        <template v-if="feoRollup(node).qty != null || feoRollup(node).amount != null">
                          <div class="feo-plan-note text-right"
                            :class="feoRollup(node).qtyAuto || feoRollup(node).amountAuto ? 'text-medium-emphasis' : ''"
                            :title="(feoRollup(node).qtyAuto || feoRollup(node).amountAuto) ? 'Сумма по вложенным' : 'Количество и стоимость по документу ФЭО'"
                          >
                            <template v-if="feoRollup(node).qty != null && feoRollup(node).amount != null">
                              {{ feoRollup(node).qty }}{{ node.feo_unit ? ` ${node.feo_unit}` : '' }} × {{ feoRollup(node).amount?.toLocaleString('ru-RU') }} ₽
                            </template>
                            <template v-else-if="feoRollup(node).qty != null">
                              {{ feoRollup(node).qty }}{{ node.feo_unit ? ` ${node.feo_unit}` : ' шт' }}
                            </template>
                            <template v-else>
                              {{ feoRollup(node).amount?.toLocaleString('ru-RU') }} ₽
                            </template>
                            <v-chip v-if="feoRollup(node).qtyAuto || feoRollup(node).amountAuto" size="x-small" color="blue-grey" variant="tonal" class="ml-1">авто</v-chip>
                          </div>
                        </template>
                        <div v-if="inlineBudgetId === node.id" class="d-flex align-center justify-end">
                          <input
                            ref="inlineInputEl"
                            v-model="inlineBudgetVal"
                            type="number"
                            class="inline-input"
                            @blur="saveInlineBudget(node)"
                            @keydown.enter="saveInlineBudget(node)"
                            @keydown.esc="inlineBudgetId = null"
                          />
                        </div>
                        <div v-else-if="isAutoNode(node)" class="feo-amount-cell text-right" :class="{ 'feo-amount-cell--readonly': !canEditFeo }" @click="canEditFeo && startInlineBudget(node)"
                          :title="canEditFeo ? 'Расчёт: ручное ФЭО дочерних; без ФЭО — факт (поставлено/оплачено), иначе план. Кликните, чтобы задать вручную' : 'Расчёт: ручное ФЭО дочерних; без ФЭО — факт (поставлено/оплачено), иначе план'"
                        >
                          <template v-if="feoEffectiveFor(node) > 0">
                            <span class="feo-amount text-medium-emphasis">{{ formatCurrency(feoEffectiveFor(node)) }}</span>
                            <v-chip size="x-small" color="blue-grey" variant="tonal" class="ml-1">расчёт</v-chip>
                          </template>
                          <span v-else-if="canEditFeo" class="feo-set-hint">Задать</span>
                          <span v-else class="feo-set-hint">—</span>
                        </div>
                        <div v-else class="feo-amount-cell" :class="{ 'feo-amount-cell--readonly': !canEditFeo }" @click="canEditFeo && startInlineBudget(node)">
                          <span v-if="feoBudgetFor(node) > 0" class="feo-amount"
                            :style="feoChildrenBudgetDiff(node) > 0.005 ? 'color:#EF4444;font-weight:700' : ''"
                          >{{ formatCurrency(feoBudgetFor(node)) }}</span>
                          <span v-else-if="canEditFeo" class="feo-set-hint">Задать</span>
                          <span v-else class="feo-set-hint">—</span>
                        </div>
                        <template v-if="node.hasChildren && node.budget != null && node.budget > 0">
                          <div v-if="!hasManualChildFeo(node)"
                            class="feo-plan-note text-medium-emphasis"
                            title="Ни у одной дочерней строки не задано финансирование по ФЭО"
                          >
                            Подробное деление в ФЭО отсутствовало
                          </div>
                          <div v-else-if="feoChildrenBudgetDiff(node) > 0.005"
                            class="feo-plan-note" style="color:#EF4444"
                            :title="`Ручное ФЭО дочерних ${formatCurrency(manualChildFeoSum(node))} превышает финансирование этой строки ${formatCurrency(node.budget || 0)}. Ищите лишнюю сумму в дочерних строках.`"
                          >
                            заложено в ФЭО {{ formatCurrency(manualChildFeoSum(node)) }} — лишние {{ formatCurrency(feoChildrenBudgetDiff(node)) }}
                          </div>
                          <div v-else-if="feoChildrenBudgetDiff(node) < -0.005"
                            class="feo-plan-note" style="color:#F59E0B"
                            :title="`Ручное ФЭО дочерних ${formatCurrency(manualChildFeoSum(node))} меньше финансирования этой строки ${formatCurrency(node.budget || 0)}. Часть суммы не распределена по дочерним в ФЭО.`"
                          >
                            заложено в ФЭО {{ formatCurrency(manualChildFeoSum(node)) }} — не распределено {{ formatCurrency(-feoChildrenBudgetDiff(node)) }}
                          </div>
                          <div v-else class="feo-plan-note text-medium-emphasis">
                            заложено в ФЭО {{ formatCurrency(manualChildFeoSum(node)) }}
                          </div>
                        </template>
                      </td>

                      <!-- Плановое количество -->
                      <td class="feo-td feo-td-num" style="vertical-align:top">
                        <div v-if="isAutoQtyNode(node)" class="text-right">
                          <div class="feo-amount">{{ feoQtyDisplayFor(node) > 0 ? feoQtyDisplayFor(node) : '—' }}{{ node.unit ? ` ${node.unit}` : '' }}</div>
                          <div v-if="plannedQtyBase === 'all' && feoQtyRequestsFor(node) > 0"
                            class="feo-plan-note text-medium-emphasis"
                            :title="`Количество из позиций заявок в статусе «План закупок» и дальше: ${feoQtyRequestsFor(node)}`"
                          >
                            в т.ч. из заявок {{ feoQtyRequestsFor(node) }}
                          </div>
                          <v-chip size="x-small" color="blue-grey" variant="tonal"
                            title="Количество автоматически считается из дочерних"
                          >авто</v-chip>
                        </div>
                        <div v-else-if="inlineQtyId === node.id" class="d-flex align-center justify-end">
                          <input
                            ref="inlineQtyInputEl"
                            v-model="inlineQtyVal"
                            type="number"
                            class="inline-input"
                            @blur="saveInlineQty(node)"
                            @keydown.enter="saveInlineQty(node)"
                            @keydown.esc="inlineQtyId = null"
                          />
                        </div>
                        <template v-else>
                          <!-- feo-amount-cell — display:inline-flex (см. стили ниже, нужен для строки
                               «сумма/чип» в других колонках) — блочные пояснения feo-plan-note ниже
                               ВЫНЕСЕНЫ из него сиблингами (как в колонке «Финансирование по ФЭО»,
                               см. td выше), иначе inline-flex склеивает их с суммой в одну строку без
                               пробела («204 услугав т.ч. из заявок 2», баг вёрстки 2026-08-07). -->
                          <div class="feo-amount-cell" :class="{ 'feo-amount-cell--readonly': !canEditFeo }" @click="canEditFeo && startInlineQty(node)">
                            <span v-if="feoQtyDisplayFor(node) > 0" class="feo-amount">{{ feoQtyDisplayFor(node) }}{{ node.unit ? ` ${node.unit}` : '' }}</span>
                            <span v-else class="feo-set-hint">—</span>
                          </div>
                          <div v-if="plannedQtyBase === 'all' && feoQtyRequestsFor(node) > 0"
                            class="feo-plan-note text-medium-emphasis"
                            :title="`Количество из позиций заявок в статусе «План закупок» и дальше: ${feoQtyRequestsFor(node)}`"
                          >
                            в т.ч. из заявок {{ feoQtyRequestsFor(node) }}
                          </div>
                          <template v-if="plannedQtyBase === 'all' && matchedReqFor(node).length">
                            <div v-if="mergedQtyDiff(node) > 0"
                              class="feo-plan-note" style="color:#F59E0B"
                              :title="`Всего запланировано ${feoQtyDisplayFor(node)}, в ФЭО заложено ${Number(node.feo_quantity) || 0}`"
                            >
                              на {{ mergedQtyDiff(node) }} превышает заложенный в ФЭО показатель ({{ Number(node.feo_quantity) || 0 }})
                            </div>
                            <div v-else-if="mergedQtyDiff(node) < 0"
                              class="feo-plan-note text-medium-emphasis"
                              :title="`Всего запланировано ${feoQtyDisplayFor(node)}, в ФЭО заложено ${Number(node.feo_quantity) || 0}`"
                            >
                              не хватает {{ -mergedQtyDiff(node) }} до заложенного в ФЭО ({{ Number(node.feo_quantity) || 0 }})
                            </div>
                          </template>
                        </template>
                      </td>

                      <!-- Плановая сумма: ручной план ФЭО и/или позиции заявок (по переключателю) -->
                      <td class="feo-td feo-td-num" style="vertical-align:top">
                        <span v-if="feoPlannedDisplayFor(node) > 0" class="feo-amount"
                          :style="(feoDisplayedFor(node) > 0 && feoPlannedDisplayFor(node) > feoDisplayedFor(node)) || feoHasOverspentDescendant(node) ? 'color:#EF4444;font-weight:700' : ''"
                          :title="plannedSumBase === 'all' ? `Ручные ${formatCurrency(feoPlannedTotalFor(node))} + из заявок ${formatCurrency(feoPlannedRequestsFor(node))}` : ''"
                        >{{ formatCurrency(feoPlannedDisplayFor(node)) }}</span>
                        <span v-else class="feo-amount-empty">—</span>
                        <!-- Заметка «в т.ч. из заявок N ₽» под плановой суммой УБРАНА (жалоба
                             владельца 2026-08-13): совпадает по величине с «в закупках» из строки
                             разбора ниже (feoResidualNoteFor/feoPlanConsumedNoteFor), но стояла прямо
                             под планом и читалась как его часть — «выбрано 695 656, что уже больше
                             561». Та же заметка в колонке «Плановое количество» (feoQtyRequestsFor,
                             см. ниже по файлу) НЕ трогается — она про количество, путаницы там не
                             было. Заметка «в т.ч. из заявок {{ matchedReqTotal }}» (matchedReqFor,
                             сопоставление по ИМЕНИ) была убрана раньше, 2026-08-07, — см. ШАГ 1
                             плана дедупликации. -->
                        <!-- «В т.ч. на самом направлении N ₽» (жалоба владельца 2026-08-13:
                             «48 441,80 — нигде нет такой суммы», «что это за фантом») — часть плана
                             узла с детьми, заложенная НЕПОСРЕДСТВЕННО на нём самом (плановые позиции,
                             привязанные к направлению, а не к его подкатегориям), см.
                             feoOwnDirectionPlanFor(). Кликабельна — раскрывает ту же панель, что и
                             иконка-список в «Действиях» (toggleItemPanel), см. feo-action-slot ниже. -->
                        <div v-if="feoOwnDirectionPlanFor(node) > 0"
                          class="feo-plan-note text-medium-emphasis feo-plan-note--link"
                          title="Часть плана этого направления, заложенная прямо на нём (не в подкатегориях). Клик открывает список этих плановых позиций"
                          @click="toggleItemPanel(node)"
                        >
                          в т.ч. на самом направлении {{ formatCurrency(feoOwnDirectionPlanFor(node)) }}
                        </div>
                        <!-- Жалоба владельца 2026-08-17: «можно добавить N ₽ до финансирования ФЭО» считало
                             N как ФЭО минус ПЛАН (560 000 − 351 844 = 208 156), хотя в закупках уже размещено
                             432 162 — реально до потолка ФЭО остаётся 127 838 (560 000 − 432 162), меньше почти
                             в 2 раза. Первая строка теперь явно называет себя «остатком по ПЛАНУ», вторая
                             (feoRemainingWithPurchasesNote) появляется, только когда «в закупках» уже больше
                             плана — тогда именно она честная, а не первая. -->
                        <div v-if="feoDisplayedFor(node) > 0 && (node.budget != null || feoPlannedDisplayFor(node) > 0) && Math.abs(feoFinDiff(node)) > 0.005"
                          class="feo-plan-note"
                          :style="feoFinDiff(node) > 0 ? 'color:#16A34A' : 'color:#EF4444'"
                          :title="`Финансирование по ФЭО (бюджет, заложенный в документе ФЭО): ${formatCurrency(feoDisplayedFor(node))}. Плановая сумма (сколько уже расписано по плану/заявкам): ${formatCurrency(feoPlannedDisplayFor(node))}`"
                        >
                          {{ feoFinDiff(node) > 0 ? `по плану можно добавить ещё ${formatCurrency(feoFinDiff(node))} до финансирования ФЭО (это остаток по плану, не по факту закупок)` : `надо убрать ${formatCurrency(-feoFinDiff(node))}, чтобы уложиться в ФЭО` }}
                          <div v-if="feoRemainingWithPurchasesNote(node)"
                            style="font-size:11px;color:#EF4444;font-weight:600;margin-top:2px"
                          >
                            {{ feoRemainingWithPurchasesNote(node) }}
                          </div>
                        </div>
                        <div v-if="!feoIsOverBudget(node) && feoHasOverspentDescendant(node)"
                          class="feo-plan-note" style="color:#EF4444"
                          :title="feoOverspentDescendantTitle(node)"
                        >
                          {{ feoOverspentDescendantText(node) }}
                        </div>
                        <!-- Разбор «план · в закупках · свободно» (жалоба владельца 2026-08-13:
                             «план 513 244 — это откуда? Выбрано 695 — откуда?»). Оба источника
                             (feoResidualNoteFor — лист со своими Ур.5-позициями; feoPlanConsumedNoteFor —
                             остальные узлы, включая направления) теперь берут «план» из ТОГО ЖЕ
                             planTreeByCat.plan_manual, что и шапка строки (не считают свою отдельную
                             формулу), и «в закупках» = привязанные + непривязанные позиции заявок —
                             см. комментарии у функций ниже по файлу. -->
                        <div v-if="feoResidualNoteFor(node)"
                          class="feo-plan-note text-medium-emphasis"
                          title="План: сумма плановых позиций этой категории. В закупках: сколько из них уже набрано заявками (привязанными к этим позициям). Свободно: план минус то, что в закупках — если в закупках больше плана, показано превышение"
                        >
                          план {{ formatCurrency(feoResidualNoteFor(node)!.planned) }} · в закупках {{ formatCurrency(feoResidualNoteFor(node)!.consumed) }} ·
                          <span v-if="feoResidualNoteFor(node)!.residual < -0.005" style="color:#EF4444;font-weight:700">больше плана на {{ formatCurrency(-feoResidualNoteFor(node)!.residual) }}</span>
                          <span v-else>свободно {{ formatCurrency(feoResidualNoteFor(node)!.residual) }}</span>
                          <!-- Расшифровка «больше плана на X» (жалоба владельца 2026-08-13: «откуда 5 121,60,
                               если в позициях плана этого нет?»; продолжение 2026-08-17: «где это превышение
                               80 318? где оно?» — см. factExcessReasonItems, считает ОБА источника: перерасход
                               внутри плановых позиций И закупки без действующей плановой привязки/с мёртвой
                               привязкой). Данные (comparisonData[node.id]) грузятся лениво — если панель плана
                               ещё не раскрывали, вместо расшифровки кнопка «Показать, из-за чего», которая сама
                               догружает сравнение (ensureComparison, тот же запрос, что и обычное раскрытие
                               панели) — точечно для ЭТОГО узла, не для всего дерева разом. -->
                          <div v-if="feoResidualNoteFor(node)!.residual < -0.005" style="font-size:11px;white-space:normal;margin-top:2px">
                            <v-btn v-if="!comparisonData[node.id]"
                              size="x-small" variant="text" color="orange-darken-3"
                              :loading="loadingComparison.has(node.id)"
                              @click.stop="ensureComparison(node.id)"
                            >Показать, из-за чего</v-btn>
                            <template v-else-if="factExcessReasonItems(node).length">
                              <span style="color:#B45309">из-за: </span>
                              <template v-for="(it, idx) in factExcessReasonItems(node)" :key="it.key">
                                <span v-if="idx > 0" style="color:#B45309"> · </span>
                                <a v-if="it.purchases.length === 1" href="javascript:void(0)" class="feo-purchase-link"
                                  :title="`Перейти в закупку ${it.purchases[0].label}`"
                                  @click.stop="router.push(`/orders/${it.purchases[0].id}`)"
                                >{{ it.name }} +{{ formatCurrency(it.amount) }}</a>
                                <v-menu v-else location="bottom start">
                                  <template #activator="{ props: excMenuProps }">
                                    <a href="javascript:void(0)" class="feo-purchase-link" v-bind="excMenuProps" @click.stop
                                    >{{ it.name }} +{{ formatCurrency(it.amount) }}</a>
                                  </template>
                                  <v-list density="compact">
                                    <v-list-item v-for="p in it.purchases" :key="p.id" @click="router.push(`/orders/${p.id}`)">
                                      <v-list-item-title>
                                        {{ p.label }} · {{ formatCurrency(p.amount) }}
                                        <span v-if="p.stopped" class="feo-stopped-marker ml-1">остановлена</span>
                                      </v-list-item-title>
                                    </v-list-item>
                                  </v-list>
                                </v-menu>
                              </template>
                              <!-- Сумма расшифровки обязана сходиться с самим числом превышения (владелец,
                                   2026-08-17) — если не сходится (недобор по другим плановым позициям съедает
                                   часть), честно показываем остаток строкой, а не молчим про разницу. -->
                              <span v-if="factExcessReasonRemainder(node) > 0.5" style="color:#B45309">
                                и ещё {{ formatCurrency(factExcessReasonRemainder(node)) }} (гасится недобором по другим плановым позициям — расшифровка не покрывает эту часть один-в-один)
                              </span>
                            </template>
                            <span v-else style="color:#B45309">
                              точную причину разобрать не удалось — {{ formatCurrency(factExcessReasonRemainder(node)) }} без разбивки по позициям
                            </span>
                          </div>
                        </div>
                        <div v-else-if="plannedSumBase === 'all' && feoPlanConsumedNoteFor(node)"
                          class="feo-plan-note text-medium-emphasis"
                          title="План: та же сумма, что и в плановой сумме строки выше. В закупках: сколько из плана уже занято заявками — своими и заявками подкатегорий. Свободно: план минус то, что в закупках — если в закупках больше плана, показано превышение"
                        >
                          план {{ formatCurrency(feoPlanConsumedNoteFor(node)!.planned) }} · в закупках {{ formatCurrency(feoPlanConsumedNoteFor(node)!.consumed) }} ·
                          <span v-if="feoPlanConsumedNoteFor(node)!.residual < -0.005" style="color:#EF4444;font-weight:700">больше плана на {{ formatCurrency(-feoPlanConsumedNoteFor(node)!.residual) }}</span>
                          <span v-else>свободно {{ formatCurrency(feoPlanConsumedNoteFor(node)!.residual) }}</span>
                        </div>
                        <!-- Прогноз «цена выше плановой» — ТОЛЬКО у конечной категории (жалоба
                             владельца 2026-08-13: «вишенкой откуда-то выяснилось, что цена выше
                             плановой и прогноз 1 257 342» — у направления с детьми это план плюс
                             перерасходы детей, число не значит ничего осмысленного). -->
                        <div v-if="!node.hasChildren && feoForecastWarningFor(node)"
                          class="feo-plan-note" style="color:#F97316;font-weight:600"
                          :title="`Если оставшуюся часть купить по нынешней средней цене заказанного, итоговая сумма составит ${formatCurrency(feoForecastWarningFor(node)!.forecast)} — выше плана ${formatCurrency(feoForecastWarningFor(node)!.planManual)}. Не блокирует, только предупреждение`"
                        >
                          если оставшееся купить по нынешней средней цене, выйдет {{ formatCurrency(feoForecastWarningFor(node)!.forecast) }} при плане {{ formatCurrency(feoForecastWarningFor(node)!.planManual) }}
                        </div>
                        <!-- Превышение плана над финансированием ФЭО — требует согласования цепочкой
                             (задача владельца 2026-08-05), см. excessFor()/requestPlanExcessApproval().
                             Детали запроса (шаги, ФИО текущего согласующего, комментарий отказа) —
                             из planExcessApprovals (GET /api/plan-excess?subsidy_id=), см. loadPlanExcessApprovals(). -->
                        <div v-if="excessFor(node)" class="feo-plan-note d-flex align-center flex-wrap ga-1 mt-1">
                          <template v-if="excessApprovalFor(node)?.status === 'pending'">
                            <v-chip size="x-small" color="orange" variant="flat">
                              согласование ПРЕВЫШЕНИЯ ПЛАНА (не закупки) {{ formatCurrency(excessFor(node)!.amount) }} · на согласовании у: {{ excessPendingNames(node) || '—' }}
                            </v-chip>
                            <template v-if="excessMyPendingStep(node) && excessApprovalFor(node)?.can_decide">
                              <v-btn size="x-small" variant="tonal" color="success"
                                :loading="excessDecideLoading === node.id"
                                @click.stop="decidePlanExcess(node, 'approved')"
                              >Одобрить</v-btn>
                              <v-btn size="x-small" variant="tonal" color="error"
                                :loading="excessDecideLoading === node.id"
                                @click.stop="openExcessRejectDialog(node)"
                              >Отклонить</v-btn>
                            </template>
                            <div v-else-if="excessMyPendingStep(node) && !excessApprovalFor(node)?.can_decide" class="feo-plan-note text-medium-emphasis" style="width:100%">
                              Решение по превышению принимают только уполномоченные (владелец/финансист). Обратитесь к ним — согласовывать может не любой назначенный.
                            </div>
                          </template>
                          <template v-else-if="excessApprovalFor(node)?.status === 'approved'">
                            <v-chip size="x-small" color="grey" variant="flat">
                              превышение {{ formatCurrency(excessFor(node)!.amount) }} · согласовано · {{ excessResolvedByName(node) }}{{ excessResolvedDate(node) ? ' · ' + excessResolvedDate(node) : '' }}
                            </v-chip>
                          </template>
                          <template v-else-if="excessApprovalFor(node)?.status === 'rejected'">
                            <v-chip size="x-small" color="red" variant="flat">
                              превышение отклонено{{ excessApprovalFor(node)?.comment ? ': ' + excessApprovalFor(node)!.comment : '' }}
                            </v-chip>
                            <v-btn size="x-small" variant="tonal" color="red"
                              :loading="excessRequestLoading === node.id"
                              @click.stop="requestPlanExcessApproval(node)"
                            >Согласовать</v-btn>
                          </template>
                          <template v-else>
                            <v-chip size="x-small" color="red" variant="flat">
                              превышение {{ formatCurrency(excessFor(node)!.amount) }} — требуется согласование
                            </v-chip>
                            <v-btn size="x-small" variant="tonal" color="red"
                              :loading="excessRequestLoading === node.id"
                              @click.stop="requestPlanExcessApproval(node)"
                            >Согласовать</v-btn>
                          </template>
                        </div>
                        <!-- «Заметный сигнал превышения» (план zany-fluttering-mountain.md, возвращено
                             из отката e0db76a): владелец — «в случае превышения должна отображаться
                             данная закупка и показать, что из-за неё всё превысило». Раньше плашка выше
                             называла ТОЛЬКО сумму — виновник нигде не был виден. Крупно, адресно, с
                             прямой ссылкой на закупку. -->
                        <div v-if="excessCulpritFor(node)" class="feo-excess-culprit">
                          <v-icon size="16" icon="mdi-alert-decagram" class="mr-1" />
                          {{ excessCulpritText(node) }}
                          <v-btn v-if="excessCulpritFor(node)!.purchase_id" size="x-small" variant="flat" color="red"
                            class="ml-1" @click.stop="router.push(`/orders/${excessCulpritFor(node)!.purchase_id}`)"
                          >Открыть закупку</v-btn>
                        </div>

                        <!-- Задача владельца «план ≠ факт» (сессия 2026-08-06, Шаг 5, п.5): ВТОРАЯ,
                             независимая плашка — «итог закупки/КП дороже плана» (excess_fact_over_plan),
                             отдельно от превышения плана над финансированием ФЭО выше. Тот же механизм
                             согласования (см. excessFactFor()/requestPlanExcessApproval()). -->
                        <div v-if="excessFactFor(node)" class="feo-plan-note d-flex align-center flex-wrap ga-1 mt-1">
                          <template v-if="excessApprovalFor(node)?.status === 'pending'">
                            <v-chip size="x-small" color="orange" variant="flat">
                              согласование ПРЕВЫШЕНИЯ: итог закупки дороже плана на {{ formatCurrency(excessFactFor(node)!.amount) }} · на согласовании у: {{ excessPendingNames(node) || '—' }}
                            </v-chip>
                            <template v-if="excessMyPendingStep(node) && excessApprovalFor(node)?.can_decide">
                              <v-btn size="x-small" variant="tonal" color="success"
                                :loading="excessDecideLoading === node.id"
                                @click.stop="decidePlanExcess(node, 'approved')"
                              >Одобрить</v-btn>
                              <v-btn size="x-small" variant="tonal" color="error"
                                :loading="excessDecideLoading === node.id"
                                @click.stop="openExcessRejectDialog(node)"
                              >Отклонить</v-btn>
                            </template>
                            <div v-else-if="excessMyPendingStep(node) && !excessApprovalFor(node)?.can_decide" class="feo-plan-note text-medium-emphasis" style="width:100%">
                              Решение по превышению принимают только уполномоченные (владелец/финансист). Обратитесь к ним — согласовывать может не любой назначенный.
                            </div>
                          </template>
                          <template v-else-if="excessFactFor(node)!.approved">
                            <v-chip size="x-small" color="grey" variant="flat">
                              итог закупки дороже плана на {{ formatCurrency(excessFactFor(node)!.amount) }} · согласовано · {{ excessResolvedByName(node) }}{{ excessResolvedDate(node) ? ' · ' + excessResolvedDate(node) : '' }}
                            </v-chip>
                          </template>
                          <template v-else-if="excessApprovalFor(node)?.status === 'rejected'">
                            <v-chip size="x-small" color="red" variant="flat">
                              превышение факта отклонено{{ excessApprovalFor(node)?.comment ? ': ' + excessApprovalFor(node)!.comment : '' }}
                            </v-chip>
                            <v-btn size="x-small" variant="tonal" color="red"
                              :loading="excessRequestLoading === node.id"
                              @click.stop="requestPlanExcessApproval(node)"
                            >Согласовать</v-btn>
                          </template>
                          <template v-else>
                            <v-chip size="x-small" color="red" variant="flat">
                              итог закупки дороже плана на {{ formatCurrency(excessFactFor(node)!.amount) }} — требуется согласование
                            </v-chip>
                            <v-btn size="x-small" variant="tonal" color="red"
                              :loading="excessRequestLoading === node.id"
                              @click.stop="requestPlanExcessApproval(node)"
                            >Согласовать</v-btn>
                          </template>
                        </div>

                        <!-- Замечание владельца п.2 (2026-08-12): ТРЕТЬЯ, независимая плашка — сумма
                             плановых позиций категории превысила вручную заданный план (excessPlanFor).
                             Тот же механизм согласования — см. excessPlanFor()/requestPlanExcessApproval(). -->
                        <div v-if="excessPlanFor(node)" class="feo-plan-note d-flex align-center flex-wrap ga-1 mt-1">
                          <template v-if="excessApprovalFor(node)?.status === 'pending'">
                            <v-chip size="x-small" color="orange" variant="flat">
                              согласование ПРЕВЫШЕНИЯ: план превышает заданный вручную на {{ formatCurrency(excessPlanFor(node)!.amount) }} (задано {{ formatCurrency(excessPlanFor(node)!.manualEntered) }}, стало {{ formatCurrency(excessPlanFor(node)!.manualEntered + excessPlanFor(node)!.amount) }}) · на согласовании у: {{ excessPendingNames(node) || '—' }}
                            </v-chip>
                            <template v-if="excessMyPendingStep(node) && excessApprovalFor(node)?.can_decide">
                              <v-btn size="x-small" variant="tonal" color="success"
                                :loading="excessDecideLoading === node.id"
                                @click.stop="decidePlanExcess(node, 'approved')"
                              >Одобрить</v-btn>
                              <v-btn size="x-small" variant="tonal" color="error"
                                :loading="excessDecideLoading === node.id"
                                @click.stop="openExcessRejectDialog(node)"
                              >Отклонить</v-btn>
                            </template>
                            <div v-else-if="excessMyPendingStep(node) && !excessApprovalFor(node)?.can_decide" class="feo-plan-note text-medium-emphasis" style="width:100%">
                              Решение по превышению принимают только уполномоченные (владелец/финансист). Обратитесь к ним — согласовывать может не любой назначенный.
                            </div>
                          </template>
                          <template v-else-if="excessApprovalFor(node)?.status === 'rejected'">
                            <v-chip size="x-small" color="red" variant="flat">
                              превышение плана над ручным отклонено{{ excessApprovalFor(node)?.comment ? ': ' + excessApprovalFor(node)!.comment : '' }}
                            </v-chip>
                            <v-btn size="x-small" variant="tonal" color="red"
                              :loading="excessRequestLoading === node.id"
                              @click.stop="requestPlanExcessApproval(node)"
                            >Согласовать</v-btn>
                          </template>
                          <template v-else>
                            <v-chip size="x-small" color="red" variant="flat">
                              план превышает заданный вручную на {{ formatCurrency(excessPlanFor(node)!.amount) }} (задано {{ formatCurrency(excessPlanFor(node)!.manualEntered) }}, стало {{ formatCurrency(excessPlanFor(node)!.manualEntered + excessPlanFor(node)!.amount) }})
                            </v-chip>
                            <v-btn size="x-small" variant="tonal" color="red"
                              :loading="excessRequestLoading === node.id"
                              @click.stop="requestPlanExcessApproval(node)"
                            >Согласовать</v-btn>
                          </template>
                          <!-- План zany-fluttering-mountain.md, п.2: вместо текстовой строки —
                               кликабельные чипы по позициям. Одна связанная закупка → сразу
                               открыть (router.push, тот же приём, что и у excessCulpritFor
                               выше/virtCart); несколько — v-menu со списком «номер · статус ·
                               сумма», остановленные помечены; закупок нет — чип без действия,
                               с подсказкой почему (см. excessPlanItemPurchaseTitle). -->
                          <div v-if="excessPlanFor(node)!.items.length" class="d-flex align-center flex-wrap ga-1 mt-1" style="width:100%">
                            <span style="font-size:11px;color:#B45309">Позиции-виновники:</span>
                            <template v-for="item in excessPlanFor(node)!.items" :key="item.id">
                              <span v-if="!item.purchases.length" class="feo-purchase-link" style="cursor:default;opacity:0.7"
                                :title="`«${item.name}» (${formatCurrency(item.amount)}) — нет связанной закупки: позиция ещё не попала ни в одну закупку`"
                              >{{ item.name }} ({{ formatCurrency(item.amount) }})</span>
                              <a v-else-if="item.purchases.length === 1" href="javascript:void(0)" class="feo-purchase-link"
                                @click.stop="router.push(`/orders/${item.purchases[0].id}`)"
                              >{{ item.name }} ({{ formatCurrency(item.amount) }})</a>
                              <v-menu v-else location="bottom start">
                                <template #activator="{ props: purchMenuProps }">
                                  <a href="javascript:void(0)" class="feo-purchase-link" v-bind="purchMenuProps" @click.stop
                                  >{{ item.name }} ({{ formatCurrency(item.amount) }})</a>
                                </template>
                                <v-list density="compact">
                                  <v-list-item v-for="p in item.purchases" :key="p.id" @click="router.push(`/orders/${p.id}`)">
                                    <v-list-item-title>
                                      {{ excessPlanItemPurchaseTitle(p) }}
                                      <span v-if="p.stopped_at" class="feo-stopped-marker ml-1">остановлена</span>
                                    </v-list-item-title>
                                  </v-list-item>
                                </v-list>
                              </v-menu>
                            </template>
                          </div>
                        </div>

                        <!-- Замечание владельца п.4: «если согласовали превышение — так и остаётся,
                             надо чтобы висело предупреждение, что согласовали» — постоянная спокойная
                             пометка, НЕ зависит от того, активно ли превышение прямо сейчас. План
                             zany-fluttering-mountain.md, п.3: дополнено «план был X → стал Y» из
                             excess_approval_plan_before/after (может отсутствовать у старых запросов). -->
                        <div v-if="excessPlanApprovalPermanent(node)" class="feo-plan-note mt-1">
                          <v-chip size="x-small" color="grey" variant="tonal" prepend-icon="mdi-check-decagram">
                            превышение согласовано: {{ formatCurrency(excessPlanApprovalPermanent(node)!.amount) }}{{ excessPlanApprovalPermanent(node)!.at ? ', ' + excessPlanApprovalPermanent(node)!.at : '' }}, {{ excessPlanApprovalPermanent(node)!.by }}<template v-if="excessPlanApprovalPermanent(node)!.planBefore != null && excessPlanApprovalPermanent(node)!.planAfter != null"> · план был {{ formatCurrency(excessPlanApprovalPermanent(node)!.planBefore!) }} → стал {{ formatCurrency(excessPlanApprovalPermanent(node)!.planAfter!) }}</template>
                          </v-chip>
                        </div>

                        <!-- Замечание владельца п.3: «Приравнять ФЭО к плану» — только org_admin и выше
                             (canSaveVersion — переиспользован без изменений, см. её объявление ниже). -->
                        <div v-if="canSaveVersion" class="mt-1">
                          <v-btn size="x-small" variant="text" color="blue-grey" prepend-icon="mdi-equal"
                            title="Установить финансирование по ФЭО этой категории равным её полной плановой сумме"
                            @click.stop="openAlignBudgetConfirm(node)"
                          >Приравнять ФЭО к плану</v-btn>
                        </div>
                      </td>

                      <!-- «В плане-графике» — решение владельца 2026-08-18 (жалоба на категории 3710:
                           строка дерева показывала три несводимые шкалы одновременно — план 351 844,
                           «фактическая» 54 318 (договорный факт), остаток 351 844 (плюс ещё заметка ниже
                           «в закупках 432 162»). Владелец потребовал «фактическая должна получаться
                           432 162» — свели колонку к той же шкале, что и заметка «в закупках» под
                           «Плановой суммой» (feoInPlanScheduleFor — сумма всех статусов плана закупок,
                           второй источник не изобретаем). feoFactFor (plan_tree.fact, договорный факт
                           work_in_progress…paid) НЕ удалён и не изменён — остался подписью «по договору»
                           ниже и по-прежнему единственный источник плашки превышения факта. -->
                      <td class="feo-td feo-td-num" style="vertical-align:top">
                        <span :class="feoInPlanScheduleFor(node) > 0 ? 'feo-amount feo-amount--link' : 'feo-amount-empty'"
                          :style="(feoDisplayedFor(node) > 0 && feoInPlanScheduleFor(node) > feoDisplayedFor(node)) || (feoPlannedDisplayFor(node) > 0 && feoInPlanScheduleFor(node) > feoPlannedDisplayFor(node)) ? 'color:#EF4444;font-weight:700' : ''"
                          :title="feoInPlanScheduleFor(node) > 0 ? 'Открыть закупки по этой категории' : ''"
                          @click="feoInPlanScheduleFor(node) > 0 && router.push(`/orders?feo_category_id=${node.id}`)"
                        >
                          {{ feoInPlanScheduleFor(node) > 0 ? formatCurrency(feoInPlanScheduleFor(node)) : '—' }}
                        </span>
                        <!-- Договорный факт — подпись, не отдельная метрика (правило «одна подпись = одна
                             метрика»): показываем только когда он есть и реально отличается от «в плане-графике». -->
                        <div v-if="feoFactFor(node) > 0 && Math.abs(feoInPlanScheduleFor(node) - feoFactFor(node)) > 0.005"
                          class="feo-plan-note text-medium-emphasis"
                          :title="`Из них уже есть договорная цена (договор/акт). Остальное — закупки, которые ещё в статусе «План закупок»`"
                        >
                          по договору {{ formatCurrency(feoFactFor(node)) }}
                        </div>
                      </td>

                      <!-- Остаток = (Плановая сумма | Финансирование по ФЭО) − В плане-графике.
                           Решение владельца 2026-08-18: та же шкала, что и колонка «В плане-графике»
                           и заметка «в закупках» — см. feoResidualFor/feoInPlanScheduleFor. -->
                      <td class="feo-td feo-td-num" style="vertical-align:top">
                        <span v-if="feoResidualBaseFor(node) > 0 || feoInPlanScheduleFor(node) > 0"
                          class="feo-amount"
                          :style="feoResidualFor(node) < -0.005 ? 'color:#EF4444;font-weight:700' : 'color:#16A34A'"
                          :title="`${residualBase === 'feo' ? 'ФЭО' : 'План'} ${formatCurrency(feoResidualBaseFor(node))} − В плане-графике ${formatCurrency(feoInPlanScheduleFor(node))}`"
                        >
                          {{ feoResidualFor(node) < 0 ? '−' : '' }}{{ formatCurrency(Math.abs(feoResidualFor(node))) }}
                        </span>
                        <span v-else class="feo-amount-empty">—</span>
                      </td>

                      <!-- Действия -->
                      <td class="feo-td feo-td-actions">
                        <div class="feo-actions-wrap">
                          <!-- Level 3: кнопка раскрытия позиций / spacer for alignment.
                               Задача владельца «направление со временем может наполниться»
                               (2026-08-12): у направления (node.hasChildren) кнопка тоже
                               появляется, но ТОЛЬКО если у него есть СОБСТВЕННЫЕ плановые
                               позиции (hasOwnPlannedAmountFor) — иначе раскрывать нечего,
                               ничего не меняется для обычных направлений без своего плана. -->
                          <span class="feo-action-slot"><v-btn v-if="!node.hasChildren || hasOwnPlannedAmountFor(node)"
                            :icon="expandedItemPanels.has(node.id) ? 'mdi-list-box' : 'mdi-list-box-outline'"
                            variant="text" size="x-small"
                            :color="expandedItemPanels.has(node.id) ? 'teal' : 'grey'"
                            :title="node.hasChildren ? 'Состав плана: позиции, привязанные к самому направлению (не к его подкатегориям)' : 'Показать плановые / фактические позиции'"
                            @click="toggleItemPanel(node)"
                          /></span>
                          <!-- Стрелки — друг под другом (B5: скрыты без feo_category.edit) -->
                          <div v-if="canEditFeo" class="feo-actions-col">
                            <v-btn icon="mdi-chevron-up" variant="text" size="x-small" color="grey-darken-1"
                              title="Переместить выше" @click.stop="reorderFeoNode(node, 'up')" />
                            <v-btn icon="mdi-chevron-down" variant="text" size="x-small" color="grey-darken-1"
                              title="Переместить ниже" @click.stop="reorderFeoNode(node, 'down')" />
                          </div>
                          <!-- Значки: добавить/редактировать/удалить скрыты без feo_category.edit;
                               «показать закупки» — чтение, остаётся всегда -->
                          <div class="feo-actions-grid">
                            <v-btn v-if="canEditFeo" icon="mdi-plus-circle-outline" variant="text" size="x-small" color="success"
                              title="Добавить дочернюю" @click="feoForm.parentId = node.id; showAddFeoDialog = true" />
                            <v-btn icon="mdi-cart-outline" variant="text" size="x-small" color="blue"
                              title="Показать закупки по этой категории"
                              @click.stop="router.push(`/orders?feo_category_id=${node.id}`)" />
                            <v-btn v-if="canEditFeo" icon="mdi-pencil-outline" variant="text" size="x-small" color="primary"
                              title="Редактировать" @click="startFeoEdit(node)" />
                            <v-btn v-if="canEditFeo" icon="mdi-delete-outline" variant="text" size="x-small" color="error"
                              title="Удалить" @click="confirmFeoDelete(node)" />
                          </div>
                        </div>
                      </td>
                    </tr>

                    <!-- ── Level 5 панель: Плановые vs Фактические ──
                         Условие расширено (!node.hasChildren || hasOwnPlannedAmountFor(node)) —
                         см. комментарий у hasOwnPlannedAmountFor выше: у направления панель
                         раскрывается, только если есть чем её наполнить. -->
                    <tr v-if="(!node.hasChildren || hasOwnPlannedAmountFor(node)) && expandedItemPanels.has(node.id)" :key="`items-${node.id}`" :data-feo-panel-for="node.id">
                      <!-- Правка владельца (2026-08-12): отступ 0 0 0 60px убран — он сдвигал ВСЮ
                           вложенную таблицу плановых позиций вправо и ломал вертикальное выравнивание
                           её колонок с колонками основной таблицы (feo-table). Визуальная вложенность
                           теперь только padding-left ВНУТРИ первой ячейки «Позиция плана» ниже.
                           colspan="7" (было 6) — вложенная таблица теперь имеет ту же раскладку из
                           7 колонок, что и основная (см. feoResize выше); чтобы её auto-колонки делили
                           РОВНО ТУ ЖЕ полную ширину контейнера, что и основная таблица, ячейка обязана
                           захватывать ВСЕ 7 колонок основной строки, а не 6. -->
                      <td colspan="7" style="padding:0">
                        <!-- padding-left:0 (было 12px) — тот же замер в браузере показал, что этот
                             левый паддинг сдвигал ВСЮ вложенную таблицу плановых позиций на 12px
                             вправо от колонок основной таблицы feo-table.
                             padding-right:0 (было 12px, правка 2026-08-12) — тот же принцип: правый
                             паддинг урезал ширину вложенной таблицы на 12px относительно основной,
                             из-за чего table-layout:fixed делил остаток на 3px меньше на каждую
                             auto-колонку и budget/qty/planned чуть съезжали влево от одноимённых
                             колонок основной таблицы. Только top/bottom оставлены. -->
                        <div style="padding:10px 0 12px 0">
                          <!-- Требование владельца (план zany-fluttering-mountain.md, возвращено из отката
                               e0db76a): при раскрытии категории СРАЗУ видны её плановые позиции — БЕЗ
                               промежуточного заголовка-обёртки «Позиции: план vs факт», это уже просто
                               продолжение дерева. Кнопка добавления плановой позиции осталась, без title. -->
                          <div class="d-flex align-center mb-2" style="gap:8px">
                            <!-- Замечание владельца 1 (2026-08-12): «по одной сворачивать неудобно,
                                 надо развернуть все сразу, посмотреть, как что покупалось, и свернуть
                                 все сразу» — переключатель раскрытия «План vs факт» у ВСЕХ плановых
                                 позиций именно этой категории, см. toggleAllPlannedItemsForCategory. -->
                            <v-btn v-if="displayPlannedRowsFor(node).length > 1" size="x-small" variant="text" color="teal"
                              :prepend-icon="anyPlannedExpandedFor(node) ? 'mdi-arrow-collapse-vertical' : 'mdi-arrow-expand-vertical'"
                              @click="toggleAllPlannedItemsForCategory(node)"
                            >{{ anyPlannedExpandedFor(node) ? 'Свернуть всё' : 'Развернуть всё' }}</v-btn>
                            <v-spacer />
                            <v-btn size="x-small" variant="tonal" color="teal" prepend-icon="mdi-plus"
                              @click="openAddPlannedItem(node.id)">
                              Добавить плановую
                            </v-btn>
                          </div>

                          <!-- Спиннер загрузки -->
                          <div v-if="loadingComparison.has(node.id)" class="d-flex align-center" style="gap:8px;padding:8px 0">
                            <v-progress-circular indeterminate size="16" color="teal" />
                            <span class="text-caption">Загрузка...</span>
                          </div>

                          <!-- Таблица сравнения -->
                          <!-- table-layout:fixed (правка 2026-08-12, вместе с откатом фиксированных 180px
                               выше): без него браузер считает ширину auto-колонок ПО СОДЕРЖИМОМУ (обычный
                               table-layout:auto), а не делит остаток поровну как в основной .feo-table
                               (там table-layout:fixed задан классом). Из-за этого «Позиция плана» (длинный
                               текст) раздувалась на сотни px, а budget/qty/planned вообще не совпадали с
                               основной таблицей, несмотря на одинаковые resizeStyle(key). -->
                          <table v-else-if="comparisonData[node.id]" style="width:100%;table-layout:fixed;border-collapse:collapse;font-size:12px">
                            <thead>
                              <!-- Требование владельца (2026-08-12): в рамках одной плановой позиции может быть
                                   несколько разных закупок — одна строка на уровне плана физически не может
                                   описать факт по всем сразу (либо врёт, либо пустует). Поэтому фактические
                                   колонки убраны с ЭТОГО уровня целиком: тут только план (синий), весь факт —
                                   уровнем ниже, в раскрывающемся блоке «План vs факт» под каждой плановой
                                   позицией (см. ниже, вёрстка не тронута). Строка-группировка «ПОЗИЦИИ ПЛАНА» /
                                   «ПЛАН VS ФАКТ» убрана — делить больше нечего, вся таблица теперь про план. -->
                              <!-- Правка владельца (2026-08-12): колонки этой (вложенной) таблицы выровнены
                                   ПОД одноимёнными колонками ОСНОВНОЙ таблицы дерева ФЭО (feo-table) — тем же
                                   feoResize.resizeStyle(key), тот же порядок ключей: name → budget → qty → planned.
                                   «Цена плана» стоит под budget («Количество и финансирование по ФЭО» — там тоже
                                   деньги), поэтому она ЛЕВЕЕ «Кол-во плана» (qty) — так требует вертикальное
                                   выравнивание, не смысловой порядок колонок.
                                   Правка владельца (2026-08-12, откат фиксированных 180px): чтобы авто-колонки
                                   (name/qty/planned/residual, ширина 0 = делят остаток) делили ОДИНАКОВЫЙ
                                   остаток в обеих таблицах, у вложенной таблицы теперь РОВНО ТЕ ЖЕ 7 колонок,
                                   что у основной — добавлены пустые spent/residual (те же ключи, те же
                                   fixed/auto свойства), а колонка кнопок зафиксирована в 112px — как
                                   .feo-th-actions у основной (там тоже fixed, не auto). Иначе набор и число
                                   auto-колонок в двух таблицах отличались бы, и остаток делился бы по-разному. -->
                              <!-- Замечание владельца 3 (2026-08-12): «слишком сливающиеся подложки» —
                                   фон шапки/строк убран (белый), синий остался только в тексте заголовков
                                   и тонкой нижней границе шапки. -->
                              <tr>
                                <th :style="[feoResize.resizeStyle('name'), { paddingLeft: `${plannedItemIndentPx(node)}px` }]" style="padding-top:4px;padding-right:8px;padding-bottom:4px;text-align:left;color:#1e40af;font-weight:600;border-bottom:1px solid #BFDBFE" title="Плановая позиция. Закупки, привязанные к ней (как выставили в закупку / как в договоре — по стадии), — в раскрывающемся блоке под строкой плана.">
                                  Позиция плана
                                </th>
                                <th :style="feoResize.resizeStyle('budget')" style="padding:4px 8px;text-align:right;color:#1e40af;font-weight:600;border-bottom:1px solid #BFDBFE">Плановая цена за единицу</th>
                                <th :style="feoResize.resizeStyle('qty')" style="padding:4px 8px;text-align:right;color:#1e40af;font-weight:600;border-bottom:1px solid #BFDBFE">Кол-во плана</th>
                                <th :style="feoResize.resizeStyle('planned')" style="padding:4px 8px;text-align:right;color:#1e40af;font-weight:600;border-bottom:1px solid #BFDBFE">Сумма плана</th>
                                <!-- «Тип» (блок 1, план zany-fluttering-mountain.md, 2026-08-14): товар/услуга/
                                     работа плановой позиции. Колонка ДОПОЛНИТЕЛЬНАЯ, фиксированной ширины (не
                                     через feoResize) — сознательно нарушает описанный выше «ровно те же 7
                                     колонок» подсчёт остатка совместно с основной таблицей; смирились с этим
                                     ради нового признака, вертикальное совпадение auto-колонок левее (name/
                                     budget/qty/planned) не страдает. -->
                                <th style="width:74px;min-width:74px;padding:4px 8px;text-align:center;color:#1e40af;font-weight:600;border-bottom:1px solid #BFDBFE">Тип</th>
                                <th :style="feoResize.resizeStyle('spent')" style="border-bottom:1px solid #BFDBFE"></th>
                                <th :style="feoResize.resizeStyle('residual')" style="border-bottom:1px solid #BFDBFE"></th>
                                <th style="width:112px;min-width:112px;max-width:112px;padding:4px 2px;border-bottom:1px solid #BFDBFE"></th>
                              </tr>
                            </thead>
                            <tbody>
                              <!-- Плановые позиции Ур.5: строка плана свёрнута по умолчанию, шеврон + чип
                                   «заявок: N на сумму M» раскрывают привязанные позиции заявок ВНУТРИ неё
                                   (feo_planned_item_id = planned.id) — переиспользует вёрстку строки позиции
                                   заявки (аватар/ссылка на закупку/снять сопоставление), но с увеличенным
                                   левым отступом первой ячейки, чтобы визуально вложить её под план.
                                   Источник строк — displayPlannedRowsFor(node): реальные FeoPlannedItem,
                                   ИЛИ (если их нет) одна синтетическая «ручной план ФЭО» с id = -node.id —
                                   единая иерархия ШАГ 1 (2026-08-07), псевдо-строка была отдельным блоком
                                   ниже, теперь та же вёрстка, что и у реальной плановой позиции. -->
                              <template v-for="(planned, pIdx) in displayPlannedRowsFor(node)" :key="`p-${planned.id}`">
                                <tr style="border-bottom:1px solid #E5E7EB">
                                  <td :style="[feoResize.resizeStyle('name'), { paddingLeft: `${plannedItemIndentPx(node)}px` }]" style="padding-top:4px;padding-right:8px;padding-bottom:4px;color:#0c4a6e">
                                    <div class="d-flex align-center" style="gap:2px">
                                      <!-- Правка владельца (жалоба по скриншоту): раскрытие теперь доступно ВСЕГДА —
                                           даже без единой привязанной закупки, чтобы блок «План vs факт» не пропадал
                                           бесследно и не вводил в заблуждение. Раньше (2026-08-10) шеврон скрывался
                                           при пустом factForPlanned; теперь пустой случай рисует заглушку внутри. -->
                                      <v-btn
                                        :icon="expandedPlannedItems.has(planned.id) ? 'mdi-chevron-down' : 'mdi-chevron-right'"
                                        variant="text" density="compact" size="x-small" color="teal"
                                        title="Показать/скрыть закупки, привязанные к этой плановой позиции"
                                        @click="togglePlannedItemFolder(planned.id)"
                                      />
                                      <span>{{ planned.name }}</span>
                                      <v-chip size="x-small" color="blue-grey" variant="tonal" class="ml-1" style="font-size:9px;height:16px"
                                        title="Это плановая позиция — она запланирована, а не выставлена в закупку и не приехала по факту"
                                      >план</v-chip>
                                      <!-- Спокойная пометка владельца (2026-08-12, повод — «Бинт марлевый» на
                                           «Окружных»): панель сейчас открыта для направления (node.hasChildren) —
                                           ЛЮБАЯ плановая позиция в ней по построению привязана ПРЯМО к нему
                                           (comparisonData грузится по feo_category_id=node.id, без детей),
                                           а не к какой-то из его конечных категорий. Не тревожный красный —
                                           нейтральный серый, суммы при переносе вниз не меняются. -->
                                      <v-chip v-if="node.hasChildren" size="x-small" color="grey" variant="tonal" class="ml-1" style="font-size:9px;height:16px"
                                        title="Позиция привязана к направлению, а не к конечной категории. Её можно перенести вниз, в подходящую категорию — суммы при этом не изменятся."
                                      >на направлении целиком</v-chip>
                                      <!-- Происхождение (владелец, 2026-09-01) — компактные пометки, не мешающие
                                           читать строку: жёсткая разбивка ФЭО против внутреннего плана (см.
                                           докстринг is_feo_breakdown/is_internal_plan в feo_planned_item.py). Обе
                                           могут стоять одновременно — независимые галочки, не переключатель. -->
                                      <v-chip v-if="!planned.isManual && planned.is_feo_breakdown" size="x-small" color="green" variant="tonal" class="ml-1" style="font-size:9px;height:16px"
                                        title="По ФЭО — жёсткая построчная разбивка ФЭО, покупать будут именно это, отчётность строгая"
                                      >по ФЭО</v-chip>
                                      <v-chip v-if="!planned.isManual && planned.is_internal_plan" size="x-small" color="amber-darken-3" variant="tonal" class="ml-1" style="font-size:9px;height:16px"
                                        title="Внутренний план — в ФЭО была более широкая категория (или позиции не было вовсе), состав определили сами"
                                      >внутренний план</v-chip>
                                    </div>
                                    <div v-if="planned.isManual" class="feo-plan-note text-medium-emphasis">
                                      <v-icon icon="mdi-pencil-ruler" size="11" class="mr-1" />ручной план ФЭО — подробного деления в ФЭО не было
                                    </div>
                                    <!-- Разбор плана (требование владельца 2026-08-09): сколько уже разобрано
                                         этой плановой позиции — и в штуках, и в деньгах, остаток тем же образом.
                                         Штуки — только если у плана вообще задано количество (planned.quantity),
                                         иначе у плана нет множителя количества и писать «из N шт» нечего. -->
                                    <div v-if="planned.amount != null" class="text-medium-emphasis" style="font-size:10px;line-height:1.3;white-space:normal">
                                      {{ planBreakdownText(node.id, planned) }}
                                    </div>
                                  </td>
                                  <!-- Правка владельца (2026-08-12): «Цена плана» — под колонкой budget
                                       («Количество и финансирование по ФЭО») основной таблицы, поэтому она
                                       ЛЕВЕЕ «Кол-во плана» (qty) ниже — порядок задан выравниванием колонок. -->
                                  <td :style="feoResize.resizeStyle('budget')" style="padding:4px 8px;text-align:right;color:#64748b">
                                    <span v-if="planned.amount && Number(planned.quantity) > 0">{{ formatCurrency(Number(planned.amount) / Number(planned.quantity)) }}</span>
                                  </td>
                                  <td :style="feoResize.resizeStyle('qty')" style="padding:4px 8px;text-align:right;color:#64748b">
                                    <span v-if="planned.quantity">{{ parseFloat(String(planned.quantity)) }} {{ planned.unit || '' }}</span>
                                  </td>
                                  <td :style="feoResize.resizeStyle('planned')" style="padding:4px 8px;text-align:right;color:#64748b">
                                    <span v-if="planned.amount">{{ formatCurrency(planned.amount) }}</span>
                                  </td>
                                  <td style="width:74px;min-width:74px;padding:4px 8px;text-align:center;color:#64748b">
                                    <span
                                      v-if="planned.item_type_inherited"
                                      class="text-medium-emphasis"
                                      title="Тип взят из позиций закупок — у самой плановой позиции он не задан"
                                    >{{ planned.item_type_effective }}</span>
                                    <span v-else>{{ planned.item_type_effective || '—' }}</span>
                                  </td>
                                  <!-- spent/residual — пустые заглушки, только чтобы раскладка колонок совпадала
                                       со основной таблицей (см. правку выше у feoResize/th этой таблицы). -->
                                  <td :style="feoResize.resizeStyle('spent')"></td>
                                  <td :style="feoResize.resizeStyle('residual')"></td>
                                  <!-- Требование владельца (2026-08-12): факт (colspan-заглушка, «Разница»,
                                       «Контрагент», «Статус» — factForPlanned/calcDiff/getDiffStyle/isFactActual)
                                       убран с уровня строки плановой позиции целиком — одна строка не может
                                       описать несколько разных закупок под одной плановой позицией; весь факт
                                       теперь только в раскрывающемся блоке ниже (шеврон слева от названия).
                                       Кнопка «План vs факт» (жалоба владельца 2026-08-12 — раскрытие было не
                                       видно, только маленький шеврон у названия) дублирует togglePlannedItemFolder
                                       текстовой ссылкой; видна на КАЖДОЙ строке, включая синтетическую
                                       (planned.isManual), поэтому вынесена ИЗ ветки v-if/v-else ниже.
                                       width:112px — как у .feo-th-actions основной таблицы (fixed, не auto),
                                       чтобы остаток между auto-колонками делился одинаково в обеих таблицах. -->
                                  <td style="width:112px;min-width:112px;max-width:112px;padding:2px;text-align:center">
                                    <div class="d-flex align-center flex-wrap justify-center" style="gap:0">
                                      <!-- Замечание владельца 2 (2026-08-12): «должна быть возможность менять
                                           плановые позиции местами внутри категории» — те же стрелки, что уже
                                           есть у категорий ФЭО в дереве (reorderFeoNode), только для плановых
                                           позиций (reorderPlannedItem, PUT /feo-planned-items/{id} с sort_order).
                                           Не показываются у синтетической строки (planned.isManual) — она одна
                                           и переставлять её не с чем (displayPlannedRowsFor никогда не мешает
                                           ручную строку с реальными). -->
                                      <template v-if="!planned.isManual">
                                        <v-btn icon="mdi-chevron-up" variant="text" size="x-small" color="grey-darken-1"
                                          :disabled="pIdx === 0"
                                          :loading="reorderingPlannedItemId === planned.id"
                                          title="Переместить выше"
                                          @click.stop="reorderPlannedItem(node, pIdx, 'up')"
                                        />
                                        <v-btn icon="mdi-chevron-down" variant="text" size="x-small" color="grey-darken-1"
                                          :disabled="pIdx === displayPlannedRowsFor(node).length - 1"
                                          :loading="reorderingPlannedItemId === planned.id"
                                          title="Переместить ниже"
                                          @click.stop="reorderPlannedItem(node, pIdx, 'down')"
                                        />
                                      </template>
                                    </div>
                                    <v-btn
                                      size="x-small" variant="text" color="teal" class="text-none"
                                      :prepend-icon="expandedPlannedItems.has(planned.id) ? 'mdi-chevron-down' : 'mdi-chevron-right'"
                                      title="Показать/скрыть закупки, привязанные к этой плановой позиции"
                                      @click="togglePlannedItemFolder(planned.id)"
                                    >План vs факт</v-btn>
                                    <template v-if="!planned.isManual">
                                      <!-- Требование владельца, п.2/п.3 (2026-08-12): позицию, висящую прямо на
                                           направлении («на направлении целиком», см. чип выше), можно перенести
                                           вниз, в подходящую конечную категорию — суммы при этом не меняются
                                           (перенос просто меняет feo_category_id, деньги как считались в плане
                                           направления, так и продолжат считаться, просто уже на новом узле).
                                           Кнопка видна ТОЛЬКО в панели направления (node.hasChildren) — у обычной
                                           конечной категории переносить пока некуда конкретным местом, ничего не
                                           меняем в её поведении. -->
                                      <v-menu v-if="node.hasChildren" location="bottom end">
                                        <template #activator="{ props: moveMenuProps }">
                                          <v-btn v-bind="moveMenuProps" icon="mdi-arrow-down-bold-box-outline"
                                            size="x-small" variant="text" color="orange-darken-1"
                                            :loading="movingPlannedItemId === planned.id"
                                            title="Перенести позицию вниз, в подходящую конечную категорию — суммы не изменятся"
                                          />
                                        </template>
                                        <v-list density="compact" max-height="320" style="overflow-y:auto">
                                          <v-list-subheader>Перенести в категорию</v-list-subheader>
                                          <v-list-item v-for="d in descendantCategoriesFor(node)" :key="d.id"
                                            :title="d.name"
                                            :style="{ paddingLeft: `${8 + (d.depth - node.depth - 1) * 16}px` }"
                                            @click="movePlannedItemToCategory(planned, d.id)"
                                          />
                                        </v-list>
                                      </v-menu>
                                      <v-btn icon="mdi-pencil" size="x-small" variant="text" color="blue"
                                        title="Редактировать плановую позицию"
                                        @click="openEditPlannedItem(planned)"
                                      />
                                      <v-btn icon="mdi-delete-outline" size="x-small" variant="text" color="error"
                                        title="Удалить плановую позицию"
                                        :loading="deletingPlannedItemId === planned.id"
                                        @click="deletePlannedItem(planned)"
                                      />
                                    </template>
                                    <template v-else>
                                      <v-btn icon="mdi-pencil" size="x-small" variant="text" color="blue"
                                        title="Редактировать план категории — количество, цена за единицу, единица измерения"
                                        @click="openEditCategoryPlan(node)"
                                      />
                                      <v-btn icon="mdi-playlist-plus" size="x-small" variant="text" color="teal"
                                        title="Завести плановую позицию — именованный товар/услуга вместо строки категории; количество и цена берутся из плана листа, факты привяжутся к ней автоматически"
                                        @click="openConvertManualPlanToItem(node)"
                                      />
                                    </template>
                                  </td>
                                </tr>
                                <!-- Раскрывающийся блок плановой позиции: под одной плановой позицией может
                                     висеть несколько закупок («покупаю по одной машине в каждой закупке»).
                                     Правка владельца (жалоба по скриншоту): раскрытие теперь доступно ВСЕГДА,
                                     даже без единой закупки — иначе блок «План vs факт» пропадал бесследно и
                                     вводил в заблуждение (было видно только у позиций С закупками). Пустой
                                     случай рисует ту же шапку и одну строку-заглушку вместо строк actual —
                                     фактические ячейки НЕ заполняются плановыми числами (правка 2026-08-10
                                     остаётся в силе, тут просто видимость блока, не логика чисел). Своя
                                     вложенная таблица со своей шапкой (см. factStageHeaderFor/leftGroupInfo) —
                                     ровно одна стадия, если все закупки позиции на ней, иначе нейтральный
                                     заголовок и стадия подписана на каждой строке (пометка «как выставили»/
                                     «как в договоре» уже есть на строке). -->
                                <tr v-if="expandedPlannedItems.has(planned.id)">
                                  <!-- colspan="8" (было 7, до колонки «Тип» — 5) — у вложенной таблицы плановых
                                       позиций теперь 8 колонок (добавлены пустые spent/residual + «Тип», см.
                                       выше), эта ячейка должна закрывать всю строку целиком, а не оставлять
                                       колонки «дыркой» справа. -->
                                  <!-- Замечание владельца 3+4 (2026-08-12): вложенный блок «План vs факт» —
                                       собственная светло-серая заливка + рамка + заметный отступ сверху/слева
                                       (визуальная вложенность внутрь плановой позиции), ЧТОБЫ читался как
                                       отдельная от плана сущность. table-layout:fixed добавлен на ВНУТРЕННЮЮ
                                       таблицу (у неё его не было — вот почему в МИНПРОСе блок садился по
                                       ширине содержимого вместо 100% строки, см. разбор в отчёте задачи;
                                       у обёртки-td теперь padding:0, вся раскладка — во внутреннем div). -->
                                  <td colspan="8" style="padding:0">
                                    <div style="margin:10px 8px 12px 32px;padding:8px;background:#F8FAFC;border:1px solid #E2E8F0;border-radius:6px">
                                    <table style="width:100%;table-layout:fixed;border-collapse:collapse;font-size:12px">
                                      <thead>
                                        <!-- Замечание владельца 5 (2026-08-12): порядок «цена → количество → сумма»,
                                             как в «Позициях плана» — было «кол-во → цена», переставлено местами
                                             в ОБЕИХ группах (план-сторона и факт-сторона). Подписи не менялись. -->
                                        <tr>
                                          <th style="padding:4px 8px;text-align:left;color:#0f766e;font-weight:600;border-bottom:1px solid #99F6E4" :title="factStageHeaderFor(node.id, planned.id) === 'Позиция закупки' ? 'Закупки этой плановой позиции сейчас на разных стадиях — стадия каждой подписана на её строке' : ''">
                                            {{ factStageHeaderFor(node.id, planned.id) }}
                                          </th>
                                          <th style="padding:4px 8px;text-align:right;color:#0f766e;font-weight:600;border-bottom:1px solid #99F6E4;width:90px">Цена</th>
                                          <th style="padding:4px 8px;text-align:right;color:#0f766e;font-weight:600;border-bottom:1px solid #99F6E4;width:90px">Кол-во</th>
                                          <th style="padding:4px 8px;text-align:right;color:#0f766e;font-weight:600;border-bottom:1px solid #99F6E4;width:110px">Сумма</th>
                                          <th style="padding:4px 8px;text-align:left;color:#0f766e;font-weight:600;border-bottom:1px solid #99F6E4" title="Реальные закупки, привязанные к этой плановой позиции — что действительно куплено или заказано">ФАКТ (из закупок)</th>
                                          <th style="padding:4px 8px;text-align:right;color:#0f766e;font-weight:600;border-bottom:1px solid #99F6E4;width:90px">Цена (факт)</th>
                                          <th style="padding:4px 8px;text-align:right;color:#0f766e;font-weight:600;border-bottom:1px solid #99F6E4;width:90px">Кол-во (факт)</th>
                                          <th style="padding:4px 8px;text-align:right;color:#0f766e;font-weight:600;border-bottom:1px solid #99F6E4;width:110px">Сумма (факт)</th>
                                          <th style="padding:4px 8px;text-align:right;color:#0f766e;font-weight:600;border-bottom:1px solid #99F6E4;width:100px">Разница</th>
                                          <th style="padding:4px 8px;text-align:left;color:#0f766e;font-weight:600;border-bottom:1px solid #99F6E4;width:120px">Контрагент</th>
                                          <th style="padding:4px 8px;text-align:center;color:#0f766e;font-weight:600;border-bottom:1px solid #99F6E4;width:80px">Статус</th>
                                          <th style="padding:4px 2px;width:80px;border-bottom:1px solid #99F6E4"></th>
                                        </tr>
                                      </thead>
                                      <tbody>
                                        <tr v-if="!factForPlanned(node.id, planned.id).length">
                                          <td colspan="12" style="padding:8px 8px;color:#94a3b8;font-style:italic">Закупок по этой плановой позиции пока нет</td>
                                        </tr>
                                        <template v-for="actual in factForPlanned(node.id, planned.id)" :key="`pa-${actual.purchase_item_id}`">
                                        <tr
                                          :class="kpiItemRowClass(actual)"
                                          :data-item-id="actual.purchase_item_id" data-item-group="planned"
                                          style="border-bottom:1px solid #E2E8F0">
                                          <td style="padding:4px 8px;color:#0c4a6e">
                                            {{ leftGroupInfo(actual).name }}
                                            <v-chip size="x-small" :color="stageChipColorFor(actual.purchase_status)" variant="tonal" class="ml-1" style="font-size:9px;height:16px"
                                              :title="stageChipTitleFor(actual.purchase_status)"
                                            >{{ stageChipLabelFor(actual.purchase_status) }}</v-chip>
                                          </td>
                                          <td style="padding:4px 8px;text-align:right;color:#64748b">{{ leftGroupInfo(actual).unitPrice != null ? formatCurrency(leftGroupInfo(actual).unitPrice!) : '—' }}</td>
                                          <td style="padding:4px 8px;text-align:right;color:#64748b">{{ leftGroupInfo(actual).quantity != null ? `${parseFloat(String(leftGroupInfo(actual).quantity))} ${leftGroupInfo(actual).unit || ''}` : '—' }}</td>
                                          <td style="padding:4px 8px;text-align:right;color:#64748b">{{ leftGroupInfo(actual).total != null ? formatCurrency(leftGroupInfo(actual).total!) : '—' }}</td>
                                          <td style="padding:4px 8px 4px 24px;color:#166534">
                                            <div class="d-flex align-center" style="gap:6px">
                                              <v-btn v-if="(actual.stages?.length || 0) >= 2"
                                                :icon="expandedStageRows.has(`pa-${actual.purchase_item_id}`) ? 'mdi-chevron-down' : 'mdi-chevron-right'"
                                                variant="text" density="compact" size="x-small" color="teal"
                                                title="Показать стадии уточнения позиции"
                                                @click.stop="toggleStageRow(`pa-${actual.purchase_item_id}`)"
                                              />
                                              <v-avatar v-if="actual.product_photo" size="24" rounded class="flex-shrink-0" style="cursor:pointer"
                                                @click.stop="photoPreview = { src: actual.product_photo!, title: actual.item_name }">
                                                <v-img :src="actual.product_photo" cover />
                                              </v-avatar>
                                              <div>{{ actual.item_name }}</div>
                                              <v-chip v-if="isExcessCulpritActual(node, actual)" size="x-small" color="red" variant="flat" class="ml-1"
                                                style="font-size:9px;height:16px" :title="excessCulpritChipTooltip(node)"
                                              ><v-icon icon="mdi-alert-decagram" size="10" class="mr-1" />из-за неё превышение</v-chip>
                                            </div>
                                            <a
                                              href="javascript:void(0)"
                                              class="feo-purchase-link"
                                              :title="`Перейти в закупку #${actual.purchase_id}`"
                                              @click.stop="router.push(`/orders/${actual.purchase_id}`)"
                                            >
                                              <v-icon icon="mdi-link-variant" size="11" class="mr-1" />
                                              {{ actual.registry_number || (actual.purchase_number != null ? `№ ${actual.purchase_number}` : `Закупка #${actual.purchase_id}`) }}
                                            </a>
                                            <a v-if="actual.wish_id" href="javascript:void(0)" class="feo-purchase-link ml-2"
                                              title="Перейти к заявкам"
                                              @click.stop="router.push('/wishes')"
                                            >
                                              <v-icon icon="mdi-hand-heart-outline" size="11" class="mr-1" />заявка #{{ actual.wish_id }}
                                            </a>
                                            <!-- Владелец, 2026-08-13: остановка закупки — см. FeoActualItem.stopped_at -->
                                            <div v-if="actual.stopped_at" class="feo-stopped-marker mt-1">
                                              <v-icon icon="mdi-alert-octagon" size="13" class="mr-1" />ЗАКУПКА ОСТАНОВЛЕНА · {{ feoStoppedLine(actual) }}
                                            </div>
                                          </td>
                                          <!-- Правка владельца (2026-08-12): «Кол-во (факт)»/«Цена (факт)» раньше
                                               брались из actual.quantity/unit_price — это поля позиции закупки,
                                               заполненные на ЛЮБОЙ стадии (даже «план закупок», без единой поставки).
                                               Тот же признак факта, что уже работает у «Сумма (факт)»:
                                               fact_amount != null — до появления факта прочерк, как и у суммы. -->
                                          <td style="padding:4px 8px;text-align:right;color:#64748b">{{ actual.fact_amount != null && actual.unit_price ? formatCurrency(actual.unit_price) : '—' }}</td>
                                          <td style="padding:4px 8px;text-align:right;color:#64748b">{{ actual.fact_amount != null && actual.quantity ? `${parseFloat(String(actual.quantity))} ${actual.unit || ''}` : '—' }}</td>
                                          <td style="padding:4px 8px;text-align:right;font-weight:500">
                                            <template v-if="actual.fact_amount != null">
                                              <span :title="actual.fact_allocated ? 'Распределено пропорционально между позициями закупки' : ''">{{ formatCurrency(actual.fact_amount) }}</span>
                                              <v-chip v-if="!actual.fact_confirmed" size="x-small" variant="tonal" color="warning" class="ml-1" style="font-size:9px;height:16px"
                                                title="Сумма по договору — закрывающими документами (актом приёмки) ещё не подтверждена"
                                              >по договору</v-chip>
                                            </template>
                                            <span v-else class="text-medium-emphasis" style="font-style:italic;font-weight:400">{{ purchaseStatusLabel(actual.purchase_status) }}</span>
                                          </td>
                                          <td style="padding:4px 8px"></td>
                                          <td style="padding:4px 8px;color:#64748b;font-size:11px">{{ actual.contractor_name || '—' }}</td>
                                          <!-- Правка владельца (2026-08-12): галочка mdi-check-circle стояла безусловно
                                               (строка и так вложена под своей плановой позицией — «сопоставлено» и
                                               так очевидно, галочка ничего не сообщала). Вместо неё — стадия закупки
                                               текстом, тем же purchaseStatusLabel, что и в других местах файла. -->
                                          <td style="padding:4px 8px;text-align:center;color:#94a3b8;font-size:10px">
                                            {{ purchaseStatusLabel(actual.purchase_status) }}
                                          </td>
                                          <td style="padding:2px;text-align:center;white-space:nowrap">
                                            <v-btn icon="mdi-pencil" size="x-small" variant="text" color="primary"
                                              title="Редактировать позицию закупки"
                                              @click="openReqItemEditFromActual(node, actual)"
                                            />
                                            <!-- Баг найден при приёмке (2026-08-11): mapTarget/mapCategoryId — refs,
                                                 в шаблоне уже auto-unwrap; `mapTarget.value = actual` пытался создать
                                                 свойство "value" на РАЗВЁРНУТОМ значении (объекте/числе), а не на самом
                                                 ref — падало TypeError «Cannot create property 'value' on number»,
                                                 и applyMapping(null) вообще не успевал выполниться (обрыв на строке
                                                 выше). «Снять сопоставление» из вложенной таблицы плановой позиции
                                                 был полностью нерабочим. Исправлено на прямое присваивание — компилятор
                                                 Vue сам генерирует `x.value = y` для присваивания top-level ref. -->
                                            <v-btn icon="mdi-link-off" size="x-small" variant="text" color="grey"
                                              title="Снять сопоставление"
                                              @click="() => { mapTarget = actual; mapCategoryId = node.id; applyMapping(null) }"
                                            />
                                          </td>
                                        </tr>
                                        <!-- Подстроки стадий уточнения (справочно, НЕ входят в comparisonPlanTotal/comparisonFactTotal) -->
                                        <template v-if="expandedStageRows.has(`pa-${actual.purchase_item_id}`)">
                                        <tr v-for="sr in stagesWithDiff(actual.stages)" :key="`pa-stage-${actual.purchase_item_id}-${sr.stage.key}`"
                                          style="border-bottom:1px solid #E2E8F0">
                                          <td style="padding:2px 8px 2px 40px;color:#94a3b8;font-size:10px">{{ sr.stage.label }}</td>
                                          <td style="padding:2px 8px"></td>
                                          <td style="padding:2px 8px"></td>
                                          <td style="padding:2px 8px"></td>
                                          <td style="padding:2px 8px" :style="sr.nameChanged ? 'color:#4F46E5' : ''">{{ sr.stage.name }}</td>
                                          <td style="padding:2px 8px;text-align:right;color:#64748b">
                                            {{ sr.stage.unit_price != null ? formatCurrency(sr.stage.unit_price) : '—' }}
                                            <div v-if="sr.priceDeltaLabel" style="font-size:10px" :style="`color:${sr.priceDeltaColor}`">{{ sr.priceDeltaLabel }}</div>
                                          </td>
                                          <td style="padding:2px 8px;text-align:right;color:#64748b">
                                            {{ sr.stage.quantity != null ? `${parseFloat(String(sr.stage.quantity))} ${sr.stage.unit || ''}` : '—' }}
                                            <div v-if="sr.qtyDeltaLabel" style="font-size:10px" :style="`color:${sr.qtyDeltaColor}`">{{ sr.qtyDeltaLabel }}</div>
                                          </td>
                                          <td style="padding:2px 8px;text-align:right;color:#64748b">{{ sr.stage.total != null ? formatCurrency(sr.stage.total) : '—' }}</td>
                                          <td style="padding:2px 8px"></td>
                                          <td style="padding:2px 8px"></td>
                                          <td style="padding:2px 8px"></td>
                                          <td style="padding:2px 8px"></td>
                                        </tr>
                                        </template>
                                        </template>
                                      </tbody>
                                    </table>
                                    </div>
                                  </td>
                                </tr>
                              </template>

                              <!-- Правка владельца (2026-08-11): «Плановые из закупок» как самостоятельный
                                   блок УБРАН — позиция в стадии «План закупок» это уже начало жизни строки
                                   плана, а не отдельная параллельная сущность (баг «пикап Great Wall POER»:
                                   рисовалась ЗДЕСЬ и одновременно план ФЭО отдельной строкой — ИТОГО складывал
                                   план с закупкой, 16 000 000 вместо 8 000 000). Такие позиции (привязанные —
                                   feo_planned_item_id, непривязанные — на синтетическую «ручной план ФЭО»)
                                   теперь нарисованы ВНУТРИ раскрывающегося блока плановой строки выше —
                                   см. factForPlanned (расширен до ЛЮБОЙ стадии закупки, не только FACT_STATUSES). -->

                              <!-- «Не привязаны к плану — требуется действие»: позиции закупок ЛЮБОЙ
                                   стадии (правка 2026-08-11 — раньше только FACT_STATUSES, теперь
                                   unplannedActualFor смотрит на allActualFor, иначе позиции в статусе
                                   «План закупок» без привязки молча пропадали бы после удаления блока
                                   «Плановые из закупок») без feo_planned_item_id. Показывается ТОЛЬКО
                                   когда есть куда «не привязаться» осмысленно: у листа либо вообще нет
                                   плановой строки (ни реальных FeoPlannedItem, ни ручного плана —
                                   тогда те же самые позиции стали бы фактом синтетической «ручной план
                                   ФЭО» строки, см. factForPlanned(catId, -node.id) — hasManualPseudoRow
                                   ниже это и проверяет), либо реальные плановые позиции есть, но именно
                                   эта закупка ни к одной не привязана.
                                   Правка (регресс вёрстки, найдено при разборе задачи): этот блок — 12
                                   реальных колонок (те же, что у вложенной таблицы «План vs факт» выше —
                                   см. её thead), а НЕ 7 колонок основной таблицы плановых позиций. Раньше
                                   его строки были ПРЯМЫМИ детьми <tbody> внешней 7-колоночной таблицы —
                                   table-layout:fixed считал колонки по МАКСИМУМУ ячеек среди ВСЕХ строк
                                   таблицы (а не только thead), находил тут 12 и делил остаток между 4+8=12
                                   auto-колонками вместо 4, отчего «Позиция плана»/«Кол-во плана»/«Сумма
                                   плана» в шапке резко сужались и текст/подписи наезжали друг на друга —
                                   именно это было на скриншоте по МИНПРОС (у категорий без непривязанных
                                   закупок, как «Внедорожник» у ЦентрПоиск, эффекта не было, поэтому баг
                                   был на вид «плавающий»). Оборачиваем в colspan="7"+свою таблицу — тот
                                   же приём, что уже применён у «План vs факт» (td colspan=7 → div → own
                                   table), тогда обе таблицы снова независимы по колонкам. -->
                              <tr v-if="unplannedActualFor(node).length">
                                <td colspan="7" style="padding:0">
                                  <div style="margin:8px 8px 4px 8px;padding:8px;background:rgba(245,158,11,0.08);border:1px solid rgba(245,158,11,0.35);border-radius:6px">
                                  <table style="width:100%;table-layout:fixed;border-collapse:collapse;font-size:12px">
                                    <tbody>
                                    <tr style="background:rgba(245,158,11,0.14)">
                                      <td colspan="12" style="padding:4px 8px;font-weight:600;color:#B45309;font-size:11px">
                                        <v-icon icon="mdi-alert-circle-outline" size="14" color="warning" class="mr-1" />
                                        <!-- Владелец (2026-08-31): отличать от плашки в самой закупке
                                             («позиция закупки пока не привязана — человек в процессе»).
                                             Здесь — про план: строка висит непривязанной и не попадает
                                             в общий объём, пока её не привяжут. -->
                                        В плане есть непривязанные позиции — не учитываются в общем объёме, нужно привязать
                                      </td>
                                    </tr>
                              <template v-for="actual in unplannedActualFor(node)" :key="`a-${actual.purchase_item_id}`">
                              <tr
                                :data-item-id="actual.purchase_item_id" data-item-group="unplanned"
                                style="border-bottom:1px solid var(--crm-border);background:rgba(245,158,11,0.06)">
                                <td style="padding:4px 8px;color:#0c4a6e">
                                  {{ leftGroupInfo(actual).name }}
                                  <v-chip size="x-small" :color="stageChipColorFor(actual.purchase_status)" variant="tonal" class="ml-1" style="font-size:9px;height:16px"
                                    :title="stageChipTitleFor(actual.purchase_status)"
                                  >{{ stageChipLabelFor(actual.purchase_status) }}</v-chip>
                                </td>
                                <td style="padding:4px 8px;text-align:right;color:#64748b">{{ leftGroupInfo(actual).quantity != null ? `${parseFloat(String(leftGroupInfo(actual).quantity))} ${leftGroupInfo(actual).unit || ''}` : '—' }}</td>
                                <td style="padding:4px 8px;text-align:right;color:#64748b">{{ leftGroupInfo(actual).unitPrice != null ? formatCurrency(leftGroupInfo(actual).unitPrice!) : '—' }}</td>
                                <td style="padding:4px 8px;text-align:right;color:#64748b">{{ leftGroupInfo(actual).total != null ? formatCurrency(leftGroupInfo(actual).total!) : '—' }}</td>
                                <td style="padding:4px 8px" class="text-orange-darken-2">
                                  <div class="d-flex align-center" style="gap:6px">
                                    <v-btn v-if="(actual.stages?.length || 0) >= 2"
                                      :icon="expandedStageRows.has(`a-${actual.purchase_item_id}`) ? 'mdi-chevron-down' : 'mdi-chevron-right'"
                                      variant="text" density="compact" size="x-small" color="teal"
                                      title="Показать стадии уточнения позиции"
                                      @click.stop="toggleStageRow(`a-${actual.purchase_item_id}`)"
                                    />
                                    <v-avatar v-if="actual.product_photo" size="28" rounded class="flex-shrink-0" style="cursor:pointer"
                                      @click.stop="photoPreview = { src: actual.product_photo!, title: actual.item_name }">
                                      <v-img :src="actual.product_photo" cover />
                                    </v-avatar>
                                    <div>{{ actual.item_name }}</div>
                                    <v-chip v-if="isExcessCulpritActual(node, actual)" size="x-small" color="red" variant="flat" class="ml-1"
                                      style="font-size:9px;height:16px" :title="excessCulpritChipTooltip(node)"
                                    ><v-icon icon="mdi-alert-decagram" size="10" class="mr-1" />из-за неё превышение</v-chip>
                                    <!-- Жалоба владельца 2026-08-17 (категория 3710): позиции с feo_planned_item_id,
                                         указывающим на УЖЕ УДАЛЁННУЮ плановую позицию, раньше пропадали с экрана
                                         молча (см. правку unplannedActualFor/isOrphanedActual) — теперь показаны
                                         здесь же, с пометкой ПОЧЕМУ они тут, а не просто «не привязаны». -->
                                    <v-chip v-if="isOrphanedActual(actual)" size="x-small" color="deep-orange" variant="flat" class="ml-1"
                                      style="font-size:9px;height:16px"
                                      title="feo_planned_item_id заполнен, но такой плановой позиции больше нет среди плановых позиций категории — она была удалена. Привязка мертва, позиция не засчитана в план. Заведите новую плановую позицию (кнопка справа) или сопоставьте с существующей."
                                    ><v-icon icon="mdi-link-off" size="10" class="mr-1" />привязана к удалённой плановой позиции</v-chip>
                                  </div>
                                  <a
                                    href="javascript:void(0)"
                                    class="feo-purchase-link"
                                    :title="`Перейти в закупку #${actual.purchase_id}`"
                                    @click.stop="router.push(`/orders/${actual.purchase_id}`)"
                                  >
                                    <v-icon icon="mdi-link-variant" size="11" class="mr-1" />
                                    {{ actual.registry_number || (actual.purchase_number != null ? `№ ${actual.purchase_number}` : `Закупка #${actual.purchase_id}`) }}
                                  </a>
                                  <a v-if="actual.wish_id" href="javascript:void(0)" class="feo-purchase-link ml-2"
                                    title="Перейти к заявкам"
                                    @click.stop="router.push('/wishes')"
                                  >
                                    <v-icon icon="mdi-hand-heart-outline" size="11" class="mr-1" />заявка #{{ actual.wish_id }}
                                  </a>
                                  <!-- Владелец, 2026-08-13: остановка закупки — см. FeoActualItem.stopped_at -->
                                  <div v-if="actual.stopped_at" class="feo-stopped-marker mt-1">
                                    <v-icon icon="mdi-alert-octagon" size="13" class="mr-1" />ЗАКУПКА ОСТАНОВЛЕНА · {{ feoStoppedLine(actual) }}
                                  </div>
                                </td>
                                <td style="padding:4px 8px;text-align:right" class="text-medium-emphasis">{{ actual.quantity ? `${parseFloat(String(actual.quantity))} ${actual.unit || ''}` : '—' }}</td>
                                <td style="padding:4px 8px;text-align:right" class="text-medium-emphasis">{{ actual.unit_price ? formatCurrency(actual.unit_price) : '—' }}</td>
                                <td style="padding:4px 8px;text-align:right;font-weight:500" class="text-orange-darken-2">
                                  <template v-if="actual.fact_amount != null">
                                    <span :title="actual.fact_allocated ? 'Распределено пропорционально между позициями закупки' : ''">{{ formatCurrency(actual.fact_amount) }}</span>
                                    <v-chip v-if="!actual.fact_confirmed" size="x-small" variant="tonal" color="warning" class="ml-1" style="font-size:9px;height:16px"
                                      title="Сумма по договору — закрывающими документами (актом приёмки) ещё не подтверждена"
                                    >по договору</v-chip>
                                  </template>
                                  <span v-else class="text-medium-emphasis" style="font-style:italic;font-weight:400">{{ purchaseStatusLabel(actual.purchase_status) }}</span>
                                </td>
                                <!-- calcDiff(0,[actual]) считает вклад в diff ТОЛЬКО для committed/delivered
                                     статусов (см. DIFF_COMMITTED_STATUSES) — для позиции в «План закупок»
                                     это дало бы враньё «0», хотя вся сумма ей не покрыта планом; здесь
                                     нет строки плана вовсе, поэтому просто минус вся сумма позиции. -->
                                <td style="padding:4px 8px;text-align:right;color:#DC2626">{{ formatCurrency(-(Number(actual.fact_amount ?? actual.total_price ?? 0))) }}</td>
                                <td style="padding:4px 8px;font-size:11px" class="text-medium-emphasis">{{ actual.contractor_name || '—' }}</td>
                                <td style="padding:4px 8px;text-align:center">
                                  <v-icon icon="mdi-alert-circle-outline" size="16" color="warning"
                                    :title="isOrphanedActual(actual)
                                      ? 'Закупка привязана к плановой позиции, которой больше нет (удалена) — в графу «план» она не засчитана. Заведите новую плановую позицию кнопкой справа, либо сопоставьте с существующей.'
                                      : 'Закупка не привязана ни к одной плановой позиции — в графу «план» она не засчитана. Нажмите кнопку-ссылку справа «Сопоставить с плановой».'" />
                                </td>
                                <td style="padding:2px;text-align:center;white-space:nowrap">
                                  <v-btn icon="mdi-pencil" size="x-small" variant="text" color="primary"
                                    title="Редактировать позицию закупки"
                                    @click="openReqItemEditFromActual(node, actual)"
                                  />
                                  <!-- Задача владельца 2026-08-17: «раз причина в том, что плановой позиции
                                       нет — предложи создать её из данных этой позиции закупки и сразу
                                       привязать». Переиспользует showAddPlannedDialog/plannedItemForm/
                                       savePlannedItem (тот же диалог, что «Добавить плановую» и
                                       openConvertManualPlanToItem выше) — второй диалог не пишем. -->
                                  <v-btn icon="mdi-plus-box-outline" size="x-small" variant="text" color="deep-orange"
                                    title="Завести плановую позицию по этой закупке и сразу привязать"
                                    @click="openCreatePlannedFromActual(node, actual)"
                                  />
                                  <v-btn icon="mdi-link-variant" size="x-small" variant="text" color="teal"
                                    title="Сопоставить с плановой"
                                    @click="openMapDialog(actual, node.id)"
                                  />
                                </td>
                              </tr>
                              <!-- Подстроки стадий уточнения (справочно, НЕ входят в comparisonPlanTotal/comparisonFactTotal) -->
                              <template v-if="expandedStageRows.has(`a-${actual.purchase_item_id}`)">
                              <tr v-for="sr in stagesWithDiff(actual.stages)" :key="`a-stage-${actual.purchase_item_id}-${sr.stage.key}`"
                                style="border-bottom:1px solid var(--crm-border);background:rgba(245,158,11,0.1)">
                                <td style="padding:2px 8px 2px 40px;color:#94a3b8;font-size:10px">{{ sr.stage.label }}</td>
                                <td style="padding:2px 8px"></td>
                                <td style="padding:2px 8px"></td>
                                <td style="padding:2px 8px"></td>
                                <td style="padding:2px 8px" :style="sr.nameChanged ? 'color:#4F46E5' : ''">{{ sr.stage.name }}</td>
                                <td style="padding:2px 8px;text-align:right;color:#64748b">
                                  {{ sr.stage.quantity != null ? `${parseFloat(String(sr.stage.quantity))} ${sr.stage.unit || ''}` : '—' }}
                                  <div v-if="sr.qtyDeltaLabel" style="font-size:10px" :style="`color:${sr.qtyDeltaColor}`">{{ sr.qtyDeltaLabel }}</div>
                                </td>
                                <td style="padding:2px 8px;text-align:right;color:#64748b">
                                  {{ sr.stage.unit_price != null ? formatCurrency(sr.stage.unit_price) : '—' }}
                                  <div v-if="sr.priceDeltaLabel" style="font-size:10px" :style="`color:${sr.priceDeltaColor}`">{{ sr.priceDeltaLabel }}</div>
                                </td>
                                <td style="padding:2px 8px;text-align:right;color:#64748b">{{ sr.stage.total != null ? formatCurrency(sr.stage.total) : '—' }}</td>
                                <td style="padding:2px 8px"></td>
                                <td style="padding:2px 8px"></td>
                                <td style="padding:2px 8px"></td>
                                <td style="padding:2px 8px"></td>
                              </tr>
                              </template>
                              </template>
                                    </tbody>
                                  </table>
                                  </div>
                                </td>
                              </tr>

                              <!-- Ручной план ФЭО (сама категория) — до 2026-08-07 был отдельным блоком
                                   строк здесь; теперь это ОДНА строка внутри цикла displayPlannedRowsFor
                                   выше (id = -node.id, planned.isManual), переиспользующая ту же вёрстку,
                                   что и реальная плановая позиция — не отдельный рендер. -->

                              <!-- «Одноимённые позиции из заявок» (сопоставление по ИМЕНИ, matchedReqFor)
                                   УБРАНЫ ЦЕЛИКОМ 2026-08-07 (ШАГ 1 плана дедупликации дерева ФЭО): это был
                                   ТРЕТИЙ независимый рендер тех же самых позиций закупок (см. Таблицу B —
                                   reqOwnersAfter/reqItemRowsFor — и «actualFactFor» выше в этой же панели),
                                   плюс сопоставление по названию давало ложные совпадения (позиция другой
                                   категории с тем же именем показывалась здесь). Единственный источник
                                   факта листа теперь — comparisonData[node.id].actual (см. factForPlanned/
                                   unplannedActualFor). -->

                              <!-- Пусто -->
                              <tr v-if="!displayPlannedRowsFor(node).length && !comparisonData[node.id].actual.length">
                                <td colspan="8" style="padding:12px 8px;text-align:center;color:#9ca3af;font-style:italic">
                                  Нет плановых позиций. Добавьте вручную или загрузите из Excel.
                                </td>
                              </tr>
                            </tbody>
                            <!-- Итоговая строка -->
                            <tfoot v-if="displayPlannedRowsFor(node).length || comparisonData[node.id].actual.length">
                              <!-- Требование владельца (2026-08-12): ИТОГО на уровне плана — только план,
                                   фактическая сумма/разница отсюда убраны вместе с остальными факт-колонками
                                   этого уровня (см. thead выше); факт по-прежнему суммируется в раскрывающихся
                                   блоках под каждой плановой позицией. -->
                              <tr style="background:rgba(34,197,94,0.08);font-weight:600;border-top:2px solid rgba(34,197,94,0.3)">
                                <td :style="{ paddingLeft: `${plannedItemIndentPx(node)}px` }" style="padding-top:4px;padding-right:8px;padding-bottom:4px" class="text-success">ИТОГО</td>
                                <td style="padding:4px 8px"></td>
                                <td style="padding:4px 8px"></td>
                                <td style="padding:4px 8px;text-align:right">
                                  {{ formatCurrency(comparisonPlanTotal(node)) }}
                                </td>
                                <td style="padding:4px 8px"></td>
                              </tr>
                            </tfoot>
                          </table>

                        </div>
                      </td>
                    </tr>

                    <!-- ── Позиции «из заявок» как позиции ФЭО (после поддерева владельца) ── -->
                    <template v-for="owner in (reqOwnersAfter[node.id] || [])" :key="`reqblk-${owner.id}`">
                      <template v-if="plannedBase !== 'purchases'">
                        <template v-for="row in reqItemRowsFor(owner)" :key="`req-${owner.id}-${row.key}`">
                          <tr
                            class="feo-tr feo-req-row"
                            :class="kpiReqRowClass(row)"
                            :data-item-ids="row.group ? row.group.items.map(i => i.id).join(',') : ''"
                            data-item-group="owner-virtual"
                            :style="row.group ? 'background:rgba(20,184,166,0.04)' : 'background:rgba(20,184,166,0.10)'"
                          >
                            <td class="feo-td feo-td-name" :style="{ paddingLeft: reqRowIndent(owner, row) }">
                              <div class="feo-name-inner">
                                <template v-if="!row.group">
                                  <v-icon size="14" class="mr-1 flex-shrink-0"
                                    :icon="row.level === 1 ? 'mdi-shape-outline' : 'mdi-tag-outline'"
                                    :color="row.level === 1 ? '#0D9488' : '#64748B'" />
                                  <span :style="row.level === 1 ? 'font-weight:600;font-size:12px' : 'font-weight:500;font-size:12px;color:#475569'">{{ row.header }}</span>
                                  <span class="feo-code ml-2">{{ row.count }} поз.</span>
                                </template>
                                <template v-else>
                                  <span style="width:16px;display:inline-block" />
                                  <v-icon size="16" class="mr-1 flex-shrink-0" icon="mdi-file-document-outline" color="#22C55E" />
                                  <v-avatar v-if="row.group.items.find(i => i.product_photo)" size="28" rounded class="mr-1 flex-shrink-0" style="cursor:pointer"
                                    @click.stop="photoPreview = { src: row.group.items.find(i => i.product_photo)!.product_photo!, title: row.group.name }">
                                    <v-img :src="row.group.items.find(i => i.product_photo)!.product_photo!" cover />
                                  </v-avatar>
                                  <span class="feo-status-strip mr-1">
                                    <v-icon v-for="gs in groupStatuses(row.group).slice(0, 3)" :key="gs.status"
                                      :icon="purchaseStatusIcon(gs.status)" :color="purchaseStatusColor(gs.status)" size="13"
                                      :title="`${gs.label} — ${gs.count} поз.`" class="mr-1" />
                                  </span>
                                  <span class="feo-name feo-name--l3">{{ row.group.name }}</span>
                                  <span v-if="row.group.items.length > 1" class="feo-code ml-2"
                                    title="Слито из нескольких позиций заявок">{{ row.group.items.length }} поз. в заявках</span>
                                </template>
                              </div>
                            </td>
                            <!-- Финансирование по ФЭО: не задавалось -->
                            <td class="feo-td feo-td-num">
                              <span v-if="row.group" class="feo-amount-empty"
                                title="Эта позиция не задавалась в ФЭО — заведена через заявку">—</span>
                            </td>
                            <!-- Плановое кол-во: снимок ТЗ (planned_quantity), НЕ текущее кол-во —
                                 см. задачу владельца «план ≠ факт» (Шаг 5, п.1). -->
                            <td class="feo-td feo-td-num">
                              <span class="feo-amount" :class="!row.group ? 'text-medium-emphasis' : ''" style="font-size:12px">{{ row.group ? groupPlannedQty(row.group) : row.sumQty }}{{ row.group?.unit ? ` ${row.group.unit}` : '' }}</span>
                              <div v-if="row.group" class="feo-plan-note text-medium-emphasis">из заявок</div>
                            </td>
                            <!-- Плановая сумма: снимок ТЗ (planned_total), не съезжает при правке итоговой цены -->
                            <td class="feo-td feo-td-num">
                              <span class="feo-amount" :class="!row.group ? 'text-medium-emphasis' : ''" style="font-size:12px">{{ formatCurrency(row.group ? groupPlannedTotal(row.group) : row.sum) }}</span>
                              <div v-if="row.group && row.group.items.length === 1 && (row.group.items[0].planned_unit_price ?? row.group.items[0].unit_price)"
                                class="feo-plan-note text-medium-emphasis">{{ formatCurrency(row.group.items[0].planned_unit_price ?? row.group.items[0].unit_price) }}/ед.</div>
                            </td>
                            <!-- Фактическая сумма: реальный факт (ContractItem/contract_price), а не заглушка —
                                 см. задачу владельца «план ≠ факт» (Шаг 5, п.1). «—» только когда факта ещё нет. -->
                            <td class="feo-td feo-td-num">
                              <span v-if="row.group && groupFactTotal(row.group) != null" class="feo-amount" style="font-size:12px">{{ formatCurrency(groupFactTotal(row.group)!) }}</span>
                              <span v-else-if="row.group" class="feo-amount-empty" title="Итог закупки/договора ещё не известен">—</span>
                            </td>
                            <td class="feo-td feo-td-num"><span v-if="row.group" class="feo-amount-empty">—</span></td>
                            <td class="feo-td feo-td-actions">
                              <div v-if="row.group" class="d-flex align-center justify-end">
                                <v-btn
                                  :icon="expandedReqItemPanels.has(reqPanelKey(owner, row.group)) ? 'mdi-list-box' : 'mdi-list-box-outline'"
                                  variant="text" size="x-small"
                                  :color="expandedReqItemPanels.has(reqPanelKey(owner, row.group)) ? 'teal' : 'grey'"
                                  title="Источники: план vs факт по этой позиции"
                                  @click="toggleReqItemPanel(owner, row.group)"
                                />
                                <v-btn icon="mdi-cart-outline" variant="text" size="x-small" color="blue"
                                  :title="virtGroupPurchaseIds(row.group).length === 1 ? 'Открыть закупку' : 'Несколько закупок — открыть источники'"
                                  @click.stop="virtCart(owner, row.group)" />
                                <v-btn icon="mdi-pencil-outline" variant="text" size="x-small" color="primary"
                                  :title="row.group.items.length === 1 ? 'Редактировать позицию закупки' : 'Несколько позиций — открыть источники'"
                                  @click="virtEdit(owner, row.group)" />
                                <v-btn icon="mdi-delete-outline" variant="text" size="x-small" color="error"
                                  :title="row.group.items.length === 1 ? 'Удалить позицию из закупки' : 'Несколько позиций — открыть источники'"
                                  @click="virtDelete(owner, row.group)" />
                              </div>
                            </td>
                          </tr>

                          <!-- Панель источников: план vs факт по каждой позиции заявки -->
                          <tr v-if="row.group && expandedReqItemPanels.has(reqPanelKey(owner, row.group))">
                            <td colspan="7" style="padding:0;background:rgba(20,184,166,0.08)">
                              <div :style="{ padding: '8px 12px 10px', marginLeft: reqRowIndent(owner, row) }">
                                <div class="d-flex align-center mb-1" style="gap:6px">
                                  <v-icon icon="mdi-compare-horizontal" size="14" color="teal" />
                                  <span style="font-size:11px;font-weight:600" class="text-teal-darken-2">Позиции: план vs факт</span>
                                </div>
                                <div v-if="loadingComparison.has(owner.id)" class="d-flex align-center" style="gap:8px;padding:4px 0">
                                  <v-progress-circular indeterminate size="14" color="teal" />
                                  <span class="text-caption">Загрузка...</span>
                                </div>
                                <table v-else style="width:100%;border-collapse:collapse;font-size:11px;background:#fff">
                                  <thead>
                                    <tr style="background:#CCFBF1">
                                      <th style="padding:3px 8px;text-align:left;color:#0f766e;font-weight:600">Название (из ТЗ)</th>
                                      <th style="padding:3px 8px;text-align:right;color:#0f766e;font-weight:600;width:90px">Кол-во (из ТЗ)</th>
                                      <th style="padding:3px 8px;text-align:right;color:#0f766e;font-weight:600;width:90px">Цена (из ТЗ)</th>
                                      <th style="padding:3px 8px;text-align:right;color:#0f766e;font-weight:600;width:110px">Сумма (из ТЗ)</th>
                                      <th style="padding:3px 8px;text-align:left;color:#0f766e;font-weight:600">ФАКТ (из закупок)</th>
                                      <th style="padding:3px 8px;text-align:right;color:#0f766e;font-weight:600;width:90px">Кол-во (факт)</th>
                                      <th style="padding:3px 8px;text-align:right;color:#0f766e;font-weight:600;width:90px">Цена (факт)</th>
                                      <th style="padding:3px 8px;text-align:right;color:#0f766e;font-weight:600;width:110px">Сумма (факт)</th>
                                      <th style="padding:3px 8px;text-align:right;color:#0f766e;font-weight:600;width:100px">Разница</th>
                                      <th style="padding:3px 8px;text-align:left;color:#0f766e;font-weight:600;width:120px">Контрагент</th>
                                      <th style="padding:3px 8px;text-align:center;color:#0f766e;font-weight:600;width:80px">Статус</th>
                                      <th style="padding:3px 2px;width:80px"></th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    <tr v-for="it in row.group.items" :key="`src-${it.id}`" :class="kpiItemRowClass(it)" :data-item-id="it.id" data-item-group="owner-virtual-source" style="border-bottom:1px solid #E0F2FE">
                                      <td style="padding:4px 8px;color:#0c4a6e">
                                        <div class="d-flex align-center" style="gap:6px">
                                          <v-avatar v-if="it.product_photo" size="28" rounded class="flex-shrink-0" style="cursor:pointer"
                                            @click.stop="photoPreview = { src: it.product_photo!, title: it.item_name }">
                                            <v-img :src="it.product_photo" cover />
                                          </v-avatar>
                                          <v-icon :icon="purchaseStatusIcon(it.purchase_status)" :color="purchaseStatusColor(it.purchase_status)" size="14" class="mr-1" :title="purchaseStatusLabel(it.purchase_status)" />
                                          <div>{{ it.item_name }}</div>
                                        </div>
                                        <div class="d-flex align-center flex-wrap" style="gap:8px">
                                          <a href="javascript:void(0)" class="feo-purchase-link"
                                            :title="`Перейти в закупку #${it.purchase_id}`"
                                            @click.stop="router.push(`/orders/${it.purchase_id}`)"
                                          >
                                            <v-icon icon="mdi-link-variant" size="11" class="mr-1" />
                                            {{ it.registry_number || (it.purchase_number != null ? `№ ${it.purchase_number}` : `Закупка #${it.purchase_id}`) }}
                                          </a>
                                          <a v-if="it.wish_id" href="javascript:void(0)" class="feo-purchase-link"
                                            title="Перейти к заявкам"
                                            @click.stop="router.push('/wishes')"
                                          >
                                            <v-icon icon="mdi-hand-heart-outline" size="11" class="mr-1" />заявка #{{ it.wish_id }}
                                          </a>
                                        </div>
                                        <div v-if="reqItemPlanned(owner.id, it.id)" class="feo-plan-note text-medium-emphasis">
                                          сопоставлено с плановой «{{ reqItemPlanned(owner.id, it.id)?.name }}»
                                        </div>
                                      </td>
                                      <!-- Снимок ТЗ (planned_*), заморожен с момента объявления закупки — не текущее
                                           кол-во/цена, см. задачу владельца «план ≠ факт» (Шаг 5, п.1/2). -->
                                      <td style="padding:4px 8px;text-align:right;color:#64748b">{{ it.planned_quantity ?? it.quantity }}{{ it.unit ? ` ${it.unit}` : '' }}</td>
                                      <td style="padding:4px 8px;text-align:right;color:#64748b">{{ (it.planned_unit_price ?? it.unit_price) ? formatCurrency(it.planned_unit_price ?? it.unit_price) : '—' }}</td>
                                      <td style="padding:4px 8px;text-align:right;font-weight:500">{{ formatCurrency(it.planned_total ?? it.total_price) }}</td>
                                      <!-- ФАКТ: реальные данные (ContractItem/contract_price), «ещё не поставлено»
                                           только когда факта действительно нет — Шаг 5, п.3. -->
                                      <td style="padding:4px 8px;color:#9ca3af;font-style:italic">{{ it.fact_amount != null ? '' : 'ещё не поставлено' }}</td>
                                      <td style="padding:4px 8px;text-align:right;color:#64748b">{{ it.fact_amount != null ? `${it.fact_quantity ?? it.planned_quantity ?? it.quantity}${it.unit ? ` ${it.unit}` : ''}` : '' }}</td>
                                      <td style="padding:4px 8px;text-align:right;color:#64748b">{{ it.fact_amount != null && it.fact_unit_price != null ? formatCurrency(it.fact_unit_price) : '' }}</td>
                                      <td style="padding:4px 8px;text-align:right;font-weight:500">{{ it.fact_amount != null ? formatCurrency(it.fact_amount) : '' }}</td>
                                      <td style="padding:4px 8px;text-align:right" :style="getDiffStyle(it.planned_total ?? it.total_price, [it])">{{ formatCurrency(calcDiff(it.planned_total ?? it.total_price, [it])) }}</td>
                                      <td style="padding:4px 8px;color:#9ca3af">—</td>
                                      <td style="padding:4px 8px;text-align:center">
                                        <v-chip size="x-small" color="blue" variant="tonal" :prepend-icon="purchaseStatusIcon(it.purchase_status)">
                                          {{ purchaseStatusLabel(it.purchase_status) }}
                                        </v-chip>
                                      </td>
                                      <td style="padding:2px;text-align:center;white-space:nowrap">
                                        <v-btn icon="mdi-cart-outline" size="x-small" variant="text" color="blue"
                                          title="Открыть закупку"
                                          @click.stop="router.push(`/orders/${it.purchase_id}`)" />
                                        <a v-if="it.wish_id" href="javascript:void(0)" class="feo-purchase-link"
                                          title="Изменить можно только в заявке"
                                          @click.stop="router.push({ path: '/wishes', query: { open: String(it.wish_id) } })"
                                        ><v-icon icon="mdi-hand-heart-outline" size="11" class="mr-1" />заявка #{{ it.wish_id }}</a>
                                        <v-btn v-if="it.wish_id" icon="mdi-swap-horizontal" size="x-small" variant="text" color="teal"
                                          title="Сменить категорию ФЭО позиции"
                                          @click.stop="openWishItemFeoEdit(owner, it)" />
                                        <template v-if="!it.wish_id">
                                          <v-btn icon="mdi-pencil-outline" size="x-small" variant="text" color="primary"
                                            title="Редактировать позицию закупки"
                                            @click="openReqItemEdit(owner, it)" />
                                          <v-btn icon="mdi-delete-outline" size="x-small" variant="text" color="error"
                                            title="Удалить позицию из закупки"
                                            @click="confirmReqItemDelete(owner, it)" />
                                        </template>
                                        <v-btn v-if="!reqItemPlanned(owner.id, it.id) && reqItemActual(owner.id, it.id)"
                                          icon="mdi-link-variant" size="x-small" variant="text" color="teal"
                                          title="Сопоставить с плановой позицией"
                                          @click="mapReqItem(owner, it)"
                                        />
                                      </td>
                                    </tr>
                                  </tbody>
                                </table>
                              </div>
                            </td>
                          </tr>
                        </template>
                      </template>
                      <template v-else>
                        <!-- Режим «по закупкам»: папки по purchase_id без слияния -->
                        <template v-for="f in purchaseFoldersFor(owner)" :key="`pf-${owner.id}-${f.purchase_id}`">
                          <tr class="feo-tr feo-req-row" :class="kpiFolderClass(f)" style="background:rgba(20,184,166,0.10)">
                            <td class="feo-td feo-td-name" :style="{ paddingLeft: ((owner.depth + 1) * 20 + 8) + 'px' }">
                              <div class="feo-name-inner">
                                <span class="feo-tree-chevron" style="cursor:pointer" @click.stop="togglePurchaseFolder(f.purchase_id)">
                                  <v-icon size="16">{{ expandedPurchases.has(f.purchase_id) ? 'mdi-chevron-down' : 'mdi-chevron-right' }}</v-icon>
                                </span>
                                <v-icon size="15" color="#0D9488" class="mr-1">{{ expandedPurchases.has(f.purchase_id) ? 'mdi-folder-open-outline' : 'mdi-folder-outline' }}</v-icon>
                                <span>{{ purchaseFolderTitle(f) }}</span>
                                <v-chip size="x-small" variant="tonal" color="blue" class="ml-2" :prepend-icon="purchaseStatusIcon(f.purchase_status)">{{ purchaseStatusLabel(f.purchase_status) }}</v-chip>
                                <span class="feo-code ml-2">{{ f.items.length }} поз.</span>
                                <a v-if="f.wish_id" href="javascript:void(0)" class="feo-purchase-link ml-2"
                                  title="Перейти к заявкам"
                                  @click.stop="router.push('/wishes')"
                                >
                                  <v-icon icon="mdi-hand-heart-outline" size="11" class="mr-1" />заявка #{{ f.wish_id }}
                                </a>
                                <!-- Владелец, 2026-08-13: остановка закупки (сейчас всегда скрыт — backend
                                     ещё не отдаёт stopped_at в этой выборке, см. FeoPurchaseFolder.stopped_at) -->
                                <span v-if="f.stopped_at" class="feo-stopped-marker ml-2">
                                  <v-icon icon="mdi-alert-octagon" size="13" class="mr-1" />ЗАКУПКА ОСТАНОВЛЕНА · {{ feoStoppedLine(f) }}
                                </span>
                              </div>
                            </td>
                            <td class="feo-td feo-td-num"><span class="feo-amount-empty">—</span></td>
                            <td class="feo-td feo-td-num">
                              <span class="feo-amount" style="font-size:12px">{{ f.qty }}{{ f.unit ? ` ${f.unit}` : '' }}</span>
                            </td>
                            <td class="feo-td feo-td-num">
                              <span class="feo-amount" style="font-size:12px">{{ formatCurrency(f.total) }}</span>
                            </td>
                            <td class="feo-td feo-td-num"><span class="feo-amount-empty">—</span></td>
                            <td class="feo-td feo-td-num"><span class="feo-amount-empty">—</span></td>
                            <td class="feo-td feo-td-actions">
                              <div class="d-flex align-center justify-end">
                                <v-btn icon="mdi-cart-outline" variant="text" size="x-small" color="blue"
                                  title="Открыть закупку"
                                  @click.stop="router.push(`/orders/${f.purchase_id}`)" />
                              </div>
                            </td>
                          </tr>
                          <template v-if="expandedPurchases.has(f.purchase_id)">
                            <tr v-for="it in f.items" :key="`pfi-${owner.id}-${it.id}`" class="feo-tr feo-req-row" :class="kpiItemRowClass(it)" :data-item-id="it.id" data-item-group="owner-purchase-folder" style="background:rgba(20,184,166,0.04)">
                              <td class="feo-td feo-td-name" :style="{ paddingLeft: ((owner.depth + 2) * 20 + 8) + 'px' }">
                                <div class="feo-name-inner">
                                  <span style="width:16px;display:inline-block" />
                                  <v-icon size="15" class="mr-1 flex-shrink-0" icon="mdi-file-document-outline" color="#22C55E" />
                                  <v-avatar v-if="it.product_photo" size="28" rounded class="mr-1 flex-shrink-0" style="cursor:pointer"
                                    @click.stop="photoPreview = { src: it.product_photo!, title: it.item_name }">
                                    <v-img :src="it.product_photo" cover />
                                  </v-avatar>
                                  <v-icon :icon="purchaseStatusIcon(it.purchase_status)" :color="purchaseStatusColor(it.purchase_status)" size="14" class="mr-1" :title="purchaseStatusLabel(it.purchase_status)" />
                                  <span class="feo-name feo-name--l3">{{ it.item_name }}</span>
                                </div>
                              </td>
                              <td class="feo-td feo-td-num"><span class="feo-amount-empty">—</span></td>
                              <td class="feo-td feo-td-num">
                                <span class="feo-amount" style="font-size:12px">{{ it.quantity }}{{ it.unit ? ` ${it.unit}` : '' }}</span>
                              </td>
                              <td class="feo-td feo-td-num">
                                <span class="feo-amount" style="font-size:12px">{{ formatCurrency(it.total_price) }}</span>
                                <div v-if="it.unit_price" class="feo-plan-note text-medium-emphasis">{{ formatCurrency(it.unit_price) }}/ед.</div>
                              </td>
                              <td class="feo-td feo-td-num"><span class="feo-amount-empty">—</span></td>
                              <td class="feo-td feo-td-num"><span class="feo-amount-empty">—</span></td>
                              <td class="feo-td feo-td-actions">
                                <div class="d-flex align-center justify-end">
                                  <a v-if="it.wish_id" href="javascript:void(0)" class="feo-purchase-link"
                                    title="Изменить можно только в заявке"
                                    @click.stop="router.push({ path: '/wishes', query: { open: String(it.wish_id) } })"
                                  ><v-icon icon="mdi-hand-heart-outline" size="11" class="mr-1" />заявка #{{ it.wish_id }}</a>
                                  <v-btn v-if="it.wish_id" icon="mdi-swap-horizontal" size="x-small" variant="text" color="teal"
                                    title="Сменить категорию ФЭО позиции"
                                    @click.stop="openWishItemFeoEdit(owner, it)" />
                                  <template v-if="!it.wish_id">
                                    <v-btn icon="mdi-pencil-outline" size="x-small" variant="text" color="primary"
                                      title="Редактировать позицию закупки"
                                      @click="openReqItemEdit(owner, it)" />
                                    <v-btn icon="mdi-delete-outline" size="x-small" variant="text" color="error"
                                      title="Удалить позицию из закупки"
                                      @click="confirmReqItemDelete(owner, it)" />
                                  </template>
                                </div>
                              </td>
                            </tr>
                          </template>
                        </template>
                      </template>
                    </template>
                  </template>

                  <!-- Drop zone: переместить на верхний уровень -->
                  <tr v-if="dragNodeId"
                    class="feo-tr feo-drop-root"
                    :class="{ 'feo-drop-target': dragOverId === -1 }"
                    @dragover.prevent="dragOverId = -1"
                    @dragleave="dragOverId = null"
                    @drop.prevent="onDropToRoot"
                  >
                    <td colspan="6" class="feo-td text-center text-caption text-medium-emphasis" style="padding:12px">
                      <v-icon icon="mdi-arrow-up-bold" size="16" class="mr-1" />
                      Переместить на верхний уровень (корень)
                    </td>
                  </tr>

                  <!-- Без категории ФЭО: закупки субсидии, у которых ни сама закупка, ни одна
                       позиция не привязаны к категории — деньги есть (KPI их видит), но в дереве
                       ФЭО не отображаются, т.к. дерево строится по категориям. Справочная строка,
                       НЕ входит в ИТОГО ниже. -->
                  <tr v-if="unassignedFeo.amount > 0 || unassignedFeo.purchase_count > 0"
                    class="feo-tr feo-tr--unassigned"
                    style="cursor:pointer"
                    title="Перейти в реестр закупок субсидии"
                    @click="goToUnassignedFeoPurchases"
                  >
                    <td class="feo-td feo-td-name" style="padding-left:8px">
                      <v-icon icon="mdi-help-circle-outline" size="16" color="#F59E0B" class="mr-1" />
                      <span style="color:#F59E0B;font-weight:600">Без категории ФЭО</span>
                      <div class="feo-plan-note text-medium-emphasis font-weight-regular">
                        {{ unassignedFeo.purchase_count }} {{ unassignedFeo.purchase_count === 1 ? 'закупка не привязана' : 'закупок не привязаны' }}
                        к категориям — распределите, иначе деньги не видны в плане
                      </div>
                    </td>
                    <td class="feo-td feo-td-num">—</td>
                    <td class="feo-td feo-td-num">—</td>
                    <td class="feo-td feo-td-num" style="color:#F59E0B;font-weight:600">{{ formatCurrency(unassignedFeo.amount) }}</td>
                    <td class="feo-td feo-td-num">—</td>
                    <td class="feo-td feo-td-num">—</td>
                  </tr>

                  <!-- Итого -->
                  <tr class="feo-tr feo-tr--total">
                    <td class="feo-td feo-td-name font-weight-bold" style="padding-left:8px">ИТОГО</td>
                    <td class="feo-td feo-td-num font-weight-bold">
                      <span title="Сумма верхних категорий: ручное ФЭО, без него — факт (поставлено/оплачено), иначе план">
                        {{ formatCurrency(totalFeoEffective) }}
                      </span>
                      <div v-if="totalFeoBudget !== null" class="feo-plan-note text-medium-emphasis font-weight-regular"
                        title="Ручной бюджет субсидии"
                      >
                        бюджет {{ formatCurrency(totalFeoBudget) }}
                      </div>
                      <div v-if="totalFeoBudget !== null && totalFeoDiff > 0.005"
                        class="feo-plan-note font-weight-regular" style="color:#EF4444"
                        :title="`Сумма категорий ${formatCurrency(totalFeoEffective)} превышает бюджет субсидии ${formatCurrency(totalFeoBudget)}`"
                      >
                        лишние {{ formatCurrency(totalFeoDiff) }}
                      </div>
                      <div v-else-if="totalFeoBudget !== null && totalFeoDiff < -0.005"
                        class="feo-plan-note font-weight-regular" style="color:#F59E0B"
                        :title="`Сумма категорий ${formatCurrency(totalFeoEffective)} меньше бюджета субсидии ${formatCurrency(totalFeoBudget)}`"
                      >
                        не распределено {{ formatCurrency(-totalFeoDiff) }}
                      </div>
                    </td>
                    <td class="feo-td feo-td-num font-weight-bold">
                      {{ feoTree.reduce((acc, r) => acc + feoQtyDisplayFor(r), 0) > 0 ? feoTree.reduce((acc, r) => acc + feoQtyDisplayFor(r), 0) : '—' }}
                    </td>
                    <td class="feo-td feo-td-num font-weight-bold">
                      {{ feoTree.reduce((acc, r) => acc + feoPlannedDisplayFor(r), 0) > 0 ? formatCurrency(feoTree.reduce((acc, r) => acc + feoPlannedDisplayFor(r), 0)) : '—' }}
                    </td>
                    <!-- Футер обязан считаться по той же шкале, что и колонка «В плане-графике» в строках
                         (решение владельца 2026-08-18), иначе ИТОГО противоречит телу таблицы. -->
                    <td class="feo-td feo-td-num font-weight-bold">{{ formatCurrency(totalFeoInPlanSchedule) }}</td>
                    <td class="feo-td feo-td-num font-weight-bold">
                      {{ formatCurrency(feoTree.reduce((acc, r) => acc + feoResidualBaseFor(r), 0) - totalFeoInPlanSchedule) }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- ── Мероприятия ── -->
          <div class="mt-4">
            <div class="detail-feo-header">
              <span class="chart-card-title">Мероприятия</span>
              <div class="d-flex gap-2">
                <v-btn v-if="selectedId" size="small" variant="tonal" color="success" prepend-icon="mdi-microsoft-excel"
                  @click="downloadReport(selectedId)">
                  Приложение №3
                </v-btn>
                <v-btn v-if="isAdminLevel" size="small" variant="tonal" prepend-icon="mdi-plus" @click="showAddEventDialog = true">
                  Добавить
                </v-btn>
              </div>
            </div>
            <div v-if="subsidyEvents.length === 0" class="feo-empty">
              <v-icon icon="mdi-calendar-blank" size="40" color="grey-lighten-2" />
              <div class="text-caption text-medium-emphasis mt-2">Нет мероприятий</div>
            </div>
            <v-list v-else density="compact" class="pa-0">
              <v-list-item v-for="ev in subsidyEvents" :key="ev.id" class="px-2">
                <template #prepend>
                  <v-icon :icon="ev.is_active ? 'mdi-calendar-check' : 'mdi-calendar-remove'" :color="ev.is_active ? 'success' : 'grey'" size="18" />
                </template>
                <v-list-item-title class="text-body-2">{{ ev.name }}</v-list-item-title>
                <v-list-item-subtitle v-if="ev.region || ev.date_from" class="text-caption">
                  <span v-if="ev.region">{{ ev.region }}</span>
                  <span v-if="ev.region && ev.date_from"> · </span>
                  <span v-if="ev.date_from">{{ ev.date_from }} — {{ ev.date_to }}</span>
                </v-list-item-subtitle>
                <template v-if="isAdminLevel" #append>
                  <v-btn icon="mdi-pencil" size="x-small" variant="text" color="primary" @click="openEditEventDialog(ev)" />
                  <v-btn icon="mdi-delete" size="x-small" variant="text" color="error" @click="deleteEvent(ev.id)" />
                </template>
              </v-list-item>
            </v-list>
          </div>
        </div>

      </template>
    </template>

    <!-- ── Add Event Dialog ── -->
    <v-dialog v-model="showAddEventDialog" max-width="640" :fullscreen="mobile">
      <v-card class="dialog-card">
        <v-card-title class="dialog-title">
          <v-icon icon="mdi-calendar-plus" color="primary" class="mr-2" />
          Добавить мероприятие
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="showAddEventDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pa-4">
          <v-alert type="info" variant="tonal" density="compact" class="mb-3">
            Это единственное место, где заводятся мероприятия. В заявках, закупках и импорте
            они только выбираются из этого списка — не создавайте копию с другим написанием.
          </v-alert>
          <v-text-field v-model="newEventName" label="Название мероприятия *" variant="outlined" density="compact" class="mb-3" />
          <v-row dense>
            <v-col cols="12" md="6">
              <v-text-field v-model="newEventRegion" label="Регион проведения" variant="outlined" density="compact" hide-details />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field v-model="newEventDateFrom" label="Дата начала" type="date" variant="outlined" density="compact" hide-details />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field v-model="newEventDateTo" label="Дата окончания" type="date" variant="outlined" density="compact" hide-details />
            </v-col>
          </v-row>
          <v-text-field v-model="newEventOrderDecree" label="Реквизиты приказа" variant="outlined" density="compact" class="mt-3" hide-details />
          <v-textarea v-model="newEventPlannedIndicators" label="Плановые показатели (KPI)" variant="outlined" density="compact" rows="2" class="mt-3" hide-details />
          <v-textarea v-model="newEventActualIndicators" label="Фактически достигнутые показатели" variant="outlined" density="compact" rows="2" class="mt-3" hide-details />
          <v-text-field v-model="newEventMediaLink1" label="Ссылка на СМИ 1" variant="outlined" density="compact" class="mt-3" hide-details />
          <v-text-field v-model="newEventMediaLink2" label="Ссылка на СМИ 2" variant="outlined" density="compact" class="mt-2" hide-details />
          <v-text-field v-model="newEventMediaLink3" label="Ссылка на СМИ 3" variant="outlined" density="compact" class="mt-2" hide-details />
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="showAddEventDialog = false">Отмена</v-btn>
          <v-btn color="primary" variant="flat" :disabled="!newEventName.trim()" @click="addEvent">Добавить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Edit Event Dialog ── -->
    <v-dialog v-model="showEditEventDialog" max-width="640" :fullscreen="mobile">
      <v-card class="dialog-card">
        <v-card-title class="dialog-title">
          <v-icon icon="mdi-calendar-edit" color="primary" class="mr-2" />
          Редактировать мероприятие
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="showEditEventDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pa-4">
          <v-text-field v-model="editEventForm.name" label="Название *" variant="outlined" density="compact" class="mb-3" />
          <v-row>
            <v-col cols="12" md="6">
              <v-text-field v-model="editEventForm.region" label="Регион проведения" variant="outlined" density="compact" hide-details />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field v-model="editEventForm.date_from" label="Дата начала" type="date" variant="outlined" density="compact" hide-details />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field v-model="editEventForm.date_to" label="Дата окончания" type="date" variant="outlined" density="compact" hide-details />
            </v-col>
          </v-row>
          <v-text-field v-model="editEventForm.order_decree" label="Реквизиты приказа (номер, дата)" variant="outlined" density="compact" class="mt-3" hide-details />
          <v-textarea v-model="editEventForm.planned_indicators" label="Плановые показатели (KPI)" variant="outlined" density="compact" rows="2" class="mt-3" hide-details />
          <v-textarea v-model="editEventForm.actual_indicators" label="Фактически достигнутые показатели" variant="outlined" density="compact" rows="2" class="mt-3" hide-details />
          <v-text-field v-model="editEventForm.media_link_1" label="Ссылка на СМИ 1" variant="outlined" density="compact" class="mt-3" hide-details />
          <v-text-field v-model="editEventForm.media_link_2" label="Ссылка на СМИ 2" variant="outlined" density="compact" class="mt-2" hide-details />
          <v-text-field v-model="editEventForm.media_link_3" label="Ссылка на СМИ 3" variant="outlined" density="compact" class="mt-2" hide-details />
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="showEditEventDialog = false">Отмена</v-btn>
          <v-btn color="primary" variant="flat" :loading="savingEvent" @click="saveEditEvent">Сохранить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Add Subsidy Dialog ── -->
    <v-dialog v-model="showAddDialog" max-width="520" :fullscreen="mobile">
      <v-card class="dialog-card">
        <v-card-title class="dialog-title">
          <v-icon icon="mdi-plus-circle-outline" color="primary" class="mr-2" />
          Добавить субсидию
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="showAddDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          <v-text-field v-model="form.name" label="Название *" variant="outlined" density="compact" class="mb-3" hide-details />
          <v-row>
            <v-col cols="6">
              <v-text-field v-model.number="form.year" label="Год *" variant="outlined" density="compact" type="number" hide-details />
            </v-col>
            <v-col cols="6">
              <v-text-field v-model.number="form.budget" label="Бюджет, ₽ *" variant="outlined" density="compact" type="number" hide-details />
            </v-col>
          </v-row>
          <ContractorPicker v-model="form.contractor_id" class="mt-3" />
          <v-textarea v-model="form.description" label="Описание" variant="outlined" density="compact" rows="2" class="mt-3" hide-details />
          <v-row dense class="mt-3">
            <v-col cols="12" md="6">
              <v-text-field
                v-model="form.basis_doc_number"
                label="Номер документа-основания"
                hint="№ соглашения о субсидии (например, 831-2025-ВСКС). Используется для авто-связки банковских платежей."
                persistent-hint
                variant="outlined" density="compact"
              />
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field
                v-model="form.basis_doc_date"
                label="Дата документа-основания"
                type="date"
                variant="outlined" density="compact"
              />
            </v-col>
          </v-row>
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="showAddDialog = false">Отмена</v-btn>
          <v-btn color="primary" :loading="saving" :disabled="!form.name || !form.budget" @click="addSubsidy">
            Добавить
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Edit Subsidy Dialog ── -->
    <v-dialog v-model="showEditDialog" max-width="520" :fullscreen="mobile">
      <v-card class="dialog-card">
        <v-card-title class="dialog-title">
          <v-icon icon="mdi-pencil-outline" color="primary" class="mr-2" />
          Редактировать субсидию
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="showEditDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          <v-text-field v-model="editForm.name" label="Название *" variant="outlined" density="compact" class="mb-3" hide-details />
          <v-row>
            <v-col cols="6">
              <v-text-field v-model.number="editForm.year" label="Год *" variant="outlined" density="compact" type="number" hide-details />
            </v-col>
            <v-col cols="6">
              <v-text-field v-model.number="editForm.budget" label="Бюджет, ₽ *" variant="outlined" density="compact" type="number" hide-details />
            </v-col>
          </v-row>
          <ContractorPicker v-model="editForm.contractor_id" :initial-contractor="editInitialContractor" class="mt-3" />
          <v-textarea v-model="editForm.description" label="Описание" variant="outlined" density="compact" rows="2" class="mt-3" hide-details />
          <v-textarea
            v-model="editForm.agreement_text"
            label="Текст соглашения о субсидии (для шаблонов)"
            variant="outlined" density="compact"
            rows="4" auto-grow
            class="mt-3"
            placeholder="Например: Финансирование договора осуществляется в рамках соглашения…"
            hint="Переменная шаблона {{subsidy_agreement_text}}"
            persistent-hint
          />
          <v-row dense class="mt-3">
            <v-col cols="12" md="6">
              <v-text-field
                v-model="editForm.basis_doc_number"
                label="Номер документа-основания"
                hint="№ соглашения о субсидии (например, 831-2025-ВСКС). Используется для авто-связки банковских платежей."
                persistent-hint
                variant="outlined" density="compact"
              />
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field
                v-model="editForm.basis_doc_date"
                label="Дата документа-основания"
                type="date"
                variant="outlined" density="compact"
              />
            </v-col>
          </v-row>
          <v-divider class="mt-4 mb-3" />
          <div class="text-caption text-medium-emphasis mb-2">Реквизиты для шаблонов договоров</div>
          <v-text-field
            v-model="editForm.grantor_name"
            label="Грантодатель (для договоров)"
            hint="Напр. «Российская Федерация» или «Тверская область». Переменная {{subsidy_grantor_name}}"
            persistent-hint
            variant="outlined" density="compact"
            class="mb-3"
          />
          <v-text-field
            v-model="editForm.ministry_name"
            label="Министерство-грантодатель (для договоров)"
            hint="Напр. «МИНИСТЕРСТВОМ МОЛОДЕЖНОЙ ПОЛИТИКИ РФ» (как пишется в тексте договора). Переменная {{subsidy_ministry_name}}"
            persistent-hint
            variant="outlined" density="compact"
            class="mb-3"
          />
          <v-textarea
            v-model="editForm.extra_contract_clause_1"
            label="Доп. пункт договора 1 (зависит от субсидии)"
            hint="Например пункт о раздельном учёте расходов. Вставляется в шаблон как {{subsidy_extra_clause_1}}. Если пусто — пункт пропускается."
            persistent-hint
            rows="3"
            auto-grow
            variant="outlined"
            density="compact"
            class="mb-3"
          />
          <v-textarea
            v-model="editForm.extra_contract_clause_2"
            label="Доп. пункт договора 2 (зависит от субсидии)"
            hint="{{subsidy_extra_clause_2}}. Если пусто — пункт пропускается."
            persistent-hint
            rows="3"
            auto-grow
            variant="outlined"
            density="compact"
          />
          <!-- Настройки плана закупок (только для admin+) -->
          <template v-if="canSaveVersion">
            <v-divider class="mt-4 mb-3" />
            <div class="text-caption text-medium-emphasis mb-2">Настройки плана закупок</div>
            <v-switch
              v-model="editForm.require_planned_dates"
              label="Требовать дату потребности у позиций (для помесячного плана)"
              density="compact"
              color="primary"
              hide-details
              class="mb-2"
            />
            <v-alert
              v-if="!editForm.require_planned_dates"
              type="warning"
              density="compact"
              variant="tonal"
              class="mt-2"
            >
              Без дат плановые траты по месяцам считаться не будут
            </v-alert>
          </template>
          <v-divider class="mt-4 mb-3" />
          <v-text-field
            v-model.number="editForm.ceiling_warn_percent"
            label="Порог предупреждения о подходе к потолку субсидии, %"
            hint="Когда сумма заказанного (включая ежемесячные платежи — весь график) достигнет этого процента от потолка ФЭО, появится предупреждение в карточке субсидии, списке и на дашборде. По умолчанию 90%."
            persistent-hint
            type="number"
            min="1" max="100"
            variant="outlined" density="compact"
            class="mt-1"
          />
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="showEditDialog = false">Отмена</v-btn>
          <v-btn color="primary" :loading="saving" :disabled="!editForm.name || !editForm.budget" @click="updateSubsidy">
            Сохранить
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Delete confirm ── -->
    <v-dialog v-model="showDeleteDialog" max-width="420">
      <v-card class="dialog-card">
        <v-card-title class="dialog-title">
          <v-icon icon="mdi-alert-circle-outline" color="error" class="mr-2" />
          Удалить субсидию
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          <template v-if="deleteErrorLinked">
            <v-alert type="error" variant="tonal" class="mb-3" style="white-space:pre-line">
              {{ deleteErrorMsg || 'Нельзя удалить субсидию: есть связанные записи. Сначала удалите или перепривяжите их.' }}
            </v-alert>
            <v-btn v-if="(deleteImpact?.purchases ?? 0) > 0" block color="primary" variant="tonal"
              prepend-icon="mdi-cart-outline" class="mb-2" @click="goToLinkedPurchases">
              Перейти к закупкам ({{ deleteImpact?.purchases }})
            </v-btn>
            <v-btn v-if="(deleteImpact?.contracts ?? 0) > 0" block color="primary" variant="tonal"
              prepend-icon="mdi-file-document-outline" @click="goToLinkedContracts">
              Перейти к договорам ({{ deleteImpact?.contracts }})
            </v-btn>
          </template>
          <template v-else>
            <div class="mb-2">Удалить <strong>{{ deleteTarget?.name }}</strong>? Действие нельзя отменить.</div>
            <v-alert v-if="deleteImpact && (deleteImpact.feo_categories > 0 || deleteImpact.planned_items > 0)"
              type="warning" variant="tonal" density="compact">
              Вместе с субсидией будет безвозвратно удалено:
              <ul class="mt-1 mb-0" style="padding-left:18px;">
                <li v-if="deleteImpact.feo_categories > 0">{{ deleteImpact.feo_categories }} категорий ФЭО</li>
                <li v-if="deleteImpact.planned_items > 0">{{ deleteImpact.planned_items }} плановых позиций</li>
              </ul>
            </v-alert>
          </template>
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="showDeleteDialog = false">Отмена</v-btn>
          <v-btn v-if="!deleteErrorLinked" color="error" :loading="saving" @click="deleteSubsidy">Удалить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Add FEO category dialog ── -->
    <v-dialog v-model="showAddFeoDialog" max-width="520" :fullscreen="mobile">
      <v-card class="dialog-card">
        <v-card-title class="dialog-title">
          <v-icon icon="mdi-folder-plus-outline" color="primary" class="mr-2" />
          Добавить направление ФЭО
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="showAddFeoDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          <v-autocomplete
            v-model="feoForm.parentId"
            :items="feoCategories.filter(c => c.level < 3)"
            item-title="name" item-value="id"
            label="Родительская категория (необязательно)"
            variant="outlined" density="compact" clearable class="mb-3" hide-details
          />
          <v-text-field v-model="feoForm.name" label="Название *" variant="outlined" density="compact" class="mb-3" hide-details />
          <v-row>
            <v-col cols="6">
              <v-text-field v-model="feoForm.code" label="Код" variant="outlined" density="compact" hide-details />
            </v-col>
            <v-col cols="6">
              <v-text-field v-model="feoForm.appendix" label="Приложение" variant="outlined" density="compact" hide-details />
            </v-col>
          </v-row>
          <v-textarea
            v-model="feoForm.description"
            label="Пояснение (что входит в направление)"
            variant="outlined" density="compact" rows="2" auto-grow hide-details class="mt-3"
          />
          <v-divider class="my-3" />
          <!-- Блок: По документу ФЭО -->
          <div style="border:1px solid rgba(var(--v-border-color),var(--v-border-opacity));border-radius:8px;padding:12px" class="mb-3">
            <div class="text-body-2 font-weight-medium mb-3">По документу ФЭО</div>
            <!-- Финансирование по ФЭО -->
            <div class="d-flex align-center mb-2">
              <span class="text-body-2">Финансирование по ФЭО</span>
              <v-btn-toggle
                v-model="feoForm.budgetAuto"
                mandatory
                density="compact"
                class="ml-4"
                color="primary"
              >
                <v-btn :value="false" size="x-small">Вручную</v-btn>
                <v-btn :value="true" size="x-small">Авто из детей</v-btn>
              </v-btn-toggle>
            </div>
            <v-text-field
              v-if="!feoForm.budgetAuto"
              v-model.number="feoForm.budget"
              label="Сумма финансирования, ₽"
              variant="outlined" density="compact" type="number" hide-details class="mb-3"
            />
            <!-- Кол-во, ед. изм. и стоимость за ед. по ФЭО -->
            <v-row dense>
              <v-col cols="4">
                <v-text-field
                  v-model.number="feoForm.feo_quantity"
                  label="Кол-во по ФЭО"
                  variant="outlined" density="compact" type="number" hide-details
                />
              </v-col>
              <v-col cols="4">
                <v-combobox
                  v-model="feoForm.feo_unit"
                  :items="['шт', 'компл', 'кг', 'л', 'м', 'услуга', 'чел.', 'рейс']"
                  label="Ед. изм. по ФЭО"
                  variant="outlined" density="compact" hide-details
                />
              </v-col>
              <v-col cols="4">
                <v-text-field
                  v-model="feoForm.feo_amount"
                  label="Стоимость за ед. по ФЭО"
                  variant="outlined" density="compact" type="number" hide-details
                  suffix="₽"
                />
              </v-col>
            </v-row>
          </div>
          <!-- Блок: Плановые показатели (CRM) — задача владельца (2026-08-11, Правка 2):
               план вводится именованной плановой позицией внутри категории, а не
               голыми числами на самой категории (planned_quantity/planned_amount) — иначе
               план виден как безымянное число без ответа на вопрос «что именно планируем
               купить». Поля planned_quantity/planned_amount по-прежнему не редактируются
               при создании (см. addFeoCategory) — «Ед. изм.» ниже это единица измерения
               САМОЙ КАТЕГОРИИ (для отображения), а не план.

               План zany-fluttering-mountain.md, п.1/п.5 (2026-08-13): добавлен переключатель
               «Как считать план» — способ теперь ЗАДАЁТСЯ явно, а не угадывается по тому,
               пустые ли поля (это угадывание билось само с собой — см. контекст плана).
               «По плановым позициям» (по умолчанию) — план = Σ позиций категории. «По
               вручную заданной сумме» — ОДНО поле manual_plan_amount, без кол-ва/цены за
               ед. (владелец прямо выбрал одно поле, не количество × цена). -->
          <div style="border:1px solid rgba(var(--v-border-color),var(--v-border-opacity));border-radius:8px;padding:12px">
            <div class="text-body-2 font-weight-medium mb-1">Как считать план</div>
            <v-btn-toggle
              v-model="feoForm.planSource"
              mandatory
              density="compact"
              color="primary"
              class="mb-2"
            >
              <v-btn value="planned_items" size="x-small">По плановым позициям</v-btn>
              <v-btn value="manual_sum" size="x-small">По вручную заданной сумме</v-btn>
            </v-btn-toggle>
            <div class="text-caption text-medium-emphasis mb-3">
              «По плановым позициям» — план складывается из именованных позиций внутри категории (видно, что именно
              планируем купить). «По вручную заданной сумме» — план это одно число; позиции можно вести отдельно,
              но если их сумма превысит его — потребуется согласование.
            </div>
            <v-text-field
              v-if="feoForm.planSource === 'manual_sum'"
              v-model.number="feoForm.manual_plan_amount"
              label="Плановая сумма, ₽"
              variant="outlined" density="compact" type="number" hide-details class="mb-3"
            />
            <v-alert v-else type="info" variant="tonal" density="compact" class="mb-3 text-caption">
              Создайте категорию и нажмите «Добавить плановую позицию» в панели.
            </v-alert>
            <v-combobox
              v-model="feoForm.unit"
              :items="['шт', 'компл', 'кг', 'л', 'м', 'услуга', 'чел.', 'рейс']"
              label="Ед. изм. категории"
              variant="outlined" density="compact" hide-details
            />
          </div>
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="showAddFeoDialog = false">Отмена</v-btn>
          <v-btn color="primary" :loading="savingFeo" :disabled="!feoForm.name || !!feoAddPlanPairError" @click="addFeoCategory">
            Добавить
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Edit FEO category dialog ── -->
    <v-dialog v-model="showEditFeoDialog" max-width="520" :fullscreen="mobile">
      <v-card class="dialog-card">
        <v-card-title class="dialog-title">
          <v-icon icon="mdi-pencil-outline" color="primary" class="mr-2" />
          Редактировать направление ФЭО
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="showEditFeoDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          <v-text-field v-model="feoEditForm.name" label="Название *" variant="outlined" density="compact" class="mb-3" hide-details />
          <v-row>
            <v-col cols="6">
              <v-text-field v-model="feoEditForm.code" label="Код" variant="outlined" density="compact" hide-details />
            </v-col>
            <v-col cols="6">
              <v-text-field v-model="feoEditForm.appendix" label="Приложение" variant="outlined" density="compact" hide-details />
            </v-col>
          </v-row>
          <v-autocomplete
            v-model="feoEditForm.parent_id"
            :items="feoParentOptions"
            item-title="name"
            item-value="id"
            label="Родительская категория"
            variant="outlined"
            density="compact"
            clearable
            class="mt-3"
            hint="Очистите для корневого уровня. Или перетащите в таблице."
            persistent-hint
          />
          <v-textarea
            v-model="feoEditForm.description"
            label="Пояснение (что входит в направление)"
            variant="outlined" density="compact" rows="2" auto-grow hide-details class="mt-3"
          />
          <v-divider class="my-3" />
          <!-- Блок: По документу ФЭО -->
          <div style="border:1px solid rgba(var(--v-border-color),var(--v-border-opacity));border-radius:8px;padding:12px" class="mb-3">
            <div class="text-body-2 font-weight-medium mb-3">По документу ФЭО</div>
            <!-- Финансирование по ФЭО -->
            <div class="d-flex align-center mb-2">
              <span class="text-body-2">Финансирование по ФЭО</span>
              <v-btn-toggle
                v-if="feoEditForm.hasChildren"
                v-model="feoEditForm.budgetAuto"
                mandatory
                density="compact"
                class="ml-4"
                color="primary"
              >
                <v-btn :value="false" size="x-small">Вручную</v-btn>
                <v-btn :value="true" size="x-small">Авто из детей</v-btn>
              </v-btn-toggle>
            </div>
            <v-text-field
              v-if="!feoEditForm.hasChildren || !feoEditForm.budgetAuto"
              v-model.number="feoEditForm.budget"
              label="Сумма финансирования, ₽"
              variant="outlined" density="compact" type="number" hide-details class="mb-2"
            />
            <v-alert
              v-if="feoEditForm.hasChildren && feoEditForm.budgetAuto"
              type="info" variant="tonal" density="compact" class="mb-2 text-caption"
            >
              Сумма рассчитывается автоматически из дочерних направлений
            </v-alert>
            <!-- Кол-во, ед. изм. и стоимость за ед. по ФЭО -->
            <v-row dense>
              <v-col cols="4">
                <v-text-field
                  v-model.number="feoEditForm.feo_quantity"
                  label="Кол-во по ФЭО"
                  variant="outlined" density="compact" type="number" hide-details
                />
              </v-col>
              <v-col cols="4">
                <v-combobox
                  v-model="feoEditForm.feo_unit"
                  :items="['шт', 'компл', 'кг', 'л', 'м', 'услуга', 'чел.', 'рейс']"
                  label="Ед. изм. по ФЭО"
                  variant="outlined" density="compact" hide-details
                />
              </v-col>
              <v-col cols="4">
                <v-text-field
                  v-model="feoEditForm.feo_amount"
                  label="Стоимость за ед. по ФЭО"
                  variant="outlined" density="compact" type="number" hide-details
                  suffix="₽"
                />
              </v-col>
            </v-row>
          </div>
          <!-- Блок: Как считать план — план zany-fluttering-mountain.md, п.1/п.5
               (2026-08-13). Способ теперь ЗАДАЁТСЯ явно переключателем, а не угадывается
               по тому, пустые ли поля planned_quantity/planned_amount (угадывание билось
               само с собой — см. контекст плана, категория 3710). «По вручную заданной
               сумме» — ОДНО поле manual_plan_amount (не количество × цена — владелец
               прямо выбрал одно поле). Переключение на «ручную сумму» у категории, где
               уже есть плановые позиции (feoEditPlanSourceSwitchWarning), сопровождается
               предупреждением о последствиях: позиции останутся, но план будет считаться
               от суммы, их превышение потребует согласования. -->
          <div style="border:1px solid rgba(var(--v-border-color),var(--v-border-opacity));border-radius:8px;padding:12px" class="mb-3">
            <div class="text-body-2 font-weight-medium mb-1">Как считать план</div>
            <v-btn-toggle
              v-model="feoEditForm.planSource"
              mandatory
              density="compact"
              color="primary"
              class="mb-2"
            >
              <v-btn value="planned_items" size="x-small">По плановым позициям</v-btn>
              <v-btn value="manual_sum" size="x-small">По вручную заданной сумме</v-btn>
            </v-btn-toggle>
            <div class="text-caption text-medium-emphasis mb-3">
              «По плановым позициям» — план складывается из именованных позиций внутри категории (видно, что именно
              планируем купить). «По вручную заданной сумме» — план это одно число; позиции можно вести отдельно,
              но если их сумма превысит его — потребуется согласование.
            </div>

            <v-alert
              v-if="feoEditPlanSourceSwitchWarning"
              type="warning" variant="tonal" density="compact" class="mb-3 text-caption"
            >
              У категории уже есть плановые позиции — они останутся на месте, но план будет считаться от введённой
              суммы. Если сумма позиций превысит её, потребуется согласование превышения.
            </v-alert>

            <template v-if="feoEditForm.planSource === 'manual_sum'">
              <v-text-field
                v-model.number="feoEditForm.manual_plan_amount"
                label="Плановая сумма, ₽"
                variant="outlined" density="compact" type="number" hide-details
              />
            </template>

            <!-- Правка 2Б (2026-08-11): три состояния старого способа отображения плана —
                 (1) есть подкатегории — план считают они; (2) план не задан — подсказка
                 завести плановую позицию; (3) план задан старыми полями категории — только
                 для чтения + перенос в плановую позицию (openConvertManualPlanToItem). Всё
                 показывается только в режиме «по плановым позициям» — режим «по сумме» выше
                 уже закрыл вопрос одним полем. -->
            <template v-else>
              <v-alert
                v-if="feoEditForm.hasChildren"
                type="info" variant="tonal" density="compact" class="text-caption"
              >
                У категории есть подкатегории: план считается по ним, собственный план категории в расчёте не участвует.
              </v-alert>

              <template v-else-if="feoEditManualPlanSet">
                <div class="d-flex align-center flex-wrap mb-2" style="gap:8px">
                  <span class="text-body-2">
                    Плановое количество: <strong>{{ feoEditForm.planned_quantity ?? '—' }} {{ feoEditForm.unit || 'ед.' }}</strong>
                  </span>
                  <v-chip size="x-small" color="orange" variant="tonal">старый формат</v-chip>
                </div>
                <div class="text-body-2 mb-2">
                  Плановая цена за единицу: <strong>{{ feoEditForm.planned_amount != null ? formatCurrency(feoEditForm.planned_amount) : '—' }}</strong>
                </div>
                <div class="text-body-2 mb-3">
                  Плановая сумма: {{ feoEditForm.planned_quantity ?? '—' }} × {{ feoEditForm.planned_amount != null ? formatCurrency(feoEditForm.planned_amount) : '—' }}
                  <template v-if="feoEditForm.planned_quantity != null && feoEditForm.planned_amount != null">
                    = <strong>{{ formatCurrency(Number(feoEditForm.planned_quantity) * Number(feoEditForm.planned_amount)) }}</strong>
                  </template>
                </div>
                <v-alert
                  v-if="feoEditPlanPairError"
                  type="warning" variant="tonal" density="compact" class="mb-3 text-caption"
                >
                  {{ feoEditPlanPairError }}
                </v-alert>
                <div class="text-caption text-medium-emphasis mb-3">
                  План записан полями самой категории, без названия. Перенесите его в плановую позицию — тогда будет
                  видно, что именно запланировано, и позицию можно будет править.
                </div>
                <v-btn size="small" variant="tonal" color="teal" prepend-icon="mdi-swap-horizontal" @click="convertCategoryEditPlanToItem">
                  Перенести в плановую позицию
                </v-btn>
              </template>

              <template v-else>
                <v-alert type="info" variant="tonal" density="compact" class="mb-3 text-caption">
                  План задаётся плановой позицией внутри категории: нажмите «Добавить плановую позицию» ниже. Так у
                  плана будет название (что именно планируем купить), а не просто число.
                </v-alert>
                <v-btn size="small" variant="tonal" color="teal" prepend-icon="mdi-playlist-plus" @click="openAddPlannedItemFromCategoryEdit">
                  Добавить плановую позицию
                </v-btn>
              </template>
            </template>
          </div>
          <v-checkbox v-model="feoEditForm.is_active" label="Активна" density="compact" hide-details class="mt-2" />
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="showEditFeoDialog = false">Отмена</v-btn>
          <!-- feoEditPlanPairError НЕ гейтит кнопку (см. ответ в отчёте по Правке 2Б):
               planned_quantity/planned_amount больше не редактируются в этом диалоге,
               мисматч пары может быть только унаследован из БД — категория с таким
               мисматчем обязана сохраняться (иначе «Сохранить» блокируется навсегда
               без способа это поправить из этой формы). Предупреждение всё равно
               показывается пользователю в блоке «старый формат» выше. -->
          <v-btn color="primary" :loading="savingFeo" :disabled="!feoEditForm.name" @click="updateFeoCategory">
            Сохранить
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Delete FEO category dialog ── -->
    <v-dialog v-model="showDeleteFeoDialog" max-width="440">
      <v-card class="dialog-card">
        <v-card-title class="dialog-title">
          <v-icon icon="mdi-alert-circle-outline" color="error" class="mr-2" />
          Удалить направление?
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="showDeleteFeoDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          <div class="mb-2">«{{ feoDeleteTarget?.name }}»</div>
          <v-alert v-if="feoDeleteChildrenCount > 0" type="warning" density="compact" variant="tonal" class="mb-3">
            Будет удалено вместе с {{ feoDeleteChildrenCount }}
            {{ feoDeleteChildrenCount === 1 ? 'дочерней категорией' : 'дочерними категориями' }}
          </v-alert>
          <v-alert v-if="feoDeleteError" type="error" variant="tonal" class="mb-3">
            {{ feoDeleteError }}
            <div class="mt-2">
              <v-btn size="small" variant="tonal" color="primary" prepend-icon="mdi-arrow-right"
                @click="showDeleteFeoDialog = false; router.push(`/orders?feo_category_id=${feoDeleteTarget?.id}`)">
                Перейти к закупкам этой категории
              </v-btn>
            </div>
          </v-alert>
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="showDeleteFeoDialog = false">Отмена</v-btn>
          <v-btn v-if="!feoDeleteError" color="error" :loading="savingFeo" @click="deleteFeoCategory">Удалить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── «Приравнять ФЭО к плану» — подтверждение с текущими числами (замечание владельца п.3, 2026-08-12) ── -->
    <v-dialog v-model="alignBudgetDialog.show" max-width="440">
      <v-card class="dialog-card">
        <v-card-title class="dialog-title">
          <v-icon icon="mdi-equal" color="primary" class="mr-2" />
          Приравнять ФЭО к плану?
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="alignBudgetDialog.show = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          <div class="mb-2">«{{ alignBudgetDialog.node?.name }}»</div>
          <div>ФЭО категории станет {{ formatCurrency(alignBudgetDialog.newBudget) }} вместо {{ formatCurrency(alignBudgetDialog.oldBudget) }}</div>
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="alignBudgetDialog.show = false">Отмена</v-btn>
          <v-btn color="primary" :loading="alignBudgetLoading === alignBudgetDialog.node?.id" @click="confirmAlignBudgetToPlan">Приравнять</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Отклонить превышение плана ФЭО — обязательный комментарий (задача владельца 2026-08-05) ── -->
    <v-dialog v-model="excessRejectDialog.show" max-width="440">
      <v-card class="dialog-card">
        <v-card-title class="dialog-title">
          <v-icon icon="mdi-close-circle-outline" color="error" class="mr-2" />
          Отклонить превышение плана
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="excessRejectDialog.show = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          <div class="mb-2">«{{ excessRejectDialog.node?.name }}»</div>
          <v-textarea v-model="excessRejectDialog.comment" label="Причина отклонения" density="comfortable"
            variant="outlined" rows="3" autofocus hide-details="auto" />
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="excessRejectDialog.show = false">Отмена</v-btn>
          <v-btn color="error" :loading="excessDecideLoading === excessRejectDialog.node?.id" @click="submitExcessReject">Отклонить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Редактирование позиции закупки (из дерева ФЭО) ── -->
    <v-dialog v-model="reqItemEdit.show" :max-width="reqItemEditDialogWidth" :fullscreen="mobile">
      <v-card class="dialog-card">
        <v-card-title class="dialog-title">
          <v-icon icon="mdi-pencil-outline" color="primary" class="mr-2" />
          Редактировать позицию
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="reqItemEdit.show = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          <v-text-field v-model="reqItemEdit.form.item_name" label="Название позиции" density="comfortable"
            variant="outlined" class="mb-2" hide-details="auto" />
          <div class="d-flex ga-2 mb-2">
            <v-text-field v-model.number="reqItemEdit.form.quantity" label="Кол-во" type="number" min="0"
              density="comfortable" variant="outlined" hide-details="auto" style="max-width: 130px" />
            <v-text-field v-model="reqItemEdit.form.unit" label="Ед." density="comfortable" variant="outlined"
              hide-details="auto" style="max-width: 100px" />
            <v-text-field v-model.number="reqItemEdit.form.unit_price" label="Цена за ед., ₽" type="number" min="0"
              density="comfortable" variant="outlined" hide-details="auto" />
          </div>
          <div class="text-body-2 text-medium-emphasis mb-3">
            Сумма: <b>{{ formatCurrency((Number(reqItemEdit.form.quantity) || 0) * (Number(reqItemEdit.form.unit_price) || 0)) }}</b>
          </div>
          <FeoTreeSelect
            v-model="reqItemEdit.form.feo_category_id"
            :nodes="reqItemEditFeoNodes"
            :leaves="reqItemEditFeoLeaves"
            label="Категория ФЭО"
          />
          <div class="text-caption text-medium-emphasis mt-1 mb-2">
            Перенос в другую категорию не тратит новых денег — так перерасход и разбирается
          </div>
          <!-- Владелец (2026-08-18): выбор ПЛАНОВОЙ ПОЗИЦИИ внутри выбранной категории —
               без него позиция при переносе в новую категорию находит план только точным
               совпадением имени, иначе молча заводит новую плановую позицию рядом с уже
               подходящей (прод-инцидент «Огнетушитель ОУ-2»). -->
          <FeoPlannedItemsSelect
            v-if="reqItemEdit.form.feo_category_id"
            :model-value="reqItemEditPlanSelection"
            :category-id="reqItemEdit.form.feo_category_id"
            :nodes="reqItemEditFeoNodes"
            :items="reqItemEditPlannedResiduals"
            :amount="reqItemEditPlanAmount"
            :loading="reqItemEditPlannedLoading"
            :prefill="reqItemEditPlanPrefill"
            :purchase-id="reqItemEdit.purchaseId"
            @update:model-value="onReqItemEditPlanSelect"
            @planned-item-created="reloadReqItemEditPlanned"
            @planned-item-deleted="reloadReqItemEditPlanned"
          />
          <div class="text-caption text-medium-emphasis mt-1">
            Можно привязать к существующей плановой позиции или создать новую — если не
            выбирать, система подберёт сама по точному совпадению названия.
          </div>
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="reqItemEdit.show = false">Отмена</v-btn>
          <v-btn color="primary" :loading="reqItemEdit.saving" @click="saveReqItemEdit">Сохранить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Удаление позиции закупки (из дерева ФЭО) ── -->
    <v-dialog v-model="reqItemDelete.show" max-width="480">
      <v-card class="dialog-card">
        <v-card-title class="dialog-title">
          <v-icon icon="mdi-delete-outline" color="error" class="mr-2" />
          Удалить позицию
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          Удалить позицию «<b>{{ reqItemDelete.name }}</b>» из закупки?
          <v-alert type="warning" variant="tonal" density="compact" class="mt-3">
            Позиция будет удалена из закупки, суммы закупки пересчитаются.
          </v-alert>
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="reqItemDelete.show = false">Отмена</v-btn>
          <v-btn color="error" :loading="reqItemDelete.deleting" @click="doReqItemDelete">Удалить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Позиция из заявки: точечное удаление запрещено — объясняем и даём легальный путь ── -->
    <v-dialog v-model="wishBlockedDelete.show" max-width="520">
      <v-card class="dialog-card">
        <v-card-title class="dialog-title">
          <v-icon icon="mdi-information-outline" color="primary" class="mr-2" />
          Позиция создана заявкой №{{ wishBlockedDelete.wishId }}
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          Позиция «<b>{{ wishBlockedDelete.name }}</b>» ({{ wishBlockedDelete.quantity }} {{ wishBlockedDelete.unit || 'шт' }}, {{ formatCurrency(wishBlockedDelete.sum) }} ₽)
          пришла из заявки №{{ wishBlockedDelete.wishId }}.
          <v-alert type="warning" variant="tonal" density="compact" class="mt-3">
            Позиции согласованной заявки нельзя убирать из плана по одной: заявка меняется целиком и уходит на повторное согласование.
          </v-alert>
          <div class="mt-3">
            Чтобы убрать её из плана-графика — откройте заявку и отредактируйте состав. При сохранении она вернётся на согласование и уйдёт из плана автоматически.
          </div>
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="wishBlockedDelete.show = false">Отмена</v-btn>
          <v-btn color="primary" @click="openWishFromBlockedDelete">Открыть заявку</v-btn>
          <v-btn v-if="isSaas" color="warning" :loading="wishBlockedDelete.reverting" @click="revertWishBlockedDeleteToDraft">Вернуть заявку в черновик</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Смена категории ФЭО у wish-позиции ── -->
    <v-dialog v-model="wishItemFeoEdit.show" max-width="520">
      <v-card class="dialog-card">
        <v-card-title class="dialog-title">
          <v-icon icon="mdi-swap-horizontal" color="primary" class="mr-2" />
          Сменить категорию ФЭО
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="wishItemFeoEdit.show = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          <div class="text-body-2 text-medium-emphasis mb-3">
            Позиция: <b>{{ wishItemFeoEdit.itemName }}</b>
          </div>
          <v-select
            v-model="wishItemFeoEdit.selectedCatId"
            :items="leafFeoCategories"
            item-title="name"
            item-value="id"
            label="Категория ФЭО"
            density="comfortable"
            variant="outlined"
            clearable
            hide-details="auto"
            class="mb-3"
          />
          <div class="mt-1">
            <v-btn
              size="small"
              variant="tonal"
              color="orange"
              prepend-icon="mdi-package-variant"
              :loading="wishItemFeoEdit.unallocatedLoading"
              @click="pickWishItemUnallocated"
            >
              ❓ Не определена
            </v-btn>
          </div>
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="wishItemFeoEdit.show = false">Отмена</v-btn>
          <v-btn color="primary" :loading="wishItemFeoEdit.saving" :disabled="wishItemFeoEdit.selectedCatId == null" @click="saveWishItemFeo">Сохранить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Approvers Dialog ── -->
    <v-dialog v-model="showApproversDialog" max-width="700" scrollable :fullscreen="mobile">
      <v-card class="dialog-card">
        <v-card-title class="dialog-title">
          <v-icon icon="mdi-account-multiple" color="teal" class="mr-2" />
          Согласующие: {{ approversSubsidy?.name }}
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="showApproversDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pa-0">
          <v-data-table
            v-resizable-columns="'subsidies-approvers'"
            :headers="approversHeaders"
            :items="approversList"
            :loading="loadingApprovers"
            density="compact"
            hide-default-footer
            :items-per-page="-1"
            no-data-text="Нет согласующих. Добавьте первого."
          >
            <template #item.is_default="{ item }">
              <v-chip v-if="item.is_default" color="success" size="x-small">По умолчанию</v-chip>
            </template>
            <template #item.can_initiate="{ item }">
              <v-chip v-if="item.can_initiate" color="blue" size="x-small">Инициатор</v-chip>
              <v-chip v-if="item.show_feo_path" color="orange" size="x-small" class="ml-1">ФЭО путь</v-chip>
            </template>
            <template #item.order_num="{ item, index }">
              <span class="text-caption text-medium-emphasis">{{ index + 1 }}</span>
            </template>
            <template #item.full_name="{ item }">
              <span v-if="item.role_name === 'Ответственный исполнитель'" class="text-medium-emphasis font-italic">
                — Исполнитель определяется для каждой закупки
              </span>
              <span v-else>{{ item.full_name }}</span>
            </template>
            <template #item.actions="{ item, index }">
              <v-btn icon="mdi-arrow-up" size="x-small" variant="text" :disabled="index === 0" @click="moveApprover(index, -1)" />
              <v-btn icon="mdi-arrow-down" size="x-small" variant="text" :disabled="index === approversList.length - 1" @click="moveApprover(index, 1)" />
              <v-btn icon="mdi-pencil" size="x-small" variant="text" color="primary" @click="startEditApprover(item)" />
              <v-btn icon="mdi-delete" size="x-small" variant="text" color="error" @click="deleteApprover(item)" />
            </template>
          </v-data-table>
        </v-card-text>
        <v-divider />
        <v-card-actions class="px-4 py-3">
          <v-btn variant="outlined" color="indigo" prepend-icon="mdi-content-copy"
                 @click="openCopyApproversDialog">
            Скопировать из другой субсидии
          </v-btn>
          <v-spacer />
          <v-btn color="teal" variant="tonal" prepend-icon="mdi-plus" @click="startAddApprover">
            Добавить
          </v-btn>
          <v-spacer />
          <v-btn variant="text" @click="showApproversDialog = false">Закрыть</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Members (co-editors) Dialog ── -->
    <v-dialog v-model="showMembersDialog" max-width="520" scrollable :fullscreen="mobile">
      <v-card class="dialog-card">
        <v-card-title class="dialog-title">
          <v-icon icon="mdi-account-group" color="deep-purple" class="mr-2" />
          Участники: {{ membersSubsidy?.name }}
          <v-chip class="ml-2" size="x-small" variant="tonal">{{ membersList.length }}</v-chip>
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="showMembersDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pa-4">
          <v-autocomplete
            v-if="canManageMembers"
            v-model="memberToAdd"
            :items="memberUsersList"
            item-title="full_name"
            item-value="id"
            label="Добавить участника"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            :loading="addingMember"
            class="mb-3"
            @update:model-value="(val) => { if (val) addSubsidyMember(val) }"
          />
          <div v-else class="text-caption text-medium-emphasis mb-3">
            Добавлять/удалять участников может автор субсидии или сотрудник с правом «Редактирование субсидий».
          </div>
          <div v-if="loadingMembers" class="d-flex justify-center py-4">
            <v-progress-circular indeterminate color="primary" size="28" />
          </div>
          <div v-else-if="!membersList.length" class="text-caption text-medium-emphasis">Пока нет участников.</div>
          <div v-else class="d-flex flex-wrap" style="gap:8px">
            <v-chip
              v-for="m in membersList"
              :key="m.user_id"
              :closable="canManageMembers"
              @click:close="removeSubsidyMember(m.user_id)"
            >
              {{ m.full_name || m.username || '—' }}
            </v-chip>
          </div>
        </v-card-text>
        <v-divider />
        <v-card-actions class="px-4 py-3">
          <v-spacer />
          <v-btn variant="text" @click="showMembersDialog = false">Закрыть</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Copy Approvers Sub-dialog ── -->
    <v-dialog v-model="showCopyApproversDialog" max-width="520" :fullscreen="mobile">
      <v-card>
        <v-card-title class="d-flex align-center pa-4 pb-2">
          <v-icon icon="mdi-content-copy" color="indigo" class="mr-2" />
          Скопировать согласующих из другой субсидии
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="showCopyApproversDialog = false" />
        </v-card-title>
        <v-card-text>
          <v-autocomplete
            v-model="copyApprovers.sourceId"
            :items="copySourceSubsidies"
            item-title="name"
            item-value="id"
            label="Источник (другая субсидия)"
            variant="outlined" density="compact"
          />
          <v-checkbox
            v-model="copyApprovers.replace"
            label="Заменить существующих (иначе добавить в конец)"
            hide-details density="compact"
          />
          <v-alert v-if="copyApprovers.error" type="error" variant="tonal" density="compact" class="mt-2">
            {{ copyApprovers.error }}
          </v-alert>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="showCopyApproversDialog = false">Отмена</v-btn>
          <v-btn color="indigo" :loading="copyApprovers.loading"
                 :disabled="!copyApprovers.sourceId"
                 @click="confirmCopyApprovers">
            Скопировать
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Approver Add/Edit Dialog ── -->
    <v-dialog v-model="showApproverFormDialog" max-width="480" :persistent="true" :fullscreen="mobile">
      <v-card class="dialog-card">
        <v-card-title class="dialog-title">
          <v-icon :icon="approverEditTarget ? 'mdi-pencil-outline' : 'mdi-plus'" color="teal" class="mr-2" />
          {{ approverEditTarget ? 'Редактировать' : 'Добавить' }} согласующего
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="showApproverFormDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          <v-combobox
            v-model="approverForm.role_name"
            :items="ROLE_SUGGESTIONS"
            label="Роль / Должность *"
            variant="outlined"
            density="compact"
            class="mb-3"
            hide-details
            @update:model-value="onApproverRoleChange"
          />
          <v-alert
            v-if="approverForm.role_name === 'Ответственный исполнитель'"
            type="info"
            variant="tonal"
            density="compact"
            class="mb-3"
            text="Для роли «Ответственный исполнитель» ФИО не указывается — исполнитель определяется для каждой закупки из её данных. Конкретного человека можно выбрать при скачивании листа согласования — поле «Ответственный исполнитель» в диалоге документа."
          />
          <v-autocomplete
            v-if="approverForm.role_name !== 'Ответственный исполнитель'"
            v-model="approverForm.selectedUser"
            :items="approverUsersList"
            item-title="full_name"
            item-value="id"
            label="Сотрудник *"
            variant="outlined"
            density="compact"
            class="mb-1"
            clearable
            return-object
            @update:model-value="onApproverUserSelect"
          />
          <v-alert
            v-if="approverEditTarget && !approverForm.selectedUser"
            type="warning"
            variant="tonal"
            density="compact"
            class="mb-3"
            text="Старая запись без привязки к сотруднику. Выберите сотрудника для сохранения."
          />
          <div v-if="!approverEditTarget || approverForm.selectedUser" class="mb-3" />
          <v-checkbox
            v-model="approverForm.is_default"
            label="Выбирать по умолчанию при генерации документов"
            density="compact"
            hide-details
            class="mb-1"
          />
          <v-checkbox
            v-model="approverForm.can_initiate"
            label="Может быть инициатором служебной записки"
            density="compact"
            hide-details
            class="mb-1"
          />
          <v-checkbox
            v-model="approverForm.show_feo_path"
            label="Показывать путь категории ФЭО в примечании"
            density="compact"
            hide-details
          />
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="showApproverFormDialog = false">Отмена</v-btn>
          <v-btn
            color="teal"
            :loading="savingApprover"
            :disabled="!approverForm.role_name || (approverForm.role_name !== 'Ответственный исполнитель' && !approverForm.selectedUser)"
            @click="saveApprover"
          >
            {{ approverEditTarget ? 'Сохранить' : 'Добавить' }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Templates Dialog (multi-type) ── -->
    <v-dialog v-model="showTemplateDialog" max-width="1100" scrollable :fullscreen="mobile">
      <v-card class="dialog-card">
        <v-card-title class="dialog-title">
          <v-icon icon="mdi-file-document-multiple-outline" color="indigo" class="mr-2" />
          Шаблоны документов
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="showTemplateDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-3">
          <div class="text-caption text-medium-emphasis mb-3">{{ templateSubsidy?.name }}</div>
          <v-alert type="info" variant="tonal" density="compact" class="mb-4" text="Скачайте текущий шаблон (в нём уже расставлены переменные), отредактируйте в Word и загрузите обратно — он будет использоваться для этой субсидии вместо глобального. Список переменных с примерами — ниже, полное руководство — кнопка внизу." />

          <v-list density="compact">
            <v-list-item v-for="t in subsidyTemplatesList" :key="t.doc_type" class="px-0 mb-2">
              <template #prepend>
                <v-icon :color="t.has_custom ? 'green' : 'grey'" class="mr-2">
                  {{ t.has_custom ? 'mdi-check-circle' : 'mdi-circle-outline' }}
                </v-icon>
              </template>
              <template #title>
                <span class="text-body-2 font-weight-medium">{{ t.label }}</span>
                <v-chip v-if="t.has_custom" size="x-small" color="green" variant="tonal" class="ml-2">свой</v-chip>
                <v-chip v-else-if="t.has_global" size="x-small" color="grey" variant="tonal" class="ml-2">глобальный</v-chip>
                <v-chip v-else size="x-small" color="warning" variant="tonal" class="ml-2">нет шаблона</v-chip>
                <v-tooltip v-if="t.has_custom && t.render_ok === false" location="top"
                  text="Шаблон содержит синтаксическую ошибку docxtpl. Загрузите исправленную версию.">
                  <template #activator="{ props: tipProps }">
                    <v-chip v-bind="tipProps" size="x-small" variant="flat" prepend-icon="mdi-alert"
                      class="ml-2" style="background-color:#fb923c; color:white; cursor:default">
                      Шаблон не работает
                    </v-chip>
                  </template>
                </v-tooltip>
              </template>
              <template #append>
                <div class="d-flex gap-1">
                  <v-btn
                    v-if="t.has_custom || t.has_global"
                    icon="mdi-download" variant="text" size="small" color="indigo"
                    title="Скачать текущий шаблон"
                    @click="downloadSubsidyTemplate(t.doc_type)"
                  />
                  <v-btn
                    icon="mdi-upload" variant="text" size="small" color="primary"
                    title="Загрузить свой шаблон"
                    @click="triggerTemplateUpload(t.doc_type)"
                  />
                  <v-btn
                    v-if="t.has_custom"
                    icon="mdi-delete-outline" variant="text" size="small" color="error"
                    title="Удалить — вернётся к глобальному"
                    @click="deleteSubsidyTemplate(t.doc_type)"
                  />
                </div>
              </template>
            </v-list-item>
          </v-list>

          <!-- Template variables reference panel -->
          <v-expansion-panels variant="accordion" class="mt-3">
            <v-expansion-panel title="Доступные переменные шаблона">
              <template #text>
                <v-text-field
                  v-model="varsSearch"
                  prepend-inner-icon="mdi-magnify"
                  label="Поиск по переменной или описанию..."
                  density="compact"
                  hide-details
                  clearable
                  class="mb-2"
                />
                <v-data-table
                  v-resizable-columns="'subsidies-template-vars'"
                  :headers="[
                    { title: 'Переменная', key: 'var', width: '280px', minWidth: '280px' },
                    { title: 'Описание', key: 'description' },
                    { title: 'Пример записи в шаблоне', key: 'example_template', width: '22%' },
                    { title: 'Что получится', key: 'example_result', width: '20%' },
                  ]"
                  :items="filteredVars"
                  density="compact"
                  :items-per-page="-1"
                  hide-default-footer
                  class="text-caption"
                >
                  <template #item.var="{ item }">
                    <div class="d-flex align-center gap-1" style="white-space: nowrap; min-width: 260px;">
                      <v-tooltip :text="item.var" location="top">
                        <template #activator="{ props: tProps }">
                          <code class="text-caption text-truncate" style="max-width: 210px; display: inline-block;" v-bind="tProps">{{ item.var }}</code>
                        </template>
                      </v-tooltip>
                      <v-btn
                        icon size="x-small" variant="text"
                        :title="'Копировать ' + item.var"
                        @click="copyVar(item.var)"
                      >
                        <v-icon size="x-small">mdi-content-copy</v-icon>
                      </v-btn>
                    </div>
                  </template>
                  <template #item.example_template="{ item }">
                    <code class="text-caption">{{ item.example_template }}</code>
                  </template>
                </v-data-table>
              </template>
            </v-expansion-panel>
          </v-expansion-panels>

          <!-- Hidden file input for template upload -->
          <input ref="templateFileInputRef" type="file" accept=".docx" style="display:none"
            @change="onTemplateFileSelected" />
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-btn variant="outlined" prepend-icon="mdi-book-open-variant" color="indigo" @click="downloadMarkupGuide">
            Руководство по переменным
          </v-btn>
          <v-spacer />
          <v-btn variant="outlined" color="indigo" prepend-icon="mdi-content-copy"
                 @click="openCopyTemplatesDialog">
            Скопировать из другой субсидии
          </v-btn>
          <v-spacer />
          <v-btn variant="text" @click="showTemplateDialog = false">Закрыть</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Copy Templates Sub-dialog ── -->
    <v-dialog v-model="showCopyTemplatesDialog" max-width="520" :fullscreen="mobile">
      <v-card>
        <v-card-title class="d-flex align-center pa-4 pb-2">
          <v-icon icon="mdi-content-copy" color="indigo" class="mr-2" />
          Скопировать шаблоны из другой субсидии
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="showCopyTemplatesDialog = false" />
        </v-card-title>
        <v-card-text>
          <v-autocomplete
            v-model="copyTemplates.sourceId"
            :items="copySourceSubsidiesForTemplates"
            item-title="name"
            item-value="id"
            label="Источник (другая субсидия)"
            variant="outlined" density="compact"
          />
          <v-checkbox
            v-model="copyTemplates.replace"
            label="Перезаписать существующие шаблоны"
            hide-details density="compact"
          />
          <v-alert v-if="copyTemplates.error" type="error" variant="tonal" density="compact" class="mt-2">
            {{ copyTemplates.error }}
          </v-alert>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="showCopyTemplatesDialog = false">Отмена</v-btn>
          <v-btn color="indigo" :loading="copyTemplates.loading"
                 :disabled="!copyTemplates.sourceId"
                 @click="confirmCopyTemplates">
            Скопировать
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Contractor Override Dialog ── -->
    <v-dialog v-model="showOverrideDialog" max-width="640" scrollable :fullscreen="mobile">
      <v-card class="dialog-card">
        <v-card-title class="dialog-title">
          <v-icon icon="mdi-account-edit-outline" color="teal" class="mr-2" />
          Реквизиты контрагента для субсидии
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="showOverrideDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4" style="max-height:75vh">
          <v-alert type="info" variant="tonal" density="compact" class="mb-4">
            Эти реквизиты будут использоваться при генерации документов для данной субсидии.
            Если не заполнены — берутся из основной карточки контрагента.
          </v-alert>

          <div class="section-label">Основные данные</div>
          <v-select v-model="overrideForm.org_type" :items="['Юр.лицо','ИП','Самозанятый','Физ.лицо']"
            label="Форма организации" variant="outlined" density="compact" clearable hide-details class="mb-3" />
          <v-row dense>
            <v-col cols="4">
              <v-text-field v-model="overrideForm.inn" label="ИНН" variant="outlined" density="compact" hide-details />
            </v-col>
            <v-col cols="4">
              <v-text-field v-model="overrideForm.kpp" label="КПП" variant="outlined" density="compact" hide-details />
            </v-col>
            <v-col cols="4">
              <v-text-field v-model="overrideForm.ogrn" label="ОГРН" variant="outlined" density="compact" hide-details />
            </v-col>
          </v-row>
          <v-textarea v-model="overrideForm.address" label="Адрес местонахождения" variant="outlined" density="compact" rows="2" class="mt-3" hide-details />
          <v-textarea v-model="overrideForm.postal_address" label="Почтовый адрес" variant="outlined" density="compact" rows="2" class="mt-3" hide-details />

          <div class="section-label mt-4">Подписант</div>
          <v-text-field v-model="overrideForm.signatory_position" label="Должность подписанта" variant="outlined" density="compact" class="mb-2" hide-details />
          <v-row dense class="mb-3">
            <v-col cols="4">
              <v-text-field v-model="overrideForm.signatory_last_name" label="Фамилия" variant="outlined" density="compact" hide-details />
            </v-col>
            <v-col cols="4">
              <v-text-field v-model="overrideForm.signatory_first_name" label="Имя" variant="outlined" density="compact" hide-details />
            </v-col>
            <v-col cols="4">
              <v-text-field v-model="overrideForm.signatory_middle_name" label="Отчество" variant="outlined" density="compact" hide-details />
            </v-col>
          </v-row>
          <v-text-field v-model="overrideForm.signatory_basis" label="На основании чего действует" variant="outlined" density="compact" hide-details
            placeholder="Устава, доверенности №..." />

          <div class="section-label mt-4">Контакты</div>
          <v-row dense class="mb-3">
            <v-col cols="6">
              <v-text-field v-model="overrideForm.org_phone" label="Телефон организации" variant="outlined" density="compact" hide-details />
            </v-col>
            <v-col cols="6">
              <v-text-field v-model="overrideForm.org_email" label="Email организации" variant="outlined" density="compact" hide-details />
            </v-col>
          </v-row>
          <v-text-field v-model="overrideForm.contact_person" label="Контактное лицо" variant="outlined" density="compact" class="mb-3" hide-details />
          <v-row dense>
            <v-col cols="6">
              <v-text-field v-model="overrideForm.phone" label="Телефон контактного лица" variant="outlined" density="compact" hide-details />
            </v-col>
            <v-col cols="6">
              <v-text-field v-model="overrideForm.email" label="Email контактного лица" variant="outlined" density="compact" hide-details />
            </v-col>
          </v-row>

          <div class="section-label mt-4">Банковские реквизиты</div>
          <v-text-field v-model="overrideForm.settlement_account" label="Расчётный счёт (р/с)" variant="outlined" density="compact" class="mb-3" hide-details maxlength="20" />
          <v-text-field v-model="overrideForm.bank_name" label="Банк (наименование)" variant="outlined" density="compact" class="mb-3" hide-details
            placeholder="в ПАО «Сбербанк»..." />
          <v-row dense>
            <v-col cols="6">
              <v-text-field v-model="overrideForm.bik" label="БИК" variant="outlined" density="compact" hide-details maxlength="9" />
            </v-col>
            <v-col cols="6">
              <v-text-field v-model="overrideForm.correspondent_account" label="Корр. счёт (к/с)" variant="outlined" density="compact" hide-details maxlength="20" />
            </v-col>
          </v-row>
          <v-textarea v-model="overrideForm.bank_details" label="Банковские реквизиты (свободное поле)" variant="outlined" density="compact" rows="2" class="mt-3" hide-details />
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="showOverrideDialog = false">Отмена</v-btn>
          <v-btn color="teal" :loading="savingOverride" @click="saveContractorOverride">Сохранить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Import FEO dialog ── -->
    <v-dialog v-model="feoImport.show" max-width="1400" persistent :fullscreen="mobile">
      <v-card class="dialog-card">
        <v-card-title class="dialog-title">
          <v-icon icon="mdi-upload" color="primary" class="mr-2" />
          Импорт категорий ФЭО из Excel
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="closeFeoImport" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">

          <!-- Step 1: File upload -->
          <template v-if="feoImport.step === 1">
            <v-alert type="info" variant="tonal" density="compact" class="mb-4" icon="mdi-information-outline">
              <div class="text-body-2">
                <strong>Поддерживаемые форматы:</strong> Excel (.xlsx, .xls), Word (.docx), PDF<br>
                <strong>Название листа:</strong> любое — система прочитает первый лист (или предложит выбрать)<br>
                <strong>Заголовки столбцов:</strong> система автоматически найдёт строку с заголовками по ключевым словам
                (субсидия, направление, уровень, количество и т.д.). Заголовки могут быть в любой строке — не обязательно в первой.<br>
                <strong>На следующем шаге</strong> вы увидите распознанные столбцы и сможете вручную указать,
                какой столбец соответствует какому полю.
              </div>
            </v-alert>
            <v-file-input
              v-model="feoImport.fileList"
              label="Выберите файл (Excel, PDF или Word)"
              accept=".xlsx,.xls,.pdf,.docx,.doc"
              variant="outlined" density="compact"
              prepend-icon="mdi-file-upload"
              show-size
              hint="Перетащите файл сюда или нажмите для выбора"
              persistent-hint
              @update:model-value="feoImport.file = Array.isArray($event) ? ($event[0] ?? null) : ($event ?? null)"
            />
          </template>

          <!-- Step 2: Column mapping -->
          <template v-if="feoImport.step === 2 && feoImport.previewData">
            <v-alert v-if="feoCurrentSheet" type="info" variant="tonal" density="compact" class="mb-3" icon="mdi-file-table-outline">
              <strong>Лист:</strong> {{ feoCurrentSheet.name }} ({{ feoCurrentSheet.total_rows }} строк данных)
            </v-alert>
            <v-select
              v-if="feoImport.previewData.sheets.length > 1"
              v-model="feoImport.selectedSheet"
              :items="feoImport.previewData.sheets.map((s: any) => ({ title: `${s.name} (${s.total_rows} строк)`, value: s.name }))"
              label="Сменить лист" variant="outlined" density="compact" class="mb-3"
              @update:model-value="feoAutoMap(feoCurrentSheet?.headers || [])"
            />
            <v-select
              v-model="feoImportTargetSubsidy"
              :items="allSubsidies"
              item-title="name" item-value="id"
              label="Субсидия назначения (для строк без столбца «Субсидия»)"
              variant="outlined" density="compact" clearable class="mb-3"
              hint="Если в файле колонка «Субсидия» пустая — все строки будут отнесены к выбранной субсидии"
              persistent-hint />

            <div class="feo-imap-grid">
              <div v-for="target in FEO_TARGET_FIELDS" :key="target.value"
                class="feo-imap-col"
                :class="{
                  'feo-imap-col--over': feoDragOverTarget === target.value,
                  'feo-imap-col--filled': feoIsTargetFilled(target.value),
                  'feo-imap-col--required': target.required && !feoIsTargetFilled(target.value),
                }"
                @dragover.prevent="feoDragOverTarget = target.value"
                @dragleave="feoDragOverTarget = null"
                @drop.prevent="feoOnDropToTarget(target.value, $event)">
                <div class="feo-imap-col-hdr">{{ target.title }}<span v-if="target.required" style="color:#e53935">*</span></div>
                <div class="feo-imap-col-body">
                  <div v-if="feoIsTargetFilled(target.value)"
                    class="feo-imap-card"
                    draggable="true"
                    @dragstart="feoOnDragStart(feoDragMapping[target.value] as number, $event)">
                    <div class="feo-imap-card-row">
                      <span class="feo-imap-card-name">{{ feoGetColumnLabel(feoDragMapping[target.value] as number) }}</span>
                      <button class="feo-imap-card-x" @click.stop="feoUnmapTarget(target.value)">×</button>
                    </div>
                    <div class="feo-imap-card-samples">{{ feoGetSamples(feoDragMapping[target.value] as number).join(', ') || '—' }}</div>
                  </div>
                  <div v-else class="feo-imap-col-empty">—</div>
                </div>
              </div>
            </div>

            <div class="feo-imap-unresolved mt-3"
              :class="{ 'feo-imap-unresolved--over': feoDragOverTarget === '_unresolved' }"
              @dragover.prevent="feoDragOverTarget = '_unresolved'"
              @dragleave="feoDragOverTarget = null"
              @drop.prevent="feoOnDropToUnresolved($event)">
              <span class="feo-imap-unresolved-label">Не определилось</span>
              <div class="d-flex gap-2 flex-wrap mt-1">
                <template v-for="(_, idx) in feoCurrentHeaders" :key="idx">
                  <div v-if="!feoIsMapped(idx) && !feoIsIgnored(idx)"
                    class="feo-imap-card feo-imap-card--free"
                    draggable="true"
                    @dragstart="feoOnDragStart(idx, $event)">
                    <div class="feo-imap-card-row">
                      <span class="feo-imap-card-name">{{ feoGetColumnLabel(idx) }}</span>
                      <button class="feo-imap-card-x feo-imap-card-x--grey" title="Убрать" @click.stop="feoIgnoreColumn(idx)">×</button>
                    </div>
                    <div class="feo-imap-card-samples">{{ feoGetSamples(idx).join(', ') || '—' }}</div>
                  </div>
                </template>
                <span v-if="feoUnmappedCount === 0" style="font-size:11px;color:#888;align-self:center">все распределены ✓</span>
              </div>
            </div>

            <v-alert v-if="!feoMappingValid" type="warning" density="compact" icon="mdi-alert" class="mt-3">
              Укажите столбцы «Субсидия» и «Уровень 2 / Направление»
            </v-alert>
          </template>

          <!-- Step 3: Dry-run preview (прогноз перед записью) -->
          <template v-if="feoImport.step === 3">
            <v-alert type="info" variant="tonal" density="compact" class="mb-3" icon="mdi-clipboard-text-search-outline">
              Это <strong>прогноз</strong> — данные ещё не записаны в базу. Проверьте результат и нажмите «Импортировать».
            </v-alert>
            <div v-if="feoImport.dryResult" class="d-flex flex-wrap gap-2 mb-3">
              <v-chip color="success" variant="flat"
                :disabled="!feoImport.dryResult.created_details?.length"
                @click="feoToggleResultPanel('dry_created')">
                <v-icon icon="mdi-plus-circle" start size="16" />Будет создано: {{ feoImport.dryResult.created ?? 0 }}
                <v-icon v-if="feoImport.dryResult.created_details?.length" end size="16"
                  :icon="feoResultPanels.includes('dry_created') ? 'mdi-chevron-up' : 'mdi-chevron-down'" />
              </v-chip>
              <v-chip color="warning" variant="flat"
                :disabled="!feoImport.dryResult.updated_details?.length"
                @click="feoToggleResultPanel('dry_updated')">
                <v-icon icon="mdi-pencil" start size="16" />Будет обновлено: {{ feoImport.dryResult.updated ?? 0 }}
                <v-icon v-if="feoImport.dryResult.updated_details?.length" end size="16"
                  :icon="feoResultPanels.includes('dry_updated') ? 'mdi-chevron-up' : 'mdi-chevron-down'" />
              </v-chip>
              <v-chip color="grey" variant="flat"
                :disabled="!feoImport.dryResult.skipped_details?.length"
                @click="feoToggleResultPanel('dry_skipped')">
                <v-icon icon="mdi-debug-step-over" start size="16" />Будет пропущено: {{ feoImport.dryResult.skipped }}
                <v-icon v-if="feoImport.dryResult.skipped_details?.length" end size="16"
                  :icon="feoResultPanels.includes('dry_skipped') ? 'mdi-chevron-up' : 'mdi-chevron-down'" />
              </v-chip>
            </div>
            <!-- Предупреждения dry-run -->
            <template v-if="feoImport.dryResult?.warnings?.length">
              <div class="text-subtitle-2 mb-1 text-warning">Предупреждения ({{ feoImport.dryResult.warnings.length }}):</div>
              <v-expansion-panels v-model="feoResultPanels" multiple class="mb-3">
                <v-expansion-panel
                  v-for="kind in [...new Set(feoImport.dryResult.warnings.map(w => w.kind))]"
                  :key="'dw_' + kind"
                  :value="'dw_' + kind">
                  <v-expansion-panel-title>
                    <v-icon icon="mdi-alert-outline" size="18" color="warning" class="mr-2" />
                    {{ feoWarnKindLabel(kind) }} ({{ feoImport.dryResult.warnings.filter(w => w.kind === kind).length }})
                  </v-expansion-panel-title>
                  <v-expansion-panel-text>
                    <v-list density="compact" max-height="280" class="overflow-y-auto">
                      <v-list-item
                        v-for="(w, wi) in feoImport.dryResult.warnings.filter(x => x.kind === kind)"
                        :key="wi"
                        :title="w.name"
                        :subtitle="feoWarnSubtitle(w)" />
                    </v-list>
                  </v-expansion-panel-text>
                </v-expansion-panel>
              </v-expansion-panels>
            </template>
            <!-- Ошибки dry-run — красным, блокируют импорт -->
            <div v-if="feoImport.dryResult?.errors?.length" class="mt-2">
              <div class="text-subtitle-2 mb-1 text-error">Ошибки ({{ feoImport.dryResult.errors.length }}) — исправьте файл перед импортом:</div>
              <v-list density="compact" class="bg-error-lighten-5 rounded">
                <v-list-item v-for="(e, i) in feoImport.dryResult.errors" :key="i"
                  :subtitle="`Стр. ${e.row}: ${e.name} — ${e.message}`" />
              </v-list>
            </div>
            <!-- Детали по категориям (сворачиваемые) -->
            <v-expansion-panels v-if="feoImport.dryResult" v-model="feoResultPanels" multiple class="mb-3">
              <v-expansion-panel v-if="feoImport.dryResult.created_details?.length" value="dry_created">
                <v-expansion-panel-title>
                  <v-icon icon="mdi-plus-circle" size="18" color="success" class="mr-2" />
                  Будет создано ({{ feoImport.dryResult.created_details.length }})
                </v-expansion-panel-title>
                <v-expansion-panel-text>
                  <v-list density="compact" max-height="320" class="overflow-y-auto">
                    <v-list-item v-for="(d, i) in feoImport.dryResult.created_details" :key="i"
                      :title="d.name" :subtitle="`Стр. ${d.row} — ${d.reason}`" />
                  </v-list>
                </v-expansion-panel-text>
              </v-expansion-panel>
              <v-expansion-panel v-if="feoImport.dryResult.updated_details?.length" value="dry_updated">
                <v-expansion-panel-title>
                  <v-icon icon="mdi-pencil" size="18" color="warning" class="mr-2" />
                  Будет обновлено ({{ feoImport.dryResult.updated_details.length }})
                </v-expansion-panel-title>
                <v-expansion-panel-text>
                  <v-list density="compact" max-height="320" class="overflow-y-auto">
                    <v-list-item v-for="(d, i) in feoImport.dryResult.updated_details" :key="i"
                      :title="d.name" :subtitle="`Стр. ${d.row} — ${d.reason}`" />
                  </v-list>
                </v-expansion-panel-text>
              </v-expansion-panel>
              <v-expansion-panel v-if="feoImport.dryResult.skipped_details?.length" value="dry_skipped">
                <v-expansion-panel-title>
                  <v-icon icon="mdi-debug-step-over" size="18" color="grey" class="mr-2" />
                  Будет пропущено ({{ feoImport.dryResult.skipped_details.length }})
                </v-expansion-panel-title>
                <v-expansion-panel-text>
                  <v-list density="compact" max-height="320" class="overflow-y-auto">
                    <v-list-item v-for="(d, i) in feoImport.dryResult.skipped_details" :key="i"
                      :title="d.name" :subtitle="`Стр. ${d.row} — ${d.reason}`" />
                  </v-list>
                </v-expansion-panel-text>
              </v-expansion-panel>
              <v-expansion-panel v-if="feoImport.dryResult.deleted_details?.length" value="dry_deleted">
                <v-expansion-panel-title>
                  <v-icon icon="mdi-delete-outline" size="18" color="error" class="mr-2" />
                  Будет удалено как пустое ({{ feoImport.dryResult.deleted_details.length }})
                </v-expansion-panel-title>
                <v-expansion-panel-text>
                  <v-list density="compact" max-height="240" class="overflow-y-auto">
                    <v-list-item v-for="(d, i) in feoImport.dryResult.deleted_details" :key="i"
                      :title="d.path" :subtitle="d.reason" />
                  </v-list>
                </v-expansion-panel-text>
              </v-expansion-panel>
            </v-expansion-panels>
            <!-- Останется вне новой разбивки — узлы, ждущие решения человека -->
            <template v-if="feoUnmatchedNeedsMapping.length">
              <div class="text-subtitle-2 mb-1 text-error">
                Останется вне новой разбивки ({{ feoUnmatchedNeedsMapping.length }}):
              </div>
              <v-list density="compact" class="bg-error-lighten-5 rounded mb-3">
                <v-list-item v-for="n in feoUnmatchedNeedsMapping" :key="n.id"
                  :title="n.path" :subtitle="feoLoadSummary(n.load)" />
              </v-list>
            </template>
            <v-alert v-if="feoImport.dryResult?.remap_aborted_reason" type="warning" variant="tonal"
              icon="mdi-alert" class="mb-3">
              {{ feoImport.dryResult.remap_aborted_reason }}
            </v-alert>
          </template>

          <!-- Step 4: Remap unmatched nodes (условный — только если есть needs_mapping) -->
          <template v-if="feoImport.step === 4">
            <v-alert type="info" variant="tonal" density="compact" class="mb-3" icon="mdi-source-branch">
              <div class="text-body-2">
                Направления, которых в файле нет вообще, дерево не трогает.<br>
                Узел, которому не выбрали цель, останется в дереве как есть — ничего не теряется.<br>
                Удалённое исчезает из текущего дерева, но остаётся в предыдущей редакции плана закупок —
                она доступна в Истории и выгружается из неё.
              </div>
            </v-alert>

            <v-btn v-if="feoHasSuggestions" size="small" variant="tonal" color="primary" class="mb-3"
              prepend-icon="mdi-auto-fix" @click="feoAcceptAllSuggestions">
              Принять все подсказки
            </v-btn>

            <v-table density="comfortable" class="feo-remap-table">
              <thead>
                <tr>
                  <th style="width:26%">Старый узел</th>
                  <th style="width:28%">Что на нём висит</th>
                  <th style="width:46%">Куда перенести</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="n in feoUnmatchedNeedsMapping" :key="n.id">
                  <td>{{ n.path }}</td>
                  <td>
                    <div>{{ feoLoadSummary(n.load) }}</div>
                    <div v-if="n.blocking_purchases?.length" class="text-caption text-medium-emphasis mt-1">
                      <div v-for="bp in n.blocking_purchases" :key="bp.id" class="d-flex align-center" style="gap:4px">
                        <span class="flex-shrink-0">{{ bp.purchase_number != null ? `№${bp.purchase_number}` : `Закупка #${bp.id}` }}</span>
                        <span v-if="bp.subject" class="text-truncate" style="min-width:0">{{ bp.subject }}</span>
                        <span class="flex-shrink-0">{{ bp.status_label }}</span>
                      </div>
                    </div>
                  </td>
                  <td class="py-2">
                    <div v-if="n.suggestion" class="text-caption mb-1">
                      Похоже на: «{{ n.suggestion }}»<span v-if="n.suggestion_reason"> ({{ n.suggestion_reason }})</span>
                      <v-btn size="x-small" variant="text" color="primary" class="ml-1"
                        @click="feoImport.remap[n.id] = n.suggestion">Принять</v-btn>
                    </div>
                    <v-autocomplete
                      v-model="feoImport.remap[n.id]"
                      :items="feoImport.dryResult?.new_paths || []"
                      clearable density="compact" variant="outlined" hide-details
                      placeholder="Оставить как есть" />
                  </td>
                </tr>
              </tbody>
            </v-table>
          </template>

          <!-- Step 5: Result (после реального импорта) -->
          <template v-if="feoImport.step === 5">
            <div v-if="feoImport.result" class="d-flex flex-wrap gap-2 mb-3">
              <v-chip color="success" variant="flat"
                :disabled="!feoImport.result.created_details?.length"
                @click="feoToggleResultPanel('created')">
                <v-icon icon="mdi-plus-circle" start size="16" />Создано: {{ feoImport.result.created ?? 0 }}
                <v-icon v-if="feoImport.result.created_details?.length" end size="16"
                  :icon="feoResultPanels.includes('created') ? 'mdi-chevron-up' : 'mdi-chevron-down'" />
              </v-chip>
              <v-chip color="warning" variant="flat"
                :disabled="!feoImport.result.updated_details?.length"
                @click="feoToggleResultPanel('updated')">
                <v-icon icon="mdi-pencil" start size="16" />Обновлено: {{ feoImport.result.updated ?? 0 }}
                <v-icon v-if="feoImport.result.updated_details?.length" end size="16"
                  :icon="feoResultPanels.includes('updated') ? 'mdi-chevron-up' : 'mdi-chevron-down'" />
              </v-chip>
              <v-chip color="grey" variant="flat"
                :disabled="!feoImport.result.skipped_details?.length"
                @click="feoToggleResultPanel('skipped')">
                <v-icon icon="mdi-debug-step-over" start size="16" />Пропущено: {{ feoImport.result.skipped }}
                <v-icon v-if="feoImport.result.skipped_details?.length" end size="16"
                  :icon="feoResultPanels.includes('skipped') ? 'mdi-chevron-up' : 'mdi-chevron-down'" />
              </v-chip>
            </div>
            <v-expansion-panels v-if="feoImport.result" v-model="feoResultPanels" multiple class="mb-3">
              <v-expansion-panel v-if="feoImport.result.created_details?.length" value="created">
                <v-expansion-panel-title>
                  <v-icon icon="mdi-plus-circle" size="18" color="success" class="mr-2" />
                  Созданные позиции ({{ feoImport.result.created_details.length }})
                </v-expansion-panel-title>
                <v-expansion-panel-text>
                  <v-list density="compact" max-height="320" class="overflow-y-auto">
                    <v-list-item v-for="(d, i) in feoImport.result.created_details" :key="i"
                      :title="d.name" :subtitle="`Стр. ${d.row} — ${d.reason}`" />
                  </v-list>
                </v-expansion-panel-text>
              </v-expansion-panel>
              <v-expansion-panel v-if="feoImport.result.updated_details?.length" value="updated">
                <v-expansion-panel-title>
                  <v-icon icon="mdi-pencil" size="18" color="warning" class="mr-2" />
                  Обновлённые позиции ({{ feoImport.result.updated_details.length }})
                </v-expansion-panel-title>
                <v-expansion-panel-text>
                  <v-list density="compact" max-height="320" class="overflow-y-auto">
                    <v-list-item v-for="(d, i) in feoImport.result.updated_details" :key="i"
                      :title="d.name" :subtitle="`Стр. ${d.row} — ${d.reason}`" />
                  </v-list>
                </v-expansion-panel-text>
              </v-expansion-panel>
              <v-expansion-panel v-if="feoImport.result.skipped_details?.length" value="skipped">
                <v-expansion-panel-title>
                  <v-icon icon="mdi-debug-step-over" size="18" color="grey" class="mr-2" />
                  Пропущенные позиции ({{ feoImport.result.skipped_details.length }})
                </v-expansion-panel-title>
                <v-expansion-panel-text>
                  <v-list density="compact" max-height="320" class="overflow-y-auto">
                    <v-list-item v-for="(d, i) in feoImport.result.skipped_details" :key="i"
                      :title="d.name" :subtitle="`Стр. ${d.row} — ${d.reason}`" />
                  </v-list>
                </v-expansion-panel-text>
              </v-expansion-panel>
            </v-expansion-panels>
            <!-- Итоги переезда/удаления узлов -->
            <div v-if="feoImport.result?.relinked_count || feoImport.result?.deleted_count" class="text-body-2 mb-2">
              <div v-if="feoImport.result?.relinked_count">Перенесено ссылок: {{ feoImport.result.relinked_count }}</div>
              <div v-if="feoImport.result?.deleted_count">Удалено узлов: {{ feoImport.result.deleted_count }}</div>
            </div>
            <v-alert v-if="feoImport.result?.version_created" type="info" variant="tonal" density="compact"
              icon="mdi-history" class="mb-3">
              Создана предыдущая редакция плана закупок (доступна в истории для выгрузки)
            </v-alert>
            <v-expansion-panels v-if="feoImport.result?.deleted_details?.length || feoImport.result?.remap_applied?.length"
              v-model="feoResultPanels" multiple class="mb-3">
              <v-expansion-panel v-if="feoImport.result?.deleted_details?.length" value="result_deleted">
                <v-expansion-panel-title>
                  <v-icon icon="mdi-delete-outline" size="18" color="error" class="mr-2" />
                  Удалённые узлы ({{ feoImport.result.deleted_details.length }})
                </v-expansion-panel-title>
                <v-expansion-panel-text>
                  <v-list density="compact" max-height="240" class="overflow-y-auto">
                    <v-list-item v-for="(d, i) in feoImport.result.deleted_details" :key="i"
                      :title="d.path" :subtitle="d.reason" />
                  </v-list>
                </v-expansion-panel-text>
              </v-expansion-panel>
              <v-expansion-panel v-if="feoImport.result?.remap_applied?.length" value="result_remap">
                <v-expansion-panel-title>
                  <v-icon icon="mdi-swap-horizontal" size="18" color="primary" class="mr-2" />
                  Перенесённые узлы ({{ feoImport.result.remap_applied.length }})
                </v-expansion-panel-title>
                <v-expansion-panel-text>
                  <v-list density="compact" max-height="280" class="overflow-y-auto">
                    <v-list-item v-for="(r, i) in feoImport.result.remap_applied" :key="i"
                      :title="`${r.old_path} → ${r.new_path}`" />
                  </v-list>
                </v-expansion-panel-text>
              </v-expansion-panel>
            </v-expansion-panels>
            <!-- Предупреждения итогового импорта (те же kinds, но факт, не прогноз) -->
            <template v-if="feoImport.result?.warnings?.length">
              <div class="text-subtitle-2 mb-1 text-warning">Предупреждения ({{ feoImport.result.warnings.length }}):</div>
              <v-expansion-panels v-model="feoResultPanels" multiple class="mb-3">
                <v-expansion-panel
                  v-for="kind in [...new Set(feoImport.result.warnings.map(w => w.kind))]"
                  :key="'rw_' + kind"
                  :value="'rw_' + kind">
                  <v-expansion-panel-title>
                    <v-icon icon="mdi-alert-outline" size="18" color="warning" class="mr-2" />
                    {{ feoWarnKindLabel(kind) }} ({{ feoImport.result.warnings!.filter(w => w.kind === kind).length }})
                  </v-expansion-panel-title>
                  <v-expansion-panel-text>
                    <v-list density="compact" max-height="280" class="overflow-y-auto">
                      <v-list-item
                        v-for="(w, wi) in feoImport.result.warnings!.filter(x => x.kind === kind)"
                        :key="wi"
                        :title="w.name"
                        :subtitle="feoWarnSubtitle(w)" />
                    </v-list>
                  </v-expansion-panel-text>
                </v-expansion-panel>
              </v-expansion-panels>
            </template>
            <div v-if="feoImport.result?.errors?.length" class="mt-2">
              <div class="text-subtitle-2 mb-1 text-error">Ошибки ({{ feoImport.result.errors.length }}):</div>
              <v-list density="compact" class="bg-error-lighten-5 rounded">
                <v-list-item v-for="(e, i) in feoImport.result.errors" :key="i"
                  :subtitle="`Стр. ${e.row}: ${e.name} — ${e.message}`" />
              </v-list>
            </div>
          </template>

        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-btn v-if="feoImport.step === 2" variant="text" @click="feoImport.step = 1">
            <v-icon icon="mdi-arrow-left" class="mr-1" /> Назад
          </v-btn>
          <v-btn v-if="feoImport.step === 3" variant="text" @click="feoImport.step = 2">
            <v-icon icon="mdi-arrow-left" class="mr-1" /> Назад к сопоставлению
          </v-btn>
          <v-btn v-if="feoImport.step === 4" variant="text" @click="feoImport.step = 3">
            <v-icon icon="mdi-arrow-left" class="mr-1" /> Назад
          </v-btn>
          <v-spacer />
          <v-btn variant="text" @click="closeFeoImport">{{ feoImport.step === 5 ? 'Закрыть' : 'Отмена' }}</v-btn>
          <v-btn v-if="feoImport.step === 1" color="primary" :loading="feoImport.loading"
            :disabled="!feoImport.file" @click="doFeoImport">Далее</v-btn>
          <!-- Шаг 2: запускает dry-run → шаг 3 (Проверка) -->
          <v-btn v-if="feoImport.step === 2" color="primary" variant="flat"
            :loading="feoImport.loading" :disabled="!feoMappingValid"
            @click="doFeoMappedImport(true)">Проверить</v-btn>
          <!-- Шаг 3: если есть несопоставленные узлы — на шаг 4 (Сопоставление), иначе сразу реальный импорт → шаг 5 -->
          <v-btn v-if="feoImport.step === 3 && feoUnmatchedNeedsMapping.length" color="primary" variant="flat"
            :disabled="!!(feoImport.dryResult?.errors?.length)"
            @click="feoImport.step = 4">Сопоставить ({{ feoUnmatchedNeedsMapping.length }})</v-btn>
          <v-btn v-if="feoImport.step === 3 && !feoUnmatchedNeedsMapping.length" color="success" variant="flat"
            :loading="feoImport.loading"
            :disabled="!!(feoImport.dryResult?.errors?.length)"
            @click="doFeoMappedImport(false)">Импортировать<template v-if="feoImport.dryResult?.deleted_count">, удалить {{ feoImport.dryResult.deleted_count }}</template></v-btn>
          <!-- Шаг 4: пересчитать прогноз с текущим remap или перейти к реальному импорту → шаг 5 -->
          <v-btn v-if="feoImport.step === 4" variant="tonal" :loading="feoImport.loading"
            @click="doFeoMappedImport(true, true)">
            <v-icon icon="mdi-refresh" class="mr-1" /> Пересчитать
          </v-btn>
          <v-btn v-if="feoImport.step === 4" color="success" variant="flat"
            :loading="feoImport.loading"
            :disabled="!!(feoImport.dryResult?.errors?.length)"
            @click="doFeoMappedImport(false)">{{ feoStep4MainLabel }}</v-btn>
          <v-btn v-if="feoImport.step === 5" color="primary" variant="flat"
            @click="closeFeoImport">Готово</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Диалог редактирования плановой позиции ── -->
    <v-dialog v-model="editPlannedDialog.show" max-width="480" :fullscreen="mobile">
      <v-card>
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">
          <v-icon icon="mdi-pencil" color="blue" class="mr-2" />Редактировать плановую позицию
        </v-card-title>
        <v-card-text class="px-4 pb-2">
          <v-text-field v-model="editPlannedDialog.name" label="Наименование" variant="outlined" density="compact" class="mb-2" autofocus />
          <v-row dense>
            <v-col cols="5">
              <v-text-field v-model="editPlannedDialog.quantity" label="Кол-во" type="number" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="7">
              <v-text-field v-model="editPlannedDialog.unit" label="Ед. изм." variant="outlined" density="compact" />
            </v-col>
          </v-row>
          <!-- Цена за единицу (владелец, 2026-09-02) — необязательное поле, то же
               поведение, что в диалоге создания (FeoPlannedItemsSelect.vue): задана —
               «Сумма (план)» ниже считается сама (кол-во × цена) и недоступна для
               ручного ввода; не задана — обычное поле, сумма вводится руками. -->
          <v-text-field
            v-if="editPlannedDialog.payment_mode !== 'monthly'"
            v-model.number="editPlannedDialog.unitPrice"
            type="number"
            label="Цена за единицу, ₽ (необязательно)"
            variant="outlined"
            density="compact"
            class="mb-1"
          />
          <v-text-field
            v-model="editPlannedDialog.amount"
            label="Сумма (план), ₽" type="number"
            variant="outlined" density="compact"
            :readonly="editAmountIsComputed"
            :bg-color="editAmountIsComputed ? 'grey-lighten-4' : undefined"
            :class="editPlannedDialog.payment_mode === 'monthly' ? 'd-none' : 'mb-1'"
          />
          <div
            v-if="editPlannedDialog.payment_mode !== 'monthly'"
            class="text-caption text-medium-emphasis mb-2"
            style="line-height:1.35"
          >
            <v-icon icon="mdi-information-outline" size="13" style="margin-top:-2px" class="mr-1" />{{ editPriceCaption }}
          </div>
          <!-- Происхождение (владелец, 2026-09-01) — ДВЕ НЕЗАВИСИМЫЕ галочки, тот же
               смысл, что и в диалоге создания. Правка доступна только тому, кто может
               редактировать ФЭО — этот диалог уже за той же вкладкой (feo_categories). -->
          <div class="text-caption text-medium-emphasis mb-1">Происхождение позиции</div>
          <v-checkbox v-model="editPlannedDialog.is_feo_breakdown" density="compact" hide-details class="mb-1">
            <template #label>
              <div>
                <div style="line-height:1.2">По ФЭО</div>
                <div class="text-caption text-medium-emphasis" style="line-height:1.2">жёсткая разбивка ФЭО — покупать будут именно это, отчётность строгая</div>
              </div>
            </template>
          </v-checkbox>
          <v-checkbox v-model="editPlannedDialog.is_internal_plan" density="compact" hide-details class="mb-3">
            <template #label>
              <div>
                <div style="line-height:1.2">Внутренний план</div>
                <div class="text-caption text-medium-emphasis" style="line-height:1.2">в ФЭО была более широкая категория (или позиции не было) — разбивку придумали сами</div>
              </div>
            </template>
          </v-checkbox>
          <!-- Тип платежа -->
          <div class="text-caption text-medium-emphasis mb-1">Тип платежа</div>
          <v-btn-toggle
            v-model="editPlannedDialog.payment_mode"
            mandatory density="compact" variant="outlined" divided
            class="mb-3"
          >
            <v-btn value="one_time" size="small">Разовый</v-btn>
            <v-btn value="monthly" size="small">Ежемесячный</v-btn>
          </v-btn-toggle>
          <!-- Разовый: дата потребности -->
          <v-text-field
            v-if="editPlannedDialog.payment_mode === 'one_time'"
            v-model="editPlannedDialog.planned_date"
            label="Дата потребности"
            type="date"
            variant="outlined" density="compact"
            class="mb-2"
          />
          <!-- Ежемесячный: поля -->
          <template v-if="editPlannedDialog.payment_mode === 'monthly'">
            <v-text-field
              v-model="editPlannedDialog.monthly_start_date"
              label="Первый платёж"
              type="date"
              variant="outlined" density="compact"
              class="mb-2"
            />
            <v-row dense>
              <v-col cols="6">
                <v-text-field
                  v-model.number="editPlannedDialog.months_count"
                  label="Кол-во месяцев"
                  type="number"
                  variant="outlined" density="compact"
                />
              </v-col>
              <v-col cols="6">
                <v-text-field
                  v-model.number="editPlannedDialog.monthly_amount"
                  label="Платёж за месяц, ₽"
                  type="number"
                  variant="outlined" density="compact"
                />
              </v-col>
            </v-row>
            <div
              v-if="editPlannedDialog.monthly_amount && editPlannedDialog.months_count"
              class="text-caption text-medium-emphasis mb-2"
            >
              Итого по позиции: {{ ((editPlannedDialog.monthly_amount ?? 0) * (editPlannedDialog.months_count ?? 0)).toLocaleString('ru-RU') }} ₽
            </div>
          </template>
        </v-card-text>
        <v-card-actions class="px-4 pb-3">
          <v-spacer />
          <v-btn variant="text" @click="editPlannedDialog.show = false">Отмена</v-btn>
          <v-btn color="primary" variant="tonal" :loading="editPlannedDialog.saving" @click="saveEditPlannedItem">Сохранить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Диалог редактирования ручного плана категории (синтетическая строка «ручной
         план ФЭО» в панели, planned.isManual) — правит planned_quantity/planned_amount/
         unit НА КАТЕГОРИИ, а не заводит FeoPlannedItem (для этого рядом отдельная кнопка). ── -->
    <v-dialog v-model="editCategoryPlanDialog.show" max-width="440" :fullscreen="mobile">
      <v-card>
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">
          <v-icon icon="mdi-pencil-ruler" color="blue" class="mr-2" />
          Редактировать план категории
        </v-card-title>
        <v-card-text class="px-4 pb-2">
          <div class="text-caption text-medium-emphasis mb-3">{{ editCategoryPlanDialog.categoryName }}</div>
          <v-row dense>
            <v-col cols="6">
              <v-text-field
                v-model="editCategoryPlanDialog.quantity"
                label="Плановое количество" type="number"
                variant="outlined" density="compact" autofocus
              />
            </v-col>
            <v-col cols="6">
              <v-text-field
                v-model="editCategoryPlanDialog.unitPrice"
                label="Плановая цена за единицу, ₽" type="number"
                variant="outlined" density="compact"
              />
            </v-col>
          </v-row>
          <v-combobox
            v-model="editCategoryPlanDialog.unit"
            :items="CATEGORY_UNIT_OPTIONS"
            label="Единица измерения"
            variant="outlined" density="compact" class="mb-1"
            :color="isCategoryUnitSuspicious ? 'warning' : undefined"
          />
          <div v-if="isCategoryUnitSuspicious" class="text-caption mb-2" style="color:#B45309;display:flex;align-items:flex-start;gap:4px">
            <v-icon icon="mdi-alert" size="14" style="margin-top:2px" />
            <span>Похоже на число, а не единицу измерения — след старого импорта со сдвигом колонок. Выберите единицу из списка или введите свою.</span>
          </div>
          <div class="text-caption text-medium-emphasis mt-2" style="border-top:1px solid #e2e8f0;padding-top:8px">
            Плановая сумма (кол-во × цена):
            <span class="font-weight-medium" :style="editCategoryPlanSum != null ? 'color:#0f766e' : ''">
              {{ editCategoryPlanSum != null ? formatCurrency(editCategoryPlanSum) : '—' }}
            </span>
          </div>
        </v-card-text>
        <v-card-actions class="px-4 pb-3">
          <v-spacer />
          <v-btn variant="text" @click="editCategoryPlanDialog.show = false">Отмена</v-btn>
          <v-btn color="primary" variant="tonal" :loading="editCategoryPlanDialog.saving" @click="saveEditCategoryPlan">Сохранить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Диалог сопоставления позиций ── -->
    <v-dialog v-model="showMapDialog" max-width="520" :fullscreen="mobile">
      <v-card>
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">
          <v-icon icon="mdi-link-variant" color="teal" class="mr-2" />
          Сопоставить с плановой позицией
        </v-card-title>
        <v-card-text>
          <div v-if="mapTarget" class="mb-3">
            <div class="text-caption text-medium-emphasis mb-1">Фактическая позиция:</div>
            <div class="font-weight-medium">{{ mapTarget.item_name }}</div>
            <div class="text-caption text-medium-emphasis">Контрагент: {{ mapTarget.contractor_name || '—' }}</div>
          </div>
          <div class="text-caption text-medium-emphasis mb-2">Выберите плановую позицию:</div>
          <v-list density="compact" v-if="mapCategoryId && comparisonData[mapCategoryId]">
            <v-list-item
              v-for="planned in comparisonData[mapCategoryId].planned"
              :key="planned.id"
              :title="planned.name"
              :subtitle="planned.quantity ? `${planned.quantity} ${planned.unit || ''}` : undefined"
              rounded="lg"
              class="mb-1"
              style="border:1px solid #e2e8f0"
              @click="() => { mapTarget && (mapTarget.feo_planned_item_id = planned.id); applyMapping(planned.id) }"
            >
              <template #append>
                <v-icon icon="mdi-check" color="teal" v-if="mapTarget && mapTarget.feo_planned_item_id === planned.id" />
              </template>
            </v-list-item>
            <div v-if="!comparisonData[mapCategoryId].planned.length" class="text-caption text-medium-emphasis pa-2">
              Нет плановых позиций. Сначала добавьте их.
            </div>
          </v-list>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="showMapDialog = false">Отмена</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Диалог добавления плановой позиции ── -->
    <v-dialog v-model="showAddPlannedDialog" max-width="440" :fullscreen="mobile">
      <v-card>
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">
          <v-icon icon="mdi-plus-circle" color="teal" class="mr-2" />
          Добавить плановую позицию
        </v-card-title>
        <v-card-text>
          <!-- Владелец (2026-08-31): при добавлении плановой позиции можно написать
               что угодно, но у нас есть большая база товаров/услуг — подсказки с
               фильтром по вводу и картинкой. Переиспользует InlineProductMatch
               (тот же компонент, что и в строках позиций закупки/заявок) — второй
               такой же компонент не заводим. Свободный ввод обязателен: любое
               набранное имя сохраняется как есть, ничего не дописывается в каталог
               товаров (hideCreateNew скрывает «Создать новый товар…» — здесь это
               только подсказки/визуализация, а не привязка к каталогу). -->
          <!-- Владелец (2026-09-01): «добавляется плановая позиция по одной штуке,
               соответственно картинку сделай раза в 3 больше, чтобы было видно» —
               size 36 → 108 (ровно ×3). -->
          <!-- Владелец (2026-09-01, повторно): картинку над полем наименования (не
               сбоку) — сбоку она отжирала ширину и длинные названия вылезали за
               пределы узкого поля. Поле — на всю ширину диалога (w-100), картинку
               не уменьшаем. -->
          <div class="mb-2">
            <v-tooltip v-if="addPlannedProductPhoto" location="right">
              <template #activator="{ props: tip }">
                <v-avatar v-bind="tip" size="108" rounded="lg" style="cursor:pointer;overflow:hidden">
                  <img :src="addPlannedProductPhoto" style="width:108px;height:108px;object-fit:cover;display:block" />
                </v-avatar>
              </template>
              <img :src="addPlannedProductPhoto" style="width:240px;height:240px;object-fit:cover;border-radius:8px;display:block" />
            </v-tooltip>
            <v-icon v-else size="64" class="text-medium-emphasis">mdi-package-variant</v-icon>
          </div>
          <InlineProductMatch
            class="w-100 mb-3"
            :item-name="plannedItemForm.name"
            :product-id="addPlannedProductId"
            :match-confirmed="addPlannedMatchConfirmed"
            hide-create-new
            @update:search-text="plannedItemForm.name = $event"
            @pick="onPlannedItemProductPick"
            @clear="onPlannedItemProductClear"
          />
          <v-row>
            <v-col cols="5">
              <v-text-field
                v-model.number="plannedItemForm.quantity"
                label="Количество" type="number"
                variant="outlined" density="compact"
              />
            </v-col>
            <v-col cols="7">
              <v-text-field
                v-model="plannedItemForm.unit"
                label="Единица измерения"
                variant="outlined" density="compact"
                placeholder="шт, кг, услуга..."
              />
            </v-col>
          </v-row>
          <!-- Плановая стоимость за единицу (владелец, 2026-09-01): подставляется из
               каталога при выборе товара (onPlannedItemProductPick), полностью
               редактируема; пока задана и не равна 0 — «Плановая сумма» ниже считается
               как количество × эта цена (см. watch на plannedItemForm.quantity/unitPrice). -->
          <v-text-field
            v-model.number="plannedItemForm.unitPrice"
            label="Плановая стоимость за единицу, ₽" type="number"
            variant="outlined" density="compact" suffix="₽"
            class="mb-1"
          />
          <div v-if="addPlannedPriceCaption" class="text-caption text-medium-emphasis mb-2" style="line-height:1.35">
            <v-icon icon="mdi-information-outline" size="13" style="margin-top:-2px" class="mr-1" />{{ addPlannedPriceCaption }}
          </div>
          <v-text-field
            v-model.number="plannedItemForm.amount"
            label="Плановая сумма (₽)" type="number"
            variant="outlined" density="compact" suffix="₽"
            :readonly="plannedItemAmountIsComputed"
            :bg-color="plannedItemAmountIsComputed ? 'grey-lighten-4' : undefined"
            :hint="plannedItemAmountIsComputed ? 'Считается автоматически: количество × стоимость за единицу' : ''"
            :persistent-hint="plannedItemAmountIsComputed"
            :class="plannedItemForm.payment_mode === 'monthly' ? 'd-none' : 'mb-3'"
          />
          <!-- Происхождение плановой позиции (владелец, 2026-09-01): «это плановая
               позиция в соответствии с ФЭО, или только в соответствии с нашим
               внутренним планом» — ДВЕ НЕЗАВИСИМЫЕ галочки, не переключатель, обе
               можно поставить/снять независимо. Доступны только тому, кто может
               редактировать ФЭО (вкладка feo_categories) — эта же панель уже целиком
               ограничена ею, см. проверку доступа страницы. -->
          <div class="text-caption text-medium-emphasis mb-1">Происхождение позиции</div>
          <v-checkbox
            v-model="plannedItemForm.is_feo_breakdown"
            density="compact" hide-details
            class="mb-1"
          >
            <template #label>
              <div>
                <div style="line-height:1.2">По ФЭО</div>
                <div class="text-caption text-medium-emphasis" style="line-height:1.2">жёсткая разбивка ФЭО — покупать будут именно это, отчётность строгая</div>
              </div>
            </template>
          </v-checkbox>
          <v-checkbox
            v-model="plannedItemForm.is_internal_plan"
            density="compact" hide-details
            class="mb-3"
          >
            <template #label>
              <div>
                <div style="line-height:1.2">Внутренний план</div>
                <div class="text-caption text-medium-emphasis" style="line-height:1.2">в ФЭО была более широкая категория (или позиции не было) — разбивку придумали сами</div>
              </div>
            </template>
          </v-checkbox>
          <!-- Тип платежа -->
          <div class="text-caption text-medium-emphasis mb-1">Тип платежа</div>
          <v-btn-toggle
            v-model="plannedItemForm.payment_mode"
            mandatory density="compact" variant="outlined" divided
            class="mb-3"
          >
            <v-btn value="one_time" size="small">Разовый</v-btn>
            <v-btn value="monthly" size="small">Ежемесячный</v-btn>
          </v-btn-toggle>
          <!-- Разовый: дата потребности -->
          <v-text-field
            v-if="plannedItemForm.payment_mode === 'one_time'"
            v-model="plannedItemForm.planned_date"
            label="Дата потребности"
            type="date"
            variant="outlined" density="compact"
            class="mb-2"
          />
          <!-- Ежемесячный: поля -->
          <template v-if="plannedItemForm.payment_mode === 'monthly'">
            <v-text-field
              v-model="plannedItemForm.monthly_start_date"
              label="Первый платёж"
              type="date"
              variant="outlined" density="compact"
              class="mb-2"
            />
            <v-row dense>
              <v-col cols="6">
                <v-text-field
                  v-model.number="plannedItemForm.months_count"
                  label="Кол-во месяцев"
                  type="number"
                  variant="outlined" density="compact"
                />
              </v-col>
              <v-col cols="6">
                <v-text-field
                  v-model.number="plannedItemForm.monthly_amount"
                  label="Платёж за месяц, ₽"
                  type="number"
                  variant="outlined" density="compact"
                />
              </v-col>
            </v-row>
            <div
              v-if="plannedItemForm.monthly_amount && plannedItemForm.months_count"
              class="text-caption text-medium-emphasis mb-2"
            >
              Итого по позиции: {{ ((plannedItemForm.monthly_amount ?? 0) * (plannedItemForm.months_count ?? 0)).toLocaleString('ru-RU') }} ₽
            </div>
          </template>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="showAddPlannedDialog = false">Отмена</v-btn>
          <v-btn color="teal" variant="flat" :loading="savingPlannedItem"
            :disabled="!plannedItemForm.name.trim()"
            @click="savePlannedItem">
            Добавить
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <BudgetHistoryDialog ref="historyDialogRef" />

    <!-- 12-04: Version History Dialog -->
    <v-dialog v-model="showVersionHistoryDialog" max-width="720" scrollable :fullscreen="mobile">
      <v-card>
        <v-card-title class="d-flex align-center pa-4">
          <v-icon icon="mdi-history" size="20" color="blue-grey" class="mr-2" />
          История плана закупок
          <v-spacer />
          <v-btn icon="mdi-close" size="x-small" variant="text" @click="showVersionHistoryDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text style="min-height:200px">
          <div v-if="versionHistoryLoading" class="d-flex justify-center py-8">
            <v-progress-circular indeterminate color="blue-grey" />
          </div>
          <div v-else-if="versionHistoryList.length === 0" class="text-center text-medium-emphasis py-8">
            Нет сохранённых версий
          </div>
          <v-table v-else density="compact">
            <thead>
              <tr>
                <th>Версия</th>
                <th>Дата</th>
                <th>Дата редакции</th>
                <th>Автор</th>
                <th class="text-right">Всего план, ₽</th>
                <th class="text-right">Факт, ₽</th>
                <th>Примечание</th>
                <th>Сравнить</th>
                <th>Excel</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="v in versionHistoryList" :key="v.id">
                <td><v-chip size="x-small" color="blue-grey" variant="tonal">v{{ v.version_number }}</v-chip></td>
                <td style="font-size:12px">{{ v.created_at ? new Date(v.created_at).toLocaleString('ru') : '—' }}</td>
                <td style="font-size:12px">{{ (v as any).effective_date ? new Date((v as any).effective_date).toLocaleDateString('ru-RU') : '—' }}</td>
                <td style="font-size:12px">{{ v.created_by_name || '—' }}</td>
                <td class="text-right" style="font-size:12px">{{ formatCurrency(v.total_planned) }}</td>
                <td class="text-right" style="font-size:12px">{{ formatCurrency(v.total_used) }}</td>
                <td style="font-size:12px;max-width:200px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{{ v.note || '—' }}</td>
                <td>
                  <v-checkbox
                    v-model="compareSelected"
                    :value="v.id"
                    :disabled="compareSelected.length >= 2 && !compareSelected.includes(v.id)"
                    density="compact"
                    hide-details
                  />
                </td>
                <td>
                  <v-btn icon="mdi-file-excel" size="x-small" variant="text" color="green" @click="downloadVersionExcel(v.id)" />
                </td>
                <td>
                  <v-btn size="x-small" variant="text" color="blue" icon="mdi-eye-outline"
                    title="Просмотр снимка"
                    @click="viewVersionSnapshot(v.id)" />
                </td>
              </tr>
            </tbody>
          </v-table>
          <div class="d-flex align-center justify-end mt-3 ga-2">
            <span v-if="compareSelected.length > 0" class="text-caption text-medium-emphasis mr-auto">
              Выбрано: {{ compareSelected.length }}/2
            </span>
            <v-btn
              v-if="compareSelected.length > 0"
              size="small"
              variant="text"
              @click="compareSelected = []"
            >Очистить</v-btn>
            <v-btn
              :disabled="compareSelected.length !== 2"
              color="primary"
              variant="flat"
              size="small"
              prepend-icon="mdi-compare"
              :loading="compareLoading"
              @click="downloadCompareExcel"
            >Скачать сравнение (Excel)</v-btn>
          </div>
        </v-card-text>
      </v-card>
    </v-dialog>

    <!-- Export versions dialog -->
    <v-dialog v-model="showExportVersionsDialog" max-width="760" scrollable>
      <v-card>
        <v-card-title class="d-flex align-center pa-4">
          <v-icon icon="mdi-file-excel-outline" size="20" color="success" class="mr-2" />
          Выгрузить редакции ФЭО
          <v-spacer />
          <v-btn icon="mdi-close" size="x-small" variant="text" @click="showExportVersionsDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text style="min-height:160px">
          <v-progress-linear v-if="exportVersionsLoading" indeterminate color="primary" class="mb-3" />
          <div class="text-caption text-medium-emphasis mb-3">Выберите одну или несколько редакций. Несколько редакций выгрузятся в один документ — колонки рядом.</div>
          <v-checkbox v-model="exportIncludeCurrent" density="compact" hide-details label="Текущая (живая) ФЭО" class="mb-2" />
          <v-table density="compact">
            <thead>
              <tr>
                <th></th>
                <th>Дата редакции</th>
                <th>Примечание</th>
                <th class="text-right">План, ₽</th>
                <th class="text-right">Факт, ₽</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="v in exportVersionsList" :key="v.id">
                <td>
                  <v-checkbox
                    :model-value="exportSelectedIds.includes(v.id)"
                    @update:model-value="toggleExportId(v.id)"
                    density="compact"
                    hide-details
                  />
                </td>
                <td style="font-size:12px">{{ formatEditionDate(v.effective_date || v.created_at) }}</td>
                <td style="font-size:12px">{{ v.note || '—' }}</td>
                <td class="text-right" style="font-size:12px">{{ Number(v.total_planned || 0).toLocaleString('ru-RU') }}</td>
                <td class="text-right" style="font-size:12px">{{ Number(v.total_used || 0).toLocaleString('ru-RU') }}</td>
              </tr>
              <tr v-if="!exportVersionsLoading && exportVersionsList.length === 0">
                <td colspan="5" class="text-center text-medium-emphasis py-4">Сохранённых редакций нет</td>
              </tr>
            </tbody>
          </v-table>
        </v-card-text>
        <v-divider />
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="showExportVersionsDialog = false">Отмена</v-btn>
          <v-btn
            color="success"
            variant="flat"
            prepend-icon="mdi-file-excel-outline"
            :loading="exportRunning"
            :disabled="exportSelectedIds.length === 0 && !exportIncludeCurrent"
            @click="runVersionsExport"
          >Выгрузить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 12-04/12-05: Version Snapshot Dialog -->
    <v-dialog v-model="showVersionSnapshotDialog" max-width="960" scrollable :fullscreen="mobile">
      <v-card v-if="selectedVersionSnapshot">
        <v-card-title class="d-flex align-center pa-4">
          <v-icon icon="mdi-database-eye" size="20" color="blue" class="mr-2" />
          <div>
            Снимок версии v{{ selectedVersionSnapshot.version_number }}
            <span v-if="selectedVersionSnapshot.effective_date" class="text-body-2 text-medium-emphasis ml-2">
              (дата редакции: {{ new Date(selectedVersionSnapshot.effective_date).toLocaleDateString('ru-RU') }})
            </span>
            <div v-if="selectedVersionSnapshot.note" class="text-caption text-medium-emphasis mt-1">
              {{ selectedVersionSnapshot.note }}
            </div>
          </div>
          <v-spacer />
          <v-btn icon="mdi-close" size="x-small" variant="text" @click="showVersionSnapshotDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text>
          <!-- v2 snapshot с tree -->
          <table v-if="selectedVersionSnapshot.snapshot?.tree?.length" class="snapshot-tree-table">
            <thead>
              <tr>
                <th>Наименование</th>
                <th class="text-right">План (snapshot) ₽</th>
                <th class="text-right">Факт (текущий) ₽</th>
                <th class="text-right">Остаток ₽</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="node in flattenedSnapshotTree" :key="node._key">
                <tr :class="`level-${node.level} status-${getReconStatus(node)}`">
                  <td :style="`padding-left:${(node.level - 1) * 20 + 8}px`">
                    <v-icon v-if="node.children?.length" icon="mdi-folder-outline" size="14" class="mr-1" />
                    {{ node.name }}
                  </td>
                  <td class="text-right">{{ formatCurrency(node.budget || 0) }}</td>
                  <td class="text-right">{{ formatCurrency(getActualUsed(node.id)) }}</td>
                  <td class="text-right" :class="getActualResidual(node) < 0 ? 'text-error' : ''">
                    {{ formatCurrency(getActualResidual(node)) }}
                  </td>
                  <td>
                    <v-chip v-if="getReconStatus(node) === 'moved'" size="x-small" color="info" variant="tonal">переименован</v-chip>
                    <v-chip v-else-if="getReconStatus(node) === 'orphan'" size="x-small" color="warning" variant="tonal">не сматчился</v-chip>
                    <v-chip v-else-if="getReconStatus(node) === 'matched'" size="x-small" color="success" variant="tonal">✓</v-chip>
                  </td>
                </tr>
              </template>
            </tbody>
            <tfoot>
              <tr>
                <td><b>Итого</b></td>
                <td class="text-right"><b>{{ formatCurrency(selectedVersionSnapshot.snapshot?.total_planned || 0) }}</b></td>
                <td class="text-right"><b>{{ formatCurrency(snapshotTotalActual) }}</b></td>
                <td class="text-right"><b>{{ formatCurrency((selectedVersionSnapshot.snapshot?.total_planned || 0) - snapshotTotalActual) }}</b></td>
                <td></td>
              </tr>
            </tfoot>
          </table>
          <!-- v1 snapshot — fallback на flat items -->
          <v-table v-else density="compact" style="font-size:12px">
            <thead>
              <tr style="background:#EFF6FF">
                <th>Наименование</th>
                <th class="text-right">Планово, ₽</th>
                <th class="text-right">Факт, ₽</th>
                <th class="text-right">Остаток, ₽</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in selectedVersionSnapshot.snapshot?.items || []" :key="item.feo_item_id">
                <td>{{ item.name }}</td>
                <td class="text-right">{{ formatCurrency(item.planned_amount) }}</td>
                <td class="text-right">{{ formatCurrency(item.used_amount) }}</td>
                <td class="text-right"
                  :style="item.residual < 0 ? 'color:#EF4444;font-weight:bold' : item.residual === 0 ? 'color:#22C55E' : ''">
                  {{ formatCurrency(item.residual) }}
                </td>
              </tr>
            </tbody>
            <tfoot>
              <tr style="background:#EFF6FF;font-weight:bold">
                <td>Итого</td>
                <td class="text-right">{{ formatCurrency(selectedVersionSnapshot.snapshot?.total_planned || 0) }}</td>
                <td class="text-right">{{ formatCurrency(selectedVersionSnapshot.snapshot?.total_used || 0) }}</td>
                <td class="text-right">{{ formatCurrency((selectedVersionSnapshot.snapshot?.total_planned || 0) - (selectedVersionSnapshot.snapshot?.total_used || 0)) }}</td>
              </tr>
            </tfoot>
          </v-table>
        </v-card-text>
      </v-card>
    </v-dialog>

    <!-- 12-05: Save version dialog -->
    <v-dialog v-model="showSaveVersionDialog" max-width="540" :fullscreen="mobile">
      <v-card>
        <v-card-title class="d-flex justify-space-between align-center">
          Сохранить редакцию ФЭО
          <v-btn icon="mdi-close" size="x-small" variant="text" @click="showSaveVersionDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          <v-text-field
            v-model="saveVersionEffectiveDate"
            type="date"
            label="Дата редакции"
            density="comfortable"
            variant="outlined"
            hide-details="auto"
            class="mb-3"
          />
          <v-textarea
            v-model="saveVersionNote"
            label="Примечание (необязательно)"
            rows="2"
            density="comfortable"
            variant="outlined"
            hide-details="auto"
          />
        </v-card-text>
        <v-divider />
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="showSaveVersionDialog = false">Отмена</v-btn>
          <v-btn
            color="primary"
            variant="flat"
            :loading="saveVersionLoading"
            :disabled="!saveVersionEffectiveDate"
            @click="saveVersion"
          >
            Сохранить
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Превью фото товара ── -->
    <v-dialog
      :model-value="!!photoPreview"
      max-width="640"
      @update:model-value="v => !v && (photoPreview = null)"
    >
      <v-card v-if="photoPreview">
        <v-card-title class="d-flex align-center pa-3 text-subtitle-2">
          {{ photoPreview.title }}
          <v-spacer />
          <v-btn icon="mdi-close" size="small" variant="text" @click="photoPreview = null" />
        </v-card-title>
        <v-card-text class="pa-2">
          <v-img :src="photoPreview.src" contain style="max-height:70vh" />
        </v-card-text>
      </v-card>
    </v-dialog>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, reactive, nextTick } from 'vue'
import { useDisplay } from 'vuetify'
import { useAnimatedNumber } from '@/composables/useAnimatedNumber'
import { useRouter, useRoute } from 'vue-router'
import { apiFetch } from '@/api'
import { refreshMyPendingApprovals } from '@/composables/useApprovalsBadge'
import { useGlobalSubsidy } from '@/composables/useGlobalSubsidy'
import { useResizableColumns } from '@/composables/useResizableColumns'
import { useCardView } from '@/composables/useCardView'
import { useToast, type ToastType } from '@/composables/useToast'
import BudgetHistoryDialog from '@/components/BudgetHistoryDialog.vue'
import ContractorPicker from '@/components/ContractorPicker.vue'
import BudgetBar from '@/components/BudgetBar.vue'
import RegistryExportButton from '@/components/RegistryExportButton.vue'
import { useRegistryExport } from '@/composables/useRegistryExport'
import FeoTreeSelect from '@/components/items/FeoTreeSelect.vue'
import { useFeoLeaves } from '@/composables/useFeoLeaves'
import { useAuthStore } from '@/stores/auth'
// Владелец (2026-08-18, прод-инцидент — «Огнетушитель ОУ-2» перенесён в новую
// категорию, автоподбор не нашёл точное совпадение имени и молча завёл вторую
// плановую позицию рядом с уже подходящей): диалог «Редактировать позицию»
// теперь даёт выбрать плановую позицию явно, тот же компонент, что в
// CreateOrderView.vue/WishesView.vue — см. reqItemEdit ниже.
import FeoPlannedItemsSelect from '@/components/items/FeoPlannedItemsSelect.vue'
import InlineProductMatch from '@/components/items/InlineProductMatch.vue'
import type { MatchCandidate } from '@/composables/useItemMatching'
import { useFeoPlannedResiduals } from '@/composables/useFeoPlannedResiduals'
import type { FeoPlanSelection } from '@/composables/useFeoPlannedResiduals'
import { PURCHASE_STATUS_META, PURCHASE_STATUS_ORDER, purchaseStatusLabel, purchaseStatusIcon, purchaseStatusColor } from '@/constants/purchaseStatus'
import { type KpiKey, KPI_MODE, KPI_LABELS, KPI_EMPTY_REASONS, kpiItemMatches } from '@/constants/kpiMetrics'

const { globalSubsidyId } = useGlobalSubsidy()

// ── Persist настроек отображения дерева ФЭО (localStorage) — по образцу CARD_ORDER_KEY
// (см. ниже ~subsidyOrder). Без этого переключатель «план»/группировка/раскрытые узлы
// сбрасывались при каждой загрузке страницы — «на разных компьютерах по-разному»
// (задача владельца ШАГ 1, 2026-08-07). Загружается ОДИН раз при инициализации модуля;
// используется как фолбэк для начальных значений refs, объявленных ниже по файлу.
const FEO_DISPLAY_PREFS_KEY = 'subsidies_feo_display_prefs'
interface FeoDisplayPrefs {
  plannedBase?: 'all' | 'manual' | 'requests' | 'purchases'
  feoItemsGroupBy?: 'none' | 'category' | 'category_type'
  expandedIds?: number[]
  expandedReqItems?: number[]
  expandedItemPanels?: number[]
  expandedPlannedItems?: number[]
  // Возвращено из отката e0db76a (план zany-fluttering-mountain.md, п.4): строка плана
  // раскрыта по умолчанию, если под ней есть закупка (см. applyDefaultPlannedExpansion) —
  // но явное решение пользователя СВЕРНУТЬ строку обязано пережить перезагрузку и не быть
  // перезаписано дефолтом. Раз "развёрнуто" теперь может появиться и БЕЗ клика пользователя,
  // самого expandedPlannedItems недостаточно, чтобы отличить «дефолт» от «пользователь
  // свернул» (оба случая — id отсутствует в массиве). collapsedPlannedItems — id, которые
  // пользователь ЯВНО свернул кликом по шеврону (см. togglePlannedItemFolder) —
  // единственный признак с приоритетом над дефолтом.
  collapsedPlannedItems?: number[]
}
function loadFeoDisplayPrefs(): FeoDisplayPrefs {
  try {
    const raw = localStorage.getItem(FEO_DISPLAY_PREFS_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}
const feoDisplayPrefs = loadFeoDisplayPrefs()

// Название карточки в одну строку: базовый крупный шрифт, ужимается пока не влезет
function fitTextToWidth(el: HTMLElement) {
  const base = 30
  el.style.fontSize = `${base}px`
  const cw = el.clientWidth
  if (cw > 0 && el.scrollWidth > cw) {
    el.style.fontSize = `${Math.max(13, Math.floor((base * cw) / el.scrollWidth))}px`
  }
}
const vFitText = {
  mounted: fitTextToWidth,
  updated: fitTextToWidth,
}

// Правка владельца (2026-08-12, откат явных 180px — регресс): фиксированные
// name/qty/planned/spent=180px сузили feo-table в узкую полосу по центру экрана
// (авто-колонки с width:0 растягивали таблицу на всю ширину, фиксированные — нет).
// Возвращены авто-ширины (0) для name/qty/planned/residual — budget/spent остаются
// зафиксированы под деньги (180px), как и раньше. Совпадение колонок вложенной
// таблицы плановых позиций с основной (см. предыдущую правку выше и баг
// «name~470px vs 187px») теперь достигается НЕ фиксацией ширин, а тем, что у
// вложенной таблицы РОВНО ТОТ ЖЕ набор из 7 колонок, что и у основной —
// name/budget/qty/planned/spent/residual (spent/residual — пустые заглушки) +
// колонка кнопок шириной 112px (как .feo-th-actions у основной). При одинаковом
// наборе фиксированных/авто-колонок и одинаковой полной ширине контейнера
// (colspan захватывает ВСЕ 7 колонок основной таблицы, а не 6) table-layout:fixed
// делит остаток одинаково в обеих таблицах — колонки совпадают по построению.
const feoResize = useResizableColumns('feo-table', {
  name: 0, budget: 180, qty: 0, planned: 0, spent: 180, residual: 0,
})

const router = useRouter()
const route  = useRoute()

// Владелец (2026-08-29): «превышение согласовывают только владельцы/финансисты,
// у начальника отдела таких прав быть не может». Раньше здесь стоял фронтовый
// canDecidePlanExcess = can('plan_excess.decide') поверх «я назначен в шаге»
// (excessMyPendingStep) — но can() читал НАСЛЕДУЮЩИЙ список прав с /api/users/me
// (get_effective_actions), а реальный гейт POST /decide — НЕнаследующий
// has_org_key. org_admin без гранта ВИДЕЛ кнопку «Одобрить» и получал 403 при
// клике. Убрано — единственный источник истины теперь can_decide в ответе
// GET /api/plan-excess (см. excessApprovalFor(node)?.can_decide ниже,
// backend/app/routers/plan_excess.py _can_decide_plan_excess).

interface SubsidyRow {
  id: number; name: string; year: number; budget: number
  calculated_budget?: number
  description?: string; planned: number; paid: number; contracted: number
  plan_schedule: number; ordered: number
  feo_filled?: boolean
  feo_budget_total?: number
  contractor_id?: number
  contractor_name?: string
  contractor_inn?: string
  basis_doc_number?: string
  basis_doc_date?: string
  // Phase 31-05: canonical budget fields
  remaining?: number | null
  planned_amount?: number | null
  budget_discrepancy?: number | null
  require_planned_dates?: boolean
  // Phase 32: dashboard KPI fields
  work: number
  contracts: number
  delivered: number
  delivered_unpaid: number
  // Владелец (2026-08-30): предупреждение «сумма заказанного приближается к
  // потолку субсидии» — см. app/services/feo_plan.py calculate_ceiling_forecast*.
  ceiling_warn_percent?: number | null
  ceiling_total?: number | null
  ceiling_committed_total?: number | null
  ceiling_committed_percent?: number | null
  ceiling_near_warning?: boolean
  ceiling_exceeded?: boolean
  // C4: черновые субсидии — статус/автор/утвердивший. dashboard/charts их не
  // отдаёт, подтягиваются отдельным вызовом GET /subsidies/ в loadAll() и
  // мёрджатся по id (см. ниже).
  status?: string
  created_by?: number | null
  approved_by?: number | null
  approved_at?: string | null
}

// C4: участник (соредактор) черновой субсидии — калька wish_member без
// consent-флоу, см. backend/app/routers/subsidy_members.py.
interface SubsidyMember {
  id: number
  subsidy_id: number
  user_id: number
  added_by_id: number | null
  username?: string | null
  full_name?: string | null
  added_by_name?: string | null
  created_at?: string | null
}

interface FeoCategory {
  id: number; parent_id: number | null; subsidy_id: number
  level: number; name: string; code: string | null; appendix: string | null
  is_active: boolean; budget: number | null; planned_quantity: number | null; planned_amount: number | null; unit: string | null
  feo_quantity: number | null; feo_unit: string | null
  description: string | null; feo_amount: number | null
  // План zany-fluttering-mountain.md, п.1/п.5: способ расчёта плана — переключатель
  // «по плановым позициям» / «по вручную заданной сумме», см. feoForm.planSource ниже.
  // Опционально: старые категории на бэкенде без миграции отдают undefined — фронт
  // трактует это как значение по умолчанию 'planned_items' (см. startFeoEdit).
  plan_source?: 'planned_items' | 'manual_sum'
  manual_plan_amount?: number | null
}

interface FeoNode extends FeoCategory {
  depth: number
  hasChildren: boolean
  children: FeoNode[]
}

// ── Approvers types ───────────────────────────────
interface SubsidyApprover {
  id: number
  subsidy_id: number
  role_name: string
  full_name: string
  order_num: number
  is_default: boolean
  can_initiate: boolean
  show_feo_path: boolean
  user_id?: number | null
}

const ROLE_SUGGESTIONS = [
  'Первый заместитель руководителя',
  'Куратор проекта',
  'Ответственный исполнитель',
  'Юрист',
  'Главный бухгалтер',
  'Начальник отдела МТО',
  'Заместитель руководителя по ФХД',
]

const approversHeaders = [
  { title: '#', key: 'order_num', width: '60px', sortable: false },
  { title: 'Роль / Должность', key: 'role_name', sortable: false },
  { title: 'ФИО', key: 'full_name', sortable: false },
  { title: '', key: 'is_default', width: '120px', sortable: false },
  { title: '', key: 'can_initiate', width: '100px', sortable: false },
  { title: '', key: 'actions', width: '110px', sortable: false },
]

// ── State ─────────────────────────────────────────
const registryArea = ref<HTMLElement | null>(null)
const feoTableArea = ref<HTMLElement | null>(null)
const { exportScreenshotPdf: _exportFeoScreenshotPdf } = useRegistryExport()
const loading    = ref(false)
const saving     = ref(false)
const savingFeo  = ref(false)
const loadingFeo = ref(false)

const allSubsidies    = ref<SubsidyRow[]>([])
const feoCategories   = ref<FeoCategory[]>([])
const purchaseTotals  = ref<Record<number, number>>({})
// НЕпривязанные (feo_planned_item_id IS NULL) — используются в feoPlannedRequestsFor/feoQtyRequestsFor,
// чтобы не задваивать ручной план листа (Ур.5) позициями заявок, которые его уже расходуют.
const plannedPurchaseTotals = ref<Record<number, number>>({})
const plannedPurchaseQty = ref<Record<number, number>>({})
// Привязанные (feo_planned_item_id IS NOT NULL) — «выбрано заявками» из плана; см.
// feoPlannedConsumedFor/feoQtyConsumedFor и заметку под «Плановой суммой».
const plannedPurchaseTotalsLinked = ref<Record<number, number>>({})
const plannedPurchaseQtyLinked = ref<Record<number, number>>({})
// «Сверх плана» (over_plan=true, НЕпривязанные) — прибавляется к плановой сумме элемента
// безусловно, поверх план/заказ. См. feoPlannedOverFor/feoQtyOverFor. Итоговая «Плановая
// сумма»/«Плановое количество» (feoPlannedDisplayRaw/feoQtyDisplayRaw) больше НЕ считается
// на фронте — читается готовой из GET /api/feo-categories/plan-tree (planTreeByCat), см.
// app.services.feo_plan.compute_feo_plan_tree (единый источник, сессия 2026-08-05).
const plannedPurchaseTotalsOver = ref<Record<number, number>>({})
const plannedPurchaseQtyOver = ref<Record<number, number>>({})
// Прогнозное предупреждение «цена выше плановой» (сессия 2026-08-05, формула v2 —
// backend app.services.feo_plan.compute_feo_plan_tree). Только для информирования,
// НИКАКИХ блокировок — см. feoForecastWarningFor и предупреждение под «Плановой суммой».
const plannedPurchaseForecast = ref<Record<number, { forecast: number; forecast_over: number; plan_manual: number }>>({})
// Единая формула «Плановой суммы»/«Планового количества» узла — числа готовые с бэкенда
// (сессия 2026-08-05, задача «формула только на бэкенде»: раньше фронт пересчитывал сам,
// MAX(план, выбрано) + сверх_плана — СТАРАЯ формула, расходилась с KPI «Запланировано»
// на дашборде/в списке субсидий, который считает НОВУЮ формулу «заказ замещает план»,
// app.services.feo_plan.compute_feo_plan_tree). См. GET /api/feo-categories/plan-tree.
// excess_amount/excess_pending/excess_approved — согласование превышения плана
// над финансированием ФЭО узла (задача владельца 2026-08-05, «блокировать пока
// не согласовано» — см. backend app.services.feo_plan.compute_feo_plan_tree /
// app.routers.plan_excess). excessFor(node) ниже читает их из этой же карты.
// plan_manual/ordered_sum/residual/consumed — те же поля, что в GET /feo-categories/plan-tree
// (см. compute_feo_plan_tree), нужны feoResidualNoteFor ниже, чтобы заметка под «Плановой
// суммой» брала план из ТОГО ЖЕ источника, что и сама колонка (баг «заметка показывает
// не тот план», сессия 2026-08-05) — не из feoResiduals (Ур.5-детализация, другая сущность).
// Виновник превышения плана над ФЭО (задача владельца, план zany-fluttering-mountain.md
// п.«Заметный сигнал превышения», возвращено из отката e0db76a) — см. backend/app/services/
// feo_plan.py::find_excess_culprit за методом определения; null, пока превышения нет либо
// оно согласовано (сервер считает виновника только для узлов с неснятым excess_amount).
interface ExcessCulprit {
  purchase_id: number | null
  purchase_number: string | number | null
  item_name: string | null
  amount_before: number
  amount_at_crossing: number
  cumulative_after: number
}
// План zany-fluttering-mountain.md, п.4/п.2 (фронт): «позиции-виновники» превышения
// плана над вручную заданной суммой (excess_plan_items) — раньше приходили как голое
// {name, amount} без возможности перейти в закупку. Теперь каждая позиция несёт свой
// id и список связанных закупок (переиспользует planned_item_consumption на бэкенде,
// см. app/services/feo_plan.py); клик по позиции с одной закупкой ведёт прямо туда,
// с несколькими — открывает список (см. excessPlanCulpritClick/шаблон ниже).
interface ExcessPlanItemPurchase {
  id: number
  registry_number: string | number | null
  purchase_number: string | number | null
  status: string | null
  status_label: string | null
  amount: number
  stopped_at: string | null
}
interface ExcessPlanItem {
  id: number
  name: string
  amount: number
  purchases: ExcessPlanItemPurchase[]
}
const planTreeByCat = ref<Record<number, {
  display: number; display_quantity: number
  excess_amount?: number; excess_pending?: boolean; excess_approved?: boolean
  plan_manual?: number; ordered_sum?: number; residual?: number; consumed?: number
  // qty_plan — количественный двойник plan_manual/plan (замещение «заказ вместо плана»,
  // если набрано полностью, иначе собственный plan_manual-по-количеству), см.
  // backend/app/services/feo_plan.py::compute_feo_plan_tree. Нужен фолбэком в feoQtyFor
  // для мигрированных листьев (план в FeoPlannedItem, planned_quantity узла = null).
  qty_plan?: number
  // Задача владельца «план ≠ факт» (сессия 2026-08-06): факт узла (fact/fact_quantity)
  // и второй, независимый вид превышения — «итог закупки/КП дороже плана»
  // (excess_fact_over_plan/excess_fact_pending/excess_fact_approved), см. excessFactFor().
  plan?: number; fact?: number; fact_quantity?: number
  excess_fact_over_plan?: number; excess_fact_pending?: boolean; excess_fact_approved?: boolean
  // «Заметный сигнал превышения» — то же excess_amount под понятным именем + виновник
  // (закупка, из-за которой узел вышел за ФЭО), см. ExcessCulprit выше.
  excess_over_feo?: number; excess_culprit?: ExcessCulprit | null
  // over — полная плановая сумма узла ПОВЕРХ node["plan"] (см. backend
  // align_budget_to_plan: new_budget = plan + over), нужен фронту только чтобы
  // показать «станет N ₽» в подтверждении «Приравнять ФЭО к плану» ДО вызова —
  // реальный расчёт всё равно делает бэкенд.
  over?: number
  // Замечания владельца п.2/п.4 (2026-08-12, «план ≠ факт», продолжение) —
  // ТРЕТИЙ вид превышения (Σ плановых позиций > вручную заданного плана) и
  // постоянная пометка «превышение согласовано», см. excessPlanFor()/
  // excessPlanApprovalPermanent() ниже.
  manual_plan_entered?: number
  excess_plan_over_manual?: number
  excess_plan_approved?: boolean
  excess_plan_pending?: boolean
  excess_plan_items?: ExcessPlanItem[]
  excess_approval_amount?: number | null
  excess_approval_at?: string | null
  excess_approval_by_name?: string | null
  // План zany-fluttering-mountain.md, п.3: «план был X → стал Y» в постоянной плашке
  // «превышение согласовано» — снимок plan_excess_approvals.plan_before/plan_after на
  // МОМЕНТ создания запроса согласования (не пересчитывается задним числом), см.
  // excessPlanApprovalPermanent() ниже.
  excess_approval_plan_before?: number | null
  excess_approval_plan_after?: number | null
  // План zany-fluttering-mountain.md, п.1/п.5: способ расчёта плана категории —
  // переключатель в диалоге создания/редактирования, см. feoForm.planSource/
  // feoEditForm.planSource ниже.
  plan_source?: 'planned_items' | 'manual_sum'
  manual_plan_amount?: number | null
}>>({})
// Детали запросов согласования превышения плана ФЭО — GET /api/plan-excess?subsidy_id=
// (backend/app/routers/plan_excess.py). Карта feo_category_id → ПОСЛЕДНИЙ (по created_at,
// список от бэкенда уже отсортирован) запрос: шаги с ФИО согласующих, статус, комментарий
// отказа. planTreeByCat.excess_pending/excess_approved читает ТУ ЖЕ таблицу на бэкенде
// (см. app.services.feo_plan.compute_feo_plan_tree), поэтому статусы согласованы между
// собой — этот объект добавляет детали (кто именно, комментарий), которых в plan-tree нет.
interface PlanExcessStep {
  id: number; approval_id: number; user_id: number | null; order_num: number
  role_name: string | null; full_name: string | null; status: string
  comment: string | null; decided_at: string | null; decided_by_user_id: number | null
}
interface PlanExcessApprovalDto {
  id: number; feo_category_id: number; subsidy_id: number
  excess_amount: number; plan_amount: number | null; budget_amount: number | null
  status: string; mode: string; requested_by_id: number | null
  created_at: string | null; resolved_at: string | null; comment: string | null
  steps: PlanExcessStep[]
  self_approval?: boolean; warning?: string | null
  // Правка 2026-08-29: сервер сам считает, реально ли пройдёт POST /decide для
  // текущего пользователя (та же проверка has_org_key + «свой шаг» + запрет
  // самосогласования, что и в гейте /decide — см. backend/app/routers/plan_excess.py
  // _can_decide_plan_excess). Раньше кнопки судили по наследующему списку прав
  // с /api/users/me (canDecidePlanExcess/can('plan_excess.decide')) — org_admin
  // без гранта ВИДЕЛ кнопку «Одобрить» и получал 403 при клике.
  can_decide?: boolean
}
const planExcessApprovals = ref<Record<number, PlanExcessApprovalDto>>({})
// Закупки субсидии без категории ФЭО (ни у самой закупки, ни у одной позиции) — деньги
// есть (влияют на KPI «Ведётся работа»/«Запланировано» по субсидии), но в дереве ФЭО
// их не видно, т.к. дерево строится по категориям (сессия 2026-08-05). Отдельный
// ключ "unassigned" в GET /api/feo-categories/plan-tree, справочный, НЕ входит в
// ИТОГО дерева / feoPlannedDisplayFor / comparisonPlanTotal.
const unassignedFeo = ref<{ amount: number; purchase_count: number; purchase_ids: number[] }>({
  amount: 0, purchase_count: 0, purchase_ids: [],
})
// GET /plan-tree отдаёт "unassigned" как ДОПОЛНИТЕЛЬНЫЙ ключ рядом с числовыми id категорий
// (см. backend/app/routers/feo_categories.py) — вычленяем его в unassignedFeo, а
// planTreeByCat остаётся чистым Record<number, ...>, как и раньше (по нему никто не
// итерируется, только node.id → значение, так что нечисловой ключ и без выделения
// был бы безвреден, но так типобезопаснее).
function splitPlanTree(raw: Record<string, any>) {
  const { unassigned, ...rest } = raw || {}
  unassignedFeo.value = unassigned && typeof unassigned === 'object'
    ? { amount: Number(unassigned.amount || 0), purchase_count: Number(unassigned.purchase_count || 0), purchase_ids: unassigned.purchase_ids || [] }
    : { amount: 0, purchase_count: 0, purchase_ids: [] }
  return rest as Record<number, {
    display: number; display_quantity: number
    excess_amount?: number; excess_pending?: boolean; excess_approved?: boolean
    plan_manual?: number; ordered_sum?: number; residual?: number; consumed?: number
    qty_plan?: number
    plan?: number; fact?: number; fact_quantity?: number
    excess_fact_over_plan?: number; excess_fact_pending?: boolean; excess_fact_approved?: boolean
    excess_over_feo?: number; excess_culprit?: ExcessCulprit | null
  }>
}
function goToUnassignedFeoPurchases() {
  if (!selectedId.value) return
  router.push(`/orders?subsidy_id=${selectedId.value}`)
}
const excessRequestLoading = ref<number | null>(null)
const excessDecideLoading = ref<number | null>(null)
const excessRejectDialog = ref<{ show: boolean; node: FeoNode | null; comment: string }>({
  show: false, node: null, comment: '',
})
const expandedIds     = ref<number[]>(feoDisplayPrefs.expandedIds || [])
const selectedId      = ref<number | null>(null)
const selectedYear    = ref<number>(new Date().getFullYear())

// Объявлен здесь (не ниже, у других computed из блока «панель субсидии»), потому что
// reqItemEditSubsidyId (см. useFeoLeaves для диалога правки позиции) читает
// selectedSubsidy.value синхронно при вызове composable'а — до его собственной
// декларации это ReferenceError "Cannot access 'selectedSubsidy' before initialization".
const selectedSubsidy = computed(() =>
  allSubsidies.value.find(s => s.id === selectedId.value) ?? null
)

// 12-04: Residuals state
const feoResiduals = ref<Record<number, {
  feo_item_id: number
  name: string
  category_id: number
  planned_amount: number
  used_amount: number
  wish_used_amount: number
  residual: number
  linked_purchase_ids: number[]
}>>({})
const residualsLoading = ref(false)

// Плановые позиции (Ур.5) сгруппированы по листовой категории ФЭО — для заметки
// «план N · выбрано заявками M · остаток K» под «Плановой суммой» (см. feoResidualNoteFor).
// Переиспользует уже загруженный feoResiduals, ничего заново не считает.
const feoResidualsByCat = computed<Record<number, { planned: number; consumed: number; residual: number }>>(() => {
  const result: Record<number, { planned: number; consumed: number; residual: number }> = {}
  for (const item of Object.values(feoResiduals.value)) {
    const catId = item.category_id
    if (catId == null) continue
    const acc = (result[catId] ||= { planned: 0, consumed: 0, residual: 0 })
    acc.planned += Number(item.planned_amount || 0)
    // Заявки не расходуют план (владелец, 2026-08-17) — в consumed идут только
    // позиции закупок; wish_used_amount всегда 0, но поле оставлено в типе ради контракта ответа.
    acc.consumed += Number(item.used_amount || 0)
    acc.residual += Number(item.residual || 0)
  }
  return result
})
// БАГ 4 (сессия 2026-08-05): раньше значения брались из feoResidualsByCat — суммы
// ТОЛЬКО по Ур.5-записям (FeoPlannedItem) этой категории. У категории могли одновременно
// быть: (а) собственный план на уровне листа (planned_quantity × planned_amount, напр.
// 8 000 000 ₽) и (б) одна мелкая Ур.5-детализация (напр. «вавава» на 333 ₽) — заметка
// показывала «план 333 ₽», хотя колонка «Плановая сумма» рядом честно показывала
// 8 000 000 ₽ (из planTreeByCat/display). Теперь ЗНАЧЕНИЯ берутся из planTreeByCat —
// того же источника, что и колонка (plan_manual); feoResidualsByCat используется
// ТОЛЬКО как признак «у категории есть Ур.5-детализация», не как источник чисел —
// иначе эта заметка задваивала бы feoPlanConsumedNoteFor (см. v-else-if в шаблоне).
//
// БАГ (жалоба владельца 2026-08-13, конечная категория «Расходные материалы для
// проведения окружных полуфиналов…»): «Выбрано заявками 0 — это блядь что значит?»
// — consumed раньше читался из t.ordered_sum/t.consumed (planTreeByCat) — это
// backend-поле own_ordered/ordered, СЧИТАЕТ ТОЛЬКО заявки, ПРИВЯЗАННЫЕ к плановым
// позициям этой категории (feo_planned_item_id). У этой категории все 9 закупленных
// позиций на 118 365,60 ₽ заведены БЕЗ привязки (обычные позиции с тем же
// feo_category_id) — ordered_sum по ним 0, хотя по плану уже фактически набрано.
// Тот же приём, что и в feoPlanConsumedNoteFor: consumed = непривязанные
// (feoPlannedRequestsFor, карта plannedPurchaseTotals) + привязанные
// (feoPlannedConsumedFor, карта plannedPurchaseTotalsLinked) — «в закупках» считает
// ВСЕ заявки по категории, а не только те, что явно привязаны к Ур.5-позиции.
function feoResidualNoteFor(node: FeoNode): { planned: number; consumed: number; residual: number } | null {
  if (node.hasChildren) return null
  if (!feoResidualsByCat.value[node.id]) return null
  const t = planTreeByCat.value[node.id]
  if (!t) return null
  const planned = Number(t.plan_manual ?? 0)
  const consumed = feoInPlanScheduleFor(node)
  const residual = planned - consumed
  if (planned <= 0 && consumed <= 0) return null
  return { planned, consumed, residual }
}

// 12-04: Version history state
const showVersionHistoryDialog = ref(false)
const versionHistoryList = ref<Array<{
  id: number
  version_number: number
  created_at: string
  created_by_name: string
  note: string
  total_planned: number
  total_used: number
  item_count: number
}>>([])
const versionHistoryLoading = ref(false)
const selectedVersionSnapshot = ref<any>(null)
const showVersionSnapshotDialog = ref(false)
// 12-05 F2: compare state
const compareSelected = ref<number[]>([])
const compareLoading = ref(false)

// Export versions dialog state
const showExportVersionsDialog = ref(false)
const exportVersionsLoading = ref(false)      // loading the list
const exportVersionsList = ref<any[]>([])
const exportSelectedIds = ref<number[]>([])
const exportIncludeCurrent = ref(true)        // current live FEO preselected
const exportRunning = ref(false)              // during download

// 12-05: Save version state
const showSaveVersionDialog = ref(false)
const saveVersionEffectiveDate = ref('') // YYYY-MM-DD
const saveVersionNote = ref('')
const saveVersionLoading = ref(false)

const showAddDialog      = ref(false)
const showEditDialog     = ref(false)
const showDeleteDialog   = ref(false)
const showAddFeoDialog   = ref(false)
const showEditFeoDialog  = ref(false)
const showDeleteFeoDialog = ref(false)

// Budget history dialog ref
const historyDialogRef = ref<InstanceType<typeof BudgetHistoryDialog> | null>(null)

// Approvers state
const showApproversDialog    = ref(false)
const showApproverFormDialog = ref(false)
const loadingApprovers       = ref(false)
const savingApprover         = ref(false)
const approversSubsidy       = ref<SubsidyRow | null>(null)
const approversList          = ref<SubsidyApprover[]>([])
const approverEditTarget     = ref<SubsidyApprover | null>(null)
const approverForm = ref<{
  role_name: string
  full_name: string
  order_num: number
  is_default: boolean
  can_initiate: boolean
  show_feo_path: boolean
  user_id: number | null
  selectedUser: { id: number; full_name: string } | null
}>({ role_name: '', full_name: '', order_num: 0, is_default: true, can_initiate: false, show_feo_path: false, user_id: null, selectedUser: null })

const approverUsersList = ref<Array<{ id: number; full_name: string }>>([])

// C4: черновые субсидии — approve + members state
const approvingSubsidyId = ref<number | null>(null)
const showMembersDialog = ref(false)
const membersSubsidy = ref<SubsidyRow | null>(null)
const membersList = ref<SubsidyMember[]>([])
const loadingMembers = ref(false)
const addingMember = ref(false)
const memberToAdd = ref<number | null>(null)
const memberUsersList = ref<Array<{ id: number; full_name: string }>>([])
// Тот же гейт, что на бэкенде (_can_manage_subsidy_members): автор субсидии
// или обладатель subsidy.edit. hasAction() читает /users/me permissions
// (тот же механизм, что canEditFeo выше) — orgId-скоуп на бэкенд-стороне
// гейта per-subsidy (has_org_key), фронт для UI-показа кнопок довольствуется
// плоским правом, сервер всё равно перепроверит per-subsidy при запросе.
const canManageMembers = computed(() => {
  const s = membersSubsidy.value
  if (!s) return false
  if (authStore.hasAction('subsidy.edit')) return true
  return s.created_by != null && s.created_by === currentUserId
})

// ── Copy Approvers state ──────────────────────────
const showCopyApproversDialog = ref(false)
const copyApprovers = ref<{ sourceId: number | null; replace: boolean; loading: boolean; error: string }>({
  sourceId: null, replace: false, loading: false, error: '',
})
const copySourceSubsidies = computed(() =>
  (allSubsidies.value || []).filter(s => s.id !== approversSubsidy.value?.id)
)
function openCopyApproversDialog() {
  copyApprovers.value = { sourceId: null, replace: false, loading: false, error: '' }
  showCopyApproversDialog.value = true
}
async function confirmCopyApprovers() {
  if (!approversSubsidy.value?.id || !copyApprovers.value.sourceId) return
  copyApprovers.value.loading = true
  copyApprovers.value.error = ''
  try {
    const result = await apiFetch<{ copied: number; replaced: boolean }>(
      `/subsidies/${approversSubsidy.value.id}/approvers/copy-from/${copyApprovers.value.sourceId}?replace=${copyApprovers.value.replace}`,
      { method: 'POST' }
    )
    showCopyApproversDialog.value = false
    showSnack(`Скопировано: ${result.copied} согласующих${result.replaced ? ' (с заменой)' : ''}`, 'success')
    const list = await apiFetch<SubsidyApprover[]>(`/subsidies/${approversSubsidy.value.id}/approvers`)
    approversList.value = list
  } catch (e: any) {
    copyApprovers.value.error = e?.payload?.message || e?.message || 'Ошибка копирования'
  } finally {
    copyApprovers.value.loading = false
  }
}

// ── Copy Templates state ──────────────────────────
const showCopyTemplatesDialog = ref(false)
const copyTemplates = ref<{ sourceId: number | null; replace: boolean; loading: boolean; error: string }>({
  sourceId: null, replace: false, loading: false, error: '',
})
const copySourceSubsidiesForTemplates = computed(() =>
  (allSubsidies.value || []).filter(s => s.id !== templateSubsidy.value?.id)
)
function openCopyTemplatesDialog() {
  copyTemplates.value = { sourceId: null, replace: false, loading: false, error: '' }
  showCopyTemplatesDialog.value = true
}
async function confirmCopyTemplates() {
  if (!templateSubsidy.value?.id || !copyTemplates.value.sourceId) return
  copyTemplates.value.loading = true
  copyTemplates.value.error = ''
  try {
    const result = await apiFetch<{ copied: string[]; skipped: string[]; reason?: string }>(
      `/subsidies/${templateSubsidy.value.id}/templates/copy-from/${copyTemplates.value.sourceId}?replace=${copyTemplates.value.replace}`,
      { method: 'POST' }
    )
    showCopyTemplatesDialog.value = false
    if (result.reason) {
      showSnack(result.reason, 'error')
    } else {
      const skippedNote = result.skipped.length ? `, пропущено: ${result.skipped.length}` : ''
      showSnack(`Скопировано шаблонов: ${result.copied.length}${skippedNote}`, 'success')
    }
    await openTemplateDialog(templateSubsidy.value)
  } catch (e: any) {
    copyTemplates.value.error = e?.payload?.message || e?.message || 'Ошибка копирования'
  } finally {
    copyTemplates.value.loading = false
  }
}

let _approverUsersSubsidyId: number | null = null
async function loadApproverUsers() {
  // Согласующим может быть только сотрудник орг(а) субсидии или человек
  // с персональным доступом к ней — не весь контур.
  const sid = approversSubsidy.value?.id ?? null
  if (approverUsersList.value.length && _approverUsersSubsidyId === sid) return
  try {
    const data = await apiFetch<any[]>(`/users/${sid ? `?subsidy_id=${sid}` : ''}`)
    approverUsersList.value = data
    _approverUsersSubsidyId = sid
  } catch { approverUsersList.value = [] }
}

// Template variables panel state
interface TemplateVar { var: string; description: string; example_template: string; example_result: string }
const templateVars = ref<TemplateVar[]>([])
const varsSearch = ref('')
const filteredVars = computed(() => {
  if (!varsSearch.value) return templateVars.value
  const q = varsSearch.value.toLowerCase()
  return templateVars.value.filter(v =>
    v.var.toLowerCase().includes(q) ||
    v.description.toLowerCase().includes(q) ||
    v.example_template.toLowerCase().includes(q)
  )
})
async function loadTemplateVars() {
  try {
    templateVars.value = await apiFetch<TemplateVar[]>('/documents/template-vars')
  } catch (e) { console.error('loadTemplateVars:', e) }
}
async function copyVar(text: string) {
  // phase26-mm: на HTTP-only проде navigator.clipboard undefined.
  // Fallback на document.execCommand('copy') через временный textarea.
  let ok = false
  try {
    if (window.isSecureContext && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      ok = true
    } else {
      const ta = document.createElement('textarea')
      ta.value = text
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      ta.style.top = '0'
      ta.style.left = '0'
      document.body.appendChild(ta)
      ta.focus()
      ta.select()
      try { ok = document.execCommand('copy') } catch { ok = false }
      document.body.removeChild(ta)
    }
  } catch { ok = false }
  if (ok) showSnack(`Скопировано: ${text}`, 'success', { duration: 2500 })
  else showSnack(`Не удалось скопировать. Выделите и нажмите Ctrl+C: ${text}`, 'error')
}

// Template management state
const showTemplateDialog  = ref(false)
const templateSubsidy     = ref<SubsidyRow | null>(null)
const contractTemplates   = ref<Record<number, boolean>>({})
const subsidyTemplatesList = ref<Array<{ doc_type: string; label: string; has_custom: boolean; has_global: boolean; render_ok?: boolean | null }>>([])
const templateFileInputRef = ref<HTMLInputElement | null>(null)
const uploadingDocType     = ref<string | null>(null)
const deleteTarget       = ref<SubsidyRow | null>(null)
const deleteErrorLinked  = ref(false)
const deleteErrorMsg     = ref('')
const deleteImpact       = ref<{ feo_categories: number; planned_items: number; purchases: number; contracts: number } | null>(null)
const feoEditTarget      = ref<FeoCategory | null>(null)
const feoDeleteTarget    = ref<FeoCategory | null>(null)
const feoDeleteError     = ref('')
const feoDeleteLinkedIds = ref<number[]>([])

// FEO search
const feoSearch = ref('')

// FEO inline budget edit
const inlineBudgetId = ref<number | null>(null)
const inlineBudgetVal = ref('')
const inlineInputEl = ref<HTMLInputElement | null>(null)

// FEO inline planned_quantity edit
const inlineQtyId = ref<number | null>(null)
const inlineQtyVal = ref('')
const inlineQtyInputEl = ref<HTMLInputElement | null>(null)

// FEO inline planned_amount edit
const inlineAmtId = ref<number | null>(null)
const inlineAmtVal = ref('')
const inlineAmtInputEl = ref<HTMLInputElement | null>(null)

// FEO Drag & Drop
const dragNodeId = ref<number | null>(null)
const dragOverId = ref<number | null>(null)

// FEO Import
interface FeoWarning {
  kind: 'level_gap' | 'level_duplicate' | 'sum_mismatch' | 'sum_without_qty' | 'parent_sum_mismatch'
    | 'level_name_in_number_column' | 'item_promoted_to_level2' | 'item_type_unknown'
    | 'column_shift' | 'group_plan_ignored' | 'plan_vs_items_mismatch' | 'plan_skipped_has_items'
  row: number | null
  name: string
  message: string
}
function feoWarnKindLabel(kind: string): string {
  const labels: Record<string, string> = {
    level_gap: 'Пропущенный уровень поднят выше',
    level_duplicate: 'Одинаковые уровни склеены в один узел',
    sum_mismatch: 'Сумма не совпадает с кол-во × цена',
    sum_without_qty: 'Сумма задана без количества',
    parent_sum_mismatch: 'Бюджет родителя ≠ сумма дочерних',
    level_name_in_number_column: 'Название уровня стояло в числовой колонке',
    item_promoted_to_level2: 'Плановая позиция без уровней — создана направлением',
    item_type_unknown: 'Не распознан тип товар/услуга',
    column_shift: 'Похоже, колонки сдвинуты — число попало не в ту колонку',
    group_plan_ignored: 'План строки не записан — у категории есть подкатегории',
    plan_vs_items_mismatch: 'План строки не совпадает с суммой плановых позиций',
    plan_skipped_has_items: 'План строки не записан — у категории уже есть позиции',
  }
  return labels[kind] ?? kind
}
function feoWarnSubtitle(w: FeoWarning): string {
  return w.row != null ? `Стр. ${w.row} — ${w.message}` : w.message
}
interface FeoUnmatchedNode {
  id: number
  path: string
  kind: 'empty' | 'needs_mapping'
  suggestion: string | null
  suggestion_reason: string | null
  load: {
    purchases?: number
    purchase_items?: number
    wishes?: number
    wish_items?: number
    products?: number
    feo_planned_items?: number
  }
  blocking_purchases: { id: number; purchase_number: number | null; subject: string; status: string; status_label: string }[]
}
interface FeoRemapApplied {
  old_path: string
  new_path: string
  counts: Record<string, number>
}
interface FeoImportResult {
  created: number
  updated?: number
  skipped: number
  errors: { row: number; name: string; message: string }[]
  updated_details?: { row: number; name: string; reason: string }[]
  skipped_details?: { row: number; name: string; reason: string }[]
  created_details?: { row: number; name: string; reason: string }[]
  warnings?: FeoWarning[]
  unmatched?: FeoUnmatchedNode[]
  new_paths?: string[]
  deleted_count?: number
  relinked_count?: number
  deleted_details?: { path: string; reason: string }[]
  remap_applied?: FeoRemapApplied[]
  remap_aborted_reason?: string | null
  version_created?: boolean
  deletes_applied?: boolean
}
const feoImport = reactive({
  show: false, step: 1, file: null as File | null, fileList: [] as File[],
  loading: false,
  result: null as FeoImportResult | null,
  dryResult: null as FeoImportResult | null,
  previewData: null as any,
  selectedSheet: '',
  // ключ = unmatched.id, значение = выбранный new_path либо null («оставить как есть»)
  remap: {} as Record<number, string | null>,
})

const feoImportTargetSubsidy = ref<number | null>(null)

// FEO column mapping
const FEO_TARGET_FIELDS = [
  { value: 'subsidy',  title: 'Субсидия (название)',                          required: true },
  { value: 'lvl2',     title: 'Уровень 2 — Направление расходов по ФЭО',     required: true },
  { value: 'qty_lvl2',      title: 'Количество для Уровня 2 (Направление)',       required: false },
  { value: 'unit_lvl2',     title: 'Единица измерения для Уровня 2',              required: false },
  { value: 'amt_lvl2',      title: 'Плановая стоимость за ед. для Уровня 2 (Направление)', required: false },
  { value: 'plan_sum_lvl2', title: 'Сумма плана (Ур.2)',                          required: false },
  { value: 'lvl3',          title: 'Уровень 3 — Тип расходов по ФЭО',            required: false },
  { value: 'qty_lvl3',      title: 'Количество для Уровня 3 (Тип расходов)',      required: false },
  { value: 'unit_lvl3',     title: 'Единица измерения для Уровня 3',              required: false },
  { value: 'amt_lvl3',      title: 'Плановая стоимость за ед. для Уровня 3 (Тип расходов)', required: false },
  { value: 'plan_sum_lvl3', title: 'Сумма плана (Ур.3)',                          required: false },
  { value: 'lvl4',          title: 'Уровень 4 — Конкретизированный',              required: false },
  { value: 'qty_lvl4',      title: 'Количество для Уровня 4 (Конкретизир.)',      required: false },
  { value: 'unit_lvl4',     title: 'Единица измерения для Уровня 4',              required: false },
  { value: 'amt_lvl4',      title: 'Плановая стоимость за ед. для Уровня 4 (Конкретизир.)', required: false },
  { value: 'plan_sum_lvl4', title: 'Сумма плана (Ур.4)',                          required: false },
  { value: 'lvl5',          title: 'Плановая позиция (папку не создаёт)',        required: false },
  { value: 'item_type',       title: 'Товар/услуга',                             required: false },
  // Новый плоский 18-колоночный шаблон (2026-08-14): одна пара колонок «по ФЭО»/«плана»
  // на всю строку — вместо колонок-на-каждый-уровень выше. См. col_row_* в _do_feo_import.
  { value: 'row_feo_qty',     title: 'Количество по ФЭО',                        required: false },
  { value: 'row_feo_unit',    title: 'Ед. изм. по ФЭО',                          required: false },
  { value: 'row_feo_price',   title: 'Цена за единицу по ФЭО',                   required: false },
  { value: 'row_feo_sum',     title: 'Сумма по ФЭО',                             required: false },
  { value: 'row_plan_qty',    title: 'Плановое количество',                      required: false },
  { value: 'row_plan_unit',   title: 'Ед. изм. плана',                           required: false },
  { value: 'row_plan_price',  title: 'Плановая цена за единицу',                 required: false },
  { value: 'row_plan_sum',    title: 'Сумма плана',                              required: false },
  { value: 'quantity',      title: 'Количество для Уровня 5 (Товар/услуга)',      required: false },
  { value: 'unit',          title: 'Единица измерения (Ур.5: шт, кг, услуга)',   required: false },
  { value: 'item_amt',      title: 'Сумма по позиции (Ур.5)',                     required: false },
  { value: 'item_price',    title: 'Цена за ед. (Ур.5)',                          required: false },
  { value: 'feo_qty_lvl2',    title: 'Кол-во по ФЭО (Ур.2)',                     required: false },
  { value: 'feo_unit_lvl2',   title: 'Ед. изм. по ФЭО (Ур.2)',                  required: false },
  { value: 'feo_amount_lvl2', title: 'Стоимость по ФЭО (Ур.2)',                  required: false },
  { value: 'feo_sum_lvl2',    title: 'Сумма по ФЭО (Ур.2)',                      required: false },
  { value: 'feo_qty_lvl3',    title: 'Кол-во по ФЭО (Ур.3)',                     required: false },
  { value: 'feo_unit_lvl3',   title: 'Ед. изм. по ФЭО (Ур.3)',                  required: false },
  { value: 'feo_amount_lvl3', title: 'Стоимость по ФЭО (Ур.3)',                  required: false },
  { value: 'feo_sum_lvl3',    title: 'Сумма по ФЭО (Ур.3)',                      required: false },
  { value: 'feo_qty_lvl4',    title: 'Кол-во по ФЭО (Ур.4)',                     required: false },
  { value: 'feo_unit_lvl4',   title: 'Ед. изм. по ФЭО (Ур.4)',                  required: false },
  { value: 'feo_amount_lvl4', title: 'Стоимость по ФЭО (Ур.4)',                  required: false },
  { value: 'feo_sum_lvl4',    title: 'Сумма по ФЭО (Ур.4)',                      required: false },
  { value: 'code',     title: 'Код категории ФЭО (Ур.2–4)',                 required: false },
  { value: 'appendix', title: 'Номер приложения (Ур.2–4: Прил. 1, Прил. 2...)', required: false },
  { value: 'budget',   title: 'Финансирование по ФЭО (Ур.2–4)', required: false },
  { value: 'active',   title: 'Активна (да / нет)',                          required: false },
]
const feoDragMapping = ref<Record<string, number | null>>({})
const feoIgnoredCols = ref<number[]>([])
const feoDragOverTarget = ref<string | null>(null)
const feoResultPanels = ref<string[]>([])
function feoToggleResultPanel(key: string) {
  const i = feoResultPanels.value.indexOf(key)
  if (i >= 0) feoResultPanels.value.splice(i, 1)
  else feoResultPanels.value.push(key)
}
// При переходе на шаг 3 (dry-run) или шаг 5 (результат) раскрываем панели предупреждений
watch(() => feoImport.step, (step) => {
  if (step === 3 && feoImport.dryResult?.warnings?.length) {
    const warnKeys = [...new Set(feoImport.dryResult.warnings.map(w => w.kind))].map(k => 'dw_' + k)
    warnKeys.forEach(k => { if (!feoResultPanels.value.includes(k)) feoResultPanels.value.push(k) })
  } else if (step === 5 && feoImport.result?.warnings?.length) {
    const warnKeys = [...new Set(feoImport.result.warnings.map(w => w.kind))].map(k => 'rw_' + k)
    warnKeys.forEach(k => { if (!feoResultPanels.value.includes(k)) feoResultPanels.value.push(k) })
  }
})

// Узлы, которым не хватает цели переезда — требуют решения человека (шаг «Сопоставление»)
const feoUnmatchedNeedsMapping = computed<FeoUnmatchedNode[]>(() =>
  (feoImport.dryResult?.unmatched || []).filter(u => u.kind === 'needs_mapping'))
const feoHasSuggestions = computed(() => feoUnmatchedNeedsMapping.value.some(n => !!n.suggestion))
const feoRemapPlannedCount = computed(() =>
  feoUnmatchedNeedsMapping.value.filter(n => !!feoImport.remap[n.id]).length)
function feoAcceptAllSuggestions() {
  feoUnmatchedNeedsMapping.value.forEach(n => { if (n.suggestion) feoImport.remap[n.id] = n.suggestion })
}
const feoStep4MainLabel = computed(() => {
  const parts = ['Импортировать']
  if (feoRemapPlannedCount.value) parts.push(`перенести ${feoRemapPlannedCount.value}`)
  const deleted = feoImport.dryResult?.deleted_count ?? 0
  if (deleted) parts.push(`удалить ${deleted}`)
  return parts.join(', ')
})
function feoPluralRu(n: number, forms: [string, string, string]): string {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return forms[0]
  if ([2, 3, 4].includes(mod10) && ![12, 13, 14].includes(mod100)) return forms[1]
  return forms[2]
}
function feoLoadSummary(load: FeoUnmatchedNode['load'] | undefined): string {
  if (!load) return 'ничего'
  const parts: string[] = []
  if (load.purchases) parts.push(`${load.purchases} ${feoPluralRu(load.purchases, ['закупка', 'закупки', 'закупок'])}`)
  if (load.purchase_items) parts.push(`${load.purchase_items} ${feoPluralRu(load.purchase_items, ['позиция закупки', 'позиции закупки', 'позиций закупки'])}`)
  if (load.wishes) parts.push(`${load.wishes} ${feoPluralRu(load.wishes, ['заявка', 'заявки', 'заявок'])}`)
  if (load.wish_items) parts.push(`${load.wish_items} ${feoPluralRu(load.wish_items, ['позиция заявки', 'позиции заявки', 'позиций заявки'])}`)
  if (load.products) parts.push(`${load.products} ${feoPluralRu(load.products, ['товар', 'товара', 'товаров'])}`)
  if (load.feo_planned_items) parts.push(`${load.feo_planned_items} ${feoPluralRu(load.feo_planned_items, ['плановая позиция', 'плановые позиции', 'плановых позиций'])}`)
  return parts.length ? parts.join(', ') : 'ничего'
}

const feoCurrentSheet = computed(() => {
  if (!feoImport.previewData) return null
  const sheets = feoImport.previewData.sheets
  return sheets.find((s: any) => s.name === feoImport.selectedSheet) || sheets[0]
})
const feoCurrentHeaders = computed(() => feoCurrentSheet.value?.headers || [])
const feoMappingValid = computed(() =>
  feoDragMapping.value['lvl2'] != null &&
  (feoDragMapping.value['subsidy'] != null || feoImportTargetSubsidy.value != null)
)
const feoUnmappedCount = computed(() =>
  feoCurrentHeaders.value.filter((_: any, i: number) => !feoIsMapped(i) && !feoIsIgnored(i)).length
)

function feoIsMapped(idx: number): boolean {
  return Object.values(feoDragMapping.value).includes(idx)
}
function feoIsIgnored(idx: number): boolean {
  return feoIgnoredCols.value.includes(idx)
}
function feoIsTargetFilled(field: string): boolean {
  return feoDragMapping.value[field] != null
}
function feoGetColumnLabel(idx: number): string {
  return (feoCurrentHeaders.value[idx] as string) || `Столбец ${idx + 1}`
}
function feoGetSamples(idx: number): string[] {
  const sample = feoCurrentSheet.value?.sample || []
  return (sample as any[][]).slice(0, 3)
    .map((row: any[]) => String(row[idx] ?? '').trim())
    .filter(Boolean)
}
function feoOnDragStart(idx: number, e: DragEvent) {
  e.dataTransfer!.effectAllowed = 'move'
  e.dataTransfer!.setData('text/plain', String(idx))
}
function feoOnDropToTarget(field: string, e: DragEvent) {
  const idx = parseInt(e.dataTransfer!.getData('text/plain'))
  for (const f of Object.keys(feoDragMapping.value)) {
    if (feoDragMapping.value[f] === idx) feoDragMapping.value[f] = null
  }
  feoDragMapping.value[field] = idx
  feoDragOverTarget.value = null
}
function feoOnDropToUnresolved(e: DragEvent) {
  const idx = parseInt(e.dataTransfer!.getData('text/plain'))
  for (const f of Object.keys(feoDragMapping.value)) {
    if (feoDragMapping.value[f] === idx) feoDragMapping.value[f] = null
  }
  feoDragOverTarget.value = null
}
function feoUnmapTarget(field: string) {
  feoDragMapping.value[field] = null
}
function feoIgnoreColumn(idx: number) {
  for (const f of Object.keys(feoDragMapping.value)) {
    if (feoDragMapping.value[f] === idx) feoDragMapping.value[f] = null
  }
  if (!feoIgnoredCols.value.includes(idx)) feoIgnoredCols.value.push(idx)
}

function feoAutoMap(headers: string[]) {
  const mapping: Record<string, number | null> = {}
  for (const f of FEO_TARGET_FIELDS) mapping[f.value] = null
  const KEYWORDS: Record<string, string[]> = {
    subsidy:  ['субсидия'],
    lvl2:     ['уровень 2', 'направление расходов', 'level 2'],
    qty_lvl2:  ['кол-во (ур.2)', 'кол-во ур.2', 'количество (ур.2)'],
    unit_lvl2: ['ед. изм. (ур.2)', 'ед.изм. ур.2', 'единица ур.2'],
    // amt_lvl2 = цена за ед. — только специфичные алиасы, без «сумма» (сумму забирает plan_sum_lvl2)
    amt_lvl2:  ['плановая стоимость за ед. (ур.2)', 'плановая стоимость (ур.2)', 'стоимость за ед. (ур.2)', 'стоимость ур.2'],
    plan_sum_lvl2: ['сумма плана (ур.2)', 'плановая сумма (ур.2)', 'сумма ур.2'],
    lvl3:      ['уровень 3', 'тип расходов', 'level 3'],
    qty_lvl3:  ['кол-во (ур.3)', 'кол-во ур.3', 'количество (ур.3)'],
    unit_lvl3: ['ед. изм. (ур.3)', 'ед.изм. ур.3', 'единица ур.3'],
    // amt_lvl3 = цена за ед.
    amt_lvl3:  ['плановая стоимость за ед. (ур.3)', 'плановая стоимость (ур.3)', 'стоимость за ед. (ур.3)', 'стоимость ур.3'],
    plan_sum_lvl3: ['сумма плана (ур.3)', 'плановая сумма (ур.3)', 'сумма ур.3'],
    lvl4:         ['уровень 4', 'конкретизир', 'level 4'],
    qty_lvl4:     ['кол-во (ур.4)', 'кол-во ур.4', 'количество (ур.4)'],
    unit_lvl4:    ['ед. изм. (ур.4)', 'ед.изм. ур.4', 'единица ур.4'],
    // amt_lvl4 = цена за ед.
    amt_lvl4:     ['плановая стоимость за ед. (ур.4)', 'плановая стоимость (ур.4)', 'стоимость за ед. (ур.4)', 'стоимость ур.4'],
    plan_sum_lvl4: ['сумма плана (ур.4)', 'плановая сумма (ур.4)', 'сумма ур.4'],
    // feo_sum_* идут ДО feo_amount_* (более специфичны «сумма по фэо»)
    feo_sum_lvl2:    ['сумма по фэо (ур.2)', 'сумма по фэо ур.2'],
    // Бэкенд (see find_col в import_feo_from_excel) НЕ имеет generic-фолбэка без
    // «(Ур.2)» для этих трёх — иначе эти ключи перехватывали бы плоские колонки
    // нового 18-колоночного шаблона («Количество по ФЭО» и т.п.), которые обязаны
    // достаться row_feo_qty/row_feo_unit/row_feo_price ниже
    feo_qty_lvl2:    ['кол-во по фэо (ур.2)', 'кол-во по фэо ур.2'],
    feo_unit_lvl2:   ['ед. изм. по фэо (ур.2)', 'ед. изм. по фэо ур.2'],
    feo_amount_lvl2: ['стоимость по фэо (ур.2)', 'стоимость по фэо ур.2'],
    feo_sum_lvl3:    ['сумма по фэо (ур.3)', 'сумма по фэо ур.3'],
    feo_qty_lvl3:    ['кол-во по фэо (ур.3)', 'кол-во по фэо ур.3'],
    feo_unit_lvl3:   ['ед. изм. по фэо (ур.3)', 'ед. изм. по фэо ур.3'],
    feo_amount_lvl3: ['стоимость по фэо (ур.3)', 'стоимость по фэо ур.3'],
    feo_sum_lvl4:    ['сумма по фэо (ур.4)', 'сумма по фэо ур.4'],
    feo_qty_lvl4:    ['кол-во по фэо (ур.4)', 'кол-во по фэо ур.4'],
    feo_unit_lvl4:   ['ед. изм. по фэо (ур.4)', 'ед. изм. по фэо ур.4'],
    feo_amount_lvl4: ['стоимость по фэо (ур.4)', 'стоимость по фэо ур.4'],
    lvl5:     ['плановая позиция', 'уровень 5', 'плановый товар', 'level 5'],
    // Новый плоский 18-колоночный шаблон (2026-08-14): одна пара «по ФЭО»/«плана» на
    // всю строку. Объявлены ПОСЛЕ всех per-level ключей выше и ДО generic-фолбэков
    // ниже (quantity/unit/item_amt/item_price) — порядок и слова совпадают с
    // col_row_* в import_feo_mapped/import_feo_from_excel (backend). lvl5 обязан
    // резолвиться раньше item_type, иначе «Уровень 5 (Плановый товар/услуга)»
    // старого шаблона перехватит item_type своим «товар/услуга» — здесь lvl5 уже
    // объявлен строкой выше, порядок соблюдён.
    row_feo_qty:    ['количество по фэо'],
    row_feo_unit:   ['ед. изм. по фэо'],
    row_feo_price:  ['цена за единицу по фэо', 'цена за ед. по фэо'],
    row_feo_sum:    ['сумма по фэо'],
    row_plan_qty:   ['плановое количество'],
    row_plan_unit:  ['ед. изм. плана'],
    row_plan_price: ['плановая цена за единицу', 'плановая цена за ед.'],
    row_plan_sum:   ['сумма плана'],
    item_type:      ['товар/услуга', 'тип позиции'],
    code:     ['код'],
    appendix: ['приложение'],
    budget:   ['финансирование', 'бюджет'],
    quantity: ['количество (ур.5)', 'количество ур.5', 'кол-во (ур.5)', 'кол-во ур.5'],
    unit:     ['ед. измерения (ур.5)', 'ед. изм. (ур.5)', 'ед.изм. ур.5', 'единица ур.5', 'ед. изм', 'ед.изм', 'единица'],
    // item_amt = итог позиции (amount); item_price = цена за ед. — специфичные ключи первыми
    item_amt:   ['сумма по позиции (ур.5)', 'сумма плановая', 'сумма (ур.5)', 'плановая стоимость за ед. (ур.5)', 'плановая стоимость (ур.5)', 'стоимость за ед. (ур.5)', 'стоимость ур.5', 'сумма ур'],
    item_price: ['цена за ед. (ур.5)', 'стоимость за ед. (ур.5)'],
    active:   ['активна', 'активен'],
  }
  // Каждая колонка достаётся ровно одному полю: без этого generic-ключи
  // («ед. изм») утаскивали колонку Ур.2 в поле Ур.5
  const used = new Set<number>()
  for (const [field, kws] of Object.entries(KEYWORDS)) {
    for (const kw of kws) {
      let found = -1
      for (let i = 0; i < headers.length; i++) {
        if (used.has(i)) continue
        if (headers[i].toLowerCase().includes(kw)) { found = i; break }
      }
      if (found >= 0) {
        mapping[field] = found
        used.add(found)
        break
      }
    }
  }
  feoDragMapping.value = mapping
}

// ── FEO Level 5: Плановые позиции vs Фактические ──
interface FeoPlannedItem {
  id: number
  feo_category_id: number
  name: string
  quantity: number | null
  unit: string | null
  amount: number | null
  // Цена ЗА ЕДИНИЦУ (владелец, 2026-09-02) — необязательное поле, см. докстринг
  // FeoPlannedItem.unit_price (backend/app/models/feo_planned_item.py) и
  // assert_tz_not_over_plan (backend/app/services/feo_plan.py): задана → план
  // полноценный (кол-во/цена/сумма проверяются); NULL → amount сама по себе
  // итоговая сумма, quantity ориентировочное. PUT здесь — ПОЛНАЯ замена (см.
  // остальные PATCHABLE-комментарии в файле) — все места, шлющие PUT
  // /feo-planned-items/{id}, обязаны передавать unit_price существующей
  // позиции явно, иначе он молча обнулится.
  unit_price?: number | null
  notes: string | null
  is_active: boolean
  payment_mode?: 'one_time' | 'monthly'
  planned_date?: string | null
  monthly_start_date?: string | null
  months_count?: number | null
  monthly_amount?: number | null
  // Владелец (2026-08-12, замечание 2): порядок позиций внутри категории —
  // настраиваемый (стрелки вверх/вниз), см. reorderPlannedItem ниже.
  sort_order?: number | null
  // Блок 1 (план zany-fluttering-mountain.md, 2026-08-14): товар / услуга / работа.
  item_type?: string | null
  // Владелец (2026-08-18): «данные есть [у связанных позиций закупок], почему
  // не подтягиваются?» — свой item_type, иначе унаследованный от purchase_items,
  // иначе null (GET /feo-planned-items/comparison, см. FeoPlannedItemOut в бэкенде).
  item_type_effective?: string | null
  item_type_inherited?: boolean
  // Происхождение плановой позиции (владелец, 2026-09-01) — ДВЕ НЕЗАВИСИМЫЕ
  // галочки, не переключатель: is_feo_breakdown — жёсткая построчная разбивка
  // ФЭО реально есть (покупать будут именно это, отчётность строгая);
  // is_internal_plan — в ФЭО была только более широкая категория (или позиции
  // не было вовсе), состав придумали сами. См. backend/app/models/feo_planned_item.py.
  is_feo_breakdown?: boolean
  is_internal_plan?: boolean
}
// Стадия уточнения позиции (ФЭО → План → Что выставили на закупку → Номенклатура
// подрядчика → Приняли) — справочная детализация, отдаётся бэкендом внутри FeoActualItem.stages.
interface FeoStage {
  key: string
  label: string
  name: string
  quantity: number | null
  unit: string | null
  unit_price: number | null
  total: number | null
}
interface FeoActualItem {
  purchase_item_id: number
  item_name: string
  quantity: number | null
  unit: string | null
  unit_price: number | null
  total_price: number | null
  feo_planned_item_id: number | null
  purchase_id: number
  purchase_number: number | null
  registry_number: string | null
  purchase_status: string | null
  wish_id?: number | null
  contract_number: string | null
  contractor_name: string | null
  product_photo?: string | null
  // Требование владельца (2026-08-05): факт появляется с «Заказано», уточняется закрывающими
  // документами при «Поставлено»/«Оплачено» — см. calcDiff/FACT_STATUSES ниже.
  final_unit_price?: number | null
  final_total?: number | null
  acceptance_doc_amount?: number | null
  contract_price?: number | null
  purchase_items_count?: number | null
  fact_amount?: number | null
  fact_confirmed?: boolean
  fact_allocated?: boolean
  over_plan?: boolean
  // Разворот по стадиям уточнения наименования/кол-ва (панель «план vs факт», см. FeoStage)
  stages?: FeoStage[]
  // Владелец, 2026-08-13: остановка закупки — read-only, системой проставляется в
  // POST /api/wishes/{wish_id}/stop. ⚠️ /feo-planned-items/comparison пока не
  // выбирает и не отдаёт эти поля на строке позиции (только Purchase.status) —
  // поля опциональны и на практике сейчас всегда undefined, маркер «ЗАКУПКА
  // ОСТАНОВЛЕНА» ниже по файлу не появится, пока бэкенд их не добавит.
  stopped_at?: string | null
  stopped_by_name?: string | null
}
const expandedItemPanels = ref<Set<number>>(new Set(feoDisplayPrefs.expandedItemPanels || []))
const comparisonData = ref<Record<number, { planned: FeoPlannedItem[]; actual: FeoActualItem[] }>>({})
const loadingComparison = ref<Set<number>>(new Set())

// Photo preview overlay
const photoPreview = ref<{ src: string; title: string } | null>(null)

// Map dialog
const showMapDialog = ref(false)
const mapTarget = ref<FeoActualItem | null>(null)
const mapCategoryId = ref<number | null>(null)
const mappingInProgress = ref(false)

// Add planned item dialog
const showAddPlannedDialog = ref(false)
const addPlannedCategoryId = ref<number | null>(null)
const savingPlannedItem = ref(false)
// Флаг «эта позиция заводится действием "Перенести в плановую позицию"» (не обычной
// кнопкой «Добавить плановую») — savePlannedItem после успешного создания по нему
// очищает planned_quantity/planned_amount категории (см. ниже), иначе поля категории
// продолжают заслонять созданную запись в расчёте плана листа. Сбрасывается и при
// отмене/закрытии диалога любым способом (watch на showAddPlannedDialog ниже), чтобы
// следующее обычное «Добавить плановую» не подхватило чужой id и не очистило план
// категории, которую пользователь трогать не просил.
const convertFromCategoryPlanId = ref<number | null>(null)
// Флаг «эта плановая позиция заводится из КОНКРЕТНОЙ позиции закупки» (кнопка
// mdi-plus-box-outline в блоке «Не привязаны к плану», см. openCreatePlannedFromActual)
// — хранит purchase_item_id, который savePlannedItem обязан привязать к только что
// созданной плановой позиции (POST /feo-planned-items/map), иначе позиция создастся, но
// закупка так и останется висеть в «Не привязаны» до следующего ручного клика. Сбрасывается
// тем же watch(showAddPlannedDialog), что и convertFromCategoryPlanId — по той же причине
// (не «протекать» в следующее открытие диалога другим путём).
const createPlannedFromActualId = ref<number | null>(null)
const plannedItemForm = ref({
  name: '',
  quantity: null as number | null,
  unit: '',
  // Плановая стоимость за единицу, ₽ (владелец, 2026-09-01) — UI-поле, подставляется
  // из каталога при выборе товара (см. onPlannedItemProductPick), полностью
  // редактируемо. FeoPlannedItem (backend) СВОЕГО поля под цену за единицу не имеет
  // (только amount — итоговая сумма), поэтому unitPrice в бэкенд не уходит: пока он
  // задан и не равен 0, им лишь пересчитывается amount (см. watch ниже).
  unitPrice: null as number | null,
  amount: null as number | null,
  payment_mode: 'one_time' as 'one_time' | 'monthly',
  planned_date: '' as string,
  monthly_start_date: '' as string,
  months_count: null as number | null,
  monthly_amount: null as number | null,
  // Происхождение (владелец, 2026-09-01) — ДВЕ НЕЗАВИСИМЫЕ галочки, см. чекбоксы
  // диалога выше. Дефолт «внутренний план» — по правилу бэкфилла (см. миграцию
  // aa1b2c3d4e5f_feo_planned_item_origin.py): позиция, заводимая человеком через
  // этот диалог, по умолчанию не является жёсткой построчной разбивкой ФЭО, пока
  // человек явно не отметит обратное.
  is_feo_breakdown: false,
  is_internal_plan: true,
})
// Владелец (2026-08-31): «Добавить плановую позицию» — подсказки/картинка из
// каталога товаров через InlineProductMatch, но FeoPlannedItem (backend модель)
// НЕ имеет product_id — это чисто UI-состояние диалога, ничего из этого не
// уходит в POST /feo-planned-items/ (см. savePlannedItem ниже, шлёт только
// name/quantity/unit/amount/...). Сбрасывается везде, где сбрасывается
// plannedItemForm (openAddPlannedItem/openConvertManualPlanToItem/
// openCreatePlannedFromActual) и при закрытии диалога любым способом.
const addPlannedProductId = ref<number | null>(null)
const addPlannedProductPhoto = ref<string | null>(null)
const addPlannedMatchConfirmed = ref<boolean | undefined>(undefined)
// Происхождение цены товара, подставленной при выборе из каталога (владелец,
// 2026-09-01: «указывать информацию по дате стоимости за единицу — как при
// формировании заявки, чтобы человек мог понять, насколько он адекватно
// планирует»). MatchCandidate (POST /products/match) уже отдаёт эти поля —
// см. useItemMatching.ts/backend/app/routers/products.py — читаем их отсюда
// напрямую, БЕЗ импорта usePriceFreshness.ts/PriceFreshnessStamp.vue (эти два
// файла ещё не в репозитории, параллельная незакоммиченная работа — импорт
// уронит сборку на проде, см. правила задачи). Подпись строим сами, ниже.
const addPlannedPriceMeta = ref<{
  price_updated_at: string | null
  price_source: string | null
  price_source_ref: string | null
} | null>(null)

// Русские подписи источника цены — минимальная копия PRICE_SOURCE_LABELS
// (usePriceFreshness.ts), намеренно НЕ импортированная (см. коммент выше у
// addPlannedPriceMeta). Держать в синхроне вручную, если появятся новые источники.
const PLANNED_PRICE_SOURCE_LABELS: Record<string, string> = {
  contract: 'договор',
  kp: 'КП',
  manual: 'вручную',
  import: 'импорт',
  monitoring: 'мониторинг цен',
}

function formatRuDateShort(iso: string | null | undefined): string | null {
  if (!iso) return null
  const d = new Date(iso)
  if (isNaN(d.getTime())) return null
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

// Подпись под полем «Плановая стоимость за единицу» — честно говорит, откуда цена
// и когда актуализирована, либо что данных нет (требование владельца, п.4).
const addPlannedPriceCaption = computed<string | null>(() => {
  if (addPlannedProductId.value == null) return null
  if (plannedItemForm.value.unitPrice == null) {
    return 'У товара в каталоге не указана цена — введите стоимость за единицу вручную.'
  }
  const meta = addPlannedPriceMeta.value
  const dateStr = meta ? formatRuDateShort(meta.price_updated_at) : null
  const parts: string[] = [dateStr ? `цена из каталога от ${dateStr}` : 'цена из каталога, дата актуализации не указана']
  const sourceLabel = meta?.price_source ? (PLANNED_PRICE_SOURCE_LABELS[meta.price_source] || meta.price_source) : null
  if (sourceLabel) {
    parts.push(`источник: ${sourceLabel}${meta?.price_source_ref ? ` · ${meta.price_source_ref}` : ''}`)
  } else {
    parts.push('источник не указан')
  }
  return parts.join(', ')
})

// Плановая сумма считается автоматически, пока стоимость за единицу задана и не
// равна 0 (требование владельца, п.3); количество по умолчанию 1, если поле пусто —
// «добавляется плановая позиция по одной штуке».
const plannedItemAmountIsComputed = computed(() => {
  const p = plannedItemForm.value.unitPrice
  return p != null && Number(p) !== 0
})

function recalcPlannedAmountFromUnitPrice() {
  if (!plannedItemAmountIsComputed.value) return
  const price = Number(plannedItemForm.value.unitPrice)
  const qtyRaw = plannedItemForm.value.quantity
  const qty = qtyRaw != null && Number(qtyRaw) > 0 ? Number(qtyRaw) : 1
  plannedItemForm.value.amount = Math.round(qty * price * 100) / 100
}

watch(
  [() => plannedItemForm.value.quantity, () => plannedItemForm.value.unitPrice],
  () => recalcPlannedAmountFromUnitPrice(),
)

// Единица измерения + цена/дата/источник товара каталога — ОДНИМ запросом
// (GET /feo-planned-items/product-hint, добавлен рядом с этим диалогом — см.
// докстринг эндпоинта). Координатор (2026-09-01) поймал зависимость от чужой
// незакоммиченной работы: candidate.price_updated_at/price_source/price_source_ref
// (MatchCandidate из POST /products/match) существуют только в РАБОЧЕМ ДЕРЕВЕ
// параллельной сессии — в закоммиченном backend/app/routers/products.py (который
// мы не трогаем) этих полей нет, и на проде подпись о цене всегда молчала бы.
// product-hint читает price/price_updated_at/price_source/price_source_ref
// напрямую из МОДЕЛИ Product — эти колонки уже закоммичены (app/models/product.py:
// 25,40-42) — и потому не зависит от чужого незакоммиченного кода. Это ОСНОВНОЙ
// источник цены/даты/источника; candidate.* (см. onPlannedItemProductPick) —
// только запасной вариант на время, пока этот запрос не ответил/если он упал.
// Гвард по product_id — пока запрос летал, пользователь мог выбрать другой товар.
async function applyPlannedProductHint(productId: number) {
  try {
    const res = await apiFetch<{
      unit: string | null
      price: number | null
      price_updated_at: string | null
      price_source: string | null
      price_source_ref: string | null
    }>(`/feo-planned-items/product-hint?product_id=${productId}`)
    if (addPlannedProductId.value !== productId) return
    if (res?.unit) plannedItemForm.value.unit = res.unit
    if (res && res.price != null) {
      plannedItemForm.value.unitPrice = Number(res.price)
    }
    addPlannedPriceMeta.value = {
      price_updated_at: res?.price_updated_at ?? null,
      price_source: res?.price_source ?? null,
      price_source_ref: res?.price_source_ref ?? null,
    }
    recalcPlannedAmountFromUnitPrice()
  } catch {
    // Запрос не удался — остаётся то, что уже подставлено из candidate (запасной
    // вариант, см. onPlannedItemProductPick), поля остаются редактируемыми.
  }
}

// InlineProductMatch @pick — пользователь выбрал кандидата из каталога. Имя —
// сразу из кандидата; единица/цена/дата/источник — предзаполняются из
// candidate как ЗАПАСНОЙ вариант (может не содержать price_updated_at/
// price_source на проде, см. applyPlannedProductHint выше), а затем
// перезаписываются авторитетным ответом product-hint. Оба поля (единица,
// стоимость за единицу) остаются полностью редактируемыми. Перезаписываем
// unitPrice/name/фото при КАЖДОМ выборе (не только если поле было пусто) —
// это осознанный выбор другого товара, а не первичное предзаполнение.
function onPlannedItemProductPick(c: MatchCandidate) {
  plannedItemForm.value.name = c.name || plannedItemForm.value.name
  addPlannedProductId.value = c.product_id
  addPlannedProductPhoto.value = c.photo_url ?? null
  addPlannedMatchConfirmed.value = true
  const price = c.contract_price ?? c.price
  plannedItemForm.value.unitPrice = price != null ? Number(price) : null
  addPlannedPriceMeta.value = {
    price_updated_at: c.price_updated_at ?? null,
    price_source: c.price_source ?? null,
    price_source_ref: c.price_source_ref ?? null,
  }
  recalcPlannedAmountFromUnitPrice()
  void applyPlannedProductHint(c.product_id)
}

function onPlannedItemProductClear() {
  addPlannedProductId.value = null
  addPlannedProductPhoto.value = null
  addPlannedMatchConfirmed.value = undefined
  addPlannedPriceMeta.value = null
  plannedItemForm.value.name = ''
  plannedItemForm.value.unitPrice = null
}

async function toggleItemPanel(node: FeoNode) {
  const id = node.id
  if (expandedItemPanels.value.has(id)) {
    expandedItemPanels.value.delete(id)
    return
  }
  expandedItemPanels.value.add(id)
  if (comparisonData.value[id]) return
  loadingComparison.value.add(id)
  try {
    const subsId = selectedId.value
    const res = await apiFetch<{ planned: FeoPlannedItem[]; actual: FeoActualItem[] }>(
      `/feo-planned-items/comparison?feo_category_id=${id}${subsId ? `&subsidy_id=${subsId}` : ''}`
    )
    comparisonData.value[id] = res
    applyDefaultPlannedExpansion(id)
  } catch {
    comparisonData.value[id] = { planned: [], actual: [] }
  } finally {
    loadingComparison.value.delete(id)
  }
}

async function refreshComparison(categoryId: number) {
  const subsId = selectedId.value
  const res = await apiFetch<{ planned: FeoPlannedItem[]; actual: FeoActualItem[] }>(
    `/feo-planned-items/comparison?feo_category_id=${categoryId}${subsId ? `&subsidy_id=${subsId}` : ''}`
  )
  comparisonData.value[categoryId] = res
  applyDefaultPlannedExpansion(categoryId)
}

// ── Позиции «из заявок» в дереве ФЭО (раскрытие листа-папки) ──
interface FeoReqItem {
  id: number
  item_name: string
  quantity: number
  unit: string | null
  unit_price: number
  total_price: number
  purchase_id: number
  purchase_number: number | null
  registry_number: string | null
  purchase_status: string
  wish_id: number | null
  category: string
  product_type: string
  product_photo?: string | null
  // Phase KPI-drilldown: расширено бэкендом, старый бэк может не отдавать — все опциональны
  contract_id?: number | null
  purchase_contract_type?: string | null
  contract_type?: string | null
  contract_status?: string | null
  contract_number?: string | null
  // Anti-doublecount: позиция привязана к плановой позиции (feo_planned_items) — РАСХОДУЕТ
  // её план, а не складывается с ним поверх. wish_item_id — исходная позиция заявки (справочно).
  feo_planned_item_id?: number | null
  wish_item_id?: number | null
  // Задача владельца «план ≠ факт» (сессия 2026-08-06, шаг 5): снимок ТЗ — заморожен
  // с момента объявления закупки (см. purchase_items.planned_*), фолбэк на текущие
  // quantity/unit_price/total_price для старых записей без снимка — см. backend
  // /feo-categories/planned-purchase-items.
  planned_quantity?: number | null
  planned_unit_price?: number | null
  planned_total?: number | null
  // Факт — та же формула, что и FeoActualItem.fact_amount (comparison-эндпоинт):
  // точное сопоставление по ContractItem.source_item_id, иначе пропорция от
  // purchases.contract_price. null — факта ещё нет (план_schedule/нет договорных данных).
  fact_amount?: number | null
  fact_quantity?: number | null
  fact_unit_price?: number | null
  fact_confirmed?: boolean
  fact_allocated?: boolean
  // Владелец, 2026-08-13: остановка закупки — см. аналогичный комментарий у
  // FeoActualItem.stopped_at. /feo-categories/planned-purchase-items тоже пока
  // не отдаёт эти поля — на практике всегда undefined.
  stopped_at?: string | null
  stopped_by_name?: string | null
}
interface FeoReqRow {
  key: string
  header: string
  level: number
  count: number
  sumQty: number
  sum: number
  group: FeoVirtualGroup | null
  items: FeoReqItem[]
}
const plannedItemsByCat = ref<Record<number, FeoReqItem[]>>({})
const plannedItemsLoaded = ref(false)
const expandedReqItems = ref<Set<number>>(new Set(feoDisplayPrefs.expandedReqItems || []))
const feoItemsGroupBy = ref<'none' | 'category' | 'category_type'>(feoDisplayPrefs.feoItemsGroupBy || 'none')

interface FeoPurchaseFolder {
  purchase_id: number
  purchase_number: number | null
  registry_number: string | null
  purchase_status: string
  wish_id: number | null
  qty: number
  unit: string | null
  total: number
  items: FeoReqItem[]
  // Владелец, 2026-08-13: остановка закупки — переносится из items[0] при
  // группировке (см. purchaseFoldersFor), см. комментарий у FeoReqItem.stopped_at.
  stopped_at?: string | null
  stopped_by_name?: string | null
}
const expandedPurchases = ref<Set<number>>(new Set())
function togglePurchaseFolder(pid: number) {
  if (expandedPurchases.value.has(pid)) expandedPurchases.value.delete(pid)
  else expandedPurchases.value.add(pid)
}

// Раскрытие позиций закупок, привязанных к конкретной плановой позиции (Ур.5) в панели
// «план vs факт». Персистится в FEO_DISPLAY_PREFS_KEY наравне с остальными настройками
// дерева (требование владельца 2026-08-09) — см. saveFeoDisplayPrefs/watch ниже.
// Возвращено из отката e0db76a (план zany-fluttering-mountain.md, п.4): владелец решил,
// что закупки под плановой строкой «нет вовсе», если её не видно без клика — раскрыто ПО
// УМОЛЧАНИЮ, когда под строкой есть хотя бы одна закупка (см. applyDefaultPlannedExpansion).
// Явное решение пользователя свернуть строку (collapsedPlannedItems, см. интерфейс
// FeoDisplayPrefs) имеет приоритет над этим правилом — именно поэтому toggle ниже пишет
// в ОБА множества.
const expandedPlannedItems = ref<Set<number>>(new Set(feoDisplayPrefs.expandedPlannedItems || []))
const collapsedPlannedItems = ref<Set<number>>(new Set(feoDisplayPrefs.collapsedPlannedItems || []))
function togglePlannedItemFolder(plannedId: number) {
  if (expandedPlannedItems.value.has(plannedId)) {
    expandedPlannedItems.value.delete(plannedId)
    collapsedPlannedItems.value.add(plannedId)
  } else {
    expandedPlannedItems.value.add(plannedId)
    collapsedPlannedItems.value.delete(plannedId)
  }
}

// Применяет правило «раскрыто по умолчанию, если под плановой позицией есть закупка» —
// вызывается сразу после того, как comparisonData[catId] загрузился (единственный момент,
// когда factForPlanned() вообще может быть непустым), см. toggleItemPanel/refreshComparison/
// ensureComparison. Пропускает id из collapsedPlannedItems (пользователь явно свернул —
// его выбор приоритетнее) и id, уже присутствующие в expandedPlannedItems (нечего делать).
function applyDefaultPlannedExpansion(catId: number) {
  const data = comparisonData.value[catId]
  if (!data) return
  const cat = feoCategories.value.find(c => c.id === catId)
  const plannedIds: number[] = data.planned.length
    ? data.planned.map(p => p.id)
    : (cat && (cat.planned_quantity != null || cat.planned_amount != null)) ? [-catId] : []
  for (const pid of plannedIds) {
    if (collapsedPlannedItems.value.has(pid)) continue
    if (expandedPlannedItems.value.has(pid)) continue
    if (factForPlanned(catId, pid).length > 0) {
      expandedPlannedItems.value.add(pid)
    }
  }
}

// Замечание владельца 1 (2026-08-12): «по одной сворачивать неудобно, надо развернуть
// все сразу, посмотреть, как что покупалось, и свернуть все сразу». Кнопка-переключатель
// в шапке раскрытой категории — использует ТЕ ЖЕ expandedPlannedItems/collapsedPlannedItems
// (persist через FEO_DISPLAY_PREFS_KEY уже работает, см. watch ниже), ничего нового не заводит.
function anyPlannedExpandedFor(node: FeoNode): boolean {
  return displayPlannedRowsFor(node).some(p => expandedPlannedItems.value.has(p.id))
}
function toggleAllPlannedItemsForCategory(node: FeoNode) {
  const ids = displayPlannedRowsFor(node).map(p => p.id)
  const collapse = ids.some(id => expandedPlannedItems.value.has(id))
  for (const id of ids) {
    if (collapse) {
      expandedPlannedItems.value.delete(id)
      collapsedPlannedItems.value.add(id)
    } else {
      expandedPlannedItems.value.add(id)
      collapsedPlannedItems.value.delete(id)
    }
  }
}

// Разворот строки позиции закупки в подстроки стадий уточнения (ФЭО/План/Закупка/Договор/Приёмка).
// Ключ — строка вида `<префикс-типа-строки>-<purchase_item_id | it.id>`, префикс совпадает с
// префиксом :key соответствующей <tr v-for> ниже, чтобы не пересекаться между типами строк.
const expandedStageRows = ref<Set<string>>(new Set())
function toggleStageRow(key: string) {
  if (expandedStageRows.value.has(key)) expandedStageRows.value.delete(key)
  else expandedStageRows.value.add(key)
}

// hasReqItems/toggleReqItems (переключатель Таблицы B на САМОМ листе) убраны 2026-08-07 —
// после ШАГ 1 плана дедупликации у листа единственный источник детализации это
// expandedItemPanels/toggleItemPanel (Таблица A), см. шеврон/папку в имени узла выше.
// expandedReqItems осталась — она всё ещё используется reqExpandedFor() для владельцев
// (hasChildren-категорий), там Таблица B легитимна (см. reqOwnersAfter).

// ── Слияние: позиции из заявок ↔ ручные дочерние позиции ФЭО ──
// Миграция плана категории → плановые позиции (сессия 2026-08-12): у мигрированного
// листа planned_quantity/planned_amount оба null, хотя план есть (живёт в активных
// плановых позициях) — без фолбэка isManualPosLeaf вернула бы false, и «строгая
// фильтрация ручные/из заявок» (v-if в шапке дерева, plannedBase==='requests')
// перестала бы прятать мигрированный лист, как прятала до миграции. Фолбэк —
// planTreeByCat.plan_manual > 0, тот же сигнал «есть план в позициях», что и в
// feoPlannedTotalFor выше (там же объяснение поля).
function isManualPosLeaf(node: FeoNode): boolean {
  if (node.hasChildren) return false
  if (node.planned_quantity != null || node.planned_amount != null) return true
  const t = planTreeByCat.value[node.id]
  return !!(t && Number(t.plan_manual || 0) > 0)
}

// Задача владельца «направление со временем может наполниться, соответственно
// должно считаться и оно» (сессия 2026-08-12, повод — «Бинт марлевый» 48 441,80 ₽
// привязан прямо к «Окружным», а это направление с 5 подкатегориями, не лист —
// панель «Плановые позиции» раньше раскрывалась ТОЛЬКО у листа, состав был не
// посмотреть). Раскрывать панель у узла с детьми имеет смысл, только если у него
// САМОГО есть активные FeoPlannedItem (иначе раскрывать нечего — там всегда пусто).
//
// Выбор способа определения «есть свои позиции» БЕЗ похода в сеть за comparisonData
// для каждого узла подряд (это раскрывало бы GET .../comparison на КАЖДУЮ группу
// дерева сразу при рендере — дорого и не нужно, панель и так грузится ЛЕНИВО по
// клику): бэкенд (compute_feo_plan_tree, app/services/feo_plan.py, ветка с детьми)
// теперь считает plan_manual направления как «Σ plan_manual детей + Σ amount
// СОБСТВЕННЫХ активных плановых позиций узла» (own_amt). Раз оба числа уже лежат в
// planTreeByCat (bulk-загружен один раз в loadFeo для ВСЕХ категорий сразу),
// «plan_manual узла минус Σ plan_manual его НЕПОСРЕДСТВЕННЫХ детей» и есть own_amt —
// без единого дополнительного запроса. Для многоуровневых направлений это тоже
// корректно: plan_manual каждого ребёнка уже рекурсивно включает ЕГО own_amt, поэтому
// разница с суммой прямых детей даёт own_amt именно ЭТОГО узла, а не всей ветки.
//
// Если бэкенд-правка ещё не выкатилась (plan_manual группы = Σ детей без own_amt,
// как было раньше) — diff всегда 0, и кнопка раскрытия у направления не появится,
// даже если своя позиция физически есть. Это ожидаемо и безопасно (см. поручение) —
// как только бэкенд посчитает own_amt, число само перестанет быть нулевым без правок
// фронта.
function hasOwnPlannedAmountFor(node: FeoNode): boolean {
  if (!node.hasChildren) return false
  const t = planTreeByCat.value[node.id]
  if (t) {
    const childrenPlanManual = (node.children || []).reduce(
      (sum, ch) => sum + Number(planTreeByCat.value[ch.id]?.plan_manual || 0), 0
    )
    const ownAmt = Number(t.plan_manual || 0) - childrenPlanManual
    if (ownAmt > 0.005) return true
  }
  // Фолбэк на приёмке (2026-08-12): на живых данных бэкенд-процесс ещё не перезапущен
  // с правкой own_amt (см. комментарий выше — файл поменялся, работающий сервер нет),
  // поэтому diff по plan_manual выше пока всегда 0, хотя «Бинт марлевый» физически
  // висит на категории 3677. Используем УЖЕ загруженный bulk-массив plannedItemsByCat
  // (`/feo-categories/planned-purchase-items`, грузится один раз на всю субсидию в
  // loadFeo/refreshReqData, БЕЗ дополнительного запроса на этот узел) — если у узла
  // есть СОБСТВЕННЫЕ позиции закупок (те же, что попадают в панель через
  // unplannedActualFor/displayPlannedRowsFor), считаем, что раскрывать есть что.
  // Не идеальный признак (пропустит совсем ручной FeoPlannedItem без единой закупки
  // за ним), но не требует похода в сеть и покрывает боевой сценарий задачи.
  return (plannedItemsByCat.value[node.id]?.length || 0) > 0
}

// Числовой двойник hasOwnPlannedAmountFor выше — не просто «есть ли своя сумма», а
// СКОЛЬКО её (жалоба владельца 2026-08-13: «48 441,80 — нигде нет такой суммы»,
// «внутри какой панели, я нигде не вижу этой хуйни, что это за фантом» — план
// направления после бэкенд-правки own_amt уже включает свою часть в шапке строки, но
// нигде не показан отдельным числом). Та же формула («plan_manual узла минус Σ
// plan_manual его непосредственных детей» = own_amt этого узла, см. комментарий у
// hasOwnPlannedAmountFor), только возвращает сумму, а не boolean — используется в
// строке «в т.ч. на самом направлении N ₽» под «Плановой суммой» направления.
function feoOwnDirectionPlanFor(node: FeoNode): number {
  if (!node.hasChildren) return 0
  const t = planTreeByCat.value[node.id]
  if (!t) return 0
  const childrenPlanManual = (node.children || []).reduce(
    (sum, ch) => sum + Number(planTreeByCat.value[ch.id]?.plan_manual || 0), 0
  )
  const own = Number(t.plan_manual || 0) - childrenPlanManual
  return own > 0.005 ? own : 0
}

interface FeoVirtualGroup {
  name: string
  unit: string | null
  qty: number
  total: number
  category: string
  product_type: string
  items: FeoReqItem[]
}

function normName(s: string | null | undefined): string {
  return (s || '').trim().toLowerCase().replace(/\s+/g, ' ')
}

const mergedReqByCat = computed(() => {
  const matched: Record<number, FeoReqItem[]> = {}
  const virtualByCat: Record<number, FeoVirtualGroup[]> = {}
  // Позиции, привязанные к плановой позиции (feo_planned_item_id) — расходуют план Ур.5,
  // а не складываются с ним поверх. Ключ — feo_planned_item_id. Исключены из matched/
  // virtualByCat, иначе matchedReqTotal() и feoPlannedDisplayFor() задвоят план.
  const linkedByPlanned: Record<number, FeoReqItem[]> = {}
  const byId: Record<number, FeoNode> = {}
  for (const n of flattenAll(feoTree.value)) byId[n.id] = n
  for (const [catIdStr, items] of Object.entries(plannedItemsByCat.value)) {
    const catId = Number(catIdStr)
    const node = byId[catId]
    const leafByName: Record<string, number> = {}
    for (const ch of node?.children || []) {
      if (!ch.hasChildren) leafByName[normName(ch.name)] = ch.id
    }
    const groups = new Map<string, FeoVirtualGroup>()
    for (const it of items || []) {
      if (it.feo_planned_item_id != null) {
        ;(linkedByPlanned[it.feo_planned_item_id] ||= []).push(it)
        continue
      }
      const key = normName(it.item_name)
      const childId = leafByName[key]
      if (childId != null) {
        ;(matched[childId] ||= []).push(it)
        continue
      }
      let g = groups.get(key)
      if (!g) {
        g = { name: it.item_name, unit: it.unit, qty: 0, total: 0, category: it.category, product_type: it.product_type, items: [] }
        groups.set(key, g)
      }
      g.qty = Math.round((g.qty + Number(it.quantity || 0)) * 10000) / 10000
      g.total += Number(it.total_price || 0)
      if (!g.unit && it.unit) g.unit = it.unit
      g.items.push(it)
    }
    const list = [...groups.values()]
    if (list.length) virtualByCat[catId] = list
  }
  return { matched, virtualByCat, linkedByPlanned }
})

// Все позиции заявок сгруппированные по cat (без исключения matched) — для режима 'requests'
const allReqGroupsByCat = computed<Record<number, FeoVirtualGroup[]>>(() => {
  const result: Record<number, FeoVirtualGroup[]> = {}
  for (const [catIdStr, items] of Object.entries(plannedItemsByCat.value)) {
    const catId = Number(catIdStr)
    const groups = new Map<string, FeoVirtualGroup>()
    for (const it of items || []) {
      const key = normName(it.item_name)
      let g = groups.get(key)
      if (!g) {
        g = { name: it.item_name, unit: it.unit, qty: 0, total: 0, category: it.category, product_type: it.product_type, items: [] }
        groups.set(key, g)
      }
      g.qty = Math.round((g.qty + Number(it.quantity || 0)) * 10000) / 10000
      g.total += Number(it.total_price || 0)
      if (!g.unit && it.unit) g.unit = it.unit
      g.items.push(it)
    }
    const list = [...groups.values()]
    if (list.length) result[catId] = list
  }
  return result
})

const purchaseFoldersByCat = computed<Record<number, FeoPurchaseFolder[]>>(() => {
  const res: Record<number, FeoPurchaseFolder[]> = {}
  for (const [catIdStr, items] of Object.entries(plannedItemsByCat.value)) {
    const byPid = new Map<number, FeoPurchaseFolder>()
    for (const it of items || []) {
      let f = byPid.get(it.purchase_id)
      if (!f) {
        f = { purchase_id: it.purchase_id, purchase_number: it.purchase_number, registry_number: it.registry_number, purchase_status: it.purchase_status, wish_id: it.wish_id, qty: 0, unit: it.unit, total: 0, items: [], stopped_at: it.stopped_at, stopped_by_name: it.stopped_by_name }
        byPid.set(it.purchase_id, f)
      }
      f.qty = Math.round((f.qty + Number(it.quantity || 0)) * 10000) / 10000
      f.total += Number(it.total_price || 0)
      if (f.unit !== it.unit) f.unit = null
      f.items.push(it)
    }
    const list = [...byPid.values()].sort((a, b) => (a.registry_number || String(a.purchase_number ?? a.purchase_id)).localeCompare(b.registry_number || String(b.purchase_number ?? b.purchase_id), 'ru'))
    if (list.length) res[Number(catIdStr)] = list
  }
  return res
})
function purchaseFoldersFor(node: FeoNode): FeoPurchaseFolder[] {
  return purchaseFoldersByCat.value[node.id] || []
}
// Владелец, 2026-08-13: «закупка остановлена {ФИО}, {дата}» — используется в
// маркере ЗАКУПКА ОСТАНОВЛЕНА у позиций/папок закупок (см. FeoActualItem/
// FeoReqItem/FeoPurchaseFolder.stopped_at — сейчас всегда undefined, т.к.
// /feo-planned-items/comparison и /feo-categories/planned-purchase-items ещё не
// отдают эти поля; функция готова, сработает как только бэкенд их добавит).
function feoStoppedLine(row: { stopped_by_name?: string | null; stopped_at?: string | null }): string {
  const who = row.stopped_by_name || 'неизвестно кем'
  const when = row.stopped_at ? new Date(row.stopped_at).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' }) : ''
  return `остановлена ${who}${when ? ', ' + when : ''}`
}
function purchaseFolderTitle(f: FeoPurchaseFolder): string {
  return 'Закупка ' + (f.registry_number || (f.purchase_number != null ? '№ ' + f.purchase_number : '#' + f.purchase_id))
}

function matchedReqFor(node: FeoNode): FeoReqItem[] {
  return mergedReqByCat.value.matched[node.id] || []
}
function virtualGroupsFor(node: FeoNode): FeoVirtualGroup[] {
  if (plannedBase.value === 'requests') return allReqGroupsByCat.value[node.id] || []
  return mergedReqByCat.value.virtualByCat[node.id] || []
}

// Задача владельца «план ≠ факт» (сессия 2026-08-06, Шаг 5, п.1): строка виртуальной
// позиции «из заявок» обязана показывать ЗАМОРОЖЕННЫЙ снимок ТЗ (planned_quantity/
// planned_total), а не текущее quantity/total_price позиции закупки (которое задним
// числом подменяется ценой по итогам закупки) — иначе плановая сумма «съезжает» вслед
// за правкой цены. it.planned_quantity/planned_total уже приходят с бэкенда с фолбэком
// на текущие значения для старых записей без снимка (см. GET /feo-categories/planned-purchase-items) —
// доп. `?? it.quantity`/`?? it.total_price` здесь — вторая линия защиты на случай отсутствия поля.
function groupPlannedQty(g: FeoVirtualGroup): number {
  return Math.round(g.items.reduce((s, it) => s + Number(it.planned_quantity ?? it.quantity ?? 0), 0) * 10000) / 10000
}
function groupPlannedTotal(g: FeoVirtualGroup): number {
  return g.items.reduce((s, it) => s + Number(it.planned_total ?? it.total_price ?? 0), 0)
}
// Фактическая сумма группы: сумма fact_amount по позициям, у которых факт уже известен
// (ContractItem/contract_price, см. purchase_item_fact_amount). null — ни у одной
// позиции группы факта ещё нет (план_schedule или нет договорных данных).
function groupFactTotal(g: FeoVirtualGroup): number | null {
  const withFact = g.items.filter(it => it.fact_amount != null)
  if (!withFact.length) return null
  return withFact.reduce((s, it) => s + Number(it.fact_amount || 0), 0)
}
function matchedReqQty(node: FeoNode): number {
  return Math.round(matchedReqFor(node).reduce((s, x) => s + Number(x.quantity || 0), 0) * 10000) / 10000
}
function matchedReqTotal(node: FeoNode): number {
  return matchedReqFor(node).reduce((s, x) => s + Number(x.total_price || 0), 0)
}
// Финансирование задано вручную → детальное разбиение в ФЭО, ручные план-значения приоритетнее заявок
function mergedManualPriority(node: FeoNode): boolean {
  return feoBudgetFor(node) > 0
}

// Раскрыт ли узел для показа виртуальных позиций из заявок
function reqExpandedFor(node: FeoNode): boolean {
  return node.hasChildren ? expandedIds.value.includes(node.id) : expandedReqItems.value.has(node.id)
}

// Карта: после какой строки дерева (последний узел поддерева) рисовать виртуальные позиции владельца
function ownerReqRowCount(n: FeoNode): number {
  if (plannedBase.value === 'manual') return 0
  return plannedBase.value === 'purchases' ? purchaseFoldersFor(n).length : virtualGroupsFor(n).length
}

// ШАГ 1 плана дедупликации дерева ФЭО (2026-08-07): ЛИСТЬЯ (!n.hasChildren) исключены —
// их plannedItemsByCat-позиции (эта же «Таблица B») сгруппированы РОВНО тем же ключом
// coalesce(feo_category_id, purchase.feo_category_id), что и comparisonData[leaf.id].actual
// (см. Таблицу A выше, expandedItemPanels) — то есть это ФИЗИЧЕСКИ ТЕ ЖЕ позиции закупок,
// просто пришедшие с другого эндпоинта. Для листа Таблица A уже показывает их все —
// повторный показ здесь был вторым независимым рендером (баг «Great Wall POER» ×2-3).
// Для владельцев (hasChildren) содержимое другое — позиции, заведённые прямо на
// родительскую категорию, а не на конкретный лист — оставлено без изменений.
const reqOwnersAfter = computed<Record<number, FeoNode[]>>(() => {
  const map: Record<number, FeoNode[]> = {}
  const all = visibleFeoNodes.value
  for (let i = all.length - 1; i >= 0; i--) {
    const n = all[i]
    if (!n.hasChildren || !ownerReqRowCount(n) || !reqExpandedFor(n) || !isNodeVisible(n)) continue
    let j = i
    while (j + 1 < all.length && all[j + 1].depth > n.depth) j++
    ;(map[all[j].id] ||= []).push(n)
  }
  return map
})

function reqItemRowsFor(node: FeoNode): FeoReqRow[] {
  const groupsList = virtualGroupsFor(node)
  const mode = feoItemsGroupBy.value
  const groupRowOf = (g: FeoVirtualGroup): FeoReqRow =>
    ({ key: `g-${normName(g.name)}`, header: '', level: 0, count: g.items.length, sumQty: g.qty, sum: g.total, group: g, items: g.items })
  if (mode === 'none') {
    return [...groupsList].sort((a, b) => a.name.localeCompare(b.name, 'ru')).map(groupRowOf)
  }
  const sorted = [...groupsList].sort((a, b) =>
    a.category.localeCompare(b.category, 'ru')
    || a.product_type.localeCompare(b.product_type, 'ru')
    || a.name.localeCompare(b.name, 'ru'))
  const rows: FeoReqRow[] = []
  let curCat: string | null = null
  let curType: string | null = null
  const headerRow = (key: string, header: string, level: number, grp: FeoVirtualGroup[]): FeoReqRow => ({
    key, header, level,
    count: grp.reduce((s, x) => s + x.items.length, 0),
    sumQty: Math.round(grp.reduce((s, x) => s + x.qty, 0) * 10000) / 10000,
    sum: grp.reduce((s, x) => s + x.total, 0),
    group: null,
    items: grp.flatMap(x => x.items),
  })
  for (const g of sorted) {
    if (g.category !== curCat) {
      curCat = g.category
      curType = null
      rows.push(headerRow(`c-${curCat}`, curCat, 1, sorted.filter(x => x.category === curCat)))
    }
    if (mode === 'category_type' && g.product_type !== curType) {
      curType = g.product_type
      rows.push(headerRow(`c-${curCat}-t-${curType}`, curType, 2,
        sorted.filter(x => x.category === curCat && x.product_type === curType)))
    }
    rows.push(groupRowOf(g))
  }
  return rows
}

function reqRowIndent(node: FeoNode, row: FeoReqRow): string {
  const extra = row.group
    ? (feoItemsGroupBy.value === 'none' ? 0 : feoItemsGroupBy.value === 'category' ? 1 : 2)
    : row.level - 1
  return `${(node.depth + 1 + extra) * 20 + 8}px`
}

// ── Панель источников виртуальной позиции «план vs факт» + правка/удаление ──
const expandedReqItemPanels = ref<Set<string>>(new Set())

function reqPanelKey(node: FeoNode, g: FeoVirtualGroup): string {
  return `${node.id}|${normName(g.name)}`
}

async function ensureComparison(catId: number) {
  if (comparisonData.value[catId]) return
  loadingComparison.value.add(catId)
  try {
    const subsId = selectedId.value
    comparisonData.value[catId] = await apiFetch<{ planned: FeoPlannedItem[]; actual: FeoActualItem[] }>(
      `/feo-planned-items/comparison?feo_category_id=${catId}${subsId ? `&subsidy_id=${subsId}` : ''}`
    )
    applyDefaultPlannedExpansion(catId)
  } catch {
    comparisonData.value[catId] = { planned: [], actual: [] }
  } finally {
    loadingComparison.value.delete(catId)
  }
}

function toggleReqItemPanel(node: FeoNode, g: FeoVirtualGroup) {
  const key = reqPanelKey(node, g)
  if (expandedReqItemPanels.value.has(key)) {
    expandedReqItemPanels.value.delete(key)
    return
  }
  expandedReqItemPanels.value.add(key)
  ensureComparison(node.id)
}

function openReqItemPanel(node: FeoNode, g: FeoVirtualGroup) {
  expandedReqItemPanels.value.add(reqPanelKey(node, g))
  ensureComparison(node.id)
}

// Кнопки виртуальной позиции: одна цель → сразу действие, несколько → раскрыть панель источников
function virtGroupPurchaseIds(g: FeoVirtualGroup): number[] {
  return [...new Set(g.items.map(i => i.purchase_id))]
}

function virtCart(node: FeoNode, g: FeoVirtualGroup) {
  const ids = virtGroupPurchaseIds(g)
  if (ids.length === 1) router.push(`/orders/${ids[0]}`)
  else openReqItemPanel(node, g)
}

function virtEdit(node: FeoNode, g: FeoVirtualGroup) {
  if (g.items.length === 1) openReqItemEdit(node, g.items[0])
  else openReqItemPanel(node, g)
}

function virtDelete(node: FeoNode, g: FeoVirtualGroup) {
  if (g.items.length === 1) confirmReqItemDelete(node, g.items[0])
  else openReqItemPanel(node, g)
}

function reqItemActual(catId: number, itemId: number): FeoActualItem | null {
  return comparisonData.value[catId]?.actual.find(a => a.purchase_item_id === itemId) || null
}

// Стадии позиции «из заявок» (matchedReqFor) — сама FeoReqItem их не содержит, но одна и та же
// позиция закупки, как правило, приходит и в comparisonData.actual (см. reqItemActual), где
// бэкенд уже проставил stages.
function stagesForReqItem(catId: number, itemId: number): FeoStage[] {
  return reqItemActual(catId, itemId)?.stages || []
}

function reqItemPlanned(catId: number, itemId: number): FeoPlannedItem | null {
  const a = reqItemActual(catId, itemId)
  if (!a?.feo_planned_item_id) return null
  return comparisonData.value[catId]?.planned.find(p => p.id === a.feo_planned_item_id) || null
}

function mapReqItem(node: FeoNode, item: FeoReqItem) {
  const a = reqItemActual(node.id, item.id)
  if (a) openMapDialog(a, node.id)
}

// Обновление данных «из заявок» без сброса раскрытых папок
async function refreshReqData(catId?: number) {
  if (!selectedId.value) return
  const [totals, items, planTree] = await Promise.all([
    apiFetch<Record<number, { total: number; qty: number; total_linked?: number; qty_linked?: number; total_over?: number; qty_over?: number; forecast?: number; forecast_over?: number; plan_manual?: number }>>(`/feo-categories/planned-purchase-totals?subsidy_id=${selectedId.value}`),
    apiFetch<Record<number, FeoReqItem[]>>(`/feo-categories/planned-purchase-items?subsidy_id=${selectedId.value}`),
    apiFetch<Record<string, any>>(`/feo-categories/plan-tree?subsidy_id=${selectedId.value}`),
  ])
  planTreeByCat.value = splitPlanTree(planTree)
  loadPlanExcessApprovals(selectedId.value)
  const sums: Record<number, number> = {}
  const qtys: Record<number, number> = {}
  const sumsLinked: Record<number, number> = {}
  const qtysLinked: Record<number, number> = {}
  const sumsOver: Record<number, number> = {}
  const qtysOver: Record<number, number> = {}
  const forecasts: Record<number, { forecast: number; forecast_over: number; plan_manual: number }> = {}
  for (const [k, v] of Object.entries(totals)) {
    const totalLinked = Number(v?.total_linked || 0)
    const qtyLinked = Number(v?.qty_linked || 0)
    const totalOver = Number(v?.total_over || 0)
    const qtyOver = Number(v?.qty_over || 0)
    sums[Number(k)] = Number(v?.total || 0) - totalLinked - totalOver
    qtys[Number(k)] = Number(v?.qty || 0) - qtyLinked - qtyOver
    sumsLinked[Number(k)] = totalLinked
    qtysLinked[Number(k)] = qtyLinked
    sumsOver[Number(k)] = totalOver
    qtysOver[Number(k)] = qtyOver
    forecasts[Number(k)] = {
      forecast: Number(v?.forecast || 0),
      forecast_over: Number(v?.forecast_over || 0),
      plan_manual: Number(v?.plan_manual || 0),
    }
  }
  plannedPurchaseTotals.value = sums
  plannedPurchaseQty.value = qtys
  plannedPurchaseTotalsLinked.value = sumsLinked
  plannedPurchaseQtyLinked.value = qtysLinked
  plannedPurchaseTotalsOver.value = sumsOver
  plannedPurchaseQtyOver.value = qtysOver
  plannedPurchaseForecast.value = forecasts
  plannedItemsByCat.value = items
  plannedItemsLoaded.value = true
  if (catId != null) {
    delete comparisonData.value[catId]
    await ensureComparison(catId)
  }
}

const reqItemEdit = reactive({
  show: false, saving: false,
  catId: null as number | null, purchaseId: null as number | null, itemId: null as number | null,
  form: { item_name: '', quantity: null as number | null, unit: '', unit_price: null as number | null, feo_category_id: null as number | null },
  // Снимок значений на момент открытия диалога (правка 2026-08-18): saveReqItemEdit
  // шлёт в PATCH только реально изменённые поля — иначе при заморозке ТЗ
  // (TZ_FROZEN_STATUSES) правка ОДНОЙ ТОЛЬКО категории отбивается 409 из-за
  // молча переотправленных qty/price, которых пользователь не трогал.
  original: { item_name: '', quantity: null as number | null, unit: '', unit_price: null as number | null },
})

// Жалоба владельца (2026-08-18): диалог правки позиции всегда был зашит в
// max-width 520 — на мониторе 27" название категории/позиции не влезает, а
// внутри уже дерево ФЭО + список плановых позиций, которым тесно. В файле нет
// общего паттерна адаптивной ширины диалогов (остальные — фикс max-width +
// :fullscreen="mobile"), поэтому заводим свой computed по брейкпоинтам
// Vuetify. mobile (<mobileBreakpoint) уже держит fullscreen как было.
const { smAndDown: reqItemEditSmAndDown, mdAndDown: reqItemEditMdAndDown } = useDisplay()
const reqItemEditDialogWidth = computed(() => {
  if (reqItemEditSmAndDown.value) return 720   // планшет/маленький ноутбук
  if (reqItemEditMdAndDown.value) return 900   // обычный десктоп
  return 1100                                   // крупный монитор (lg/xl и выше)
})

// selectedSubsidy объявлен выше (сразу после allSubsidies/selectedId) — useFeoLeaves
// ниже читает reqItemEditSubsidyId.value синхронно при вызове (immediate-watch внутри
// композабла), поэтому computed(), от которого он зависит, обязан быть создан ДО этой
// строки, иначе ReferenceError "Cannot access before initialization" (было до 2026-08-12).
//
// Дерево категорий ФЭО для пикера в диалоге правки позиции (Правка владельца
// 2026-08-12: «перенести позицию в другую категорию — так превышение и
// разбирается»). Переиспользует useFeoLeaves (тот же composable, что
// PurchaseItemsEditor использует под FeoTreeSelect) — реагирует на subsidyId,
// сам подгружает узлы/листья при открытии диалога/смене субсидии.
const reqItemEditSubsidyId = computed(() => selectedSubsidy.value?.id ?? null)
const { feoLeaves: reqItemEditFeoLeaves, feoNodes: reqItemEditFeoNodes } = useFeoLeaves({ subsidyId: reqItemEditSubsidyId })

// Плановые позиции категории для диалога правки (владелец, 2026-08-18) — тот же
// источник (/feo-categories/plan-positions) и composable, что CreateOrderView.vue
// использует для того же компонента (purchasePlannedResiduals) — здесь своя копия,
// т.к. reqItemEdit — отдельный, независимый от формы создания закупки диалог.
// plannedItemsByCat в этом файле — ДРУГОЕ (реальные позиции закупок категории из
// /feo-categories/planned-purchase-items, «Таблица B»), не годится как items для
// FeoPlannedItemsSelect (там нужны сами плановые строки с planned_amount/residual).
// excludePurchaseId — своя закупка не занимает свой же план (иначе двойное вычитание).
const {
  plannedResiduals: reqItemEditPlannedResiduals,
  plannedLoading: reqItemEditPlannedLoading,
  reloadPlanned: reloadReqItemEditPlanned,
} = useFeoPlannedResiduals({
  subsidyId: reqItemEditSubsidyId,
  excludePurchaseId: computed(() => reqItemEdit.purchaseId),
})
// Составной выбор { kind, id } | null — зеркалит feoPlanSelection в CreateOrderView.vue.
// touched различает «не трогал» (PATCH без feo_planned_item_id — прежний автоподбор)
// от «явно выбрал/снял выбор» (PATCH шлёт feo_planned_item_id, в т.ч. null).
const reqItemEditPlanSelection = ref<FeoPlanSelection | null>(null)
const reqItemEditPlanTouched = ref(false)
function onReqItemEditPlanSelect(val: FeoPlanSelection | null) {
  reqItemEditPlanTouched.value = true
  // Строки kind='plan_position'/'feo_article' — план самого листа категории ФЭО
  // (FeoCategory.planned_quantity/amount), а не отдельная FeoPlannedItem — им нечего
  // положить в feo_planned_item_id (id там — id категории, не плановой позиции).
  // Выбор такой строки означает «план — на уровне категории», что эквивалентно
  // отсутствию привязки к конкретной FeoPlannedItem — отправляем null тем же путём,
  // что и снятие выбора.
  reqItemEditPlanSelection.value = val && val.kind === 'planned_item' ? val : null
}
// Сумма редактируемой позиции — компонент честно покажет, хватает ли остатка плана.
const reqItemEditPlanAmount = computed(() =>
  (Number(reqItemEdit.form.quantity) || 0) * (Number(reqItemEdit.form.unit_price) || 0)
)
// Предзаполнение диалога «Создать в плане закупок» данными уже введённой позиции.
const reqItemEditPlanPrefill = computed(() => ({
  name: reqItemEdit.form.item_name,
  quantity: reqItemEdit.form.quantity,
  unit: reqItemEdit.form.unit,
  amount: reqItemEditPlanAmount.value,
}))

// Принцип владельца (2026-08-18): «после того как заявка попала в План
// закупок, дальше редактирование и перераспределение между плановыми
// позициями — только в Закупках». Раньше здесь был ранний выход в /wishes
// для item.wish_id — тупик: заявка, уже ушедшая в закупку, там заблокирована
// (TZ_FROZEN_STATUSES), и пользователь упирался в баннер «редактирование
// запрещено», хотя позиция реально существует в закупке и правится через
// PATCH /purchases/{id}/items/{id} (см. saveReqItemEdit ниже). Диалог теперь
// открывается всегда; блокировки (заморозка ТЗ, превышение плана) отрабатывает
// сам PATCH своим 409, который saveReqItemEdit уже распаковывает.
function openReqItemEdit(node: FeoNode, item: FeoReqItem) {
  reqItemEdit.catId = node.id
  reqItemEdit.purchaseId = item.purchase_id
  reqItemEdit.itemId = item.id
  reqItemEdit.form = { item_name: item.item_name, quantity: item.quantity, unit: item.unit || '', unit_price: item.unit_price, feo_category_id: node.id }
  reqItemEdit.original = {
    item_name: reqItemEdit.form.item_name, quantity: reqItemEdit.form.quantity,
    unit: reqItemEdit.form.unit, unit_price: reqItemEdit.form.unit_price,
  }
  // Текущая привязка к плановой позиции — начальное состояние пикера ниже; сброс
  // touched — открытие диалога не считается правкой, пока пользователь не кликнет.
  reqItemEditPlanSelection.value = item.feo_planned_item_id != null
    ? { kind: 'planned_item', id: item.feo_planned_item_id }
    : null
  reqItemEditPlanTouched.value = false
  reqItemEdit.show = true
}

// Карандаш в строках факта панели «план vs факт» (все три блока) правит ПОЗИЦИЮ
// ЗАКУПКИ, а не план — задача владельца (2026-08-09, пункт 2). Переиспользует
// готовый диалог reqItemEdit/saveReqItemEdit выше вместо второго диалога:
// адаптер собирает совместимый FeoReqItem из FeoActualItem (те же данные под
// другими именами полей — purchase_item_id → id). Блокировки уже отработаны
// внутри переиспользуемых функций, второй раз их тут не пишем: заморозка ТЗ
// (TZ_FROZEN_STATUSES) и превышение плана (assert_tz_not_over_plan) → 409 от
// PATCH /purchases/{id}/items/{id} (backend/app/routers/purchases.py),
// распаковывается в saveReqItemEdit через e.payload.message/e.detail.
function openReqItemEditFromActual(node: FeoNode, actual: FeoActualItem) {
  openReqItemEdit(node, {
    id: actual.purchase_item_id,
    item_name: actual.item_name,
    quantity: actual.quantity ?? 0,
    unit: actual.unit,
    unit_price: actual.unit_price ?? 0,
    total_price: actual.total_price ?? 0,
    purchase_id: actual.purchase_id,
    purchase_number: actual.purchase_number,
    registry_number: actual.registry_number,
    purchase_status: actual.purchase_status || '',
    wish_id: actual.wish_id ?? null,
    category: '', product_type: '',
    feo_planned_item_id: actual.feo_planned_item_id ?? null,
  })
}

async function saveReqItemEdit() {
  if (!reqItemEdit.itemId || !reqItemEdit.purchaseId) return
  reqItemEdit.saving = true
  try {
    // Шлём ТОЛЬКО реально изменённые поля (правка 2026-08-18) — сверяем со
    // снимком, сделанным при открытии диалога (reqItemEdit.original). Раньше
    // тело PATCH всегда несло item_name/quantity/unit/unit_price целиком, даже
    // нетронутыми — при заморозке ТЗ (TZ_FROZEN_STATUSES) это отбивало 409
    // правку ОДНОЙ ТОЛЬКО категории, хотя её менять можно.
    const body: Record<string, any> = {}
    if (reqItemEdit.form.item_name !== reqItemEdit.original.item_name) {
      body.item_name = reqItemEdit.form.item_name
    }
    if (reqItemEdit.form.quantity !== reqItemEdit.original.quantity) {
      body.quantity = reqItemEdit.form.quantity
    }
    if ((reqItemEdit.form.unit || '') !== (reqItemEdit.original.unit || '')) {
      body.unit = reqItemEdit.form.unit || null
    }
    if (reqItemEdit.form.unit_price !== reqItemEdit.original.unit_price) {
      body.unit_price = reqItemEdit.form.unit_price
    }
    // Категорию отправляем ТОЛЬКО если пользователь её реально сменил (catId —
    // категория, под которой позиция открыта в дереве, т.е. текущая) — не
    // переписывать лишнего при обычном редактировании имени/цены.
    const categoryChanged = reqItemEdit.form.feo_category_id != null && reqItemEdit.form.feo_category_id !== reqItemEdit.catId
    if (categoryChanged) body.feo_category_id = reqItemEdit.form.feo_category_id
    // Явный выбор плановой позиции (владелец, 2026-08-18) — шлём поле ТОЛЬКО если
    // пользователь реально кликнул в пикере (reqItemEditPlanTouched), иначе бэкенд
    // не должен отличить «не трогал» от «выбрал и снял» — молчание сохраняет прежний
    // автоподбор по точному совпадению имени (см. backend patch_purchase_item).
    if (reqItemEditPlanTouched.value) {
      body.feo_planned_item_id = reqItemEditPlanSelection.value?.id ?? null
    }
    if (Object.keys(body).length === 0) {
      reqItemEdit.show = false
      showSnack('Изменений нет')
      return
    }
    await apiFetch(`/purchases/${reqItemEdit.purchaseId}/items/${reqItemEdit.itemId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    })
    reqItemEdit.show = false
    await refreshReqData(reqItemEdit.catId ?? undefined)
    if (categoryChanged && reqItemEdit.form.feo_category_id != null) {
      delete comparisonData.value[reqItemEdit.form.feo_category_id]
      await ensureComparison(reqItemEdit.form.feo_category_id)
    }
    showSnack('Позиция обновлена')
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.detail || 'Не удалось сохранить позицию', 'error')
  } finally {
    reqItemEdit.saving = false
  }
}

const reqItemDelete = reactive({
  show: false, deleting: false,
  catId: null as number | null, purchaseId: null as number | null, itemId: null as number | null, name: '',
})

// Позиция «из заявки»: точечно удалить её из плана нельзя — заявка уже согласована,
// и убрать одну строку в обход цепочки согласующих значит сломать инвариант
// «изменил заявку → она уходит на повторное согласование» (см. backend/app/routers/purchases.py).
// Вместо слепого перехода в заявку — объясняем, куда идти и что произойдёт.
const wishBlockedDelete = reactive({
  show: false, reverting: false,
  wishId: null as number | null, catId: null as number | null,
  name: '', quantity: null as number | null, unit: '' as string | null, sum: 0,
})

function confirmReqItemDelete(node: FeoNode, item: FeoReqItem) {
  if (item.wish_id) {
    wishBlockedDelete.wishId = item.wish_id
    wishBlockedDelete.catId = node.id
    wishBlockedDelete.name = item.item_name
    wishBlockedDelete.quantity = item.quantity
    wishBlockedDelete.unit = item.unit
    wishBlockedDelete.sum = item.total_price
    wishBlockedDelete.show = true
    return
  }
  reqItemDelete.catId = node.id
  reqItemDelete.purchaseId = item.purchase_id
  reqItemDelete.itemId = item.id
  reqItemDelete.name = item.item_name
  reqItemDelete.show = true
}

async function doReqItemDelete() {
  if (!reqItemDelete.itemId || !reqItemDelete.purchaseId) return
  reqItemDelete.deleting = true
  try {
    await apiFetch(`/purchases/${reqItemDelete.purchaseId}/items/${reqItemDelete.itemId}`, { method: 'DELETE' })
    reqItemDelete.show = false
    await refreshReqData(reqItemDelete.catId ?? undefined)
    showSnack('Позиция удалена из закупки')
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.detail || 'Не удалось удалить позицию', 'error')
  } finally {
    reqItemDelete.deleting = false
  }
}

function openWishFromBlockedDelete() {
  wishBlockedDelete.show = false
  router.push({ path: '/wishes', query: { open: String(wishBlockedDelete.wishId) } })
}

// Только для SaaS-ролей: принудительно вернуть заявку в черновик — эндпоинт сам
// убирает всю заявку (не одну позицию) из плана-графика.
async function revertWishBlockedDeleteToDraft() {
  if (!wishBlockedDelete.wishId) return
  wishBlockedDelete.reverting = true
  try {
    const res = await apiFetch<{ convert_warning?: string | null }>(`/wishes/${wishBlockedDelete.wishId}/status`, {
      method: 'POST',
      body: JSON.stringify({ status: 'draft' }),
    })
    wishBlockedDelete.show = false
    if (res?.convert_warning) {
      showSnack(`Заявка №${wishBlockedDelete.wishId} возвращена в черновик. ${res.convert_warning}`, 'warning')
    } else {
      showSnack(`Заявка №${wishBlockedDelete.wishId} возвращена в черновик и убрана из плана`)
    }
    await refreshReqData(wishBlockedDelete.catId ?? undefined)
    await loadResiduals()
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.message || 'Не удалось вернуть заявку в черновик', 'error')
  } finally {
    wishBlockedDelete.reverting = false
  }
}

// ── Смена ФЭО-категории у wish-позиции ──────────────────────────────────────
const wishItemFeoEdit = reactive({
  show: false,
  saving: false,
  unallocatedLoading: false,
  purchaseId: null as number | null,
  itemId: null as number | null,
  itemName: '',
  catId: null as number | null,   // текущий catId для refreshReqData
  selectedCatId: null as number | null,
})

// Только листовые категории текущей субсидии
const leafFeoCategories = computed(() =>
  feoCategories.value.filter(c => !feoCategories.value.some(x => x.parent_id === c.id))
)

function openWishItemFeoEdit(node: FeoNode, item: FeoReqItem) {
  wishItemFeoEdit.catId = node.id
  wishItemFeoEdit.purchaseId = item.purchase_id
  wishItemFeoEdit.itemId = item.id
  wishItemFeoEdit.itemName = item.item_name
  wishItemFeoEdit.selectedCatId = null
  wishItemFeoEdit.show = true
}

async function saveWishItemFeo() {
  if (!wishItemFeoEdit.itemId || !wishItemFeoEdit.purchaseId || wishItemFeoEdit.selectedCatId == null) return
  wishItemFeoEdit.saving = true
  try {
    await apiFetch(`/purchases/${wishItemFeoEdit.purchaseId}/items/${wishItemFeoEdit.itemId}`, {
      method: 'PATCH',
      body: JSON.stringify({ feo_category_id: wishItemFeoEdit.selectedCatId }),
    })
    wishItemFeoEdit.show = false
    await refreshReqData(wishItemFeoEdit.catId ?? undefined)
    showSnack('Категория ФЭО обновлена')
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.message || 'Не удалось сменить категорию ФЭО', 'error')
  } finally {
    wishItemFeoEdit.saving = false
  }
}

async function pickWishItemUnallocated() {
  if (!selectedId.value) return
  wishItemFeoEdit.unallocatedLoading = true
  try {
    const cat = await apiFetch<{ id: number; name: string }>('/feo-categories/unallocated', {
      method: 'POST',
      body: JSON.stringify({ subsidy_id: selectedId.value }),
    })
    // Добавить в feoCategories если ещё нет
    if (!feoCategories.value.find(c => c.id === cat.id)) {
      feoCategories.value = [...feoCategories.value, {
        id: cat.id, name: cat.name, parent_id: null, level: 0,
        subsidy_id: selectedId.value!, code: null, appendix: null,
        is_active: true, budget: null, planned_quantity: null, planned_amount: null, unit: null,
      }]
    }
    wishItemFeoEdit.selectedCatId = cat.id
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.message || 'Ошибка получения «Не определена»', 'error')
  } finally {
    wishItemFeoEdit.unallocatedLoading = false
  }
}
// ─────────────────────────────────────────────────────────────────────────────

function openMapDialog(item: FeoActualItem, categoryId: number) {
  mapTarget.value = item
  mapCategoryId.value = categoryId
  showMapDialog.value = true
}

async function applyMapping(plannedItemId: number | null) {
  if (!mapTarget.value) return
  mappingInProgress.value = true
  try {
    // Баг найден при приёмке (2026-08-11): при снятии сопоставления (plannedItemId=null)
    // `planned_item_id=${plannedItemId ?? ''}` слал ПУСТУЮ строку вместо отсутствия параметра —
    // бэкенд (Optional[int] = None) валит пустую строку 422 «ожидается целое число», «Снять
    // сопоставление» падало молча (mappingInProgress просто гасился в finally). Параметр нужно
    // не слать вовсе, когда planned_item_id=null — тогда FastAPI подставляет свой default None.
    const qs = `purchase_item_id=${mapTarget.value.purchase_item_id}` + (plannedItemId != null ? `&planned_item_id=${plannedItemId}` : '')
    const result = await apiFetch<{ moved_to_category_id?: number | null }>(`/feo-planned-items/map?${qs}`, {
      method: 'POST',
    })
    showMapDialog.value = false
    // Правка владельца (2026-08-18): «позиции в дашборде должны пересчитываться
    // сразу» — map/unmap двигает total_linked/qty_linked в /planned-purchase-totals
    // (шапка узла, «Не привязаны к плану»), а refreshComparison() один обновлял
    // только панель «план vs факт», не дашборд. refreshReqData(catId) — тот же
    // приём, что в saveReqItemEdit/doReqItemDelete: перечитывает totals/items/
    // plan-tree И делает delete comparisonData[catId] + ensureComparison(catId)
    // (см. её тело выше), так что оба источника обновляются одним вызовом.
    const movedToCategoryId = result?.moved_to_category_id ?? null
    if (mapCategoryId.value) await refreshReqData(mapCategoryId.value)
    // Перенос между категориями ФЭО (решение владельца 2026-08-18): бэкенд
    // POST /feo-planned-items/map при сопоставлении с плановой позицией из ДРУГОЙ
    // категории больше не отказывает 409, а переносит позицию закупки (и
    // зеркально — связанную позицию заявки) в категорию плановой позиции,
    // возвращая moved_to_category_id. refreshReqData(mapCategoryId) выше уже
    // перечитал totals/items/plan-tree по всей субсидии разом (эндпоинты не
    // фильтруются по категории) и инвалидировал comparisonData СТАРОЙ категории —
    // но НОВУЮ категорию она не трогала, и панель «план vs факт» там показывала
    // бы устаревшие числа до перезагрузки страницы. Инвалидируем и её тем же
    // приёмом, что saveReqItemEdit делает при ручной смене категории (см. выше):
    // без повторного похода за totals/items/plan-tree, только delete+ensureComparison.
    if (movedToCategoryId != null && movedToCategoryId !== mapCategoryId.value) {
      delete comparisonData.value[movedToCategoryId]
      await ensureComparison(movedToCategoryId)
    }
  } catch (e: any) {
    // Этап 3 (владелец, 2026-09-02): раньше здесь не было catch вовсе — ошибка
    // (в т.ч. новая 409 PLANNED_ITEM_CATEGORY_MISMATCH при несовпадении категорий,
    // см. app/services/plan_autoassign.py) улетала необработанной, диалог оставался
    // открытым без единого объяснения пользователю. Распаковываем detail.message
    // (правило проекта — не глотать generic-снэкбаром), диалог намеренно НЕ
    // закрываем — пусть человек попробует другую плановую позицию.
    showSnack(e?.payload?.message || e?.detail || e?.message || 'Не удалось сопоставить с плановой позицией', 'error')
  } finally {
    mappingInProgress.value = false
  }
}

function openAddPlannedItem(categoryId: number) {
  addPlannedCategoryId.value = categoryId
  convertFromCategoryPlanId.value = null
  createPlannedFromActualId.value = null
  plannedItemForm.value = {
    // Владелец (2026-09-01): «добавляется плановая позиция по одной штуке» —
    // количество по умолчанию 1, а не пусто.
    name: '', quantity: 1, unit: '', unitPrice: null, amount: null,
    payment_mode: 'one_time', planned_date: '', monthly_start_date: '',
    months_count: null, monthly_amount: null,
    is_feo_breakdown: false, is_internal_plan: true,
  }
  addPlannedProductId.value = null
  addPlannedProductPhoto.value = null
  addPlannedMatchConfirmed.value = undefined
  addPlannedPriceMeta.value = null
  showAddPlannedDialog.value = true
}

// Диалог showAddPlannedDialog закрывается разными путями (Отмена/backdrop/Esc, не
// только через savePlannedItem) — сбрасываем convertFromCategoryPlanId/createPlannedFromActualId
// при ЛЮБОМ закрытии, чтобы флаги не «протекли» в следующее открытие обычной кнопкой.
// Заодно сбрасываем UI-состояние подбора по каталогу (addPlannedProductId и т.п.) —
// та же причина, оно тоже не должно «протечь» в следующее открытие.
watch(showAddPlannedDialog, (val) => {
  if (!val) {
    convertFromCategoryPlanId.value = null
    createPlannedFromActualId.value = null
    addPlannedProductId.value = null
    addPlannedProductPhoto.value = null
    addPlannedMatchConfirmed.value = undefined
    addPlannedPriceMeta.value = null
  }
})

// «Завести плановую позицию» — задача владельца (2026-08-09, пункт 3): у категории
// с ручным планом (нет ни одной реальной FeoPlannedItem, план задан прямо на
// листе node.planned_quantity/planned_amount) строка называется именем категории
// вместо именованного товара («Great Wall POER» ожидалось увидеть, а видно имя
// категории). Действие создаёт именованную FeoPlannedItem с тем же кол-вом/ценой,
// что уже показаны в ручном плане листа — node.planned_quantity/planned_amount
// САМИ НЕ МЕНЯЮТСЯ, а backend/app/services/feo_plan.py::_visit продолжает считать
// «Плановую сумму» шапки категории ИЗ ЭТИХ ПОЛЕЙ (qty×amt), а не суммой
// FeoPlannedItem, пока это произведение > 0 — сумма НЕ задваивается. На фронте
// синтетическая строка (displayPlannedRowsFor) после создания реальной
// FeoPlannedItem перестаёт отрисовываться сама (real.length > 0), так что и
// панель не задваивает план. Дедуп по точному совпадению нормализованного имени —
// на бэкенде (POST /feo-planned-items/, см. докстринг create_planned_item).
// Имя предзаполняется из единственного привязанного факта, если он ровно один
// (обычный случай — «ручной план» листа обычно закрыт одной закупкой), иначе из
// названия категории — пользователь правит перед сохранением. Переиспользует
// диалог showAddPlannedDialog/plannedItemForm/savePlannedItem — второй диалог не
// пишем.
function openConvertManualPlanToItem(node: FeoNode) {
  const facts = factForPlanned(node.id, -node.id)
  const prefillName = facts.length === 1 ? facts[0].item_name : node.name
  const qty = node.planned_quantity != null ? Number(node.planned_quantity) : null
  const unitPrice = node.planned_amount != null ? Number(node.planned_amount) : null
  const amount = (qty != null && qty > 0 && unitPrice != null && unitPrice > 0) ? qty * unitPrice : null
  addPlannedCategoryId.value = node.id
  convertFromCategoryPlanId.value = node.id
  plannedItemForm.value = {
    name: prefillName,
    quantity: qty,
    unit: node.unit || '',
    unitPrice,
    amount,
    payment_mode: 'one_time',
    planned_date: '', monthly_start_date: '', months_count: null, monthly_amount: null,
    // Ручной план ФЭО (planned_quantity/planned_amount на самой категории) по
    // определению без построчной ФЭО-разбивки — та же строка панели уже
    // подписана «подробного деления в ФЭО не было» (см. шаблон выше).
    is_feo_breakdown: false, is_internal_plan: true,
  }
  addPlannedProductId.value = null
  addPlannedProductPhoto.value = null
  addPlannedMatchConfirmed.value = undefined
  addPlannedPriceMeta.value = null
  showAddPlannedDialog.value = true
}

// Действие владельца 2026-08-17 (жалоба «где превышение 80 318? где увидеть?»): у
// позиции без ДЕЙСТВУЮЩЕЙ плановой привязки (обычная «не привязана» ИЛИ мёртвая ссылка
// на удалённую плановую позицию, см. isOrphanedActual/unplannedActualFor) предлагаем
// сразу завести плановую позицию по данным САМОЙ закупки (наименование/количество/сумма —
// leftGroupInfo, тот же источник, что уже рисует эту строку в таблице) и сразу привязать.
// Переиспользует showAddPlannedDialog/plannedItemForm/savePlannedItem — второй диалог не
// пишем; savePlannedItem довязывает созданную позицию к purchase_item_id по
// createPlannedFromActualId (см. ниже).
function openCreatePlannedFromActual(node: FeoNode, actual: FeoActualItem) {
  const info = leftGroupInfo(actual)
  addPlannedCategoryId.value = node.id
  convertFromCategoryPlanId.value = null
  createPlannedFromActualId.value = actual.purchase_item_id
  plannedItemForm.value = {
    name: info.name || actual.item_name,
    quantity: info.quantity,
    unit: info.unit || '',
    unitPrice: info.unitPrice ?? null,
    amount: info.total ?? Number(actual.fact_amount ?? actual.total_price ?? 0),
    payment_mode: 'one_time',
    planned_date: '', monthly_start_date: '', months_count: null, monthly_amount: null,
    // Заводится по факту закупки/заявки, без плана — та же семантика, что и
    // auto_created в plan_autoassign.py (см. is_internal_plan там).
    is_feo_breakdown: false, is_internal_plan: true,
  }
  addPlannedProductId.value = null
  addPlannedProductPhoto.value = null
  addPlannedMatchConfirmed.value = undefined
  addPlannedPriceMeta.value = null
  showAddPlannedDialog.value = true
}

async function savePlannedItem() {
  if (!addPlannedCategoryId.value || !plannedItemForm.value.name.trim()) return
  savingPlannedItem.value = true
  try {
    const f = plannedItemForm.value
    const isMonthly = f.payment_mode === 'monthly'
    // Владелец (2026-09-01): «добавляется плановая позиция по одной штуке» — если
    // количество осталось пустым (в т.ч. стёрто вручную), по умолчанию 1.
    const qtyOrDefault = (f.quantity == null || (f.quantity as unknown as string) === '') ? 1 : f.quantity
    const created = await apiFetch<FeoPlannedItem>('/feo-planned-items/', {
      method: 'POST',
      body: JSON.stringify({
        feo_category_id: addPlannedCategoryId.value,
        name: f.name.trim(),
        quantity: qtyOrDefault,
        unit: f.unit || null,
        amount: isMonthly ? null : f.amount,
        is_active: true,
        payment_mode: f.payment_mode,
        planned_date: !isMonthly && f.planned_date ? f.planned_date : null,
        monthly_start_date: isMonthly && f.monthly_start_date ? f.monthly_start_date : null,
        months_count: isMonthly ? f.months_count : null,
        monthly_amount: isMonthly ? f.monthly_amount : null,
        is_feo_breakdown: f.is_feo_breakdown,
        is_internal_plan: f.is_internal_plan,
      }),
    })
    // Если позиция заводилась ИЗ конкретной закупки (openCreatePlannedFromActual выше) —
    // сразу привязываем её к только что созданной плановой позиции тем же эндпоинтом, что
    // и ручное «Сопоставить с плановой» (applyMapping/POST /feo-planned-items/map), иначе
    // плановая позиция создастся, а закупка так и провисит в «Не привязаны» до следующего
    // ручного клика — половинчатое действие. Ошибку не глотаем — распаковываем
    // e.payload.message (правило проекта), позиция при этом уже создана, поэтому диалог
    // не блокируем повторной попыткой, просто честно сообщаем, что довязать не вышло.
    if (createPlannedFromActualId.value != null) {
      try {
        await apiFetch(`/feo-planned-items/map?purchase_item_id=${createPlannedFromActualId.value}&planned_item_id=${created.id}`, {
          method: 'POST',
        })
      } catch (e: any) {
        showSnack(e?.payload?.message || e?.detail || e?.message || 'Плановая позиция создана, но не удалось привязать к ней закупку — сопоставьте вручную кнопкой «Сопоставить с плановой»', 'error')
      }
      createPlannedFromActualId.value = null
    }
    // Позиция создана. Если это было действие «Перенести в плановую позицию»
    // (convertFromCategoryPlanId стоит на id этой же категории) — очищаем
    // planned_quantity/planned_amount категории: иначе они и дальше заслоняют
    // только что созданную запись при расчёте плана листа (backend суммирует
    // плановые позиции, ТОЛЬКО когда qty×amt категории не заданы), и правка
    // записи не будет менять сумму в шапке — ровно та жалоба, из-за которой
    // всё это переделывается. Сначала — успешное создание позиции (уже
    // произошло выше), потом — очистка полей категории.
    const convertCategoryId = convertFromCategoryPlanId.value === addPlannedCategoryId.value
      ? convertFromCategoryPlanId.value
      : null
    showAddPlannedDialog.value = false
    convertFromCategoryPlanId.value = null
    // refreshComparison обновляет только состав панели «План vs факт»; числа узла/
    // родителей в шапке дерева и плашка превышения читаются из planTreeByCat —
    // его обновляет refreshReqData (см. разбор жалобы владельца у deletePlannedItem
    // и уже работающий movePlannedItemToCategory). Без него новая плановая позиция
    // не давала вклад в «Плановую сумму» до перезагрузки страницы.
    await Promise.all([refreshComparison(addPlannedCategoryId.value), refreshReqData()])
    if (convertCategoryId) await clearCategoryManualPlan(convertCategoryId)
  } catch (e: any) {
    // Жалоба владельца (сессия 2026-08-19): create_planned_item теперь отдаёт 409
    // planned_item_duplicate_name вместо тихого слияния с существующей позицией (см.
    // backend/app/routers/feo_planned_items.py). Полноценный диалог выбора (привязать/
    // создать отдельную), как в FeoPlannedItemsSelect.vue, здесь не заводим — этот путь
    // создания «из закупки»/«из ручного плана категории» — редкий сценарий, здесь просто
    // честно показываем сообщение сервера, не глотаем ошибку generic-снэкбаром.
    const det = e?.payload?.details
    if (e?.status === 409 && det?.error_code === 'planned_item_duplicate_name') {
      showSnack(det.message || e.message || 'Такая плановая позиция уже есть в категории', 'error')
    } else {
      showSnack(e?.payload?.message || e?.detail || e?.message || 'Не удалось создать плановую позицию', 'error')
    }
  } finally {
    savingPlannedItem.value = false
  }
}

// Чистит planned_quantity/planned_amount категории после переноса ручного плана в
// именованную плановую позицию (см. openConvertManualPlanToItem/savePlannedItem выше).
// PUT с ПОЛНЫМ payload — как в saveEditCategoryPlan: неполный payload (см. историю
// startInlineAmt/startInlineQty) обнуляет на сервере поля, которых в нём нет.
async function clearCategoryManualPlan(categoryId: number) {
  const cat = feoCategories.value.find(c => c.id === categoryId)
  if (cat) {
    try {
      await apiFetch(`/feo-categories/${categoryId}`, {
        method: 'PUT',
        body: JSON.stringify({
          subsidy_id: cat.subsidy_id, name: cat.name, code: cat.code ?? null, appendix: cat.appendix ?? null,
          is_active: cat.is_active, budget: cat.budget ?? null,
          feo_quantity: cat.feo_quantity ?? null, feo_unit: cat.feo_unit ?? null, feo_amount: cat.feo_amount ?? null,
          description: cat.description ?? null, unit: cat.unit ?? null,
          planned_quantity: null, planned_amount: null,
        }),
      })
      cat.planned_quantity = null
      cat.planned_amount = null
    } catch (e: any) {
      // Позиция УЖЕ создана — не откатываем и не пугаем «ошибка добавления», честно
      // говорим, что не подчистилось старое поле, и ниже всё равно перезагружаем
      // данные, чтобы пользователь видел реальное состояние, а не выдуманное.
      showSnack(e?.payload?.message || e?.detail || 'Позиция создана, но не удалось очистить старый план категории — проверьте вручную', 'error')
    }
  }
  if (selectedId.value) await loadFeo(selectedId.value)
}

// Баг владельца (2026-08-17): «убрал огнетушитель — сумма не пересчиталась,
// превышение осталось». Причина — эта функция звала ТОЛЬКО refreshComparison
// (перечитывает состав панели «План vs факт» для одной категории), а числа узла/
// родителей в шапке дерева (feoPlannedDisplayFor/excessFor и т.д.) читаются из
// planTreeByCat — его обновляет ТОЛЬКО refreshReqData (см. movePlannedItemToCategory
// выше, который уже делает это правильно). Без refreshReqData() дерево показывало
// старые plan_manual/display/excess_amount до полной перезагрузки страницы.
const deletingPlannedItemId = ref<number | null>(null)
async function deletePlannedItem(item: FeoPlannedItem) {
  deletingPlannedItemId.value = item.id
  try {
    await apiFetch(`/feo-planned-items/${item.id}`, { method: 'DELETE' })
    await Promise.all([refreshComparison(item.feo_category_id), refreshReqData()])
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.detail || e?.message || 'Не удалось удалить плановую позицию', 'error')
  } finally {
    deletingPlannedItemId.value = null
  }
}

// Все категории, лежащие НИЖЕ данного узла в дереве (сам узел не включён) — источник
// списка «Куда перенести» для плановой позиции направления (см. кнопку
// mdi-arrow-down-bold-box-outline в панели выше). flattenAll(node.children) уже
// используется в файле для того же обхода дерева (см. её объявление выше).
function descendantCategoriesFor(node: FeoNode): FeoNode[] {
  return flattenAll(node.children || [])
}

// Требование владельца, п.2/п.3 (2026-08-12): «Её можно перенести вниз, в подходящую
// категорию — суммы при этом не изменятся» — перенос плановой позиции, привязанной
// прямо к направлению, в одну из его конечных (или промежуточных) категорий.
// PUT /feo-planned-items/{id} — та же ПОЛНАЯ замена, что и у saveEditPlannedItem/
// reorderPlannedItem выше (неполный payload обнулил бы остальные поля позиции),
// меняется только feo_category_id.
const movingPlannedItemId = ref<number | null>(null)
async function movePlannedItemToCategory(item: FeoPlannedItem, targetCategoryId: number) {
  if (item.feo_category_id === targetCategoryId) return
  const sourceCategoryId = item.feo_category_id
  movingPlannedItemId.value = item.id
  try {
    await apiFetch(`/feo-planned-items/${item.id}`, {
      method: 'PUT',
      body: JSON.stringify({
        feo_category_id: targetCategoryId,
        name: item.name,
        quantity: item.quantity,
        unit: item.unit,
        amount: item.amount,
        notes: item.notes,
        is_active: item.is_active,
        payment_mode: item.payment_mode ?? 'one_time',
        planned_date: item.planned_date ?? null,
        monthly_start_date: item.monthly_start_date ?? null,
        months_count: item.months_count ?? null,
        monthly_amount: item.monthly_amount ?? null,
        sort_order: item.sort_order ?? null,
        item_type: item.item_type ?? null,
      }),
    })
    // Затронуты ДВА узла (старый и новый) плюс их суммы по всей ветке вверх —
    // refreshComparison точечно обновляет составы обеих панелей, refreshReqData
    // перечитывает planTreeByCat (plan_manual/display), от которого зависит и
    // «Плановая сумма» в шапке дерева, и hasOwnPlannedAmountFor (раскрытие панели
    // направления) для обоих узлов.
    await Promise.all([refreshComparison(sourceCategoryId), refreshComparison(targetCategoryId)])
    await refreshReqData()
    showSnack('Позиция перенесена')
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.detail || 'Ошибка переноса', 'error')
  } finally {
    movingPlannedItemId.value = null
  }
}

// Замечание владельца 2 (2026-08-12): «должна быть возможность менять плановые позиции
// местами внутри категории». Бэкенд готов — FeoPlannedItem.sort_order (nulls last),
// PUT /feo-planned-items/{id} принимает sort_order как ОБЫЧНОЕ поле полного payload'а
// (тот же роутер, что update_planned_item — НЕ отдельный /reorder-эндпоинт, как у
// категорий ФЭО, см. reorderFeoNode выше). PUT там — ПОЛНАЯ замена (см. её же
// докстринг/паттерн saveEditPlannedItem/clearCategoryManualPlan) — неполный payload
// обнулил бы amount/quantity/notes и т.д., поэтому отправляем ВСЕ поля позиции как есть.
const reorderingPlannedItemId = ref<number | null>(null)
async function savePlannedItemSortOrder(item: FeoPlannedItem, newOrder: number) {
  await apiFetch(`/feo-planned-items/${item.id}`, {
    method: 'PUT',
    body: JSON.stringify({
      feo_category_id: item.feo_category_id,
      name: item.name,
      quantity: item.quantity,
      unit: item.unit,
      amount: item.amount,
      notes: item.notes,
      is_active: item.is_active,
      payment_mode: item.payment_mode ?? 'one_time',
      planned_date: item.planned_date ?? null,
      monthly_start_date: item.monthly_start_date ?? null,
      months_count: item.months_count ?? null,
      monthly_amount: item.monthly_amount ?? null,
      sort_order: newOrder,
      item_type: item.item_type ?? null,
    }),
  })
}

async function reorderPlannedItem(node: FeoNode, pIdx: number, direction: 'up' | 'down') {
  const rows = displayPlannedRowsFor(node)
  const a = rows[pIdx]
  const targetIdx = direction === 'up' ? pIdx - 1 : pIdx + 1
  if (!a || a.isManual || targetIdx < 0 || targetIdx >= rows.length) return
  const b = rows[targetIdx]
  if (!b || b.isManual) return
  reorderingPlannedItemId.value = a.id
  try {
    // sort_order пуст у части/всех (старые данные, до этой правки) — при первом
    // перемещении проставляем базовую нумерацию по текущему видимому порядку (1,2,3…),
    // чтобы дальше поведение было предсказуемым (требование владельца).
    const needsBaseline = rows.some(p => p.sort_order == null)
    const orders = needsBaseline ? rows.map((_, i) => i + 1) : rows.map(p => Number(p.sort_order))
    if (needsBaseline) {
      for (let i = 0; i < rows.length; i++) {
        if (i === pIdx || i === targetIdx) continue
        if (Number(rows[i].sort_order) === orders[i]) continue
        await savePlannedItemSortOrder(rows[i], orders[i])
      }
    }
    await savePlannedItemSortOrder(a, orders[targetIdx])
    await savePlannedItemSortOrder(b, orders[pIdx])
    await refreshComparison(node.id)
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.detail || e?.message || 'Не удалось изменить порядок плановых позиций', 'error')
  } finally {
    reorderingPlannedItemId.value = null
  }
}

// ── Diff helpers ──────────────────────────────────────────────────────────
// Формула владельца (2026-08-05): «Остаток считается на основании "плановая сумма" минус
// заказано, и если поставлено, то "плановая сумма" − "поставлено"». Применяется ко всем типам
// строк панели (не только к плановым позициям Ур.5): если среди актуалов есть хотя бы одна
// поставленная/оплаченная — вычитаем сумму поставленного, иначе — сумму заказанного.
// fact_amount берём из API, если он отдан; иначе (напр. для «одноимённых из заявок», у которых
// нет fact_amount) — падаем на total_price позиции.
// Задача владельца «план ≠ факт» (сессия 2026-08-06, Шаг 5): «заказано»-уровень (комитированный,
// но ещё не подтверждённый актом факт) расширен с одного статуса 'ordered' до всей тройки
// work_in_progress/contracted/ordered (см. FACT_PRICED_STATUSES в backend/app/services/feo_plan.py) —
// иначе позиция в статусе «Ведётся работа»/«Договор» с уже известной ценой по итогам закупки
// (fact_amount) не давала вклада в factSum и «Разница» ошибочно показывала полный план вместо
// план-факт.
type DiffActual = { total_price?: number | string | null; fact_amount?: number | string | null; purchase_status?: string | null }
const DIFF_COMMITTED_STATUSES = ['work_in_progress', 'contracted', 'ordered']
function calcDiff(plannedAmount: number | string | null | undefined, actuals: DiffActual[]): number {
  const amountOf = (a: DiffActual) => Number(a.fact_amount ?? a.total_price ?? 0)
  const delivered = actuals.filter(a => ['delivered', 'paid'].includes(a.purchase_status || ''))
  const committed = actuals.filter(a => DIFF_COMMITTED_STATUSES.includes(a.purchase_status || ''))
  const factSum = delivered.length
    ? delivered.reduce((s, a) => s + amountOf(a), 0)
    : committed.reduce((s, a) => s + amountOf(a), 0)
  return Number(plannedAmount || 0) - factSum
}
function getDiffStyle(plannedAmount: number | string | null | undefined, actuals: DiffActual[]): string {
  const diff = calcDiff(plannedAmount, actuals)
  return diff >= 0 ? 'color:#166534;font-weight:600' : 'color:#DC2626;font-weight:600'
}

// ── Подстроки стадий (разворот позиции закупки на ФЭО/План/Закупка/Договор/Приёмка) ──
// Совпадение соседних стадий — норма (уточнили наименование, но купили ровно то же кол-во/цену),
// подсвечиваем ТОЛЬКО расхождение, чтобы не плодить визуальный шум там, где всё сошлось.
interface FeoStageRow {
  stage: FeoStage
  nameChanged: boolean
  qtyDeltaLabel: string | null
  qtyDeltaColor: string
  priceDeltaLabel: string | null
  priceDeltaColor: string
}
function stagesWithDiff(stages: FeoStage[] | undefined): FeoStageRow[] {
  const list = stages || []
  return list.map((stage, i) => {
    const prev = i > 0 ? list[i - 1] : null
    let nameChanged = false
    let qtyDeltaLabel: string | null = null
    let qtyDeltaColor = ''
    let priceDeltaLabel: string | null = null
    let priceDeltaColor = ''
    if (prev) {
      nameChanged = normName(stage.name) !== normName(prev.name)
      const qtyDelta = Math.round((Number(stage.quantity || 0) - Number(prev.quantity || 0)) * 10000) / 10000
      if (Math.abs(qtyDelta) >= 0.0001) {
        qtyDeltaColor = qtyDelta < 0 ? '#DC2626' : '#EA580C'
        qtyDeltaLabel = `${qtyDelta > 0 ? '+' : '−'}${Math.abs(qtyDelta)}${stage.unit ? ' ' + stage.unit : ''}`
      }
      const priceDelta = Number(stage.unit_price || 0) - Number(prev.unit_price || 0)
      if (Math.abs(priceDelta) >= 0.005) {
        priceDeltaColor = priceDelta < 0 ? '#DC2626' : '#EA580C'
        priceDeltaLabel = `${priceDelta > 0 ? '+' : '−'}${formatCurrencyRound(Math.abs(priceDelta))}`
      }
    }
    return { stage, nameChanged, qtyDeltaLabel, qtyDeltaColor, priceDeltaLabel, priceDeltaColor }
  })
}

// ── Edit planned item dialog ─────────────────────────────────────────────
const editPlannedDialog = reactive({
  show: false, saving: false,
  id: 0, feo_category_id: 0,
  name: '', quantity: '' as string | number, unit: '', amount: '' as string | number,
  // Цена за единицу (владелец, 2026-09-02) — то же необязательное поле, что и в
  // диалоге создания (FeoPlannedItemsSelect.vue::createForm.unitPrice). ПРОБЕЛ,
  // из-за которого владелец видел «опять делит»: это окно правки поля не имело
  // вовсе, а PUT ниже — полная замена, так что при сохранении любой другой правки
  // цена молча обнулялась бы, даже если была задана. См. editAmountIsComputed.
  unitPrice: '' as string | number,
  payment_mode: 'one_time' as 'one_time' | 'monthly',
  planned_date: '' as string,
  monthly_start_date: '' as string,
  months_count: null as number | null,
  monthly_amount: null as number | null,
  // Блок 1 (план zany-fluttering-mountain.md, 2026-08-14): PUT — полная замена
  // (FeoPlannedItemCreate), поле обязано доехать до payload неизменным, иначе
  // любое сохранение этого диалога молча стирало бы уже выбранный тип (см.
  // «выбранное на предыдущем этапе не смеет меняться само»). Своего v-select
  // тут нет — правка типа только через диалог создания/импорт.
  item_type: null as string | null,
  // Происхождение (владелец, 2026-09-01) — ДВЕ НЕЗАВИСИМЫЕ галочки, тот же
  // смысл, что и в диалоге создания (plannedItemForm выше). Всегда шлются
  // явно в PUT-payload (см. saveEditPlannedItem) — backend читает их через
  // model_fields_set, поэтому «не трогать» здесь недостижимо и не нужно:
  // это и есть штатное место правки признака (задача владельца, п.5).
  is_feo_breakdown: false as boolean,
  is_internal_plan: false as boolean,
})

// Тот же режим «цена задана → сумма считается сама», что и в диалоге создания
// (FeoPlannedItemsSelect.vue::createAmountIsComputed/recalcCreateAmountFromUnitPrice/
// createPriceCaption) — формулировки специально СЛОВО В СЛОВО те же, чтобы не
// разъезжались между двумя окнами правки одной и той же сущности.
const editAmountIsComputed = computed(() => editPlannedDialog.unitPrice !== '' && editPlannedDialog.unitPrice != null && Number(editPlannedDialog.unitPrice) !== 0)
function recalcEditAmountFromUnitPrice() {
  if (!editAmountIsComputed.value) return
  const price = Number(editPlannedDialog.unitPrice)
  const qty = editPlannedDialog.quantity !== '' && Number(editPlannedDialog.quantity) > 0 ? Number(editPlannedDialog.quantity) : 1
  editPlannedDialog.amount = Math.round(qty * price * 100) / 100
}
watch([() => editPlannedDialog.quantity, () => editPlannedDialog.unitPrice], () => recalcEditAmountFromUnitPrice())
const editPriceCaption = computed((): string =>
  editAmountIsComputed.value
    ? 'С ценой за единицу закупка по этой позиции проверяется и по цене, и по количеству, и по сумме — превысить нельзя ничего из трёх.'
    : 'Без цены за единицу количество считается ориентировочным и не ограничивает закупку — под контролем только общая сумма плана.'
)

function openEditPlannedItem(item: FeoPlannedItem) {
  editPlannedDialog.id = item.id
  editPlannedDialog.feo_category_id = item.feo_category_id
  editPlannedDialog.name = item.name
  editPlannedDialog.quantity = item.quantity != null ? parseFloat(String(item.quantity)) : ''
  editPlannedDialog.unit = item.unit || ''
  editPlannedDialog.amount = item.amount != null ? parseFloat(String(item.amount)) : ''
  editPlannedDialog.unitPrice = item.unit_price != null ? parseFloat(String(item.unit_price)) : ''
  editPlannedDialog.payment_mode = item.payment_mode ?? 'one_time'
  editPlannedDialog.planned_date = item.planned_date ?? ''
  editPlannedDialog.monthly_start_date = item.monthly_start_date ?? ''
  editPlannedDialog.item_type = item.item_type ?? null
  editPlannedDialog.months_count = item.months_count ?? null
  editPlannedDialog.monthly_amount = item.monthly_amount ?? null
  editPlannedDialog.is_feo_breakdown = item.is_feo_breakdown ?? false
  editPlannedDialog.is_internal_plan = item.is_internal_plan ?? false
  editPlannedDialog.show = true
}

async function saveEditPlannedItem() {
  editPlannedDialog.saving = true
  try {
    const d = editPlannedDialog
    const isMonthly = d.payment_mode === 'monthly'
    await apiFetch(`/feo-planned-items/${d.id}`, {
      method: 'PUT',
      body: JSON.stringify({
        feo_category_id: d.feo_category_id,
        name: d.name,
        quantity: d.quantity !== '' ? Number(d.quantity) : null,
        unit: d.unit || null,
        amount: isMonthly ? null : (d.amount !== '' ? Number(d.amount) : null),
        // PUT — полная замена (см. коммент у editPlannedDialog.unitPrice выше и
        // у item.unit_price = data.unit_price в feo_planned_items.py) — без явной
        // передачи цена за единицу молча обнулится, даже если правили что-то другое.
        unit_price: d.unitPrice !== '' && d.unitPrice != null ? Number(d.unitPrice) : null,
        notes: null,
        is_active: true,
        payment_mode: d.payment_mode,
        planned_date: !isMonthly && d.planned_date ? d.planned_date : null,
        monthly_start_date: isMonthly && d.monthly_start_date ? d.monthly_start_date : null,
        months_count: isMonthly ? d.months_count : null,
        monthly_amount: isMonthly ? d.monthly_amount : null,
        item_type: d.item_type,
        is_feo_breakdown: d.is_feo_breakdown,
        is_internal_plan: d.is_internal_plan,
      }),
    })
    editPlannedDialog.show = false
    // См. комментарий у deletePlannedItem — refreshComparison один не обновляет
    // planTreeByCat, от которого зависят числа узла/родителей и плашка превышения.
    await Promise.all([refreshComparison(d.feo_category_id), refreshReqData()])
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.detail || e?.message || 'Ошибка сохранения', 'error')
  } finally {
    editPlannedDialog.saving = false
  }
}

// ── Edit category manual-plan dialog (ручной план ФЭО на самой категории) ──
// Жалоба владельца (2026-08-11): «Great Wall POER могу редактировать, а Микроавтобус
// плановый — не могу». Причина — у синтетической строки «ручной план ФЭО» в панели
// (displayPlannedRowsFor, planned.isManual, id = -node.id) карандаш раньше отсутствовал,
// был только «Завести плановую позицию» (это про другое — заводит именованную
// FeoPlannedItem, план листа сам не трогает). Этот диалог — лёгкий редактор ровно тех
// полей, что и формируют синтетическую строку: planned_quantity/planned_amount/unit
// НА САМОЙ КАТЕГОРИИ (PUT /feo-categories/{id}), а НЕ полный feoEditForm (там полей
// больше, чем нужно для этой задачи — легче промахнуться не в то поле).
// ⚠️ Семантика (см. displayPlannedRowsFor выше): FeoCategory.planned_amount — ЦЕНА ЗА
// ЕДИНИЦУ, а не сумма (в отличие от FeoPlannedItem.amount, которое сумма). Подписи
// полей ниже — «Плановое количество» / «Плановая цена за единицу» — и расчётная сумма
// рядом, чтобы это не перепуталось снова (уже дважды ломало боевые числа).
// ⚠️ startInlineAmt/startInlineQty (см. выше) шлют PUT-payload БЕЗ feo_quantity/
// feo_unit/feo_amount/description — FastAPI трактует отсутствующее поле как None
// (см. backend/app/routers/feo_categories.py::update_category — `cat.description =
// category_data.description` присваивается безусловно) и обнуляет их на сервере.
// Здесь эта ловушка не повторяется — payload переносит все существующие поля из `cat`,
// меняются только planned_quantity/planned_amount/unit.
const CATEGORY_UNIT_OPTIONS = ['шт.', 'усл.', 'компл.', 'уп.', 'м.', 'кг.', 'л.', 'п.м.', 'кв.м.', 'час.', 'мес.', 'год']

// «Ед. изм.» — число (напр. 5500000 вместо «шт») — след старого импорта со сдвигом
// колонок (на проде таких 35 категорий). Распознаём как «подозрительно», если строка
// целиком — число (с необязательным десятичным разделителем), но не молчим и не правим
// сами — только подсвечиваем и предлагаем заменить (см. isCategoryUnitSuspicious ниже).
function isNumericLikeUnit(u: string | null | undefined): boolean {
  const s = String(u ?? '').trim()
  if (!s) return false
  return /^-?\d+([.,]\d+)?$/.test(s.replace(/\s+/g, ''))
}

const editCategoryPlanDialog = reactive({
  show: false, saving: false,
  nodeId: 0, categoryName: '',
  quantity: '' as string | number,
  unitPrice: '' as string | number,
  unit: '' as string,
})

const isCategoryUnitSuspicious = computed(() => isNumericLikeUnit(editCategoryPlanDialog.unit))

const editCategoryPlanSum = computed<number | null>(() => {
  const q = editCategoryPlanDialog.quantity !== '' ? Number(editCategoryPlanDialog.quantity) : null
  const p = editCategoryPlanDialog.unitPrice !== '' ? Number(editCategoryPlanDialog.unitPrice) : null
  if (q != null && p != null && !isNaN(q) && !isNaN(p) && q > 0 && p > 0) return q * p
  return null
})

function openEditCategoryPlan(node: FeoNode) {
  editCategoryPlanDialog.nodeId = node.id
  editCategoryPlanDialog.categoryName = node.name
  editCategoryPlanDialog.quantity = node.planned_quantity != null ? parseFloat(String(node.planned_quantity)) : ''
  editCategoryPlanDialog.unitPrice = node.planned_amount != null ? parseFloat(String(node.planned_amount)) : ''
  editCategoryPlanDialog.unit = node.unit || ''
  editCategoryPlanDialog.show = true
}

async function saveEditCategoryPlan() {
  const nodeId = editCategoryPlanDialog.nodeId
  const cat = feoCategories.value.find(c => c.id === nodeId)
  if (!nodeId || !cat) { editCategoryPlanDialog.show = false; return }
  editCategoryPlanDialog.saving = true
  try {
    const qtyRaw = String(editCategoryPlanDialog.quantity ?? '').trim()
    const amtRaw = String(editCategoryPlanDialog.unitPrice ?? '').trim()
    const qty = qtyRaw === '' ? null : Number(qtyRaw)
    const unitPrice = amtRaw === '' ? null : Number(amtRaw)
    const unit = editCategoryPlanDialog.unit.trim() || null
    const res = await apiFetch<any>(`/feo-categories/${nodeId}`, {
      method: 'PUT',
      body: JSON.stringify({
        subsidy_id: cat.subsidy_id, name: cat.name, code: cat.code ?? null, appendix: cat.appendix ?? null,
        is_active: cat.is_active, budget: cat.budget ?? null,
        feo_quantity: cat.feo_quantity ?? null, feo_unit: cat.feo_unit ?? null, feo_amount: cat.feo_amount ?? null,
        description: cat.description ?? null,
        planned_quantity: qty, planned_amount: unitPrice, unit,
      }),
    })
    // Оптимистично патчим локально (строка панели — displayPlannedRowsFor читает node
    // напрямую из feoCategories), НО «Плановая сумма» в шапке (feoPlannedDisplayFor)
    // читает готовое число с бэкенда (planTreeByCat, см. feoPlannedDisplayRaw) — этот
    // локальный патч его не трогает. startInlineAmt/startInlineQty останавливаются
    // здесь и из-за этого шапка у них не обновляется без reload — тот же полный
    // updateFeoCategory() (v-diалог «Редактировать») дальше зовёт loadFeo(), и здесь
    // тоже зовём — иначе не выполняется приёмка «шапка обновилась без перезагрузки».
    cat.planned_quantity = qty
    cat.planned_amount = unitPrice
    cat.unit = unit
    feoCategories.value = [...feoCategories.value]
    editCategoryPlanDialog.show = false
    showSnack('План категории сохранён')
    if (res?.warning) showSnack(res.warning, 'warning')
    if (selectedId.value) await loadFeo(selectedId.value)
  } catch (e: any) {
    showSnack(e.detail || 'Ошибка сохранения', 'error')
  } finally {
    editCategoryPlanDialog.saving = false
  }
}

// Contractor override state
const showOverrideDialog = ref(false)
const savingOverride = ref(false)
const overrideSubsidyId = ref<number | null>(null)
const overrideForm = ref({
  org_type: '', inn: '', kpp: '', ogrn: '',
  signatory_last_name: '', signatory_first_name: '', signatory_middle_name: '', signatory_position: '',
  signatory_basis: '', address: '', postal_address: '',
  contact_person: '', phone: '', email: '', org_phone: '', org_email: '',
  bank_details: '', settlement_account: '', bank_name: '', bik: '', correspondent_account: '',
})

// Events (Мероприятия) state
interface EventItem {
  id: number; subsidy_id: number; name: string; is_active: boolean
  region?: string; date_from?: string; date_to?: string
  order_decree?: string; planned_indicators?: string; actual_indicators?: string
  media_link_1?: string; media_link_2?: string; media_link_3?: string
}
const subsidyEvents = ref<EventItem[]>([])
const showAddEventDialog = ref(false)
const newEventName = ref('')
const newEventRegion = ref('')
const newEventDateFrom = ref('')
const newEventDateTo = ref('')
const newEventOrderDecree = ref('')
const newEventPlannedIndicators = ref('')
const newEventActualIndicators = ref('')
const newEventMediaLink1 = ref('')
const newEventMediaLink2 = ref('')
const newEventMediaLink3 = ref('')
const showEditEventDialog = ref(false)
const savingEvent = ref(false)
const editEventForm = ref<EventItem>({
  id: 0, subsidy_id: 0, name: '', is_active: true,
  region: '', date_from: '', date_to: '',
  order_decree: '', planned_indicators: '', actual_indicators: '',
  media_link_1: '', media_link_2: '', media_link_3: '',
})
const userRoleRaw = localStorage.getItem('user_role') || ''
const isAdminLevel = ['superadmin', 'org_admin', 'admin'].includes(userRoleRaw)
// 12-05: admin or account_owner can save a version
const canSaveVersion = computed(() => ['superadmin', 'org_admin', 'admin', 'account_owner'].includes(userRoleRaw))
// B5 (2026-09-01): право на запись в дерево категорий ФЭО (backend-гейт —
// feo_category.edit, см. backend/app/routers/feo_categories.py). Экспорт и
// просмотр остаются доступны без этого права — прячем только
// create/edit/delete/import/reorder/drag редактора дерева ниже.
const authStore = useAuthStore()
const canEditFeo = computed(() => authStore.hasAction('feo_category.edit'))
// SaaS-роли (как в WishesView.vue) — им доступен force-возврат заявки в черновик из диалога блокировки удаления
const isSaas = computed(() => ['superadmin', 'account_owner'].includes(userRoleRaw))
// Как в WishesView.vue — id текущего пользователя, чтобы определить «это назначенный
// согласующий превышения плана ФЭО или нет» (см. excessMyPendingStep/decidePlanExcess).
const currentUserId = Number(localStorage.getItem('user_id') || '0')

// Snackbar — единый механизм (useToast + ToastContainer, смонтирован в App.vue).
// По умолчанию уведомление НЕ исчезает само (duration=0): результат действия
// пользователя должен быть прочитан, а не пропасть за 3-4 секунды.
const toast = useToast()

const contractors = ref<{ id: number; name: string; inn?: string }[]>([])

const form = ref({ name: '', year: new Date().getFullYear(), budget: 0, description: '', contractor_id: null as number | null, agreement_text: '' as string, basis_doc_number: '' as string, basis_doc_date: '' as string })
const editForm = ref({ id: 0, name: '', year: new Date().getFullYear(), budget: 0, description: '', contractor_id: null as number | null, agreement_text: '' as string, basis_doc_number: '' as string, basis_doc_date: '' as string, grantor_name: '' as string, ministry_name: '' as string, extra_contract_clause_1: null as string | null, extra_contract_clause_2: null as string | null, require_planned_dates: true as boolean, ceiling_warn_percent: 90 as number | null })
// План zany-fluttering-mountain.md, п.1/п.5: planSource/manual_plan_amount — новый
// переключатель «как считать план» (по плановым позициям / по вручную заданной
// сумме), см. блок «Плановые показатели» в диалогах создания/редактирования ниже.
const feoForm  = ref({ parentId: null as number | null, name: '', code: '', appendix: '', budget: null as number | null, budgetAuto: false, planned_quantity: null as number | null, qtyAuto: false, planned_amount: null as number | null, amtAuto: false, unit: '' as string, feo_quantity: null as number | null, feo_unit: '' as string, description: '', feo_amount: '' as string | number, planSource: 'planned_items' as 'planned_items' | 'manual_sum', manual_plan_amount: null as number | null })
const feoEditForm = ref({ name: '', code: '', appendix: '', budget: null as number | null, budgetAuto: false, planned_quantity: null as number | null, qtyAuto: false, planned_amount: null as number | null, amtAuto: false, unit: '' as string, is_active: true, hasChildren: false, parent_id: null as number | null, feo_quantity: null as number | null, feo_unit: '' as string, description: '', feo_amount: '' as string | number, planSource: 'planned_items' as 'planned_items' | 'manual_sum', manual_plan_amount: null as number | null })

// Дефект 2026-08-31 (владелец, форма «Редактировать направление ФЭО», тупик 409/422):
// v-model.number на Vuetify НЕ приводит очищенное поле к null — Vue's looseToNumber
// возвращает исходную строку '' как есть, если parseFloat('') === NaN. Наивное
// `field ?? null` в PUT/POST-payload пропускало эту '' насквозь (?? срабатывает
// только на null/undefined) → бэкенд получал '' в Optional[float]-поле → 422
// «ожидается число» с техническим именем поля вместо русской подписи (feo_quantity
// не было в field_labels в app/__init__.py — трогать этот файл в этой задаче
// запрещено, поэтому чиним у источника, здесь). Пустая строка/null/undefined —
// «поле не задано» = null; 0 — валидное число, НЕ схлопывается в null.
function numOrNull(v: unknown): number | null {
  if (v === '' || v === null || v === undefined) return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

// Правило владельца (2026-08-09): «Плановое кол-во»/«Плановая стоимость за ед.» —
// пара. Задана цена без количества (или наоборот) → сумма НЕ считается автоматически
// и молча ломается (см. backend _validate_plan_pair в feo_categories.py, тот же порог
// >0). auto-режим («Авто из детей», отправляется как null) считается пустым полем —
// зеркалит то, что реально уйдёт в payload PUT/POST.
function feoPlanPairError(
  qty: number | null, qtyAuto: boolean,
  amt: number | null, amtAuto: boolean,
): string {
  const qFilled = !qtyAuto && qty != null && Number(qty) > 0
  const aFilled = !amtAuto && amt != null && Number(amt) > 0
  if (qFilled === aFilled) return ''
  return qFilled
    ? 'Задано количество, но не задана цена за ед. — заполните оба поля (сумма посчитается автоматически), либо очистите количество и задайте план общей суммой отдельной плановой позицией («Добавить плановую» в панели) без указания количества.'
    : 'Задана цена за ед., но не задано количество — заполните оба поля (сумма посчитается автоматически), либо очистите цену и задайте план общей суммой отдельной плановой позицией («Добавить плановую» в панели) без указания количества.'
}

const feoAddPlanPairError = computed(() => feoPlanPairError(
  feoForm.value.planned_quantity, feoForm.value.qtyAuto,
  feoForm.value.planned_amount, feoForm.value.amtAuto,
))
const feoEditPlanPairError = computed(() => feoPlanPairError(
  feoEditForm.value.planned_quantity, feoEditForm.value.qtyAuto,
  feoEditForm.value.planned_amount, feoEditForm.value.amtAuto,
))

// Правка 2Б (2026-08-11): диалог редактирования категории решает, какую из трёх
// подстрок «Плановых показателей» показать — «есть подкатегории» / «план не задан,
// заведите позицию» / «старый формат, только для чтения». Категория без детей и
// хотя бы с одним из двух полей — тот самый «старый формат»; ноль/пусто в обоих —
// план ещё не задан вовсе.
const feoEditManualPlanSet = computed(() => {
  const f = feoEditForm.value
  if (f.hasChildren) return false
  const q = f.planned_quantity
  const a = f.planned_amount
  return (q != null && Number(q) > 0) || (a != null && Number(a) > 0)
})

// План zany-fluttering-mountain.md, п.1: «при переключении на ручную сумму у
// категории, где уже есть плановые позиции, — предупреждение о последствиях»
// (владелец: позиции останутся, план будет считаться от суммы, их превышение
// потребует согласования). «Уже есть позиции» — категория до открытия диалога
// была в режиме 'planned_items' (feoEditTarget — исходный, не мутируется формой)
// и её Σ позиций (plan_manual из planTreeByCat, тот же сигнал, что и в
// isManualPosLeaf выше) больше нуля.
const feoEditPlanSourceSwitchWarning = computed(() => {
  const target = feoEditTarget.value
  if (!target) return false
  const origSource = target.plan_source || 'planned_items'
  if (origSource !== 'planned_items') return false
  if (feoEditForm.value.planSource !== 'manual_sum') return false
  const t = planTreeByCat.value[target.id]
  return !!(t && Number(t.plan_manual || 0) > 0.005)
})

// ── Computed ──────────────────────────────────────
const availableYears = computed(() =>
  [...new Set(allSubsidies.value.map(s => s.year))].sort((a, b) => b - a)
)

const editInitialContractor = computed(() => {
  if (!editForm.value.contractor_id) return null
  const c = contractors.value.find((x: any) => x.id === editForm.value.contractor_id)
  return c ? { id: c.id, name: c.name, inn: c.inn } : { id: editForm.value.contractor_id, name: `Контрагент #${editForm.value.contractor_id}`, inn: undefined }
})

const CARD_ORDER_KEY = 'subsidies_card_order'
const cardDragIdx = ref(-1)
const cardDragOverIdx = ref(-1)
const subsidyOrder = ref<number[]>(JSON.parse(localStorage.getItem(CARD_ORDER_KEY) || '[]'))

function onCardDragStart(e: DragEvent, idx: number) {
  cardDragIdx.value = idx
  if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move'
}
function onCardDragOver(idx: number) {
  cardDragOverIdx.value = idx
}
function onCardDrop(targetIdx: number) {
  const srcIdx = cardDragIdx.value
  if (srcIdx < 0 || srcIdx === targetIdx) return
  const ids = filteredSubsidies.value.map(s => s.id)
  const [moved] = ids.splice(srcIdx, 1)
  ids.splice(targetIdx, 0, moved)
  subsidyOrder.value = ids
  localStorage.setItem(CARD_ORDER_KEY, JSON.stringify(ids))
  cardDragOverIdx.value = -1
  cardDragIdx.value = -1
}

const filteredSubsidies = computed(() => {
  const yearFiltered = allSubsidies.value.filter(s => s.year === selectedYear.value)
  if (subsidyOrder.value.length === 0) return yearFiltered
  const orderMap = new Map(subsidyOrder.value.map((id, i) => [id, i]))
  return [...yearFiltered].sort((a, b) => {
    const ai = orderMap.get(a.id) ?? 9999
    const bi = orderMap.get(b.id) ?? 9999
    return ai - bi
  })
})

// ── Table ↔ Cards toggle ──────────────────────────
const { mobile, viewMode, effectiveView, page: subPage, totalPages: subTotalPages, paged: subPaged } = useCardView<SubsidyRow>({
  storageKey: 'subsidies_view_mode',
  source: () => filteredSubsidies.value,
})

const subsidyTableHeaders = [
  { title: 'Название', key: 'name', minWidth: '200px' },
  { title: 'Бюджет ФЭО', key: 'feo_budget_total', align: 'end' as const },
  { title: 'Запланировано', key: 'planned', align: 'end' as const },
  { title: 'Заказано', key: 'ordered', align: 'end' as const },
  { title: 'Оплачено', key: 'paid', align: 'end' as const },
  { title: 'Контрагент', key: 'contractor_name' },
  { title: 'ФЭО', key: 'feo_filled', align: 'center' as const },
  { title: 'Потолок', key: 'ceiling_committed_percent', align: 'center' as const },
  { title: '', key: 'actions', sortable: false, align: 'end' as const },
]

function getSubsidyExportColumns() {
  return subsidyTableHeaders
    .filter(h => h.key !== 'actions' && h.title)
    .map(h => ({ key: h.key, title: h.title, align: h.align }))
}
function getSubsidyExportRows() {
  return filteredSubsidies.value
}

const selectedBudget = computed(() => {
  if (!selectedSubsidy.value) return 0
  // Живой расчёт по дереву ФЭО; ручное поле budget — только как fallback (решение 15.07)
  if (feoTree.value.length) return totalFeoEffective.value
  return selectedSubsidy.value.feo_budget_total || selectedSubsidy.value.budget || 0
})

// «Запланировано» панели ФЭО = плановая сумма дерева (ручные позиции ФЭО + из заявок в плане закупок),
// а не только закупки — план вносится и импортом/созданием позиций прямо в ФЭО
const selectedPlannedTotal = computed(() => {
  if (feoTree.value.length) {
    return feoTree.value.reduce((acc, r) => acc + feoPlannedTotalFor(r) + feoPlannedRequestsFor(r), 0)
  }
  return selectedSubsidy.value?.planned || 0
})

const totals = computed(() => ({
  budget:           filteredSubsidies.value.reduce((s, x) => s + (x.feo_budget_total || x.budget || 0), 0),
  planned:          filteredSubsidies.value.reduce((s, x) => s + x.planned,            0),
  ordered:          filteredSubsidies.value.reduce((s, x) => s + x.ordered,            0),
  contracted:       filteredSubsidies.value.reduce((s, x) => s + (x.contracted || 0),  0),
  paid:             filteredSubsidies.value.reduce((s, x) => s + x.paid,               0),
  work:             filteredSubsidies.value.reduce((s, x) => s + x.work,               0),
  contracts:        filteredSubsidies.value.reduce((s, x) => s + x.contracts,          0),
  delivered:        filteredSubsidies.value.reduce((s, x) => s + x.delivered,          0),
  delivered_unpaid: filteredSubsidies.value.reduce((s, x) => s + x.delivered_unpaid,   0),
}))

// ── FEO tree ──────────────────────────────────────
// ФИКС (замер на проде 2026-08-13, жалоба владельца: «Приобретение футболок…» смещено
// относительно «Призового фонда…», дети «Окружных»/«Финала» не на одной линии, хотя в БД
// у всех level=3 и один и тот же parent_id — данные ровные, врала отрисовка). Раньше
// глубина ребёнка бралась из node.depth родителя ПРЯМО В ЭТОМ ЖЕ ПРОХОДЕ по плоскому
// cats.forEach — если ребёнок в массиве (порядок = sort_order/id) шёл РАНЬШЕ своего
// родителя, у родителя на тот момент ещё не была проставлена его собственная глубина
// (он сам ещё не был привязан к своему родителю в этом же проходе), и ребёнок получал
// depth на 1 меньше правильного. Отсюда «часть строк ровные, часть съехала» — зависело
// от порядка в массиве, а не от structure. Теперь связи (children/hasChildren/roots)
// строятся отдельным первым проходом, а depth — вторым проходом, обходом уже готового
// дерева от корней, поэтому не зависит от порядка элементов в исходном списке.
const feoTree = computed<FeoNode[]>(() => {
  const cats = feoCategories.value
  const byId: Record<number, FeoNode> = {}
  cats.forEach(c => { byId[c.id] = { ...c, depth: 0, hasChildren: false, children: [] } })
  const roots: FeoNode[] = []
  cats.forEach(c => {
    const node = byId[c.id]
    if (c.parent_id && byId[c.parent_id]) {
      byId[c.parent_id].children.push(node)
      byId[c.parent_id].hasChildren = true
    } else {
      roots.push(node)
    }
  })
  // visited защищает от циклов в битых данных (узел, ссылающийся сам на себя или
  // образующий петлю через parent_id) — такой узел просто не будет посещён повторно,
  // обход не зависает.
  const visited = new Set<number>()
  const assignDepth = (node: FeoNode, depth: number) => {
    if (visited.has(node.id)) return
    visited.add(node.id)
    node.depth = depth
    node.children.forEach(child => assignDepth(child, depth + 1))
  }
  roots.forEach(r => assignDepth(r, 0))
  return roots
})

function flattenAll(nodes: FeoNode[]): FeoNode[] {
  return nodes.flatMap(n => [n, ...flattenAll(n.children)])
}

function isNodeVisible(node: FeoNode): boolean {
  if (feoSearch.value) return true  // при поиске все найденные видны
  if (!node.parent_id) return true
  const checkParent = (pid: number): boolean => {
    if (!expandedIds.value.includes(pid)) return false
    const p = feoCategories.value.find(c => c.id === pid)
    return !p?.parent_id || checkParent(p.parent_id)
  }
  return checkParent(node.parent_id)
}

const visibleFeoNodes = computed(() => {
  const q = feoSearch.value.toLowerCase()
  const all = flattenAll(feoTree.value)
  if (q) return all.filter(n => n.name.toLowerCase().includes(q) || (n.code ?? '').toLowerCase().includes(q))
  // Баг (2026-08-12): фильтр по видимости предков раньше стоял только на guard'е
  // ОСНОВНОЙ строки узла в шаблоне (v-if="isNodeVisible(node) && ..."). Остальные
  // блоки того же v-for (панель плановых позиций, служебки, папки закупок) такого
  // guard'а не имели — при сворачивании родительской категории её строка пропадала,
  // а эти блоки дочерних узлов оставались висеть на экране. Фильтруем здесь, в
  // источнике списка, чтобы ни один блок цикла не рендерился для скрытого узла —
  // isNodeVisible сама учитывает expandedIds (и остаётся true при активном поиске).
  return all.filter(isNodeVisible)
})

// Решение 14.07: итог по субсидии НЕ суммируется из дерева — сравнение всегда
// с ручным бюджетом субсидии (Subsidy.budget)
const totalFeoBudget = computed(() => {
  const b = selectedSubsidy.value?.budget
  return b != null && Number(b) > 0 ? Number(b) : null
})

// Расчётная справка: Σ effective по корням дерева
const totalFeoEffective = computed(() => feoTree.value.reduce((a, r) => a + feoEffectiveFor(r), 0))

// Расхождение итога: расчёт по дереву vs ручной бюджет субсидии
const totalFeoDiff = computed(() =>
  totalFeoBudget.value != null ? totalFeoEffective.value - totalFeoBudget.value : 0
)

const totalFeoPurchased = computed(() => feoTree.value.reduce((a, r) => a + feoPurchasedFor(r), 0))

// Итог по той же шкале, что и колонка «В плане-графике» в строках дерева (решение
// владельца 2026-08-18) — footer «ИТОГО» обязан считаться через feoInPlanScheduleFor,
// иначе строки показывают сумму по плану закупок, а ИТОГО — старую (только delivered/paid).
const totalFeoInPlanSchedule = computed(() => feoTree.value.reduce((a, r) => a + feoInPlanScheduleFor(r), 0))

// ── Animated KPI targets for the detail panel (9 cards) ──────────────
const kpiSubTarget_budget            = computed(() => selectedBudget.value)
const kpiSubTarget_plan_schedule     = computed(() => selectedPlannedTotal.value)
const kpiSubTarget_work              = computed(() => selectedSubsidy.value?.work              ?? 0)
const kpiSubTarget_ordered           = computed(() => selectedSubsidy.value?.ordered           ?? 0)
const kpiSubTarget_contracts         = computed(() => selectedSubsidy.value?.contracts         ?? 0)
const kpiSubTarget_delivered         = computed(() => selectedSubsidy.value?.delivered         ?? 0)
const kpiSubTarget_delivered_unpaid  = computed(() => selectedSubsidy.value?.delivered_unpaid  ?? 0)
const kpiSubTarget_paid              = computed(() => selectedSubsidy.value?.paid              ?? 0)
const kpiSubTarget_free              = computed(() => selectedBudget.value - selectedPlannedTotal.value)

const kpiSubAnim_budget            = useAnimatedNumber(kpiSubTarget_budget,           800)
const kpiSubAnim_plan_schedule     = useAnimatedNumber(kpiSubTarget_plan_schedule,    800)
const kpiSubAnim_work              = useAnimatedNumber(kpiSubTarget_work,             800)
const kpiSubAnim_ordered           = useAnimatedNumber(kpiSubTarget_ordered,          800)
const kpiSubAnim_contracts         = useAnimatedNumber(kpiSubTarget_contracts,        800)
const kpiSubAnim_delivered         = useAnimatedNumber(kpiSubTarget_delivered,        800)
const kpiSubAnim_delivered_unpaid  = useAnimatedNumber(kpiSubTarget_delivered_unpaid, 800)
const kpiSubAnim_paid              = useAnimatedNumber(kpiSubTarget_paid,             800)
const kpiSubAnim_free              = useAnimatedNumber(kpiSubTarget_free,             800)

// ── KPI drill-down: клик по карточке подсвечивает в дереве ФЭО состав суммы ──────
// Типы/константы/kpiItemMatches вынесены в @/constants/kpiMetrics.ts (см. import выше) —
// логика покрыта тестом на паритет с backend/app/routers/dashboard.py.

interface KpiSnapshot {
  expandedIds: number[]
  expandedReqItems: number[]
  expandedPurchases: number[]
  expandedItemPanels: number[]
  expandedPlannedItems: number[]
  plannedBase: PlannedBase
  feoSearch: string
}
const activeKpi = ref<KpiKey | null>(null)
const kpiSnapshot = ref<KpiSnapshot | null>(null)

function feoHasChildren(id: number): boolean {
  return feoCategories.value.some(c => c.parent_id === id)
}

const feoParentMap = computed<Record<number, number | null>>(() => {
  const map: Record<number, number | null> = {}
  for (const c of feoCategories.value) map[c.id] = c.parent_id
  return map
})

// Строгие предки узла (без самого узла), до корня
function feoAncestorIds(id: number): number[] {
  const result: number[] = []
  let pid = feoParentMap.value[id] ?? null
  while (pid != null) {
    result.push(pid)
    pid = feoParentMap.value[pid] ?? null
  }
  return result
}

// Все id позиций (FeoReqItem.id), из которых складывается активная метрика
// ('items' и 'mixed' считают позиции заявок; чистый 'nodes' — нет)
const kpiItemIds = computed<Set<number>>(() => {
  const key = activeKpi.value
  const set = new Set<number>()
  if (!key || KPI_MODE[key] === 'nodes') return set
  for (const items of Object.values(plannedItemsByCat.value)) {
    for (const it of items) if (kpiItemMatches(key, it)) set.add(it.id)
  }
  return set
})

// Закупки (purchase_id), содержащие подходящие позиции — для режима «по закупкам»
const kpiPurchaseIds = computed<Set<number>>(() => {
  const key = activeKpi.value
  const set = new Set<number>()
  if (!key || KPI_MODE[key] === 'nodes') return set
  for (const items of Object.values(plannedItemsByCat.value)) {
    for (const it of items) if (kpiItemMatches(key, it)) set.add(it.purchase_id)
  }
  return set
})

// Листья ФЭО, в которые слиты одноимённые позиции заявок (mergedReqByCat.matched)
const kpiMatchedLeafIds = computed<Set<number>>(() => {
  const key = activeKpi.value
  const set = new Set<number>()
  if (!key || KPI_MODE[key] === 'nodes') return set
  for (const [leafIdStr, items] of Object.entries(mergedReqByCat.value.matched)) {
    if (items.some(it => kpiItemMatches(key, it))) set.add(Number(leafIdStr))
  }
  return set
})

// Категории-владельцы «виртуальных» позиций заявок (не слитых в существующий лист)
const kpiOwnerCatIds = computed<Set<number>>(() => {
  const key = activeKpi.value
  const set = new Set<number>()
  if (!key || KPI_MODE[key] === 'nodes') return set
  if (plannedBase.value === 'purchases') {
    for (const [catIdStr, folders] of Object.entries(purchaseFoldersByCat.value)) {
      if (folders.some(f => f.items.some(it => kpiItemMatches(key, it)))) set.add(Number(catIdStr))
    }
    return set
  }
  for (const [catIdStr, groups] of Object.entries(mergedReqByCat.value.virtualByCat)) {
    if (groups.some(g => g.items.some(it => kpiItemMatches(key, it)))) set.add(Number(catIdStr))
  }
  return set
})

// Регресс владельца (2026-08-13): подсветка выше искала подходящие позиции ТОЛЬКО среди
// mergedReqByCat (matched/virtualByCat) — а туда попадают лишь позиции БЕЗ привязки к плановой
// позиции (feo_planned_item_id == null, см. фильтр в mergedReqByCat). После бэкфилла привязок
// на проде (МИНПРОС_2026) все позиции категории оказались привязаны — mergedReqByCat опустел,
// и плитке «Поставлено, не оплачено» стало нечего раскрывать, хотя сумма на плитке ненулевая.
// plannedItemsByCat (см. её объявление выше) — источник истины: ВСЕ позиции закупок категории,
// привязанные и нет, без исключений. Категория попадает сюда, если у неё директно (не у потомков —
// ключ карты это feo_category_id самой позиции) есть хоть одна позиция под активную метрику —
// не важно, лист это или направление (направления теперь тоже могут иметь свои плановые позиции,
// см. hasOwnPlannedAmountFor выше).
const kpiPlannedOwnerCatIds = computed<Set<number>>(() => {
  const key = activeKpi.value
  const set = new Set<number>()
  if (!key || KPI_MODE[key] === 'nodes') return set
  for (const [catIdStr, items] of Object.entries(plannedItemsByCat.value)) {
    if (items.some(it => kpiItemMatches(key, it))) set.add(Number(catIdStr))
  }
  return set
})

// Плановые позиции (FeoPlannedItem.id), к которым привязана подходящая позиция закупки —
// нужно раскрыть саму строку «Позиция плана» (expandedPlannedItems), иначе панель категории
// откроется (см. kpiPlannedOwnerCatIds выше), а строка «План vs факт» под конкретной плановой
// позицией останется свёрнутой, и позиция всё равно не будет видна. mergedReqByCat.linkedByPlanned
// уже группирует ВСЕ привязанные позиции закупок по feo_planned_item_id — ровно то, что нужно.
const kpiPlannedRowIds = computed<Set<number>>(() => {
  const key = activeKpi.value
  const set = new Set<number>()
  if (!key || KPI_MODE[key] === 'nodes') return set
  for (const [plannedIdStr, items] of Object.entries(mergedReqByCat.value.linkedByPlanned)) {
    if (items.some(it => kpiItemMatches(key, it))) set.add(Number(plannedIdStr))
  }
  return set
})

// Узлы дерева ФЭО, попадающие в метрику напрямую: режим 'nodes' (budget/free)
// и режим 'mixed' (plan_schedule — ручные листья ФЭО, которые эндпоинт planned-purchase-items
// вообще не видит). Условие для plan_schedule — НЕ isManualPosLeaf (та проверяет != null через OR
// и подсветила бы лист без фактического вклада в сумму, например с заданным только количеством).
// feoPlannedTotalFor(n) — ровно та формула, что складывается в карточку «Запланировано»
// (qty > 0 && unitPrice > 0), поэтому подсветка совпадает с суммой 1:1.
const kpiNodeIds = computed<Set<number>>(() => {
  const key = activeKpi.value
  const set = new Set<number>()
  if (!key || KPI_MODE[key] === 'items') return set
  for (const n of flattenAll(feoTree.value)) {
    if (key === 'budget' && n.budget != null) set.add(n.id)
    if (key === 'free' && Math.abs(feoFinDiff(n)) > 0.005) set.add(n.id)
    if (key === 'plan_schedule' && !n.hasChildren && feoPlannedTotalFor(n) > 0) set.add(n.id)
  }
  return set
})

// Что нужно раскрыть, чтобы показать состав активной метрики
const kpiExpandTargets = computed<{ ids: Set<number>; reqItems: Set<number>; itemPanels: Set<number>; purchases: Set<number>; plannedItems: Set<number> }>(() => {
  const ids = new Set<number>()
  const reqItems = new Set<number>()
  const itemPanels = new Set<number>()
  const purchases = new Set<number>()
  const plannedItems = new Set<number>()
  if (!activeKpi.value) return { ids, reqItems, itemPanels, purchases, plannedItems }

  for (const catId of kpiOwnerCatIds.value) {
    for (const a of feoAncestorIds(catId)) ids.add(a)
    if (feoHasChildren(catId)) ids.add(catId)
    // ШАГ 1 (2026-08-07): у листа (!feoHasChildren) содержимое kpiOwnerCatIds теперь
    // показывается ИСКЛЮЧИТЕЛЬНО через Таблицу A (expandedItemPanels) — Таблица B
    // (expandedReqItems/reqOwnersAfter) для листьев больше не рендерится, см. reqOwnersAfter.
    else itemPanels.add(catId)
  }
  // Охват для позиций, привязанных к плановой позиции (регресс 2026-08-13, см. комментарий
  // у kpiPlannedOwnerCatIds выше) — панель категории (лист ИЛИ направление со своими позициями)
  // открывается через Таблицу A так же, как и у kpiOwnerCatIds; сама подходящая позиция
  // подсвечивается ВНУТРИ панели, под своей плановой строкой (см. kpiItemRowClass в шаблоне).
  for (const catId of kpiPlannedOwnerCatIds.value) {
    for (const a of feoAncestorIds(catId)) ids.add(a)
    itemPanels.add(catId)
    if (feoHasChildren(catId)) ids.add(catId)
  }
  for (const plannedId of kpiPlannedRowIds.value) plannedItems.add(plannedId)
  for (const leafId of kpiMatchedLeafIds.value) {
    for (const a of feoAncestorIds(leafId)) ids.add(a)
  }
  for (const nodeId of kpiNodeIds.value) {
    for (const a of feoAncestorIds(nodeId)) ids.add(a)
  }
  if (plannedBase.value === 'purchases') {
    for (const pid of kpiPurchaseIds.value) purchases.add(pid)
  }
  return { ids, reqItems, itemPanels, purchases, plannedItems }
})

// Одно присваивание на каждый ref — именно это даёт автосворачивание лишних папок
function applyKpiExpansion() {
  const t = kpiExpandTargets.value
  expandedIds.value = [...t.ids]
  expandedReqItems.value = new Set(t.reqItems)
  expandedItemPanels.value = new Set(t.itemPanels)
  expandedPurchases.value = new Set(t.purchases)
  // Строки «Позиция плана», под которыми лежит подходящая позиция — раскрываются тем же
  // приёмом (сплошное присваивание). collapsedPlannedItems (ручное сворачивание пользователем,
  // см. комментарий у togglePlannedItemFolder) сюда НЕ подмешивается — эта запись читается
  // только внутри applyDefaultPlannedExpansion, которую этот путь не вызывает; чистим её для
  // раскрытых KPI id на всякий случай, чтобы более поздний ре-запрос comparison (после правки
  // пользователем) не унаследовал стухшее «было свёрнуто вручную» от ДО клика по плитке.
  expandedPlannedItems.value = new Set(t.plannedItems)
  for (const pid of t.plannedItems) collapsedPlannedItems.value.delete(pid)
  // Панели раскрыты напрямую присваиванием (не через toggleItemPanel) — данные для новых
  // id надо подгрузить отдельно, иначе KPI-подсветка откроет пустую панель.
  for (const id of t.itemPanels) {
    if (!comparisonData.value[id] && !loadingComparison.value.has(id)) refreshComparison(id)
  }
}

async function scrollToFirstKpiHighlight() {
  await nextTick()
  const el = feoTableArea.value?.querySelector('.feo-kpi-hl')
  el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

function onKpiCardClick(key: KpiKey) {
  if (!selectedSubsidy.value) return
  if (activeKpi.value === key) { resetKpi(); return }
  if (activeKpi.value === null) {
    kpiSnapshot.value = {
      expandedIds: [...expandedIds.value],
      expandedReqItems: [...expandedReqItems.value],
      expandedPurchases: [...expandedPurchases.value],
      expandedItemPanels: [...expandedItemPanels.value],
      expandedPlannedItems: [...expandedPlannedItems.value],
      plannedBase: plannedBase.value,
      feoSearch: feoSearch.value,
    }
  }
  activeKpi.value = key
  feoSearch.value = '' // поиск ломает isNodeVisible (при поиске видно всё без учёта expandedIds)
  if ((KPI_MODE[key] === 'items' || KPI_MODE[key] === 'mixed') && plannedBase.value !== 'all') {
    plannedBase.value = 'all' // единственный режим, показывающий все позиции без утраты части
  }
  if (!plannedItemsLoaded.value) return // раскрытие применит watch(plannedItemsLoaded) после загрузки
  applyKpiExpansion()
  scrollToFirstKpiHighlight()
}

function resetKpi() {
  const snap = kpiSnapshot.value
  if (snap) {
    expandedIds.value = [...snap.expandedIds]
    expandedReqItems.value = new Set(snap.expandedReqItems)
    expandedPurchases.value = new Set(snap.expandedPurchases)
    expandedItemPanels.value = new Set(snap.expandedItemPanels)
    expandedPlannedItems.value = new Set(snap.expandedPlannedItems)
    plannedBase.value = snap.plannedBase
    feoSearch.value = snap.feoSearch
  }
  activeKpi.value = null
  kpiSnapshot.value = null
}

// watch(plannedBase, ...) вынесен ниже — plannedBase объявлен позже по файлу (TDZ)
watch(plannedItemsLoaded, (v) => {
  if (v && activeKpi.value) applyKpiExpansion()
})
watch(selectedId, () => {
  // узлы другой субсидии — просто гасим kpi-режим, без восстановления снапшота
  activeKpi.value = null
  kpiSnapshot.value = null
})
watch(feoSearch, (v) => {
  if (v && activeKpi.value) resetKpi()
})

function kpiCardClass(key: KpiKey): string {
  return activeKpi.value === key ? 'kpi-card--active' : ''
}

const kpiHasMatches = computed(() => {
  const key = activeKpi.value
  if (!key) return false
  const mode = KPI_MODE[key]
  if (mode === 'nodes') return kpiNodeIds.value.size > 0
  if (mode === 'mixed') return kpiNodeIds.value.size > 0 || kpiItemIds.value.size > 0
  return kpiItemIds.value.size > 0
})

// Класс строки узла дерева ФЭО (feo-tr на 564): совпал / на пути к совпадению / ни при чём
function kpiNodeClass(node: FeoNode): string {
  if (!activeKpi.value) return ''
  if (kpiNodeIds.value.has(node.id) || kpiMatchedLeafIds.value.has(node.id)) return 'feo-kpi-hl'
  if (kpiOwnerCatIds.value.has(node.id) || kpiPlannedOwnerCatIds.value.has(node.id)) return 'feo-kpi-path'
  const ancestors = feoAncestorIds(node.id)
  if (ancestors.some(pid => kpiOwnerCatIds.value.has(pid) || kpiPlannedOwnerCatIds.value.has(pid) || kpiMatchedLeafIds.value.has(pid) || kpiNodeIds.value.has(pid))) {
    return 'feo-kpi-path'
  }
  return 'feo-kpi-dim'
}

// Класс строки виртуальной позиции/заголовка группы (reqItemRowsFor)
function kpiReqRowClass(row: FeoReqRow): string {
  if (!activeKpi.value) return ''
  const hit = row.items.some(it => kpiItemIds.value.has(it.id))
  if (!hit) return 'feo-kpi-dim'
  return row.group ? 'feo-kpi-hl' : 'feo-kpi-path'
}

// Класс строки одиночной позиции закупки (msrc / панель источников / товар в папке-закупке).
// Принимает и FeoReqItem (id), и FeoActualItem (purchase_item_id — та же строка purchase_items,
// просто другой эндпоинт/интерфейс, см. комментарий у FeoActualItem) — обе используют один и тот
// же набор id, kpiItemIds. Добавлено для строк «План vs факт» внутри панели плановой позиции
// (регресс 2026-08-13: раньше у этих строк не было kpi-класса вовсе, см. правку у kpiPlannedOwnerCatIds).
function kpiItemRowClass(it: FeoReqItem | FeoActualItem): string {
  if (!activeKpi.value) return ''
  const id = 'id' in it ? it.id : it.purchase_item_id
  return kpiItemIds.value.has(id) ? 'feo-kpi-hl' : 'feo-kpi-dim'
}

// Класс строки папки-закупки (режим «по закупкам»)
function kpiFolderClass(f: FeoPurchaseFolder): string {
  if (!activeKpi.value) return ''
  return f.items.some(it => kpiItemIds.value.has(it.id)) ? 'feo-kpi-path' : 'feo-kpi-dim'
}

// Уникальные статусы товаров виртуальной группы, отсортированные по жизненному циклу закупки
function groupStatuses(g: FeoVirtualGroup): { status: string; count: number; label: string }[] {
  const counts = new Map<string, number>()
  for (const it of g.items) counts.set(it.purchase_status, (counts.get(it.purchase_status) || 0) + 1)
  return PURCHASE_STATUS_ORDER
    .filter(s => counts.has(s))
    .map(s => ({ status: s, count: counts.get(s)!, label: PURCHASE_STATUS_META[s]?.label ?? s }))
}

// Финансирование ФЭО: ТОЛЬКО ручное значение (решение 14.07 — без авто-суммирования из детей)
function feoBudgetFor(node: FeoNode): number {
  return node.budget != null ? Number(node.budget) : 0
}

// Расчётное значение узла: ручное ФЭО, если задано; иначе факт (поставлено/оплачено),
// если появился; иначе плановая сумма. Группа без ручного — Σ по детям.
function feoEffectiveFor(node: FeoNode): number {
  if (node.budget != null) return Number(node.budget)
  if (!node.hasChildren) {
    const fact = purchaseTotals.value[node.id] || 0
    return fact > 0 ? fact : feoPlannedTotalFor(node)
  }
  return node.children.reduce((acc, child) => acc + feoEffectiveFor(child), 0)
}

// Σ ручного ФЭО в поддеревьях прямых детей. Факт/план НЕ подставляются;
// budget 0 или NULL = «не задано» (в UI оба показываются как «Задать»)
function manualChildFeoSum(node: FeoNode): number {
  const walk = (n: FeoNode): number =>
    Number(n.budget) > 0 ? Number(n.budget) : n.children.reduce((a, c) => a + walk(c), 0)
  return node.children.reduce((a, c) => a + walk(c), 0)
}

function hasManualChildFeo(node: FeoNode): boolean {
  const walk = (n: FeoNode): boolean => Number(n.budget) > 0 || n.children.some(walk)
  return node.children.some(walk)
}

function isAutoNode(node: FeoNode): boolean {
  if (!node.hasChildren) return false
  return node.budget == null
}

/** Rollup-хелпер: возвращает qty/amount для узла с признаком «авто» (из потомков). */
function feoRollup(node: FeoNode): { qty: number | null; qtyAuto: boolean; amount: number | null; amountAuto: boolean } {
  const ownQty = node.feo_quantity != null ? Number(node.feo_quantity) : null
  const ownAmt = node.feo_amount != null ? Number(node.feo_amount) : null
  if (ownQty != null || ownAmt != null) {
    return { qty: ownQty, qtyAuto: false, amount: ownAmt, amountAuto: false }
  }
  if (!node.hasChildren) return { qty: null, qtyAuto: false, amount: null, amountAuto: false }
  // Суммируем по прямым и косвенным детям рекурсивно
  let sumQty = 0; let hasQty = false
  let sumAmt = 0; let hasAmt = false
  const walkChildren = (children: FeoNode[]) => {
    for (const c of children) {
      const r = feoRollup(c)
      if (r.qty != null) { sumQty += r.qty; hasQty = true }
      if (r.amount != null) { sumAmt += r.amount; hasAmt = true }
    }
  }
  walkChildren(node.children)
  return {
    qty: hasQty ? sumQty : null, qtyAuto: hasQty,
    amount: hasAmt ? sumAmt : null, amountAuto: hasAmt,
  }
}

// Фактически запланированные расходы:
// - листовая категория (нет детей) → берём закупки, привязанные напрямую к ней
// - родительская категория → ТОЛЬКО сумма детей (закупки напрямую на уровне 1/2 не считаются)
// ⚠️ Старая шкала «Остатка» (только delivered/paid) — решением владельца 2026-08-18 строка
// дерева ФЭО больше НЕ использует эту функцию (заменена на feoInPlanScheduleFor), но саму
// функцию не удаляем: проверено грепом, используется в других местах (напр. плашка факта).
function feoPurchasedFor(node: FeoNode): number {
  if (!node.hasChildren) {
    return purchaseTotals.value[node.id] || 0
  }
  return node.children.reduce((acc, child) => acc + feoPurchasedFor(child), 0)
}

// Задача владельца «план ≠ факт» (сессия 2026-08-06, Шаг 5): «Фактическая сумма» дерева ФЭО
// читает готовое число fact из GET /feo-categories/plan-tree (compute_feo_plan_tree — единая
// формула факта, уже питающая плашку «итог закупки дороже плана», см. excessFactFor()).
// Учитывает ContractItem/contract_price с «Ведётся работа» (не только delivered/paid, как
// feoPurchasedFor() выше — тот оставлен нетронутым для «Остатка» и прочих мест, не входящих
// в явное поручение). planTreeByCat уже содержит fact для каждого узла, включая роллап по
// родителям (бэкенд суммирует по дереву сам — фронт не пересчитывает).
function feoFactFor(node: FeoNode): number {
  return planTreeByCat.value[node.id]?.fact || 0
}

// База остатка: от плановой суммы или от финансирования по ФЭО
const residualBase = ref<'plan' | 'feo'>('plan')

// Режим колонок «Плановая сумма»/«Плановое кол-во» — единый синхронный переключатель
type PlannedBase = 'all' | 'manual' | 'requests' | 'purchases'
const plannedBase = ref<PlannedBase>(feoDisplayPrefs.plannedBase || 'all')
const plannedSumBase = plannedBase
const plannedQtyBase = plannedBase

watch(plannedBase, () => {
  if (activeKpi.value && plannedItemsLoaded.value) applyKpiExpansion()
})

// Сохранение настроек отображения дерева ФЭО (см. FEO_DISPLAY_PREFS_KEY/feoDisplayPrefs
// в начале файла) — единая точка на все семь настроек, deep:true нужен, т.к. expandedIds/
// expandedReqItems/expandedItemPanels/expandedPlannedItems/collapsedPlannedItems мутируются
// на месте (push/add/delete), а не переприсваиваются.
function saveFeoDisplayPrefs() {
  try {
    localStorage.setItem(FEO_DISPLAY_PREFS_KEY, JSON.stringify({
      plannedBase: plannedBase.value,
      feoItemsGroupBy: feoItemsGroupBy.value,
      expandedIds: expandedIds.value,
      expandedReqItems: [...expandedReqItems.value],
      expandedItemPanels: [...expandedItemPanels.value],
      expandedPlannedItems: [...expandedPlannedItems.value],
      collapsedPlannedItems: [...collapsedPlannedItems.value],
    } satisfies FeoDisplayPrefs))
  } catch {
    // localStorage недоступен (приватный режим и т.п.) — не критично, просто не персистим
  }
}
watch(
  [plannedBase, feoItemsGroupBy, expandedIds, expandedReqItems, expandedItemPanels, expandedPlannedItems, collapsedPlannedItems],
  saveFeoDisplayPrefs,
  { deep: true },
)

function feoResidualBaseFor(node: FeoNode): number {
  return residualBase.value === 'feo' ? feoEffectiveFor(node) : feoPlannedDisplayFor(node)
}

// Остаток = (Плановая сумма | Финансирование по ФЭО) − В плане-графике.
// Решение владельца 2026-08-18: раньше вычитался feoPurchasedFor (только delivered/paid),
// из-за чего «Остаток» жил на третьей шкале, отдельной от «В плане-графике»/заметки
// «в закупках» — сводим все три числа строки к одной шкале.
function feoResidualFor(node: FeoNode): number {
  return feoResidualBaseFor(node) - feoInPlanScheduleFor(node)
}

// Отображаемое финансирование по ФЭО: ручное значение, для групп без ручного — серый расчёт
function feoDisplayedFor(node: FeoNode): number {
  if (node.budget != null) return Number(node.budget)
  return node.hasChildren ? feoEffectiveFor(node) : 0
}

// Финансирование vs Плановая сумма (в текущем режиме): >0 — можно добавить (зелёная), <0 — надо убрать (красная)
function feoFinDiff(node: FeoNode): number {
  return feoDisplayedFor(node) - feoPlannedDisplayFor(node)
}

// Жалоба владельца 2026-08-17 (категория 3710, «Расходные материалы для проведения
// окружных полуфиналов…»): «можно добавить 208 156 ₽ до финансирования ФЭО» вводит в
// заблуждение — это ФЭО минус ПЛАН (560 000 − 351 844), но в закупках уже 432 162 ₽ (план
// уже превышен закупками), и реально до потолка ФЭО остаётся 560 000 − 432 162 = 127 838 ₽,
// почти вдвое меньше. Вторая строка появляется ТОЛЬКО когда «в закупках» уже больше плана
// (иначе она дублировала бы первую строку той же цифрой, см. feedback_no_duplicate_metrics_
// same_label в Lessons) — берёт consumed из ТОЙ ЖЕ заметки «план · в закупках · свободно»
// (feoResidualNoteFor/feoPlanConsumedNoteFor), что уже нарисована строкой ниже под этим же
// узлом — второй источник чисел не изобретаем.
function feoRemainingWithPurchasesNote(node: FeoNode): string | null {
  // Решение владельца 2026-08-18: при базе «от ФЭО» ровно это число (feoDisplayedFor − consumed)
  // уже стоит в колонке «ОСТАТОК» — не дублируем ту же величину второй строкой под «Плановой суммой».
  if (residualBase.value === 'feo') return null
  if (feoFinDiff(node) <= 0.005) return null
  const note = feoResidualNoteFor(node) || feoPlanConsumedNoteFor(node)
  if (!note || note.residual >= -0.005) return null
  const remaining = feoDisplayedFor(node) - note.consumed
  return `с учётом уже размещённых закупок (${formatCurrency(note.consumed)}) до потолка ФЭО реально остаётся ${formatCurrency(remaining)}`
}

// «Собственный» перерасход узла — ровно то же условие, по которому строка
// "надо убрать N" уже красится ниже в шаблоне (feoDisplayedFor(node) > 0 — лимит вообще задан).
// Без этой проверки feoFinDiff() ложно уходит в минус у любого листа без лимита ФЭО
// (feoDisplayedFor = 0, а плановая сумма положительная — это НЕ перерасход, лимита просто нет).
function feoIsOverBudget(node: FeoNode): boolean {
  return feoDisplayedFor(node) > 0 && feoFinDiff(node) < -0.005
}

// Согласование превышения плана над финансированием ФЭО (задача владельца
// 2026-08-05: «если где-то превысил план ФЭО, значит где-то надо снимать —
// действия заблокированы, пока план закупок не загонять обратно в размеры ФЭО,
// либо согласовать превышение цепочкой»). excess_amount/excess_pending/
// excess_approved приходят готовыми с бэкенда в planTreeByCat (см.
// app.services.feo_plan.compute_feo_plan_tree) — фронт ничего не пересчитывает.
function excessFor(node: FeoNode): { amount: number; pending: boolean; approved: boolean } | null {
  const t = planTreeByCat.value[node.id]
  const amount = Number(t?.excess_amount || 0)
  if (amount <= 0.005) return null
  return { amount, pending: !!t?.excess_pending, approved: !!t?.excess_approved }
}

// «Заметный сигнал превышения» (план zany-fluttering-mountain.md, возвращено из отката
// e0db76a) — виновная закупка, из-за которой узел вышел за финансирование ФЭО. Приходит
// готовой с бэкенда (см. app.services.feo_plan.find_excess_culprit, GET /api/feo-categories/
// plan-tree) — сервер заполняет её ТОЛЬКО пока excess_amount не согласован, поэтому
// дополнительно проверять excessApprovalFor тут не нужно: approved-случай уже отдаёт
// culprit=null сам по себе.
function excessCulpritFor(node: FeoNode): ExcessCulprit | null {
  return planTreeByCat.value[node.id]?.excess_culprit ?? null
}

// Текст виновника — «закупка № РЕЕ-2026-00889 «Great Wall POER» добавила 4 000 000 ₽,
// после неё выбрано 12 000 000 ₽ при ФЭО 8 000 000 ₽», либо без номера закупки, если
// виновник — синтетическое «плановое значение категории» (ручной план листа без
// разбивки на плановые позиции, см. find_excess_culprit).
function excessCulpritText(node: FeoNode): string {
  const c = excessCulpritFor(node)
  if (!c) return ''
  const source = c.purchase_number != null
    ? `закупка № ${c.purchase_number}${c.item_name ? ` «${c.item_name}»` : ''}`
    : (c.item_name || 'плановое значение категории')
  const budget = node.budget != null ? formatCurrency(node.budget) : '—'
  return `из-за чего: ${source} — добавила ${formatCurrency(c.amount_at_crossing)}, после неё выбрано ${formatCurrency(c.cumulative_after)} при ФЭО ${budget}`
}

// Правка владельца (2026-08-12): виновник превышения (excess_culprit) уже виден
// плашкой над деревом, но НЕ на самой строке позиции в панели «план vs факт» —
// найти её среди десятков строк было неочевидно. Сопоставляем по purchase_id +
// item_name (у ExcessCulprit нет purchase_item_id — сервер отдаёт только эти два
// поля, см. find_excess_culprit); ничего не пересчитываем, только сверяем то,
// что уже пришло с бэкенда.
function isExcessCulpritActual(node: FeoNode, actual: FeoActualItem): boolean {
  const c = excessCulpritFor(node)
  if (!c || c.purchase_id == null) return false
  return c.purchase_id === actual.purchase_id && (c.item_name || '') === (actual.item_name || '')
}

function excessCulpritChipTooltip(node: FeoNode): string {
  const c = excessCulpritFor(node)
  if (!c) return ''
  const budget = node.budget != null ? formatCurrency(node.budget) : '—'
  return `Добавила ${formatCurrency(c.amount_at_crossing)} — после неё выбрано ${formatCurrency(c.cumulative_after)} при ФЭО ${budget}`
}

// Задача владельца «план ≠ факт» (сессия 2026-08-06, Шаг 5, п.5): ВТОРОЙ, независимый
// вид превышения — «итог закупки/КП (факт) дороже плана», отличный от excessFor()
// («план дороже финансирования ФЭО»). Оба поля приходят готовыми в той же карте
// planTreeByCat (compute_feo_plan_tree — см. backend/app/services/feo_plan.py) и
// закрываются ОДНИМ и тем же механизмом согласования (POST /plan-excess {feo_category_id}
// сам решает, какое из двух превышений согласовывать — см. request_plan_excess_approval),
// поэтому кнопка и вся инфраструктура approvalFor/pendingNames/decidePlanExcess ниже
// переиспользуются без изменений.
function excessFactFor(node: FeoNode): { amount: number; pending: boolean; approved: boolean } | null {
  const t = planTreeByCat.value[node.id]
  const amount = Number(t?.excess_fact_over_plan || 0)
  if (amount <= 0.005) return null
  return { amount, pending: !!t?.excess_fact_pending, approved: !!t?.excess_fact_approved }
}

// Замечание владельца п.2 (2026-08-12, сессия «план ≠ факт», продолжение): ТРЕТИЙ,
// независимый вид превышения — Σ всех активных плановых позиций категории больше
// вручную заданного плана (excess_plan_over_manual/manual_plan_entered/excess_plan_items
// приходят готовыми в planTreeByCat, см. app.services.feo_plan.compute_feo_plan_tree).
// Тот же механизм согласования (POST /plan-excess сам выбирает, какое из трёх
// превышений согласовывать по приоритету — см. requestPlanExcessApproval выше,
// backend app.routers.plan_excess.request_plan_excess_approval), поэтому вся
// инфраструктура excessApprovalFor/excessPendingNames/excessMyPendingStep/
// decidePlanExcess переиспользуется без изменений.
function excessPlanFor(node: FeoNode): { amount: number; pending: boolean; approved: boolean; manualEntered: number; items: ExcessPlanItem[] } | null {
  const t = planTreeByCat.value[node.id]
  const amount = Number(t?.excess_plan_over_manual || 0)
  if (amount <= 0.005) return null
  return {
    amount,
    pending: !!t?.excess_plan_pending,
    approved: !!t?.excess_plan_approved,
    manualEntered: Number(t?.manual_plan_entered || 0),
    items: t?.excess_plan_items || [],
  }
}

// Клик по чипу «позиция-виновник» (план zany-fluttering-mountain.md, п.2): одна связанная
// закупка → сразу открыть её (тот же приём router.push, что и у excessCulpritFor/
// virtCart выше — ничего нового не изобретаем); несколько — открывается v-menu со
// списком прямо в шаблоне (см. .feo-excess-plan-item-chip), сюда доходит только
// однозначный случай.
function excessPlanItemPurchaseTitle(p: ExcessPlanItemPurchase): string {
  const num = p.registry_number || (p.purchase_number != null ? `№ ${p.purchase_number}` : `#${p.id}`)
  const status = p.status_label || p.status || '—'
  return `${num} · ${status} · ${formatCurrency(p.amount)}`
}

// Замечание владельца п.4: «если согласовали превышение — так и остаётся, надо чтобы
// висело предупреждение, что согласовали» — спокойная ПОСТОЯННАЯ пометка, читает
// excess_approval_amount/at/by_name (данные ПОСЛЕДНЕГО approved-запроса по категории,
// см. compute_feo_plan_tree) НЕЗАВИСИМО от того, есть ли активное превышение прямо
// сейчас (excessPlanFor может уже вернуть null, если план снова уложился в ручной,
// пометка о прошлом согласовании всё равно должна остаться видна).
function excessPlanApprovalPermanent(node: FeoNode): { amount: number; at: string; by: string; planBefore: number | null; planAfter: number | null } | null {
  const t = planTreeByCat.value[node.id]
  if (t?.excess_approval_amount == null) return null
  return {
    amount: Number(t.excess_approval_amount),
    at: t.excess_approval_at ? new Date(t.excess_approval_at).toLocaleDateString('ru-RU') : '',
    by: t.excess_approval_by_name || '—',
    // План zany-fluttering-mountain.md, п.3: снимок «план был X → стал Y» на момент
    // согласования (plan_excess_approvals.plan_before/plan_after) — может быть null у
    // старых запросов, созданных до миграции; тогда фронт просто не показывает стрелку.
    planBefore: t.excess_approval_plan_before != null ? Number(t.excess_approval_plan_before) : null,
    planAfter: t.excess_approval_plan_after != null ? Number(t.excess_approval_plan_after) : null,
  }
}

// Детали запроса согласования превышения по узлу — см. planExcessApprovals/loadPlanExcessApprovals.
function excessApprovalFor(node: FeoNode): PlanExcessApprovalDto | null {
  return planExcessApprovals.value[node.id] || null
}

// ФИО, у кого сейчас на согласовании: sequential — первый pending-шаг по order_num,
// parallel — все pending-шаги сразу (см. backend _notify_pending_plan_excess_approvers,
// та же логика различия sequential/parallel).
function excessPendingNames(node: FeoNode): string {
  const appr = excessApprovalFor(node)
  if (!appr || appr.status !== 'pending') return ''
  const sorted = [...appr.steps].sort((a, b) => a.order_num - b.order_num)
  const pendingSteps = appr.mode === 'parallel'
    ? sorted.filter(s => s.status === 'pending')
    : sorted.filter(s => s.status === 'pending').slice(0, 1)
  return pendingSteps.map(s => s.full_name || s.role_name || `пользователь #${s.user_id}`).join(', ')
}

// Шаг, который может решить ИМЕННО текущий пользователь: назначенный согласующий
// текущего шага, либо любая SaaS-роль (см. backend decide_plan_excess_step: !_is_saas
// и role not in MANAGER_ROLES блокируют чужой шаг, иначе — можно).
function excessMyPendingStep(node: FeoNode): PlanExcessStep | null {
  const appr = excessApprovalFor(node)
  if (!appr || appr.status !== 'pending') return null
  const sorted = [...appr.steps].sort((a, b) => a.order_num - b.order_num)
  if (appr.mode === 'parallel') {
    return sorted.find(s => s.status === 'pending' && (s.user_id === currentUserId || isSaas.value)) || null
  }
  const first = sorted.find(s => s.status === 'pending')
  if (first && (first.user_id === currentUserId || isSaas.value)) return first
  return null
}

// Кто согласовал (последний решённый шаг approved) — для бейджа «превышение согласовано».
function excessResolvedByName(node: FeoNode): string {
  const appr = excessApprovalFor(node)
  if (!appr) return ''
  const decided = [...appr.steps]
    .filter(s => s.status === 'approved' && s.decided_at)
    .sort((a, b) => new Date(b.decided_at!).getTime() - new Date(a.decided_at!).getTime())
  return decided[0]?.full_name || decided[0]?.role_name || '—'
}

function excessResolvedDate(node: FeoNode): string {
  const appr = excessApprovalFor(node)
  if (!appr?.resolved_at) return ''
  return new Date(appr.resolved_at).toLocaleDateString('ru-RU')
}

// Загрузка запросов согласования превышения плана ФЭО по субсидии — GET /api/plan-excess.
// Список уже отсортирован бэкендом по created_at desc, поэтому первое вхождение
// на категорию — последний (актуальный) запрос.
async function loadPlanExcessApprovals(subsidyId: number) {
  try {
    const rows = await apiFetch<PlanExcessApprovalDto[]>(`/plan-excess?subsidy_id=${subsidyId}`)
    const map: Record<number, PlanExcessApprovalDto> = {}
    for (const r of rows) {
      if (!(r.feo_category_id in map)) map[r.feo_category_id] = r
    }
    planExcessApprovals.value = map
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.message || 'Не удалось загрузить согласования превышения плана', 'error')
  }
}

async function requestPlanExcessApproval(node: FeoNode) {
  excessRequestLoading.value = node.id
  try {
    const res = await apiFetch<PlanExcessApprovalDto>('/plan-excess', {
      method: 'POST',
      body: JSON.stringify({ feo_category_id: node.id }),
    })
    if (res.self_approval && res.warning) {
      showSnack(res.warning, 'warning')
    } else if (res.warning) {
      showSnack(`Запрос отправлен. ${res.warning}`, 'warning')
    } else {
      showSnack('Запрос на согласование превышения плана отправлен', 'success')
    }
    if (selectedId.value) await refreshReqData()
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.message || 'Не удалось запросить согласование превышения', 'error')
  } finally {
    excessRequestLoading.value = null
  }
}

function openExcessRejectDialog(node: FeoNode) {
  excessRejectDialog.value = { show: true, node, comment: '' }
}

async function decidePlanExcess(node: FeoNode, decision: 'approved' | 'rejected', comment?: string) {
  const appr = excessApprovalFor(node)
  const step = excessMyPendingStep(node)
  if (!appr || !step) {
    showSnack('Шаг согласования не найден — обновите страницу', 'error')
    return
  }
  excessDecideLoading.value = node.id
  try {
    await apiFetch(`/plan-excess/${appr.id}/decide`, {
      method: 'POST',
      body: JSON.stringify({ decision, step_id: step.id, comment: comment || null }),
    })
    showSnack(decision === 'approved' ? 'Превышение согласовано' : 'Превышение отклонено', decision === 'approved' ? 'success' : 'warning')
    if (selectedId.value) await refreshReqData()
    refreshMyPendingApprovals()  // бейдж «мои согласования» в сайдбаре
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.message || 'Не удалось сохранить решение', 'error')
  } finally {
    excessDecideLoading.value = null
  }
}

async function submitExcessReject() {
  const node = excessRejectDialog.value.node
  if (!node) return
  if (!excessRejectDialog.value.comment.trim()) {
    showSnack('Укажите причину отклонения', 'error')
    return
  }
  await decidePlanExcess(node, 'rejected', excessRejectDialog.value.comment.trim())
  excessRejectDialog.value.show = false
}

// Для каждого узла — потомки (любой глубины), у которых feoIsOverBudget === true.
// Мемоизировано Map'ом за один обход дерева, а не пересчитывается в шаблоне на каждый узел —
// дерево ФЭО большое, feoNodeClass/рендер строки вызываются в цикле по всем видимым узлам.
interface FeoOverspentInfo { names: string[]; count: number }
const feoOverspentDescendantMap = computed<Map<number, FeoOverspentInfo>>(() => {
  const map = new Map<number, FeoOverspentInfo>()
  function walk(node: FeoNode): string[] {
    let names: string[] = []
    for (const child of node.children) {
      if (feoIsOverBudget(child)) names.push(child.name)
      names = names.concat(walk(child))
    }
    map.set(node.id, { names, count: names.length })
    return names
  }
  for (const root of feoTree.value) walk(root)
  return map
})

// Есть ли хотя бы один потомок (на любой глубине), превышающий СВОЙ лимит ФЭО
function feoHasOverspentDescendant(node: FeoNode): boolean {
  return (feoOverspentDescendantMap.value.get(node.id)?.count ?? 0) > 0
}

// Текст комментария у родителя: если превышающая подкатегория одна — называем её,
// иначе общая формулировка (по требованию пользователя)
function feoOverspentDescendantText(node: FeoNode): string {
  const info = feoOverspentDescendantMap.value.get(node.id)
  if (!info || info.count === 0) return ''
  if (info.count === 1) return `подкатегория «${info.names[0]}» превышает лимит`
  return 'одна из подкатегорий превышает лимит'
}

// Тултип: до трёх имён превышающих подкатегорий + «и ещё N», чтобы было видно, куда идти
function feoOverspentDescendantTitle(node: FeoNode): string {
  const info = feoOverspentDescendantMap.value.get(node.id)
  if (!info || info.count === 0) return ''
  const shown = info.names.slice(0, 3)
  const suffix = info.count > 3 ? ` и ещё ${info.count - 3}` : ''
  const verb = info.count === 1 ? 'Превышает' : 'Превышают'
  return `${verb} лимит ФЭО: ${shown.join(', ')}${suffix}`
}

// Ручное ФЭО дочерних vs собственная ручная сумма узла (без подмены фактом/планом)
function feoChildrenBudgetDiff(node: FeoNode): number {
  if (!node.hasChildren || node.budget == null || node.budget <= 0) return 0
  if (!hasManualChildFeo(node)) return 0
  return manualChildFeoSum(node) - node.budget
}

// Факт по требованию владельца (2026-08-05): появляется с «Заказано» (по договору, актом ещё
// не подтверждено — см. fact_confirmed), уточняется закрывающими документами при «Поставлено»/
// «Оплачено». До «Заказано» это ещё ПЛАН, а не факт.
// Задача владельца «план ≠ факт» (сессия 2026-08-06, Шаг 3/5): порог опущен с «Заказано» до
// «Ведётся работа» (см. FACT_PRICED_STATUSES в backend/app/services/feo_plan.py) — факт (цена
// по итогам КП/торгов) должен попадать в панель «план vs факт» ещё ДО подписания договора,
// иначе позиция в статусе «Ведётся работа»/«Договор» с уже известным fact_amount ошибочно
// показывала текущую (замороженную ТЗ) сумму вместо факта — панель и дерево ФЭО расходились.
// isFactActual/FACT_STATUSES остаются нужны для ИТОГО/факт-колонок и для guard'а «Разница»
// (нужен именно подтверждённый факт); для вложения строк ПОД плановой позицией с 2026-08-11
// используется расширенный allActualFor/factForPlanned — см. ниже.
const FACT_STATUSES = ['work_in_progress', 'contracted', 'ordered', 'delivered', 'paid']
function isFactActual(a: { purchase_status?: string | null }): boolean {
  return FACT_STATUSES.includes(a.purchase_status || '')
}

// Позиция «из заявки» в плановой стадии (до договора): источник истины — заявка,
// поэтому название/кол-во/цену тут править нельзя (бэкенд отдаёт 409). Прячем карандаш/удаление.
const WISH_PLAN_LOCKED_STATUSES = ['wishes', 'plan_schedule', 'work_in_progress']
function isWishLocked(it: { wish_id?: number | null; purchase_status?: string | null }): boolean {
  return !!it.wish_id && WISH_PLAN_LOCKED_STATUSES.includes(it.purchase_status || '')
}

function actualFactFor(catId: number) {
  return (comparisonData.value[catId]?.actual || []).filter(a => isFactActual(a))
}

// Все позиции закупок категории, ЛЮБОЙ стадии (включая «План закупок» — по нашей модели это
// уже начало жизни позиции, не отдельная параллельная сущность). Правка владельца 2026-08-11
// («пикап» Great Wall POER на стадии «План закупок» рисовался ОТДЕЛЬНОЙ строкой рядом с планом
// вместо вложения под неё, ИТОГО складывал план с закупкой) — единственный источник вложенных
// строк под плановой позицией теперь этот, а не actualFactFor (тот остаётся только для
// ИТОГО/факт-колонок, где нужен именно подтверждённый факт, см. comparisonFactTotal).
function allActualFor(catId: number) {
  return comparisonData.value[catId]?.actual || []
}

// Фолбэк владельца (2026-08-12): «плановая позиция была создана из заявки — названия сейчас
// совпадают, значит должны разворачиваться в план БЕЗ факта». У части плановых позиций
// (проверено в БД, категория 3710) ни одна позиция закупки не получила feo_planned_item_id —
// привязка не проставлена (ручной ввод/миграция пропустили её), хотя закупка с тем же
// названием реально существует в той же категории. Считаем ОДИН РАЗ на всю категорию (не в
// factForPlanned/unplannedActualFor по отдельности!) — единый источник для обеих функций
// ниже, иначе одна и та же позиция закупки задвоится: попадёт и под план (по имени), и в
// «Не привязаны к плану» (по !feo_planned_item_id). Жадный «первое совпадение выигрывает»
// (usedIds) — на случай двух плановых позиций с одинаковым именем в одной категории, чтобы
// одна непривязанная позиция не досталась сразу обеим. Плановые позиции, у которых УЖЕ есть
// хоть одна привязанная (bound) позиция, в фолбэке не участвуют — там factForPlanned и так
// находит факт напрямую.
const fallbackAbsorbedByCategory = computed((): Record<number, Map<number, number>> => {
  const result: Record<number, Map<number, number>> = {}
  for (const key of Object.keys(comparisonData.value)) {
    const catId = Number(key)
    const data = comparisonData.value[catId]
    const map = new Map<number, number>()
    const usedIds = new Set<number>()
    for (const planned of data.planned || []) {
      const hasBound = (data.actual || []).some(a => a.feo_planned_item_id === planned.id)
      if (hasBound) continue
      const targetName = normName(planned.name)
      if (!targetName) continue
      for (const a of data.actual || []) {
        if (a.feo_planned_item_id) continue
        if (usedIds.has(a.purchase_item_id)) continue
        if (normName(a.item_name) !== targetName) continue
        map.set(a.purchase_item_id, planned.id)
        usedIds.add(a.purchase_item_id)
      }
    }
    result[catId] = map
  }
  return result
})

// plannedId < 0 — синтетическая «ручная плановая позиция» (см. displayPlannedRowsFor):
// когда у категории нет ни одной реальной FeoPlannedItem, а план задан прямо на листе
// (node.planned_quantity/planned_amount), лист получает ОДНУ псевдо-строку с id = -node.id,
// и её «факт» — это ВСЕ позиции категории без привязки к плановой (им и привязываться не к
// чему — детального деления в ФЭО не было). ШАГ 1 плана дедупликации дерева ФЭО (2026-08-07):
// раньше эти же позиции рисовались ВТОРОЙ раз через matchedReqFor (сопоставление по ИМЕНИ) —
// убрано целиком, единственный источник теперь этот. С 2026-08-11 — allActualFor (любая
// стадия), а не actualFactFor: закупка на стадии «План закупок» тоже обязана лечь ПОД свою
// плановую строку, а не рисоваться рядом отдельным блоком (см. снесённый actualPlanStageFor).
// С 2026-08-12 (plannedId >= 0) — если привязанных позиций нет вовсе, фолбэк на
// fallbackAbsorbedByCategory (см. выше, комментарий там).
function factForPlanned(catId: number, plannedId: number) {
  if (plannedId < 0) return allActualFor(catId).filter(a => !a.feo_planned_item_id)
  const bound = allActualFor(catId).filter(a => a.feo_planned_item_id === plannedId)
  if (bound.length) return bound
  const absorbed = fallbackAbsorbedByCategory.value[catId]
  if (!absorbed) return bound
  return allActualFor(catId).filter(a => absorbed.get(a.purchase_item_id) === plannedId)
}

function factForPlannedTotal(catId: number, plannedId: number): number {
  // fact_amount — реальный факт (ContractItem/contract_price); total_price (ТЗ) —
  // фолбэк только пока факта ещё нет (см. calcDiff::amountOf — тот же приоритет).
  return factForPlanned(catId, plannedId).reduce((s, a) => s + Number(a.fact_amount ?? a.total_price ?? 0), 0)
}

// Расшифровка «больше плана на X» у заметки «план … · в закупках … · больше плана на …»
// (жалоба владельца 2026-08-13: «в закупках 118 365,60 — больше плана на 5 121,60, откуда,
// если в позициях плана этого нет?»; продолжение — 2026-08-17, категория 3710: «где это
// превышение 80 318? где оно?»). Это заметка feoResidualNoteFor ниже по шаблону (строка
// «план X · в закупках Y · больше плана на Z»), НЕ плашка у «Фактической суммы» (та про
// контрактный факт, отдельная и обычно ещё пустая, пока закупка не дошла до договора/
// поставки — «в закупках» здесь про заявки/ТЗ).
//
// Превышение складывается из ДВУХ независимых источников — расследование 2026-08-17
// показало, что раньше учитывался только первый, из-за чего у категории 3710 расшифровка
// молчала (пусто), хотя число «больше плана на 80 318» было честным:
//  1) перерасход ВНУТРИ существующей плановой позиции — сумма закупок, привязанных к ней
//     (factForPlanned), больше её planned.amount. Арифметика — та же, что у
//     planBreakdownText (factForPlannedTotal − planned.amount), берём только положительные.
//  2) позиции закупок БЕЗ действующей плановой позиции — unplannedActualFor(node) (и вовсе
//     непривязанные, и с мёртвой привязкой на удалённую плановую позицию, см. её правку
//     выше) — такая позиция ничей план не убавляет, целиком уходит в превышение категории
//     (пример владельца: огнетушитель 54 318 ₽ + каска 26 000 ₽ = ровно 80 318 ₽, обе с
//     feo_planned_item_id на уже удалённые плановые позиции 809/1409).
// Каждый пункт несёт список закупок-источников (обычно один, но плановая позиция может
// быть покрыта несколькими закупками сразу) — шаблон рисует по ним кликабельные ссылки/меню
// (тот же приём, что excessPlanFor().items выше по файлу — v-menu при >1 закупке).
//
// ⚠️ comparisonData[node.id] грузится ТОЛЬКО когда панель плановых позиций категории
// раскрыта, либо когда явно нажали «Показать, из-за чего» (см. ensureComparison в шаблоне) —
// читаем здесь готовое значение ref'а, ничего сами не запрашиваем.
interface ExcessReasonPurchase { id: number; label: string; amount: number; stopped: boolean }
interface ExcessReasonItem { key: string; name: string; amount: number; purchases: ExcessReasonPurchase[] }
function purchaseLabelFor(a: { registry_number?: string | null; purchase_number?: number | null; purchase_id: number }): string {
  return a.registry_number || (a.purchase_number != null ? `№ ${a.purchase_number}` : `#${a.purchase_id}`)
}
function factExcessReasonItems(node: FeoNode): ExcessReasonItem[] {
  const catId = node.id
  const data = comparisonData.value[catId]
  if (!data) return []
  const items: ExcessReasonItem[] = []
  // Источник 1 — перерасход внутри существующих плановых позиций.
  for (const p of data.planned || []) {
    const amount = factForPlannedTotal(catId, p.id) - Number(p.amount ?? 0)
    if (amount <= 0.005) continue
    const facts = factForPlanned(catId, p.id)
    items.push({
      key: `p-${p.id}`,
      name: p.name,
      amount,
      purchases: facts.map(a => ({
        id: a.purchase_id,
        label: purchaseLabelFor(a),
        amount: Number(a.fact_amount ?? a.total_price ?? 0),
        stopped: !!a.stopped_at,
      })),
    })
  }
  // Источник 2 — закупки без действующей плановой позиции (непривязанные ИЛИ с мёртвой
  // привязкой на удалённую плановую позицию) — unplannedActualFor уже ловит оба случая.
  for (const a of unplannedActualFor(node)) {
    const amount = Number(a.fact_amount ?? a.total_price ?? 0)
    if (amount <= 0.005) continue
    items.push({
      key: `a-${a.purchase_item_id}`,
      name: a.item_name,
      amount,
      purchases: [{ id: a.purchase_id, label: purchaseLabelFor(a), amount, stopped: !!a.stopped_at }],
    })
  }
  return items.sort((a, b) => b.amount - a.amount)
}
// Расшифровка обязана сходиться с самим числом превышения (требование владельца
// 2026-08-17: «если не сходится — показывай остаток строкой, а не молчи»). Расхождение
// возможно: источник 1 берёт только плановые позиции, которые САМИ перерасходованы —
// недобор по другим плановым позициям категории эту сумму не компенсирует здесь, хотя
// компенсирует итоговый residual категории (там план минус ВЕСЬ consumed целиком).
function factExcessReasonRemainder(node: FeoNode): number {
  const note = feoResidualNoteFor(node)
  if (!note) return 0
  const total = -note.residual
  const shown = factExcessReasonItems(node).reduce((s, it) => s + it.amount, 0)
  return total - shown
}

// ── Левая группа колонок панели «план vs факт»: ДВА состояния, не «план» ──────
// Правка владельца (2026-08-09): левая группа у строк ФАКТА — это НЕ план (план —
// только строка самой плановой позиции, помечена чипом «план»). До заключения
// договора показываем, как товар завели в заявке/ТЗ (stage 'purchase' в
// _build_item_stages, backend/app/routers/feo_planned_items.py — снимок
// PurchaseItem.item_name/quantity/unit_price/total_price); как только появилась
// договорная позиция — номенклатуру, количество и цену подрядчика (stage
// 'contract' — ContractItem). Источник — уже загруженный actual.stages, второй
// запрос/расчёт не делает. Фолбэк на actual.* — на случай отсутствия stages
// (защитный код: 'purchase' стадия в _build_item_stages есть всегда, но панель
// не должна показывать пустые клетки, если что-то разошлось).
interface FeoLeftGroupInfo {
  name: string
  quantity: number | null
  unit: string | null
  unitPrice: number | null
  total: number | null
  isContract: boolean
}
function leftGroupInfo(actual: FeoActualItem): FeoLeftGroupInfo {
  const stages = actual.stages || []
  const contract = stages.find(s => s.key === 'contract')
  const purchase = stages.find(s => s.key === 'purchase')
  const chosen = contract || purchase
  if (chosen) {
    return {
      name: chosen.name || '',
      quantity: chosen.quantity,
      unit: chosen.unit,
      unitPrice: chosen.unit_price,
      total: chosen.total,
      isContract: !!contract,
    }
  }
  return {
    name: actual.item_name,
    quantity: actual.quantity,
    unit: actual.unit,
    unitPrice: actual.unit_price,
    total: actual.total_price,
    isContract: false,
  }
}

// ── Шапка вложенной таблицы закупок плановой позиции — ровно одна стадия ──────
// Требование владельца (2026-08-09), дословно: «если ещё на стадии закупки, то просто
// "как выставили в закупку", не надо туда дополнять "как в договоре"; когда переместится
// на стадию договора, то тогда эта надпись меняется на "как в договоре", не нужно
// дополнять непонятными сущностями». Все закупки этой плановой позиции на одной стадии →
// шапка называет ровно её; стадии разные → нейтральное «Позиция закупки», стадия —
// на каждой строке (чип уже есть).
//
// Правка владельца (2026-08-12, разбор задвоения плановой позиции без факта): раньше
// шапка различала только 2 состояния (leftGroupInfo.isContract), из-за чего заявка
// (wishes/plan_schedule) и «Ведётся работа» получали одну и ту же надпись «Как выставили
// в закупку». Дословно от владельца: «плановая позиция была создана из заявки, названия
// сейчас совпадают [→ "Как называется в заявке"]. Перейдёт в работу — статус сменится
// "как называется в закупке" [work_in_progress], далее в договоре [contracted/ordered/
// delivered/paid → "Как в договоре"]». PURCHASE_STATUS_META — единственный источник
// статусов (constants/purchaseStatus.ts), см. импорт в начале файла.
function stageHeaderLabelFor(status: string | null | undefined): string {
  if (status === 'wishes' || status === 'plan_schedule') return 'Как называется в заявке'
  if (status === 'work_in_progress') return 'Как называется в закупке'
  if (status === 'contracted' || status === 'ordered' || status === 'delivered' || status === 'paid') return 'Как в договоре'
  return 'Позиция закупки'
}
// Краткий вариант stageHeaderLabelFor для чипа НА СТРОКЕ (не в шапке колонки).
// Баг владельца (2026-08-13): у «Бинт марлевый Навтекс» в статусе «План закупок»
// чип писал «как выставили», хотя ничего ещё не выставлено в закупку — это
// название из заявки. Чип раньше жил на своей отдельной двоичной логике
// (leftGroupInfo.isContract ? 'как в договоре' : 'как выставили'), не совпадающей
// со стадийной функцией шапки. Переиспользуем stageHeaderLabelFor, никакой новой
// логики стадий не изобретаем.
function stageChipLabelFor(status: string | null | undefined): string {
  const full = stageHeaderLabelFor(status)
  if (full === 'Как называется в заявке') return 'как в заявке'
  if (full === 'Как называется в закупке') return 'как в закупке'
  if (full === 'Как в договоре') return 'как в договоре'
  return 'как выставили'
}
// Хвост той же правки (2026-08-13): :title и :color рядом с чипом остались на старой
// двоичной логике (leftGroupInfo.isContract) — у позиции «Ведётся работа» чип уже писал
// «как в закупке» (stageChipLabelFor выше), а подсказка при наведении всё ещё говорила
// про заявку/ТЗ. Считаем обе от той же стадии (actual.purchase_status), что и текст чипа.
function stageChipTitleFor(status: string | null | undefined): string {
  if (status === 'wishes' || status === 'plan_schedule') return 'Наименование, количество и цена — как их завели в заявке; в закупку ещё не выставлено'
  if (status === 'work_in_progress') return 'Наименование, количество и цена — как выставлено в закупке'
  if (status === 'contracted' || status === 'ordered' || status === 'delivered' || status === 'paid') return 'Наименование, количество и цена — из договора с подрядчиком'
  return 'Как товар завели в заявке/ТЗ — до заключения договора'
}
function stageChipColorFor(status: string | null | undefined): string {
  return (status === 'contracted' || status === 'ordered' || status === 'delivered' || status === 'paid') ? 'indigo' : 'blue-grey'
}
function factStageHeaderFor(catId: number, plannedId: number): string {
  const facts = factForPlanned(catId, plannedId)
  if (!facts.length) return 'Позиция закупки'
  const labels = new Set(facts.map(a => stageHeaderLabelFor(a.purchase_status)))
  if (labels.size > 1) return 'Позиция закупки'
  return [...labels][0]
}

// ── Разбор плана на строке плановой позиции («сколько уже разобрано») ─────────
// Требование владельца (2026-08-09): под одной плановой позицией может висеть НЕСКОЛЬКО
// закупок («покупаю по одной машине в каждой закупке») — на строке плана нужно видеть,
// сколько уже взято и сколько осталось, И в штуках, И в деньгах. Деньги считаются той же
// формулой, что и factForPlannedTotal (fact_amount, фолбэк total_price) — второй источник
// приоритета не изобретаем. Штуки — Σ actual.quantity (реальное количество позиции закупки,
// та же колонка «Кол-во (факт)» вложенной таблицы) против planned.quantity; если у плана
// количество не задано — про штуки не пишем вообще (у плана тогда нет множителя количества).
// Правка владельца (2026-08-11): facts (factForPlanned) теперь включает ЛЮБУЮ стадию закупки,
// в т.ч. «План закупок» — слово «закуплено» для неё враньё (ничего ещё не куплено, только
// выставлено в закупку). Нейтральное «в закупках» верно для всех стадий одинаково.
function planBreakdownText(catId: number, planned: FeoPlannedItem & { isManual?: boolean }): string {
  const facts = factForPlanned(catId, planned.id)
  const amountTotal = Number(planned.amount ?? 0)
  const amountTaken = factForPlannedTotal(catId, planned.id)
  const amountRemaining = amountTotal - amountTaken
  const unit = planned.unit || 'шт'
  if (planned.quantity != null) {
    const qtyTotal = Math.round(Number(planned.quantity) * 10000) / 10000
    const qtyTaken = Math.round(facts.reduce((s, a) => s + Number(a.quantity ?? 0), 0) * 10000) / 10000
    const qtyRemaining = Math.round((qtyTotal - qtyTaken) * 10000) / 10000
    return `в закупках ${qtyTaken} из ${qtyTotal} ${unit} · на ${formatCurrency(amountTaken)} из ${formatCurrency(amountTotal)} · остаток ${qtyRemaining} ${unit} и ${formatCurrency(amountRemaining)}`
  }
  return `в закупках на ${formatCurrency(amountTaken)} из ${formatCurrency(amountTotal)} · остаток ${formatCurrency(amountRemaining)}`
}

// Строки «Плановые позиции» листа для панели «план vs факт»: реальные FeoPlannedItem
// категории, ИЛИ — если их нет, а план задан прямо на листе — одна псевдо-строка
// «ручной план ФЭО» (id = -node.id, отрицательный, никогда не совпадает с реальным id).
// Переиспользует вёрстку обычной плановой строки (см. таблицу ниже) вместо отдельного блока.
//
// ⚠️ Семантика поля `amount` РАЗНАЯ у двух источников и это специально не унифицировано
// в БД (баг с проды 2026-08-07): `FeoPlannedItem.amount` (реальная плановая позиция,
// приходит от бэкенда как есть) — это уже ИТОГОВАЯ СУММА строки. А `FeoCategory.planned_amount`
// (ручной план на листе, поля «Плановое кол-во»/«Финансирование по ФЭО» в дереве) — это ЦЕНА
// ЗА ЕДИНИЦУ (см. feoPlannedTotalFor/feoAmtFor выше, которые считают qty × planned_amount).
// Вся остальная вёрстка панели (строки 1057/1060/1069-1070 ниже, calcDiff, comparisonPlanTotal)
// трактует `planned.amount` как СУММУ — поэтому здесь для синтетической строки amount ОБЯЗАН
// быть посчитан как planned_quantity × planned_amount, а не взят «как есть» из planned_amount
// (иначе «Сумма (план)» делится на количество ещё раз при выводе цены за единицу).
function displayPlannedRowsFor(node: FeoNode): (FeoPlannedItem & { isManual?: boolean })[] {
  const real = comparisonData.value[node.id]?.planned || []
  if (real.length) return real
  if (node.planned_quantity == null && node.planned_amount == null) return []
  const qty = node.planned_quantity != null ? Number(node.planned_quantity) : null
  const unitPrice = node.planned_amount != null ? Number(node.planned_amount) : null
  // И количество, И цена ОБЯЗАНЫ быть заданы и положительны, чтобы сумму вообще можно
  // было посчитать — иначе null (неизвестно), а не «додумывать» недостающий множитель
  // за 1. Проверено на приёмке 2026-08-07: значение «количество не задано → считать 1»
  // ЗАВОДИТ РАСХОЖДЕНИЕ с «Плановой суммой» шапки дерева (feoPlannedTotalFor на фронте
  // и plan_manual в backend/app/services/feo_plan.py::_visit — оба явно требуют
  // `qty > 0 and amt > 0`, иначе план листа = 0/«не задано»). Панель обязана
  // ЗЕРКАЛИТЬ эту же формулу, а не изобретать свою — их расхождение и есть баг.
  const amount = (qty != null && qty > 0 && unitPrice != null && unitPrice > 0) ? qty * unitPrice : null
  return [{
    id: -node.id,
    feo_category_id: node.id,
    name: node.name,
    quantity: qty,
    unit: node.unit || null,
    amount,
    notes: null,
    is_active: true,
    isManual: true,
  }]
}

// «Не привязаны к плану — требуется действие»: позиции категории (ЛЮБОЙ стадии закупки —
// правка 2026-08-11, было actualFactFor/FACT_STATUSES, см. allActualFor) без
// feo_planned_item_id. НЕ показываются только в одном случае — когда те же самые позиции
// уже отрисованы как факт синтетической строки «ручной план ФЭО» (displayPlannedRowsFor
// возвращает псевдо-строку id=-node.id именно тогда, когда реальных плановых позиций нет,
// а план на листе задан вручную — см. factForPlanned(catId, -node.id) выше). Если у листа
// НЕТ ни реальных плановых позиций, ни ручного плана — абсорбировать эти позиции некуда,
// они обязаны показаться здесь как «требует действия» (иначе позиции пропадают из дерева
// молча — так и было до фикса: 15+ позиций категории без плана исчезали совсем).
// С 2026-08-12 — дополнительно исключены позиции, поглощённые фолбэком по имени
// (fallbackAbsorbedByCategory, см. factForPlanned) — те уже показаны ПОД своей плановой
// строкой, повторно рисовать их тут значило бы задвоить одну и ту же закупку на экране.
//
// БАГ (жалоба владельца 2026-08-17, категория 3710 «Расходные материалы для проведения
// окружных полуфиналов…»): «где превышение 80 318? где его увидеть?» — две позиции закупок
// (огнетушитель 54 318 ₽, каска 26 000 ₽) имели feo_planned_item_id, указывающий на
// плановые позиции, которые к этому моменту УДАЛЕНЫ (id 809/1409 больше нет среди
// comparisonData[catId].planned). Из-за этого они проваливались МИМО обеих веток: у
// factForPlanned нет плановой строки с таким id, чтобы их подставить, а этот фильтр
// (`!a.feo_planned_item_id`) их тоже отбрасывал — feo_planned_item_id формально заполнен,
// просто ссылка мертва. Позиции исчезали с экрана совсем — не факт, не план, ничего.
// Теперь ловим ОБА случая: (1) привязки вовсе нет — прежнее поведение; (2) привязка ЕСТЬ,
// но указанной плановой позиции больше не существует в текущем списке категории — «мёртвая»
// привязка. Мёртвая привязка показывается ВСЕГДА (даже при hasManualPseudoRow — абсорбировать
// в синтетическую строку её всё равно нельзя, там участвуют только позиции без
// feo_planned_item_id вовсе, см. factForPlanned(catId, -node.id)). Различение — isOrphanedActual
// ниже, шаблон рисует по нему отдельную пометку «привязана к удалённой плановой позиции».
function unplannedActualFor(node: FeoNode) {
  const catId = node.id
  const hasManualPseudoRow = !(comparisonData.value[catId]?.planned || []).length
    && (node.planned_quantity != null || node.planned_amount != null)
  const absorbed = fallbackAbsorbedByCategory.value[catId]
  const plannedIds = new Set((comparisonData.value[catId]?.planned || []).map(p => p.id))
  return allActualFor(catId).filter(a => {
    if (a.feo_planned_item_id != null) {
      // Мёртвая привязка — не зависит от hasManualPseudoRow/fallback, показываем всегда.
      return !plannedIds.has(a.feo_planned_item_id)
    }
    if (hasManualPseudoRow) return false
    return !(absorbed && absorbed.has(a.purchase_item_id))
  })
}

// Различает две причины попадания в «Не привязаны к плану»: мёртвая привязка (позиция
// формально привязана к feo_planned_item_id, но та плановая позиция удалена) vs позиция
// вообще никогда не была привязана. Внутри unplannedActualFor(node) — единственный
// источник истины, что считается «мёртвым», эта функция ничего не решает заново.
function isOrphanedActual(actual: FeoActualItem): boolean {
  return actual.feo_planned_item_id != null
}

// Dev-ассерт (ШАГ 1 плана дедупликации, 2026-08-07; расширен 2026-08-11 после удаления
// блока «Плановые из закупок»): панель «план vs факт» листа обязана показывать каждую
// PurchaseItem категории РОВНО один раз — либо под своей плановой позицией/синтетической
// строкой (factForPlanned, любая стадия), либо в «Не привязаны» (unplannedActualFor).
// Группы по построению не пересекаются (feo_planned_item_id делит позиции на
// привязанные/непривязанные, hasManualPseudoRow решает, кто абсорбирует непривязанные) —
// если дубль или пропажа всё же появились, это регресс, обязан быть виден в консоли сразу,
// а не найден на проде (см. feedback_no_false_absence_claims в Lessons — позиции не должны
// пропадать молча).
function devCheckNoDuplicateItems(catId: number) {
  if (!import.meta.env.DEV) return
  const node = flattenAll(feoTree.value).find(n => n.id === catId)
  if (!node || node.hasChildren) return
  const ids: number[] = []
  for (const planned of displayPlannedRowsFor(node)) {
    for (const a of factForPlanned(catId, planned.id)) ids.push(a.purchase_item_id)
  }
  for (const a of unplannedActualFor(node)) ids.push(a.purchase_item_id)
  const seen = new Set<number>()
  const dups = new Set<number>()
  for (const id of ids) {
    if (seen.has(id)) dups.add(id)
    seen.add(id)
  }
  if (dups.size) {
    console.warn(`[ФЭО дерево] Дубли PurchaseItem.id в панели «${node.name}» (категория ${catId}):`, [...dups])
  }
  const missing = allActualFor(catId).filter(a => !seen.has(a.purchase_item_id))
  if (missing.length) {
    console.warn(`[ФЭО дерево] Позиции закупок пропали из панели «${node.name}» (категория ${catId}):`, missing.map(a => a.purchase_item_id))
  }
}
watch(comparisonData, (data) => {
  for (const catId of Object.keys(data).map(Number)) devCheckNoDuplicateItems(catId)
}, { deep: true })

// ⚠️ БАГ с прода (2026-08-07): раньше суммировал ТОЛЬКО comparisonData.value[catId].planned —
// это реальные FeoPlannedItem с бэкенда. У категории с РУЧНЫМ планом листа (planned_quantity/
// planned_amount на FeoCategory) и без единой реальной FeoPlannedItem реальный список планового
// пуст, и строка ИТОГО панели не учитывала ручной план вообще, расходясь с «Плановой суммой»
// в шапке дерева (feoPlannedTotalFor/planTreeByCat). Теперь берём displayPlannedRowsFor(node) —
// тот же источник строк, что рисует сама таблица (реальные позиции ИЛИ синтетическая
// «ручной план ФЭО» с уже посчитанной суммой qty × unitPrice, см. displayPlannedRowsFor выше).
// ⚠️ ВТОРОЙ БАГ с прода (2026-08-11, «пикап» Great Wall POER, категория 903): раньше СВЕРХУ
// ещё добавлялась сумма непривязанных позиций закупки в плановой стадии (planStage,
// через actualPlanStageFor) — план и сама закупка складывались (ИТОГО 16 000 000 вместо
// 8 000 000). Плановая часть ИТОГО обязана быть РОВНО суммой плановых строк — позиции
// закупок (любой стадии) теперь либо вложены ПОД своей плановой строкой (не добавляют
// ничего к сумме — она уже посчитана в planned.amount), либо, если не привязаны и плана нет
// вовсе, повисают в «Не привязаны» и намеренно НЕ участвуют ни в плановом, ни в фактическом
// ИТОГО (это и есть смысл пометки «требуется действие»).
function comparisonPlanTotal(node: FeoNode): number {
  return displayPlannedRowsFor(node).reduce((s, p) => s + Number(p.amount || 0), 0)
}

// Требование владельца (2026-08-12): таблица плановых позиций должна выглядеть вложенной
// в свою категорию — так же, как «Внедорожник» вложен в «Транспорт и технику». 20px — это
// сам шаг вложенности дерева (paddingLeft строки категории в основном дереве =
// node.depth * 20 + 8px, см. feo-td-name выше), к нему прибавлен один уровень (+20) плюс
// поправка +5px компенсирующая разницу ширины иконок ПЕРЕД текстом: в строке дерева их
// две — шеврон + папка (~39px), а в строке плановой позиции — одна маленькая (~14px);
// без этой поправки визуальный левый край текста «съедает» уступ и вложенность не видна
// на глаз, хотя padding формально уже глубже. Итог замерян в браузере (getBoundingClientRect
// по текстовым узлам): «Транспорт и техника» → «Внедорожник» → «Great Wall POER» идут
// лесенкой с шагом ≈20px. Привязано к depth, а не константе, чтобы уступ был одинаковым
// на любом уровне вложенности дерева.
function plannedItemIndentPx(node: FeoNode): number {
  return node.depth * 20 + 53
}

// Задача владельца «план ≠ факт» (сессия 2026-08-06, Шаг 5, п.6): ИТОГО «факт» панели
// обязано суммировать РЕАЛЬНЫЙ факт (fact_amount — ContractItem/contract_price), а не
// текущую total_price позиции — та с момента заморозки ТЗ (Шаг 2) держит плановую цену
// и была бы неотличима от плана в самой строке, где как раз нужно показать факт.
function comparisonFactTotal(catId: number): number {
  return actualFactFor(catId).reduce((s, a) => s + Number(a.fact_amount ?? a.total_price ?? 0), 0)
}

function toggleExpand(id: number) {
  const idx = expandedIds.value.indexOf(id)
  if (idx >= 0) {
    expandedIds.value.splice(idx, 1)
  } else {
    expandedIds.value.push(id)
  }
}

// ── Subtree helpers ──────────────────────────────
function collectSubtreeIds(nodeId: number): number[] {
  const ids = [nodeId]
  const find = (pid: number) => {
    for (const c of feoCategories.value) {
      if (c.parent_id === pid) { ids.push(c.id); find(c.id) }
    }
  }
  find(nodeId)
  return ids
}

const feoParentOptions = computed(() => {
  if (!feoEditTarget.value) return []
  const excludeIds = new Set(collectSubtreeIds(feoEditTarget.value.id))
  return feoCategories.value
    .filter(c => !excludeIds.has(c.id))
    .map(c => ({ id: c.id, name: '  '.repeat(c.level - 1) + c.name }))
})

const feoDeleteChildrenCount = computed(() => {
  if (!feoDeleteTarget.value) return 0
  return collectSubtreeIds(feoDeleteTarget.value.id).length - 1
})

// ── Inline budget edit ───────────────────────────
async function startInlineBudget(node: FeoNode) {
  inlineBudgetId.value = node.id
  inlineBudgetVal.value = node.budget != null ? String(node.budget) : ''
  _pendingBudgetSave = { nodeId: node.id, node }
  await nextTick()
  const el = Array.isArray(inlineInputEl.value) ? inlineInputEl.value[0] : inlineInputEl.value
  el?.focus?.()
}

let _pendingBudgetSave: { nodeId: number; node: FeoNode } | null = null

async function saveInlineBudget(node: FeoNode) {
  // Save nodeId before clearing — blur may fire after re-render
  const nodeId = _pendingBudgetSave?.nodeId ?? inlineBudgetId.value
  if (!nodeId) return
  const savedNode = _pendingBudgetSave?.node ?? node
  _pendingBudgetSave = null
  inlineBudgetId.value = null
  const raw = String(inlineBudgetVal.value ?? '').trim()
  const val = raw === '' ? null : parseFloat(raw)
  try {
    await apiFetch(`/feo-categories/${nodeId}`, {
      method: 'PUT',
      body: JSON.stringify({ name: savedNode.name, code: savedNode.code ?? null, appendix: savedNode.appendix ?? null,
        is_active: savedNode.is_active, budget: val, planned_quantity: savedNode.planned_quantity ?? null,
        planned_amount: savedNode.planned_amount ?? null, unit: savedNode.unit ?? null, subsidy_id: savedNode.subsidy_id }),
    })
    const cat = feoCategories.value.find(c => c.id === nodeId)
    if (cat) cat.budget = val
    savedNode.budget = val
    feoCategories.value = [...feoCategories.value]
    syncFeoFilled()
  } catch (e: any) { showSnack(e.detail || 'Ошибка сохранения', 'error') }
}

// ── Planned quantity helpers ─────────────────────
// Зеркало фолбэка feoPlannedTotalFor выше (миграция плана → плановые позиции): у
// мигрированного листа planned_quantity null, но план есть в плановых позициях —
// берём qty_plan из planTreeByCat вместо 0.
function feoQtyFor(node: FeoNode): number {
  if (!node.hasChildren) {
    if (node.planned_quantity != null) return Number(node.planned_quantity)
    const t = planTreeByCat.value[node.id]
    if (t && t.qty_plan != null) return Number(t.qty_plan)
    return 0
  }
  if (node.planned_quantity != null) return Number(node.planned_quantity)
  return node.children.reduce((acc, child) => acc + feoQtyFor(child), 0)
}

function isAutoQtyNode(node: FeoNode): boolean {
  if (!node.hasChildren) return false
  return node.planned_quantity == null
}

// ── Плановое количество из заявок (статусы план закупок и дальше), БЕЗ привязанных к
// плановой позиции (feo_planned_item_id) — те расходуют ручной план листа, а не
// складываются с ним поверх. Карта plannedPurchaseQty уже нетто (qty − qty_linked).
function feoQtyRequestsFor(node: FeoNode): number {
  const own = plannedPurchaseQty.value[node.id] || 0
  if (!node.hasChildren) return own
  return own + node.children.reduce((acc, child) => acc + feoQtyRequestsFor(child), 0)
}

// Количество «выбрано заявками» из ручного плана — зеркало feoQtyRequestsFor по карте
// ПРИВЯЗАННЫХ позиций. Нужно, чтобы режимы 'purchases'/'requests' (показывающие ВСЕ
// позиции заявок, не нетто) не потеряли привязанную часть после нетто-правки выше.
function feoQtyConsumedFor(node: FeoNode): number {
  const own = plannedPurchaseQtyLinked.value[node.id] || 0
  if (!node.hasChildren) return own
  return own + node.children.reduce((acc, child) => acc + feoQtyConsumedFor(child), 0)
}

// Количество «сверх плана» (over_plan=true, НЕпривязанные) — прибавляется к плановому
// количеству элемента безусловно, поверх план/заказ. Зеркало feoPlannedOverFor (см. ниже)
// для количеств.
function feoQtyOverFor(node: FeoNode): number {
  const own = plannedPurchaseQtyOver.value[node.id] || 0
  if (!node.hasChildren) return own
  return own + node.children.reduce((acc, child) => acc + feoQtyOverFor(child), 0)
}

// Единая формула «Планового количества» узла — считается на бэкенде (сессия
// 2026-08-05, задача «формула только на бэкенде»: раньше здесь была СВОЯ формула
// MAX(план, выбрано) + сверх_плана, которая расходилась с KPI «Запланировано» на
// дашборде/в списке субсидий — тот считает НОВУЮ формулу «заказ замещает план»
// (app.services.feo_plan.compute_feo_plan_tree). Теперь читаем готовое число из
// GET /api/feo-categories/plan-tree (planTreeByCat) — фронт ничего не пересчитывает.
function feoQtyDisplayRaw(node: FeoNode): number {
  return planTreeByCat.value[node.id]?.display_quantity || 0
}

// Отображаемое «Плановое количество» по режиму собственного переключателя
function feoQtyDisplayFor(node: FeoNode): number {
  if (plannedQtyBase.value === 'manual') return feoQtyFor(node)
  // 'purchases'/'requests' — режимы «показать всё из заявок»: +Consumed/+Over возвращают
  // привязанную и сверхплановую часть, вычтенные из feoQtyRequestsFor (иначе переключатель
  // занизит объём).
  if (plannedQtyBase.value === 'purchases') return feoQtyFor(node) + feoQtyRequestsFor(node) + feoQtyConsumedFor(node) + feoQtyOverFor(node)
  if (plannedQtyBase.value === 'requests') {
    // одноимённые из заявок привязаны к родителю — у слитого листа добавляем их явно
    return feoQtyRequestsFor(node) + feoQtyConsumedFor(node) + feoQtyOverFor(node) + (!node.hasChildren ? matchedReqQty(node) : 0)
  }
  // 'all' (по умолчанию): готовое число с бэкенда — см. feoQtyDisplayRaw. До 2026-08-07 здесь
  // была ветка «слитая позиция: ручной план + matchedReqQty(node)» — складывала ручное
  // количество узла с количеством позиций заявок, сматченных с ним ПО ИМЕНИ (см. matchedReqFor),
  // то есть задваивала счётчик тем же способом, каким уже была исправлена «Плановая сумма»
  // (см. feoPlannedDisplayFor выше, задача «план ≠ факт», сессия 2026-08-06). В 'all' фронт
  // обязан ТОЛЬКО читать готовое число с бэкенда.
  return feoQtyDisplayRaw(node)
}

// Отклонение слитого кол-ва от заложенного в ФЭО показателя (кол-во по документу ФЭО)
function mergedQtyDiff(node: FeoNode): number {
  if (!mergedManualPriority(node) || node.feo_quantity == null) return 0
  const total = feoQtyFor(node) + matchedReqQty(node) + feoQtyRequestsFor(node)
  return Math.round((total - Number(node.feo_quantity)) * 10000) / 10000
}

// ── Planned amount helpers ───────────────────────
function feoAmtFor(node: FeoNode): number {
  if (!node.hasChildren) return node.planned_amount != null ? Number(node.planned_amount) : 0
  if (node.planned_amount != null) return Number(node.planned_amount)
  return node.children.reduce((acc, child) => acc + feoAmtFor(child), 0)
}

// ── Computed planned total: кол-во × стоимость за ед. ───
// Parent = sum of children's planned totals (never qty × unitPrice of parent)
// Leaf = own planned_quantity × own planned_amount
// Миграция плана категории → именованные плановые позиции (FeoPlannedItem, сессия
// 2026-08-12): у мигрированного листа planned_quantity/planned_amount оба null (план
// живёт в активных плановых позициях), поэтому qty×unitPrice ниже даёт 0. Фолбэк —
// planTreeByCat.value[node.id]?.plan_manual, точный двойник этой функции на бэкенде
// (см. app.services.feo_plan.compute_feo_plan_tree: qty×amt, если поля заданы, иначе
// Σ сумм активных плановых позиций). Если дерево плана ещё не загружено — старая
// локальная формула как запасной вариант (даст 0 для мигрированного листа, как раньше).
function feoPlannedTotalFor(node: FeoNode): number {
  if (node.hasChildren) {
    return node.children.reduce((acc, child) => acc + feoPlannedTotalFor(child), 0)
  }
  // Leaf: qty × unit_price (both must be set on THIS node, not inherited)
  const qty = node.planned_quantity != null ? Number(node.planned_quantity) : 0
  const unitPrice = node.planned_amount != null ? Number(node.planned_amount) : 0
  if (qty > 0 && unitPrice > 0) return qty * unitPrice
  if (node.planned_quantity == null && node.planned_amount == null) {
    const t = planTreeByCat.value[node.id]
    if (t && t.plan_manual != null) return Number(t.plan_manual)
  }
  return 0
}

// ── Плановая сумма из заявок (статусы план закупок и дальше), БЕЗ позиций, привязанных
// к плановой позиции (feo_planned_item_id) — они РАСХОДУЮТ ручной план листа (Ур.5),
// а не складываются с ним поверх (иначе план задваивается — см. feoPlannedConsumedFor).
// Лист — из карты бэкенда (уже нетто: total − total_linked); группа — собственные
// позиции (привязанные прямо к группе) + сумма детей.
function feoPlannedRequestsFor(node: FeoNode): number {
  const own = plannedPurchaseTotals.value[node.id] || 0
  if (!node.hasChildren) return own
  return own + node.children.reduce((acc, child) => acc + feoPlannedRequestsFor(child), 0)
}

// Сумма «выбрано заявками» из ручного плана — зеркало feoPlannedRequestsFor по карте
// ПРИВЯЗАННЫХ позиций. Нужна для заметки под «Плановой суммой» и чтобы режимы
// 'purchases'/'requests' (показывающие ВСЕ позиции заявок целиком) не потеряли
// привязанную часть после нетто-правки feoPlannedRequestsFor выше.
function feoPlannedConsumedFor(node: FeoNode): number {
  const own = plannedPurchaseTotalsLinked.value[node.id] || 0
  if (!node.hasChildren) return own
  return own + node.children.reduce((acc, child) => acc + feoPlannedConsumedFor(child), 0)
}

// «В плане-графике» — решение владельца 2026-08-18 (категория 3710: три несводимые шкалы
// в строке дерева читались как противоречие). Это ровно та же величина, что уже показывает
// заметка «в закупках» под «Плановой суммой» (feoResidualNoteFor/feoPlanConsumedNoteFor
// считают consumed этой же суммой) — второй источник чисел не изобретаем, оба места сведены
// к этому хелперу.
function feoInPlanScheduleFor(node: FeoNode): number {
  return feoPlannedRequestsFor(node) + feoPlannedConsumedFor(node)
}

// Сумма «сверх плана» (over_plan=true, НЕпривязанные) — прибавляется к плановой сумме
// элемента безусловно, поверх план/заказ (см. feoPlannedDisplayRaw ниже).
// Лист — из карты бэкенда (уже нетто относительно linked); группа — собственные
// сверхплановые позиции (прямо на группе) + сумма детей.
function feoPlannedOverFor(node: FeoNode): number {
  const own = plannedPurchaseTotalsOver.value[node.id] || 0
  if (!node.hasChildren) return own
  return own + node.children.reduce((acc, child) => acc + feoPlannedOverFor(child), 0)
}

// Единая формула «Плановой суммы» узла — считается на бэкенде (сессия 2026-08-05,
// задача «формула только на бэкенде»). Раньше здесь была СВОЯ формула
// MAX(план, выбрано) + сверх_плана — расходилась с KPI «Запланировано» на дашборде/
// в списке субсидий, который считает через _calculate_feo_planned_tree_bulk НОВУЮ
// формулу «заказ замещает план, когда количество набрано полностью»
// (app.services.feo_plan.compute_feo_plan_tree) — два разных числа на одном экране.
// Теперь читаем готовое число из GET /api/feo-categories/plan-tree (planTreeByCat) —
// единственный источник правды, фронт ничего не пересчитывает и не обходит детей сам.
function feoPlannedDisplayRaw(node: FeoNode): number {
  return planTreeByCat.value[node.id]?.display || 0
}

// Отображаемая «Плановая сумма» по режиму переключателя.
// Нетто-исключение привязанных применяется ТОЛЬКО в ветке 'all' (последний return —
// единственный режим, где «Плановая сумма» это цельный лимит листа, который заявка не
// должна задваивать). 'purchases' и 'requests' — режимы «показать всё из заявок», там
// +feoPlannedConsumedFor(node)/+feoPlannedOverFor(node) восстанавливают привязанную и
// сверхплановую часть до полного объёма (feoPlannedRequestsFor теперь исключает обе).
function feoPlannedDisplayFor(node: FeoNode): number {
  if (plannedSumBase.value === 'manual') return feoPlannedTotalFor(node)
  if (plannedSumBase.value === 'purchases') return feoPlannedTotalFor(node) + feoPlannedRequestsFor(node) + feoPlannedConsumedFor(node) + feoPlannedOverFor(node)
  if (plannedSumBase.value === 'requests') {
    // одноимённые из заявок привязаны к родителю — у слитого листа добавляем их явно
    return feoPlannedRequestsFor(node) + feoPlannedConsumedFor(node) + feoPlannedOverFor(node) + (!node.hasChildren ? matchedReqTotal(node) : 0)
  }
  // 'all' (по умолчанию): готовое число с бэкенда — см. feoPlannedDisplayRaw.
  // Задача владельца «план ≠ факт» (сессия 2026-08-06, Шаг 5, п.4): раньше здесь была
  // ветка «слитая позиция: ручной план + matchedReqTotal(node)», которая СКЛАДЫВАЛА
  // ручной план узла с суммой позиций заявок, сматченных с ним ПО ИМЕНИ — источник
  // задвоения (пример владельца: ручной план 8 000 000 + заявка 8 380 000 = 16 760 000,
  // хотя заявка ЯВЛЯЕТСЯ этим планом, а не чем-то поверх него). В режиме 'all' фронт
  // обязан ТОЛЬКО читать готовое число с бэкенда (compute_feo_plan_tree уже правильно
  // засчитывает факт/план по каждой позиции ровно один раз — см. feo_plan.py).
  return feoPlannedDisplayRaw(node)
}

// Заметка под «Плановой суммой»: план N ₽ · в закупках M ₽ · свободно K ₽ (см. ЗАДАЧА
// сессии 2026-08-05). Свободно = plan_manual − consumed (может уйти в минус — тогда
// шаблон пишет «больше плана на X»). Показывается ТОЛЬКО в режиме 'all' (единственный
// режим, где действует новая формула MAX) и только когда есть хоть какие-то числа —
// пустые узлы (ни плана, ни заявок) заметку не показывают.
//
// БАГ (жалоба владельца 2026-08-13, «Окружные»): «план 513 244 — это откуда?» — раньше
// planned = feoPlannedTotalFor(node), а та для узла с детьми считает ТОЛЬКО сумму
// планов детей, без собственной плановой позиции узла — расходилась с шапкой строки
// (feoPlannedDisplayFor/planTreeByCat.plan_manual, который = дети + own_amt, см.
// feoOwnDirectionPlanFor). Теперь planned читается из ТОГО ЖЕ planTreeByCat.plan_manual,
// что и шапка — те же 561 685,80, а не 513 244. feoPlannedTotalFor(node) остаётся ТОЛЬКО
// запасным вариантом на случай, когда дерево плана (planTreeByCat) ещё не загружено.
//
// БАГ 2: «выбрано 695 656 — откуда?» / у конечной категории «выбрано заявками 0,00»
// при факте 118 365,60 закупками — раньше consumed = feoPlannedRequestsFor(node), это
// ТОЛЬКО непривязанные к Ур.5 позиции заявок (plannedPurchaseTotals). Если у категории
// все позиции привязаны (feo_planned_item_id задан), consumed был 0, хотя по плану уже
// набрано. Складываем непривязанные (feoPlannedRequestsFor) с привязанными
// (feoPlannedConsumedFor, карта plannedPurchaseTotalsLinked) — «в закупках» теперь
// считает ВСЁ, что стоит за планом, вне зависимости от привязки.
function feoPlanConsumedNoteFor(node: FeoNode): { planned: number; consumed: number; residual: number } | null {
  const t = planTreeByCat.value[node.id]
  const planned = (t && t.plan_manual != null) ? Number(t.plan_manual) : feoPlannedTotalFor(node)
  const consumed = feoInPlanScheduleFor(node)
  if (planned <= 0 && consumed <= 0) return null
  return { planned, consumed, residual: planned - consumed }
}

// Прогнозное предупреждение «цена выше плановой» (ЗАДАЧА 2/3 сессии 2026-08-05).
// Данные считаются на бэкенде (app.services.feo_plan.compute_feo_plan_tree, поля
// forecast/forecast_over/plan_manual в GET /feo-categories/planned-purchase-totals,
// см. plannedPurchaseForecast) — фронт только читает готовое число, НИКАКИХ
// вычислений и блокировок. Только информирование: если по факту заказанного темпу
// цен итоговая сумма грозит превысить план — оранжевая заметка под «Плановой суммой».
function feoForecastWarningFor(node: FeoNode): { forecast: number; forecastOver: number; planManual: number } | null {
  const v = plannedPurchaseForecast.value[node.id]
  if (!v || !(v.forecast_over > 0)) return null
  return { forecast: v.forecast, forecastOver: v.forecast_over, planManual: v.plan_manual }
}

function isAutoAmtNode(node: FeoNode): boolean {
  if (!node.hasChildren) return false
  return node.planned_amount == null
}

let _pendingAmtSave: { nodeId: number; node: FeoNode } | null = null

async function startInlineAmt(node: FeoNode) {
  inlineAmtId.value = node.id
  inlineAmtVal.value = node.planned_amount != null ? String(node.planned_amount) : ''
  _pendingAmtSave = { nodeId: node.id, node }
  await nextTick()
  const elA = Array.isArray(inlineAmtInputEl.value) ? inlineAmtInputEl.value[0] : inlineAmtInputEl.value
  elA?.focus?.()
}

async function saveInlineAmt(node: FeoNode) {
  const nodeId = _pendingAmtSave?.nodeId ?? inlineAmtId.value
  if (!nodeId) return
  const savedNode = _pendingAmtSave?.node ?? node
  _pendingAmtSave = null
  inlineAmtId.value = null
  const raw = String(inlineAmtVal.value ?? '').trim()
  const val = raw === '' ? null : parseFloat(raw)
  try {
    await apiFetch(`/feo-categories/${nodeId}`, {
      method: 'PUT',
      body: JSON.stringify({ name: savedNode.name, code: savedNode.code ?? null, appendix: savedNode.appendix ?? null,
        is_active: savedNode.is_active, budget: savedNode.budget ?? null, planned_quantity: savedNode.planned_quantity ?? null,
        planned_amount: val ?? null, unit: savedNode.unit ?? null, subsidy_id: savedNode.subsidy_id }),
    })
    const cat = feoCategories.value.find(c => c.id === nodeId)
    if (cat) cat.planned_amount = val ?? null
    savedNode.planned_amount = val ?? null
    feoCategories.value = [...feoCategories.value]
  } catch (e: any) { showSnack(e.detail || 'Ошибка сохранения', 'error') }
}

let _pendingQtySave: { nodeId: number; node: FeoNode } | null = null

async function startInlineQty(node: FeoNode) {
  inlineQtyId.value = node.id
  inlineQtyVal.value = node.planned_quantity != null ? String(node.planned_quantity) : ''
  _pendingQtySave = { nodeId: node.id, node }
  await nextTick()
  const elQ = Array.isArray(inlineQtyInputEl.value) ? inlineQtyInputEl.value[0] : inlineQtyInputEl.value
  elQ?.focus?.()
}

async function saveInlineQty(node: FeoNode) {
  const nodeId = _pendingQtySave?.nodeId ?? inlineQtyId.value
  if (!nodeId) return
  const savedNode = _pendingQtySave?.node ?? node
  _pendingQtySave = null
  inlineQtyId.value = null
  const raw = String(inlineQtyVal.value ?? '').trim()
  const val = raw === '' ? null : parseFloat(raw)
  try {
    await apiFetch(`/feo-categories/${nodeId}`, {
      method: 'PUT',
      body: JSON.stringify({ name: savedNode.name, code: savedNode.code ?? null, appendix: savedNode.appendix ?? null,
        is_active: savedNode.is_active, budget: savedNode.budget ?? null, planned_quantity: val,
        planned_amount: savedNode.planned_amount ?? null, unit: savedNode.unit ?? null, subsidy_id: savedNode.subsidy_id }),
    })
    const cat = feoCategories.value.find(c => c.id === nodeId)
    if (cat) cat.planned_quantity = val
    savedNode.planned_quantity = val
    feoCategories.value = [...feoCategories.value]
  } catch (e: any) { showSnack(e.detail || 'Ошибка сохранения', 'error') }
}

// ── Drag & Drop ──────────────────────────────────
function onDragStart(e: DragEvent, node: FeoNode) {
  dragNodeId.value = node.id
  e.dataTransfer!.effectAllowed = 'move'
  e.dataTransfer!.setData('text/plain', String(node.id))
}

function onDragOver(e: DragEvent, node: FeoNode) {
  if (!dragNodeId.value || dragNodeId.value === node.id) return
  const subtree = collectSubtreeIds(dragNodeId.value)
  if (subtree.includes(node.id)) return
  dragOverId.value = node.id
}

function onDragLeave() { dragOverId.value = null }

async function onDrop(e: DragEvent, targetNode: FeoNode) {
  e.preventDefault()
  if (!dragNodeId.value || dragNodeId.value === targetNode.id) return
  const srcId = dragNodeId.value
  const srcNode = visibleFeoNodes.value.find(n => n.id === srcId)
  dragOverId.value = null; dragNodeId.value = null
  if (!srcNode) return
  const subtree = collectSubtreeIds(srcId)
  if (subtree.includes(targetNode.id)) { showSnack('Нельзя переместить в собственное поддерево', 'error'); return }
  if (srcNode.parent_id === targetNode.id) return
  try {
    const res = await apiFetch<any>(`/feo-categories/${srcId}/move`, {
      method: 'PATCH', body: JSON.stringify({ parent_id: targetNode.id }),
    })
    showSnack('Категория перемещена')
    if (res?.warning) showSnack(res.warning, 'warning')
    if (selectedId.value) await loadFeo(selectedId.value)
    syncFeoFilled()
  } catch (e: any) { showSnack(e.detail || 'Ошибка перемещения', 'error') }
}

async function onDropToRoot(e: DragEvent) {
  e.preventDefault()
  if (!dragNodeId.value) return
  const srcId = dragNodeId.value
  const srcNode = visibleFeoNodes.value.find(n => n.id === srcId)
  dragOverId.value = null; dragNodeId.value = null
  if (!srcNode || !srcNode.parent_id) return
  try {
    const res = await apiFetch<any>(`/feo-categories/${srcId}/move`, {
      method: 'PATCH', body: JSON.stringify({ parent_id: null }),
    })
    showSnack('Категория перемещена на верхний уровень')
    if (res?.warning) showSnack(res.warning, 'warning')
    if (selectedId.value) await loadFeo(selectedId.value)
    syncFeoFilled()
  } catch (e: any) { showSnack(e.detail || 'Ошибка перемещения', 'error') }
}

function onDragEnd() { dragNodeId.value = null; dragOverId.value = null }

// ── Data load ─────────────────────────────────────
// Phase 26-ZZ: bulk-load контрагентов убран. Локальный contractors массив
// наполняется через ContractorPicker и ad-hoc fetch при edit.
async function loadAll() {
  loading.value = true
  try {
    const charts = await apiFetch<any>('/dashboard/charts?scope=managed')
    allSubsidies.value = charts.subsidy_stats.map((s: any) => ({
      id: s.id, name: s.name, year: s.year, budget: s.budget,
      calculated_budget: s.calculated_budget ?? 0,
      planned: s.planned_tree ?? s.total_planned, paid: s.total_paid, contracted: s.total_confirmed,
      plan_schedule: s.total_plan_schedule ?? 0,
      ordered: s.total_ordered ?? 0,
      feo_budget_total: s.feo_budget_total ?? 0,
      feo_filled: s.feo_filled ?? false,
      contractor_id: s.contractor_id ?? null,
      contractor_name: s.contractor_name ?? null,
      contractor_inn: s.contractor_inn ?? null,
      // Phase 31-05: canonical budget fields (D-17)
      remaining: s.remaining ?? null,
      planned_amount: s.planned_amount ?? null,
      budget_discrepancy: s.budget_discrepancy ?? null,
      // Phase 32: dashboard KPI fields
      work: s.total_work ?? 0,
      contracts: s.total_contracts ?? 0,
      delivered: s.total_delivered ?? 0,
      delivered_unpaid: s.total_delivered_unpaid ?? 0,
      // Владелец (2026-08-30): предупреждение о подходе к потолку субсидии
      ceiling_warn_percent: s.ceiling_warn_percent ?? 90,
      ceiling_total: s.ceiling_total ?? 0,
      ceiling_committed_total: s.ceiling_committed_total ?? 0,
      ceiling_committed_percent: s.ceiling_committed_percent ?? 0,
      ceiling_near_warning: s.ceiling_near_warning ?? false,
      ceiling_exceeded: s.ceiling_exceeded ?? false,
      status: 'approved', // fallback, перезаписывается ниже реальным значением
    }))
    // C4: dashboard/charts не отдаёт status/created_by/approved_by/approved_at
    // (это отдельная сводка бюджетов). Статус черновика подтягиваем отдельным
    // вызовом уже существующего списочного эндпоинта и мёрджим по id — без
    // изменений на бэкенде. Ошибка здесь не должна ломать страницу (fallback
    // 'approved' — чипы просто не появятся).
    try {
      const statusRows = await apiFetch<Array<{ id: number; status?: string; created_by?: number | null; approved_by?: number | null; approved_at?: string | null }>>('/subsidies/')
      const byId = new Map(statusRows.map(r => [r.id, r]))
      for (const row of allSubsidies.value) {
        const found = byId.get(row.id)
        if (found) {
          row.status = found.status ?? 'approved'
          row.created_by = found.created_by ?? null
          row.approved_by = found.approved_by ?? null
          row.approved_at = found.approved_at ?? null
        }
      }
    } catch (e) {
      console.warn('[subsidies] status load failed:', e)
    }
    const years = [...new Set(allSubsidies.value.map((s: SubsidyRow) => s.year))].sort((a, b) => b - a)
    if (years.length) selectedYear.value = years[0]  // always reset to most recent year

    // Handle ?sid=X navigation from Quick Access
    const sidParam = route.query.sid
    if (sidParam) {
      const targetId = Number(sidParam)
      const target = allSubsidies.value.find(s => s.id === targetId)
      if (target) {
        selectedYear.value = target.year
        selectedId.value = targetId
        loadFeo(targetId)
      }
    }
  } catch (e) {
    showSnack('Ошибка загрузки данных', 'error')
  } finally {
    loading.value = false
  }
}

async function exportFeoPdf() {
  if (!feoTableArea.value) { showSnack('Таблица ФЭО не готова', 'error'); return }
  try {
    const name = `ФЭО_${selectedSubsidy.value?.name ?? ''}`.trim()
    await _exportFeoScreenshotPdf(feoTableArea.value, name, undefined, {
      // Колонка «Действия» нефункциональна в PDF и съедает место — скрыть.
      hideSelectors: ['.feo-th-actions', '.feo-td-actions'],
      // С table-layout:fixed «Наименование» ужимается в столбик; auto + перенос по словам.
      extraCss: '.feo-table{table-layout:auto!important;width:100%!important}'
        + '.feo-th-name,.feo-td-name{min-width:280px!important;white-space:normal!important}'
        + '.feo-name{word-break:normal!important;overflow-wrap:anywhere!important}',
    })
  } catch (e: any) {
    showSnack(e?.message ?? 'Ошибка экспорта PDF', 'error')
  }
}

async function exportFeoToExcel() {
  if (!selectedId.value) return
  const token = localStorage.getItem('auth_token')
  const res = await fetch(`/api/feo-categories/export?subsidy_id=${selectedId.value}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) { showSnack('Ошибка экспорта', 'error'); return }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  const cd = res.headers.get('Content-Disposition') || ''
  // Парсим RFC 5987: предпочитаем filename*=UTF-8'' (кириллица), иначе filename="...".
  // Голый /filename=([^;]+)/ захватывал кавычки → браузер превращал их в «_» → битый «.xlsx_».
  let name = 'feo_export.xlsx'
  const star = cd.match(/filename\*\s*=\s*UTF-8''([^;\n]+)/i)
  const plain = cd.match(/filename\s*=\s*(?:"([^"]+)"|([^;\n]+))/i)
  if (star) name = decodeURIComponent(star[1].trim())
  else if (plain) name = (plain[1] ?? plain[2] ?? name).trim()
  a.href = url; a.download = name; a.click()
  URL.revokeObjectURL(url)
}

async function downloadFeoTemplate() {
  const token = localStorage.getItem('auth_token')
  const res = await fetch('/api/feo-categories/import/template', {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) { showSnack('Ошибка загрузки шаблона', 'error'); return }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a'); a.href = url; a.download = 'Шаблон_импорта_направлений_ФЭО.xlsx'; a.click()
  URL.revokeObjectURL(url)
}

async function doFeoImport() {
  if (!feoImport.file) return
  feoImport.loading = true
  try {
    const fd = new FormData()
    fd.append('file', feoImport.file)
    const token = localStorage.getItem('auth_token')
    const res = await fetch('/api/feo-categories/import-preview', {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: fd,
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      showSnack(err.detail || 'Ошибка чтения файла', 'error'); return
    }
    const data = await res.json()
    feoImport.previewData = data
    feoImport.selectedSheet = data.sheets[0]?.name || ''
    feoIgnoredCols.value = []
    feoAutoMap(data.sheets[0]?.headers || [])
    feoImportTargetSubsidy.value = selectedId.value
    feoImport.step = 2
  } catch {
    showSnack('Ошибка чтения файла', 'error')
  } finally {
    feoImport.loading = false
  }
}

async function doFeoMappedImport(dryRun = false, keepStep = false) {
  if (!feoImport.file) return
  feoImport.loading = true
  try {
    const m = feoDragMapping.value
    const sheet = feoCurrentSheet.value
    // remap задаётся путём, а не id: у целевого узла в момент показа таблицы ещё нет id — он появится только при записи
    const remapEntries = Object.entries(feoImport.remap)
      .filter(([, newPath]) => !!newPath)
      .map(([oldId, newPath]) => ({ old_id: Number(oldId), new_path: newPath as string }))
    const params = new URLSearchParams({
      sheet_name: feoImport.selectedSheet,
      header_row_offset: String(sheet?.header_row_offset ?? 0),
      dry_run: dryRun ? 'true' : 'false',
      apply_remap: 'true',
      col_subsidy:  String(m['subsidy']  ?? -1),
      default_subsidy_id: String(feoImportTargetSubsidy.value ?? -1),
      col_lvl2:     String(m['lvl2']     ?? -1),
      col_lvl3:     String(m['lvl3']     ?? -1),
      col_lvl4:     String(m['lvl4']     ?? -1),
      col_lvl5:     String(m['lvl5']     ?? -1),
      col_code:     String(m['code']     ?? -1),
      col_appendix: String(m['appendix'] ?? -1),
      col_budget:   String(m['budget']   ?? -1),
      col_quantity: String(m['quantity'] ?? -1),
      col_unit:      String(m['unit']      ?? -1),
      col_item_amt:  String(m['item_amt']  ?? -1),
      col_active:    String(m['active']    ?? -1),
      col_qty_lvl2:  String(m['qty_lvl2']  ?? -1),
      col_qty_lvl3:  String(m['qty_lvl3']  ?? -1),
      col_qty_lvl4:  String(m['qty_lvl4']  ?? -1),
      col_unit_lvl2: String(m['unit_lvl2'] ?? -1),
      col_unit_lvl3: String(m['unit_lvl3'] ?? -1),
      col_unit_lvl4: String(m['unit_lvl4'] ?? -1),
      col_amt_lvl2:  String(m['amt_lvl2']  ?? -1),
      col_amt_lvl3:  String(m['amt_lvl3']  ?? -1),
      col_amt_lvl4:  String(m['amt_lvl4']  ?? -1),
      col_feo_qty_lvl2:    String(m['feo_qty_lvl2']    ?? -1),
      col_feo_unit_lvl2:   String(m['feo_unit_lvl2']   ?? -1),
      col_feo_amount_lvl2: String(m['feo_amount_lvl2'] ?? -1),
      col_feo_qty_lvl3:    String(m['feo_qty_lvl3']    ?? -1),
      col_feo_unit_lvl3:   String(m['feo_unit_lvl3']   ?? -1),
      col_feo_amount_lvl3: String(m['feo_amount_lvl3'] ?? -1),
      col_feo_qty_lvl4:    String(m['feo_qty_lvl4']    ?? -1),
      col_feo_unit_lvl4:   String(m['feo_unit_lvl4']   ?? -1),
      col_feo_amount_lvl4: String(m['feo_amount_lvl4'] ?? -1),
      col_feo_sum_lvl2: String(m['feo_sum_lvl2'] ?? -1),
      col_feo_sum_lvl3: String(m['feo_sum_lvl3'] ?? -1),
      col_feo_sum_lvl4: String(m['feo_sum_lvl4'] ?? -1),
      col_plan_sum_lvl2: String(m['plan_sum_lvl2'] ?? -1),
      col_plan_sum_lvl3: String(m['plan_sum_lvl3'] ?? -1),
      col_plan_sum_lvl4: String(m['plan_sum_lvl4'] ?? -1),
      col_item_price:    String(m['item_price']    ?? -1),
      // Новый плоский 18-колоночный шаблон (2026-08-14)
      col_row_feo_qty:    String(m['row_feo_qty']    ?? -1),
      col_row_feo_unit:   String(m['row_feo_unit']   ?? -1),
      col_row_feo_price:  String(m['row_feo_price']  ?? -1),
      col_row_feo_sum:    String(m['row_feo_sum']    ?? -1),
      col_row_plan_qty:   String(m['row_plan_qty']   ?? -1),
      col_row_plan_unit:  String(m['row_plan_unit']  ?? -1),
      col_row_plan_price: String(m['row_plan_price'] ?? -1),
      col_row_plan_sum:   String(m['row_plan_sum']   ?? -1),
      col_item_type:      String(m['item_type']      ?? -1),
    })
    if (remapEntries.length) params.set('remap', JSON.stringify(remapEntries))
    const fd = new FormData()
    fd.append('file', feoImport.file)
    const token = localStorage.getItem('auth_token')
    const res = await fetch(`/api/feo-categories/import-mapped?${params}`, {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: fd,
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      const msg = err.detail || err.message || `Ошибка импорта (HTTP ${res.status})`
      showSnack(msg, 'error')
      console.error('FEO import error:', err)
      return
    }
    const data: FeoImportResult = await res.json()
    if (dryRun) {
      // Dry-run: show preview on step 3 (или остаёмся на шаге 4 при «Пересчитать»), no DB write, no snackbar, no tree reload
      feoImport.dryResult = data
      ;(data.unmatched || []).forEach(u => {
        if (u.kind === 'needs_mapping' && !(u.id in feoImport.remap)) feoImport.remap[u.id] = null
      })
      if (!keepStep) feoImport.step = 3
    } else {
      feoImport.result = data
      feoImport.step = 5
      let msg = `Импорт завершён: создано ${data.created}`
      if (data.relinked_count) msg += `, перенесено ссылок ${data.relinked_count}`
      if (data.deleted_count) msg += `, удалено узлов ${data.deleted_count}`
      showSnack(msg)
      if (selectedId.value) { await loadFeo(selectedId.value); syncFeoFilled() }
    }
  } catch {
    showSnack('Ошибка импорта', 'error')
  } finally {
    feoImport.loading = false
  }
}

function closeFeoImport() {
  const wasCreated = (feoImport.result?.created ?? 0) > 0
  feoImport.show = false; feoImport.step = 1
  feoImport.file = null; feoImport.fileList = []; feoImport.result = null; feoImport.dryResult = null
  feoImport.previewData = null; feoImport.selectedSheet = ''
  feoDragMapping.value = {}; feoIgnoredCols.value = []; feoImport.remap = {}
  if (wasCreated && selectedId.value) { loadFeo(selectedId.value); syncFeoFilled() }
}

async function loadFeo(subsidyId: number) {
  loadingFeo.value = true
  feoCategories.value = []
  purchaseTotals.value = {}
  plannedPurchaseTotals.value = {}
  plannedPurchaseQty.value = {}
  plannedPurchaseTotalsLinked.value = {}
  plannedPurchaseQtyLinked.value = {}
  plannedPurchaseTotalsOver.value = {}
  plannedPurchaseQtyOver.value = {}
  plannedPurchaseForecast.value = {}
  planTreeByCat.value = {}
  planExcessApprovals.value = {}
  unassignedFeo.value = { amount: 0, purchase_count: 0, purchase_ids: [] }
  plannedItemsByCat.value = {}
  plannedItemsLoaded.value = false
  // expandedReqItems больше НЕ сбрасывается здесь безусловно (было `= new Set()`) — это
  // ломало persist раскрытых узлов при перезагрузке страницы (см. FEO_DISPLAY_PREFS_KEY):
  // loadFeo вызывается сразу при выборе субсидии, и сброс стирал восстановленное из
  // localStorage состояние раньше, чем пользователь успевал его увидеть. Устаревшие id
  // от другой субсидии безвредны — hasReqItems/virtualGroupsFor для несуществующего в
  // текущей субсидии узла просто вернут пусто.
  try {
    const [cats, totals, plannedTotals, plannedItems, planTree] = await Promise.all([
      apiFetch<FeoCategory[]>(`/feo-categories/?subsidy_id=${subsidyId}`),
      apiFetch<Record<number, number>>(`/feo-categories/purchase-totals?subsidy_id=${subsidyId}`),
      apiFetch<Record<number, { total: number; qty: number; total_linked?: number; qty_linked?: number; total_over?: number; qty_over?: number; forecast?: number; forecast_over?: number; plan_manual?: number }>>(`/feo-categories/planned-purchase-totals?subsidy_id=${subsidyId}`),
      apiFetch<Record<number, FeoReqItem[]>>(`/feo-categories/planned-purchase-items?subsidy_id=${subsidyId}`),
      apiFetch<Record<string, any>>(`/feo-categories/plan-tree?subsidy_id=${subsidyId}`),
    ])
    feoCategories.value = cats
    purchaseTotals.value = totals
    planTreeByCat.value = splitPlanTree(planTree)
    loadPlanExcessApprovals(subsidyId)
    plannedItemsByCat.value = plannedItems
    plannedItemsLoaded.value = true
    const sums: Record<number, number> = {}
    const qtys: Record<number, number> = {}
    const sumsLinked: Record<number, number> = {}
    const qtysLinked: Record<number, number> = {}
    const sumsOver: Record<number, number> = {}
    const qtysOver: Record<number, number> = {}
    const forecasts: Record<number, { forecast: number; forecast_over: number; plan_manual: number }> = {}
    for (const [k, v] of Object.entries(plannedTotals)) {
      const totalLinked = Number(v?.total_linked || 0)
      const qtyLinked = Number(v?.qty_linked || 0)
      const totalOver = Number(v?.total_over || 0)
      const qtyOver = Number(v?.qty_over || 0)
      sums[Number(k)] = Number(v?.total || 0) - totalLinked - totalOver
      qtys[Number(k)] = Number(v?.qty || 0) - qtyLinked - qtyOver
      sumsLinked[Number(k)] = totalLinked
      qtysLinked[Number(k)] = qtyLinked
      sumsOver[Number(k)] = totalOver
      qtysOver[Number(k)] = qtyOver
      forecasts[Number(k)] = {
        forecast: Number(v?.forecast || 0),
        forecast_over: Number(v?.forecast_over || 0),
        plan_manual: Number(v?.plan_manual || 0),
      }
    }
    plannedPurchaseTotals.value = sums
    plannedPurchaseQty.value = qtys
    plannedPurchaseTotalsLinked.value = sumsLinked
    plannedPurchaseQtyLinked.value = qtysLinked
    plannedPurchaseTotalsOver.value = sumsOver
    plannedPurchaseQtyOver.value = qtysOver
    plannedPurchaseForecast.value = forecasts
    // Восстановленные из localStorage раскрытые панели «план vs факт» (expandedItemPanels)
    // не тянут свои данные сами — toggleItemPanel грузит их только по клику. Подгружаем
    // явно, иначе после перезагрузки страницы раскрытая панель будет пустой до повторного клика.
    for (const id of expandedItemPanels.value) {
      if (feoCategories.value.some(c => c.id === id)) refreshComparison(id)
    }
  } catch {
    showSnack('Ошибка загрузки категорий ФЭО', 'error')
  } finally {
    loadingFeo.value = false
  }
}

async function reorderFeoNode(node: any, direction: 'up' | 'down') {
  if (!selectedId.value) return
  try {
    const res = await apiFetch<any>(`/feo-categories/${node.id}/reorder`, {
      method: 'PATCH',
      body: JSON.stringify({ direction }),
    })
    if (res?.moved === false) {
      showSnack(direction === 'up' ? 'Уже первая в списке' : 'Уже последняя в списке', 'info')
      return
    }
    await loadFeo(selectedId.value)
    syncFeoFilled()
  } catch (e: any) {
    showSnack(e?.detail || e?.payload?.message || 'Не удалось переместить', 'error')
  }
}

// Замечание владельца п.3 (2026-08-12): «Приравнять ФЭО к плану» — POST
// /feo-categories/{id}/align-budget-to-plan (бэкенд уже готов, включая жёсткий
// потолок субсидии — assert внутри самого эндпоинта, фронт ничего не проверяет
// заранее). Доступ — org_admin и выше: переиспользуем canSaveVersion (тот же
// набор ролей, что backend ADMIN_ROLES = superadmin/account_owner/admin/org_admin,
// см. её объявление ниже) — НЕ придумываем новую проверку, чтобы не потерять
// org_admin, как это уже бывало в проекте (см. Lessons).
const alignBudgetLoading = ref<number | null>(null)
const alignBudgetDialog = ref<{ show: boolean; node: FeoNode | null; newBudget: number; oldBudget: number }>({
  show: false, node: null, newBudget: 0, oldBudget: 0,
})
function openAlignBudgetConfirm(node: FeoNode) {
  const t = planTreeByCat.value[node.id]
  const newBudget = Number(t?.plan || 0) + Number(t?.over || 0)
  alignBudgetDialog.value = { show: true, node, newBudget, oldBudget: Number(node.budget || 0) }
}
async function confirmAlignBudgetToPlan() {
  const node = alignBudgetDialog.value.node
  if (!node) return
  alignBudgetLoading.value = node.id
  try {
    await apiFetch(`/feo-categories/${node.id}/align-budget-to-plan`, { method: 'POST' })
    alignBudgetDialog.value.show = false
    showSnack('Финансирование по ФЭО приравнено к плану', 'success')
    if (selectedId.value) await loadFeo(selectedId.value)
  } catch (e: any) {
    // Ошибку показываем распакованной (в т.ч. отказ по общему потолку субсидии,
    // код PLAN_OVER_SUBSIDY_CEILING) — showSnack по умолчанию без автозакрытия.
    showSnack(e?.payload?.message || e?.detail || e?.message || 'Не удалось приравнять ФЭО к плану', 'error')
  } finally {
    alignBudgetLoading.value = null
  }
}

// ── Actions ───────────────────────────────────────
// 12-04: load FEO residuals for selected subsidy
async function loadResiduals() {
  if (!selectedId.value) return
  residualsLoading.value = true
  try {
    const data = await apiFetch<any[]>(`/feo-planned-items/residuals?subsidy_id=${selectedId.value}`)
    const byItemId: Record<number, any> = {}
    for (const item of data) {
      byItemId[item.feo_item_id] = item
    }
    feoResiduals.value = byItemId
  } catch (e) {
    console.error('Failed to load residuals', e)
  } finally {
    residualsLoading.value = false
  }
}

async function loadVersionHistory() {
  if (!selectedId.value) return
  versionHistoryLoading.value = true
  try {
    versionHistoryList.value = await apiFetch<any[]>(`/subsidies/${selectedId.value}/plan-graph/versions`)
  } finally {
    versionHistoryLoading.value = false
  }
}

async function openVersionHistory() {
  compareSelected.value = []
  await loadVersionHistory()
  showVersionHistoryDialog.value = true
}

async function viewVersionSnapshot(verId: number) {
  selectedVersionSnapshot.value = await apiFetch<any>(`/subsidies/${selectedId.value}/plan-graph/versions/${verId}?with_reconciliation=true`)
  showVersionSnapshotDialog.value = true
}

async function downloadVersionExcel(vid: number) {
  if (!selectedId.value) return
  try {
    const token = localStorage.getItem('auth_token')
    const res = await fetch(`/api/subsidies/${selectedId.value}/plan-graph/versions/${vid}/export`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!res.ok) throw new Error('Ошибка экспорта')
    const blob = await res.blob()
    const cd = res.headers.get('content-disposition') || ''
    const m = cd.match(/filename="?([^"]+)"?/)
    const filename = m ? m[1] : `version-${vid}.xlsx`
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = filename; a.click()
    URL.revokeObjectURL(url)
  } catch (e: any) {
    showSnack(e?.message || 'Ошибка экспорта', 'error')
  }
}

function formatEditionDate(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return '—'
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

async function openExportVersionsDialog() {
  if (!selectedId.value) return
  exportVersionsLoading.value = true
  showExportVersionsDialog.value = true
  exportSelectedIds.value = []
  exportIncludeCurrent.value = true
  try {
    exportVersionsList.value = await apiFetch<any[]>(`/subsidies/${selectedId.value}/plan-graph/versions`)
  } finally {
    exportVersionsLoading.value = false
  }
}

function toggleExportId(id: number) {
  const idx = exportSelectedIds.value.indexOf(id)
  if (idx === -1) exportSelectedIds.value.push(id)
  else exportSelectedIds.value.splice(idx, 1)
}

async function runVersionsExport() {
  const sel = exportSelectedIds.value
  const inc = exportIncludeCurrent.value
  if (sel.length === 0 && !inc) {
    showSnack('Выберите хотя бы одну редакцию', 'warning')
    return
  }
  if (sel.length === 0 && inc) {
    await exportFeoToExcel()
    showExportVersionsDialog.value = false
    return
  }
  if (sel.length === 1 && !inc) {
    await downloadVersionExcel(sel[0])
    showExportVersionsDialog.value = false
    return
  }
  // multi: several selected, or selected+current
  exportRunning.value = true
  try {
    const token = localStorage.getItem('auth_token')
    const url = `/api/subsidies/${selectedId.value}/plan-graph/versions/export-multi.xlsx?ids=${sel.join(',')}&include_current=${inc}`
    const res = await fetch(url, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!res.ok) {
      let errMsg = 'Ошибка выгрузки'
      try { const j = await res.json(); errMsg = j.message || j.detail || errMsg } catch { /* ignore */ }
      throw new Error(errMsg)
    }
    const blob = await res.blob()
    const cd = res.headers.get('Content-Disposition') || ''
    let name = 'feo_editions.xlsx'
    const star = cd.match(/filename\*\s*=\s*UTF-8''([^;\n]+)/i)
    const plain = cd.match(/filename\s*=\s*(?:"([^"]+)"|([^;\n]+))/i)
    if (star) name = decodeURIComponent(star[1].trim())
    else if (plain) name = (plain[1] ?? plain[2] ?? name).trim()
    const objUrl = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = objUrl; a.download = name; a.click()
    URL.revokeObjectURL(objUrl)
    showExportVersionsDialog.value = false
  } catch (e: any) {
    showSnack(e?.message || 'Ошибка выгрузки', 'error')
  } finally {
    exportRunning.value = false
  }
}

async function downloadCompareExcel() {
  if (!selectedId.value || compareSelected.value.length !== 2) return
  compareLoading.value = true
  try {
    const token = localStorage.getItem('auth_token')
    const [v1, v2] = [...compareSelected.value].sort((a, b) => a - b)
    const res = await fetch(`/api/subsidies/${selectedId.value}/plan-graph/versions/compare.xlsx?v1=${v1}&v2=${v2}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!res.ok) {
      let errMsg = 'Ошибка сравнения'
      try {
        const err = await res.json()
        errMsg = err?.message || err?.detail?.message || err?.detail || errMsg
      } catch {}
      throw new Error(errMsg)
    }
    const blob = await res.blob()
    const cd = res.headers.get('content-disposition') || ''
    const m = cd.match(/filename="?([^"]+)"?/)
    const filename = m ? m[1] : `compare-v${v1}-v${v2}.xlsx`
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = filename; a.click()
    URL.revokeObjectURL(url)
  } catch (e: any) {
    showSnack(e?.message || 'Ошибка сравнения', 'error')
  } finally {
    compareLoading.value = false
  }
}

// 12-05 F3: reconciliation helpers for snapshot tree view
const flattenedSnapshotTree = computed(() => {
  const tree = selectedVersionSnapshot.value?.snapshot?.tree || []
  const out: any[] = []
  function walk(nodes: any[], depth = 1) {
    for (const n of nodes) {
      out.push({ ...n, level: depth, _key: `${n.id}_${depth}` })
      if (n.children?.length) walk(n.children, depth + 1)
    }
  }
  walk(tree)
  return out
})

function getReconStatus(node: any): 'matched' | 'moved' | 'orphan' {
  const rec = selectedVersionSnapshot.value?.reconciliation?.[node.id]
  if (!rec || !rec.matched_current_id) return 'orphan'
  if (rec.match_type === 'fallback') return 'moved'
  return 'matched'
}
function getActualUsed(nodeId: number): number {
  return selectedVersionSnapshot.value?.reconciliation?.[nodeId]?.actual_used || 0
}
function getActualResidual(node: any): number {
  const used = getActualUsed(node.id)
  return (node.budget || 0) - used
}
const snapshotTotalActual = computed(() => {
  const tree = selectedVersionSnapshot.value?.snapshot?.tree || []
  let total = 0
  // только level-1 чтобы не дублировать (children агрегированы)
  for (const n of tree) total += getActualUsed(n.id)
  return total
})

// 12-05: Save version
function openSaveVersionDialog() {
  if (!selectedId.value) return
  const today = new Date().toISOString().slice(0, 10)
  saveVersionEffectiveDate.value = today
  saveVersionNote.value = ''
  showSaveVersionDialog.value = true
}

async function saveVersion() {
  if (!selectedId.value || !saveVersionEffectiveDate.value) return
  saveVersionLoading.value = true
  try {
    await apiFetch(`/subsidies/${selectedId.value}/plan-graph/versions`, {
      method: 'POST',
      body: JSON.stringify({
        effective_date: saveVersionEffectiveDate.value,
        note: saveVersionNote.value || null,
      }),
    })
    showSaveVersionDialog.value = false
    // re-load history if dialog open
    if (showVersionHistoryDialog.value) {
      await loadVersionHistory()
    }
    showSnack('Редакция ФЭО сохранена')
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.message || 'Ошибка сохранения редакции', 'error')
  } finally {
    saveVersionLoading.value = false
  }
}

function exportPlanGraphExcel() {
  const token = localStorage.getItem('auth_token') || ''
  const url = `/api/subsidies/${selectedId.value}/plan-graph/export`
  fetch(url, { headers: { Authorization: `Bearer ${token}` } })
    .then(r => r.blob())
    .then(blob => {
      const bUrl = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = bUrl
      a.click()
      URL.revokeObjectURL(bUrl)
    })
}

async function exportPlanGraphDocx() {
  const token = localStorage.getItem('auth_token') || ''
  const url = `/api/subsidies/${selectedId.value}/plan-graph/export-docx`
  const r = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
  if (!r.ok) {
    const err = await r.json().catch(() => ({}))
    showSnack(err.message || 'Шаблон не загружен', 'error')
    return
  }
  const blob = await r.blob()
  const bUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = bUrl
  a.click()
  URL.revokeObjectURL(bUrl)
}

async function uploadTemplate(file: File) {
  const fd = new FormData()
  fd.append('file', file)
  const token = localStorage.getItem('auth_token') || ''
  const r = await fetch(`/api/subsidies/${selectedId.value}/plan-graph/template`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: fd,
  })
  const data = await r.json()
  if (r.ok) {
    showSnack('Шаблон загружен')
  } else {
    showSnack(data.message || 'Ошибка загрузки', 'error')
  }
}

function toggleSelect(id: number) {
  if (selectedId.value === id) { selectedId.value = null; globalSubsidyId.value = null; return }
  selectedId.value = id
  globalSubsidyId.value = id
  loadFeo(id)
  loadEvents(id)
  loadResiduals()  // 12-04
}

// Sync: global → local
watch(globalSubsidyId, (id: number | null) => {
  if (id !== null && id !== selectedId.value) {
    selectedId.value = id
    loadFeo(id)
    loadEvents(id)
    loadResiduals()  // 12-04
  } else if (id === null) {
    selectedId.value = null
    feoResiduals.value = {}  // 12-04
  }
})

async function startEdit(s: SubsidyRow) {
  if (s.contractor_id && !contractors.value.find(c => c.id === s.contractor_id)) {
    try { const f = await apiFetch<any>(`/contractors/${s.contractor_id}`); contractors.value.push(f) } catch {}
  }
  // /dashboard/charts не отдаёт agreement_text / basis_doc_*, тянем полную карточку
  // через /api/subsidies/{id} — иначе при save поля перезатрутся в NULL.
  let full: any = s
  try { full = await apiFetch<any>(`/subsidies/${s.id}`) } catch { full = s }
  editForm.value = {
    id: full.id,
    name: full.name,
    year: full.year,
    budget: full.budget,
    description: full.description || '',
    contractor_id: full.contractor_id ?? null,
    agreement_text: full.agreement_text || '',
    basis_doc_number: full.basis_doc_number || '',
    basis_doc_date: full.basis_doc_date || '',
    grantor_name: full.grantor_name || '',
    ministry_name: full.ministry_name || '',
    extra_contract_clause_1: full.extra_contract_clause_1 ?? null,
    extra_contract_clause_2: full.extra_contract_clause_2 ?? null,
    require_planned_dates: full.require_planned_dates ?? true,
    ceiling_warn_percent: full.ceiling_warn_percent ?? 90,
  }
  showEditDialog.value = true
}

async function confirmDelete(s: SubsidyRow) {
  deleteTarget.value = s
  deleteErrorLinked.value = false
  deleteErrorMsg.value = ''
  deleteImpact.value = null
  showDeleteDialog.value = true
  try {
    deleteImpact.value = await apiFetch<any>(`/subsidies/${s.id}/delete-impact`)
  } catch { /* предупреждение опционально */ }
}

async function addSubsidy() {
  saving.value = true
  try {
    const res = await apiFetch<any>('/subsidies/', {
      method: 'POST',
      body: JSON.stringify({ name: form.value.name, year: form.value.year, budget: form.value.budget, description: form.value.description || null, contractor_id: form.value.contractor_id, agreement_text: form.value.agreement_text || null, basis_doc_number: form.value.basis_doc_number || null, basis_doc_date: form.value.basis_doc_date || null })
    })
    allSubsidies.value.push({ ...res, planned: 0, paid: 0, contracted: 0, plan_schedule: 0, ordered: 0, work: 0, contracts: 0, delivered: 0, delivered_unpaid: 0 })
    showAddDialog.value = false
    form.value = { name: '', year: new Date().getFullYear(), budget: 0, description: '', contractor_id: null, agreement_text: '', basis_doc_number: '', basis_doc_date: '' }
    showSnack('Субсидия добавлена')
  } catch (e: any) {
    showSnack(e?.detail || e?.payload?.message || 'Ошибка добавления', 'error')
  } finally {
    saving.value = false
  }
}

async function updateSubsidy() {
  saving.value = true
  try {
    await apiFetch<any>(`/subsidies/${editForm.value.id}`, {
      method: 'PUT',
      body: JSON.stringify({ name: editForm.value.name, year: editForm.value.year, budget: editForm.value.budget, description: editForm.value.description || null, contractor_id: editForm.value.contractor_id, agreement_text: editForm.value.agreement_text || null, basis_doc_number: editForm.value.basis_doc_number || null, basis_doc_date: editForm.value.basis_doc_date || null, grantor_name: editForm.value.grantor_name || null, ministry_name: editForm.value.ministry_name || null, extra_contract_clause_1: editForm.value.extra_contract_clause_1 || null, extra_contract_clause_2: editForm.value.extra_contract_clause_2 || null, require_planned_dates: editForm.value.require_planned_dates, ceiling_warn_percent: editForm.value.ceiling_warn_percent ?? null })
    })
    // После save перезагружаем весь список с backend — гарантированно свежие
    // данные (включая поля которые backend мог трансформировать). Spread-merge
    // ответа PUT мог давать stale поля если SW кэшировал предыдущий GET.
    await loadAll()
    showEditDialog.value = false
    showSnack('Субсидия обновлена')
  } catch (e: any) {
    console.error('updateSubsidy failed:', e)
    showSnack(e?.detail || e?.payload?.message || 'Ошибка сохранения', 'error')
  } finally {
    saving.value = false
  }
}

async function deleteSubsidy() {
  if (!deleteTarget.value) return
  saving.value = true
  try {
    await apiFetch(`/subsidies/${deleteTarget.value.id}`, { method: 'DELETE' })
    allSubsidies.value = allSubsidies.value.filter(s => s.id !== deleteTarget.value!.id)
    if (selectedId.value === deleteTarget.value.id) selectedId.value = null
    showDeleteDialog.value = false
    showSnack('Субсидия удалена', 'warning')
  } catch (e: any) {
    if (e?.status === 409) {
      deleteErrorLinked.value = true
      deleteErrorMsg.value = e?.detail || e?.payload?.message || ''
    } else {
      showSnack(e?.detail || e?.payload?.message || 'Ошибка удаления', 'error')
    }
  } finally {
    saving.value = false
  }
}

function goToLinkedPurchases() {
  showDeleteDialog.value = false
  router.push(`/orders?subsidy_id=${deleteTarget.value?.id}`)
}

function goToLinkedContracts() {
  showDeleteDialog.value = false
  router.push(`/contracts?subsidy_id=${deleteTarget.value?.id}`)
}

async function addFeoCategory() {
  if (!selectedSubsidy.value) return
  if (feoAddPlanPairError.value) { showSnack(feoAddPlanPairError.value, 'error'); return }
  savingFeo.value = true
  try {
    const res = await apiFetch<FeoCategory>('/feo-categories/', {
      method: 'POST',
      body: JSON.stringify({
        subsidy_id: selectedSubsidy.value.id,
        parent_id: feoForm.value.parentId || null,
        name: feoForm.value.name,
        code: feoForm.value.code || null,
        appendix: feoForm.value.appendix || null,
        is_active: true,
        budget: feoForm.value.budgetAuto ? null : numOrNull(feoForm.value.budget),
        planned_quantity: feoForm.value.qtyAuto ? null : numOrNull(feoForm.value.planned_quantity),
        planned_amount: feoForm.value.amtAuto ? null : numOrNull(feoForm.value.planned_amount),
        unit: feoForm.value.unit || null,
        feo_quantity: numOrNull(feoForm.value.feo_quantity),
        feo_unit: feoForm.value.feo_unit || null,
        description: feoForm.value.description?.trim() || null,
        feo_amount: numOrNull(feoForm.value.feo_amount),
        // План zany-fluttering-mountain.md, п.1: способ расчёта плана — при 'manual_sum'
        // уходит введённая сумма, при 'planned_items' поле обнуляется (истина в позициях).
        plan_source: feoForm.value.planSource,
        manual_plan_amount: feoForm.value.planSource === 'manual_sum' ? numOrNull(feoForm.value.manual_plan_amount) : null,
      })
    })
    feoCategories.value.push(res)
    showAddFeoDialog.value = false
    feoForm.value = { parentId: null, name: '', code: '', appendix: '', budget: null, budgetAuto: false, planned_quantity: null, qtyAuto: false, planned_amount: null, amtAuto: false, unit: '', feo_quantity: null, feo_unit: '', description: '', feo_amount: '', planSource: 'planned_items', manual_plan_amount: null }
    showSnack('Направление добавлено')
    if (selectedId.value) await loadFeo(selectedId.value)
    syncFeoFilled()
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.detail || e?.message || 'Ошибка добавления направления', 'error')
  } finally {
    savingFeo.value = false
  }
}

// Update calculated_budget on the card after FEO budget changes (using tree logic)
function syncFeoFilled() {
  if (!selectedId.value) return
  // Справочный расчёт по дереву: ручное ФЭО, без него — факт, иначе план
  const total = feoTree.value.reduce((sum, root) => sum + feoEffectiveFor(root), 0)
  const s = allSubsidies.value.find(x => x.id === selectedId.value)
  if (s) {
    s.feo_filled = total > 0
    s.feo_budget_total = total
    s.calculated_budget = total
  }
}

function startFeoEdit(node: FeoNode) {
  feoEditTarget.value = node
  const autoMode = node.hasChildren && node.budget === null
  const qtyAutoMode = node.hasChildren && node.planned_quantity === null
  const amtAutoMode = node.hasChildren && node.planned_amount === null
  feoEditForm.value = {
    name: node.name,
    code: node.code || '',
    appendix: node.appendix || '',
    budget: node.budget ?? null,
    budgetAuto: autoMode,
    planned_quantity: node.planned_quantity ?? null,
    qtyAuto: qtyAutoMode,
    planned_amount: node.planned_amount ?? null,
    amtAuto: amtAutoMode,
    unit: node.unit || '',
    is_active: node.is_active,
    hasChildren: node.hasChildren,
    parent_id: node.parent_id ?? null,
    feo_quantity: node.feo_quantity ?? null,
    feo_unit: node.feo_unit || '',
    description: node.description || '',
    feo_amount: node.feo_amount ?? '',
    planSource: node.plan_source || 'planned_items',
    manual_plan_amount: node.manual_plan_amount ?? null,
  }
  showEditFeoDialog.value = true
}

// Правка 2Б (2026-08-11): из диалога редактирования категории — план не задан вовсе →
// сразу открыть форму «Добавить плановую позицию» на той же категории (переиспользует
// openAddPlannedItem, второй диалог не заводим).
function openAddPlannedItemFromCategoryEdit() {
  if (!feoEditTarget.value) return
  const categoryId = feoEditTarget.value.id
  showEditFeoDialog.value = false
  openAddPlannedItem(categoryId)
}

// Правка 2Б: план уже задан старым способом (planned_quantity/planned_amount на самой
// категории) → перенести его в именованную плановую позицию тем же путём, что и кнопка
// в панели (openConvertManualPlanToItem уже переносит кол-во/цену и после сохранения
// сам чистит эти поля категории, см. savePlannedItem/clearCategoryManualPlan выше).
// Функции нужен FeoNode (с hasChildren/depth), а feoEditTarget — просто FeoCategory,
// поэтому берём актуальный узел из дерева по id — так же, как это делает
// openEditCategoryPlan для той же категории.
function convertCategoryEditPlanToItem() {
  if (!feoEditTarget.value) return
  const node = flattenAll(feoTree.value).find(n => n.id === feoEditTarget.value!.id)
  if (!node) return
  showEditFeoDialog.value = false
  openConvertManualPlanToItem(node)
}

async function updateFeoCategory() {
  if (!feoEditTarget.value) return
  // feoEditPlanPairError больше НЕ блокирует сохранение здесь (см. комментарий у кнопки
  // «Сохранить» в шаблоне) — planned_quantity/planned_amount не редактируются в этом
  // диалоге, мисматч пары может прийти только унаследованным из БД, и сохранение
  // остальных полей категории (название, код и т.д.) обязано проходить в любом случае.
  savingFeo.value = true
  try {
    // Если parent_id изменился — вызываем move endpoint
    const oldParentId = feoEditTarget.value.parent_id ?? null
    const newParentId = feoEditForm.value.parent_id ?? null
    if (oldParentId !== newParentId) {
      const moveRes = await apiFetch<any>(`/feo-categories/${feoEditTarget.value.id}/move`, {
        method: 'PATCH', body: JSON.stringify({ parent_id: newParentId }),
      })
      if (moveRes?.warning) showSnack(moveRes.warning, 'warning')
    }
    // Обновляем остальные поля
    await apiFetch<FeoCategory>(`/feo-categories/${feoEditTarget.value.id}`, {
      method: 'PUT',
      body: JSON.stringify({
        subsidy_id: feoEditTarget.value.subsidy_id,
        parent_id: newParentId,
        name: feoEditForm.value.name,
        code: feoEditForm.value.code || null,
        appendix: feoEditForm.value.appendix || null,
        is_active: feoEditForm.value.is_active,
        budget: feoEditForm.value.budgetAuto ? null : numOrNull(feoEditForm.value.budget),
        planned_quantity: feoEditForm.value.qtyAuto ? null : numOrNull(feoEditForm.value.planned_quantity),
        planned_amount: feoEditForm.value.amtAuto ? null : numOrNull(feoEditForm.value.planned_amount),
        unit: feoEditForm.value.unit || null,
        feo_quantity: numOrNull(feoEditForm.value.feo_quantity),
        feo_unit: feoEditForm.value.feo_unit || null,
        description: feoEditForm.value.description?.trim() || null,
        feo_amount: numOrNull(feoEditForm.value.feo_amount),
        // План zany-fluttering-mountain.md, п.1: способ расчёта плана — см. комментарий
        // у того же поля в addFeoCategory выше.
        plan_source: feoEditForm.value.planSource,
        manual_plan_amount: feoEditForm.value.planSource === 'manual_sum' ? numOrNull(feoEditForm.value.manual_plan_amount) : null,
      })
    })
    showEditFeoDialog.value = false
    showSnack('Направление обновлено')
    if (selectedId.value) await loadFeo(selectedId.value)
    syncFeoFilled()
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.detail || e?.message || 'Ошибка обновления', 'error')
  } finally {
    savingFeo.value = false
  }
}

function confirmFeoDelete(node: FeoCategory) {
  feoDeleteTarget.value = node
  feoDeleteError.value = ''
  showDeleteFeoDialog.value = true
}

async function deleteFeoCategory() {
  if (!feoDeleteTarget.value) return
  savingFeo.value = true
  feoDeleteError.value = ''
  try {
    await apiFetch(`/feo-categories/${feoDeleteTarget.value.id}`, { method: 'DELETE' })
    showDeleteFeoDialog.value = false
    showSnack('Направление удалено', 'warning')
    if (selectedId.value) await loadFeo(selectedId.value)
    syncFeoFilled()
  } catch (e: any) {
    const detail = e?.detail
    if (detail && typeof detail === 'object' && detail.message) {
      feoDeleteError.value = detail.message
      feoDeleteLinkedIds.value = detail.feo_category_ids || []
    } else {
      feoDeleteError.value = typeof detail === 'string' ? detail : 'Ошибка удаления'
      feoDeleteLinkedIds.value = []
    }
  } finally {
    savingFeo.value = false
  }
}

// ── Budget history ────────────────────────────────
function openHistoryDialog(s: any) {
  historyDialogRef.value?.open(s.id, s.name)
}

// ── C4: Draft subsidies — approve + members ────────
// Кнопка видна только для черновика и только тому, у кого есть право
// subsidy.edit — тот же hasAction(), которым уже проверяется canEditFeo
// (feo_category.edit) в этом файле. Сервер (POST /approve) перепроверяет
// require_action('subsidy.edit') сам — фронт лишь скрывает лишнее.
function canApproveSubsidy(s: SubsidyRow | null): boolean {
  if (!s) return false
  return s.status === 'draft' && authStore.hasAction('subsidy.edit')
}

async function approveSubsidy(s: SubsidyRow) {
  approvingSubsidyId.value = s.id
  try {
    const updated = await apiFetch<{ status?: string; approved_by?: number | null; approved_at?: string | null }>(
      `/subsidies/${s.id}/approve`, { method: 'POST' }
    )
    const idx = allSubsidies.value.findIndex(x => x.id === s.id)
    if (idx >= 0) {
      allSubsidies.value[idx] = {
        ...allSubsidies.value[idx],
        status: updated.status ?? 'approved',
        approved_by: updated.approved_by ?? null,
        approved_at: updated.approved_at ?? null,
      }
    }
    showSnack('Субсидия утверждена')
  } catch (e: any) {
    showSnack(e.detail || 'Ошибка утверждения субсидии', 'error')
  } finally {
    approvingSubsidyId.value = null
  }
}

let _memberUsersSubsidyId: number | null = null
async function loadMemberUsers(sid: number) {
  if (memberUsersList.value.length && _memberUsersSubsidyId === sid) return
  try {
    memberUsersList.value = await apiFetch<any[]>(`/users/?subsidy_id=${sid}`)
    _memberUsersSubsidyId = sid
  } catch { memberUsersList.value = [] }
}

async function openMembersDialog(s: SubsidyRow) {
  membersSubsidy.value = s
  showMembersDialog.value = true
  loadingMembers.value = true
  try {
    membersList.value = await apiFetch<SubsidyMember[]>(`/subsidies/${s.id}/members`)
  } catch (e: any) {
    showSnack(e.detail || 'Ошибка загрузки участников', 'error')
  } finally {
    loadingMembers.value = false
  }
  loadMemberUsers(s.id)
}

async function addSubsidyMember(userId: number | null) {
  if (!userId || !membersSubsidy.value) { memberToAdd.value = null; return }
  if (membersList.value.some(m => m.user_id === userId)) { memberToAdd.value = null; return }
  addingMember.value = true
  try {
    const created = await apiFetch<SubsidyMember>(`/subsidies/${membersSubsidy.value.id}/members`, {
      method: 'POST', body: JSON.stringify({ user_id: userId }),
    })
    membersList.value.push(created)
    showSnack('Участник добавлен')
  } catch (e: any) {
    showSnack(e.detail || 'Ошибка добавления участника', 'error')
  } finally {
    addingMember.value = false
    memberToAdd.value = null
  }
}

async function removeSubsidyMember(userId: number) {
  if (!membersSubsidy.value) return
  try {
    await apiFetch(`/subsidies/${membersSubsidy.value.id}/members/${userId}`, { method: 'DELETE' })
    membersList.value = membersList.value.filter(m => m.user_id !== userId)
    showSnack('Участник удалён', 'warning')
  } catch (e: any) {
    showSnack(e.detail || 'Ошибка удаления участника', 'error')
  }
}

// ── Approvers CRUD ────────────────────────────────
async function openApproversDialog(s: SubsidyRow) {
  approversSubsidy.value = s
  showApproversDialog.value = true
  loadingApprovers.value = true
  try {
    const list = await apiFetch<SubsidyApprover[]>(`/subsidies/${s.id}/approvers`)
    approversList.value = list
    // Fix any duplicate order_nums silently
    const hasDuplicates = list.some((a, i) => a.order_num !== i + 1)
    if (hasDuplicates) await _renumberApprovers()
  } catch {
    showSnack('Ошибка загрузки согласующих', 'error')
  } finally {
    loadingApprovers.value = false
  }
}

const RESPONSIBLE_PLACEHOLDER = '_________________'

function onApproverRoleChange(role: string) {
  if (role === 'Ответственный исполнитель') {
    approverForm.value.full_name = RESPONSIBLE_PLACEHOLDER
    approverForm.value.selectedUser = null
    approverForm.value.user_id = null
  }
}

function onApproverUserSelect(user: { id: number; full_name: string } | null) {
  if (user) {
    approverForm.value.full_name = user.full_name
    approverForm.value.user_id = user.id
  } else {
    approverForm.value.full_name = ''
    approverForm.value.user_id = null
  }
}

function startAddApprover() {
  approverEditTarget.value = null
  approverForm.value = { role_name: '', full_name: '', order_num: approversList.value.length + 1, is_default: true, can_initiate: false, show_feo_path: false, user_id: null, selectedUser: null }
  loadApproverUsers()
  showApproverFormDialog.value = true
}

function startEditApprover(a: SubsidyApprover) {
  approverEditTarget.value = a
  // «Ответственный исполнитель» — роль-слот: ФИО определяется по каждой
  // закупке, а не хранится фиксированным в настройках субсидии. Даже если
  // в БД у старой записи оказалось живое ФИО (баг, почищен миграцией
  // g8h9i0j1k2l3), форма редактирования не должна его снова показывать и
  // молча сохранять обратно — иначе правка любого другого поля этой строки
  // (например order_num) вернула бы фиксированное ФИО.
  const isResponsibleRole = a.role_name === 'Ответственный исполнитель'
  const foundUser = (!isResponsibleRole && a.user_id)
    ? (approverUsersList.value.find(u => u.id === a.user_id) ?? null)
    : null
  approverForm.value = {
    role_name: a.role_name,
    full_name: isResponsibleRole ? RESPONSIBLE_PLACEHOLDER : a.full_name,
    order_num: a.order_num,
    is_default: a.is_default,
    can_initiate: a.can_initiate,
    show_feo_path: a.show_feo_path ?? false,
    user_id: isResponsibleRole ? null : (a.user_id ?? null),
    selectedUser: foundUser,
  }
  loadApproverUsers().then(() => {
    // re-resolve after load in case list was empty when dialog opened
    if (!isResponsibleRole && a.user_id && !approverForm.value.selectedUser) {
      approverForm.value.selectedUser = approverUsersList.value.find(u => u.id === a.user_id) ?? null
    }
  })
  showApproverFormDialog.value = true
}

async function saveApprover() {
  if (!approversSubsidy.value) return
  savingApprover.value = true
  const sid = approversSubsidy.value.id
  const { selectedUser: _su, ...formData } = approverForm.value
  try {
    if (approverEditTarget.value) {
      const updated = await apiFetch<SubsidyApprover>(`/subsidies/${sid}/approvers/${approverEditTarget.value.id}`, {
        method: 'PUT',
        body: JSON.stringify(formData),
      })
      const idx = approversList.value.findIndex(a => a.id === updated.id)
      if (idx >= 0) approversList.value[idx] = updated
    } else {
      const created = await apiFetch<SubsidyApprover>(`/subsidies/${sid}/approvers`, {
        method: 'POST',
        body: JSON.stringify(formData),
      })
      approversList.value.push(created)
    }
    showApproverFormDialog.value = false
    showSnack(approverEditTarget.value ? 'Обновлено' : 'Добавлено')
  } catch (e: any) {
    console.error('saveApprover failed:', e)
    showSnack('Ошибка сохранения', 'error')
  } finally {
    savingApprover.value = false
  }
}

async function deleteApprover(a: SubsidyApprover) {
  if (!approversSubsidy.value) return
  try {
    await apiFetch(`/subsidies/${approversSubsidy.value.id}/approvers/${a.id}`, { method: 'DELETE' })
    approversList.value = approversList.value.filter(x => x.id !== a.id)
    await _renumberApprovers()
    showSnack('Удалено', 'warning')
  } catch {
    showSnack('Ошибка удаления', 'error')
  }
}

async function moveApprover(index: number, direction: -1 | 1) {
  const list = approversList.value
  const swapIdx = index + direction
  if (swapIdx < 0 || swapIdx >= list.length) return
  // Swap in local list
  const tmp = list[index]
  list[index] = list[swapIdx]
  list[swapIdx] = tmp
  approversList.value = [...list]
  await _renumberApprovers()
}

async function _renumberApprovers() {
  if (!approversSubsidy.value) return
  const sid = approversSubsidy.value.id
  for (let i = 0; i < approversList.value.length; i++) {
    const a = approversList.value[i]
    if (a.order_num !== i + 1) {
      try {
        const updated = await apiFetch<SubsidyApprover>(`/subsidies/${sid}/approvers/${a.id}`, {
          method: 'PUT',
          body: JSON.stringify({ ...a, order_num: i + 1 }),
        })
        approversList.value[i] = updated
      } catch {}
    }
  }
}

// ── Template management (multi-type) ──────────────
async function openTemplateDialog(s: SubsidyRow) {
  templateSubsidy.value = s
  showTemplateDialog.value = true
  subsidyTemplatesList.value = []
  try {
    const list = await apiFetch<Array<{ doc_type: string; label: string; has_custom: boolean; has_global: boolean; render_ok?: boolean | null }>>(
      `/subsidies/${s.id}/templates`
    )
    subsidyTemplatesList.value = list
    contractTemplates.value[s.id] = list.some(t => t.has_custom)
  } catch {
    subsidyTemplatesList.value = []
  }
}

function triggerTemplateUpload(docType: string) {
  uploadingDocType.value = docType
  templateFileInputRef.value?.click()
}

async function onTemplateFileSelected(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file || !templateSubsidy.value || !uploadingDocType.value) return
  const token = localStorage.getItem('auth_token')
  const fd = new FormData()
  fd.append('file', file)
  try {
    const res = await fetch(`/api/subsidies/${templateSubsidy.value.id}/templates/${uploadingDocType.value}`, {
      method: 'PUT',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: fd,
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      const detail = err.detail || `Ошибка загрузки (HTTP ${res.status})`
      throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
    }
    showSnack('Шаблон загружен')
    await openTemplateDialog(templateSubsidy.value)
  } catch (e: any) {
    showSnack(e.message || 'Ошибка загрузки шаблона', 'error')
  } finally {
    uploadingDocType.value = null
    ;(event.target as HTMLInputElement).value = ''
  }
}

const DOC_TYPE_RU: Record<string, string> = {
  service_note_delivery: 'Служебная_записка_выдача',
  service_note_payment: 'Служебная_записка_оплата',
  service_note_procurement: 'Служебная_записка_закупка',
  service_note_advance: 'Служебная_записка_аванс',
  contract_tz: 'Договор_с_ТЗ',
  tech_spec: 'Техническое_задание',
  tech_spec_request: 'ТЗ_запрос_цен',
  tech_spec_contract: 'ТЗ_к_договору',
  contract: 'Договор',
  approval_sheet: 'Лист_согласования',
  order_purchase: 'Приказ_о_закупке',
  contract_services: 'Договор_услуг',
  // Алиасы — сохранены на бэке для старых закупок, оставлены и здесь на всякий случай
  contract_services_large: 'Договор_услуги_крупный',
  contract_services_small: 'Договор_услуги_малый',
  contract_services_food: 'Договор_услуги_питание',
  methodology_large: 'Методические_рекомендации_большие',
  methodology_small: 'Методические_рекомендации_малые',
  contract_goods_single: 'Договор_поставка_единственный',
  contract_gph_individual: 'Договор_ГПХ_физлицо',
  contract_gph_individual_rid: 'Договор_ГПХ_физлицо_РИД',
  contract_repair_vehicle: 'Договор_ремонт_ТС',
  contract_repair_framework: 'Договор_ремонт_рамочный',
  fabrikant_instruction: 'Фабрикант_инструкция',
  fabrikant_application_form: 'Фабрикант_форма_заявки',
  fabrikant_documentation: 'Фабрикант_документация',
  fabrikant_contract_project: 'Фабрикант_проект_договора',
}

async function downloadSubsidyTemplate(docType: string) {
  if (!templateSubsidy.value) return
  const token = localStorage.getItem('auth_token')
  const res = await fetch(`/api/subsidies/${templateSubsidy.value.id}/templates/${docType}/download?t=${Date.now()}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) { showSnack('Ошибка скачивания', 'error'); return }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  const ruName = DOC_TYPE_RU[docType] || docType
  a.download = `Шаблон_${ruName}_субсидия_${templateSubsidy.value.id}.docx`
  a.click()
  URL.revokeObjectURL(url)
}

async function deleteSubsidyTemplate(docType: string) {
  if (!templateSubsidy.value) return
  try {
    await apiFetch(`/subsidies/${templateSubsidy.value.id}/templates/${docType}`, { method: 'DELETE' })
    showSnack('Шаблон удалён', 'warning')
    await openTemplateDialog(templateSubsidy.value)
  } catch {
    showSnack('Ошибка удаления шаблона', 'error')
  }
}

async function downloadMarkupGuide() {
  const token = localStorage.getItem('auth_token')
  const res = await fetch('/api/documents/template-guide', {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) { showSnack('Ошибка скачивания руководства', 'error'); return }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'Инструкция_по_шаблонам.docx'
  a.click()
  URL.revokeObjectURL(url)
}

// ── Helpers ───────────────────────────────────────
function pct(part: number, total: number) {
  return total ? Math.round((part / total) * 100) : 0
}

function progressColor(p: number) {
  if (p > 100) return '#EF4444'
  if (p >= 80) return '#F59E0B'
  return '#22C55E'
}

function formatCurrency(v: number | string) {
  // API отдаёт Decimal строками — без Number() toLocaleString вернёт строку как есть, без пробелов-разрядов
  const n = Number(v) || 0
  return n.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' ₽'
}

function formatCurrencyRound(v: number | string) {
  const n = typeof v === 'string' ? parseFloat(v) : v
  return (n || 0).toLocaleString('ru-RU', { maximumFractionDigits: 0 }) + ' ₽'
}

function cardDelta(s: SubsidyRow): number {
  // Приоритет ручного бюджета субсидии (решение 14.07)
  return (s.feo_budget_total || s.budget || 0) - (s.planned || 0)
}

function formatCurrencyShort(v: number) {
  if (!v) return '0 ₽'
  if (Math.abs(v) >= 1_000_000_000) return (v / 1_000_000_000).toFixed(1) + ' млрд ₽'
  if (Math.abs(v) >= 1_000_000)     return (v / 1_000_000).toFixed(1)     + ' млн ₽'
  if (Math.abs(v) >= 1_000)         return (v / 1_000).toFixed(0)         + ' тыс ₽'
  return v.toLocaleString('ru-RU') + ' ₽'
}

function showSnack(
  text: string,
  color: ToastType = 'success',
  opts?: { actionText?: string; onAction?: () => void; duration?: number },
) {
  toast.addToast(text, color, opts)
}

// ── Contractor override ─────────────────────────
async function openContractorOverride(s: SubsidyRow) {
  if (!s.contractor_id) return
  overrideSubsidyId.value = s.id
  try {
    const data = await apiFetch<any>(`/subsidies/${s.id}/contractor-override`)
    overrideForm.value = {
      org_type: data.org_type || '',
      inn: data.inn || '',
      kpp: data.kpp || '',
      ogrn: data.ogrn || '',
      signatory_last_name: data.signatory_last_name || '',
      signatory_first_name: data.signatory_first_name || '',
      signatory_middle_name: data.signatory_middle_name || '',
      signatory_position: data.signatory_position || '',
      signatory_basis: data.signatory_basis || '',
      address: data.address || '',
      postal_address: data.postal_address || '',
      contact_person: data.contact_person || '',
      phone: data.phone || '',
      email: data.email || '',
      org_phone: data.org_phone || '',
      org_email: data.org_email || '',
      bank_details: data.bank_details || '',
      settlement_account: data.settlement_account || '',
      bank_name: data.bank_name || '',
      bik: data.bik || '',
      correspondent_account: data.correspondent_account || '',
    }
    showOverrideDialog.value = true
  } catch {
    showSnack('Ошибка загрузки реквизитов', 'error')
  }
}

async function saveContractorOverride() {
  if (!overrideSubsidyId.value) return
  savingOverride.value = true
  try {
    await apiFetch(`/subsidies/${overrideSubsidyId.value}/contractor-override`, {
      method: 'PUT',
      body: JSON.stringify(overrideForm.value),
    })
    showOverrideDialog.value = false
    showSnack('Реквизиты сохранены')
  } catch (e: any) {
    console.error('upsertContractorOverride failed:', e)
    showSnack('Ошибка сохранения', 'error')
  } finally {
    savingOverride.value = false
  }
}

// ── Events (Мероприятия) CRUD ──
async function loadEvents(subsidyId: number) {
  try {
    subsidyEvents.value = await apiFetch<EventItem[]>(`/events/?subsidy_id=${subsidyId}`)
  } catch {
    subsidyEvents.value = []
  }
}

async function addEvent() {
  if (!newEventName.value.trim() || !selectedId.value) return
  try {
    await apiFetch('/events/', {
      method: 'POST',
      body: JSON.stringify({
        subsidy_id: selectedId.value,
        name: newEventName.value.trim(),
        is_active: true,
        region: newEventRegion.value.trim() || null,
        date_from: newEventDateFrom.value || null,
        date_to: newEventDateTo.value || null,
        order_decree: newEventOrderDecree.value.trim() || null,
        planned_indicators: newEventPlannedIndicators.value.trim() || null,
        actual_indicators: newEventActualIndicators.value.trim() || null,
        media_link_1: newEventMediaLink1.value.trim() || null,
        media_link_2: newEventMediaLink2.value.trim() || null,
        media_link_3: newEventMediaLink3.value.trim() || null,
      }),
    })
    showAddEventDialog.value = false
    newEventName.value = ''
    newEventRegion.value = ''
    newEventDateFrom.value = ''
    newEventDateTo.value = ''
    newEventOrderDecree.value = ''
    newEventPlannedIndicators.value = ''
    newEventActualIndicators.value = ''
    newEventMediaLink1.value = ''
    newEventMediaLink2.value = ''
    newEventMediaLink3.value = ''
    await loadEvents(selectedId.value)
    showSnack('Мероприятие добавлено')
  } catch (e: any) {
    showSnack(e?.payload?.detail || e?.payload?.message || e?.message || 'Ошибка', 'error')
  }
}

function openEditEventDialog(ev: EventItem) {
  editEventForm.value = {
    id: ev.id,
    subsidy_id: ev.subsidy_id,
    name: ev.name,
    is_active: ev.is_active,
    region: ev.region || '',
    date_from: ev.date_from || '',
    date_to: ev.date_to || '',
    order_decree: ev.order_decree || '',
    planned_indicators: ev.planned_indicators || '',
    actual_indicators: ev.actual_indicators || '',
    media_link_1: ev.media_link_1 || '',
    media_link_2: ev.media_link_2 || '',
    media_link_3: ev.media_link_3 || '',
  }
  showEditEventDialog.value = true
}

async function saveEditEvent() {
  if (!editEventForm.value.name.trim() || !selectedId.value) return
  savingEvent.value = true
  try {
    const f = editEventForm.value
    await apiFetch(`/events/${f.id}`, {
      method: 'PUT',
      body: JSON.stringify({
        subsidy_id: f.subsidy_id,
        name: f.name.trim(),
        is_active: f.is_active,
        region: f.region || null,
        date_from: f.date_from || null,
        date_to: f.date_to || null,
        order_decree: f.order_decree || null,
        planned_indicators: f.planned_indicators || null,
        actual_indicators: f.actual_indicators || null,
        media_link_1: f.media_link_1 || null,
        media_link_2: f.media_link_2 || null,
        media_link_3: f.media_link_3 || null,
      }),
    })
    showEditEventDialog.value = false
    await loadEvents(selectedId.value)
    showSnack('Мероприятие обновлено')
  } catch (e: any) {
    showSnack(e?.payload?.detail || e?.payload?.message || e?.message || 'Ошибка', 'error')
  } finally {
    savingEvent.value = false
  }
}

async function downloadReport(subsidyId: number) {
  try {
    const token = localStorage.getItem('auth_token') || localStorage.getItem('access_token') || ''
    const resp = await fetch(`/api/reports/subsidy/${subsidyId}/xlsx`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!resp.ok) throw new Error(`Ошибка ${resp.status}`)
    const blob = await resp.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `Приложение_3_субсидия_${subsidyId}.xlsx`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e: any) {
    showSnack(e.message || 'Ошибка скачивания', 'error')
  }
}

async function deleteEvent(eventId: number) {
  if (!selectedId.value) return
  try {
    await apiFetch(`/events/${eventId}`, { method: 'DELETE' })
    await loadEvents(selectedId.value)
    showSnack('Мероприятие удалено')
  } catch (e: any) {
    showSnack(e?.payload?.detail || e?.payload?.message || e?.message || 'Ошибка', 'error')
  }
}

onMounted(() => {
  loadAll()
  loadTemplateVars()
})
</script>

<style scoped>
/* ── Layout ── */
/* Ширина страницы не ограничивается (жалоба владельца 2026-08-12: «какого хуя
   половина окна не задействована»): раньше стоял max-width: 1600px, и на широком
   мониторе правая половина экрана пустовала, хотя таблица ФЭО как раз просит
   ширины — у неё шесть числовых колонок плюс раскрывающиеся панели плана и факта. */
.subsidies-page {
  padding: 20px 24px;
  width: 100%;
  box-sizing: border-box;
}

/* ── Header ── */
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
  flex-wrap: wrap;
  gap: 12px;
}
.page-header-left  { display: flex; align-items: center; }
.page-header-right { display: flex; align-items: center; }
.page-title    { font-size: 26px; font-weight: 700; color: var(--crm-text); line-height: 1.2; }
.page-subtitle { font-size: 13px; color: var(--crm-text-muted); margin-top: 2px; }

/* ── Empty state ── */
.empty-state {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; padding: 64px 0; color: var(--crm-text-faint);
}

/* ── Subsidies grid ── */
.subsidies-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}

.subsidy-card {
  background: var(--crm-surface);
  border-radius: 12px;
  border: 2px solid var(--crm-border);
  box-shadow: 0 1px 4px var(--crm-shadow);
  padding: 18px 20px;
  cursor: grab;
  transition: transform 0.15s, box-shadow 0.15s, border-color 0.15s, opacity 0.15s;
  position: relative;
}
.subsidy-card:active {
  cursor: grabbing;
}
.subsidy-card--dragging {
  opacity: 0.4;
}
.subsidy-card--drag-over {
  outline: 2px dashed rgb(var(--v-theme-primary));
  outline-offset: -2px;
}
.subsidy-card::after {
  content: 'Нажмите для подробностей';
  position: absolute;
  bottom: 6px;
  right: 12px;
  font-size: 10px;
  color: var(--crm-text-faint);
  opacity: 0;
  transition: opacity 0.15s;
}
.subsidy-card:hover::after {
  opacity: 1;
}
.subsidy-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px var(--crm-shadow-hover);
  border-color: rgba(var(--v-theme-primary), 0.3);
}
.subsidy-card--active {
  border-color: #3B82F6;
  box-shadow: 0 0 0 4px rgba(59,130,246,0.12), 0 4px 16px var(--crm-shadow-hover);
}

/* Шапка карточки: название — крупные полупрозрачные буквы в одну строку (фон),
   кнопки управления поверх них */
.sc-title-band {
  margin-bottom: 8px;
  display: flex; flex-direction: column; align-items: center;
}
.sc-actions { display: flex; gap: 2px; align-items: center; justify-content: center; }
.sc-name {
  font-weight: 800; color: var(--crm-text-muted);
  line-height: 1.15; text-align: center;
  white-space: nowrap; overflow: hidden;
  width: 100%; user-select: none;
}
.sc-delta-chip { height: auto !important; max-width: 100%; }
.sc-delta-chip :deep(.v-chip__content) { white-space: normal; line-height: 1.35; padding-top: 3px; padding-bottom: 3px; }
.sc-budget      { font-size: 22px; font-weight: 700; color: var(--crm-text); }
.sc-budget-label{ font-size: 11px; color: var(--crm-text-faint); margin-bottom: 12px; }

.sc-mini-row { display: flex; gap: 20px; }
.sc-mini-label { font-size: 11px; color: var(--crm-text-faint); margin-bottom: 2px; }
.sc-mini-val   { font-size: 13px; font-weight: 600; }

.sc-contractor { font-size: 12px; color: var(--crm-text-faint); display: flex; align-items: center; margin-top: 6px; }
.sc-footer { display: flex; align-items: center; justify-content: space-between; margin-top: 4px; }
.sc-pct { font-size: 11px; color: var(--crm-text-faint); }
.sc-feo-badge { display: flex; align-items: center; font-size: 11px; font-weight: 600; border-radius: 10px; padding: 1px 7px; }
.sc-feo-badge--ok  { color: #16a34a; background: #dcfce7; }
.sc-feo-badge--no  { color: var(--crm-text-faint); background: var(--crm-surface-hover); }

/* ── Summary bar ── */
.summary-bar {
  display: flex; align-items: center; gap: 0;
  background: var(--crm-surface);
  border-radius: 12px;
  border: 1px solid var(--crm-border);
  box-shadow: 0 1px 4px var(--crm-shadow);
  padding: 14px 24px;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 16px;
}
.summary-item  { display: flex; flex-direction: column; gap: 2px; }
.summary-item--link { cursor: pointer; border-radius: 8px; padding: 4px 8px; margin: -4px -8px; transition: background 0.15s; }
.summary-item--link:hover { background: rgba(59,130,246,0.08); }
.summary-item--link:hover .summary-label { color: #3B82F6; }
.summary-sep   { width: 1px; height: 32px; background: var(--crm-border-strong); flex-shrink: 0; }
.summary-label { font-size: 11px; color: var(--crm-text-faint); text-transform: uppercase; letter-spacing: 0.04em; transition: color 0.15s; }
.summary-value { font-size: 15px; font-weight: 700; color: var(--crm-text); }

/* ── Detail panel ── */
.detail-panel {
  background: var(--crm-surface);
  border-radius: 12px;
  border: 1px solid var(--crm-border);
  box-shadow: 0 1px 4px var(--crm-shadow);
  padding: 20px 24px;
  margin-bottom: 20px;
}
.detail-header {
  display: flex; align-items: center;
  margin-bottom: 16px;
}
.detail-title {
  font-size: 15px; font-weight: 600; color: var(--crm-text-secondary);
}

/* Detail KPI mini-cards */
.detail-kpis {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(236px, 1fr));
  grid-auto-rows: 1fr;
  gap: 12px;
  margin-bottom: 20px;
}
.detail-kpis .kpi-card {
  /* 132px даёт запас под 2-строчное значение (самая длинная сумма в проде —
     «1 109 245 278,72 ₽», см. .kpi-value ниже) без клиппинга родительским overflow:hidden */
  min-height: 132px;
  height: 100%;
}

/* ── KPI Cards (copied from DashboardView) ── */
.kpi-card {
  border-radius: 12px;
  padding: 18px 20px;
  display: flex;
  align-items: center;
  gap: 14px;
  cursor: default;
  transition: transform 0.25s cubic-bezier(0.22, 1, 0.36, 1),
              box-shadow 0.25s cubic-bezier(0.22, 1, 0.36, 1),
              border-color 0.25s ease;
  position: relative;
  overflow: hidden;
  border: 1px solid var(--crm-border);
  background: var(--crm-surface);
  box-shadow: 0 1px 4px var(--crm-shadow);
}
.kpi-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 12px 28px var(--crm-shadow-hover);
  border-color: var(--crm-border-strong);
}
.kpi-card:active {
  transform: translateY(-1px) scale(0.985);
  transition-duration: 0.1s;
}
.kpi-card::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  opacity: 0;
  transition: opacity 0.35s ease;
  z-index: -1;
}
.kpi-card:hover::before { opacity: 1; }
.kpi-budget::before            { box-shadow: 0 0 30px rgba(59,130,246,0.15); }
.kpi-plan_schedule::before     { box-shadow: 0 0 30px rgba(245,158,11,0.15); }
.kpi-work::before              { box-shadow: 0 0 30px rgba(99,102,241,0.15); }
.kpi-ordered::before           { box-shadow: 0 0 30px rgba(59,130,246,0.15); }
.kpi-contracts::before         { box-shadow: 0 0 30px rgba(2,132,199,0.15); }
.kpi-delivered::before         { box-shadow: 0 0 30px rgba(20,184,166,0.15); }
.kpi-delivered_unpaid::before  { box-shadow: 0 0 30px rgba(239,68,68,0.15); }
.kpi-paid::before              { box-shadow: 0 0 30px rgba(34,197,94,0.15); }
.kpi-free::before              { box-shadow: 0 0 30px rgba(148,163,184,0.15); }

.kpi-icon-box {
  width: 48px;
  height: 48px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: transform 0.25s cubic-bezier(0.22, 1, 0.36, 1);
}
.kpi-card:hover .kpi-icon-box { transform: scale(1.12) rotate(-3deg); }

.kpi-budget .kpi-icon-box            { background: rgba(59,130,246,0.12);  color: #3B82F6; }
.kpi-plan_schedule .kpi-icon-box     { background: rgba(245,158,11,0.12);  color: #F59E0B; }
.kpi-work .kpi-icon-box              { background: rgba(99,102,241,0.12);  color: #6366F1; }
.kpi-ordered .kpi-icon-box           { background: rgba(59,130,246,0.12);  color: #3B82F6; }
.kpi-contracts .kpi-icon-box         { background: rgba(2,132,199,0.12);   color: #0284C7; }
.kpi-delivered .kpi-icon-box         { background: rgba(20,184,166,0.12);  color: #14B8A6; }
.kpi-delivered_unpaid .kpi-icon-box  { background: rgba(239,68,68,0.12);   color: #EF4444; }
.kpi-paid .kpi-icon-box              { background: rgba(34,197,94,0.12);   color: #22C55E; }
.kpi-free .kpi-icon-box              { background: rgba(148,163,184,0.12); color: #94A3B8; }

.kpi-budget           { border-top: 3px solid #3B82F6; }
.kpi-plan_schedule    { border-top: 3px solid #F59E0B; }
.kpi-work             { border-top: 3px solid #6366F1; }
.kpi-ordered          { border-top: 3px solid #3B82F6; }
.kpi-contracts        { border-top: 3px solid #0284C7; }
.kpi-delivered        { border-top: 3px solid #14B8A6; }
.kpi-delivered_unpaid { border-top: 3px solid #EF4444; }
.kpi-paid             { border-top: 3px solid #22C55E; }
.kpi-free             { border-top: 3px solid #94A3B8; }
.kpi-card.kpi-over { border-top-color: #EF4444; }
.kpi-over .kpi-icon-box { background: rgba(239,68,68,0.12); color: #EF4444; }

.kpi-body  { flex: 1; min-width: 0; }
.kpi-value {
  /* Чуть меньше 20px + разрешённый перенос строк — гарантия, что даже самая длинная
     сумма в проде («1 109 245 278,72 ₽», 19 символов) не будет ни обрезана,
     ни съедена многоточием, независимо от ширины карточки (проверено Playwright,
     см. отчёт в задаче: scrollHeight/scrollWidth не превышают clientHeight/clientWidth) */
  font-size: 18px;
  font-weight: 700;
  color: var(--crm-text);
  white-space: normal;
  overflow-wrap: break-word;
  word-break: break-word;
  line-height: 1.25;
}
.kpi-label {
  font-size: 12px;
  color: var(--crm-text-muted);
  margin-top: 2px;
}
@media (max-width: 599px) {
  .kpi-card {
    flex-direction: column;
    align-items: flex-start;
    gap: 6px;
    padding: 12px;
  }
  .kpi-icon-box {
    width: 34px;
    height: 34px;
    border-radius: 8px;
  }
  .kpi-icon-box :deep(.v-icon) { font-size: 18px !important; }
  .kpi-body  { width: 100%; }
  .kpi-value { font-size: 15px; white-space: normal; overflow-wrap: break-word; word-break: break-word; line-height: 1.25; }
  .kpi-label { font-size: 10px; line-height: 1.2; white-space: normal; margin-top: 1px; }
}

/* FEO section */
.detail-feo-header {
  display: flex; align-items: center;
  margin-bottom: 12px;
}
.chart-card-title {
  font-size: 14px; font-weight: 600; color: var(--crm-text-secondary);
}
.feo-empty {
  display: flex; flex-direction: column; align-items: center;
  padding: 32px 0; color: var(--crm-text-faint);
}
.feo-purchase-link {
  display: inline-flex; align-items: center;
  font-size: 11px; color: #0d9488;
  text-decoration: none; margin-top: 2px;
  cursor: pointer;
}
.feo-purchase-link:hover { text-decoration: underline; color: #0f766e; }

/* Владелец, 2026-08-13: «остановка закупки» — крупный (для контекста строки
   плотной таблицы) маркер в красной рамке, тот же приём, что и в WishesView/
   OrdersView. Сейчас всегда скрыт (v-if на stopped_at) — см. комментарии у
   FeoActualItem/FeoReqItem/FeoPurchaseFolder.stopped_at. */
.feo-stopped-marker {
  display: inline-flex;
  align-items: center;
  font-weight: 800;
  font-size: 11px;
  letter-spacing: 0.02em;
  color: #b71c1c;
  background: #fdecea;
  border: 1.5px solid #d32f2f;
  border-radius: 4px;
  padding: 2px 8px;
}

/* FEO table */
.feo-table-wrap {
  border: 1px solid var(--crm-border-strong);
  border-radius: 8px;
  overflow-x: auto;
  overflow-y: auto;
  max-height: calc(100vh - 260px);
}
.feo-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  min-width: 1100px;
}
.feo-th {
  font-size: 11px; font-weight: 600; color: var(--crm-text-muted);
  text-transform: uppercase; letter-spacing: 0.05em;
  background: var(--crm-table-header); padding: 9px 12px;
  text-align: left;
  border-bottom: 1px solid var(--crm-border-strong);
  position: sticky;
  top: 0;
  z-index: 3;
  box-shadow: inset 0 -1px 0 var(--crm-border-strong);
}
.feo-th-num { text-align: right; }
.feo-th-name { }
/* table-layout:fixed — ширину колонки задаёт th: ровно под 6 значков (100px контент + 12px паддинги) */
.feo-th-actions { width: 112px; position: sticky; right: 0; z-index: 5; }
.feo-td {
  padding: 8px 12px; border-bottom: 1px solid var(--crm-border);
  vertical-align: middle;
}
.feo-td-name { min-width: 0; }
.feo-name-inner { display: flex; align-items: center; min-width: 0; }
.feo-td-num { text-align: right; }
.feo-td-actions {
  text-align: right; white-space: nowrap; padding-left: 6px; padding-right: 6px;
  position: sticky; right: 0; z-index: 2;
  background: var(--crm-surface);
  box-shadow: inset 1px 0 0 var(--crm-border-strong);
}
/* Действия: [позиции][стрелки друг под другом][квадрат 2×2] — всегда влезает в вьюпорт */
.feo-actions-wrap { display: inline-flex; align-items: center; vertical-align: middle; }
.feo-actions-wrap .v-btn { width: 24px !important; height: 24px !important; }
.feo-actions-col { display: flex; flex-direction: column; align-items: center; }
.feo-actions-grid {
  display: inline-grid; grid-template-columns: repeat(2, 26px);
  justify-items: center; align-items: center;
}
.feo-td-actions .v-btn { background: transparent !important; }
/* sticky-колонку действий держим непрозрачной во всех состояниях строки,
   иначе при горизонтальном скролле сквозь неё видны другие колонки */
.feo-tr:hover .feo-td-actions { background: var(--crm-surface-alt); }
.feo-tr--l1 .feo-td-actions { background: var(--crm-surface-alt); }
.feo-tr--l1:hover .feo-td-actions { background: var(--crm-surface-hover); }
.feo-action-slot { display: inline-flex; width: 24px; justify-content: center; vertical-align: middle; }
.feo-tr:last-child .feo-td { border-bottom: none; }
.feo-tr:hover .feo-td { background: var(--crm-surface-alt); }
.feo-tr--l1 .feo-td { background: var(--crm-surface-alt); }
.feo-tr--l1:hover .feo-td { background: var(--crm-surface-hover); }
.feo-plan-note { font-size: 10px; line-height: 1.2; white-space: nowrap; }
/* Кликабельная заметка «в т.ч. на самом направлении N ₽» (жалоба владельца
   2026-08-13) — раскрывает панель направления, см. feoOwnDirectionPlanFor(). */
.feo-plan-note--link { cursor: pointer; text-decoration: none; }
.feo-plan-note--link:hover { text-decoration: underline; color: #0f766e; }
/* «Заметный сигнал превышения» (план zany-fluttering-mountain.md, возвращено из отката
   e0db76a) — сознательно КРУПНЕЕ и заметнее соседних .feo-plan-note (10px, тонкий текст):
   владелец жаловался, что превышение «теряется среди чисел» — эта плашка обязана читаться
   с первого взгляда, поэтому контрастный красный фон/рамка, а не просто цвет текста. */
.feo-excess-culprit {
  display: flex; align-items: center; flex-wrap: wrap; gap: 4px;
  font-size: 12px; font-weight: 700; line-height: 1.4; white-space: normal;
  color: #7f1d1d; background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.45);
  border-radius: 6px; padding: 4px 8px; margin-top: 4px; max-width: 100%;
}
.feo-residual-toggle { display: flex; gap: 2px; justify-content: flex-end; margin-top: 2px; }
.feo-residual-opt {
  font-size: 9px; font-weight: 500; text-transform: none; letter-spacing: 0;
  padding: 1px 6px; border-radius: 8px; cursor: pointer;
  color: #94a3b8; border: 1px solid transparent; user-select: none;
}
.feo-residual-opt:hover { color: #475569; }
.feo-residual-opt--active { color: #0f766e; background: rgba(20,184,166,0.12); border-color: rgba(20,184,166,0.35); }
.feo-name { font-size: 13px; font-weight: 500; color: var(--crm-text); white-space: normal; word-break: break-word; min-width: 0; flex: 1; }
.feo-name--l1 { font-weight: 700; font-size: 13px; }
.feo-name--l2 { font-weight: 600; }
.feo-name--l3 { font-weight: 400; color: var(--crm-text-secondary); }
.feo-code {
  font-size: 11px; color: var(--crm-text-muted); background: var(--crm-input-bg);
  border-radius: 4px; padding: 1px 5px; font-family: monospace; white-space: nowrap;
}
.feo-appendix { font-size: 11px; color: var(--crm-text-faint); white-space: nowrap; }
.feo-amount { font-size: 13px; font-weight: 500; color: var(--crm-text); }
.feo-amount--link { cursor: pointer; text-decoration: underline dotted; }
.feo-amount--link:hover { color: #1976d2; }
.feo-amount-empty { font-size: 13px; color: var(--crm-text-faint); }
.feo-set-hint {
  font-size: 12px; color: #3B82F6; cursor: pointer; text-decoration: underline dotted;
}
.feo-set-hint:hover { color: #2563EB; }
.feo-tree-chevron { display: inline-flex; align-items: center; }
.cursor-pointer { cursor: pointer; }

/* Inline budget edit */
.feo-amount-cell { cursor: pointer; padding: 2px 4px; border-radius: 4px; display: inline-flex; align-items: center; }
.feo-amount-cell:hover { background: rgba(59,130,246,0.07); }
.feo-amount-cell--readonly { cursor: default; }
.feo-amount-cell--readonly:hover { background: none; }
.inline-input {
  border: 1px solid rgba(59,130,246,0.7); border-radius: 4px;
  padding: 2px 6px; width: 120px; text-align: right;
  font-size: 0.875rem; outline: none; background: var(--crm-surface);
  color: var(--crm-text);
}

/* Drag & Drop */
.feo-tr[draggable="true"] { cursor: grab; }
.feo-tr[draggable="true"]:active { cursor: grabbing; }
.feo-dragging { opacity: 0.45; }
.feo-dragging .feo-td { background: var(--crm-surface-alt) !important; }
.feo-drop-target .feo-td {
  background: rgba(59, 130, 246, 0.12) !important;
  outline: 2px dashed rgba(59, 130, 246, 0.6);
  outline-offset: -2px;
}
.feo-drop-root { border-top: 2px dashed var(--crm-border); transition: background 0.15s; }
.feo-drop-root.feo-drop-target .feo-td { background: rgba(59, 130, 246, 0.08) !important; }

/* Total row */
.feo-tr--total .feo-td { background: var(--crm-surface-alt); border-top: 2px solid var(--crm-border-strong); }

/* ── Dialogs ── */
.dialog-card {}
.dialog-title {
  display: flex; align-items: center;
  font-size: 16px !important; font-weight: 600 !important;
  padding: 16px 20px !important;
}

/* Column resize handle */
.col-resize-handle {
  position: absolute;
  right: 0;
  top: 0;
  bottom: 0;
  width: 10px;
  cursor: col-resize;
  z-index: 1;
}
.col-resize-handle::before {
  content: '';
  position: absolute;
  right: 3px;
  top: 20%;
  bottom: 20%;
  width: 2px;
  background: rgba(0, 0, 0, 0.18);
  border-radius: 2px;
  transition: all 0.15s ease;
}
.v-theme--dark .col-resize-handle::before {
  background: rgba(255, 255, 255, 0.22);
}
.col-resize-handle:hover::before,
.col-resize-handle:active::before {
  right: 2px;
  top: 5%;
  bottom: 5%;
  width: 3px;
  background: rgb(59, 130, 246);
}

/* ── FEO Column Mapping ── */
.feo-imap-grid {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  padding-bottom: 4px;
}
.feo-imap-col {
  flex: 1;
  min-width: 130px;
  border: 1px dashed #ccc;
  border-radius: 6px;
  background: #fafafa;
  transition: border-color 0.15s, background 0.15s;
}
.feo-imap-col--over {
  border-color: #1976D2;
  background: rgba(25, 118, 210, 0.04);
}
.feo-imap-col--filled {
  border-style: solid;
  border-color: #43A047;
  background: #f6fff6;
}
.feo-imap-col--required {
  border-color: #ef9a9a;
  background: #fff8f8;
}
.feo-imap-col-hdr {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  color: #555;
  padding: 5px 7px 3px;
  border-bottom: 1px solid #e8e8e8;
  white-space: normal;
  word-break: break-word;
}
.feo-imap-col-body {
  padding: 5px;
  min-height: 58px;
}
.feo-imap-col-empty {
  font-size: 10px;
  color: #ccc;
  text-align: center;
  margin-top: 10px;
  font-style: italic;
}
.feo-imap-card {
  border-radius: 4px;
  background: #fff;
  border: 1px solid #e0e0e0;
  padding: 4px 6px;
  cursor: grab;
  user-select: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.feo-imap-card:hover {
  border-color: #1976D2;
  box-shadow: 0 1px 5px rgba(25, 118, 210, 0.15);
}
.feo-imap-card-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 2px;
}
.feo-imap-card-name {
  font-size: 11px;
  font-weight: 600;
  white-space: normal;
  word-break: break-word;
  flex: 1;
}
.feo-imap-card-x {
  font-size: 14px;
  line-height: 1;
  background: none;
  border: none;
  cursor: pointer;
  color: #aaa;
  padding: 0 2px;
  flex-shrink: 0;
}
.feo-imap-card-x:hover { color: #e53935; }
.feo-imap-card-x--grey { color: #bbb; }
.feo-imap-card-samples {
  font-size: 10px;
  color: #999;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 2px;
  line-height: 1.3;
}
.feo-imap-card--free {
  background: #fafafa;
}
.feo-imap-unresolved {
  border: 1px dashed #ccc;
  border-radius: 6px;
  padding: 6px 10px;
  min-height: 44px;
  transition: border-color 0.15s, background 0.15s;
}
.feo-imap-unresolved--over {
  border-color: #1976D2;
  background: rgba(25, 118, 210, 0.04);
}
.feo-imap-unresolved-label {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  color: #aaa;
  letter-spacing: 0.3px;
}
/* 12-05 F3: snapshot tree table */
.snapshot-tree-table { width: 100%; border-collapse: collapse; }
.snapshot-tree-table th, .snapshot-tree-table td { padding: 6px 8px; border-bottom: 1px solid rgba(0,0,0,0.08); font-size: 13px; }
.snapshot-tree-table .level-1 td { font-weight: 600; background: rgba(33,150,243,0.06); }
.snapshot-tree-table .level-2 td { background: rgba(33,150,243,0.03); }
.snapshot-tree-table tfoot td { background: rgba(0,0,0,0.05); padding: 8px; border-top: 2px solid rgba(0,0,0,0.15); }
.snapshot-tree-table .status-orphan td:first-child { color: rgb(180,120,0); }

/* ── KPI drill-down: подсветка дерева ФЭО по клику на карточку ── */
.kpi-card { cursor: pointer; }
.kpi-card--active {
  outline: 2px solid #fb923c; outline-offset: -2px;
  box-shadow: 0 0 0 4px rgba(251,146,60,.22);
}
.feo-kpi-hl > .feo-td, .feo-kpi-hl > td {
  background: rgba(251,146,60,.16) !important;
  animation: feo-kpi-glow 1.4s ease-in-out infinite;
}
.feo-kpi-hl > .feo-td:first-child, .feo-kpi-hl > td:first-child { border-left: 3px solid #fb923c; }
@keyframes feo-kpi-glow {
  0%, 100% { box-shadow: inset 0 0 0 9999px rgba(251,146,60,0); }
  50%      { box-shadow: inset 0 0 0 9999px rgba(251,146,60,.14); }
}
.feo-kpi-path > .feo-td:first-child { border-left: 3px solid rgba(251,146,60,.35); }
.feo-kpi-dim  > .feo-td, .feo-kpi-dim > td { opacity: .32; filter: grayscale(.5); }
.feo-kpi-dim  > .feo-td-actions { opacity: 1; filter: none; }
.feo-kpi-banner {
  display: flex; align-items: center; gap: 8px;
  font-size: 12px; color: var(--crm-text-secondary);
  background: rgba(251,146,60,.10); border: 1px solid rgba(251,146,60,.35);
  border-radius: 8px; padding: 6px 12px; margin: -8px 0 16px;
}
.feo-status-strip { display: inline-flex; align-items: center; }

/* Тёмная тема: .16/.32/.14 почти сливаются с тёмной подложкой — усиливаем контраст */
.v-theme--dark .feo-kpi-hl > .feo-td,
.v-theme--dark .feo-kpi-hl > td {
  background: rgba(251,146,60,.30) !important;
  animation-name: feo-kpi-glow-dark;
}
@keyframes feo-kpi-glow-dark {
  0%, 100% { box-shadow: inset 0 0 0 9999px rgba(251,146,60,0); }
  50%      { box-shadow: inset 0 0 0 9999px rgba(251,146,60,.22); }
}
.v-theme--dark .feo-kpi-dim > .feo-td,
.v-theme--dark .feo-kpi-dim > td { opacity: .22; }
</style>
