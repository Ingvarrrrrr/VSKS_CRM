<template>
  <v-card variant="outlined" class="mb-4">
    <v-card-title class="d-flex align-center text-subtitle-1 font-weight-bold px-4 pt-4">
      <v-icon icon="mdi-cash-multiple" class="mr-2" color="green" />
      Платежи
      <v-spacer />
      <div v-if="payments.length" class="d-flex align-center flex-wrap gap-2">
        <v-tooltip location="top" text="Найдено в казначейской выписке и разнесено на закупку">
          <template #activator="{ props: tp }">
            <span v-bind="tp" class="text-body-2 font-weight-bold text-green">
              Оплачено (подтверждено): {{ formatMoney(totalConfirmed) }}
            </span>
          </template>
        </v-tooltip>
        <span v-if="totalDeclared > 0" class="text-body-2 font-weight-medium text-orange-darken-2">
          Отмечено, ждёт подтверждения: {{ formatMoney(totalDeclared) }}
        </span>
        <v-chip
          v-if="percentPaid !== null"
          size="small"
          :color="percentPaid >= 100 ? 'success' : 'orange'"
          variant="tonal"
        >
          оплачено {{ percentPaid }}% от {{ formatMoney(basePrice) }}
        </v-chip>
      </div>
    </v-card-title>

    <v-card-text class="pa-3">
      <!-- Новая закупка — платежи недоступны -->
      <v-alert v-if="!purchaseId" type="info" variant="tonal" density="compact" class="mb-0">
        Сохраните закупку, чтобы добавить платежи
      </v-alert>

      <template v-else>
        <!-- Таблица платежей -->
        <v-table v-if="payments.length" density="compact" class="mb-3">
          <thead>
            <tr>
              <th>Дата</th>
              <th>№ платёжки</th>
              <th class="text-right">Сумма</th>
              <th>Назначение / основание</th>
              <th>Код расходов</th>
              <th class="text-center">Статус</th>
              <th>Источник</th>
              <th>Действия</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="pm in payments" :key="pm.id">
              <td class="text-no-wrap">{{ pm.payment_date || '—' }}</td>
              <td>{{ pm.document_number || '—' }}</td>
              <td class="text-right text-no-wrap">{{ pm.amount ? formatMoney(Number(pm.amount)) : '—' }}</td>
              <td style="max-width:260px">
                <div v-if="pm.basis_label" class="text-body-2 font-weight-medium">{{ pm.basis_label }}</div>
                <div class="text-caption text-medium-emphasis" :title="pm.payment_purpose || ''" style="overflow-wrap:anywhere">
                  {{ pm.payment_purpose || '—' }}
                </div>
              </td>
              <td>
                <v-chip v-if="pm.expense_code" size="x-small" variant="tonal" color="blue" :title="expenseCodeName(pm.expense_code) || ''">
                  {{ pm.expense_code }}
                </v-chip>
                <span v-else class="text-medium-emphasis">—</span>
              </td>
              <td class="text-center">
                <!-- Владелец (2026-08-19): «по нашим данным» (человек отметил) и
                     «подтверждено казначейством» (найдено в выписке) — два
                     разных факта, раньше слитых в один флаг matched_confirmed. -->
                <v-chip
                  v-if="pm.confirmed_by_statement"
                  size="x-small"
                  color="success"
                  variant="tonal"
                  prepend-icon="mdi-bank-check"
                >
                  Подтверждено казначейством
                </v-chip>
                <v-tooltip v-else location="top" text="Отметил человек, без сверки с казначейской выпиской — суммой можно ошибиться">
                  <template #activator="{ props: tp }">
                    <v-chip v-bind="tp" size="x-small" color="orange" variant="tonal" prepend-icon="mdi-account-alert-outline">
                      По нашим данным
                    </v-chip>
                  </template>
                </v-tooltip>
              </td>
              <td>
                <v-btn
                  v-if="pm.bank_payment_id"
                  size="x-small"
                  variant="text"
                  color="primary"
                  :href="`/payments/registry?bank_payment_id=${pm.bank_payment_id}`"
                  target="_blank"
                  prepend-icon="mdi-bank-outline"
                >
                  Выписка #{{ pm.bank_payment_id }}
                </v-btn>
                <span v-else class="text-caption text-medium-emphasis">Ручной</span>
              </td>
              <td>
                <v-btn
                  size="x-small"
                  icon="mdi-delete-outline"
                  color="error"
                  variant="text"
                  :loading="deletingId === pm.id"
                  @click="deletePayment(pm)"
                />
              </td>
            </tr>
          </tbody>
        </v-table>

        <div v-else class="text-caption text-medium-emphasis mb-3">
          Платежей нет
        </div>

        <!-- Кнопки -->
        <div class="d-flex flex-wrap gap-2">
          <v-btn
            size="small"
            variant="tonal"
            color="green"
            prepend-icon="mdi-plus"
            @click="addDialog = true"
          >
            Добавить платёж вручную
          </v-btn>
          <v-btn
            size="small"
            variant="tonal"
            color="primary"
            prepend-icon="mdi-magnify"
            :loading="candidatesLoading"
            @click="openFindDialog"
          >
            Найти платежи в реестре
          </v-btn>
        </div>
      </template>
    </v-card-text>
  </v-card>

  <!-- Диалог добавления ручного платежа -->
  <v-dialog v-model="addDialog" max-width="480" persistent :fullscreen="mobile">
    <v-card>
      <v-card-title class="text-subtitle-1 font-weight-bold pa-4">
        Добавить платёж вручную
      </v-card-title>
      <v-card-text class="pa-4 pt-0">
        <v-alert type="warning" variant="tonal" density="compact" class="mb-3" icon="mdi-account-alert-outline">
          Это отметка «по нашим данным» — со слов, без сверки с казначейской выпиской.
          Он не увеличит подтверждённую сумму оплаты, пока не сопоставится с реальной строкой выписки.
        </v-alert>
        <v-row dense>
          <v-col cols="12" md="6">
            <v-text-field
              v-model="newPayment.document_number"
              label="Номер платёжного поручения"
              variant="outlined"
              density="compact"
            />
          </v-col>
          <v-col cols="12" md="6">
            <v-text-field
              v-model="newPayment.payment_date"
              label="Дата платежа"
              variant="outlined"
              density="compact"
              type="date"
            />
          </v-col>
          <v-col cols="12" md="6">
            <v-text-field
              v-model.number="newPayment.amount"
              label="Сумма, ₽"
              variant="outlined"
              density="compact"
              type="number"
              suffix="₽"
            />
          </v-col>
          <v-col cols="12" md="6">
            <v-text-field
              v-model="newPayment.payment_purpose"
              label="Назначение платежа"
              variant="outlined"
              density="compact"
            />
          </v-col>
        </v-row>
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="closeAddDialog">Отмена</v-btn>
        <v-btn
          color="green"
          variant="tonal"
          :loading="saving"
          :disabled="!newPayment.amount"
          @click="submitPayment"
        >
          Добавить
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- Диалог «Найти платежи в реестре» (Этап 7б) -->
  <v-dialog v-model="findDialog" max-width="720" scrollable :fullscreen="mobile">
    <v-card>
      <v-card-title class="d-flex align-center text-subtitle-1 font-weight-bold pa-4">
        <v-icon icon="mdi-magnify" class="mr-2" color="primary" />
        Найти платежи в реестре
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="findDialog = false" />
      </v-card-title>
      <v-card-text class="pa-4 pt-0">
        <div v-if="candidatesLoading" class="d-flex justify-center py-8">
          <v-progress-circular indeterminate color="primary" />
        </div>
        <template v-else>
          <v-alert v-if="candidatesReason" type="warning" variant="tonal" density="compact" class="mb-3">
            {{ candidatesReason }}
          </v-alert>
          <template v-else>
            <div v-for="kind in (['goods', 'services'] as const)" :key="kind" class="mb-4">
              <div v-if="candidates[kind].length" class="text-subtitle-2 font-weight-bold mb-2">
                {{ kind === 'goods' ? 'Товары' : 'Услуги / работы' }}
              </div>
              <v-card
                v-for="c in candidates[kind]"
                :key="c.bank_payment_id"
                variant="outlined"
                class="mb-2 pa-2"
                :class="{ 'bg-grey-lighten-4': !c.free }"
              >
                <div class="d-flex align-center flex-wrap gap-2">
                  <span class="font-weight-bold">{{ formatMoney(c.amount) }}</span>
                  <span class="text-caption text-medium-emphasis">от {{ fmtDate(c.payment_date) }}, № {{ c.payment_number || '—' }}</span>
                  <v-chip v-if="c.auto" size="x-small" color="success" variant="tonal">авто</v-chip>
                  <v-spacer />
                  <v-btn
                    v-if="c.free"
                    size="x-small"
                    variant="tonal"
                    color="primary"
                    :loading="attachingId === c.bank_payment_id"
                    @click="attachCandidate(c)"
                  >
                    Загрузить
                  </v-btn>
                </div>
                <div v-if="c.basis_label" class="text-body-2 mt-1">{{ c.basis_label }}</div>
                <div class="d-flex flex-wrap gap-1 mt-1">
                  <v-chip v-for="(chk, i) in c.checks" :key="i" size="x-small" variant="tonal" color="grey">{{ chk }}</v-chip>
                </div>
                <div v-if="!c.free" class="text-caption text-error mt-1">
                  <v-icon size="14" icon="mdi-lock-outline" class="mr-1" />{{ c.reason }}
                </div>
              </v-card>
            </div>
            <div v-if="!candidates.goods.length && !candidates.services.length" class="text-center text-medium-emphasis py-6">
              Подходящих платежей в реестре не найдено
            </div>
          </template>
        </template>
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="findDialog = false">Закрыть</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { apiFetch } from '@/api'
import { useToast } from '@/composables/useToast'

const { mobile } = useDisplay()
const toast = useToast()

const props = defineProps<{
  purchaseId: number | null
  contractPrice?: number | null
  plannedTotalPrice?: number | null
  status?: string
}>()

const emit = defineEmits<{
  (e: 'changed'): void
}>()

interface Payment {
  id: number
  purchase_id: number | null
  contract_id: number | null
  document_number: string | null
  payment_purpose: string | null
  payment_date: string | null
  amount: number | string | null
  bank_payment_id: number | null
  matched_confirmed: boolean
  // Владелец (2026-08-19): payment_source/confirmed_by_statement — см.
  // backend/app/models/payment.py.
  payment_source?: 'manual' | 'statement'
  confirmed_by_statement?: boolean
  expense_code?: string | null
  basis_label?: string | null
}

const payments = ref<Payment[]>([])
const deletingId = ref<number | null>(null)
const addDialog = ref(false)
const saving = ref(false)

const newPayment = ref({
  document_number: '',
  payment_date: '',
  amount: null as number | null,
  payment_purpose: '',
})

// Владелец (2026-08-19): «оплачено» — только подтверждённое казначейством;
// заявленное человеком без выписки — отдельная (более слабая) сумма.
const totalConfirmed = computed(() =>
  payments.value.filter(p => p.confirmed_by_statement).reduce((s, p) => s + Number(p.amount || 0), 0)
)
const totalDeclared = computed(() =>
  payments.value.filter(p => !p.confirmed_by_statement).reduce((s, p) => s + Number(p.amount || 0), 0)
)

const basePrice = computed(() =>
  props.contractPrice ?? props.plannedTotalPrice ?? null
)

const percentPaid = computed(() => {
  if (!basePrice.value || !basePrice.value) return null
  return Math.round((totalConfirmed.value / Number(basePrice.value)) * 100)
})

function formatMoney(n: number): string {
  return n.toLocaleString('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 2 })
}

function fmtDate(d: string | null): string {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('ru-RU')
}

// ── Справочник кодов расходов (для tooltip с расшифровкой) ─────────────────
interface ExpenseCodeRow { code: string; name: string }
const expenseCodesMap = ref<Record<string, string>>({})
async function loadExpenseCodes() {
  try {
    const data = await apiFetch<ExpenseCodeRow[]>('/expense-codes')
    expenseCodesMap.value = Object.fromEntries((data || []).map(c => [c.code, c.name]))
  } catch {
    expenseCodesMap.value = {}
  }
}
function expenseCodeName(code?: string | null): string | null {
  if (!code) return null
  return expenseCodesMap.value[code] || null
}

async function loadPayments() {
  if (!props.purchaseId) {
    payments.value = []
    return
  }
  try {
    const data = await apiFetch(`/payments/?purchase_id=${props.purchaseId}`)
    payments.value = data
  } catch {
    payments.value = []
  }
}

async function deletePayment(pm: Payment) {
  if (!confirm(`Удалить платёж ${pm.document_number || '#' + pm.id}?`)) return
  deletingId.value = pm.id
  try {
    await apiFetch(`/payments/${pm.id}`, { method: 'DELETE' })
    await loadPayments()
    emit('changed')
  } finally {
    deletingId.value = null
  }
}

function closeAddDialog() {
  addDialog.value = false
  newPayment.value = { document_number: '', payment_date: '', amount: null, payment_purpose: '' }
}

async function submitPayment() {
  if (!props.purchaseId || !newPayment.value.amount) return
  saving.value = true
  try {
    await apiFetch('/payments/', {
      method: 'POST',
      body: JSON.stringify({
        purchase_id: props.purchaseId,
        contract_id: null,
        document_number: newPayment.value.document_number || null,
        payment_date: newPayment.value.payment_date || null,
        amount: newPayment.value.amount,
        payment_purpose: newPayment.value.payment_purpose || null,
        // Владелец (2026-08-19): ручной платёж — «по нашим данным», НЕ
        // подтверждённый выпиской (payment_source='manual' и
        // confirmed_by_statement=False проставляются на бэкенде по умолчанию —
        // см. app/routers/payments.py::create_payment).
      }),
    })
    closeAddDialog()
    await loadPayments()
    emit('changed')
  } finally {
    saving.value = false
  }
}

// ── «Найти платежи в реестре» (Этап 7б) ─────────────────────────────────────
interface Candidate {
  bank_payment_id: number
  amount: number
  kind: string
  checks: string[]
  auto: boolean
  free: boolean
  reason: string | null
  basis_label: string | null
  payment_number: string | null
  payment_date: string | null
}

const findDialog = ref(false)
const candidatesLoading = ref(false)
const candidatesReason = ref<string | null>(null)
const attachingId = ref<number | null>(null)
const groupInfo = ref<{ subsidy_id: number; group_key: string } | null>(null)
const candidates = ref<{ goods: Candidate[]; services: Candidate[] }>({ goods: [], services: [] })

async function openFindDialog() {
  if (!props.purchaseId) return
  findDialog.value = true
  candidatesLoading.value = true
  candidatesReason.value = null
  candidates.value = { goods: [], services: [] }
  groupInfo.value = null
  try {
    const data = await apiFetch<any>(`/purchases/${props.purchaseId}/payment-candidates`)
    if (!data.group) {
      candidatesReason.value = data.reason || 'Группа оплаты не найдена'
      return
    }
    groupInfo.value = { subsidy_id: data.group.subsidy_id, group_key: data.group.group_key }
    candidates.value = { goods: data.goods || [], services: data.services || [] }
  } catch (e: any) {
    candidatesReason.value = e?.payload?.message || e?.detail || e?.message || 'Ошибка поиска платежей'
  } finally {
    candidatesLoading.value = false
  }
}

async function attachCandidate(c: Candidate) {
  if (!groupInfo.value) return
  attachingId.value = c.bank_payment_id
  try {
    await apiFetch('/purchases/attach-payments', {
      method: 'POST',
      body: JSON.stringify({
        subsidy_id: groupInfo.value.subsidy_id,
        group_key: groupInfo.value.group_key,
        bank_payment_ids: [c.bank_payment_id],
      }),
    })
    toast.addToast('Платёж загружен в закупку', 'success')
    findDialog.value = false
    await loadPayments()
    emit('changed')
  } catch (e: any) {
    toast.addToast(e?.payload?.message || e?.detail || e?.message || 'Ошибка загрузки платежа', 'error')
  } finally {
    attachingId.value = null
  }
}

watch(() => props.purchaseId, () => loadPayments(), { immediate: true })
loadExpenseCodes()
</script>

<style scoped>
</style>
