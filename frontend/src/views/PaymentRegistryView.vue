<template>
  <v-container fluid class="pa-4">
    <!-- Header -->
    <div class="d-flex align-center justify-space-between mb-4 flex-wrap gap-2">
      <div>
        <h1 class="text-h5 font-weight-bold">
          Реестр платежей
          <span v-if="importId" class="text-medium-emphasis font-weight-regular">· Импорт #{{ importId }}</span>
        </h1>
        <span class="text-body-2 text-medium-emphasis">{{ totalCount }} записей</span>
      </div>
      <div class="d-flex ga-2 align-center">
        <v-btn prepend-icon="mdi-table-check" variant="outlined" color="warning" @click="openReconciliation">
          Сверка платежей
        </v-btn>
        <v-btn prepend-icon="mdi-view-column" variant="outlined" color="primary" @click="showColumnPicker = true">
          Колонки
        </v-btn>
        <RegistryExportButton
          title="Реестр платежей"
          :get-columns="() => visibleColumnHeaders.filter(h => !['actions','avatar','data-table-expand','data-table-select'].includes(h.key) && !!h.title).map(h => ({ key: h.key, title: h.title, align: h.align }))"
          :get-rows="() => searchedItems"
          :get-capture-el="() => registryArea"
          @error="(msg) => error(msg)"
        />
        <v-btn-toggle
          v-if="!prMobile"
          v-model="prViewMode"
          mandatory
          density="comfortable"
          variant="outlined"
          divided
        >
          <v-btn value="table" size="small" icon="mdi-table" title="Таблица" />
          <v-btn value="cards" size="small" icon="mdi-view-grid" title="Карточки" />
        </v-btn-toggle>
      </div>
    </div>

    <!-- 27.4-21: Reconciliation dialog -->
    <v-dialog v-model="reconciliationDialog" max-width="1100" scrollable :fullscreen="mobile">
      <v-card>
        <v-card-title class="d-flex align-center pa-4 pb-2">
          <v-icon start color="warning">mdi-table-check</v-icon>
          Сверка платежей: реестр vs закупки
          <span v-if="importId" class="text-caption text-medium-emphasis ml-2">Импорт #{{ importId }}</span>
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" @click="reconciliationDialog = false" />
        </v-card-title>
        <v-card-text class="pa-4">
          <div v-if="reconciliationLoading" class="d-flex justify-center py-6">
            <v-progress-circular indeterminate color="warning" />
          </div>
          <div v-else-if="reconciliation">
            <div class="d-flex ga-2 mb-3">
              <v-chip color="success" variant="tonal" size="small" prepend-icon="mdi-check">
                Совпало: {{ reconciliation.match_count }}
              </v-chip>
              <v-chip color="error" variant="tonal" size="small" prepend-icon="mdi-currency-rub">
                Расходятся суммы: {{ reconciliation.mismatch_count }}
              </v-chip>
              <v-chip color="error" variant="tonal" size="small" prepend-icon="mdi-alert">
                Только в реестре: {{ reconciliation.registry_only_count }}
              </v-chip>
              <v-chip color="warning" variant="tonal" size="small" prepend-icon="mdi-help">
                Только в закупках: {{ reconciliation.purchases_only_count }}
              </v-chip>
              <v-chip color="orange" variant="tonal" size="small" prepend-icon="mdi-account-alert">
                Заявлено, не подтверждено: {{ reconciliation.declared_unconfirmed_count }}
              </v-chip>
              <v-spacer />
              <v-chip size="small" variant="tonal">
                Показано: {{ filteredReconciliationRows.length }} / {{ reconciliation.total }}
              </v-chip>
            </div>

            <!-- 27.4-22: filter -->
            <v-text-field
              v-model="reconciliationFilter"
              placeholder="Фильтр по получателю / номеру / статусу..."
              prepend-inner-icon="mdi-magnify"
              density="compact" variant="outlined" hide-details clearable
              class="mb-3" />

            <v-table density="compact">
              <thead>
                <tr>
                  <th>№ платежа</th>
                  <th class="text-right">Реестр (₽)</th>
                  <th class="text-right">Привязано (₽)</th>
                  <th class="text-right">Δ (₽)</th>
                  <th>Получатель</th>
                  <th>Закупки</th>
                  <th>Статус</th>
                  <th style="width:140px">Действие</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in filteredReconciliationRows" :key="r.payment_number"
                    :class="reconciliationRowClass(r.status)">
                  <td><b>{{ r.payment_number }}</b></td>
                  <td class="text-right">{{ formatMoney(r.registry_amount) }}</td>
                  <td class="text-right">{{ formatMoney(r.purchases_amount) }}</td>
                  <td class="text-right" :class="r.amount_diff > 0.02 ? 'text-error font-weight-bold' : ''">
                    {{ r.amount_diff > 0.02 ? formatMoney(r.amount_diff) : '—' }}
                  </td>
                  <td class="text-caption">{{ (r.registry_payees || []).join(', ') || '—' }}</td>
                  <td>
                    <a v-for="pid in (r.linked_purchase_ids || [])" :key="pid"
                       :href="`/orders/${pid}/edit`" target="_blank" class="mr-1">
                      <v-chip size="x-small" color="primary" variant="tonal">#{{ pid }}</v-chip>
                    </a>
                    <span v-if="!(r.linked_purchase_ids || []).length" class="text-medium-emphasis">—</span>
                  </td>
                  <td>
                    <v-chip :color="reconciliationStatusColor(r.status)" size="x-small" variant="flat">
                      {{ reconciliationStatusLabel(r.status) }}
                    </v-chip>
                  </td>
                  <td>
                    <v-btn v-if="(r.registry_ids?.length === 1) && r.status !== 'match'"
                           size="x-small" variant="tonal" color="primary"
                           prepend-icon="mdi-link-variant"
                           @click="openMatchFromReconciliation(r.registry_ids[0])">
                      Привязать
                    </v-btn>
                    <v-menu v-else-if="(r.registry_ids?.length || 0) > 1">
                      <template #activator="{ props: ap }">
                        <v-btn v-bind="ap" size="x-small" variant="tonal" color="primary"
                               prepend-icon="mdi-link-variant" append-icon="mdi-menu-down">
                          Привязать ({{ r.registry_ids.length }})
                        </v-btn>
                      </template>
                      <v-list density="compact">
                        <v-list-item v-for="bpId in r.registry_ids" :key="bpId"
                                     :title="`Платёж #${bpId}`"
                                     @click="openMatchFromReconciliation(bpId)" />
                      </v-list>
                    </v-menu>
                    <span v-else class="text-medium-emphasis">—</span>
                  </td>
                </tr>
              </tbody>
            </v-table>
          </div>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="reconciliationDialog = false">Закрыть</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Stale parsed alert: записи где parsed_contract_number совпадает с номером субсидии -->
    <v-alert
      v-if="hasStaleParsed"
      type="warning"
      variant="tonal"
      closable
      density="compact"
      class="mb-3"
      @click:close="staleParsedDismissed = true"
    >
      В реестре есть записи где номер субсидии попал в колонку «Договор (авто)».
      Откройте импорт → нажмите «Перепарсить» для исправления.
    </v-alert>

    <!-- Filters -->
    <v-card class="mb-4" variant="outlined" rounded="lg">
      <v-card-text class="py-2 px-3">
        <div class="d-flex align-center gap-1 mb-2">
          <v-icon size="16" color="grey">mdi-filter</v-icon>
          <span class="text-caption font-weight-medium text-medium-emphasis">ФИЛЬТРЫ</span>
          <v-spacer />
          <!-- Import badge -->
          <v-chip
            v-if="importId"
            size="small"
            color="blue"
            variant="tonal"
            closable
            @click:close="clearImport"
          >Фильтр: Импорт #{{ importId }}</v-chip>
          <v-chip
            v-if="activeFilterCount > 0"
            size="small"
            color="primary"
            variant="tonal"
            prepend-icon="mdi-filter-check"
          >Фильтры {{ activeFilterCount }}</v-chip>
          <v-btn v-if="hasFilters" variant="text" size="x-small" color="error" prepend-icon="mdi-filter-remove" @click="clearFilters">
            Сбросить
          </v-btn>
        </div>
        <div class="d-flex flex-wrap gap-2 align-end">
          <v-text-field
            v-model="searchQuery"
            prepend-inner-icon="mdi-magnify"
            label="Поиск по любому полю"
            variant="outlined"
            density="compact"
            hide-details
            clearable
            style="min-width:220px; max-width:340px"
          />
          <v-select
            v-model="filterSubsidyId"
            :items="subsidiesList"
            item-title="name"
            item-value="id"
            label="Субсидия"
            variant="outlined"
            density="compact"
            hide-details
            clearable
            style="min-width:180px; max-width:260px"
          />
          <v-text-field
            v-model="fDateFrom"
            label="Дата от"
            type="date"
            variant="outlined"
            density="compact"
            hide-details
            clearable
            style="min-width:145px; max-width:145px"
          />
          <v-text-field
            v-model="fDateTo"
            label="Дата до"
            type="date"
            variant="outlined"
            density="compact"
            hide-details
            clearable
            style="min-width:145px; max-width:145px"
          />
          <v-select
            v-model="fStatus"
            :items="statusOptions"
            item-title="label"
            item-value="value"
            label="Статус"
            variant="outlined"
            density="compact"
            hide-details
            clearable
            style="min-width:160px; max-width:200px"
          />
          <v-select
            v-model="fMatched"
            :items="yesNoOptions"
            item-title="label"
            item-value="value"
            label="Сматчено"
            variant="outlined"
            density="compact"
            hide-details
            clearable
            style="min-width:160px; max-width:200px"
          />
          <v-select
            v-model="fConfirmed"
            :items="yesNoOptions"
            item-title="label"
            item-value="value"
            label="Подтверждено"
            variant="outlined"
            density="compact"
            hide-details
            clearable
            style="min-width:165px; max-width:200px"
          />
          <v-text-field
            v-model="fInn"
            label="ИНН получателя"
            variant="outlined"
            density="compact"
            hide-details
            clearable
            style="min-width:160px; max-width:200px"
            @keyup.enter="applyFilters"
          />
          <v-select
            v-model="fDisposition"
            :items="dispositionOptions"
            item-title="label"
            item-value="value"
            label="Разнесение"
            variant="outlined"
            density="compact"
            hide-details
            clearable
            style="min-width:190px; max-width:230px"
          />
          <v-btn color="primary" variant="elevated" @click="applyFilters" :loading="loading">
            Применить
          </v-btn>
          <v-chip color="primary" variant="tonal" prepend-icon="mdi-cash-multiple" size="small" class="ml-2">
            Сумма: {{ formatMoney(filteredSum) }}
          </v-chip>
        </div>
      </v-card-text>
    </v-card>

    <!-- Table -->
    <div ref="registryArea">
    <v-data-table
      v-if="prEffectiveView === 'table'"
      v-resizable-columns="'payment-registry'"
      :headers="tableHeaders"
      :items="searchedItemsWithRowNum"
      :loading="loading"
      density="compact"
      show-expand
      v-model:expanded="expanded"
      item-value="id"
      class="elevation-1"
      fixed-header
      height="calc(100vh - 320px)"
      :items-per-page="50"
      :items-per-page-options="[25, 50, 100]"
      :page="page"
      @update:page="page = $event"
    >
      <!-- ColumnHeaderMenu slots — только типизированные core-колонки -->
      <template #header.payment_number="{ column }">
        <ColumnHeaderMenu col-key="payment_number" :title="column.title" col-type="text"
          :model-value="colConfigState.filters['payment_number'] ?? null"
          :sort-by="getSortBy('payment_number')"
          @update:model-value="v => setFilter('payment_number', v)"
          @sort="dir => applySort('payment_number', dir)"
          @hide="toggleVisible('payment_number', false)" />
      </template>
      <template #header.payer_name="{ column }">
        <ColumnHeaderMenu col-key="payer_name" :title="column.title" col-type="text"
          :model-value="colConfigState.filters['payer_name'] ?? null"
          :sort-by="getSortBy('payer_name')"
          @update:model-value="v => setFilter('payer_name', v)"
          @sort="dir => applySort('payer_name', dir)"
          @hide="toggleVisible('payer_name', false)" />
      </template>
      <template #header.payee_name="{ column }">
        <ColumnHeaderMenu col-key="payee_name" :title="column.title" col-type="text"
          :model-value="colConfigState.filters['payee_name'] ?? null"
          :sort-by="getSortBy('payee_name')"
          @update:model-value="v => setFilter('payee_name', v)"
          @sort="dir => applySort('payee_name', dir)"
          @hide="toggleVisible('payee_name', false)" />
      </template>
      <template #header.payer_inn="{ column }">
        <ColumnHeaderMenu col-key="payer_inn" :title="column.title" col-type="text"
          :model-value="colConfigState.filters['payer_inn'] ?? null"
          :sort-by="getSortBy('payer_inn')"
          @update:model-value="v => setFilter('payer_inn', v)"
          @sort="dir => applySort('payer_inn', dir)"
          @hide="toggleVisible('payer_inn', false)" />
      </template>
      <template #header.payee_inn="{ column }">
        <ColumnHeaderMenu col-key="payee_inn" :title="column.title" col-type="text"
          :model-value="colConfigState.filters['payee_inn'] ?? null"
          :sort-by="getSortBy('payee_inn')"
          @update:model-value="v => setFilter('payee_inn', v)"
          @sort="dir => applySort('payee_inn', dir)"
          @hide="toggleVisible('payee_inn', false)" />
      </template>
      <template #header.purpose_text="{ column }">
        <ColumnHeaderMenu col-key="purpose_text" :title="column.title" col-type="text"
          :model-value="colConfigState.filters['purpose_text'] ?? null"
          :sort-by="getSortBy('purpose_text')"
          @update:model-value="v => setFilter('purpose_text', v)"
          @sort="dir => applySort('purpose_text', dir)"
          @hide="toggleVisible('purpose_text', false)" />
      </template>
      <template #header.parsed_contract_number="{ column }">
        <ColumnHeaderMenu col-key="parsed_contract_number" :title="column.title" col-type="text"
          :model-value="colConfigState.filters['parsed_contract_number'] ?? null"
          :sort-by="getSortBy('parsed_contract_number')"
          @update:model-value="v => setFilter('parsed_contract_number', v)"
          @sort="dir => applySort('parsed_contract_number', dir)"
          @hide="toggleVisible('parsed_contract_number', false)" />
      </template>
      <template #header.parsed_kbk="{ column }">
        <ColumnHeaderMenu col-key="parsed_kbk" :title="column.title" col-type="text"
          :model-value="colConfigState.filters['parsed_kbk'] ?? null"
          :sort-by="getSortBy('parsed_kbk')"
          @update:model-value="v => setFilter('parsed_kbk', v)"
          @sort="dir => applySort('parsed_kbk', dir)"
          @hide="toggleVisible('parsed_kbk', false)" />
      </template>
      <template #header.expense_code="{ column }">
        <ColumnHeaderMenu col-key="expense_code" :title="column.title" col-type="text"
          :model-value="colConfigState.filters['expense_code'] ?? null"
          :sort-by="getSortBy('expense_code')"
          @update:model-value="v => setFilter('expense_code', v)"
          @sort="dir => applySort('expense_code', dir)"
          @hide="toggleVisible('expense_code', false)" />
      </template>
      <template #header.status="{ column }">
        <ColumnHeaderMenu col-key="status" :title="column.title" col-type="enum"
          :items="uniqValues(payments, 'status')"
          :model-value="colConfigState.filters['status'] ?? null"
          :sort-by="getSortBy('status')"
          @update:model-value="v => setFilter('status', v)"
          @sort="dir => applySort('status', dir)"
          @hide="toggleVisible('status', false)" />
      </template>
      <template #header.matched="{ column }">
        <ColumnHeaderMenu col-key="matched" :title="column.title" col-type="boolean"
          :model-value="colConfigState.filters['matched'] ?? null"
          :sort-by="getSortBy('matched')"
          @update:model-value="v => setFilter('matched', v)"
          @sort="dir => applySort('matched', dir)"
          @hide="toggleVisible('matched', false)" />
      </template>
      <template #header.matched_confirmed="{ column }">
        <ColumnHeaderMenu col-key="matched_confirmed" :title="column.title" col-type="boolean"
          :model-value="colConfigState.filters['matched_confirmed'] ?? null"
          :sort-by="getSortBy('matched_confirmed')"
          @update:model-value="v => setFilter('matched_confirmed', v)"
          @sort="dir => applySort('matched_confirmed', dir)"
          @hide="toggleVisible('matched_confirmed', false)" />
      </template>
      <template #header.amount="{ column }">
        <ColumnHeaderMenu col-key="amount" :title="column.title" col-type="number"
          :model-value="colConfigState.filters['amount'] ?? null"
          :sort-by="getSortBy('amount')"
          align="end"
          @update:model-value="v => setFilter('amount', v)"
          @sort="dir => applySort('amount', dir)"
          @hide="toggleVisible('amount', false)" />
      </template>
      <template #header.payment_date="{ column }">
        <ColumnHeaderMenu col-key="payment_date" :title="column.title" col-type="date"
          :model-value="colConfigState.filters['payment_date'] ?? null"
          :sort-by="getSortBy('payment_date')"
          @update:model-value="v => setFilter('payment_date', v)"
          @sort="dir => applySort('payment_date', dir)"
          @hide="toggleVisible('payment_date', false)" />
      </template>
      <template #header.parsed_contract_date="{ column }">
        <ColumnHeaderMenu col-key="parsed_contract_date" :title="column.title" col-type="date"
          :model-value="colConfigState.filters['parsed_contract_date'] ?? null"
          :sort-by="getSortBy('parsed_contract_date')"
          @update:model-value="v => setFilter('parsed_contract_date', v)"
          @sort="dir => applySort('parsed_contract_date', dir)"
          @hide="toggleVisible('parsed_contract_date', false)" />
      </template>

      <!-- Index -->
      <template #item.index="{ index }">
        <span class="text-medium-emphasis">{{ (page - 1) * 50 + index + 1 }}</span>
      </template>

      <!-- Date -->
      <template #item.payment_date="{ item }">
        {{ fmtDate(item.payment_date) }}
      </template>

      <!-- Payer -->
      <template #item.payer_name="{ item }">
        <div class="text-body-2">
          {{ item.payer_name_resolved || item.payer_name || '—' }}
        </div>
        <div v-if="item.payer_name_resolved && item.payer_name_resolved !== item.payer_name" class="text-caption text-medium-emphasis" :title="item.payer_name || ''">
          ({{ item.payer_name }})
        </div>
      </template>

      <!-- Payee -->
      <template #item.payee_name="{ item }">
        <div class="text-body-2">
          {{ item.payee_name_resolved || item.payee_name || '—' }}
        </div>
        <div v-if="item.payee_inn" class="text-caption text-medium-emphasis">ИНН {{ item.payee_inn }}</div>
      </template>

      <!-- Amount -->
      <template #item.amount="{ item }">
        <span class="font-weight-medium">{{ formatMoney(item.amount) }}</span>
      </template>

      <!-- Status chip -->
      <template #item.status="{ item }">
        <v-chip size="x-small" :color="statusColor(item.status)" variant="tonal">
          {{ item.status || '—' }}
        </v-chip>
      </template>

      <!-- Parsed contract / advance report / agreement -->
      <template #item.parsed_contract_number="{ item }">
        <span class="text-caption">{{ docDisplay(item) }}</span>
      </template>

      <!-- Matched chip -->
      <template #item.matched="{ item }">
        <v-chip
          v-if="item.matched_contract_id"
          size="x-small"
          color="success"
          variant="tonal"
          prepend-icon="mdi-check"
        >Да</v-chip>
        <v-chip v-else size="x-small" color="grey" variant="tonal">Нет</v-chip>
      </template>

      <!-- Confirmed chip (key = matched_confirmed) -->
      <template #item.matched_confirmed="{ item }">
        <v-chip
          v-if="item.matched_confirmed"
          size="x-small"
          color="blue"
          variant="tonal"
          prepend-icon="mdi-check-decagram"
        >Да</v-chip>
        <v-chip v-else size="x-small" color="grey" variant="tonal">Нет</v-chip>
      </template>

      <!-- 27.4-23: Match: Контрагент — название + ИНН-аналог в подписи -->
      <template #item.matched_contractor_id="{ item }">
        <div v-if="item.matched_contractor_id">
          <a :href="`/suppliers?contractor_id=${item.matched_contractor_id}`"
             target="_blank"
             class="text-primary text-decoration-none text-body-2"
             :title="item.matched_contractor_name || ''">
            {{ item.matched_contractor_name || `#${item.matched_contractor_id}` }}
          </a>
          <div class="text-caption text-medium-emphasis">#{{ item.matched_contractor_id }}</div>
        </div>
        <span v-else class="text-medium-emphasis">—</span>
      </template>

      <!-- 27.4-23: Match: Субсидия — название -->
      <template #item.matched_subsidy_id="{ item }">
        <div v-if="item.matched_subsidy_id">
          <div class="text-body-2" :title="item.matched_subsidy_name || ''">
            {{ item.matched_subsidy_name || `#${item.matched_subsidy_id}` }}
          </div>
          <div class="text-caption text-medium-emphasis">#{{ item.matched_subsidy_id }}</div>
        </div>
        <span v-else class="text-medium-emphasis">—</span>
      </template>

      <!-- 27.4-23: Match: Договор — № + предмет + дата -->
      <template #item.matched_contract_id="{ item }">
        <div v-if="item.matched_contract_id">
          <div class="text-body-2 font-weight-medium">
            <span v-if="item.matched_contract_number">№ {{ item.matched_contract_number }}</span>
            <span v-else>#{{ item.matched_contract_id }}</span>
            <span v-if="item.matched_contract_date" class="text-caption text-medium-emphasis ml-1">
              от {{ fmtDate(item.matched_contract_date) }}
            </span>
          </div>
          <div v-if="item.matched_contract_subject" class="text-caption text-medium-emphasis" style="max-width:220px"
               :title="item.matched_contract_subject">
            {{ item.matched_contract_subject }}
          </div>
        </div>
        <span v-else class="text-medium-emphasis">—</span>
      </template>

      <!-- 27.4-20/23: Match: Закупка — кликабельный № + предмет + сумма -->
      <template #item.matched_purchase_id="{ item }">
        <div v-if="item.matched_purchase_id">
          <a :href="`/orders/${item.matched_purchase_id}/edit`"
             target="_blank"
             class="text-primary text-decoration-none">
            <v-chip size="x-small" color="primary" variant="tonal" prepend-icon="mdi-arrow-right-bold">
              <span v-if="item.matched_purchase_number">№ {{ item.matched_purchase_number }}</span>
              <span v-else>#{{ item.matched_purchase_id }}</span>
            </v-chip>
          </a>
          <div v-if="item.matched_purchase_item_name" class="text-caption text-medium-emphasis mt-1" style="max-width:220px"
               :title="item.matched_purchase_item_name">
            {{ item.matched_purchase_item_name }}
          </div>
          <div v-if="item.matched_purchase_amount != null" class="text-caption font-weight-medium">
            {{ formatMoney(item.matched_purchase_amount) }}
          </div>
        </div>
        <span v-else class="text-medium-emphasis">—</span>
      </template>

      <!-- Этап 7в: Код расходов -->
      <template #item.expense_code="{ item }">
        <v-chip v-if="item.expense_code" size="x-small" variant="tonal" color="blue" :title="item.expense_code_name || ''">
          {{ item.expense_code }}
        </v-chip>
        <span v-else class="text-medium-emphasis">—</span>
      </template>

      <!-- Этап 7в: Куда отнесён — закупки, на которые платёж реально разнесён -->
      <template #item.attached_purchases="{ item }">
        <div v-if="item.attached_purchases && item.attached_purchases.length">
          <a v-for="ap in item.attached_purchases" :key="ap.purchase_id"
             :href="`/orders/${ap.purchase_id}/edit`" target="_blank"
             class="text-decoration-none d-block mb-1">
            <v-chip size="x-small" color="primary" variant="tonal" prepend-icon="mdi-arrow-right-bold">
              <span v-if="ap.purchase_number">№ {{ ap.purchase_number }}</span>
              <span v-else>#{{ ap.purchase_id }}</span>
              <span v-if="ap.amount != null" class="ml-1">· {{ formatMoney(ap.amount) }}</span>
            </v-chip>
          </a>
        </div>
        <span v-else class="text-medium-emphasis">—</span>
      </template>

      <!-- Basis doc date -->
      <template #item.basis_doc_date="{ item }">
        <span class="text-caption">{{ fmtDate(item.basis_doc_date) }}</span>
      </template>

      <!-- Parsed contract date -->
      <template #item.parsed_contract_date="{ item }">
        <span class="text-caption">{{ fmtDate(item.parsed_contract_date) }}</span>
      </template>

      <!-- Created at -->
      <template #item.created_at="{ item }">
        <span class="text-caption">{{ fmtDate(item.created_at) }}</span>
      </template>

      <!-- Purpose text (wrap) -->
      <template #item.purpose_text="{ item }">
        <div class="text-caption" style="max-width:280px">
          {{ item.purpose_text || '—' }}
        </div>
      </template>

      <!-- Basis doc text (wrap) -->
      <template #item.basis_doc_text="{ item }">
        <div class="text-caption" style="max-width:220px">
          {{ item.basis_doc_text || '—' }}
        </div>
      </template>

      <!-- Actions -->
      <template #item.actions="{ item }">
        <div class="d-flex gap-1 align-center">
          <!-- Confirm button (only if matched) -->
          <v-btn
            v-if="can('payment.confirm')"
            icon
            size="x-small"
            variant="text"
            color="success"
            :disabled="!item.matched_contract_id"
            :title="item.matched_contract_id ? 'Подтвердить' : 'Сначала привяжите договор'"
            @click.stop="openConfirm(item)"
          >
            <v-icon>mdi-check</v-icon>
          </v-btn>

          <!-- Match/re-link button -->
          <v-btn
            icon
            size="x-small"
            variant="text"
            color="primary"
            title="Привязать договор"
            @click.stop="openMatch(item)"
          >
            <v-icon>mdi-link-variant</v-icon>
          </v-btn>

          <!-- Unbind button -->
          <v-btn
            v-if="can('payment.unbind') && item.matched_confirmed"
            icon
            size="x-small"
            variant="text"
            color="warning"
            title="Откатить подтверждение"
            :loading="unbindingId === item.id"
            @click.stop="unbind(item)"
          >
            <v-icon>mdi-undo</v-icon>
          </v-btn>
        </div>
      </template>

      <!-- Expanded row -->
      <template #expanded-row="{ columns, item }">
        <tr>
          <td :colspan="columns.length" class="pa-0">
            <div class="pa-3 bg-grey-lighten-5">
              <div class="d-flex flex-wrap gap-x-8 gap-y-1 text-body-2 mb-2">
                <span><b>Назначение платежа:</b> {{ item.purpose_text || '—' }}</span>
              </div>
              <div class="d-flex flex-wrap gap-x-8 gap-y-1 text-caption text-medium-emphasis">
                <span v-if="item.kbk"><b>КБК:</b> {{ item.kbk }}</span>
                <span v-if="item.payer_kpp"><b>КПП плательщика:</b> {{ item.payer_kpp }}</span>
                <span v-if="item.payee_kpp"><b>КПП получателя:</b> {{ item.payee_kpp }}</span>
              </div>
            </div>
          </td>
        </tr>
      </template>

      <!-- No data -->
      <template #no-data>
        <div class="text-center py-8 text-medium-emphasis">
          <v-icon size="48" class="mb-2">mdi-bank-outline</v-icon>
          <div>Платежи не найдены</div>
          <div class="text-caption">Измените параметры фильтра</div>
        </div>
      </template>
    </v-data-table>

    <!-- Cards view -->
    <div v-else>
      <v-row dense>
        <v-col v-for="item in prPaged" :key="item.id" cols="12" sm="6" md="4" lg="3">
          <v-card variant="outlined" class="h-100 d-flex flex-column" hover>
            <v-card-item class="pb-1">
              <v-card-title class="text-body-2 d-flex align-center ga-2 flex-wrap">
                <span class="font-weight-bold">{{ item.payment_number || ('#' + item.id) }}</span>
                <v-chip size="x-small" :color="statusColor(item.status)" variant="tonal">
                  {{ item.status || '—' }}
                </v-chip>
              </v-card-title>
            </v-card-item>
            <v-card-text class="py-1 flex-grow-1">
              <!-- Получатель -->
              <div class="text-caption text-medium-emphasis">Получатель</div>
              <div class="text-body-2 mb-1" style="overflow-wrap:anywhere">
                {{ item.payee_name_resolved || item.payee_name || '—' }}
              </div>
              <div v-if="item.payee_inn" class="text-caption text-medium-emphasis mb-2">ИНН {{ item.payee_inn }}</div>
              <!-- Сумма и дата -->
              <div class="d-flex flex-wrap ga-3 mt-1 mb-2">
                <div>
                  <div class="text-caption text-medium-emphasis">Сумма</div>
                  <div class="text-body-2 font-weight-bold">{{ formatMoney(item.amount) }}</div>
                </div>
                <div>
                  <div class="text-caption text-medium-emphasis">Дата</div>
                  <div class="text-body-2">{{ fmtDate(item.payment_date) }}</div>
                </div>
              </div>
              <!-- Договор (авто) -->
              <div v-if="docDisplay(item) !== '—'" class="text-caption text-medium-emphasis mb-1">
                {{ docDisplay(item) }}
              </div>
              <!-- Match badges -->
              <div class="d-flex flex-wrap ga-1 mt-1">
                <v-chip
                  v-if="item.matched_contract_id"
                  size="x-small" color="success" variant="tonal" prepend-icon="mdi-check"
                >Сматчен</v-chip>
                <v-chip v-else size="x-small" color="grey" variant="tonal">Не сматчен</v-chip>
                <v-chip
                  v-if="item.matched_confirmed"
                  size="x-small" color="blue" variant="tonal" prepend-icon="mdi-check-decagram"
                >Подтверждён</v-chip>
              </div>
            </v-card-text>
            <v-divider />
            <v-card-actions class="py-1" @click.stop>
              <v-spacer />
              <!-- Confirm button (only if matched) -->
              <v-btn
                v-if="can('payment.confirm')"
                icon
                size="x-small"
                variant="text"
                color="success"
                :disabled="!item.matched_contract_id"
                :title="item.matched_contract_id ? 'Подтвердить' : 'Сначала привяжите договор'"
                @click.stop="openConfirm(item)"
              >
                <v-icon>mdi-check</v-icon>
              </v-btn>
              <!-- Match/re-link button -->
              <v-btn
                icon
                size="x-small"
                variant="text"
                color="primary"
                title="Привязать договор"
                @click.stop="openMatch(item)"
              >
                <v-icon>mdi-link-variant</v-icon>
              </v-btn>
              <!-- Unbind button -->
              <v-btn
                v-if="can('payment.unbind') && item.matched_confirmed"
                icon
                size="x-small"
                variant="text"
                color="warning"
                title="Откатить подтверждение"
                :loading="unbindingId === item.id"
                @click.stop="unbind(item)"
              >
                <v-icon>mdi-undo</v-icon>
              </v-btn>
            </v-card-actions>
          </v-card>
        </v-col>
      </v-row>
      <div v-if="!prPaged.length" class="text-center py-10">
        <v-icon icon="mdi-bank-outline" size="48" color="grey-lighten-1" class="mb-3" />
        <div class="text-medium-emphasis">Платежи не найдены</div>
        <div class="text-caption">Измените параметры фильтра</div>
      </div>
      <v-pagination
        v-if="prCardsTotalPages > 1"
        v-model="prCardsPage"
        :length="prCardsTotalPages"
        density="compact"
        total-visible="7"
        class="d-flex justify-center mt-4"
      />
    </div>
    </div>

    <!-- Column picker dialog -->
    <ColumnConfigDialog
      v-model="showColumnPicker"
      :all-columns="allColumnsRef"
      :state="colConfigState"
      :show-width="true"
      :groups="[
        { key: 'core', label: `Основные (${coreColumnDefs.length})` },
        { key: 'file', label: `В этом файле (${rawColumns.length})` },
        { key: 'all', label: `Все возможные (${masterListLength})` },
      ]"
      :toggle-visible="toggleVisible"
      :set-position="setPosition"
      :set-width="setColWidth"
      :reset="resetColumns"
    />

    <!-- Match dialog -->
    <PaymentMatchDialog
      v-model="matchDialog"
      :bank-payment-id="selectedPaymentId"
      @updated="onUpdated"
    />

    <!-- Unbind confirm dialog -->
    <v-dialog v-model="unbindDialog" max-width="420">
      <v-card>
        <v-card-title>Откатить подтверждение?</v-card-title>
        <v-card-text>
          Платёжные записи, созданные при подтверждении, будут удалены. Статусы закупок пересчитаются автоматически.
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="unbindDialog = false">Отмена</v-btn>
          <v-btn color="warning" variant="elevated" :loading="unbindLoading" @click="doUnbind">Откатить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiFetch } from '@/api'
import { useToast } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'
import PaymentMatchDialog from '@/components/PaymentMatchDialog.vue'
import ColumnConfigDialog from '@/components/ColumnConfigDialog.vue'
import RegistryExportButton from '@/components/RegistryExportButton.vue'
import ColumnHeaderMenu from '@/components/ColumnHeaderMenu.vue'
import { useColumnConfig, type ColumnDef } from '@/composables/useColumnConfig'
import { SCROLLERHASH_MASTER_KEYS } from '@/constants/scrollerhash_columns'
import { formatMoney } from '@/utils/formatMoney'
import { useCardView } from '@/composables/useCardView'
import { useDisplay } from 'vuetify'

// ── Route & auth ───────────────────────────────────────────────────────────
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const { success, error } = useToast()

function can(action: string) {
  return authStore.hasAction?.(action) ?? true
}

// ── Import filter from query ────────────────────────────────────────────────
const importId = computed<number | null>(() => {
  const v = route.query.import_id
  return v ? Number(v) : null
})

function clearImport() {
  const q = { ...route.query }
  delete q.import_id
  router.replace({ query: q })
}

// ── Filter state ────────────────────────────────────────────────────────────
const fDateFrom = ref<string>('')
const fDateTo = ref<string>('')
const fStatus = ref<string | null>(null)
const fMatched = ref<string | null>(null)
const fConfirmed = ref<string | null>(null)
const fInn = ref<string>('')
// Этап 7в: «свободные / разнесённые» — разнесение через новое групповое
// сопоставление (app/services/payment_lookup.py::attach), не старая matched_*.
const fDisposition = ref<string | null>(null)
const dispositionOptions = [
  { label: 'Свободные (не разнесены)', value: 'free' },
  { label: 'Разнесённые', value: 'attached' },
]

const statusOptions = [
  { label: 'ИСПОЛНЕН', value: 'ИСПОЛНЕН' },
  { label: 'АННУЛИРОВАН', value: 'АННУЛИРОВАН' },
  { label: 'Прочие', value: 'OTHER' },
]
const yesNoOptions = [
  { label: 'Только сматченные', value: 'true' },
  { label: 'Только не сматченные', value: 'false' },
]

// ── Global search + subsidy filter ─────────────────────────────────────────
const searchQuery = ref('')
const filterSubsidyId = ref<number | null>(null)

interface SubsidyItem { id: number; name: string }
const subsidiesList = ref<SubsidyItem[]>([])

async function loadSubsidies() {
  try {
    const data = await apiFetch<any[]>('/subsidies/')
    subsidiesList.value = (data || []).map((s: any) => ({ id: s.id, name: s.name }))
  } catch {}
}

const searchedItems = computed(() => {
  let items = payments.value as any[]
  if (filterSubsidyId.value) {
    items = items.filter(i => i.matched_subsidy_id === filterSubsidyId.value)
  }
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.toLowerCase()
    items = items.filter((item: any) => {
      const haystack = [
        item.payer_name, item.payer_name_resolved, item.payer_inn,
        item.payee_name, item.payee_name_resolved, item.payee_inn,
        item.purpose_text, item.basis_doc_text, item.basis_doc_number,
        item.parsed_contract_number, item.payment_number, item.subsidy_code,
      ].filter(Boolean).join(' ').toLowerCase()
      return haystack.includes(q)
    })
  }
  // column-header filters
  if (colConfigState.value && Object.keys(colConfigState.value.filters).length > 0) {
    items = items.filter(matchesColumnFilters)
  }
  return items
})

const searchedItemsWithRowNum = computed(() => {
  // Нумерация по возрастанию id: более раннее (меньший id) = меньший _rownum
  const sorted = [...searchedItems.value].sort((a, b) => (Number(a.id) || 0) - (Number(b.id) || 0))
  const map = new Map<string, number>()
  sorted.forEach((p, idx) => map.set(String(p.id), idx + 1))
  let items = searchedItems.value.map(p => ({ ...p, _rownum: map.get(String(p.id)) ?? '' }))
  // Apply localSort from ColumnHeaderMenu
  if (localSort.value) {
    const { key, order } = localSort.value
    items = [...items].sort((a, b) => {
      const av = a?.[key] ?? null
      const bv = b?.[key] ?? null
      const cmp = String(av ?? '').localeCompare(String(bv ?? ''), 'ru', { numeric: true })
      return order === 'asc' ? cmp : -cmp
    })
  }
  return items
})

const filteredSum = computed(() =>
  searchedItems.value.reduce((acc, p) => acc + (p.amount ? Number(p.amount) : 0), 0)
)

const hasFilters = computed(() =>
  fDateFrom.value || fDateTo.value || fStatus.value || fMatched.value || fConfirmed.value || fInn.value ||
  fDisposition.value || activeFilterCount.value > 0
)

function clearFilters() {
  fDateFrom.value = ''
  fDateTo.value = ''
  fStatus.value = null
  fMatched.value = null
  fConfirmed.value = null
  fInn.value = ''
  fDisposition.value = null
  searchQuery.value = ''
  filterSubsidyId.value = null
  clearAllFilters()
  localSort.value = null
  applyFilters()
}

// ── Table state ─────────────────────────────────────────────────────────────
interface BankPayment {
  id: number
  import_id: number | null
  payment_date: string | null
  payment_number: string | null
  amount: number | null
  // Плательщик
  payer_name: string | null
  payer_name_resolved: string | null
  payer_inn: string | null
  payer_kpp: string | null
  payer_account: string | null
  payer_bank: string | null
  payer_bik: string | null
  // Получатель
  payee_name: string | null
  payee_name_resolved: string | null
  payee_inn: string | null
  payee_kpp: string | null
  payee_account: string | null
  payee_bank: string | null
  payee_bik: string | null
  // Парсинг
  parsed_contract_number: string | null
  parsed_contract_date: string | null
  parsed_kbk: string | null
  parsed_documents: Record<string, Array<{ number: string; date: string | null }>> | null
  status: string | null
  purpose_text: string | null
  basis_doc_text: string | null
  basis_doc_number: string | null
  basis_doc_date: string | null
  subsidy_code: string | null
  execution_datetime: string | null
  // raw_json (for raw_* columns)
  raw_json: Record<string, any> | null
  // Match
  matched_contract_id: number | null
  matched_contractor_id: number | null
  matched_purchase_id: number | null
  matched_subsidy_id: number | null
  matched_confirmed: boolean
  // 27.4-23: human-readable enriched поля для match-колонок
  matched_contractor_name: string | null
  matched_subsidy_name: string | null
  matched_contract_number: string | null
  matched_contract_subject: string | null
  matched_contract_date: string | null
  matched_purchase_number: number | null
  matched_purchase_item_name: string | null
  matched_purchase_amount: number | null
  created_at: string | null
  // Этап 7в
  expense_code: string | null
  expense_code_name: string | null
  attached_purchases: Array<{
    purchase_id: number
    purchase_number: number | null
    item_name: string | null
    amount: number | null
    basis_label: string | null
  }> | null
}

const payments = ref<BankPayment[]>([])
const loading = ref(false)
const registryArea = ref<HTMLElement | null>(null)
const totalCount = ref(0)
const page = ref(1)
const expanded = ref<number[]>([])

// Stale parsed detection: записи где parsed_contract_number совпадает с basis_doc_number (номер субсидии)
const staleParsedDismissed = ref(false)
const hasStaleParsed = computed(() =>
  !staleParsedDismissed.value &&
  payments.value.some(
    p => p.parsed_contract_number && p.basis_doc_number &&
      p.parsed_contract_number === p.basis_doc_number
  )
)

// ── Column picker ─────────────────────────────────────────────────────────────

// Map from key to column definition including width/sortable
const _colMetaDefaults: Record<string, { width?: number; sortable?: boolean }> = {
  index:                      { sortable: false, width: 50 },
  payment_number:              { width: 130 },
  payment_date:                { width: 100 },
  execution_datetime:          { width: 150 },
  // Плательщик
  payer_name:                  { sortable: false, width: 180 },
  payer_inn:                   { width: 130 },
  payer_kpp:                   { width: 110 },
  payer_account:               { width: 160 },
  payer_bank:                  { sortable: false, width: 180 },
  payer_bik:                   { width: 110 },
  // Получатель
  payee_name:                  { sortable: false, width: 180 },
  payee_inn:                   { width: 130 },
  payee_kpp:                   { width: 110 },
  payee_account:               { width: 160 },
  payee_bank:                  { sortable: false, width: 180 },
  payee_bik:                   { width: 110 },
  // Прочее
  amount:                      { width: 130 },
  status:                      { width: 130 },
  purpose_text:                { sortable: false, width: 280 },
  basis_doc_text:              { sortable: false, width: 220 },
  basis_doc_number:            { width: 160 },
  basis_doc_date:              { width: 130 },
  subsidy_code:                { width: 130 },
  parsed_contract_number:      { width: 200 },
  parsed_contract_date:        { width: 130 },
  parsed_kbk:                  { width: 120 },
  matched:                     { width: 90, sortable: false },
  matched_confirmed:           { width: 110, sortable: false },
  matched_contractor_id:       { width: 200, sortable: false },
  matched_contract_id:         { width: 240, sortable: false },
  matched_purchase_id:         { width: 240, sortable: false },
  matched_subsidy_id:          { width: 200, sortable: false },
  expense_code:                { width: 150 },
  attached_purchases:          { width: 220, sortable: false },
  created_at:                  { width: 150 },
  actions:                     { sortable: false, width: 110 },
  'data-table-expand':         { width: 48 },
}

// Core typed columns — все имеют backing-поля в модели BankPayment
const coreColumnDefs: ColumnDef[] = [
  // _rownum добавляется отдельно через tableHeaders computed (всегда первая колонка, не зависит от LS)
  { title: '', key: 'data-table-expand', group: 'core', ..._colMetaDefaults['data-table-expand'] },
  { title: '№', key: 'index', group: 'core', ..._colMetaDefaults['index'] },
  // Метаданные документа
  { title: 'Номер документа', key: 'payment_number', group: 'core', ..._colMetaDefaults['payment_number'] },
  { title: 'Дата документа', key: 'payment_date', group: 'core', ..._colMetaDefaults['payment_date'] },
  { title: 'Дата исполнения операции', key: 'execution_datetime', group: 'core', ..._colMetaDefaults['execution_datetime'] },
  { title: 'Статус документа', key: 'status', group: 'core', ..._colMetaDefaults['status'] },
  { title: 'Сумма', key: 'amount', group: 'core', ..._colMetaDefaults['amount'] },
  // Плательщик
  { title: 'ИНН плательщика', key: 'payer_inn', group: 'core', ..._colMetaDefaults['payer_inn'] },
  { title: 'КПП плательщика', key: 'payer_kpp', group: 'core', ..._colMetaDefaults['payer_kpp'] },
  { title: 'Плательщик', key: 'payer_name', group: 'core', ..._colMetaDefaults['payer_name'] },
  { title: 'Лицевой счёт плательщика', key: 'payer_account', group: 'core', ..._colMetaDefaults['payer_account'] },
  { title: 'Банк плательщика', key: 'payer_bank', group: 'core', ..._colMetaDefaults['payer_bank'] },
  { title: 'БИК плательщика', key: 'payer_bik', group: 'core', ..._colMetaDefaults['payer_bik'] },
  // Получатель
  { title: 'ИНН получателя', key: 'payee_inn', group: 'core', ..._colMetaDefaults['payee_inn'] },
  { title: 'КПП получателя', key: 'payee_kpp', group: 'core', ..._colMetaDefaults['payee_kpp'] },
  { title: 'Получатель', key: 'payee_name', group: 'core', ..._colMetaDefaults['payee_name'] },
  { title: 'Лицевой счёт получателя', key: 'payee_account', group: 'core', ..._colMetaDefaults['payee_account'] },
  { title: 'Банк получателя', key: 'payee_bank', group: 'core', ..._colMetaDefaults['payee_bank'] },
  { title: 'БИК получателя', key: 'payee_bik', group: 'core', ..._colMetaDefaults['payee_bik'] },
  // Назначение и парсинг
  { title: 'Назначение платежа', key: 'purpose_text', group: 'core', ..._colMetaDefaults['purpose_text'] },
  { title: 'Документ-основание (raw)', key: 'basis_doc_text', group: 'core', ..._colMetaDefaults['basis_doc_text'] },
  { title: '№ документа-основания', key: 'basis_doc_number', group: 'core', ..._colMetaDefaults['basis_doc_number'] },
  { title: 'Дата документа-основания', key: 'basis_doc_date', group: 'core', ..._colMetaDefaults['basis_doc_date'] },
  { title: 'Шифр субсидии', key: 'subsidy_code', group: 'core', ..._colMetaDefaults['subsidy_code'] },
  { title: 'Договор (авто)', key: 'parsed_contract_number', group: 'core', ..._colMetaDefaults['parsed_contract_number'] },
  { title: 'Дата договора (авто)', key: 'parsed_contract_date', group: 'core', ..._colMetaDefaults['parsed_contract_date'] },
  { title: 'КБК', key: 'parsed_kbk', group: 'core', ..._colMetaDefaults['parsed_kbk'] },
  // Этап 7в: код расходов (КРЦС) + куда фактически разнесён (новое групповое сопоставление)
  { title: 'Код расходов', key: 'expense_code', group: 'core', ..._colMetaDefaults['expense_code'] },
  { title: 'Куда отнесён', key: 'attached_purchases', group: 'core', ..._colMetaDefaults['attached_purchases'] },
  // Match
  { title: 'Match: Контрагент', key: 'matched_contractor_id', group: 'core', ..._colMetaDefaults['matched_contractor_id'] },
  { title: 'Match: Субсидия', key: 'matched_subsidy_id', group: 'core', ..._colMetaDefaults['matched_subsidy_id'] },
  { title: 'Match: Договор', key: 'matched_contract_id', group: 'core', ..._colMetaDefaults['matched_contract_id'] },
  { title: 'Match: Закупка', key: 'matched_purchase_id', group: 'core', ..._colMetaDefaults['matched_purchase_id'] },
  { title: 'Сматчен', key: 'matched', group: 'core', ..._colMetaDefaults['matched'] },
  { title: 'Подтверждён', key: 'matched_confirmed', group: 'core', ..._colMetaDefaults['matched_confirmed'] },
  // Audit
  { title: 'Создано', key: 'created_at', group: 'core', ..._colMetaDefaults['created_at'] },
  { title: 'Действия', key: 'actions', group: 'core', ..._colMetaDefaults['actions'] },
]

const showColumnPicker = ref(false)
const rawColumns = ref<{ key: string; count: number }[]>([])
const masterFilter = ref('')
const masterListLength = SCROLLERHASH_MASTER_KEYS.length

const filteredMaster = computed(() => {
  const q = masterFilter.value.trim().toLowerCase()
  return q
    ? SCROLLERHASH_MASTER_KEYS.filter(k => k.toLowerCase().includes(q))
    : SCROLLERHASH_MASTER_KEYS
})

async function loadRawColumns() {
  try {
    const importIdFilter = importId.value
    const url = importIdFilter
      ? `/payments/registry/raw-columns?import_id=${importIdFilter}`
      : '/payments/registry/raw-columns'
    rawColumns.value = await apiFetch<{ key: string; count: number }[]>(url)
  } catch {
    rawColumns.value = []
  }
}

watch(showColumnPicker, (open) => {
  if (open) loadRawColumns()
})

// allColumnsRef: core + file (raw_* from API) + all (master list), merged reactively
const allColumnsRef = computed<ColumnDef[]>(() => {
  const fileColumns: ColumnDef[] = rawColumns.value.map(rc => ({
    key: `raw_${rc.key}`,
    title: rc.key,
    group: 'file',
    width: 160,
    sortable: false,
  }))
  const allMasterColumns: ColumnDef[] = SCROLLERHASH_MASTER_KEYS.map(k => ({
    key: `raw_${k}`,
    title: k,
    group: 'all',
    width: 160,
    sortable: false,
  }))
  // Deduplicate: file columns override all-master entries with same key
  const fileKeys = new Set(fileColumns.map(c => c.key))
  const dedupedMaster = allMasterColumns.filter(c => !fileKeys.has(c.key))
  return [...coreColumnDefs, ...fileColumns, ...dedupedMaster]
})

const {
  state: colConfigState,
  visibleHeaders: visibleColumnHeaders,
  toggleVisible,
  setPosition,
  setWidth: setColWidth,
  reset: resetColumns,
  migrateFrom,
  setFilter,
  clearAllFilters,
  activeFilterCount,
} = useColumnConfig('payment_registry', allColumnsRef)

const activeHeaders = computed(() =>
  visibleColumnHeaders.value.map(col => {
    // raw_* колонки — данные из raw_json
    if (col.key.startsWith('raw_')) {
      const rawKey = col.key.slice(4)
      const w = colConfigState.value.widths[col.key] ?? col.width ?? 160
      return {
        title: col.title,
        key: col.key,
        value: (item: any) => item.raw_json?.[rawKey] ?? '—',
        sortable: false,
        width: w ? `${w}px` : undefined,
      }
    }
    const w = colConfigState.value.widths[col.key] ?? col.width
    return {
      title: col.title,
      key: col.key,
      sortable: col.sortable,
      width: w ? `${w}px` : undefined,
    }
  })
)

// ── Load data ───────────────────────────────────────────────────────────────
async function loadPayments() {
  loading.value = true
  try {
    const params = new URLSearchParams({ limit: '200' })
    if (fDateFrom.value) params.set('date_from', fDateFrom.value)
    if (fDateTo.value) params.set('date_to', fDateTo.value)
    if (fStatus.value) params.set('status', fStatus.value)
    if (fMatched.value !== null && fMatched.value !== '') params.set('matched', fMatched.value)
    if (fConfirmed.value !== null && fConfirmed.value !== '') params.set('confirmed', fConfirmed.value)
    if (fInn.value) params.set('payee_inn', fInn.value)
    if (fDisposition.value) params.set('disposition', fDisposition.value)
    if (importId.value) params.set('import_id', String(importId.value))

    const data = await apiFetch<any>(`/payments/registry?${params}`)
    const raw: BankPayment[] = Array.isArray(data) ? data : (data as any).items ?? []
    payments.value = raw
    totalCount.value = (data as any).total ?? raw.length
  } catch (e: any) {
    error('Не удалось загрузить реестр: ' + (e.detail || ''))
  } finally {
    loading.value = false
  }
}

function applyFilters() {
  page.value = 1
  loadPayments()
}

// _rownum — всегда первая колонка, не зависит от useColumnConfig состояния
const tableHeaders = computed(() => [
  { title: '№ п/п', key: '_rownum', width: 60, sortable: false },
  ...activeHeaders.value,
])

// ── ColumnHeaderMenu helpers ─────────────────────────────────────────────────
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
  const filters = colConfigState.value.filters
  for (const [k, f] of Object.entries(filters)) {
    // matched — derived from matched_contract_id
    let v: any
    if (k === 'matched') {
      v = Boolean(row?.matched_contract_id)
    } else if (k.startsWith('raw_')) {
      v = row?.raw_json?.[k.slice(4)] ?? null
    } else {
      v = row?.[k] ?? null
    }
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

// ── Watch import_id changes in URL ──────────────────────────────────────────
watch(importId, () => {
  applyFilters()
})

// ── Match dialog ─────────────────────────────────────────────────────────────
const matchDialog = ref(false)
const selectedPaymentId = ref<number | null>(null)

function openMatch(item: BankPayment) {
  selectedPaymentId.value = item.id
  matchDialog.value = true
}

function openConfirm(item: BankPayment) {
  // Open match dialog with pre-loaded contract for confirmation flow
  selectedPaymentId.value = item.id
  matchDialog.value = true
}

function onUpdated() {
  loadPayments()
  // 27.4-22: если диалог сверки открыт — перезагружаем счётчики/строки
  if (reconciliationDialog.value) openReconciliation()
}

// ── Unbind ───────────────────────────────────────────────────────────────────
const unbindDialog = ref(false)
const unbindingId = ref<number | null>(null)
const unbindLoading = ref(false)

function unbind(item: BankPayment) {
  unbindingId.value = item.id
  unbindDialog.value = true
}

async function doUnbind() {
  if (!unbindingId.value) return
  unbindLoading.value = true
  try {
    await apiFetch(`/payments/registry/${unbindingId.value}/unbind`, { method: 'POST' })
    success('Подтверждение откатено')
    unbindDialog.value = false
    loadPayments()
  } catch (e: any) {
    error('Ошибка при откате: ' + (e.detail || ''))
  } finally {
    unbindLoading.value = false
    unbindingId.value = null
  }
}

// ── Doc display: тип + номер ──────────────────────────────────────────────────
// Соглашение убрано — оно в 100% платежей через basis_doc, неинформативно в этой колонке.
function docDisplay(item: any): string {
  const pd = item.parsed_documents || {}
  if (pd.contracts?.[0]) return `Договор ${pd.contracts[0].number}`
  if (pd.advance_reports?.[0]) return `Авансовый отчёт ${pd.advance_reports[0].number}`
  if (pd.acts?.[0]) return `Акт ${pd.acts[0].number}`
  if (pd.upd?.[0]) return `УПД ${pd.upd[0].number}`
  if (pd.invoices?.[0]) return `Счёт ${pd.invoices[0].number}`
  if (pd.ttn?.[0]) return `ТТН ${pd.ttn[0].number}`
  if (pd.registry?.[0]) return `Реестр ${pd.registry[0].number}`
  if (item.parsed_contract_number) return `Договор ${item.parsed_contract_number}`
  return '—'
}

// ── Helpers ──────────────────────────────────────────────────────────────────
function fmtDate(d: string | null) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('ru-RU')
}

function formatMoney(v: number | null | undefined) {
  if (v == null) return '—'
  return new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 2 }).format(v)
}

// 27.4-21: Reconciliation state + helpers
const reconciliationDialog = ref(false)
const reconciliationLoading = ref(false)
const reconciliation = ref<any>(null)
// 27.4-22: filter + per-row action
const reconciliationFilter = ref('')

const filteredReconciliationRows = computed(() => {
  const rows = reconciliation.value?.rows || []
  const q = reconciliationFilter.value.trim().toLowerCase()
  if (!q) return rows
  return rows.filter((r: any) =>
    (r.payment_number || '').toLowerCase().includes(q) ||
    (r.registry_payees || []).some((p: string) => p.toLowerCase().includes(q)) ||
    reconciliationStatusLabel(r.status).toLowerCase().includes(q)
  )
})

async function openReconciliation() {
  reconciliationDialog.value = true
  reconciliationLoading.value = true
  reconciliation.value = null
  reconciliationFilter.value = ''
  try {
    const url = importId.value
      ? `/payments/reconciliation?import_id=${importId.value}`
      : '/payments/reconciliation'
    reconciliation.value = await apiFetch<any>(url)
  } catch (e: any) {
    error('Ошибка сверки: ' + (e?.payload?.message || e?.message || ''))
  } finally {
    reconciliationLoading.value = false
  }
}

function openMatchFromReconciliation(bpId: number) {
  // Открываем PaymentMatchDialog поверх сверки (диалог-над-диалогом OK)
  selectedPaymentId.value = bpId
  matchDialog.value = true
}

function reconciliationRowClass(status: string): string {
  if (status === 'amount_mismatch' || status === 'registry_only') return 'bg-red-lighten-5'
  if (status === 'purchases_only' || status === 'declared_unconfirmed') return 'bg-amber-lighten-5'
  return ''
}

function reconciliationStatusColor(status: string): string {
  if (status === 'match') return 'success'
  if (status === 'amount_mismatch') return 'error'
  if (status === 'registry_only') return 'error'
  if (status === 'purchases_only') return 'warning'
  if (status === 'declared_unconfirmed') return 'orange'
  return 'grey'
}

function reconciliationStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    match: 'OK',
    amount_mismatch: 'Расхождение сумм',
    registry_only: 'Только в реестре',
    purchases_only: 'Только в закупках',
    declared_unconfirmed: 'Заявлено, не подтверждено',
  }
  return labels[status] || status
}

function statusColor(s: string | null) {
  if (!s) return 'grey'
  if (s === 'ИСПОЛНЕН') return 'success'
  if (s === 'АННУЛИРОВАН') return 'error'
  return 'warning'
}

const { mobile } = useDisplay()

// ── Card view (table↔cards toggle) ───────────────────────────────────────────
const {
  mobile: prMobile,
  viewMode: prViewMode,
  effectiveView: prEffectiveView,
  page: prCardsPage,
  totalPages: prCardsTotalPages,
  paged: prPaged,
} = useCardView({
  storageKey: 'payment_registry_view_mode',
  // source returns already-filtered + sorted list (searchedItemsWithRowNum)
  source: () => searchedItemsWithRowNum.value,
})

// ── Init ──────────────────────────────────────────────────────────────────────
onMounted(() => {
  // Мигрируем старые LS ключи в новый формат (один раз, потом игнорируется)
  migrateFrom({ visible: 'payment_registry_columns', widths: 'payment_registry_col_widths' })
  loadPayments()
  loadSubsidies()
})
</script>

<style scoped>
/* Phase 22.5: перенос текста в ячейках таблицы */
:deep(.v-data-table td) {
  white-space: normal !important;
  word-break: break-word;
  vertical-align: top;
  padding-top: 8px;
  padding-bottom: 8px;
}
</style>
