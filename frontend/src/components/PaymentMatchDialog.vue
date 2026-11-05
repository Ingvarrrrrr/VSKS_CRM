<template>
  <v-dialog v-model="dialog" max-width="720" scrollable :fullscreen="mobile">
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
          <div v-if="payment?.purpose_text" class="mt-2">
            <PaymentPurposeCell :text="payment.purpose_text" />
          </div>
          <div v-if="!payment && loadingPayment" class="text-caption text-medium-emphasis">Загрузка...</div>
        </v-sheet>

        <v-tabs v-model="matchMode" density="compact" color="primary" class="mb-3">
          <v-tab value="subsidy">По закупкам субсидии (1 или несколько)</v-tab>
          <v-tab value="contract">По договору</v-tab>
        </v-tabs>

        <div v-if="matchMode === 'subsidy'">
          <v-autocomplete
            v-model="selectedSubsidyId"
            :items="subsidyOptions"
            item-title="name"
            item-value="id"
            label="Субсидия"
            density="compact"
            variant="outlined"
            hide-details
            class="mb-3"
          />

          <div v-if="loadingSubsidyCandidates" class="d-flex justify-center py-4">
            <v-progress-circular indeterminate size="28" color="primary" />
          </div>
          <template v-else-if="selectedSubsidyId">
            <!-- Сводка выбранных закупок -->
            <v-sheet
              v-if="subSelectedIds.length > 0"
              rounded="lg"
              border
              class="pa-3 mb-3"
              :class="Math.abs(subDelta) <= 0.02 ? 'bg-green-lighten-5' : 'bg-amber-lighten-5'"
            >
              <div class="d-flex align-center justify-space-between flex-wrap gap-2 text-body-2">
                <div>
                  <b>Выбрано закупок: {{ subSelectedIds.length }} шт.</b>
                  · Сумма: <b>{{ formatMoney(subSelectedTotal) }}</b>
                  · Разница (Δ):
                  <b :class="Math.abs(subDelta) <= 0.02 ? 'text-success' : 'text-warning'">
                    {{ subDelta > 0 ? '+' : '' }}{{ formatMoney(subDelta) }}
                  </b>
                </div>
                <v-btn size="x-small" variant="text" @click="subSelectedIds = []">Сбросить</v-btn>
              </div>
              <v-checkbox
                v-if="subSelectedIds.length > 1"
                v-model="subMergePurchases"
                density="compact"
                hide-details
                color="primary"
                class="mt-1"
                label="Объединить выбранные позиции в одну общую закупку и проставить контрагента"
              />
              <v-checkbox
                v-if="Math.abs(subDelta) > 0.02"
                v-model="subApproveDiff"
                density="compact"
                hide-details
                color="warning"
                class="mt-1"
                label="Согласовать расхождение суммы для привязки"
              />
            </v-sheet>

            <!-- Найденные комбинации по сумме -->
            <div v-if="subCombos.length" class="mb-3">
              <div class="text-caption font-weight-bold mb-1">Автоматически найденные комбинации по сумме:</div>
              <v-list density="compact" class="border rounded pa-1">
                <v-list-item
                  v-for="(cs, cIdx) in subCombos"
                  :key="'sc-' + cIdx"
                  class="mb-1 rounded border"
                  @click="selectSubCombo(cs.purchase_ids)"
                >
                  <template #prepend>
                    <v-checkbox-btn
                      :model-value="isSubComboSelected(cs.purchase_ids)"
                      color="primary"
                      density="compact"
                      @click.stop="selectSubCombo(cs.purchase_ids)"
                    />
                  </template>
                  <v-list-item-title class="text-body-2 font-weight-medium">
                    {{ cs.probability_label }} · {{ cs.count }} поз. = {{ formatMoney(cs.total_amount) }}
                  </v-list-item-title>
                  <v-list-item-subtitle class="text-caption">
                    {{ (cs.items || []).map((i: any) => `${i.registry_number || '#' + i.purchase_id} ${i.subject || ''} (${formatMoney(i.amount)})`).join(' + ') }}
                  </v-list-item-subtitle>
                </v-list-item>
              </v-list>
            </div>

            <!-- Поиск и мультивыбор из всех закупок субсидии -->
            <v-text-field
              v-model="subPurchaseSearch"
              density="compact"
              variant="outlined"
              prepend-inner-icon="mdi-magnify"
              placeholder="Поиск закупок по номеру, сумме, предмету или категории ФЭО..."
              clearable
              hide-details
              class="mb-2"
            />
            <v-list density="compact" style="max-height: 280px; overflow-y: auto;" class="border rounded pa-1">
              <v-list-item
                v-for="p in filteredSubPurchases"
                :key="'sp-' + p.purchase_id"
                class="mb-1 rounded border"
                :active="subSelectedIds.includes(p.purchase_id)"
                @click="toggleSubPurchase(p.purchase_id)"
              >
                <template #prepend>
                  <v-checkbox-btn
                    :model-value="subSelectedIds.includes(p.purchase_id)"
                    color="primary"
                    density="compact"
                    @click.stop="toggleSubPurchase(p.purchase_id)"
                  />
                </template>
                <v-list-item-title class="text-body-2 font-weight-medium">
                  {{ p.registry_number || `#${p.purchase_id}` }}
                  <span v-if="p.is_temp_plan" class="text-caption text-deep-purple">(План закупок «Да»)</span>
                  — {{ p.subject || '—' }}
                </v-list-item-title>
                <v-list-item-subtitle class="text-caption">
                  {{ p.contractor_name || 'Без контрагента' }} · <b>{{ formatMoney(p.contract_price || 0) }}</b>
                </v-list-item-subtitle>
                <div v-if="p.feo_category_path" class="text-caption text-medium-emphasis">
                  {{ p.feo_category_path }} › {{ p.subject || '—' }}
                </div>
              </v-list-item>
            </v-list>
          </template>
        </div>

        <div v-else>
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
                  <!-- Задача 04.10.2026: месяц оказания для помесячной закупки (или причина,
                       почему он неоднозначен) — см. app/services/match_candidates.py -->
                  <div v-if="s.service_period" class="mt-1">
                    <v-chip size="x-small" color="primary" variant="tonal" prepend-icon="mdi-calendar-check">
                      за месяц: {{ fmtMonth(s.service_period) }}
                    </v-chip>
                  </div>
                  <div v-else-if="s.service_period_conflict" class="mt-1 text-warning">
                    <v-icon size="12" color="warning">mdi-alert</v-icon>
                    {{ s.service_period_conflict }}
                  </div>
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
        </div>
      </v-card-text>

      <v-divider />

      <v-card-actions class="pa-4 gap-2">
        <v-btn variant="text" @click="dialog = false">Отмена</v-btn>
        <v-spacer />
        <template v-if="matchMode === 'subsidy'">
          <v-btn
            color="primary"
            variant="elevated"
            :loading="attachingSubCombo"
            :disabled="!selectedSubsidyId || subSelectedIds.length === 0"
            @click="confirmSubsidyCombo"
          >
            {{ subSelectedIds.length > 1 && subMergePurchases ? `Объединить (${subSelectedIds.length} поз.) и привязать` : `Привязать (${subSelectedIds.length} шт.)` }}
          </v-btn>
        </template>
        <template v-else>
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
        </template>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- Задача 04.10.2026: 409 «конфликт месяца оказания» при подтверждении — не
       снэкбаром и не молча, а выбором месяца человеком с повтором запроса. -->
  <ServicePeriodPickDialog
    v-model="servicePeriodDialog"
    :reason="servicePeriodReason"
    @submit="onServicePeriodPicked"
    @cancel="servicePeriodPendingPurchaseId = null"
  />
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { apiFetch } from '@/api'
import ServicePeriodPickDialog from '@/components/payments/ServicePeriodPickDialog.vue'
import PaymentPurposeCell from '@/components/subsidies/PaymentPurposeCell.vue'
import { isServicePeriodConflict, extractConflictPurchaseId, extractConflictMessage } from '@/composables/payments/useServicePeriodConflict'

const { mobile } = useDisplay()
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

// ── Режим сопоставления по закупкам субсидии (1 или несколько сразу) ──────
const matchMode = ref<'subsidy' | 'contract'>('subsidy')
const subsidyOptions = ref<{ id: number; name: string }[]>([])
const selectedSubsidyId = ref<number | null>(null)
const loadingSubsidyCandidates = ref(false)
const subCombos = ref<any[]>([])
const subAllPurchases = ref<any[]>([])
const subPurchaseSearch = ref('')
const subSelectedIds = ref<number[]>([])
const subMergePurchases = ref(true)
const subApproveDiff = ref(false)
const attachingSubCombo = ref(false)

const filteredSubPurchases = computed(() => {
  const q = (subPurchaseSearch.value || '').trim().toLowerCase()
  if (!q) return subAllPurchases.value
  return subAllPurchases.value.filter((p: any) => {
    const t = `${p.registry_number || ''} ${p.subject || ''} ${p.feo_category_path || ''} ${p.contractor_name || ''} ${p.contract_price || ''}`.toLowerCase()
    return t.includes(q)
  })
})

const subSelectedTotal = computed(() => {
  const map = new Map<number, number>()
  for (const cs of subCombos.value) {
    for (const it of cs.items || []) map.set(it.purchase_id, Number(it.amount || 0))
  }
  for (const p of subAllPurchases.value) {
    map.set(p.purchase_id, Number(p.contract_price || 0))
  }
  return subSelectedIds.value.reduce((s, id) => s + (map.get(id) || 0), 0)
})

const subDelta = computed(() => {
  const bpAmt = Number(payment.value?.amount || 0)
  return Math.round((bpAmt - subSelectedTotal.value) * 100) / 100
})

function toggleSubPurchase(pid: number) {
  const idx = subSelectedIds.value.indexOf(pid)
  if (idx >= 0) subSelectedIds.value.splice(idx, 1)
  else subSelectedIds.value.push(pid)
}

function isSubComboSelected(pids: number[]): boolean {
  if (!pids?.length || subSelectedIds.value.length !== pids.length) return false
  const set = new Set(subSelectedIds.value)
  return pids.every(id => set.has(id))
}

function selectSubCombo(pids: number[]) {
  if (isSubComboSelected(pids)) subSelectedIds.value = []
  else subSelectedIds.value = [...pids]
}

async function loadSubsidyList() {
  if (subsidyOptions.value.length) return
  try {
    const res = await apiFetch<any>('/subsidies/')
    const list = Array.isArray(res) ? res : (res?.items || [])
    subsidyOptions.value = list.map((s: any) => ({ id: s.id, name: s.name || s.title || `Субсидия #${s.id}` }))
  } catch {
    subsidyOptions.value = []
  }
}

async function loadSubsidyCandidates(sid: number | null) {
  if (!sid || !props.bankPaymentId) return
  loadingSubsidyCandidates.value = true
  subCombos.value = []
  subAllPurchases.value = []
  subSelectedIds.value = []
  try {
    const res = await apiFetch<any>(`/subsidies/${sid}/payment-control/bank-payments/${props.bankPaymentId}/candidates`)
    subCombos.value = res.combo_suggestions || []
    subAllPurchases.value = res.all_unpaid_purchases || []
    if (subCombos.value.length > 0 && !subCombos.value[0].needs_amount_approval) {
      subSelectedIds.value = [...subCombos.value[0].purchase_ids]
    }
  } catch {
    subCombos.value = []
    subAllPurchases.value = []
  } finally {
    loadingSubsidyCandidates.value = false
  }
}

watch(selectedSubsidyId, (sid) => {
  if (sid && dialog.value) loadSubsidyCandidates(sid)
})

async function confirmSubsidyCombo() {
  if (!selectedSubsidyId.value || !props.bankPaymentId || !subSelectedIds.value.length) return
  attachingSubCombo.value = true
  try {
    const res = await apiFetch<any>(
      `/subsidies/${selectedSubsidyId.value}/payment-control/bank-payments/${props.bankPaymentId}/attach-combo`,
      {
        method: 'POST',
        body: JSON.stringify({
          purchase_ids: subSelectedIds.value,
          merge_purchases: subMergePurchases.value && subSelectedIds.value.length > 1,
          approve_amount_diff: subApproveDiff.value,
        }),
      },
    )
    success(
      res.merged
        ? `Позиции (${res.merged_count} шт.) объединены в закупку ${res.registry_number || '#' + res.primary_purchase_id} и привязаны к платёжке`
        : 'Выбранные закупки привязаны к платёжке',
    )
    dialog.value = false
    emit('updated')
  } catch (e: any) {
    error('Не удалось привязать закупки: ' + (e?.payload?.message || e?.detail || e?.message || ''))
  } finally {
    attachingSubCombo.value = false
  }
}

// 27.4-20: Match suggestions
interface MatchSuggestion {
  purchase_ids: number[]
  purchase_names: string[]
  purchase_amounts: number[]
  score: number
  kind: string
  label: string
  service_period?: string | null
  service_period_conflict?: string | null
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
  servicePeriodOverrides.value = {}
  servicePeriodPendingPurchaseId.value = null
  servicePeriodReason.value = null
}

async function loadPayment() {
  if (!props.bankPaymentId) return
  loadingPayment.value = true
  try {
    payment.value = await apiFetch<BankPayment>(`/payments/registry/${props.bankPaymentId}`)
    await loadSubsidyList()
    const anyPay = payment.value as any
    if (anyPay?.matched_subsidy_id) {
      selectedSubsidyId.value = anyPay.matched_subsidy_id
    } else if (!selectedSubsidyId.value && subsidyOptions.value.length > 0) {
      selectedSubsidyId.value = subsidyOptions.value[0].id
    } else if (selectedSubsidyId.value) {
      await loadSubsidyCandidates(selectedSubsidyId.value)
    }
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

// Задача 04.10.2026: месяц оказания, выбранный человеком вручную после 409
// («Закупка №{id}: ... месяц ...») — {purchase_id: 'YYYY-MM-01'}, копится между
// повторами, если конфликтов на разные помесячные закупки несколько подряд.
const servicePeriodOverrides = ref<Record<number, string>>({})
const servicePeriodDialog = ref(false)
const servicePeriodReason = ref<string | null>(null)
const servicePeriodPendingPurchaseId = ref<number | null>(null)

async function confirm() {
  if (!props.bankPaymentId || !selectedPurchases.value.length) return
  confirming.value = true
  try {
    const result = await apiFetch<{ payments_created: number }>(`/payments/registry/${props.bankPaymentId}/confirm`, {
      method: 'POST',
      body: JSON.stringify({
        purchase_ids: selectedPurchases.value,
        service_periods: Object.keys(servicePeriodOverrides.value).length ? servicePeriodOverrides.value : undefined,
      }),
    })
    const n = result?.payments_created ?? selectedPurchases.value.length
    success(`${n} платежей создано`)
    servicePeriodOverrides.value = {}
    dialog.value = false
    emit('updated')
  } catch (e: any) {
    if (isServicePeriodConflict(e)) {
      // Бэк не определил месяц сам — открываем диалог ручного выбора вместо
      // snackbar-а; извлекаем id закупки из текста причины, иначе отдаём на
      // единственную выбранную закупку (edge-case race-backstop без id в тексте).
      servicePeriodPendingPurchaseId.value =
        extractConflictPurchaseId(e) ?? (selectedPurchases.value.length === 1 ? selectedPurchases.value[0] : null)
      servicePeriodReason.value = extractConflictMessage(e)
      servicePeriodDialog.value = true
    } else {
      error('Ошибка подтверждения: ' + (e.detail || ''))
    }
  } finally {
    confirming.value = false
  }
}

async function onServicePeriodPicked(isoDate: string) {
  const pid = servicePeriodPendingPurchaseId.value
  if (pid == null) {
    error('Не удалось определить закупку для выбранного месяца — повторите подтверждение вручную')
    return
  }
  servicePeriodOverrides.value = { ...servicePeriodOverrides.value, [pid]: isoDate }
  servicePeriodPendingPurchaseId.value = null
  await confirm()
}

// ── Helpers ────────────────────────────────────────────────────────────────
function fmtDate(d: string | null) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('ru-RU')
}

const MONTH_NAMES_RU = [
  'январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
  'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь',
]
function fmtMonth(iso: string) {
  // iso = 'YYYY-MM-DD' (первое число месяца, см. payments.service_period)
  const [y, m] = iso.split('-')
  const idx = Number(m) - 1
  return `${MONTH_NAMES_RU[idx] ?? m} ${y}`
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
