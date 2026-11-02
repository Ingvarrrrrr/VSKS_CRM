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
              <v-btn size="x-small" variant="text" @click="selectAll(true)">Выбрать все</v-btn>
              <v-btn size="x-small" variant="text" @click="selectAll(false)">Снять выбор</v-btn>
            </div>
          </div>

          <v-alert type="info" variant="tonal" density="compact" class="mb-3">
            Перед применением проверьте состав каждой закупки. При подтверждении система объединит позиции в одну закупку,
            проставит контрагента (ИНН) и назначение из платёжки, и зафиксирует оплату.
          </v-alert>

          <div class="d-flex flex-column gap-3">
            <v-card
              v-for="(m, idx) in matches"
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
                  <v-checkbox-btn v-model="m.selected" density="compact" color="deep-purple" />
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
                  {{ m.combo.count > 1 ? `Комбинация из ${m.combo.count} поз.` : 'Точное совпадение 1 поз.' }}
                </div>
              </div>

              <!-- Реквизиты платёжки -->
              <div class="bg-grey-lighten-4 pa-2 rounded mb-2 text-caption">
                <div>
                  <b>Получатель:</b> {{ m.payee_name || 'Не указан' }}
                  <span v-if="m.payee_inn" class="text-medium-emphasis">(ИНН: {{ m.payee_inn }})</span>
                </div>
                <div v-if="m.purpose_text" class="text-truncate text-medium-emphasis" :title="m.purpose_text">
                  <b>Назначение:</b> {{ m.purpose_text }}
                </div>
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
                    <v-chip size="x-small" variant="outlined" color="primary">
                      {{ it.registry_number || `#${it.purchase_id}` }}
                    </v-chip>
                    <span class="font-weight-medium">{{ it.subject || '—' }}</span>
                    <v-chip v-if="it.feo_category_name || it.semantic_cluster" size="x-small" variant="tonal" color="grey">
                      {{ it.feo_category_name || it.semantic_cluster }}
                    </v-chip>
                    <v-chip v-if="!it.contractor_name" size="x-small" color="orange" variant="tonal">
                      без контрагента → подставится {{ m.payee_name || m.payee_inn }}
                    </v-chip>
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

const props = defineProps<{
  subsidyId: number | null | undefined
  onApplied?: () => void
}>()

const { mobile } = useDisplay()
const control = useSubsidyPaymentControl()

const visible = ref(false)
const loading = ref(false)
const applying = ref(false)
const error = ref('')
const unattachedCount = ref(0)

interface SelectableMatch extends PaymentControlBatchComboMatch {
  selected: boolean
  merge_purchases: boolean
}

const matches = ref<SelectableMatch[]>([])

const selectedCount = computed(() => matches.value.filter((m) => m.selected).length)

function fmtDate(d: string | null): string {
  if (!d) return ''
  return new Date(d).toLocaleDateString('ru-RU')
}

function probColor(prob: string): string {
  if (prob === 'high') return 'success'
  if (prob === 'medium') return 'warning'
  return 'grey'
}

function selectAll(val: boolean) {
  matches.value.forEach((m) => {
    m.selected = val
  })
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
    matches.value = res.matches.map((m) => ({
      ...m,
      selected: m.combo.probability === 'high' || m.combo.probability === 'medium',
      merge_purchases: true,
    }))
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
    }))
    const res = await control.batchApplyCombos(props.subsidyId, payload)
    visible.value = false
    props.onApplied?.()
  } catch (e: any) {
    error.value = e?.message || 'Ошибка применения комбинаций'
  } finally {
    applying.value = false
  }
}

defineExpose({ open })
</script>
