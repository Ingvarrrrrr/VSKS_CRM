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
              <div v-for="p in r.purchases" :key="p.id" class="d-flex align-center gap-1 flex-wrap ml-1 mt-1">
                <a :href="`/orders/${p.id}/edit`" target="_blank">
                  <v-chip size="x-small" color="success" variant="tonal">{{ p.registry_number || '#' + p.id }}</v-chip>
                </a>
                <span v-if="p.sheet_ref" class="text-caption text-medium-emphasis">{{ p.sheet_ref }}</span>
              </div>
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
              <!-- «Почти совпало» (квик-план 06.10) — подсказки с причиной словами
                   владельца; «Привязать и исправить сумму» только если
                   can_fix_amount (одна позиция в закупке либо Δ ≤ 1 ₽). -->
              <div v-if="r.near_miss && r.near_miss.length" class="near-miss-block mt-2">
                <div class="text-caption text-medium-emphasis mb-1">Почти совпало:</div>
                <div v-for="nm in r.near_miss" :key="nm.purchase_id" class="near-miss-item mb-1">
                  <div class="d-flex align-center flex-wrap gap-1">
                    <a :href="`/orders/${nm.purchase_id}/edit`" target="_blank">
                      <v-chip size="x-small" color="warning" variant="tonal">{{ nm.registry_number || '#' + nm.purchase_id }}</v-chip>
                    </a>
                    <span class="text-caption">{{ nm.subject || '—' }} · {{ nm.contractor_name || 'без контрагента' }} · {{ formatCurrency(nm.amount) }}</span>
                  </div>
                  <div class="text-caption text-medium-emphasis">{{ nearMissReasonText(nm) }}</div>
                  <div class="d-flex flex-wrap gap-1 mt-1">
                    <v-btn size="x-small" variant="tonal" color="success" :loading="attachingKey === attachKey(r, nm.purchase_id)" @click="onAttachNearMiss(r, nm, false)">Привязать</v-btn>
                    <v-btn v-if="nm.can_fix_amount" size="x-small" variant="tonal" color="orange" :loading="attachingKey === attachKey(r, nm.purchase_id) + ':fix'" @click="onAttachNearMiss(r, nm, true)">
                      Привязать и исправить сумму закупки на {{ formatCurrency(r.amount) }}
                    </v-btn>
                  </div>
                </div>
              </div>
            </template>

            <template v-else-if="r.status === 'amount_mismatch'">
              <v-icon color="warning" size="16">mdi-alert</v-icon>
              <span class="text-caption text-warning ml-1">
                расхождение {{ formatCurrency(r.amount_diff) }}
              </span>
              <div v-if="r.purchases.length" class="d-flex flex-wrap gap-1 mt-1">
                <div v-for="p in r.purchases" :key="p.id" class="d-flex align-center gap-1">
                  <a :href="`/orders/${p.id}/edit`" target="_blank">
                    <v-chip size="x-small" color="warning" variant="tonal">{{ p.registry_number || '#' + p.id }}</v-chip>
                  </a>
                  <span v-if="p.sheet_ref" class="text-caption text-medium-emphasis">{{ p.sheet_ref }}</span>
                </div>
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

            <template v-else-if="r.status === 'in_other_subsidy'">
              <!-- Общий номер соглашения с другой субсидией (06.10) — платёжка
                   уже в чужой закупке, привязывать здесь нечего и не нужно. -->
              <span class="text-caption text-medium-emphasis">
                уже в закупке субсидии «{{ r.other_subsidy?.name || '—' }}»
              </span>
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
import type {
  PaymentControlRow, PaymentControlArticle, PaymentControlNearMiss, useSubsidyPaymentControl,
} from '@/composables/subsidies/useSubsidyPaymentControl'
import { formatCurrency } from '@/composables/subsidies/format'
import { useToast } from '@/composables/useToast'
import { describeApiError } from '@/utils/apiErrorMessage'
import PaymentPurposeCell from '@/components/subsidies/PaymentPurposeCell.vue'

const props = defineProps<{
  rows: PaymentControlRow[]
  articles: PaymentControlArticle[]
  subsidyId: number
  control: ReturnType<typeof useSubsidyPaymentControl>
}>()
const emit = defineEmits<{
  (e: 'find', row: PaymentControlRow): void
  (e: 'create', row: PaymentControlRow): void
}>()

const toast = useToast()
const attachingKey = ref<string | null>(null)

function attachKey(r: PaymentControlRow, purchaseId: number): string {
  return `${r.bank_payment_ids[0]}:${purchaseId}`
}

const NEAR_MISS_REASON_LABELS: Record<string, (nm: PaymentControlNearMiss) => string> = {
  amount_close: (nm) => `та же организация, разница ${formatCurrency(Math.abs(nm.delta))}`,
  same_act: () => 'тот же акт/УПД в назначении',
  orders_sum: () => 'сумма нескольких заказов договора',
}
function nearMissReasonText(nm: PaymentControlNearMiss): string {
  const fn = NEAR_MISS_REASON_LABELS[nm.reason]
  return fn ? fn(nm) : (nm.reason || 'похоже на эту закупку')
}

async function onAttachNearMiss(r: PaymentControlRow, nm: PaymentControlNearMiss, fixAmount: boolean) {
  const bpId = r.bank_payment_ids[0]
  if (!bpId) return
  const key = fixAmount ? attachKey(r, nm.purchase_id) + ':fix' : attachKey(r, nm.purchase_id)
  attachingKey.value = key
  try {
    const res = await props.control.attachPurchase(props.subsidyId, bpId, nm.purchase_id, fixAmount)
    for (const w of (res.warnings || [])) toast.addToast(w, 'warning')
    if (res.fixed_amount) {
      toast.success(`Закупка привязана, сумма закупки исправлена с ${formatCurrency(res.fixed_amount.from)} на ${formatCurrency(res.fixed_amount.to)}`)
    } else {
      toast.success('Закупка привязана к платёжке')
    }
    await props.control.reload()
  } catch (e: any) {
    toast.addToast(describeApiError(e, { fallback: 'Не удалось привязать закупку' }), 'error')
  } finally {
    attachingKey.value = null
  }
}

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

<style scoped>
.near-miss-block {
  border-left: 2px solid rgba(251, 146, 60, 0.5);
  padding-left: 6px;
}
</style>
