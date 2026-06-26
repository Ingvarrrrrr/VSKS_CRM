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
          <template #item.plan_schedule="{ item }">
            <span style="color:#F59E0B">{{ formatCurrencyShort(item.plan_schedule) }}</span>
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
          <template #item.name="{ item }">
            <span class="font-weight-medium cursor-pointer" @click="toggleSelect(item.id)">{{ item.name }}</span>
          </template>
          <template #item.actions="{ item }">
            <div class="d-flex align-center justify-end" style="gap:2px">
              <v-btn
                icon="mdi-file-document-outline"
                size="x-small" variant="text"
                :color="contractTemplates[item.id] ? 'indigo' : 'grey-lighten-1'"
                :title="contractTemplates[item.id] ? 'Шаблон договора (загружен)' : 'Шаблон договора (не загружен)'"
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
            <div class="sc-header">
              <div class="sc-name">{{ s.name }}</div>
              <div class="sc-actions">
                <v-btn
                  icon="mdi-file-document-outline"
                  size="x-small" variant="text"
                  :color="contractTemplates[s.id] ? 'indigo' : 'grey-lighten-1'"
                  :title="contractTemplates[s.id] ? 'Шаблон договора (загружен)' : 'Шаблон договора (не загружен)'"
                  @click.stop="openTemplateDialog(s)"
                />
                <v-btn icon="mdi-account-multiple" size="x-small" variant="text" color="teal" title="Согласующие" @click.stop="openApproversDialog(s)" />
                <v-btn icon="mdi-history" size="x-small" variant="text" color="blue-grey" title="История бюджета" @click.stop="openHistoryDialog(s)" />
                <v-btn icon="mdi-pencil" size="x-small" variant="text" color="primary" @click.stop="startEdit(s)" />
                <v-btn icon="mdi-delete" size="x-small" variant="text" color="error" @click.stop="confirmDelete(s)" />
              </div>
            </div>

            <div class="sc-budget">{{ formatCurrencyShort(s.feo_budget_total || s.budget) }}</div>
            <div class="sc-budget-label">{{ (s.feo_budget_total || 0) > 0 ? 'Бюджет ФЭО' : 'Бюджет' }}</div>

            <div class="sc-mini-row">
              <div class="sc-mini">
                <div class="sc-mini-label">Запланировано</div>
                <div class="sc-mini-val" style="color:#F59E0B">{{ formatCurrencyShort(s.plan_schedule) }}</div>
              </div>
              <div class="sc-mini">
                <div class="sc-mini-label">Заказано</div>
                <div class="sc-mini-val" style="color:#3B82F6">{{ formatCurrencyShort(s.ordered) }}</div>
              </div>
              <div class="sc-mini">
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
              :subsidy="{
                id: s.id,
                name: s.name,
                budget: s.feo_budget_total || s.budget,
                planned: s.planned,
                contracted: s.contracted,
                paid: s.paid,
              }"
            />
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
          <div class="summary-item">
            <span class="summary-label">Запланировано</span>
            <span class="summary-value" style="color:#F59E0B">{{ formatCurrency(totals.plan_schedule) }}</span>
          </div>
          <div class="summary-sep" />
          <div class="summary-item summary-item--link" @click="router.push('/orders?status=confirmed')">
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
        </div>

        <!-- ── Detail panel ── -->
        <div v-if="selectedSubsidy" class="detail-panel">
          <div class="detail-header">
            <v-icon icon="mdi-folder-open-outline" size="20" color="#3B82F6" class="mr-2" />
            <span class="detail-title">{{ selectedSubsidy.name }} — направления ФЭО</span>
            <v-btn icon="mdi-close" size="x-small" variant="text" class="ml-auto" @click="selectedId = null" />
          </div>

          <!-- KPI mini-cards for selected subsidy -->
          <div class="detail-kpis">
            <div class="dkpi dkpi-budget">
              <div class="dkpi-label">Бюджет (ФЭО)</div>
              <div class="dkpi-val">{{ formatCurrency(selectedBudget) }}</div>
            </div>
            <div class="dkpi dkpi-planned">
              <div class="dkpi-label">Запланировано</div>
              <div class="dkpi-val">{{ formatCurrency(selectedSubsidy.planned) }}</div>
            </div>
            <div class="dkpi dkpi-paid">
              <div class="dkpi-label">Оплачено</div>
              <div class="dkpi-val">{{ formatCurrency(selectedSubsidy.paid) }}</div>
            </div>
            <div class="dkpi dkpi-free" :class="selectedBudget - selectedSubsidy.planned < 0 ? 'dkpi-over' : ''">
              <div class="dkpi-label">{{ selectedBudget - selectedSubsidy.planned < 0 ? 'Превышение' : 'Свободно' }}</div>
              <div class="dkpi-val">{{ formatCurrency(Math.abs(selectedBudget - selectedSubsidy.planned)) }}</div>
            </div>
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
              <div class="d-flex align-center ml-auto" style="gap:8px">
                <v-btn size="small" variant="outlined" color="success" prepend-icon="mdi-file-excel-outline" @click="exportFeoToExcel">Выгрузить</v-btn>
                <v-btn size="small" variant="outlined" prepend-icon="mdi-download-outline" @click="downloadFeoTemplate">Шаблон</v-btn>
                <v-btn size="small" variant="outlined" color="secondary" prepend-icon="mdi-upload-outline" @click="feoImport.show = true">Импорт</v-btn>
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
                <v-btn size="small" variant="tonal" color="primary" prepend-icon="mdi-plus" @click="feoForm.parentId = null; showAddFeoDialog = true">Добавить</v-btn>
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
                      Финансирование по ФЭО
                      <span class="col-resize-handle" @mousedown="feoResize.onResizeStart($event, 'budget')"></span>
                    </th>
                    <th class="feo-th feo-th-num">ПЛАНОВОЕ<br>КОЛ-ВО</th>
                    <th class="feo-th feo-th-num">ПЛАНОВАЯ<br>СУММА</th>
                    <th class="feo-th feo-th-num" :style="feoResize.resizeStyle('spent')">
                      Фактическая сумма
                      <span class="col-resize-handle" @mousedown="feoResize.onResizeStart($event, 'spent')"></span>
                    </th>
                    <th class="feo-th feo-th-num">ОСТАТОК</th>
                    <th class="feo-th feo-th-actions" :style="feoResize.resizeStyle('actions')"></th>
                  </tr>
                </thead>
                <tbody>
                  <template v-for="node in visibleFeoNodes" :key="node.id">
                    <tr
                      v-if="isNodeVisible(node)"
                      class="feo-tr"
                      :class="[
                        `feo-tr--l${node.level}`,
                        feoBudgetFor(node) > 0 && feoPurchasedFor(node) > feoBudgetFor(node) ? 'feo-tr--over' : '',
                        node.hasChildren && node.budget != null && directChildSum(node) > node.budget ? 'feo-tr--children-exceed' : '',
                        dragOverId === node.id ? 'feo-drop-target' : '',
                        dragNodeId === node.id ? 'feo-dragging' : '',
                      ]"
                      draggable="true"
                      @dragstart="onDragStart($event, node)"
                      @dragover.prevent="onDragOver($event, node)"
                      @dragleave="onDragLeave"
                      @drop="onDrop($event, node)"
                      @dragend="onDragEnd"
                    >
                      <!-- Наименование -->
                      <td class="feo-td feo-td-name" :style="{ paddingLeft: `${node.depth * 20 + 8}px` }">
                        <div class="feo-name-inner">
                          <span class="feo-tree-chevron" @click="node.hasChildren ? toggleExpand(node.id) : undefined">
                            <v-icon
                              v-if="node.hasChildren"
                              size="15"
                              :icon="expandedIds.includes(node.id) ? 'mdi-chevron-down' : 'mdi-chevron-right'"
                              color="grey"
                              class="mr-1 cursor-pointer"
                            />
                            <span v-else style="width:16px;display:inline-block" />
                          </span>
                          <v-icon
                            size="16"
                            class="mr-1 flex-shrink-0"
                            :icon="node.hasChildren ? (expandedIds.includes(node.id) ? 'mdi-folder-open' : 'mdi-folder') : 'mdi-file-document-outline'"
                            :color="node.level === 1 ? '#3B82F6' : node.level === 2 ? '#F59E0B' : '#22C55E'"
                          />
                          <span class="feo-name" :class="`feo-name--l${node.level}`">{{ node.name }}</span>
                          <span v-if="node.code" class="feo-code ml-2">{{ node.code }}</span>
                          <span v-if="node.appendix" class="feo-appendix ml-1">{{ node.appendix }}</span>
                        </div>
                      </td>

                      <!-- Финансирование по ФЭО (inline edit) -->
                      <td class="feo-td feo-td-num">
                        <div v-if="isAutoNode(node)" class="text-right">
                          <div class="feo-amount">{{ formatCurrency(feoBudgetFor(node)) }}</div>
                          <v-chip size="x-small" color="blue-grey" variant="tonal"
                            title="Сумма автоматически считается из дочерних направлений"
                          >авто</v-chip>
                        </div>
                        <div v-else-if="inlineBudgetId === node.id" class="d-flex align-center justify-end">
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
                        <div v-else class="feo-amount-cell" @click="startInlineBudget(node)">
                          <span v-if="feoBudgetFor(node) > 0" class="feo-amount">{{ formatCurrency(feoBudgetFor(node)) }}</span>
                          <span v-else class="feo-set-hint">Задать</span>
                        </div>
                      </td>

                      <!-- Плановое количество -->
                      <td class="feo-td feo-td-num">
                        <div v-if="isAutoQtyNode(node)" class="text-right">
                          <div class="feo-amount">{{ feoQtyFor(node) > 0 ? feoQtyFor(node) : '—' }}{{ node.unit ? ` ${node.unit}` : '' }}</div>
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
                        <div v-else class="feo-amount-cell" @click="startInlineQty(node)">
                          <span v-if="feoQtyFor(node) > 0" class="feo-amount">{{ feoQtyFor(node) }}{{ node.unit ? ` ${node.unit}` : '' }}</span>
                          <span v-else class="feo-set-hint">—</span>
                        </div>
                      </td>

                      <!-- Плановая сумма (кол-во × стоимость за ед.) -->
                      <td class="feo-td feo-td-num">
                        <span v-if="feoPlannedTotalFor(node) > 0" class="feo-amount"
                          :style="feoBudgetFor(node) > 0 && feoPlannedTotalFor(node) > feoBudgetFor(node) ? 'color:#EF4444;font-weight:700' : ''"
                        >{{ formatCurrency(feoPlannedTotalFor(node)) }}</span>
                        <span v-else class="feo-amount-empty">—</span>
                      </td>

                      <!-- Фактическая сумма -->
                      <td class="feo-td feo-td-num">
                        <span :class="feoPurchasedFor(node) > 0 ? 'feo-amount feo-amount--link' : 'feo-amount-empty'"
                          :style="(feoBudgetFor(node) > 0 && feoPurchasedFor(node) > feoBudgetFor(node)) || (feoPlannedTotalFor(node) > 0 && feoPurchasedFor(node) > feoPlannedTotalFor(node)) ? 'color:#EF4444;font-weight:700' : ''"
                          :title="feoPurchasedFor(node) > 0 ? 'Открыть закупки по этой категории' : ''"
                          @click="feoPurchasedFor(node) > 0 && router.push(`/orders?feo_category_id=${node.id}`)"
                        >
                          {{ feoPurchasedFor(node) > 0 ? formatCurrency(feoPurchasedFor(node)) : '—' }}
                        </span>
                      </td>

                      <!-- 12-04: Остаток (residual) -->
                      <td class="feo-td feo-td-num">
                        <template v-if="!node.hasChildren">
                          <div v-for="item in Object.values(feoResiduals).filter((r: any) => r.category_id === node.id)" :key="(item as any).feo_item_id">
                            <span
                              :style="(item as any).residual < 0 ? 'color:#EF4444;font-weight:700;font-size:11px' : (item as any).residual === 0 ? 'color:#22C55E;font-size:11px' : 'font-size:11px'"
                              :title="`${(item as any).name}: план ${formatCurrency((item as any).planned_amount)}, факт ${formatCurrency((item as any).used_amount)}`"
                            >
                              {{ (item as any).residual < 0 ? '−' : '' }}{{ formatCurrency(Math.abs((item as any).residual)) }}
                            </span>
                          </div>
                          <span v-if="!Object.values(feoResiduals).some((r: any) => r.category_id === node.id)" class="feo-amount-empty">—</span>
                        </template>
                        <span v-else class="feo-amount-empty">—</span>
                      </td>

                      <!-- Действия -->
                      <td class="feo-td feo-td-actions">
                        <!-- Level 3: кнопка раскрытия позиций / spacer for alignment -->
                        <span class="feo-action-slot"><v-btn v-if="!node.hasChildren"
                          :icon="expandedItemPanels.has(node.id) ? 'mdi-list-box' : 'mdi-list-box-outline'"
                          variant="text" size="x-small"
                          :color="expandedItemPanels.has(node.id) ? 'teal' : 'grey'"
                          title="Показать плановые / фактические позиции"
                          @click="toggleItemPanel(node)"
                        /></span>
                        <v-btn icon="mdi-chevron-up" variant="text" size="x-small" color="grey-darken-1"
                          title="Переместить выше" @click.stop="reorderFeoNode(node, 'up')" />
                        <v-btn icon="mdi-chevron-down" variant="text" size="x-small" color="grey-darken-1"
                          title="Переместить ниже" @click.stop="reorderFeoNode(node, 'down')" />
                        <v-btn icon="mdi-plus-circle-outline" variant="text" size="x-small" color="success"
                          title="Добавить дочернюю" @click="feoForm.parentId = node.id; showAddFeoDialog = true" />
                        <v-btn icon="mdi-cart-outline" variant="text" size="x-small" color="blue"
                          title="Показать закупки по этой категории"
                          @click.stop="router.push(`/orders?feo_category_id=${node.id}`)" />
                        <v-btn icon="mdi-pencil-outline" variant="text" size="x-small" color="primary"
                          title="Редактировать" @click="startFeoEdit(node)" />
                        <v-btn icon="mdi-delete-outline" variant="text" size="x-small" color="error"
                          title="Удалить" @click="confirmFeoDelete(node)" />
                      </td>
                    </tr>

                    <!-- ── Level 5 панель: Плановые vs Фактические ── -->
                    <tr v-if="!node.hasChildren && expandedItemPanels.has(node.id)" :key="`items-${node.id}`">
                      <td colspan="6" style="padding:0 0 0 60px; background:rgba(20,184,166,0.06)">
                        <div style="padding:10px 12px 12px">
                          <!-- Заголовок панели -->
                          <div class="d-flex align-center mb-2" style="gap:8px">
                            <v-icon icon="mdi-compare-horizontal" size="16" color="teal" />
                            <span style="font-size:12px;font-weight:600" class="text-teal-darken-2">Позиции: план vs факт</span>
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
                          <table v-else-if="comparisonData[node.id]" style="width:100%;border-collapse:collapse;font-size:12px">
                            <thead>
                              <tr style="background:#CCFBF1">
                                <th style="padding:4px 8px;text-align:left;color:#0f766e;font-weight:600;border-bottom:1px solid #99F6E4">ПЛАН (Уровень 5)</th>
                                <th style="padding:4px 8px;text-align:right;color:#0f766e;font-weight:600;border-bottom:1px solid #99F6E4;width:90px">Кол-во (план)</th>
                                <th style="padding:4px 8px;text-align:right;color:#0f766e;font-weight:600;border-bottom:1px solid #99F6E4;width:110px">Сумма (план)</th>
                                <th style="padding:4px 8px;text-align:left;color:#0f766e;font-weight:600;border-bottom:1px solid #99F6E4">ФАКТ (из закупок)</th>
                                <th style="padding:4px 8px;text-align:right;color:#0f766e;font-weight:600;border-bottom:1px solid #99F6E4;width:90px">Кол-во (факт)</th>
                                <th style="padding:4px 8px;text-align:right;color:#0f766e;font-weight:600;border-bottom:1px solid #99F6E4;width:90px">Цена</th>
                                <th style="padding:4px 8px;text-align:right;color:#0f766e;font-weight:600;border-bottom:1px solid #99F6E4;width:110px">Сумма (факт)</th>
                                <th style="padding:4px 8px;text-align:right;color:#0f766e;font-weight:600;border-bottom:1px solid #99F6E4;width:100px">Разница</th>
                                <th style="padding:4px 8px;text-align:left;color:#0f766e;font-weight:600;border-bottom:1px solid #99F6E4;width:120px">Контрагент</th>
                                <th style="padding:4px 8px;text-align:center;color:#0f766e;font-weight:600;border-bottom:1px solid #99F6E4;width:80px">Статус</th>
                                <th style="padding:4px 2px;width:80px;border-bottom:1px solid #99F6E4"></th>
                              </tr>
                            </thead>
                            <tbody>
                              <!-- Сопоставленные пары: actual сгруппированы по planned_item_id -->
                              <template v-for="planned in comparisonData[node.id].planned" :key="`p-${planned.id}`">
                                <!-- Найдём все actual для этого planned -->
                                <template v-for="(actual, ai) in comparisonData[node.id].actual.filter(a => a.feo_planned_item_id === planned.id)" :key="`pa-${actual.purchase_item_id}`">
                                  <tr style="border-bottom:1px solid #E0F2FE">
                                    <td style="padding:4px 8px;color:#0c4a6e">
                                      <span v-if="ai === 0">{{ planned.name }}</span>
                                    </td>
                                    <td style="padding:4px 8px;text-align:right;color:#64748b">
                                      <span v-if="ai === 0 && planned.quantity">{{ parseFloat(String(planned.quantity)) }} {{ planned.unit || '' }}</span>
                                    </td>
                                    <td style="padding:4px 8px;text-align:right;color:#64748b">
                                      <span v-if="ai === 0 && planned.amount">{{ formatCurrency(planned.amount) }}</span>
                                    </td>
                                    <td style="padding:4px 8px;color:#166534">
                                      <div>{{ actual.item_name }}</div>
                                      <a
                                        href="javascript:void(0)"
                                        class="feo-purchase-link"
                                        :title="`Перейти в закупку #${actual.purchase_id}`"
                                        @click.stop="router.push(`/orders/${actual.purchase_id}`)"
                                      >
                                        <v-icon icon="mdi-link-variant" size="11" class="mr-1" />
                                        {{ actual.registry_number || (actual.purchase_number != null ? `№ ${actual.purchase_number}` : `Закупка #${actual.purchase_id}`) }}
                                      </a>
                                    </td>
                                    <td style="padding:4px 8px;text-align:right;color:#64748b">{{ actual.quantity ? `${parseFloat(String(actual.quantity))} ${actual.unit || ''}` : '—' }}</td>
                                    <td style="padding:4px 8px;text-align:right;color:#64748b">{{ actual.unit_price ? formatCurrency(actual.unit_price) : '—' }}</td>
                                    <td style="padding:4px 8px;text-align:right;font-weight:500">{{ actual.total_price ? formatCurrency(actual.total_price) : '—' }}</td>
                                    <td v-if="ai === 0" :rowspan="comparisonData[node.id].actual.filter(a => a.feo_planned_item_id === planned.id).length" style="padding:4px 8px;text-align:right">
                                      <span v-if="planned.amount != null" :style="getDiffStyle(planned, comparisonData[node.id].actual.filter(a => a.feo_planned_item_id === planned.id))">
                                        {{ formatCurrency(calcDiff(planned, comparisonData[node.id].actual.filter(a => a.feo_planned_item_id === planned.id))) }}
                                      </span>
                                    </td>
                                    <td style="padding:4px 8px;color:#64748b;font-size:11px">{{ actual.contractor_name || '—' }}</td>
                                    <td style="padding:4px 8px;text-align:center">
                                      <v-icon icon="mdi-check-circle" size="16" color="success" title="Сопоставлено" />
                                    </td>
                                    <td style="padding:2px;text-align:center">
                                      <v-btn v-if="ai === 0" icon="mdi-pencil" size="x-small" variant="text" color="blue"
                                        title="Редактировать плановую позицию"
                                        @click="openEditPlannedItem(planned)"
                                      />
                                      <v-btn icon="mdi-link-off" size="x-small" variant="text" color="grey"
                                        title="Снять сопоставление"
                                        @click="() => { mapTarget.value = actual; mapCategoryId.value = node.id; applyMapping(null) }"
                                      />
                                      <v-btn v-if="ai === 0" icon="mdi-delete-outline" size="x-small" variant="text" color="error"
                                        title="Удалить плановую позицию"
                                        @click="deletePlannedItem(planned)"
                                      />
                                    </td>
                                  </tr>
                                </template>
                                <!-- Плановая без факта -->
                                <tr v-if="comparisonData[node.id].actual.filter(a => a.feo_planned_item_id === planned.id).length === 0"
                                  style="border-bottom:1px solid #E0F2FE">
                                  <td style="padding:4px 8px;color:#0c4a6e">{{ planned.name }}</td>
                                  <td style="padding:4px 8px;text-align:right;color:#64748b">
                                    {{ planned.quantity ? `${parseFloat(String(planned.quantity))} ${planned.unit || ''}` : '—' }}
                                  </td>
                                  <td style="padding:4px 8px;text-align:right;color:#64748b">
                                    {{ planned.amount ? formatCurrency(planned.amount) : '—' }}
                                  </td>
                                  <td style="padding:4px 8px;color:#9ca3af;font-style:italic">—</td>
                                  <td style="padding:4px 8px"></td>
                                  <td style="padding:4px 8px"></td>
                                  <td style="padding:4px 8px"></td>
                                  <td style="padding:4px 8px;text-align:right;color:#9ca3af">{{ planned.amount ? formatCurrency(Number(planned.amount)) : '—' }}</td>
                                  <td style="padding:4px 8px;color:#9ca3af">—</td>
                                  <td style="padding:4px 8px;text-align:center">
                                    <v-icon icon="mdi-clock-outline" size="16" color="warning" title="Не куплено" />
                                  </td>
                                  <td style="padding:2px;text-align:center">
                                    <v-btn icon="mdi-pencil" size="x-small" variant="text" color="blue"
                                      title="Редактировать плановую позицию"
                                      @click="openEditPlannedItem(planned)"
                                    />
                                    <v-btn icon="mdi-delete-outline" size="x-small" variant="text" color="error"
                                      title="Удалить плановую позицию"
                                      @click="deletePlannedItem(planned)"
                                    />
                                  </td>
                                </tr>
                              </template>

                              <!-- Фактические без плана -->
                              <tr v-for="actual in comparisonData[node.id].actual.filter(a => !a.feo_planned_item_id)"
                                :key="`a-${actual.purchase_item_id}`"
                                style="border-bottom:1px solid var(--crm-border);background:rgba(245,158,11,0.06)">
                                <td style="padding:4px 8px;font-style:italic" class="text-medium-emphasis">—</td>
                                <td style="padding:4px 8px"></td>
                                <td style="padding:4px 8px"></td>
                                <td style="padding:4px 8px" class="text-orange-darken-2">
                                  <div>{{ actual.item_name }}</div>
                                  <a
                                    href="javascript:void(0)"
                                    class="feo-purchase-link"
                                    :title="`Перейти в закупку #${actual.purchase_id}`"
                                    @click.stop="router.push(`/orders/${actual.purchase_id}`)"
                                  >
                                    <v-icon icon="mdi-link-variant" size="11" class="mr-1" />
                                    {{ actual.registry_number || (actual.purchase_number != null ? `№ ${actual.purchase_number}` : `Закупка #${actual.purchase_id}`) }}
                                  </a>
                                </td>
                                <td style="padding:4px 8px;text-align:right" class="text-medium-emphasis">{{ actual.quantity ? `${parseFloat(String(actual.quantity))} ${actual.unit || ''}` : '—' }}</td>
                                <td style="padding:4px 8px;text-align:right" class="text-medium-emphasis">{{ actual.unit_price ? formatCurrency(actual.unit_price) : '—' }}</td>
                                <td style="padding:4px 8px;text-align:right;font-weight:500" class="text-orange-darken-2">{{ actual.total_price ? formatCurrency(actual.total_price) : '—' }}</td>
                                <td style="padding:4px 8px"></td>
                                <td style="padding:4px 8px;font-size:11px" class="text-medium-emphasis">{{ actual.contractor_name || '—' }}</td>
                                <td style="padding:4px 8px;text-align:center">
                                  <v-icon icon="mdi-alert-circle-outline" size="16" color="warning" title="Не в плане" />
                                </td>
                                <td style="padding:2px;text-align:center">
                                  <v-btn icon="mdi-link-variant" size="x-small" variant="text" color="teal"
                                    title="Сопоставить с плановой"
                                    @click="openMapDialog(actual, node.id)"
                                  />
                                </td>
                              </tr>

                              <!-- Пусто -->
                              <tr v-if="!comparisonData[node.id].planned.length && !comparisonData[node.id].actual.length">
                                <td colspan="11" style="padding:12px 8px;text-align:center;color:#9ca3af;font-style:italic">
                                  Нет плановых позиций. Добавьте вручную или загрузите из Excel.
                                </td>
                              </tr>
                            </tbody>
                            <!-- Итоговая строка -->
                            <tfoot v-if="comparisonData[node.id].planned.length || comparisonData[node.id].actual.length">
                              <tr style="background:rgba(34,197,94,0.08);font-weight:600;border-top:2px solid rgba(34,197,94,0.3)">
                                <td style="padding:4px 8px" class="text-success">ИТОГО</td>
                                <td style="padding:4px 8px"></td>
                                <td style="padding:4px 8px;text-align:right">
                                  {{ formatCurrency(comparisonData[node.id].planned.reduce((s, p) => s + Number(p.amount || 0), 0)) }}
                                </td>
                                <td style="padding:4px 8px"></td>
                                <td style="padding:4px 8px"></td>
                                <td style="padding:4px 8px"></td>
                                <td style="padding:4px 8px;text-align:right">
                                  {{ formatCurrency(comparisonData[node.id].actual.reduce((s, a) => s + Number(a.total_price || 0), 0)) }}
                                </td>
                                <td style="padding:4px 8px;text-align:right">
                                  <span :class="comparisonData[node.id].planned.reduce((s,p)=>s+Number(p.amount||0),0) >= comparisonData[node.id].actual.reduce((s,a)=>s+Number(a.total_price||0),0) ? 'text-success' : 'text-error'">
                                    {{ formatCurrency(comparisonData[node.id].planned.reduce((s,p)=>s+Number(p.amount||0),0) - comparisonData[node.id].actual.reduce((s,a)=>s+Number(a.total_price||0),0)) }}
                                  </span>
                                </td>
                                <td colspan="3" style="padding:4px 8px"></td>
                              </tr>
                            </tfoot>
                          </table>
                        </div>
                      </td>
                    </tr>
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

                  <!-- Итого -->
                  <tr class="feo-tr feo-tr--total">
                    <td class="feo-td feo-td-name font-weight-bold" style="padding-left:8px">ИТОГО</td>
                    <td class="feo-td feo-td-num font-weight-bold">
                      {{ totalFeoBudget !== null ? formatCurrency(totalFeoBudget) : '—' }}
                    </td>
                    <td class="feo-td feo-td-num font-weight-bold">
                      {{ feoTree.reduce((acc, r) => acc + feoQtyFor(r), 0) > 0 ? feoTree.reduce((acc, r) => acc + feoQtyFor(r), 0) : '—' }}
                    </td>
                    <td class="feo-td feo-td-num font-weight-bold">
                      {{ feoTree.reduce((acc, r) => acc + feoPlannedTotalFor(r), 0) > 0 ? formatCurrency(feoTree.reduce((acc, r) => acc + feoPlannedTotalFor(r), 0)) : '—' }}
                    </td>
                    <td class="feo-td feo-td-num font-weight-bold">{{ formatCurrency(totalFeoPurchased) }}</td>
                    <td class="feo-td" />
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
          <v-select
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
          <v-divider class="my-3" />
          <!-- Финансирование по ФЭО -->
          <div class="d-flex align-center mb-2">
            <span class="text-body-2 font-weight-medium">Финансирование по ФЭО</span>
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
            variant="outlined" density="compact" type="number" hide-details
          />
          <v-divider class="my-3" />
          <!-- Плановое количество -->
          <div class="d-flex align-center mb-2">
            <span class="text-body-2 font-weight-medium">Плановое количество</span>
            <v-btn-toggle
              v-model="feoForm.qtyAuto"
              mandatory
              density="compact"
              class="ml-4"
              color="primary"
            >
              <v-btn :value="false" size="x-small">Вручную</v-btn>
              <v-btn :value="true" size="x-small">Авто из детей</v-btn>
            </v-btn-toggle>
          </div>
          <v-row v-if="!feoForm.qtyAuto" dense>
            <v-col cols="8">
              <v-text-field
                v-model.number="feoForm.planned_quantity"
                label="Количество"
                variant="outlined" density="compact" type="number" hide-details
              />
            </v-col>
            <v-col cols="4">
              <v-combobox
                v-model="feoForm.unit"
                :items="['шт', 'компл', 'кг', 'л', 'м', 'услуга', 'чел.', 'рейс']"
                label="Ед. изм."
                variant="outlined" density="compact" hide-details
              />
            </v-col>
          </v-row>
          <v-divider class="my-3" />
          <!-- Плановая стоимость за ед. -->
          <div class="d-flex align-center mb-2">
            <span class="text-body-2 font-weight-medium">Плановая стоимость за ед.</span>
            <v-btn-toggle
              v-model="feoForm.amtAuto"
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
            v-if="!feoForm.amtAuto"
            v-model.number="feoForm.planned_amount"
            label="Плановая стоимость за ед., ₽"
            variant="outlined" density="compact" type="number" hide-details
          />
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="showAddFeoDialog = false">Отмена</v-btn>
          <v-btn color="primary" :loading="savingFeo" :disabled="!feoForm.name" @click="addFeoCategory">
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
          <v-divider class="my-3" />
          <!-- Финансирование по ФЭО -->
          <div class="d-flex align-center mb-2">
            <span class="text-body-2 font-weight-medium">Финансирование по ФЭО</span>
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
            variant="outlined" density="compact" type="number" hide-details
          />
          <v-alert
            v-if="feoEditForm.hasChildren && feoEditForm.budgetAuto"
            type="info" variant="tonal" density="compact" class="mt-2 text-caption"
          >
            Сумма рассчитывается автоматически из дочерних направлений
          </v-alert>
          <v-divider class="my-3" />
          <!-- Плановое количество -->
          <div class="d-flex align-center mb-2">
            <span class="text-body-2 font-weight-medium">Плановое количество</span>
            <v-btn-toggle
              v-if="feoEditForm.hasChildren"
              v-model="feoEditForm.qtyAuto"
              mandatory
              density="compact"
              class="ml-4"
              color="primary"
            >
              <v-btn :value="false" size="x-small">Вручную</v-btn>
              <v-btn :value="true" size="x-small">Авто из детей</v-btn>
            </v-btn-toggle>
          </div>
          <v-row v-if="!feoEditForm.hasChildren || !feoEditForm.qtyAuto" dense>
            <v-col cols="8">
              <v-text-field
                v-model.number="feoEditForm.planned_quantity"
                label="Количество"
                variant="outlined" density="compact" type="number" hide-details
              />
            </v-col>
            <v-col cols="4">
              <v-combobox
                v-model="feoEditForm.unit"
                :items="['шт', 'компл', 'кг', 'л', 'м', 'услуга', 'чел.', 'рейс']"
                label="Ед. изм."
                variant="outlined" density="compact" hide-details
              />
            </v-col>
          </v-row>
          <v-alert
            v-if="feoEditForm.hasChildren && feoEditForm.qtyAuto"
            type="info" variant="tonal" density="compact" class="mt-2 text-caption"
          >
            Количество рассчитывается автоматически из дочерних направлений
          </v-alert>
          <v-divider class="my-3" />
          <!-- Плановая стоимость за ед. -->
          <div class="d-flex align-center mb-2">
            <span class="text-body-2 font-weight-medium">Плановая стоимость за ед.</span>
            <v-btn-toggle
              v-if="feoEditForm.hasChildren"
              v-model="feoEditForm.amtAuto"
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
            v-if="!feoEditForm.hasChildren || !feoEditForm.amtAuto"
            v-model.number="feoEditForm.planned_amount"
            label="Плановая стоимость за ед., ₽"
            variant="outlined" density="compact" type="number" hide-details
          />
          <v-alert
            v-if="feoEditForm.hasChildren && feoEditForm.amtAuto"
            type="info" variant="tonal" density="compact" class="mt-2 text-caption"
          >
            Сумма рассчитывается автоматически из дочерних направлений
          </v-alert>
          <v-checkbox v-model="feoEditForm.is_active" label="Активна" density="compact" hide-details class="mt-2" />
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="showEditFeoDialog = false">Отмена</v-btn>
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
            text="Для роли «Ответственный исполнитель» ФИО не указывается — исполнитель определяется для каждой закупки из её данных."
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
          <v-alert type="info" variant="tonal" density="compact" class="mb-4" text="Загруженные шаблоны используются при генерации документов для этой субсидии вместо глобальных." />

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
          <v-text-field v-model="overrideForm.signatory" label="Подписант (ФИО, должность)" variant="outlined" density="compact" class="mb-3" hide-details />
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

          <!-- Step 3: Result -->
          <template v-if="feoImport.step === 3">
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
          <v-spacer />
          <v-btn variant="text" @click="closeFeoImport">{{ feoImport.step === 3 ? 'Закрыть' : 'Отмена' }}</v-btn>
          <v-btn v-if="feoImport.step === 1" color="primary" :loading="feoImport.loading"
            :disabled="!feoImport.file" @click="doFeoImport">Далее</v-btn>
          <v-btn v-if="feoImport.step === 2" color="success" variant="flat"
            :loading="feoImport.loading" :disabled="!feoMappingValid"
            @click="doFeoMappedImport">Импортировать</v-btn>
          <v-btn v-if="feoImport.step === 3" color="primary" variant="flat"
            @click="closeFeoImport">Готово</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Snackbar ── -->
    <v-snackbar
      v-model="snack.show"
      :color="snack.color"
      :timeout="snack.color === 'error' ? -1 : 3000"
      location="bottom right"
      :multi-line="snack.color === 'error'"
      max-width="600">
      {{ snack.text }}
      <template #actions>
        <v-btn variant="text" @click="snack.show = false">Закрыть</v-btn>
      </template>
    </v-snackbar>

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
          <v-text-field v-model="editPlannedDialog.amount" label="Сумма (план), ₽" type="number" variant="outlined" density="compact" />
        </v-card-text>
        <v-card-actions class="px-4 pb-3">
          <v-spacer />
          <v-btn variant="text" @click="editPlannedDialog.show = false">Отмена</v-btn>
          <v-btn color="primary" variant="tonal" :loading="editPlannedDialog.saving" @click="saveEditPlannedItem">Сохранить</v-btn>
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
          <v-text-field
            v-model="plannedItemForm.name"
            label="Наименование товара/услуги"
            variant="outlined" density="compact" class="mb-3"
            placeholder="Например: Ноутбук HP 15 Intel i5"
            autofocus
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
          <v-text-field
            v-model.number="plannedItemForm.amount"
            label="Плановая сумма (₽)" type="number"
            variant="outlined" density="compact" suffix="₽"
          />
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
          История план-графика
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

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, reactive, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { apiFetch } from '@/api'
import { useGlobalSubsidy } from '@/composables/useGlobalSubsidy'
import { useResizableColumns } from '@/composables/useResizableColumns'
import { useCardView } from '@/composables/useCardView'
import BudgetHistoryDialog from '@/components/BudgetHistoryDialog.vue'
import ContractorPicker from '@/components/ContractorPicker.vue'
import BudgetBar from '@/components/BudgetBar.vue'
import RegistryExportButton from '@/components/RegistryExportButton.vue'
import { useRegistryExport } from '@/composables/useRegistryExport'

const { globalSubsidyId } = useGlobalSubsidy()

const feoResize = useResizableColumns('feo-table', {
  name: 0, budget: 180, spent: 180, actions: 200,
})

const router = useRouter()
const route  = useRoute()

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
}

interface FeoCategory {
  id: number; parent_id: number | null; subsidy_id: number
  level: number; name: string; code: string | null; appendix: string | null
  is_active: boolean; budget: number | null; planned_quantity: number | null; planned_amount: number | null; unit: string | null
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
const expandedIds     = ref<number[]>([])
const selectedId      = ref<number | null>(null)
const selectedYear    = ref<number>(new Date().getFullYear())

// 12-04: Residuals state
const feoResiduals = ref<Record<number, {
  feo_item_id: number
  name: string
  category_id: number
  planned_amount: number
  used_amount: number
  residual: number
  linked_purchase_ids: number[]
}>>({})
const residualsLoading = ref(false)

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

async function loadApproverUsers() {
  if (approverUsersList.value.length) return
  try {
    const data = await apiFetch<any[]>('/users/')
    approverUsersList.value = data
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
  if (ok) showSnack(`Скопировано: ${text}`, 'success')
  else showSnack(`Не удалось скопировать. Выделите и нажмите Ctrl+C: ${text}`, 'error')
}

// Template management state
const showTemplateDialog  = ref(false)
const templateSubsidy     = ref<SubsidyRow | null>(null)
const contractTemplates   = ref<Record<number, boolean>>({})
const subsidyTemplatesList = ref<Array<{ doc_type: string; label: string; has_custom: boolean; has_global: boolean }>>([])
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
const feoImport = reactive({
  show: false, step: 1, file: null as File | null, fileList: [] as File[],
  loading: false,
  result: null as { created: number; updated?: number; skipped: number; errors: { row: number; name: string; message: string }[]; updated_details?: { row: number; name: string; reason: string }[]; skipped_details?: { row: number; name: string; reason: string }[] } | null,
  previewData: null as any,
  selectedSheet: '',
})

const feoImportTargetSubsidy = ref<number | null>(null)

// FEO column mapping
const FEO_TARGET_FIELDS = [
  { value: 'subsidy',  title: 'Субсидия (название)',                          required: true },
  { value: 'lvl2',     title: 'Уровень 2 — Направление расходов по ФЭО',     required: true },
  { value: 'qty_lvl2',  title: 'Количество для Уровня 2 (Направление)',      required: false },
  { value: 'unit_lvl2', title: 'Единица измерения для Уровня 2',             required: false },
  { value: 'amt_lvl2', title: 'Плановая стоимость за ед. для Уровня 2 (Направление)',   required: false },
  { value: 'lvl3',     title: 'Уровень 3 — Тип расходов по ФЭО',            required: false },
  { value: 'qty_lvl3', title: 'Количество для Уровня 3 (Тип расходов)',      required: false },
  { value: 'unit_lvl3', title: 'Единица измерения для Уровня 3',             required: false },
  { value: 'amt_lvl3', title: 'Плановая стоимость за ед. для Уровня 3 (Тип расходов)', required: false },
  { value: 'lvl4',     title: 'Уровень 4 — Конкретизированный',              required: false },
  { value: 'qty_lvl4', title: 'Количество для Уровня 4 (Конкретизир.)',      required: false },
  { value: 'unit_lvl4', title: 'Единица измерения для Уровня 4',             required: false },
  { value: 'amt_lvl4', title: 'Плановая стоимость за ед. для Уровня 4 (Конкретизир.)', required: false },
  { value: 'lvl5',     title: 'Уровень 5 — Плановый товар / услуга',        required: false },
  { value: 'quantity', title: 'Количество для Уровня 5 (Товар/услуга)',      required: false },
  { value: 'unit',     title: 'Единица измерения (Ур.5: шт, кг, услуга)',   required: false },
  { value: 'item_amt', title: 'Плановая стоимость за ед. Ур.5 (товар/услуга)', required: false },
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
    amt_lvl2:  ['плановая стоимость за ед. (ур.2)', 'плановая стоимость (ур.2)', 'стоимость за ед. (ур.2)', 'стоимость ур.2', 'плановая сумма (ур.2)', 'сумма ур.2', 'план.сумма ур.2'],
    lvl3:      ['уровень 3', 'тип расходов', 'level 3'],
    qty_lvl3:  ['кол-во (ур.3)', 'кол-во ур.3', 'количество (ур.3)'],
    unit_lvl3: ['ед. изм. (ур.3)', 'ед.изм. ур.3', 'единица ур.3'],
    amt_lvl3:  ['плановая стоимость за ед. (ур.3)', 'плановая стоимость (ур.3)', 'стоимость за ед. (ур.3)', 'стоимость ур.3', 'плановая сумма (ур.3)', 'сумма ур.3'],
    lvl4:      ['уровень 4', 'конкретизир', 'level 4'],
    qty_lvl4:  ['кол-во (ур.4)', 'кол-во ур.4', 'количество (ур.4)'],
    unit_lvl4: ['ед. изм. (ур.4)', 'ед.изм. ур.4', 'единица ур.4'],
    amt_lvl4:  ['плановая стоимость за ед. (ур.4)', 'плановая стоимость (ур.4)', 'стоимость за ед. (ур.4)', 'стоимость ур.4', 'плановая сумма (ур.4)', 'сумма ур.4'],
    lvl5:     ['уровень 5', 'плановый товар', 'level 5'],
    code:     ['код'],
    appendix: ['приложение'],
    budget:   ['финансирование', 'бюджет'],
    quantity: ['количество (ур.5)', 'количество ур.5', 'кол-во (ур.5)', 'кол-во ур.5'],
    unit:     ['ед. изм', 'ед.изм', 'единица'],
    item_amt: ['плановая стоимость за ед. (ур.5)', 'плановая стоимость (ур.5)', 'стоимость за ед. (ур.5)', 'стоимость ур.5', 'сумма плановая', 'сумма (ур.5)', 'сумма ур'],
    active:   ['активна', 'активен'],
  }
  for (const [field, kws] of Object.entries(KEYWORDS)) {
    for (let i = 0; i < headers.length; i++) {
      const h = headers[i].toLowerCase()
      if (kws.some(kw => h.includes(kw))) {
        mapping[field] = i
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
  notes: string | null
  is_active: boolean
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
  contract_number: string | null
  contractor_name: string | null
}
const expandedItemPanels = ref<Set<number>>(new Set())
const comparisonData = ref<Record<number, { planned: FeoPlannedItem[]; actual: FeoActualItem[] }>>({})
const loadingComparison = ref<Set<number>>(new Set())

// Map dialog
const showMapDialog = ref(false)
const mapTarget = ref<FeoActualItem | null>(null)
const mapCategoryId = ref<number | null>(null)
const mappingInProgress = ref(false)

// Add planned item dialog
const showAddPlannedDialog = ref(false)
const addPlannedCategoryId = ref<number | null>(null)
const savingPlannedItem = ref(false)
const plannedItemForm = ref({ name: '', quantity: null as number | null, unit: '', amount: null as number | null })

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
}

function openMapDialog(item: FeoActualItem, categoryId: number) {
  mapTarget.value = item
  mapCategoryId.value = categoryId
  showMapDialog.value = true
}

async function applyMapping(plannedItemId: number | null) {
  if (!mapTarget.value) return
  mappingInProgress.value = true
  try {
    await apiFetch(`/feo-planned-items/map?purchase_item_id=${mapTarget.value.purchase_item_id}&planned_item_id=${plannedItemId ?? ''}`, {
      method: 'POST',
    })
    showMapDialog.value = false
    if (mapCategoryId.value) await refreshComparison(mapCategoryId.value)
  } finally {
    mappingInProgress.value = false
  }
}

function openAddPlannedItem(categoryId: number) {
  addPlannedCategoryId.value = categoryId
  plannedItemForm.value = { name: '', quantity: null, unit: '', amount: null }
  showAddPlannedDialog.value = true
}

async function savePlannedItem() {
  if (!addPlannedCategoryId.value || !plannedItemForm.value.name.trim()) return
  savingPlannedItem.value = true
  try {
    await apiFetch('/feo-planned-items/', {
      method: 'POST',
      body: JSON.stringify({
        feo_category_id: addPlannedCategoryId.value,
        name: plannedItemForm.value.name.trim(),
        quantity: plannedItemForm.value.quantity,
        unit: plannedItemForm.value.unit || null,
        amount: plannedItemForm.value.amount,
        is_active: true,
      }),
    })
    showAddPlannedDialog.value = false
    await refreshComparison(addPlannedCategoryId.value)
  } finally {
    savingPlannedItem.value = false
  }
}

async function deletePlannedItem(item: FeoPlannedItem) {
  await apiFetch(`/feo-planned-items/${item.id}`, { method: 'DELETE' })
  await refreshComparison(item.feo_category_id)
}

// ── Diff helpers ──────────────────────────────────────────────────────────
function calcDiff(planned: FeoPlannedItem, actuals: FeoActualItem[]): number {
  const factSum = actuals.reduce((s, a) => s + Number(a.total_price || 0), 0)
  return Number(planned.amount || 0) - factSum
}
function getDiffStyle(planned: FeoPlannedItem, actuals: FeoActualItem[]): string {
  const diff = calcDiff(planned, actuals)
  return diff >= 0 ? 'color:#166534;font-weight:600' : 'color:#DC2626;font-weight:600'
}

// ── Edit planned item dialog ─────────────────────────────────────────────
const editPlannedDialog = reactive({
  show: false, saving: false,
  id: 0, feo_category_id: 0,
  name: '', quantity: '' as string | number, unit: '', amount: '' as string | number,
})

function openEditPlannedItem(item: FeoPlannedItem) {
  editPlannedDialog.id = item.id
  editPlannedDialog.feo_category_id = item.feo_category_id
  editPlannedDialog.name = item.name
  editPlannedDialog.quantity = item.quantity != null ? parseFloat(String(item.quantity)) : ''
  editPlannedDialog.unit = item.unit || ''
  editPlannedDialog.amount = item.amount != null ? parseFloat(String(item.amount)) : ''
  editPlannedDialog.show = true
}

async function saveEditPlannedItem() {
  editPlannedDialog.saving = true
  try {
    await apiFetch(`/feo-planned-items/${editPlannedDialog.id}`, {
      method: 'PUT',
      body: JSON.stringify({
        feo_category_id: editPlannedDialog.feo_category_id,
        name: editPlannedDialog.name,
        quantity: editPlannedDialog.quantity !== '' ? Number(editPlannedDialog.quantity) : null,
        unit: editPlannedDialog.unit || null,
        amount: editPlannedDialog.amount !== '' ? Number(editPlannedDialog.amount) : null,
        notes: null,
        is_active: true,
      }),
    })
    editPlannedDialog.show = false
    await refreshComparison(editPlannedDialog.feo_category_id)
  } catch (e: any) {
    showSnack(e.detail || 'Ошибка сохранения', 'error')
  } finally {
    editPlannedDialog.saving = false
  }
}

// Contractor override state
const showOverrideDialog = ref(false)
const savingOverride = ref(false)
const overrideSubsidyId = ref<number | null>(null)
const overrideForm = ref({
  org_type: '', inn: '', kpp: '', ogrn: '',
  signatory: '', signatory_basis: '', address: '', postal_address: '',
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

const snack = ref({ show: false, text: '', color: 'success' })

const contractors = ref<{ id: number; name: string; inn?: string }[]>([])

const form = ref({ name: '', year: new Date().getFullYear(), budget: 0, description: '', contractor_id: null as number | null, agreement_text: '' as string, basis_doc_number: '' as string, basis_doc_date: '' as string })
const editForm = ref({ id: 0, name: '', year: new Date().getFullYear(), budget: 0, description: '', contractor_id: null as number | null, agreement_text: '' as string, basis_doc_number: '' as string, basis_doc_date: '' as string, grantor_name: '' as string, ministry_name: '' as string, extra_contract_clause_1: null as string | null, extra_contract_clause_2: null as string | null })
const feoForm  = ref({ parentId: null as number | null, name: '', code: '', appendix: '', budget: null as number | null, budgetAuto: false, planned_quantity: null as number | null, qtyAuto: false, planned_amount: null as number | null, amtAuto: false, unit: '' as string })
const feoEditForm = ref({ name: '', code: '', appendix: '', budget: null as number | null, budgetAuto: false, planned_quantity: null as number | null, qtyAuto: false, planned_amount: null as number | null, amtAuto: false, unit: '' as string, is_active: true, hasChildren: false, parent_id: null as number | null })

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
  { title: 'Запланировано', key: 'plan_schedule', align: 'end' as const },
  { title: 'Заказано', key: 'ordered', align: 'end' as const },
  { title: 'Оплачено', key: 'paid', align: 'end' as const },
  { title: 'Контрагент', key: 'contractor_name' },
  { title: 'ФЭО', key: 'feo_filled', align: 'center' as const },
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

const selectedSubsidy = computed(() =>
  allSubsidies.value.find(s => s.id === selectedId.value) ?? null
)

const selectedBudget = computed(() => {
  if (!selectedSubsidy.value) return 0
  // Use totalFeoBudget from local FEO tree if loaded, otherwise feo_budget_total from API
  if (totalFeoBudget.value !== null && totalFeoBudget.value > 0) return totalFeoBudget.value
  return selectedSubsidy.value.feo_budget_total || selectedSubsidy.value.budget
})

const totals = computed(() => ({
  budget:        filteredSubsidies.value.reduce((s, x) => s + (x.feo_budget_total || x.budget), 0),
  planned:       filteredSubsidies.value.reduce((s, x) => s + x.planned,        0),
  plan_schedule: filteredSubsidies.value.reduce((s, x) => s + x.plan_schedule,  0),
  ordered:       filteredSubsidies.value.reduce((s, x) => s + x.ordered,        0),
  contracted:    filteredSubsidies.value.reduce((s, x) => s + (x.contracted || 0), 0),
  paid:          filteredSubsidies.value.reduce((s, x) => s + x.paid,           0),
}))

// ── FEO tree ──────────────────────────────────────
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
      node.depth = byId[c.parent_id].depth + 1
    } else {
      roots.push(node)
    }
  })
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
  return all
})

const totalFeoBudget = computed(() => {
  let sum = 0; let any = false
  for (const r of feoTree.value) { const v = feoBudgetFor(r); if (v > 0) { sum += v; any = true } }
  return any ? sum : null
})

const totalFeoPurchased = computed(() => feoTree.value.reduce((a, r) => a + feoPurchasedFor(r), 0))

// Бюджет по ФЭО:
// Правило: budget = NULL → авто из детей; budget = значение → ручной режим (приоритет)
function feoBudgetFor(node: FeoNode): number {
  if (!node.hasChildren) return node.budget != null ? Number(node.budget) : 0
  // Ручной режим: если явно задан бюджет — использовать его
  if (node.budget != null) return Number(node.budget)
  // Авто: сумма всех детей
  return node.children.reduce((acc, child) => acc + feoBudgetFor(child), 0)
}

// Только прямые дети (для проверки превышения)
function directChildSum(node: FeoNode): number {
  return node.children.reduce((acc, child) => acc + feoBudgetFor(child), 0)
}

function isAutoNode(node: FeoNode): boolean {
  if (!node.hasChildren) return false
  return node.budget == null
}

// Фактически запланированные расходы:
// - листовая категория (нет детей) → берём закупки, привязанные напрямую к ней
// - родительская категория → ТОЛЬКО сумма детей (закупки напрямую на уровне 1/2 не считаются)
function feoPurchasedFor(node: FeoNode): number {
  if (!node.hasChildren) {
    return purchaseTotals.value[node.id] || 0
  }
  return node.children.reduce((acc, child) => acc + feoPurchasedFor(child), 0)
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
function feoQtyFor(node: FeoNode): number {
  if (!node.hasChildren) return node.planned_quantity != null ? Number(node.planned_quantity) : 0
  if (node.planned_quantity != null) return Number(node.planned_quantity)
  return node.children.reduce((acc, child) => acc + feoQtyFor(child), 0)
}

function isAutoQtyNode(node: FeoNode): boolean {
  if (!node.hasChildren) return false
  return node.planned_quantity == null
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
function feoPlannedTotalFor(node: FeoNode): number {
  if (node.hasChildren) {
    return node.children.reduce((acc, child) => acc + feoPlannedTotalFor(child), 0)
  }
  // Leaf: qty × unit_price (both must be set on THIS node, not inherited)
  const qty = node.planned_quantity != null ? Number(node.planned_quantity) : 0
  const unitPrice = node.planned_amount != null ? Number(node.planned_amount) : 0
  if (qty > 0 && unitPrice > 0) return qty * unitPrice
  return 0
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
      planned: s.total_planned, paid: s.total_paid, contracted: s.total_confirmed,
      plan_schedule: s.total_plan_schedule ?? 0,
      ordered: s.total_ordered ?? 0,
      feo_budget_total: s.feo_budget_total ?? 0,
      feo_filled: s.feo_filled ?? false,
      contractor_id: s.contractor_id ?? null,
      contractor_name: s.contractor_name ?? null,
      contractor_inn: s.contractor_inn ?? null,
    }))
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
  const a = document.createElement('a'); a.href = url; a.download = 'feo_categories_template.xlsx'; a.click()
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

async function doFeoMappedImport() {
  if (!feoImport.file) return
  feoImport.loading = true
  try {
    const m = feoDragMapping.value
    const sheet = feoCurrentSheet.value
    const params = new URLSearchParams({
      sheet_name: feoImport.selectedSheet,
      header_row_offset: String(sheet?.header_row_offset ?? 0),
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
    })
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
    feoImport.result = await res.json()
    feoImport.step = 3
    showSnack(`Импорт завершён: создано ${feoImport.result!.created}`)
    // Reload FEO tree immediately
    if (selectedId.value) { await loadFeo(selectedId.value); syncFeoFilled() }
  } catch {
    showSnack('Ошибка импорта', 'error')
  } finally {
    feoImport.loading = false
  }
}

function closeFeoImport() {
  const wasCreated = (feoImport.result?.created ?? 0) > 0
  feoImport.show = false; feoImport.step = 1
  feoImport.file = null; feoImport.fileList = []; feoImport.result = null
  feoImport.previewData = null; feoImport.selectedSheet = ''
  feoDragMapping.value = {}; feoIgnoredCols.value = []
  if (wasCreated && selectedId.value) { loadFeo(selectedId.value); syncFeoFilled() }
}

async function loadFeo(subsidyId: number) {
  loadingFeo.value = true
  feoCategories.value = []
  purchaseTotals.value = {}
  try {
    const [cats, totals] = await Promise.all([
      apiFetch<FeoCategory[]>(`/feo-categories/?subsidy_id=${subsidyId}`),
      apiFetch<Record<number, number>>(`/feo-categories/purchase-totals?subsidy_id=${subsidyId}`),
    ])
    feoCategories.value = cats
    purchaseTotals.value = totals
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
    snack.value = { show: true, text: e?.message || 'Ошибка экспорта', color: 'error' }
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
    snack.value = { show: true, text: e?.message || 'Ошибка сравнения', color: 'error' }
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
    snack.value = { show: true, text: 'Редакция ФЭО сохранена', color: 'success' }
  } catch (e: any) {
    snack.value = { show: true, text: e?.payload?.message || e?.message || 'Ошибка сохранения редакции', color: 'error' }
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
    allSubsidies.value.push({ ...res, planned: 0, paid: 0, contracted: 0, plan_schedule: 0, ordered: 0 })
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
      body: JSON.stringify({ name: editForm.value.name, year: editForm.value.year, budget: editForm.value.budget, description: editForm.value.description || null, contractor_id: editForm.value.contractor_id, agreement_text: editForm.value.agreement_text || null, basis_doc_number: editForm.value.basis_doc_number || null, basis_doc_date: editForm.value.basis_doc_date || null, grantor_name: editForm.value.grantor_name || null, ministry_name: editForm.value.ministry_name || null, extra_contract_clause_1: editForm.value.extra_contract_clause_1 || null, extra_contract_clause_2: editForm.value.extra_contract_clause_2 || null })
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
        budget: feoForm.value.budgetAuto ? null : (feoForm.value.budget ?? null),
        planned_quantity: feoForm.value.qtyAuto ? null : (feoForm.value.planned_quantity ?? null),
        planned_amount: feoForm.value.amtAuto ? null : (feoForm.value.planned_amount ?? null),
        unit: feoForm.value.unit || null,
      })
    })
    feoCategories.value.push(res)
    showAddFeoDialog.value = false
    feoForm.value = { parentId: null, name: '', code: '', appendix: '', budget: null, budgetAuto: false, planned_quantity: null, qtyAuto: false, planned_amount: null, amtAuto: false, unit: '' }
    showSnack('Направление добавлено')
    if (selectedId.value) await loadFeo(selectedId.value)
    syncFeoFilled()
  } catch {
    showSnack('Ошибка добавления направления', 'error')
  } finally {
    savingFeo.value = false
  }
}

// Update calculated_budget on the card after FEO budget changes (using tree logic)
function syncFeoFilled() {
  if (!selectedId.value) return
  // Recalculate from tree: use feoBudgetFor on root nodes
  const total = feoTree.value.reduce((sum, root) => sum + feoBudgetFor(root), 0)
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
  }
  showEditFeoDialog.value = true
}

async function updateFeoCategory() {
  if (!feoEditTarget.value) return
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
        budget: feoEditForm.value.budgetAuto ? null : (feoEditForm.value.budget ?? null),
        planned_quantity: feoEditForm.value.qtyAuto ? null : (feoEditForm.value.planned_quantity ?? null),
        planned_amount: feoEditForm.value.amtAuto ? null : (feoEditForm.value.planned_amount ?? null),
        unit: feoEditForm.value.unit || null,
      })
    })
    showEditFeoDialog.value = false
    showSnack('Направление обновлено')
    if (selectedId.value) await loadFeo(selectedId.value)
    syncFeoFilled()
  } catch {
    showSnack('Ошибка обновления', 'error')
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
  const foundUser = a.user_id ? (approverUsersList.value.find(u => u.id === a.user_id) ?? null) : null
  approverForm.value = {
    role_name: a.role_name,
    full_name: a.full_name,
    order_num: a.order_num,
    is_default: a.is_default,
    can_initiate: a.can_initiate,
    show_feo_path: a.show_feo_path ?? false,
    user_id: a.user_id ?? null,
    selectedUser: foundUser,
  }
  loadApproverUsers().then(() => {
    // re-resolve after load in case list was empty when dialog opened
    if (a.user_id && !approverForm.value.selectedUser) {
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
    const list = await apiFetch<Array<{ doc_type: string; label: string; has_custom: boolean; has_global: boolean }>>(
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
      throw new Error(err.detail || 'Ошибка загрузки')
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
  a.download = `template_${docType}_subsidy_${templateSubsidy.value.id}.docx`
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
  a.download = 'template_guide.docx'
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

function formatCurrency(v: number) {
  return (v || 0).toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' ₽'
}

function formatCurrencyShort(v: number) {
  if (!v) return '0 ₽'
  if (Math.abs(v) >= 1_000_000_000) return (v / 1_000_000_000).toFixed(1) + ' млрд ₽'
  if (Math.abs(v) >= 1_000_000)     return (v / 1_000_000).toFixed(1)     + ' млн ₽'
  if (Math.abs(v) >= 1_000)         return (v / 1_000).toFixed(0)         + ' тыс ₽'
  return v.toLocaleString('ru-RU') + ' ₽'
}

function showSnack(text: string, color = 'success') {
  snack.value = { show: true, text, color }
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
      signatory: data.signatory || '',
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
    snack.value = { show: true, text: 'Мероприятие добавлено', color: 'success' }
  } catch (e: any) {
    snack.value = { show: true, text: e.message || 'Ошибка', color: 'error' }
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
    snack.value = { show: true, text: 'Мероприятие обновлено', color: 'success' }
  } catch (e: any) {
    snack.value = { show: true, text: e.message || 'Ошибка', color: 'error' }
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
    snack.value = { show: true, text: e.message || 'Ошибка скачивания', color: 'error' }
  }
}

async function deleteEvent(eventId: number) {
  if (!selectedId.value) return
  try {
    await apiFetch(`/events/${eventId}`, { method: 'DELETE' })
    await loadEvents(selectedId.value)
    snack.value = { show: true, text: 'Мероприятие удалено', color: 'success' }
  } catch (e: any) {
    snack.value = { show: true, text: e.message || 'Ошибка', color: 'error' }
  }
}

onMounted(() => {
  loadAll()
  loadTemplateVars()
})
</script>

<style scoped>
/* ── Layout ── */
.subsidies-page {
  padding: 20px 24px;
  max-width: 1600px;
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

.sc-header {
  display: flex; align-items: flex-start; justify-content: space-between;
  margin-bottom: 8px;
}
.sc-actions { display: flex; gap: 2px; flex-shrink: 0; margin-left: 4px; }
.sc-name {
  font-size: 14px; font-weight: 700; color: var(--crm-text);
  line-height: 1.3; word-break: break-word;
}
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
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 12px;
  margin-bottom: 20px;
}
.dkpi {
  border-radius: 10px; padding: 14px 16px;
  border: 1px solid var(--crm-border);
  border-top: 3px solid #CBD5E1;
}
.dkpi-budget    { border-top-color: #3B82F6; }
.dkpi-planned   { border-top-color: #F59E0B; }
.dkpi-paid      { border-top-color: #22C55E; }
.dkpi-free      { border-top-color: #8B5CF6; }
.dkpi-over      { border-top-color: #EF4444; }

.dkpi-label { font-size: 11px; color: var(--crm-text-faint); margin-bottom: 4px; }
.dkpi-val   { font-size: 16px; font-weight: 700; color: var(--crm-text); }

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
.feo-th-actions { min-width: 200px; position: sticky; right: 0; z-index: 5; }
.feo-td {
  padding: 8px 12px; border-bottom: 1px solid var(--crm-border);
  vertical-align: middle;
}
.feo-td-name { min-width: 0; }
.feo-name-inner { display: flex; align-items: center; min-width: 0; }
.feo-td-num { text-align: right; }
.feo-td-actions {
  text-align: right; white-space: nowrap; min-width: 200px;
  position: sticky; right: 0; z-index: 2;
  background: var(--crm-surface);
  box-shadow: inset 1px 0 0 var(--crm-border-strong);
}
.feo-td-actions .v-btn { background: transparent !important; }
/* sticky-колонку действий держим непрозрачной во всех состояниях строки,
   иначе при горизонтальном скролле сквозь неё видны другие колонки */
.feo-tr:hover .feo-td-actions { background: var(--crm-surface-alt); }
.feo-tr--l1 .feo-td-actions { background: var(--crm-surface-alt); }
.feo-tr--l1:hover .feo-td-actions { background: var(--crm-surface-hover); }
.feo-tr--over .feo-td-actions,
.feo-tr--children-exceed .feo-td-actions {
  background: linear-gradient(rgba(239,68,68,0.08), rgba(239,68,68,0.08)), var(--crm-surface) !important;
}
.feo-tr--over:hover .feo-td-actions {
  background: linear-gradient(rgba(239,68,68,0.13), rgba(239,68,68,0.13)), var(--crm-surface-alt) !important;
}
.feo-action-slot { display: inline-flex; width: 28px; justify-content: center; vertical-align: middle; }
.feo-tr:last-child .feo-td { border-bottom: none; }
.feo-tr:hover .feo-td { background: var(--crm-surface-alt); }
.feo-tr--l1 .feo-td { background: var(--crm-surface-alt); }
.feo-tr--l1:hover .feo-td { background: var(--crm-surface-hover); }
.feo-tr--over .feo-td { background: rgba(239,68,68,0.08) !important; }
.feo-tr--over:hover .feo-td { background: rgba(239,68,68,0.13) !important; }
.feo-tr--over .feo-amount { color: #EF4444; font-weight: 700; }
.feo-tr--children-exceed .feo-td { background: rgba(239,68,68,0.08) !important; }
.feo-tr--children-exceed .feo-amount { color: #EF4444; font-weight: 700; }
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
</style>
