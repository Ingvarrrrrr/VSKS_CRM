<template>
  <v-dialog v-model="dialog" max-width="860" scrollable>
    <v-card>
      <v-card-title class="d-flex align-center pa-4 pb-2">
        <v-icon start color="primary">mdi-link-variant-plus</v-icon>
        Сопоставить платёж с одной или несколькими закупками
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" @click="dialog = false" />
      </v-card-title>
      <v-card-text class="pa-4">
        <div v-if="loading" class="d-flex justify-center py-6">
          <v-progress-circular indeterminate color="primary" />
        </div>
        <template v-else>
          <!-- Информация о платёжке из выписки -->
          <v-sheet v-if="bankPayment" rounded="lg" border class="pa-3 mb-3 bg-grey-lighten-4 text-body-2">
            <div class="d-flex align-center justify-space-between flex-wrap gap-2 mb-1">
              <div>
                <v-chip size="x-small" color="deep-purple" variant="flat" class="mr-2">
                  ПП №{{ bankPayment.payment_number || bankPayment.id }}
                  {{ bankPayment.payment_date ? 'от ' + new Date(bankPayment.payment_date).toLocaleDateString('ru-RU') : '' }}
                </v-chip>
                <b>{{ bankPayment.payee_name || 'Получатель не указан' }}</b>
                <span v-if="bankPayment.payee_inn" class="text-caption text-medium-emphasis ml-1">(ИНН {{ bankPayment.payee_inn }})</span>
              </div>
              <div class="text-subtitle-1 font-weight-bold text-primary">
                {{ formatCurrency(bankPayment.amount) }}
              </div>
            </div>
            <div v-if="bankPayment.expense_direction" class="text-caption text-primary mt-1" style="line-height: 1.3;">
              <b>Направление расходов (выписка):</b> {{ bankPayment.expense_direction }}
            </div>
            <div class="mt-1" style="white-space: normal; word-break: break-word; line-height: 1.35;">
              <b>Назначение платежа:</b> {{ bankPayment.purpose_text || '—' }}
            </div>

            <!-- Если платёж уже сопоставлен — показываем текущую привязку и кнопку «Отвязать» -->
            <v-alert
              v-if="bankPayment.currently_attached && bankPayment.currently_attached.length"
              type="success"
              variant="tonal"
              density="compact"
              class="mt-2 mb-0"
            >
              <div class="d-flex align-center justify-space-between flex-wrap gap-2">
                <div>
                  <div class="font-weight-bold text-caption">Сейчас платёж уже привязан к закупке:</div>
                  <div v-for="ca in bankPayment.currently_attached" :key="ca.purchase_id" class="text-caption">
                    <b>{{ ca.registry_number || '#' + ca.purchase_id }}</b>
                    <span v-if="ca.sheet_ref"> ({{ ca.sheet_ref }})</span>
                    — {{ ca.subject || '—' }} ({{ formatCurrency(ca.amount) }})
                  </div>
                </div>
                <v-btn
                  size="x-small"
                  color="error"
                  variant="tonal"
                  prepend-icon="mdi-link-off"
                  :loading="detaching"
                  @click="onDetach"
                >
                  Отвязать платёж
                </v-btn>
              </div>
            </v-alert>
          </v-sheet>

          <!-- Панель выбранных закупок (1 или несколько сразу) и сверки суммы -->
          <v-sheet
            v-if="selectedPurchaseIds.length > 0"
            rounded="lg"
            border
            class="pa-3 mb-3"
            :class="Math.abs(selectedDelta) <= 0.02 ? 'bg-green-lighten-5' : 'bg-amber-lighten-5'"
          >
            <div class="d-flex align-center justify-space-between flex-wrap gap-2">
              <div class="text-body-2">
                <b>Выбрано закупок: {{ selectedPurchaseIds.length }} шт.</b>
                · Сумма выбранных: <b>{{ formatCurrency(selectedTotalAmount) }}</b>
                · Платёжка: <b>{{ formatCurrency(bankPayment?.amount || 0) }}</b>
                · Разница (Δ):
                <b :class="Math.abs(selectedDelta) <= 0.02 ? 'text-success' : 'text-warning'">
                  {{ selectedDelta > 0 ? '+' : '' }}{{ formatCurrency(selectedDelta) }}
                </b>
              </div>
              <v-btn size="x-small" variant="text" color="grey-darken-1" @click="clearSelection">
                Сбросить выбор
              </v-btn>
            </div>

            <div class="d-flex flex-wrap gap-1 mt-2">
              <v-chip
                v-for="sp in selectedPurchaseObjects"
                :key="sp.purchase_id"
                size="small"
                closable
                color="primary"
                variant="tonal"
                @click:close="togglePurchase(sp.purchase_id)"
              >
                {{ sp.registry_number || '#' + sp.purchase_id }} · {{ truncate(sp.subject || '—', 32) }} ({{ formatCurrency(sp.amount) }})
              </v-chip>
            </div>

            <v-checkbox
              v-if="selectedPurchaseIds.length > 1"
              v-model="mergePurchases"
              density="compact"
              hide-details
              color="primary"
              class="mt-2"
              label="Объединить выбранные позиции в одну общую закупку и проставить контрагента из платёжки"
            />

            <v-checkbox
              v-if="needsAmountApproval"
              v-model="approveAmountDiff"
              density="compact"
              hide-details
              color="warning"
              class="mt-1"
              :label="`Согласовать расхождение суммы (${selectedDelta > 0 ? '+' : ''}${selectedDelta.toFixed(2).replace('.', ',')} ₽) для привязки`"
            />
          </v-sheet>

          <div v-if="!items.length && !combos.length && !signHints.length && !allPurchases.length" class="text-caption text-medium-emphasis py-4">
            Подходящих закупок или комбинаций сумм не найдено
          </div>
          <template v-else>
            <!-- 1. Составные варианты (Subset Sum) с ранжированием по категориям -->
            <div v-if="combos.length" class="mb-4">
              <div class="text-subtitle-2 font-weight-bold mb-2">
                Автоматически найденные варианты по сумме (нажмите, чтобы выбрать всю комбинацию):
              </div>
              <v-list density="compact">
                <v-list-item
                  v-for="(cs, idx) in combos"
                  :key="'combo-' + idx"
                  class="mb-2 rounded border"
                  :active="isComboSelected(cs)"
                  @click="selectCombo(cs)"
                >
                  <template #prepend>
                    <v-checkbox-btn
                      :model-value="isComboSelected(cs)"
                      color="primary"
                      density="compact"
                      @click.stop="selectCombo(cs)"
                    />
                  </template>
                  <div class="d-flex align-center flex-wrap gap-2 mb-1">
                    <v-chip
                      size="x-small"
                      :color="probColor(cs.probability)"
                      variant="flat"
                    >
                      {{ cs.probability_label }}
                    </v-chip>
                    <span class="font-weight-medium text-body-2">
                      {{ cs.count > 1 ? `Комбинация из ${cs.count} поз. = ${formatCurrency(cs.total_amount)}` : `Сумма закупки = ${formatCurrency(cs.total_amount)}` }}
                    </span>
                  </div>
                  <div class="text-body-2 mb-1">
                    <div v-for="it in cs.items" :key="it.purchase_id" class="d-flex align-center flex-wrap gap-1">
                      <v-chip size="x-small" variant="tonal" :color="it.is_temp_plan ? 'deep-purple' : 'primary'">
                        {{ it.registry_number || `#${it.purchase_id}` }}
                      </v-chip>
                      <v-chip v-if="it.is_temp_plan" size="x-small" color="deep-purple" variant="flat">
                        План закупок («Да») · временная
                      </v-chip>
                      <span v-if="it.sheet_ref" class="text-caption text-medium-emphasis">({{ it.sheet_ref }})</span>
                      <span>{{ it.subject || '—' }}</span>
                      <span class="font-weight-bold">({{ formatCurrency(it.amount) }})</span>
                      <span v-if="!it.contractor_name" class="text-caption text-warning">
                        · без контрагента
                      </span>
                      <div v-if="it.feo_category_name" class="text-caption text-medium-emphasis w-100" style="line-height: 1.25;">
                        <v-icon icon="mdi-folder-outline" size="12" class="mr-1" />{{ it.feo_category_name }} › {{ it.subject || '—' }}
                      </div>
                    </div>
                  </div>
                  <div class="text-caption text-medium-emphasis">
                    {{ cs.coherence_reason }}
                  </div>
                </v-list-item>
              </v-list>
            </div>

            <!-- 2. Обычные кандидаты по контрагенту/договору -->
            <div v-if="items.length" class="mb-3">
              <div class="text-subtitle-2 font-weight-bold mb-2">
                Кандидаты по контрагенту / договору (можно отметить одну или несколько):
              </div>
              <v-list density="compact">
                <v-list-item
                  v-for="c in items"
                  :key="c.purchase_id"
                  class="mb-2 rounded border"
                  :active="selectedPurchaseIds.includes(c.purchase_id)"
                  @click="togglePurchase(c.purchase_id)"
                >
                  <template #prepend>
                    <v-checkbox-btn
                      :model-value="selectedPurchaseIds.includes(c.purchase_id)"
                      color="primary"
                      density="compact"
                      @click.stop="togglePurchase(c.purchase_id)"
                    />
                  </template>
                  <v-list-item-title class="font-weight-medium">
                    {{ c.registry_number || `Закупка #${c.purchase_id}` }} — {{ c.subject || '—' }}
                  </v-list-item-title>
                  <v-list-item-subtitle class="text-caption">
                    {{ c.contractor_name || 'Контрагент не указан' }}
                    · сумма {{ formatCurrency(c.contract_price || 0) }}
                    <template v-if="c.paid_by_statement != null"> · уже оплачено по выписке {{ formatCurrency(c.paid_by_statement) }}</template>
                  </v-list-item-subtitle>
                  <div v-if="c.reason" class="text-caption text-medium-emphasis mt-1">{{ c.reason }}</div>
                </v-list-item>
              </v-list>
            </div>

            <!-- 3. Все неоплаченные закупки субсидии — ручной выбор одной или нескольких сразу -->
            <div v-if="allPurchases.length" class="mb-3">
              <div class="d-flex align-center justify-space-between flex-wrap gap-2 mb-2">
                <div class="text-subtitle-2 font-weight-bold">
                  Выбрать закупки вручную — одну или несколько сразу ({{ filteredAllPurchases.length }} из {{ allPurchases.length }}):
                </div>
                <v-checkbox-btn
                  v-if="selectedPurchaseIds.length > 0"
                  v-model="onlySelectedFilter"
                  density="compact"
                  label="Показать только выбранные"
                />
              </div>
              <v-text-field
                v-model="purchaseSearch"
                density="compact"
                variant="outlined"
                prepend-inner-icon="mdi-magnify"
                placeholder="Поиск по № закупки, сумме, предмету или категории ФЭО..."
                clearable
                hide-details
                class="mb-2"
              />
              <v-list density="compact" style="max-height: 320px; overflow-y: auto;" class="border rounded pa-1">
                <v-list-item
                  v-for="p in filteredAllPurchases"
                  :key="'all-' + p.purchase_id"
                  class="mb-1 rounded border"
                  :active="selectedPurchaseIds.includes(p.purchase_id)"
                  @click="togglePurchase(p.purchase_id)"
                >
                  <template #prepend>
                    <v-checkbox-btn
                      :model-value="selectedPurchaseIds.includes(p.purchase_id)"
                      color="primary"
                      density="compact"
                      @click.stop="togglePurchase(p.purchase_id)"
                    />
                  </template>
                  <v-list-item-title class="font-weight-medium text-body-2 d-flex align-center flex-wrap gap-1">
                    <v-chip size="x-small" variant="tonal" :color="p.is_temp_plan ? 'deep-purple' : 'primary'">
                      {{ p.registry_number || `Закупка #${p.purchase_id}` }}
                    </v-chip>
                    <v-chip v-if="p.is_temp_plan" size="x-small" color="deep-purple" variant="flat">
                      План закупок («Да») · временная
                    </v-chip>
                    <span v-if="p.sheet_ref" class="text-caption text-primary">({{ p.sheet_ref }})</span>
                    <span>— {{ p.subject || '—' }}</span>
                  </v-list-item-title>
                  <v-list-item-subtitle class="text-caption mt-1">
                    {{ p.contractor_name || 'Без контрагента (подставится из платёжки)' }}
                    · сумма <b>{{ formatCurrency(p.contract_price || 0) }}</b>
                  </v-list-item-subtitle>
                  <div v-if="p.feo_category_path" class="text-caption text-medium-emphasis mt-1" style="line-height: 1.25;">
                    <v-icon icon="mdi-folder-outline" size="12" class="mr-1" />{{ p.feo_category_path }} › {{ p.subject || '—' }}
                  </div>
                  <div v-else-if="p.reason" class="text-caption text-deep-purple mt-1">{{ p.reason }}</div>
                </v-list-item>
              </v-list>
            </div>

            <!-- 4. Подсказка об ошибке знака (÷2) -->
            <v-alert v-if="signHints.length" type="warning" variant="tonal" density="compact" class="mt-2">
              <div class="font-weight-bold mb-1">Возможная ошибка знака (сумма ÷ 2):</div>
              <div v-for="sh in signHints" :key="sh.purchase_id" class="text-caption">
                {{ sh.registry_number || `#${sh.purchase_id}` }} «{{ sh.subject }}» — {{ sh.reason }}
              </div>
            </v-alert>
          </template>
        </template>
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="dialog = false">Отмена</v-btn>
        <v-btn
          color="primary"
          variant="flat"
          :disabled="selectedPurchaseIds.length === 0"
          :loading="attaching"
          @click="onAttach"
        >
          {{
            selectedPurchaseIds.length > 1 && mergePurchases
              ? `Объединить (${selectedPurchaseIds.length} поз.) в закупку и привязать`
              : selectedPurchaseIds.length > 1
                ? `Привязать выбранные закупки (${selectedPurchaseIds.length} шт.)`
                : 'Привязать выбранную закупку'
          }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  useSubsidyPaymentControl,
  type PaymentControlCandidate,
  type PaymentControlCandidatesBankPaymentInfo,
  type PaymentControlComboSuggestion,
  type PaymentControlSignErrorHint,
} from '@/composables/subsidies/useSubsidyPaymentControl'
import { formatCurrency } from '@/composables/subsidies/format'
import { useToast } from '@/composables/useToast'
import { describeApiError } from '@/utils/apiErrorMessage'

const props = defineProps<{
  subsidyId: number
  bankPaymentId: number | null
  control: ReturnType<typeof useSubsidyPaymentControl>
}>()
const emit = defineEmits<{ (e: 'attached'): void }>()

const dialog = defineModel<boolean>({ default: false })
const toast = useToast()

const bankPayment = ref<PaymentControlCandidatesBankPaymentInfo | null>(null)
const items = ref<PaymentControlCandidate[]>([])
const combos = ref<PaymentControlComboSuggestion[]>([])
const signHints = ref<PaymentControlSignErrorHint[]>([])
const allPurchases = ref<PaymentControlCandidate[]>([])
const purchaseSearch = ref('')
const onlySelectedFilter = ref(false)
const loading = ref(false)
const selectedPurchaseIds = ref<number[]>([])
const mergePurchases = ref(true)
const approveAmountDiff = ref(false)
const attaching = ref(false)
const detaching = ref(false)

interface SelectedPurchaseMeta {
  purchase_id: number
  registry_number: string | null
  subject: string | null
  amount: number
  is_larger_parent?: boolean
}

const purchaseMetaById = computed<Map<number, SelectedPurchaseMeta>>(() => {
  const m = new Map<number, SelectedPurchaseMeta>()
  for (const cs of combos.value) {
    for (const it of cs.items) {
      m.set(it.purchase_id, {
        purchase_id: it.purchase_id,
        registry_number: it.registry_number,
        subject: it.subject,
        amount: Number(it.amount || 0),
      })
    }
  }
  for (const it of items.value) {
    if (!m.has(it.purchase_id)) {
      m.set(it.purchase_id, {
        purchase_id: it.purchase_id,
        registry_number: it.registry_number,
        subject: it.subject,
        amount: Number(it.contract_price || 0),
      })
    }
  }
  for (const p of allPurchases.value) {
    m.set(p.purchase_id, {
      purchase_id: p.purchase_id,
      registry_number: p.registry_number,
      subject: p.subject,
      amount: Number(p.contract_price || 0),
      is_larger_parent: p.is_larger_parent,
    })
  }
  return m
})

const selectedPurchaseObjects = computed<SelectedPurchaseMeta[]>(() =>
  selectedPurchaseIds.value.map(
    id =>
      purchaseMetaById.value.get(id) || {
        purchase_id: id,
        registry_number: `#${id}`,
        subject: null,
        amount: 0,
      },
  ),
)

const selectedTotalAmount = computed(() =>
  selectedPurchaseObjects.value.reduce((sum, p) => sum + (Number(p.amount) || 0), 0),
)

const selectedDelta = computed(() => {
  const bpAmt = Number(bankPayment.value?.amount || 0)
  return Math.round((bpAmt - selectedTotalAmount.value) * 100) / 100
})

const needsAmountApproval = computed(() => {
  if (selectedPurchaseIds.value.length === 0) return false
  if (Math.abs(selectedDelta.value) <= 0.02) return false
  // Если выбрана 1 более крупная сводная закупка (например, ГСМ или Проезд) под частичный транш — согласование изменения суммы договора не требуется
  if (
    selectedPurchaseIds.value.length === 1 &&
    selectedTotalAmount.value > Number(bankPayment.value?.amount || 0)
  ) {
    return false
  }
  return true
})

const filteredAllPurchases = computed(() => {
  let list = allPurchases.value
  if (onlySelectedFilter.value) {
    list = list.filter(p => selectedPurchaseIds.value.includes(p.purchase_id))
  }
  const q = (purchaseSearch.value || '').trim().toLowerCase()
  if (!q) return list
  return list.filter((p) => {
    const text = `${p.registry_number || ''} ${p.sheet_ref || ''} ${p.subject || ''} ${p.feo_category_path || ''} ${p.contractor_name || ''} ${p.contract_price || ''}`.toLowerCase()
    return text.includes(q)
  })
})

function truncate(s: string, maxLen: number): string {
  return s.length > maxLen ? s.slice(0, maxLen) + '…' : s
}

function probColor(p: 'high' | 'medium' | 'needs_approval' | 'low'): string {
  if (p === 'high') return 'success'
  if (p === 'medium') return 'info'
  return 'warning'
}

function isComboSelected(cs: PaymentControlComboSuggestion): boolean {
  if (selectedPurchaseIds.value.length !== cs.purchase_ids.length) return false
  const set = new Set(selectedPurchaseIds.value)
  return cs.purchase_ids.every(id => set.has(id))
}

function selectCombo(cs: PaymentControlComboSuggestion) {
  if (isComboSelected(cs)) {
    selectedPurchaseIds.value = []
  } else {
    selectedPurchaseIds.value = [...cs.purchase_ids]
  }
  approveAmountDiff.value = false
}

function togglePurchase(pid: number) {
  const idx = selectedPurchaseIds.value.indexOf(pid)
  if (idx >= 0) {
    selectedPurchaseIds.value.splice(idx, 1)
  } else {
    selectedPurchaseIds.value.push(pid)
  }
}

function clearSelection() {
  selectedPurchaseIds.value = []
  onlySelectedFilter.value = false
  approveAmountDiff.value = false
}

async function load() {
  if (!props.bankPaymentId) return
  loading.value = true
  bankPayment.value = null
  items.value = []
  combos.value = []
  signHints.value = []
  allPurchases.value = []
  purchaseSearch.value = ''
  onlySelectedFilter.value = false
  selectedPurchaseIds.value = []
  approveAmountDiff.value = false
  try {
    const res = await props.control.fetchCandidatesFull(props.subsidyId, props.bankPaymentId)
    bankPayment.value = res.bank_payment || null
    items.value = res.items || []
    combos.value = res.combo_suggestions || []
    signHints.value = res.sign_error_hints || []
    allPurchases.value = res.all_unpaid_purchases || []
    if (combos.value.length > 0 && !combos.value[0].needs_amount_approval) {
      selectedPurchaseIds.value = [...combos.value[0].purchase_ids]
    } else if (items.value.length > 0) {
      selectedPurchaseIds.value = [items.value[0].purchase_id]
    } else if (allPurchases.value.length > 0 && (allPurchases.value[0].match_score || 0) >= 30) {
      selectedPurchaseIds.value = [allPurchases.value[0].purchase_id]
    }
  } catch (e: any) {
    toast.addToast(describeApiError(e, { fallback: 'Не удалось загрузить кандидатов' }), 'error')
  } finally {
    loading.value = false
  }
}

async function onDetach() {
  if (!props.bankPaymentId) return
  detaching.value = true
  try {
    await props.control.detachPurchase(props.subsidyId, props.bankPaymentId)
    toast.success('Платёж отвязан от закупки')
    emit('attached')
    await load()
  } catch (e: any) {
    toast.addToast(describeApiError(e, { fallback: 'Не удалось отвязать платёж' }), 'error')
  } finally {
    detaching.value = false
  }
}

async function onAttach() {
  if (!props.bankPaymentId || selectedPurchaseIds.value.length === 0) return
  if (needsAmountApproval.value && !approveAmountDiff.value) {
    toast.addToast('Поставьте галочку согласования расхождения суммы перед привязкой', 'warning')
    return
  }
  attaching.value = true
  try {
    const res = await props.control.attachCombo(
      props.subsidyId,
      props.bankPaymentId,
      selectedPurchaseIds.value,
      mergePurchases.value && selectedPurchaseIds.value.length > 1,
      approveAmountDiff.value,
    )
    for (const w of (res.warnings || [])) toast.addToast(w, 'warning')
    if (res.merged) {
      toast.success(`Позиции (${res.merged_count} шт.) объединены в закупку ${res.registry_number || '#' + res.primary_purchase_id} и привязаны к платёжке`)
    } else {
      toast.success('Выбранные закупки привязаны к платёжке')
    }
    dialog.value = false
    emit('attached')
  } catch (e: any) {
    toast.addToast(describeApiError(e, { fallback: 'Не удалось привязать закупку' }), 'error')
  } finally {
    attaching.value = false
  }
}

watch(dialog, (v) => { if (v) load() })
</script>
