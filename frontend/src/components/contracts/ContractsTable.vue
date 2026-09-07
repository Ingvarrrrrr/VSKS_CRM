<template>
  <v-data-table
    v-resizable-columns="'contracts'"
    :headers="headers"
    :items="items"
    :loading="loading"
    density="compact"
    show-expand
    v-model:expanded="expanded"
    item-value="id"
    class="elevation-1"
    items-per-page="50"
    :items-per-page-options="[25,50,100,-1]"
    :sort-by="localSort ? [localSort] : []"
    @click:row="(_e: any, { item }: any) => emit('edit', item)"
    style="cursor: pointer"
  >
    <!-- ColumnHeaderMenu slots -->
    <template #header.number="{ column }">
      <ColumnHeaderMenu col-key="number" :title="column.title" col-type="text"
        :model-value="colFilters['number'] ?? null"
        :sort-by="getSortBy('number')"
        @update:model-value="v => setFilter('number', v)"
        @sort="dir => applySort('number', dir)"
        @hide="toggleVisible('number', false)"
      />
    </template>
    <template #header.date="{ column }">
      <ColumnHeaderMenu col-key="date" :title="column.title" col-type="date"
        :model-value="colFilters['date'] ?? null"
        :sort-by="getSortBy('date')"
        @update:model-value="v => setFilter('date', v)"
        @sort="dir => applySort('date', dir)"
        @hide="toggleVisible('date', false)"
      />
    </template>
    <template #header.contract_type="{ column }">
      <ColumnHeaderMenu col-key="contract_type" :title="column.title" col-type="enum"
        :items="uniqValues(contracts, 'contract_type')"
        :item-labels="contractTypeLabels"
        :model-value="colFilters['contract_type'] ?? null"
        :sort-by="getSortBy('contract_type')"
        @update:model-value="v => setFilter('contract_type', v)"
        @sort="dir => applySort('contract_type', dir)"
        @hide="toggleVisible('contract_type', false)"
      />
    </template>
    <template #header.purchase_method="{ column }">
      <ColumnHeaderMenu col-key="purchase_method" :title="column.title" col-type="enum"
        :items="uniqValues(contracts, 'purchase_method')"
        :item-labels="purchaseMethodLabels"
        :model-value="colFilters['purchase_method'] ?? null"
        :sort-by="getSortBy('purchase_method')"
        @update:model-value="v => setFilter('purchase_method', v)"
        @sort="dir => applySort('purchase_method', dir)"
        @hide="toggleVisible('purchase_method', false)"
      />
    </template>
    <template #header.contractor_name="{ column }">
      <ColumnHeaderMenu col-key="contractor_name" :title="column.title" col-type="text"
        :model-value="colFilters['contractor_name'] ?? null"
        :sort-by="getSortBy('contractor_name')"
        @update:model-value="v => setFilter('contractor_name', v)"
        @sort="dir => applySort('contractor_name', dir)"
        @hide="toggleVisible('contractor_name', false)"
      />
    </template>
    <template #header.subsidy_name="{ column }">
      <ColumnHeaderMenu col-key="subsidy_name" :title="column.title" col-type="enum"
        :items="uniqValues(contracts, 'subsidy_name')"
        :model-value="colFilters['subsidy_name'] ?? null"
        :sort-by="getSortBy('subsidy_name')"
        @update:model-value="v => setFilter('subsidy_name', v)"
        @sort="dir => applySort('subsidy_name', dir)"
        @hide="toggleVisible('subsidy_name', false)"
      />
    </template>
    <template #header.max_amount="{ column }">
      <ColumnHeaderMenu col-key="max_amount" :title="column.title" col-type="number" align="end"
        :model-value="colFilters['max_amount'] ?? null"
        :sort-by="getSortBy('max_amount')"
        @update:model-value="v => setFilter('max_amount', v)"
        @sort="dir => applySort('max_amount', dir)"
        @hide="toggleVisible('max_amount', false)"
      />
    </template>
    <template #header.total_ordered="{ column }">
      <ColumnHeaderMenu col-key="total_ordered" :title="column.title" col-type="number" align="end"
        :model-value="colFilters['total_ordered'] ?? null"
        :sort-by="getSortBy('total_ordered')"
        @update:model-value="v => setFilter('total_ordered', v)"
        @sort="dir => applySort('total_ordered', dir)"
        @hide="toggleVisible('total_ordered', false)"
      />
    </template>
    <template #header.total_delivered="{ column }">
      <ColumnHeaderMenu col-key="total_delivered" :title="column.title" col-type="number" align="end"
        :model-value="colFilters['total_delivered'] ?? null"
        :sort-by="getSortBy('total_delivered')"
        @update:model-value="v => setFilter('total_delivered', v)"
        @sort="dir => applySort('total_delivered', dir)"
        @hide="toggleVisible('total_delivered', false)"
      />
    </template>
    <template #header.total_paid="{ column }">
      <ColumnHeaderMenu col-key="total_paid" :title="column.title" col-type="number" align="end"
        :model-value="colFilters['total_paid'] ?? null"
        :sort-by="getSortBy('total_paid')"
        @update:model-value="v => setFilter('total_paid', v)"
        @sort="dir => applySort('total_paid', dir)"
        @hide="toggleVisible('total_paid', false)"
      />
    </template>
    <template #header.remaining_ordered="{ column }">
      <ColumnHeaderMenu col-key="remaining_ordered" :title="column.title" col-type="number" align="end"
        :model-value="colFilters['remaining_ordered'] ?? null"
        :sort-by="getSortBy('remaining_ordered')"
        @update:model-value="v => setFilter('remaining_ordered', v)"
        @sort="dir => applySort('remaining_ordered', dir)"
        @hide="toggleVisible('remaining_ordered', false)"
      />
    </template>
    <template #header.remaining_delivered="{ column }">
      <ColumnHeaderMenu col-key="remaining_delivered" :title="column.title" col-type="number" align="end"
        :model-value="colFilters['remaining_delivered'] ?? null"
        :sort-by="getSortBy('remaining_delivered')"
        @update:model-value="v => setFilter('remaining_delivered', v)"
        @sort="dir => applySort('remaining_delivered', dir)"
        @hide="toggleVisible('remaining_delivered', false)"
      />
    </template>
    <template #header.remaining_paid="{ column }">
      <ColumnHeaderMenu col-key="remaining_paid" :title="column.title" col-type="number" align="end"
        :model-value="colFilters['remaining_paid'] ?? null"
        :sort-by="getSortBy('remaining_paid')"
        @update:model-value="v => setFilter('remaining_paid', v)"
        @sort="dir => applySort('remaining_paid', dir)"
        @hide="toggleVisible('remaining_paid', false)"
      />
    </template>
    <template #header.subject="{ column }">
      <ColumnHeaderMenu col-key="subject" :title="column.title" col-type="text"
        :model-value="colFilters['subject'] ?? null"
        :sort-by="getSortBy('subject')"
        @update:model-value="v => setFilter('subject', v)"
        @sort="dir => applySort('subject', dir)"
        @hide="toggleVisible('subject', false)"
      />
    </template>
    <template #header.end_date="{ column }">
      <ColumnHeaderMenu col-key="end_date" :title="column.title" col-type="date"
        :model-value="colFilters['end_date'] ?? null"
        :sort-by="getSortBy('end_date')"
        @update:model-value="v => setFilter('end_date', v)"
        @sort="dir => applySort('end_date', dir)"
        @hide="toggleVisible('end_date', false)"
      />
    </template>
    <template #header.status="{ column }">
      <ColumnHeaderMenu col-key="status" :title="column.title" col-type="enum"
        :items="uniqValues(contracts, 'status')"
        :item-labels="statusLabels"
        :model-value="colFilters['status'] ?? null"
        :sort-by="getSortBy('status')"
        @update:model-value="v => setFilter('status', v)"
        @sort="dir => applySort('status', dir)"
        @hide="toggleVisible('status', false)"
      />
    </template>
    <template #header.notes="{ column }">
      <ColumnHeaderMenu col-key="notes" :title="column.title" col-type="text"
        :model-value="colFilters['notes'] ?? null"
        :sort-by="getSortBy('notes')"
        @update:model-value="v => setFilter('notes', v)"
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
      <!-- Владелец, 2026-09-02: рамочная голова без согласования — затемнение
           строки + плашка «ТРЕБУЕТСЯ СОГЛАСОВАНИЕ», по образцу
           .purchase-stopped-banner из OrdersView.vue (тот же приём, тот же
           принцип наложения — не блюр). -->
      <div v-if="item.approval_state === 'pending'" class="contract-approval-pending-banner">
        <v-icon icon="mdi-shield-alert-outline" size="18" class="mr-1" />
        <span class="contract-approval-pending-banner__title">ТРЕБУЕТСЯ СОГЛАСОВАНИЕ</span>
        <span class="contract-approval-pending-banner__meta">Рамочный договор ждёт согласования по цепочке руководителей</span>
      </div>
      <span class="text-caption" :title="item.subject">{{ item.subject ? (item.subject.length > 60 ? item.subject.slice(0, 60) + '...' : item.subject) : '—' }}</span>
    </template>
    <template #item.item_type="{ item }">
      <v-chip v-if="item.item_type" size="x-small" :color="item.item_type === 'услуга' ? 'blue' : 'teal'" variant="tonal">
        {{ item.item_type === 'услуга' ? 'Услуги' : 'Товары' }}
      </v-chip>
      <span v-else class="text-medium-emphasis">—</span>
    </template>
    <!-- Phase 26-III: per-row delete -->
    <template #item.actions="{ item }">
      <v-btn
        v-if="isAdmin"
        icon="mdi-delete"
        variant="text"
        size="small"
        color="error"
        @click.stop="emit('confirm-delete', item)"
      />
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
                      {{ p.registry_number || p.purchase_number || p.id }}
                    </td>
                    <td class="text-caption">{{ p.subject || p.item_name || '—' }}</td>
                    <!-- ПРАВИЛО №6 (2026-09-05/06): «Сумма» закупки — единый расчёт бэкенда
                         (amounts.effective), не сырой contract_price — см. заголовок
                         «Цена договора» контракта выше (item.max_amount) для того показателя. -->
                    <td class="text-right">{{ purchaseEffectiveAmount(p) != null ? formatMoney(purchaseEffectiveAmount(p)!) : '—' }}</td>
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
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import ColumnHeaderMenu from '@/components/ColumnHeaderMenu.vue'
import type { FilterValue } from '@/composables/useColumnConfig'
import type { Contract, Purchase } from '@/composables/contracts/contractsTypes'
import {
  contractTypeLabel, purchaseMethodLabel, contractTypeColor, contractTypeLabels, purchaseMethodLabels, statusLabels,
  fmtDate, isExpired, formatMoney, purchaseEffectiveAmount, isFrameworkContract,
} from '@/composables/contracts/contractsLabels'

const props = defineProps<{
  headers: any[]
  items: any[]
  contracts: Contract[]
  loading: boolean
  colFilters: Record<string, FilterValue>
  localSort: { key: string; order: 'asc' | 'desc' } | null
  getSortBy: (k: string) => 'asc' | 'desc' | null
  applySort: (k: string, dir: 'asc' | 'desc' | null) => void
  setFilter: (k: string, v: FilterValue | null) => void
  toggleVisible: (k: string, v: boolean) => void
  uniqValues: (rows: any[], key: string) => (string | number | null)[]
  isAdmin: boolean
  purchasesByContract: Record<number, Purchase[]>
  expandedPurchases: Record<number, boolean>
  loadPurchasesForContract: (id: number) => void
  fProduct: string
}>()

const expanded = defineModel<number[]>('expanded', { required: true })

const emit = defineEmits<{
  edit: [item: Contract]
  'confirm-delete': [item: Contract]
}>()

const router = useRouter()
</script>

<style scoped>
.contract-approval-pending-banner {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  column-gap: 10px;
  row-gap: 2px;
  background: rgba(15, 23, 42, 0.85);
  border: 1px solid rgba(15, 23, 42, 0.92);
  color: #fff;
  border-radius: 6px;
  padding: 6px 10px;
  margin-bottom: 6px;
}
.contract-approval-pending-banner__title {
  font-weight: 800;
  font-size: 0.92rem;
  letter-spacing: 0.02em;
}
.contract-approval-pending-banner__meta {
  font-size: 0.78rem;
  font-weight: 500;
  opacity: 0.85;
}
</style>
