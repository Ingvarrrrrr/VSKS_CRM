<template>
  <div>
    <div class="d-flex flex-wrap align-center gap-2 mb-3">
      <v-checkbox-btn v-model="onlyProblem" density="compact" label="Только проблемные" />
      <v-select
        v-model="articleFilter"
        :items="articleOptions"
        item-title="label"
        item-value="code"
        label="Статья"
        clearable
        density="compact"
        variant="outlined"
        hide-details
        style="max-width:260px"
      />
      <v-text-field
        v-model="search"
        placeholder="Поиск по № / получателю"
        prepend-inner-icon="mdi-magnify"
        density="compact"
        variant="outlined"
        hide-details
        clearable
        style="max-width:260px"
      />
      <v-spacer />
      <span class="text-caption text-medium-emphasis">Показано: {{ filteredRows.length }} / {{ rows.length }}</span>
    </div>

    <v-table density="compact">
      <thead>
        <tr>
          <th>№</th>
          <th>Дата</th>
          <th>Получатель</th>
          <th class="text-right">Сумма</th>
          <th>Назначение</th>
          <th>Статья</th>
          <th>Состояние</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in filteredRows" :key="r.key" :class="rowClass(r)">
          <td class="text-no-wrap">{{ r.payment_number || '—' }}</td>
          <td class="text-no-wrap">{{ fmtDate(r.payment_date) }}</td>
          <td style="max-width:180px">
            {{ r.payee_name || '—' }}
            <div v-if="r.payee_inn" class="text-caption text-medium-emphasis">ИНН {{ r.payee_inn }}</div>
          </td>
          <td class="text-right text-no-wrap">{{ formatCurrency(r.amount) }}</td>
          <td style="max-width:260px">
            <PaymentPurposeCell :text="r.purpose_text" />
          </td>
          <td class="text-caption">{{ r.expense_name || r.expense_code || '—' }}</td>
          <td style="min-width:260px">
            <template v-if="r.status === 'match'">
              <v-icon color="success" size="16">mdi-check-circle</v-icon>
              <a
                v-for="p in r.purchases"
                :key="p.id"
                :href="`/orders/${p.id}/edit`"
                target="_blank"
                class="ml-1"
              >
                <v-chip size="x-small" color="success" variant="tonal">{{ p.registry_number || '#' + p.id }}</v-chip>
              </a>
            </template>

            <template v-else-if="r.status === 'registry_only'">
              <div class="d-flex align-center flex-wrap gap-1">
                <v-icon color="error" size="16">mdi-close-circle</v-icon>
                <span class="text-caption text-error">закупка не найдена</span>
              </div>
              <div class="d-flex flex-wrap gap-1 mt-1">
                <v-btn size="x-small" variant="tonal" color="primary" @click="emit('find', r)">Найти закупку</v-btn>
                <v-btn size="x-small" variant="tonal" color="success" @click="emit('create', r)">Создать закупку по платёжке</v-btn>
              </div>
            </template>

            <template v-else-if="r.status === 'amount_mismatch'">
              <v-icon color="warning" size="16">mdi-alert</v-icon>
              <span class="text-caption text-warning ml-1">
                расхождение {{ formatCurrency(r.amount_diff) }}
              </span>
              <div v-if="r.purchases.length" class="mt-1">
                <a v-for="p in r.purchases" :key="p.id" :href="`/orders/${p.id}/edit`" target="_blank" class="mr-1">
                  <v-chip size="x-small" color="warning" variant="tonal">{{ p.registry_number || '#' + p.id }}</v-chip>
                </a>
              </div>
            </template>

            <template v-else-if="r.status === 'duplicate'">
              <v-icon color="error" size="16">mdi-content-duplicate</v-icon>
              <span class="text-caption text-error ml-1">
                возможный дубль: {{ (r.duplicate_with || []).join(', ') || '—' }}
              </span>
            </template>

            <template v-else-if="r.status === 'not_reconciled'">
              <span class="text-caption text-medium-emphasis">не сверяется (статья не отмечена)</span>
            </template>

            <template v-else-if="r.status === 'purchases_only'">
              <span class="text-caption" style="color:#b58900">в закупках есть, в выписке нет</span>
            </template>

            <template v-else-if="r.status === 'declared_unconfirmed'">
              <span class="text-caption" style="color:#b58900">отмечено вручную, выпиской не подтверждено</span>
            </template>
          </td>
        </tr>
      </tbody>
    </v-table>
    <div v-if="!filteredRows.length" class="text-caption text-medium-emphasis text-center py-6">
      Нет платёжек по заданным фильтрам
    </div>
  </div>
</template>

<script setup lang="ts">
// Вкладка «Платёжки» диалога сверки — построчный список исполненных платежей
// выписки с состоянием сверки по каждой. Действия «Найти закупку» / «Создать
// закупку по платёжке» эмитятся наверх (SubsidyPaymentControlDialog.vue),
// который открывает соответствующие диалоги — сами действия идут через общий
// composable useSubsidyPaymentControl.ts (ПРАВИЛО №6).
import { computed, ref } from 'vue'
import type { PaymentControlRow, PaymentControlArticle } from '@/composables/subsidies/useSubsidyPaymentControl'
import { formatCurrency } from '@/composables/subsidies/format'
import PaymentPurposeCell from '@/components/subsidies/PaymentPurposeCell.vue'

const props = defineProps<{
  rows: PaymentControlRow[]
  articles: PaymentControlArticle[]
}>()
const emit = defineEmits<{
  (e: 'find', row: PaymentControlRow): void
  (e: 'create', row: PaymentControlRow): void
}>()

const onlyProblem = ref(true)
const articleFilter = ref<string | null>(null)
const search = ref('')

const PROBLEM_STATUSES = new Set(['registry_only', 'amount_mismatch', 'duplicate', 'purchases_only', 'declared_unconfirmed'])

const articleOptions = computed(() =>
  props.articles
    .filter(a => a.statement_count > 0)
    .map(a => ({ code: a.code, label: `${a.code} — ${a.name}` })),
)

const filteredRows = computed(() => {
  let list = props.rows
  if (onlyProblem.value) list = list.filter(r => PROBLEM_STATUSES.has(r.status))
  if (articleFilter.value) list = list.filter(r => r.expense_code === articleFilter.value)
  const q = search.value.trim().toLowerCase()
  if (q) {
    list = list.filter(r =>
      (r.payment_number || '').toLowerCase().includes(q) ||
      (r.payee_name || '').toLowerCase().includes(q),
    )
  }
  return list
})

function rowClass(r: PaymentControlRow): string {
  if (r.status === 'registry_only' || r.status === 'duplicate') return 'bg-red-lighten-5'
  if (r.status === 'amount_mismatch') return 'bg-orange-lighten-5'
  if (r.status === 'purchases_only' || r.status === 'declared_unconfirmed') return 'bg-amber-lighten-5'
  return ''
}

function fmtDate(d: string | null): string {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('ru-RU')
}
</script>
