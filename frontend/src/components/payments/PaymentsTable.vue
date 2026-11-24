<template>
  <div>
    <!-- Legend -->
    <PaymentsTableLegend />

    <div v-if="cellMarks.activeColorFilter.value?.payment" class="mb-2">
      <v-chip
        size="small"
        color="purple"
        variant="tonal"
        closable
        prepend-icon="mdi-palette"
        @click:close="cellMarks.setColorFilter('payment', null)"
      >
        🎨 Фильтр цвета: {{ cellMarks.activeColorFilter.value.payment }}
      </v-chip>
    </div>

    <v-data-table
      v-resizable-columns="'payment-registry'"
      :headers="headers"
      :items="displayItems"
      :loading="loading"
      density="compact"
      show-expand
      v-model:expanded="expanded"
      item-value="id"
      class="elevation-1 registry-colored-table"
      fixed-header
      height="calc(100vh - 350px)"
      :items-per-page="50"
      :items-per-page-options="[25, 50, 100]"
      :page="page"
      :row-props="getRowProps"
      @update:page="page = $event"
      @click:row="onRowClick"
    >
      <template
        v-for="col in headerMenuColumns"
        :key="col.key"
        #[`header.${col.key}`]="{ column }"
      >
        <ColumnHeaderMenu
          :col-key="col.key"
          :title="column.title"
          :col-type="col.type"
          :align="col.align"
          :items="col.type !== 'date' && col.type !== 'boolean' ? uniqValues(payments, col.key) : undefined"
          :model-value="colFilters[col.key] ?? null"
          :sort-by="getSortBy(col.key)"
          @update:model-value="v => setFilter(col.key, v)"
          @sort="dir => applySort(col.key, dir)"
          @hide="toggleVisible(col.key, false)"
        />
      </template>

      <!-- Index -->
      <template #item.index="{ index }">
        <span class="text-medium-emphasis">{{ (page - 1) * 50 + index + 1 }}</span>
      </template>

      <!-- Date -->
      <template #item.payment_date="{ item }">
        <span
          :class="cellMarks.getCellMarkClasses('payment', item.id, 'payment_date')"
          :style="cellMarks.getCellMarkStyle('payment', item.id, 'payment_date')"
          @click="onCellClick($event, { entityType: 'payment', entityId: item.id, fieldName: 'payment_date' })"
          @contextmenu.prevent="openPaymentCellMenu($event, item, 'payment_date', 'Дата платежа', fmtDate(item.payment_date))"
        >
          {{ fmtDate(item.payment_date) }}
        </span>
      </template>

      <!-- Payer -->
      <template #item.payer_name="{ item }">
        <div
          :class="cellMarks.getCellMarkClasses('payment', item.id, 'payer_name')"
          :style="cellMarks.getCellMarkStyle('payment', item.id, 'payer_name')"
          @click="onCellClick($event, { entityType: 'payment', entityId: item.id, fieldName: 'payer_name' })"
          @contextmenu.prevent="openPaymentCellMenu($event, item, 'payer_name', 'Плательщик', item.payer_name_resolved || item.payer_name)"
        >
          <div class="text-body-2">
            {{ item.payer_name_resolved || item.payer_name || '—' }}
          </div>
          <div v-if="item.payer_name_resolved && item.payer_name_resolved !== item.payer_name" class="text-caption text-medium-emphasis" :title="item.payer_name || ''">
            ({{ item.payer_name }})
          </div>
        </div>
      </template>

      <!-- Payee -->
      <template #item.payee_name="{ item }">
        <div
          :class="cellMarks.getCellMarkClasses('payment', item.id, 'payee_name')"
          :style="cellMarks.getCellMarkStyle('payment', item.id, 'payee_name')"
          @click="onCellClick($event, { entityType: 'payment', entityId: item.id, fieldName: 'payee_name' })"
          @contextmenu.prevent="openPaymentCellMenu($event, item, 'payee_name', 'Получатель', item.payee_name_resolved || item.payee_name)"
        >
          <div class="text-body-2">
            {{ item.payee_name_resolved || item.payee_name || '—' }}
          </div>
          <div v-if="item.payee_inn" class="text-caption text-medium-emphasis">ИНН {{ item.payee_inn }}</div>
        </div>
      </template>

      <!-- Amount -->
      <template #item.amount="{ item }">
        <span
          class="font-weight-medium"
          :class="cellMarks.getCellMarkClasses('payment', item.id, 'amount')"
          :style="cellMarks.getCellMarkStyle('payment', item.id, 'amount')"
          @click="onCellClick($event, { entityType: 'payment', entityId: item.id, fieldName: 'amount' })"
          @contextmenu.prevent="openPaymentCellMenu($event, item, 'amount', 'Сумма', item.amount, item.amount)"
        >
          {{ formatMoney(item.amount) }}
        </span>
      </template>

      <!-- Status chip -->
      <template #item.status="{ item }">
        <v-chip
          size="x-small"
          :color="statusColor(item.status)"
          variant="tonal"
          :class="cellMarks.getCellMarkClasses('payment', item.id, 'status')"
          :style="cellMarks.getCellMarkStyle('payment', item.id, 'status')"
          @click="onCellClick($event, { entityType: 'payment', entityId: item.id, fieldName: 'status' })"
          @contextmenu.prevent="openPaymentCellMenu($event, item, 'status', 'Статус', item.status)"
        >
          {{ item.status || '—' }}
        </v-chip>
      </template>

      <!-- Parsed contract / advance report / agreement -->
      <template #item.parsed_contract_number="{ item }">
        <span
          class="text-caption"
          :class="cellMarks.getCellMarkClasses('payment', item.id, 'parsed_contract_number')"
          :style="cellMarks.getCellMarkStyle('payment', item.id, 'parsed_contract_number')"
          @click="onCellClick($event, { entityType: 'payment', entityId: item.id, fieldName: 'parsed_contract_number' })"
          @contextmenu.prevent="openPaymentCellMenu($event, item, 'parsed_contract_number', 'Договор / Документ', docDisplay(item))"
        >
          {{ docDisplay(item) }}
        </span>
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
        <div class="d-flex align-center">
          <v-btn
            v-if="can(ACTIONS.PAYMENT_CONFIRM!)"
            icon
            size="x-small"
            variant="text"
            color="success"
            :disabled="!item.matched_contract_id"
            :title="item.matched_contract_id ? 'Подтвердить' : 'Сначала привяжите договор'"
            @click.stop="emit('confirm', item)"
          >
            <v-icon>mdi-check</v-icon>
          </v-btn>

          <v-btn
            icon
            size="x-small"
            variant="text"
            color="primary"
            title="Привязать договор"
            @click.stop="emit('match', item)"
          >
            <v-icon>mdi-link-variant</v-icon>
          </v-btn>

          <v-btn
            v-if="can(ACTIONS.PAYMENT_UNBIND!) && item.matched_confirmed"
            icon
            size="x-small"
            variant="text"
            color="warning"
            title="Откатить подтверждение"
            :loading="unbindingId === item.id"
            @click.stop="emit('unbind', item)"
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
              <div class="d-flex flex-wrap text-body-2 mb-2">
                <span><b>Назначение платежа:</b> {{ item.purpose_text || '—' }}</span>
              </div>
              <div class="d-flex flex-wrap text-caption text-medium-emphasis">
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
  </div>
</template>

<script setup lang="ts">
import { useAuthStore } from '@/stores/auth'
import { ACTIONS } from '@/constants/permissionActions'
import ColumnHeaderMenu from '@/components/ColumnHeaderMenu.vue'
import PaymentsTableLegend from './PaymentsTableLegend.vue'
import type { FilterValue } from '@/composables/useColumnConfig'
import type { BankPayment } from '@/composables/payments/paymentsTypes'
import { fmtDate, formatMoney, docDisplay, statusColor } from '@/composables/payments/paymentsFormat'
import { usePaymentsTableMarks, headerMenuColumns, resolveItemMatchedKind } from './usePaymentsTableMarks'

const authStore = useAuthStore()
function can(action: string) {
  return authStore.hasAction?.(action) ?? true
}

const expanded = defineModel<number[]>('expanded', { required: true })
const page = defineModel<number>('page', { required: true })

const props = defineProps<{
  headers: any[]
  items: any[]
  loading: boolean
  payments: BankPayment[]
  colFilters: Record<string, FilterValue>
  getSortBy: (k: string) => 'asc' | 'desc' | null
  setFilter: (key: string, value: any) => void
  applySort: (k: string, dir: 'asc' | 'desc' | null) => void
  toggleVisible: (key: string, visible: boolean) => void
  uniqValues: (rows: any[], key: string) => (string | number | null)[]
  unbindingId: number | null
}>()

const emit = defineEmits<{
  confirm: [item: BankPayment]
  match: [item: BankPayment]
  unbind: [item: BankPayment]
}>()

const { cellMarks, displayItems, onCellClick, openPaymentCellMenu } = usePaymentsTableMarks(props)

function getRowProps({ item }: { item: any }) {
  const kind = resolveItemMatchedKind(item)
  const baseClass =
    kind === 'goods'
      ? 'row-matched-goods clickable-registry-row'
      : kind === 'services'
      ? 'row-matched-services clickable-registry-row'
      : 'clickable-registry-row'
  const markClasses = cellMarks.getRowMarkClasses('payment', item.id)
  const markStyle = cellMarks.getRowMarkStyle('payment', item.id)
  return {
    class: [baseClass, markClasses],
    style: markStyle,
    'data-gala-focus': `payment:${item.id}`,
  }
}

function onRowClick(event: Event, { item }: { item: any }) {
  const target = event?.target as HTMLElement | null
  if (target && target.closest('a, button, input, .v-btn, .v-chip')) return
  emit('match', item)
}
</script>

<style scoped>
:deep(.v-data-table table),
:deep(table) {
  table-layout: auto !important;
}

:deep(.v-data-table td) {
  white-space: normal !important;
  word-break: break-word;
  vertical-align: top;
  padding-top: 8px;
  padding-bottom: 8px;
}
:deep(.clickable-registry-row) {
  cursor: pointer;
  transition: filter 0.12s ease;
}
:deep(.clickable-registry-row:hover) {
  filter: brightness(0.96);
}
:deep(.row-matched-goods),
:deep(.row-matched-goods > td) {
  background-color: #dcfce7 !important;
}
:deep(.row-matched-goods > td:first-child) {
  border-left: 4px solid #16a34a !important;
}
:deep(.row-matched-services),
:deep(.row-matched-services > td) {
  background-color: #f9ecc9 !important;
}
:deep(.row-matched-services > td:first-child) {
  border-left: 4px solid #d97706 !important;
}
/* Priority of user color marks over matched status colors */
:deep(tr[style*="background"] > td),
:deep(tr.gala-row-marked > td) {
  background-color: inherit !important;
}
</style>
