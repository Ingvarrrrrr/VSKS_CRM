<template>
  <v-dialog v-model="visible" max-width="960" scrollable :fullscreen="mobile">
    <v-card>
      <v-card-title class="d-flex align-center pa-4 pb-2 bg-deep-purple-lighten-5">
        <v-icon start color="deep-purple">mdi-auto-fix</v-icon>
        <span>Умный комбинаторный подбор оплат</span>
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="visible = false" />
      </v-card-title>

      <v-divider />

      <v-card-text class="pa-4">
        <!-- Загрузка -->
        <div v-if="loading" class="d-flex flex-column align-center justify-center py-10">
          <v-progress-circular indeterminate color="deep-purple" size="48" class="mb-3" />
          <div class="text-body-2 text-medium-emphasis">
            Сканируем платежи и перебираем составные комбинации сумм...
          </div>
        </div>

        <!-- Ошибка -->
        <v-alert v-else-if="error" type="error" variant="tonal" density="compact" class="mb-4">
          {{ error }}
        </v-alert>

        <!-- Пустой результат -->
        <div v-else-if="!matches.length" class="text-center py-10">
          <v-icon size="48" color="grey-lighten-1" class="mb-2">mdi-check-all</v-icon>
          <div class="text-subtitle-1 font-weight-bold">Подходящих комбинаций не найдено</div>
          <div class="text-caption text-medium-emphasis mt-1">
            Все платежи уже привязаны, либо суммы непривязанных оплат не сходятся с доступными закупками.
          </div>
        </div>

        <!-- Список совпадений -->
        <template v-else>
          <div class="d-flex align-center justify-space-between flex-wrap gap-2 mb-3">
            <div class="text-body-2">
              Найдено совпадений: <b>{{ matches.length }}</b>
              <span class="text-medium-emphasis"> (из {{ unattachedCount }} непривязанных платежей)</span>
            </div>
            <div class="d-flex align-center gap-2">
              <v-btn size="x-small" variant="text" @click="selectAllExact()">Выбрать все точные</v-btn>
              <v-btn size="x-small" variant="text" @click="selectAll(false)">Снять выбор</v-btn>
            </div>
          </div>

          <v-alert type="info" variant="tonal" density="compact" class="mb-3">
            Алгоритм работает в 3 шага: 1) закупки с уже известным подрядчиком (строго тот же подрядчик и точная сумма);
            2) единичные совпадения 1-к-1 по сумме среди закупок без подрядчика;
            3) комбинаторика (от 2 до 100+ единичных закупок без подрядчика в одну общую закупку).
            Расхождения даже в 1 копейку автоматически НЕ приравниваются и требуют ручного согласования.
          </v-alert>

          <div class="d-flex flex-column gap-3">
            <v-card
              v-for="m in matches"
              :key="m.bank_payment_id"
              variant="outlined"
              :class="{
                'border-primary': m.selected,
                'opacity-60': !m.selected
              }"
              class="pa-3 rounded-lg"
            >
              <!-- Шапка карточки платежа -->
              <div class="d-flex align-center justify-space-between flex-wrap gap-2 mb-2">
                <div class="d-flex align-center gap-2">
                  <v-checkbox-btn
                    v-model="m.selected"
                    density="compact"
                    color="deep-purple"
                    @update:model-value="(val) => onToggleSelect(m, Boolean(val))"
                  />
                  <span class="font-weight-bold text-subtitle-2 text-deep-purple-darken-2">
                    {{ formatCurrency(m.amount) }}
                  </span>
                  <v-chip size="x-small" variant="tonal">
                    {{ m.payment_date ? fmtDate(m.payment_date) : '' }} №{{ m.payment_number || m.bank_payment_id }}
                  </v-chip>
                  <v-chip
                    size="x-small"
                    :color="probColor(m.combo.probability)"
                    variant="flat"
                  >
                    {{ m.combo.probability_label }}
                  </v-chip>
                </div>
                <div class="text-caption text-medium-emphasis">
                  {{ m.combo.count > 1 ? `Комбинация из ${m.combo.count} поз.` : (m.combo.needs_amount_approval ? `Расхождение суммы (${fmtDelta(m.combo.delta)})` : 'Точное совпадение 1 поз.') }}
                </div>
              </div>

              <!-- Предупреждение о расхождении суммы (копейки / рубли) -->
              <v-alert
                v-if="m.combo.needs_amount_approval || Math.abs(m.combo.delta) > 0.0001"
                type="warning"
                variant="tonal"
                density="compact"
                class="mb-2 text-caption"
              >
                <div class="font-weight-bold">
                  Требуется согласование человека: расхождение суммы на {{ fmtDelta(m.combo.delta) }}
                </div>
                <div>
                  В закупке указано <b>{{ formatCurrency(m.combo.total_amount) }}</b>, а в банковской выписке оплачено <b>{{ formatCurrency(m.amount) }}</b>.
                </div>
                <v-checkbox
                  v-model="m.approve_amount_diff"
                  density="compact"
                  hide-details
                  color="warning"
                  label="Согласовать расхождение и скорректировать сумму закупки под выписку"
                  class="mt-1"
                  @update:model-value="(val) => { m.selected = Boolean(val) }"
                />
              </v-alert>

              <!-- Реквизиты платёжки (получатель, направление расходов и назначение платежа) -->
              <div class="bg-grey-lighten-4 pa-2 rounded mb-2 text-body-2">
                <div>
                  <b>Получатель:</b> {{ m.payee_name || 'Не указан' }}
                  <span v-if="m.payee_inn" class="text-caption text-medium-emphasis">(ИНН: {{ m.payee_inn }})</span>
                </div>
                <div v-if="m.expense_direction" class="text-caption text-primary mt-1" style="line-height: 1.3;">
                  <b>Направление расходов (выписка):</b> {{ m.expense_direction }}
                </div>
                <div class="mt-1" style="white-space: normal; word-break: break-word; line-height: 1.35;">
                  <b>Назначение платежа:</b> {{ m.purpose_text || '—' }}
                </div>
              </div>

              <!-- Выбор альтернативной комбинации (если найдено несколько вариантов) -->
              <div v-if="m.alternatives && m.alternatives.length > 1" class="d-flex align-center flex-wrap gap-2 mb-2 pa-2 rounded bg-purple-lighten-5">
                <span class="text-caption font-weight-bold text-deep-purple">Вариант подбора:</span>
                <v-btn-toggle
                  :model-value="m.combo.purchase_ids.join(',')"
                  mandatory
                  density="compact"
                  color="deep-purple"
                  variant="outlined"
                  @update:model-value="(val) => selectAlternative(m, String(val))"
                >
                  <v-btn
                    v-for="(alt, aIdx) in m.alternatives"
                    :key="alt.purchase_ids.join(',')"
                    :value="alt.purchase_ids.join(',')"
                    size="x-small"
                  >
                    Вариант {{ aIdx + 1 }} ({{ alt.count }} поз.)
                  </v-btn>
                </v-btn-toggle>
              </div>

              <!-- Что входит в закупку (список позиций) -->
              <div class="pl-2" style="border-left: 3px solid #7c4dff;">
                <div class="text-caption font-weight-bold mb-1 text-grey-darken-2">
                  ЧТО ВХОДИТ В ЗАКУПКУ:
                </div>
                <div
                  v-for="it in m.combo.items"
                  :key="it.purchase_id"
                  class="d-flex align-center justify-space-between flex-wrap gap-1 text-body-2 py-1 border-b"
                >
                  <div class="d-flex align-center flex-wrap gap-1">
                    <v-chip size="x-small" variant="outlined" :color="it.is_temp_plan ? 'deep-purple' : 'primary'">
                      {{ it.registry_number || `#${it.purchase_id}` }}
                    </v-chip>
                    <v-chip v-if="it.is_temp_plan" size="x-small" color="deep-purple" variant="flat">
                      План закупок («Да») · временная закупка
                    </v-chip>
                    <span class="font-weight-medium">{{ it.subject || '—' }}</span>
                    <v-chip v-if="!it.contractor_name" size="x-small" color="orange" variant="tonal">
                      без контрагента → подставится {{ m.payee_name || m.payee_inn }}
                    </v-chip>
                    <div v-if="it.feo_category_name" class="text-caption text-medium-emphasis w-100 mt-1" style="line-height: 1.3;">
                      <v-icon icon="mdi-folder-outline" size="13" class="mr-1" />{{ it.feo_category_name }} › <b>{{ it.subject || '—' }}</b>
                    </div>
                  </div>
                  <span class="font-weight-bold ml-auto">{{ formatCurrency(it.amount) }}</span>
                </div>
              </div>

              <!-- Обоснование и чекбокс слияния -->
              <div class="d-flex align-center justify-space-between flex-wrap gap-2 mt-2 pt-1">
                <span class="text-caption text-medium-emphasis">
                  💡 {{ m.combo.coherence_reason }}
                </span>
                <v-checkbox
                  v-if="m.combo.count > 1"
                  v-model="m.merge_purchases"
                  density="compact"
                  hide-details
                  color="deep-purple"
                  label="Объединить эти позиции в одну закупку"
                  class="text-caption"
                />
              </div>
            </v-card>
          </div>
        </template>
      </v-card-text>

      <v-divider />

      <v-card-actions class="pa-4">
        <v-spacer />
        <v-btn variant="text" :disabled="applying" @click="visible = false">Отмена</v-btn>
        <v-btn
          color="deep-purple"
          variant="flat"
          :disabled="selectedCount === 0"
          :loading="applying"
          @click="applyMatches"
        >
          Применить выбранные комбинации ({{ selectedCount }})
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useDisplay } from 'vuetify'
import {
  useSubsidyPaymentControl,
  type PaymentControlBatchComboMatch,
} from '@/composables/subsidies/useSubsidyPaymentControl'
import { formatCurrency } from '@/composables/subsidies/format'
import { useToast } from '@/composables/useToast'

const props = defineProps<{
  subsidyId: number | null | undefined
  onApplied?: () => void
}>()

const emit = defineEmits<{
  (e: 'applied'): void
}>()

const { mobile } = useDisplay()
const control = useSubsidyPaymentControl()
const { success: showSuccess, error: showError } = useToast()

const visible = ref(false)
const loading = ref(false)
const applying = ref(false)
const error = ref('')
const unattachedCount = ref(0)

interface SelectableMatch extends PaymentControlBatchComboMatch {
  selected: boolean
  merge_purchases: boolean
  approve_amount_diff: boolean
}

const matches = ref<SelectableMatch[]>([])

const selectedCount = computed(() => matches.value.filter((m) => m.selected).length)

function fmtDate(d: string | null): string {
  if (!d) return ''
  return new Date(d).toLocaleDateString('ru-RU')
}

function fmtDelta(delta: number): string {
  const sign = delta > 0 ? '+' : ''
  return `${sign}${delta.toFixed(2).replace('.', ',')} ₽`
}

function probColor(prob: string): string {
  if (prob === 'high') return 'success'
  if (prob === 'medium') return 'info'
  if (prob === 'needs_approval') return 'warning'
  return 'grey'
}

function onToggleSelect(m: SelectableMatch, val: boolean) {
  if (m.combo.needs_amount_approval || Math.abs(m.combo.delta) > 0.0001) {
    m.approve_amount_diff = val
  }
}

function selectAllExact() {
  matches.value.forEach((m) => {
    const needsApproval = Boolean(m.combo.needs_amount_approval || Math.abs(m.combo.delta) > 0.0001)
    if (!needsApproval) {
      m.selected = true
    }
  })
}

function selectAll(val: boolean) {
  matches.value.forEach((m) => {
    m.selected = val
    if (!val) m.approve_amount_diff = false
  })
}

function selectAlternative(m: SelectableMatch, idsKey: string) {
  if (!m.alternatives) return
  const found = m.alternatives.find((a) => a.purchase_ids.join(',') === idsKey)
  if (found) {
    m.combo = found
    if (found.needs_amount_approval || Math.abs(found.delta) > 0.0001) {
      m.selected = false
      m.approve_amount_diff = false
    }
  }
}

async function open() {
  if (!props.subsidyId) return
  visible.value = true
  loading.value = true
  error.value = ''
  matches.value = []
  try {
    const res = await control.getBatchCombos(props.subsidyId)
    unattachedCount.value = res.unattached_payments_count
    matches.value = res.matches.map((m) => {
      const needsApproval = Boolean(m.combo.needs_amount_approval || Math.abs(m.combo.delta) > 0.0001)
      return {
        ...m,
        selected: !needsApproval && m.combo.probability === 'high',
        merge_purchases: true,
        approve_amount_diff: false,
      }
    })
  } catch (e: any) {
    error.value = e?.message || 'Не удалось выполнить поиск комбинаций'
  } finally {
    loading.value = false
  }
}

async function applyMatches() {
  if (!props.subsidyId) return
  const selected = matches.value.filter((m) => m.selected)
  if (!selected.length) return

  applying.value = true
  error.value = ''
  try {
    const payload = selected.map((m) => ({
      bank_payment_id: m.bank_payment_id,
      purchase_ids: m.combo.purchase_ids,
      merge_purchases: m.merge_purchases,
      approve_amount_diff: Boolean(m.approve_amount_diff || m.combo.needs_amount_approval || Math.abs(m.combo.delta) > 0.0001),
    }))
    const res = await control.batchApplyCombos(props.subsidyId, payload)
    if (res.applied > 0) {
      showSuccess(`Успешно привязано комбинаций оплат: ${res.applied}. Закупки переведены в «Оплачено».`)
    }
    if (res.errors && res.errors.length > 0) {
      showError(`Ошибки при привязке (${res.errors.length}): ${res.errors.map((e: any) => e.error).join('; ')}`)
    }
    visible.value = false
    emit('applied')
    props.onApplied?.()
    window.dispatchEvent(new CustomEvent('subsidy-data-changed', { detail: { subsidyId: props.subsidyId } }))
  } catch (e: any) {
    error.value = e?.message || 'Ошибка применения комбинаций'
  } finally {
    applying.value = false
  }
}

defineExpose({ open })
</script>
