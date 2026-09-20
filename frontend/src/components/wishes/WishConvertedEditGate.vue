<template>
  <v-dialog :model-value="modelValue" max-width="520" @update:model-value="(v: boolean) => $emit('update:modelValue', v)">
    <v-card>
      <v-card-title class="d-flex align-center ga-2">
        <v-icon color="warning">mdi-lock-alert-outline</v-icon>
        Состав согласованной заявки заблокирован
      </v-card-title>
      <v-card-text>
        <div>
          Состав согласованной заявки меняется только через возврат на доработку. Закупки,
          созданные из неё ({{ purchasesCount }} шт.), будут скрыты и вернутся с той же
          разбивкой после повторного согласования.
        </div>
        <v-alert v-if="reason" type="error" variant="tonal" density="compact" class="mt-3">
          {{ reason }}
        </v-alert>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="tonal" color="default" @click="$emit('update:modelValue', false)">Отмена</v-btn>
        <v-tooltip :disabled="canReturn" location="top" text="Доступно менеджеру или администратору">
          <template #activator="{ props: tipProps }">
            <span v-bind="tipProps">
              <v-btn
                variant="flat"
                color="warning"
                :disabled="!canReturn"
                :loading="loading"
                @click="$emit('confirm-return')"
              >
                Вернуть на доработку
              </v-btn>
            </span>
          </template>
        </v-tooltip>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
// WishConvertedEditGate.vue — понятный гейт вместо голого сообщения (владелец,
// лист 2 №4, 2026-09-20). Показывается в двух случаях, оба из WishFormDialog.vue:
// 1) состав заявки УЖЕ заблокирован (editingWish.contracted_locked — поля формы
//    disabled) — плашка-кнопка над таблицей позиций открывает этот диалог сразу;
// 2) PUT /wishes/{id} вернул 409 при попытке сохранить изменённый состав
//    approved/converted заявки, которую отклонить обычным способом бэк ещё не
//    даёт (см. useWishForm.ts::saveWish catch) — тогда `reason` содержит сырой
//    текст ошибки сервера (например, какая конкретно закупка блокирует откат).
// «Вернуть на доработку» переиспользует СУЩЕСТВУЮЩЕЕ действие «Отклонить»
// (actions.openRejectDialog, POST /wishes/{id}/reject) — единственный маршрут,
// которым бэк уже умеет снимать approved/converted обратно в редактируемый
// статус вне обычного submitted (backend/app/routers/wish_transitions.py:
// SaaS может отклонить заявку в любом статусе, включая converted) — второго
// механизма не заводим (Правило №6). Именно поэтому кнопка активна только для
// isSaas — иначе бэк ответит 400, и это не тот маршрут, который стоит предлагать.
defineProps<{
  modelValue: boolean
  purchasesCount: number
  reason?: string | null
  canReturn: boolean
  loading?: boolean
}>()
defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'confirm-return'): void
}>()
</script>
