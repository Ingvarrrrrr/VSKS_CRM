<template>
  <v-card v-if="wishId" variant="outlined" class="mb-4">
    <v-card-title class="text-subtitle-1 d-flex align-center gap-2">
      <v-icon size="20">mdi-file-document-check-outline</v-icon>
      Заявка на возмещение
      <v-chip v-if="wish" size="small" variant="tonal" :color="statusColor" class="ml-1">{{ statusLabel }}</v-chip>
      <v-spacer />
      <v-btn size="small" color="primary" variant="flat" prepend-icon="mdi-send" :loading="submitting"
        :disabled="!canSubmit" @click="submit">
        Отправить на согласование
      </v-btn>
    </v-card-title>
    <v-card-text class="pt-0">
      <div v-if="wish?.status === 'submitted' && wish.approver_names?.length" class="text-caption text-medium-emphasis">
        Согласующие: {{ wish.approver_names.join(', ') }}
      </div>
      <div v-if="!wish" class="text-caption text-medium-emphasis">Загрузка статуса…</div>
      <v-alert v-if="!hasReceipts" type="info" variant="tonal" density="compact" class="mt-2">
        Прикрепите чеки перед отправкой
      </v-alert>
      <div v-if="itemsCount === 0" class="text-caption text-medium-emphasis mt-2">
        В отчёте нет ни одной позиции — добавьте хотя бы одну, чтобы отправить заявку.
      </div>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
// Карточка заявки-компаньона авансового отчёта (владелец, опрос 2026-09-15):
// показывает статус заявки-возмещения и кнопку ручной отправки на
// согласование. Логика — в composables/purchase/useAdvanceReimbursement.ts,
// здесь только разметка (mirrors PurchaseLinkedTasksCard.vue).
import type { Receipt, ReceiptFile } from '@/composables/purchase/usePurchaseReceipts'
import type { ToastType } from '@/composables/useToast'
import { toRef } from 'vue'
import { useAdvanceReimbursement } from '@/composables/purchase/useAdvanceReimbursement'

const props = defineProps<{
  purchaseId: number | null
  wishId: number | null | undefined
  itemsCount: number
  receipts: Receipt[]
  receiptFiles: ReceiptFile[]
  showSnack: (text: string, color?: ToastType) => void
}>()

const { wish, submitting, statusLabel, statusColor, hasReceipts, canSubmit, submit } = useAdvanceReimbursement(
  toRef(props, 'wishId'),
  toRef(props, 'itemsCount'),
  toRef(props, 'receipts'),
  toRef(props, 'receiptFiles'),
  props.showSnack,
)
</script>
