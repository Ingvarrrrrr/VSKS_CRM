<template>
  <v-dialog :model-value="modelValue" fullscreen transition="dialog-bottom-transition" @update:model-value="v => emit('update:modelValue', v)">
    <v-card v-if="contract">
      <v-toolbar color="primary" density="comfortable">
        <v-btn icon="mdi-close" @click="emit('update:modelValue', false)" />
        <v-toolbar-title>
          Договор № {{ contract.number || '—' }}
          <span class="text-body-2 font-weight-regular ml-2">от {{ fmtDate(contract.date) }}</span>
        </v-toolbar-title>
        <v-spacer />
        <v-chip v-if="contract.status" size="small" variant="flat" class="mr-3">
          {{ statusLabel(contract.status) }}
        </v-chip>
        <v-btn variant="tonal" prepend-icon="mdi-pencil" @click="emit('edit', contract)">Редактировать</v-btn>
      </v-toolbar>

      <!-- Шапка со сводкой. Регресс 2026-09-17 (владелец): v-card в fullscreen
           v-dialog — flex-column, а v-card-text по умолчанию flex-grow:1 —
           ОБА card-text (шапка и контент вкладок) растягивались и делили
           между собой всю оставшуюся высоту диалога, отсюда ~250-300px
           пустого места под шапкой. flex-grow-0/flex-shrink-0 фиксируют
           шапку по высоте содержимого; вся оставшаяся высота уходит второму
           card-text (с вкладками) — это и нужно, у него скролл контента. -->
      <v-card-text class="pb-2 flex-grow-0 flex-shrink-0">
        <div class="d-flex flex-wrap header-summary">
          <div class="header-summary__item">
            <div class="text-caption text-medium-emphasis">Контрагент</div>
            <div class="text-body-1 font-weight-medium">{{ contract.contractor_name || '—' }}</div>
            <div v-if="contract.contractor_inn" class="text-caption text-medium-emphasis">ИНН {{ contract.contractor_inn }}</div>
          </div>
          <div class="header-summary__item header-summary__item--divided">
            <div class="text-caption text-medium-emphasis">Субсидия</div>
            <div class="text-body-1">{{ contract.subsidy_name || '—' }}</div>
          </div>
          <div class="header-summary__item header-summary__item--divided">
            <div class="text-caption text-medium-emphasis">Предельная сумма</div>
            <div class="text-body-1 font-weight-medium">{{ contract.max_amount ? formatMoney(contract.max_amount) : '—' }}</div>
          </div>
          <div class="header-summary__item header-summary__item--divided">
            <div class="text-caption text-medium-emphasis">Заказано / Оплачено</div>
            <div class="text-body-1">
              {{ contract.total_ordered ? formatMoney(contract.total_ordered) : '—' }} /
              {{ contract.total_paid ? formatMoney(contract.total_paid) : '—' }}
            </div>
          </div>
        </div>
      </v-card-text>

      <v-tabs v-model="tab" class="px-4">
        <v-tab value="purchases">Закупки по договору</v-tab>
        <v-tab value="requisites">Реквизиты</v-tab>
      </v-tabs>
      <v-divider />

      <v-card-text style="max-width: 1200px">
        <v-window v-model="tab">
          <!-- ── Закупки по договору ── -->
          <v-window-item value="purchases">
            <div v-if="loading" class="d-flex justify-center py-8">
              <v-progress-circular indeterminate color="primary" />
            </div>
            <div v-else-if="!purchases.length" class="text-medium-emphasis text-center py-8">
              Закупок по этому договору нет
            </div>
            <v-table v-else density="comfortable" class="purchases-table">
              <!-- Регресс 2026-09-17 (владелец): без явных ширин колонок auto-layout
                   таблицы схлопывал узкие столбцы (пустой «—») и визуально сбивал
                   значения относительно заголовков на строках с короткими данными.
                   colgroup жёстко фиксирует порядок/ширину — 1:1 с <th> ниже. -->
              <colgroup>
                <col style="width: 160px">
                <col style="width: auto">
                <col style="width: 170px">
                <col style="width: 140px">
                <col style="width: 150px">
              </colgroup>
              <thead>
                <tr>
                  <th>№ закупки</th>
                  <th>Наименование / предмет</th>
                  <th>Статус</th>
                  <th class="text-right">Сумма</th>
                  <th>Срок исполнения</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="p in purchases" :key="p.id" class="card-purchase-row" @click="router.push(`/orders/${p.id}/edit`)">
                  <td class="font-weight-medium">{{ p.registry_number || p.purchase_number || p.id }}</td>
                  <td class="text-caption">{{ p.subject || p.item_name || '—' }}</td>
                  <td>
                    <v-chip size="x-small" variant="tonal" :color="purchaseStatusColor(p.status)">
                      {{ purchaseStatusLabel(p.status) || '—' }}
                    </v-chip>
                  </td>
                  <td class="text-right">
                    {{ purchaseEffectiveAmount(p) != null ? formatMoney(purchaseEffectiveAmount(p)!) : '—' }}
                  </td>
                  <td>{{ (p as any).execution_term ? fmtDate((p as any).execution_term) : '—' }}</td>
                </tr>
              </tbody>
            </v-table>
          </v-window-item>

          <!-- ── Реквизиты (только чтение) ── -->
          <v-window-item value="requisites">
            <v-row dense class="mt-2">
              <v-col cols="12" md="6">
                <div class="text-caption text-medium-emphasis">Номер договора</div>
                <div class="text-body-1 mb-3">{{ contract.number || '—' }}</div>
              </v-col>
              <v-col cols="12" md="6">
                <div class="text-caption text-medium-emphasis">Дата договора</div>
                <div class="text-body-1 mb-3">{{ fmtDate(contract.date) }}</div>
              </v-col>
              <v-col cols="12" md="6">
                <div class="text-caption text-medium-emphasis">Тип договора</div>
                <div class="text-body-1 mb-3">{{ contractTypeLabel(contract.contract_type) }}</div>
              </v-col>
              <v-col cols="12" md="6">
                <div class="text-caption text-medium-emphasis">Способ закупки</div>
                <div class="text-body-1 mb-3">{{ contract.purchase_method ? purchaseMethodLabel(contract.purchase_method) : '—' }}</div>
              </v-col>
              <v-col cols="12">
                <div class="text-caption text-medium-emphasis">Предмет договора</div>
                <div class="text-body-1 mb-3">{{ contract.subject || '—' }}</div>
              </v-col>
              <v-col cols="12" md="6">
                <div class="text-caption text-medium-emphasis">Дата начала</div>
                <div class="text-body-1 mb-3">{{ contract.start_date ? fmtDate(contract.start_date) : '—' }}</div>
              </v-col>
              <v-col cols="12" md="6">
                <div class="text-caption text-medium-emphasis">Дата окончания</div>
                <div class="text-body-1 mb-3">{{ contract.end_date ? fmtDate(contract.end_date) : '—' }}</div>
              </v-col>
              <v-col cols="12" md="6">
                <div class="text-caption text-medium-emphasis">Предельная сумма</div>
                <div class="text-body-1 mb-3">{{ contract.max_amount ? formatMoney(contract.max_amount) : '—' }}</div>
              </v-col>
              <v-col cols="12" md="6">
                <div class="text-caption text-medium-emphasis">Плановый ежемесячный платёж</div>
                <div class="text-body-1 mb-3">{{ contract.planned_monthly ? formatMoney(contract.planned_monthly) : '—' }}</div>
              </v-col>
              <v-col v-if="contract.extra_subsidies?.length" cols="12">
                <div class="text-caption text-medium-emphasis mb-1">Дополнительные субсидии</div>
                <div class="d-flex flex-wrap ga-1 mb-3">
                  <v-chip v-for="es in contract.extra_subsidies" :key="es.subsidy_id" size="small" color="secondary" variant="tonal">
                    {{ es.subsidy_name }}
                  </v-chip>
                </div>
              </v-col>
              <v-col v-if="contract.notes" cols="12">
                <div class="text-caption text-medium-emphasis">Примечания</div>
                <div class="text-body-1 mb-3" style="white-space: pre-wrap">{{ contract.notes }}</div>
              </v-col>
            </v-row>
            <v-btn variant="tonal" prepend-icon="mdi-pencil" @click="emit('edit', contract)">Редактировать реквизиты</v-btn>
            <!-- Файлы/платежи договора: отдельного эндпоинта карточки договора нет,
                 файлы/акты живут на закупках (см. вкладку «Закупки по договору» —
                 суммы поставки/оплаты там же). Второй запрос ради этой вкладки
                 заводить не стали (см. отчёт задачи). -->
          </v-window-item>
        </v-window>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { purchaseStatusLabel, purchaseStatusColor } from '@/constants/purchaseStatus'
import {
  contractTypeLabel, purchaseMethodLabel, statusLabel,
  fmtDate, formatMoney, purchaseEffectiveAmount,
} from '@/composables/contracts/contractsLabels'
import type { Contract, Purchase } from '@/composables/contracts/contractsTypes'

const props = defineProps<{
  modelValue: boolean
  contract: Contract | null
  purchases: Purchase[]
  loading: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [v: boolean]
  edit: [c: Contract]
}>()

const router = useRouter()
const tab = ref('purchases')

// Сбрасываем на вкладку «Закупки» при открытии новой карточки.
watch(() => props.modelValue, (v) => { if (v) tab.value = 'purchases' })
</script>

<style scoped>
.header-summary {
  column-gap: 32px;
  row-gap: 8px;
}
.header-summary__item--divided {
  padding-left: 32px;
  border-left: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.purchases-table :deep(table) {
  table-layout: fixed;
}
.purchases-table :deep(td) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.card-purchase-row {
  cursor: pointer;
}
.card-purchase-row:hover {
  background: rgba(var(--v-theme-primary), 0.06);
}
</style>
