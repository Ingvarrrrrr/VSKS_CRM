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
        <!-- ── Cards grid ── -->
        <div class="subsidies-grid">
          <div
            v-for="s in filteredSubsidies" :key="s.id"
            class="subsidy-card"
            :class="{ 'subsidy-card--active': selectedId === s.id }"
            @click="toggleSelect(s.id)"
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
                <v-btn icon="mdi-pencil" size="x-small" variant="text" color="primary" @click.stop="startEdit(s)" />
                <v-btn icon="mdi-delete" size="x-small" variant="text" color="error" @click.stop="confirmDelete(s)" />
              </div>
            </div>

            <div class="sc-budget">{{ formatCurrencyShort(s.budget || s.calculated_budget || 0) }}</div>
            <div class="sc-budget-label">{{ s.budget ? 'Бюджет' : 'Рассчитанный' }}</div>

            <div class="sc-mini-row">
              <div class="sc-mini">
                <div class="sc-mini-label">Запланировано</div>
                <div class="sc-mini-val" style="color: #F59E0B;">{{ formatCurrencyShort(s.planned) }}</div>
              </div>
              <div class="sc-mini">
                <div class="sc-mini-label">Законтрактовано</div>
                <div class="sc-mini-val" style="color: #3B82F6;">{{ formatCurrencyShort(s.contracted || 0) }}</div>
              </div>
              <div class="sc-mini">
                <div class="sc-mini-label">Оплачено</div>
                <div class="sc-mini-val" style="color: #22C55E;">{{ formatCurrencyShort(s.paid) }}</div>
              </div>
            </div>

            <v-progress-linear
              :model-value="pct(s.planned, s.budget || s.calculated_budget)"
              :color="progressColor(pct(s.planned, s.budget || s.calculated_budget))"
              height="6" rounded class="mt-3"
            />
            <div class="sc-pct">{{ pct(s.planned, s.budget || s.calculated_budget) }}% запланировано</div>
          </div>
        </div>

        <!-- ── Summary bar ── -->
        <div class="summary-bar">
          <div class="summary-item">
            <span class="summary-label">Субсидий</span>
            <span class="summary-value">{{ filteredSubsidies.length }}</span>
          </div>
          <div class="summary-sep" />
          <div class="summary-item">
            <span class="summary-label">Итого бюджет</span>
            <span class="summary-value">{{ formatCurrency(totals.budget) }}</span>
          </div>
          <div class="summary-sep" />
          <div class="summary-item">
            <span class="summary-label">Рассчитанный</span>
            <span class="summary-value" style="color: #8B5CF6;">{{ formatCurrency(totals.calculated_budget || 0) }}</span>
          </div>
          <div class="summary-sep" />
          <div class="summary-item">
            <span class="summary-label">Запланировано</span>
            <span class="summary-value" style="color: #F59E0B;">{{ formatCurrency(totals.planned) }}</span>
          </div>
          <div class="summary-sep" />
          <div class="summary-item">
            <span class="summary-label">Законтрактовано</span>
            <span class="summary-value" style="color: #3B82F6;">{{ formatCurrency(totals.contracted) }}</span>
          </div>
          <div class="summary-sep" />
          <div class="summary-item">
            <span class="summary-label">Оплачено</span>
            <span class="summary-value" style="color: #22C55E;">{{ formatCurrency(totals.paid) }}</span>
          </div>
          <div class="summary-sep" />
          <div class="summary-item">
            <span class="summary-label">Свободно</span>
            <span class="summary-value" :style="{ color: (totals.budget || totals.calculated_budget || 0) - totals.planned < 0 ? '#EF4444' : '#3B82F6' }">
              {{ formatCurrency((totals.budget || totals.calculated_budget || 0) - totals.planned) }}
            </span>
          </div>
        </div>

        <!-- ── Detail panel ── -->
        <div v-if="selectedSubsidy" class="detail-panel">
          <div class="detail-header">
            <v-icon icon="mdi-folder-open-outline" size="20" color="#3B82F6" class="mr-2" />
            <span class="detail-title">{{ selectedSubsidy.name }}</span>
            <span class="detail-budget ml-2" v-if="selectedSubsidy.calculated_budget">
              ({{ formatCurrency(selectedSubsidy.calculated_budget) }})
            </span>
            <span class="detail-budget ml-2" v-else-if="selectedSubsidy.budget">
              ({{ formatCurrency(selectedSubsidy.budget) }})
            </span>
            <span class="detail-subtitle ml-2 text-grey">— направления ФЭО</span>
            <v-btn icon="mdi-close" size="x-small" variant="text" class="ml-auto" @click="selectedId = null" />
          </div>

          <!-- KPI mini-cards for selected subsidy -->
          <div class="detail-kpis">
            <div class="dkpi dkpi-budget">
              <div class="dkpi-label">Бюджет (ручной)</div>
              <div class="dkpi-val">{{ formatCurrency(selectedSubsidy.budget) }}</div>
            </div>
            <div class="dkpi dkpi-calculated">
              <div class="dkpi-label">Рассчитанный</div>
              <div class="dkpi-val">{{ formatCurrency(selectedSubsidy.calculated_budget || 0) }}</div>
            </div>
            <div class="dkpi dkpi-planned">
              <div class="dkpi-label">Запланировано</div>
              <div class="dkpi-val">{{ formatCurrency(selectedSubsidy.planned) }}</div>
            </div>
            <div class="dkpi dkpi-paid">
              <div class="dkpi-label">Оплачено</div>
              <div class="dkpi-val">{{ formatCurrency(selectedSubsidy.paid) }}</div>
            </div>
            <div class="dkpi dkpi-free" :class="selectedSubsidy.budget - selectedSubsidy.planned < 0 ? 'dkpi-over' : ''">
              <div class="dkpi-label">{{ (selectedSubsidy.budget || selectedSubsidy.calculated_budget || 0) - selectedSubsidy.planned < 0 ? 'Превышение' : 'Свободно' }}</div>
              <div class="dkpi-val">{{ formatCurrency(Math.abs((selectedSubsidy.budget || selectedSubsidy.calculated_budget || 0) - selectedSubsidy.planned)) }}</div>
            </div>
          </div>

          <!-- FEO categories -->
          <div v-if="loadingFeo" class="d-flex justify-center py-8">
            <v-progress-circular indeterminate color="primary" />
          </div>

          <div v-else>
            <div class="detail-feo-header">
              <span class="chart-card-title">Направления ФЭО</span>
              <v-btn size="small" variant="outlined" color="success" prepend-icon="mdi-file-excel-outline" class="ml-auto mr-2" @click="exportFeoToExcel">
                Выгрузить
              </v-btn>
              <v-btn size="small" variant="tonal" prepend-icon="mdi-plus" @click="showAddFeoDialog = true">
                Добавить направление
              </v-btn>
            </div>

            <div v-if="feoCategories.length === 0" class="feo-empty">
              <v-icon icon="mdi-folder-off" size="40" color="grey-lighten-2" />
              <div class="text-caption text-medium-emphasis mt-2">Нет категорий ФЭО</div>
            </div>

            <!-- FEO table with 3 columns -->
            <div v-else class="feo-table-wrap">
              <table class="feo-table">
                <thead>
                  <tr>
                    <th class="feo-th feo-th-name">Наименование</th>
                    <th class="feo-th feo-th-num">Финансирование по ФЭО</th>
                    <th class="feo-th feo-th-num">Фактически запланировано</th>
                    <th class="feo-th feo-th-actions"></th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="node in visibleFeoNodes"
                    :key="node.id"
                    class="feo-tr"
                    :class="[
                      `feo-tr--l${node.level}`,
                      feoBudgetFor(node) > 0 && feoPurchasedFor(node) > feoBudgetFor(node) ? 'feo-tr--over' : ''
                    ]"
                  >
                    <!-- Наименование -->
                    <td class="feo-td feo-td-name" :style="{ paddingLeft: `${node.depth * 20 + 8}px` }">
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
                    </td>

                    <!-- Финансирование по ФЭО -->
                    <td class="feo-td feo-td-num">
                      <!-- Авто-режим: дети имеют суммы -->
                      <template v-if="isAutoNode(node)">
                        <span class="feo-amount">{{ formatCurrency(feoBudgetFor(node)) }}</span>
                        <v-chip size="x-small" color="blue-grey" variant="tonal" class="ml-1"
                          title="Сумма автоматически считается из дочерних направлений"
                        >авто</v-chip>
                      </template>
                      <!-- Ручной режим: задана сумма -->
                      <template v-else-if="feoBudgetFor(node) > 0">
                        <span class="feo-amount">{{ formatCurrency(feoBudgetFor(node)) }}</span>
                      </template>
                      <!-- Ручной режим: пусто — подсказка задать -->
                      <template v-else>
                        <span class="feo-set-hint" title="Нажмите ✏️ чтобы задать сумму"
                          @click="startFeoEdit(node)"
                        >Задать</span>
                      </template>
                    </td>

                    <!-- Фактически запланировано -->
                    <td class="feo-td feo-td-num">
                      <span :class="feoPurchasedFor(node) > 0 ? 'feo-amount' : 'feo-amount-empty'">
                        {{ feoPurchasedFor(node) > 0 ? formatCurrency(feoPurchasedFor(node)) : '—' }}
                      </span>
                    </td>

                    <!-- Действия -->
                    <td class="feo-td feo-td-actions">
                      <v-btn
                        icon="mdi-pencil"
                        variant="text"
                        size="x-small"
                        color="primary"
                        class="mr-1"
                        title="Редактировать"
                        @click="startFeoEdit(node)"
                      />
                      <v-btn
                        v-if="!node.hasChildren"
                        icon="mdi-delete"
                        variant="text"
                        size="x-small"
                        color="error"
                        title="Удалить"
                        @click="confirmFeoDelete(node)"
                      />
                      <v-btn
                        v-if="node.level < 3"
                        icon="mdi-plus"
                        variant="text"
                        size="x-small"
                        color="success"
                        title="Добавить дочернее направление"
                        @click="feoForm.parentId = node.id; showAddFeoDialog = true"
                      />
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

      </template>
    </template>

    <!-- ── Add Subsidy Dialog ── -->
    <v-dialog v-model="showAddDialog" max-width="520">
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
          <v-textarea v-model="form.description" label="Описание" variant="outlined" density="compact" rows="2" class="mt-3" hide-details />
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
    <v-dialog v-model="showEditDialog" max-width="520">
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
          <v-textarea v-model="editForm.description" label="Описание" variant="outlined" density="compact" rows="2" class="mt-3" hide-details />
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
            <v-alert type="error" variant="tonal" class="mb-3">
              Нельзя удалить <strong>{{ deleteTarget?.name }}</strong>: есть связанные закупки.
              Сначала удалите или перенесите их.
            </v-alert>
            <v-btn block color="primary" variant="tonal" prepend-icon="mdi-cart-outline" @click="goToLinkedPurchases">
              Перейти к закупкам субсидии
            </v-btn>
          </template>
          <template v-else>
            Удалить <strong>{{ deleteTarget?.name }}</strong>? Действие нельзя отменить.
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
    <v-dialog v-model="showAddFeoDialog" max-width="520">
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
          <div class="d-flex align-center mb-2">
            <span class="text-body-2 font-weight-medium">Финансирование по ФЭО</span>
            <v-switch
              v-model="feoForm.budgetAuto"
              label="Авто из детей"
              density="compact"
              hide-details
              class="ml-4"
              color="primary"
            />
          </div>
          <v-text-field
            v-if="!feoForm.budgetAuto"
            v-model.number="feoForm.budget"
            label="Сумма финансирования, ₽"
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
    <v-dialog v-model="showEditFeoDialog" max-width="520">
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
          <v-divider class="my-3" />
          <div class="d-flex align-center mb-2">
            <span class="text-body-2 font-weight-medium">Финансирование по ФЭО</span>
            <!-- "Авто" только у родительских категорий (есть дети) -->
            <v-switch
              v-if="feoEditForm.hasChildren"
              v-model="feoEditForm.budgetAuto"
              label="Авто из детей"
              density="compact"
              hide-details
              class="ml-4"
              color="primary"
            />
          </div>
          <!-- Для листовых категорий поле всегда видно; для родительских — только в ручном режиме -->
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
    <v-dialog v-model="showDeleteFeoDialog" max-width="420">
      <v-card class="dialog-card">
        <v-card-title class="dialog-title">
          <v-icon icon="mdi-alert-circle-outline" color="error" class="mr-2" />
          Удалить направление?
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="showDeleteFeoDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          <v-alert v-if="feoDeleteError" type="error" variant="tonal" class="mb-3">{{ feoDeleteError }}</v-alert>
          <template v-else>
            Удалить направление <strong>{{ feoDeleteTarget?.name }}</strong>? Действие нельзя отменить.
          </template>
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="showDeleteFeoDialog = false">Отмена</v-btn>
          <v-btn v-if="!feoDeleteError" color="error" :loading="savingFeo" @click="deleteFeoCategory">Удалить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Approvers Dialog ── -->
    <v-dialog v-model="showApproversDialog" max-width="700" scrollable>
      <v-card class="dialog-card">
        <v-card-title class="dialog-title">
          <v-icon icon="mdi-account-multiple" color="teal" class="mr-2" />
          Согласующие: {{ approversSubsidy?.name }}
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="showApproversDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pa-0">
          <v-data-table
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
          <v-btn color="teal" variant="tonal" prepend-icon="mdi-plus" @click="startAddApprover">
            Добавить
          </v-btn>
          <v-spacer />
          <v-btn variant="text" @click="showApproversDialog = false">Закрыть</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Approver Add/Edit Dialog ── -->
    <v-dialog v-model="showApproverFormDialog" max-width="480" :persistent="true">
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
          <v-text-field
            v-model="approverForm.full_name"
            label="ФИО *"
            variant="outlined"
            density="compact"
            class="mb-3"
            hide-details
          />
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
            :disabled="!approverForm.role_name || !approverForm.full_name"
            @click="saveApprover"
          >
            {{ approverEditTarget ? 'Сохранить' : 'Добавить' }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Contract Template Dialog ── -->
    <v-dialog v-model="showTemplateDialog" max-width="480">
      <v-card class="dialog-card">
        <v-card-title class="dialog-title">
          <v-icon icon="mdi-file-document-outline" color="indigo" class="mr-2" />
          Шаблон договора
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="showTemplateDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          <div class="text-caption text-medium-emphasis mb-3">{{ templateSubsidy?.name }}</div>
          <v-alert
            v-if="templateExists"
            type="success" variant="tonal" density="compact" class="mb-3"
          >
            Шаблон загружен. При генерации договора для этой субсидии будет использоваться этот файл вместо стандартного.
          </v-alert>
          <v-alert
            v-else
            type="info" variant="tonal" density="compact" class="mb-3"
          >
            Шаблон не загружен. Будет использоваться стандартный шаблон договора.
          </v-alert>

          <div class="d-flex align-center gap-2">
            <v-file-input
              v-model="templateFile"
              label="Выбрать .docx файл"
              accept=".docx"
              density="compact"
              variant="outlined"
              hide-details
              prepend-icon=""
              prepend-inner-icon="mdi-paperclip"
              class="flex-grow-1"
            />
            <v-btn
              color="indigo"
              :loading="templateUploading"
              :disabled="!templateFile || !templateFile.length"
              @click="uploadTemplate"
            >
              Загрузить
            </v-btn>
          </div>
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-btn
            v-if="templateExists"
            variant="outlined"
            color="indigo"
            prepend-icon="mdi-download"
            @click="downloadTemplate"
          >
            Скачать
          </v-btn>
          <v-spacer />
          <v-btn v-if="templateExists" variant="text" color="error" @click="deleteTemplate">Удалить</v-btn>
          <v-btn variant="text" @click="showTemplateDialog = false">Закрыть</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Snackbar ── -->
    <v-snackbar v-model="snack.show" :color="snack.color" :timeout="3000" location="bottom right">
      {{ snack.text }}
    </v-snackbar>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { apiFetch } from '@/api'

const router = useRouter()
const route  = useRoute()

interface SubsidyRow {
  id: number; name: string; year: number; budget: number
  description?: string; planned: number; paid: number; contracted: number
}

interface FeoCategory {
  id: number; parent_id: number | null; subsidy_id: number
  level: number; name: string; code: string | null; appendix: string | null
  is_active: boolean; budget: number | null
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

const showAddDialog      = ref(false)
const showEditDialog     = ref(false)
const showDeleteDialog   = ref(false)
const showAddFeoDialog   = ref(false)
const showEditFeoDialog  = ref(false)
const showDeleteFeoDialog = ref(false)

// Approvers state
const showApproversDialog    = ref(false)
const showApproverFormDialog = ref(false)
const loadingApprovers       = ref(false)
const savingApprover         = ref(false)
const approversSubsidy       = ref<SubsidyRow | null>(null)
const approversList          = ref<SubsidyApprover[]>([])
const approverEditTarget     = ref<SubsidyApprover | null>(null)
const approverForm = ref({ role_name: '', full_name: '', order_num: 0, is_default: true, can_initiate: false, show_feo_path: false })

// Contract template state
const showTemplateDialog  = ref(false)
const templateSubsidy     = ref<SubsidyRow | null>(null)
const templateExists      = ref(false)
const templateUploading   = ref(false)
const templateFile        = ref<File[]>([])
const contractTemplates   = ref<Record<number, boolean>>({})
const deleteTarget       = ref<SubsidyRow | null>(null)
const deleteErrorLinked  = ref(false)
const feoEditTarget      = ref<FeoCategory | null>(null)
const feoDeleteTarget    = ref<FeoCategory | null>(null)
const feoDeleteError     = ref('')

const snack = ref({ show: false, text: '', color: 'success' })

const form = ref({ name: '', year: new Date().getFullYear(), budget: 0, description: '' })
const editForm = ref({ id: 0, name: '', year: new Date().getFullYear(), budget: 0, description: '' })
const feoForm  = ref({ parentId: null as number | null, name: '', code: '', appendix: '', budget: null as number | null, budgetAuto: false })
const feoEditForm = ref({ name: '', code: '', appendix: '', budget: null as number | null, budgetAuto: false, is_active: true, hasChildren: false })

// ── Computed ──────────────────────────────────────
const availableYears = computed(() =>
  [...new Set(allSubsidies.value.map(s => s.year))].sort((a, b) => b - a)
)

const filteredSubsidies = computed(() =>
  allSubsidies.value.filter(s => s.year === selectedYear.value)
)

const selectedSubsidy = computed(() =>
  allSubsidies.value.find(s => s.id === selectedId.value) ?? null
)

const totals = computed(() => ({
  budget:      filteredSubsidies.value.reduce((s, x) => s + x.budget,      0),
  calculated_budget: filteredSubsidies.value.reduce((s, x) => s + (x.calculated_budget || 0), 0),
  planned:     filteredSubsidies.value.reduce((s, x) => s + x.planned,     0),
  contracted:  filteredSubsidies.value.reduce((s, x) => s + (x.contracted || 0), 0),
  paid:        filteredSubsidies.value.reduce((s, x) => s + x.paid,        0),
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

function flattenVisible(nodes: FeoNode[]): FeoNode[] {
  const result: FeoNode[] = []
  for (const node of nodes) {
    result.push(node)
    if (node.hasChildren && expandedIds.value.includes(node.id)) {
      result.push(...flattenVisible(node.children))
    }
  }
  return result
}

const visibleFeoNodes = computed(() => flattenVisible(feoTree.value))

// Бюджет по ФЭО:
// - Листовой узел: всегда ручное значение
// - Родительский: если хоть у одного ребёнка есть сумма → авто-сумма (node.budget игнорируется)
//                 если ни у кого нет → используем node.budget (ручное)
function feoBudgetFor(node: FeoNode): number {
  if (!node.hasChildren) return node.budget != null ? Number(node.budget) : 0
  const childSum = node.children.reduce((acc, child) => acc + feoBudgetFor(child), 0)
  if (childSum > 0) return childSum   // авто-режим: дети имеют суммы
  return node.budget != null ? Number(node.budget) : 0  // ручной режим
}

function isAutoNode(node: FeoNode): boolean {
  if (!node.hasChildren) return false
  return node.children.some(c => feoBudgetFor(c) > 0)
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

// ── Data load ─────────────────────────────────────
async function loadAll() {
  loading.value = true
  try {
    const charts = await apiFetch<any>('/dashboard/charts')
    allSubsidies.value = charts.subsidy_stats.map((s: any) => ({
      id: s.id, name: s.name, year: s.year, budget: s.budget,
      planned: s.total_planned, paid: s.total_paid, contracted: s.total_confirmed,
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
  const match = cd.match(/filename=([^;]+)/)
  a.href = url; a.download = match ? match[1] : 'feo_export.xlsx'; a.click()
  URL.revokeObjectURL(url)
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

// ── Actions ───────────────────────────────────────
function toggleSelect(id: number) {
  if (selectedId.value === id) { selectedId.value = null; return }
  selectedId.value = id
  loadFeo(id)
}

function startEdit(s: SubsidyRow) {
  editForm.value = { id: s.id, name: s.name, year: s.year, budget: s.budget, description: s.description || '' }
  showEditDialog.value = true
}

function confirmDelete(s: SubsidyRow) {
  deleteTarget.value = s
  deleteErrorLinked.value = false
  showDeleteDialog.value = true
}

async function addSubsidy() {
  saving.value = true
  try {
    const res = await apiFetch<any>('/subsidies/', {
      method: 'POST',
      body: JSON.stringify({ name: form.value.name, year: form.value.year, budget: form.value.budget, description: form.value.description || null })
    })
    allSubsidies.value.push({ ...res, planned: 0, paid: 0, contracted: 0 })
    showAddDialog.value = false
    form.value = { name: '', year: new Date().getFullYear(), budget: 0, description: '' }
    showSnack('Субсидия добавлена')
  } catch {
    showSnack('Ошибка добавления', 'error')
  } finally {
    saving.value = false
  }
}

async function updateSubsidy() {
  saving.value = true
  try {
    const res = await apiFetch<any>(`/subsidies/${editForm.value.id}`, {
      method: 'PUT',
      body: JSON.stringify({ name: editForm.value.name, year: editForm.value.year, budget: editForm.value.budget, description: editForm.value.description || null })
    })
    const i = allSubsidies.value.findIndex(s => s.id === res.id)
    if (i !== -1) allSubsidies.value[i] = { ...allSubsidies.value[i], ...res }
    showEditDialog.value = false
    showSnack('Субсидия обновлена')
  } catch {
    showSnack('Ошибка сохранения', 'error')
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
    if (e?.status === 409 || e?.detail?.includes('закупк')) {
      deleteErrorLinked.value = true
    } else {
      showSnack(e?.detail || 'Ошибка удаления', 'error')
    }
  } finally {
    saving.value = false
  }
}

function goToLinkedPurchases() {
  showDeleteDialog.value = false
  router.push(`/orders?subsidy_id=${deleteTarget.value?.id}`)
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
        budget: feoForm.value.budgetAuto ? null : (feoForm.value.budget || null),
      })
    })
    feoCategories.value.push(res)
    showAddFeoDialog.value = false
    feoForm.value = { parentId: null, name: '', code: '', appendix: '', budget: null, budgetAuto: false }
    showSnack('Направление добавлено')
    if (selectedId.value) await loadFeo(selectedId.value)
  } catch {
    showSnack('Ошибка добавления направления', 'error')
  } finally {
    savingFeo.value = false
  }
}

function startFeoEdit(node: FeoNode) {
  feoEditTarget.value = node
  // "Авто из детей" — только если у категории есть дети И бюджет не задан вручную
  const autoMode = node.hasChildren && node.budget === null
  feoEditForm.value = {
    name: node.name,
    code: node.code || '',
    appendix: node.appendix || '',
    budget: node.budget ?? null,
    budgetAuto: autoMode,
    is_active: node.is_active,
    hasChildren: node.hasChildren,
  }
  showEditFeoDialog.value = true
}

async function updateFeoCategory() {
  if (!feoEditTarget.value) return
  savingFeo.value = true
  try {
    const res = await apiFetch<FeoCategory>(`/feo-categories/${feoEditTarget.value.id}`, {
      method: 'PUT',
      body: JSON.stringify({
        subsidy_id: feoEditTarget.value.subsidy_id,
        parent_id: feoEditTarget.value.parent_id,
        name: feoEditForm.value.name,
        code: feoEditForm.value.code || null,
        appendix: feoEditForm.value.appendix || null,
        is_active: feoEditForm.value.is_active,
        budget: feoEditForm.value.budgetAuto ? null : (feoEditForm.value.budget || null),
      })
    })
    const idx = feoCategories.value.findIndex(c => c.id === res.id)
    if (idx >= 0) feoCategories.value[idx] = res
    showEditFeoDialog.value = false
    showSnack('Направление обновлено')
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
    feoCategories.value = feoCategories.value.filter(c => c.id !== feoDeleteTarget.value!.id)
    showDeleteFeoDialog.value = false
    showSnack('Направление удалено', 'warning')
  } catch (e: any) {
    feoDeleteError.value = e?.detail || 'Ошибка удаления'
  } finally {
    savingFeo.value = false
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
  if (role === 'Ответственный исполнитель' && !approverForm.value.full_name) {
    approverForm.value.full_name = RESPONSIBLE_PLACEHOLDER
  }
}

function startAddApprover() {
  approverEditTarget.value = null
  approverForm.value = { role_name: '', full_name: '', order_num: approversList.value.length + 1, is_default: true, can_initiate: false, show_feo_path: false }
  showApproverFormDialog.value = true
}

function startEditApprover(a: SubsidyApprover) {
  approverEditTarget.value = a
  approverForm.value = { role_name: a.role_name, full_name: a.full_name, order_num: a.order_num, is_default: a.is_default, can_initiate: a.can_initiate, show_feo_path: a.show_feo_path ?? false }
  showApproverFormDialog.value = true
}

async function saveApprover() {
  if (!approversSubsidy.value) return
  savingApprover.value = true
  const sid = approversSubsidy.value.id
  try {
    if (approverEditTarget.value) {
      const updated = await apiFetch<SubsidyApprover>(`/subsidies/${sid}/approvers/${approverEditTarget.value.id}`, {
        method: 'PUT',
        body: JSON.stringify(approverForm.value),
      })
      const idx = approversList.value.findIndex(a => a.id === updated.id)
      if (idx >= 0) approversList.value[idx] = updated
    } else {
      const created = await apiFetch<SubsidyApprover>(`/subsidies/${sid}/approvers`, {
        method: 'POST',
        body: JSON.stringify(approverForm.value),
      })
      approversList.value.push(created)
    }
    showApproverFormDialog.value = false
    showSnack(approverEditTarget.value ? 'Обновлено' : 'Добавлено')
  } catch {
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

// ── Contract template management ──────────────────
async function openTemplateDialog(s: SubsidyRow) {
  templateSubsidy.value = s
  templateFile.value = []
  showTemplateDialog.value = true
  try {
    const res = await apiFetch<{ exists: boolean }>(`/subsidies/${s.id}/contract-template/status`)
    templateExists.value = res.exists
    contractTemplates.value[s.id] = res.exists
  } catch {
    templateExists.value = false
  }
}

async function uploadTemplate() {
  if (!templateSubsidy.value || !templateFile.value?.length) return
  templateUploading.value = true
  try {
    const token = localStorage.getItem('auth_token')
    const fd = new FormData()
    fd.append('file', templateFile.value[0])
    const res = await fetch(`/api/subsidies/${templateSubsidy.value.id}/contract-template`, {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: fd,
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || 'upload failed')
    }
    templateExists.value = true
    contractTemplates.value[templateSubsidy.value.id] = true
    templateFile.value = []
    showSnack('Шаблон договора загружен')
  } catch (e: any) {
    showSnack(e.message || 'Ошибка загрузки шаблона', 'error')
  } finally {
    templateUploading.value = false
  }
}

async function downloadTemplate() {
  if (!templateSubsidy.value) return
  const token = localStorage.getItem('auth_token')
  const res = await fetch(`/api/subsidies/${templateSubsidy.value.id}/contract-template/download`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) { showSnack('Ошибка скачивания', 'error'); return }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `contract_template_subsidy_${templateSubsidy.value.id}.docx`
  a.click()
  URL.revokeObjectURL(url)
}

async function deleteTemplate() {
  if (!templateSubsidy.value) return
  try {
    await apiFetch(`/subsidies/${templateSubsidy.value.id}/contract-template`, { method: 'DELETE' })
    templateExists.value = false
    contractTemplates.value[templateSubsidy.value.id] = false
    showSnack('Шаблон договора удалён', 'warning')
  } catch {
    showSnack('Ошибка удаления шаблона', 'error')
  }
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
  return (v || 0).toLocaleString('ru-RU', { maximumFractionDigits: 0 }) + ' ₽'
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

onMounted(loadAll)
</script>

<style scoped>
/* ── Layout ── */
.subsidies-page {
  padding: 20px 24px;
  max-width: 1600px;
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
.page-title    { font-size: 26px; font-weight: 700; color: #111827; line-height: 1.2; }
.page-subtitle { font-size: 13px; color: #6B7280; margin-top: 2px; }

/* ── Empty state ── */
.empty-state {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; padding: 64px 0; color: #9CA3AF;
}

/* ── Subsidies grid ── */
.subsidies-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}

.subsidy-card {
  background: #fff;
  border-radius: 12px;
  border: 2px solid transparent;
  box-shadow: 0 1px 4px rgba(0,0,0,0.07);
  padding: 18px 20px;
  cursor: pointer;
  transition: transform 0.15s, box-shadow 0.15s, border-color 0.15s;
}
.subsidy-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(0,0,0,0.12);
}
.subsidy-card--active {
  border-color: #3B82F6;
  box-shadow: 0 0 0 4px rgba(59,130,246,0.12), 0 4px 16px rgba(0,0,0,0.1);
}

.sc-header {
  display: flex; align-items: flex-start; justify-content: space-between;
  margin-bottom: 8px;
}
.sc-actions { display: flex; gap: 2px; flex-shrink: 0; margin-left: 4px; }
.sc-name {
  font-size: 14px; font-weight: 700; color: #111827;
  line-height: 1.3; word-break: break-word;
}
.sc-budget      { font-size: 22px; font-weight: 700; color: #111827; }
.sc-budget-label{ font-size: 11px; color: #9CA3AF; margin-bottom: 12px; }

.sc-mini-row { display: flex; gap: 20px; }
.sc-mini-label { font-size: 11px; color: #9CA3AF; margin-bottom: 2px; }
.sc-mini-val   { font-size: 13px; font-weight: 600; }

.sc-pct { font-size: 11px; color: #9CA3AF; margin-top: 4px; }

/* ── Summary bar ── */
.summary-bar {
  display: flex; align-items: center; gap: 0;
  background: #fff;
  border-radius: 12px;
  border: 1px solid rgba(0,0,0,0.07);
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  padding: 14px 24px;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 16px;
}
.summary-item  { display: flex; flex-direction: column; gap: 2px; }
.summary-sep   { width: 1px; height: 32px; background: #E5E7EB; flex-shrink: 0; }
.summary-label { font-size: 11px; color: #9CA3AF; text-transform: uppercase; letter-spacing: 0.04em; }
.summary-value { font-size: 15px; font-weight: 700; color: #111827; }

/* ── Detail panel ── */
.detail-panel {
  background: #fff;
  border-radius: 12px;
  border: 1px solid rgba(0,0,0,0.07);
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  padding: 20px 24px;
  margin-bottom: 20px;
}
.detail-header {
  display: flex; align-items: center;
  margin-bottom: 16px;
}
.detail-title {
  font-size: 15px; font-weight: 600; color: #374151;
}
.detail-budget {
  font-size: 14px; font-weight: 500; color: #8B5CF6;
}
.detail-subtitle {
  font-size: 13px;
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
  border: 1px solid rgba(0,0,0,0.07);
  border-top: 3px solid #CBD5E1;
}
.dkpi-budget    { border-top-color: #3B82F6; }
.dkpi-calculated { border-top-color: #8B5CF6; }
.dkpi-planned   { border-top-color: #F59E0B; }
.dkpi-paid      { border-top-color: #22C55E; }
.dkpi-free      { border-top-color: #8B5CF6; }
.dkpi-over      { border-top-color: #EF4444; }

.dkpi-label { font-size: 11px; color: #9CA3AF; margin-bottom: 4px; }
.dkpi-val   { font-size: 16px; font-weight: 700; color: #111827; }

/* FEO section */
.detail-feo-header {
  display: flex; align-items: center;
  margin-bottom: 12px;
}
.chart-card-title {
  font-size: 14px; font-weight: 600; color: #374151;
}
.feo-empty {
  display: flex; flex-direction: column; align-items: center;
  padding: 32px 0; color: #9CA3AF;
}

/* FEO table */
.feo-table-wrap {
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  overflow-x: hidden;
}
.feo-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
}
.feo-th {
  font-size: 11px; font-weight: 600; color: #6B7280;
  text-transform: uppercase; letter-spacing: 0.05em;
  background: #F9FAFB; padding: 9px 12px;
  text-align: left;
  border-bottom: 1px solid #E5E7EB;
}
.feo-th-num { text-align: right; width: 180px; }
.feo-th-name { width: auto; }
.feo-th-actions { width: 90px; }
.feo-td {
  padding: 8px 12px; border-bottom: 1px solid #F3F4F6;
  vertical-align: middle;
}
.feo-td-name { display: flex; align-items: center; min-width: 0; }
.feo-td-num { text-align: right; }
.feo-td-actions { text-align: right; white-space: nowrap; }
.feo-tr:last-child .feo-td { border-bottom: none; }
.feo-tr:hover .feo-td { background: #F9FAFB; }
.feo-tr--l1 .feo-td { background: #FAFBFF; }
.feo-tr--l1:hover .feo-td { background: #EFF6FF; }
.feo-tr--over .feo-td { background: #FEF2F2 !important; }
.feo-tr--over:hover .feo-td { background: #FEE2E2 !important; }
.feo-tr--over .feo-amount { color: #DC2626; font-weight: 700; }
.feo-name { font-size: 13px; font-weight: 500; color: #111827; white-space: normal; word-break: break-word; min-width: 0; flex: 1; }
.feo-name--l1 { font-weight: 700; font-size: 13px; }
.feo-name--l2 { font-weight: 600; }
.feo-name--l3 { font-weight: 400; color: #374151; }
.feo-code {
  font-size: 11px; color: #6B7280; background: #F3F4F6;
  border-radius: 4px; padding: 1px 5px; font-family: monospace; white-space: nowrap;
}
.feo-appendix { font-size: 11px; color: #9CA3AF; white-space: nowrap; }
.feo-amount { font-size: 13px; font-weight: 500; color: #111827; }
.feo-amount-empty { font-size: 13px; color: #9CA3AF; }
.feo-set-hint {
  font-size: 12px; color: #3B82F6; cursor: pointer; text-decoration: underline dotted;
}
.feo-set-hint:hover { color: #2563EB; }
.feo-tree-chevron { display: inline-flex; align-items: center; }
.cursor-pointer { cursor: pointer; }

/* ── Dialogs ── */
.dialog-card {}
.dialog-title {
  display: flex; align-items: center;
  font-size: 16px !important; font-weight: 600 !important;
  padding: 16px 20px !important;
}
</style>
