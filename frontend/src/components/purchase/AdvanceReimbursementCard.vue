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
      <div v-if="!wish" class="text-caption text-medium-emphasis">Загрузка статуса…</div>
      <v-alert v-if="!hasReceipts" type="info" variant="tonal" density="compact" class="mt-2">
        Прикрепите чеки перед отправкой
      </v-alert>
      <div v-if="itemsCount === 0" class="text-caption text-medium-emphasis mt-2">
        В отчёте нет ни одной позиции — добавьте хотя бы одну, чтобы отправить заявку.
      </div>

      <!-- Раздел «Согласующие» — владелец, прод-инцидент с заявкой №85
           (2026-09-29): цепочка НЕ строится сама на «Отправить», только этой
           кнопкой «Построить цепочку». Тот же механизм и те же эндпоинты
           (/wishes/{id}/approvers*), что и у обычной заявки — ПРАВИЛО №6,
           см. composables/purchase/useAdvanceReimbursement.ts. -->
      <v-divider class="my-3" />
      <div class="text-subtitle-2 d-flex align-center ga-1 mb-1">
        <v-icon size="18" class="mr-1">mdi-account-check</v-icon>
        Согласующие
        <v-chip class="ml-2" size="x-small" variant="tonal">{{ approvers.length }}</v-chip>
        <v-spacer />
        <v-chip v-if="approvers.length" size="x-small" :color="approvalMode === 'sequential' ? 'blue' : 'teal'" variant="tonal">
          {{ approvalMode === 'sequential' ? 'Последовательно' : 'Параллельно' }}
        </v-chip>
      </div>

      <template v-if="isEditable">
        <div class="text-caption text-medium-emphasis mb-2">
          Выберите верхнего согласующего — система подтянет восходящую цепочку начальников снизу вверх.
          Построение цепочки НЕ отправляет заявку: на согласование она уйдёт только по кнопке «Отправить на согласование».
        </div>
        <v-row dense align="center">
          <v-col cols="12" md="6">
            <v-autocomplete
              v-model="approverTopUser"
              :items="orgUsers"
              item-title="full_name"
              item-value="id"
              label="Верхний согласующий"
              variant="outlined"
              density="compact"
              clearable
              hide-details
            />
          </v-col>
          <v-col cols="12" md="3">
            <v-select
              v-model="approvalMode"
              :items="[
                { value: 'sequential', title: 'Последовательно' },
                { value: 'parallel', title: 'Параллельно' },
              ]"
              label="Режим"
              variant="outlined"
              density="compact"
              hide-details
            />
          </v-col>
          <v-col cols="12" md="3">
            <v-btn
              color="primary"
              variant="flat"
              block
              :loading="cascadeLoading"
              :disabled="!approverTopUser"
              prepend-icon="mdi-sitemap"
              @click="runCascade"
            >Построить цепочку</v-btn>
          </v-col>
        </v-row>
        <v-divider class="my-3" />
      </template>

      <div v-if="approvers.length === 0" class="text-caption text-medium-emphasis">
        Согласующие ещё не назначены. Без хотя бы одного согласующего отправить нельзя.
      </div>
      <div v-else class="d-flex flex-column" style="gap:10px">
        <v-sheet v-for="(a, ai) in approvers" :key="a.id" rounded="lg" border class="pa-3">
          <div class="d-flex align-center flex-wrap" style="gap:8px">
            <v-chip size="x-small" variant="tonal" color="grey">#{{ a.order_num + 1 }}</v-chip>
            <span class="font-weight-medium">{{ a.full_name || '—' }}</span>
            <span v-if="a.role_name" class="text-caption text-medium-emphasis">{{ a.role_name }}</span>
            <v-chip v-if="!a.is_auto" size="x-small" variant="tonal" color="purple">вручную</v-chip>
            <v-spacer />
            <v-chip size="small" :color="approvalStatusColor[a.status]" variant="tonal">
              {{ approvalStatusLabel[a.status] || a.status }}
            </v-chip>
            <v-btn v-if="a.status === 'pending' && isEditable" icon="mdi-close" size="x-small" variant="text"
              @click="removeApprover(a.id)" />
          </div>
          <div v-if="approverDecisionLine(a)" class="text-caption text-medium-emphasis mt-1">
            {{ approverDecisionLine(a) }}
          </div>
          <div v-if="a.comment" class="text-caption text-medium-emphasis mt-1">Комментарий: {{ a.comment }}</div>

          <!-- Решение текущего пользователя — «согласовать за себя» без причины,
               «за другого» требует комментарий (тот же гейт, что и у обычной
               заявки, backend/app/routers/wish_approvals.py::decide_wish_approval). -->
          <div v-if="canDecideApprover(a)" class="mt-2">
            <div v-if="isDecidingOnBehalf(a)" class="text-caption text-orange-darken-3 mb-1 d-flex align-center" style="gap:4px">
              <v-icon size="14">mdi-account-arrow-right</v-icon>
              Вы решаете за {{ a.full_name || 'назначенного согласующего' }}
            </div>
            <v-textarea
              v-model="decideComment[a.id]"
              :label="isDecidingOnBehalf(a) ? 'Причина решения за другого (обязательно)' : 'Комментарий (необязательно при согласовании, обязателен при отказе)'"
              variant="outlined"
              density="compact"
              rows="2"
              auto-grow
              hide-details
              class="mb-1"
            />
            <div v-if="isDecidingOnBehalf(a) && !(decideComment[a.id] || '').trim()" class="text-caption text-red mb-2">
              Укажите причину — например, что согласующий в отпуске или поручил вам решение.
            </div>
            <div v-else class="mb-2" />
            <div class="d-flex" style="gap:8px">
              <v-btn color="green" variant="flat" size="small" :loading="decideLoading === a.id"
                :disabled="isDecidingOnBehalf(a) && !(decideComment[a.id] || '').trim()"
                prepend-icon="mdi-check" @click="decideApprover(a.id, 'approved')">Согласовать</v-btn>
              <v-btn color="red" variant="tonal" size="small" :loading="decideLoading === a.id"
                :disabled="!decideComment[a.id]"
                prepend-icon="mdi-close" @click="decideApprover(a.id, 'rejected')">Отклонить</v-btn>
            </div>
          </div>
        </v-sheet>
      </div>

      <template v-if="isEditable || wish?.status === 'submitted'">
        <v-divider class="my-3" />
        <v-autocomplete
          v-model="approverToAdd"
          :items="orgUsers"
          item-title="full_name"
          item-value="id"
          label="Добавить согласующего"
          variant="outlined"
          density="compact"
          clearable
          hide-details
          @update:model-value="(val: number | null) => { if (val) addApprover(val) }"
        />
      </template>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
// Карточка заявки-компаньона авансового отчёта (владелец, опрос 2026-09-15):
// показывает статус заявки-возмещения, кнопку ручной отправки на согласование
// и раздел «Согласующие» (владелец, прод-инцидент с заявкой №85, 2026-09-29 —
// у компаньона раньше не было этого раздела вовсе, submit сам строил цепочку
// без единого нажатия кнопки). Логика — в composables/purchase/
// useAdvanceReimbursement.ts (те же REST-эндпоинты /wishes/{id}/approvers*,
// что и у обычной заявки, ПРАВИЛО №6 — второй механизм не заводим), здесь
// только разметка (mirrors PurchaseLinkedTasksCard.vue).
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
  orgUsers: { id: number; full_name: string }[]
  currentUserId: number
  isAdmin: boolean
}>()

const {
  wish, submitting, statusLabel, statusColor, hasReceipts, canSubmit, submit,
  approvers, approverTopUser, approvalMode, cascadeLoading, approverToAdd,
  decideComment, decideLoading, approvalStatusColor, approvalStatusLabel,
  isEditable, runCascade, addApprover, removeApprover, decideApprover,
  canDecideApprover, isDecidingOnBehalf, approverDecisionLine,
} = useAdvanceReimbursement(
  toRef(props, 'wishId'),
  toRef(props, 'itemsCount'),
  toRef(props, 'receipts'),
  toRef(props, 'receiptFiles'),
  props.showSnack,
  props.currentUserId,
  toRef(props, 'isAdmin'),
)
</script>
