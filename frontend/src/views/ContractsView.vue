<template>
  <v-container fluid class="pa-4">
    <!-- Header -->
    <div class="d-flex align-center justify-space-between mb-4">
      <div>
        <h1 class="text-h5 font-weight-bold">Реестр договоров</h1>
        <span class="text-body-2 text-medium-emphasis">
          {{ filtered.length }} из {{ contracts.length }} записей
        </span>
      </div>
      <div class="d-flex gap-2">
        <v-btn v-if="isAdmin" variant="outlined" prepend-icon="mdi-database-import" @click="migrateDialog = true">
          Мигрировать из закупок
        </v-btn>
        <v-btn variant="outlined" prepend-icon="mdi-file-upload-outline" color="info"
          @click="importDialog.show = true"
          @dragover.prevent.stop
          @dragenter.prevent.stop
          @drop.prevent.stop="onButtonDrop"
          class="import-drop-btn"
          :class="{ 'import-drop-btn--hover': btnDragOver }"
          @dragenter="btnDragOver = true" @dragleave="btnDragOver = false"
        >
          Импорт из файла
        </v-btn>
        <v-btn variant="outlined" prepend-icon="mdi-content-duplicate" color="warning" @click="checkDuplicates" :loading="dupLoading">
          Проверить дубли
        </v-btn>
        <v-btn variant="outlined" prepend-icon="mdi-file-excel-outline" color="success" @click="exportDialog = true">
          Скачать реестр
        </v-btn>
        <v-btn color="primary" prepend-icon="mdi-plus" @click="openCreate">Добавить</v-btn>
        <v-btn variant="tonal" prepend-icon="mdi-view-column" size="small" @click="showColumnPicker = true">Колонки</v-btn>
      </div>
    </div>

    <!-- ── Filters ── -->
    <v-card class="mb-4" variant="outlined" rounded="lg">
      <v-card-text class="py-2 px-3">
        <div class="d-flex align-center gap-1 mb-2">
          <v-icon size="16" color="grey">mdi-filter</v-icon>
          <span class="text-caption font-weight-medium text-medium-emphasis">ФИЛЬТРЫ (мульти-выбор)</span>
          <v-spacer />
          <v-chip color="primary" variant="tonal" prepend-icon="mdi-cash-multiple" size="small" class="mr-2">
            Сумма: {{ formatMoneyUtil(filteredSum) }}
          </v-chip>
          <v-btn v-if="hasFilters" variant="text" size="x-small" color="error" prepend-icon="mdi-filter-remove" @click="clearFilters">
            Сбросить все
          </v-btn>
          <v-chip
            v-if="cfgActiveFilterCount > 0"
            color="info" variant="tonal" size="small"
            prepend-icon="mdi-filter-check"
            class="ml-1"
          >
            Фильтры {{ cfgActiveFilterCount }}
            <v-btn
              icon="mdi-close"
              size="x-small"
              variant="text"
              class="ml-1"
              @click="cfgClearAllFilters()"
            />
          </v-chip>
        </div>
        <div class="d-flex flex-wrap gap-2">

          <!-- Субсидия -->
          <v-autocomplete
            v-model="fSubsidy"
            :items="usedSubsidies"
            item-title="name" item-value="id"
            label="Субсидия" multiple chips closable-chips
            variant="outlined" density="compact" hide-details clearable
            style="min-width:200px; max-width:280px"
          />

          <!-- Тип документа -->
          <v-autocomplete
            v-model="fType"
            :items="usedContractTypes"
            item-title="label" item-value="value"
            label="Тип документа" multiple chips closable-chips
            variant="outlined" density="compact" hide-details clearable
            style="min-width:200px; max-width:300px"
          />

          <!-- Способ закупки -->
          <v-autocomplete
            v-model="fMethod"
            :items="usedPurchaseMethods"
            item-title="label" item-value="value"
            label="Способ закупки" multiple chips closable-chips
            variant="outlined" density="compact" hide-details clearable
            style="min-width:180px; max-width:240px"
          />

          <!-- Контрагент -->
          <v-autocomplete
            v-model="fContractor"
            :items="usedContractors"
            item-title="name" item-value="id"
            label="Контрагент" multiple chips closable-chips
            variant="outlined" density="compact" hide-details clearable
            style="min-width:200px; max-width:300px"
          />

          <!-- Поиск по товару -->
          <v-text-field
            v-model="fProduct"
            label="Поиск товара"
            prepend-inner-icon="mdi-magnify"
            variant="outlined" density="compact" hide-details clearable
            style="min-width:200px; max-width:280px"
            placeholder="Название товара..."
          />

          <!-- Дата от/до -->
          <v-text-field
            v-model="fDateFrom"
            label="Дата от" type="date"
            variant="outlined" density="compact" hide-details clearable
            style="min-width:145px; max-width:145px"
          />
          <v-text-field
            v-model="fDateTo"
            label="Дата до" type="date"
            variant="outlined" density="compact" hide-details clearable
            style="min-width:145px; max-width:145px"
          />

        </div>
      </v-card-text>
    </v-card>

    <!-- ── Table ── -->
    <v-data-table
      :headers="tableHeaders"
      :items="filteredWithRowNum"
      :loading="loading"
      density="compact"
      show-expand
      v-model:expanded="expanded"
      item-value="id"
      class="elevation-1"
      items-per-page="50"
      :items-per-page-options="[25,50,100,-1]"
      :sort-by="localSort ? [localSort] : []"
      @click:row="(_e: any, { item }: any) => openEdit(item)"
      style="cursor: pointer"
    >
      <!-- ColumnHeaderMenu slots -->
      <template #header.number="{ column }">
        <ColumnHeaderMenu col-key="number" :title="column.title" col-type="text"
          :model-value="colState.filters['number'] ?? null"
          :sort-by="getSortBy('number')"
          @update:model-value="v => cfgSetFilter('number', v)"
          @sort="dir => applySort('number', dir)"
          @hide="toggleVisible('number', false)"
        />
      </template>
      <template #header.date="{ column }">
        <ColumnHeaderMenu col-key="date" :title="column.title" col-type="date"
          :model-value="colState.filters['date'] ?? null"
          :sort-by="getSortBy('date')"
          @update:model-value="v => cfgSetFilter('date', v)"
          @sort="dir => applySort('date', dir)"
          @hide="toggleVisible('date', false)"
        />
      </template>
      <template #header.contract_type="{ column }">
        <ColumnHeaderMenu col-key="contract_type" :title="column.title" col-type="enum"
          :items="uniqValues(contracts, 'contract_type')"
          :item-labels="contractTypeLabels"
          :model-value="colState.filters['contract_type'] ?? null"
          :sort-by="getSortBy('contract_type')"
          @update:model-value="v => cfgSetFilter('contract_type', v)"
          @sort="dir => applySort('contract_type', dir)"
          @hide="toggleVisible('contract_type', false)"
        />
      </template>
      <template #header.purchase_method="{ column }">
        <ColumnHeaderMenu col-key="purchase_method" :title="column.title" col-type="enum"
          :items="uniqValues(contracts, 'purchase_method')"
          :item-labels="purchaseMethodLabels"
          :model-value="colState.filters['purchase_method'] ?? null"
          :sort-by="getSortBy('purchase_method')"
          @update:model-value="v => cfgSetFilter('purchase_method', v)"
          @sort="dir => applySort('purchase_method', dir)"
          @hide="toggleVisible('purchase_method', false)"
        />
      </template>
      <template #header.contractor_name="{ column }">
        <ColumnHeaderMenu col-key="contractor_name" :title="column.title" col-type="text"
          :model-value="colState.filters['contractor_name'] ?? null"
          :sort-by="getSortBy('contractor_name')"
          @update:model-value="v => cfgSetFilter('contractor_name', v)"
          @sort="dir => applySort('contractor_name', dir)"
          @hide="toggleVisible('contractor_name', false)"
        />
      </template>
      <template #header.subsidy_name="{ column }">
        <ColumnHeaderMenu col-key="subsidy_name" :title="column.title" col-type="enum"
          :items="uniqValues(contracts, 'subsidy_name')"
          :model-value="colState.filters['subsidy_name'] ?? null"
          :sort-by="getSortBy('subsidy_name')"
          @update:model-value="v => cfgSetFilter('subsidy_name', v)"
          @sort="dir => applySort('subsidy_name', dir)"
          @hide="toggleVisible('subsidy_name', false)"
        />
      </template>
      <template #header.max_amount="{ column }">
        <ColumnHeaderMenu col-key="max_amount" :title="column.title" col-type="number" align="end"
          :model-value="colState.filters['max_amount'] ?? null"
          :sort-by="getSortBy('max_amount')"
          @update:model-value="v => cfgSetFilter('max_amount', v)"
          @sort="dir => applySort('max_amount', dir)"
          @hide="toggleVisible('max_amount', false)"
        />
      </template>
      <template #header.total_ordered="{ column }">
        <ColumnHeaderMenu col-key="total_ordered" :title="column.title" col-type="number" align="end"
          :model-value="colState.filters['total_ordered'] ?? null"
          :sort-by="getSortBy('total_ordered')"
          @update:model-value="v => cfgSetFilter('total_ordered', v)"
          @sort="dir => applySort('total_ordered', dir)"
          @hide="toggleVisible('total_ordered', false)"
        />
      </template>
      <template #header.total_delivered="{ column }">
        <ColumnHeaderMenu col-key="total_delivered" :title="column.title" col-type="number" align="end"
          :model-value="colState.filters['total_delivered'] ?? null"
          :sort-by="getSortBy('total_delivered')"
          @update:model-value="v => cfgSetFilter('total_delivered', v)"
          @sort="dir => applySort('total_delivered', dir)"
          @hide="toggleVisible('total_delivered', false)"
        />
      </template>
      <template #header.total_paid="{ column }">
        <ColumnHeaderMenu col-key="total_paid" :title="column.title" col-type="number" align="end"
          :model-value="colState.filters['total_paid'] ?? null"
          :sort-by="getSortBy('total_paid')"
          @update:model-value="v => cfgSetFilter('total_paid', v)"
          @sort="dir => applySort('total_paid', dir)"
          @hide="toggleVisible('total_paid', false)"
        />
      </template>
      <template #header.remaining_ordered="{ column }">
        <ColumnHeaderMenu col-key="remaining_ordered" :title="column.title" col-type="number" align="end"
          :model-value="colState.filters['remaining_ordered'] ?? null"
          :sort-by="getSortBy('remaining_ordered')"
          @update:model-value="v => cfgSetFilter('remaining_ordered', v)"
          @sort="dir => applySort('remaining_ordered', dir)"
          @hide="toggleVisible('remaining_ordered', false)"
        />
      </template>
      <template #header.remaining_delivered="{ column }">
        <ColumnHeaderMenu col-key="remaining_delivered" :title="column.title" col-type="number" align="end"
          :model-value="colState.filters['remaining_delivered'] ?? null"
          :sort-by="getSortBy('remaining_delivered')"
          @update:model-value="v => cfgSetFilter('remaining_delivered', v)"
          @sort="dir => applySort('remaining_delivered', dir)"
          @hide="toggleVisible('remaining_delivered', false)"
        />
      </template>
      <template #header.remaining_paid="{ column }">
        <ColumnHeaderMenu col-key="remaining_paid" :title="column.title" col-type="number" align="end"
          :model-value="colState.filters['remaining_paid'] ?? null"
          :sort-by="getSortBy('remaining_paid')"
          @update:model-value="v => cfgSetFilter('remaining_paid', v)"
          @sort="dir => applySort('remaining_paid', dir)"
          @hide="toggleVisible('remaining_paid', false)"
        />
      </template>
      <template #header.subject="{ column }">
        <ColumnHeaderMenu col-key="subject" :title="column.title" col-type="text"
          :model-value="colState.filters['subject'] ?? null"
          :sort-by="getSortBy('subject')"
          @update:model-value="v => cfgSetFilter('subject', v)"
          @sort="dir => applySort('subject', dir)"
          @hide="toggleVisible('subject', false)"
        />
      </template>
      <template #header.end_date="{ column }">
        <ColumnHeaderMenu col-key="end_date" :title="column.title" col-type="date"
          :model-value="colState.filters['end_date'] ?? null"
          :sort-by="getSortBy('end_date')"
          @update:model-value="v => cfgSetFilter('end_date', v)"
          @sort="dir => applySort('end_date', dir)"
          @hide="toggleVisible('end_date', false)"
        />
      </template>
      <template #header.status="{ column }">
        <ColumnHeaderMenu col-key="status" :title="column.title" col-type="enum"
          :items="uniqValues(contracts, 'status')"
          :item-labels="statusLabels"
          :model-value="colState.filters['status'] ?? null"
          :sort-by="getSortBy('status')"
          @update:model-value="v => cfgSetFilter('status', v)"
          @sort="dir => applySort('status', dir)"
          @hide="toggleVisible('status', false)"
        />
      </template>
      <template #header.notes="{ column }">
        <ColumnHeaderMenu col-key="notes" :title="column.title" col-type="text"
          :model-value="colState.filters['notes'] ?? null"
          :sort-by="getSortBy('notes')"
          @update:model-value="v => cfgSetFilter('notes', v)"
          @sort="dir => applySort('notes', dir)"
          @hide="toggleVisible('notes', false)"
        />
      </template>
      <!-- /ColumnHeaderMenu slots -->

      <template #item.number="{ item }">
        <span class="font-weight-medium">{{ item.number }}</span>
      </template>
      <template #item.date="{ item }">
        {{ fmtDate(item.date) }}
      </template>
      <template #item.end_date="{ item }">
        <span :style="item.end_date && isExpired(item.end_date) ? 'color:#DC2626' : ''">
          {{ fmtDate(item.end_date) }}
        </span>
      </template>
      <template #item.contract_type="{ item }">
        <v-chip size="x-small" :color="contractTypeColor(item.contract_type)" variant="tonal"
                style="white-space: normal; height: auto; min-height: 22px; padding: 2px 8px;">
          {{ contractTypeLabel(item.contract_type) }}
        </v-chip>
      </template>
      <template #item.purchase_method="{ item }">
        <span class="text-caption">{{ item.purchase_method ? purchaseMethodLabel(item.purchase_method) : '—' }}</span>
      </template>
      <template #item.contractor_name="{ item }">
        <template v-if="(item as any)._is_advance_report && (item as any).reimbursement_user_name">
          <v-chip size="x-small" color="purple" variant="tonal" prepend-icon="mdi-account">
            {{ (item as any).reimbursement_user_name }}
          </v-chip>
        </template>
        <template v-else-if="(item as any)._is_advance_report && (item as any).multi_contractor_label === 'Множественный контрагент'">
          <v-chip size="x-small" color="orange" variant="tonal" prepend-icon="mdi-domain-switch">
            {{ (item as any).multi_contractor_label }}
          </v-chip>
        </template>
        <template v-else>
          <div>{{ (item as any)._is_advance_report ? ((item as any).multi_contractor_label || item.contractor_name || '—') : (item.contractor_name || '—') }}</div>
          <div v-if="item.contractor_inn && !(item as any)._is_advance_report" class="text-caption text-medium-emphasis">ИНН {{ item.contractor_inn }}</div>
          <div v-if="!item.contractor_name || !item.signing_date || !item.max_amount" class="d-flex flex-wrap ga-1 mt-1">
            <v-chip v-if="!item.contractor_name" size="x-small" color="error" variant="tonal" prepend-icon="mdi-domain-off">Контрагент</v-chip>
            <v-chip v-if="!item.signing_date" size="x-small" color="warning" variant="tonal" prepend-icon="mdi-calendar-alert">Дата</v-chip>
            <v-chip v-if="!item.max_amount" size="x-small" color="warning" variant="tonal" prepend-icon="mdi-currency-rub">Сумма</v-chip>
          </div>
        </template>
      </template>
      <template #item.max_amount="{ item }">
        {{ item.max_amount ? formatMoney(item.max_amount) : '—' }}
      </template>
      <template #item.total_ordered="{ item }">
        <span :style="item.max_amount && Number(item.total_ordered) > Number(item.max_amount) ? 'color:var(--color-loss);font-weight:700' : ''">
          {{ item.total_ordered ? formatMoney(item.total_ordered) : '—' }}
        </span>
      </template>
      <template #item.total_delivered="{ item }">
        <span>{{ item.total_delivered ? formatMoney(item.total_delivered) : '—' }}</span>
      </template>
      <template #item.total_paid="{ item }">
        <span style="color:var(--color-profit)">{{ item.total_paid ? formatMoney(item.total_paid) : '—' }}</span>
      </template>
      <template #item.remaining_ordered="{ item }">
        <span :style="Number(item.remaining_ordered) < 0 ? 'color:var(--color-loss);font-weight:700' : ''">
          {{ item.remaining_ordered != null ? formatMoney(item.remaining_ordered) : '—' }}
        </span>
      </template>
      <template #item.remaining_delivered="{ item }">
        <span :style="Number(item.remaining_delivered) < 0 ? 'color:var(--color-loss);font-weight:700' : 'color:var(--color-profit)'">
          {{ item.remaining_delivered != null ? formatMoney(item.remaining_delivered) : '—' }}
        </span>
      </template>
      <template #item.remaining_paid="{ item }">
        <span :style="Number(item.remaining_paid) < 0 ? 'color:var(--color-loss);font-weight:700' : 'color:var(--color-profit)'">
          {{ item.remaining_paid != null ? formatMoney(item.remaining_paid) : '—' }}
        </span>
      </template>
      <template #item.subsidy_name="{ item }">
        <div class="d-flex flex-wrap gap-1">
          <v-chip v-if="item.subsidy_name" size="x-small" color="primary" variant="tonal">{{ item.subsidy_name }}</v-chip>
          <v-chip v-for="es in (item.extra_subsidies || [])" :key="es.subsidy_id" size="x-small" color="secondary" variant="tonal">{{ es.subsidy_name }}</v-chip>
          <span v-if="!item.subsidy_name && !(item.extra_subsidies?.length)" class="text-medium-emphasis">—</span>
        </div>
      </template>
      <template #item.subject="{ item }">
        <span class="text-caption" :title="item.subject">{{ item.subject ? (item.subject.length > 60 ? item.subject.slice(0, 60) + '...' : item.subject) : '—' }}</span>
      </template>
      <template #item.item_type="{ item }">
        <v-chip v-if="item.item_type" size="x-small" :color="item.item_type === 'услуга' ? 'blue' : 'teal'" variant="tonal">
          {{ item.item_type === 'услуга' ? 'Услуги' : 'Товары' }}
        </v-chip>
        <span v-else class="text-medium-emphasis">—</span>
      </template>
      <!-- Expanded: закупки по договору -->
      <template #expanded-row="{ columns, item }">
        <tr>
          <td :colspan="columns.length" class="pa-0">
            <div class="pa-3 bg-grey-lighten-5">
              <div class="text-caption font-weight-medium text-medium-emphasis mb-2">
                Закупки по документу {{ item.number }}
              </div>

              <!-- ── Финансовый блок для рамочных договоров ── -->
              <v-card v-if="isFrameworkContract(item)" class="mb-2" variant="tonal" rounded="lg">
                <v-card-text class="d-flex flex-wrap ga-3 align-center py-2">
                  <div>
                    <div class="text-caption text-medium-emphasis">Максимальная сумма</div>
                    <div class="text-subtitle-2 font-weight-bold">{{ formatMoney(item.max_amount ?? 0) }}</div>
                  </div>
                  <v-divider vertical />
                  <div>
                    <div class="text-caption text-medium-emphasis">Заказано всего</div>
                    <div class="text-subtitle-2 font-weight-bold text-info">{{ formatMoney(item.total_ordered ?? 0) }}</div>
                  </div>
                  <v-divider vertical />
                  <div>
                    <div class="text-caption text-medium-emphasis">Поставлено</div>
                    <div class="text-subtitle-2 font-weight-bold text-warning">{{ formatMoney(item.total_delivered ?? 0) }}</div>
                  </div>
                  <v-divider vertical />
                  <div>
                    <div class="text-caption text-medium-emphasis">Оплачено</div>
                    <div class="text-subtitle-2 font-weight-bold text-success">{{ formatMoney(item.total_paid ?? 0) }}</div>
                  </div>
                  <v-divider vertical />
                  <div>
                    <div class="text-caption text-medium-emphasis">Остаток (не заказано)</div>
                    <div class="text-subtitle-2 font-weight-bold" :class="Number(item.remaining_ordered) < 0 ? 'text-error' : 'text-primary'">
                      {{ formatMoney(item.remaining_ordered ?? 0) }}
                    </div>
                  </div>
                </v-card-text>
              </v-card>

              <!-- Alert для накопительного договора -->
              <v-alert
                v-if="item.contract_type === 'framework_cumulative'"
                type="info"
                density="compact"
                variant="tonal"
                class="mb-2"
                icon="mdi-information"
              >
                Договор накопительный — сумма за поставку согласуйте с руководителем.
              </v-alert>
              <div v-if="!purchasesByContract[item.id]" class="text-caption text-medium-emphasis">
                <v-btn size="x-small" variant="text" @click="loadPurchasesForContract(item.id)">Загрузить</v-btn>
              </div>
              <div v-else-if="!purchasesByContract[item.id].length" class="text-caption text-medium-emphasis">Нет закупок</div>
              <v-table v-else density="compact">
                <thead>
                  <tr>
                    <th>№ закупки</th>
                    <th>Наименование</th>
                    <th class="text-right">Сумма</th>
                  </tr>
                </thead>
                <tbody>
                  <template v-for="p in purchasesByContract[item.id]" :key="p.id">
                    <tr style="cursor:pointer" @click="router.push(`/orders/${p.id}/edit`)">
                      <td>
                        <v-btn v-if="p.items?.length" :icon="expandedPurchases[p.id] ? 'mdi-chevron-up' : 'mdi-chevron-down'"
                          variant="text" size="x-small" @click.stop="expandedPurchases[p.id] = !expandedPurchases[p.id]" />
                        {{ p.purchase_number || p.id }}
                      </td>
                      <td class="text-caption">{{ p.subject || p.item_name || '—' }}</td>
                      <td class="text-right">{{ p.contract_price ? formatMoney(p.contract_price) : '—' }}</td>
                    </tr>
                    <tr v-if="expandedPurchases[p.id] && p.items?.length">
                      <td colspan="3" class="pa-0 pl-8">
                        <v-table density="compact" class="bg-grey-lighten-4">
                          <thead><tr><th>Наименование</th><th class="text-right">Кол-во</th><th class="text-right">Цена ед.</th><th class="text-right">Сумма</th></tr></thead>
                          <tbody>
                            <tr v-for="(pi, ii) in p.items" :key="ii"
                              :class="fProduct && pi.item_name?.toLowerCase().includes(fProduct.trim().toLowerCase()) ? 'bg-yellow-lighten-4' : ''">
                              <td class="text-caption">{{ pi.item_name }}</td>
                              <td class="text-right text-caption">{{ pi.quantity }}</td>
                              <td class="text-right text-caption">{{ pi.unit_price ? formatMoney(pi.unit_price) : '—' }}</td>
                              <td class="text-right text-caption">{{ pi.total_price ? formatMoney(pi.total_price) : '—' }}</td>
                            </tr>
                            <tr class="font-weight-bold">
                              <td colspan="3" class="text-right text-caption">Итого:</td>
                              <td class="text-right text-caption">{{ formatMoney(p.items.reduce((s, i) => s + (Number(i.total_price) || 0), 0)) }}</td>
                            </tr>
                          </tbody>
                        </v-table>
                      </td>
                    </tr>
                  </template>
                </tbody>
              </v-table>
            </div>
          </td>
        </tr>
      </template>
    </v-data-table>

    <!-- Column Config Dialog -->
    <ColumnConfigDialog
      v-model="showColumnPicker"
      :all-columns="allColumns"
      :state="colState"
      :show-width="true"
      :groups="groups"
      :toggle-visible="toggleVisible"
      :set-position="setPosition"
      :set-width="setWidth"
      :reset="resetColumns"
    />

    <!-- Export Dialog -->
    <v-dialog v-model="exportDialog" max-width="480">
      <v-card>
        <v-card-title class="pa-4">
          <v-icon icon="mdi-file-excel-outline" color="success" class="mr-2" />Скачать реестр договоров
        </v-card-title>
        <v-card-text class="pa-4 pt-0">
          <div class="text-body-2 mb-3">Выберите колонки для экспорта:</div>
          <v-checkbox v-for="col in exportColumns" :key="col.key"
            v-model="col.selected" :label="col.title" density="compact" hide-details />
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-btn variant="text" size="small" @click="exportColumns.forEach(c => c.selected = true)">Выбрать все</v-btn>
          <v-btn variant="text" size="small" @click="exportColumns.forEach(c => c.selected = false)">Снять все</v-btn>
          <v-spacer />
          <v-btn variant="text" @click="exportDialog = false">Отмена</v-btn>
          <v-btn color="success" variant="flat" prepend-icon="mdi-download" :loading="exportLoading" @click="doExport">Скачать</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Duplicates Dialog -->
    <v-dialog v-model="dupDialog" max-width="700" scrollable>
      <v-card>
        <v-card-title class="pa-4">
          <v-icon icon="mdi-content-duplicate" color="warning" class="mr-2" />
          Найденные дубли ({{ duplicateGroups.length }} групп)
        </v-card-title>
        <v-card-text v-if="!duplicateGroups.length" class="text-center py-8 text-medium-emphasis">
          Дубликатов не найдено
        </v-card-text>
        <v-card-text v-else class="pa-4 pt-0">
          <div v-for="(group, gi) in duplicateGroups" :key="gi" class="mb-4 pa-3 rounded-lg" style="background:rgba(255,152,0,0.08);border-left:3px solid #ff9800">
            <div class="text-body-2 font-weight-bold mb-2">{{ group[0].number }} — {{ group[0].contractor_name || '?' }}</div>
            <v-table density="compact">
              <thead><tr><th>ID</th><th>Дата</th><th>Сумма</th><th>Закупок</th><th></th></tr></thead>
              <tbody>
                <tr v-for="c in group" :key="c.id">
                  <td>{{ c.id }}</td>
                  <td>{{ c.date || '—' }}</td>
                  <td>{{ c.max_amount ? Number(c.max_amount).toLocaleString('ru-RU') + ' ₽' : '—' }}</td>
                  <td>{{ c._purchaseCount ?? '?' }}</td>
                  <td>
                    <v-btn v-if="group.length > 1" size="x-small" variant="tonal" color="error"
                      @click="mergeContract(c.id, group.find(x => x.id !== c.id)!.id)">
                      Объединить в #{{ group.find(x => x.id !== c.id)?.id }}
                    </v-btn>
                  </td>
                </tr>
              </tbody>
            </v-table>
          </div>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="dupDialog = false">Закрыть</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Create/Edit Dialog -->
    <v-dialog v-model="dialog.show" max-width="680">
      <v-card>
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">
          {{ dialog.id ? 'Редактировать документ' : 'Новый документ' }}
        </v-card-title>
        <v-card-text class="px-4 pb-2">
          <v-row dense>
            <v-col cols="12" md="6">
              <v-text-field v-model="dialog.form.number" label="Номер *" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field v-model="dialog.form.date" label="Дата" type="date" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12" md="6">
              <v-select v-model="dialog.form.contract_type"
                :items="contractTypeItems" item-title="label" item-value="value"
                label="Тип документа *" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12" md="4">
              <v-select v-model="dialog.form.purchase_method"
                :items="purchaseMethodItems" item-title="label" item-value="value"
                label="Способ закупки" variant="outlined" density="compact" clearable />
            </v-col>
            <v-col cols="12" md="4">
              <v-select v-model="dialog.form.item_type"
                :items="[{ title: 'Товары', value: 'товар' }, { title: 'Услуги', value: 'услуга' }]"
                label="Товары / Услуги" variant="outlined" density="compact" clearable />
            </v-col>
            <v-col cols="12" md="4">
              <v-autocomplete v-model="dialog.form.contractor_id"
                :items="contractors" item-title="name" item-value="id"
                label="Контрагент" variant="outlined" density="compact" clearable />
            </v-col>
            <v-col cols="12" md="6">
              <v-select v-model="dialog.form.subsidy_id"
                :items="subsidies" item-title="name" item-value="id"
                label="Основная субсидия" variant="outlined" density="compact" clearable />
            </v-col>
            <v-col cols="12">
              <v-autocomplete v-model="dialog.form.extra_subsidy_ids"
                :items="subsidies.filter(s => s.id !== dialog.form.subsidy_id)"
                item-title="name" item-value="id"
                label="Дополнительные субсидии" variant="outlined" density="compact"
                multiple chips closable-chips clearable
                hint="Договор может быть привязан к нескольким субсидиям одной организации"
                persistent-hint />
            </v-col>
            <v-col cols="12">
              <v-text-field v-model="dialog.form.subject" label="Предмет" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field v-model.number="dialog.form.max_amount" label="Предельная сумма, ₽" type="number" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field v-model.number="dialog.form.planned_monthly" label="Плановый ежемесячный платёж, ₽" type="number" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field v-model="dialog.form.start_date" label="Дата начала" type="date" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field v-model="dialog.form.end_date" label="Дата окончания" type="date" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12" md="6">
              <v-select v-model="dialog.form.status"
                :items="statusItems" item-title="label" item-value="value"
                label="Статус" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12">
              <v-textarea v-model="dialog.form.notes" label="Примечания" variant="outlined" density="compact" rows="2" />
            </v-col>
          </v-row>
        </v-card-text>
        <v-card-actions class="px-4 pb-3">
          <v-btn v-if="isAdmin && dialog.id" color="error" variant="text" prepend-icon="mdi-delete"
            @click="dialog.show = false; confirmDelete(contracts.find(c => c.id === dialog.id)!)">Удалить</v-btn>
          <v-btn
            v-if="dialog.id && dialog.form.contract_type && dialog.form.contract_type.startsWith('framework_')"
            color="teal" variant="tonal" prepend-icon="mdi-plus"
            @click="openMonthlyStagesFromDialog"
          >
            Создать ежемесячные этапы
          </v-btn>
          <v-spacer />
          <v-btn variant="text" @click="dialog.show = false">Отмена</v-btn>
          <v-btn color="primary" variant="tonal" :loading="dialog.saving" @click="saveContract">Сохранить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Monthly Stages Dialog -->
    <MonthlyStagesDialog
      v-model="monthlyStagesDialog.show"
      :contract-id="monthlyStagesDialog.contractId"
      :contract-name="monthlyStagesDialog.contractName"
      :contract-type="monthlyStagesDialog.contractType"
      :default-subsidy-id="monthlyStagesDialog.subsidyId"
      :default-amount="monthlyStagesDialog.defaultAmount"
      @created="onMonthlyStagesCreated"
    />

    <!-- Delete confirm -->
    <v-dialog v-model="deleteDialog.show" max-width="400">
      <v-card>
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">Удалить запись?</v-card-title>
        <v-card-text class="px-4">
          Удалить <strong>{{ deleteDialog.item?.number }}</strong>? Закупки сохранятся.
        </v-card-text>
        <v-card-actions class="px-4 pb-3">
          <v-spacer />
          <v-btn variant="text" @click="deleteDialog.show = false">Отмена</v-btn>
          <v-btn color="error" variant="tonal" :loading="deleteDialog.deleting" @click="doDelete">Удалить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Migrate dialog -->
    <v-dialog v-model="migrateDialog" max-width="480">
      <v-card>
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">Мигрировать из закупок</v-card-title>
        <v-card-text class="px-4">
          <p class="text-body-2 mb-3">
            Создаст записи реестра из всех закупок с заполненным номером договора. Уже существующие номера пропускаются.
          </p>
          <v-alert v-if="migrateResult" :type="migrateResult.created > 0 ? 'success' : 'info'" variant="tonal" density="compact">
            Создано: <strong>{{ migrateResult.created }}</strong>,
            пропущено: <strong>{{ migrateResult.skipped }}</strong>
          </v-alert>
        </v-card-text>
        <v-card-actions class="px-4 pb-3">
          <v-spacer />
          <v-btn variant="text" @click="migrateDialog = false">Закрыть</v-btn>
          <v-btn v-if="!migrateResult" color="primary" variant="tonal" :loading="migrating" @click="doMigrate">
            Запустить
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Import from file dialog -->
    <v-dialog v-model="importDialog.show" max-width="800" persistent>
      <v-card>
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">
          Импорт договоров из файла
        </v-card-title>
        <v-card-text class="px-4">
          <!-- Step 1: File upload with drag-and-drop -->
          <div v-if="importDialog.step === 1">
            <v-alert type="info" variant="tonal" density="compact" class="mb-3" icon="mdi-information-outline">
              <div class="text-body-2">
                <strong>Форматы:</strong> Excel (.xlsx, .xls), Word (.docx), PDF<br>
                <strong>Заголовки:</strong> определяются автоматически по ключевым словам — могут быть в любой строке<br>
                <strong>Лист:</strong> любое название — система прочитает первый или предложит выбрать
              </div>
            </v-alert>
            <FileDropZone v-model="importDialog.file" accept=".pdf,.xlsx,.xls,.docx,.doc"
              hint="PDF, Excel (.xlsx, .xls), Word (.docx) — таблица с договорами" class="mb-3" />
            <v-select v-model="importDialog.subsidyId" :items="subsidyOptions" item-title="name" item-value="id"
              label="Субсидия (для всех импортируемых)" variant="outlined" density="compact" clearable class="mt-2" />
          </div>

          <!-- Step 2: Column mapping -->
          <div v-if="importDialog.step === 2">
            <v-alert type="info" variant="tonal" density="compact" class="mb-3" icon="mdi-file-table-outline">
              <strong>Лист:</strong> {{ importDialog.sheetName || 'Первый лист' }} ({{ importDialog.totalRows }} строк данных)
            </v-alert>
            <p class="text-body-2 mb-3">
              Сопоставьте столбцы файла с полями договора:
            </p>
            <v-row dense>
              <v-col v-for="field in importFields" :key="field.key" cols="12" md="6">
                <v-select v-model="importDialog.mapping[field.key]" :items="importDialog.headerOptions"
                  :label="field.label + (field.required ? ' *' : '')" variant="outlined" density="compact" clearable />
              </v-col>
            </v-row>
            <!-- Sample data preview -->
            <div v-if="importDialog.sample.length" class="mt-3">
              <div class="text-body-2 font-weight-medium mb-1">Пример данных:</div>
              <v-table density="compact" class="text-caption">
                <thead>
                  <tr><th v-for="h in importDialog.headers" :key="h">{{ h }}</th></tr>
                </thead>
                <tbody>
                  <tr v-for="(row, ri) in importDialog.sample" :key="ri">
                    <td v-for="(cell, ci) in row" :key="ci">{{ cell }}</td>
                  </tr>
                </tbody>
              </v-table>
            </div>
          </div>

          <!-- Step 3: Result -->
          <div v-if="importDialog.step === 3">
            <v-alert type="success" variant="tonal" density="compact" class="mb-2">
              Создано: <strong>{{ importDialog.result?.created }}</strong>,
              пропущено (дубли): <strong>{{ importDialog.result?.skipped }}</strong>
            </v-alert>
          </div>

          <v-alert v-if="importDialog.error" type="error" variant="tonal" density="compact" class="mt-2">
            {{ importDialog.error }}
          </v-alert>
        </v-card-text>
        <v-card-actions class="px-4 pb-3">
          <v-spacer />
          <v-btn variant="text" @click="closeImportDialog">{{ importDialog.step === 3 ? 'Закрыть' : 'Отмена' }}</v-btn>
          <v-btn v-if="importDialog.step === 1" color="primary" variant="tonal" :loading="importDialog.loading"
            :disabled="!importDialog.file" @click="doImportPreview">
            Далее
          </v-btn>
          <v-btn v-if="importDialog.step === 2" color="primary" variant="tonal" :loading="importDialog.loading"
            :disabled="!importDialog.mapping.number" @click="doImportMapped">
            Импортировать
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snack.show" :color="snack.color" timeout="3000">{{ snack.text }}</v-snackbar>
  </v-container>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch } from '@/api'
import { useContractorsStore } from '@/stores/contractors'
import { useAppSearch } from '@/composables/useAppSearch'
import FileDropZone from '@/components/FileDropZone.vue'
import MonthlyStagesDialog from '@/components/MonthlyStagesDialog.vue'
import { useColumnConfig, type ColumnDef } from '@/composables/useColumnConfig'
import ColumnConfigDialog from '@/components/ColumnConfigDialog.vue'
import ColumnHeaderMenu from '@/components/ColumnHeaderMenu.vue'
import { formatMoney as formatMoneyUtil } from '@/utils/formatMoney'

const router = useRouter()

// Prevent browser from opening dropped files globally
const preventDrop = (e: DragEvent) => { e.preventDefault(); e.stopPropagation() }
onMounted(() => {
  document.addEventListener('dragover', preventDrop)
  document.addEventListener('drop', preventDrop)
})
onUnmounted(() => {
  document.removeEventListener('dragover', preventDrop)
  document.removeEventListener('drop', preventDrop)
})

const btnDragOver = ref(false)
function onButtonDrop(e: DragEvent) {
  btnDragOver.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file) {
    importDialog.file = file
    importDialog.show = true
  }
}

const { appSearch, appSearchScope } = useAppSearch()

const userRole = localStorage.getItem('user_role') || ''
const isAdmin = ['admin', 'superadmin', 'org_admin'].includes(userRole)

interface ContractSubsidyItem { id: number; subsidy_id: number; subsidy_name?: string }
interface Contract {
  id: number
  number: string
  date?: string
  contract_type: string
  purchase_method?: string
  contractor_id?: number
  contractor_name?: string
  contractor_inn?: string
  reimbursement_user_id?: number | null
  reimbursement_user_name?: string | null
  multi_contractor_label?: string | null
  subsidy_id?: number
  subsidy_name?: string
  extra_subsidies?: ContractSubsidyItem[]
  subject?: string
  max_amount?: number
  total_ordered?: number
  total_paid?: number
  remaining?: number
  start_date?: string
  end_date?: string
  status?: string
  notes?: string
  planned_monthly?: number
}
interface Subsidy { id: number; name: string; year: number }
interface Contractor { id: number; name: string; inn?: string }
interface PurchaseItem { item_name: string; quantity?: number; unit_price?: number; total_price?: number }
interface Purchase { id: number; purchase_number?: number; subject?: string; item_name?: string; contract_price?: number; status: string; items?: PurchaseItem[] }

const contracts = ref<Contract[]>([])
const subsidies = ref<Subsidy[]>([])
const contractors = ref<Contractor[]>([])
const loading = ref(false)
const expanded = ref<number[]>([])

// Export
const exportDialog = ref(false)
const exportColumns = reactive([
  { key: 'number', title: '№ договора', selected: true },
  { key: 'date', title: 'Дата договора', selected: true },
  { key: 'contract_type', title: 'Тип договора', selected: true },
  { key: 'purchase_method', title: 'Способ закупки', selected: true },
  { key: 'contractor_name', title: 'Контрагент', selected: true },
  { key: 'contractor_inn', title: 'ИНН контрагента', selected: true },
  { key: 'subject', title: 'Предмет договора', selected: true },
  { key: 'subsidy_name', title: 'Субсидия', selected: true },
  { key: 'max_amount', title: 'Макс. сумма', selected: true },
  { key: 'total_ordered', title: 'Заказано', selected: true },
  { key: 'total_delivered', title: 'Поставлено', selected: true },
  { key: 'total_paid', title: 'Оплачено', selected: true },
  { key: 'remaining_ordered', title: 'Ост. (заказ)', selected: true },
  { key: 'remaining_delivered', title: 'Не поставлено', selected: true },
  { key: 'remaining_paid', title: 'Не оплачено', selected: true },
  { key: 'start_date', title: 'Дата начала', selected: true },
  { key: 'end_date', title: 'Дата окончания', selected: true },
  { key: 'notes', title: 'Примечания', selected: false },
  { key: 'closing_docs', title: 'Закрывающие документы', selected: true },
  { key: 'payment_docs', title: 'Платёжные документы', selected: true },
  { key: 'other_docs', title: 'Прочие документы', selected: true },
])

const exportLoading = ref(false)

interface CatFiles { closing: { name: string; path: string }[]; payment: { name: string; path: string }[]; other: { name: string; path: string }[] }
const CLOSING_TYPES = new Set(['act', 'upd'])
const PAYMENT_TYPES = new Set(['invoice'])

async function doExport() {
  exportLoading.value = true
  try {
    const XLSX = await import('xlsx')
    const JSZip = (await import('jszip')).default
    const zip = new JSZip()
    const docsFolder = zip.folder('Документы')!
    const selected = exportColumns.filter(c => c.selected)
    const docKeys = new Set(['closing_docs', 'payment_docs', 'other_docs'])
    const hasDocCols = selected.some(c => docKeys.has(c.key))

    const header = selected.map(c => c.title)
    const rows: any[][] = [header]
    // Parallel array: for each data row, store {colKey -> zipPath} for link generation
    const rowLinks: Map<string, string>[] = []

    const contractFiles = new Map<number, CatFiles>()
    const token = localStorage.getItem('auth_token')
    const baseUrl = window.location.origin

    // Collect and download all files, categorized
    if (hasDocCols) {
      for (const contract of filtered.value) {
        const cats: CatFiles = { closing: [], payment: [], other: [] }
        const safeNum = (contract.number || contract.id).toString().replace(/[\\/:*?"<>|]/g, '_')
        const folderName = `${safeNum}_${contract.contractor_name || 'без_контрагента'}`.replace(/[\\/:*?"<>|]/g, '_').slice(0, 80)
        const contractFolder = docsFolder.folder(folderName)!

        // Load purchases if not yet loaded
        if (!purchasesByContract.value[contract.id]) {
          try {
            const items = await apiFetch<Purchase[]>(`/purchases/by-contract/${contract.id}`)
            purchasesByContract.value = { ...purchasesByContract.value, [contract.id]: items }
          } catch { /* skip */ }
        }

        const purchasesForContract = purchasesByContract.value[contract.id] || []
        const seenHashes = new Set<string>()

        for (const p of purchasesForContract) {
          try {
            const filesResp = await apiFetch<any[]>(`/purchases/${p.id}/files`)
            if (!Array.isArray(filesResp)) continue
            for (const f of filesResp) {
              // Skip duplicates by content_hash within same contract export
              if (f.content_hash && seenHashes.has(f.content_hash)) continue
              if (f.content_hash) seenHashes.add(f.content_hash)

              try {
                const resp = await fetch(`${baseUrl}/api/purchases/${p.id}/files/${f.id}/download`, {
                  headers: { Authorization: `Bearer ${token}` }
                })
                if (!resp.ok) continue
                const blob = await resp.blob()
                const fileName = f.filename || `file_${f.id}`
                contractFolder.file(fileName, blob)
                const entry = { name: fileName, path: `Документы/${folderName}/${fileName}` }

                const ft = f.file_type || 'other'
                if (CLOSING_TYPES.has(ft)) cats.closing.push(entry)
                else if (PAYMENT_TYPES.has(ft)) cats.payment.push(entry)
                else cats.other.push(entry)
              } catch { /* skip */ }
            }
          } catch { /* skip */ }
        }
        contractFiles.set(contract.id, cats)
      }
    }

    // Build data rows — one row per file (or at least one row per contract)
    const merges: { s: { r: number; c: number }; e: { r: number; c: number } }[] = []

    for (const contract of filtered.value) {
      const cats = contractFiles.get(contract.id) || { closing: [], payment: [], other: [] }
      const maxFiles = Math.max(1, cats.closing.length, cats.payment.length, cats.other.length)
      const startRow = rows.length

      for (let fi = 0; fi < maxFiles; fi++) {
        const row: any[] = []
        const links: Map<string, string> = new Map()
        for (const col of selected) {
          if (col.key === 'closing_docs') {
            row.push(cats.closing[fi]?.name || '')
            if (cats.closing[fi]) links.set(col.key, cats.closing[fi].path)
          } else if (col.key === 'payment_docs') {
            row.push(cats.payment[fi]?.name || '')
            if (cats.payment[fi]) links.set(col.key, cats.payment[fi].path)
          } else if (col.key === 'other_docs') {
            row.push(cats.other[fi]?.name || '')
            if (cats.other[fi]) links.set(col.key, cats.other[fi].path)
          } else if (fi === 0) {
            // Contract data only on first row
            if (col.key === 'contract_type') row.push(contractTypeLabel(contract.contract_type))
            else if (col.key === 'purchase_method') row.push(purchaseMethodLabel(contract.purchase_method))
            else if (['max_amount', 'total_ordered', 'total_delivered', 'total_paid', 'remaining_ordered', 'remaining_delivered', 'remaining_paid'].includes(col.key)) {
              const v = (contract as any)[col.key]; row.push(v != null ? Number(v) : '')
            } else if (['date', 'start_date', 'end_date'].includes(col.key)) row.push(fmtDate((contract as any)[col.key]))
            else row.push((contract as any)[col.key] ?? '')
          } else {
            row.push('') // empty for subsequent file rows
          }
        }
        rows.push(row)
        rowLinks.push(links)
      }

      // Merge contract data cells if multiple file rows
      if (maxFiles > 1) {
        for (let ci = 0; ci < selected.length; ci++) {
          if (!docKeys.has(selected[ci].key)) {
            merges.push({ s: { r: startRow, c: ci }, e: { r: startRow + maxFiles - 1, c: ci } })
          }
        }
      }
    }

    const ws = XLSX.utils.aoa_to_sheet(rows)
    ws['!merges'] = merges

    // Add clickable links to document cells
    for (let r = 1; r < rows.length; r++) {
      const links = rowLinks[r - 1]
      if (!links) continue
      for (const [colKey, zipPath] of links) {
        const ci = selected.findIndex(c => c.key === colKey)
        if (ci < 0) continue
        const cellRef = XLSX.utils.encode_cell({ r, c: ci })
        const cell = ws[cellRef]
        if (cell && cell.v) {
          cell.l = { Target: zipPath, Tooltip: 'Открыть документ' }
        }
      }
    }

    // Auto-width
    const colWidths = header.map((h: string, i: number) => {
      let max = h.length
      for (let r = 1; r < rows.length; r++) { max = Math.max(max, String(rows[r][i] ?? '').length) }
      return { wch: Math.min(max + 2, 50) }
    })
    ws['!cols'] = colWidths

    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, 'Реестр договоров')
    const xlsxData = XLSX.write(wb, { bookType: 'xlsx', type: 'array' })
    const dateSuffix = new Date().toISOString().slice(0, 10)
    zip.file(`Реестр_договоров_${dateSuffix}.xlsx`, xlsxData)

    const zipBlob = await zip.generateAsync({ type: 'blob' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(zipBlob)
    a.download = `Реестр_договоров_${dateSuffix}.zip`
    a.click()
    URL.revokeObjectURL(a.href)

    exportDialog.value = false
    showSnack('Реестр скачан')
  } catch (e: any) {
    showSnack(`Ошибка экспорта: ${e.message || e}`, 'error')
  } finally {
    exportLoading.value = false
  }
}

// Duplicates
const dupDialog = ref(false)
const dupLoading = ref(false)
const duplicateGroups = ref<any[][]>([])

async function checkDuplicates() {
  dupLoading.value = true
  try {
    // Group contracts by number+contractor_id+subsidy_id
    const groups = new Map<string, any[]>()
    for (const c of contracts.value) {
      const key = `${c.number}|${c.contractor_id || ''}|${c.subsidy_id || ''}`
      if (!groups.has(key)) groups.set(key, [])
      groups.get(key)!.push(c)
    }
    // Filter groups with >1 contract
    const dups: any[][] = []
    for (const group of groups.values()) {
      if (group.length > 1) {
        // Count purchases per contract
        for (const c of group) {
          try {
            const p = await apiFetch<any[]>(`/purchases/by-contract/${c.id}`)
            c._purchaseCount = p.length
          } catch { c._purchaseCount = 0 }
        }
        dups.push(group)
      }
    }
    duplicateGroups.value = dups
    dupDialog.value = true
  } finally {
    dupLoading.value = false
  }
}

async function mergeContract(sourceId: number, targetId: number) {
  if (!confirm(`Объединить договор #${sourceId} в #${targetId}? Закупки будут перепривязаны, #${sourceId} удалён.`)) return
  try {
    await apiFetch(`/contracts/${sourceId}/merge/${targetId}`, { method: 'POST' })
    showSnack('Договоры объединены')
    dupDialog.value = false
    await loadContracts()
  } catch (e: any) {
    showSnack(e.message || 'Ошибка объединения', 'error')
  }
}
const purchasesByContract = ref<Record<number, Purchase[]>>({})
const expandedPurchases = ref<Record<number, boolean>>({})

const snack = reactive({ show: false, text: '', color: 'success' })
const showSnack = (text: string, color = 'success') => { snack.text = text; snack.color = color; snack.show = true }

// ── Filters (all multi-select, client-side) ────────────────────────────────
const fSubsidy    = ref<number[]>([])
const fType       = ref<string[]>([])
const fMethod     = ref<string[]>([])
const fStatus     = ref<string[]>([])
const fContractor = ref<number[]>([])
const fProduct    = ref('')
const fDateFrom   = ref('')
const fDateTo     = ref('')

const hasFilters = computed(() =>
  fSubsidy.value.length > 0 || fType.value.length > 0 || fMethod.value.length > 0 ||
  fStatus.value.length > 0 || fContractor.value.length > 0 || !!fProduct.value || !!fDateFrom.value || !!fDateTo.value
)

const clearFilters = () => {
  fSubsidy.value = []; fType.value = []; fMethod.value = []
  fStatus.value = []; fContractor.value = []; fProduct.value = ''; fDateFrom.value = ''; fDateTo.value = ''
}

// ── Dropdown items: only values present in contracts ──────────────────────
const usedSubsidies = computed(() => {
  const ids = new Set(contracts.value.map(c => c.subsidy_id).filter(Boolean))
  return subsidies.value.filter(s => ids.has(s.id))
})
// Дедуп по имени контрагента — для авансовых contractor_id часто пуст,
// заполнено только contractor_name (через JOIN на бэке).
const usedContractors = computed(() => {
  const byName = new Map<string, any>()
  for (const c of contracts.value as any[]) {
    const name = c.contractor_name
    if (!name || byName.has(name)) continue
    const real = contractors.value.find(x =>
      (c.contractor_id && x.id === c.contractor_id) ||
      (c.contractor_inn && x.inn === c.contractor_inn) ||
      x.name === name
    )
    byName.set(name, real || { id: -byName.size - 1, name, inn: c.contractor_inn || '' })
  }
  return Array.from(byName.values())
})
const usedContractTypes = computed(() => {
  const types = new Set(contracts.value.map(c => c.contract_type))
  return contractTypeItems.filter(i => types.has(i.value))
})
const usedPurchaseMethods = computed(() => {
  const methods = new Set(contracts.value.map(c => c.purchase_method).filter(Boolean))
  return purchaseMethodItems.filter(i => methods.has(i.value))
})

function matchesSearch(c: Contract, q: string): boolean {
  const lq = q.toLowerCase()
  return [c.number, c.contractor_name, c.contractor_inn, c.subsidy_name, c.subject, c.notes]
    .some(v => v?.toLowerCase().includes(lq))
}

// Product search: contracts whose purchases contain matching items
const productMatchContractIds = computed(() => {
  const q = fProduct.value.trim().toLowerCase()
  if (!q) return null
  const ids = new Set<number>()
  for (const [cid, purchases] of Object.entries(purchasesByContract.value)) {
    for (const p of purchases) {
      if (p.items?.some(i => i.item_name?.toLowerCase().includes(q)) ||
          p.subject?.toLowerCase().includes(q) ||
          p.item_name?.toLowerCase().includes(q)) {
        ids.add(Number(cid))
      }
    }
  }
  return ids
})

// Auto-expand contracts and purchases when product search is active
watch(productMatchContractIds, (ids) => {
  if (!ids || ids.size === 0) return
  // Expand matching contracts
  const toExpand = [...ids].filter(id => !expanded.value.includes(id))
  if (toExpand.length) expanded.value = [...expanded.value, ...toExpand]
  // Expand matching purchases to show items
  const q = fProduct.value.trim().toLowerCase()
  if (!q) return
  for (const [cid, purchases] of Object.entries(purchasesByContract.value)) {
    if (!ids.has(Number(cid))) continue
    for (const p of purchases) {
      if (p.items?.some(i => i.item_name?.toLowerCase().includes(q))) {
        expandedPurchases[p.id] = true
      }
    }
  }
})

const filtered = computed(() => {
  const q = appSearch.value.trim()

  // "По всей БД" — global search handled by GlobalSearch dialog, page shows all
  if (q && appSearchScope.value === 'global') return contracts.value

  let list = contracts.value
  if (fSubsidy.value.length)    list = list.filter(c => c.subsidy_id != null && fSubsidy.value.includes(c.subsidy_id))
  if (fType.value.length)       list = list.filter(c => fType.value.includes(c.contract_type))
  if (fMethod.value.length)     list = list.filter(c => c.purchase_method != null && fMethod.value.includes(c.purchase_method))
  if (fStatus.value.length)     list = list.filter(c => c.status != null && fStatus.value.includes(c.status))
  if (fContractor.value.length) {
    const allowedNames = new Set(
      usedContractors.value
        .filter((x: any) => fContractor.value.includes(x.id))
        .map((x: any) => x.name)
    )
    list = list.filter(c => !!c.contractor_name && allowedNames.has(c.contractor_name))
  }
  if (fDateFrom.value)          list = list.filter(c => !c.date || c.date >= fDateFrom.value)
  if (fDateTo.value)            list = list.filter(c => !c.date || c.date <= fDateTo.value)
  // Product filter
  if (productMatchContractIds.value) list = list.filter(c => productMatchContractIds.value!.has(c.id))
  // "По странице" — filter current list by search query
  if (q && appSearchScope.value === 'page') list = list.filter(c => matchesSearch(c, q))
  return list
})

const filteredWithRowNum = computed(() => {
  // Применяем column-header фильтры поверх основного filtered
  let list = filtered.value.filter(matchesColumnFilters)
  // Применяем локальную сортировку из ColumnHeaderMenu
  if (localSort.value) {
    const { key, order } = localSort.value
    list = [...list].sort((a, b) => {
      const av = (a as any)[key] ?? ''
      const bv = (b as any)[key] ?? ''
      const cmp = String(av).localeCompare(String(bv), 'ru', { numeric: true })
      return order === 'asc' ? cmp : -cmp
    })
  }
  // Нумерация по возрастанию id: более раннее (меньший id) = меньший _rownum
  const forNum = [...filtered.value].sort((a, b) => (Number(a.id) || 0) - (Number(b.id) || 0))
  const map = new Map<string, number>()
  forNum.forEach((c, idx) => map.set(String(c.id), idx + 1))
  return list.map(c => ({ ...c, _rownum: map.get(String(c.id)) ?? '' }))
})

const filteredSum = computed(() =>
  filtered.value.reduce((acc, c) => acc + (c.max_amount ? Number(c.max_amount) : 0), 0)
)

// ── Type / method / status lookup tables ──────────────────────────────────
const contractTypeItems = [
  { value: 'single',                label: 'Разовая поставка' },
  { value: 'framework_cumulative',  label: 'Рамочный (нарастающий итог)' },
  { value: 'framework_with_amount', label: 'Рамочный (с суммой)' },
  { value: 'invoice',               label: 'Счёт' },
  { value: 'invoice_contract',      label: 'Счёт-договор' },
  { value: 'advance_report',        label: 'Авансовый платёж' },
]
const purchaseMethodItems = [
  { value: 'single',      label: 'Единственный поставщик' },
  { value: 'competitive', label: 'Конкурсная процедура' },
]
const statusItems = [
  { value: 'active', label: 'Активен' },
  { value: 'closed', label: 'Закрыт' },
]

const contractTypeLabel = (t?: string) => contractTypeItems.find(i => i.value === t)?.label || t || '—'
const purchaseMethodLabel = (m?: string) => purchaseMethodItems.find(i => i.value === m)?.label || m || '—'
const statusLabel = (s?: string) => statusItems.find(i => i.value === s)?.label || s || '—'

const contractTypeLabels = Object.fromEntries(contractTypeItems.map(i => [i.value, i.label]))
const purchaseMethodLabels = Object.fromEntries(purchaseMethodItems.map(i => [i.value, i.label]))
const statusLabels = Object.fromEntries(statusItems.map(i => [i.value, i.label]))

const PURCHASE_STATUS_LABEL: Record<string, string> = {
  wishes: 'Желания', plan_schedule: 'План-график', confirmed: 'Подтверждено',
  work_in_progress: 'Ведётся работа', contracted: 'Договор',
  delivered: 'Поставлено', paid: 'Оплачено',
}
const PURCHASE_STATUS_COLOR: Record<string, string> = {
  wishes: 'grey', plan_schedule: 'orange', confirmed: 'blue',
  work_in_progress: 'teal', contracted: 'indigo', delivered: 'deep-purple', paid: 'green',
}
const contractTypeColor = (t?: string) => {
  if (t === 'single') return 'blue'
  if (t?.startsWith('framework')) return 'orange'
  if (t === 'invoice' || t === 'invoice_contract') return 'teal'
  if (t === 'advance_report') return 'purple'
  return 'grey'
}

const isExpired = (d: string) => new Date(d) < new Date()
const fmtDate = (d?: string) => d ? new Date(d).toLocaleDateString('ru-RU') : '—'
const formatMoney = (v: number | string) =>
  Number(v).toLocaleString('ru-RU', { minimumFractionDigits: 0, maximumFractionDigits: 2 }) + ' ₽'
const isFrameworkContract = (c: any): boolean =>
  c?.contract_type === 'framework_cumulative' || c?.contract_type === 'framework_non_cumulative'

// ── Table headers ──────────────────────────────────────────────────────────
const allColumns: ColumnDef[] = [
  // core — видимые по умолчанию
  // (_rownum добавляется отдельно через tableHeaders computed — всегда первая колонка,
  //  не зависит от useColumnConfig localStorage state)
  { title: '', key: 'data-table-expand', width: 40, sortable: false, group: 'core' },
  { title: '№ документа', key: 'number', group: 'core' },
  { title: 'Дата', key: 'date', width: 110, group: 'core' },
  { title: 'Тип', key: 'contract_type', width: 170, group: 'core' },
  { title: 'Способ', key: 'purchase_method', width: 130, group: 'core' },
  { title: 'Контрагент', key: 'contractor_name', group: 'core' },
  { title: 'Субсидия', key: 'subsidy_name', group: 'core' },
  { title: 'Предельная сумма', key: 'max_amount', align: 'end', width: 140, group: 'core' },
  { title: 'Заказано', key: 'total_ordered', align: 'end', width: 120, group: 'core' },
  { title: 'Поставлено', key: 'total_delivered', align: 'end', width: 120, group: 'core' },
  { title: 'Оплачено', key: 'total_paid', align: 'end', width: 120, group: 'core' },
  { title: 'Ост. (заказ)', key: 'remaining_ordered', align: 'end', width: 130, group: 'core' },
  { title: 'Не поставлено', key: 'remaining_delivered', align: 'end', width: 140, group: 'core' },
  { title: 'Не оплачено', key: 'remaining_paid', align: 'end', width: 130, group: 'core' },
  { title: 'Предмет договора', key: 'subject', group: 'core' },
  { title: 'Тип позиции', key: 'item_type', width: 90, group: 'core' },
  { title: 'Срок', key: 'end_date', width: 110, group: 'core' },
  // all — дополнительные поля из ContractOut / Contract модели
  { title: 'Дата начала', key: 'start_date', width: 130, group: 'all' },
  { title: 'Статус', key: 'status', width: 120, group: 'all' },
  { title: 'Примечания', key: 'notes', group: 'all' },
  { title: 'ИНН контрагента', key: 'contractor_inn', width: 160, group: 'all' },
  { title: 'ID контрагента', key: 'contractor_id', width: 140, group: 'all' },
  { title: 'ID субсидии', key: 'subsidy_id', width: 120, group: 'all' },
  { title: 'Плановый ежемесячный', key: 'planned_monthly', width: 190, align: 'end', group: 'all' },
  { title: 'Всего оплат', key: 'total_payment', width: 140, align: 'end', group: 'all' },
  { title: 'Остаток (legacy)', key: 'remaining', width: 150, align: 'end', group: 'all' },
  { title: 'Доп. субсидии', key: 'extra_subsidies', width: 160, group: 'all' },
]

const groups = [
  { key: 'core', label: 'Основные' },
  { key: 'all', label: 'Все возможные' },
]

const { state: colState, visibleHeaders, toggleVisible, setPosition, setWidth, reset: resetColumns, setFilter: cfgSetFilter, clearAllFilters: cfgClearAllFilters, activeFilterCount: cfgActiveFilterCount } = useColumnConfig('contracts', allColumns)
// _rownum — всегда первая колонка, не зависит от useColumnConfig состояния
const tableHeaders = computed(() => [
  { title: '№ п/п', key: '_rownum', width: 60, sortable: false },
  ...visibleHeaders.value,
])
const showColumnPicker = ref(false)

// ── Column header filters & sort ──────────────────────────────────────────
const localSort = ref<{ key: string; order: 'asc' | 'desc' } | null>(null)
function getSortBy(k: string): 'asc' | 'desc' | null {
  return localSort.value?.key === k ? localSort.value.order : null
}
function applySort(k: string, dir: 'asc' | 'desc' | null) {
  localSort.value = dir ? { key: k, order: dir } : null
}

function uniqValues(rows: any[], key: string): (string | number | null)[] {
  const set = new Set<any>()
  rows.forEach(r => set.add(r?.[key] ?? null))
  return [...set].sort((a, b) => String(a ?? '').localeCompare(String(b ?? '')))
}

function matchesColumnFilters(row: any): boolean {
  const filters = colState.value.filters
  for (const [k, f] of Object.entries(filters)) {
    const v = row?.[k] ?? null
    if (f.type === 'text') {
      if (!f.q) continue
      if (!String(v ?? '').toLowerCase().includes(f.q.toLowerCase())) return false
    } else if (f.type === 'enum') {
      if (!f.values || f.values.length === 0) continue
      if (!f.values.includes(v)) return false
    } else if (f.type === 'number') {
      const n = typeof v === 'number' ? v : parseFloat(v)
      if (f.min != null && !(n >= f.min)) return false
      if (f.max != null && !(n <= f.max)) return false
    } else if (f.type === 'date') {
      if (!v) { if (f.from || f.to) return false; continue }
      const d = String(v).slice(0, 10)
      if (f.from && d < f.from) return false
      if (f.to && d > f.to) return false
    } else if (f.type === 'boolean') {
      if (f.value == null) continue
      if (Boolean(v) !== f.value) return false
    }
  }
  return true
}

// ── Load data (all contracts, no server-side filter) ──────────────────────
const loadContracts = async () => {
  loading.value = true
  try {
    const [contractsData, advanceReports] = await Promise.all([
      apiFetch<Contract[]>('/contracts/'),
      apiFetch<any[]>('/purchases/?purchase_method=advance').catch(() => [])
    ])
    const arAsContracts = advanceReports.map((p: any) => ({
      id: p.id,
      number: p.registry_number || `АО-${p.id}`,
      date: p.created_at,
      contract_type: 'advance_report',
      contractor_name: p.contractor_name,
      contractor_inn: p.contractor_inn,
      subsidy_name: p.subsidy_name,
      subject: p.subject || p.item_name,
      max_amount: p.planned_total_price,
      total_ordered: p.planned_total_price,
      total_paid: null,
      status: p.status,
      _is_advance_report: true,
      _purchase_id: p.id,
      reimbursement_user_id: p.reimbursement_user_id,
      reimbursement_user_name: p.reimbursement_user_name,
      multi_contractor_label: p.multi_contractor_label,
    }))
    contracts.value = [...contractsData, ...arAsContracts]
  } catch {
    showSnack('Ошибка загрузки', 'error')
  } finally {
    loading.value = false
  }
}

const loadSubsidies = async () => { subsidies.value = await apiFetch<Subsidy[]>('/subsidies/') }
// Phase 26-YY: Pinia кэш (TTL 5 мин) — один запрос за сессию, переиспользуется во всех views
const contractorsStore = useContractorsStore()
const loadContractors = async () => {
  await contractorsStore.ensureLoaded()
  contractors.value = contractorsStore.list as Contractor[]
}

const loadPurchasesForContract = async (contractId: number) => {
  const c = contracts.value.find(x => x.id === contractId) as any
  if (c?._is_advance_report) {
    // Авансовый отчёт = одна Purchase. Грузим её items напрямую.
    const p = await apiFetch<Purchase>(`/purchases/${c._purchase_id}`)
    purchasesByContract.value = { ...purchasesByContract.value, [contractId]: [p] }
    return
  }
  const items = await apiFetch<Purchase[]>(`/purchases/by-contract/${contractId}`)
  purchasesByContract.value = { ...purchasesByContract.value, [contractId]: items }
}

const loadAllPurchases = async () => {
  // Load purchases for all contracts (needed for product search)
  const ids = contracts.value.map(c => c.id)
  const batchSize = 10
  for (let i = 0; i < ids.length; i += batchSize) {
    const batch = ids.slice(i, i + batchSize)
    await Promise.all(batch.filter(id => !purchasesByContract.value[id]).map(id => loadPurchasesForContract(id)))
  }
}

watch(expanded, (newVal) => {
  for (const id of newVal) {
    if (!purchasesByContract.value[id]) loadPurchasesForContract(id)
  }
})

// When product filter starts being typed, load all purchases if not yet loaded
watch(fProduct, (val) => {
  if (val && val.trim().length >= 2) {
    const missingIds = contracts.value.filter(c => !purchasesByContract.value[c.id]).map(c => c.id)
    if (missingIds.length) loadAllPurchases()
  }
})

// ── Dialog ─────────────────────────────────────────────────────────────────
const emptyForm = () => ({
  number: '', date: '', contract_type: 'single', purchase_method: null as string | null, item_type: null as string | null,
  contractor_id: null as number | null, subsidy_id: null as number | null,
  extra_subsidy_ids: [] as number[],
  subject: '', max_amount: null as number | null, planned_monthly: null as number | null,
  start_date: '', end_date: '', status: 'active', notes: '',
})
const dialog = reactive({ show: false, saving: false, id: 0, form: emptyForm() })

const openCreate = () => { dialog.id = 0; Object.assign(dialog.form, emptyForm()); dialog.show = true }

const openEdit = async (c: Contract) => {
  if ((c as any)._is_advance_report) {
    router.push(`/advance-reports/${(c as any)._purchase_id}/edit`)
    return
  }
  dialog.id = c.id
  // Ensure contractor is loaded before showing
  if (c.contractor_id && !contractors.value.find(x => x.id === c.contractor_id)) {
    try {
      const fetched = await apiFetch<Contractor>(`/contractors/${c.contractor_id}`)
      contractors.value.push(fetched)
    } catch {}
  }
  Object.assign(dialog.form, {
    number: c.number || '', date: c.date || '', contract_type: c.contract_type || 'single',
    purchase_method: c.purchase_method || null, item_type: (c as any).item_type || null, contractor_id: c.contractor_id || null,
    subsidy_id: c.subsidy_id || null,
    extra_subsidy_ids: (c.extra_subsidies || []).map(es => es.subsidy_id),
    subject: c.subject || '',
    max_amount: c.max_amount || null, planned_monthly: c.planned_monthly || null,
    start_date: c.start_date || '', end_date: c.end_date || '',
    status: c.status || 'active', notes: c.notes || '',
  })
  dialog.show = true
}

const saveContract = async () => {
  dialog.saving = true
  try {
    const body = { ...dialog.form, date: dialog.form.date || null, start_date: dialog.form.start_date || null, end_date: dialog.form.end_date || null }
    if (dialog.id) {
      await apiFetch(`/contracts/${dialog.id}`, { method: 'PUT', body: JSON.stringify(body) })
      showSnack('Сохранено')
    } else {
      await apiFetch('/contracts/', { method: 'POST', body: JSON.stringify(body) })
      showSnack('Создано')
    }
    dialog.show = false
    await loadContracts()
  } catch (e: any) {
    showSnack(e?.detail || 'Ошибка сохранения', 'error')
  } finally {
    dialog.saving = false
  }
}

// ── Monthly Stages ─────────────────────────────────────────────────────────
const monthlyStagesDialog = reactive({
  show: false,
  contractId: 0,
  contractName: '',
  contractType: '',
  subsidyId: null as number | null,
  defaultAmount: null as number | null,
})

function openMonthlyStagesFromDialog() {
  const c = contracts.value.find(x => x.id === dialog.id)
  monthlyStagesDialog.contractId = dialog.id
  monthlyStagesDialog.contractName = c?.number || ''
  monthlyStagesDialog.contractType = dialog.form.contract_type
  monthlyStagesDialog.subsidyId = dialog.form.subsidy_id
  monthlyStagesDialog.defaultAmount = dialog.form.planned_monthly
  dialog.show = false
  monthlyStagesDialog.show = true
}

function onMonthlyStagesCreated(res: any) {
  const created = res.created?.length ?? 0
  showSnack(`Создано ${created} этапов`)
  loadContracts()
}

const deleteDialog = reactive({ show: false, deleting: false, item: null as Contract | null })
const confirmDelete = (c: Contract) => { deleteDialog.item = c; deleteDialog.show = true }
const doDelete = async () => {
  if (!deleteDialog.item) return
  deleteDialog.deleting = true
  try {
    await apiFetch(`/contracts/${deleteDialog.item.id}`, { method: 'DELETE' })
    showSnack('Удалено', 'warning')
    deleteDialog.show = false
    await loadContracts()
  } catch (e: any) {
    showSnack(e?.detail || 'Ошибка удаления', 'error')
  } finally {
    deleteDialog.deleting = false
  }
}

// ── Migration ──────────────────────────────────────────────────────────────
const migrateDialog = ref(false)
const migrating = ref(false)
const migrateResult = ref<{ created: number; skipped: number } | null>(null)

watch(migrateDialog, (v) => { if (!v) migrateResult.value = null })

const doMigrate = async () => {
  migrating.value = true
  try {
    const res = await apiFetch<{ created: number; skipped: number }>('/contracts/migrate-from-purchases', { method: 'POST' })
    migrateResult.value = res
    if (res.created > 0) await loadContracts()
    showSnack(`Создано: ${res.created}`)
  } catch (e: any) {
    showSnack(e?.detail || 'Ошибка миграции', 'error')
  } finally {
    migrating.value = false
  }
}

// ── Import from file ─────────────────────────────────────────────────────
const importFields = [
  { key: 'number', label: 'Номер договора', required: true },
  { key: 'date', label: 'Дата договора', required: false },
  { key: 'contractor', label: 'Контрагент (название/ИНН)', required: false },
  { key: 'subject', label: 'Предмет', required: false },
  { key: 'max_amount', label: 'Сумма', required: false },
  { key: 'start_date', label: 'Дата начала', required: false },
  { key: 'end_date', label: 'Дата окончания', required: false },
  { key: 'contract_type', label: 'Тип договора', required: false },
  { key: 'purchase_method', label: 'Способ закупки', required: false },
  { key: 'item_type', label: 'Тип (товар/услуга)', required: false },
  { key: 'status', label: 'Статус', required: false },
  { key: 'notes', label: 'Примечания', required: false },
]

const importDialog = reactive({
  show: false,
  step: 1,
  loading: false,
  dragging: false,
  file: null as File | null,
  subsidyId: null as number | null,
  headers: [] as string[],
  headerOptions: [] as { title: string; value: number }[],
  sample: [] as string[][],
  totalRows: 0,
  headerRowOffset: 0,
  sheetName: '',
  mapping: {} as Record<string, number | null>,
  result: null as { created: number; skipped: number } | null,
  error: '',
})

const subsidyOptions = computed(() => subsidies.value)

function closeImportDialog() {
  importDialog.show = false
  importDialog.step = 1
  importDialog.file = null
  importDialog.headers = []
  importDialog.headerOptions = []
  importDialog.sample = []
  importDialog.mapping = {}
  importDialog.result = null
  importDialog.error = ''
  importDialog.subsidyId = null
  if (importDialog.result?.created) loadContracts()
}

async function doImportPreview() {
  if (!importDialog.file) return
  importDialog.loading = true
  importDialog.error = ''
  try {
    const fd = new FormData()
    fd.append('file', importDialog.file)
    const res = await fetch('/api/contracts/import/preview', {
      method: 'POST',
      headers: { Authorization: `Bearer ${localStorage.getItem('auth_token')}` },
      body: fd,
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Ошибка загрузки' }))
      throw new Error(err.detail || err.message || 'Ошибка')
    }
    const data = await res.json()
    importDialog.headers = data.headers
    importDialog.headerOptions = data.headers.map((h: string, i: number) => ({ title: h, value: i }))
    importDialog.sample = data.sample
    importDialog.totalRows = data.total_rows
    importDialog.headerRowOffset = data.header_row_offset
    importDialog.sheetName = data.sheet_name || ''
    // Auto-map by header hints
    importDialog.mapping = {}
    for (let i = 0; i < data.headers.length; i++) {
      const h = (data.headers[i] as string).toLowerCase()
      if (/номер|number|№\s*догов/.test(h) && !importDialog.mapping.number) importDialog.mapping.number = i
      else if (/дата\s*(догов|заключ)|date/.test(h) && !importDialog.mapping.date) importDialog.mapping.date = i
      else if (/контрагент|поставщик|исполнитель|contractor/.test(h) && !importDialog.mapping.contractor) importDialog.mapping.contractor = i
      else if (/предмет|subject/.test(h) && !importDialog.mapping.subject) importDialog.mapping.subject = i
      else if (/сумм|цена|amount|стоимость/.test(h) && !importDialog.mapping.max_amount) importDialog.mapping.max_amount = i
      else if (/начал|start/.test(h) && !importDialog.mapping.start_date) importDialog.mapping.start_date = i
      else if (/оконч|end|заверш/.test(h) && !importDialog.mapping.end_date) importDialog.mapping.end_date = i
      else if (/тип\s*догов|type/.test(h) && !importDialog.mapping.contract_type) importDialog.mapping.contract_type = i
      else if (/способ|метод|method/.test(h) && !importDialog.mapping.purchase_method) importDialog.mapping.purchase_method = i
      else if (/примечан|notes|комментар/.test(h) && !importDialog.mapping.notes) importDialog.mapping.notes = i
      else if (/статус|status/.test(h) && !importDialog.mapping.status) importDialog.mapping.status = i
    }
    importDialog.step = 2
  } catch (e: any) {
    importDialog.error = e.message || 'Ошибка'
  } finally {
    importDialog.loading = false
  }
}

async function doImportMapped() {
  if (!importDialog.file || importDialog.mapping.number == null) return
  importDialog.loading = true
  importDialog.error = ''
  try {
    const fd = new FormData()
    fd.append('file', importDialog.file)
    const params = new URLSearchParams()
    params.set('header_row_offset', String(importDialog.headerRowOffset))
    for (const [key, val] of Object.entries(importDialog.mapping)) {
      if (val != null) params.set(`col_${key}`, String(val))
    }
    if (importDialog.subsidyId) params.set('subsidy_id', String(importDialog.subsidyId))
    const res = await fetch(`/api/contracts/import/mapped?${params}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${localStorage.getItem('auth_token')}` },
      body: fd,
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Ошибка импорта' }))
      throw new Error(err.detail || err.message || 'Ошибка')
    }
    const data = await res.json()
    importDialog.result = data
    importDialog.step = 3
    if (data.created > 0) await loadContracts()
  } catch (e: any) {
    importDialog.error = e.message || 'Ошибка'
  } finally {
    importDialog.loading = false
  }
}

onMounted(() => { loadContracts(); loadSubsidies(); loadContractors() })
</script>

<style scoped>
.import-dropzone {
  border: 2px dashed rgba(var(--v-border-color), 0.3);
  transition: all 0.2s;
  cursor: pointer;
}
.import-dropzone--active,
.import-dropzone:hover {
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.04);
}
.import-drop-btn--hover {
  outline: 2px dashed rgb(var(--v-theme-info));
  outline-offset: 2px;
  background: rgba(var(--v-theme-info), 0.08) !important;
}
</style>
