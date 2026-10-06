<template>
  <!-- Ничего не показываем, если pending-запросов нет — владелец, задание 04.10.2026 -->
  <v-alert
    v-if="confirmations.items.value.length"
    type="warning"
    variant="tonal"
    density="comfortable"
    class="paid-confirmations-panel mb-4"
    icon="mdi-bank-check"
  >
    <div class="text-subtitle-1 font-weight-bold mb-3">
      Оплата найдена в выписке — подтвердите перевод в «Оплачено» ({{ confirmations.items.value.length }})
    </div>

    <div v-if="confirmations.loading.value" class="d-flex align-center py-2">
      <v-progress-circular indeterminate size="20" width="2" color="primary" class="mr-2" />
      <span class="text-caption text-medium-emphasis">Загрузка…</span>
    </div>

    <v-card
      v-for="row in visibleRows"
      :key="row.id"
      variant="outlined"
      class="mb-2 pa-3 bg-surface"
    >
      <div class="d-flex align-center flex-wrap gap-2 mb-1">
        <router-link :to="`/orders/${row.purchase.id}/edit`" target="_blank" class="font-weight-bold text-decoration-none">
          {{ row.purchase.registry_number || `Закупка #${row.purchase.id}` }}
        </router-link>
        <span class="text-body-2">— {{ row.purchase.subject || '—' }}</span>
      </div>
      <div class="text-caption text-medium-emphasis mb-2">
        {{ row.purchase.contractor_name || 'Контрагент не указан' }}
        · договор {{ formatCurrency(row.purchase.contract_price || 0) }}
        · оплачено по выписке {{ formatCurrency(row.purchase.payment_amount || 0) }}
        <template v-if="row.purchase.status_label"> · сейчас: {{ row.purchase.status_label }}</template>
      </div>

      <v-table density="compact" class="mb-2">
        <thead>
          <tr>
            <th>Дата</th>
            <th>№ платёжки</th>
            <th class="text-right">Сумма</th>
            <th>Назначение</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="pm in row.payments" :key="pm.id">
            <td class="text-no-wrap">{{ fmtDate(pm.payment_date) }}</td>
            <td>{{ pm.document_number || '—' }}</td>
            <td class="text-right text-no-wrap">{{ formatCurrency(pm.amount || 0) }}</td>
            <td style="max-width:320px">
              <PaymentPurposeCell :text="pm.payment_purpose" />
            </td>
          </tr>
        </tbody>
      </v-table>

      <v-alert v-if="row.blocked_reason" type="warning" variant="tonal" density="compact" class="mb-2 text-caption">
        Подтвердить пока нельзя: {{ row.blocked_reason }}
      </v-alert>

      <v-alert v-if="checkErrors[row.id]" type="error" variant="tonal" density="compact" class="mb-2 text-caption">
        Не удалось проверить: {{ checkErrors[row.id] }}
        <v-btn size="x-small" variant="text" class="ml-2" @click="retryCheck(row.id)">Повторить проверку</v-btn>
      </v-alert>

      <div v-if="row.plan_excess_warning" class="text-caption text-error mb-2 d-flex align-center flex-wrap ga-2">
        <span><v-icon icon="mdi-alert-circle-outline" size="14" class="mr-1" />Превышение плана не согласовано: {{ row.plan_excess_warning }}</span>
        <!-- «Где взять деньги» (план .planning/quick/2026-10-05-funding-sources/
             PLAN.md, п.2б) — у строки нет готовой категории закупки, подбираем
             через GET /purchases/{id}/funding-hint (useFundingSources.ts). -->
        <v-btn size="x-small" variant="text" color="deep-purple" prepend-icon="mdi-cash-sync"
          @click="funding.openFundingSourcesForPurchase(row.subsidy_id, row.purchase.id)"
        >Где взять деньги</v-btn>
      </div>

      <div class="d-flex flex-wrap gap-2 confirm-actions">
        <v-btn
          size="small"
          :color="row.blocked_reason ? undefined : 'success'"
          variant="flat"
          prepend-icon="mdi-check"
          class="confirm-btn"
          style="white-space: normal; height: auto"
          :loading="confirmations.actingId.value === row.id"
          :disabled="!row.checked || !!row.blocked_reason || (confirmations.actingId.value !== null && confirmations.actingId.value !== row.id)"
          @click="onConfirm(row)"
        >
          Подтвердить → Оплачено
        </v-btn>
        <span v-if="!row.checked && !checkErrors[row.id]" class="d-flex align-center text-caption text-medium-emphasis">
          <v-progress-circular indeterminate size="14" width="2" class="mr-1" />проверяю…
        </span>
        <v-btn
          size="small"
          color="error"
          variant="tonal"
          prepend-icon="mdi-close"
          class="confirm-btn"
          :loading="false"
          :disabled="confirmations.actingId.value !== null"
          @click="openRejectDialog(row)"
        >
          Не та оплата
        </v-btn>
      </div>
      <div v-if="row.purchase.status !== 'delivered'" class="text-caption text-medium-emphasis mt-1">
        Подтверждение отметит поставку и переведёт в «Оплачено»
      </div>
    </v-card>

    <div v-if="visibleCount < confirmations.items.value.length" class="d-flex justify-center mt-2">
      <v-btn size="small" variant="tonal" @click="showMore">
        Показать ещё {{ Math.min(PAGE_SIZE, confirmations.items.value.length - visibleCount) }}
      </v-btn>
    </div>
  </v-alert>

  <!-- Диалог отклонения — комментарий обязателен (контракт бэкенда) -->
  <v-dialog v-model="rejectDialog" max-width="480" persistent>
    <v-card>
      <v-card-title class="text-subtitle-1 font-weight-bold pa-4">
        Не та оплата
      </v-card-title>
      <v-card-text class="pa-4 pt-0">
        <v-textarea
          v-model="rejectComment"
          label="Комментарий — почему эта оплата не подходит"
          variant="outlined"
          density="compact"
          rows="3"
          auto-grow
          :rules="[(v: string) => !!v?.trim() || 'Комментарий обязателен']"
        />
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="rejectDialog = false">Отмена</v-btn>
        <v-btn
          color="error"
          variant="flat"
          :disabled="!rejectComment.trim()"
          :loading="rejecting"
          @click="submitReject"
        >
          Отклонить
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
// Задание владельца 04.10.2026: панель на странице «Субсидии» для согласующих —
// видят запросы «подтвердите перевод в Оплачено» по найденным в выписке
// платежам и подтверждают/отклоняют их. Логика запросов — в
// usePaidConfirmations.ts (ПРАВИЛО №6, тот же composable использует плашка в
// карточке закупки, components/PaymentsBlock.vue).
import { computed, ref, watch } from 'vue'
import { usePaidConfirmations, type PaidConfirmation } from '@/composables/subsidies/usePaidConfirmations'
import { formatCurrency } from '@/composables/subsidies/format'
import { useToast } from '@/composables/useToast'
import { describeApiError } from '@/utils/apiErrorMessage'
import PaymentPurposeCell from '@/components/subsidies/PaymentPurposeCell.vue'
import { useFundingSources } from '@/composables/subsidies/useFundingSources'

const props = defineProps<{ subsidyId: number | null | undefined }>()

const toast = useToast()
const confirmations = usePaidConfirmations()
const funding = useFundingSources()

// Перф-доработка 2026-10-06: список может прийти с десятками/сотней строк,
// каждая без реальной проверки (checked=false, см. usePaidConfirmations.ts).
// Показываем порциями по PAGE_SIZE и проверяем показанные порциями того же
// размера, ПОСЛЕДОВАТЕЛЬНО (не параллельно — не грузить сервер одним залпом
// запросов). Ошибка проверки одной порции — показываем причину у затронутых
// строк, не глотаем generic-ом.
const PAGE_SIZE = 10
const visibleCount = ref(PAGE_SIZE)
const checkErrors = ref<Record<number, string>>({})
const visibleRows = computed(() => confirmations.items.value.slice(0, visibleCount.value))

async function checkUncheckedVisible() {
  const pending = visibleRows.value.filter(r => !r.checked && !checkErrors.value[r.id])
  for (let i = 0; i < pending.length; i += PAGE_SIZE) {
    const chunk = pending.slice(i, i + PAGE_SIZE).map(r => r.id)
    if (!chunk.length) continue
    try {
      await confirmations.checkRows(props.subsidyId, chunk)
    } catch (e: any) {
      const msg = describeApiError(e, { fallback: 'не удалось проверить' })
      const next = { ...checkErrors.value }
      for (const id of chunk) next[id] = msg
      checkErrors.value = next
    }
  }
}

function showMore() {
  visibleCount.value += PAGE_SIZE
  checkUncheckedVisible()
}

function retryCheck(id: number) {
  const next = { ...checkErrors.value }
  delete next[id]
  checkErrors.value = next
  checkUncheckedVisible()
}

function fmtDate(d: string | null): string {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('ru-RU')
}

async function onConfirm(row: PaidConfirmation) {
  try {
    await confirmations.confirm(row.id)
    toast.success(`Закупка ${row.purchase.registry_number || '#' + row.purchase.id} переведена в «Оплачено»`)
  } catch (e: any) {
    toast.addToast(describeApiError(e, { fallback: 'Не удалось подтвердить оплату' }), 'error')
  }
}

const rejectDialog = ref(false)
const rejectComment = ref('')
const rejecting = ref(false)
const rejectTarget = ref<PaidConfirmation | null>(null)

function openRejectDialog(row: PaidConfirmation) {
  rejectTarget.value = row
  rejectComment.value = ''
  rejectDialog.value = true
}

async function submitReject() {
  if (!rejectTarget.value || !rejectComment.value.trim()) return
  rejecting.value = true
  try {
    await confirmations.reject(rejectTarget.value.id, rejectComment.value.trim())
    toast.info('Запрос на подтверждение оплаты отклонён')
    rejectDialog.value = false
  } catch (e: any) {
    toast.addToast(describeApiError(e, { fallback: 'Не удалось отклонить запрос' }), 'error')
  } finally {
    rejecting.value = false
  }
}

watch(() => props.subsidyId, async (id) => {
  visibleCount.value = PAGE_SIZE
  checkErrors.value = {}
  await confirmations.loadPending(id)
  await checkUncheckedVisible()
}, { immediate: true })
</script>

<style scoped>
.paid-confirmations-panel :deep(.v-alert__content) {
  width: 100%;
}

/* Узкий экран (~400px): кнопки в столбик на всю ширину, текст не обрезается */
@media (max-width: 440px) {
  .confirm-actions {
    flex-direction: column;
    align-items: stretch;
  }
  .confirm-actions .confirm-btn {
    width: 100%;
  }
}
</style>
