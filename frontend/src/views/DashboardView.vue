<template>
  <div class="crm-dashboard">

    <!-- ── Header ── -->
    <div class="dash-header">
      <div class="dash-header-left">
        <v-icon icon="mdi-view-dashboard-outline" size="34" color="#3B82F6" class="mr-3" />
        <div>
          <div class="dash-title gradient-text">Дашборд</div>
          <div class="dash-subtitle">ВСКС · Управление субсидиями · {{ selectedYear }}</div>
        </div>
      </div>
      <div class="dash-header-right">
        <v-chip-group v-model="selectedYear" mandatory class="year-chips">
          <v-chip
            v-for="year in availableYears" :key="year" :value="year"
            filter variant="elevated" color="primary" size="small"
          >{{ year }}</v-chip>
        </v-chip-group>
        <v-select
          v-model="selectedSubsidyIds"
          :items="allSubsidies.filter((s: SubsidyRow) => s.year === selectedYear)"
          item-title="name" item-value="id"
          label="Субсидии"
          variant="outlined" multiple chips clearable density="compact"
          style="min-width: 220px; max-width: 340px;"
          hide-details class="ml-3"
        />
        <v-btn
          :icon="isEditing ? 'mdi-lock-open' : 'mdi-cursor-move'"
          :variant="isEditing ? 'flat' : 'tonal'"
          :color="isEditing ? 'warning' : 'default'"
          size="small" class="ml-3"
          @click="toggleEditing"
          :title="isEditing ? 'Завершить редактирование' : 'Настроить расположение'"
        />
        <v-btn
          v-if="isEditing"
          icon="mdi-restore" variant="tonal" color="error"
          size="small" class="ml-1"
          @click="resetLayout"
          title="Сбросить расположение"
        />
        <v-btn
          icon="mdi-refresh" variant="tonal" color="primary"
          :loading="loading" @click="loadAll" size="small" class="ml-3"
        />
        <v-chip-group
          v-model="dashboardToggleMode"
          mandatory class="ml-3"
          selected-class="text-primary"
        >
          <v-chip value="classic" size="small" variant="outlined" prepend-icon="mdi-view-dashboard" style="min-height: 44px">
            Классик
          </v-chip>
          <v-chip value="radar" size="small" variant="outlined" prepend-icon="mdi-radar" style="min-height: 44px">
            Радар
          </v-chip>
        </v-chip-group>
      </div>
    </div>

    <!-- ── Quick subsidy chips ── -->
    <div v-if="yearSubsidies.length > 0" class="subsidy-chips-bar">
      <v-chip
        v-for="s in yearSubsidies" :key="s.id"
        :color="selectedSubsidyIds.includes(s.id) ? 'primary' : undefined"
        :variant="selectedSubsidyIds.includes(s.id) ? 'flat' : 'outlined'"
        size="small"
        class="subsidy-chip"
        @click="toggleSubsidyChip(s.id)"
      >
        {{ s.shortName || s.name }}
      </v-chip>
      <v-chip
        v-if="selectedSubsidyIds.length > 0"
        variant="text" size="small" class="subsidy-chip"
        prepend-icon="mdi-close-circle-outline"
        @click="selectedSubsidyIds = []"
      >Все</v-chip>
    </div>

    <!-- ── Tabs ── -->
    <v-tabs v-model="activeTab" color="primary" class="mb-4">
      <v-tab value="summary">
        <v-icon icon="mdi-view-dashboard" class="mr-2" size="18" />Сводка
      </v-tab>
      <v-tab value="analytics">
        <v-icon icon="mdi-chart-line" class="mr-2" size="18" />Аналитика
      </v-tab>
    </v-tabs>

    <v-window v-model="activeTab">
    <v-window-item value="summary">

    <!-- ── Edit mode banner ── -->
    <div v-if="isEditing" class="edit-mode-banner">
      <v-icon icon="mdi-cursor-move" size="18" class="mr-2" />
      Режим редактирования — перетаскивайте и изменяйте размер виджетов
      <v-btn size="small" variant="tonal" color="white" class="ml-4" @click="toggleEditing">Готово</v-btn>
    </div>

    <!-- ── Budget Overflow Alert (outside grid) ── -->
    <div v-if="overrunSubsidies.length > 0" class="budget-overrun-banner">
      <v-icon icon="mdi-alert" size="28" color="white" class="mr-3 flex-shrink-0" />
      <div class="overrun-content">
        <div class="overrun-title">Превышение бюджета субсидий!</div>
        <div v-for="s in overrunSubsidies" :key="s.id" class="overrun-row">
          <strong>{{ s.name }}</strong>:
          бюджет {{ formatCurrency(s.budget) }},
          НМЦД {{ formatCurrency(s.planned) }}
          <span v-if="s.contracted > s.budget">
            · законтрактовано {{ formatCurrency(s.contracted) }}
          </span>
          → <strong>перерасход {{ formatCurrency(Math.max(s.planned, s.contracted) - s.budget) }}</strong>
        </div>
        <div class="overrun-hint">Уменьшите НМЦД закупок или увеличьте размер субсидии</div>
      </div>
    </div>

    <GridLayout
      v-model:layout="layout"
      :col-num="12"
      :row-height="30"
      :is-draggable="isEditing"
      :is-resizable="isEditing"
      :margin="[12, 12]"
      :vertical-compact="true"
      :use-css-transforms="true"
      @layout-updated="onLayoutUpdated"
    >
      <!-- ── KPI Cards ── -->
      <GridItem v-bind="layout.find(l => l.i === 'kpi')" key="kpi">
        <div class="grid-widget" :class="{ 'grid-widget--editing': isEditing }">
          <div v-if="isEditing" class="widget-drag-handle">
            <v-icon icon="mdi-drag" size="16" /> KPI
          </div>
          <v-row v-if="loading" class="kpi-row" style="margin:0">
            <v-col cols="6" lg="3" v-for="n in 4" :key="'skel-'+n">
              <v-skeleton-loader type="card" height="88" class="rounded-lg" />
            </v-col>
          </v-row>
          <v-row v-else class="kpi-row" style="margin:0">
            <v-col cols="6" lg="3" v-for="card in kpiCards" :key="card.key">
              <div class="kpi-card" :class="'kpi-' + card.key" @click="handleKpiClick(card.key)">
                <div class="kpi-icon-box">
                  <v-icon :icon="card.icon" size="26" />
                </div>
                <div class="kpi-body">
                  <div class="kpi-value">{{ formatCurrency(card.value) }}</div>
                  <div class="kpi-label">{{ card.label }}</div>
                </div>
                <div class="kpi-badge" v-if="card.badge">{{ card.badge }}</div>
              </div>
            </v-col>
          </v-row>
        </div>
      </GridItem>

      <!-- ── Donut Chart ── -->
      <GridItem v-bind="layout.find(l => l.i === 'donut')" key="donut">
        <div class="grid-widget" :class="{ 'grid-widget--editing': isEditing }">
          <div v-if="isEditing" class="widget-drag-handle">
            <v-icon icon="mdi-drag" size="16" /> Структура бюджета
          </div>
          <div class="chart-card" style="height:100%;overflow:auto">
            <div class="chart-card-header">
              <template v-if="donutView === 'breakdown'">
                <v-btn icon="mdi-arrow-left" variant="text" size="x-small" class="mr-1" @click="donutView = 'donut'" />
                <v-icon size="18" class="mr-2"
                  :icon="['mdi-cash-check','mdi-file-sign','mdi-clock-outline','mdi-cash-remove'][drillDownSegment ?? 0]"
                  :color="['success','primary','warning','grey'][drillDownSegment ?? 0]" />
                <span class="chart-card-title">{{ SEGMENT_LABELS[drillDownSegment ?? 0] }}</span>
              </template>
              <template v-else>
                <v-icon icon="mdi-chart-donut" size="18" color="#3B82F6" class="mr-2" />
                <span class="chart-card-title">Структура бюджета</span>
                <span class="text-caption text-medium-emphasis ml-2">(нажмите на сегмент)</span>
              </template>
              <v-btn
                v-if="donutView === 'breakdown' && drillDownSegment !== null"
                size="x-small" variant="tonal" color="primary"
                prepend-icon="mdi-cart-outline"
                class="ml-auto"
                @click="openDonutSegmentPurchases"
              >Закупки</v-btn>
            </div>
            <Transition name="chart-fade" mode="out-in">
              <div v-if="donutView === 'donut'" key="donut">
                <apexchart v-if="donutReady" type="donut" height="270" :options="donutOptions" :series="donutSeries" />
                <div v-else class="chart-empty">
                  <v-icon icon="mdi-chart-donut" size="48" color="grey-lighten-2" />
                  <div class="text-caption text-medium-emphasis mt-2">Нет данных о бюджете</div>
                </div>
              </div>
              <div v-else key="breakdown">
                <apexchart type="bar" height="270" :options="breakdownBarOptions" :series="breakdownBarSeries" />
              </div>
            </Transition>
          </div>
        </div>
      </GridItem>

      <!-- ── Radial Gauge ── -->
      <GridItem v-bind="layout.find(l => l.i === 'radial')" key="radial">
        <div class="grid-widget" :class="{ 'grid-widget--editing': isEditing }">
          <div v-if="isEditing" class="widget-drag-handle">
            <v-icon icon="mdi-drag" size="16" /> Освоение
          </div>
          <div class="chart-card chart-card--compact" style="height:100%;overflow:auto">
            <div class="chart-card-header">
              <v-icon icon="mdi-gauge" size="18" color="#22C55E" class="mr-2" />
              <span class="chart-card-title">Освоение</span>
            </div>
            <apexchart type="radialBar" height="180" :options="radialOptions" :series="[totalUsagePct]" :key="'gauge-' + totalUsagePct" />
            <div class="radial-footer">
              <span class="text-caption text-medium-emphasis">
                {{ formatCurrencyShort(totalPaid) }} из {{ formatCurrencyShort(totalBudget) }}
              </span>
            </div>
          </div>
        </div>
      </GridItem>

      <!-- ── Pipeline ── -->
      <GridItem v-bind="layout.find(l => l.i === 'pipeline')" key="pipeline">
        <div class="grid-widget" :class="{ 'grid-widget--editing': isEditing }">
          <div v-if="isEditing" class="widget-drag-handle">
            <v-icon icon="mdi-drag" size="16" /> Закупки по этапам
          </div>
          <div class="chart-card" style="height:100%;overflow:auto">
            <div class="chart-card-header">
              <v-icon icon="mdi-stairs-up" size="18" color="#F59E0B" class="mr-2" />
              <span class="chart-card-title">Закупки по этапам</span>
              <span class="text-caption text-medium-emphasis ml-2">(нажмите для детализации)</span>
            </div>
            <div v-if="totalBudget > 0 || pipelineStages.some(s => s.amount > 0)" class="pipeline-wrap">
              <div class="pipeline-row">
                <div class="pipeline-label">
                  <span class="pipeline-dot" style="background:#9CA3AF" />
                  Бюджет
                </div>
                <div class="pipeline-bar-track">
                  <div class="pipeline-bar-fill" style="width:100%; background:#9CA3AF; opacity:0.35" />
                </div>
                <div class="pipeline-meta">
                  <span class="pipeline-amount">{{ formatCurrencyShort(totalBudget) }}</span>
                  <span class="pipeline-pct" :style="{ color: chartMuted }">100%</span>
                </div>
              </div>
              <div
                v-for="stage in pipelineStages" :key="stage.status"
                class="pipeline-row"
                @click="onPipelineClick(stage.status)"
              >
                <div class="pipeline-label">
                  <span class="pipeline-dot" :style="{ background: stage.color }" />
                  {{ stage.label }}
                </div>
                <div class="pipeline-bar-track">
                  <div
                    class="pipeline-bar-fill"
                    :style="{ width: Math.min(stage.pct, 100) + '%', background: stage.color }"
                  />
                </div>
                <div class="pipeline-meta">
                  <span class="pipeline-amount">{{ formatCurrencyShort(stage.amount) }}</span>
                  <span class="pipeline-pct" :style="{ color: stage.pct > 100 ? '#EF4444' : chartMuted }">
                    {{ stage.pct }}%
                  </span>
                </div>
              </div>
              <!-- Дополнительная метрика: поставлено но не оплачено -->
              <div
                v-if="deliveredNotPaid.amount > 0"
                class="pipeline-row"
                style="background: rgba(239,68,68,0.06); border-radius:6px; margin-top:6px"
                @click="onDeliveredNotPaidClick"
              >
                <div class="pipeline-label">
                  <span class="pipeline-dot" style="background:#EF4444" />
                  Поставлено, не оплачено
                </div>
                <div class="pipeline-bar-track">
                  <div class="pipeline-bar-fill" :style="{ width: Math.min(deliveredNotPaid.pct, 100) + '%', background: '#EF4444' }" />
                </div>
                <div class="pipeline-meta">
                  <span class="pipeline-amount" style="color:#EF4444">{{ formatCurrencyShort(deliveredNotPaid.amount) }}</span>
                  <span class="pipeline-pct" :style="{ color: chartMuted }">{{ deliveredNotPaid.pct }}%</span>
                </div>
              </div>
              <div v-if="wishesAmountForPie > 0" class="pipeline-wishes-hint">
                <v-icon icon="mdi-star-circle-outline" size="14" color="warning" class="mr-1" />
                Желания: {{ formatCurrencyShort(wishesAmountForPie) }}
                ({{ Math.round(wishesAmountForPie / (totalBudget || 1) * 100) }}% бюджета)
              </div>
            </div>
            <div v-else class="chart-empty">
              <v-icon icon="mdi-cart-outline" size="48" color="grey-lighten-2" />
              <div class="text-caption text-medium-emphasis mt-2">Нет данных о закупках</div>
            </div>
          </div>
        </div>
      </GridItem>

      <!-- ── Monthly Contracts ── -->
      <GridItem v-if="monthlyContractsRemaining.length > 0" v-bind="layout.find(l => l.i === 'monthly')" key="monthly">
        <div class="grid-widget" :class="{ 'grid-widget--editing': isEditing }">
          <div v-if="isEditing" class="widget-drag-handle">
            <v-icon icon="mdi-drag" size="16" /> Ежемесячные договоры
          </div>
          <div class="chart-card" style="height:100%;overflow:auto">
            <div class="chart-card-header">
              <v-icon icon="mdi-calendar-refresh" size="18" color="#6366F1" class="mr-2" />
              <span class="chart-card-title">Ежемесячные договоры — остаток к заказу</span>
              <span class="ml-auto font-weight-bold" style="color:#6366F1">{{ formatCurrencyShort(totalMonthlyRemaining) }}</span>
            </div>
            <div
              v-for="c in monthlyContractsRemaining" :key="c.id"
              class="pipeline-row"
              style="cursor:pointer"
              @click="openMonthlyContractDrill(c.id, c.name)"
            >
              <div class="pipeline-label">
                <span class="pipeline-dot" style="background:#6366F1" />
                {{ c.name }}
              </div>
              <div class="pipeline-bar-track">
                <div class="pipeline-bar-fill" :style="{ width: c.elapsedPct + '%', background: '#6366F1' }" />
              </div>
              <div class="pipeline-meta">
                <span class="pipeline-amount">{{ formatCurrencyShort(c.remaining) }} ост.</span>
                <span class="pipeline-pct" :style="{ color: chartMuted }">{{ c.elapsedPct }}%</span>
              </div>
            </div>
          </div>
        </div>
      </GridItem>

      <!-- ── Goods/Services Breakdown ── -->
      <GridItem v-if="pipelineByType.length > 0" v-bind="layout.find(l => l.i === 'breakdown')" key="breakdown">
        <div class="grid-widget" :class="{ 'grid-widget--editing': isEditing }">
          <div v-if="isEditing" class="widget-drag-handle">
            <v-icon icon="mdi-drag" size="16" /> Товары / Услуги
          </div>
          <div class="chart-card" style="height:100%;overflow:auto">
            <div class="chart-card-header">
              <v-icon icon="mdi-chart-box" size="18" color="#8B5CF6" class="mr-2" />
              <span class="chart-card-title">Структура закупок — Товары / Услуги</span>
            </div>
            <div class="pipeline-row">
              <div class="pipeline-label"><span class="pipeline-dot" style="background:#9CA3AF" />Бюджет</div>
              <div class="pipeline-bar-track" style="margin-bottom:3px">
                <div class="pipeline-bar-fill" style="width:100%; background:#F59E0B; opacity:0.35" />
              </div>
              <div class="pipeline-meta">{{ formatCurrencyShort(totalBudget) }}</div>
            </div>
            <div v-for="stage in pipelineByType" :key="stage.status" class="pipeline-row" style="cursor:pointer" @click="openBreakdownTypeDrill(stage.status, stage.label)">
              <div class="pipeline-label">
                <span class="pipeline-dot" :style="{ background: stage.color }" />
                {{ stage.label }}
              </div>
              <div style="flex:1; min-width:0">
                <div class="pipeline-bar-track" style="margin-bottom:3px">
                  <div class="pipeline-bar-fill" :style="{ width: Math.min(stage.goodsPct, 100) + '%', background: '#F59E0B' }" />
                </div>
                <div class="pipeline-bar-track">
                  <div class="pipeline-bar-fill" :style="{ width: Math.min(stage.servicesPct, 100) + '%', background: '#3B82F6' }" />
                </div>
              </div>
              <div class="pipeline-meta" style="flex-direction:column; align-items:flex-end; gap:2px">
                <span style="color:#F59E0B; font-size:11px">{{ formatCurrencyShort(stage.goods) }}</span>
                <span style="color:#3B82F6; font-size:11px">{{ formatCurrencyShort(stage.services) }}</span>
              </div>
            </div>
            <div class="d-flex gap-4 mt-2" style="font-size:11px; color:var(--crm-text-muted)">
              <span><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#F59E0B;margin-right:4px"></span>Товары</span>
              <span><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#3B82F6;margin-right:4px"></span>Услуги / Работы</span>
            </div>
          </div>
        </div>
      </GridItem>

      <!-- ── Subsidy Bar Chart ── -->
      <GridItem v-bind="layout.find(l => l.i === 'bar')" key="bar">
        <div class="grid-widget" :class="{ 'grid-widget--editing': isEditing }">
          <div v-if="isEditing" class="widget-drag-handle">
            <v-icon icon="mdi-drag" size="16" /> Субсидии — бюджет
          </div>
          <div class="chart-card" style="height:100%;overflow:auto">
            <div class="chart-card-header">
              <v-icon icon="mdi-chart-bar" size="18" color="#8B5CF6" class="mr-2" />
              <span class="chart-card-title">Субсидии — бюджет и исполнение</span>
            </div>
            <div v-if="barReady">
              <div class="text-caption text-medium-emphasis mb-1" style="font-size:10px">
                <v-icon icon="mdi-cursor-pointer" size="12" class="mr-1" />Нажмите на столбец для детализации по ФЭО категориям
              </div>
              <apexchart type="bar" :height="Math.max(220, filteredSubsidyStats.length * 70)" :options="barOptions" :series="barSeries" />
            </div>
            <div v-else class="chart-empty">
              <v-icon icon="mdi-chart-bar" size="48" color="grey-lighten-2" />
              <div class="text-caption text-medium-emphasis mt-2">Нет субсидий за {{ selectedYear }} год</div>
            </div>
          </div>
        </div>
      </GridItem>

      <!-- ── Recent Purchases ── -->
      <GridItem v-bind="layout.find(l => l.i === 'purchases')" key="purchases">
        <div class="grid-widget" :class="{ 'grid-widget--editing': isEditing }">
          <div v-if="isEditing" class="widget-drag-handle">
            <v-icon icon="mdi-drag" size="16" /> Последние закупки
          </div>
          <div class="chart-card" style="height:100%;overflow:auto">
            <div class="chart-card-header">
              <v-icon icon="mdi-clipboard-list-outline" size="18" color="#14B8A6" class="mr-2" />
              <span class="chart-card-title">Последние закупки</span>
              <span class="chart-link ml-auto" style="cursor:pointer" @click="goToOrders">Все →</span>
            </div>
            <div v-if="loadingPurchases" class="chart-empty">
              <v-progress-circular indeterminate size="32" color="primary" />
            </div>
            <div v-else-if="recentPurchases.length === 0" class="chart-empty">
              <v-icon icon="mdi-cart-off" size="48" color="grey-lighten-2" />
              <div class="text-caption text-medium-emphasis mt-2">Нет закупок</div>
            </div>
            <div v-else class="purchase-list">
              <div
                v-for="p in recentPurchases" :key="p.id"
                class="purchase-row"
                @click="$router.push(`/orders/${p.id}/edit`)"
              >
                <div class="purchase-num">
                  <v-icon icon="mdi-package-variant" size="16" :color="statusColorHex(p.status)" />
                </div>
                <div class="purchase-main">
                  <div class="purchase-name">{{ p.subject || p.items?.[0]?.item_name || p.item_name || 'Без названия' }}</div>
                  <div class="purchase-meta">
                    {{ p.registry_number || p.order_number || '—' }}
                    <span v-if="p.contractor_name"> · {{ p.contractor_name }}</span>
                  </div>
                </div>
                <div class="purchase-right">
                  <div class="purchase-amount">{{ formatCurrencyShort(purchaseEffectivePrice(p)) }}</div>
                  <v-chip size="x-small" :color="statusColor(p.status)" variant="flat" class="mt-1">
                    {{ statusLabel(p.status) }}
                  </v-chip>
                </div>
              </div>
            </div>
          </div>
        </div>
      </GridItem>

      <!-- ── Summary Table ── -->
      <GridItem v-bind="layout.find(l => l.i === 'table')" key="table">
        <div class="grid-widget" :class="{ 'grid-widget--editing': isEditing }">
          <div v-if="isEditing" class="widget-drag-handle">
            <v-icon icon="mdi-drag" size="16" /> Детализация субсидий
          </div>
          <div class="chart-card table-card" style="height:100%;overflow:auto">
            <div class="chart-card-header">
              <v-icon icon="mdi-table" size="18" color="#1976D2" class="mr-2" />
              <span class="chart-card-title">Детализация субсидий — {{ selectedYear }}</span>
              <div class="ml-auto d-flex align-center" style="gap: 12px;">
                <v-btn
                  variant="tonal" color="primary" size="small"
                  prepend-icon="mdi-chart-pie"
                  @click="openBreakdown('budget')"
                >
                  Аналитика
                </v-btn>
              </div>
            </div>

            <v-table density="compact" class="dash-table mt-3">
              <thead>
                <tr>
                  <th>Субсидия</th>
                  <th class="text-right">Бюджет</th>
                  <th class="text-right">Запланировано</th>
                  <th class="text-right">Заказано</th>
                  <th class="text-right">Оплачено</th>
                  <th class="text-right">Остаток</th>
                  <th style="width: 160px;" class="text-center">% освоения</th>
                  <th style="width: 60px;"></th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="s in filteredSubsidies" :key="s.id"
                  class="table-row-hover"
                  @click="openBreakdown('budget')"
                  style="cursor: pointer;"
                >
                  <td>
                    <div class="font-weight-medium">{{ s.name }}</div>
                    <div v-if="s.description" class="text-caption text-medium-emphasis">{{ s.description }}</div>
                  </td>
                  <td class="text-right font-weight-medium">{{ formatCurrency(s.budget) }}</td>
                  <td class="text-right text-warning">{{ formatCurrency(s.plan_schedule) }}</td>
                  <td class="text-right text-primary">{{ formatCurrency(s.ordered) }}</td>
                  <td class="text-right text-success">{{ formatCurrency(s.paid) }}</td>
                  <td class="text-right" :class="s.budget - s.paid >= 0 ? 'text-success' : 'text-error'">
                    {{ formatCurrency(s.budget - s.paid) }}
                  </td>
                  <td>
                    <v-progress-linear
                      :model-value="pct(s.paid, s.budget)" height="18"
                      :color="progressColor(pct(s.paid, s.budget))" rounded
                      class="gradient-progress"
                    >
                      <template #default>
                        <span class="text-caption font-weight-bold">{{ pct(s.paid, s.budget) }}%</span>
                      </template>
                    </v-progress-linear>
                  </td>
                  <td>
                    <v-btn icon="mdi-magnify" size="x-small" variant="text" @click.stop="openBreakdown('budget')" />
                  </td>
                </tr>

                <tr class="total-row">
                  <td><strong>ИТОГО</strong></td>
                  <td class="text-right"><strong>{{ formatCurrency(totalBudget) }}</strong></td>
                  <td class="text-right text-warning"><strong>{{ formatCurrency(totalPlanSchedule) }}</strong></td>
                  <td class="text-right text-primary"><strong>{{ formatCurrency(totalOrdered) }}</strong></td>
                  <td class="text-right text-success"><strong>{{ formatCurrency(totalPaid) }}</strong></td>
                  <td class="text-right" :class="totalRemaining >= 0 ? 'text-success' : 'text-error'">
                    <strong>{{ formatCurrency(totalRemaining) }}</strong>
                  </td>
                  <td>
                    <v-progress-linear
                      :model-value="totalUsagePct" height="18"
                      :color="progressColor(totalUsagePct)" rounded
                      class="gradient-progress"
                    >
                      <template #default>
                        <span class="text-caption font-weight-bold">{{ totalUsagePct }}%</span>
                      </template>
                    </v-progress-linear>
                  </td>
                  <td></td>
                </tr>
              </tbody>
            </v-table>
          </div>
        </div>
      </GridItem>

      <!-- ── Financial Plan ── -->
      <GridItem v-bind="layout.find(l => l.i === 'finplan')" key="finplan">
        <div class="grid-widget" :class="{ 'grid-widget--editing': isEditing }">
          <div v-if="isEditing" class="widget-drag-handle">
            <v-icon icon="mdi-drag" size="16" /> Финансовый план
          </div>
          <div class="chart-card" style="height:100%;overflow:auto">
            <div class="chart-card-header">
              <v-icon icon="mdi-calendar-clock" size="18" color="primary" class="mr-2" />
              <span class="chart-card-title">Финансовый план</span>
              <v-spacer />
              <v-tooltip text="Кликни по бару чтобы увидеть закупки этой группы" location="top">
                <template #activator="{ props: tip }">
                  <v-icon v-bind="tip" icon="mdi-cursor-default-click" size="14" class="ml-1" color="grey" />
                </template>
              </v-tooltip>
              <v-btn-toggle v-model="finplanGranularity" mandatory size="x-small" density="compact" class="ml-2">
                <v-btn value="month">По месяцам</v-btn>
                <v-btn value="quarter">По кварталам</v-btn>
              </v-btn-toggle>
              <v-btn size="x-small" variant="tonal" color="success" prepend-icon="mdi-microsoft-excel" @click="exportFinplanXlsx" class="ml-2">
                Excel
              </v-btn>
            </div>

            <!-- No-deadline banner -->
            <v-alert
              v-if="finplanNoDeadlineCount > 0"
              type="warning" variant="tonal" density="compact" class="mx-3 mt-2"
              :text="`${finplanNoDeadlineCount} закупок без срока исполнения — данные некорректны`"
            >
              <template #append>
                <v-btn size="x-small" variant="tonal" color="warning" @click="openFinplanDrilldown('', 'no_deadline')">
                  Показать
                </v-btn>
              </template>
            </v-alert>

            <!-- KPI текущего месяца -->
            <div v-if="finplanCurrentMonthKpi" class="d-flex gap-3 px-3 py-2">
              <v-card variant="tonal" color="warning" class="pa-2 flex-1 text-center" density="compact">
                <div class="text-caption text-medium-emphasis">План</div>
                <div class="text-body-2 font-weight-bold">{{ formatCurrencyShort(finplanCurrentMonthKpi.plan) }}</div>
              </v-card>
              <v-card variant="tonal" color="error" class="pa-2 flex-1 text-center" density="compact" style="cursor:pointer" @click="openFinplanDrilldown(finplanCurrentMonthKpi.period, 'overdue')">
                <div class="text-caption text-medium-emphasis">Накопл. долг</div>
                <div class="text-body-2 font-weight-bold">{{ formatCurrencyShort(finplanCurrentMonthKpi.overdue) }}</div>
              </v-card>
              <v-card variant="tonal" color="primary" class="pa-2 flex-1 text-center" density="compact">
                <div class="text-caption text-medium-emphasis">Итого к оплате</div>
                <div class="text-body-2 font-weight-bold">{{ formatCurrencyShort(finplanCurrentMonthKpi.plan + finplanCurrentMonthKpi.overdue) }}</div>
              </v-card>
            </div>

            <apexchart
              v-if="finplanSeries.length"
              type="bar" height="300"
              :options="finplanOptions" :series="finplanSeries"
            />
            <div v-else class="chart-empty">
              <v-icon icon="mdi-calendar-clock" size="48" color="grey-lighten-2" />
              <div class="text-caption text-medium-emphasis mt-2">Нет данных по ожидаемым выплатам</div>
            </div>
          </div>
        </div>
      </GridItem>
    </GridLayout>

    </v-window-item>

    <v-window-item value="analytics">
      <div v-if="analyticsLoading" class="d-flex justify-center py-12">
        <v-progress-circular indeterminate color="primary" size="48" />
      </div>
      <template v-else-if="analyticsData">
        <!-- KPI row -->
        <v-row class="mb-4">
          <v-col cols="6" md="3">
            <v-card variant="outlined" class="pa-4 text-center table-row-hover" style="cursor:pointer" @click="router.push('/orders?overdue=1')">
              <div class="text-h4 font-weight-bold text-error">{{ analyticsData.overdue_count }}</div>
              <div class="text-body-2 text-medium-emphasis mt-1">Просрочено</div>
              <v-icon icon="mdi-alert-circle" color="error" class="mt-1" />
            </v-card>
          </v-col>
          <v-col cols="6" md="3">
            <v-card variant="outlined" class="pa-4 text-center table-row-hover" style="cursor:pointer" @click="router.push('/orders?due_soon=1')">
              <div class="text-h4 font-weight-bold text-warning">{{ analyticsData.upcoming_deadlines.length }}</div>
              <div class="text-body-2 text-medium-emphasis mt-1">Срок до 30 дней</div>
              <v-icon icon="mdi-clock-alert" color="warning" class="mt-1" />
            </v-card>
          </v-col>
          <v-col cols="6" md="3">
            <v-card variant="outlined" class="pa-4 text-center table-row-hover" style="cursor:pointer" @click="router.push('/orders?status=paid')">
              <div class="text-h4 font-weight-bold text-success">{{ analyticsTotalPaid }}</div>
              <div class="text-body-2 text-medium-emphasis mt-1">Оплачено за год</div>
              <v-icon icon="mdi-cash-check" color="success" class="mt-1" />
            </v-card>
          </v-col>
          <v-col cols="6" md="3">
            <v-card variant="outlined" class="pa-4 text-center table-row-hover" style="cursor:pointer" @click="router.push('/orders')">
              <div class="text-h4 font-weight-bold text-primary">{{ analyticsTotalPurchases }}</div>
              <div class="text-body-2 text-medium-emphasis mt-1">Всего закупок</div>
              <v-icon icon="mdi-clipboard-list" color="primary" class="mt-1" />
            </v-card>
          </v-col>
        </v-row>

        <v-row>
          <!-- Purchase funnel -->
          <v-col cols="12" md="6">
            <v-card variant="outlined" class="pa-4">
              <div class="text-subtitle-1 font-weight-bold mb-3">Воронка закупок</div>
              <div v-for="item in analyticsData.funnel" :key="item.status" class="mb-3" style="cursor:pointer" @click="router.push(`/orders?status=${item.status}`)">
                <div class="d-flex justify-space-between mb-1">
                  <span class="text-body-2">{{ A_STATUS_LABELS[item.status] || item.status }}</span>
                  <span class="text-body-2 font-weight-medium">{{ item.count }} шт{{ item.total ? ' · ' + formatCurrencyShort(item.total) : '' }}</span>
                </div>
                <v-progress-linear
                  :model-value="analyticsFunnelPct(item.total)"
                  :color="A_STATUS_COLORS[item.status] || 'grey'"
                  rounded height="14" bg-color="grey-lighten-3"
                />
              </div>
            </v-card>
          </v-col>

          <!-- Purchase method distribution -->
          <v-col cols="12" md="3">
            <v-card variant="outlined" class="pa-4" style="height:100%">
              <div class="text-subtitle-1 font-weight-bold mb-3">Способы закупки</div>
              <div v-for="(cnt, method) in analyticsData.method_distribution" :key="method" class="mb-3" style="cursor:pointer" @click="router.push(`/orders?method=${method}`)">
                <div class="d-flex justify-space-between mb-1">
                  <span class="text-body-2">{{ A_METHOD_LABELS[method] || method }}</span>
                  <span class="text-body-2 font-weight-medium">{{ cnt }}</span>
                </div>
                <v-progress-linear
                  :model-value="analyticsTotalPurchases > 0 ? (cnt / analyticsTotalPurchases) * 100 : 0"
                  :color="A_METHOD_COLORS[method] || 'blue-grey'"
                  rounded height="14" bg-color="grey-lighten-3"
                />
              </div>
            </v-card>
          </v-col>

          <!-- Upcoming deadlines -->
          <v-col cols="12" md="3">
            <v-card variant="outlined" class="pa-4" style="height:100%">
              <div class="text-subtitle-1 font-weight-bold mb-3">
                Ближайшие сроки
                <v-chip size="x-small" color="warning" variant="tonal" class="ml-1">{{ analyticsData.upcoming_deadlines.length }}</v-chip>
              </div>
              <div v-if="analyticsData.upcoming_deadlines.length === 0" class="text-caption text-medium-emphasis">
                Нет сроков в ближайшие 30 дней
              </div>
              <div v-for="d in analyticsData.upcoming_deadlines" :key="d.id" class="analytics-deadline-item">
                <div class="d-flex align-center justify-space-between">
                  <router-link :to="`/orders/${d.id}`" class="text-body-2 analytics-deadline-link">
                    {{ d.name || `Закупка #${d.purchase_number || d.id}` }}
                  </router-link>
                  <v-chip :color="analyticsDeadlineColor(d.execution_term)" size="x-small" variant="tonal">
                    {{ analyticsFormatDate(d.execution_term) }}
                  </v-chip>
                </div>
              </div>
            </v-card>
          </v-col>
        </v-row>

        <!-- Plan vs Fact -->
        <v-row class="mt-4">
          <v-col cols="12">
            <v-card variant="outlined" class="pa-4">
              <div class="text-subtitle-1 font-weight-bold mb-3">План / Факт по субсидиям</div>
              <v-table density="compact">
                <thead>
                  <tr>
                    <th>Субсидия</th>
                    <th class="text-right">НМЦД (план)</th>
                    <th class="text-right">Законтрактовано</th>
                    <th class="text-right">Оплачено</th>
                    <th>Исполнение</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="pf in analyticsData.plan_fact" :key="pf.subsidy">
                    <td class="text-body-2">{{ pf.subsidy }}</td>
                    <td class="text-right text-body-2">{{ formatCurrencyShort(pf.plan) }}</td>
                    <td class="text-right text-body-2">{{ formatCurrencyShort(pf.contracted) }}</td>
                    <td class="text-right text-body-2 text-success">{{ formatCurrencyShort(pf.paid) }}</td>
                    <td style="min-width:150px">
                      <v-progress-linear
                        v-if="pf.plan > 0"
                        :model-value="Math.min((pf.contracted / pf.plan) * 100, 100)"
                        color="blue" height="12" rounded bg-color="grey-lighten-3"
                        :title="`Законтрактовано: ${Math.round((pf.contracted / pf.plan)*100)}%`"
                      />
                    </td>
                  </tr>
                  <tr v-if="analyticsData.plan_fact.length === 0">
                    <td colspan="5" class="text-center text-medium-emphasis text-caption pa-4">Нет данных</td>
                  </tr>
                </tbody>
              </v-table>
            </v-card>
          </v-col>
        </v-row>

        <!-- Monthly paid + Top contractors -->
        <v-row class="mt-4">
          <v-col cols="12" md="7">
            <v-card variant="outlined" class="pa-4">
              <div class="text-subtitle-1 font-weight-bold mb-3">Ежемесячные оплаты</div>
              <div v-if="analyticsData.monthly_payments.length === 0" class="text-caption text-medium-emphasis text-center py-4">
                Нет данных об оплатах
              </div>
              <div v-else class="analytics-monthly-chart">
                <div v-for="m in analyticsData.monthly_payments" :key="`${m.year}-${m.month}`" class="analytics-bar-col">
                  <div class="analytics-bar-label">{{ formatCurrencyShort(m.total) }}</div>
                  <div class="analytics-bar-wrap">
                    <div class="analytics-bar-fill" :style="{ height: analyticsBarHeight(m.total) + '%' }" />
                  </div>
                  <div class="analytics-bar-x">{{ A_MONTH_NAMES[m.month - 1].slice(0,3) }}<br/>{{ m.year }}</div>
                </div>
              </div>
            </v-card>
          </v-col>

          <v-col cols="12" md="5">
            <v-card variant="outlined" class="pa-4">
              <div class="text-subtitle-1 font-weight-bold mb-3">Топ контрагентов по сумме</div>
              <div v-for="(c, i) in analyticsData.top_contractors" :key="c.name" class="mb-2">
                <div class="d-flex justify-space-between mb-1">
                  <span class="text-body-2 text-truncate" style="max-width:200px" :title="c.name">
                    {{ i + 1 }}. {{ c.name }}
                  </span>
                  <span class="text-body-2 font-weight-medium ml-2 flex-shrink-0">{{ formatCurrencyShort(c.total) }}</span>
                </div>
                <v-progress-linear
                  :model-value="analyticsTopPct(c.total)"
                  color="indigo" rounded height="10" bg-color="grey-lighten-3"
                />
              </div>
              <div v-if="analyticsData.top_contractors.length === 0" class="text-caption text-medium-emphasis text-center py-4">
                Нет данных
              </div>
            </v-card>
          </v-col>
        </v-row>
      </template>
    </v-window-item>
    </v-window>

    <BudgetDrillDownDialog
      v-model="showBreakdownDialog"
      :subsidies="drillDialogSubsidies.length ? drillDialogSubsidies : filteredSubsidies"
      :metric="breakdownMetric"
      :all-purchases="allPurchases"
      @update:modelValue="v => { if (!v) drillDialogSubsidies.value = [] }"
    />

    <!-- Status pie drill-down — delegated to PurchasesDrillDialog (statusDrillDialog/statusDrillStatus kept for computed) -->

    <!-- Generic PurchasesDrillDialog — used by donut/monthly/breakdown/KPI -->
    <PurchasesDrillDialog
      :visible="purchasesDrillVisible"
      :title="purchasesDrillTitle"
      :title-icon="purchasesDrillIcon"
      :title-color="purchasesDrillColor"
      :purchases="purchasesDrillItems"
      :filename-prefix="purchasesDrillPrefix"
      :show-framework-seq="purchasesDrillFramework"
      @close="closePurchasesDrill"
      @row-click="purchasesDrillRowClick"
    />

    <!-- Donut drill-down dialog — purchases by segment -->
    <!-- NOTE: drillDownDialog is still used internally by donut breakdown bar click (opens BudgetDrillDownDialog).
         For direct segment clicks we now use purchasesDrillVisible via openPurchasesDrill. -->
    <v-dialog v-model="drillDownDialog" max-width="500" style="display:none" />

    <!-- ── Financial Plan Drill-Down Dialog ── -->
    <v-dialog v-model="finplanDrilldown.show" max-width="1100" scrollable>
      <v-card>
        <v-card-title class="d-flex align-center pa-3">
          <v-icon icon="mdi-format-list-bulleted" class="mr-2" />
          <span>{{ finplanDrilldownTitle }} — {{ finplanDrilldown.period || 'все периоды' }}</span>
          <v-spacer />
          <v-chip size="small" variant="tonal" :color="finplanDrilldownChipColor">
            {{ finplanDrilldown.items.length }} закупок · Σ {{ finplanDrilldownTotal.toLocaleString('ru-RU') }} ₽
          </v-chip>
          <v-btn v-if="finplanDrilldown.category !== 'no_deadline'" size="small" variant="tonal" color="success" prepend-icon="mdi-microsoft-excel" @click="exportFinplanDrilldownXlsx" class="ml-2">
            Excel
          </v-btn>
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-2" @click="finplanDrilldown.show = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pa-0">
          <v-progress-linear v-if="finplanDrilldown.loading" indeterminate />
          <v-table density="compact" v-else-if="finplanDrilldown.items.length">
            <thead>
              <tr>
                <th>№</th>
                <th>Предмет</th>
                <th>Контрагент</th>
                <th>Дата обязательства</th>
                <th>Статус</th>
                <th class="text-right">Сумма</th>
                <th class="text-right">Оплачено</th>
                <th class="text-right">Остаток</th>
                <th>Метки</th>
                <th>Понадобится</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in finplanDrilldown.items" :key="row.id"
                  :style="{ cursor: 'pointer', opacity: row.is_likely_needed === false ? 0.55 : 1 }"
                  @click="goToOrder(row.id)">
                <td><code>{{ row.purchase_number || row.id }}</code></td>
                <td>
                  <div>{{ row.subject }}</div>
                  <div v-if="row.stage_label" class="text-caption text-medium-emphasis">{{ row.stage_label }}</div>
                </td>
                <td>{{ row.contractor_name }}</td>
                <td>{{ formatDate(row.obligation_date || row.expected_date) }}</td>
                <td><v-chip size="x-small" variant="tonal">{{ STATUS_LABELS_FINPLAN[row.status] || row.status }}</v-chip></td>
                <td class="text-right font-weight-medium">{{ (row.amount || 0).toLocaleString('ru-RU') }} ₽</td>
                <td class="text-right">{{ (row.paid_amount || 0).toLocaleString('ru-RU') }} ₽</td>
                <td class="text-right">{{ (row.remaining || 0).toLocaleString('ru-RU') }} ₽</td>
                <td>
                  <v-chip v-if="row.is_overdue" size="x-small" color="error" variant="tonal" class="mr-1">
                    Просрочено
                  </v-chip>
                  <v-chip v-if="row.missing_deadline" size="x-small" color="warning" variant="tonal" class="mr-1">
                    Нет срока
                  </v-chip>
                  <v-chip v-if="row.is_prepayment" size="x-small" color="info" variant="tonal">
                    Предоплата
                  </v-chip>
                </td>
                <td @click.stop>
                  <v-checkbox
                    :model-value="row.is_likely_needed !== false"
                    density="compact" hide-details
                    @update:model-value="patchIsLikelyNeeded(row, $event)"
                  />
                </td>
              </tr>
            </tbody>
          </v-table>
          <div v-else class="text-medium-emphasis text-center py-6">Нет закупок в этой группе</div>
        </v-card-text>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useTheme } from 'vuetify'
import BudgetDrillDownDialog from '@/components/BudgetDrillDownDialog.vue'
import PurchasesDrillDialog from '@/components/PurchasesDrillDialog.vue'
import StatusPieWithWishes from '@/components/StatusPieWithWishes.vue'
import { apiFetch } from '@/api'
import { useGlobalSubsidy } from '@/composables/useGlobalSubsidy'
import { useAnimatedNumber } from '@/composables/useAnimatedNumber'
import { GridLayout, GridItem } from 'grid-layout-plus'
import { useDashboardLayout } from '@/composables/useDashboardLayout'
import { useDashboardMode } from '@/composables/useDashboardMode'

const { globalSubsidyId } = useGlobalSubsidy()
const { layout, isEditing, toggleEditing, resetLayout, onLayoutUpdated } = useDashboardLayout()
const { setMode } = useDashboardMode()
const dashboardToggleMode = ref<'classic' | 'radar'>('classic')
watch(dashboardToggleMode, (v) => {
  if (v === 'classic' || v === 'radar') setMode(v)
})

const theme = useTheme()
const router = useRouter()
const route = useRoute()
const loading = ref(false)
const loadingPurchases = ref(false)
const selectedYear = ref(new Date().getFullYear())
const selectedSubsidyIds = ref<number[]>([])
const showBreakdownDialog = ref(false)
const activeTab = ref((route.query.tab as string) || 'summary')
watch(activeTab, (tab) => router.replace({ query: { ...route.query, tab } }))

// ── Data ──────────────────────────────────────────
interface SubsidyRow {
  id: number; name: string; shortName: string; description: string; year: number
  budget: number; contracted: number; paid: number; planned: number
  plan_schedule: number; ordered: number
}

const allSubsidies    = ref<SubsidyRow[]>([])
const allPurchases    = ref<any[]>([])
const statusCounts    = ref<Record<string, number>>({})
const breakdownMetric = ref('budget')

// Dark mode aware colors for ApexCharts
const isDark = computed(() => theme.global.name.value === 'dark')
const chartText = computed(() => isDark.value ? '#CBD5E1' : '#374151')
const chartMuted = computed(() => isDark.value ? '#94A3B8' : '#6B7280')
const chartGrid = computed(() => isDark.value ? 'rgba(255,255,255,0.08)' : '#E2E8F0')
const chartTrack = computed(() => isDark.value ? '#334155' : '#E2E8F0')

// ── Derived ──────────────────────────────────────
const availableYears = computed(() =>
  [...new Set(allSubsidies.value.map(s => s.year))].sort((a, b) => b - a)
)

const yearSubsidies = computed((): SubsidyRow[] =>
  allSubsidies.value.filter((s: SubsidyRow) => s.year === selectedYear.value)
)

// Sync: global → local
watch(globalSubsidyId, (id: number | null) => {
  if (id !== null) selectedSubsidyIds.value = [id]
  else selectedSubsidyIds.value = []
}, { immediate: true })

// Clear selection when year changes to avoid stale IDs from other year
watch(selectedYear, () => { selectedSubsidyIds.value = [] })

// Sync: local → global (only single selection)
watch(selectedSubsidyIds, (ids: number[]) => {
  if (ids.length === 1) globalSubsidyId.value = ids[0]
  else if (ids.length === 0) globalSubsidyId.value = null
})

function toggleSubsidyChip(id: number) {
  const idx = selectedSubsidyIds.value.indexOf(id)
  if (idx >= 0) {
    selectedSubsidyIds.value = selectedSubsidyIds.value.filter((x: number) => x !== id)
  } else {
    selectedSubsidyIds.value = [...selectedSubsidyIds.value, id]
  }
}

const filteredSubsidies = computed(() => {
  let res = allSubsidies.value.filter(s => s.year === selectedYear.value)
  if (selectedSubsidyIds.value.length > 0)
    res = res.filter(s => selectedSubsidyIds.value.includes(s.id))
  return res
})

const filteredSubsidyStats = computed(() => filteredSubsidies.value)

// Recent purchases filtered to selected subsidies
const recentPurchases = computed(() => {
  const subsidyIds = filteredSubsidies.value.map(s => s.id)
  return allPurchases.value
    .filter(p => subsidyIds.length === 0 || subsidyIds.includes(p.subsidy_id))
    .slice(0, 8)
})

const totalBudget       = computed(() => filteredSubsidies.value.reduce((s, x) => s + x.budget, 0))
const totalContracted   = computed(() => filteredSubsidies.value.reduce((s, x) => s + x.contracted, 0))
const totalPaid         = computed(() => filteredSubsidies.value.reduce((s, x) => s + x.paid, 0))
const totalPlanned      = computed(() => filteredSubsidies.value.reduce((s, x) => s + x.planned, 0))
const totalPlanSchedule = computed(() => filteredSubsidies.value.reduce((s, x) => s + x.plan_schedule, 0))
const totalOrdered      = computed(() => filteredSubsidies.value.reduce((s, x) => s + x.ordered, 0))
const totalRemaining    = computed(() => totalBudget.value - totalPaid.value)
const totalUsagePct   = computed(() => pct(totalPaid.value, totalBudget.value))

// Animated KPI values
const animBudget       = useAnimatedNumber(totalBudget)
const animPlanSchedule = useAnimatedNumber(totalPlanSchedule)
const animOrdered      = useAnimatedNumber(totalOrdered)
const animPaid         = useAnimatedNumber(totalPaid)

const overrunSubsidies = computed(() =>
  filteredSubsidies.value.filter(s => s.planned > s.budget || s.contracted > s.budget)
)

// ── KPI Cards ─────────────────────────────────────
const kpiCards = computed(() => [
  {
    key: 'budget', label: 'Общий бюджет', value: animBudget.value,
    icon: 'mdi-bank-outline',
    badge: `${filteredSubsidies.value.length} субс.`
  },
  {
    key: 'plan_schedule', label: 'Запланировано', value: animPlanSchedule.value,
    icon: 'mdi-calendar-clock',
    badge: `${pct(totalPlanSchedule.value, totalBudget.value)}%`
  },
  {
    key: 'ordered', label: 'Заказано', value: animOrdered.value,
    icon: 'mdi-cart-check',
    badge: `${pct(totalOrdered.value, totalBudget.value)}%`
  },
  {
    key: 'paid', label: 'Оплачено', value: animPaid.value,
    icon: 'mdi-cash-check',
    badge: `${pct(totalPaid.value, totalBudget.value)}%`
  },
])

// ── Chart: Donut ──────────────────────────────────
const donutReady = computed(() => totalBudget.value > 0)

const donutSeries = computed(() => {
  const paid       = totalPaid.value
  const ordered    = Math.max(0, totalOrdered.value - paid)         // заказано (договор), не оплачено
  const planned    = totalPlanSchedule.value                        // запланировано (confirmed+wip)
  const free       = Math.max(0, totalBudget.value - totalOrdered.value - planned)
  return [paid, ordered, planned, free]
})

const SEGMENT_LABELS  = ['Оплачено', 'Заказано', 'Запланировано', 'Свободно']
const SEGMENT_COLORS  = ['#22C55E', '#3B82F6', '#F59E0B', '#94A3B8']
const SEGMENT_METRICS = ['paid', 'ordered', 'budget', 'budget'] // maps to BudgetDrillDownDialog metric

const drillDownDialog  = ref(false)
const drillDownSegment = ref<number | null>(null)
const donutView        = ref<'donut' | 'breakdown'>('donut')

// Drill-down: scoped dialog subsidiaries
const drillDialogSubsidies = ref<any[]>([])

// Status pie drill-down
const statusDrillDialog = ref(false)
const statusDrillStatus = ref('')

// Generic purchases drill dialog (reusable)
const purchasesDrillVisible = ref(false)
const purchasesDrillTitle   = ref('Закупки')
const purchasesDrillIcon    = ref('mdi-cart-outline')
const purchasesDrillColor   = ref('primary')
const purchasesDrillItems   = ref<any[]>([])
const purchasesDrillPrefix  = ref('purchases')
const purchasesDrillFramework = ref(false)

function openPurchasesDrill(
  title: string,
  items: any[],
  opts?: { icon?: string; color?: string; prefix?: string; framework?: boolean }
) {
  purchasesDrillTitle.value     = title
  purchasesDrillItems.value     = items
  purchasesDrillIcon.value      = opts?.icon   ?? 'mdi-cart-outline'
  purchasesDrillColor.value     = opts?.color  ?? 'primary'
  purchasesDrillPrefix.value    = opts?.prefix ?? 'purchases'
  purchasesDrillFramework.value = opts?.framework ?? false
  purchasesDrillVisible.value   = true
}

function closePurchasesDrill() { purchasesDrillVisible.value = false }

function purchasesDrillRowClick(id: number) {
  purchasesDrillVisible.value = false
  router.push(`/orders/${id}/edit`)
}


function getStatusPurchases(status: string): any[] {
  const subsidyIds = filteredSubsidies.value.map((s: any) => s.id)
  return allPurchases.value.filter((p: any) => {
    if (subsidyIds.length > 0 && !subsidyIds.includes(p.subsidy_id)) return false
    return p.status === status
  })
}

// Cumulative funnel filter: status И все статусы дальше по воронке.
// Для бара pipeline бара 'Заказано' включает (ordered + delivered + paid).
function getCumulativeStagePurchases(status: string): any[] {
  const idx = PIPELINE_ORDER.indexOf(status)
  if (idx < 0) return getStatusPurchases(status)
  const stages = new Set(PIPELINE_ORDER.slice(idx))
  const subsidyIds = filteredSubsidies.value.map((s: any) => s.id)
  return allPurchases.value.filter((p: any) => {
    if (subsidyIds.length > 0 && !subsidyIds.includes(p.subsidy_id)) return false
    return stages.has(p.status)
  })
}

const statusDrillPurchases = computed(() => getStatusPurchases(statusDrillStatus.value))

// Status amounts for tooltip
const filteredStatusAmounts = computed(() => {
  const subsidyIds = filteredSubsidies.value.map((s: any) => s.id)
  const amounts: Record<string, number> = {}
  for (const p of allPurchases.value) {
    if (subsidyIds.length > 0 && !subsidyIds.includes(p.subsidy_id)) continue
    amounts[p.status] = (amounts[p.status] || 0) + purchaseEffectivePrice(p)
  }
  return amounts
})

// Purchases filtered by donut segment
const donutSegmentPurchases = computed(() => {
  const seg = drillDownSegment.value
  if (seg === null) return []
  const subsidyIds = filteredSubsidies.value.map((s: any) => s.id)
  return allPurchases.value.filter((p: any) => {
    if (subsidyIds.length > 0 && !subsidyIds.includes(p.subsidy_id)) return false
    if (seg === 0) return p.status === 'paid'
    if (seg === 1) return ['contracted', 'ordered', 'delivered'].includes(p.status)
    if (seg === 2) return ['plan_schedule', 'confirmed', 'work_in_progress'].includes(p.status)
    if (seg === 3) return !['paid', 'contracted', 'ordered', 'delivered', 'plan_schedule', 'confirmed', 'work_in_progress'].includes(p.status)
    return false
  })
})

function openDonutSegmentPurchases() {
  const seg = drillDownSegment.value
  if (seg === null) return
  const label = SEGMENT_LABELS[seg] || 'Сегмент'
  const icons  = ['mdi-cash-check','mdi-file-sign','mdi-clock-outline','mdi-cash-remove']
  const colors = ['success','primary','warning','grey']
  openPurchasesDrill(label, donutSegmentPurchases.value, {
    icon: icons[seg],
    color: colors[seg],
    prefix: `donut_${label.toLowerCase()}`,
  })
}

const drillDownRows = computed(() => {
  if (drillDownSegment.value === null) return []
  return filteredSubsidies.value.map(s => {
    const values = [
      s.paid,
      Math.max(0, s.ordered - s.paid),
      s.plan_schedule,
      Math.max(0, s.budget - s.ordered - s.plan_schedule),
    ]
    return { name: s.name, value: values[drillDownSegment.value!] }
  }).filter(r => r.value > 0).sort((a, b) => b.value - a.value)
})

const breakdownBarSeries = computed(() => [{
  name: drillDownSegment.value !== null ? SEGMENT_LABELS[drillDownSegment.value] : '',
  data: drillDownRows.value.map(r => r.value)
}])

const breakdownBarOptions = computed(() => ({
  chart: {
    type: 'bar', background: 'transparent', toolbar: { show: false },
    animations: { speed: 350 },
    theme: { mode: isDark.value ? 'dark' : 'light' },
    events: {
      dataPointSelection: (_e: any, _ctx: any, config: any) => {
        const row = drillDownRows.value[config.dataPointIndex]
        if (!row) return
        const sub = filteredSubsidies.value.find((s: any) => s.name === row.name)
        if (sub) {
          drillDialogSubsidies.value = [sub]
          breakdownMetric.value = SEGMENT_METRICS[drillDownSegment.value ?? 0]
          showBreakdownDialog.value = true
        }
      }
    }
  },
  colors: [drillDownSegment.value !== null ? SEGMENT_COLORS[drillDownSegment.value] : '#3B82F6'],
  plotOptions: { bar: { horizontal: true, barHeight: '55%', borderRadius: 4, borderRadiusApplication: 'end' } },
  dataLabels: {
    enabled: true,
    formatter: (v: number) => formatCurrencyShort(v),
    style: { fontSize: '10px', colors: [chartText.value] }
  },
  xaxis: {
    categories: drillDownRows.value.map(r => truncate(r.name, 22)),
    labels: { formatter: (v: number) => formatCurrencyShort(v), style: { colors: chartMuted.value, fontSize: '10px' } }
  },
  yaxis: { labels: { style: { colors: chartText.value, fontSize: '11px' } } },
  grid: { borderColor: chartGrid.value },
  tooltip: {
    theme: isDark.value ? 'dark' : 'light',
    y: { formatter: (v: number) => formatCurrency(v) },
    custom: () => `<div style="padding:6px 10px;font-size:12px">Нажмите для детализации →</div>`
  }
}))

const donutOptions = computed(() => ({
  chart: {
    type: 'donut', background: 'transparent', toolbar: { show: false },
    animations: { speed: 500 },
    theme: { mode: isDark.value ? 'dark' : 'light' },
    events: {
      dataPointSelection: (_e: any, _ctx: any, config: any) => {
        const idx = config.dataPointIndex
        drillDownSegment.value = idx
        donutView.value = 'breakdown'
      }
    }
  },
  colors: ['#22C55E', '#3B82F6', '#F59E0B', '#94A3B8'],
  labels: SEGMENT_LABELS,
  legend: { position: 'bottom', fontSize: '12px', labels: { colors: chartText.value } },
  dataLabels: {
    enabled: true,
    style: { fontSize: '11px', colors: ['#fff', '#fff', '#fff', '#374151'] },
    dropShadow: { enabled: false }
  },
  plotOptions: {
    pie: {
      donut: {
        size: '68%',
        labels: {
          show: true,
          total: {
            show: true,
            label: 'Бюджет',
            color: chartMuted.value,
            fontSize: '13px',
            formatter: () => formatCurrencyShort(totalBudget.value)
          },
          value: {
            show: true,
            fontSize: '18px',
            fontWeight: '600',
            color: chartText.value,
            formatter: (v: string) => formatCurrencyShort(Number(v))
          },
          name: { show: true, color: chartMuted.value }
        }
      }
    }
  },
  tooltip: { y: { formatter: (v: number) => formatCurrency(v) } }
}))

// ── Chart: Radial ─────────────────────────────────
const radialOptions = computed(() => ({
  chart: { type: 'radialBar', background: 'transparent', toolbar: { show: false }, theme: { mode: isDark.value ? 'dark' : 'light' } },
  colors: [totalUsagePct.value >= 90 ? '#EF4444' : totalUsagePct.value >= 70 ? '#F59E0B' : '#22C55E'],
  plotOptions: {
    radialBar: {
      startAngle: -135,
      endAngle: 135,
      hollow: { size: '60%', background: 'transparent' },
      track: { background: chartTrack.value, strokeWidth: '100%' },
      dataLabels: {
        name: {
          show: true, offsetY: -10, color: chartMuted.value,
          fontSize: '13px', fontWeight: '400'
        },
        value: {
          show: true, color: chartText.value,
          fontSize: '30px', fontWeight: '700',
          formatter: (val: number) => `${val}%`
        }
      }
    }
  },
  labels: ['Освоение'],
  fill: {
    type: 'gradient',
    gradient: {
      shade: 'light', type: 'horizontal',
      gradientToColors: [totalUsagePct.value >= 90 ? '#B91C1C' : '#3B82F6'],
      stops: [0, 100]
    }
  }
}))

// ── Chart: Status Pie ─────────────────────────────
const STATUS_LABELS: Record<string, string> = {
  wishes: 'Желания', plan_schedule: 'План-график',
  planned: 'Планируется', confirmed: 'Подтверждено',
  in_progress: 'Ведётся работа', work_in_progress: 'В работе',
  contracted: 'Договор', ordered: 'Заказано', delivered: 'Поставлено', paid: 'Оплачено'
}

// Status counts filtered by selected subsidies
const filteredStatusCounts = computed(() => {
  const subsidyIds = filteredSubsidies.value.map(s => s.id)
  const counts: Record<string, number> = {}
  for (const p of allPurchases.value) {
    if (subsidyIds.length > 0 && !subsidyIds.includes(p.subsidy_id)) continue
    counts[p.status] = (counts[p.status] || 0) + 1
  }
  return counts
})

const STATUS_COLORS: Record<string, string> = {
  wishes: '#6B7280', plan_schedule: '#F59E0B',
  planned: '#94A3B8', confirmed: '#3B82F6',
  in_progress: '#14B8A6', work_in_progress: '#14B8A6',
  contracted: '#6366F1', ordered: '#0EA5E9', delivered: '#8B5CF6', paid: '#22C55E',
}

const statusPieReady = computed(() =>
  Object.keys(filteredStatusCounts.value).length > 0 &&
  Object.values(filteredStatusCounts.value).some(v => v > 0)
)

// Sorted entries so chart is stable
const statusPieEntries = computed(() => {
  const ORDER = ['planned', 'confirmed', 'in_progress', 'contracted', 'delivered', 'paid']
  return Object.entries(filteredStatusCounts.value)
    .filter(([, v]) => v > 0)
    .sort((a, b) => ORDER.indexOf(a[0]) - ORDER.indexOf(b[0]))
})

const statusPieSeries = computed(() => statusPieEntries.value.map(([, v]) => v))
const statusPieLabels = computed(() => statusPieEntries.value.map(([k]) => STATUS_LABELS[k] || k))
const statusPieColors = computed(() => statusPieEntries.value.map(([k]) => STATUS_COLORS[k] || '#94A3B8'))
const statusPieKey    = computed(() => statusPieEntries.value.map(e => e[0]).join('-'))

// For custom StatusPieWithWishes component
const statusPieForComponent = computed(() =>
  statusPieEntries.value
    .filter(([k]) => k !== 'wishes')
    .map(([k, v]) => ({
      status: k,
      count: v,
      color: STATUS_COLORS[k] || '#94A3B8',
      label: STATUS_LABELS[k] || k,
    }))
)
const wishesAmountForPie = computed(() => filteredStatusAmounts.value['wishes'] || 0)
function onPieSliceClick(status: string) {
  statusDrillStatus.value = status
  const label = STATUS_LABELS[status] || status
  const items = getStatusPurchases(status)
  openPurchasesDrill(label, items, {
    icon: 'mdi-chart-pie',
    color: STATUS_COLORS[status] || 'grey',
    prefix: `status_${status}`,
  })
}

// Pipeline stages (purchase lifecycle funnel)
const PIPELINE_ORDER = ['plan_schedule', 'confirmed', 'work_in_progress', 'contracted', 'ordered', 'delivered', 'paid']
const pipelineStages = computed(() => {
  const budget = totalBudget.value || 1
  const subsidyIds = filteredSubsidies.value.map((s: any) => s.id)
  const filtered = allPurchases.value.filter((p: any) =>
    subsidyIds.length === 0 || subsidyIds.includes(p.subsidy_id)
  )
  return PIPELINE_ORDER
    .map((status, idx) => {
      const stagesAtOrBeyond = PIPELINE_ORDER.slice(idx)
      const amount = filtered
        .filter((p: any) => stagesAtOrBeyond.includes(p.status))
        .reduce((sum: number, p: any) => sum + purchaseEffectivePrice(p), 0)
      return {
        status,
        label: STATUS_LABELS[status] || status,
        color: STATUS_COLORS[status] || '#94A3B8',
        amount,
        pct: Math.round(amount / budget * 100),
      }
    })
})

// «Поставлено, не оплачено» = SUM(delivered) − SUM(paid). Drill открывает status='delivered'.
const deliveredNotPaid = computed(() => {
  const subsidyIds = filteredSubsidies.value.map((s: any) => s.id)
  const filtered = allPurchases.value.filter((p: any) =>
    subsidyIds.length === 0 || subsidyIds.includes(p.subsidy_id)
  )
  const delivered = filtered.filter((p: any) => p.status === 'delivered')
    .reduce((sum: number, p: any) => sum + purchaseEffectivePrice(p), 0)
  const budget = totalBudget.value || 1
  return {
    amount: delivered,
    pct: Math.round(delivered / budget * 100),
  }
})
function onPipelineClick(status: string) {
  statusDrillStatus.value = status
  const label = `${STATUS_LABELS[status] || status} (и далее)`
  const items = getCumulativeStagePurchases(status)
  openPurchasesDrill(label, items, {
    icon: 'mdi-stairs-up',
    color: STATUS_COLORS[status] || 'warning',
    prefix: `pipeline_${status}`,
  })
}

// Точный фильтр для метрики «Поставлено, не оплачено» — без cumulative.
function onDeliveredNotPaidClick() {
  statusDrillStatus.value = 'delivered'
  const items = getStatusPurchases('delivered')
  openPurchasesDrill('Поставлено, не оплачено', items, {
    icon: 'mdi-truck-delivery-outline',
    color: '#EF4444',
    prefix: 'delivered_not_paid',
  })
}

// Helper: split purchase amount by товары/услуги using item-level data
function purchaseTypeSplit(p: any): { goods: number, services: number } {
  const items: any[] = p.items || []
  if (items.length === 0) {
    const total = purchaseEffectivePrice(p)
    if (p.item_type === 'товар') return { goods: total, services: 0 }
    if (p.item_type === 'услуга' || p.item_type === 'работа') return { goods: 0, services: total }
    return { goods: total / 2, services: total / 2 }
  }
  let goods = 0, services = 0
  for (const item of items) {
    const amt = parseFloat(item.final_total || item.total_price || 0)
    if (item.item_type === 'товар') goods += amt
    else services += amt
  }
  return { goods, services }
}

// Товары/услуги breakdown by pipeline stage (cumulative)
const pipelineByType = computed(() => {
  const budget = totalBudget.value || 1
  const subsidyIds = filteredSubsidies.value.map((s: any) => s.id)
  const filtered = allPurchases.value.filter((p: any) =>
    subsidyIds.length === 0 || subsidyIds.includes(p.subsidy_id)
  )
  return PIPELINE_ORDER
    .map((status, idx) => {
      const stagesAtOrBeyond = PIPELINE_ORDER.slice(idx)
      const stagePurchases = filtered.filter((p: any) => stagesAtOrBeyond.includes(p.status))
      let goods = 0, services = 0
      for (const p of stagePurchases) {
        const split = purchaseTypeSplit(p)
        goods += split.goods
        services += split.services
      }
      const total = goods + services
      return {
        status,
        label: STATUS_LABELS[status] || status,
        color: STATUS_COLORS[status] || '#94A3B8',
        goods,
        services,
        total,
        goodsPct: budget > 0 ? Math.round(goods / budget * 100) : 0,
        servicesPct: budget > 0 ? Math.round(services / budget * 100) : 0,
      }
    })
    .filter(s => s.total > 0)
})

function openBreakdownTypeDrill(status: string, label: string) {
  const subsidyIds = filteredSubsidies.value.map((s: any) => s.id)
  const stagesAtOrBeyond = PIPELINE_ORDER.slice(PIPELINE_ORDER.indexOf(status))
  const items = allPurchases.value.filter((p: any) => {
    if (subsidyIds.length > 0 && !subsidyIds.includes(p.subsidy_id)) return false
    return stagesAtOrBeyond.includes(p.status)
  })
  openPurchasesDrill(`Товары / Услуги — ${label}`, items, {
    icon: 'mdi-chart-box',
    color: 'deep-purple',
    prefix: `breakdown_${status}`,
  })
}

// Monthly payment contracts remaining
const monthlyContractsRemaining = computed(() => {
  const subsidyIds = filteredSubsidies.value.map((s: any) => s.id)
  const today = new Date()
  return allPurchases.value
    .filter((p: any) => {
      if (subsidyIds.length > 0 && !subsidyIds.includes(p.subsidy_id)) return false
      return p.is_monthly_payment && p.monthly_payment_count && p.monthly_payment_amount
    })
    .map((p: any) => {
      const count = Number(p.monthly_payment_count)
      const perMonth = parseFloat(p.monthly_payment_amount)
      const total = count * perMonth
      const start = p.service_start_date ? new Date(p.service_start_date) : null
      let elapsed = 0
      if (start && !isNaN(start.getTime())) {
        const fullMonths = Math.min(
          Math.max(0, (today.getFullYear() - start.getFullYear()) * 12 + (today.getMonth() - start.getMonth())),
          count
        )
        const partialFraction = fullMonths < count ? today.getDate() / 30 : 0
        elapsed = (fullMonths + Math.min(partialFraction, 1)) * perMonth
      }
      const remaining = Math.max(0, total - elapsed)
      return {
        id: p.id,
        name: p.name || `Закупка #${p.id}`,
        total,
        remaining,
        elapsedPct: total > 0 ? Math.min(100, Math.round((total - remaining) / total * 100)) : 0,
      }
    })
    .filter(c => c.total > 0)
})

const totalMonthlyRemaining = computed(() =>
  monthlyContractsRemaining.value.reduce((s, c) => s + c.remaining, 0)
)

function openMonthlyContractDrill(contractPurchaseId: number, contractName: string) {
  const items = allPurchases.value.filter((p: any) => p.id === contractPurchaseId)
  // Also look for related framework orders by contract_id if purchase itself has an id
  // Since monthlyContractsRemaining uses p.id directly, we match by id
  openPurchasesDrill(contractName, items, {
    icon: 'mdi-calendar-refresh',
    color: 'indigo',
    prefix: `monthly_${contractPurchaseId}`,
    framework: true,
  })
}

const statusPieOptions = computed(() => ({
  chart: {
    type: 'pie', background: 'transparent', toolbar: { show: false },
    animations: { speed: 400 },
    theme: { mode: isDark.value ? 'dark' : 'light' },
    events: {
      dataPointSelection: (_e: any, _ctx: any, config: any) => {
        const entry = statusPieEntries.value[config.dataPointIndex]
        if (entry) {
          const status = entry[0]
          statusDrillStatus.value = status
          const items = getStatusPurchases(status)
          openPurchasesDrill(STATUS_LABELS[status] || status, items, {
            icon: 'mdi-chart-pie',
            color: STATUS_COLORS[status] || 'grey',
            prefix: `status_${status}`,
          })
        }
      }
    }
  },
  colors: statusPieColors.value,
  labels: statusPieLabels.value,
  legend: { position: 'bottom', fontSize: '12px', labels: { colors: chartText.value } },
  dataLabels: { enabled: true, style: { fontSize: '11px', colors: ['#fff'] }, dropShadow: { enabled: false } },
  tooltip: {
    theme: isDark.value ? 'dark' : 'light',
    y: {
      formatter: (v: number, { dataPointIndex }: any) => {
        const status = statusPieEntries.value[dataPointIndex]?.[0]
        const amount = filteredStatusAmounts.value[status] || 0
        return `${v} шт.${amount > 0 ? ' · ' + formatCurrencyShort(amount) : ''}`
      }
    }
  },
}))

// ── Chart: Bar ────────────────────────────────────
const barReady = computed(() => filteredSubsidyStats.value.length > 0)

const barSeries = computed(() => [
  { name: 'Бюджет',          data: filteredSubsidyStats.value.map(s => s.budget) },
  { name: 'Заказано',        data: filteredSubsidyStats.value.map(s => s.ordered) },
  { name: 'Законтрактовано', data: filteredSubsidyStats.value.map(s => s.contracted) },
  { name: 'Оплачено',        data: filteredSubsidyStats.value.map(s => s.paid) },
])

const barOptions = computed(() => ({
  chart: {
    type: 'bar', background: 'transparent', toolbar: { show: false },
    animations: { speed: 500 },
    theme: { mode: isDark.value ? 'dark' : 'light' },
    events: {
      dataPointSelection: (_e: any, _ctx: any, config: any) => {
        const sub = filteredSubsidyStats.value[config.dataPointIndex]
        if (sub) {
          drillDialogSubsidies.value = [sub]
          breakdownMetric.value = 'budget'
          showBreakdownDialog.value = true
        }
      }
    }
  },
  colors: ['#8B5CF6', '#3B82F6', '#F59E0B', '#22C55E'],
  plotOptions: {
    bar: {
      horizontal: true,
      dataLabels: { position: 'top' },
      barHeight: '60%',
      borderRadius: 3,
      borderRadiusApplication: 'end'
    }
  },
  dataLabels: {
    enabled: true,
    style: { fontSize: '10px', fontWeight: '600', colors: ['#1F2937'] },
    formatter: (val: number) => val > 0 ? formatCurrencyShort(val) : '',
    offsetX: 6,
    background: { enabled: false }
  },
  xaxis: {
    categories: filteredSubsidyStats.value.map(s => truncate(s.name, 28)),
    labels: {
      style: { colors: chartMuted.value, fontSize: '11px' },
      formatter: (val: number) => formatCurrencyShort(val)
    }
  },
  yaxis: { labels: { style: { colors: chartText.value, fontSize: '11px' } } },
  legend: {
    show: true, position: 'top',
    fontSize: '12px', labels: { colors: chartText.value }
  },
  grid: { borderColor: chartGrid.value },
  tooltip: { theme: isDark.value ? 'dark' : 'light', y: { formatter: (v: number) => formatCurrency(v) } }
}))

// ── Load data ─────────────────────────────────────
async function loadAll() {
  loading.value = true
  loadingPurchases.value = true
  try {
    const [chartsData, purchasesData] = await Promise.all([
      apiFetch<any>('/dashboard/charts'),
      apiFetch<any[]>('/purchases/')
    ])

    // Build subsidy rows from charts endpoint
    allSubsidies.value = chartsData.subsidy_stats.map((s: any) => ({
      id: s.id,
      name: s.name,
      shortName: truncate(s.name, 20),
      description: '',
      year: s.year,
      budget: s.calculated_budget || s.feo_budget_total || s.budget,
      contracted: s.total_confirmed,
      paid: s.total_paid,
      planned: s.total_planned,
      plan_schedule: s.total_plan_schedule ?? 0,
      ordered: s.total_ordered ?? 0,
    }))

    statusCounts.value = chartsData.status_counts

    // Store all purchases for filtering
    allPurchases.value = purchasesData

    // Set default year to most recent available
    const years = [...new Set(allSubsidies.value.map((s: SubsidyRow) => s.year))].sort((a, b) => b - a)
    if (years.length > 0 && !years.includes(selectedYear.value)) {
      selectedYear.value = years[0]
    }
  } catch (e) {
    console.error('Dashboard load error:', e)
  } finally {
    loading.value = false
    loadingPurchases.value = false
  }
}

function openBreakdown(metric = 'budget') {
  breakdownMetric.value = metric
  showBreakdownDialog.value = true
}

function handleKpiClick(key: string) {
  const subsidyIds = filteredSubsidies.value.map((s: any) => s.id)
  const filtered = allPurchases.value.filter((p: any) =>
    subsidyIds.length === 0 || subsidyIds.includes(p.subsidy_id)
  )
  const KPI_STATUS_MAP: Record<string, string[]> = {
    plan_schedule: ['confirmed', 'work_in_progress', 'plan_schedule'],
    ordered:       ['contracted', 'delivered', 'ordered'],
    paid:          ['paid'],
    budget:        [],  // all
  }
  const KPI_ICONS: Record<string, string> = {
    budget: 'mdi-bank-outline', plan_schedule: 'mdi-calendar-clock',
    ordered: 'mdi-cart-check', paid: 'mdi-cash-check',
  }
  const KPI_COLORS: Record<string, string> = {
    budget: 'primary', plan_schedule: 'warning', ordered: 'blue', paid: 'success',
  }
  const statuses = KPI_STATUS_MAP[key] ?? []
  const items = statuses.length > 0
    ? filtered.filter((p: any) => statuses.includes(p.status))
    : filtered
  const card = kpiCards.value.find(c => c.key === key)
  openPurchasesDrill(card?.label ?? key, items, {
    icon: KPI_ICONS[key],
    color: KPI_COLORS[key],
    prefix: `kpi_${key}`,
  })
}

function goToOrders() {
  const ids = selectedSubsidyIds.value
  if (ids.length === 1) {
    router.push(`/orders?subsidy_id=${ids[0]}`)
  } else {
    router.push('/orders')
  }
}

// ── Helpers ───────────────────────────────────────
function pct(part: number, total: number): number {
  if (!total) return 0
  return Math.round((part / total) * 100)
}

function progressColor(p: number): string {
  if (p >= 90) return 'error'
  if (p >= 70) return 'warning'
  return 'primary'
}

function formatCurrency(v: number): string {
  return (v || 0).toLocaleString('ru-RU', { maximumFractionDigits: 0 }) + ' ₽'
}

function formatCurrencyShort(v: number): string {
  if (!v) return '0 ₽'
  if (Math.abs(v) >= 1_000_000_000) return (v / 1_000_000_000).toFixed(1) + ' млрд ₽'
  if (Math.abs(v) >= 1_000_000) return (v / 1_000_000).toFixed(1) + ' млн ₽'
  if (Math.abs(v) >= 1_000) return (v / 1_000).toFixed(0) + ' тыс ₽'
  return v.toLocaleString('ru-RU') + ' ₽'
}

function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n) + '…' : s
}

// Возвращает первое значение > 0 (после parseFloat), иначе 0.
function pickPositive(...vals: any[]): number {
  for (const v of vals) {
    const n = parseFloat(v || 0)
    if (n > 0) return n
  }
  return 0
}

function purchaseEffectivePrice(p: any): number {
  const status = p.status
  if (status === 'paid') {
    return pickPositive(
      p.payment_amount, p.delivery_payment_amount,
      p.acceptance_doc_amount, p.contract_price, p.planned_total_price,
    )
  }
  if (status === 'delivered') {
    return pickPositive(
      p.acceptance_doc_amount, p.delivery_payment_amount,
      p.contract_price, p.planned_total_price,
    )
  }
  if (status === 'ordered') {
    return pickPositive(
      p.contract_price, p.delivery_payment_amount,
      p.acceptance_doc_amount, p.planned_total_price,
    )
  }
  if (status === 'contracted') {
    const isFramework = p.purchase_contract_type === 'framework_cumulative' ||
                        p.purchase_contract_type === 'framework_with_amount'
    if (isFramework) {
      return pickPositive(
        p.acceptance_doc_amount, p.delivery_payment_amount,
        p.contract_price, p.planned_total_price,
      )
    }
    if (p.purchase_method === 'single') {
      return pickPositive(p.contract_price, p.delivery_payment_amount, p.planned_total_price)
    }
    return pickPositive(p.delivery_payment_amount, p.contract_price, p.planned_total_price)
  }
  return pickPositive(p.total_nmck, p.planned_total_price, p.contract_price)
}

function statusLabel(s: string): string {
  return STATUS_LABELS[s] || s
}

function statusColor(s: string): string {
  const map: Record<string, string> = {
    planned: 'grey', confirmed: 'primary', in_progress: 'teal',
    contracted: 'indigo', delivered: 'deep-purple', paid: 'success'
  }
  return map[s] || 'grey'
}

function statusColorHex(s: string): string {
  const map: Record<string, string> = {
    planned: '#94A3B8', confirmed: '#3B82F6', in_progress: '#14B8A6',
    contracted: '#6366F1', delivered: '#8B5CF6', paid: '#22C55E'
  }
  return map[s] || '#94A3B8'
}

// ── Analytics Tab ─────────────────────────────────
interface AnalyticsData {
  funnel: { status: string; count: number; total: number }[]
  monthly_payments: { year: number; month: number; total: number }[]
  top_contractors: { name: string; count: number; total: number }[]
  upcoming_deliveries: { count: number; total: number }
  economy: number
  overdue_count: number
  upcoming_deadlines: { id: number; name: string; purchase_number?: number; execution_term: string; status: string }[]
  method_distribution: Record<string, number>
  plan_fact: { subsidy: string; plan: number; contracted: number; paid: number }[]
}

const analyticsData = ref<AnalyticsData | null>(null)
const analyticsLoading = ref(false)

const A_STATUS_LABELS: Record<string, string> = {
  wishes:           'Пожелания',
  plan_schedule:    'План-график',
  confirmed:        'Подтверждена',
  work_in_progress: 'В работе',
  contracted:       'Законтрактована',
  ordered:          'Заказана',
  delivered:        'Поставлена',
  paid:             'Оплачена',
  planned:          'Планирование',
  in_progress:      'В работе',
}
const A_STATUS_COLORS: Record<string, string> = {
  wishes:           'grey',
  plan_schedule:    'blue-grey',
  confirmed:        'blue',
  work_in_progress: 'teal',
  contracted:       'indigo',
  ordered:          'light-blue',
  delivered:        'deep-purple',
  paid:             'green',
  planned:          'orange',
  in_progress:      'teal',
}
const A_METHOD_LABELS: Record<string, string> = {
  single: 'Единственный поставщик', competitive: 'Конкурсная процедура',
  quote_request: 'Запрос котировок', unknown: 'Не указано',
}
const A_METHOD_COLORS: Record<string, string> = {
  single: 'blue', competitive: 'teal', quote_request: 'purple', unknown: 'grey',
}
const A_MONTH_NAMES = ['Янв','Фев','Мар','Апр','Май','Июн','Июл','Авг','Сен','Окт','Ноя','Дек']

const analyticsTotalPurchases = computed(() =>
  analyticsData.value ? analyticsData.value.funnel.reduce((s, i) => s + i.count, 0) : 0
)
const analyticsTotalPaid = computed(() => {
  if (!analyticsData.value) return '—'
  const total = analyticsData.value.monthly_payments.reduce((s, i) => s + i.total, 0)
  return formatCurrencyShort(total)
})
const analyticsMaxFunnel = computed(() =>
  analyticsData.value ? Math.max(...analyticsData.value.funnel.map(i => i.total), 1) : 1
)
const analyticsFunnelPct = (count: number) => (count / analyticsMaxFunnel.value) * 100
const analyticsMaxContractor = computed(() =>
  analyticsData.value?.top_contractors?.length ? analyticsData.value.top_contractors[0].total : 1
)
const analyticsTopPct = (total: number) => (total / analyticsMaxContractor.value) * 100
const analyticsMaxMonthly = computed(() =>
  analyticsData.value?.monthly_payments?.length ? Math.max(...analyticsData.value.monthly_payments.map(m => m.total)) : 1
)
const analyticsBarHeight = (total: number) => Math.max((total / analyticsMaxMonthly.value) * 100, 4)

function analyticsFormatDate(d: string): string {
  if (!d) return ''
  const [y, m, day] = d.split('-')
  return `${day}.${m}.${y}`
}
function analyticsDeadlineColor(d: string): string {
  const diff = (new Date(d).getTime() - Date.now()) / 86400000
  if (diff <= 7) return 'error'
  if (diff <= 14) return 'warning'
  return 'success'
}

async function loadAnalytics() {
  analyticsLoading.value = true
  try {
    const ids = selectedSubsidyIds.value
    const qs = ids.length > 0 ? `?subsidy_ids=${ids.join(',')}` : ''
    analyticsData.value = await apiFetch<AnalyticsData>(`/dashboard/analytics${qs}`)
  } finally {
    analyticsLoading.value = false
  }
}

// Load analytics on tab switch (lazy)
watch(activeTab, (tab) => {
  if (tab === 'analytics') {
    loadAnalytics()
  }
})

// Reload analytics when subsidy filter changes while on analytics tab
watch(selectedSubsidyIds, () => {
  if (activeTab.value === 'analytics') {
    loadAnalytics()
  }
})

// ── Financial Plan Widget ──────────────────────────
const finplanGranularity = ref<'month' | 'quarter'>('month')
const finplanData = ref<any>(null)
const finplanAllPeriods = ref<string[]>([])

const finplanDrilldown = ref({
  show: false,
  loading: false,
  period: '' as string,
  category: '' as 'plan' | 'committed' | 'overdue' | 'no_deadline' | '',
  items: [] as any[],
})

async function openFinplanDrilldown(period: string, category: 'plan' | 'committed' | 'overdue' | 'no_deadline') {
  finplanDrilldown.value.show = true
  finplanDrilldown.value.loading = true
  finplanDrilldown.value.period = period
  finplanDrilldown.value.category = category
  finplanDrilldown.value.items = []
  try {
    const sidParam = selectedSubsidyIds.value.length === 1 ? `&subsidy_id=${selectedSubsidyIds.value[0]}` : ''
    const periodParam = period ? `&period=${period}` : ''
    const data = await apiFetch<any>(`/dashboard/financial-plan/details?category=${category}&granularity=${finplanGranularity.value}${periodParam}${sidParam}`)
    finplanDrilldown.value.items = data.items || []
  } catch (e) {
    finplanDrilldown.value.items = []
  } finally {
    finplanDrilldown.value.loading = false
  }
}

const finplanDrilldownTotal = computed(() =>
  finplanDrilldown.value.items.reduce((s: number, r: any) => s + (r.amount || 0), 0)
)

const finplanDrilldownTitle = computed(() => {
  const cat = finplanDrilldown.value.category
  if (cat === 'plan') return 'Плановые'
  if (cat === 'committed') return 'Принятые обязательства'
  if (cat === 'overdue') return 'Накопленный долг'
  if (cat === 'no_deadline') return 'Без срока исполнения'
  return 'Закупки'
})

const finplanDrilldownChipColor = computed(() => {
  const cat = finplanDrilldown.value.category
  if (cat === 'plan') return 'warning'
  if (cat === 'committed') return 'success'
  if (cat === 'overdue') return 'error'
  if (cat === 'no_deadline') return 'warning'
  return 'grey'
})

async function patchIsLikelyNeeded(row: any, val: boolean) {
  try {
    await apiFetch(`/purchases/${row.id}`, { method: 'PATCH', body: { is_likely_needed: val } })
    row.is_likely_needed = val
  } catch (e) {
    console.error('patchIsLikelyNeeded error', e)
  }
}

// no_deadline count for banner
const finplanNoDeadlineCount = computed(() => {
  if (!finplanData.value) return 0
  const key = finplanGranularity.value === 'month' ? 'by_month' : 'by_quarter'
  return finplanData.value[key]?.no_deadline?.items_count ?? 0
})

// KPI текущего месяца
const finplanCurrentMonthKpi = computed(() => {
  if (!finplanData.value) return null
  const key = finplanGranularity.value === 'month' ? 'by_month' : 'by_quarter'
  const data = finplanData.value[key]
  if (!data) return null
  const now = new Date()
  const period = finplanGranularity.value === 'month'
    ? `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
    : `${now.getFullYear()}-Q${Math.ceil((now.getMonth() + 1) / 3)}`
  const planEntry = (data.plan || []).find((d: any) => d.period === period)
  const overdueEntry = (data.overdue || []).find((d: any) => d.period === period)
  return {
    period,
    plan: planEntry?.amount ?? 0,
    overdue: overdueEntry?.accumulated ?? 0,
  }
})

function goToOrder(id: number) {
  finplanDrilldown.value.show = false
  router.push(`/orders/${id}/edit`)
}

async function exportFinplanXlsx() {
  const sidParam = selectedSubsidyIds.value.length === 1 ? `&subsidy_id=${selectedSubsidyIds.value[0]}` : ''
  const token = localStorage.getItem('auth_token')
  const url = `/api/dashboard/financial-plan/export.xlsx?granularity=${finplanGranularity.value}${sidParam}`
  const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
  if (!res.ok) return
  const blob = await res.blob()
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `finplan_${finplanGranularity.value}_${new Date().toISOString().slice(0, 10)}.xlsx`
  link.click()
  URL.revokeObjectURL(link.href)
}

async function exportFinplanDrilldownXlsx() {
  const sidParam = selectedSubsidyIds.value.length === 1 ? `&subsidy_id=${selectedSubsidyIds.value[0]}` : ''
  const params = `period=${encodeURIComponent(finplanDrilldown.value.period)}&category=${finplanDrilldown.value.category}&granularity=${finplanGranularity.value}${sidParam}`
  const token = localStorage.getItem('auth_token')
  const res = await fetch(`/api/dashboard/financial-plan/details/export.xlsx?${params}`, { headers: { Authorization: `Bearer ${token}` } })
  if (!res.ok) return
  const blob = await res.blob()
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `finplan_${finplanDrilldown.value.period}_${finplanDrilldown.value.category}.xlsx`
  link.click()
  URL.revokeObjectURL(link.href)
}

function formatDate(iso: string) {
  if (!iso) return ''
  const [y, m, d] = iso.split('-')
  return `${d}.${m}.${y}`
}

const STATUS_LABELS_FINPLAN: Record<string, string> = {
  planned: 'Запланирован', confirmed: 'Подтверждён', wishes: 'Заявка',
  plan_schedule: 'Запланировано',
  contracted: 'Заключён договор', ordered: 'Заказано', delivered: 'Поставлено',
  paid: 'Оплачено', work_in_progress: 'В работе',
}

async function loadFinplan() {
  try {
    const sidParam = selectedSubsidyIds.value.length === 1 ? `?subsidy_id=${selectedSubsidyIds.value[0]}` : ''
    finplanData.value = await apiFetch<any>(`/dashboard/financial-plan${sidParam}`)
  } catch {
    finplanData.value = null
  }
}

const finplanSeries = computed(() => {
  if (!finplanData.value) return []
  const key = finplanGranularity.value === 'month' ? 'by_month' : 'by_quarter'
  const data = finplanData.value[key]
  if (!data) return []
  const allPeriods = [...new Set([
    ...(data.plan || []).map((d: any) => d.period),
    ...(data.committed || []).map((d: any) => d.period),
    ...(data.overdue || []).map((d: any) => d.period),
  ])].sort()
  if (allPeriods.length === 0) return []
  finplanAllPeriods.value = allPeriods
  const planMap = new Map((data.plan || []).map((d: any) => [d.period, d.amount]))
  const commMap = new Map((data.committed || []).map((d: any) => [d.period, d.amount]))
  const overdueMap = new Map((data.overdue || []).map((d: any) => [d.period, d.accumulated ?? d.amount ?? 0]))
  const series: any[] = [
    { name: 'Принятые обязательства', data: allPeriods.map(p => Math.round((commMap.get(p) as number) ?? 0)) },
    { name: 'Плановые', data: allPeriods.map(p => Math.round((planMap.get(p) as number) ?? 0)) },
  ]
  const hasOverdue = (data.overdue || []).length > 0
  if (hasOverdue) {
    series.push({ name: 'Накопленный долг', data: allPeriods.map(p => Math.round((overdueMap.get(p) as number) ?? 0)) })
  }
  return series
})

const finplanOptions = computed(() => {
  if (!finplanData.value) return {}
  const key = finplanGranularity.value === 'month' ? 'by_month' : 'by_quarter'
  const data = finplanData.value[key]
  if (!data) return {}
  const allPeriods = [...new Set([
    ...(data.plan || []).map((d: any) => d.period),
    ...(data.committed || []).map((d: any) => d.period),
  ])].sort()
  return {
    chart: {
      type: 'bar', stacked: true, background: 'transparent', toolbar: { show: false },
      theme: { mode: isDark.value ? 'dark' : 'light' },
      events: {
        dataPointSelection: (_event: any, _ctx: any, config: any) => {
          const period = finplanAllPeriods.value[config.dataPointIndex]
          const seriesName = config.w.config.series[config.seriesIndex]?.name || ''
          let category: 'plan' | 'committed' | 'overdue' | 'no_deadline' = 'plan'
          if (seriesName.toLowerCase().includes('принят')) category = 'committed'
          else if (seriesName.toLowerCase().includes('накопл') || seriesName.toLowerCase().includes('долг')) category = 'overdue'
          if (period) openFinplanDrilldown(period, category)
        },
      },
    },
    plotOptions: { bar: { horizontal: false, columnWidth: '60%' } },
    dataLabels: { enabled: false },
    xaxis: { categories: allPeriods, labels: { style: { colors: chartMuted.value, fontSize: '11px' } } },
    yaxis: { labels: { formatter: (v: number) => formatCurrencyShort(v), style: { colors: chartMuted.value, fontSize: '11px' } } },
    colors: ['#15803D', '#F59E0B', '#EF4444'],
    legend: { position: 'top', fontSize: '12px', labels: { colors: chartText.value } },
    grid: { borderColor: chartGrid.value },
    tooltip: { theme: isDark.value ? 'dark' : 'light', y: { formatter: (v: number) => formatCurrency(v) } },
  }
})

// Reload finplan when subsidy filter changes
watch(selectedSubsidyIds, () => { loadFinplan() })

onMounted(() => {
  setMode('classic')
  loadAll()
  loadFinplan()
  if (activeTab.value === 'analytics') {
    loadAnalytics()
  }
})
</script>

<style scoped>
/* ── Budget Overrun Banner ── */
.budget-overrun-banner {
  display: flex;
  align-items: flex-start;
  background: linear-gradient(135deg, #EF4444, #DC2626);
  color: white;
  border-radius: 12px;
  padding: 20px 24px;
  margin-bottom: 20px;
  box-shadow: 0 4px 20px rgba(239,68,68,0.4);
  animation: pulse-border 2s infinite;
}
@keyframes pulse-border {
  0%, 100% { box-shadow: 0 4px 20px rgba(239,68,68,0.4); }
  50%       { box-shadow: 0 4px 32px rgba(239,68,68,0.7); }
}
.overrun-content { flex: 1; }
.overrun-title { font-size: 18px; font-weight: 700; margin-bottom: 8px; }
.overrun-row { font-size: 14px; margin-bottom: 4px; line-height: 1.5; opacity: 0.95; }
.overrun-hint { font-size: 12px; opacity: 0.8; margin-top: 8px; font-style: italic; }

/* ── Layout ── */
.crm-dashboard {
  padding: 20px 24px;
  max-width: 1600px;
}

/* ── Header ── */
.dash-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
  flex-wrap: wrap;
  gap: 12px;
}
.dash-header-left {
  display: flex;
  align-items: center;
}
.dash-title {
  font-size: 26px;
  font-weight: 700;
  color: var(--crm-text);
  line-height: 1.2;
}
.dash-subtitle {
  font-size: 13px;
  color: var(--crm-text-muted);
  margin-top: 2px;
}
.dash-header-right {
  display: flex;
  align-items: center;
}

/* ── Subsidy quick chips ── */
.subsidy-chips-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 12px;
  padding: 0 2px;
}
.subsidy-chip {
  font-size: 12px;
  letter-spacing: 0;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}
.subsidy-chip:hover {
  transform: translateY(-1px);
  box-shadow: 0 2px 8px var(--crm-shadow);
}

/* ── KPI Cards ── */
.kpi-row { margin-bottom: 4px; }

.kpi-card {
  border-radius: 12px;
  padding: 18px 20px;
  display: flex;
  align-items: center;
  gap: 14px;
  cursor: pointer;
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

/* ── Glassmorphism + Glow (Wiza-inspired) ── */
.kpi-card::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  opacity: 0;
  transition: opacity 0.35s ease;
  z-index: -1;
}
.kpi-card:hover::before {
  opacity: 1;
}
.kpi-budget::before        { box-shadow: 0 0 30px rgba(59,130,246,0.15); }
.kpi-plan_schedule::before { box-shadow: 0 0 30px rgba(245,158,11,0.15); }
.kpi-ordered::before       { box-shadow: 0 0 30px rgba(59,130,246,0.15); }
.kpi-paid::before          { box-shadow: 0 0 30px rgba(34,197,94,0.15); }

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
.kpi-card:hover .kpi-icon-box {
  transform: scale(1.12) rotate(-3deg);
}

.kpi-budget .kpi-icon-box        { background: var(--crm-kpi-bg-blue); color: #3B82F6; }
.kpi-plan_schedule .kpi-icon-box { background: rgba(245,158,11,0.12); color: #F59E0B; }
.kpi-ordered .kpi-icon-box       { background: rgba(59,130,246,0.12); color: #3B82F6; }
.kpi-contracted .kpi-icon-box    { background: var(--crm-kpi-bg-sky); color: #0284C7; }
.kpi-paid .kpi-icon-box          { background: var(--crm-kpi-bg-green); color: #22C55E; }

.kpi-budget       { border-top: 3px solid #3B82F6; }
.kpi-plan_schedule { border-top: 3px solid #F59E0B; }
.kpi-ordered      { border-top: 3px solid #3B82F6; }
.kpi-contracted   { border-top: 3px solid #0284C7; }
.kpi-paid         { border-top: 3px solid #22C55E; }

.kpi-body { flex: 1; min-width: 0; }
.kpi-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--crm-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.kpi-label {
  font-size: 12px;
  color: var(--crm-text-muted);
  margin-top: 2px;
}
.kpi-badge {
  font-size: 11px;
  font-weight: 600;
  color: var(--crm-text-muted);
  background: var(--crm-surface-hover);
  padding: 2px 8px;
  border-radius: 20px;
  white-space: nowrap;
  transition: all 0.25s ease;
}
.kpi-card:hover .kpi-badge {
  background: var(--crm-border-strong);
  color: var(--crm-text);
}

/* ── Chart Cards ── */
.chart-row { margin-bottom: 4px; }

.chart-card {
  background: var(--crm-surface);
  border-radius: 12px;
  border: 1px solid var(--crm-border);
  box-shadow: 0 1px 4px var(--crm-shadow);
  padding: 18px 20px;
  height: 100%;
}

.chart-card-header {
  display: flex;
  align-items: center;
  margin-bottom: 4px;
}
.chart-card-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--crm-text-secondary);
}
.chart-link {
  font-size: 13px;
  color: #3B82F6;
  text-decoration: none;
  font-weight: 500;
}
.chart-link:hover { text-decoration: underline; }

.chart-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 220px;
  color: var(--crm-text-faint);
}

.radial-footer {
  text-align: center;
  margin-top: -8px;
  padding-bottom: 4px;
}

/* ── Pipeline Chart ── */
.pipeline-wrap { display: flex; flex-direction: column; gap: 10px; padding: 4px 0; }
.pipeline-row {
  display: grid;
  grid-template-columns: 130px 1fr 110px;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  border-radius: 6px;
  padding: 4px 2px;
  transition: background 0.15s;
}
.pipeline-row:hover { background: var(--crm-surface-alt); }
.pipeline-label {
  display: flex; align-items: center; gap: 6px;
  font-size: 12px; color: var(--crm-text); white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis;
}
.pipeline-dot {
  display: inline-block; width: 8px; height: 8px;
  border-radius: 50%; flex-shrink: 0; margin-right: 6px;
}
.pipeline-bar-track {
  height: 10px; background: var(--crm-border); border-radius: 5px; overflow: hidden;
}
.pipeline-bar-fill {
  height: 100%; border-radius: 5px;
  transition: width 0.4s ease;
  min-width: 2px;
}
.pipeline-meta {
  display: flex; align-items: center; justify-content: flex-end; gap: 6px;
}
.pipeline-amount { font-size: 11px; font-weight: 600; color: var(--crm-text); }
.pipeline-pct { font-size: 11px; color: var(--crm-text-muted); min-width: 36px; text-align: right; }
.pipeline-wishes-hint {
  display: flex; align-items: center;
  font-size: 11px; color: #F59E0B;
  border-top: 1px solid var(--crm-border);
  padding-top: 8px; margin-top: 4px;
}
.chart-card--compact { min-height: unset; }

/* ── Recent Purchases ── */
.purchase-list { margin-top: 4px; }
.purchase-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 4px;
  border-bottom: 1px solid var(--crm-border);
  cursor: pointer;
  transition: background 0.12s;
  border-radius: 6px;
}
.purchase-row:last-child { border-bottom: none; }
.purchase-row:hover { background: var(--crm-surface-alt); }
.purchase-num { padding-top: 2px; }
.purchase-main { flex: 1; min-width: 0; }
.purchase-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--crm-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.purchase-meta {
  font-size: 11px;
  color: var(--crm-text-faint);
  margin-top: 1px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.purchase-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  flex-shrink: 0;
}
.purchase-amount {
  font-size: 12px;
  font-weight: 600;
  color: var(--crm-text-secondary);
  white-space: nowrap;
}

/* ── Summary Table ── */
.table-card { margin-bottom: 20px; }

.dash-table thead th {
  font-size: 12px !important;
  font-weight: 600 !important;
  color: var(--crm-text-muted) !important;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  background: var(--crm-table-header);
  white-space: nowrap;
  padding: 10px 12px !important;
}
.dash-table tbody td { padding: 10px 12px !important; }

.table-row-hover:hover td { background: var(--crm-surface-alt); }

.total-row td {
  background: var(--crm-table-stripe) !important;
  font-weight: 600;
  font-size: 13px;
}

/* ── Analytics Tab ── */
.analytics-deadline-item { padding: 6px 0; border-bottom: 1px solid var(--crm-border); }
.analytics-deadline-item:last-child { border-bottom: none; }
.analytics-deadline-link { text-decoration: none; color: inherit; }
.analytics-deadline-link:hover { text-decoration: underline; }
.analytics-monthly-chart {
  display: flex; align-items: flex-end; gap: 6px;
  height: 160px; padding: 0 4px;
}
.analytics-bar-col {
  flex: 1; display: flex; flex-direction: column; align-items: center;
}
.analytics-bar-label {
  font-size: 9px; color: var(--crm-text-muted); text-align: center; min-height: 24px;
  display: flex; align-items: flex-end; justify-content: center; margin-bottom: 2px;
  transform: rotate(-30deg); transform-origin: bottom right;
}
.analytics-bar-wrap {
  flex: 1; width: 100%; display: flex; align-items: flex-end;
  min-height: 100px;
}
.analytics-bar-fill {
  width: 100%; background: linear-gradient(180deg, #6366f1 0%, #4338ca 100%);
  border-radius: 4px 4px 0 0; min-height: 4px;
  transition: height 0.5s ease;
}
.analytics-bar-x { font-size: 9px; text-align: center; color: var(--crm-text-faint); margin-top: 4px; line-height: 1.2; }
:deep(.apexcharts-pie-series path) { cursor: pointer; }
.chart-fade-enter-active, .chart-fade-leave-active { transition: opacity 0.25s, transform 0.25s; }
.chart-fade-enter-from { opacity: 0; transform: translateX(12px); }
.chart-fade-leave-to  { opacity: 0; transform: translateX(-12px); }

/* ── Gradient progress bars ── */
.gradient-progress :deep(.v-progress-linear__determinate) {
  transition: width 0.6s cubic-bezier(0.22, 1, 0.36, 1) !important;
}
.gradient-progress :deep(.v-progress-linear__background) {
  opacity: 0.15 !important;
}

/* ── Chart card hover (glassmorphism) ── */
.chart-card {
  transition: box-shadow 0.3s cubic-bezier(0.22, 1, 0.36, 1),
              transform 0.3s cubic-bezier(0.22, 1, 0.36, 1),
              border-color 0.3s ease;
}
.chart-card:hover {
  box-shadow: 0 12px 32px var(--crm-shadow-hover);
  transform: translateY(-3px);
  border-color: var(--crm-border-strong);
}

/* ── Smooth skeleton transition ── */
.kpi-row {
  transition: opacity 0.3s ease;
}

/* ── Animated gradient text (Wiza-inspired) ── */
.gradient-text {
  background: linear-gradient(
    90deg,
    #3B82F6 0%,
    #8B5CF6 25%,
    #EC4899 50%,
    #F59E0B 75%,
    #3B82F6 100%
  );
  background-size: 200% auto;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: gradient-shift 4s linear infinite;
}

@keyframes gradient-shift {
  0% { background-position: 0% center; }
  100% { background-position: 200% center; }
}

/* ── Dot grid background (First Internet inspired) ── */
.crm-dashboard {
  position: relative;
}
.crm-dashboard::before {
  content: '';
  position: fixed;
  inset: 0;
  background-image: radial-gradient(circle, var(--crm-border-strong) 1px, transparent 1px);
  background-size: 24px 24px;
  opacity: 0.4;
  pointer-events: none;
  z-index: 0;
}
.crm-dashboard > * {
  position: relative;
  z-index: 1;
}

/* ── Staggered entrance animation ── */
@keyframes card-entrance {
  from {
    opacity: 0;
    transform: translateY(16px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.kpi-row .v-col:nth-child(1) .kpi-card { animation: card-entrance 0.4s cubic-bezier(0.22, 1, 0.36, 1) 0.05s both; }
.kpi-row .v-col:nth-child(2) .kpi-card { animation: card-entrance 0.4s cubic-bezier(0.22, 1, 0.36, 1) 0.12s both; }
.kpi-row .v-col:nth-child(3) .kpi-card { animation: card-entrance 0.4s cubic-bezier(0.22, 1, 0.36, 1) 0.19s both; }
.kpi-row .v-col:nth-child(4) .kpi-card { animation: card-entrance 0.4s cubic-bezier(0.22, 1, 0.36, 1) 0.26s both; }

/* Charts entrance */
.chart-row .v-col:nth-child(1) .chart-card { animation: card-entrance 0.5s cubic-bezier(0.22, 1, 0.36, 1) 0.3s both; }
.chart-row .v-col:nth-child(2) .chart-card { animation: card-entrance 0.5s cubic-bezier(0.22, 1, 0.36, 1) 0.38s both; }
.chart-row .v-col:nth-child(3) .chart-card { animation: card-entrance 0.5s cubic-bezier(0.22, 1, 0.36, 1) 0.46s both; }

/* ── Grid layout widgets ── */
.grid-widget {
  height: 100%;
  border-radius: 12px;
  overflow: hidden;
  transition: box-shadow 0.2s ease;
}
.grid-widget--editing {
  box-shadow: 0 0 0 2px rgba(245,158,11,0.4);
  cursor: grab;
}
.grid-widget--editing:active {
  cursor: grabbing;
}

.widget-drag-handle {
  background: linear-gradient(90deg, rgba(245,158,11,0.15), transparent);
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 600;
  color: var(--crm-text-muted);
  display: flex;
  align-items: center;
  gap: 4px;
  border-bottom: 1px solid var(--crm-border);
}

.edit-mode-banner {
  background: linear-gradient(90deg, #F59E0B, #EF4444);
  color: white;
  padding: 8px 16px;
  border-radius: 8px;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  font-size: 13px;
  font-weight: 500;
}

/* grid-layout-plus overrides */
:deep(.vue-grid-item) {
  transition: all 0.2s ease;
}
:deep(.vue-grid-item.vue-grid-placeholder) {
  background: rgba(59,130,246,0.15) !important;
  border: 2px dashed #3B82F6 !important;
  border-radius: 12px;
}
:deep(.vue-grid-item > .vue-resizable-handle) {
  width: 16px;
  height: 16px;
  bottom: 4px;
  right: 4px;
  background: none;
}
:deep(.vue-grid-item > .vue-resizable-handle::after) {
  content: '';
  position: absolute;
  right: 2px;
  bottom: 2px;
  width: 8px;
  height: 8px;
  border-right: 2px solid var(--crm-text-muted);
  border-bottom: 2px solid var(--crm-text-muted);
  border-radius: 0 0 2px 0;
}
</style>
