<template>
  <v-dialog v-model="dialog" max-width="1360" scrollable :fullscreen="mobile">
    <v-card>
      <v-card-title class="d-flex align-center flex-wrap gap-2 pa-4 pb-2">
        <v-icon start color="warning">mdi-scale-unbalanced</v-icon>
        <span>Расхождение «Оплачено по отметке ↔ Подтверждено выпиской»</span>
        <v-spacer />
        <v-btn
          size="small"
          color="deep-purple"
          variant="flat"
          prepend-icon="mdi-auto-fix"
          @click="batchComboRef?.open()"
        >
          Умный автоподбор комбинаций
        </v-btn>
        <v-btn
          icon="mdi-refresh"
          variant="text"
          size="small"
          :loading="loading"
          title="Обновить"
          @click="loadWorkspace"
        />
        <v-btn icon="mdi-close" variant="text" @click="dialog = false" />
      </v-card-title>

      <v-divider />

      <v-card-text class="pa-4">
        <div v-if="loading && !workspace" class="d-flex flex-column align-center justify-center py-10">
          <v-progress-circular indeterminate color="primary" size="42" class="mb-3" />
          <div class="text-body-2 text-medium-emphasis">
            Загружаем позиции расхождения и непривязанные платежи из выписки...
          </div>
        </div>

        <v-alert v-else-if="error" type="error" variant="tonal" density="compact" class="mb-3">
          {{ error }}
        </v-alert>

        <template v-else-if="workspace">
          <!-- Сводная плашка -->
          <v-sheet rounded="lg" border class="pa-3 mb-3 bg-orange-lighten-5">
            <div class="d-flex flex-wrap align-center gap-x-6 gap-y-2 text-body-2">
              <div>
                <span class="text-medium-emphasis">По отметке в закупках:</span>
                <b class="ml-1">{{ formatCurrency(workspace.totals.declared_total) }}</b>
              </div>
              <div>
                <span class="text-medium-emphasis">Подтверждено выпиской:</span>
                <b class="ml-1 text-success">{{ formatCurrency(workspace.totals.confirmed_total) }}</b>
              </div>
              <div>
                <span class="text-medium-emphasis">Расхождение:</span>
                <b class="ml-1 text-warning-darken-3">
                  {{ workspace.totals.discrepancy_total >= 0 ? '+' : '' }}{{ formatCurrency(workspace.totals.discrepancy_total) }}
                </b>
                <span class="text-caption text-medium-emphasis ml-1">
                  ({{ workspace.totals.discrepancy_positions_count }} поз.)
                </span>
              </div>
              <div>
                <span class="text-medium-emphasis">Свободных платежей в выгрузке:</span>
                <b class="ml-1 text-primary">
                  {{ workspace.totals.unattached_payments_count }} шт. на {{ formatCurrency(workspace.totals.unattached_payments_total) }}
                </b>
              </div>
            </div>
          </v-sheet>

          <!-- Двухколоночная рабочая область -->
          <v-row dense>
            <!-- ЛЕВАЯ КОЛОНКА: Позиции в закупках (выбор одной или нескольких позиций) -->
            <v-col cols="12" md="6">
              <v-card variant="outlined" class="h-100 d-flex flex-column">
                <div class="pa-3 bg-grey-lighten-4 border-b">
                  <div class="d-flex align-center justify-space-between flex-wrap gap-2 mb-2">
                    <div class="text-subtitle-2 font-weight-bold">
                      1. Позиции в субсидии ({{ filteredPositions.length }})
                    </div>
                    <v-switch
                      v-model="onlyDiscrepancyPositions"
                      density="compact"
                      hide-details
                      color="orange-darken-2"
                      label="Только отмеченные «Оплачено» (выкл. = + позиции из «План закупок»)"
                      class="text-caption"
                    />
                  </div>
                  <div class="d-flex align-center gap-2">
                    <v-text-field
                      v-model="positionSearch"
                      density="compact"
                      variant="outlined"
                      prepend-inner-icon="mdi-magnify"
                      placeholder="Поиск по № (1662, РЕЕ-...), предмету, пути в субсидии, сумме..."
                      clearable
                      hide-details
                      bg-color="white"
                    />
                    <v-btn
                      v-if="selectedPurchaseIds.length"
                      size="x-small"
                      variant="text"
                      color="grey-darken-2"
                      @click="selectedPurchaseIds = []"
                    >
                      Сбросить ({{ selectedPurchaseIds.length }})
                    </v-btn>
                  </div>
                </div>

                <div class="pa-2 overflow-y-auto" style="max-height: 500px;">
                  <div v-if="!filteredPositions.length" class="text-caption text-medium-emphasis text-center py-6">
                    Позиций по фильтру не найдено
                  </div>
                  <v-card
                    v-for="pos in filteredPositions"
                    :key="pos.purchase_id"
                    variant="outlined"
                    class="mb-2 pa-2 cursor-pointer transition-swing"
                    :style="posCardStyle(pos)"
                    @click="togglePurchase(pos.purchase_id)"
                  >
                    <div class="d-flex align-start gap-2">
                      <v-checkbox-btn
                        :model-value="selectedPurchaseIds.includes(pos.purchase_id)"
                        color="primary"
                        density="compact"
                        @click.stop="togglePurchase(pos.purchase_id)"
                      />
                      <div class="flex-grow-1" style="min-width: 0;">
                        <div class="d-flex align-center justify-space-between flex-wrap gap-1">
                          <div class="d-flex align-center flex-wrap gap-1">
                            <v-chip size="x-small" :color="pos.is_temp_plan ? 'deep-purple' : 'primary'" variant="tonal" class="font-weight-bold">
                              {{ pos.is_temp_plan ? (pos.registry_number || 'ВРЕМ-ПЛАН') : `№ ${pos.purchase_number || pos.purchase_id}` }}
                            </v-chip>
                            <v-chip v-if="pos.registry_number && !pos.is_temp_plan" size="x-small" variant="outlined">
                              {{ pos.registry_number }}
                            </v-chip>
                            <v-chip
                              v-if="pos.is_temp_plan"
                              size="x-small"
                              color="deep-purple"
                              variant="flat"
                            >
                              План закупок («Да») · временная закупка
                            </v-chip>
                            <v-chip
                              v-if="pos.is_in_discrepancy"
                              size="x-small"
                              color="warning"
                              variant="flat"
                            >
                              По отметке оплачено
                            </v-chip>
                            <v-chip
                              v-if="pos.item_type"
                              size="x-small"
                              variant="tonal"
                              :color="pos.item_type === 'товар' ? 'blue' : 'purple'"
                            >
                              {{ pos.item_type }}
                            </v-chip>
                          </div>
                          <div class="text-subtitle-2 font-weight-bold text-no-wrap">
                            {{ formatCurrency(pos.remaining_amount) }}
                          </div>
                        </div>

                        <!-- Полный путь категории ФЭО в субсидии до позиции -->
                        <div
                          v-if="pos.feo_category_path"
                          class="text-caption text-medium-emphasis mt-1"
                          style="line-height: 1.25;"
                        >
                          <v-icon icon="mdi-folder-outline" size="13" class="mr-1" />
                          <span>{{ pos.feo_category_path }}</span>
                        </div>

                        <!-- Предмет / наименование позиции -->
                        <div class="text-body-2 font-weight-medium mt-1" style="line-height: 1.3;">
                          {{ pos.subject || '—' }}
                        </div>

                        <!-- Контрагент -->
                        <div class="text-caption mt-1" :class="pos.contractor_name ? 'text-medium-emphasis' : 'text-warning-darken-2'">
                          <v-icon icon="mdi-domain" size="12" class="mr-1" />
                          {{ pos.contractor_name || 'Контрагент не указан (подставится из выписки)' }}
                        </div>
                      </div>
                    </div>
                  </v-card>
                </div>
              </v-card>
            </v-col>

            <!-- ПРАВАЯ КОЛОНКА: Непривязанные платежи из выписки (выгрузки) -->
            <v-col cols="12" md="6">
              <v-card variant="outlined" class="h-100 d-flex flex-column">
                <div class="pa-3 bg-grey-lighten-4 border-b">
                  <div class="d-flex align-center justify-space-between flex-wrap gap-2 mb-2">
                    <div class="text-subtitle-2 font-weight-bold">
                      2. Непривязанные платежи из выгрузки ({{ sortedBankPayments.length }})
                    </div>
                    <span v-if="selectedPositionsSum > 0" class="text-caption text-primary font-weight-bold">
                      Ищем под сумму: {{ formatCurrency(selectedPositionsSum) }}
                    </span>
                  </div>
                  <div class="d-flex align-center gap-2">
                    <v-text-field
                      v-model="paymentSearch"
                      density="compact"
                      variant="outlined"
                      prepend-inner-icon="mdi-magnify"
                      placeholder="Поиск по № ПП, контрагенту, назначению, направлению, сумме..."
                      clearable
                      hide-details
                      bg-color="white"
                    />
                    <v-btn
                      v-if="selectedBankPaymentIds.length"
                      size="x-small"
                      variant="text"
                      color="grey-darken-2"
                      @click="selectedBankPaymentIds = []"
                    >
                      Сбросить ({{ selectedBankPaymentIds.length }})
                    </v-btn>
                  </div>
                </div>

                <div class="pa-2 overflow-y-auto" style="max-height: 500px;">
                  <div v-if="!sortedBankPayments.length" class="text-caption text-medium-emphasis text-center py-6">
                    Непривязанных платежей по фильтру не найдено
                  </div>
                  <v-card
                    v-for="bp in sortedBankPayments"
                    :key="bp.id"
                    variant="outlined"
                    class="mb-2 pa-2 cursor-pointer transition-swing"
                    :style="bpCardStyle(bp)"
                    @click="toggleBankPayment(bp.id)"
                  >
                    <div class="d-flex align-start gap-2">
                      <v-checkbox-btn
                        :model-value="selectedBankPaymentIds.includes(bp.id)"
                        color="deep-purple"
                        density="compact"
                        @click.stop="toggleBankPayment(bp.id)"
                      />
                      <div class="flex-grow-1" style="min-width: 0;">
                        <div class="d-flex align-center justify-space-between flex-wrap gap-1">
                          <div class="d-flex align-center flex-wrap gap-1">
                            <v-chip size="x-small" color="deep-purple" variant="tonal" class="font-weight-bold">
                              ПП №{{ bp.payment_number || bp.id }}
                            </v-chip>
                            <span v-if="bp.payment_date" class="text-caption text-medium-emphasis">
                              от {{ fmtDate(bp.payment_date) }}
                            </span>
                            <v-chip
                              v-if="isExactMatchBp(bp)"
                              size="x-small"
                              color="success"
                              variant="flat"
                            >
                              Точное совпадение суммы!
                            </v-chip>
                            <v-chip
                              v-else-if="isCloseMatchBp(bp)"
                              size="x-small"
                              color="warning"
                              variant="flat"
                            >
                              Близкая сумма ({{ fmtDelta(selectedPositionsSum - bp.amount) }})
                            </v-chip>
                          </div>
                          <div class="text-subtitle-2 font-weight-bold text-no-wrap">
                            {{ formatCurrency(bp.amount) }}
                          </div>
                        </div>

                        <!-- Получатель платежа -->
                        <div class="text-body-2 font-weight-medium mt-1">
                          {{ bp.payee_name || '—' }}
                          <span v-if="bp.payee_inn" class="text-caption text-medium-emphasis">(ИНН {{ bp.payee_inn }})</span>
                        </div>

                        <!-- Направление расходов из выписки -->
                        <div v-if="bp.expense_direction" class="text-caption text-primary mt-1" style="line-height: 1.25;">
                          <b>Направление расходов (выписка):</b> {{ bp.expense_direction }}
                        </div>

                        <!-- Назначение платежа из выписки -->
                        <div v-if="bp.purpose_text" class="text-caption text-medium-emphasis mt-1" style="line-height: 1.25;">
                          <b>Назначение:</b> {{ bp.purpose_text }}
                        </div>
                      </div>
                    </div>
                  </v-card>
                </div>
              </v-card>
            </v-col>
          </v-row>

          <!-- Панель сопоставления выбранных позиций и платежей -->
          <v-sheet
            rounded="lg"
            border
            class="pa-3 mt-3"
            :color="canReconcile ? 'deep-purple-lighten-5' : 'grey-lighten-4'"
          >
            <div class="d-flex align-center justify-space-between flex-wrap gap-3">
              <div class="d-flex flex-wrap align-center gap-4 text-body-2">
                <div>
                  Выбрано позиций: <b>{{ selectedPurchaseIds.length }}</b>
                  на сумму <b>{{ formatCurrency(selectedPositionsSum) }}</b>
                </div>
                <v-icon icon="mdi-swap-horizontal" size="18" />
                <div>
                  Выбрано платежей выписки: <b>{{ selectedBankPaymentIds.length }}</b>
                  на сумму <b>{{ formatCurrency(selectedPaymentsSum) }}</b>
                </div>
                <div v-if="selectedPurchaseIds.length && selectedBankPaymentIds.length">
                  Разница:
                  <v-chip
                    size="small"
                    :color="Math.abs(selectionDelta) < 0.005 ? 'success' : 'warning'"
                    variant="flat"
                    class="font-weight-bold ml-1"
                  >
                    {{ Math.abs(selectionDelta) < 0.005 ? '0,00 ₽ (Точно до копейки)' : fmtDelta(selectionDelta) }}
                  </v-chip>
                </div>
              </div>

              <div class="d-flex align-center flex-wrap gap-3">
                <v-checkbox
                  v-if="selectedPurchaseIds.length > 1"
                  v-model="mergeSelectedPurchases"
                  density="compact"
                  hide-details
                  color="deep-purple"
                  label="Объединить выбранные позиции в одну закупку"
                />
                <v-checkbox
                  v-if="needsDiffApproval"
                  v-model="approveAmountDiff"
                  density="compact"
                  hide-details
                  color="warning"
                  label="Согласовать расхождение и скорректировать сумму закупки под выписку"
                />
                <v-btn
                  color="deep-purple"
                  variant="flat"
                  :disabled="!canReconcile"
                  :loading="submitting"
                  prepend-icon="mdi-link-variant"
                  @click="submitReconcile"
                >
                  Сопоставить выбранные ({{ selectedPurchaseIds.length }} поз. ↔ {{ selectedBankPaymentIds.length }} ПП)
                </v-btn>
              </div>
            </div>
          </v-sheet>
        </template>
      </v-card-text>
    </v-card>

    <!-- Диалог умного автоподбора комбинаций -->
    <SubsidyPaymentControlBatchComboDialog
      ref="batchComboRef"
      :subsidy-id="props.subsidyId"
      @applied="onBatchComboApplied"
    />
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { apiFetch } from '@/api'
import { formatCurrency } from '@/composables/subsidies/format'
import { useToast } from '@/composables/useToast'
import SubsidyPaymentControlBatchComboDialog from './SubsidyPaymentControlBatchComboDialog.vue'

interface DiscrepancyPosition {
  purchase_id: number
  purchase_number: number | null
  registry_number: string | null
  subject: string | null
  feo_category_path: string | null
  contractor_id: number | null
  contractor_name: string | null
  contractor_inn: string | null
  item_type: string | null
  status: string | null
  remaining_amount: number
  declared_paid_amount: number
  confirmed_paid_amount: number
  discrepancy_amount: number
  is_in_discrepancy: boolean
  is_temp_plan?: boolean
  sheet_ref: string | null
}

interface UnattachedBankPayment {
  id: number
  payment_number: string | null
  payment_date: string | null
  amount: number
  payee_name: string | null
  payee_inn: string | null
  expense_direction: string | null
  purpose_text: string | null
  contract_number: string | null
  contract_date: string | null
}

interface DiscrepancyWorkspaceResponse {
  totals: {
    declared_total: number
    confirmed_total: number
    discrepancy_total: number
    discrepancy_positions_count: number
    unattached_payments_count: number
    unattached_payments_total: number
  }
  positions: DiscrepancyPosition[]
  unattached_payments: UnattachedBankPayment[]
}

const props = defineProps<{
  visible: boolean
  subsidyId: number | null | undefined
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'reconciled'): void
}>()

const { mobile } = useDisplay()
const { success: showSuccess, error: showError } = useToast()

const dialog = computed({
  get: () => props.visible,
  set: (v: boolean) => { if (!v) emit('close') },
})

const loading = ref(false)
const submitting = ref(false)
const error = ref('')
const workspace = ref<DiscrepancyWorkspaceResponse | null>(null)

const onlyDiscrepancyPositions = ref(true)
const positionSearch = ref('')
const paymentSearch = ref('')

const selectedPurchaseIds = ref<number[]>([])
const selectedBankPaymentIds = ref<number[]>([])
const mergeSelectedPurchases = ref(true)
const approveAmountDiff = ref(false)

const batchComboRef = ref<InstanceType<typeof SubsidyPaymentControlBatchComboDialog> | null>(null)

watch(
  () => [props.visible, props.subsidyId],
  async ([vis, sid]) => {
    if (vis && sid) {
      selectedPurchaseIds.value = []
      selectedBankPaymentIds.value = []
      approveAmountDiff.value = false
      await loadWorkspace()
    }
  },
  { immediate: true },
)

async function loadWorkspace() {
  if (!props.subsidyId) return
  loading.value = true
  error.value = ''
  try {
    workspace.value = await apiFetch<DiscrepancyWorkspaceResponse>(
      `/subsidies/${props.subsidyId}/payment-control/discrepancy-workspace`,
    )
  } catch (e: any) {
    error.value = e?.payload?.detail || e?.detail || e?.message || 'Не удалось загрузить данные расхождения'
  } finally {
    loading.value = false
  }
}

const filteredPositions = computed(() => {
  if (!workspace.value) return []
  let list = workspace.value.positions
  if (onlyDiscrepancyPositions.value) {
    list = list.filter((p) => p.is_in_discrepancy)
  }
  const q = (positionSearch.value || '').trim().toLowerCase()
  if (!q) return list
  return list.filter((p) => {
    const pnum = String(p.purchase_number || p.purchase_id)
    const rnum = (p.registry_number || '').toLowerCase()
    const subj = (p.subject || '').toLowerCase()
    const fpath = (p.feo_category_path || '').toLowerCase()
    const cname = (p.contractor_name || '').toLowerCase()
    const amt = String(p.remaining_amount)
    return (
      pnum.includes(q)
      || rnum.includes(q)
      || subj.includes(q)
      || fpath.includes(q)
      || cname.includes(q)
      || amt.includes(q)
    )
  })
})

const selectedPositionsSum = computed(() => {
  if (!workspace.value || !selectedPurchaseIds.value.length) return 0
  const map = new Map(workspace.value.positions.map((p) => [p.purchase_id, p.remaining_amount]))
  return selectedPurchaseIds.value.reduce((acc, pid) => acc + (map.get(pid) || 0), 0)
})

const selectedPaymentsSum = computed(() => {
  if (!workspace.value || !selectedBankPaymentIds.value.length) return 0
  const map = new Map(workspace.value.unattached_payments.map((b) => [b.id, b.amount]))
  return selectedBankPaymentIds.value.reduce((acc, bid) => acc + (map.get(bid) || 0), 0)
})

const selectionDelta = computed(() => {
  return Number((selectedPositionsSum.value - selectedPaymentsSum.value).toFixed(2))
})

const sortedBankPayments = computed(() => {
  if (!workspace.value) return []
  let list = [...workspace.value.unattached_payments]
  const q = (paymentSearch.value || '').trim().toLowerCase()
  if (q) {
    list = list.filter((b) => {
      const num = (b.payment_number || '').toLowerCase()
      const name = (b.payee_name || '').toLowerCase()
      const inn = (b.payee_inn || '').toLowerCase()
      const purp = (b.purpose_text || '').toLowerCase()
      const dir = (b.expense_direction || '').toLowerCase()
      const amt = String(b.amount)
      return (
        num.includes(q)
        || name.includes(q)
        || inn.includes(q)
        || purp.includes(q)
        || dir.includes(q)
        || amt.includes(q)
      )
    })
  }
  const target = selectedPositionsSum.value
  if (target > 0) {
    list.sort((a, b) => {
      const aSelected = selectedBankPaymentIds.value.includes(a.id) ? 0 : 1
      const bSelected = selectedBankPaymentIds.value.includes(b.id) ? 0 : 1
      if (aSelected !== bSelected) return aSelected - bSelected
      const aDiff = Math.abs(a.amount - target)
      const bDiff = Math.abs(b.amount - target)
      return aDiff - bDiff
    })
  }
  return list
})

const needsDiffApproval = computed(() => {
  if (!selectedPurchaseIds.value.length || selectedBankPaymentIds.value.length !== 1) return false
  const absDelta = Math.abs(selectionDelta.value)
  return absDelta > 0.005
})

const canReconcile = computed(() => {
  if (!selectedPurchaseIds.value.length || !selectedBankPaymentIds.value.length) return false
  // Если выбрано несколько платежей (траншей) к одной сводной закупке, сумма траншей может быть <= суммы закупки
  if (selectedBankPaymentIds.value.length > 1) {
    return selectedPaymentsSum.value <= selectedPositionsSum.value + 0.01
  }
  // Если выбран 1 платёж и есть расхождение суммы — нужно либо точное совпадение, либо галочка согласования, либо частичный транш в сводную закупку
  if (Math.abs(selectionDelta.value) < 0.005) return true
  if (selectedPurchaseIds.value.length === 1 && selectedPaymentsSum.value < selectedPositionsSum.value) {
    // Частичная оплата (транш) крупной закупки ИЛИ согласование расхождения
    return true
  }
  return approveAmountDiff.value
})

function togglePurchase(pid: number) {
  const idx = selectedPurchaseIds.value.indexOf(pid)
  if (idx >= 0) {
    selectedPurchaseIds.value.splice(idx, 1)
  } else {
    selectedPurchaseIds.value.push(pid)
  }
  approveAmountDiff.value = false
}

function toggleBankPayment(bpId: number) {
  const idx = selectedBankPaymentIds.value.indexOf(bpId)
  if (idx >= 0) {
    selectedBankPaymentIds.value.splice(idx, 1)
  } else {
    selectedBankPaymentIds.value.push(bpId)
  }
  approveAmountDiff.value = false
}

function isExactMatchBp(bp: UnattachedBankPayment): boolean {
  if (selectedPositionsSum.value <= 0) return false
  return Math.abs(bp.amount - selectedPositionsSum.value) < 0.005
}

function isCloseMatchBp(bp: UnattachedBankPayment): boolean {
  if (selectedPositionsSum.value <= 0) return false
  const diff = Math.abs(bp.amount - selectedPositionsSum.value)
  return diff >= 0.005 && diff <= 5.0
}

function posCardStyle(pos: DiscrepancyPosition): Record<string, string> {
  if (selectedPurchaseIds.value.includes(pos.purchase_id)) {
    return { borderColor: '#2563EB', backgroundColor: '#EFF6FF' }
  }
  return {}
}

function bpCardStyle(bp: UnattachedBankPayment): Record<string, string> {
  if (selectedBankPaymentIds.value.includes(bp.id)) {
    return { borderColor: '#7C3AED', backgroundColor: '#F5F3FF' }
  }
  if (isExactMatchBp(bp)) {
    return { borderColor: '#16A34A', backgroundColor: '#F0FDF4' }
  }
  if (isCloseMatchBp(bp)) {
    return { borderColor: '#D97706', backgroundColor: '#FFFBEB' }
  }
  return {}
}

function fmtDate(d: string | null): string {
  if (!d) return ''
  return new Date(d).toLocaleDateString('ru-RU')
}

function fmtDelta(delta: number): string {
  const sign = delta > 0 ? '+' : ''
  return `${sign}${delta.toFixed(2).replace('.', ',')} ₽`
}

async function submitReconcile() {
  if (!props.subsidyId || !canReconcile.value) return
  submitting.value = true
  try {
    await apiFetch(`/subsidies/${props.subsidyId}/payment-control/reconcile-selection`, {
      method: 'POST',
      body: JSON.stringify({
        purchase_ids: selectedPurchaseIds.value,
        bank_payment_ids: selectedBankPaymentIds.value,
        merge_purchases: mergeSelectedPurchases.value,
        approve_amount_diff: approveAmountDiff.value,
      }),
    })
    showSuccess('Выбранные позиции успешно сопоставлены с выпиской')
    selectedPurchaseIds.value = []
    selectedBankPaymentIds.value = []
    approveAmountDiff.value = false
    await loadWorkspace()
    emit('reconciled')
  } catch (e: any) {
    showError(e?.payload?.detail || e?.detail || e?.message || 'Ошибка при сопоставлении позиций')
  } finally {
    submitting.value = false
  }
}

async function onBatchComboApplied() {
  selectedPurchaseIds.value = []
  selectedBankPaymentIds.value = []
  await loadWorkspace()
  emit('reconciled')
}
</script>

