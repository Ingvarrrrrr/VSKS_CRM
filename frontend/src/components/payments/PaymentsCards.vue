<template>
  <div>
    <v-row dense>
      <v-col v-for="item in items" :key="item.id" cols="12" sm="6" md="4" lg="3">
        <v-card variant="outlined" class="h-100 d-flex flex-column" hover>
          <v-card-item class="pb-1">
            <v-card-title class="text-body-2 d-flex align-center ga-2 flex-wrap">
              <span class="font-weight-bold">{{ item.payment_number || ('#' + item.id) }}</span>
              <v-chip size="x-small" :color="statusColor(item.status)" variant="tonal">
                {{ item.status || '—' }}
              </v-chip>
            </v-card-title>
          </v-card-item>
          <v-card-text class="py-1 flex-grow-1">
            <!-- Получатель -->
            <div class="text-caption text-medium-emphasis">Получатель</div>
            <div class="text-body-2 mb-1" style="overflow-wrap:anywhere">
              {{ item.payee_name_resolved || item.payee_name || '—' }}
            </div>
            <div v-if="item.payee_inn" class="text-caption text-medium-emphasis mb-2">ИНН {{ item.payee_inn }}</div>
            <!-- Сумма и дата -->
            <div class="d-flex flex-wrap ga-3 mt-1 mb-2">
              <div>
                <div class="text-caption text-medium-emphasis">Сумма</div>
                <div class="text-body-2 font-weight-bold">{{ formatMoney(item.amount) }}</div>
              </div>
              <div>
                <div class="text-caption text-medium-emphasis">Дата</div>
                <div class="text-body-2">{{ fmtDate(item.payment_date) }}</div>
              </div>
            </div>
            <!-- Договор (авто) -->
            <div v-if="docDisplay(item) !== '—'" class="text-caption text-medium-emphasis mb-1">
              {{ docDisplay(item) }}
            </div>
            <!-- Match badges -->
            <div class="d-flex flex-wrap ga-1 mt-1">
              <v-chip
                v-if="item.matched_contract_id"
                size="x-small" color="success" variant="tonal" prepend-icon="mdi-check"
              >Сматчен</v-chip>
              <v-chip v-else size="x-small" color="grey" variant="tonal">Не сматчен</v-chip>
              <v-chip
                v-if="item.matched_confirmed"
                size="x-small" color="blue" variant="tonal" prepend-icon="mdi-check-decagram"
              >Подтверждён</v-chip>
            </div>
          </v-card-text>
          <v-divider />
          <v-card-actions class="py-1" @click.stop>
            <v-spacer />
            <!-- Confirm button (only if matched) -->
            <v-btn
              v-if="can(ACTIONS.PAYMENT_CONFIRM!)"
              icon
              size="x-small"
              variant="text"
              color="success"
              :disabled="!item.matched_contract_id"
              :title="item.matched_contract_id ? 'Подтвердить' : 'Сначала привяжите договор'"
              @click.stop="emit('confirm', item)"
            >
              <v-icon>mdi-check</v-icon>
            </v-btn>
            <!-- Match/re-link button -->
            <v-btn
              icon
              size="x-small"
              variant="text"
              color="primary"
              title="Привязать договор"
              @click.stop="emit('match', item)"
            >
              <v-icon>mdi-link-variant</v-icon>
            </v-btn>
            <!-- Unbind button -->
            <v-btn
              v-if="can(ACTIONS.PAYMENT_UNBIND!) && item.matched_confirmed"
              icon
              size="x-small"
              variant="text"
              color="warning"
              title="Откатить подтверждение"
              :loading="unbindingId === item.id"
              @click.stop="emit('unbind', item)"
            >
              <v-icon>mdi-undo</v-icon>
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-col>
    </v-row>
    <div v-if="!items.length" class="text-center py-10">
      <v-icon icon="mdi-bank-outline" size="48" color="grey-lighten-1" class="mb-3" />
      <div class="text-medium-emphasis">Платежи не найдены</div>
      <div class="text-caption">Измените параметры фильтра</div>
    </div>
    <v-pagination
      v-if="totalPages > 1"
      v-model="page"
      :length="totalPages"
      density="compact"
      total-visible="7"
      class="d-flex justify-center mt-4"
    />
  </div>
</template>

<script setup lang="ts">
import { useAuthStore } from '@/stores/auth'
import { ACTIONS } from '@/constants/permissionActions'
import type { BankPayment } from '@/composables/payments/paymentsTypes'
import { fmtDate, formatMoney, docDisplay, statusColor } from '@/composables/payments/paymentsFormat'

const authStore = useAuthStore()
function can(action: string) {
  return authStore.hasAction?.(action) ?? true
}

const page = defineModel<number>('page', { required: true })

defineProps<{
  items: BankPayment[]
  totalPages: number
  unbindingId: number | null
}>()

const emit = defineEmits<{
  confirm: [item: BankPayment]
  match: [item: BankPayment]
  unbind: [item: BankPayment]
}>()
</script>
