<template>
  <div v-if="loadError" class="mb-2 text-caption text-medium-emphasis">{{ loadError }}</div>
  <div v-if="result && result.status !== 'ok' && result.status !== 'no_payments'" class="mb-2">
    <v-alert
      v-if="result.status === 'mismatch' || result.status === 'unknown_purchase_vat'"
      type="warning" variant="tonal" density="comfortable" border="start"
    >
      <div class="text-body-2">
        НДС в платежах: <strong>{{ paymentsSummaryLabel }}</strong>
        <span class="text-medium-emphasis"> — в закупке: {{ result.purchase_vat_label }}</span>
      </div>
      <div v-if="firstPayment" class="text-caption text-medium-emphasis mt-1">
        {{ firstPayment.number ? `п/п №${firstPayment.number}` : 'платёж' }}
        <template v-if="firstPayment.date"> от {{ formatDate(firstPayment.date) }}</template>
        <template v-if="firstPayment.vat_amount != null"> — НДС {{ formatMoney(firstPayment.vat_amount) }}</template>
        <span v-if="result.payments.length > 1"> (и ещё {{ result.payments.length - 1 }})</span>
        <v-chip v-if="!firstPayment.confirmed" size="x-small" color="warning" variant="outlined" class="ml-1">
          сопоставлен автоматически, не подтверждён
        </v-chip>
      </div>
      <div class="mt-2">
        <v-btn
          v-if="result.suggested"
          size="small" color="warning" variant="flat"
          :loading="aligning"
          @click="confirmOpen = true"
        >
          Приравнять НДС к платежам
        </v-btn>
      </div>
    </v-alert>

    <v-alert
      v-else-if="result.status === 'payments_disagree'"
      type="warning" variant="tonal" density="comfortable" border="start"
    >
      <div class="text-body-2 mb-1">
        Платежи по этой закупке указывают РАЗНЫЙ НДС — не могу предложить единую ставку.
      </div>
      <ul class="text-caption text-medium-emphasis pl-4">
        <li v-for="pmt in result.payments" :key="pmt.id">
          {{ pmt.number ? `п/п №${pmt.number}` : 'платёж' }}
          <template v-if="pmt.date"> от {{ formatDate(pmt.date) }}</template>
          — {{ pmt.label }}
          <span v-if="!pmt.confirmed" class="text-warning">(не подтверждён)</span>
        </li>
      </ul>
    </v-alert>

    <v-dialog v-model="confirmOpen" max-width="440">
      <v-card>
        <v-card-title class="text-body-1">Приравнять НДС закупки к платежам?</v-card-title>
        <v-card-text class="text-body-2">
          Ставка НДС закупки будет изменена на <strong>{{ suggestedLabel }}</strong>
          (режим станет «Одинаковый на всю закупку»). Позиции закупки не меняются.
          <v-alert v-if="hasUnconfirmedPayments" type="warning" variant="tonal" density="compact" class="mt-3">
            Часть платежей, на которых основано предложение, сопоставлена с закупкой
            автоматически и ЕЩЁ НЕ подтверждена в реестре платежей.
          </v-alert>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="confirmOpen = false">Отмена</v-btn>
          <v-btn color="warning" variant="flat" :loading="aligning" @click="align">Приравнять</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
// Владелец (2026-09-26): «надо проверять НДС по выгрузке платежей: если в
// платежах НДС указан другой — сообщать, давать ссылки на закупки, где не
// соответствует НДС, и предлагать приравнять НДС тому, что в выгрузках
// платежей». Логика сверки — ИСКЛЮЧИТЕЛЬНО на бэке (app/services/
// purchase_vat_check.py), этот компонент только показывает результат и
// вызывает align-эндпоинт — второй копии сверки на фронте не заводим.
import { computed, ref, watch } from 'vue'
import { apiFetch } from '@/api'
import { useToast } from '@/composables/useToast'
import { formatMoney } from '@/utils/formatMoney'

const props = defineProps<{
  purchaseId: number | null
}>()

const emit = defineEmits<{
  aligned: []
}>()

const { success, error } = useToast()

interface VatCheckResult {
  status: 'ok' | 'mismatch' | 'unknown_purchase_vat' | 'no_payments' | 'payments_disagree'
  purchase_vat_label: string
  payments: Array<{
    id: number; number: string | null; date: string | null; amount: number
    vat_amount: number | null; rate: number | null; kind: string; label: string
    confirmed: boolean
  }>
  suggested: { vat_applicable: boolean; vat_rate: number | null } | null
}

const result = ref<VatCheckResult | null>(null)
const confirmOpen = ref(false)
const aligning = ref(false)
// 27.09: GET здесь необязателен для открытия карточки закупки — apiFetch по
// умолчанию сам открывает глобальный ApiErrorDialog на любой ошибке (см.
// api.ts::apiFetch), из-за чего сбойный/устаревший процесс backend отдавал
// модалку «Ошибка HTTP_404» поверх только что открытой закупки. Гасим
// глобальную модалку suppressErrorDialog и показываем короткий inline-текст
// на месте баннера — «Приравнять» ниже (align()) НЕ трогаем, там ошибка
// должна быть явной.
const loadError = ref<string | null>(null)

const firstPayment = computed(() => result.value?.payments?.[0] ?? null)

const paymentsSummaryLabel = computed(() => firstPayment.value?.label ?? '—')

const hasUnconfirmedPayments = computed(() => (result.value?.payments ?? []).some(p => !p.confirmed))

const suggestedLabel = computed(() => {
  const s = result.value?.suggested
  if (!s) return '—'
  return s.vat_applicable ? `${s.vat_rate}%` : 'без НДС'
})

function formatDate(d: string) {
  try {
    return new Date(d).toLocaleDateString('ru-RU')
  } catch {
    return d
  }
}

async function load() {
  loadError.value = null
  if (!props.purchaseId) {
    result.value = null
    return
  }
  try {
    result.value = await apiFetch<VatCheckResult>(`/purchases/${props.purchaseId}/vat-payment-check`, {
      suppressErrorDialog: true,
    })
  } catch (e: any) {
    // Тихо (без глобальной модалки): баннер необязателен, не мешаем открытию
    // карточки закупки ошибкой сверки — только маленький inline-текст ниже.
    result.value = null
    const status = e?.status ? ` ${e.status}` : ''
    loadError.value = `Не удалось проверить НДС по платежам:${status} ${e?.detail || e?.message || 'ошибка запроса'}`
  }
}

async function align() {
  if (!props.purchaseId || !result.value?.suggested) return
  aligning.value = true
  try {
    await apiFetch(`/purchases/${props.purchaseId}/align-vat-to-payments`, {
      method: 'POST',
      body: result.value.suggested,
    })
    success('НДС закупки приравнен к платежам')
    confirmOpen.value = false
    emit('aligned')
    await load()
  } catch (e: any) {
    error(`Не удалось приравнять НДС: ${e?.detail || e?.message || 'неизвестная ошибка'}${e?.status ? ` (HTTP ${e.status})` : ''}`, { duration: 0 })
  } finally {
    aligning.value = false
  }
}

watch(() => props.purchaseId, load, { immediate: true })

defineExpose({ reload: load })
</script>
