<template>
  <v-dialog v-model="dialog" max-width="720" scrollable>
    <v-card>
      <v-card-title class="d-flex align-center pa-4 pb-2">
        <v-icon start color="primary">mdi-link-variant</v-icon>
        Матчинг платежа
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" @click="dialog = false" />
      </v-card-title>

      <v-divider />

      <v-card-text class="pa-4">
        <!-- Payment info block -->
        <v-sheet rounded="lg" color="blue-grey-lighten-5" class="pa-3 mb-4">
          <div class="text-caption font-weight-medium text-medium-emphasis mb-2">ПЛАТЁЖ</div>
          <div v-if="payment" class="d-flex flex-wrap gap-x-6 gap-y-1 text-body-2">
            <span><b>Дата:</b> {{ fmtDate(payment.payment_date) }}</span>
            <span><b>Сумма:</b> {{ formatMoney(payment.amount) }}</span>
            <span><b>№ п/п:</b> {{ payment.payment_number || '—' }}</span>
          </div>
          <div v-if="payment" class="mt-1 text-body-2">
            <b>Получатель:</b> {{ payment.payee_name || '—' }}
            <span v-if="payment.payee_inn" class="text-medium-emphasis ml-1">(ИНН {{ payment.payee_inn }})</span>
          </div>
          <div v-if="payment?.parsed_contract_number" class="mt-1 text-body-2">
            <b>Распознанный договор:</b>
            <v-chip size="x-small" color="blue" variant="tonal" class="ml-1">{{ payment.parsed_contract_number }}</v-chip>
          </div>
          <div v-if="payment?.purpose_text" class="mt-1 text-caption text-medium-emphasis text-truncate" :title="payment.purpose_text">
            {{ payment.purpose_text }}
          </div>
          <div v-if="!payment && loadingPayment" class="text-caption text-medium-emphasis">Загрузка...</div>
        </v-sheet>

        <!-- 27.4-20: Suggested matches block -->
        <div v-if="suggestions.length" class="mb-4">
          <div class="text-subtitle-2 mb-2 d-flex align-center">
            <v-icon start size="small" color="warning">mdi-lightbulb-on</v-icon>
            Рекомендуемые варианты
            <v-spacer />
            <v-btn size="x-small" variant="text" :loading="loadingSuggestions" @click="loadSuggestions">Обновить</v-btn>
          </div>
          <v-sheet rounded="lg" border>
            <v-list density="compact" class="pa-0">
              <v-list-item
                v-for="(s, idx) in suggestions"
                :key="idx"
                :active="appliedSuggestionIdx === idx"
                @click="applySuggestion(s, idx)"
                class="suggestion-item"
              >
                <template #prepend>
                  <v-chip size="x-small" :color="suggestionColor(s.score)" variant="flat" class="mr-2">
                    {{ s.score }}
                  </v-chip>
                </template>
                <v-list-item-title class="text-body-2 font-weight-medium">
                  {{ s.label }}
                </v-list-item-title>
                <v-list-item-subtitle class="text-caption">
                  {{ s.purchase_names.join(' + ') }}
                  <span class="text-medium-emphasis ml-1">
                    ({{ s.purchase_amounts.map((a: number) => formatMoney(a)).join(' + ') }})
                  </span>
                </v-list-item-subtitle>
                <template #append>
                  <v-icon v-if="appliedSuggestionIdx === idx" color="success">mdi-check-circle</v-icon>
                  <v-btn v-else size="x-small" variant="tonal" color="primary">Применить</v-btn>
                </template>
              </v-list-item>
            </v-list>
          </v-sheet>
          <div class="text-caption text-medium-emphasis mt-1">
            Клик по варианту → автоматически выберет контракт и закупки. Нажмите «Подтвердить» внизу.
          </div>
        </div>

        <!-- Contract selection -->
        <div class="mb-4">
          <div class="text-subtitle-2 mb-2">Договор</div>

          <div v-if="payment?.matched_contract_id && !changingContract" class="d-flex align-center gap-2">
            <v-chip color="success" variant="tonal" prepend-icon="mdi-check-circle">
              {{ payment.matched_contract_number || 'Договор #' + payment.matched_contract_id }}
            </v-chip>
            <v-btn size="x-small" variant="text" @click="changingContract = true">Изменить</v-btn>
          </div>

          <v-autocomplete
            v-else
            v-model="selectedContract"
            :items="contractItems"
            :loading="loadingContracts"
            :search="contractSearch"
            @update:search="onContractSearch"
            item-title="display"
            item-value="id"
            return-object
            label="Поиск договора"
            placeholder="Введите номер или название..."
            variant="outlined"
            density="compact"
            hide-details
            clearable
            no-filter
            :hint="payment?.payee_inn ? `ИНН получателя: ${payment.payee_inn}` : ''"
            persistent-hint
          >
            <template #item="{ item, props }">
              <v-list-item v-bind="props" :title="item.raw.number" :subtitle="item.raw.contractor_name || ''" />
            </template>
          </v-autocomplete>
        </div>

        <!-- Purchases list -->
        <div v-if="effectiveContractId">
          <div class="d-flex align-center mb-2">
            <div class="text-subtitle-2">Закупки по договору</div>
            <v-spacer />
            <v-btn
              v-if="purchases.length"
              size="x-small"
              variant="text"
              @click="toggleAll"
            >{{ selectedPurchases.length === purchases.length ? 'Снять все' : 'Выбрать все' }}</v-btn>
          </div>

          <div v-if="loadingPurchases" class="d-flex justify-center py-3">
            <v-progress-circular indeterminate size="24" />
          </div>

          <div v-else-if="!purchases.length" class="text-caption text-medium-emphasis pa-2">
            Нет подходящих закупок по этому договору
          </div>

          <v-sheet v-else rounded="lg" border class="overflow-hidden">
            <v-list density="compact" class="pa-0">
              <v-list-item
                v-for="p in purchases"
                :key="p.id"
                class="purchase-item"
                @click="togglePurchase(p.id)"
              >
                <template #prepend>
                  <v-checkbox-btn
                    :model-value="selectedPurchases.includes(p.id)"
                    color="primary"
                    @click.stop="togglePurchase(p.id)"
                  />
                </template>
                <v-list-item-title class="text-body-2">
                  <span class="font-weight-medium">{{ p.short_name || p.purchase_name || '—' }}</span>
                </v-list-item-title>
                <v-list-item-subtitle class="text-caption">
                  Статус: {{ p.status }} · Сумма: {{ formatMoney(p.amount) }}
                </v-list-item-subtitle>
              </v-list-item>
            </v-list>
          </v-sheet>

          <!-- Preview -->
          <v-alert
            v-if="selectedPurchases.length"
            density="compact"
            type="info"
            variant="tonal"
            class="mt-3 text-body-2"
          >
            Будет создано {{ selectedPurchases.length }} платежей
            по {{ payment ? formatMoney(payment.amount / selectedPurchases.length) : '—' }} каждый
          </v-alert>
        </div>
      </v-card-text>

      <v-divider />

      <v-card-actions class="pa-4 gap-2">
        <v-btn variant="text" @click="dialog = false">Отмена</v-btn>
        <v-spacer />
        <v-btn
          variant="outlined"
          color="primary"
          :loading="savingMatch"
          :disabled="!effectiveContractId"
          @click="saveMatch"
        >
          Сохранить привязку
        </v-btn>
        <v-btn
          color="success"
          variant="elevated"
          :loading="confirming"
          :disabled="!effectiveContractId || !selectedPurchases.length"
          @click="confirm"
        >
          Подтвердить и создать платежи
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { apiFetch } from '@/api'
import { useToast } from '@/composables/useToast'

// ── Props & emits ──────────────────────────────────────────────────────────
const props = defineProps<{
  bankPaymentId: number | null
}>()

const emit = defineEmits<{
  (e: 'updated'): void
}>()

// ── State ──────────────────────────────────────────────────────────────────
const dialog = defineModel<boolean>({ default: false })

const { success, error } = useToast()

// Payment data
interface BankPayment {
  id: number
  payment_date: string
  payment_number: string | null
  amount: number
  payer_name: string | null
  payee_name: string | null
  payee_inn: string | null
  parsed_contract_number: string | null
  purpose_text: string | null
  matched_contract_id: number | null
  matched_contract_number: string | null
  matched_confirmed: boolean
}
const payment = ref<BankPayment | null>(null)
const loadingPayment = ref(false)

// Contract search
interface Contract {
  id: number
  number: string
  contractor_name: string | null
  display: string
}
const contractItems = ref<Contract[]>([])
const loadingContracts = ref(false)
const contractSearch = ref('')
const selectedContract = ref<Contract | null>(null)
const changingContract = ref(false)
let searchTimeout: ReturnType<typeof setTimeout> | null = null

// Purchases
interface Purchase {
  id: number
  short_name: string | null
  purchase_name: string | null
  status: string
  amount: number
}
const purchases = ref<Purchase[]>([])
const loadingPurchases = ref(false)
const selectedPurchases = ref<number[]>([])

// Actions
const savingMatch = ref(false)
const confirming = ref(false)

// 27.4-20: Match suggestions
interface MatchSuggestion {
  purchase_ids: number[]
  purchase_names: string[]
  purchase_amounts: number[]
  score: number
  kind: string
  label: string
}
const suggestions = ref<MatchSuggestion[]>([])
const loadingSuggestions = ref(false)
const appliedSuggestionIdx = ref<number | null>(null)

function suggestionColor(score: number): string {
  if (score >= 95) return 'success'
  if (score >= 80) return 'primary'
  if (score >= 50) return 'warning'
  return 'grey'
}

async function loadSuggestions() {
  if (!props.bankPaymentId) return
  loadingSuggestions.value = true
  try {
    const data = await apiFetch<{candidates: MatchSuggestion[]}>(
      `/payments/registry/${props.bankPaymentId}/match-suggestions`)
    suggestions.value = data.candidates || []
  } catch {
    suggestions.value = []
  } finally {
    loadingSuggestions.value = false
  }
}

async function applySuggestion(s: MatchSuggestion, idx: number) {
  appliedSuggestionIdx.value = idx
  // Если контракт ещё не выбран — подгрузим закупки нет нужды (purchase_ids известны)
  selectedPurchases.value = [...s.purchase_ids]
  // Если контракт известен из payment.matched_contract_id — оставим, иначе подгрузим автоматом
  // (apply сразу пытается активировать confirm)
}

// ── Computed ───────────────────────────────────────────────────────────────
const effectiveContractId = computed<number | null>(() => {
  if (selectedContract.value) return selectedContract.value.id
  if (!changingContract.value && payment.value?.matched_contract_id) {
    return payment.value.matched_contract_id
  }
  return null
})

// ── Watch ──────────────────────────────────────────────────────────────────
watch(dialog, async (val) => {
  if (val && props.bankPaymentId) {
    resetState()
    await loadPayment()
  }
})

watch(effectiveContractId, async (id) => {
  if (id) {
    await loadPurchases(id)
  } else {
    purchases.value = []
    selectedPurchases.value = []
  }
})

// ── Methods ────────────────────────────────────────────────────────────────
function resetState() {
  payment.value = null
  contractItems.value = []
  contractSearch.value = ''
  selectedContract.value = null
  changingContract.value = false
  purchases.value = []
  selectedPurchases.value = []
  suggestions.value = []
  appliedSuggestionIdx.value = null
}

async function loadPayment() {
  if (!props.bankPaymentId) return
  loadingPayment.value = true
  try {
    payment.value = await apiFetch<BankPayment>(`/payments/registry/${props.bankPaymentId}`)
    // Pre-load contract suggestions using payee_inn
    if (payment.value.payee_inn) {
      await searchContracts(payment.value.payee_inn)
    }
    // 27.4-20: подгружаем ранжированные suggestions параллельно
    loadSuggestions()
  } catch (e: any) {
    error('Не удалось загрузить данные платежа: ' + e.detail)
  } finally {
    loadingPayment.value = false
  }
}

async function searchContracts(query: string) {
  loadingContracts.value = true
  try {
    const params = new URLSearchParams({ search: query, limit: '20' })
    if (payment.value?.payee_inn) {
      params.set('contractor_inn', payment.value.payee_inn)
    }
    const data = await apiFetch<{ items: any[] }>(`/contracts?${params}`)
    const raw = Array.isArray(data) ? data : (data as any).items ?? []
    contractItems.value = raw.map((c: any) => ({
      id: c.id,
      number: c.number,
      contractor_name: c.contractor_name || null,
      display: c.contractor_name ? `${c.number} — ${c.contractor_name}` : c.number,
    }))
  } catch {
    contractItems.value = []
  } finally {
    loadingContracts.value = false
  }
}

function onContractSearch(q: string) {
  if (searchTimeout) clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => {
    if (q && q.length >= 2) searchContracts(q)
  }, 350)
}

async function loadPurchases(contractId: number) {
  loadingPurchases.value = true
  purchases.value = []
  selectedPurchases.value = []
  try {
    const params = new URLSearchParams({
      contract_id: String(contractId),
      limit: '200',
    })
    const data = await apiFetch<any>(`/purchases/?${params}`)
    const raw: any[] = Array.isArray(data) ? data : (data as any).items ?? []
    // Filter to actionable statuses on client
    const ACTIVE_STATUSES = ['delivered', 'contracted', 'ordered', 'work_in_progress', 'approved']
    purchases.value = raw
      .filter((p: any) => ACTIVE_STATUSES.includes(p.status))
      .map((p: any) => ({
        id: p.id,
        short_name: p.short_name || null,
        purchase_name: p.purchase_name || null,
        status: p.status,
        amount: p.amount ?? 0,
      }))
  } catch (e: any) {
    error('Не удалось загрузить закупки: ' + (e.detail || ''))
  } finally {
    loadingPurchases.value = false
  }
}

function togglePurchase(id: number) {
  const idx = selectedPurchases.value.indexOf(id)
  if (idx === -1) selectedPurchases.value.push(id)
  else selectedPurchases.value.splice(idx, 1)
}

function toggleAll() {
  if (selectedPurchases.value.length === purchases.value.length) {
    selectedPurchases.value = []
  } else {
    selectedPurchases.value = purchases.value.map(p => p.id)
  }
}

async function saveMatch() {
  if (!props.bankPaymentId || !effectiveContractId.value) return
  savingMatch.value = true
  try {
    await apiFetch(`/payments/registry/${props.bankPaymentId}/match`, {
      method: 'PATCH',
      body: JSON.stringify({ contract_id: effectiveContractId.value }),
    })
    success('Договор привязан')
    dialog.value = false
    emit('updated')
  } catch (e: any) {
    error('Ошибка привязки: ' + (e.detail || ''))
  } finally {
    savingMatch.value = false
  }
}

async function confirm() {
  if (!props.bankPaymentId || !selectedPurchases.value.length) return
  confirming.value = true
  try {
    const result = await apiFetch<{ payments_created: number }>(`/payments/registry/${props.bankPaymentId}/confirm`, {
      method: 'POST',
      body: JSON.stringify({ purchase_ids: selectedPurchases.value }),
    })
    const n = result?.payments_created ?? selectedPurchases.value.length
    success(`${n} платежей создано`)
    dialog.value = false
    emit('updated')
  } catch (e: any) {
    error('Ошибка подтверждения: ' + (e.detail || ''))
  } finally {
    confirming.value = false
  }
}

// ── Helpers ────────────────────────────────────────────────────────────────
function fmtDate(d: string | null) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('ru-RU')
}

function formatMoney(v: number | null | undefined) {
  if (v == null) return '—'
  return new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 2 }).format(v)
}
</script>

<style scoped>
.purchase-item {
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}
.purchase-item:last-child {
  border-bottom: none;
}
</style>
