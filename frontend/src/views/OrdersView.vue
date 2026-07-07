<template>
  <v-container fluid class="pa-6">
    <!-- Header -->
    <div class="d-flex align-center justify-space-between mb-6">
      <div>
        <h1 class="text-h5 font-weight-bold">Закупки</h1>
        <span class="text-body-2 text-medium-emphasis">{{ orders.length }} записей</span>
      </div>
      <div class="d-flex gap-2">
        <v-btn variant="outlined" size="small" prepend-icon="mdi-download" @click="downloadTemplate">Шаблон</v-btn>
        <v-btn variant="outlined" prepend-icon="mdi-file-import" color="blue" @click="importDialog.show = true">Импорт</v-btn>
        <v-btn variant="outlined" prepend-icon="mdi-file-export" color="success" @click="openExportDialog">Excel</v-btn>
        <v-btn color="primary" prepend-icon="mdi-plus" to="/create-order">Добавить</v-btn>
      </div>
    </div>

    <!-- Filters -->
    <v-card class="mb-4" variant="outlined">
      <v-card-text class="py-3">
        <div class="d-flex align-center gap-4 flex-wrap">
          <v-select
            v-model="filterSubsidyId"
            :items="subsidies"
            item-title="name"
            item-value="id"
            label="Субсидия"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            style="min-width:220px"
          />
          <v-select
            v-model="filterStatus"
            :items="statusItems"
            item-title="label"
            item-value="value"
            label="Статус"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            style="min-width:170px"
          />
          <v-text-field
            v-model="search"
            prepend-inner-icon="mdi-magnify"
            label="Поиск"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            style="min-width:200px"
          />
          <v-select
            v-model="filterTypes"
            :items="orderTypeOptions"
            item-title="label"
            item-value="value"
            label="Тип договора"
            variant="outlined"
            density="compact"
            multiple
            chips
            closable-chips
            clearable
            hide-details
            style="min-width:220px"
          />
          <v-autocomplete
            v-model="filterContractorIds"
            :items="contractorsForFilter"
            item-title="name"
            item-value="id"
            label="Контрагент"
            variant="outlined"
            density="compact"
            multiple
            chips
            closable-chips
            clearable
            hide-details
            style="min-width:220px"
          />
          <v-text-field
            v-model="fProduct"
            label="Поиск товара"
            prepend-inner-icon="mdi-magnify"
            variant="outlined" density="compact" hide-details clearable
            placeholder="Название товара..."
            style="min-width:200px; max-width:240px"
          />
          <v-btn
            size="small" variant="tonal" color="primary"
            prepend-icon="mdi-bookmark-plus-outline"
            @click="saveFilterPreset">
            Сохранить фильтр
          </v-btn>
          <v-btn variant="tonal" prepend-icon="mdi-view-column" size="small" @click="showColumnPicker = true">Колонки</v-btn>
          <!-- Phase 31-06: filter by unseen changes -->
          <v-checkbox
            v-model="filterOnlyUnseen"
            label="Только с чужими правками"
            density="compact"
            hide-details
            color="#fb923c"
            class="ml-1"
            style="min-width:fit-content"
          />
          <v-btn-toggle v-if="!mobile" v-model="viewMode" mandatory density="compact" variant="outlined" divided class="ml-1">
            <v-btn value="table" size="small" icon="mdi-table" />
            <v-btn value="cards" size="small" icon="mdi-view-grid" />
          </v-btn-toggle>
          <v-chip
            v-if="activeFilterCount > 0"
            color="deep-orange" variant="tonal" size="small"
            prepend-icon="mdi-filter-multiple"
            class="ml-1"
            closable
            @click:close="clearAllFilters()"
          >
            Фильтры {{ activeFilterCount }}
          </v-chip>
          <v-chip color="primary" variant="tonal" prepend-icon="mdi-cash-multiple" size="small" class="ml-2">
            Сумма: {{ formatMoney(filteredSum) }}
          </v-chip>
        </div>
        <!-- Saved filter preset chips -->
        <div v-if="savedFilterPresets.length" class="d-flex align-center gap-2 flex-wrap mt-2">
          <span class="text-caption text-medium-emphasis">Пресеты:</span>
          <v-chip
            v-for="p in savedFilterPresets" :key="p.name"
            size="small" variant="tonal" color="primary"
            class="cursor-pointer"
            @click="applyFilterPreset(p)">
            {{ p.name }}
            <v-icon icon="mdi-close" size="12" class="ml-1" @click.stop="removeFilterPreset(p.name)" />
          </v-chip>
        </div>
      </v-card-text>
    </v-card>

    <!-- Status tab chips -->
    <v-chip-group v-model="filterStatus" class="mb-4">
      <v-chip value="" variant="outlined" filter>Все</v-chip>
      <v-chip
        v-for="s in statusItems"
        :key="s.value"
        :value="s.value"
        :color="s.color"
        filter
        variant="outlined"
      >
        {{ s.label }}
      </v-chip>
    </v-chip-group>

    <!-- FEO category filter badge -->
    <v-chip v-if="filterFeoCategoryId" color="teal" variant="tonal" closable class="mb-3" prepend-icon="mdi-filter"
      @click:close="filterFeoCategoryId = null; filterFeoCategoryName = ''">
      ФЭО: {{ filterFeoCategoryName }}
    </v-chip>

    <!-- Bulk actions bar -->
    <div v-if="selectedOrders.length > 0" class="d-flex align-center gap-3 mb-3 pa-3 bg-blue-lighten-5 rounded-lg">
      <v-icon icon="mdi-checkbox-marked-outline" color="primary" />
      <span class="text-body-2 font-weight-medium">Выбрано: {{ selectedOrders.length }}</span>
      <v-menu>
        <template v-slot:activator="{ props }">
          <v-btn v-bind="props" size="small" variant="tonal" color="blue" prepend-icon="mdi-swap-horizontal">
            Сменить статус
          </v-btn>
        </template>
        <v-list density="compact">
          <v-list-item
            v-for="s in statusItems" :key="s.value"
            :title="s.label"
            :prepend-icon="'mdi-circle-small'"
            @click="bulkChangeStatus(s.value)"
          />
        </v-list>
      </v-menu>
      <v-spacer />
      <v-btn v-if="isAdmin" color="error" variant="tonal" size="small" prepend-icon="mdi-delete" @click="confirmBulkDelete">
        Удалить выбранные
      </v-btn>
      <v-btn variant="text" size="small" @click="selectedOrders = []">Снять выделение</v-btn>
    </div>

    <!-- Link task banner -->
    <v-alert v-if="linkTaskId" type="info" variant="tonal" closable class="mb-3"
      @click:close="linkTaskId = null; $router.replace({ query: {} })">
      <div class="d-flex align-center ga-2">
        <v-icon>mdi-link-variant</v-icon>
        <span>Выберите закупку для привязки к задаче <b>#{{ linkTaskId }}</b></span>
        <v-btn size="small" variant="text" @click="linkTaskId = null; $router.replace({ query: {} })">Отмена</v-btn>
      </div>
    </v-alert>

    <!-- Table / Cards toggle -->
    <v-data-table
        v-if="effectiveView === 'table'"
        v-resizable-columns="'orders'"
        ref="ordersTableRef"
        :headers="tableHeaders"
        :items="filteredOrdersWithRowNum"
        :loading="loading"
        :search="search"
        density="compact"
        hover
        show-expand
        show-select
        v-model="selectedOrders"
        v-model:expanded="expanded"
        items-per-page="25"
        :items-per-page-options="[25, 50, 100]"
        return-object
        class="orders-clickable"
        @click:row="(_, { item }) => router.push(`/orders/${item.id}/edit`)"
      >
        <!-- Column header menus -->
        <template #header.registry_number="{ column }">
          <ColumnHeaderMenu col-key="registry_number" :title="column.title" col-type="text"
            :model-value="cfg.state.value.filters['registry_number'] ?? null"
            :sort-by="getSortBy('registry_number')"
            @update:model-value="v => cfg.setFilter('registry_number', v)"
            @sort="dir => applySort('registry_number', dir)"
            @hide="toggleVisible('registry_number', false)" />
        </template>
        <template #header.subject="{ column }">
          <ColumnHeaderMenu col-key="subject" :title="column.title" col-type="text"
            :model-value="cfg.state.value.filters['subject'] ?? null"
            :sort-by="getSortBy('subject')"
            @update:model-value="v => cfg.setFilter('subject', v)"
            @sort="dir => applySort('subject', dir)"
            @hide="toggleVisible('subject', false)" />
        </template>
        <template #header.contractor_name="{ column }">
          <ColumnHeaderMenu col-key="contractor_name" :title="column.title" col-type="enum"
            :items="uniqValues(filteredOrders, 'contractor_name')"
            :model-value="cfg.state.value.filters['contractor_name'] ?? null"
            :sort-by="getSortBy('contractor_name')"
            @update:model-value="v => cfg.setFilter('contractor_name', v)"
            @sort="dir => applySort('contractor_name', dir)"
            @hide="toggleVisible('contractor_name', false)" />
        </template>
        <template #header.subsidy_name="{ column }">
          <ColumnHeaderMenu col-key="subsidy_name" :title="column.title" col-type="enum"
            :items="uniqValues(filteredOrders, 'subsidy_name')"
            :model-value="cfg.state.value.filters['subsidy_name'] ?? null"
            :sort-by="getSortBy('subsidy_name')"
            @update:model-value="v => cfg.setFilter('subsidy_name', v)"
            @sort="dir => applySort('subsidy_name', dir)"
            @hide="toggleVisible('subsidy_name', false)" />
        </template>
        <template #header.effective_price="{ column }">
          <ColumnHeaderMenu col-key="effective_price" :title="column.title" col-type="number"
            align="end"
            :model-value="cfg.state.value.filters['effective_price'] ?? null"
            :sort-by="getSortBy('effective_price')"
            @update:model-value="v => cfg.setFilter('effective_price', v)"
            @sort="dir => applySort('effective_price', dir)"
            @hide="toggleVisible('effective_price', false)" />
        </template>
        <template #header.contract_number="{ column }">
          <ColumnHeaderMenu col-key="contract_number" :title="column.title" col-type="text"
            :model-value="cfg.state.value.filters['contract_number'] ?? null"
            :sort-by="getSortBy('contract_number')"
            @update:model-value="v => cfg.setFilter('contract_number', v)"
            @sort="dir => applySort('contract_number', dir)"
            @hide="toggleVisible('contract_number', false)" />
        </template>
        <template #header.contract_date="{ column }">
          <ColumnHeaderMenu col-key="contract_date" :title="column.title" col-type="date"
            :model-value="cfg.state.value.filters['contract_date'] ?? null"
            :sort-by="getSortBy('contract_date')"
            @update:model-value="v => cfg.setFilter('contract_date', v)"
            @sort="dir => applySort('contract_date', dir)"
            @hide="toggleVisible('contract_date', false)" />
        </template>
        <template #header.purchase_type="{ column }">
          <ColumnHeaderMenu col-key="purchase_type" :title="column.title" col-type="enum"
            :items="['one_time', 'framework_cumulative', 'framework_with_amount', 'advance', 'invoice']"
            :item-labels="{ one_time: 'Разовый', framework_cumulative: 'Рамочный (накопительный)', framework_with_amount: 'Рамочный (с суммой)', advance: 'Авансовый', invoice: 'По счёту' }"
            :model-value="cfg.state.value.filters['purchase_type'] ?? null"
            :sort-by="getSortBy('purchase_type')"
            @update:model-value="v => cfg.setFilter('purchase_type', v)"
            @sort="dir => applySort('purchase_type', dir)"
            @hide="toggleVisible('purchase_type', false)" />
        </template>
        <template #header.status="{ column }">
          <ColumnHeaderMenu col-key="status" :title="column.title" col-type="enum"
            :items="STATUS_ORDER"
            :item-labels="STATUS_LABEL"
            :model-value="cfg.state.value.filters['status'] ?? null"
            :sort-by="getSortBy('status')"
            @update:model-value="v => cfg.setFilter('status', v)"
            @sort="dir => applySort('status', dir)"
            @hide="toggleVisible('status', false)" />
        </template>
        <template #header.approval_status="{ column }">
          <ColumnHeaderMenu col-key="approval_status" :title="column.title" col-type="enum"
            :items="['in_progress', 'approved', 'rejected']"
            :item-labels="{ in_progress: 'На согласовании', approved: 'Согласовано', rejected: 'Отклонено' }"
            :model-value="cfg.state.value.filters['approval_status'] ?? null"
            :sort-by="getSortBy('approval_status')"
            @update:model-value="v => cfg.setFilter('approval_status', v)"
            @sort="dir => applySort('approval_status', dir)"
            @hide="toggleVisible('approval_status', false)" />
        </template>
        <!-- Phase 26-K: доп. соглашение и дата заказа -->
        <template #header.agreement_number="{ column }">
          <ColumnHeaderMenu col-key="agreement_number" :title="column.title" col-type="text"
            :model-value="cfg.state.value.filters['agreement_number'] ?? null"
            :sort-by="getSortBy('agreement_number')"
            @update:model-value="v => cfg.setFilter('agreement_number', v)"
            @sort="dir => applySort('agreement_number', dir)"
            @hide="toggleVisible('agreement_number', false)" />
        </template>
        <template #header.agreement_date="{ column }">
          <ColumnHeaderMenu col-key="agreement_date" :title="column.title" col-type="date"
            :model-value="cfg.state.value.filters['agreement_date'] ?? null"
            :sort-by="getSortBy('agreement_date')"
            @update:model-value="v => cfg.setFilter('agreement_date', v)"
            @sort="dir => applySort('agreement_date', dir)"
            @hide="toggleVisible('agreement_date', false)" />
        </template>
        <template #header.order_number="{ column }">
          <ColumnHeaderMenu col-key="order_number" :title="column.title" col-type="text"
            :model-value="cfg.state.value.filters['order_number'] ?? null"
            :sort-by="getSortBy('order_number')"
            @update:model-value="v => cfg.setFilter('order_number', v)"
            @sort="dir => applySort('order_number', dir)"
            @hide="toggleVisible('order_number', false)" />
        </template>
        <template #header.order_date="{ column }">
          <ColumnHeaderMenu col-key="order_date" :title="column.title" col-type="date"
            :model-value="cfg.state.value.filters['order_date'] ?? null"
            :sort-by="getSortBy('order_date')"
            @update:model-value="v => cfg.setFilter('order_date', v)"
            @sort="dir => applySort('order_date', dir)"
            @hide="toggleVisible('order_date', false)" />
        </template>
        <!-- Phase 26-N: денежные показатели по закупке -->
        <template #header.ordered_amount="{ column }">
          <ColumnHeaderMenu col-key="ordered_amount" :title="column.title" col-type="number"
            :model-value="cfg.state.value.filters['ordered_amount'] ?? null"
            :sort-by="getSortBy('ordered_amount')"
            @update:model-value="v => cfg.setFilter('ordered_amount', v)"
            @sort="dir => applySort('ordered_amount', dir)"
            @hide="toggleVisible('ordered_amount', false)" />
        </template>
        <template #header.delivered_amount="{ column }">
          <ColumnHeaderMenu col-key="delivered_amount" :title="column.title" col-type="number"
            :model-value="cfg.state.value.filters['delivered_amount'] ?? null"
            :sort-by="getSortBy('delivered_amount')"
            @update:model-value="v => cfg.setFilter('delivered_amount', v)"
            @sort="dir => applySort('delivered_amount', dir)"
            @hide="toggleVisible('delivered_amount', false)" />
        </template>
        <template #header.paid_amount="{ column }">
          <ColumnHeaderMenu col-key="paid_amount" :title="column.title" col-type="number"
            :model-value="cfg.state.value.filters['paid_amount'] ?? null"
            :sort-by="getSortBy('paid_amount')"
            @update:model-value="v => cfg.setFilter('paid_amount', v)"
            @sort="dir => applySort('paid_amount', dir)"
            @hide="toggleVisible('paid_amount', false)" />
        </template>
        <template #header.diff_ordered_delivered="{ column }">
          <ColumnHeaderMenu col-key="diff_ordered_delivered" :title="column.title" col-type="number"
            :model-value="cfg.state.value.filters['diff_ordered_delivered'] ?? null"
            :sort-by="getSortBy('diff_ordered_delivered')"
            @update:model-value="v => cfg.setFilter('diff_ordered_delivered', v)"
            @sort="dir => applySort('diff_ordered_delivered', dir)"
            @hide="toggleVisible('diff_ordered_delivered', false)" />
        </template>
        <template #header.diff_delivered_paid="{ column }">
          <ColumnHeaderMenu col-key="diff_delivered_paid" :title="column.title" col-type="number"
            :model-value="cfg.state.value.filters['diff_delivered_paid'] ?? null"
            :sort-by="getSortBy('diff_delivered_paid')"
            @update:model-value="v => cfg.setFilter('diff_delivered_paid', v)"
            @sort="dir => applySort('diff_delivered_paid', dir)"
            @hide="toggleVisible('diff_delivered_paid', false)" />
        </template>
        <template #header.diff_ordered_paid="{ column }">
          <ColumnHeaderMenu col-key="diff_ordered_paid" :title="column.title" col-type="number"
            :model-value="cfg.state.value.filters['diff_ordered_paid'] ?? null"
            :sort-by="getSortBy('diff_ordered_paid')"
            @update:model-value="v => cfg.setFilter('diff_ordered_paid', v)"
            @sort="dir => applySort('diff_ordered_paid', dir)"
            @hide="toggleVisible('diff_ordered_paid', false)" />
        </template>

        <!-- Expand toggle column -->
        <template #item.data-table-expand="{ item, internalItem, isExpanded, toggleExpand }">
          <v-btn
            v-if="item.items && item.items.length > 0"
            :icon="isExpanded(internalItem) ? 'mdi-chevron-up' : 'mdi-chevron-down'"
            variant="text"
            size="small"
            @click.stop="toggleExpand(internalItem)"
          />
        </template>

        <!-- Предмет договора -->
        <template #item.subject="{ item }">
          <div class="d-flex align-center flex-wrap" style="gap:6px">
            <span>{{ item.subject || item.item_name || '—' }}</span>
            <!-- Phase 31-06: badge for unseen changes -->
            <v-chip
              v-if="item.unseen_changes_count > 0"
              size="x-small"
              variant="tonal"
              color="#fb923c"
              :title="`${item.unseen_changes_count} чужих правок с последнего просмотра`"
            >+{{ item.unseen_changes_count }}</v-chip>
          </div>
          <div v-if="!item.contractor_name || !item.feo_category_id || !item.execution_term || !(item.planned_total_price)" class="d-flex flex-wrap ga-1 mt-1">
            <v-chip v-if="!item.contractor_name" size="x-small" color="error" variant="tonal" prepend-icon="mdi-domain-off">Контрагент</v-chip>
            <v-chip v-if="!item.feo_category_id" size="x-small" color="warning" variant="tonal" prepend-icon="mdi-tag-off">ФЭО</v-chip>
            <v-chip v-if="!item.execution_term" size="x-small" color="warning" variant="tonal" prepend-icon="mdi-calendar-alert">Срок</v-chip>
            <v-chip v-if="!item.planned_total_price" size="x-small" color="warning" variant="tonal" prepend-icon="mdi-currency-rub">Сумма</v-chip>
          </div>
        </template>

        <!-- Display name (first item or legacy item_name) -->
        <template #item.display_name="{ item }">
          <span class="text-body-2">{{ itemDisplayName(item) }}</span>
        </template>

        <!-- Тип закупки -->
        <template #item.purchase_type="{ item }">
          <v-chip :color="purchaseTypeColor(item)" size="x-small" variant="tonal">
            {{ purchaseTypeLabel(item) }}
          </v-chip>
        </template>

        <!-- Способ закупки (локализованный) -->
        <template #item.purchase_method="{ item }">
          <span class="text-caption">{{ purchaseMethodLabel(item.purchase_method) }}</span>
        </template>

        <!-- Кому возмещать (фиолетовый chip, единый стиль) -->
        <template #item.reimbursement_user_name="{ item }">
          <v-chip v-if="item.reimbursement_user_name" size="x-small" color="purple" variant="tonal" prepend-icon="mdi-account">
            {{ item.reimbursement_user_name }}
          </v-chip>
          <span v-else class="text-medium-emphasis">—</span>
        </template>

        <!-- Контрагент (поставщик/продавец). Phase 26-nnn:
             Для авансовых раньше показывали reimbursement_user_name (получателя
             возмещения) — это ПУТАНИЦА. Контрагент = продавец/поставщик; кому
             возмещать = отдельная колонка key='reimbursement_user_name'.
             Multi-contractor label остаётся (если у items[] несколько продавцов
             из разных чеков). Без chip-обёртки — обычный текст переносится по
             глобальному CSS overflow-wrap: anywhere. -->
        <template #item.contractor_name="{ item }">
          <span v-if="(item as any).multi_contractor_label === 'Множественный контрагент'"
                class="text-body-2" style="color: var(--v-theme-warning, #f57c00)">
            {{ (item as any).multi_contractor_label }}
          </span>
          <span v-else class="text-body-2">
            {{ item.contractor_name || '—' }}
          </span>
        </template>

        <template #item.status="{ item }">
          <div class="d-flex align-center ga-1 flex-wrap">
            <v-chip :color="STATUS_COLOR[item.status] || 'grey'" size="small" variant="tonal">
              {{ statusLabelFor(item) }}
            </v-chip>
            <v-chip v-if="item.substatus" size="x-small" variant="outlined" color="teal">
              {{ SUBSTATUS_LABEL[item.substatus] || item.substatus }}
            </v-chip>
            <v-icon v-if="item.is_monthly_payment" size="x-small" color="blue" title="Ежемесячный платёж">mdi-calendar-sync</v-icon>
          </div>
        </template>

        <template #item.effective_price="{ item }">
          {{ formatMoney(effectivePrice(item)) }}
        </template>

        <!-- phase26-m: для рамочного — framework_contract_total (max_amount or SUM) -->
        <template #item.contract_price="{ item }">
          {{ formatMoney(FIELD_GETTERS.contract_price(item)) }}
        </template>

        <!-- Phase 26-N: денежные показатели по закупке -->
        <template #item.ordered_amount="{ item }">
          {{ FIELD_GETTERS.ordered_amount(item) != null ? formatMoney(FIELD_GETTERS.ordered_amount(item)) : '—' }}
        </template>
        <template #item.delivered_amount="{ item }">
          {{ FIELD_GETTERS.delivered_amount(item) != null ? formatMoney(FIELD_GETTERS.delivered_amount(item)) : '—' }}
        </template>
        <template #item.paid_amount="{ item }">
          {{ FIELD_GETTERS.paid_amount(item) != null ? formatMoney(FIELD_GETTERS.paid_amount(item)) : '—' }}
        </template>
        <template #item.diff_ordered_delivered="{ item }">
          {{ FIELD_GETTERS.diff_ordered_delivered(item) != null ? formatMoney(FIELD_GETTERS.diff_ordered_delivered(item)) : '—' }}
        </template>
        <template #item.diff_delivered_paid="{ item }">
          {{ FIELD_GETTERS.diff_delivered_paid(item) != null ? formatMoney(FIELD_GETTERS.diff_delivered_paid(item)) : '—' }}
        </template>
        <template #item.diff_ordered_paid="{ item }">
          {{ FIELD_GETTERS.diff_ordered_paid(item) != null ? formatMoney(FIELD_GETTERS.diff_ordered_paid(item)) : '—' }}
        </template>

        <template #item.contract_date="{ item }">
          {{ item.contract_date ? formatDate(item.contract_date) : '—' }}
        </template>

        <template #item.subsidy_name="{ item }">
          <span class="text-body-2">
            {{ item.subsidy_name || '—' }}
          </span>
        </template>

        <template #item.approval_status="{ item }">
          <v-chip v-if="item.approval_status" :color="APPROVAL_STATUS_COLOR[item.approval_status]" size="x-small" variant="tonal"
                  style="white-space: normal; height: auto; min-height: 22px; padding: 2px 8px;">
            {{ APPROVAL_STATUS_LABEL[item.approval_status] }}
          </v-chip>
          <span v-else class="text-caption text-medium-emphasis">—</span>
        </template>

        <template #item.actions="{ item }">
          <div class="d-flex align-center gap-1 w-100" @click.stop>
            <v-btn
              v-if="!isAdmin && nextStatus(item.status)"
              size="x-small"
              :color="STATUS_COLOR[nextStatus(item.status)!]"
              variant="tonal"
              :loading="transitioning === item.id"
              style="min-width: 130px"
              @click.stop="doTransition(item)"
            >
              → {{ statusLabelFor(item, nextStatus(item.status)!) }}
            </v-btn>
            <v-menu v-if="isAdmin">
              <template #activator="{ props: menuProps }">
                <v-btn v-bind="menuProps" size="x-small" :color="STATUS_COLOR[item.status]" variant="tonal" :loading="transitioning === item.id" append-icon="mdi-chevron-down" style="min-width: 130px">
                  {{ statusLabelFor(item) }}
                </v-btn>
              </template>
              <v-list density="compact">
                <v-list-item
                  v-for="s in statusItems" :key="s.value"
                  :title="s.label"
                  :active="item.status === s.value"
                  @click="doForceStatus(item, s.value)"
                />
              </v-list>
            </v-menu>
            <v-btn v-if="linkTaskId" size="x-small" variant="tonal" color="deep-purple"
              prepend-icon="mdi-link-variant" @click.stop="doLinkTask(item.id)">
              Привязать
            </v-btn>
            <v-spacer />
            <v-btn v-if="isAdmin" icon="mdi-delete" variant="text" size="small" color="error" @click.stop="confirmDeleteOne(item)" />
          </div>
        </template>

        <!-- Expanded row: items list -->
        <template #expanded-row="{ columns, item }">
          <tr>
            <td :colspan="columns.length" class="pa-0 bg-grey-lighten-5">
              <div class="pa-3">
                <v-table density="compact" class="rounded border expand-items-table">
                  <colgroup>
                    <col style="width: auto">
                    <col style="width: 140px">
                    <col style="width: 110px">
                    <col style="width: 80px">
                    <col style="width: 160px">
                    <col style="width: 160px">
                  </colgroup>
                  <thead>
                    <tr class="bg-grey-lighten-4">
                      <th>Наименование позиции</th>
                      <th>Тип</th>
                      <th class="text-right">Кол-во</th>
                      <th>Ед.</th>
                      <th class="text-right">Цена ед., ₽</th>
                      <th class="text-right">Сумма, ₽</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="itm in item.items" :key="itm.id">
                      <td>{{ itm.item_name }}</td>
                      <td>{{ itm.item_type || '—' }}</td>
                      <td class="text-right">{{ itm.quantity ?? '—' }}</td>
                      <td>{{ itm.unit || '—' }}</td>
                      <td class="text-right">{{ itm.unit_price ? Number(itm.unit_price).toLocaleString('ru-RU') : '—' }}</td>
                      <td class="text-right">{{ itm.total_price ? Number(itm.total_price).toLocaleString('ru-RU') : '—' }}</td>
                    </tr>
                    <tr v-if="!item.items?.length">
                      <td colspan="6" class="text-center text-medium-emphasis text-caption py-2">Нет позиций</td>
                    </tr>
                  </tbody>
                </v-table>
              </div>
            </td>
          </tr>
        </template>

        <template #no-data>
          <div class="text-center py-10">
            <v-icon icon="mdi-clipboard-text-outline" size="48" color="grey-lighten-1" class="mb-3" />
            <div class="text-medium-emphasis">Закупки не найдены</div>
          </div>
        </template>
      </v-data-table>

    <!-- Cards view -->
    <div v-else>
      <v-row dense>
        <v-col v-for="item in pagedCards" :key="item.id" cols="12" sm="6" lg="4">
          <v-card variant="outlined" class="h-100 d-flex flex-column" hover @click="router.push(`/orders/${item.id}/edit`)">
            <v-card-item class="pb-1">
              <template #prepend>
                <v-checkbox-btn :model-value="isOrderSelected(item)" density="compact" @click.stop @update:model-value="toggleOrderSelected(item)" />
              </template>
              <v-card-title class="text-body-2 d-flex align-center ga-2">
                <span class="font-weight-bold">{{ item.registry_number || ('#' + item.id) }}</span>
                <v-chip :color="STATUS_COLOR[item.status] || 'grey'" size="x-small" variant="tonal">{{ statusLabelFor(item) }}</v-chip>
              </v-card-title>
            </v-card-item>
            <v-card-text class="py-1 flex-grow-1">
              <div class="text-body-2 font-weight-medium mb-1" style="overflow-wrap:anywhere">{{ item.subject || item.item_name || '—' }}</div>
              <div class="d-flex flex-wrap ga-1 mb-2">
                <v-chip :color="purchaseTypeColor(item)" size="x-small" variant="tonal">{{ purchaseTypeLabel(item) }}</v-chip>
                <v-chip v-if="item.approval_status" :color="APPROVAL_STATUS_COLOR[item.approval_status]" size="x-small" variant="tonal">{{ APPROVAL_STATUS_LABEL[item.approval_status] }}</v-chip>
              </div>
              <div class="text-caption text-medium-emphasis">Контрагент</div>
              <div class="text-body-2 mb-1" style="overflow-wrap:anywhere">{{ item.contractor_name || '—' }}</div>
              <div class="text-caption text-medium-emphasis">Субсидия</div>
              <div class="text-body-2 mb-1">{{ item.subsidy_name || '—' }}</div>
              <div class="d-flex justify-space-between mt-2">
                <div>
                  <div class="text-caption text-medium-emphasis">Сумма</div>
                  <div class="text-body-1 font-weight-bold">{{ formatMoney(effectivePrice(item)) }}</div>
                </div>
                <div class="text-right">
                  <div class="text-caption text-medium-emphasis">Договор</div>
                  <div class="text-body-2">{{ item.contract_date ? formatDate(item.contract_date) : '—' }}</div>
                </div>
              </div>
            </v-card-text>
            <v-divider />
            <v-card-actions class="py-1" @click.stop>
              <v-btn v-if="nextStatus(item.status)" size="x-small" :color="STATUS_COLOR[nextStatus(item.status)!]" variant="tonal" :loading="transitioning === item.id" @click.stop="doTransition(item)">→ {{ statusLabelFor(item, nextStatus(item.status)!) }}</v-btn>
              <v-spacer />
              <v-btn v-if="isAdmin" icon="mdi-delete" variant="text" size="small" color="error" @click.stop="confirmDeleteOne(item)" />
            </v-card-actions>
          </v-card>
        </v-col>
      </v-row>
      <div v-if="!pagedCards.length" class="text-center py-10">
        <v-icon icon="mdi-clipboard-text-outline" size="48" color="grey-lighten-1" class="mb-3" />
        <div class="text-medium-emphasis">Закупки не найдены</div>
      </div>
      <div v-if="cardsTotalPages > 1" class="d-flex justify-center mt-4">
        <v-pagination v-model="cardsPage" :length="cardsTotalPages" density="compact" total-visible="7" />
      </div>
    </div>

    <!-- Delete dialog -->
    <v-dialog v-model="deleteDialog.show" max-width="420">
      <v-card>
        <v-card-title class="text-h6 pt-4 px-6 d-flex align-center gap-2">
          <v-icon icon="mdi-alert-circle-outline" color="error" />
          Удалить закупки
        </v-card-title>
        <v-card-text class="px-6">
          <template v-if="deleteDialog.bulk">
            Удалить <strong>{{ selectedOrders.length }}</strong> выбранных закупок? Действие нельзя отменить.
          </template>
          <template v-else>
            Удалить закупку <strong>{{ deleteDialog.single?.subject || deleteDialog.single?.item_name || `#${deleteDialog.single?.id}` }}</strong>? Действие нельзя отменить.
          </template>
        </v-card-text>
        <v-card-actions class="px-6 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="deleteDialog.show = false">Отмена</v-btn>
          <v-btn color="error" :loading="deleteDialog.deleting" @click="doDelete">Удалить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Snackbar -->
    <v-snackbar v-model="snack.show" :color="snack.color" :timeout="3000" location="bottom right">
      {{ snack.text }}
    </v-snackbar>

    <!-- Guard dialog -->
    <v-dialog v-model="guardDialog.show" max-width="480">
      <v-card>
        <v-card-title class="text-h6 pt-4 px-6">Не заполнены обязательные поля</v-card-title>
        <v-card-text class="px-6">
          <p class="mb-3 text-body-2 text-medium-emphasis">
            Для перехода в статус «{{ guardDialog.targetStatus === 'contracted' && guardDialog.isFramework ? 'Заказ' : STATUS_LABEL[guardDialog.targetStatus] }}» заполните:
          </p>
          <v-list density="compact">
            <v-list-item
              v-for="f in guardDialog.missing"
              :key="f"
              prepend-icon="mdi-alert-circle-outline"
              :title="f"
            />
          </v-list>
        </v-card-text>
        <v-card-actions class="px-6 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="guardDialog.show = false">Закрыть</v-btn>
          <v-btn color="primary" :to="`/orders/${guardDialog.purchaseId}/edit`" @click="guardDialog.show = false">
            Открыть форму
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Import Dialog ── -->
    <v-dialog v-model="importDialog.show" max-width="580" persistent :fullscreen="mobile">
      <v-card>
        <v-card-title class="pa-5 pb-2 d-flex align-center">
          <v-icon icon="mdi-file-import" color="blue" class="mr-2" />
          Импорт закупок из Excel
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="resetImport" />
        </v-card-title>
        <v-card-text class="pa-5 pt-2">

          <!-- Step 1: Setup -->
          <template v-if="importDialog.step === 1">
            <!-- Format selection -->
            <v-radio-group v-model="importDialog.format" inline class="mb-3" hide-details density="compact">
              <template #label><span class="text-body-2 font-weight-medium mr-3">Формат файла:</span></template>
              <v-radio value="standard" label="Стандартный (17 колонок)" />
              <v-radio value="feo" label="ФЭО-формат (57 колонок)" />
            </v-radio-group>

            <!-- Standard: subsidy override -->
            <v-select
              v-if="importDialog.format === 'standard'"
              v-model="importDialog.subsidyId"
              :items="[{ id: null, name: '— Из файла (колонка «Субсидия»)' }, ...subsidies]"
              item-title="name" item-value="id"
              label="Субсидия (переопределить для всего файла)"
              variant="outlined" density="compact" class="mb-3"
            />

            <!-- Standard: format hint -->
            <v-alert
              v-if="importDialog.format === 'standard'"
              type="info" variant="tonal" density="compact" class="mb-3"
              icon="mdi-information-outline"
            >
              <div class="text-body-2">
                <strong>Форматы:</strong> Excel (.xlsx, .xls)<br>
                <strong>Заголовки:</strong> определяются автоматически по ключевым словам — могут быть в любой строке<br>
                <strong>Лист:</strong> любое название — система прочитает первый или предложит выбрать
              </div>
            </v-alert>

            <!-- FEO: info banner -->
            <v-alert
              v-else
              type="info" variant="tonal" density="compact" class="mb-3"
              prepend-icon="mdi-information-outline"
            >
              Субсидия определяется автоматически по категории ФЭО (колонка 5). Заголовки — в строке 6.
            </v-alert>

            <!-- FEO: assigned user selector -->
            <v-autocomplete
              v-if="importDialog.format === 'feo'"
              v-model="importDialog.assignedUserId"
              :items="importUserItems"
              item-title="text"
              item-value="value"
              label="Ответственный исполнитель"
              hint="Все импортируемые закупки будут назначены на этого сотрудника"
              persistent-hint
              variant="outlined"
              density="compact"
              class="mb-3"
              :rules="[(v: any) => !!v || 'Обязательное поле']"
              clearable
            />

            <FileDropZone v-model="importDialog.file"
              accept=".xlsx,.xls"
              hint="Excel (.xlsx, .xls) — перетащите или нажмите"
              class="mb-2" />

            <div v-if="importDialog.format === 'standard'" class="mt-3 text-caption text-medium-emphasis">
              Допустимые заголовки колонок:
              <span class="fz-11">Наименование, Субсидия, Категория ФЭО, Контрагент, ИНН контрагента, НМЦД, Способ закупки, Реестровый №, № договора, Дата договора, Цена договора, Срок исполнения, ПП №, ПП дата, Оплачено, Статус, Год</span>
            </div>
          </template>

          <!-- Step 2: Result -->
          <template v-else-if="importDialog.step === 2">
            <div class="import-result-row">
              <div class="import-stat import-stat--ok">
                <div class="import-stat-val">{{ importDialog.result?.created ?? 0 }}</div>
                <div class="import-stat-lbl">Создано</div>
              </div>
              <div class="import-stat import-stat--skip">
                <div class="import-stat-val">{{ importDialog.result?.skipped ?? 0 }}</div>
                <div class="import-stat-lbl">Пропущено</div>
              </div>
              <div class="import-stat import-stat--err">
                <div class="import-stat-val">{{ importDialog.result?.errors?.length ?? 0 }}</div>
                <div class="import-stat-lbl">Ошибок</div>
              </div>
            </div>
            <div v-if="importDialog.result?.errors?.length" class="mt-4">
              <div class="text-caption font-weight-bold mb-2">Строки с ошибками:</div>
              <v-list density="compact" class="import-errors-list">
                <v-list-item
                  v-for="e in importDialog.result.errors" :key="e.row"
                  :subtitle="`Строка ${e.row}: ${e.message}`"
                  :title="e.name"
                  prepend-icon="mdi-alert-circle-outline"
                  color="error"
                />
              </v-list>
            </div>
          </template>

        </v-card-text>
        <v-card-actions class="pa-5 pt-0">
          <v-btn variant="text" size="small" prepend-icon="mdi-download"
            @click="downloadTemplate">Скачать шаблон</v-btn>
          <v-spacer />
          <v-btn variant="text" @click="resetImport">
            {{ importDialog.step === 2 ? 'Закрыть' : 'Отмена' }}
          </v-btn>
          <v-btn v-if="importDialog.step === 1" color="blue" variant="flat"
            :loading="importDialog.loading" :disabled="!importDialog.file"
            @click="doImport">
            Загрузить
          </v-btn>
          <v-btn v-else color="primary" variant="flat" @click="resetImport">Готово</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Save Filter Preset Dialog -->
    <v-dialog v-model="filterPresetDialog.show" max-width="380">
      <v-card>
        <v-card-title class="pa-4">Сохранить фильтр</v-card-title>
        <v-card-text class="pa-4 pt-0">
          <v-text-field
            v-model="filterPresetDialog.name"
            label="Название пресета"
            variant="outlined" density="compact" autofocus
            placeholder="Например: ФАДМ 2026 неоплачено"
            @keyup.enter="confirmSaveFilterPreset"
          />
          <div class="text-caption text-medium-emphasis mt-1">
            <span v-if="filterSubsidyId">Субсидия: {{ subsidies.find(s=>s.id===filterSubsidyId)?.name }}</span>
            <span v-if="filterStatus" class="ml-2">Статус: {{ STATUS_LABEL[filterStatus] }}</span>
            <span v-if="search" class="ml-2">Поиск: "{{ search }}"</span>
          </div>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="filterPresetDialog.show = false">Отмена</v-btn>
          <v-btn color="primary" variant="flat" :disabled="!filterPresetDialog.name.trim()" @click="confirmSaveFilterPreset">
            Сохранить
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

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

    <!-- Excel Export Dialog -->
    <v-dialog v-model="exportDialog.show" max-width="680" scrollable :fullscreen="mobile">
      <v-card>
        <v-card-title class="d-flex align-center pa-4">
          <v-icon icon="mdi-microsoft-excel" color="success" class="mr-2" />
          Экспорт в Excel
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="exportDialog.show = false" />
        </v-card-title>

        <v-card-text class="pa-0">
          <!-- Presets row -->
          <div class="d-flex align-center gap-2 px-4 py-2 bg-grey-lighten-5 border-b">
            <span class="text-caption text-medium-emphasis mr-1">Пресет:</span>
            <v-btn size="x-small" variant="tonal" @click="applyPreset('default')">Стандартный</v-btn>
            <v-btn size="x-small" variant="tonal" @click="applyPreset('all')">Полный</v-btn>
            <v-btn size="x-small" variant="tonal" color="blue" @click="applyPreset('saved')" :disabled="!hasSavedPreset">
              Мой ({{ savedPresetCount }})
            </v-btn>
            <v-spacer />
            <v-btn size="x-small" variant="outlined" prepend-icon="mdi-content-save" @click="savePreset">
              Сохранить
            </v-btn>
          </div>

          <!-- Columns by group -->
          <div v-if="exportDialog.loading" class="d-flex justify-center py-8">
            <v-progress-circular indeterminate color="primary" />
          </div>
          <div v-else class="px-4 py-2">
            <div v-for="group in exportColumnGroups" :key="group.name" class="mb-3">
              <div class="d-flex align-center mb-1">
                <span class="text-caption font-weight-bold text-medium-emphasis text-uppercase">{{ group.name }}</span>
                <v-btn
                  size="x-small" variant="text" class="ml-1"
                  @click="toggleGroup(group.name, true)">все</v-btn>
                <v-btn
                  size="x-small" variant="text"
                  @click="toggleGroup(group.name, false)">ни одного</v-btn>
              </div>
              <div class="d-flex flex-wrap gap-1">
                <v-checkbox
                  v-for="col in group.cols" :key="col.key"
                  v-model="exportDialog.selected"
                  :value="col.key"
                  :label="col.label"
                  density="compact"
                  hide-details
                  class="export-col-check"
                />
              </div>
            </div>
          </div>
        </v-card-text>

        <v-card-actions class="pa-4 pt-2">
          <span class="text-caption text-medium-emphasis">Выбрано: {{ exportDialog.selected.length }}</span>
          <v-spacer />
          <v-btn variant="text" @click="exportDialog.show = false">Отмена</v-btn>
          <v-btn
            color="success" variant="flat"
            prepend-icon="mdi-download"
            :loading="exportDialog.exporting"
            :disabled="exportDialog.selected.length === 0"
            @click="doExport">
            Скачать Excel
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiFetch } from '@/api'
import { useGlobalSubsidy } from '@/composables/useGlobalSubsidy'
import { addResizeHandles, restoreTableWidths } from '@/composables/useTableResize'
import FileDropZone from '@/components/FileDropZone.vue'
import { useColumnConfig, type ColumnDef, type FilterValue } from '@/composables/useColumnConfig'
import ColumnConfigDialog from '@/components/ColumnConfigDialog.vue'
import ColumnHeaderMenu from '@/components/ColumnHeaderMenu.vue'
import { formatMoney } from '@/utils/formatMoney'
import { useDisplay } from 'vuetify'

const { globalSubsidyId } = useGlobalSubsidy()

const route = useRoute()
const router = useRouter()

// View mode toggle (table ↔ cards)
const { mobile } = useDisplay()
const viewMode = ref<'table' | 'cards'>((localStorage.getItem('orders_view_mode') as 'table' | 'cards') || 'table')
watch(viewMode, v => localStorage.setItem('orders_view_mode', v))
const effectiveView = computed(() => (mobile.value ? 'cards' : viewMode.value))
const cardsPage = ref(1)
const cardsPageSize = 24
const userRole = localStorage.getItem('user_role') || ''
const isAdmin = ['admin', 'superadmin', 'org_admin'].includes(userRole)

interface PurchaseItem { id: number; item_name: string; item_type?: string; quantity?: number; unit?: string; unit_price?: number; total_price?: number }
interface Subsidy { id: number; name: string; year: number }
interface Contractor { id: number; name: string }
interface Purchase {
  id: number
  purchase_number?: number
  item_name?: string
  contractor_id?: number
  contractor_name?: string
  reimbursement_user_id?: number | null
  reimbursement_user_name?: string | null
  multi_contractor_label?: string | null
  feo_category_name?: string
  feo_category_id?: number
  subsidy_name?: string
  subsidy_id?: number
  subject?: string
  planned_total_price?: number
  total_nmck?: number
  purchase_method?: string
  purchase_basis?: string
  purchase_contract_type?: string
  registry_number?: string
  responsible_person?: string
  assigned_user_id?: number
  contract_price?: number
  framework_contract_total?: number | string | null
  delivery_payment_amount?: number
  status: string
  substatus?: string
  is_monthly_payment?: boolean
  delivery_date?: string
  contract_number?: string
  contract_date?: string
  acceptance_doc_name?: string
  acceptance_doc_date?: string
  acceptance_doc_number?: string
  acceptance_doc_amount?: number
  payment_doc_number?: string
  payment_doc_date?: string
  payment_amount?: number
  items?: PurchaseItem[]
  approval_status?: string
  execution_term?: string
  // Phase 26-K
  agreement_number?: string
  agreement_date?: string
  order_number?: string
  order_date?: string
}

const FRAMEWORK_TYPES = new Set(['framework_cumulative', 'framework_with_amount'])
function isItemFramework(item: Purchase) { return FRAMEWORK_TYPES.has(item.purchase_contract_type || '') }

function purchaseTypeLabel(item: Purchase): string {
  if (item.purchase_method === 'advance') return 'Авансовый'
  if (isItemFramework(item)) return 'Рамочный'
  if (item.purchase_basis === 'invoice') return 'По счёту'
  if (item.purchase_method === 'single' || item.purchase_contract_type === 'single') return 'Разовый'
  if (item.purchase_method === 'competitive') return 'Конкурентный'
  return 'Разовый'
}
function purchaseMethodLabel(m?: string): string {
  if (m === 'single') return 'Единственный поставщик'
  if (m === 'competitive') return 'Конкурсная процедура'
  if (m === 'advance') return 'Авансовый отчёт'
  return m || '—'
}
function purchaseTypeColor(item: Purchase): string {
  if (item.purchase_method === 'advance') return 'purple'
  if (isItemFramework(item)) return 'indigo'
  if (item.purchase_basis === 'invoice') return 'grey'
  if (item.purchase_method === 'competitive') return 'cyan'
  return 'green'
}
function advancePersonLabel(item: Purchase): string {
  return item.responsible_person || `#${item.assigned_user_id}` || '—'
}

const STATUS_ORDER = ['wishes', 'plan_schedule', 'confirmed', 'work_in_progress', 'contracted', 'ordered', 'delivered', 'paid']
const STATUS_LABEL: Record<string, string> = {
  wishes: 'Желания', plan_schedule: 'План-график',
  confirmed: 'Подтверждено', work_in_progress: 'Ведётся работа',
  contracted: 'Договор', ordered: 'Заказано',
  delivered: 'Поставлено', paid: 'Оплачено',
}
function statusLabelFor(item: Purchase, status?: string): string {
  const s = status || item.status
  if (s === 'contracted' && isItemFramework(item)) return 'Заказ'
  return STATUS_LABEL[s] || s
}
const STATUS_COLOR: Record<string, string> = {
  wishes: 'amber', plan_schedule: 'orange',
  confirmed: 'blue', work_in_progress: 'teal',
  contracted: 'indigo', ordered: 'purple',
  delivered: 'deep-purple', paid: 'green',
}
const SUBSTATUS_LABEL: Record<string, string> = {
  tz_forming: 'Формируется ТЗ',
  kp_collecting: 'Сбор КП',
  on_platform: 'На площадке',
}
const APPROVAL_STATUS_COLOR: Record<string, string> = {
  in_progress: 'orange', approved: 'green', rejected: 'error',
}
const APPROVAL_STATUS_LABEL: Record<string, string> = {
  in_progress: 'На согласовании', approved: 'Согласовано', rejected: 'Отклонено',
}
const statusItems = STATUS_ORDER.map(v => ({ value: v, label: STATUS_LABEL[v], color: STATUS_COLOR[v] }))

function transitionRequired(item: Purchase): Record<string, { field: keyof Purchase; label: string }[]> {
  const fw = isItemFramework(item)
  return {
  contracted: [
    { field: 'contract_number', label: fw ? 'Номер заказа' : 'Номер договора' },
    { field: 'contract_date', label: fw ? 'Дата заказа' : 'Дата договора' },
  ],
  delivered: [
    { field: 'acceptance_doc_name', label: 'Наименование закрывающего документа' },
    { field: 'acceptance_doc_date', label: 'Дата закрывающего документа' },
    { field: 'acceptance_doc_number', label: 'Номер закрывающего документа' },
    { field: 'acceptance_doc_amount', label: 'Сумма закрывающего документа' },
  ],
  paid: [
    { field: 'payment_doc_number', label: 'Номер платёжного поручения' },
    { field: 'payment_doc_date', label: 'Дата платёжного поручения' },
    { field: 'payment_amount', label: 'Сумма платежа' },
  ],
}}

const allColumns: ColumnDef[] = [
  // core — видимые по умолчанию
  // _rownum добавляется отдельно через tableHeaders computed (всегда первая колонка, не зависит от LS)
  { title: '', key: 'data-table-expand', width: 48, sortable: false, group: 'core' },
  { title: 'Реестр. №', key: 'registry_number', width: 140, group: 'core' },
  { title: 'Предмет договора', key: 'subject', group: 'core' },
  { title: 'Контрагент', key: 'contractor_name', width: 220, group: 'core' },
  { title: 'Субсидия', key: 'subsidy_name', group: 'core' },
  { title: 'Цена', key: 'effective_price', align: 'end', sortable: false, group: 'core' },
  { title: '№ договора', key: 'contract_number', group: 'core' },
  { title: 'Дата договора', key: 'contract_date', group: 'core' },
  { title: 'Тип', key: 'purchase_type', width: 110, sortable: false, group: 'core' },
  { title: 'Статус', key: 'status', width: 130, group: 'core' },
  { title: 'Согласование', key: 'approval_status', width: 130, sortable: true, group: 'core' },
  { title: 'Действия', key: 'actions', sortable: false, width: 200, group: 'core' },
  // all — все остальные поля из PurchaseOut / Purchase модели
  { title: 'Наименование', key: 'item_name', group: 'all' },
  { title: 'Отображаемое название', key: 'display_name', sortable: false, group: 'all' },
  { title: 'Кол-во', key: 'planned_quantity', width: 100, align: 'end', group: 'all' },
  { title: 'Ед. изм.', key: 'unit', width: 90, group: 'all' },
  { title: 'Цена ед. (план)', key: 'planned_unit_price', width: 140, align: 'end', group: 'all' },
  { title: 'Сумма (план)', key: 'planned_total_price', width: 130, align: 'end', group: 'all' },
  { title: 'Цена ед. (факт)', key: 'final_unit_price', width: 140, align: 'end', group: 'all' },
  { title: 'Сумма (факт)', key: 'final_total_amount', width: 130, align: 'end', group: 'all' },
  { title: 'Сумма доставки', key: 'delivery_payment_amount', width: 150, align: 'end', group: 'all' },
  { title: 'НМЦД', key: 'nmck', width: 130, align: 'end', group: 'all' },
  { title: 'Итого НМЦД', key: 'total_nmck', width: 130, align: 'end', group: 'all' },
  { title: 'Цена договора', key: 'contract_price', width: 130, align: 'end', group: 'all' },
  // Phase 26-N: денежные показатели по закупке (скрыты по умолчанию, group:'all')
  { title: 'Заказано', key: 'ordered_amount', width: 130, align: 'end', group: 'all' },
  { title: 'Поставлено', key: 'delivered_amount', width: 130, align: 'end', group: 'all' },
  { title: 'Оплачено (закупка)', key: 'paid_amount', width: 130, align: 'end', group: 'all' },
  { title: 'Заказано − Поставлено', key: 'diff_ordered_delivered', width: 160, align: 'end', group: 'all' },
  { title: 'Поставлено − Оплачено', key: 'diff_delivered_paid', width: 160, align: 'end', group: 'all' },
  { title: 'Заказано − Оплачено', key: 'diff_ordered_paid', width: 160, align: 'end', group: 'all' },
  { title: 'Экономия', key: 'economy', width: 120, align: 'end', group: 'all' },
  { title: 'Превышение', key: 'price_increase', width: 130, align: 'end', group: 'all' },
  { title: 'Срок исполнения', key: 'execution_term', width: 150, group: 'all' },
  { title: 'Срок (изменён)', key: 'execution_term_changed', width: 150, group: 'all' },
  { title: 'Дата поставки', key: 'delivery_date', width: 140, group: 'all' },
  { title: 'Страна происхождения', key: 'country_origin', width: 180, group: 'all' },
  { title: 'Способ закупки', key: 'purchase_method', width: 150, group: 'all' },
  { title: 'Тип договора (контракт)', key: 'purchase_contract_type', width: 190, group: 'all' },
  { title: 'Порядковый № (рамочный)', key: 'framework_seq', width: 190, group: 'all' },
  { title: 'Основание закупки', key: 'purchase_basis', width: 160, group: 'all' },
  { title: 'Тип позиции', key: 'item_type', width: 120, group: 'all' },
  { title: 'ФЭО категория', key: 'feo_category_name', group: 'all' },
  { title: 'Ответственный', key: 'responsible_person', group: 'all' },
  { title: 'Кому возмещать', key: 'reimbursement_user_name', width: 180, group: 'all' },
  { title: 'Мн. контрагент', key: 'multi_contractor_label', width: 180, group: 'all' },
  { title: 'Предоплата', key: 'is_prepayment', width: 120, group: 'all' },
  { title: 'Дата предоплаты', key: 'prepayment_date', width: 150, group: 'all' },
  { title: 'Ежемесячный платёж', key: 'is_monthly_payment', width: 180, group: 'all' },
  { title: 'Кол-во платежей', key: 'monthly_payment_count', width: 150, group: 'all' },
  { title: 'Сумма платежа', key: 'monthly_payment_amount', width: 150, align: 'end', group: 'all' },
  { title: 'Скорее всего нужно', key: 'is_likely_needed', width: 170, group: 'all' },
  { title: 'Этап', key: 'stage_label', width: 160, group: 'all' },
  { title: 'Подстатус', key: 'substatus', width: 150, group: 'all' },
  { title: 'Место доставки', key: 'delivery_location', group: 'all' },
  { title: 'Регион', key: 'region', width: 180, group: 'all' },
  { title: 'Тип места', key: 'delivery_location_kind', width: 130, group: 'all' },
  { title: 'Адрес доставки', key: 'delivery_address', group: 'all' },
  { title: 'Срок подачи заявок', key: 'submission_deadline', width: 170, group: 'all' },
  { title: 'Режим срока услуги', key: 'service_term_mode', width: 170, group: 'all' },
  { title: 'Дней услуги', key: 'service_term_days', width: 140, group: 'all' },
  { title: 'Тип дней', key: 'service_term_type', width: 130, group: 'all' },
  { title: 'Нач. период услуги', key: 'service_start_date', width: 170, group: 'all' },
  { title: 'Кон. период услуги', key: 'service_end_date', width: 170, group: 'all' },
  { title: 'Дедлайн услуги', key: 'service_deadline_date', width: 150, group: 'all' },
  { title: 'Плановая дата закупки', key: 'procurement_planned_date', width: 190, group: 'all' },
  { title: 'Закрывающий документ', key: 'acceptance_doc_name', width: 190, group: 'all' },
  { title: '№ закрывающего', key: 'acceptance_doc_number', width: 160, group: 'all' },
  { title: 'Дата закрывающего', key: 'acceptance_doc_date', width: 170, group: 'all' },
  { title: 'Сумма закрывающего', key: 'acceptance_doc_amount', width: 180, align: 'end', group: 'all' },
  { title: '№ ПП', key: 'payment_doc_number', width: 110, group: 'all' },
  { title: 'Дата ПП', key: 'payment_doc_date', width: 130, group: 'all' },
  { title: 'Оплачено', key: 'payment_amount', width: 130, align: 'end', group: 'all' },
  { title: 'Оплачено (федерал.)', key: 'payment_federal', width: 170, align: 'end', group: 'all' },
  { title: 'НДС применяется', key: 'vat_applicable', width: 150, group: 'all' },
  { title: 'Ставка НДС', key: 'vat_rate', width: 120, group: 'all' },
  { title: 'Ст. НК РФ (НДС)', key: 'vat_exemption_article', width: 160, group: 'all' },
  { title: 'Третьи лица', key: 'third_party_involved', width: 140, group: 'all' },
  { title: 'Срок договора (до)', key: 'contract_end_date', width: 160, group: 'all' },
  { title: 'Тип периода услуги', key: 'service_period_type', width: 170, group: 'all' },
  { title: 'Режим описания', key: 'description_mode', width: 150, group: 'all' },
  { title: 'Режим согласования', key: 'approval_mode', width: 170, group: 'all' },
  { title: 'Тип подписи', key: 'approval_sign_type', width: 140, group: 'all' },
  { title: 'Казначейский код', key: 'treasury_code', width: 160, group: 'all' },
  { title: 'Претензионная работа', key: 'has_pretension', width: 180, group: 'all' },
  { title: 'Основание оплаты', key: 'payment_basis_type', width: 170, group: 'all' },
  { title: 'Служебная записка', key: 'service_note_text', group: 'all' },
  { title: 'Мероприятие', key: 'event_name', group: 'all' },
  { title: 'ID субсидии', key: 'subsidy_id', width: 110, group: 'all' },
  { title: 'ID договора', key: 'contract_id', width: 110, group: 'all' },
  // Phase 26-K: доп. соглашение и дата заказа — скрыты по умолчанию
  { title: '№ доп.соглашения', key: 'agreement_number', width: 170, group: 'all' },
  { title: 'Дата доп.соглашения', key: 'agreement_date', width: 180, group: 'all' },
  { title: '№ заказа', key: 'order_number', width: 140, group: 'all' },
  { title: 'Дата заказа', key: 'order_date', width: 140, group: 'all' },
]

const groups = [
  { key: 'core', label: 'Основные' },
  { key: 'all', label: 'Все возможные' },
]

const cfg = useColumnConfig('orders', allColumns)
const { state: colState, visibleHeaders, toggleVisible, setPosition, setWidth, reset: resetColumns, setFilter, clearAllFilters, activeFilterCount } = cfg
// _rownum — всегда первая колонка, не зависит от useColumnConfig состояния
const tableHeaders = computed(() => [
  { title: '№ п/п', key: '_rownum', width: 60, sortable: false },
  ...visibleHeaders.value,
])
const showColumnPicker = ref(false)

// ── Column-header sort / filter helpers ──────────────────────────────────────
const localSort = ref<{ key: string; order: 'asc' | 'desc' } | null>(null)
function getSortBy(k: string) { return localSort.value?.key === k ? localSort.value.order : null }
function applySort(k: string, dir: 'asc' | 'desc' | null) { localSort.value = dir ? { key: k, order: dir } : null }

function uniqValues(rows: any[], key: string): (string | number | null)[] {
  const set = new Set<any>()
  rows.forEach(r => set.add(r?.[key] ?? null))
  return [...set].sort((a, b) => String(a ?? '').localeCompare(String(b ?? '')))
}

// Phase 26-N: helper for delivered amount (acceptance_doc_amount → delivery_payment_amount → last acceptance_docs entry)
function _deliveredAmount(r: any): number | null {
  if (r.acceptance_doc_amount != null) return Number(r.acceptance_doc_amount)
  if (r.delivery_payment_amount != null) return Number(r.delivery_payment_amount)
  if (Array.isArray(r.acceptance_docs) && r.acceptance_docs.length) {
    const last = r.acceptance_docs[r.acceptance_docs.length - 1]
    if (last?.amount != null) return Number(last.amount)
  }
  return null
}

// Field getters for computed/derived columns where row[key] is undefined.
const FIELD_GETTERS: Record<string, (r: any) => any> = {
  effective_price: (r) => effectivePrice(r),
  // phase26-m: для рамочного показываем суммарную цену договора (max_amount or SUM)
  contract_price: (r: any) => {
    const isFw = (r.purchase_contract_type || '').startsWith('framework')
    if (isFw && r.framework_contract_total != null) return Number(r.framework_contract_total)
    return r.contract_price != null ? Number(r.contract_price) : null
  },
  // Phase 26-N: денежные показатели
  ordered_amount: (r: any) => r.contract_price != null ? Number(r.contract_price) : null,
  delivered_amount: (r: any) => _deliveredAmount(r),
  paid_amount: (r: any) => r.payment_amount != null ? Number(r.payment_amount) : null,
  diff_ordered_delivered: (r: any) => {
    const o = r.contract_price != null ? Number(r.contract_price) : null
    const d = _deliveredAmount(r)
    return (o != null && d != null) ? o - d : null
  },
  diff_delivered_paid: (r: any) => {
    const d = _deliveredAmount(r)
    const p = r.payment_amount != null ? Number(r.payment_amount) : null
    return (d != null && p != null) ? d - p : null
  },
  diff_ordered_paid: (r: any) => {
    const o = r.contract_price != null ? Number(r.contract_price) : null
    const p = r.payment_amount != null ? Number(r.payment_amount) : null
    return (o != null && p != null) ? o - p : null
  },
  // purchase_type — виртуальное поле, матчим по purchase_contract_type напрямую
  purchase_type: (r: any) => {
    if (r.purchase_method === 'advance') return 'advance'
    if (r.purchase_basis === 'invoice') return 'invoice'
    const ct: string = r.purchase_contract_type || ''
    if (ct === 'framework_cumulative') return 'framework_cumulative'
    if (ct === 'framework_with_amount') return 'framework_with_amount'
    return 'one_time'
  },
}
function getRowField(row: any, key: string): any {
  const getter = FIELD_GETTERS[key]
  return getter ? getter(row) : (row?.[key] ?? null)
}

function matchesColumnFilters(row: any): boolean {
  const filters = cfg.state.value.filters
  for (const [k, f] of Object.entries(filters)) {
    const v = getRowField(row, k)
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

// ── Link task mode (from ?link_task=ID) ──
const linkTaskId = ref<number | null>(null)

async function doLinkTask(purchaseId: number) {
  if (!linkTaskId.value) return
  try {
    await apiFetch(`/tasks/${linkTaskId.value}`, {
      method: 'PATCH', body: JSON.stringify({ purchase_id: purchaseId }),
    })
    const tid = linkTaskId.value
    linkTaskId.value = null
    router.replace({ path: '/my-tasks', query: { task: String(tid) } })
  } catch (e: any) {
    alert(e?.detail || 'Ошибка привязки')
  }
}

const orders = ref<Purchase[]>([])
const subsidies = ref<Subsidy[]>([])
const contractors = ref<Contractor[]>([])
const loading = ref(false)
const transitioning = ref<number | null>(null)
const filterStatus = ref<string | null>(null)
const filterSubsidyId = ref<number | null>(null)
const filterFeoCategoryId = ref<number | null>(null)
const filterMethod   = ref<string>('')
const filterOverdue  = ref(false)
const filterDueSoon  = ref(false)
const filterFeoCategoryName = ref<string>('')
const filterTypes = ref<string[]>([])
const filterContractorIds = ref<number[]>([])
const fProduct = ref('')
const search = ref('')

// Phase 31-06: filter to show only purchases with unseen foreign changes
const filterOnlyUnseen = ref(false)

const orderTypeOptions = [
  { label: 'Разовый', value: 'one_time' },
  { label: 'Рамочный', value: 'framework' },
  { label: 'Авансовый', value: 'advance' },
  { label: 'По счёту', value: 'invoice' },
]

function getOrderTypeKey(o: Purchase): string {
  if (o.purchase_method === 'advance') return 'advance'
  if (o.purchase_contract_type === 'single' || o.purchase_method === 'single') return 'one_time'
  if ((o.purchase_contract_type || '').startsWith('framework')) return 'framework'
  if (o.purchase_basis === 'invoice') return 'invoice'
  return 'one_time'
}

// Дедуп по имени контрагента — для авансовых contractor_id часто пуст.
const contractorsForFilter = computed(() => {
  const byName = new Map<string, any>()
  for (const o of orders.value as any[]) {
    const name = o.contractor_name
    if (!name || byName.has(name)) continue
    const real = contractors.value.find(c =>
      (o.contractor_id && c.id === o.contractor_id) ||
      (o.contractor_inn && c.inn === o.contractor_inn) ||
      c.name === name
    )
    byName.set(name, real || { id: -byName.size - 1, name, inn: o.contractor_inn || '' })
  }
  return Array.from(byName.values())
})
const expanded = ref<string[]>([])
const selectedOrders = ref<Purchase[]>([])

const snack = reactive({ show: false, text: '', color: 'success' })

// ---------------------------------------------------------------------------
// Saved filter presets
// ---------------------------------------------------------------------------
const FILTER_PRESETS_KEY = 'orders_filter_presets'
interface FilterPreset { name: string; subsidyId: number | null; status: string; search: string; types?: string[]; contractorIds?: number[] }

const savedFilterPresets = ref<FilterPreset[]>([])
const filterPresetDialog = reactive({ show: false, name: '' })

function loadFilterPresets() {
  try { savedFilterPresets.value = JSON.parse(localStorage.getItem(FILTER_PRESETS_KEY) || '[]') } catch {}
}
function saveFilterPreset() {
  filterPresetDialog.name = ''
  filterPresetDialog.show = true
}
function confirmSaveFilterPreset() {
  const name = filterPresetDialog.name.trim()
  if (!name) return
  const preset: FilterPreset = {
    name,
    subsidyId: filterSubsidyId.value,
    status: filterStatus.value,
    search: search.value,
    types: [...filterTypes.value],
    contractorIds: [...filterContractorIds.value],
  }
  const existing = savedFilterPresets.value.filter(p => p.name !== name)
  savedFilterPresets.value = [...existing, preset]
  localStorage.setItem(FILTER_PRESETS_KEY, JSON.stringify(savedFilterPresets.value))
  filterPresetDialog.show = false
  showSnack('Пресет сохранён')
}
function applyFilterPreset(p: FilterPreset) {
  filterSubsidyId.value = p.subsidyId
  filterStatus.value = p.status
  search.value = p.search
  filterTypes.value = p.types ?? []
  filterContractorIds.value = p.contractorIds ?? []
}
function removeFilterPreset(name: string) {
  savedFilterPresets.value = savedFilterPresets.value.filter(p => p.name !== name)
  localStorage.setItem(FILTER_PRESETS_KEY, JSON.stringify(savedFilterPresets.value))
}

const guardDialog = reactive({
  show: false, purchaseId: 0, targetStatus: '', missing: [] as string[], isFramework: false,
})
const deleteDialog = reactive({
  show: false, single: null as Purchase | null, bulk: false, deleting: false,
})

const showSnack = (text: string, color = 'success') => { snack.text = text; snack.color = color; snack.show = true }

const effectivePrice = (item: Purchase): number | null => {
  switch (item.status) {
    case 'contracted':
      return item.contract_price ?? item.total_nmck ?? item.planned_total_price ?? null
    case 'delivered':
      return item.contract_price ?? item.total_nmck ?? item.planned_total_price ?? null
    case 'paid':
      return item.payment_amount ?? item.contract_price ?? null
    default:
      return item.total_nmck ?? item.planned_total_price ?? null
  }
}

const formatDate = (d: string) => {
  const [y, m, day] = d.split('-')
  return `${day}.${m}.${y}`
}

const itemDisplayName = (p: Purchase) => {
  if (p.items && p.items.length > 0) {
    return p.items.length === 1
      ? p.items[0].item_name
      : `${p.items[0].item_name} (+${p.items.length - 1})`
  }
  return p.item_name || '—'
}

const nextStatus = (current: string): string | null => {
  const idx = STATUS_ORDER.indexOf(current)
  return idx >= 0 && idx < STATUS_ORDER.length - 1 ? STATUS_ORDER[idx + 1] : null
}

const filteredOrders = computed(() => {
  let r = orders.value
  if (filterStatus.value) {
    const statuses = filterStatus.value.split(',').map(s => s.trim()).filter(Boolean)
    r = r.filter(o => statuses.includes(o.status))
  }
  if (filterSubsidyId.value) r = r.filter(o => o.subsidy_id === filterSubsidyId.value)
  if (filterFeoCategoryId.value) r = r.filter(o => o.feo_category_id === filterFeoCategoryId.value)
  if (filterMethod.value) r = r.filter(o => o.purchase_method === filterMethod.value)
  if (filterOverdue.value) {
    const today = new Date().toISOString().slice(0, 10)
    r = r.filter(o => o.execution_term && o.execution_term < today && !['paid', 'delivered'].includes(o.status))
  }
  if (filterDueSoon.value) {
    const today = new Date().toISOString().slice(0, 10)
    const in30  = new Date(Date.now() + 30 * 86400 * 1000).toISOString().slice(0, 10)
    r = r.filter(o => o.execution_term && o.execution_term >= today && o.execution_term <= in30 && !['paid', 'delivered'].includes(o.status))
  }
  if (filterTypes.value.length > 0) {
    r = r.filter(o => filterTypes.value.includes(getOrderTypeKey(o)))
  }
  if (filterContractorIds.value.length > 0) {
    const allowedNames = new Set(
      contractorsForFilter.value
        .filter((c: any) => filterContractorIds.value.includes(c.id))
        .map((c: any) => c.name)
    )
    r = r.filter(o => !!o.contractor_name && allowedNames.has(o.contractor_name))
  }
  // Поиск по товару (item_name позиций или subject закупки)
  if (fProduct.value && fProduct.value.trim()) {
    const q = fProduct.value.trim().toLowerCase()
    r = r.filter(o =>
      (o as any).items?.some((it: any) => it.item_name?.toLowerCase().includes(q)) ||
      o.subject?.toLowerCase().includes(q) ||
      o.item_name?.toLowerCase().includes(q)
    )
  }
  // Phase 31-06: filter to show only purchases with unseen foreign changes
  if (filterOnlyUnseen.value) r = r.filter(o => (o as any).unseen_changes_count > 0)
  // Column-header filters (поверх panel-фильтров)
  r = r.filter(matchesColumnFilters)
  return r
})

const filteredOrdersWithRowNum = computed(() => {
  // Нумерация по возрастанию id: более раннее (меньший id) = меньший _rownum.
  // Ключ Map — String(id) чтобы избежать number/string mismatch.
  const sorted = [...filteredOrders.value].sort((a, b) => (Number(a.id) || 0) - (Number(b.id) || 0))
  const map = new Map<string, number>()
  sorted.forEach((o, idx) => map.set(String(o.id), idx + 1))
  let result = filteredOrders.value.map(o => ({ ...o, _rownum: map.get(String(o.id)) ?? '' }))
  // Apply localSort from column-header menus
  if (localSort.value) {
    const { key, order } = localSort.value
    result = [...result].sort((a, b) => {
      const av = getRowField(a, key)
      const bv = getRowField(b, key)
      // Numeric-aware: если оба числа, сравниваем как числа
      const an = typeof av === 'number' ? av : parseFloat(av)
      const bn = typeof bv === 'number' ? bv : parseFloat(bv)
      let cmp: number
      if (!isNaN(an) && !isNaN(bn)) cmp = an - bn
      else cmp = String(av ?? '').localeCompare(String(bv ?? ''), 'ru', { numeric: true })
      return order === 'asc' ? cmp : -cmp
    })
  }
  return result
})

// Cards pagination + selection (declared after filteredOrdersWithRowNum to avoid TDZ).
// cardsSource also applies the free-text `search` (which the v-data-table handled
// internally via :search — cards must replicate it to keep search interactive).
const cardsSource = computed(() => {
  const q = (search.value || '').trim().toLowerCase()
  if (!q) return filteredOrdersWithRowNum.value
  return filteredOrdersWithRowNum.value.filter((o: any) =>
    [o.registry_number, o.subject, o.item_name, o.contractor_name, o.subsidy_name, o.contract_number, o.order_number, o.agreement_number]
      .some(v => String(v ?? '').toLowerCase().includes(q))
  )
})
const cardsTotalPages = computed(() => Math.max(1, Math.ceil(cardsSource.value.length / cardsPageSize)))
const pagedCards = computed(() => { const s = (cardsPage.value - 1) * cardsPageSize; return cardsSource.value.slice(s, s + cardsPageSize) })
watch(cardsTotalPages, t => { if (cardsPage.value > t) cardsPage.value = t })
function isOrderSelected(item: any) { return selectedOrders.value.some((o: any) => o.id === item.id) }
function toggleOrderSelected(item: any) { const i = selectedOrders.value.findIndex((o: any) => o.id === item.id); if (i >= 0) selectedOrders.value.splice(i, 1); else selectedOrders.value.push(item) }

const filteredSum = computed(() =>
  filteredOrders.value.reduce((acc, o) => acc + (effectivePrice(o) ?? 0), 0)
)

const loadOrders = async () => {
  loading.value = true
  try {
    orders.value = await apiFetch<Purchase[]>('/purchases/?scope=purchases')
  } catch {
    showSnack('Ошибка загрузки закупок', 'error')
  } finally {
    loading.value = false
  }
}

const loadSubsidies = async () => {
  try {
    subsidies.value = await apiFetch<Subsidy[]>('/subsidies/')
    // Если ранее выбранная субсидия больше недоступна (доступ отозван) —
    // сбросить выбор на «все доступные», иначе в селекторе залипал сырой id.
    if (filterSubsidyId.value && !subsidies.value.some(s => s.id === filterSubsidyId.value)) {
      filterSubsidyId.value = null
      globalSubsidyId.value = null
    }
  } catch {}
}

const ordersTableRef = ref<any>(null)

// Phase 26-ZZ: bulk-load контрагентов убран. Фильтр контрагентов
// dedupe-by-name из orders, не требует справочника.
onMounted(async () => {
  loadOrders()
  loadSubsidies()
  loadFilterPresets()
  // Link task mode
  if (route.query.link_task) {
    linkTaskId.value = Number(route.query.link_task)
  }
  const qSub = route.query.subsidy_id
  if (qSub) {
    filterSubsidyId.value = Number(qSub)
    globalSubsidyId.value = Number(qSub)
  } else if (globalSubsidyId.value) {
    filterSubsidyId.value = globalSubsidyId.value
  }
  const qStatus = route.query.status
  if (qStatus && typeof qStatus === 'string') filterStatus.value = qStatus
  if (route.query.method)   filterMethod.value  = route.query.method as string
  if (route.query.overdue)  filterOverdue.value  = true
  if (route.query.due_soon) filterDueSoon.value  = true
  const qFeo = route.query.feo_category_id
  if (qFeo) {
    filterFeoCategoryId.value = Number(qFeo)
    // Find feo category name from loaded orders (or set generic label)
    filterFeoCategoryName.value = `ФЭО #${qFeo}`
    // Update name once orders load
    loadOrders().then(() => {
      const found = orders.value.find(o => o.feo_category_id === Number(qFeo))
      if (found?.feo_category_name) filterFeoCategoryName.value = found.feo_category_name
    })
  }

  // Enable column resize after table renders
  setTimeout(() => {
    const el = ordersTableRef.value?.$el?.querySelector('table') || document.querySelector('.v-data-table table')
    if (el) {
      el.setAttribute('data-resize-id', 'orders')
      addResizeHandles(el)
      restoreTableWidths(el)
    }
  }, 500)
})

// Bidirectional sync with global subsidy
watch(filterSubsidyId, (id: number | null) => { globalSubsidyId.value = id })
watch(globalSubsidyId, (id: number | null) => { filterSubsidyId.value = id })

const doTransition = async (item: Purchase) => {
  const target = nextStatus(item.status)
  if (!target) return
  const required = transitionRequired(item)[target]
  if (required) {
    const missing = required.filter(r => !item[r.field]).map(r => r.label)
    if (missing.length) {
      guardDialog.purchaseId = item.id
      guardDialog.targetStatus = target
      guardDialog.missing = missing
      guardDialog.isFramework = isItemFramework(item)
      guardDialog.show = true
      return
    }
  }
  transitioning.value = item.id
  try {
    await apiFetch(`/purchases/${item.id}/transition?status=${target}`, { method: 'POST' })
    showSnack(`Статус изменён → ${statusLabelFor(item, target)}`)
    await loadOrders()
  } catch (e: any) {
    showSnack(e?.detail || e?.message || 'Ошибка перехода', 'error')
  } finally {
    transitioning.value = null
  }
}

const doForceStatus = async (item: Purchase, status: string) => {
  if (item.status === status) return
  transitioning.value = item.id
  try {
    await apiFetch(`/purchases/${item.id}/transition?status=${status}`, { method: 'POST' })
    showSnack(`Статус изменён → ${statusLabelFor(item, status)}`)
    await loadOrders()
  } catch (e: any) {
    showSnack(e?.detail || e?.message || 'Ошибка изменения статуса', 'error')
  } finally {
    transitioning.value = null
  }
}

const confirmDeleteOne = (item: Purchase) => {
  deleteDialog.single = item
  deleteDialog.bulk = false
  deleteDialog.show = true
}

const confirmBulkDelete = () => {
  deleteDialog.single = null
  deleteDialog.bulk = true
  deleteDialog.show = true
}

const bulkChangeStatus = async (status: string) => {
  const ids = selectedOrders.value.map(o => o.id)
  let ok = 0, fail = 0
  for (const id of ids) {
    try {
      await apiFetch<any>(`/purchases/${id}/transition?status=${status}`, { method: 'POST' })
      const idx = orders.value.findIndex(o => o.id === id)
      if (idx >= 0) orders.value[idx].status = status
      ok++
    } catch { fail++ }
  }
  selectedOrders.value = []
  showSnack(`Обновлено: ${ok}${fail ? `, ошибок: ${fail}` : ''}`, fail ? 'warning' : 'success')
}

const doDelete = async () => {
  deleteDialog.deleting = true
  try {
    if (deleteDialog.bulk) {
      const ids = selectedOrders.value.map(o => o.id)
      const res = await apiFetch('/purchases/bulk', {
        method: 'DELETE',
        body: JSON.stringify(ids),
      })
      const deletedIds = new Set<number>(res.deleted)
      selectedOrders.value = selectedOrders.value.filter(o => !deletedIds.has(o.id))
      if (res.failed?.length) {
        showSnack(`Удалено: ${res.deleted.length}, не удалось: ${res.failed.length}`, 'warning')
      } else {
        showSnack(`Удалено ${res.deleted.length} закупок`, 'warning')
      }
    } else {
      await apiFetch(`/purchases/${deleteDialog.single!.id}`, { method: 'DELETE' })
      showSnack('Закупка удалена', 'warning')
    }
    deleteDialog.show = false
    await loadOrders()
  } catch (e: any) {
    showSnack(e?.detail || 'Ошибка удаления', 'error')
  } finally {
    deleteDialog.deleting = false
  }
}

// ─── Import ───────────────────────────────────────────────────────────────────
const _importCurrentUserId = parseInt(localStorage.getItem('user_id') || '0')
const importUserItems = ref<{ text: string; value: number }[]>([])

const importDialog = reactive({
  show: false,
  step: 1,
  format: 'standard' as 'standard' | 'feo',
  subsidyId: null as number | null,
  assignedUserId: _importCurrentUserId || null as number | null,
  file: null as File | null,
  loading: false,
  result: null as { created: number; skipped: number; errors: { row: number; name: string; message: string }[] } | null,
})

apiFetch<any[]>('/users/in-my-orgs').then(users => {
  importUserItems.value = users.map(u => ({ text: u.full_name || u.username, value: u.id }))
}).catch(() => {})

const resetImport = () => {
  importDialog.show = false
  importDialog.step = 1
  importDialog.format = 'standard'
  importDialog.file = null
  importDialog.subsidyId = null
  importDialog.assignedUserId = _importCurrentUserId || null
  importDialog.result = null
}

const downloadTemplate = async () => {
  const token = localStorage.getItem('auth_token')
  const url = importDialog.format === 'feo'
    ? '/api/purchases/import/feo-format/template'
    : '/api/purchases/import/template'
  const filename = importDialog.format === 'feo' ? 'feo_import_template.xlsx' : 'import_template.xlsx'
  const response = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
  if (!response.ok) return
  const blob = await response.blob()
  const blobUrl = window.URL.createObjectURL(blob)
  const a = document.createElement('a'); a.href = blobUrl; a.download = filename
  document.body.appendChild(a); a.click()
  window.URL.revokeObjectURL(blobUrl); document.body.removeChild(a)
}

const doImport = async () => {
  if (!importDialog.file) return
  importDialog.loading = true
  try {
    const formData = new FormData()
    formData.append('file', importDialog.file)
    const token = localStorage.getItem('auth_token')
    let endpoint: string
    if (importDialog.format === 'feo') {
      const qs = importDialog.assignedUserId ? `?assigned_user_id=${importDialog.assignedUserId}` : ''
      endpoint = `/api/purchases/import/feo-format${qs}`
    } else {
      const qs = importDialog.subsidyId ? `?subsidy_id=${importDialog.subsidyId}` : ''
      endpoint = `/api/purchases/import${qs}`
    }
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    })
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: 'Ошибка импорта' }))
      showSnack(err.detail || 'Ошибка импорта', 'error')
      return
    }
    importDialog.result = await response.json()
    importDialog.step = 2
    if ((importDialog.result?.created ?? 0) > 0) await loadOrders()
  } catch (e: any) {
    showSnack(e.message || 'Ошибка импорта', 'error')
  } finally {
    importDialog.loading = false
  }
}

// ---------------------------------------------------------------------------
// Excel export with configurable columns
// ---------------------------------------------------------------------------

interface ExportColumn { key: string; label: string; group: string }

const DEFAULT_EXPORT_KEYS = [
  'purchase_number', 'registry_number', 'item_name', 'item_type', 'unit', 'quantity',
  'nmck', 'contract_price', 'economy', 'purchase_method',
  'contract_number', 'contract_date', 'contractor',
  'execution_term', 'country_origin',
  'acceptance_doc_name', 'acceptance_doc_number', 'acceptance_doc_date', 'acceptance_doc_amount',
  'payment_doc_number', 'payment_doc_date', 'payment_amount', 'payment_federal',
  'status',
]
const SAVED_PRESET_KEY = 'export_columns_preset'

const exportDialog = reactive({
  show: false,
  loading: false,
  exporting: false,
  allColumns: [] as ExportColumn[],
  selected: [...DEFAULT_EXPORT_KEYS],
})

const exportColumnGroups = computed(() => {
  const map: Record<string, ExportColumn[]> = {}
  for (const col of exportDialog.allColumns) {
    if (!map[col.group]) map[col.group] = []
    map[col.group].push(col)
  }
  return Object.entries(map).map(([name, cols]) => ({ name, cols }))
})

const hasSavedPreset = computed(() => !!localStorage.getItem(SAVED_PRESET_KEY))
const savedPresetCount = computed(() => {
  try { return JSON.parse(localStorage.getItem(SAVED_PRESET_KEY) || '[]').length } catch { return 0 }
})

async function openExportDialog() {
  exportDialog.show = true
  if (exportDialog.allColumns.length === 0) {
    exportDialog.loading = true
    try {
      exportDialog.allColumns = await apiFetch<ExportColumn[]>('/purchases/export/columns')
    } finally {
      exportDialog.loading = false
    }
  }
}

function applyPreset(type: 'default' | 'all' | 'saved') {
  if (type === 'default') {
    exportDialog.selected = [...DEFAULT_EXPORT_KEYS]
  } else if (type === 'all') {
    exportDialog.selected = exportDialog.allColumns.map(c => c.key)
  } else {
    try {
      const saved = JSON.parse(localStorage.getItem(SAVED_PRESET_KEY) || '[]')
      if (saved.length) exportDialog.selected = saved
    } catch {}
  }
}

function savePreset() {
  localStorage.setItem(SAVED_PRESET_KEY, JSON.stringify(exportDialog.selected))
  showSnack('Пресет сохранён', 'success')
}

function toggleGroup(groupName: string, select: boolean) {
  const group = exportColumnGroups.value.find(g => g.name === groupName)
  if (!group) return
  const keys = group.cols.map(c => c.key)
  if (select) {
    exportDialog.selected = [...new Set([...exportDialog.selected, ...keys])]
  } else {
    exportDialog.selected = exportDialog.selected.filter(k => !keys.includes(k))
  }
}

async function doExport() {
  exportDialog.exporting = true
  try {
    const token = localStorage.getItem('auth_token')
    const params = new URLSearchParams()
    if (filterSubsidyId.value) params.set('subsidy_id', String(filterSubsidyId.value))
    if (filterStatus.value) params.set('status', filterStatus.value)
    params.set('columns', exportDialog.selected.join(','))
    const response = await fetch(`/api/purchases/export/excel?${params}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!response.ok) {
      let msg = `Ошибка экспорта (HTTP ${response.status})`
      try { const j = await response.json(); if (j?.message) msg = j.message } catch { /* not json */ }
      throw new Error(msg)
    }
    const missingRaw = response.headers.get('X-Missing-Columns')
    const missing = missingRaw ? decodeURIComponent(missingRaw) : null
    const blob = await response.blob()
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `zakupki_${new Date().toISOString().slice(0, 10)}.xlsx`
    document.body.appendChild(a)
    a.click()
    window.URL.revokeObjectURL(url)
    document.body.removeChild(a)
    exportDialog.show = false
    if (missing) {
      showSnack(`Предупреждение: мало данных в колонках: ${missing}`, 'warning')
    }
  } catch (e: any) {
    showSnack(e?.message || 'Ошибка экспорта', 'error')
  } finally {
    exportDialog.exporting = false
  }
}
</script>

<style scoped>
.orders-clickable :deep(tbody tr) { cursor: pointer; }
.import-result-row {
  display: flex; gap: 16px; justify-content: center; margin: 16px 0;
}
.import-stat {
  display: flex; flex-direction: column; align-items: center;
  padding: 16px 24px; border-radius: 10px; min-width: 100px;
}
.import-stat--ok   { background: rgba(34,197,94,0.1); }
.import-stat--skip { background: rgba(245,158,11,0.1); }
.import-stat--err  { background: rgba(239,68,68,0.1); }
.import-stat-val { font-size: 32px; font-weight: 700; color: var(--crm-text); }
.import-stat-lbl { font-size: 12px; color: var(--crm-text-muted); margin-top: 4px; }
.import-errors-list { max-height: 200px; overflow-y: auto; border: 1px solid var(--crm-border); border-radius: 8px; }
.fz-11 { font-size: 11px; }
.export-col-check { min-width: 180px; max-width: 220px; }
.border-b { border-bottom: 1px solid var(--crm-border-strong); }
.expand-items-table :deep(table) { table-layout: fixed; }
.expand-items-table :deep(td),
.expand-items-table :deep(th) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.expand-items-table :deep(td:first-child) {
  white-space: normal;
  word-break: break-word;
}
</style>
