<template>
  <v-card variant="outlined" class="mb-4">
    <v-card-title class="d-flex align-center text-subtitle-1 font-weight-bold px-4 pt-4">
      <v-icon icon="mdi-cash-multiple" class="mr-2" color="green" />
      Платежи
      <v-spacer />
      <div v-if="payments.length" class="d-flex align-center gap-2">
        <span class="text-body-2 font-weight-bold text-green">
          {{ formatMoney(totalPaid) }}
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
              <th class="text-center">Подтверждён</th>
              <th>Источник</th>
              <th>Действия</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="pm in payments" :key="pm.id">
              <td class="text-no-wrap">{{ pm.payment_date || '—' }}</td>
              <td>{{ pm.document_number || '—' }}</td>
              <td class="text-right text-no-wrap">{{ pm.amount ? formatMoney(Number(pm.amount)) : '—' }}</td>
              <td class="text-center">
                <v-chip
                  size="x-small"
                  :color="pm.matched_confirmed ? 'success' : 'warning'"
                  variant="tonal"
                >
                  {{ pm.matched_confirmed ? 'Да' : 'Нет' }}
                </v-chip>
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

        <!-- Кнопка добавить -->
        <v-btn
          size="small"
          variant="tonal"
          color="green"
          prepend-icon="mdi-plus"
          @click="addDialog = true"
        >
          Добавить платёж вручную
        </v-btn>
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
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { apiFetch } from '@/api'

const { mobile } = useDisplay()

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

const totalPaid = computed(() =>
  payments.value.reduce((s, p) => s + Number(p.amount || 0), 0)
)

const basePrice = computed(() =>
  props.contractPrice ?? props.plannedTotalPrice ?? null
)

const percentPaid = computed(() => {
  if (!basePrice.value || !basePrice.value) return null
  return Math.round((totalPaid.value / Number(basePrice.value)) * 100)
})

function formatMoney(n: number): string {
  return n.toLocaleString('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 2 })
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
        matched_confirmed: true,
      }),
    })
    closeAddDialog()
    await loadPayments()
    emit('changed')
  } finally {
    saving.value = false
  }
}

watch(() => props.purchaseId, () => loadPayments(), { immediate: true })
</script>
