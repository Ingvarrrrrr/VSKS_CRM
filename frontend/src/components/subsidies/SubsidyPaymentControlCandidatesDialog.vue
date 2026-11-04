<template>
  <v-dialog v-model="dialog" max-width="760" scrollable>
    <v-card>
      <v-card-title class="d-flex align-center pa-4 pb-2">
        <v-icon start color="primary">mdi-magnify</v-icon>
        Найти закупку или составную комбинацию по платёжке
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" @click="dialog = false" />
      </v-card-title>
      <v-card-text class="pa-4">
        <div v-if="loading" class="d-flex justify-center py-6">
          <v-progress-circular indeterminate color="primary" />
        </div>
        <div v-else-if="!items.length && !combos.length && !signHints.length && !allPurchases.length" class="text-caption text-medium-emphasis py-4">
          Подходящих закупок или комбинаций сумм не найдено
        </div>
        <template v-else>
          <!-- 1. Составные варианты (Subset Sum) с ранжированием по категориям -->
          <div v-if="combos.length" class="mb-4">
            <div class="text-subtitle-2 font-weight-bold mb-2">
              Варианты по сумме и близости категорий (в т.ч. закупки без исполнителя):
            </div>
            <v-list density="compact">
              <v-list-item
                v-for="(cs, idx) in combos"
                :key="'combo-' + idx"
                class="mb-2 rounded border"
                :active="selectedComboIdx === idx"
                @click="selectCombo(idx)"
              >
                <template #prepend>
                  <v-radio :model-value="selectedComboIdx === idx" density="compact" />
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
                    <v-chip size="x-small" variant="tonal" color="primary">
                      {{ it.registry_number || `#${it.purchase_id}` }}
                    </v-chip>
                    <span v-if="it.sheet_ref" class="text-caption text-medium-emphasis">({{ it.sheet_ref }})</span>
                    <span>{{ it.subject || '—' }}</span>
                    <span class="font-weight-bold">({{ formatCurrency(it.amount) }})</span>
                    <span v-if="it.semantic_cluster || it.feo_category_name" class="text-caption text-medium-emphasis">
                      · {{ it.semantic_cluster || it.feo_category_name }}
                    </span>
                    <span v-if="!it.contractor_name" class="text-caption text-warning">
                      · без контрагента
                    </span>
                  </div>
                </div>
                <div class="text-caption text-medium-emphasis">
                  {{ cs.coherence_reason }}
                </div>
              </v-list-item>
            </v-list>

            <v-alert
              v-if="selectedCombo && (selectedCombo.needs_amount_approval || Math.abs(selectedCombo.delta) > 0.0001)"
              type="warning"
              variant="tonal"
              density="compact"
              class="mt-2 text-caption"
            >
              <div class="font-weight-bold">
                Расхождение суммы ({{ selectedCombo.delta > 0 ? '+' : '' }}{{ selectedCombo.delta.toFixed(2).replace('.', ',') }} ₽) — требуется согласование человека
              </div>
              <v-checkbox
                v-model="approveAmountDiff"
                density="compact"
                hide-details
                color="warning"
                class="mt-1"
                label="Согласовать расхождение и скорректировать сумму закупки под выписку"
              />
            </v-alert>

            <v-checkbox
              v-if="selectedCombo && selectedCombo.count > 1"
              v-model="mergePurchases"
              density="compact"
              hide-details
              color="primary"
              class="mt-1"
              label="Объединить выбранные позиции в одну общую закупку и проставить контрагента из платёжки"
            />
          </div>

          <!-- 2. Обычные кандидаты по контрагенту/договору -->
          <div v-if="items.length" class="mb-3">
            <div class="text-subtitle-2 font-weight-bold mb-2">
              Кандидаты по контрагенту / договору:
            </div>
            <v-list density="compact">
              <v-list-item
                v-for="c in items"
                :key="c.purchase_id"
                class="mb-2 rounded border"
                :active="selectedId === c.purchase_id && selectedComboIdx === null"
                @click="selectSingle(c.purchase_id)"
              >
                <template #prepend>
                  <v-radio :model-value="selectedId === c.purchase_id && selectedComboIdx === null" density="compact" />
                </template>
                <v-list-item-title class="font-weight-medium">
                  {{ c.registry_number || `Закупка #${c.purchase_id}` }} — {{ c.subject || '—' }}
                </v-list-item-title>
                <v-list-item-subtitle class="text-caption">
                  {{ c.contractor_name || 'Контрагент не указан' }}
                  · договор {{ formatCurrency(c.contract_price || 0) }}
                  <template v-if="c.paid_by_statement != null"> · уже оплачено по выписке {{ formatCurrency(c.paid_by_statement) }}</template>
                </v-list-item-subtitle>
                <div v-if="c.reason" class="text-caption text-medium-emphasis mt-1">{{ c.reason }}</div>
              </v-list-item>
            </v-list>
          </div>

          <!-- 3. Крупные/сводные закупки субсидии (частичная оплата / транш: ГСМ, Проезд и др.) -->
          <div v-if="allPurchases.length" class="mb-3">
            <div class="text-subtitle-2 font-weight-bold mb-2">
              Все неоплаченные закупки субсидии (в т.ч. сводные закупки для частичной оплаты / транша):
            </div>
            <v-text-field
              v-model="purchaseSearch"
              density="compact"
              variant="outlined"
              prepend-inner-icon="mdi-magnify"
              placeholder="Поиск по № закупки (напр. 1694, 1695, РЕЕ-...) или предмету (ГСМ, Проезд)..."
              clearable
              hide-details
              class="mb-2"
            />
            <v-list density="compact" style="max-height: 280px; overflow-y: auto;" class="border rounded pa-1">
              <v-list-item
                v-for="p in filteredAllPurchases"
                :key="'all-' + p.purchase_id"
                class="mb-1 rounded border"
                :active="selectedId === p.purchase_id && selectedComboIdx === null"
                @click="selectSingle(p.purchase_id)"
              >
                <template #prepend>
                  <v-radio :model-value="selectedId === p.purchase_id && selectedComboIdx === null" density="compact" />
                </template>
                <v-list-item-title class="font-weight-medium text-body-2">
                  {{ p.registry_number || `Закупка #${p.purchase_id}` }}
                  <span v-if="p.sheet_ref" class="text-caption text-primary">({{ p.sheet_ref }})</span>
                  — {{ p.subject || '—' }}
                </v-list-item-title>
                <v-list-item-subtitle class="text-caption">
                  {{ p.contractor_name || 'Без контрагента (подставится из платёжки)' }}
                  · остаток к оплате <b>{{ formatCurrency(p.contract_price || 0) }}</b>
                </v-list-item-subtitle>
                <div v-if="p.reason" class="text-caption text-deep-purple mt-1">{{ p.reason }}</div>
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
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="dialog = false">Отмена</v-btn>
        <v-btn
          color="primary"
          variant="flat"
          :disabled="selectedComboIdx === null && !selectedId"
          :loading="attaching"
          @click="onAttach"
        >
          {{ selectedCombo && selectedCombo.count > 1 && mergePurchases ? 'Объединить в закупку и привязать' : 'Привязать' }}
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

const items = ref<PaymentControlCandidate[]>([])
const combos = ref<PaymentControlComboSuggestion[]>([])
const signHints = ref<PaymentControlSignErrorHint[]>([])
const allPurchases = ref<PaymentControlCandidate[]>([])
const purchaseSearch = ref('')
const loading = ref(false)
const selectedId = ref<number | null>(null)
const selectedComboIdx = ref<number | null>(null)
const mergePurchases = ref(true)
const approveAmountDiff = ref(false)
const attaching = ref(false)

const selectedCombo = computed(() =>
  selectedComboIdx.value != null ? combos.value[selectedComboIdx.value] ?? null : null,
)

const filteredAllPurchases = computed(() => {
  const q = (purchaseSearch.value || '').trim().toLowerCase()
  if (!q) return allPurchases.value.slice(0, 30)
  return allPurchases.value.filter((p) => {
    const text = `${p.registry_number || ''} ${p.sheet_ref || ''} ${p.subject || ''} ${p.contractor_name || ''} ${p.contract_price || ''}`.toLowerCase()
    return text.includes(q)
  })
})

function probColor(p: 'high' | 'medium' | 'needs_approval' | 'low'): string {
  if (p === 'high') return 'success'
  if (p === 'medium') return 'info'
  return 'warning'
}

function selectCombo(idx: number) {
  selectedComboIdx.value = idx
  selectedId.value = null
  approveAmountDiff.value = false
}

function selectSingle(pid: number) {
  selectedId.value = pid
  selectedComboIdx.value = null
}

async function load() {
  if (!props.bankPaymentId) return
  loading.value = true
  items.value = []
  combos.value = []
  signHints.value = []
  allPurchases.value = []
  purchaseSearch.value = ''
  selectedId.value = null
  selectedComboIdx.value = null
  approveAmountDiff.value = false
  try {
    const res = await props.control.fetchCandidatesFull(props.subsidyId, props.bankPaymentId)
    items.value = res.items || []
    combos.value = res.combo_suggestions || []
    signHints.value = res.sign_error_hints || []
    allPurchases.value = res.all_unpaid_purchases || []
    if (combos.value.length > 0 && !combos.value[0].needs_amount_approval) {
      selectedComboIdx.value = 0
    } else if (items.value.length > 0) {
      selectedId.value = items.value[0].purchase_id
    } else if (allPurchases.value.length > 0 && (allPurchases.value[0].match_score || 0) >= 30) {
      selectedId.value = allPurchases.value[0].purchase_id
    }
  } catch (e: any) {
    toast.addToast(describeApiError(e, { fallback: 'Не удалось загрузить кандидатов' }), 'error')
  } finally {
    loading.value = false
  }
}

async function onAttach() {
  if (!props.bankPaymentId) return
  attaching.value = true
  try {
    if (selectedCombo.value) {
      const needsApproval = Boolean(selectedCombo.value.needs_amount_approval || Math.abs(selectedCombo.value.delta) > 0.0001)
      if (needsApproval && !approveAmountDiff.value) {
        toast.addToast('Поставьте галочку согласования расхождения суммы перед привязкой', 'warning')
        attaching.value = false
        return
      }
      const res = await props.control.attachCombo(
        props.subsidyId,
        props.bankPaymentId,
        selectedCombo.value.purchase_ids,
        mergePurchases.value && selectedCombo.value.count > 1,
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
      return
    }
    if (!selectedId.value) return
    const res = await props.control.attachPurchase(props.subsidyId, props.bankPaymentId, selectedId.value)
    for (const w of (res.warnings || [])) toast.addToast(w, 'warning')
    toast.success('Закупка привязана к платёжке')
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
