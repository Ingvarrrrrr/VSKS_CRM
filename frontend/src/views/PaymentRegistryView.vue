<template>
  <v-container fluid class="pa-4">
    <!-- Header -->
    <div class="d-flex align-center justify-space-between mb-4 flex-wrap gap-2">
      <div>
        <h1 class="text-h5 font-weight-bold">
          Реестр платежей
          <span v-if="importId" class="text-medium-emphasis font-weight-regular">· Импорт #{{ importId }}</span>
        </h1>
        <span class="text-body-2 text-medium-emphasis">{{ totalCount }} записей</span>
      </div>
    </div>

    <!-- Filters -->
    <v-card class="mb-4" variant="outlined" rounded="lg">
      <v-card-text class="py-2 px-3">
        <div class="d-flex align-center gap-1 mb-2">
          <v-icon size="16" color="grey">mdi-filter</v-icon>
          <span class="text-caption font-weight-medium text-medium-emphasis">ФИЛЬТРЫ</span>
          <v-spacer />
          <!-- Import badge -->
          <v-chip
            v-if="importId"
            size="small"
            color="blue"
            variant="tonal"
            closable
            @click:close="clearImport"
          >Фильтр: Импорт #{{ importId }}</v-chip>
          <v-btn v-if="hasFilters" variant="text" size="x-small" color="error" prepend-icon="mdi-filter-remove" @click="clearFilters">
            Сбросить
          </v-btn>
        </div>
        <div class="d-flex flex-wrap gap-2 align-end">
          <v-text-field
            v-model="fDateFrom"
            label="Дата от"
            type="date"
            variant="outlined"
            density="compact"
            hide-details
            clearable
            style="min-width:145px; max-width:145px"
          />
          <v-text-field
            v-model="fDateTo"
            label="Дата до"
            type="date"
            variant="outlined"
            density="compact"
            hide-details
            clearable
            style="min-width:145px; max-width:145px"
          />
          <v-select
            v-model="fStatus"
            :items="statusOptions"
            item-title="label"
            item-value="value"
            label="Статус"
            variant="outlined"
            density="compact"
            hide-details
            clearable
            style="min-width:160px; max-width:200px"
          />
          <v-select
            v-model="fMatched"
            :items="yesNoOptions"
            item-title="label"
            item-value="value"
            label="Сматчено"
            variant="outlined"
            density="compact"
            hide-details
            clearable
            style="min-width:160px; max-width:200px"
          />
          <v-select
            v-model="fConfirmed"
            :items="yesNoOptions"
            item-title="label"
            item-value="value"
            label="Подтверждено"
            variant="outlined"
            density="compact"
            hide-details
            clearable
            style="min-width:165px; max-width:200px"
          />
          <v-text-field
            v-model="fInn"
            label="ИНН получателя"
            variant="outlined"
            density="compact"
            hide-details
            clearable
            style="min-width:160px; max-width:200px"
            @keyup.enter="applyFilters"
          />
          <v-btn color="primary" variant="elevated" @click="applyFilters" :loading="loading">
            Применить
          </v-btn>
        </div>
      </v-card-text>
    </v-card>

    <!-- Table -->
    <v-data-table
      :headers="headers"
      :items="payments"
      :loading="loading"
      density="compact"
      show-expand
      v-model:expanded="expanded"
      item-value="id"
      class="elevation-1"
      :items-per-page="50"
      :items-per-page-options="[25, 50, 100]"
      :page="page"
      @update:page="page = $event"
    >
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
        <div class="text-body-2 text-truncate" style="max-width:160px" :title="item.payer_name || ''">
          {{ item.payer_name || '—' }}
        </div>
      </template>

      <!-- Payee -->
      <template #item.payee_name="{ item }">
        <div class="text-body-2 text-truncate" style="max-width:160px" :title="item.payee_name || ''">
          {{ item.payee_name || '—' }}
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

      <!-- Parsed contract -->
      <template #item.parsed_contract_number="{ item }">
        <span class="text-caption">{{ item.parsed_contract_number || '—' }}</span>
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

      <!-- Confirmed chip -->
      <template #item.confirmed="{ item }">
        <v-chip
          v-if="item.matched_confirmed"
          size="x-small"
          color="blue"
          variant="tonal"
          prepend-icon="mdi-check-decagram"
        >Да</v-chip>
        <v-chip v-else size="x-small" color="grey" variant="tonal">Нет</v-chip>
      </template>

      <!-- Actions -->
      <template #item.actions="{ item }">
        <div class="d-flex gap-1 align-center">
          <!-- Confirm button (only if matched) -->
          <v-btn
            v-if="can('payment.confirm')"
            icon
            size="x-small"
            variant="text"
            color="success"
            :disabled="!item.matched_contract_id"
            :title="item.matched_contract_id ? 'Подтвердить' : 'Сначала привяжите договор'"
            @click.stop="openConfirm(item)"
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
            @click.stop="openMatch(item)"
          >
            <v-icon>mdi-link-variant</v-icon>
          </v-btn>

          <!-- Unbind button -->
          <v-btn
            v-if="can('payment.unbind') && item.matched_confirmed"
            icon
            size="x-small"
            variant="text"
            color="warning"
            title="Откатить подтверждение"
            :loading="unbindingId === item.id"
            @click.stop="unbind(item)"
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

    <!-- Match dialog -->
    <PaymentMatchDialog
      v-model="matchDialog"
      :bank-payment-id="selectedPaymentId"
      @updated="onUpdated"
    />

    <!-- Unbind confirm dialog -->
    <v-dialog v-model="unbindDialog" max-width="420">
      <v-card>
        <v-card-title>Откатить подтверждение?</v-card-title>
        <v-card-text>
          Платёжные записи, созданные при подтверждении, будут удалены. Статусы закупок пересчитаются автоматически.
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="unbindDialog = false">Отмена</v-btn>
          <v-btn color="warning" variant="elevated" :loading="unbindLoading" @click="doUnbind">Откатить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiFetch } from '@/api'
import { useToast } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'
import PaymentMatchDialog from '@/components/PaymentMatchDialog.vue'

// ── Route & auth ───────────────────────────────────────────────────────────
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const { success, error } = useToast()

function can(action: string) {
  return authStore.hasAction?.(action) ?? true
}

// ── Import filter from query ────────────────────────────────────────────────
const importId = computed<number | null>(() => {
  const v = route.query.import_id
  return v ? Number(v) : null
})

function clearImport() {
  const q = { ...route.query }
  delete q.import_id
  router.replace({ query: q })
}

// ── Filter state ────────────────────────────────────────────────────────────
const fDateFrom = ref<string>('')
const fDateTo = ref<string>('')
const fStatus = ref<string | null>(null)
const fMatched = ref<string | null>(null)
const fConfirmed = ref<string | null>(null)
const fInn = ref<string>('')

const statusOptions = [
  { label: 'ИСПОЛНЕН', value: 'ИСПОЛНЕН' },
  { label: 'АННУЛИРОВАН', value: 'АННУЛИРОВАН' },
  { label: 'Прочие', value: 'OTHER' },
]
const yesNoOptions = [
  { label: 'Только сматченные', value: 'true' },
  { label: 'Только не сматченные', value: 'false' },
]

const hasFilters = computed(() =>
  fDateFrom.value || fDateTo.value || fStatus.value || fMatched.value || fConfirmed.value || fInn.value
)

function clearFilters() {
  fDateFrom.value = ''
  fDateTo.value = ''
  fStatus.value = null
  fMatched.value = null
  fConfirmed.value = null
  fInn.value = ''
  applyFilters()
}

// ── Table state ─────────────────────────────────────────────────────────────
interface BankPayment {
  id: number
  payment_date: string
  payment_number: string | null
  amount: number
  payer_name: string | null
  payee_name: string | null
  payee_inn: string | null
  parsed_contract_number: string | null
  status: string | null
  purpose_text: string | null
  kbk: string | null
  payer_kpp: string | null
  payee_kpp: string | null
  matched_contract_id: number | null
  matched_contract_number: string | null
  matched_confirmed: boolean
}

const payments = ref<BankPayment[]>([])
const loading = ref(false)
const totalCount = ref(0)
const page = ref(1)
const expanded = ref<number[]>([])

const headers = [
  { title: '№', key: 'index', sortable: false, width: '50px' },
  { title: 'Дата', key: 'payment_date', width: '100px' },
  { title: 'Плательщик', key: 'payer_name', sortable: false },
  { title: 'Получатель', key: 'payee_name', sortable: false },
  { title: 'Сумма', key: 'amount', width: '130px' },
  { title: 'Статус', key: 'status', width: '120px' },
  { title: 'Договор (авто)', key: 'parsed_contract_number', width: '130px' },
  { title: 'Сматчен', key: 'matched', width: '90px', sortable: false },
  { title: 'Подтверждён', key: 'confirmed', width: '110px', sortable: false },
  { title: 'Действия', key: 'actions', sortable: false, width: '110px' },
  { title: '', key: 'data-table-expand', width: '48px' },
]

// ── Load data ───────────────────────────────────────────────────────────────
async function loadPayments() {
  loading.value = true
  try {
    const params = new URLSearchParams({ limit: '200' })
    if (fDateFrom.value) params.set('date_from', fDateFrom.value)
    if (fDateTo.value) params.set('date_to', fDateTo.value)
    if (fStatus.value) params.set('status', fStatus.value)
    if (fMatched.value !== null && fMatched.value !== '') params.set('matched', fMatched.value)
    if (fConfirmed.value !== null && fConfirmed.value !== '') params.set('confirmed', fConfirmed.value)
    if (fInn.value) params.set('payee_inn', fInn.value)
    if (importId.value) params.set('import_id', String(importId.value))

    const data = await apiFetch<any>(`/payments/registry?${params}`)
    const raw: BankPayment[] = Array.isArray(data) ? data : (data as any).items ?? []
    payments.value = raw
    totalCount.value = (data as any).total ?? raw.length
  } catch (e: any) {
    error('Не удалось загрузить реестр: ' + (e.detail || ''))
  } finally {
    loading.value = false
  }
}

function applyFilters() {
  page.value = 1
  loadPayments()
}

// ── Watch import_id changes in URL ──────────────────────────────────────────
watch(importId, () => {
  applyFilters()
})

// ── Match dialog ─────────────────────────────────────────────────────────────
const matchDialog = ref(false)
const selectedPaymentId = ref<number | null>(null)

function openMatch(item: BankPayment) {
  selectedPaymentId.value = item.id
  matchDialog.value = true
}

function openConfirm(item: BankPayment) {
  // Open match dialog with pre-loaded contract for confirmation flow
  selectedPaymentId.value = item.id
  matchDialog.value = true
}

function onUpdated() {
  loadPayments()
}

// ── Unbind ───────────────────────────────────────────────────────────────────
const unbindDialog = ref(false)
const unbindingId = ref<number | null>(null)
const unbindLoading = ref(false)

function unbind(item: BankPayment) {
  unbindingId.value = item.id
  unbindDialog.value = true
}

async function doUnbind() {
  if (!unbindingId.value) return
  unbindLoading.value = true
  try {
    await apiFetch(`/payments/registry/${unbindingId.value}/unbind`, { method: 'POST' })
    success('Подтверждение откатено')
    unbindDialog.value = false
    loadPayments()
  } catch (e: any) {
    error('Ошибка при откате: ' + (e.detail || ''))
  } finally {
    unbindLoading.value = false
    unbindingId.value = null
  }
}

// ── Helpers ──────────────────────────────────────────────────────────────────
function fmtDate(d: string | null) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('ru-RU')
}

function formatMoney(v: number | null | undefined) {
  if (v == null) return '—'
  return new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 2 }).format(v)
}

function statusColor(s: string | null) {
  if (!s) return 'grey'
  if (s === 'ИСПОЛНЕН') return 'success'
  if (s === 'АННУЛИРОВАН') return 'error'
  return 'warning'
}

// ── Init ──────────────────────────────────────────────────────────────────────
onMounted(() => {
  loadPayments()
})
</script>
