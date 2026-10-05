<template>
  <v-alert
    v-if="confirmation && confirmation.status === 'pending'"
    type="warning"
    variant="tonal"
    density="compact"
    class="mb-3"
    icon="mdi-bank-check"
  >
    <div class="text-body-2 font-weight-medium mb-2">
      Оплата найдена в выписке, ждёт подтверждения согласующего субсидии
      <template v-if="confirmation.purchase.status_label"> · сейчас: {{ confirmation.purchase.status_label }}</template>
    </div>
    <v-alert v-if="confirmation.blocked_reason" type="warning" variant="tonal" density="compact" class="mb-2 text-caption">
      Подтвердить пока нельзя: {{ confirmation.blocked_reason }}
    </v-alert>

    <div v-if="confirmation.plan_excess_warning" class="text-caption text-error mb-2">
      <v-icon icon="mdi-alert-circle-outline" size="14" class="mr-1" />
      Превышение плана не согласовано: {{ confirmation.plan_excess_warning }}
    </div>

    <div class="d-flex flex-wrap gap-2 confirm-actions">
      <v-btn
        size="small"
        :color="confirmation.blocked_reason ? undefined : 'success'"
        variant="flat"
        prepend-icon="mdi-check"
        class="confirm-btn"
        style="white-space: normal; height: auto"
        :loading="acting"
        :disabled="acting || !!confirmation.blocked_reason"
        @click="onConfirm"
      >
        Подтвердить → Оплачено
      </v-btn>
      <v-btn
        size="small"
        color="error"
        variant="tonal"
        prepend-icon="mdi-close"
        class="confirm-btn"
        :disabled="acting"
        @click="rejectDialog = true"
      >
        Не та оплата
      </v-btn>
    </div>
    <div v-if="confirmation.purchase.status !== 'delivered'" class="text-caption text-medium-emphasis mt-1">
      Подтверждение отметит поставку и переведёт в «Оплачено»
    </div>
  </v-alert>

  <div v-else-if="confirmation && confirmation.status === 'rejected'" class="text-caption text-medium-emphasis mb-3 pa-2 bg-grey-lighten-4 rounded">
    Оплату отклонил {{ confirmation.decided_by || 'согласующий' }}, {{ fmtDate(confirmation.decided_at) }}: {{ confirmation.comment || '—' }}
  </div>

  <v-dialog v-model="rejectDialog" max-width="480" persistent>
    <v-card>
      <v-card-title class="text-subtitle-1 font-weight-bold pa-4">Не та оплата</v-card-title>
      <v-card-text class="pa-4 pt-0">
        <v-textarea
          v-model="rejectComment"
          label="Комментарий — почему эта оплата не подходит"
          variant="outlined"
          density="compact"
          rows="3"
          auto-grow
        />
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="rejectDialog = false">Отмена</v-btn>
        <v-btn
          color="error"
          variant="flat"
          :disabled="!rejectComment.trim()"
          :loading="acting"
          @click="onReject"
        >
          Отклонить
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
// Плашка в карточке закупки (блок платежей) — «оплата найдена в выписке,
// ждёт подтверждения согласующего субсидии». Задание владельца 04.10.2026.
// Логика запросов — общий composable usePaidConfirmations.ts (ПРАВИЛО №6,
// тот же, что PaidConfirmationsPanel.vue на странице «Субсидии»), не копия.
import { ref, watch } from 'vue'
import { usePaidConfirmations, type PaidConfirmation } from '@/composables/subsidies/usePaidConfirmations'
import { useToast } from '@/composables/useToast'
import { describeApiError } from '@/utils/apiErrorMessage'

const props = defineProps<{ purchaseId: number | null }>()
const emit = defineEmits<{ (e: 'changed'): void }>()

const toast = useToast()
const confirmations = usePaidConfirmations()
const confirmation = ref<PaidConfirmation | null>(null)
const acting = ref(false)
const rejectDialog = ref(false)
const rejectComment = ref('')

function fmtDate(d: string | null): string {
  if (!d) return '—'
  return new Date(d).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

async function load() {
  confirmation.value = await confirmations.loadForPurchase(props.purchaseId)
}

async function onConfirm() {
  if (!confirmation.value) return
  acting.value = true
  try {
    await confirmations.confirm(confirmation.value.id)
    toast.success('Закупка переведена в «Оплачено»')
    await load()
    emit('changed')
  } catch (e: any) {
    // 403 «не согласующий субсидии» — detail с бэкенда уже по-русски
    toast.addToast(describeApiError(e, { fallback: 'Не удалось подтвердить оплату' }), 'error')
  } finally {
    acting.value = false
  }
}

async function onReject() {
  if (!confirmation.value || !rejectComment.value.trim()) return
  acting.value = true
  try {
    await confirmations.reject(confirmation.value.id, rejectComment.value.trim())
    toast.info('Запрос на подтверждение оплаты отклонён')
    rejectDialog.value = false
    rejectComment.value = ''
    await load()
    emit('changed')
  } catch (e: any) {
    toast.addToast(describeApiError(e, { fallback: 'Не удалось отклонить запрос' }), 'error')
  } finally {
    acting.value = false
  }
}

watch(() => props.purchaseId, load, { immediate: true })
</script>

<style scoped>
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
