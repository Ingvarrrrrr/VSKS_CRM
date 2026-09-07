<template>
  <v-data-table
      v-resizable-columns="'orders'"
      ref="ordersTableRef"
      :headers="headers"
      :items="items"
      :loading="loading"
      :search="search"
      density="compact"
      hover
      show-expand
      show-select
      :model-value="selectedOrders"
      @update:model-value="v => emit('update:selectedOrders', v)"
      :expanded="expanded"
      @update:expanded="v => emit('update:expanded', v)"
      items-per-page="25"
      :items-per-page-options="[25, 50, 100]"
      return-object
      class="orders-clickable"
      @click:row="(_: any, { item }: any) => router.push(`/orders/${item.id}/edit`)"
    >
      <!-- Column header menus -->
      <template #header.registry_number="{ column }">
        <ColumnHeaderMenu col-key="registry_number" :title="String(column.title)" col-type="text"
          :model-value="colFilters['registry_number'] ?? null"
          :sort-by="getSortBy('registry_number')"
          @update:model-value="v => setFilter('registry_number', v)"
          @sort="dir => applySort('registry_number', dir)"
          @hide="toggleVisible('registry_number', false)" />
      </template>
      <template #header.subject="{ column }">
        <ColumnHeaderMenu col-key="subject" :title="String(column.title)" col-type="text"
          :model-value="colFilters['subject'] ?? null"
          :sort-by="getSortBy('subject')"
          @update:model-value="v => setFilter('subject', v)"
          @sort="dir => applySort('subject', dir)"
          @hide="toggleVisible('subject', false)" />
      </template>
      <template #header.contractor_name="{ column }">
        <ColumnHeaderMenu col-key="contractor_name" :title="String(column.title)" col-type="enum"
          :items="uniqValues(filteredOrders, 'contractor_name')"
          :model-value="colFilters['contractor_name'] ?? null"
          :sort-by="getSortBy('contractor_name')"
          @update:model-value="v => setFilter('contractor_name', v)"
          @sort="dir => applySort('contractor_name', dir)"
          @hide="toggleVisible('contractor_name', false)" />
      </template>
      <template #header.subsidy_name="{ column }">
        <ColumnHeaderMenu col-key="subsidy_name" :title="String(column.title)" col-type="enum"
          :items="uniqValues(filteredOrders, 'subsidy_name')"
          :model-value="colFilters['subsidy_name'] ?? null"
          :sort-by="getSortBy('subsidy_name')"
          @update:model-value="v => setFilter('subsidy_name', v)"
          @sort="dir => applySort('subsidy_name', dir)"
          @hide="toggleVisible('subsidy_name', false)" />
      </template>
      <template #header.effective_price="{ column }">
        <ColumnHeaderMenu col-key="effective_price" :title="String(column.title)" col-type="number"
          align="end"
          :model-value="colFilters['effective_price'] ?? null"
          :sort-by="getSortBy('effective_price')"
          @update:model-value="v => setFilter('effective_price', v)"
          @sort="dir => applySort('effective_price', dir)"
          @hide="toggleVisible('effective_price', false)" />
      </template>
      <template #header.contract_number="{ column }">
        <ColumnHeaderMenu col-key="contract_number" :title="String(column.title)" col-type="text"
          :model-value="colFilters['contract_number'] ?? null"
          :sort-by="getSortBy('contract_number')"
          @update:model-value="v => setFilter('contract_number', v)"
          @sort="dir => applySort('contract_number', dir)"
          @hide="toggleVisible('contract_number', false)" />
      </template>
      <template #header.contract_date="{ column }">
        <ColumnHeaderMenu col-key="contract_date" :title="String(column.title)" col-type="date"
          :model-value="colFilters['contract_date'] ?? null"
          :sort-by="getSortBy('contract_date')"
          @update:model-value="v => setFilter('contract_date', v)"
          @sort="dir => applySort('contract_date', dir)"
          @hide="toggleVisible('contract_date', false)" />
      </template>
      <template #header.purchase_type="{ column }">
        <ColumnHeaderMenu col-key="purchase_type" :title="String(column.title)" col-type="enum"
          :items="['one_time', 'framework_cumulative', 'framework_with_amount', 'advance', 'invoice']"
          :item-labels="{ one_time: 'Разовый', framework_cumulative: 'Рамочный (накопительный)', framework_with_amount: 'Рамочный (с суммой)', advance: 'Авансовый', invoice: 'По счёту' }"
          :model-value="colFilters['purchase_type'] ?? null"
          :sort-by="getSortBy('purchase_type')"
          @update:model-value="v => setFilter('purchase_type', v)"
          @sort="dir => applySort('purchase_type', dir)"
          @hide="toggleVisible('purchase_type', false)" />
      </template>
      <template #header.status="{ column }">
        <ColumnHeaderMenu col-key="status" :title="String(column.title)" col-type="enum"
          :items="STATUS_ORDER"
          :item-labels="STATUS_LABEL"
          :model-value="colFilters['status'] ?? null"
          :sort-by="getSortBy('status')"
          @update:model-value="v => setFilter('status', v)"
          @sort="dir => applySort('status', dir)"
          @hide="toggleVisible('status', false)" />
      </template>
      <template #header.approval_status="{ column }">
        <ColumnHeaderMenu col-key="approval_status" :title="String(column.title)" col-type="enum"
          :items="['in_progress', 'approved', 'rejected']"
          :item-labels="{ in_progress: 'На согласовании', approved: 'Согласовано', rejected: 'Отклонено' }"
          :model-value="colFilters['approval_status'] ?? null"
          :sort-by="getSortBy('approval_status')"
          @update:model-value="v => setFilter('approval_status', v)"
          @sort="dir => applySort('approval_status', dir)"
          @hide="toggleVisible('approval_status', false)" />
      </template>
      <!-- Phase 26-K: доп. соглашение и дата заказа -->
      <template #header.agreement_number="{ column }">
        <ColumnHeaderMenu col-key="agreement_number" :title="String(column.title)" col-type="text"
          :model-value="colFilters['agreement_number'] ?? null"
          :sort-by="getSortBy('agreement_number')"
          @update:model-value="v => setFilter('agreement_number', v)"
          @sort="dir => applySort('agreement_number', dir)"
          @hide="toggleVisible('agreement_number', false)" />
      </template>
      <template #header.agreement_date="{ column }">
        <ColumnHeaderMenu col-key="agreement_date" :title="String(column.title)" col-type="date"
          :model-value="colFilters['agreement_date'] ?? null"
          :sort-by="getSortBy('agreement_date')"
          @update:model-value="v => setFilter('agreement_date', v)"
          @sort="dir => applySort('agreement_date', dir)"
          @hide="toggleVisible('agreement_date', false)" />
      </template>
      <template #header.order_number="{ column }">
        <ColumnHeaderMenu col-key="order_number" :title="String(column.title)" col-type="text"
          :model-value="colFilters['order_number'] ?? null"
          :sort-by="getSortBy('order_number')"
          @update:model-value="v => setFilter('order_number', v)"
          @sort="dir => applySort('order_number', dir)"
          @hide="toggleVisible('order_number', false)" />
      </template>
      <template #header.order_date="{ column }">
        <ColumnHeaderMenu col-key="order_date" :title="String(column.title)" col-type="date"
          :model-value="colFilters['order_date'] ?? null"
          :sort-by="getSortBy('order_date')"
          @update:model-value="v => setFilter('order_date', v)"
          @sort="dir => applySort('order_date', dir)"
          @hide="toggleVisible('order_date', false)" />
      </template>
      <!-- Phase 26-N: денежные показатели по закупке -->
      <template #header.ordered_amount="{ column }">
        <ColumnHeaderMenu col-key="ordered_amount" :title="String(column.title)" col-type="number"
          :model-value="colFilters['ordered_amount'] ?? null"
          :sort-by="getSortBy('ordered_amount')"
          @update:model-value="v => setFilter('ordered_amount', v)"
          @sort="dir => applySort('ordered_amount', dir)"
          @hide="toggleVisible('ordered_amount', false)" />
      </template>
      <template #header.delivered_amount="{ column }">
        <ColumnHeaderMenu col-key="delivered_amount" :title="String(column.title)" col-type="number"
          :model-value="colFilters['delivered_amount'] ?? null"
          :sort-by="getSortBy('delivered_amount')"
          @update:model-value="v => setFilter('delivered_amount', v)"
          @sort="dir => applySort('delivered_amount', dir)"
          @hide="toggleVisible('delivered_amount', false)" />
      </template>
      <template #header.paid_amount="{ column }">
        <ColumnHeaderMenu col-key="paid_amount" :title="String(column.title)" col-type="number"
          :model-value="colFilters['paid_amount'] ?? null"
          :sort-by="getSortBy('paid_amount')"
          @update:model-value="v => setFilter('paid_amount', v)"
          @sort="dir => applySort('paid_amount', dir)"
          @hide="toggleVisible('paid_amount', false)" />
      </template>
      <template #header.diff_ordered_delivered="{ column }">
        <ColumnHeaderMenu col-key="diff_ordered_delivered" :title="String(column.title)" col-type="number"
          :model-value="colFilters['diff_ordered_delivered'] ?? null"
          :sort-by="getSortBy('diff_ordered_delivered')"
          @update:model-value="v => setFilter('diff_ordered_delivered', v)"
          @sort="dir => applySort('diff_ordered_delivered', dir)"
          @hide="toggleVisible('diff_ordered_delivered', false)" />
      </template>
      <template #header.diff_delivered_paid="{ column }">
        <ColumnHeaderMenu col-key="diff_delivered_paid" :title="String(column.title)" col-type="number"
          :model-value="colFilters['diff_delivered_paid'] ?? null"
          :sort-by="getSortBy('diff_delivered_paid')"
          @update:model-value="v => setFilter('diff_delivered_paid', v)"
          @sort="dir => applySort('diff_delivered_paid', dir)"
          @hide="toggleVisible('diff_delivered_paid', false)" />
      </template>
      <template #header.diff_ordered_paid="{ column }">
        <ColumnHeaderMenu col-key="diff_ordered_paid" :title="String(column.title)" col-type="number"
          :model-value="colFilters['diff_ordered_paid'] ?? null"
          :sort-by="getSortBy('diff_ordered_paid')"
          @update:model-value="v => setFilter('diff_ordered_paid', v)"
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
        <!-- Владелец, 2026-08-13: остановка закупки — крупный алерт на всю ширину -->
        <div v-if="item.stopped_at" class="purchase-stopped-banner">
          <v-icon icon="mdi-alert-octagon" size="18" class="mr-1" />
          <span class="purchase-stopped-banner__title">ЗАКУПКА ОСТАНОВЛЕНА</span>
          <span class="purchase-stopped-banner__meta">{{ stoppedPurchaseLine(item) }}</span>
        </div>
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
        <div v-if="!item.contractor_name || !item.feo_category_id || !item.execution_term || !(item.planned_total_price) || dupGroupFor(item)" class="d-flex flex-wrap ga-1 mt-1">
          <v-chip v-if="!item.contractor_name" size="x-small" color="error" variant="tonal" prepend-icon="mdi-domain-off">Контрагент</v-chip>
          <v-chip v-if="!item.feo_category_id" size="x-small" color="warning" variant="tonal" prepend-icon="mdi-tag-off">ФЭО</v-chip>
          <v-chip v-if="!item.execution_term" size="x-small" color="warning" variant="tonal" prepend-icon="mdi-calendar-alert">Срок</v-chip>
          <v-chip v-if="!item.planned_total_price" size="x-small" color="warning" variant="tonal" prepend-icon="mdi-currency-rub">Сумма</v-chip>
          <!-- Возможный дубликат: та же субсидия + контрагент + сумма (ежемесячные платежи исключены на бэке) -->
          <v-tooltip v-if="dupGroupFor(item)" location="top" max-width="380" open-on-click>
            <template #activator="{ props: dupTp }">
              <v-chip v-bind="dupTp" size="x-small" color="warning" variant="tonal" prepend-icon="mdi-content-duplicate">
                возможный дубликат
              </v-chip>
            </template>
            <div class="text-caption font-weight-bold mb-1">Возможный дубликат</div>
            <div class="text-caption mb-2">
              Та же субсидия, тот же контрагент и та же сумма. Проверьте — это разные закупки или дубль.
            </div>
            <div class="text-caption font-weight-medium">
              {{ dupGroupFor(item)?.contractor_name || '—' }}
              <template v-if="dupGroupFor(item)?.amount != null"> · {{ dupGroupFor(item).amount.toLocaleString('ru-RU') }} ₽</template>
            </div>
            <ul class="text-caption ml-4 mb-0">
              <li v-for="dp in dupGroupFor(item)?.items?.filter((x: any) => x.id !== item.id)" :key="dp.id">
                <a :href="`/orders/${dp.id}/edit`" target="_blank" rel="noopener" style="color:#fff; text-decoration:underline">
                  {{ dp.registry_number || ('№' + dp.purchase_number) }} — {{ dp.name || 'без названия' }}
                </a>
                <template v-if="dp.status"> · {{ dp.status }}</template>
              </li>
            </ul>
          </v-tooltip>
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

      <!-- Контрагент (продавец) — отдельно от «кому возмещать» (см. выше). -->
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
            {{ purchaseSubstatusLabel(item.substatus) || item.substatus }}
          </v-chip>
          <v-icon v-if="item.is_monthly_payment" size="x-small" color="blue" title="Ежемесячный платёж">mdi-calendar-sync</v-icon>
          <!-- Значок превышения ФЭО (см. feoExcessChip). -->
          <v-chip v-if="item.feo_excess" size="x-small" :color="feoExcessChip(item).color" variant="flat"
            :title="feoExcessChip(item).title"
          >
            <v-icon icon="mdi-alert-decagram" size="12" class="mr-1" />{{ feoExcessChip(item).text }}
          </v-chip>
          <!-- Расхождение категории ФЭО шапки/товара/плановой позиции. -->
          <v-tooltip v-if="item.feo_mismatch" location="top" max-width="380">
            <template #activator="{ props: mmTp }">
              <v-chip v-bind="mmTp" size="x-small" color="amber-darken-3" variant="flat">
                <v-icon icon="mdi-alert" size="12" class="mr-1" />Расхождение ФЭО
              </v-chip>
            </template>
            <div class="text-caption font-weight-bold mb-1">Расхождение категории ФЭО</div>
            <ul class="text-caption ml-4 mb-0">
              <li v-for="mi in (item.feo_mismatch_items || [])" :key="mi.item_id">{{ mi.message }}</li>
            </ul>
          </v-tooltip>
        </div>
      </template>

      <template #item.effective_price="{ item }">
        {{ formatMoney(effectivePrice(item)) }}
      </template>

      <!-- phase26-m: для рамочного — framework_contract_total (max_amount or SUM) -->
      <template #item.contract_price="{ item }">
        {{ formatMoney(getRowField(item, 'contract_price')) }}
      </template>

      <!-- Phase 26-N: денежные показатели по закупке -->
      <template #item.ordered_amount="{ item }">
        {{ getRowField(item, 'ordered_amount') != null ? formatMoney(getRowField(item, 'ordered_amount')) : '—' }}
      </template>
      <template #item.delivered_amount="{ item }">
        {{ getRowField(item, 'delivered_amount') != null ? formatMoney(getRowField(item, 'delivered_amount')) : '—' }}
      </template>
      <template #item.paid_amount="{ item }">
        {{ getRowField(item, 'paid_amount') != null ? formatMoney(getRowField(item, 'paid_amount')) : '—' }}
      </template>
      <template #item.diff_ordered_delivered="{ item }">
        {{ getRowField(item, 'diff_ordered_delivered') != null ? formatMoney(getRowField(item, 'diff_ordered_delivered')) : '—' }}
      </template>
      <template #item.diff_delivered_paid="{ item }">
        {{ getRowField(item, 'diff_delivered_paid') != null ? formatMoney(getRowField(item, 'diff_delivered_paid')) : '—' }}
      </template>
      <template #item.diff_ordered_paid="{ item }">
        {{ getRowField(item, 'diff_ordered_paid') != null ? formatMoney(getRowField(item, 'diff_ordered_paid')) : '—' }}
      </template>

      <!-- Подтверждённая сумма — основная; заявленная (не подтв.) слабее визуально. -->
      <template #item.payment_amount="{ item }">
        <span v-if="item.payment_amount != null" class="font-weight-bold text-green">{{ formatMoney(Number(item.payment_amount)) }}</span>
        <span v-else class="text-medium-emphasis">—</span>
      </template>
      <template #item.payment_amount_declared="{ item }">
        <v-tooltip v-if="item.payment_amount_declared != null" location="top" text="Отмечено человеком, без подтверждения казначейской выпиской">
          <template #activator="{ props: tp }">
            <span v-bind="tp" class="text-caption text-orange-darken-2">{{ formatMoney(Number(item.payment_amount_declared)) }}</span>
          </template>
        </v-tooltip>
        <span v-else class="text-medium-emphasis">—</span>
      </template>

      <template #item.contract_date="{ item }">
        {{ item.contract_date ? formatDate(item.contract_date) : '—' }}
      </template>

      <template #item.subsidy_name="{ item }">
        <span class="text-body-2">
          {{ item.subsidy_name || '—' }}
        </span>
      </template>

      <template #item.event_name="{ item }">
        <span v-if="item.event_name" class="text-body-2">{{ item.event_name }}</span>
        <v-tooltip v-else location="top" text="Мероприятие не привязано">
          <template #activator="{ props: tooltipProps }">
            <v-icon v-bind="tooltipProps" icon="mdi-calendar-alert" color="warning" size="20" />
          </template>
        </v-tooltip>
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
            @click.stop="emit('transition', item)"
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
                @click="emit('force-status', item, s.value)"
              />
            </v-list>
          </v-menu>
          <v-btn v-if="linkTaskId" size="x-small" variant="tonal" color="deep-purple"
            prepend-icon="mdi-link-variant" @click.stop="emit('link-task', item.id)">
            Привязать
          </v-btn>
          <v-spacer />
          <!-- Phase 32: file badge -->
          <v-chip
            v-if="(item.files_count ?? 0) > 0"
            size="x-small" variant="tonal" color="teal"
            prepend-icon="mdi-paperclip"
            class="cursor-pointer"
            :title="`${item.files_count} файл(ов)`"
            @click.stop="emit('open-files', item)"
          >{{ item.files_count }}</v-chip>
          <v-btn v-if="isAdmin" icon="mdi-delete" variant="text" size="small" color="error" @click.stop="emit('delete-one', item)" />
        </div>
      </template>

      <!-- Expanded row: items list -->
      <template #expanded-row="{ columns, item }">
        <tr>
          <td :colspan="columns.length" class="pa-0 bg-grey-lighten-5">
            <div class="pa-3">
              <div v-if="item.stopped_at" class="purchase-stopped-banner mb-3">
                <v-icon icon="mdi-alert-octagon" size="18" class="mr-1" />
                <span class="purchase-stopped-banner__title">ЗАКУПКА ОСТАНОВЛЕНА</span>
                <span class="purchase-stopped-banner__meta">{{ stoppedPurchaseLine(item) }}</span>
              </div>
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
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import ColumnHeaderMenu from '@/components/ColumnHeaderMenu.vue'
import { formatMoney } from '@/utils/formatMoney'
import { purchaseSubstatusLabel } from '@/constants/purchaseStatus'
import { addResizeHandles, restoreTableWidths } from '@/composables/useTableResize'
import { getRowField, uniqValues } from '@/composables/orders/useOrdersColumns'
import {
  STATUS_ORDER, STATUS_LABEL, STATUS_COLOR, APPROVAL_STATUS_COLOR, APPROVAL_STATUS_LABEL,
  effectivePrice, formatDate, statusLabelFor, purchaseTypeLabel, purchaseTypeColor,
  purchaseMethodLabel, feoExcessChip, stoppedPurchaseLine, itemDisplayName, nextStatus,
} from '@/composables/orders/ordersLabels'
import type { Purchase } from '@/composables/orders/ordersTypes'
import type { FilterValue } from '@/composables/useColumnConfig'

const props = defineProps<{
  headers: any[]
  items: any[]
  filteredOrders: Purchase[]
  loading: boolean
  search: string
  selectedOrders: Purchase[]
  expanded: string[]
  colFilters: Record<string, FilterValue>
  getSortBy: (k: string) => 'asc' | 'desc' | null
  applySort: (k: string, dir: 'asc' | 'desc' | null) => void
  setFilter: (k: string, v: FilterValue | null) => void
  toggleVisible: (k: string, v: boolean) => void
  dupGroupFor: (item: any) => any
  isAdmin: boolean
  transitioning: number | null
  linkTaskId: number | null
  statusItems: { value: string; label: string; color: string }[]
}>()

const emit = defineEmits<{
  'update:selectedOrders': [v: Purchase[]]
  'update:expanded': [v: string[]]
  transition: [item: Purchase]
  'force-status': [item: Purchase, status: string]
  'link-task': [id: number]
  'delete-one': [item: Purchase]
  'open-files': [item: Purchase]
}>()

const router = useRouter()
const ordersTableRef = ref<any>(null)

onMounted(() => {
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
</script>

<style scoped>
.orders-clickable :deep(tbody tr) { cursor: pointer; }
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

/* Владелец, 2026-08-13: «остановка закупки» — крупный алерт в красной рамке, а
   не мелкий чип (тот же приём, что и wish-stopped-banner в WishesView.vue). */
.purchase-stopped-banner {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  column-gap: 10px;
  row-gap: 2px;
  width: 100%;
  border: 2px solid #d32f2f;
  background: #fdecea;
  color: #b71c1c;
  border-radius: 6px;
  padding: 6px 10px;
  margin-bottom: 6px;
}
.purchase-stopped-banner__title {
  font-weight: 800;
  font-size: 0.92rem;
  letter-spacing: 0.02em;
}
.purchase-stopped-banner__meta {
  font-size: 0.78rem;
  font-weight: 500;
  opacity: 0.9;
}
</style>
