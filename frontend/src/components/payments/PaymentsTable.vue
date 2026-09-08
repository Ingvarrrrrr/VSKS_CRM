<template>
  <v-data-table
    v-resizable-columns="'payment-registry'"
    :headers="headers"
    :items="items"
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
        :model-value="colFilters['payment_number'] ?? null"
        :sort-by="getSortBy('payment_number')"
        @update:model-value="v => setFilter('payment_number', v)"
        @sort="dir => applySort('payment_number', dir)"
        @hide="toggleVisible('payment_number', false)" />
    </template>
    <template #header.payer_name="{ column }">
      <ColumnHeaderMenu col-key="payer_name" :title="column.title" col-type="text"
        :model-value="colFilters['payer_name'] ?? null"
        :sort-by="getSortBy('payer_name')"
        @update:model-value="v => setFilter('payer_name', v)"
        @sort="dir => applySort('payer_name', dir)"
        @hide="toggleVisible('payer_name', false)" />
    </template>
    <template #header.payee_name="{ column }">
      <ColumnHeaderMenu col-key="payee_name" :title="column.title" col-type="text"
        :model-value="colFilters['payee_name'] ?? null"
        :sort-by="getSortBy('payee_name')"
        @update:model-value="v => setFilter('payee_name', v)"
        @sort="dir => applySort('payee_name', dir)"
        @hide="toggleVisible('payee_name', false)" />
    </template>
    <template #header.payer_inn="{ column }">
      <ColumnHeaderMenu col-key="payer_inn" :title="column.title" col-type="text"
        :model-value="colFilters['payer_inn'] ?? null"
        :sort-by="getSortBy('payer_inn')"
        @update:model-value="v => setFilter('payer_inn', v)"
        @sort="dir => applySort('payer_inn', dir)"
        @hide="toggleVisible('payer_inn', false)" />
    </template>
    <template #header.payee_inn="{ column }">
      <ColumnHeaderMenu col-key="payee_inn" :title="column.title" col-type="text"
        :model-value="colFilters['payee_inn'] ?? null"
        :sort-by="getSortBy('payee_inn')"
        @update:model-value="v => setFilter('payee_inn', v)"
        @sort="dir => applySort('payee_inn', dir)"
        @hide="toggleVisible('payee_inn', false)" />
    </template>
    <template #header.purpose_text="{ column }">
      <ColumnHeaderMenu col-key="purpose_text" :title="column.title" col-type="text"
        :model-value="colFilters['purpose_text'] ?? null"
        :sort-by="getSortBy('purpose_text')"
        @update:model-value="v => setFilter('purpose_text', v)"
        @sort="dir => applySort('purpose_text', dir)"
        @hide="toggleVisible('purpose_text', false)" />
    </template>
    <template #header.parsed_contract_number="{ column }">
      <ColumnHeaderMenu col-key="parsed_contract_number" :title="column.title" col-type="text"
        :model-value="colFilters['parsed_contract_number'] ?? null"
        :sort-by="getSortBy('parsed_contract_number')"
        @update:model-value="v => setFilter('parsed_contract_number', v)"
        @sort="dir => applySort('parsed_contract_number', dir)"
        @hide="toggleVisible('parsed_contract_number', false)" />
    </template>
    <template #header.parsed_kbk="{ column }">
      <ColumnHeaderMenu col-key="parsed_kbk" :title="column.title" col-type="text"
        :model-value="colFilters['parsed_kbk'] ?? null"
        :sort-by="getSortBy('parsed_kbk')"
        @update:model-value="v => setFilter('parsed_kbk', v)"
        @sort="dir => applySort('parsed_kbk', dir)"
        @hide="toggleVisible('parsed_kbk', false)" />
    </template>
    <template #header.expense_code="{ column }">
      <ColumnHeaderMenu col-key="expense_code" :title="column.title" col-type="text"
        :model-value="colFilters['expense_code'] ?? null"
        :sort-by="getSortBy('expense_code')"
        @update:model-value="v => setFilter('expense_code', v)"
        @sort="dir => applySort('expense_code', dir)"
        @hide="toggleVisible('expense_code', false)" />
    </template>
    <template #header.status="{ column }">
      <ColumnHeaderMenu col-key="status" :title="column.title" col-type="enum"
        :items="uniqValues(payments, 'status')"
        :model-value="colFilters['status'] ?? null"
        :sort-by="getSortBy('status')"
        @update:model-value="v => setFilter('status', v)"
        @sort="dir => applySort('status', dir)"
        @hide="toggleVisible('status', false)" />
    </template>
    <template #header.matched="{ column }">
      <ColumnHeaderMenu col-key="matched" :title="column.title" col-type="boolean"
        :model-value="colFilters['matched'] ?? null"
        :sort-by="getSortBy('matched')"
        @update:model-value="v => setFilter('matched', v)"
        @sort="dir => applySort('matched', dir)"
        @hide="toggleVisible('matched', false)" />
    </template>
    <template #header.matched_confirmed="{ column }">
      <ColumnHeaderMenu col-key="matched_confirmed" :title="column.title" col-type="boolean"
        :model-value="colFilters['matched_confirmed'] ?? null"
        :sort-by="getSortBy('matched_confirmed')"
        @update:model-value="v => setFilter('matched_confirmed', v)"
        @sort="dir => applySort('matched_confirmed', dir)"
        @hide="toggleVisible('matched_confirmed', false)" />
    </template>
    <template #header.amount="{ column }">
      <ColumnHeaderMenu col-key="amount" :title="column.title" col-type="number"
        :model-value="colFilters['amount'] ?? null"
        :sort-by="getSortBy('amount')"
        align="end"
        @update:model-value="v => setFilter('amount', v)"
        @sort="dir => applySort('amount', dir)"
        @hide="toggleVisible('amount', false)" />
    </template>
    <template #header.payment_date="{ column }">
      <ColumnHeaderMenu col-key="payment_date" :title="column.title" col-type="date"
        :model-value="colFilters['payment_date'] ?? null"
        :sort-by="getSortBy('payment_date')"
        @update:model-value="v => setFilter('payment_date', v)"
        @sort="dir => applySort('payment_date', dir)"
        @hide="toggleVisible('payment_date', false)" />
    </template>
    <template #header.parsed_contract_date="{ column }">
      <ColumnHeaderMenu col-key="parsed_contract_date" :title="column.title" col-type="date"
        :model-value="colFilters['parsed_contract_date'] ?? null"
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

        <!-- Match/re-link button -->
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

        <!-- Unbind button -->
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
</template>

<script setup lang="ts">
import { useAuthStore } from '@/stores/auth'
import { ACTIONS } from '@/constants/permissionActions'
import ColumnHeaderMenu from '@/components/ColumnHeaderMenu.vue'
import type { FilterValue } from '@/composables/useColumnConfig'
import type { BankPayment } from '@/composables/payments/paymentsTypes'
import { fmtDate, formatMoney, docDisplay, statusColor } from '@/composables/payments/paymentsFormat'

const authStore = useAuthStore()
function can(action: string) {
  return authStore.hasAction?.(action) ?? true
}

const expanded = defineModel<number[]>('expanded', { required: true })
const page = defineModel<number>('page', { required: true })

defineProps<{
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
